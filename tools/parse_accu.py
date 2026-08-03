# -*- coding: utf-8 -*-
"""
tools/parse_accu.py

解析 tools/{yr}/accu-{yr}.xls（大學考試入學分發委員會「採計組合成績人數累計表」），
建立「組合代碼 → 科目集合 → 分數區間人數累計」查詢資料庫 accu.json。

適用對象：僅限「採計科目加權皆為1.00」的系組——這類系組的「採計總分」等於
各採計科目實得分數直接加總，因此可與同一科目組合、同樣皆採計1.00加權的
全體考生成績做精確比對，查得全國名次與百分等級（PR），比114年比較法更準確。
加權不為1.00的系組（絕大多數）仍以114年比較法為輔，並標示資料來源。

科目名稱 → 本專案科目代碼對照（對照 site/app.js 的 SUBJ 清單）：
  國文→國 英文→英 數學A→數A 數學B→數B 自然→自 社會→社
  數甲→數甲 數乙→數乙 物理→物 化學→化 生物→生 歷史→歷 地理→地 公民與社會→公

  體育→體 美術(不含美術成績)→美 音樂(不含音樂成績)→音
  註：體育/美術/音樂三類為術科性質。本專案系組資料（r115.json）對術科一律用
  概化代碼「術」表示（不區分美術/音樂/體育等具體術科種類），因此刻意不將這三個
  accu 代碼對應到「術」——避免把美術系錯配到音樂或體育考生的百分等級表，
  造成資料錯誤。這類系組（術科相關）一律仍以114年比較法為輔。

輸出格式 accu.json：
  accu[yr] = [
    {
      'subjects': [科目代碼,...]（排序後的科目集合，用於比對系組是否符合）,
      'total': 該組合全國考生總人數,
      'bands': [{'upper':區間上限分數,'n':區間人數,'cum_hi':從高分到低分累計人數,
                 'cum_lo_pct':從低分到高分累計百分比(即PR值)}, ...]
      （bands 依 upper 由低到高排序，供逐一比對）
    }, ...
  ]

查詢邏輯（make_data.py 使用）：
  給定系組科目代碼集合與考生總分 total_score：
  1. 找 subjects 完全相同（排序後集合相等）的 group
  2. 在 bands（由低到高）中找第一個 upper >= total_score 的區間
     （分數區間為「上一區間上限 < 分數 <= 本區間上限」，僅最低區間為 [0, 上限] 全含）
  3. combo_rank = 該區間 cum_hi；combo_total = group['total']；combo_pr = 該區間 cum_lo_pct
"""
import json
import pandas as pd

NAME2CODE = {
    '國文': '國', '英文': '英', '數學A': '數A', '數學B': '數B', '自然': '自', '社會': '社',
    '數甲': '數甲', '數乙': '數乙', '物理': '物', '化學': '化', '生物': '生', '歷史': '歷',
    '地理': '地', '公民與社會': '公',
    '體育': '體', '美術(不含美術成績)': '美', '音樂(不含音樂成績)': '音',
}
YEARS = ['112', '113', '114', '115']


def parse_year(yr):
    df = pd.read_excel(f'{yr}/accu-{yr}.xls', header=0)
    df.columns = ['grp', 'subj', 'band', 'n', 'pct', 'cum_hi', 'cum_hi_pct', 'cum_lo', 'cum_lo_pct']
    df['subj'] = df['subj'].astype(str).str.strip()

    groups = []
    bad = []
    for grp_id, g in df.groupby('grp', sort=True):
        names = [w.strip() for w in g['subj'].iloc[0].split('、')]
        codes = []
        ok = True
        for nm in names:
            c = NAME2CODE.get(nm)
            if c is None:
                ok = False
                bad.append(f'組{grp_id}: 未知科目名稱 "{nm}"')
                break
            codes.append(c)
        if not ok:
            continue

        bands = []
        for _, row in g.iterrows():
            band_str = str(row['band']).strip()
            try:
                upper = float(band_str.split('-')[-1])
            except ValueError:
                bad.append(f'組{grp_id}: 分數區間格式異常 "{band_str}"')
                continue
            bands.append({
                'upper': upper,
                'n': int(row['n']),
                'cum_hi': int(row['cum_hi']),
                'cum_lo_pct': float(row['cum_lo_pct']),
            })
        if not bands:
            bad.append(f'組{grp_id}: 無有效分數區間')
            continue
        bands.sort(key=lambda b: b['upper'])  # 由低到高，供逐一比對第一個 >= 分數的區間
        # cum_hi（從高分到低分累計）在「最高分區間」最小（只含頂層少數人），
        # 在「最低分區間」最大（累計了全部人）；故組合總人數 = 最低分區間(bands[0])的 cum_hi
        total_n = bands[0]['cum_hi']

        codes_sorted = sorted(codes)
        # 同一科目集合理論上不應出現兩個不同組別（若有，保留人數較多者，通常代表主要組別）
        dup = next((x for x in groups if x['subjects'] == codes_sorted), None)
        if dup is not None:
            bad.append(f'組{grp_id}: 科目集合與既有組別重複 {codes_sorted}（既有total={dup["total"]}, 本組total={total_n}）')
            if total_n <= dup['total']:
                continue
            groups.remove(dup)

        groups.append({'subjects': codes_sorted, 'total': total_n, 'bands': bands})

    return groups, bad


out = {}
for yr in YEARS:
    groups, bad = parse_year(yr)
    out[yr] = groups
    print(yr, '有效組合數:', len(groups), '| 異常/警告:', len(bad))
    for b in bad[:15]:
        print('  !', b)

json.dump(out, open('accu.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('已輸出 accu.json，總計：', {y: len(out[y]) for y in out})


def lookup(yr, subj_codes, total_score):
    key = sorted(subj_codes)
    for grp in out[yr]:
        if grp['subjects'] == key:
            for b in grp['bands']:
                if total_score <= b['upper']:
                    return {'combo_rank': b['cum_hi'], 'combo_total': grp['total'], 'combo_pr': b['cum_lo_pct']}
            b = grp['bands'][-1]
            return {'combo_rank': b['cum_hi'], 'combo_total': grp['total'], 'combo_pr': b['cum_lo_pct']}
    return None


# 抽樣測試：台大歷史學系採計 歷x1 國x1 英x1 地x1 公x1（全部加權1.00，符合官方組合排名條件）
print('--- 抽樣查詢：歷/國/英/地/公 組合 ---')
for yr in YEARS:
    r = lookup(yr, ['歷', '國', '英', '地', '公'], 260.0)
    print(yr, '總分260 =>', r)
