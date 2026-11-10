"""One cleanup of the observed cancelled chooser's exact retained fixture; no UI."""
import hashlib,json,os,signal,sys,types
from pathlib import Path
OUT=Path('/home/alex/work/pocket4-documents-cleanup09-20261105-r12-01')
BASE=Path('/home/alex/work/pocket4-documents-flow-20261105-r12-09')
TOOLS=Path('/home/alex/work/pocket4-documents-flow-20261105-r12-tools-09')
RECON=Path('/home/alex/work/pocket4-documents-reconcile09-20261105-r12-01/result.json')
def need(ok,why):
    if not ok:raise RuntimeError(why)
def load(path,pin,name):
    raw=path.read_bytes();need(hashlib.sha256(raw).hexdigest()==pin,'SOURCE_PIN_CHANGED')
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def expired(*args):raise TimeoutError('CLEANUP_DEADLINE_NO_RETRY')
def main():
    if sys.argv[1:]!=['--execute']:
        print(json.dumps({'state':'PLAN_ONLY','ui_actions':0,'installs':0}));return 0
    need(os.geteuid()==0 and OUT.parent.resolve()==OUT.parent,'CANONICAL_ROOT_REQUIRED')
    tx=load(Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py'),
        'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470','cleanup09_tx')
    f=load(TOOLS/'run_saf09.py','93ce75cffa2ac2dadf70d5f10647f4ec0c9ef597baed7d06f96cbe0d5719056d','cleanup09_flow')
    ui=load(TOOLS/'ui_adapter02.py','74234c0a3db0659e4632ce3e76510d80fe8b015514c6a72dc9e34bca31a83a54','cleanup09_ui')
    prior=json.loads(tx.read_regular(BASE/'result.json','6048be3b22be228dc6f1a845ab8c7d94afa4ceddd185900e402e93f004e62e15',65536))
    recon=json.loads(tx.read_regular(RECON,'47fbaee8c2eaa9595061f35823a0dbbcd839ca73a9f24343c990dc1bc4078fdb',262144))
    need(prior['owned_task_ids_closed']==[938,937] and prior['owned_remove_calls']==2
        and prior['pending_effects']=={'files-open-owned-file':{'input_acknowledged':True,'kind':'tap','post_capture_outcome_unknown':True}}
        and recon['read_only'] is True and recon['ui_actions']==0
        and recon['current_tasks']['old_owned_ids_absent'] is True
        and recon['current_tasks']['no_temporary_client_or_files_task'] is True,'ORIGINAL_CANCELLATION_PROOF_CHANGED')
    # Preserve the original pending result. This new controller only cleans the
    # already-closed chooser scope; it never reports an accepted VIEW or retries it.
    result={'state':'CLEANUP_NOT_STARTED','cleanup_verified':False,'business_flow_completed':False,
        'whole_app_production_ready':False,'ui_actions':0,'installs':0,'original_open_success':False,
        'original_pending_result_preserved':True,'automatic_retry':False}
    with tx.ui_lock():
        os.umask(0o077);OUT.mkdir(mode=0o700);f.ROOT=OUT
        signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,150)
        try:
            with tx.CameraSession(OUT/'commands') as session:
                need(session.guard()==prior['final_guard']==recon['guard_before']==recon['guard_after'],'ORIGINAL_GUARD_CHANGED')
                flow=f.Flow(session,tx,ui)
                roots,tasks=flow.ui.stacks('current-task-absence')
                need(not ({937,938}&(set(roots)|tasks)) and not any(c['component'].split('/')[0] in (f.PACKAGE,f.DOCS)
                    for r in roots.values() for c in r['children']),'ORIGINAL_OWNED_TASK_RETURNED')
                flow.ui.baseline=tasks
                current=f.identity(session,f.PACKAGE,f.APK_SHA)
                need(current==prior['installed_identity']==recon['installed_identity'],'RETAINED_PACKAGE_CHANGED')
                prefs=flow.pref_state()
                need(prefs==recon['owned_preferences'] and prefs['phase']==prefs['pending']=='FILES_REQUESTED'
                    and prefs['content_writes']==prefs['create_picker_calls']==prefs['provider_rename_calls']==prefs['files_launch_calls']==1
                    and prefs['content_readbacks']==3 and prefs.get('files_view_results',0)==0
                    and prefs.get('provider_delete_calls',0)==0 and prefs.get('open_picker_calls',0)==0,
                    'CANCELLED_NAVIGATION_OR_FILE_STATE_CHANGED')
                folder=flow.folder
                folder.parent=session.target.open_root('/storage/emulated/0',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                folder.fd=os.open(f.FOLDER,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=folder.parent)
                folder.birth=recon['directory']['birth'];folder.created=True
                try:
                    actual=folder.verify(f.FILES,'original-renamed-file-before-cleanup');expected=recon['retained_file']
                    need(actual['identity']==expected['identity'] and str(actual['mtime_ns'])==expected['mtime_ns']
                        and str(actual['ctime_ns'])==expected['ctime_ns'],'RETAINED_FILE_IDENTITY_CHANGED')
                    need(flow.pref_state()==prefs,'APP_PHASE_CHANGED_BEFORE_CLEANUP')
                except BaseException:
                    folder.close();raise
                flow.installed=current
                flow.ui.record('original-open-cancelled-cleanup-only',{'original_job':'1a1ab5d9616-fc05-4d05',
                    'old_tasks_absent':[938,937],'scope':'exact retained fixture only','original_business_pass':False,
                    'original_pending_preserved':prior['pending_effects'],'navigation_replayed':False})
                result['cleanup']=flow.cleanup()
                need(not result['cleanup']['errors'] and result['cleanup']['package_absent_verified']
                    and result['cleanup']['package_uninstalled_verified']
                    and result['cleanup']['file_cleanup']['directory_removed_verified'],'EXACT_CLEANUP_NOT_VERIFIED')
                roots,after=flow.ui.stacks('tasks-after-cleanup');need(after==tasks,'OTHER_TASKS_CHANGED')
                result.update(state='EXACT_RETAINED_FIXTURE_CLEANED',cleanup_verified=True,
                    original_package_identity=current,pending_effects={},final_guard=session.guard(),
                    old_owned_tasks_absent=True,other_tasks_preserved=True)
        except BaseException as exc:result.update(state='CLEANUP_STOPPED',error=type(exc).__name__+': '+str(exc))
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);tx.write_new(OUT/'result.json',result)
    print(json.dumps(result,indent=2,sort_keys=True));return 0 if result['cleanup_verified'] else 1
if __name__=='__main__':raise SystemExit(main())
