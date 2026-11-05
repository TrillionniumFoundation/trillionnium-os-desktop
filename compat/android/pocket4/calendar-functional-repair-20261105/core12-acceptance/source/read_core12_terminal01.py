#!/usr/bin/python3 -I
"""Fresh bounded read-only reconciliation of retained Core12 fixture and closed task."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,types
ROOT=Path('/home/alex/work/pocket4-calendar-core12-readonly-20261105-r12-01')
CORE=Path('/home/alex/work/pocket4-calendar-accept-core-20261105-r12-12')
TOOLS=Path('/home/alex/work/pocket4-calendar-accept-core-tools-20261105-r12-12')
CORE_SHA='89e5ba58f72707cc3235a8d5054ee83b4b613b09115989f9327f9ad591fff575'
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
READER_SHA='5cae87cf11dab38ad838ee97b43d652fd9f772348030e3cacec138f3fe5fef4e'
ORIGINAL=Path('/home/alex/work/pocket4-calendar-flow-tools-20261105-r12-01/run_calendar01.py')
ORIGINAL_SHA='d307f4ceda9fc80e216f280cb1a9558fbe4e27b43cd659ecc83a1c6edab9c8fa'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,pin,name):
 raw=path.read_bytes();assert sha(raw)==pin
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def execute():
 assert os.geteuid()==0 and not os.path.lexists(ROOT)
 tx=load(TX,TX_SHA,'calendar_core12_readonly_tx');assert tx.ACTIVATION_SHA=='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
 prior=json.loads(tx.read_regular(CORE/'result.json',CORE_SHA,32768))
 assert prior['state']=='FAILED' and prior['error']=='LeaseExpired:CALENDAR_LEASE_EXPIRED_NO_REPLAY'
 assert prior['normally_closed_tasks']==[979] and prior['owned_tasks']=={} and prior['ui_pending']=={} and prior['business_pending'] is None
 assert prior['empty_calendar_cleanup_calls']==0 and not prior['empty_calendar_cleanup_pending']
 assert prior['role_calls'].get('save-edit',0)==0 and prior['owned_event_id']==1
 reader=load(TOOLS/'read_owned_calendar12.py',READER_SHA,'calendar_owned_reader12')
 m=load(ORIGINAL,ORIGINAL_SHA,'calendar_original_definitions')
 doc=load(m.DOC,m.PINS[str(m.DOC)],'calendar_identity_definitions')
 os.umask(0o077);ROOT.mkdir(mode=0o750);os.chown(ROOT,0,1000);os.chmod(ROOT,0o750)
 result={'schema':'calendar-core12-readonly-reconciliation-v1','state':'FAILED','prior_result_sha256':CORE_SHA,
  'source_sha256':sha(Path(__file__).read_bytes()),'ui_inputs':0,'provider_mutations':0,'install_uninstall_calls':0,
  'original_failed_receipt_rewritten':False,'fixture_retained':True,'new_or_replayed_writes':0}
 try:
  with tx.ui_lock(),tx.CameraSession(ROOT/'journal') as s:
   result['guard_before']=s.guard();assert result['guard_before']==prior['guard_before']
   def tasks(label):
    raw=s.android(['/system/bin/am','stack','list'],15).decode();tx.write_new(ROOT/(label+'-stack.txt'),raw.encode())
    ids=[int(x) for x in re.findall(r'(?m)^\s*taskId=(\d+):',raw)]
    assert ids==[851] and 'com.android.calendar/' not in raw
    return {'ids':ids,'sha256':sha(raw.encode()),'Calendar_activity_present':False}
   def identities():
    calendar=doc.identity(s,'com.android.calendar',prior['candidate_apk_sha256'],10061,37)
    calendar['permissions']=m.permission_rows(s.android(['/system/bin/dumpsys','package','com.android.calendar'],12).decode(),'com.android.calendar')
    provider=doc.identity(s,'com.android.providers.calendar',prior['provider_before']['apk_sha256'],10017,37)
    assert calendar==prior['calendar_after'] and provider==prior['provider_after']
    return {'calendar':calendar,'provider':provider}
   result['tasks_before']=tasks('before');result['identities_before']=identities()
   records=[];model=reader.Model(s,lambda label,value:records.append({'label':label,'value':value}))
   before=model.read('before');model.require_event(before,reader.TITLE,prior['intended_event']['begin_utc_ms'],prior['intended_event']['end_utc_ms'])
   assert model.calendar==prior['owned_calendar'] and model.event_id==prior['owned_event_id']
   assert before==prior['gates']['created_in_calendar_ui'] and before['counts']==prior['final_counts']
   result['provider_before']=before
   files=sorted((CORE/'ui').glob('*'));assert len(files)<1000
   result['original_ui_journal_file_names']=[p.name for p in files]
   assert not any('save-edited-fresh03' in p.name for p in files)
   result['late_write_request_has_no_original_journal_entry']=True
   after=model.read('after');assert after==before;model.require_event(after,reader.TITLE,prior['intended_event']['begin_utc_ms'],prior['intended_event']['end_utc_ms'])
   result['provider_after']=after;result['provider_unchanged']=True
   result['identities_after']=identities();assert result['identities_after']==result['identities_before']
   result['tasks_after']=tasks('after')
   tx.write_new(ROOT/'owned-reads.json',records)
   s.caller_status('calendar-core12-readonly-final');result['guard_after']=s.guard();assert result['guard_after']==result['guard_before']
  result['state']='CORE12_TERMINAL_TASK_CLOSED_EXACT_UNEDITED_EVENT_RETAINED'
 except BaseException as exc:result['state']='FAILED';result['error']=type(exc).__name__+':'+str(exc)
 tx.write_new(ROOT/'result.json',result,alex_readable=True)
 raw=(ROOT/'result.json').read_bytes();compressed=gzip.compress(raw,mtime=0);tx.write_new(ROOT/'result.json.gz',compressed,alex_readable=True)
 print(json.dumps({'state':result['state'],'path':str(ROOT/'result.json'),'bytes':len(raw),'sha256':sha(raw),'gzip_bytes':len(compressed),'gzip_sha256':sha(compressed),'ui_inputs':0,'provider_mutations':0}))
 return 0 if result['state']=='CORE12_TERMINAL_TASK_CLOSED_EXACT_UNEDITED_EVENT_RETAINED' else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
 if not a.execute:print('INERT: completed Core12 and fresh owned event reads only');raise SystemExit(0)
 raise SystemExit(execute())
