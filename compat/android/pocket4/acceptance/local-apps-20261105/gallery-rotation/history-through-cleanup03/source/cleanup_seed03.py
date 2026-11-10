#!/usr/bin/python3 -I
"""Clean only remaining empty directory91/helper10194; never replay image92 delete."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,io,json,os,re,signal,stat,types,xml.etree.ElementTree as ET
from PIL import Image
OLD=Path('/home/alex/work/pocket4-gallery-rotation-flow-20261105-r12-01')
OLD_SHA='836a9aef54eb5ea0ac623ff30635e3cd0aca595ff130931cc332bf749109bd77'
READ=Path('/home/alex/work/pocket4-gallery-rotation-seed-state-20261105-r12-01/result.json')
READ_SHA='ac94c7e3cfd6583479f44af065af73700a01cfc82143b412689c39e9f5e640ee'
SEED_SHA='5d23a581acbac7fdf63c7a452b4bfb4fe6b26bc0af381eab51f64b8742e7f567'
OUT=Path('/home/alex/work/pocket4-gallery-rotation-seed-cleanup-20261105-r12-03')
FAILED_TWO=Path('/home/alex/work/pocket4-gallery-rotation-seed-cleanup-20261105-r12-02/result.json')
FAILED_TWO_SHA='1ed05eebfc606306a7f60b34980f288b98736985afde081c59a8a6f9116935c3'
RECOVERY=Path('/home/alex/work/pocket4-gallery-rotation-cleanup02-readonly-20261105-r12-01/result.json')
RECOVERY_SHA='f8d4bd06994e4d5652ecb1665d2482d85530f7b377017e73ed7a2e4ba4c21764'
NO_EFFECT=Path('/home/alex/work/pocket4-gallery-rotation-seed-cleanup-20261105-r12-01/result.json')
NO_EFFECT_SHA='234fa557fc4b724f48d2e18d236271db8728460c3665f6838ea8e0d9e4471386'
TOOLS=Path('/home/alex/work/pocket4-gallery-rotation-tools-20261105-r12-01')
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PINS={'rotation_package.py':'699fe5cea8da07d678d28564ca45d79e533a029a06ab3df624ffe11e910aa8f1',
      'owned_media.py':'c6dfe692706c756044abf1f82b38913d953657324a5816e2c10dab6d61a52813',
      'rotation_ui.py':'ac885a393ff6b3e6cc477bb9c0acf55284fe3e4c92474fb82571884d07d9b650',
      'bounded_diagnostics.py':'c0eaf47627b31793b3c90d875ce74761ae9c98e749fc437a422e73c2da66a947'}
RUN='d24b61ed8f7c9a03';PKG='org.droidloom.qa.galleryrotation.r12.n'+RUN
def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def birth(s):return {k:getattr(s,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')}
def load(path,pin):
    raw=path.read_bytes();need(sha(raw)==pin,'SOURCE_HASH_CHANGED')
    m=types.ModuleType(path.stem);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
def expired(*args):raise TimeoutError('CLEANUP_DEADLINE_NO_REPLAY')
def predicate(row):
    clauses=[]
    for k,v in row.items():
        need(re.fullmatch(r'[a-z_]+',k),'COLUMN_NAME')
        if v is None:clauses.append(k+' IS NULL')
        elif isinstance(v,int):clauses.append(k+'='+str(v))
        else:
            need(isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_./-]+',v),'EXACT_SQL_VALUE')
            clauses.append(k+"='"+v+"'")
    return ' AND '.join(clauses)

def private(s):
    path='/data/user/0/'+PKG+'/shared_prefs/owned-rotation-'+RUN+'.xml'
    raw,meta=s.target.read_file(path,65536,single_link=True);root=ET.fromstring(raw)
    need(root.tag=='map','PRIVATE_SCHEMA');values={}
    for item in root:
        key=item.get('name');need(key and key not in values,'PRIVATE_DUPLICATE')
        if item.tag=='string':value=item.text or ''
        elif item.tag in ('int','long'):value=int(item.get('value'))
        else:raise RuntimeError('PRIVATE_TYPE')
        values[key]=value
    need(values.get('run')==RUN,'PRIVATE_RUN')
    return {'sha256':sha(raw),'bytes':len(raw),'values':values}

def physical(s,media,role):
    path=media.folder(role);name=media.NAMES[role]
    try:fd=s.target.open_root(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    except FileNotFoundError:return {'directory_absent':True}
    try:
        born=birth(os.fstat(fd));fresh=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=fd)
        try:
            need(birth(os.fstat(fresh))==born,'FRESH_FOLDER_CHANGED');names=sorted(os.listdir(fresh))
        finally:os.close(fresh)
        need(len(names)<=2,'OWNED_FOLDER_ENTRY_BOUND');files={}
        for actual in names:
            need(actual==name or re.fullmatch(r'\.pending-[0-9]+-'+re.escape(name),actual),'UNRECOGNIZED_OWNED_FOLDER_ENTRY')
            f=os.open(actual,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            try:
                a=os.fstat(f);need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and 0<=a.st_size<=2097152,'OWNED_FILE_BOUND')
                chunks=[];left=a.st_size
                while left:
                    part=os.read(f,min(left,65536));need(part,'SHORT_OWNED_READ');chunks.append(part);left-=len(part)
                raw=b''.join(chunks);z=os.fstat(f)
                attrs=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
                need(all(getattr(a,k)==getattr(z,k) for k in attrs),'OWNED_FILE_CHANGED')
                item={'birth':birth(a),'nlink':a.st_nlink,'bytes':len(raw),'sha256':sha(raw),
                    'mtime_ns':str(a.st_mtime_ns),'ctime_ns':str(a.st_ctime_ns)}
                if raw:
                    with Image.open(io.BytesIO(raw)) as image:
                        item.update(format=image.format,width=image.width,height=image.height,
                            raw_RGB_sha256=sha(image.convert('RGB').tobytes()),exif_orientation=int(image.getexif().get(274,0)))
                files[actual]=item
            finally:os.close(f)
        again=s.target.open_root(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:need(birth(os.fstat(again))==born==birth(os.fstat(fd)),'OWNED_FOLDER_CHANGED')
        finally:os.close(again)
        return {'directory_absent':False,'birth':born,'names':names,'files':files}
    finally:os.close(fd)

def execute():
    need(os.geteuid()==0 and OUT.parent.resolve()==OUT.parent,'ROOT_FIXED_PARENT_REQUIRED')
    tx=load(TX,TX_SHA);pkg=load(TOOLS/'rotation_package.py',PINS['rotation_package.py'])
    media=load(TOOLS/'owned_media.py',PINS['owned_media.py']);ui=load(TOOLS/'rotation_ui.py',PINS['rotation_ui.py'])
    diag=load(TOOLS/'bounded_diagnostics.py',PINS['bounded_diagnostics.py'])
    old=json.loads(tx.read_regular(OLD/'result.json',OLD_SHA,65536));seen=json.loads(tx.read_regular(READ,READ_SHA,65536))
    no_effect=json.loads(tx.read_regular(NO_EFFECT,NO_EFFECT_SHA,16384))
    failed_two=json.loads(tx.read_regular(FAILED_TWO,FAILED_TWO_SHA,16384))
    recovery=json.loads(tx.read_regular(RECOVERY,RECOVERY_SHA,65536))
    need(failed_two['state']=='FAILED' and failed_two['pending_effect']=='delete-exact-pending-image92'
        and failed_two['outcome_unknown'] is True and failed_two['provider_delete_calls']==1
        and failed_two['rmdir_calls']==failed_two['uninstall_calls']==0,'ORIGINAL_ONE_DELETE_BOUNDARY_CHANGED')
    need(recovery['state']=='EXACT_CLEANUP02_CURRENT_STATE_READ_ONLY_VERIFIED'
        and recovery['original_cleanup02_sha256']==FAILED_TWO_SHA
        and recovery['tasks_before']==recovery['tasks_after']==[851]
        and recovery['guard_before']==recovery['guard_after']==failed_two['guard_before'],
        'ACTUAL_READONLY_RECONCILIATION_REQUIRED')
    commands=[x for x in recovery['saved_cleanup02']['commands'] if 'delete' in x.get('own_content_argv',[])]
    need(len(commands)==1 and 'content://media/external_primary/file/92' in commands[0]['own_content_argv']
        and commands[0]['rc']==0 and commands[0]['joined'] is True and commands[0]['timed_out'] is False
        and commands[0]['guard_after'] is True and commands[0]['stderr']['bytes']==0,'ONLY_OLD_JOINED_DELETE92')
    need(no_effect['state']=='FAILED' and no_effect['provider_delete_calls']==no_effect['uninstall_calls']==no_effect['rmdir_calls']==0
        and no_effect['pending_effect'] is None and no_effect['outcome_unknown'] is False,
        'PREVIOUS_CLEANUP_NOT_PROVEN_ZERO_EFFECT')
    paths=list((OLD/'ui').glob('*-helper-seed-response.json'));need(len(paths)==1,'ONE_SAVED_SEED_TERMINAL')
    reply=json.loads(tx.read_regular(paths[0],SEED_SHA,16384))['stdout'];lines=reply.splitlines()
    need(len(lines)==2 and lines[1]=='INSTRUMENTATION_CODE: 1'
        and lines[0].startswith('INSTRUMENTATION_RESULT: result_json='),'ORIGINAL_SEED_NOT_TERMINAL')
    seed=json.loads(lines[0].split('result_json=',1)[1]);state=seed['status']
    need(seed['operation']=='seed' and seed['run']==RUN and seed['package']==PKG and seed['uid']==10194
        and seed['ok'] is False and seed['error_type']=='IllegalStateException'
        and seed['error']=='OWNED_MEDIA_PATH_CHANGED','ORIGINAL_SEED_FAILURE_CHANGED')
    need(state['phase']=='SEED_PENDING' and state['pending']=='write-control' and state['gallery_launches']==0
        and state['insert_calls']==state['write_calls']==1 and state['publish_calls']==state['delete_calls']==0
        and state['control_uri']=='content://media/external_primary/images/media/92','EXACT_SEED_COUNTS_CHANGED')
    need(old['state']=='FAILED' and old['helper_pending']=='seed' and old['ui_actions']==old['native_launches']==0
        and old['native_pending']=={} and old['owned_tasks']=={} and old['rotation_pending'] is None
        and not old['install_pending'] and not old['uninstall_pending'],'ORIGINAL_FAILURE_BOUNDARY_CHANGED')
    need(seen['state']=='EXACT_RETAINED_STATE_READ_ONLY_VERIFIED' and seen['tasks_before']==seen['tasks_after']==[851]
        and seen['namespace_before']==seen['namespace_after'] and seen['private_before']==seen['private_after']
        and seen['physical']['copy']=={'directory_absent':True},'READONLY_RECONCILIATION_CHANGED')
    rows=seen['namespace_after'];need(len(rows)==2 and [r['_id'] for r in rows]==[91,92],'EXACT_TWO_ROWS')
    directory,image=rows
    need(directory['_data']==media.folder('control') and directory['owner_package_name'] is None
        and directory['media_type']==0 and directory['is_pending']==0 and image['owner_package_name']==PKG
        and image['parent']==91 and image['media_type']==1 and image['is_pending']==1,'OWNED_ROW_RELATION')
    filename=seen['physical']['control']['names'];need(len(filename)==1,'ONE_PENDING_PNG')
    filename=filename[0];need(filename=='.pending-1794515573-'+media.NAMES['control']
        and image['_data']==media.folder('control')+'/'+filename,'OBSERVED_PENDING_PATH_CHANGED')
    need(recovery['namespace_before']==recovery['namespace_after']==recovery['exact_ids_before']==recovery['exact_ids_after']==[directory]
        and recovery['helper_before']==recovery['helper_after']==old['installed_identity']
        and recovery['private_before']==recovery['private_after']==seen['private_after'],
        'EXACT_REMAINING_DIRECTORY_AND_HELPER_REQUIRED')
    for key in ('fuse_paths','backing_paths'):
        before=recovery[key+'_before'];after=recovery[key+'_after']
        need(before==after and after['roles']['control']['directory_absent'] is False
            and after['roles']['control']['entry_count']==0 and after['roles']['control']['unknown_entry_count']==0
            and all(v=={'absent':True} for v in after['roles']['control']['exact_entries'].values())
            and after['roles']['copy']=={'directory_absent':True},'BOTH_EMPTY_PHYSICAL_VIEWS_REQUIRED')
    need(recovery['fuse_paths_after']['roles']['control']['birth']==seen['physical']['control']['birth'],
        'ORIGINAL_EMPTY_DIRECTORY_BIRTH_REQUIRED')
    expected_file=seen['physical']['control']['files'][filename]
    need(expected_file['sha256']==media.PNG_SHA and expected_file['bytes']==2416,'FIXED_PNG_BYTES')
    result={'schema':'gallery01-remaining-directory-helper-cleanup-v1','state':'FAILED','cleanup_verified':False,
        'started_utc':stamp(),'original_result_sha256':OLD_SHA,'readonly_result_sha256':READ_SHA,
        'previous_cleanup_zero_effect_sha256':NO_EFFECT_SHA,
        'previous_cleanup02_failed_sha256':FAILED_TWO_SHA,'readonly_recovery_sha256':RECOVERY_SHA,
        'old_delete92_replayed':False,'image92_delete_calls':0,
        'original_cleanup02_pending_preserved':'delete-exact-pending-image92',
        'directory_empty_guard':'Exact held inode empty rmdir; row deletion only after that original directory is physically absent',
        'cross_row_SQL_atomicity_claimed':False,
        'original_failed_receipt_preserved':True,'original_helper_pending_preserved':'seed',
        'UI_actions':0,'seed_replayed':False,'published_images':0,'App_business_or_UI_delete_credit':False,
        'provider_delete_calls':0,'uninstall_calls':0,'rmdir_calls':0,'pending_effect':None,'outcome_unknown':False}
    parent=folder_fd=backing_parent=backing_folder_fd=None;previous=signal.signal(signal.SIGALRM,expired);sequence=0
    def record(label,value):
        nonlocal sequence
        sequence+=1;tx.write_new(OUT/('%03d-'%sequence+label+'.json'),value)
    def tasks(s,label):
        raw=s.android(['/system/bin/cmd','activity','stack','list'],15).decode();roots,ids=ui.parse_stacks(raw)
        need(ids=={851},'ONLY_ORIGINAL_HOME_REQUIRED');record(label,{'raw':raw,'tasks':sorted(ids)});return sorted(ids)
    def queried(s,label,uri,where,identity):
        argv=['/system/bin/content','query','--user','0','--uri',uri,'--projection','_id','--where',where]
        raw=s.android(argv,20).decode();record(label,{'argv':argv,'stdout':raw})
        need(re.fullmatch(r'Row: 0 _id='+str(identity)+r'\s*',raw) is not None,'EXACT_PROVIDER_QUERY_REQUIRED:'+label)
    def dispatch_delete(s,label,uri,where):
        need(result['pending_effect'] is None,'PENDING_EFFECT_NO_REPLAY')
        argv=['/system/bin/content','delete','--user','0','--uri',uri,'--where',where]
        result['pending_effect']=label;result['outcome_unknown']=True
        record(label+'-intent',{'argv':argv,'automatic_retry':False,'App_UI_delete_credit':False})
        result['provider_delete_calls']+=1;raw=s.android(argv,25).decode();record(label+'-ack',{'stdout':raw})
        need(not raw.strip() or re.fullmatch(r'Deleted 1 rows\.?',raw.strip()),'PROVIDER_DELETE_RESPONSE_UNKNOWN')
    try:
        with tx.ui_lock():
            OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
            signal.setitimer(signal.ITIMER_REAL,180)
            with tx.CameraSession(OUT/'commands') as s:
                result['guard_before']=s.guard();need(result['guard_before']==old['guard_before']==seen['guard_before']==recovery['guard_after'],'MAIN_CHANGED')
                need(pkg.identity(s,PKG,pkg.APK_SHA,10194)==old['installed_identity']==seen['helper_after'],'HELPER_IDENTITY_CHANGED')
                need(private(s)==seen['private_after'],'PRIVATE_PENDING_OR_SOURCE_CHANGED')
                result['tasks_before']=tasks(s,'tasks-before')
                owned=media.OwnedMedia(s,record)
                need(owned.namespace('namespace-before')==[directory],'OWNED_NAMESPACE_CHANGED')
                need(owned.query('exact-old-image92-absent','SELECT _id FROM files WHERE _id=92')==[],'OLD_IMAGE92_PRESENT_NO_REPLAY')
                baseline=seen['original_media_before'];need(owned.original('original-before')==baseline,'ORIGINAL_MEDIA_CHANGED')
                need(physical(s,media,'control')=={'directory_absent':False,'birth':seen['physical']['control']['birth'],'names':[],'files':{}}
                    and physical(s,media,'copy')=={'directory_absent':True},'EXPECTED_EMPTY_PHYSICAL_DIRECTORY_CHANGED')
                parent=s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                parent_birth=birth(os.fstat(parent));need(parent_birth==recovery['fuse_paths_after']['parent'],'FUSE_PARENT_CHANGED')
                backing_parent=s.target.open_root('/data/media/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                backing_parent_birth=birth(os.fstat(backing_parent))
                need(backing_parent_birth==recovery['backing_paths_after']['parent'],'BACKING_PARENT_CHANGED')
                folder_fd=os.open(media.FOLDERS['control'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
                need(birth(os.fstat(folder_fd))==seen['physical']['control']['birth'],'HELD_FOLDER_CHANGED')
                backing_folder_fd=os.open(media.FOLDERS['control'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=backing_parent)
                need(birth(os.fstat(backing_folder_fd))==recovery['backing_paths_after']['roles']['control']['birth'],
                    'HELD_BACKING_DIRECTORY_CHANGED')
                directory_where=predicate(directory)
                children="(parent=91 OR _data GLOB '"+media.folder('control')+"/*')"
                queried(s,'remaining-directory-tuple-preflight','content://media/external_primary/file/91',directory_where,91)
                need(owned.query('remaining-zero-children','SELECT _id FROM files WHERE '+children+' ORDER BY _id')==[],
                    'UNOWNED_CHILD_INDEX')
                need(private(s)==seen['private_after'] and owned.namespace('immediate-remaining-namespace')==[directory],
                    'REMAINING_STATE_CHANGED')
                provider_path='/apex/com.android.mediaprovider/priv-app/MediaProvider@CP2A.260605.016/MediaProvider.apk'
                provider,_=s.target.read_file(provider_path,16777216,single_link=True)
                need(len(provider)==15447727 and sha(provider)=='b98258475c14043fe1f7e0d5a61caa13aa22dea426ffc589e83012f0377ce0f4',
                    'REVIEWED_PROVIDER_APK_CHANGED')
                result['reviewed_provider_apk_sha256']=sha(provider)
                result['image92_absence_independently_reconciled']=True
                try:current=os.stat(media.FOLDERS['control'],dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:raise RuntimeError('REMAINING_DIRECTORY_DISAPPEARED_BEFORE_OWN_RMDIR')
                else:
                    need(birth(current)==birth(os.fstat(folder_fd))==seen['physical']['control']['birth'],'DIRECTORY_REPLACED')
                    fresh_parent=s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:need(birth(os.fstat(fresh_parent))==birth(os.fstat(parent))==parent_birth,'PARENT_REPLACED')
                    finally:os.close(fresh_parent)
                    fresh=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=folder_fd)
                    try:need(os.listdir(fresh)==[],'OWNED_DIRECTORY_NO_LONGER_EMPTY')
                    finally:os.close(fresh)
                    fresh_backing_parent=s.target.open_root('/data/media/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:need(birth(os.fstat(fresh_backing_parent))==birth(os.fstat(backing_parent))==backing_parent_birth,'BACKING_PARENT_REPLACED')
                    finally:os.close(fresh_backing_parent)
                    need(birth(os.stat(media.FOLDERS['control'],dir_fd=backing_parent,follow_symlinks=False))
                        ==birth(os.fstat(backing_folder_fd))==recovery['backing_paths_after']['roles']['control']['birth'],
                        'NAMED_BACKING_DIRECTORY_REPLACED')
                    fresh=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=backing_folder_fd)
                    try:need(os.listdir(fresh)==[],'BACKING_DIRECTORY_NO_LONGER_EMPTY')
                    finally:os.close(fresh)
                    s.guard();result.update(pending_effect='rmdir-exact-control',outcome_unknown=True,rmdir_calls=1)
                    record('rmdir-exact-control-intent',{'birth':birth(current),'automatic_retry':False})
                    os.rmdir(media.FOLDERS['control'],dir_fd=parent)
                need(os.fstat(backing_folder_fd).st_nlink==0,'BACKING_DIRECTORY_MOVED_NOT_REMOVED')
                for name in media.FOLDERS.values():
                    try:os.stat(name,dir_fd=parent,follow_symlinks=False)
                    except FileNotFoundError:continue
                    raise RuntimeError('OWNED_DIRECTORY_STILL_PRESENT')
                for name in media.FOLDERS.values():
                    try:os.stat(name,dir_fd=backing_parent,follow_symlinks=False)
                    except FileNotFoundError:continue
                    raise RuntimeError('OWNED_BACKING_DIRECTORY_STILL_PRESENT')
                result['backing_deleted_directory_nlink']=os.fstat(backing_folder_fd).st_nlink
                result.update(pending_effect=None,outcome_unknown=False,original_physical_directory_removed_empty=True)
                after=owned.namespace('after-exact-empty-rmdir')
                need(after in ([],[directory]),'NAMESPACE_CHANGED_AFTER_RMDIR')
                if after:
                    queried(s,'absent-physical-directory-row-preflight','content://media/external_primary/file/91',directory_where,91)
                    need(owned.query('no-child-after-rmdir','SELECT _id FROM files WHERE '+children+' ORDER BY _id')==[],
                        'DIRECTORY_CHILD_INDEX_REAPPEARED')
                    fresh_parent=s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:need(birth(os.fstat(fresh_parent))==birth(os.fstat(parent))==parent_birth,'PARENT_REPLACED_BEFORE_INDEX_DELETE')
                    finally:os.close(fresh_parent)
                    fresh_backing_parent=s.target.open_root('/data/media/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    try:need(birth(os.fstat(fresh_backing_parent))==birth(os.fstat(backing_parent))==backing_parent_birth,'BACKING_PARENT_REPLACED_BEFORE_INDEX_DELETE')
                    finally:os.close(fresh_backing_parent)
                    need(os.fstat(backing_folder_fd).st_nlink==0,'ORIGINAL_BACKING_DIRECTORY_NOT_UNLINKED')
                    try:os.stat(media.FOLDERS['control'],dir_fd=parent,follow_symlinks=False)
                    except FileNotFoundError:pass
                    else:raise RuntimeError('DIRECTORY_PATH_RECREATED_KEEP_INDEX')
                    try:os.stat(media.FOLDERS['control'],dir_fd=backing_parent,follow_symlinks=False)
                    except FileNotFoundError:pass
                    else:raise RuntimeError('BACKING_DIRECTORY_PATH_RECREATED_KEEP_INDEX')
                    need(owned.namespace('immediate-empty-index-tuple')==[directory]
                        and owned.query('immediate-zero-child-index','SELECT _id FROM files WHERE '+children+' ORDER BY _id')==[],
                        'FINAL_DIRECTORY_TUPLE_OR_CHILDREN_CHANGED')
                    s.guard();dispatch_delete(s,'delete-exact-absent-directory-index91','content://media/external_primary/file/91',directory_where)
                    need(owned.namespace('after-directory-index-delete')==[],'DIRECTORY_INDEX_NOT_ABSENT')
                    result.update(pending_effect=None,outcome_unknown=False)
                result['physical_and_indexed_namespace_absent']=True
                need(private(s)==seen['private_after'] and pkg.identity(s,PKG,pkg.APK_SHA,10194)==old['installed_identity'],
                    'EXACT_HELPER_CHANGED_BEFORE_UNINSTALL')
                need(owned.namespace('before-uninstall')==[] and owned.original('original-preuninstall')==baseline,'MEDIA_PREUNINSTALL_CHANGED')
                result.update(pending_effect='uninstall-exact-helper10194',outcome_unknown=True,uninstall_calls=1)
                record('uninstall-exact-helper-intent',{'identity':old['installed_identity'],'automatic_retry':False})
                raw=s.android(['/system/bin/pm','uninstall',PKG],60).decode();record('uninstall-ack',{'stdout':raw})
                need(raw.strip()=='Success','UNINSTALL_RESPONSE_UNKNOWN');pkg.absent(s)
                for prefix in ('/data/user/0/','/data/user_de/0/'):
                    try:fd=s.target.open_root(prefix+PKG,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                    except FileNotFoundError:continue
                    else:os.close(fd);raise RuntimeError('HELPER_DATA_REMAINS')
                result.update(pending_effect=None,outcome_unknown=False,helper_package_and_CE_DE_absent=True)
                need(owned.namespace('final-namespace')==[] and owned.original('original-final')==baseline,'FINAL_MEDIA_CHANGED')
                result['tasks_after']=tasks(s,'tasks-after')
                current=pkg.identity(s,'com.android.gallery3d',old['gallery_before']['apk_sha256'],10064,40030)
                current['permissions']=diag.permissions(s,record,'final-gallery-permissions')['com.android.gallery3d']
                need(current==old['gallery_before'],'GALLERY_IDENTITY_OR_PERMISSION_CHANGED');result['gallery_after']=current
                provider_after,_=s.target.read_file(provider_path,16777216,single_link=True)
                need(provider_after==provider,'REVIEWED_PROVIDER_APK_CHANGED_AFTER')
                result['guard_after']=s.guard();s.caller_status('cleanup-final')
                need(result['guard_after']==result['guard_before'],'FINAL_MAIN_CHANGED')
                result.update(original_media_preserved=True,task_set_restored=True)
        result.update(state='EXACT_REMAINING_DIRECTORY_AND_HELPER_CLEANED',cleanup_verified=True)
    except BaseException as e:
        result.update(state='FAILED',cleanup_verified=False,error=type(e).__name__+':'+str(e))
        result['outcome_unknown']=bool(result['pending_effect'] is not None or result['provider_delete_calls']
            or result['uninstall_calls'] or result['rmdir_calls'])
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        for fd in (backing_folder_fd,folder_fd,backing_parent,parent):
            if fd is not None:
                try:os.close(fd)
                except BaseException as e:result.update(state='FAILED',cleanup_verified=False,local_close_error=str(e))
    result['finished_utc']=stamp()
    if OUT.is_dir():tx.write_new(OUT/'result.json',result,alex_readable=True)
    print(json.dumps(result,indent=2,sort_keys=True));return 0 if result['cleanup_verified'] else 1
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true')
    if ap.parse_args().execute:raise SystemExit(execute())
    print(json.dumps({'state':'INERT','UI_actions':0,'seed_replayed':False,'scope':'remaining empty directory91/helper10194 only; no image92 delete replay'}))
