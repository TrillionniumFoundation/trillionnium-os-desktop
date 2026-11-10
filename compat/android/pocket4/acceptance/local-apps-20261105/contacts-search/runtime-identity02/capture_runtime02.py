#!/usr/bin/python3 -I
"""Observe only Contacts UID10055 during its separate, single authorized UI flow."""
from pathlib import Path
import argparse,datetime,gzip,hashlib,json,os,stat,time,types

TOOLS=Path('/home/alex/work/pocket4-contacts-runtime-tools-20261105-r12-02')
ROOT=Path('/home/alex/work/pocket4-contacts-runtime-evidence-20261105-r12-02')
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION_SHA='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
RUNTIME_SHA='8018acc97132f3e417cbcb47a23071a45849f7e52f197a6aa250ccab7cce9422'
FLOW=Path('/home/alex/work/pocket4-contacts-search-flow-20261105-r12-01/result.json')
CONTROLLER=Path('/home/alex/work/pocket4-contacts-search-tools-20261105-r12-01/contacts_search01.py')
CONTROLLER_SHA='4bcce85164f939ae9cf1aae77bd27fd48e0fc428692c65267b9a21c421ba1f54'
APK='/product/priv-app/Contacts/Contacts.apk'
APK_SHA='11f8be5fd46dd79ee4f7524d5d1334e21ce0f9e23892b2940a5b6091e2f349d0'
TOKEN='Pocket4_ContactsSearch_r12_c83f16a20e83a54b'
MAX_SECONDS=350

def need(ok,code):
    if not ok:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load(path,digest,name):
    raw=path.read_bytes();need(sha(raw)==digest,'SOURCE_PIN:'+name)
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m

def terminal_read(tx):
    if not FLOW.exists():return None
    try:
        raw=tx.read_regular(FLOW,maximum=131072)
        value=json.loads(raw)
    except (FileNotFoundError,json.JSONDecodeError):return None
    need(value.get('schema')=='contacts-search-owned-flow/v1' and value.get('marker')=='Pocket4 Search QA r12 c83f16a2'
         and value.get('edited_marker')=='Pocket4 Search QA r12 c83f16a2 Edited'
         and value.get('finished_utc'),'EXACT_SEPARATE_FLOW_RESULT_REQUIRED')
    return {'bytes':len(raw),'sha256':sha(raw),'state':value.get('state'),'finished_utc':value['finished_utc'],
            'UI_flow_business_success':value.get('business_success_verified'),'UI_flow_cleanup_verified':value.get('cleanup_verified')}

def execute():
    need(os.geteuid()==0 and not os.path.lexists(ROOT),'CREATE_ONLY_RUNTIME_ROOT')
    tx=load(TX,TX_SHA,'contacts_runtime_tx')
    need(tx.ACTIVATION_SHA==ACTIVATION_SHA,'EXACT_ORIGINAL_MAIN_PROFILE')
    runtime=load(TOOLS/'runtime_evidence.py',RUNTIME_SHA,'contacts_runtime_collector')
    need(runtime.TARGETS=={'com.android.contacts':10055} and runtime.PROCESS_NAMES=={'com.android.contacts':{'com.android.contacts'}},
         'EXACT_CONTACTS_PROCESS_SCOPE')
    os.umask(0o077);ROOT.mkdir(mode=0o750);os.chown(ROOT,0,1000);os.chmod(ROOT,0o750)
    os.sched_setaffinity(0,{21})
    result={'schema':'contacts-separate-runtime-observation/v1','state':'FAILED','started_utc':stamp(),
            'UI_actions':0,'Android_commands':0,'provider_mutations':0,'service_or_Main_mutations':0,
            'caller_environment_or_process_memory_read':False,'fixture_file_fd_scope_not_a_Contacts_database_read':True,
            'runner_sha256':sha(Path(__file__).read_bytes()),'collector_sha256':RUNTIME_SHA,
            'transport_sha256':TX_SHA,'activation_sha256':ACTIVATION_SHA,'maximum_seconds':MAX_SECONDS,
            'runtime_identity_automatically_qualified':False,'whole_app_production_ready':False}
    sampler=None
    try:
        with tx.CameraSession(ROOT/'commands') as session:
            result['guard_before']=session.guard()
            apk,metadata=session.target.read_file(APK,16*1024*1024,single_link=True)
            need(len(apk)==11839391 and sha(apk)==APK_SHA,'INSTALLED_CONTACTS_CHANGED')
            result['APK']={'bytes':len(apk),'sha256':sha(apk),'metadata':metadata}
            sampler=runtime.RuntimeEvidence(session,tx,ROOT/'samples',TOKEN)
            sampler.max_seconds=MAX_SECONDS+5
            started=time.monotonic();until=started+MAX_SECONDS
            sampler.start()
            try:
                while time.monotonic()<until:
                    session.guard()
                    if CONTROLLER.exists():
                        tx.read_regular(CONTROLLER,CONTROLLER_SHA,maximum=65536)
                    sampler.phase_changed('interval-%02d'%int((time.monotonic()-started)//20))
                    terminal=terminal_read(tx)
                    if terminal is not None:
                        # This receipt is a separate flow's outcome, not a runtime gate.
                        result['separate_UI_flow_result']=terminal
                        break
                    time.sleep(.5)
                else:raise RuntimeError('NO_COMPLETED_BOUND_UI_FLOW_WITHIN_LEASE')
            finally:
                result['sampler']=sampler.stop()
            need(result['sampler']['thread_joined'] and
                 'com.android.contacts' in result['sampler']['processes_observed'],
                 'ACTUAL_CONTACTS_PROCESS_OBSERVATION_REQUIRED')
            again,after=session.target.read_file(APK,16*1024*1024,single_link=True)
            need(sha(again)==APK_SHA and after==metadata,'INSTALLED_CONTACTS_CHANGED_DURING_CAPTURE')
            result['guard_after']=session.guard();need(result['guard_before']==result['guard_after'],'MAIN_CHANGED')
            result['state']='BOUNDED_CONTACTS_RUNTIME_OBSERVATIONS_CAPTURED_REVIEW_REQUIRED'
    except BaseException as error:
        result['state']='FAILED'
        result['error']=type(error).__name__+':'+str(error)
    result['finished_utc']=stamp()
    tx.write_new(ROOT/'result.json',result,alex_readable=True)
    raw=(ROOT/'result.json').read_bytes();packed=gzip.compress(raw,mtime=0)
    tx.write_new(ROOT/'result.json.gz',packed,alex_readable=True)
    print(json.dumps({'state':result['state'],'error':result.get('error'),'result_bytes':len(raw),'result_sha256':sha(raw),
        'gzip_bytes':len(packed),'gzip_sha256':sha(packed),'sample_count':result.get('sampler',{}).get('sample_count'),
        'UI_actions':0,'whole_app_production_ready':False}))
    return 0 if result['state']=='BOUNDED_CONTACTS_RUNTIME_OBSERVATIONS_CAPTURED_REVIEW_REQUIRED' else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');args=p.parse_args()
    if args.execute:raise SystemExit(execute())
    print(json.dumps({'state':'INERT','UI_actions':0,'provider_mutations':0}))
