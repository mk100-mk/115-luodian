# -*- coding: utf-8 -*-
"""
tools/parse_tiebreaker.py   （新增於 116學年度升級，2026-08-17）

解析 113 / 114 / 115 學年度正式榜單 PDF 的「普通生同分參酌」欄位，
輸出 tiebreaker.json，供前端做「壓線風險警示」。

────────────────────────────────────────────────────────────
為什麼需要這份資料
────────────────────────────────────────────────────────────
純分數落點模型有一個結構性盲區：**總分達標 ≠ 錄取**。
當考生總分恰好等於某系組的最低錄取分時，分發系統會啟動「同分參酌」，
依該系組簡章所定的參酌順序，逐層比較指定科目的級分，直到分出高下。

115學年度已驗證的真實案例（見 CLAUDE.md 鐵則）：
  · 國立臺灣大學 歷史學系  最低 262.00，第一層參酌「歷史」門檻 60 級分 → 262 打平但落榜
  · 國立臺灣大學 社會學系  最低 251.00，第一層參酌「英文」門檻 47 級分 → 251 打平但落榜

因此「總分打平」必須被視為**未錄取風險極高**，而非「剛好上榜」。

────────────────────────────────────────────────────────────
前端使用規格（步驟7 實作依據）
────────────────────────────────────────────────────────────
當「使用者採計總分」與「該系組最低錄取分」差距在 **±2 分以內** 時，
在落點結果卡片顯示獨立警示區塊：

    ⚠ 同分參酌風險
    此系 {yr} 年曾啟動同分參酌篩選，總分打平不保證錄取。
    參酌順序：① 歷史 ≥ 60 級分  ② …
    請比對自己的該科級分。

差距 > 2 分者不顯示，避免警示疲乏。
沒有同分參酌紀錄的系組，仍應顯示一般性提醒（該年未用到，不代表 116 年不會用到）。

────────────────────────────────────────────────────────────
資料格式
────────────────────────────────────────────────────────────
tiebreaker.json = {
  "115": {
     "{校名}|{系組名}": {
        "code":   系組代碼（僅供追溯，禁止跨年比對）,
        "school": 校名,
        "dept":   系組名,
        "score":  該年最低錄取分數（字串，None 表示未招生/無人錄取）,
        "n":      錄取人數,
        "raw":    官方原始字串（保留，供人工覆核）,
        "levels": [ {"subject": "歷", "min": 60.0, "stage": "級分"}, ... ]
                  依官方公布順序，即實際參酌順序（第一層在前）
     }, ...
  },
  "113": {...}, "114": {...},
  "_meta": {...}
}

僅收錄「該年度實際啟動同分參酌」的系組（欄位非空者）。
欄位為空代表該年最低錄取分沒有同分情形，不代表該系組沒有同分參酌規則。

────────────────────────────────────────────────────────────
欄位語法（已對 113–115 全量 1,834 筆驗證，殘留未解析字元 = 0）
────────────────────────────────────────────────────────────
基本形： 「科目 級分」重複，依參酌順序排列
    '歷 60'                 → 第一層：歷史 60 級分
    '數甲 34 英 60'          → 第一層：數甲 34；第二層：英文 60

階段標記： 部分系組（多為含術科者）分兩階段參酌
    '(級分)數甲 60物 49 化 53(實得)數甲 96.8'
    → 級分階段：數甲60 → 物49 → 化53；實得分數階段：數甲 96.8

已知版面瑕疵： 官方 PDF 偶爾漏掉層級間空白（如 '公 52地 59'），
故採用正則掃描而非空白切分，不受此影響。

用法：於 tools/ 目錄下執行   python parse_tiebreaker.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pdfplumber

BASE = Path(__file__).resolve().parent

YEARS = ['113', '114', '115']

# 科目 token。長名在前，避免 '數甲' 被拆成 '數'+'甲'
SUBJ = r'(?:術科|數甲|數乙|數A|數B|國|英|自|社|物|化|生|歷|地|公|術)'
LEVEL = re.compile(r'(' + SUBJ + r')\s*(\d+(?:\.\d+)?)')
STAGE = re.compile(r'[（(](級分|實得)[）)]')
SCORE = re.compile(r'^\d+\.\d{2}$')

# 科目代碼 → 中文全名（供前端警示文字使用）
SUBJ_NAME = {
    '國': '國文', '英': '英文', '數甲': '數學甲', '數乙': '數學乙',
    '數A': '數學A', '數B': '數學B', '物': '物理', '化': '化學',
    '生': '生物', '歷': '歷史', '地': '地理', '公': '公民與社會',
    '自': '自然', '社': '社會', '術科': '術科', '術': '術科',
}


MAX_GRADE = 60  # 分發採計一律換算為 60 級分制（學測科目亦同），故 >60 必為實得分數


def parse_levels(raw):
    """把官方同分參酌字串解析為有序的參酌層級清單。

    回傳 (levels, residual, stage_source)。
    residual 為扣除所有已辨識 token 後的殘留字元，正常應為空字串；
    非空表示出現未預期語法，須人工覆核。

    ── 階段（級分 / 實得）判定 ──
    同分參酌實務上分兩階段：先比「級分」，級分仍全同時再比「實得分數」。
    113 年榜單以 (級分)/(實得) 標記明示階段，114/115 年則**省略標記**，
    但兩階段結構仍在。例如 115 年：

        國立政治大學 財務管理學系: '數乙 60 英 52國 46 數乙 100'
        → 數乙60/英52/國46 為級分階段；數乙100 已超過級分上限，屬實得分數階段

    因此本函式以「明示標記優先、否則推論」處理，推論規則（滿足任一即進入實得階段）：
      (a) 數值帶小數（級分必為整數）      例：數甲 39.6
      (b) 數值 > 60（級分上限）           例：數乙 100
      (c) 科目在級分階段已出現過（實得階段從第一參酌科目重新輪一次）
    階段具單向性：一旦進入實得階段，其後所有層級皆為實得。

    stage_source 回傳 'explicit'（官方有標記）或 'inferred'（本函式推論）或
    'single'（僅一階段、無需判定），寫入輸出供覆核時區分資料可信度。
    """
    s = re.sub(r'\s+', ' ', raw).strip()
    has_marker = bool(STAGE.search(s))

    levels = []
    stage = '級分'
    seen_grade_subjects = set()

    for m in re.finditer(STAGE.pattern + '|' + LEVEL.pattern, s):
        g = m.group(0)
        st = STAGE.fullmatch(g)
        if st:
            stage = st.group(1)
            continue
        lv = LEVEL.fullmatch(g)
        subj, val = lv.group(1), float(lv.group(2))

        if stage == '級分' and not has_marker:
            if (val != int(val)) or (val > MAX_GRADE) or (subj in seen_grade_subjects):
                stage = '實得'

        if stage == '級分':
            seen_grade_subjects.add(subj)

        levels.append({
            'subject': subj,
            'name': SUBJ_NAME.get(subj, subj),
            'min': val,
            'stage': stage,
        })

    if has_marker:
        stage_source = 'explicit'
    elif any(l['stage'] == '實得' for l in levels):
        stage_source = 'inferred'
    else:
        stage_source = 'single'

    residual = re.sub(r'\s+', '', LEVEL.sub(' ', STAGE.sub(' ', s)))
    return levels, residual, stage_source


def parse_year(yr):
    path = BASE / yr / f'{yr}_result_school_data.pdf'
    if not path.exists():
        raise FileNotFoundError(f'找不到榜單 PDF：{path}')

    recs = {}
    bad = []
    total_rows = 0
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            table = page.extract_table()
            if not table:
                bad.append(f'p{pi + 1}: 無法擷取表格')
                continue
            for row in table[1:]:
                cells = [(c or '').replace('\n', '').strip() for c in row]
                if len(cells) < 7:
                    continue
                code = cells[0]
                if not re.fullmatch(r'\d{4}', code):
                    continue
                total_rows += 1
                raw = cells[6]
                if not raw or raw.strip('-') == '':
                    continue  # 該年未啟動同分參酌

                school = re.sub(r'\s+', '', cells[1])
                dept = re.sub(r'\s+', '', cells[2])
                score = cells[5] if SCORE.fullmatch(cells[5]) else None
                try:
                    n_adm = int(cells[4])
                except ValueError:
                    n_adm = None

                levels, residual, stage_source = parse_levels(raw)
                if residual:
                    bad.append(f'p{pi + 1}: 殘留未解析字元 {code} {school}{dept} '
                               f'raw=<{raw}> residual=<{residual}>')
                if not levels:
                    bad.append(f'p{pi + 1}: 無法解析出參酌層級 {code} {school}{dept} raw=<{raw}>')
                    continue

                recs[f'{school}|{dept}'] = {
                    'code': code, 'school': school, 'dept': dept,
                    'score': score, 'n': n_adm,
                    'raw': re.sub(r'\s+', ' ', raw).strip(),
                    'levels': levels,
                    'stage_source': stage_source,
                }
    return recs, bad, total_rows


def main():
    out = {}
    meta = {
        'generated_for': '116學年度落點試算',
        'years': YEARS,
        'purpose': '同分參酌（壓線）風險警示',
        'frontend_rule': '|使用者採計總分 - 該系最低錄取分| <= 2 時顯示警示區塊',
        'join_key': '校名+系組名（禁止使用系組代碼跨年比對）',
        'note': '欄位為空僅代表該年最低分無同分情形，不代表該系組無同分參酌規則',
        'per_year': {},
    }
    all_bad = {}

    for yr in YEARS:
        recs, bad, total_rows = parse_year(yr)
        out[yr] = recs
        all_bad[yr] = bad
        depth = Counter(len(v['levels']) for v in recs.values())
        src = Counter(v['stage_source'] for v in recs.values())
        rate = len(recs) / total_rows * 100 if total_rows else 0
        meta['per_year'][yr] = {
            'total_depts': total_rows,
            'with_tiebreaker': len(recs),
            'rate_pct': round(rate, 1),
            'depth_distribution': dict(sorted(depth.items())),
            'stage_source': dict(src),
            'anomalies': len(bad),
        }
        print(f'[{yr}] 系組 {total_rows:5d} | 啟動同分參酌 {len(recs):5d} '
              f'({rate:4.1f}%) | 參酌層數分布 {dict(sorted(depth.items()))} | 異常 {len(bad)}')
        print(f'       階段判定來源 {dict(src)}')
        for b in bad[:5]:
            print('     !', b)

    # ---------- 連續啟動偵測：三年皆啟動同分參酌者 = 高風險系組 ----------
    sets = {yr: set(out[yr].keys()) for yr in YEARS}
    always = sets['113'] & sets['114'] & sets['115']
    meta['always_tiebreak_count'] = len(always)
    print()
    print(f'三年皆啟動同分參酌：{len(always)} 系組（視為「壓線高風險」，前端可加強標示）')

    out['_meta'] = meta
    with open(BASE / 'tiebreaker.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)

    with open(BASE / 'tiebreaker_anomalies.log', 'w', encoding='utf-8') as f:
        for yr in YEARS:
            f.write(f'===== {yr} =====\n')
            for b in all_bad[yr]:
                f.write(b + '\n')

    with open(BASE / 'tiebreaker_always.log', 'w', encoding='utf-8') as f:
        f.write('校名|系組名\t113參酌\t114參酌\t115參酌\n')
        for k in sorted(always):
            f.write(k + '\t' + '\t'.join(out[y][k]['raw'] for y in YEARS) + '\n')

    print('已輸出 tiebreaker.json / tiebreaker_anomalies.log / tiebreaker_always.log')

    # ---------- 抽樣核對：115實戰驗證關鍵系組 ----------
    print()
    print('─── 抽樣核對：115學年度實戰驗證關鍵系組 ───')
    for key in ('國立臺灣大學|歷史學系',
                '國立臺灣大學|社會學系',
                '國立臺灣大學|生物產業傳播暨發展學系'):
        print(f'\n{key}')
        for yr in YEARS:
            v = out[yr].get(key)
            if v is None:
                print(f'  {yr}: 該年未啟動同分參酌')
            else:
                order = ' → '.join(
                    f'{i + 1}.{lv["name"]}≥{lv["min"]:g}({lv["stage"]})'
                    for i, lv in enumerate(v['levels']))
                print(f'  {yr}: 最低{v["score"]} 錄取{v["n"]}人 | 參酌順序 {order}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
