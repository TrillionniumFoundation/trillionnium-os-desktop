#!/usr/bin/python3 -I
"""Delete only Core11's exact empty LOCAL calendar, using its proven percent-encoded URI."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,signal,types
from urllib.parse import urlencode,quote
ROOT=Path('/home/alex/work/pocket4-calendar-core11-empty-cleanup-20261105-r12-01')
CORE=Path('/home/alex/work/pocket4-calendar-accept-core-20261105-r12-11/result.json')
CORE_SHA='b47f30619fcfd96d19e3a620b8a1f3c1826903a565fcfe027f97da2566f6b146'
READ=Path('/home/alex/work/pocket4-calendar-core11-readonly-20261105-r12-01/result.json')
READ_SHA='91e3be348d02511bca703096e8081a829c35e1636a57db885f1d3cbe58f74cc7'
TOOLS=Path('/home/alex/work/pocket4-calendar-accept-core-tools-20261105-r12-11')
INSTALLER=Path('/home/alex/work/pocket4-calendar-repair-install-tools-20261105-r12-10/calendar_install10.py')
INSTALLER_SHA='731f73cf981a07cc4b9794f8bcb7370b2ebb569247538a0849ed1128ae5df6d3'
INSTALL=Path('/home/alex/work/pocket4-calendar-repair-install-20261105-r12-10/result.json')
INSTALL_SHA='253c98a9d27f1b5bb45e01cdda6042e0d43b2f268b3c0a228bf93a639b38f957'
READER_SHA='1231e9c430a81b0af062c104b35516c3d2127e3e1cc43b78d15ffb2a5224f436'
PROBE=Path('/home/alex/work/pocket4-calendar-shell-query-tools-20261105-r12-02/probe_shell_cleanup02.py')
PROBE_SHA='3696994fe45fba3152418e32667ac3ac6ed437cf5191189bfe65a27f21bccb88'
ATOMIC_SHA='1d66de839c05c11983196764d44c518175bc10481cff754b850d6034c8533796'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(value,reason):
 if not value:raise RuntimeError(reason)
def load(path,pin,name):
 raw=path.read_bytes();need(sha(raw)==pin,'INPUT_CHANGED:'+path.name)
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def execute():
 need(os.geteuid()==0 and not os.path.lexists(ROOT),'CREATE_ONLY_ROOT_REQUIRED')
 install=load(INSTALLER,INSTALLER_SHA,'calendar_cleanup_installer_identity')
 m=load(install.FLOW,install.FLOW_SHA,'calendar_cleanup_original_definitions')
 tx=load(m.TX,m.PINS[str(m.TX)],'calendar_cleanup_tx')
 need(m.PINS[str(m.TX)]=='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470' and
      tx.ACTIVATION_SHA=='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615','EXACT_ORIGINAL_PROFILE')
 doc=load(m.DOC,m.PINS[str(m.DOC)],'calendar_cleanup_doc_identity')
 reader=load(TOOLS/'read_owned_calendar11.py',READER_SHA,'calendar_cleanup_reader')
 probe=load(PROBE,PROBE_SHA,'calendar_cleanup_shell_grants')
 prior=json.loads(tx.read_regular(CORE,CORE_SHA,32768));proof=json.loads(tx.read_regular(READ,READ_SHA,16384))
 installed=json.loads(tx.read_regular(INSTALL,INSTALL_SHA,32768))
 atomic=json.loads(tx.read_regular(TOOLS/'atomic-delete-review.json',ATOMIC_SHA,16384))
 need(atomic['provider_apk_sha256']==install.PROVIDER_SHA,'EXACT_ATOMIC_PROVIDER_SOURCE_REQUIRED')
 need(prior['state']=='FAILED' and prior['owned_tasks']=={} and prior['ui_pending']=={} and prior['business_pending'] is None
      and prior['normally_closed_tasks']==[974] and prior['empty_calendar_cleanup_calls']==0 and
      not prior['empty_calendar_cleanup_pending'],'ORIGINAL_FAILED_CORE_SCOPE')
 need(proof['state']=='READ_ONLY_RECEIPTS_TASKS_AND_EXACT_EMPTY_CALENDAR_COLLECTED' and proof['provider_unchanged'] and
      proof['percent20']['exact_one_owned_id'] and not proof['form_plus']['exact_one_owned_id'] and
      proof['provider_after']['calendars']==[prior['owned_calendar']] and
      proof['guard_before']==proof['guard_after']==prior['guard_before'],'ACTUAL_ENCODING_AND_ROW_PROOF_REQUIRED')
 need(installed['state']=='INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED' and not installed['install_pending'] and
      installed['after']['apk_sha256']==install.NEW_SHA,'EXACT_INSTALLED10_REQUIRED')
 result={'schema':'calendar-core11-exact-empty-cleanup-v1','state':'FAILED','started_utc':m.stamp(),
  'source_sha256':sha(Path(__file__).read_bytes()),'prior_failed_core_sha256':CORE_SHA,'readonly_proof_sha256':READ_SHA,
  'atomic_provider_review_sha256':ATOMIC_SHA,'transport_sha256':m.PINS[str(m.TX)],'activation_sha256':tx.ACTIVATION_SHA,
  'delete_calls':0,'delete_pending':False,'UI_inputs':0,'task_remove_calls':0,'new_launches':0,
  'package_mutations':0,'permission_changes':0,'event_writes':0,'automatic_retry':False,
  'original_failed_receipt_rewritten':False,'whole_app_production_ready':False,
  'provider_internal_path':'Normal deletion may attempt unsubscribe/scheduleSync only for this same unregistered LOCAL account; no external account or sync API is invoked by this controller.'}
 old=signal.signal(signal.SIGALRM,m.expired)
 try:
  with tx.ui_lock():
   os.umask(0o077);ROOT.mkdir(mode=0o750);os.chown(ROOT,0,1000);os.chmod(ROOT,0o750);signal.setitimer(signal.ITIMER_REAL,120)
   with tx.CameraSession(ROOT/'journal') as s:
    result['guard_before']=s.guard();need(result['guard_before']==proof['guard_after'],'SAME_MAIN_REQUIRED')
    def tasks(label):
     raw=s.android(['/system/bin/am','stack','list'],15).decode();tx.write_new(ROOT/(label+'-stack.txt'),raw.encode())
     ids=[int(x) for x in re.findall(r'(?m)^\s*taskId=(\d+):',raw)]
     need(ids==[851] and 'com.android.calendar/' not in raw,'COORDINATED_WINDOW_AND_NO_CALENDAR_ACTIVITY_REQUIRED')
     return ids
    def grants():
     rows=probe.shared_shell_permission_rows(s.android(['/system/bin/dumpsys','package','com.android.shell'],15).decode())
     selected=[row for row in rows if any(row.startswith(name+':') for name in m.GRANTS)]
     need(all(m.permission_granted(rows,name) for name in m.GRANTS),'EXISTING_SHELL_GRANTS_REQUIRED')
     need(selected==prior['existing_shell_calendar_permissions'],'SHELL_GRANTS_CHANGED')
     return selected
    result['tasks_before']=tasks('before');result['shell_grants_before']=grants()
    result['calendar_before']=install.identity(s,m,doc);need(result['calendar_before']==installed['after'],'CALENDAR10_IDENTITY_CHANGED')
    result['provider_before']=doc.identity(s,install.PROVIDER,install.PROVIDER_SHA,10017,37)
    need(result['provider_before']==prior['provider_after'],'PROVIDER_IDENTITY_CHANGED')
    model=reader.Model(s,lambda label,value:tx.write_new(ROOT/(label+'.json'),value))
    before=model.read('before');model.require_no_event(before)
    need(model.calendar==prior['owned_calendar'] and before==proof['provider_after'],'EXACT_OWNED_EMPTY_CALENDAR_REQUIRED')
    result['counts_before']=before['counts'];result['owned_calendar']=dict(model.calendar)
    old_uri,where=model.deletion_request()
    uri='content://com.android.calendar/calendars?'+urlencode({'caller_is_syncadapter':'true','account_name':reader.ACCOUNT,'account_type':'LOCAL'},quote_via=quote)
    need(old_uri==proof['form_plus']['uri'] and uri==proof['percent20']['uri'] and where==proof['exact_empty_predicate'],
         'ONLY_PROVEN_URI_ENCODING_CHANGE_ALLOWED')
    query=s.android(['/system/bin/content','query','--user','0','--uri',uri,'--projection','_id','--where',where],15).decode()
    result['fresh_guarded_query_stdout']=query
    need(query=='Row: 0 _id='+str(model.calendar['_id'])+'\n','FRESH_EXACT_OWNED_QUERY_REQUIRED')
    need(model.read('just-before')==before,'OWNED_PROVIDER_STATE_CHANGED_BEFORE_DELETE');tasks('just-before')
    tx.write_new(ROOT/'before.json',result)
    result['delete_pending']=True;result['delete_calls']=1
    argv=['/system/bin/content','delete','--user','0','--uri',uri,'--where',where]
    tx.write_new(ROOT/'delete-intent.json',{'argv':argv,'expected_owned_calendar':model.calendar,'expected_events':0,'automatic_retry':False})
    response=s.android(argv,20).decode();result['delete_stdout']=response
    tx.write_new(ROOT/'delete-ack.json',{'stdout':response,'count_not_inferred_from_stdout':True})
    after=model.read('after');model.require_empty(after)
    result['counts_after']=after['counts'];result['delete_outcome_verified_by_physical_empty_read']=True;result['delete_pending']=False
    result['calendar_after']=install.identity(s,m,doc);need(result['calendar_after']==result['calendar_before'],'CALENDAR_IDENTITY_CHANGED_AFTER')
    result['provider_after']=doc.identity(s,install.PROVIDER,install.PROVIDER_SHA,10017,37)
    need(result['provider_after']==result['provider_before'],'PROVIDER_IDENTITY_CHANGED_AFTER')
    result['shell_grants_after']=grants();result['tasks_after']=tasks('after')
    s.caller_status('calendar-cleanup-final');result['guard_after']=s.guard()
    need(result['guard_after']==result['guard_before'],'MAIN_CHANGED_AFTER')
    result['state']='EXACT_CORE11_EMPTY_CALENDAR_REMOVED_BASELINE_RESTORED'
 except BaseException as exc:result['error']=type(exc).__name__+':'+str(exc);result['state']='DELETE_OUTCOME_UNKNOWN' if result['delete_pending'] else 'FAILED'
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old);result['finished_utc']=m.stamp()
  if ROOT.is_dir():
   tx.write_new(ROOT/'result.json',result,alex_readable=True)
   tx.write_new(ROOT/'result.json.gz',gzip.compress((ROOT/'result.json').read_bytes(),mtime=0),alex_readable=True)
 print(json.dumps({k:result.get(k) for k in ('state','delete_calls','delete_pending','counts_after','tasks_after','error')}))
 return 0 if result['state']=='EXACT_CORE11_EMPTY_CALENDAR_REMOVED_BASELINE_RESTORED' else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
 if not a.execute:print('INERT: exact one owned empty calendar only; requires coordinated UI lock');raise SystemExit(0)
 raise SystemExit(execute())
