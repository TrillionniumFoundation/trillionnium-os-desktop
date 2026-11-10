#!/usr/bin/python3 -I
"""Read completed Core11 receipts and the exact empty owned calendar; no mutations or UI."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,types
from urllib.parse import urlencode,quote
ROOT=Path('/home/alex/work/pocket4-calendar-core11-readonly-20261105-r12-01')
CORE=Path('/home/alex/work/pocket4-calendar-accept-core-20261105-r12-11')
TOOLS=Path('/home/alex/work/pocket4-calendar-accept-core-tools-20261105-r12-11')
CORE_SHA='b47f30619fcfd96d19e3a620b8a1f3c1826903a565fcfe027f97da2566f6b146'
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
READER_SHA='1231e9c430a81b0af062c104b35516c3d2127e3e1cc43b78d15ffb2a5224f436'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,pin,name):
 raw=path.read_bytes();assert sha(raw)==pin
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def execute():
 assert os.geteuid()==0 and not os.path.lexists(ROOT)
 tx=load(TX,TX_SHA,'calendar_readonly_tx');assert tx.ACTIVATION_SHA=='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
 prior=json.loads(tx.read_regular(CORE/'result.json',CORE_SHA,32768))
 assert prior['state']=='FAILED' and prior['normally_closed_tasks']==[974] and prior['owned_tasks']=={} and prior['ui_pending']=={} and prior['business_pending'] is None
 assert prior['empty_calendar_cleanup_calls']==0 and not prior['empty_calendar_cleanup_pending']
 reader=load(TOOLS/'read_owned_calendar11.py',READER_SHA,'calendar_owned_reader11')
 selected={};paths=sorted((CORE/'commands').glob('*.result.json'));assert len(paths)<500
 for path in paths:
  raw=tx.read_regular(path,maximum=65536);record=json.loads(raw);args=record.get('argv',[])
  if '/system/bin/content' not in args:continue
  at=args.index('/system/bin/content');tail=args[at:]
  if len(tail)<2 or tail[1]!='query':continue
  if '--uri' not in tail or '--where' not in tail:continue
  uri=tail[tail.index('--uri')+1]
  if not uri.startswith('content://com.android.calendar/calendars?'):continue
  stem=Path(str(path)[:-len('.result.json')]);out=tx.read_regular(str(stem)+'.stdout',maximum=16384);err=tx.read_regular(str(stem)+'.stderr',maximum=16384)
  selected[path.name]={'record_sha256':sha(raw),'argv':tail,'rc':record['rc'],'joined':record['joined'],'timed_out':record['timed_out'],'guard_after':record.get('guard_after'),'stdout':out.decode(),'stderr':err.decode(),'stdout_sha256':sha(out),'stderr_sha256':sha(err)}
 assert len(selected)==1
 os.umask(0o077);ROOT.mkdir(mode=0o750);os.chown(ROOT,0,1000);os.chmod(ROOT,0o750)
 result={'schema':'calendar-core11-readonly-reconciliation-v1','state':'FAILED','prior_result_sha256':CORE_SHA,
  'source_sha256':sha(Path(__file__).read_bytes()),'original_cleanup_query':selected,
  'UI_inputs':0,'provider_mutations':0,'install_uninstall_calls':0,'original_failed_receipt_rewritten':False,
  'fixture_retained':True,'new_or_replayed_writes':0}
 with tx.ui_lock(),tx.CameraSession(ROOT/'journal') as s:
  result['guard_before']=s.guard();assert result['guard_before']==prior['guard_before']
  def tasks(label):
   raw=s.android(['/system/bin/am','stack','list'],15).decode();tx.write_new(ROOT/(label+'-stack.txt'),raw.encode())
   ids=[int(x) for x in re.findall(r'(?m)^\s*taskId=(\d+):',raw)]
   assert ids==[851] and 'com.android.calendar/' not in raw
   return {'ids':ids,'sha256':sha(raw.encode()),'Calendar_activity_present':False}
  result['tasks_before']=tasks('before')
  records=[];model=reader.Model(s,lambda label,value:records.append({'label':label,'value':value}))
  before=model.read('before');model.require_no_event(before);assert model.calendar==prior['owned_calendar']
  result['provider_before']=before
  uri,where=model.deletion_request()
  encoded='content://com.android.calendar/calendars?'+urlencode({'caller_is_syncadapter':'true','account_name':reader.ACCOUNT,'account_type':'LOCAL'},quote_via=quote)
  assert uri!=encoded and uri.replace('+','%20')==encoded
  result['exact_empty_predicate']=where
  for label,value in [('form_plus',uri),('percent20',encoded)]:
   output=s.android(['/system/bin/content','query','--user','0','--uri',value,'--projection','_id','--where',where],15).decode()
   result[label]={'uri':value,'stdout':output,'exact_one_owned_id':output=='Row: 0 _id='+str(model.calendar['_id'])+'\n'}
  after=model.read('after');model.require_no_event(after);assert after==before
  result['provider_after']=after;result['provider_unchanged']=True
  result['tasks_after']=tasks('after')
  s.caller_status('calendar-readonly-final');result['guard_after']=s.guard();assert result['guard_after']==result['guard_before']
 result['state']='READ_ONLY_RECEIPTS_TASKS_AND_EXACT_EMPTY_CALENDAR_COLLECTED'
 tx.write_new(ROOT/'result.json',result,alex_readable=True)
 raw=(ROOT/'result.json').read_bytes();compressed=gzip.compress(raw,mtime=0);tx.write_new(ROOT/'result.json.gz',compressed,alex_readable=True)
 print(json.dumps({'state':result['state'],'path':str(ROOT/'result.json'),'bytes':len(raw),'sha256':sha(raw),'gzip_bytes':len(compressed),'gzip_sha256':sha(compressed),'UI_inputs':0,'provider_mutations':0}))
 return 0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
 if not a.execute:print('INERT: retained and live read-only evidence only');raise SystemExit(0)
 raise SystemExit(execute())
