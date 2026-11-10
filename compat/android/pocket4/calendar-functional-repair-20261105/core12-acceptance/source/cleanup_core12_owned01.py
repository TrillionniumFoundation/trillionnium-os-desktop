#!/usr/bin/python3 -I
"""One normal Provider delete of Core12's exact event, then its empty LOCAL calendar."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,signal,types
from urllib.parse import urlencode,quote
ROOT=Path('/home/alex/work/pocket4-calendar-core12-cleanup-20261105-r12-01')
CORE=Path('/home/alex/work/pocket4-calendar-accept-core-20261105-r12-12/result.json')
CORE_SHA='89e5ba58f72707cc3235a8d5054ee83b4b613b09115989f9327f9ad591fff575'
READ=Path('/home/alex/work/pocket4-calendar-core12-readonly-20261105-r12-01/result.json')
READ_SHA='7d976aa401bf91481725d18e4a125ad1c1a18b4c201a3b6cd91fe75f0207ad8c'
TOOLS=Path('/home/alex/work/pocket4-calendar-accept-core-tools-20261105-r12-12')
INSTALL=Path('/home/alex/work/pocket4-calendar-repair-install-20261105-r12-11/result.json')
INSTALL_SHA='0ca5846a91a737ff795ce7f856b3916e3903bb2f6498f5f5ad25e1a893fb420a'
READER_SHA='5cae87cf11dab38ad838ee97b43d652fd9f772348030e3cacec138f3fe5fef4e'
ORIGINAL=Path('/home/alex/work/pocket4-calendar-flow-tools-20261105-r12-01/run_calendar01.py')
ORIGINAL_SHA='d307f4ceda9fc80e216f280cb1a9558fbe4e27b43cd659ecc83a1c6edab9c8fa'
PROBE=Path('/home/alex/work/pocket4-calendar-shell-query-tools-20261105-r12-02/probe_shell_cleanup02.py')
PROBE_SHA='3696994fe45fba3152418e32667ac3ac6ed437cf5191189bfe65a27f21bccb88'
ATOMIC_SHA='1d66de839c05c11983196764d44c518175bc10481cff754b850d6034c8533796'
EVENT_ATOMIC_SHA='b7425ae6b3d49a699b4d7d4ada792da1399a8c4c3183d5830c1fbbedf9ee10c3'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(value,reason):
 if not value:raise RuntimeError(reason)
def load(path,pin,name):
 raw=path.read_bytes();need(sha(raw)==pin,'INPUT_CHANGED:'+path.name)
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def exact_event_predicate(reader,calendar,event):
 need(set(event)==set(reader.EVENT_COLUMNS),'EXACT_EVENT_PROJECTION_REQUIRED')
 fields=reader.CALENDAR_COLUMNS
 owner=' AND '.join(k+'='+reader.quote(calendar[k]) for k in fields)
 terms=[k+' IS NULL' if event[k] is None else k+'='+reader.quote(event[k]) for k in reader.EVENT_COLUMNS]
 terms.append('calendar_id IN (SELECT _id FROM Calendars WHERE '+owner+')')
 for table in ('Reminders','Attendees','CalendarAlerts','ExtendedProperties'):
  terms.append('NOT EXISTS (SELECT 1 FROM '+table+' WHERE event_id='+str(event['_id'])+')')
 terms.append('NOT EXISTS (SELECT 1 FROM Events AS exceptions WHERE exceptions.original_id='+str(event['_id'])+')')
 return ' AND '.join('('+term+')' for term in terms)
def execute():
 need(os.geteuid()==0 and not os.path.lexists(ROOT),'CREATE_ONLY_ROOT_REQUIRED')
 m=load(ORIGINAL,ORIGINAL_SHA,'calendar_cleanup_original_definitions')
 tx=load(m.TX,m.PINS[str(m.TX)],'calendar_cleanup_tx')
 need(m.PINS[str(m.TX)]=='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470' and
      tx.ACTIVATION_SHA=='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615','EXACT_ORIGINAL_PROFILE')
 doc=load(m.DOC,m.PINS[str(m.DOC)],'calendar_cleanup_doc_identity')
 reader=load(TOOLS/'read_owned_calendar12.py',READER_SHA,'calendar_cleanup_reader')
 probe=load(PROBE,PROBE_SHA,'calendar_cleanup_shell_grants')
 prior=json.loads(tx.read_regular(CORE,CORE_SHA,32768));proof=json.loads(tx.read_regular(READ,READ_SHA,32768))
 installed=json.loads(tx.read_regular(INSTALL,INSTALL_SHA,32768))
 atomic=json.loads(tx.read_regular(TOOLS/'atomic-delete-review.json',ATOMIC_SHA,16384))
 event_atomic=json.loads(tx.read_regular(Path(__file__).parent/'event-delete-review.json',EVENT_ATOMIC_SHA,32768))
 provider_sha=prior['provider_before']['apk_sha256'];new_sha=prior['candidate_apk_sha256']
 need(atomic['provider_apk_sha256']==provider_sha and event_atomic['apk_sha256']==provider_sha,'EXACT_ATOMIC_PROVIDER_SOURCE_REQUIRED')
 need(prior['state']=='FAILED' and prior['owned_tasks']=={} and prior['ui_pending']=={} and prior['business_pending'] is None
      and prior['normally_closed_tasks']==[979] and prior['empty_calendar_cleanup_calls']==0 and
      not prior['empty_calendar_cleanup_pending'] and prior['role_calls'].get('save-edit',0)==0,'ORIGINAL_FAILED_CORE_SCOPE')
 need(proof['state']=='CORE12_TERMINAL_TASK_CLOSED_EXACT_UNEDITED_EVENT_RETAINED' and proof['provider_unchanged'] and
      proof['late_write_request_has_no_original_journal_entry'] and proof['tasks_after']['ids']==[851] and
      proof['provider_after']==prior['gates']['created_in_calendar_ui'] and
      proof['guard_before']==proof['guard_after']==prior['guard_before'],'ACTUAL_TERMINAL_AND_EXACT_FIXTURE_PROOF_REQUIRED')
 need(installed['state']=='INSTALLED_VERIFIED_NOT_BUSINESS_QUALIFIED' and not installed['install_pending'] and
      installed['after']['apk_sha256']==new_sha,'EXACT_INSTALLED11_REQUIRED')
 result={'schema':'calendar-core12-exact-owned-cleanup-v1','state':'FAILED','started_utc':m.stamp(),
  'source_sha256':sha(Path(__file__).read_bytes()),'prior_failed_core_sha256':CORE_SHA,'readonly_proof_sha256':READ_SHA,
  'atomic_calendar_review_sha256':ATOMIC_SHA,'atomic_event_review_sha256':EVENT_ATOMIC_SHA,
  'transport_sha256':m.PINS[str(m.TX)],'activation_sha256':tx.ACTIVATION_SHA,
  'event_delete_calls':0,'event_delete_pending':False,'calendar_delete_calls':0,'calendar_delete_pending':False,
  'ui_inputs':0,'task_remove_calls':0,'new_launches':0,'package_mutations':0,'permission_changes':0,
  'automatic_retry':False,'original_failed_receipt_rewritten':False,'whole_app_production_ready':False,
  'counts_as_ui_event_delete':False,'provider_internal_path':'Normal Provider deletion may update its next-alarm bookkeeping and attempt unsubscribe/scheduleSync only for this same unregistered LOCAL account. No external account or sync API is invoked by this controller.'}
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
    def identities():
     calendar=doc.identity(s,'com.android.calendar',new_sha,10061,37)
     calendar['permissions']=m.permission_rows(s.android(['/system/bin/dumpsys','package','com.android.calendar'],12).decode(),'com.android.calendar')
     provider=doc.identity(s,'com.android.providers.calendar',provider_sha,10017,37)
     need(calendar==prior['calendar_after'] and provider==prior['provider_after'],'CALENDAR_OR_PROVIDER_IDENTITY_CHANGED')
     return {'calendar':calendar,'provider':provider}
    def grants():
     raw=s.android(['/system/bin/pm','list','packages','-U','--user','0','com.android.shell'],12).decode()
     need([line for line in raw.splitlines() if line.startswith('package:com.android.shell ')]==['package:com.android.shell uid:2000'],'SHELL_UID_REQUIRED')
     rows=probe.shared_shell_permission_rows(s.android(['/system/bin/dumpsys','package','com.android.shell'],15).decode())
     selected=[row for row in rows if any(row.startswith(name+':') for name in m.GRANTS)]
     need(all(m.permission_granted(rows,name) for name in m.GRANTS) and selected==prior['existing_shell_calendar_permissions'],'EXISTING_SHELL_GRANTS_REQUIRED')
     return selected
    result['tasks_before']=tasks('before');result['shell_grants_before']=grants();result['identities_before']=identities()
    model=reader.Model(s,lambda label,value:tx.write_new(ROOT/(label+'.json'),value))
    before=model.read('before');event=model.require_event(before,reader.TITLE,prior['intended_event']['begin_utc_ms'],prior['intended_event']['end_utc_ms'])
    need(model.calendar==prior['owned_calendar'] and model.event_id==prior['owned_event_id'] and before==proof['provider_after'],'EXACT_OWNED_FIXTURE_REQUIRED')
    result['counts_before']=before['counts'];result['owned_calendar']=dict(model.calendar);result['owned_event']=dict(event)
    query_string=urlencode({'caller_is_syncadapter':'true','account_name':reader.ACCOUNT,'account_type':'LOCAL'},quote_via=quote)
    event_uri='content://com.android.calendar/events?'+query_string
    event_where=exact_event_predicate(reader,model.calendar,event)
    def exact_query(uri,where,rowid,label):
     output=s.android(['/system/bin/content','query','--user','0','--uri',uri,'--projection','_id','--where',where],15).decode()
     result[label]=output;need(output=='Row: 0 _id='+str(rowid)+'\n','FRESH_EXACT_QUERY_REQUIRED:'+label)
    exact_query(event_uri,event_where,event['_id'],'event_guarded_query')
    need(model.read('just-before-event-delete')==before,'OWNED_PROVIDER_CHANGED_BEFORE_DELETE');tasks('just-before-event-delete')
    tx.write_new(ROOT/'before.json',result)
    result['event_delete_pending']=True;result['event_delete_calls']=1
    argv=['/system/bin/content','delete','--user','0','--uri',event_uri,'--where',event_where]
    tx.write_new(ROOT/'event-delete-intent.json',{'argv':argv,'expected_event':event,'expected_calendar':model.calendar,'automatic_retry':False})
    response=s.android(argv,20).decode();result['event_delete_stdout']=response
    tx.write_new(ROOT/'event-delete-ack.json',{'stdout':response,'count_not_inferred_from_stdout':True})
    after_event=model.read('after-event-delete');model.require_no_event(after_event)
    result['counts_after_event_delete']=after_event['counts'];result['event_delete_pending']=False
    result['event_delete_verified']=True
    uri,where=model.deletion_request();need(uri=='content://com.android.calendar/calendars?'+query_string,'SAME_EXACT_PERCENT_ENCODED_OWNER_REQUIRED')
    exact_query(uri,where,model.calendar['_id'],'calendar_guarded_query')
    need(model.read('just-before-calendar-delete')==after_event,'EMPTY_CALENDAR_CHANGED_BEFORE_DELETE');tasks('just-before-calendar-delete')
    result['calendar_delete_pending']=True;result['calendar_delete_calls']=1
    argv=['/system/bin/content','delete','--user','0','--uri',uri,'--where',where]
    tx.write_new(ROOT/'calendar-delete-intent.json',{'argv':argv,'expected_calendar':model.calendar,'expected_events':0,'automatic_retry':False})
    response=s.android(argv,20).decode();result['calendar_delete_stdout']=response
    tx.write_new(ROOT/'calendar-delete-ack.json',{'stdout':response,'count_not_inferred_from_stdout':True})
    after=model.read('after-calendar-delete');model.require_empty(after)
    result['counts_after']=after['counts'];result['calendar_delete_pending']=False;result['calendar_delete_verified']=True
    result['identities_after']=identities();need(result['identities_after']==result['identities_before'],'IDENTITY_CHANGED_AFTER')
    result['shell_grants_after']=grants();result['tasks_after']=tasks('after')
    s.caller_status('calendar-core12-cleanup-final');result['guard_after']=s.guard();need(result['guard_after']==result['guard_before'],'MAIN_CHANGED_AFTER')
   result['state']='EXACT_CORE12_EVENT_AND_EMPTY_CALENDAR_REMOVED_BASELINE_RESTORED'
 except BaseException as exc:
  result['error']=type(exc).__name__+':'+str(exc)
  result['state']='DELETE_OUTCOME_UNKNOWN' if result['event_delete_pending'] or result['calendar_delete_pending'] else 'FAILED'
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old);result['finished_utc']=m.stamp()
  if ROOT.is_dir():
   tx.write_new(ROOT/'result.json',result,alex_readable=True)
   tx.write_new(ROOT/'result.json.gz',gzip.compress((ROOT/'result.json').read_bytes(),mtime=0),alex_readable=True)
 print(json.dumps({k:result.get(k) for k in ('state','event_delete_calls','event_delete_pending','calendar_delete_calls','calendar_delete_pending','counts_after','tasks_after','error')}))
 return 0 if result['state']=='EXACT_CORE12_EVENT_AND_EMPTY_CALENDAR_REMOVED_BASELINE_RESTORED' else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
 if not a.execute:print('INERT: exact Core12 event and empty LOCAL calendar only; coordinated lock required');raise SystemExit(0)
 raise SystemExit(execute())
