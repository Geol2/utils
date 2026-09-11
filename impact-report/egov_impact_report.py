# egov_impact_report.py
# 사용: python egov_impact_report.py ./src TB_USER --start 2026-09-14 --people 2
#   pip install openpyxl
# 검색어: 테이블명 / mapper id / 컨트롤러 URL / JS 함수명(fn_xxx) 아무거나
import re, sys, argparse, pathlib, datetime as dt
from collections import defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ---------- 공수 기준 (팀 기준으로 수정) ----------
# 항목당 기본 MD. 직접영향=1.0배, 간접영향=0.5배, 테스트는 별도 계산
BASE_MD = {
    'Table':      0.5,   # DDL/데이터 이관 검토
    'Mapper':     0.5,   # SQL 수정
    'DAO':        0.3,
    'Service':    0.5,
    'Controller': 0.5,
    'JSP':        0.7,   # 화면 수정 + 화면 확인
    'JS':         0.5,
}
TEST_RATIO   = 0.3     # 개발 공수 대비 테스트 공수 비율
BUFFER_RATIO = 0.15    # 리스크 버퍼
# ---------------------------------------------------

ap = argparse.ArgumentParser()
ap.add_argument('root'); ap.add_argument('query')
ap.add_argument('--start', default=dt.date.today().isoformat())
ap.add_argument('--people', type=float, default=1)
ap.add_argument('--out', default='영향도분석서.xlsx')
a = ap.parse_args()
root, q = pathlib.Path(a.root), a.query.lower()
read = lambda p: p.read_text(encoding='utf-8', errors='ignore')

# ---------- 1. 인덱스 구축 ----------
url_to_method, id_to_tables, id_to_xml = {}, {}, {}
java_calls_id = defaultdict(set)     # java stem -> mapper ids
view_calls_url = defaultdict(set)    # url -> jsp/js files
view_calls_fn  = defaultdict(set)    # fn_xxx -> jsp/js files
lines = {}

for j in root.rglob('*Controller.java'):
    t = read(j); lines[j] = t.count('\n')
    prefix = (re.search(r'@RequestMapping\(\s*"([^"]+)"', t) or [None, ''])[1]
    for url, name in re.findall(
        r'@(?:Request|Get|Post)Mapping\(\s*(?:value\s*=\s*)?"([^"]+)"[^)]*\)\s*(?:public\s+)?[\w<>\[\], ]+\s+(\w+)\s*\(', t):
        url_to_method[prefix + url] = (j, name)

for x in root.rglob('*.xml'):
    t = read(x)
    for _, sid, body in re.findall(r'<(select|insert|update|delete)\s+id="([^"]+)"(.*?)</\1>', t, re.S):
        id_to_tables[sid] = {m.upper() for m in re.findall(
            r'\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_][\w.]*)', body, re.I)}
        id_to_xml[sid] = x

for j in root.rglob('*.java'):
    t = read(j); lines[j] = t.count('\n')
    for sid in id_to_tables:
        if re.search(rf'["\.]{re.escape(sid)}\s*["(]', t):
            java_calls_id[j].add(sid)

for f in list(root.rglob('*.jsp')) + list(root.rglob('*.js')):
    t = read(f); lines[f] = t.count('\n')
    for u in re.findall(r'(?:url\s*:\s*|action\s*=\s*|\.(?:post|get)\(\s*)["\']([^"\']+\.do)', t):
        view_calls_url[re.sub(r'^\$\{[^}]+\}', '', u)].add(f)
    for fn in re.findall(r'\b(fn_\w+)\s*\(', t):
        view_calls_fn[fn].add(f)

# ---------- 2. 영향 항목 수집 ----------
items = {}  # (kind, path, name) -> {'impact': 직접|간접, 'via': str}
def add(kind, path, name, impact, via=''):
    k = (kind, str(path), name)
    if k not in items or impact == '직접':
        items[k] = {'impact': impact, 'via': via}

def kind_of(p):
    s = p.name
    if s.endswith('Controller.java'): return 'Controller'
    if 'DAO' in s or 'Dao' in s or 'Mapper.java' in s: return 'DAO'
    if s.endswith('.java'): return 'Service'
    if s.endswith('.jsp'): return 'JSP'
    if s.endswith('.js'): return 'JS'
    return 'Etc'

# 테이블 / mapper id 기준
for sid, tables in id_to_tables.items():
    hit_tbl = [t for t in tables if q in t.lower()]
    if hit_tbl or q in sid.lower():
        for t in hit_tbl: add('Table', '-', t, '직접')
        add('Mapper', id_to_xml[sid], sid, '직접' if hit_tbl else '직접', ','.join(hit_tbl))
        for j, ids in java_calls_id.items():
            if sid in ids:
                add(kind_of(j), j, j.stem, '직접', sid)
                cls = re.sub(r'(DAO|Dao|ServiceImpl|Service|Mapper)$', '', j.stem)
                for url, (cj, m) in url_to_method.items():
                    if cls and cls in cj.stem:
                        add('Controller', cj, f'{cj.stem}.{m} ({url})', '간접', j.stem)
                        for v in view_calls_url.get(url, []):
                            add(kind_of(v), v, v.name, '간접', url)

# URL 기준
for url, (cj, m) in url_to_method.items():
    if q in url.lower() or q in m.lower():
        add('Controller', cj, f'{cj.stem}.{m} ({url})', '직접')
        for v in view_calls_url.get(url, []): add(kind_of(v), v, v.name, '직접', url)

# JS 함수 기준
for fn, files in view_calls_fn.items():
    if q in fn.lower():
        for v in files: add(kind_of(v), v, f'{v.name}::{fn}', '직접', fn)

# ---------- 3. 공수/일정 ----------
def md_of(kind, path, impact):
    base = BASE_MD.get(kind, 0.3)
    p = pathlib.Path(path)
    ln = lines.get(p, 0)
    size = 1.0 if ln < 300 else 1.3 if ln < 1000 else 1.6   # 파일 크기 가중
    return round(base * size * (1.0 if impact == '직접' else 0.5), 2)

rows = []
for (kind, path, name), v in sorted(items.items(), key=lambda kv: (list(BASE_MD).index(kv[0][0]) if kv[0][0] in BASE_MD else 9, kv[0][2])):
    rows.append([kind, name, path if path != '-' else '', v['impact'], v['via'], md_of(kind, path, v['impact'])])

dev_md  = round(sum(r[5] for r in rows), 2)
test_md = round(dev_md * TEST_RATIO, 2)
buf_md  = round((dev_md + test_md) * BUFFER_RATIO, 2)
total   = round(dev_md + test_md + buf_md, 2)

def add_workdays(d, n):
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5: n -= 1
    return d
start = dt.date.fromisoformat(a.start)
if start.weekday() >= 5: start = add_workdays(start, 1)
days = -(-total // a.people)  # ceil
end = add_workdays(start, max(int(days) - 1, 0))

# 항목별 일정: 순차 배분 (투입인원 반영)
cur = start; acc = 0.0
for r in rows:
    s = cur
    acc += r[5]
    e = add_workdays(start, max(int(-(-acc // a.people)) - 1, 0))
    r += [s.isoformat(), e.isoformat()]
    cur = e

# ---------- 4. 엑셀 ----------
wb = Workbook()
H = Font(bold=True, color='FFFFFF'); HF = PatternFill('solid', fgColor='305496')
thin = Side(style='thin', color='BFBFBF'); B = Border(left=thin, right=thin, top=thin, bottom=thin)

def sheet(ws, header, data, widths):
    ws.append(header)
    for c in ws[1]: c.font = H; c.fill = HF; c.alignment = Alignment(horizontal='center'); c.border = B
    for row in data:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for c in row: c.border = B
    for i, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A2'

ws = wb.active; ws.title = '요약'
sheet(ws, ['항목', '값'], [
    ['변경 대상', a.query], ['분석 일자', dt.date.today().isoformat()],
    ['영향 항목 수', len(rows)],
    ['직접 영향', sum(1 for r in rows if r[3] == '직접')], ['간접 영향', sum(1 for r in rows if r[3] == '간접')],
    ['개발 공수 (MD)', dev_md], [f'테스트 공수 (MD, {int(TEST_RATIO*100)}%)', test_md],
    [f'버퍼 (MD, {int(BUFFER_RATIO*100)}%)', buf_md], ['총 공수 (MD)', total],
    ['투입 인원', a.people], ['예상 기간 (영업일)', int(days)],
    ['시작일', start.isoformat()], ['종료일', end.isoformat()],
], [28, 20])

ws2 = wb.create_sheet('영향목록')
sheet(ws2, ['No', '구분', '항목', '파일', '영향', '경유', '공수(MD)', '시작일', '종료일', '담당자', '조치내용', '비고'],
      [[i + 1] + r + ['', '', ''] for i, r in enumerate(rows)],
      [5, 11, 40, 55, 7, 22, 9, 11, 11, 10, 30, 20])
ws2.auto_filter.ref = ws2.dimensions

ws3 = wb.create_sheet('공수기준')
sheet(ws3, ['구분', '기본 MD/항목', '비고'],
      [[k, v, ''] for k, v in BASE_MD.items()] +
      [['파일크기 가중', '1.0 / 1.3 / 1.6', '<300 / <1000 / 1000+ 라인'],
       ['간접영향', 'x0.5', ''], ['테스트', f'x{TEST_RATIO}', '개발공수 대비'], ['버퍼', f'x{BUFFER_RATIO}', '개발+테스트 대비']],
      [16, 16, 30])

wb.save(a.out)
print(f'{a.out} 저장 — 영향 {len(rows)}건, 총 {total} MD, {start}~{end} ({int(days)} 영업일 / {a.people}명)')
