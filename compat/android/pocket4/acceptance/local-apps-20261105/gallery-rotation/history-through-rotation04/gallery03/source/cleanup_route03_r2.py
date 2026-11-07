#!/usr/bin/python3 -I
"""One new cleanup transaction for the reconciled, expired Gallery03 fixture.

Normal-close only task1005, then exact image100/image98, empty directories99/97,
then helper UID10197. No Open/rotation/helper replay, no renewal of its old lease.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,gzip,hashlib,json,os,re,signal,types,xml.etree.ElementTree as ET

OUT=Path('/home/alex/work/pocket4-gallery-rotation-cleanup-route03-20261105-r12-02')
SOURCE=Path('/home/alex/work/pocket4-gallery-rotation-flow-20261105-r12-03')
TOOLS=Path('/home/alex/work/pocket4-gallery-rotation-tools-20261105-r12-03')
FAILED_SHA='41a2a9c45ab1e04fc70774f711384b701b7e495b8a46011f97cd18f0c0f0fb66'
READONLY=Path('/home/alex/work/pocket4-gallery-rotation-live-route03-20261105-r12-01/result.json')
READONLY_SHA='8f13efcbd0f8a3f80e11b648a9b2866c0d75b2d871c4ff329b36bd11b53e822d'
SAVED_REVIEW_SHA='a4af8f5ad2da6422317739a53a89cab5619685a240002083750b66ed120db978'
TRANSPORT=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TRANSPORT_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PINS={'rotation_ui.py':'ac885a393ff6b3e6cc477bb9c0acf55284fe3e4c92474fb82571884d07d9b650',
      'rotation_package.py':'44abbfe0193905a7b3a6137b4bb95dafc8d6cec4d795e8b258b97508cdd83dd4',
      'owned_media.py':'95b6c90fbc9ac22c41ca2c35d9ba3a13ce140de9cc52f710f2b5fd080506ae9b',
      'bounded_diagnostics.py':'c0eaf47627b31793b3c90d875ce74761ae9c98e749fc437a422e73c2da66a947'}
PATCHED_UI_SHA='2ad57b62514cd0cc45056c34d5c30a3df0240d800394701f408b02f212be4ccf'
RUN='d24b61ed8f7c9a03';PACKAGE='org.droidloom.qa.galleryrotation.r12.n'+RUN
GALLERY='com.android.gallery3d';TASK=1005
ALBUM_URI='content://media/external/images/media?bucketId=-1681480384'
REPLACEMENTS=(
    (r"r'(?=^\s*\* Hist #\d+: ActivityRecord\{)'",r"r'(?=^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{)'"),
    (r"r'^\s*\* Hist #\d+: ActivityRecord\{[^\n]*\bu0 '",r"r'^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{[^\n]*\bu0 '"))

def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def load(path,pin,patch=False):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'SOURCE_PIN_CHANGED:'+Path(path).name)
    if patch:
        text=raw.decode()
        for old,new in REPLACEMENTS:
            need(text.count(old)==1,'TWO_EXACT_HIST_REPLACEMENTS_REQUIRED');text=text.replace(old,new)
        raw=text.encode();need(sha(raw)==PATCHED_UI_SHA,'PATCHED_UI_PIN_CHANGED')
    module=types.ModuleType('cleanup_'+Path(path).stem);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module

def source_scope(tx):
    old=json.loads(tx.read_regular(SOURCE/'result.json',FAILED_SHA,32768))
    seen=json.loads(tx.read_regular(READONLY,READONLY_SHA,65536))
    need(old['state']=='FAILED' and old['error']=='RuntimeError:EXACT_TOP_GALLERY_ACTIVITY_RECORD_REQUIRED'
        and old['run']==RUN and old['temporary_package']==PACKAGE and old['installed_identity']['uid']==10197
        and old['normal_closed_tasks']==[] and set(old['owned_tasks'])=={str(TASK)}
        and old['native_launches']==1 and old['rotation_input_calls']==0 and old['instrument_calls']==['seed'],
        'ORIGINAL_GALLERY03_FAILURE_SCOPE_CHANGED')
    need(old['native_pending']=={'open-owned-album-1':{'input_acknowledged':True,'kind':'tap',
        'post_capture_outcome_unknown':True}} and old['client_pending']=='open-owned-album-1'
        and all(old[k] is None for k in ('helper_pending','rotation_pending','album_pending','close_pending','directory_pending'))
        and old['install_pending'] is False and old['uninstall_pending'] is False
        and old['cleanup']['stage_cleanup']['staged_apk_removed'] is True,'ORIGINAL_PENDING_OR_STAGE_SCOPE')
    need(seen['state']=='FAILED' and seen['error']=='RuntimeError:RETAINED_STATE_CHANGED_DURING_READ_ONLY_RECONCILIATION'
        and seen['source_result_sha256']==FAILED_SHA and len(seen['rounds'])==2
        and seen['explicit_read_only_android_queries']==22 and seen['provider_sql_read_queries']==10
        and seen['UI_actions']==seen['provider_package_or_physical_mutations']==seen['task_removals']==0
        and 'guard_after' not in seen,'EXACT_FAILED_READONLY_RECEIPT_REQUIRED')
    a,b=seen['rounds']
    equal=('helper_identity','gallery_identity','private_state','provider','media','directory_rows',
           'fuse_parent_birth','backing_parent_birth','backing_folder_birth')
    need(all(a[k]==b[k] for k in equal),'ACTUAL_TWO_ROUND_IDENTITY_OR_MEDIA_CHANGED')
    ra=dict(a['route']);rb=dict(b['route']);left=ra.pop('actual_activity_block');right=rb.pop('actual_activity_block')
    need(ra==rb,'ACTUAL_ROUTE_IDENTITY_CHANGED')
    for before,after in (('lastLaunchTime=-30m28s294ms','lastLaunchTime=-30m29s49ms'),
                         ('lastVisibleTime=-19m6s86ms','lastVisibleTime=-19m6s841ms')):
        need(left.count(before)==1,'ACTUAL_DIAGNOSTIC_DURATION_NOT_UNIQUE');left=left.replace(before,after)
    need(left==right,'UNREVIEWED_ACTIVITY_BLOCK_CHANGE')
    need(b['helper_identity']==old['installed_identity'] and b['gallery_identity']==old['gallery_before']
        and b['lease_expired'] is True and b['fixture_age_elapsed_ms']==1834760,
        'EXACT_EXPIRED_ORIGINAL_FIXTURE_REQUIRED')
    need({k:v['_id'] for k,v in b['directory_rows'].items()}=={'control':97,'copy':99}
        and {k:v['metadata']['_id'] for k,v in b['media'].items()}=={'control':98,'copy':100},
        'FOUR_EXACT_OWNED_MEDIA_IDS_REQUIRED')
    saved={}
    for name,pin in seen['saved_record_pins'].items():
        need(name in ('004-original-media-before.json','015-owned-two-images-seeded-namespace.json',
                     '019-owned-two-images-seeded.json'),'UNEXPECTED_SAVED_PROOF_PATH')
        saved[name]=json.loads(tx.read_regular(SOURCE/'ui'/name,pin['sha256'],131072))
    return old,seen,b,saved

def private(session):
    raw,metadata=session.target.read_file('/data/user/0/'+PACKAGE+'/shared_prefs/owned-rotation-'+RUN+'.xml',
                                          65536,single_link=True)
    root=ET.fromstring(raw);need(root.tag=='map','PRIVATE_RECORD_SCHEMA');values={}
    for item in root:
        key=item.get('name');need(key and key not in values,'PRIVATE_RECORD_DUPLICATE')
        if item.tag=='string':value=item.text or ''
        elif item.tag in ('int','long'):value=int(item.get('value'))
        else:raise RuntimeError('PRIVATE_RECORD_TYPE')
        values[key]=value
    need(values.get('run')==RUN,'PRIVATE_RECORD_RUN_CHANGED')
    return {'values':values,'raw_sha256':sha(raw),'bytes':len(raw),'file_metadata':metadata}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'INERT','normal_close_task':1005,'helper_uid':10197,
            'image_ids':[100,98],'empty_directory_ids':[99,97],'Open_replay':False,'rotation':False}));return 0
    tx=load(TRANSPORT,TRANSPORT_SHA)
    need(os.geteuid()==0 and not os.path.lexists(OUT),'NEW_CLEANUP_OUTPUT_REQUIRED')
    old,seen,bound,saved=source_scope(tx)
    ui_mod=load(TOOLS/'rotation_ui.py',PINS['rotation_ui.py'],True)
    pkg_mod=load(TOOLS/'rotation_package.py',PINS['rotation_package.py'])
    media_mod=load(TOOLS/'owned_media.py',PINS['owned_media.py'])
    diag=load(TOOLS/'bounded_diagnostics.py',PINS['bounded_diagnostics.py'])
    os.umask(0o077);OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
    (OUT/'records').mkdir(mode=0o700)
    result={'schema':'gallery03-new-exact-expired-fixture-cleanup-v1','state':'FAILED','started_utc':stamp(),
        'original_failed_result_sha256':FAILED_SHA,'original_readonly_result_sha256':READONLY_SHA,
        'independent_saved_review_sha256':SAVED_REVIEW_SHA,'original_failed_and_unknown_unchanged':True,
        'old_lease_expired':True,'lease_extended':False,'Open_replayed':False,'rotation_input_calls':0,
        'UI_touch_inputs':0,'helper_invocations':0,'task_remove_calls':0,'normal_closed_tasks':[],
        'image_delete_calls':0,'deleted_image_ids':[],'uninstall_calls':0,'close_pending':None,'pending_effect':None,
        'outcome_unknown':False,'cleanup_verified':False,'App_business_or_UI_delete_credit':False,
        'whole_app_production_ready':False}
    sequence=0;ui=media=package=None;effects_started=False
    def record(label,value):
        nonlocal sequence
        sequence+=1;tx.write_new(OUT/'records'/('%03d-'%sequence+label+'.json'),value)
    def expire(*unused):raise TimeoutError('NEW_EXACT_CLEANUP_DEADLINE_NO_REPLAY')
    prior_signal=signal.signal(signal.SIGALRM,expire);signal.alarm(180)
    try:
        with tx.ui_lock(),tx.CameraSession(OUT/'commands') as session:
            result['guard_before']=session.guard();need(result['guard_before']==old['guard_after']==seen['guard_before'],
                'FIXED_MAIN_CHANGED')
            ui=ui_mod.Adapter(session,tx,OUT/'records');ui.record=record
            media=media_mod.OwnedMedia(session,record)
            package=pkg_mod.PackageFixture(session,tx,ui,result);package.installed=old['installed_identity']
            original_android=session.android;activity_dump={}
            def audited_android(argv,timeout=20):
                if argv==['/system/bin/pm','uninstall',PACKAGE]:
                    need(result['uninstall_calls']==0,'UNINSTALL_MUST_NOT_REPEAT');result['uninstall_calls']+=1
                value=original_android(argv,timeout)
                if argv==['/system/bin/dumpsys','activity','activities',GALLERY]:activity_dump['raw']=value.decode()
                return value
            session.android=audited_android
            def home_preserved(roots):
                need(roots.get(1)=={'display':0,'user':0,'freeform':False,'children':[{
                    'id':851,'component':'com.android.droidloom.home/com.android.droidloom.home.HomeActivity','user':0}]},
                    'ORIGINAL_HOME_TASK_COMPONENT_OR_USER_CHANGED')
            def identity():
                helper=pkg_mod.identity(session,PACKAGE,pkg_mod.APK_SHA,10197)
                need(helper==old['installed_identity'],'EXACT_HELPER_IDENTITY_CHANGED')
                gallery=pkg_mod.identity(session,GALLERY,old['gallery_before']['apk_sha256'],10064,40030)
                gallery['permissions']=diag.permissions(session,record,'gallery-permissions')[GALLERY]
                need(gallery==old['gallery_before'],'GALLERY_IDENTITY_OR_PERMISSIONS_CHANGED')
                return helper,gallery
            def idle():
                need(result['close_pending'] is None and result['pending_effect'] is None
                    and media.directory_pending is None and not package.install_pending and not package.uninstall_pending
                    and not ui.pending and not ui.owned,'UNRESOLVED_EFFECT_OR_TASK_NO_NEXT_MUTATION')
                roots,tasks=ui.stacks('only-original-home-before-cleanup')
                need(tasks=={851},'ONLY_ORIGINAL_HOME_REQUIRED');home_preserved(roots)
                session.guard()
            try:
                result['helper_before'],result['gallery_before']=identity()
                need(private(session)==bound['private_state'],'PRIVATE_PHASE_OR_BYTES_CHANGED')
                stage='/data/local/tmp/pocket4-owned-galleryrotation-'+RUN
                need(not session.target.exists(stage),'ORIGINAL_STAGED_INPUT_REAPPEARED')
                media.media=old['instrumentations'][0]['media'];media.baseline=bound['media']
                media.directory_rows=dict(bound['directory_rows'])
                rows=saved['004-original-media-before.json']['rows']
                media.before={'rows':len(rows),'sha256':sha(json.dumps(rows,sort_keys=True,separators=(',',':')).encode())}
                media.parent=session.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                media.parent_birth=media_mod.birth(os.fstat(media.parent))
                media.backing_parent=session.target.open_root('/data/media/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                media.backing_parent_birth=media_mod.birth(os.fstat(media.backing_parent))
                need(media.parent_birth==bound['fuse_parent_birth'] and media.backing_parent_birth==bound['backing_parent_birth'],
                    'ORIGINAL_DCIM_PARENT_IDENTITIES_CHANGED')
                result['provider_before']=media.provider_pin('provider-before')
                need(media.namespace('complete-original-namespace')==saved['015-owned-two-images-seeded-namespace.json']['rows'],
                    'FULL_ORIGINAL_FOUR_ROW_NAMESPACE_CHANGED')
                result['media_before']=media.verify('unchanged-images-before-owned-close',False)
                need(media.backing_folder_birth==bound['backing_folder_birth'],'ORIGINAL_BACKING_DIRECTORIES_CHANGED')
                for turn in ('first','last'):
                    ui.baseline={851};ui.owned={TASK:old['owned_tasks'][str(TASK)]}
                    ui.pending={k:dict(v) for k,v in old['native_pending'].items()}
                    ui.allow_new={'source':'open-owned-album-1','component':(GALLERY,ui_mod.FILES)}
                    route={}
                    def route_record(label,value):
                        record(turn+'-'+label,value)
                        if label in ('album-route-before-admission','album-route-admitted'):
                            home_preserved(ui_mod.parse_stacks(value['raw'])[0])
                        if label=='actual-owned-album-route':route.update(value)
                    ui.record=route_record
                    need(ui.bind_gallery_route('open-owned-album-1',ALBUM_URI,10197)==TASK,'EXACT_OWNED_ROUTE_TASK')
                    keys=('task','caller_uid','caller_package','component','album_uri','new_task',
                          'actual_stack_component','foreground')
                    # JSON records store tuples as arrays; compare their canonical JSON values.
                    need(json.loads(json.dumps({k:route[k] for k in keys}))=={k:bound['route'][k] for k in keys},
                        'FRESH_OWNED_ROUTE_IDENTITY_CHANGED')
                    block=route['actual_activity_block']
                    need(re.search(r'^[ \t]*\* Hist[ \t]+#1: ActivityRecord\{24212890 u0 '
                        r'com\.android\.gallery3d/\.app\.GalleryActivity t1005\}',block)
                        and re.search(r'^[ \t]*state=RESUMED finishing=false[ \t]*$',block,re.M),
                        'ORIGINAL_RESUMED_GALLERY_RECORD_REQUIRED')
                    headers=re.findall(r'^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{([^\n]+)\}',
                                       activity_dump['raw'],re.M)
                    need([h for h in headers if h.endswith(' t1005')]==[
                        '24212890 u0 com.android.gallery3d/.app.GalleryActivity t1005',
                        '243553609 u0 '+PACKAGE+'/.RotationActivity t1005'],
                        'ORIGINAL_TWO_ACTIVITY_TOKENS_REQUIRED')
                    tops=re.findall(r'^[ \t]*topResumedActivity=ActivityRecord\{([^\n]+)\}',
                                    activity_dump['raw'],re.M)
                    need(tops.count('24212890 u0 com.android.gallery3d/.app.GalleryActivity t1005')==1,
                        'ORIGINAL_GALLERY_TOKEN_MUST_BE_TOP_RESUMED')
                ui.record=record
                need(private(session)==bound['private_state'] and identity()[0]==old['installed_identity'],
                    'HELPER_CHANGED_BEFORE_NORMAL_OWNED_CLOSE')
                session.guard()
                record('independent-current-route-effect-reconciled',{'original_result_sha256':FAILED_SHA,
                    'readonly_result_sha256':READONLY_SHA,'original_native_pending':old['native_pending'],
                    'original_client_pending':old['client_pending'],'actual_route':route,
                    'original_receipts_rewritten':False,'Open_replayed':False,'business_credit':False})
                ui.pending.clear();ui.allow_new=None
                result['close_pending']='normal-remove-owned-task1005';result['outcome_unknown']=True
                record('normal-owned-close-intent',{'task':TASK,'actual_route':route,'automatic_retry':False})
                effects_started=True;ui.close_all()
                need(ui.closed==[TASK] and ui.removals==1 and not ui.owned and not ui.pending,'ONE_NORMAL_OWNED_CLOSE_REQUIRED')
                result.update(close_pending=None,outcome_unknown=False,task_remove_calls=1,normal_closed_tasks=[TASK])
                idle();media.verify('unchanged-images-after-owned-close',False)
                need(private(session)==bound['private_state'],'PRIVATE_PHASE_CHANGED_AFTER_CLOSE')
                live_rows=media.namespace('four-exact-rows-before-image-cleanup')
                for role,identity_id in (('copy',100),('control',98)):
                    idle();expected=bound['media'][role]['metadata']
                    need(expected['_id']==identity_id and expected in live_rows,'ORIGINAL_IMAGE_TUPLE_REQUIRED')
                    need(media.file(role)==bound['media'][role]['file'],'EXACT_ORIGINAL_IMAGE_BYTES_OR_IDENTITY_CHANGED')
                    need(private(session)==bound['private_state'],'PRIVATE_PHASE_CHANGED_BEFORE_IMAGE_DELETE')
                    where=media_mod.exact_row_predicate(expected)
                    uri='content://media/external_primary/file/'+str(identity_id)
                    query=['/system/bin/content','query','--user','0','--uri',uri,'--projection','_id','--where',where]
                    text=session.android(query,25).decode();record('exact-image-provider-query',{'role':role,'stdout':text,'where':where})
                    need(re.fullmatch(r'Row: 0 _id='+str(identity_id)+r'[ \t\r\n]*',text),'EXACT_IMAGE_PROVIDER_QUERY_REQUIRED')
                    need(media.namespace('immediate-image-namespace')==live_rows,'MEDIA_NAMESPACE_CHANGED_BEFORE_DELETE')
                    back=os.open(media_mod.NAMES[role],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=media.backing_held[role])
                    try:
                        stat_before=os.fstat(back)
                        need(media_mod.birth(stat_before)==bound['media'][role]['file']['backing_birth'] and stat_before.st_nlink==1,
                            'EXACT_BACKING_IMAGE_INODE_REQUIRED')
                        session.guard();result['pending_effect']='delete-exact-image-'+str(identity_id)
                        result['outcome_unknown']=True
                        argv=['/system/bin/content','delete','--user','0','--uri',uri,'--where',where]
                        record('exact-image-delete-intent',{'role':role,'id':identity_id,'argv':argv,
                            'full_original_row':expected,'automatic_retry':False,'App_UI_delete_credit':False})
                        result['image_delete_calls']+=1;text=session.android(argv,25).decode()
                        record('exact-image-delete-ack',{'id':identity_id,'stdout':text})
                        need(text.strip()=='' or re.fullmatch(r'Deleted 1 rows\.?',text.strip()),'IMAGE_DELETE_ACK_UNKNOWN')
                        remaining=media.namespace('after-exact-image-delete')
                        expected_rows=[r for r in live_rows if r['_id']!=identity_id]
                        directory=bound['directory_rows'][role]
                        need(remaining in (expected_rows,[r for r in expected_rows if r!=directory]),
                            'UNEXPECTED_NAMESPACE_AFTER_IMAGE_DELETE')
                        need(all(r['_id']!=identity_id for r in remaining),'IMAGE_ROW_NOT_ABSENT')
                        after=os.fstat(back)
                        need(media_mod.birth(after)==media_mod.birth(stat_before) and after.st_nlink==0,
                            'ORIGINAL_BACKING_IMAGE_NOT_UNLINKED')
                        paths=[media_mod.folder(role)+'/'+media_mod.NAMES[role],
                               '/data/media/0/DCIM/'+media_mod.FOLDERS[role]+'/'+media_mod.NAMES[role]]
                        need(all(not session.target.exists(path) for path in paths),'OWNED_IMAGE_PATH_REAPPEARED')
                        media.empty_after_delete(role)
                        need(media.original('original-media-after-exact-image-delete')==media.before,'ORIGINAL_MEDIA_CHANGED')
                        record('exact-image-delete-verified',{'id':identity_id,'backing_birth':media_mod.birth(after),
                            'backing_nlink':0,'both_path_views_absent':True,'directory_empty_or_removed':True})
                        live_rows=remaining;result['deleted_image_ids'].append(identity_id)
                        result.update(pending_effect=None,outcome_unknown=False)
                    finally:os.close(back)
                idle();need(result['deleted_image_ids']==[100,98] and result['image_delete_calls']==2,'TWO_EXACT_IMAGE_DELETES_REQUIRED')
                result['media_cleanup']=media.cleanup_directories()
                idle();need(media.namespace('final-owned-namespace-before-uninstall')==[],'OWNED_NAMESPACE_NOT_EMPTY')
                need(private(session)==bound['private_state'],'PRIVATE_RECORD_CHANGED_BEFORE_EXACT_UNINSTALL')
                need(pkg_mod.identity(session,PACKAGE,pkg_mod.APK_SHA,10197)==old['installed_identity'],
                    'EXACT_HELPER_IDENTITY_BEFORE_UNINSTALL')
                result['package_cleanup']=package.uninstall(True)
                need(package.uninstall_pending is False and not session.target.exists(stage),'PACKAGE_OR_STAGED_INPUT_REMAINS')
                need(media.namespace('final-owned-namespace')==[] and media.original('original-media-final')==media.before,
                    'FINAL_NAMESPACE_OR_ORIGINAL_MEDIA_CHANGED')
                roots,tasks=ui.stacks('final-only-original-home');need(tasks=={851},'FINAL_TASK_SET_CHANGED')
                home_preserved(roots)
                result['gallery_after']=pkg_mod.identity(session,GALLERY,old['gallery_before']['apk_sha256'],10064,40030)
                result['gallery_after']['permissions']=diag.permissions(session,record,'final-gallery-permissions')[GALLERY]
                need(result['gallery_after']==result['gallery_before'],'GALLERY_STATE_CHANGED')
                need(media.provider_pin('provider-after')==result['provider_before'],'MEDIAPROVIDER_CHANGED')
                tx.read_regular(SOURCE/'result.json',FAILED_SHA,32768);tx.read_regular(READONLY,READONLY_SHA,65536)
                result['guard_after']=session.guard();need(result['guard_after']==result['guard_before'],'FINAL_MAIN_CHANGED')
                result.update(task_set_restored=True,original_media_preserved=True,original_history_bytes_unchanged=True)
            finally:media.close()
        result.update(state='EXACT_RECONCILED_GALLERY03_TASK_AND_FIXTURE_CLEANED',cleanup_verified=True,outcome_unknown=False)
    except BaseException as exc:
        result.update(state='FAILED',error=type(exc).__name__+':'+str(exc),cleanup_verified=False)
        result['outcome_unknown']=bool(effects_started or result['pending_effect'] or result['close_pending'])
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,prior_signal)
        if ui is not None:
            result.update(native_pending=ui.pending,owned_tasks=ui.owned,normal_closed_tasks=ui.closed,
                          task_remove_calls=ui.removals)
        if media is not None:
            result.update(directory_pending=media.directory_pending,directory_delete_calls=media.directory_delete_calls,
                          directory_rmdir_calls=media.directory_rmdir_calls)
        if package is not None:result.update(install_pending=package.install_pending,uninstall_pending=package.uninstall_pending)
    result['finished_utc']=stamp();raw=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
    need(len(raw)<=131072,'CLEANUP_RESULT_BOUND');packed=gzip.compress(raw,mtime=0)
    need(len(packed)<=65536,'CLEANUP_GZIP_BOUND')
    tx.write_new(OUT/'result.json',raw,alex_readable=True);tx.write_new(OUT/'result.json.gz',packed,alex_readable=True)
    print(json.dumps({'state':result['state'],'error':result.get('error'),'cleanup_verified':result['cleanup_verified'],
        'outcome_unknown':result['outcome_unknown'],'pending_effect':result['pending_effect'],
        'close_pending':result['close_pending'],'directory_pending':result.get('directory_pending'),
        'uninstall_pending':result.get('uninstall_pending'),'task_remove_calls':result['task_remove_calls'],
        'image_delete_calls':result['image_delete_calls'],'uninstall_calls':result['uninstall_calls'],
        'directory_delete_calls':result.get('directory_delete_calls'),
        'directory_rmdir_calls':result.get('directory_rmdir_calls'),'result_path':str(OUT/'result.json'),
        'result_bytes':len(raw),'result_sha256':sha(raw),'gzip_path':str(OUT/'result.json.gz'),
        'gzip_bytes':len(packed),'gzip_sha256':sha(packed)},sort_keys=True))
    return 0 if result['cleanup_verified'] else 1

if __name__=='__main__':raise SystemExit(main())
