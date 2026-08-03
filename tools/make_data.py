# -*- coding: utf-8 -*-
"""
tools/make_data.py

整合：
  - r115q.json：115學年度1,764系組基本資料（採計科目/加權、學測5標檢定、英聽門檻）
  - hist.json：112/113/114 三年各系組最低錄取分（tools/parse_history_results.py 產生）
  - accu.json：115年「採計組合成績人數累計表」查詢資料庫（tools/parse_accu.py 產生）
  - tools/114/count-114.xlsx、tools/115/count-115.xlsx：回流後分發入學總名額

輸出 data/data.json（前端 fetch 載入用）。

輸出格式（頂層物件，非陣列——與舊版純陣列格式不相容，需搭配 site/app.js 同步更新讀取方式）：
{
  "rows": [
    {
      "c": 系組代碼, "s": 校名, "d": 系組名, "k": 檢定文字原文,
      "o": [科目代碼,...]（依簡章原始順序）,
      "w": {科目代碼: 加權,...},
      "e": 英聽門檻(A/B，若有),
      "q": 學測5標檢定條件(若有),
      "m4"/"a4": 114最低分/114採計科目加權,
      "m3"/"a3": 113最低分/113採計科目加權,
      "m2"/"a2": 112最低分/112採計科目加權
        （115尚未分發放榜，無最低分資料，故無 m5/a5）,
      "st":  115回流後分發入學總名額（若查得到）,
      "st4": 114回流後分發入學總名額（若查得到，供與st比較增減）,
      "cx":  官方組合排名表索引（對應 combo 陣列；僅「採計科目加權皆為1.00」
             且115年 accu 資料庫查得到對應科目組合的系組才有此欄位。
             前端依使用者輸入之總分即時查表算出全國名次/總人數/PR，
             不在建置期預先計算——因為分數是使用者當下輸入的，只有前端知道）
    }, ...
  ],
  "combo": [
    {"su": [科目代碼,...], "b": [[區間上限分數, 該區間以上累計人數, 累計百分比(PR)], ...]},
    ...
  ]（僅收錄至少被一個系組引用之115年官方組合，依科目集合去重，避免資料重複膨脹）
}

設計說明：
- 「採計科目是否與前一年不同」不另存欄位（例如 same_as_prev）。理由：a2/a3/a4/w
  已完整保留各年度採計科目與加權，前端本就有 sameW() 逐年比對函式（見 site/app.js），
  在畫面渲染時即時比較即可得到完全相同的結果，沒有必要把衍生結果重複寫進資料檔——
  多存一份等於多一個可能與來源不同步的資料版本，維護上是負擔而非資產。
  展開四年歷史（112~115）時，前端一樣可用同一函式逐年互相比較。
- combo 表僅收錄「115年」資料，因為115正是唯一缺乏最低錄取分、需要靠官方組合排名
  作為替代訊號的年度；112~114已有 hist.json 的實際最低錄取分可用，不需要官方組合表。
"""
import json
import re
import pandas as pd


def nk(s, d):
    """正規化比對鍵：校名 + 系組名（移除括號與空白），用於跨年度/跨檔案資料比對。"""
    return s + '|' + re.sub(r'[()（）\s]', '', d)


# ---------- 載入基礎資料 ----------
r115 = json.load(open('r115q.json', encoding='utf-8'))
hist = json.load(open('hist.json', encoding='utf-8'))
accu = json.load(open('accu.json', encoding='utf-8'))

hist2 = {y: {nk(v['school'], v['dept']): v for v in hist[y].values()} for y in hist}


# ---------- 回流後名額（114 / 115） ----------
def load_seats(path):
    df = pd.read_excel(path, header=0)
    df.columns = [str(c).replace('\n', '') for c in df.columns]
    ci_school = next(c for c in df.columns if '學校名稱' in c)
    ci_dept = next(c for c in df.columns if '學系組名稱' in c)
    ci_seat = next(c for c in df.columns if '回流後分發入學總名額' in c)
    out = {}
    dup = 0
    for _, row in df.iterrows():
        school, dept, seat = row[ci_school], row[ci_dept], row[ci_seat]
        if pd.isna(school) or pd.isna(dept) or pd.isna(seat):
            continue
        key = nk(str(school).strip(), str(dept).strip())
        if key in out:
            dup += 1
        out[key] = int(seat)
    return out, dup


seats15, dup15 = load_seats('115/count-115.xlsx')
seats14, dup14 = load_seats('114/count-114.xlsx')
print('115名額筆數:', len(seats15), '重複key:', dup15)
print('114名額筆數:', len(seats14), '重複key:', dup14)


# ---------- 官方組合排名（僅115年，依科目集合去重） ----------
accu_by_key = {tuple(g['subjects']): g for g in accu['115']}
combo_list = []
combo_index = {}


def get_combo_index(subj_tuple):
    if subj_tuple in combo_index:
        return combo_index[subj_tuple]
    g = accu_by_key.get(subj_tuple)
    if g is None:
        return None
    bands_compact = [[b['upper'], b['cum_hi'], b['cum_lo_pct']] for b in g['bands']]
    idx = len(combo_list)
    combo_list.append({'su': list(subj_tuple), 'b': bands_compact})
    combo_index[subj_tuple] = idx
    return idx


# ---------- 逐系組整合 ----------
out_rows = []
for r in r115:
    k = nk(r['school'], r['dept'])
    row = {
        'c': r['code'], 's': r['school'], 'd': r['dept'], 'k': r['check'],
        'o': [x[0] for x in sorted(r['subjects'], key=lambda t: (t[2] or 9))],
        'w': {x[0]: x[1] for x in r['subjects']},
    }
    m = re.search(r'英\s*聽\s*[（(]?\s*([ABＡＢ])\s*級', r['check'])
    if m:
        row['e'] = {'Ａ': 'A', 'Ｂ': 'B'}.get(m.group(1), m.group(1))
    if r.get('q'):
        row['q'] = [[[s, d] for s, d in cl] for cl in r['q']]

    for y, tag in (('114', '4'), ('113', '3'), ('112', '2')):
        h = hist2[y].get(k)
        if h:
            row['m' + tag] = float(h['score']) if h['score'] else None
            row['a' + tag] = h['subjects']

    st = seats15.get(k)
    st4 = seats14.get(k)
    if st is not None:
        row['st'] = st
    if st4 is not None:
        row['st4'] = st4

    if all(abs(v - 1.0) < 1e-9 for v in row['w'].values()):
        subj_tuple = tuple(sorted(row['w'].keys()))
        cx = get_combo_index(subj_tuple)
        if cx is not None:
            row['cx'] = cx

    out_rows.append(row)

output = {'rows': out_rows, 'combo': combo_list}
json.dump(output, open('../data/data.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))

# ---------- 統計摘要 ----------
print('系組數:', len(out_rows))
print('官方組合排名表數量(去重後):', len(combo_list))
print('有官方組合排名(cx)可查的系組數:', sum(1 for r in out_rows if 'cx' in r))
print('有115名額(st)資料的系組數:', sum(1 for r in out_rows if 'st' in r))
print('有114名額(st4)資料的系組數:', sum(1 for r in out_rows if 'st4' in r))
print('有114最低分(m4)資料的系組數:', sum(1 for r in out_rows if 'm4' in r))
print('有113最低分(m3)資料的系組數:', sum(1 for r in out_rows if 'm3' in r))
print('有112最低分(m2)資料的系組數:', sum(1 for r in out_rows if 'm2' in r))

# 抽樣核對關鍵系組
print()
for name in ('國立臺灣大學|歷史學系', '國立政治大學|歷史學系'):
    row = next((r for r in out_rows if nk(r['s'], r['d']) == name), None)
    print(name, ':', row)
