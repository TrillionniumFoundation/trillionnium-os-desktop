#!/usr/bin/python3 -I
"""Read only the exact retained Docs09 fixture after its unconfirmed dialog."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,signal,types

OLD=Path('/home/alex/work/pocket4-documents-features-flow-20261105-r12-09')
OUT=Path('/home/alex/work/pocket4-documents-features-reconcile-20261105-r12-09-01')
TOOLS=Path('/home/alex/work/pocket4-documents-features-tools-20261105-r12-09')
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PINS={'features_ui.py':'edaf39c50d6ff85748fef1b287bf3875fd51321a0a2a837ff6f30e59a8cd4417',
      'package_fixture.py':'596dfb03273f2810cf9f98871668042bb62f85807d6cdad9a113b87003b8d932',
      'owned_tree.py':'e4b19adc1e47719413bfae5656bac8b04f5624c779ee7118b490327e2776a445'}
RESULT_SHA='4361723c1bca9601a0770feb6492aa93ad3bfa9f4eeb6eebafcec01b2f7ac4be'
SAVED={'010-owned-root-created.json':'9cb2ca9412c2edc0f2facb1d1082ab1c76c37852dface6383201b50477f830e6',
       '002-target-packages-before.json':'37d4afa9561eac8c30f42071b0d63d87e9affd565e71377f1dde96cabf787864',
       '843-delete-copies-before.json':'da14ead6833ef960e9739ee45e92792fe3bf2c8c7b5fef85a3f958f5fecfb378',
       '861-delete-copies-dialog-or-result.json':'474e54d2247b9c09897bfeb6be4c089dd7bf6cafb12f60c89984e215bd7f29ce'}

def need(value,why):
    if not value:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def load(path,pin):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'SOURCE_CHANGED:'+Path(path).name)
    mod=types.ModuleType('reconcile_'+Path(path).stem);mod.__file__=str(path)
    exec(compile(raw,str(path),'exec'),mod.__dict__);return mod
class Deadline(BaseException):pass
def expired(signum,frame):raise Deadline('READ_ONLY_RECONCILIATION_DEADLINE')

def execute():
    tx=load(TX,TX_SHA);mods={n:load(TOOLS/n,p) for n,p in PINS.items()}
    result={'schema':'pocket4-documents09-readonly-delete-reconciliation-v1','state':'NOT_VERIFIED',
        'started_utc':now(),'original_result_sha256':RESULT_SHA,'original_failure_preserved':True,
        'UI_actions':0,'file_writes':0,'provider_writes':0,'package_mutations':0,
        'delete_confirmation_replayed':False,'business_delete_credit':False,
        'whole_app_production_ready':False,'outcome_unknown':True}
    OUT.mkdir(mode=0o700);(OUT/'records').mkdir(mode=0o700)
    seq=0;tree=None
    def record(label,value):
        nonlocal seq
        seq+=1;tx.write_new(OUT/'records'/('%03d-'%seq+label+'.json'),value)
    old_handler=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,120)
    try:
        original=json.loads(tx.read_regular(OLD/'result.json',RESULT_SHA,262144))
        saved={name:json.loads(tx.read_regular(OLD/'ui'/name,pin,262144)) for name,pin in SAVED.items()}
        need(original['state']=='OWNED_CLEANUP_UNVERIFIED' and original['task_set_restored'] is True
            and original['owned_tasks']==original['ui_pending']==original['helper_pending']=={}
            and original['owned_task_ids_closed']==[978,977] and original['ui_actions']==43
            and original['baseline_task_ids']==[851] and not original['install_pending']
            and not original['uninstall_pending'],'ORIGINAL_TERMINAL_BOUNDARY_CHANGED')
        pending=original['file_operation_pending'];need(pending['label']=='delete-copies'
            and pending['business_result_verified'] is False and pending['input_replayed'] is False,
            'ORIGINAL_FILE_INTENT_CHANGED')
        before=saved['843-delete-copies-before.json'];ledger=before['entries']
        need(ledger==original['gates']['FILES_MULTIPLE_MOVE']['layout']
            and sorted(ledger)==pending['before'],'ORIGINAL_LEDGER_DIFFERS')
        root_birth=saved['010-owned-root-created.json']['birth'];need(before['root_birth']==root_birth,
            'ORIGINAL_ROOT_BIRTH_DIFFERS')
        names=[p.name for p in (OLD/'ui').iterdir()]
        need(not any('delete-copies-confirm' in n or 'delete-copies-after-confirm' in n for n in names),
            'FINAL_CONFIRMATION_RECORD_PRESENT')
        nodes=saved['861-delete-copies-dialog-or-result.json']['native']['nodes']
        def unique(rid,text,klass):
            matches=[n for n in nodes if n.get('resource-id')==rid and n.get('text')==text
                and n.get('class')==klass and n.get('package')=='com.android.documentsui'
                and n.get('visible') is True and n.get('enabled') is True]
            need(len(matches)==1,'SAVED_EXACT_DELETE_DIALOG_REQUIRED');return matches[0]
        title=unique('com.android.documentsui:id/alertTitle','Delete forever?','android.widget.TextView')
        message=unique('android:id/message','2 items will be deleted forever. This can’t be undone.','android.widget.TextView')
        positive=unique('android:id/button1','OK','android.widget.Button')
        need(positive['clickable'] is True and title['window_id']==message['window_id']==positive['window_id'],
            'SAVED_DIALOG_WINDOW_CHANGED')
        result['saved_confirmation']={'title':title['text'],'message':message['text'],
            'positive_text':positive['text'],'final_confirmation_intent_count':0,
            'original_toolbar_ack_is_not_delete_completion':True}
        with tx.ui_lock(),tx.CameraSession(OUT/'commands') as session:
            guard=session.guard();need(guard==original['initial_guard']==original['final_guard'],'MAIN_GENERATION_CHANGED')
            result['guard_before']=guard
            ui=types.SimpleNamespace(record=record,owned={},pending={})
            package=mods['package_fixture.py'].PackageFixture(session,tx,ui,result)
            def identities(label):
                target=package.packages(label)
                need(target==saved['002-target-packages-before.json'],'TARGET_PACKAGE_OR_PROVIDER_CHANGED')
                own=mods['package_fixture.py'].identity(session,mods['package_fixture.py'].PACKAGE,
                    mods['package_fixture.py'].APK_SHA,10192)
                need(own==original['installed_identity'],'RETAINED_HELPER_IDENTITY_CHANGED')
                return {'targets':target,'helper':own}
            result['identity_before']=identities('packages-before')
            def task_snapshot(label):
                raw=session.android(['/system/bin/cmd','activity','stack','list'],15).decode()
                roots,tasks=mods['features_ui.py'].parse_stacks(raw)
                need(tasks=={851} and all(c['component'].split('/')[0]=='com.android.droidloom.home'
                    for r in roots.values() for c in r['children']),'EXPECTED_ONLY_ORIGINAL_HOME_TASK')
                record(label,{'raw':raw,'tasks':sorted(tasks)});return {'roots':roots,'tasks':sorted(tasks)}
            result['tasks_before']=task_snapshot('tasks-before')
            tree=mods['owned_tree.py'].OwnedTree(session,record)
            tree.parent=session.target.open_root('/storage/emulated/0',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            tree.fd=os.open(mods['owned_tree.py'].FOLDER,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                dir_fd=tree.parent)
            tree.birth=root_birth;tree.created=True;tree.ledger=ledger;tree.expected=set(ledger)
            first=tree.scan();result['first_fresh_scan']=first
            need(first==ledger,'RETAINED_NAMESPACE_OR_CONTENT_CHANGED')
            phase=package.pref_state();need(phase is not None and phase.get('phase')=='FILES_OPENED'
                and phase.get('pending','')==phase.get('step_pending','')==phase.get('error','')==''
                and phase.get('content_writes')==2 and phase.get('content_readbacks')==2
                and phase.get('files_launch_calls')==1,'RETAINED_HELPER_TRANSITION_CHANGED')
            result['helper_phase']=phase
            package.grants('retained-exact-grants',False)
            result['identity_after']=identities('packages-after')
            second=tree.scan();result['second_fresh_scan']=second
            need(second==first==ledger,'RETAINED_NAMESPACE_CHANGED_BETWEEN_READS')
            result['tasks_after']=task_snapshot('tasks-after')
            need(result['tasks_before']==result['tasks_after'],'ORIGINAL_HOME_STACK_CHANGED')
            result['guard_after']=session.guard();need(result['guard_after']==guard,'MAIN_CHANGED_AFTER_READS')
            result.update(state='FINAL_CONFIRMATION_NOT_DISPATCHED_AND_RETAINED_LAYOUT_UNCHANGED',
                current_fixture_static_and_exact=True,final_confirmation_not_dispatched=True,
                original_file_operation_pending=pending,retained_helper_and_fixture=True,
                historical_outcome_unknown_preserved=True,outcome_unknown=False)
    except BaseException as exc:result['error']=type(exc).__name__+':'+str(exc)
    finally:
        if tree is not None:tree.close()
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
        result['finished_utc']=now();tx.write_new(OUT/'result.json',result)
        print(json.dumps(result,sort_keys=True))
    return 0 if result.get('current_fixture_static_and_exact') else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:print(json.dumps({'state':'READ_ONLY_PLAN','output':str(OUT),'UI_actions':0,'provider_writes':0}))
    else:raise SystemExit(execute())
