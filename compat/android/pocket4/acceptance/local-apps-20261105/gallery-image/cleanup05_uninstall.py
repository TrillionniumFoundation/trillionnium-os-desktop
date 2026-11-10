#!/usr/bin/python3 -I
"""After independent row/path absence, uninstall only the retained Gallery helper."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,signal,types
OUT=Path('/home/alex/work/pocket4-gallery-final-cleanup-20261105-r12-05')
FLOW=Path('/home/alex/work/pocket4-gallery-tools-20261105-r12-01/run_gallery01.py')
FLOW_SHA='1373820f8c1a39203bb764d3b5f5859b1ef91387cc4b04fb564d4d4d3cd7f40e'
READ=Path('/home/alex/work/pocket4-gallery-cleanup-reconcile-20261105-r12-04/result.json')
READ_SHA='4eca5fe4b9f2d46fa4d19a345e1c3eacfd6240ef2e8fd7d5eeb6cb1f96c2b1b1'
def need(ok,why):
    if not ok:raise RuntimeError(why)
def load(path,pin,name):
    raw=path.read_bytes();need(hashlib.sha256(raw).hexdigest()==pin,'SOURCE_CHANGED')
    m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def expired(*args):raise TimeoutError('CLEANUP_DEADLINE_NO_REPLAY')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    if not args.execute:print('INERT');return 0
    need(os.geteuid()==0 and OUT.parent.resolve()==OUT.parent,'ROOT_CANONICAL_REQUIRED')
    f=load(FLOW,FLOW_SHA,'gallery_cleanup05');tx,base,doc,diag=[load(Path(p),pin,'g05_'+str(i)) for i,(p,pin) in enumerate(f.PINS.items())]
    read=json.loads(tx.read_regular(READ,READ_SHA,16384))
    need(read['state']=='EXACT_CLEANUP_OUTCOME_READBACK_COMPLETE' and read['directory_absent']
        and read['namespace']==read['children']==[] and read['old_owned_tasks_absent']
        and read['saved_receipts']['directory-delete-ack']['value']['stdout']=='','RECONCILIATION_CHANGED')
    result={'state':'FAILED','cleanup_verified':False,'whole_app_production_ready':False,'UI_actions':0,
        'provider_delete_calls':0,'directory_removal_calls':0,'installs':0,'uninstall_calls':0,'pending_effect':None,
        'automatic_retry':False,'original_results_preserved':True,'reconciliation_sha256':READ_SHA,
        'started_utc':datetime.now(timezone.utc).isoformat()}
    with tx.ui_lock():
        OUT.mkdir(mode=0o750);os.chmod(OUT,0o750);os.chown(OUT,0,1000);(OUT/'ui').mkdir(mode=0o700)
        base.ROOT=OUT/'ui';base.PACKAGE=f.GALLERY;base.COMPONENT=f.COMPONENT;doc.PACKAGE=f.PACKAGE;doc.RUN=f.RUN
        oldsignal=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,150)
        try:
            with tx.CameraSession(OUT/'commands') as s:
                g=f.Gallery(s,tx,base,doc,diag,None)
                result['guard_before']=s.guard();need(result['guard_before']==read['guard_after'],'EPOCH_CHANGED')
                before=doc.identity(s,f.PACKAGE,f.APK_SHA);need(before==read['installed_identity'],'EXACT_HELPER_CHANGED')
                need(g.prefs()==read['prefs'] and read['prefs']['phase']=='DELETED' and read['prefs']['pending']=='','PHASE_CHANGED')
                def absence(label):
                    need(g.namespace(label)==[] and g.query(label+'-ids',"SELECT _id FROM files WHERE _id IN (60,61) OR parent=60 OR _data GLOB '"+f.GUEST_FOLDER+"/*' ORDER BY _id")==[],
                        'OWNED_MEDIA_NOT_ABSENT')
                    parent=s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:
                        try:os.stat(f.FOLDER,dir_fd=parent,follow_symlinks=False)
                        except FileNotFoundError:pass
                        else:raise RuntimeError('OWNED_DIRECTORY_RETURNED')
                    finally:os.close(parent)
                    need(g.original_media(label+'-original')==read['original_media'],'PREEXISTING_MEDIA_CHANGED')
                absence('before')
                roots,tasks=g.ui.stacks('before-uninstall');need(sorted(tasks)==read['tasks'] and not {944,945}&(set(roots)|tasks),'TASKS_CHANGED')
                result['gallery_before']=g.gallery_identity()
                g.record('exact-helper-uninstall-intent',{'package':f.PACKAGE,'identity':before,
                    'row60_and_61_absent':True,'physical_directory_absent':True,'no_provider_or_directory_delete_replay':True})
                result['pending_effect']='uninstall-exact-helper';result['uninstall_calls']=1
                raw=s.android(['/system/bin/pm','uninstall',f.PACKAGE],60).decode()
                need(raw.strip()=='Success','UNINSTALL_RESPONSE_UNKNOWN');doc.absent(s)
                result['pending_effect']=None;result['package_absent']=True
                absence('after');_,after=g.ui.stacks('after-uninstall');need(after==tasks,'OTHER_TASKS_CHANGED')
                result['gallery_after']=g.gallery_identity();need(result['gallery_before']==result['gallery_after'],'GALLERY_CHANGED')
                result['guard_after']=s.guard();s.caller_status('gallery-final-cleanup-caller')
                need(result['guard_before']==result['guard_after'],'MAIN_CHANGED')
                result.update(state='GALLERY_OWNED_FIXTURE_CLEANUP_COMPLETE',cleanup_verified=True,
                    physical_directory_absent=True,owned_media_rows_absent=True,original_media_metadata_preserved=True,
                    other_tasks_preserved=True,old_owned_tasks_absent=True,original_helper_uid=before['uid'])
        except BaseException as exc:result['error']=type(exc).__name__+':'+str(exc)
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,oldsignal)
            result['finished_utc']=datetime.now(timezone.utc).isoformat();tx.write_new(OUT/'result.json',result,alex_readable=True)
    print(json.dumps({k:result.get(k) for k in ('state','cleanup_verified','error','pending_effect','uninstall_calls')}))
    return 0 if result['cleanup_verified'] else 1
if __name__=='__main__':raise SystemExit(main())
