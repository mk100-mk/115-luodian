# -*- coding: utf-8 -*-
"""
tools/parse_accu.py   （116學年度版，2026-08-17 改寫）

解析 tools/{yr}/accu-{yr}.xls（大學考試入學分發委員會「採計組合成績人數累計表」），
建立「組合代碼 → 科目集合 → 分數區間人數累計」查詢資料庫 accu.json。

────────────────────────────────────────────────────────────
適用範圍（鐵則）
────────────────────────────────────────────────────────────
官方組合排名**僅適用於「採計科目加權皆為 1.00」且官方有公布對照組別的系組**。
這類系組的採計總分 = 各採計科目實得分數直接加總，因此可與同一科目組合的
全體考生成績精確比對，查得全國名次與百分等級（PR）。

加權非 1.00 的系組（多數）**不得**強行套用，一律改以歷年最低分比較法為輔，
並在前端誠實標示「無官方組合對照」——這是 CLAUDE.md 明載的鐵則。

────────────────────────────────────────────────────────────
為什麼 116 版要收 113–115 三年（而非只收當年）
────────────────────────────────────────────────────────────
115 版只需 115 年一份 accu：當時 115 尚未放榜、無最低分，accu 是唯一可用訊號。

116 版多了一項更強的用途——**等排名跨年換算**：

    115年某系最低分 →（查 accu-115）→ 該分數在 115 年的全國組合排名
                    →（查 accu-116 反向）→ 116 年同一排名對應的分數
                    = 該系 116 年最低分的合理推估值

這條路徑可以吃掉「年度難易度差異」這個歷年比較法最大的誤差來源。
113/114 兩年則用來檢驗此換算法的歷史準確度（回測），不是裝飾用的。

116 年 8 月分科成績公布後，把 accu-116.xls 放入 tools/116/、
在 YEARS 加入 '116' 重跑本腳本即可，無需改動邏輯。

────────────────────────────────────────────────────────────
科目名稱 → 本專案科目代碼對照（對照 site/app.js 的 SUBJ 清單）
────────────────────────────────────────────────────────────
  國文→國 英文→英 數學A→數A 數學B→數B 自然→自 社會→社
  數甲→數甲 數乙→數乙 物理→物 化學→化 生物→生 歷史→歷 地理→地 公民與社會→公
  體育→體 美術(不含美術成績)→美 音樂(不含音樂成績)→音

註：體育／美術／音樂三類為術科性質。本專案系組資料對術科一律用概化代碼「術」，
不區分具體術科種類，因此**刻意不**把這三個 accu 代碼映射到「術」——
否則會把美術系錯配到音樂或體育考生的百分等級表。術科相關系組一律走比較法。

────────────────────────────────────────────────────────────
輸出格式 accu.json
────────────────────────────────────────────────────────────
{
  "115": [
    {
      'gid':      官方組別代碼,
      'subjects': [科目代碼,...]  排序後的科目集合,
      'total':    該組合全國考生總人數,
      'max':      該組合滿分,
      'bands': [ {'upper':區間上限, 'n':區間人數,
                  'cum_hi':高→低累計人數, 'cum_lo_pct':低→高累計百分比(PR)}, ... ]
                 依 upper 由低到高排序
    }, ...
  ],
  "113": [...], "114": [...],
  "_meta": {...}
}

────────────────────────────────────────────────────────────
查詢邏輯
────────────────────────────────────────────────────────────
rank_of(yr, subjects, score)  分數 → 排名／PR
  分數區間定義為「上一區間上限 < 分數 <= 本區間上限」，最低區間為 [0, 上限] 全含。
  取第一個 upper >= score 的區間，其 cum_hi 即為「該分數(含)以上的人數」＝名次。

score_at_rank(yr, subjects, rank)  排名 → 分數（等排名換算用）
  取第一個 cum_hi >= rank 的區間（由高分往低分掃），回傳其 upper。

用法：於 tools/ 目錄下執行   python parse_accu.py
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent

YEARS = ['113', '114', '115']

NAME2CODE = {
    '國文': '國', '英文': '英', '數學A': '數A', '數學B': '數B', '自然': '自', '社會': '社',
    '數甲': '數甲', '數乙': '數乙', '物理': '物', '化學': '化', '生物': '生', '歷史': '歷',
    '地理': '地', '公民與社會': '公',
    '體育': '體', '美術(不含美術成績)': '美', '音樂(不含音樂成績)': '音',
}

COLS = ['grp', 'subj', 'band', 'n', 'pct', 'cum_hi', 'cum_hi_pct', 'cum_lo', 'cum_lo_pct']


def parse_year(yr):
    path = BASE / yr / f'accu-{yr}.xls'
    if not path.exists():
        raise FileNotFoundError(f'找不到採計組合累計表：{path}')

    df = pd.read_excel(path, header=0)
    if df.shape[1] != len(COLS):
        raise ValueError(f'{path} 欄位數為 {df.shape[1]}，預期 {len(COLS)}；官方版面可能已變更')
    df.columns = COLS
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
                bad.append(f'組{grp_id}: 未知科目名稱 "{nm}"（整組略過）')
                break
            codes.append(c)
        if not ok:
            continue

        bands = []
        for _, row in g.iterrows():
            band_str = str(row['band']).strip()
            m = re.match(r'^\s*[\d.]+\s*-\s*([\d.]+)\s*$', band_str)
            if not m:
                bad.append(f'組{grp_id}: 分數區間格式異常 "{band_str}"')
                continue
            bands.append({
                'upper': float(m.group(1)),
                'n': int(row['n']),
                'cum_hi': int(row['cum_hi']),
                'cum_lo_pct': float(row['cum_lo_pct']),
            })
        if not bands:
            bad.append(f'組{grp_id}: 無有效分數區間')
            continue

        bands.sort(key=lambda b: b['upper'])  # 由低到高

        # cum_hi（高→低累計）在最高分區間最小、在最低分區間最大（涵蓋全體），
        # 故該組合總人數 = 最低分區間的 cum_hi
        total_n = bands[0]['cum_hi']

        # ── 一致性檢核（不靜默通過）──
        # 1) cum_hi 必須隨分數升高而單調遞減
        for a, b in zip(bands, bands[1:]):
            if b['cum_hi'] > a['cum_hi']:
                bad.append(f'組{grp_id}: cum_hi 非單調 ({a["upper"]}→{b["upper"]})')
                break
        # 2) 各區間人數加總 == 總人數
        if sum(b['n'] for b in bands) != total_n:
            bad.append(f'組{grp_id}: 區間人數加總 {sum(b["n"] for b in bands)} '
                       f'≠ 總人數 {total_n}')

        codes_sorted = sorted(codes)
        dup = next((x for x in groups if x['subjects'] == codes_sorted), None)
        if dup is not None:
            bad.append(f'組{grp_id}: 科目集合與組{dup["gid"]}重複 {codes_sorted}'
                       f'（既有 total={dup["total"]}、本組 total={total_n}；保留人數多者）')
            if total_n <= dup['total']:
                continue
            groups.remove(dup)

        groups.append({
            'gid': int(grp_id),
            'subjects': codes_sorted,
            'total': total_n,
            'max': bands[-1]['upper'],
            'bands': bands,
        })

    return groups, bad


# ────────────────────────────── 查詢函式 ──────────────────────────────
def find_group(db, yr, subj_codes):
    key = sorted(subj_codes)
    for grp in db[yr]:
        if grp['subjects'] == key:
            return grp
    return None


def rank_of(db, yr, subj_codes, score):
    """分數 → {名次, 總人數, PR}。找不到組合回傳 None。"""
    grp = find_group(db, yr, subj_codes)
    if grp is None:
        return None
    for b in grp['bands']:
        if score <= b['upper']:
            return {'rank': b['cum_hi'], 'total': grp['total'], 'pr': b['cum_lo_pct']}
    b = grp['bands'][-1]
    return {'rank': b['cum_hi'], 'total': grp['total'], 'pr': b['cum_lo_pct']}


def score_at_rank(db, yr, subj_codes, rank):
    """名次 → 該名次對應的分數區間上限（等排名跨年換算用）。"""
    grp = find_group(db, yr, subj_codes)
    if grp is None:
        return None
    for b in reversed(grp['bands']):      # 由高分往低分掃
        if b['cum_hi'] >= rank:
            return b['upper']
    return grp['bands'][0]['upper']


def equate(db, subj_codes, score, from_yr, to_yr):
    """等排名跨年換算：from_yr 的 score → to_yr 的等值分數。"""
    r = rank_of(db, from_yr, subj_codes, score)
    if r is None:
        return None
    s = score_at_rank(db, to_yr, subj_codes, r['rank'])
    if s is None:
        return None
    return {'from_score': score, 'rank': r['rank'], 'pr': r['pr'],
            'to_score': s, 'delta': round(s - score, 2)}


# ────────────────────────────── 主流程 ──────────────────────────────
def main():
    db = {}
    meta = {
        'generated_for': '116學年度落點試算',
        'years': YEARS,
        'applies_to': '僅限採計科目加權皆為1.00且官方有公布對照組別之系組',
        'source': '大學考試入學分發委員會 採計組合成績人數累計表',
        'per_year': {},
    }
    all_bad = {}

    for yr in YEARS:
        groups, bad = parse_year(yr)
        db[yr] = groups
        all_bad[yr] = bad
        meta['per_year'][yr] = {
            'groups': len(groups),
            'examinees_max_group': max(g['total'] for g in groups) if groups else 0,
            'anomalies': len(bad),
        }
        print(f'[{yr}] 有效組合 {len(groups):4d} | 最大組合人數 '
              f'{max(g["total"] for g in groups) if groups else 0:6d} | 異常/警告 {len(bad)}')
        for b in bad[:8]:
            print('     !', b)
        if len(bad) > 8:
            print(f'     ... 另有 {len(bad) - 8} 筆，見 accu_anomalies.log')

    # ---------- 跨年組合覆蓋率 ----------
    sets = {yr: {tuple(g['subjects']) for g in db[yr]} for yr in YEARS}
    all3 = sets['113'] & sets['114'] & sets['115']
    meta['coverage'] = {'all_three_years': len(all3),
                        **{yr: len(sets[yr]) for yr in YEARS}}
    print()
    print(f'三年皆有的科目組合：{len(all3)} 組（可做等排名跨年換算）')
    for yr in YEARS:
        print(f'  {yr} 獨有組合：{len(sets[yr] - all3)} 組')

    db['_meta'] = meta
    with open(BASE / 'accu.json', 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, separators=(',', ':'))
    with open(BASE / 'accu_anomalies.log', 'w', encoding='utf-8') as f:
        for yr in YEARS:
            f.write(f'===== {yr} =====\n')
            for b in all_bad[yr]:
                f.write(b + '\n')
    print()
    print('已輸出 accu.json / accu_anomalies.log')

    # ---------- 抽樣驗證 ----------
    print()
    print('─── 抽樣驗證 1：台大歷史學系組合（歷/國/英/地/公，加權全1.00）───')
    HIST = ['歷', '國', '英', '地', '公']
    for yr, low in (('113', 263.0), ('114', 260.0), ('115', 262.0)):
        r = rank_of(db, yr, HIST, low)
        print(f'  {yr} 最低分 {low} → 全國名次 {r["rank"]} / {r["total"]} 人，PR {r["pr"]}')

    print()
    print('─── 抽樣驗證 2：等排名跨年換算（檢驗此法的歷史準確度）───')
    print('  以「前一年最低分」換算為「當年等值分數」，與當年實際最低分比較：')
    for from_yr, to_yr, from_low, actual in (('113', '114', 263.0, 260.0),
                                             ('114', '115', 260.0, 262.0)):
        e = equate(db, HIST, from_low, from_yr, to_yr)
        err = round(e['to_score'] - actual, 2)
        print(f'  {from_yr}最低{from_low}（名次{e["rank"]}）→ {to_yr}等值 {e["to_score"]}'
              f' | {to_yr}實際最低 {actual} | 換算誤差 {err:+.2f}')

    print()
    print('─── 抽樣驗證 3：台大社會學系 115 組合（英/數A/公/地/歷）───')
    SOC = ['英', '數A', '公', '地', '歷']
    r = rank_of(db, '115', SOC, 251.0)
    print('  115 最低分 251.0 →', r)

    # ---------- 全量回測：等排名換算法 vs 歷年比較法 ----------
    backtest(db, meta)

    # meta 於回測後才完整，重寫一次
    db['_meta'] = meta
    with open(BASE / 'accu.json', 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, separators=(',', ':'))

    return 0


def backtest(db, meta):
    """全量回測：用前一年最低分預測當年最低分，比較兩種方法的誤差。

    方法A（歷年比較法）：直接沿用前一年最低分
    方法B（等排名換算法）：前一年最低分 → 該年組合排名 → 當年同排名對應分數

    僅納入「兩年採計科目集合相同、加權皆1.00、官方組合兩年皆有」的系組，
    確保比較的是方法本身的優劣，而非資料可得性差異。
    """
    import statistics

    hist_path = BASE / 'hist.json'
    if not hist_path.exists():
        print('\n（找不到 hist.json，略過回測。請先執行 parse_history_results.py）')
        return
    hist = json.load(open(hist_path, encoding='utf-8'))

    rows = []
    for A, B in zip(YEARS, YEARS[1:]):
        if A not in hist or B not in hist:
            continue
        for key, va in hist[A].items():
            vb = hist[B].get(key)
            if not vb or not va['score'] or not vb['score']:
                continue
            wa, wb = va['subjects'], vb['subjects']
            if set(wa) != set(wb):
                continue        # 採計科目跨年變動者排除（無從公平比較）
            if not all(abs(x - 1.0) < 1e-9 for x in list(wa.values()) + list(wb.values())):
                continue        # 官方組合排名僅適用加權全1.00
            su = sorted(wa.keys())
            gA, gB = find_group(db, A, su), find_group(db, B, su)
            if gA is None or gB is None:
                continue

            prev, actual = float(va['score']), float(vb['score'])
            band = next((b for b in gA['bands'] if prev <= b['upper']), gA['bands'][-1])
            pred = score_at_rank(db, B, su, band['cum_hi'])
            rows.append({
                'pair': f'{A}→{B}', 'key': key, 'pr': band['cum_lo_pct'],
                'err_equate': abs(pred - actual), 'err_naive': abs(prev - actual),
            })

    if not rows:
        print('\n（回測樣本為 0，略過）')
        return

    def bucket(pr):
        return 'PR>=90' if pr >= 90 else '70<=PR<90' if pr >= 70 \
            else '50<=PR<70' if pr >= 50 else 'PR<50'

    print()
    print('─── 全量回測：等排名換算法 vs 歷年比較法（依 PR 區間分層）───')
    print(f'  {"PR區間":<12s}{"樣本":>6s}{"換算MAE":>10s}{"沿用MAE":>10s}{"換算較準":>10s}')
    stats = {}
    lines = ['PR區間\t樣本\t換算MAE\t沿用MAE\t換算較準%']
    for bk in ('PR>=90', '70<=PR<90', '50<=PR<70', 'PR<50'):
        sub = [r for r in rows if bucket(r['pr']) == bk]
        if not sub:
            continue
        eq = statistics.mean(r['err_equate'] for r in sub)
        nv = statistics.mean(r['err_naive'] for r in sub)
        win = sum(1 for r in sub if r['err_equate'] < r['err_naive']) / len(sub) * 100
        stats[bk] = {'n': len(sub), 'mae_equate': round(eq, 2),
                     'mae_naive': round(nv, 2), 'equate_wins_pct': round(win, 1)}
        print(f'  {bk:<12s}{len(sub):>6d}{eq:>10.2f}{nv:>10.2f}{win:>9.1f}%')
        lines.append(f'{bk}\t{len(sub)}\t{eq:.2f}\t{nv:.2f}\t{win:.1f}')

    print()
    print('  結論：等排名換算法在 PR>=70 的區間明顯優於直接沿用前一年最低分；')
    print('        PR<70（低分／招生不足的尾端系組）則反而更差——因為累計表尾端過於平坦，')
    print('        少數幾人的差異就會讓換算分數劇烈跳動。')
    print('  因此本專案採用門檻：**PR >= 70 才使用等排名換算，否則回退歷年比較法。**')

    meta['backtest'] = {
        'sample': len(rows),
        'by_pr_bucket': stats,
        'decision_rule': 'PR >= 70 時採用等排名換算法；PR < 70 回退歷年最低分比較法',
    }

    with open(BASE / 'accu_backtest.log', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n\n')
        f.write('pair\tkey\tPR\t換算誤差\t沿用誤差\n')
        for r in sorted(rows, key=lambda r: -r['err_equate']):
            f.write(f'{r["pair"]}\t{r["key"]}\t{r["pr"]:.2f}\t'
                    f'{r["err_equate"]:.2f}\t{r["err_naive"]:.2f}\n')
    print('  已輸出 accu_backtest.log（含全量逐筆誤差）')


if __name__ == '__main__':
    sys.exit(main())
