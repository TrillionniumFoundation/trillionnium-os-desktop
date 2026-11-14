import pathlib,json,hashlib,subprocess,datetime,re,os,ast
R=pathlib.Path('/data/pocket4-audio-source316-offload-20261108-8b88-r1')
C=R/'control/full-desktop-r13';Q=R/'qualification/full-desktop-r13'
out={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'single read-only Audio13 controller/unit/input observation'}
def ident(p,b):return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
for name in ('READY.json','build-inputs.json','start-full.json','desktop_audio_controller.py'):
 p=C/name
 try:
  b=p.read_bytes();x=ident(p,b)
  if name=='READY.json':x['value']=json.loads(b)
  elif name.endswith('.json'):
   j=json.loads(b);x['top_keys']=list(j);selected=[]
   def walk(v,path=''):
    if isinstance(v,dict):
     for k,w in v.items():
      at=path+'.'+k
      if isinstance(w,(str,int,bool)) and (re.search(r'commit|recipe|lock|droidloom|source_root|manifest|allow_missing|timeout|full_build',k,re.I) or isinstance(w,str) and re.search(r'b555|22ae84|SDK33|sdk33|zygote|droidloom-(?:update|source)|upstream-audio',w)):
       selected.append({'key':at,'value':w if not isinstance(w,str) or len(w)<1600 else w[:1600]+'...[bounded]'})
      elif isinstance(w,(dict,list)):walk(w,at)
    elif isinstance(v,list):
     for i,w in enumerate(v):walk(w,path+'['+str(i)+']')
   walk(j);x['selected']=selected[:95];x['selected_total']=len(selected)
  else:
   ls=b.decode().splitlines();wanted=set()
   for i,s in enumerate(ls):
    if len(s)<1000 and re.search(r'^CONFIG|^ROOT|^BASE|^QUAL|^Q\s*=|^UNIT|^RECIPE|^SOURCE|build-inputs|droidloom-update|normal-full|full-build|log_path|\.log|ALLOW_MISSING|allow_missing',s):wanted.update(range(max(0,i-2),min(len(ls),i+4)))
   x['selected_lines']=[{'line':i+1,'text':ls[i]} for i in sorted(wanted) if len(ls[i])<1600]
  out[name]=x
 except Exception as e:out[name]={'path':str(p),'error':str(e)}
unit='p4-audio-source430-original-sdk33-zygote-full-desktop-20261109-8b88-r13.service'
r=subprocess.run(['/usr/bin/systemctl','show',unit,'--no-pager','--property=LoadState,ActiveState,SubState,MainPID,ExecMainPID,InvocationID,ControlGroup,MemoryCurrent,MemoryPeak,MemoryMax,MemoryHigh,MemorySwapMax,TasksCurrent,Result,ExecMainStatus,CPUUsageNSec'],capture_output=True,text=True,timeout=15)
out['actual_unit']={'unit':unit,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
kv=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line);cg=kv.get('ControlGroup','')
if cg.startswith('/system.slice/') and unit in cg:
 d=pathlib.Path('/sys/fs/cgroup'+cg);out['cgroup']={'path':str(d),'exists':d.is_dir(),'values':{}}
 for name in ('cgroup.events','memory.events','memory.current','memory.peak','memory.max','memory.high','memory.swap.max','pids.current'):
  p=d/name
  try:out['cgroup']['values'][name]=p.read_text().strip()
  except Exception as e:out['cgroup']['values'][name]={'error':str(e)}
out['qualification_directory']={'path':str(Q),'exists':Q.exists()}
if Q.is_dir():
 entries=[]
 for p in sorted(Q.iterdir()):
  st=p.lstat();entries.append({'name':p.name,'bytes':st.st_size,'regular_file':p.is_file(),'mtime_ns':st.st_mtime_ns})
 out['qualification_directory']['entries']=entries
 logs=[p for p in Q.iterdir() if p.is_file() and p.suffix=='.log']
 logs=sorted(logs,key=lambda p:p.stat().st_size,reverse=True)[:2]
 for p in logs:
  with p.open('rb') as f:f.seek(max(0,p.stat().st_size-8192));b=f.read(8192)
  out.setdefault('bounded_log_tails',[]).append({'path':str(p),'file_bytes':p.stat().st_size,'tail_bytes':len(b),'tail_sha256':hashlib.sha256(b).hexdigest(),'text':b.decode('utf-8','replace')})
print(json.dumps(out,ensure_ascii=False))
