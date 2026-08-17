# -*- coding: utf-8 -*-
"""
tools/parse_history_results.py   （116學年度版，2026-08-17 重寫）

解析 113 / 114 / 115 學年度「大學分發入學 各系組最低錄取標準及錄取人數一覽表」
官方 PDF 榜單（tools/{yr}/{yr}_result_school_data.pdf），輸出統一格式 hist.json。

────────────────────────────────────────────────────────────
為什麼是 113–115 而不是 112–114
────────────────────────────────────────────────────────────
115學年度已於 2026-08 正式放榜，取得完整最低錄取標準，成為 116 落點分析的
「歷史基準年」（詳見 tools/115/BASELINE.md）。三年滾動視窗前移一年：
112 退場，115 進場。

────────────────────────────────────────────────────────────
輸出格式
────────────────────────────────────────────────────────────
hist.json = {
  "113": { "{校名}|{系組名}": REC, ... },
  "114": { ... },
  "115": { ... },
  "_meta": { ... 解析統計與版本資訊 ... }
}

REC = {
  'code':     系組代碼（僅供追溯，**嚴禁**用於跨年度比對，見下方鐵則）,
  'school':   校名,
  'dept':     系組名,
  'subjects': {科目: 加權, ...}   採計科目及加權,
  'score':    最低錄取分數（字串，保留原始兩位小數）；當年無人錄取時為 None,
  'n':        錄取人數（含外加）
}

────────────────────────────────────────────────────────────
比對鐵則（CLAUDE.md 已載明，此處以程式強制執行）
────────────────────────────────────────────────────────────
跨年度比對一律以「校名＋系組名」為鍵，**禁止使用系組代碼**。
已證實同一代碼在不同年度可對應完全不同系組：
    代碼 0071 → 113年「財務金融學系B組」，115年「國際企業學系A組」
本腳本因此以 (school, dept) 建立字典鍵，code 僅作為附帶欄位保存。
腳本結尾會自動執行「代碼漂移偵測」，把跨年度同代碼但不同系組的案例列印出來，
作為此鐵則的持續證據。

────────────────────────────────────────────────────────────
解析方式
────────────────────────────────────────────────────────────
以 pdfplumber 的 extract_table()（依 PDF 表格格線切格）逐頁擷取。
不使用文字流式擷取（extract_text），因為「同分參酌」欄位在部分列會因版面位移
造成相鄰列資料互相污染。三年榜單版面經核實完全一致：

  系組代碼 | 校名 | 系組名 | 採計及加權 | 錄取人數(含外加) | 普通生錄取分數
         | 普通生同分參酌 | 原住民 | 退伍軍人 | 僑生 | 蒙藏生 | 派外子女

本腳本只取前 6 欄。第 7 欄「同分參酌」由 tools/parse_tiebreaker.py 另行處理，
輸出 tiebreaker.json（分離的理由：同分參酌是獨立的風險警示資料，
其結構為「科目＋門檻級分」的序列，與最低分屬不同語意層次）。

用法：於 tools/ 目錄下執行   python parse_history_results.py
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

BASE = Path(__file__).resolve().parent

YEARS = ['113', '114', '115']

# 採計科目加權 token，例如 國x1.50、數甲x1.00、術科x1.00
WT = re.compile(r'^(?:術科|數甲|數乙|數A|數B|國|英|自|社|物|化|生|歷|地|公|術)x\d+(?:\.\d+)?$')

# 最低錄取分數格式：整數部分 + 兩位小數（如 262.00、325.50）
SCORE = re.compile(r'^\d+\.\d{2}$')


def parse_year(yr):
    """解析單一年度榜單 PDF，回傳 (recs, bad, dup_keys)。

    recs: {(school, dept): REC}
    bad:  異常列說明清單（供人工覆核，不靜默丟棄）
    dup_keys: 同年度內「校名+系組名」重複的鍵清單
    """
    path = BASE / yr / f'{yr}_result_school_data.pdf'
    if not path.exists():
        raise FileNotFoundError(f'找不到榜單 PDF：{path}')

    recs = {}
    bad = []
    dup_keys = []
    n_pages = 0

    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for pi, page in enumerate(pdf.pages):
            table = page.extract_table()
            if not table:
                bad.append(f'p{pi + 1}: 無法擷取表格')
                continue
            for row in table[1:]:  # 跳過表頭列
                cells = [(c or '').replace('\n', '').strip() for c in row]
                if len(cells) < 6:
                    bad.append(f'p{pi + 1}: 欄位不足 {cells}')
                    continue

                code, school, dept, wt_str, n_str, score_str = cells[:6]

                # 少數頁面因原始PDF字距渲染異常，校名/系組名中間夾帶多餘空白
                # （例：'體 育學系'）。中文校系名稱不應含空白，故一律移除。
                school = re.sub(r'\s+', '', school)
                dept = re.sub(r'\s+', '', dept)

                if not re.fullmatch(r'\d{4}', code):
                    bad.append(f'p{pi + 1}: 代碼異常 {cells[:4]}')
                    continue

                subj = {}
                ok = True
                for tok in wt_str.split():
                    if not WT.match(tok):
                        ok = False
                        break
                    k, v = tok.split('x')
                    subj[k] = float(v)
                if not ok or not subj:
                    bad.append(f'p{pi + 1}: 採計加權異常 {code} {school}{dept} <{wt_str}>')
                    continue

                try:
                    n_adm = int(n_str)
                except ValueError:
                    bad.append(f'p{pi + 1}: 錄取人數異常 {code} {school}{dept} <{n_str}>')
                    continue

                # 錄取人數為 0（未招生／無人錄取）時，分數欄為 '-----'，正規化為 None
                score = score_str if SCORE.fullmatch(score_str) else None

                key = (school, dept)
                if key in recs:
                    dup_keys.append(key)
                    bad.append(f'p{pi + 1}: 同年度重複系組(校名+系組名) {key}')
                recs[key] = {
                    'code': code,
                    'school': school,
                    'dept': dept,
                    'subjects': subj,
                    'score': score,
                    'n': n_adm,
                }

    return recs, bad, dup_keys, n_pages


def detect_code_drift(out):
    """代碼漂移偵測：同一系組代碼在不同年度對應到不同「校名+系組名」。

    這是「禁止用代碼跨年比對」鐵則的實證。回傳 [(code, {yr: '校名|系組名'}), ...]
    """
    by_code = defaultdict(dict)
    for yr in YEARS:
        for key, rec in out[yr].items():
            by_code[rec['code']][yr] = key
    drift = []
    for code, mapping in sorted(by_code.items()):
        names = set(mapping.values())
        if len(names) > 1:
            drift.append((code, mapping))
    return drift


def main():
    out = {}
    meta = {
        'generated_for': '116學年度落點試算',
        'years': YEARS,
        'join_key': '校名+系組名（禁止使用系組代碼跨年比對）',
        'source': '大學考試入學分發委員會 各系組最低錄取標準及錄取人數一覽表',
        'per_year': {},
    }
    all_bad = {}

    for yr in YEARS:
        recs, bad, dup_keys, n_pages = parse_year(yr)
        out[yr] = {f'{s}|{d}': v for (s, d), v in recs.items()}
        all_bad[yr] = bad
        n_no_score = sum(1 for v in recs.values() if v['score'] is None)
        meta['per_year'][yr] = {
            'pages': n_pages,
            'records': len(recs),
            'no_score': n_no_score,
            'anomalies': len(bad),
            'dup_keys': len(dup_keys),
        }
        print(f'[{yr}] 頁數 {n_pages:3d} | 系組 {len(recs):5d} | '
              f'無最低分 {n_no_score:3d} | 異常列 {len(bad):3d} | 同年重複key {len(dup_keys)}')
        for b in bad[:8]:
            print('     !', b)
        if len(bad) > 8:
            print(f'     ... 另有 {len(bad) - 8} 筆異常，見 hist_anomalies.log')

    # ---------- 跨年度覆蓋率（以校名+系組名比對） ----------
    print()
    sets = {yr: set(out[yr].keys()) for yr in YEARS}
    all3 = sets['113'] & sets['114'] & sets['115']
    print(f'三年皆有(校名+系組名精確比對)：{len(all3)} 系組')
    for a, b in (('113', '114'), ('114', '115'), ('113', '115')):
        print(f'  {a}∩{b}: {len(sets[a] & sets[b]):5d}   '
              f'{a}獨有: {len(sets[a] - sets[b]):4d}   {b}獨有: {len(sets[b] - sets[a]):4d}')
    meta['coverage'] = {
        'all_three_years': len(all3),
        '113_and_114': len(sets['113'] & sets['114']),
        '114_and_115': len(sets['114'] & sets['115']),
        '113_and_115': len(sets['113'] & sets['115']),
    }

    # ---------- 代碼漂移偵測（鐵則實證） ----------
    drift = detect_code_drift(out)
    meta['code_drift_count'] = len(drift)
    print()
    print(f'代碼漂移偵測：{len(drift)} 個系組代碼在 113–115 間對應到不同系組')
    print('（此即「禁止用代碼跨年比對最低分」鐵則的實證）')
    for code, mapping in drift[:6]:
        print(f'  代碼 {code}: ' + ' → '.join(f'{y}「{mapping[y]}」' for y in YEARS if y in mapping))
    if len(drift) > 6:
        print(f'  ... 另有 {len(drift) - 6} 例，見 code_drift.log')

    # ---------- 輸出 ----------
    out['_meta'] = meta
    with open(BASE / 'hist.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)

    with open(BASE / 'hist_anomalies.log', 'w', encoding='utf-8') as f:
        for yr in YEARS:
            f.write(f'===== {yr} =====\n')
            for b in all_bad[yr]:
                f.write(b + '\n')

    with open(BASE / 'code_drift.log', 'w', encoding='utf-8') as f:
        f.write('系組代碼\t' + '\t'.join(YEARS) + '\n')
        for code, mapping in drift:
            f.write(code + '\t' + '\t'.join(mapping.get(y, '') for y in YEARS) + '\n')

    print()
    print('已輸出 hist.json：', {y: len(out[y]) for y in YEARS})
    print('已輸出 hist_anomalies.log / code_drift.log')

    # ---------- 抽樣核對（115實戰驗證關鍵系組） ----------
    print()
    print('─── 抽樣核對：115學年度實戰驗證關鍵系組 ───')
    for key in ('國立臺灣大學|歷史學系',
                '國立臺灣大學|社會學系',
                '國立臺灣大學|生物產業傳播暨發展學系',
                '國立政治大學|歷史學系'):
        print(f'\n{key}')
        for yr in YEARS:
            v = out[yr].get(key)
            if v is None:
                print(f'  {yr}: （無此系組）')
            else:
                w = ' '.join(f'{k}x{val:.2f}' for k, val in v['subjects'].items())
                print(f'  {yr}: 代碼{v["code"]} 最低{v["score"]} 錄取{v["n"]}人 | {w}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
