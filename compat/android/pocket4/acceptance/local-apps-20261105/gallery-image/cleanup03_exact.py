#!/usr/bin/python3 -I
"""Delete only observed empty MediaStore directory 60 and its exact temporary package."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,re,signal,types

OUT=Path('/home/alex/work/pocket4-gallery-cleanup-20261105-r12-03')
OLD=Path('/home/alex/work/pocket4-gallery-image-20261105-r12-01')
READ=Path('/home/alex/work/pocket4-gallery-cleanup-readonly-20261105-r12-02/result.json')
READ_SHA='ca2687706484024249d4455a78c2cc88ef76261fef089f6c7d2b03192306a0f9'
FLOW=Path('/home/alex/work/pocket4-gallery-tools-20261105-r12-01/run_gallery01.py')
FLOW_SHA='1373820f8c1a39203bb764d3b5f5859b1ef91387cc4b04fb564d4d4d3cd7f40e'
RESULT_SHA='eab3d43deddcb154e8b4f717761182df9b03f49d68f1b7826e4a5e9457c11f67'
URI='content://media/external_primary/file/60'

def need(value,reason):
    if not value:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def load(path,pin,name):
    raw=path.read_bytes();need(sha(raw)==pin,'SOURCE_CHANGED')
    value=types.ModuleType(name);value.__file__=str(path);exec(compile(raw,str(path),'exec'),value.__dict__);return value
def expired(*args):raise TimeoutError('CLEANUP_DEADLINE_NO_REPLAY')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    if not args.execute:print('INERT');return 0
    need(os.geteuid()==0 and OUT.parent.resolve()==OUT.parent,'ROOT_CANONICAL_REQUIRED')
    f=load(FLOW,FLOW_SHA,'gallery_saved')
    tx,base,doc,diag=[load(Path(p),pin,'gallery_cleanup_'+str(i)) for i,(p,pin) in enumerate(f.PINS.items())]
    prior=json.loads(tx.read_regular(OLD/'result.json',RESULT_SHA,65536))
    read=json.loads(tx.read_regular(READ,READ_SHA,65536))
    need(prior['business_scope_completed'] and prior['cleanup']['image_deleted']
        and prior['normal_closed_tasks']==prior['owned_tasks']==[944,945]
        and prior['pending_effect'] is None and prior['close_pending'] is None
        and not prior['install_pending'] and not prior['uninstall_pending'],'PRIOR_UNKNOWN_EFFECT')
    need(read['state']=='EXACT_EMPTY_DIRECTORY_READBACK_COMPLETE' and read['children']==[]
        and read['image_absence']==[] and read['UI_actions']==read['installs']==read['provider_writes']==0
        and read['namespace']==[prior['owned_directory_index_retained']],'READONLY_SCOPE_CHANGED')
    result={'state':'FAILED','cleanup_verified':False,'whole_app_production_ready':False,'UI_actions':0,
        'installs':0,'automatic_retry':False,'provider_delete_calls':0,'uninstall_calls':0,'rmdir_calls':0,
        'original_result_preserved':True,'started_utc':stamp(),'pending_effect':None,
        'original_result_sha256':RESULT_SHA,'readonly_reconciliation_sha256':READ_SHA}
    folder_fd=parent=None;previous_signal=signal.signal(signal.SIGALRM,expired)
    with tx.ui_lock():
        OUT.mkdir(mode=0o750);os.chmod(OUT,0o750);os.chown(OUT,0,1000);(OUT/'ui').mkdir(mode=0o700)
        base.ROOT=OUT/'ui';base.PACKAGE=f.GALLERY;base.COMPONENT=f.COMPONENT
        doc.PACKAGE=f.PACKAGE;doc.RUN=f.RUN
        signal.setitimer(signal.ITIMER_REAL,180)
        try:
            with tx.CameraSession(OUT/'commands') as s:
                g=f.Gallery(s,tx,base,doc,diag,None)
                result['guard_before']=s.guard();need(result['guard_before']==prior['guard_after']==read['guard_after'],'EPOCH_CHANGED')
                expected=prior['installed_identity']
                need(doc.identity(s,f.PACKAGE,f.APK_SHA)==expected==read['installed_identity'],'FIXTURE_IDENTITY_CHANGED')
                need(g.prefs()==read['owned_preferences'] and g.prefs()['phase']=='DELETED','OWNED_PHASE_CHANGED')
                roots,tasks=g.ui.stacks('before-cleanup')
                need(not {944,945}&(set(roots)|tasks) and sorted(tasks)==read['task_ids']
                    and not any(c['component'].split('/')[0] in (f.GALLERY,f.PACKAGE)
                        for r in roots.values() for c in r['children']),'OWNED_TASK_RETURNED_OR_TASK_SET_CHANGED')
                result['preserved_task_ids']=sorted(tasks)
                need(g.namespace('before-delete')==read['namespace'],'EXACT_ROW_CHANGED')
                need(g.query('children',"SELECT _id FROM files WHERE parent=60 OR _data GLOB '"+f.GUEST_FOLDER+"/*' ORDER BY _id")==[],
                    'DIRECTORY_CHILD_ROW_PRESENT')
                need(g.query('deleted-image',"SELECT _id FROM files WHERE _id=61")==[],'IMAGE61_RETURNED')
                original=read['selected_receipts']['media-original-before']['value']['rows']
                need(g.original_media('original-before')==original,'PREEXISTING_MEDIA_CHANGED')
                parent=s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                folder_fd=os.open(f.FOLDER,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
                g.folder_parent=parent;g.folder_fd=folder_fd;g.folder_birth=read['directory_identity']
                need(g.held_folder()==[],'EXACT_DIRECTORY_NOT_EMPTY')
                predicate="_id=60 AND _data='"+f.GUEST_FOLDER+"' AND _display_name='"+f.FOLDER+"' AND relative_path='DCIM/' AND media_type=0 AND is_pending=0 AND owner_package_name IS NULL"
                argv=['/system/bin/content','delete','--user','0','--uri',URI,'--where',predicate]
                g.record('exact-empty-directory-delete-intent',{'argv':argv,'actual_row':read['namespace'][0],
                    'directory_identity':g.folder_birth,'children':[],'physical_entries':[],
                    'created_during_exact_owned_seed':True,'automatic_retry':False,'App_delete_qualification':False})
                result['pending_effect']='delete-empty-directory-row60';result['provider_delete_calls']=1
                raw=s.android(argv,25).decode();g.record('directory-delete-ack',{'stdout':raw})
                need(re.fullmatch(r'Deleted 1 rows\.?',raw.strip()),'DELETE_RESPONSE_UNKNOWN')
                result['provider_delete_acknowledged']=True
                need(g.namespace('after-delete')==[],'OWNED_NAMESPACE_NOT_EMPTY')
                try:os.stat(f.FOLDER,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:result['provider_removed_directory']=True
                else:
                    need(g.held_folder()==[],'DIRECTORY_CHANGED_AFTER_PROVIDER_DELETE')
                    result['pending_effect']='remove-exact-empty-directory';result['rmdir_calls']=1
                    os.rmdir(f.FOLDER,dir_fd=parent)
                try:os.stat(f.FOLDER,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:result['physical_directory_absent']=True
                else:raise RuntimeError('DIRECTORY_NOT_ABSENT')
                need(os.fstat(folder_fd).st_nlink==0,'HELD_REMOVED_DIRECTORY_NOT_UNLINKED')
                result['pending_effect']=None
                need(g.prefs()==read['owned_preferences'] and doc.identity(s,f.PACKAGE,f.APK_SHA)==expected,
                    'FIXTURE_CHANGED_BEFORE_UNINSTALL')
                g.record('exact-fixture-uninstall-intent',{'package':f.PACKAGE,'identity':expected,'automatic_retry':False})
                result['pending_effect']='uninstall-exact-fixture';result['uninstall_calls']=1
                raw=s.android(['/system/bin/pm','uninstall',f.PACKAGE],60).decode()
                need(raw.strip()=='Success','UNINSTALL_RESPONSE_UNKNOWN');doc.absent(s)
                result['pending_effect']=None;result['package_absent']=True
                need(g.namespace('final-empty')==[] and g.original_media('original-final')==original,'FINAL_MEDIA_SCOPE_CHANGED')
                _,after=g.ui.stacks('after-cleanup');need(after==tasks,'OTHER_TASK_SET_CHANGED')
                result['gallery_identity']=g.gallery_identity();need(result['gallery_identity']==prior['gallery_after'],'GALLERY_IDENTITY_CHANGED')
                result['guard_after']=s.guard();s.caller_status('gallery-cleanup-final')
                need(result['guard_before']==result['guard_after'],'FINAL_MAIN_CHANGED')
                result.update(state='EXACT_DIRECTORY_INDEX_AND_FIXTURE_CLEANED',cleanup_verified=True,
                    original_media_metadata_preserved=True,other_tasks_preserved=True,old_owned_tasks_absent=True)
        except BaseException as exc:result['error']=type(exc).__name__+':'+str(exc)
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous_signal)
            for fd in (folder_fd,parent):
                if fd is not None:os.close(fd)
            result['finished_utc']=stamp();tx.write_new(OUT/'result.json',result,alex_readable=True)
    print(json.dumps({k:result.get(k) for k in ('state','cleanup_verified','error','pending_effect','provider_delete_calls','uninstall_calls','rmdir_calls')}))
    return 0 if result['cleanup_verified'] else 1

if __name__=='__main__':raise SystemExit(main())
