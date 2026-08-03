# -*- coding: utf-8 -*-
# 主解析器 v2：全面改用字元座標，修正(1)單一區塊頁被跳過 (2)檢定欄與科目欄字詞黏合造成科目遺漏
import pdfplumber, re, json

SUBJ_MAP = {
    '國文(學測)':'國','英文(學測)':'英','數學A(學測)':'數A','數學B(學測)':'數B',
    '自然(學測)':'自','社會(學測)':'社',
    '數學甲(分科)':'數甲','數學乙(分科)':'數乙','物理(分科)':'物','化學(分科)':'化',
    '生物(分科)':'生','歷史(分科)':'歷','地理(分科)':'地','公民與社會(分科)':'公',
}
CLEAN = re.compile(r'[\s\u3000\xa0]+')

def clines(chars, tol=5):
    rows = []
    for c in sorted(chars, key=lambda c: c['top']):
        for r in rows:
            if abs(r['top'] - c['top']) <= tol:
                r['cs'].append(c); break
        else:
            rows.append({'top': c['top'], 'cs': [c]})
    return rows

pdf = pdfplumber.open('/mnt/user-data/uploads/115recruit.pdf')
records, warnings = [], []

for pi in range(23, 267):
    page = pdf.pages[pi]
    text = page.extract_text() or ''
    m = re.search(r'校名：(.+?)\((\d{3})\)', text)
    if not m: continue
    school = m.group(1).strip()
    fw = [w for w in page.extract_words() if w['text'].startswith('其他各類外加')]
    footer_top = min((w['top'] for w in fw), default=784)
    chars = [c for c in page.chars if c['top'] < footer_top - 2]
    seps = sorted(set(round(r['top']) for r in page.rects if r['width']>300 and r['height']<3))
    if not seps:
        warnings.append(f'p{pi+1} no separators'); continue
    bounds = [(seps[i], seps[i+1]) for i in range(len(seps)-1)] + [(seps[-1], 784)]
    for (y0, y1) in bounds:
        bc = [c for c in chars if y0 < (c['top']+c['bottom'])/2 <= y1]
        if not bc: continue
        code = CLEAN.sub('', ''.join(c['text'] for c in sorted(
            [c for c in bc if 73<=c['x0']<=95 and c['text'].isdigit()],
            key=lambda c: (c['top'], c['x0']))))
        if not re.fullmatch(r'\d{4}', code): 
            if code: warnings.append(f'p{pi+1} bad code [{code}]')
            continue
        dept = CLEAN.sub('', ''.join(c['text'] for c in sorted(
            [c for c in bc if c['x0'] < 72], key=lambda c: (c['top'], c['x0']))))
        chk = ' '.join(CLEAN.sub('', ''.join(c['text'] for c in sorted(r['cs'], key=lambda c: c['x0'])))
                       for r in clines([c for c in bc if 168 <= c['x0'] <= 250]))
        chk = chk.replace('---','').strip()
        subjects = []
        for r in clines([c for c in bc if 248 <= c['x0'] <= 396]):
            cs = sorted(r['cs'], key=lambda c: c['x0'])
            nm = CLEAN.sub('', ''.join(c['text'] for c in cs if 248 <= c['x0'] <= 330 and c['text'] != 'x'))
            if not nm or set(nm) <= set('-—') or nm.isdigit() or '空白' in nm: continue
            wts = CLEAN.sub('', ''.join(c['text'] for c in cs if 334 <= c['x0'] <= 360))
            ods = CLEAN.sub('', ''.join(c['text'] for c in cs if 372 <= c['x0'] <= 396))
            mw = re.fullmatch(r'x?(\d+\.\d+)', wts)
            if not mw:
                warnings.append(f'p{pi+1} {code} [{nm}] weight?[{wts}]'); continue
            if nm in SUBJ_MAP:
                subjects.append((SUBJ_MAP[nm], float(mw.group(1)), int(ods) if ods.isdigit() else None))
            elif '術' in nm:
                subjects.append(('術', float(mw.group(1)), int(ods) if ods.isdigit() else None))
            else:
                warnings.append(f'p{pi+1} {code} unknown [{nm}]')
        if not (3 <= len(subjects) <= 5):
            warnings.append(f'p{pi+1} {code} {dept} subject count={len(subjects)}')
        if not subjects: continue
        records.append({'code':code,'school':school,'dept':dept,'check':chk,'subjects':subjects})

print('records:', len(records), 'warnings:', len(warnings))
for w in warnings[:30]: print(' !', w)
json.dump(records, open('r115.json','w',encoding='utf-8'), ensure_ascii=False)
import collections
print('dist:', dict(collections.Counter(len(r['subjects']) for r in records)))
codes = [r['code'] for r in records]
print('dup:', len(codes)-len(set(codes)))
