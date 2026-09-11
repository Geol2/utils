# egov_impact_ui.py — 스프링 영향도 분석 로컬 UI
# 실행: python egov_impact_ui.py   (브라우저가 자동으로 열림, http://127.0.0.1:8765)
# 의존성: openpyxl (엑셀 저장에만 사용). 나머지는 표준 라이브러리.
import re, io, json, pathlib, datetime as dt, webbrowser, threading
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT = 8765
HIST_FILE = pathlib.Path(__file__).with_name('impact_history.json')
HIST_MAX = 30

# ---------- 공수 기준 (팀 기준으로 수정) ----------
BASE_MD = {'Table': 0.5, 'Mapper': 0.5, 'DAO': 0.3, 'Service': 0.5, 'Controller': 0.5, 'JSP': 0.7, 'JS': 0.5}
TEST_RATIO, BUFFER_RATIO = 0.3, 0.15
# ---------------------------------------------------

read = lambda p: p.read_text(encoding='utf-8', errors='ignore')

def add_workdays(d, n):
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5: n -= 1
    return d

def load_hist():
    try: return json.loads(HIST_FILE.read_text(encoding='utf-8'))
    except Exception: return []

def save_hist(entry):
    h = [x for x in load_hist() if not (x['root'] == entry['root'] and x['query'] == entry['query'])]
    h.insert(0, entry)
    HIST_FILE.write_text(json.dumps(h[:HIST_MAX], ensure_ascii=False, indent=1), encoding='utf-8')
    return h[:HIST_MAX]

def analyze(root, query, start, people):
    root = pathlib.Path(root); q = query.lower()
    if not root.is_dir(): raise ValueError(f'폴더를 찾을 수 없습니다: {root}')
    url_to_method, id_to_tables, id_to_xml, lines = {}, {}, {}, {}
    java_calls_id, view_calls_url, view_calls_fn = defaultdict(set), defaultdict(set), defaultdict(set)

    for j in root.rglob('*Controller.java'):
        t = read(j); lines[j] = t.count('\n')
        prefix = (re.search(r'@RequestMapping\(\s*"([^"]+)"', t) or [None, ''])[1]
        for url, name in re.findall(
            r'@(?:Request|Get|Post)Mapping\(\s*(?:value\s*=\s*)?"([^"]+)"[^)]*\)\s*(?:public\s+)?[\w<>\[\], ]+\s+(\w+)\s*\(', t):
            url_to_method[prefix + url] = (j, name)
    for x in root.rglob('*.xml'):
        t = read(x)
        for _, sid, body in re.findall(r'<(select|insert|update|delete)\s+id="([^"]+)"(.*?)</\1>', t, re.S):
            id_to_tables[sid] = {m.upper() for m in re.findall(r'\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_][\w.]*)', body, re.I)}
            id_to_xml[sid] = x
    for j in root.rglob('*.java'):
        t = read(j); lines[j] = t.count('\n')
        for sid in id_to_tables:
            if re.search(rf'["\.]{re.escape(sid)}\s*["(]', t): java_calls_id[j].add(sid)
    for f in list(root.rglob('*.jsp')) + list(root.rglob('*.js')):
        t = read(f); lines[f] = t.count('\n')
        for u in re.findall(r'(?:url\s*:\s*|action\s*=\s*|\.(?:post|get)\(\s*)["\']([^"\']+\.do)', t):
            view_calls_url[re.sub(r'^\$\{[^}]+\}', '', u)].add(f)
        for fn in re.findall(r'\b(fn_\w+)\s*\(', t): view_calls_fn[fn].add(f)

    items = {}
    def add(kind, path, name, impact, via=''):
        k = (kind, str(path), name)
        if k not in items or impact == '직접': items[k] = {'impact': impact, 'via': via}
    def kind_of(p):
        s = p.name
        if s.endswith('Controller.java'): return 'Controller'
        if 'DAO' in s or 'Dao' in s or 'Mapper.java' in s: return 'DAO'
        if s.endswith('.java'): return 'Service'
        if s.endswith('.jsp'): return 'JSP'
        if s.endswith('.js'): return 'JS'
        return 'Etc'

    for sid, tables in id_to_tables.items():
        hit_tbl = [t for t in tables if q in t.lower()]
        if hit_tbl or q in sid.lower():
            for t in hit_tbl: add('Table', '-', t, '직접')
            add('Mapper', id_to_xml[sid], sid, '직접', ','.join(hit_tbl))
            for j, ids in java_calls_id.items():
                if sid in ids:
                    add(kind_of(j), j, j.stem, '직접', sid)
                    cls = re.sub(r'(DAO|Dao|ServiceImpl|Service|Mapper)$', '', j.stem)
                    for url, (cj, m) in url_to_method.items():
                        if cls and cls in cj.stem:
                            add('Controller', cj, f'{cj.stem}.{m} ({url})', '간접', j.stem)
                            for v in view_calls_url.get(url, []): add(kind_of(v), v, v.name, '간접', url)
    for url, (cj, m) in url_to_method.items():
        if q in url.lower() or q in m.lower():
            add('Controller', cj, f'{cj.stem}.{m} ({url})', '직접')
            for v in view_calls_url.get(url, []): add(kind_of(v), v, v.name, '직접', url)
    for fn, files in view_calls_fn.items():
        if q in fn.lower():
            for v in files: add(kind_of(v), v, f'{v.name}::{fn}', '직접', fn)

    def md_of(kind, path, impact):
        ln = lines.get(pathlib.Path(path), 0)
        size = 1.0 if ln < 300 else 1.3 if ln < 1000 else 1.6
        return round(BASE_MD.get(kind, 0.3) * size * (1.0 if impact == '직접' else 0.5), 2)

    order = list(BASE_MD)
    rows = []
    for (kind, path, name), v in sorted(items.items(), key=lambda kv: (order.index(kv[0][0]) if kv[0][0] in order else 9, kv[0][2])):
        rows.append({'kind': kind, 'name': name, 'path': '' if path == '-' else path,
                     'impact': v['impact'], 'via': v['via'], 'md': md_of(kind, path, v['impact'])})

    dev = round(sum(r['md'] for r in rows), 2); test = round(dev * TEST_RATIO, 2)
    buf = round((dev + test) * BUFFER_RATIO, 2); total = round(dev + test + buf, 2)
    s = dt.date.fromisoformat(start)
    if s.weekday() >= 5: s = add_workdays(s, 1)
    days = int(-(-total // people)) if total else 0
    end = add_workdays(s, max(days - 1, 0))
    acc = 0.0; cur = s
    for r in rows:
        acc += r['md']; e = add_workdays(s, max(int(-(-acc // people)) - 1, 0))
        r['start'], r['end'] = cur.isoformat(), e.isoformat(); cur = e
    return {'query': query, 'rows': rows, 'summary': {
        'count': len(rows), 'direct': sum(r['impact'] == '직접' for r in rows),
        'indirect': sum(r['impact'] == '간접' for r in rows),
        'dev': dev, 'test': test, 'buffer': buf, 'total': total,
        'people': people, 'days': days, 'start': s.isoformat(), 'end': end.isoformat()}}

def write_xlsx(res):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook(); H = Font(bold=True, color='FFFFFF'); HF = PatternFill('solid', fgColor='305496')
    thin = Side(style='thin', color='BFBFBF'); B = Border(left=thin, right=thin, top=thin, bottom=thin)
    def sheet(ws, header, data, widths):
        ws.append(header)
        for c in ws[1]: c.font = H; c.fill = HF; c.alignment = Alignment(horizontal='center'); c.border = B
        for row in data: ws.append(row)
        for row in ws.iter_rows(min_row=2):
            for c in row: c.border = B
        for i, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = 'A2'
    sm = res['summary']; ws = wb.active; ws.title = '요약'
    sheet(ws, ['항목', '값'], [['변경 대상', res['query']], ['분석 일자', dt.date.today().isoformat()],
        ['영향 항목 수', sm['count']], ['직접 영향', sm['direct']], ['간접 영향', sm['indirect']],
        ['개발 공수 (MD)', sm['dev']], [f'테스트 공수 (MD, {int(TEST_RATIO*100)}%)', sm['test']],
        [f'버퍼 (MD, {int(BUFFER_RATIO*100)}%)', sm['buffer']], ['총 공수 (MD)', sm['total']],
        ['투입 인원', sm['people']], ['예상 기간 (영업일)', sm['days']], ['시작일', sm['start']], ['종료일', sm['end']]], [28, 20])
    ws2 = wb.create_sheet('영향목록')
    sheet(ws2, ['No', '구분', '항목', '파일', '영향', '경유', '공수(MD)', '시작일', '종료일', '담당자', '조치내용', '비고'],
          [[i + 1, r['kind'], r['name'], r['path'], r['impact'], r['via'], r['md'], r['start'], r['end'], r.get('owner', ''), r.get('action', ''), r.get('note', '')]
           for i, r in enumerate(res['rows'])], [5, 11, 40, 55, 7, 22, 9, 11, 11, 10, 30, 20])
    ws2.auto_filter.ref = ws2.dimensions
    ws3 = wb.create_sheet('공수기준')
    sheet(ws3, ['구분', '기본 MD/항목', '비고'], [[k, v, ''] for k, v in BASE_MD.items()] +
          [['파일크기 가중', '1.0 / 1.3 / 1.6', '<300 / <1000 / 1000+ 라인'], ['간접영향', 'x0.5', ''],
           ['테스트', f'x{TEST_RATIO}', '개발공수 대비'], ['버퍼', f'x{BUFFER_RATIO}', '개발+테스트 대비']], [16, 16, 30])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

HTML = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>영향도 분석</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef1f5;--panel:#fff;--ink:#1c2430;--muted:#66717f;--line:#d5dbe3;--acc:#1f4e8c;--acc2:#e8f0fb;--direct:#b23a2a;--indirect:#8a6d1f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Pretendard,"Malgun Gothic",system-ui,sans-serif}
header{background:var(--acc);color:#fff;padding:14px 24px;display:flex;align-items:baseline;gap:14px}
header h1{margin:0;font-size:18px;font-weight:600}header span{opacity:.75;font-size:13px}
main{display:grid;grid-template-columns:300px 1fr;gap:16px;padding:16px 24px;min-height:calc(100vh - 52px)}
@media(max-width:820px){main{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:16px}
label{display:block;font-size:12px;color:var(--muted);margin:10px 0 4px}label:first-child{margin-top:0}
input{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:4px;font:inherit}input:focus{outline:2px solid var(--acc);outline-offset:1px;border-color:var(--acc)}
.row{display:flex;gap:6px}.row input{flex:1}
button{font:inherit;padding:8px 14px;border-radius:4px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
button.ghost{background:#fff;color:var(--acc)}button:disabled{opacity:.5;cursor:default}
.actions{display:flex;gap:8px;margin-top:16px}.hint{font-size:12px;color:var(--muted);margin-top:14px;line-height:1.6}
.msg{margin-top:12px;padding:8px 10px;border-radius:4px;font-size:13px;display:none}.msg.err{display:block;background:#fbeaea;color:#8a2a1e}.msg.ok{display:block;background:var(--acc2);color:var(--acc)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:14px}
.stat{padding:10px 12px;border:1px solid var(--line);border-radius:4px}.stat b{display:block;font-size:22px;font-weight:600;line-height:1.2}.stat span{font-size:12px;color:var(--muted)}
.stat.total{background:var(--acc2);border-color:var(--acc)}
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}.toolbar select,.toolbar input{padding:6px 8px;border:1px solid var(--line);border-radius:4px;font:inherit;width:auto}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap}
th{position:sticky;top:0;background:#f6f8fb;font-weight:600;color:var(--muted);font-size:12px}
td.path{color:var(--muted);font-size:12px;max-width:380px;overflow:hidden;text-overflow:ellipsis}
.tag{display:inline-block;padding:1px 7px;border-radius:3px;font-size:12px}.tag.direct{background:#fbe9e6;color:var(--direct)}.tag.indirect{background:#fbf3df;color:var(--indirect)}
td input{padding:4px 6px;font-size:12px;min-width:90px}
.empty{padding:60px 0;text-align:center;color:var(--muted)}
.hist{margin-top:18px;border-top:1px solid var(--line);padding-top:12px}.hist h2{font-size:12px;color:var(--muted);font-weight:600;margin:0 0 6px}
.hist ul{list-style:none;margin:0;padding:0;max-height:260px;overflow:auto}.hist li{display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:4px;cursor:pointer;font-size:12px}
.hist li:hover{background:var(--acc2)}.hist li b{font-weight:600;color:var(--ink)}.hist li .r{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.hist li .m{color:var(--muted);white-space:nowrap}.hist li .x{border:0;background:none;color:var(--muted);padding:0 4px;cursor:pointer;font-size:14px;line-height:1}.hist li .x:hover{color:var(--direct)}
.hist .none{font-size:12px;color:var(--muted);padding:4px 8px}
</style></head><body>
<header><h1>영향도 분석</h1><span>Spring MVC · JSP/JS → Controller → Service → Mapper → 테이블</span></header>
<main>
<section class="panel">
 <label for="root">소스 루트 폴더</label>
 <div class="row"><input id="root" list="roots" placeholder="D:\workspace\dWorks\src"><button class="ghost" id="pick" title="폴더 선택">…</button></div>
 <label for="q">검색어</label><input id="q" list="queries" placeholder="TB_USER / selectUserList / /user/list / fn_search">
 <label for="start">작업 시작일</label><input id="start" type="date">
 <label for="people">투입 인원</label><input id="people" type="number" step="0.5" min="0.5" value="1">
 <div class="actions"><button id="run">분석 실행</button><button class="ghost" id="export" disabled>엑셀로 저장</button></div>
 <div class="msg" id="msg"></div>
 <datalist id="roots"></datalist><datalist id="queries"></datalist>
 <div class="hist"><h2>최근 분석</h2><ul id="hist"></ul></div>
 <div class="hint">검색어는 테이블명, mapper id, 컨트롤러 URL 일부, JS 함수명(fn_xxx) 모두 가능합니다. 대소문자 구분 없이 부분 일치로 찾습니다.<br><br>표에서 담당자·조치내용·비고를 입력하면 엑셀에 같이 저장됩니다.</div>
</section>
<section class="panel">
 <div id="stats" class="stats"></div>
 <div class="toolbar">
  <select id="fkind"><option value="">구분: 전체</option><option>Table</option><option>Mapper</option><option>DAO</option><option>Service</option><option>Controller</option><option>JSP</option><option>JS</option></select>
  <select id="fimpact"><option value="">영향: 전체</option><option>직접</option><option>간접</option></select>
  <input id="ftext" placeholder="항목·파일 필터">
  <span id="fcount" style="color:var(--muted);font-size:12px"></span>
 </div>
 <div class="tw"><table><thead><tr><th>No</th><th>구분</th><th>항목</th><th>파일</th><th>영향</th><th>경유</th><th>MD</th><th>시작</th><th>종료</th><th>담당자</th><th>조치내용</th><th>비고</th></tr></thead>
 <tbody id="tb"><tr><td colspan="12" class="empty">소스 루트와 검색어를 입력하고 분석을 실행하세요.</td></tr></tbody></table></div>
</section>
</main>
<script>
const $=s=>document.querySelector(s);let res=null;
$('#start').value=new Date().toISOString().slice(0,10);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function msg(t,cls){const m=$('#msg');m.textContent=t;m.className='msg '+(cls||'');}
function stats(){const s=res.summary;$('#stats').innerHTML=[
 ['영향 항목',s.count+'건',`직접 ${s.direct} · 간접 ${s.indirect}`],['개발 공수',s.dev+' MD',''],['테스트 · 버퍼',(s.test+s.buffer).toFixed(2)+' MD',`${s.test} + ${s.buffer}`],
 ['총 공수',s.total+' MD',`${s.people}명 투입`,'total'],['예상 기간',s.days+' 영업일',`${s.start} ~ ${s.end}`]
].map(([l,v,sub,c])=>`<div class="stat ${c||''}"><span>${l}</span><b>${v}</b><span>${sub}</span></div>`).join('');}
function render(){const k=$('#fkind').value,i=$('#fimpact').value,t=$('#ftext').value.toLowerCase();
 const rows=res.rows.map((r,idx)=>({r,idx})).filter(({r})=>(!k||r.kind===k)&&(!i||r.impact===i)&&(!t||(r.name+r.path+r.via).toLowerCase().includes(t)));
 $('#fcount').textContent=`${rows.length} / ${res.rows.length}`;
 if(!rows.length){$('#tb').innerHTML='<tr><td colspan="12" class="empty">일치하는 항목이 없습니다.</td></tr>';return;}
 $('#tb').innerHTML=rows.map(({r,idx})=>`<tr><td>${idx+1}</td><td>${r.kind}</td><td>${esc(r.name)}</td><td class="path" title="${esc(r.path)}">${esc(r.path)}</td>
 <td><span class="tag ${r.impact==='직접'?'direct':'indirect'}">${r.impact}</span></td><td>${esc(r.via)}</td><td>${r.md}</td><td>${r.start}</td><td>${r.end}</td>
 <td><input data-i="${idx}" data-f="owner" value="${esc(r.owner)}"></td><td><input data-i="${idx}" data-f="action" value="${esc(r.action)}"></td><td><input data-i="${idx}" data-f="note" value="${esc(r.note)}"></td></tr>`).join('');}
$('#tb').addEventListener('input',e=>{const d=e.target.dataset;if(d.i!==undefined)res.rows[d.i][d.f]=e.target.value;});
['#fkind','#fimpact','#ftext'].forEach(s=>$(s).addEventListener('input',()=>res&&render()));
$('#run').onclick=async()=>{const body={root:$('#root').value.trim(),query:$('#q').value.trim(),start:$('#start').value,people:parseFloat($('#people').value)||1};
 if(!body.root||!body.query){msg('소스 루트와 검색어를 입력하세요.','err');return;}
 $('#run').disabled=true;msg('분석 중…','ok');
 try{const r=await fetch('/run',{method:'POST',body:JSON.stringify(body)});const j=await r.json();if(!r.ok)throw new Error(j.error);
  res=j;res.rows.forEach(x=>{x.owner='';x.action='';x.note='';});hist=j.history||hist;renderHist();stats();render();$('#export').disabled=false;
  msg(res.rows.length?`${res.rows.length}건 찾았습니다.`:'0건입니다. 검색어와 소스 루트를 확인하세요.','ok');
 }catch(e){msg('분석 실패: '+e.message,'err');}finally{$('#run').disabled=false;}};
$('#export').onclick=async()=>{const r=await fetch('/export',{method:'POST',body:JSON.stringify(res)});if(!r.ok){msg('엑셀 저장 실패: '+(await r.json()).error,'err');return;}
 const b=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=`영향도분석서_${res.query}_${res.summary.start}.xlsx`;a.click();msg('엑셀을 저장했습니다.','ok');};
$('#pick').onclick=async()=>{const r=await fetch('/pick');const j=await r.json();if(j.path)$('#root').value=j.path;else if(j.error)msg(j.error,'err');};
let hist=[];
function renderHist(){$('#roots').innerHTML=[...new Set(hist.map(h=>h.root))].map(r=>`<option value="${esc(r)}">`).join('');
 $('#queries').innerHTML=[...new Set(hist.map(h=>h.query))].map(q=>`<option value="${esc(q)}">`).join('');
 $('#hist').innerHTML=hist.length?hist.map((h,i)=>`<li data-i="${i}" title="${esc(h.root)}"><b>${esc(h.query)}</b><span class="r">${esc(h.root)}</span><span class="m">${h.count}건 · ${h.total}MD · ${h.at}</span><button class="x" data-del="${i}" title="삭제">×</button></li>`).join(''):'<li class="none">아직 없습니다. 분석을 실행하면 여기에 쌓입니다.</li>';}
$('#hist').addEventListener('click',async e=>{const d=e.target.dataset;
 if(d.del!==undefined){const h=hist[d.del];const r=await fetch('/history/delete',{method:'POST',body:JSON.stringify({root:h.root,query:h.query})});hist=await r.json();renderHist();return;}
 const li=e.target.closest('li');if(!li||li.dataset.i===undefined)return;const h=hist[li.dataset.i];
 $('#root').value=h.root;$('#q').value=h.query;$('#people').value=h.people;$('#q').focus();});
fetch('/history').then(r=>r.json()).then(j=>{hist=j;renderHist();if(hist[0]){$('#root').value=hist[0].root;$('#people').value=hist[0].people;}});
$('#q').addEventListener('keydown',e=>{if(e.key==='Enter')$('#run').click();});
</script></body></html>'''

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        self.send_response(code); self.send_header('Content-Type', ctype)
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def _json(self):
        return json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
    def do_GET(self):
        p = urlparse(self.path).path
        if p == '/': return self._send(200, HTML.encode('utf-8'), 'text/html; charset=utf-8')
        if p == '/history': return self._send(200, json.dumps(load_hist(), ensure_ascii=False).encode('utf-8'))
        if p == '/pick':
            try:
                import tkinter as tk; from tkinter import filedialog
                r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)
                d = filedialog.askdirectory(title='소스 루트 폴더 선택'); r.destroy()
                return self._send(200, json.dumps({'path': d.replace('/', '\\') if d else ''}).encode())
            except Exception as e:
                return self._send(200, json.dumps({'error': f'폴더 선택창을 열 수 없습니다 ({e}). 경로를 직접 입력하세요.'}).encode())
        self._send(404, b'{}')
    def do_POST(self):
        p = urlparse(self.path).path
        try:
            b = self._json()
            if p == '/run':
                res = analyze(b['root'], b['query'], b['start'], float(b.get('people') or 1))
                res['history'] = save_hist({'root': b['root'], 'query': b['query'], 'people': float(b.get('people') or 1),
                                            'count': res['summary']['count'], 'total': res['summary']['total'], 'at': dt.datetime.now().strftime('%m-%d %H:%M')})
                return self._send(200, json.dumps(res, ensure_ascii=False).encode('utf-8'))
            if p == '/history/delete':
                h = [x for x in load_hist() if not (x['root'] == b['root'] and x['query'] == b['query'])]
                HIST_FILE.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding='utf-8')
                return self._send(200, json.dumps(h, ensure_ascii=False).encode('utf-8'))
            if p == '/export':
                return self._send(200, write_xlsx(b), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                  {'Content-Disposition': 'attachment; filename="impact.xlsx"'})
            self._send(404, b'{}')
        except ModuleNotFoundError:
            self._send(500, json.dumps({'error': 'openpyxl이 없습니다. python -m pip install openpyxl'}, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self._send(400, json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))

if __name__ == '__main__':
    srv = HTTPServer(('127.0.0.1', PORT), H)
    url = f'http://127.0.0.1:{PORT}'
    print(f'영향도 분석 UI: {url}  (종료: Ctrl+C)')
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
