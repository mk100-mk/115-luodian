# -*- coding: utf-8 -*-
"""
tools/parse_history_results.py

解析 112/113/114 學年度「大學分發入學 各系組最低錄取標準及錄取人數一覽表」
官方 PDF 榜單（tools/{yr}/{yr}_result_school_data.pdf），輸出統一格式 hist.json：

    hist[yr]['{校名}|{系組名}'] = {
        'code':     系組代碼（該年度代碼，年度間可能變動，故不作為跨年比對鍵）,
        'school':   校名,
        'dept':     系組名,
        'subjects': {科目: 加權, ...}（採計及加權）,
        'score':    最低錄取分數字串；該年度錄取人數為0（無人錄取/未招生）時為 None,
        'n':        錄取人數（含外加）
    }

解析方式：以 pdfplumber 的 extract_table()（依 PDF 表格格線切格）逐頁擷取，
避免文字流式擷取（extract_text）在「同分參酌」欄位因版面位移，
導致相鄰列資料互相污染的風險。

115學年度尚未分發放榜（成績於2026-08-03公布，分發放榜要到月底），
無最低錄取分資料可用，故不在本腳本處理範圍內；
115年僅能以官方組合排名法（見 parse_accu.py）估算落點。
"""
import json, re
import pdfplumber

WT = re.compile(r'^(?:術科|數甲|數乙|數A|數B|國|英|自|社|物|化|生|歷|地|公|術)x\d+(?:\.\d+)?$')
YEARS = ['112', '113', '114']


def parse_year(yr):
    path = f'{yr}/{yr}_result_school_data.pdf'
    recs = {}
    bad = []
    dup = 0
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            table = page.extract_table()
            if not table:
                bad.append(f'page {pi}: 無法擷取表格')
                continue
            for row in table[1:]:  # 跳過表頭列
                cells = [(c or '').replace('\n', '').strip() for c in row]
                if len(cells) < 6:
                    bad.append(f'page {pi}: 欄位不足 {cells}')
                    continue
                code, school, dept, wt_str, n_str, score_str = cells[:6]
                # 少數頁面因原始PDF字距渲染異常，校名/系組名中間會夾帶多餘空白
                # （例：'體 育學系'）；中文校系名稱不應含空白，故一律移除。
                school = re.sub(r'\s+', '', school)
                dept = re.sub(r'\s+', '', dept)
                if not re.fullmatch(r'\d{4}', code):
                    bad.append(f'page {pi}: 代碼異常 {cells}')
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
                    bad.append(f'page {pi}: 採計加權異常 {cells}')
                    continue
                try:
                    n_adm = int(n_str)
                except ValueError:
                    bad.append(f'page {pi}: 錄取人數異常 {cells}')
                    continue
                score = score_str if re.fullmatch(r'\d+\.\d{2}', score_str) else None
                key = (school, dept)
                if key in recs:
                    dup += 1
                    bad.append(f'page {pi}: 重複系組(校名+系組名) {key}')
                recs[key] = {
                    'code': code, 'school': school, 'dept': dept,
                    'subjects': subj, 'score': score, 'n': n_adm,
                }
    return recs, bad, dup


out = {}
for yr in YEARS:
    recs, bad, dup = parse_year(yr)
    out[yr] = {f'{k[0]}|{k[1]}': v for k, v in recs.items()}
    print(yr, '筆數:', len(recs), '| 異常:', len(bad), '| 重複key:', dup)
    for b in bad[:10]:
        print('  !', b)

json.dump(out, open('hist.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('已輸出 hist.json，總計：', {y: len(out[y]) for y in out})

# 抽樣核對
for yr in YEARS:
    for key in ('國立臺灣大學|歷史學系', '國立政治大學|歷史學系'):
        v = out[yr].get(key)
        print(yr, key, ':', v)
