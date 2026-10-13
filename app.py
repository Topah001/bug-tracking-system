"""Local bug-tracking board with a SQLite database and standard-library web server."""
from __future__ import annotations
import json,os,sqlite3
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
DB_PATH=Path(os.environ.get('BUG_TRACKER_DB',Path(__file__).with_name('bugs.db')))
STATUSES={'new','triaged','in progress','resolved','closed'}; PRIORITIES={'low','medium','high','critical'}
def stamp():return datetime.now(timezone.utc).isoformat()
from contextlib import contextmanager
@contextmanager
def connect(path=DB_PATH):
 db=sqlite3.connect(path,timeout=10); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
 try:
  with db: yield db
 finally: db.close()
def initialize(path=DB_PATH):
 with connect(path) as db:
  db.execute('''CREATE TABLE IF NOT EXISTS bugs(id INTEGER PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,priority TEXT NOT NULL CHECK(priority IN ('low','medium','high','critical')),status TEXT NOT NULL CHECK(status IN ('new','triaged','in progress','resolved','closed')),assignee TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
  db.execute('''CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY,bug_id INTEGER NOT NULL REFERENCES bugs(id) ON DELETE CASCADE,author TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL)''')
  if db.execute('SELECT count(*) FROM bugs').fetchone()[0]==0:
   rows=[('Search results keep old filter','Changing a filter does not clear the previous result list.','medium','triaged','Demo QA'),('Export button needs a keyboard label','The export control is reachable by mouse but has no accessible name.','low','new','Unassigned'),('Example service returns intermittent 503','Fictional demo endpoint reported occasional service errors.','high','in progress','Demo Engineering')]
   db.executemany('INSERT INTO bugs(title,description,priority,status,assignee,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',[(a,b,c,d,e,stamp(),stamp()) for a,b,c,d,e in rows])
   db.execute('INSERT INTO comments(bug_id,author,body,created_at) VALUES(1,?,?,?)',('Demo QA','Reproduced with the sample filter set.',stamp()))
def required(data,key,limit):
 v=str(data.get(key,'')).strip()
 if not v or len(v)>limit:raise ValueError(f'{key.title()} is required (maximum {limit} characters).')
 return v
def create_bug(data,path=DB_PATH):
 title=required(data,'title',160); desc=required(data,'description',2000); priority=str(data.get('priority','medium')).lower(); assignee=str(data.get('assignee','Unassigned')).strip() or 'Unassigned'
 if priority not in PRIORITIES:raise ValueError('Priority must be low, medium, high, or critical.')
 if len(assignee)>100:raise ValueError('Assignee must be 100 characters or fewer.')
 with connect(path) as db:
  cur=db.execute('INSERT INTO bugs(title,description,priority,status,assignee,created_at,updated_at) VALUES(?,?,?,\'new\',?,?,?)',(title,desc,priority,assignee,stamp(),stamp())); bug_id=cur.lastrowid
 return bug_detail(bug_id,path)
def update_bug(bug_id,data,path=DB_PATH):
 allowed={}
 if 'status' in data:
  status=str(data['status']).lower()
  if status not in STATUSES:raise ValueError('Invalid bug status.')
  allowed['status']=status
 if 'priority' in data:
  priority=str(data['priority']).lower()
  if priority not in PRIORITIES:raise ValueError('Invalid priority.')
  allowed['priority']=priority
 if 'assignee' in data:
  assignee=str(data['assignee']).strip()
  if len(assignee)>100:raise ValueError('Assignee must be 100 characters or fewer.')
  allowed['assignee']=assignee or 'Unassigned'
 if not allowed:raise ValueError('Provide a status, priority, or assignee to update.')
 with connect(path) as db:
  if not db.execute('SELECT 1 FROM bugs WHERE id=?',(bug_id,)).fetchone():raise KeyError('Bug not found.')
  assignments=','.join(f'{key}=?' for key in allowed)
  db.execute(f'UPDATE bugs SET {assignments},updated_at=? WHERE id=?',(*allowed.values(),stamp(),bug_id))
 return bug_detail(bug_id,path)
def add_comment(bug_id,data,path=DB_PATH):
 author=str(data.get('author','')).strip() or 'Local user'; body=required(data,'body',2000)
 if len(author)>100:raise ValueError('Author must be 100 characters or fewer.')
 with connect(path) as db:
  if not db.execute('SELECT 1 FROM bugs WHERE id=?',(bug_id,)).fetchone():raise KeyError('Bug not found.')
  cur=db.execute('INSERT INTO comments(bug_id,author,body,created_at) VALUES(?,?,?,?)',(bug_id,author,body,stamp()))
  return dict(db.execute('SELECT * FROM comments WHERE id=?',(cur.lastrowid,)).fetchone())
def list_bugs(filters=None,path=DB_PATH):
 filters=filters or {}; where=[]; args=[]
 def scalar(value): return value[0] if isinstance(value,list) and value else value
 for field,allowed in [('status',STATUSES),('priority',PRIORITIES)]:
  value=str(scalar(filters.get(field,''))).lower()
  if value and value!='all':
   if value not in allowed:raise ValueError(f'Invalid {field} filter.')
   where.append(f'{field}=?');args.append(value)
 assignee=str(scalar(filters.get('assignee',''))).strip()
 if assignee:where.append('assignee LIKE ?');args.append('%'+assignee+'%')
 query=str(scalar(filters.get('q',''))).strip()
 if query:where.append('(title LIKE ? OR description LIKE ?)');args.extend(['%'+query+'%','%'+query+'%'])
 sql='SELECT * FROM bugs'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY CASE priority WHEN \'critical\' THEN 0 WHEN \'high\' THEN 1 WHEN \'medium\' THEN 2 ELSE 3 END,updated_at DESC'
 with connect(path) as db:return [dict(r) for r in db.execute(sql,args)]
def bug_detail(bug_id,path=DB_PATH):
 with connect(path) as db:
  bug=db.execute('SELECT * FROM bugs WHERE id=?',(bug_id,)).fetchone()
  if bug is None:raise KeyError('Bug not found.')
  result=dict(bug);result['comments']=[dict(r) for r in db.execute('SELECT * FROM comments WHERE bug_id=? ORDER BY id',(bug_id,))];return result
PAGE='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Issue Desk · Bug tracker</title><style>:root{font:15px/1.5 system-ui;color:#233044;background:#f4f6f9}*{box-sizing:border-box}body{margin:0}.hero{background:#172b42;color:white;padding:2.8rem max(5vw,22px)}.hero h1{font-size:clamp(2.3rem,5vw,3.5rem);margin:.1em 0}.hero p{color:#c4d0dd;max-width:700px}.wrap{max-width:1160px;margin:26px auto;padding:0 20px}.layout{display:grid;grid-template-columns:330px 1fr;gap:20px}.panel,.card{background:#fff;border:1px solid #e1e6ed;border-radius:15px;padding:20px;box-shadow:0 8px 26px #1d344b0a}.panel{height:max-content}label{font-weight:650;font-size:.88rem}input,textarea,select{width:100%;padding:10px;border:1px solid #ccd5df;border-radius:9px;font:inherit;margin:5px 0 12px}button{background:#26639b;color:white;border:0;border-radius:9px;padding:9px 13px;font:inherit;cursor:pointer}.secondary{background:#eaf1f7;color:#24557f}.filters{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.filters input,.filters select{margin:0}.card{margin-top:12px}.row{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.card h3{margin:.2em 0}.pill{padding:3px 9px;border-radius:30px;font-size:.78rem;background:#edf1f5;color:#415468}.critical,.high{background:#ffede9;color:#ad3a29}.medium{background:#fff5df;color:#8c6513}.low{background:#eaf4ec;color:#317149}.muted{color:#728092;font-size:.85rem}.actions{display:grid;grid-template-columns:repeat(3,minmax(90px,1fr));gap:6px;margin:10px 0}.comments{border-top:1px solid #edf0f3;margin-top:12px;padding-top:9px}.comment{font-size:.9rem;margin:6px 0;padding:7px;background:#f7f9fb;border-radius:8px}.commentform{display:grid;grid-template-columns:1fr 2fr auto;gap:6px}.commentform input{margin:0}.msg{color:#aa4534;min-height:1.2em}.empty{text-align:center;padding:28px;color:#758294}@media(max-width:780px){.layout{grid-template-columns:1fr}.filters{grid-template-columns:repeat(2,1fr)}.commentform{grid-template-columns:1fr}}</style></head><body><header class="hero"><div>ISSUE DESK · DELIVERY WORKFLOW</div><h1>Make bugs actionable.</h1><p>Capture reproducible issues, assign ownership, and move every fix through a visible lifecycle.</p></header><main class="wrap"><div class="layout"><section class="panel"><h2>File an issue</h2><form id="create"><label>Summary</label><input name="title" required maxlength="160" placeholder="One clear sentence"><label>Details</label><textarea name="description" rows="4" required maxlength="2000" placeholder="Steps, expected behavior, observed behavior"></textarea><label>Priority</label><select name="priority"><option>low</option><option selected>medium</option><option>high</option><option>critical</option></select><label>Assignee</label><input name="assignee" maxlength="100" placeholder="Unassigned"><button>File bug</button><p class="msg" id="msg"></p></form><p class="muted">Status flow: new → triaged → in progress → resolved → closed. Reopen by moving back to an active status.</p></section><section><div class="row"><div><h2 style="margin:.2em 0">Issue tracker</h2><span class="muted">Filter, prioritize, assign, discuss</span></div><button class="secondary" onclick="load()">Refresh</button></div><div class="filters"><input id="q" placeholder="Search issues…"><select id="fstatus"><option value="all">All statuses</option><option>new</option><option>triaged</option><option>in progress</option><option>resolved</option><option>closed</option></select><select id="fpriority"><option value="all">All priorities</option><option>critical</option><option>high</option><option>medium</option><option>low</option></select><input id="fassignee" placeholder="Assignee"></div><div id="bugs"></div></section></div></main><script>const box=document.querySelector('#bugs'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function load(){let q=new URLSearchParams({q:document.querySelector('#q').value,status:document.querySelector('#fstatus').value,priority:document.querySelector('#fpriority').value,assignee:document.querySelector('#fassignee').value}),r=await fetch('/api/bugs?'+q),rows=await r.json();box.innerHTML=rows.length?rows.map(b=>`<article class="card"><div class="row"><div><span class="pill ${b.priority}">${esc(b.priority.toUpperCase())}</span><span class="pill">${esc(b.status)}</span><h3>#${b.id} · ${esc(b.title)}</h3><p>${esc(b.description)}</p><div class="muted">Assigned: ${esc(b.assignee)} · Updated ${new Date(b.updated_at).toLocaleString()}</div></div></div><div class="actions"><select onchange="update(${b.id},'status',this.value)">${['new','triaged','in progress','resolved','closed'].map(s=>`<option ${s===b.status?'selected':''}>${s}</option>`).join('')}</select><select onchange="update(${b.id},'priority',this.value)">${['critical','high','medium','low'].map(s=>`<option ${s===b.priority?'selected':''}>${s}</option>`).join('')}</select><input aria-label="Assignee" value="${esc(b.assignee)}" onkeydown="if(event.key==='Enter')update(${b.id},'assignee',this.value)" onchange="update(${b.id},'assignee',this.value)" placeholder="Assignee"></div><div class="comments"><b>Comments (${b.comments.length})</b>${b.comments.map(c=>`<div class="comment"><strong>${esc(c.author)}</strong> · ${new Date(c.created_at).toLocaleString()}<br>${esc(c.body)}</div>`).join('')}<form class="commentform" onsubmit="comment(event,${b.id})"><input name="author" placeholder="Name (optional)" maxlength="100"><input name="body" placeholder="Add a useful update…" maxlength="2000" required><button>Comment</button></form></div></article>`).join(''):'<div class="empty">No issues match these filters. File a bug or broaden your search.</div>'}async function update(id,key,value){await fetch('/api/bugs/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value})});load()}async function comment(e,id){e.preventDefault();let r=await fetch('/api/bugs/'+id+'/comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(e.target)))}),d=await r.json();if(!r.ok)alert(d.error);load()}document.querySelector('#create').onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/bugs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(e.target)))}),d=await r.json();document.querySelector('#msg').textContent=r.ok?'Issue filed.':d.error;if(r.ok){e.target.reset();load()}};['q','fstatus','fpriority','fassignee'].forEach(id=>document.querySelector('#'+id).addEventListener('input',load));load();</script></body></html>'''
class Handler(BaseHTTPRequestHandler):
 def respond(self,code,data,ctype='application/json; charset=utf-8'):
  b=data.encode() if isinstance(data,str) else json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(b)
 def body(self):return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
 def do_GET(self):
  p=urlsplit(self.path)
  if p.path=='/':return self.respond(200,PAGE,'text/html; charset=utf-8')
  if p.path=='/api/bugs':
   try:return self.respond(200,list_bugs(parse_qs(p.query),DB_PATH))
   except ValueError as e:return self.respond(400,{'error':str(e)})
  parts=p.path.strip('/').split('/')
  if len(parts)==3 and parts[:2]==['api','bugs']:
   try:return self.respond(200,bug_detail(int(parts[2])))
   except (ValueError,KeyError) as e:return self.respond(404,{'error':str(e)})
  return self.respond(404,{'error':'Not found'})
 def do_POST(self):
  p=urlsplit(self.path).path
  try:
   if p=='/api/bugs':return self.respond(201,create_bug(self.body()))
   parts=p.strip('/').split('/')
   if len(parts)==4 and parts[:2]==['api','bugs'] and parts[3]=='comments':return self.respond(201,add_comment(int(parts[2]),self.body()))
   return self.respond(404,{'error':'Not found'})
  except (ValueError,KeyError,TypeError,json.JSONDecodeError,sqlite3.IntegrityError) as e:return self.respond(400,{'error':str(e)})
 def do_PATCH(self):
  parts=urlsplit(self.path).path.strip('/').split('/')
  if len(parts)!=3 or parts[:2]!=['api','bugs']:return self.respond(404,{'error':'Not found'})
  try:return self.respond(200,update_bug(int(parts[2]),self.body()))
  except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:return self.respond(400,{'error':str(e)})
 def log_message(self,*args):pass
def main():
 initialize();server=ThreadingHTTPServer(('127.0.0.1',8003),Handler);print('Issue Desk running at http://127.0.0.1:8003');server.serve_forever()
if __name__=='__main__':main()
