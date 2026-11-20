"""Bind fresh Main data directories to the real stopped predeployment image receipt.
No mount, namespace entry, Android command, mutation, App content read or UID signal.
Directory mtimes and package-list byte changes are observations, not identity.
"""
import hashlib,json,os,re,select,stat,time,types,uuid
from pathlib import Path,PurePosixPath
FINAL=Path('/home/alex/work/pocket4-android-final')
PREIMAGE={'path':str(FINAL/'qualification/business-data-predeployment-resume-20261107-r3/result.json'),
          'bytes':212950,'sha256':'afdbb6d7ac4bf3af0ae89ae64ed6cde00653142eecbf0698dc5e218840778042'}
DATA_IMAGE=Path('/var/lib/droidloom/users/1000/data/data.img')
OLD_CELL_SHA='f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
IMAGE_ID_KEYS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size')
META_KEYS=(*IMAGE_ID_KEYS,'st_mtime_ns','st_ctime_ns')
EPOCH_PATH=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main/framework_epoch.py')
EPOCH_SHA='ba4854fcc42def3fb37ac8add1e2b4382d24cb716e2d8181e84b286d5975c377'
READER_PATH=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main/held_runtime.py')
READER_SHA='6f0951391d95baa2e548826d3d7700b634ef89f1a6770d8a6d45b9e6eaaddd4e'
READER_BYTES=27507
USERNS_PATH=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main')/'main_user_namespace.py'
USERNS_SHA='88c66969a2fd312eca02064aa1d6c4213ec031df7c7592daedb34ae57b48fda0'
_userns_module=None

def userns_module():
    global _userns_module
    if _userns_module is None:
        _userns_module=load(USERNS_PATH,USERNS_SHA,'canonical_actual_main_user_namespace')
    return _userns_module


def need(value,code):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def parse(raw):
    def pairs(items):
        result={}
        for k,v in items:
            need(k not in result,'DUPLICATE_JSON_FIELD');result[k]=v
        return result
    def nonfinite(_):raise RuntimeError('NONFINITE_JSON_NUMBER')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)
def meta(fd):
    st=os.fstat(fd);return {key:getattr(st,key) for key in META_KEYS}
def read_pinned(ref,maximum=2*1024*1024):
    p=Path(ref['path']);need(p.is_absolute() and p.resolve()==p,'PINNED_PATH_SYMLINK_REFUSED')
    fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=meta(fd);need(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1 and 0<before['st_size']<=maximum,'PINNED_FILE_BOUND')
        raw=bytearray();deadline=time.monotonic()+8
        while True:
            need(time.monotonic()<deadline,'PINNED_FILE_READ_DEADLINE')
            part=os.read(fd,min(65536,maximum+1-len(raw)))
            if not part:break
            raw.extend(part);need(len(raw)<=maximum,'PINNED_FILE_GREW')
        need(meta(fd)==before and len(raw)==before['st_size'] and sha(raw)==ref['sha256'] and
             ('bytes' not in ref or ref['bytes']==len(raw)),'PINNED_FILE_CHANGED')
        return bytes(raw)
    finally:os.close(fd)
def load(path,pin,name):
    raw=read_pinned({'path':str(path),'sha256':pin},1024*1024)
    module=types.ModuleType(name);module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__);return module

def load_preimage():
    value=parse(read_pinned(PREIMAGE))
    need(value.get('schema')=='pocket4-business-data-predeployment-v3' and value.get('status')=='captured' and
         value.get('missing')==[] and value.get('errors')==[] and
         value.get('stable_image_and_metadata_double_observation') is True,'ACTUAL_COMPLETE_PREDEPLOYMENT_RECEIPT_REQUIRED')
    need(value['images_before']==value['images_after'] and value['loops_before']==value['loops_after']==[] and
         value['cell_before']==value['cell_after'] and value['cell_before']['sha256']==OLD_CELL_SHA,
         'PREDEPLOYMENT_IMAGE_OR_CELL_NOT_STABLE')
    need(value['data_root']==str(DATA_IMAGE.parent) and
         value['images_before']['data.img']['path']==str(DATA_IMAGE),'PREDEPLOYMENT_BACKING_CHANGED')
    for image in value['images_before'].values():
        need(image['journal_recovery_required'] is False and image['filesystem_state']&1,
             'PREDEPLOYMENT_FILESYSTEM_WAS_NOT_CLEAN')
    need(value['package_names']==sorted(value['targets'])==sorted(value['packages']) and
         len(value['targets'])==45,'EXACT_45_PREDEPLOYMENT_TARGETS_REQUIRED')
    for package,row in value['targets'].items():
        need(row['uid']==value['packages'][package] and row['user']==0,'PREDEPLOYMENT_UID_CHANGED')
        for path in ('/data/'+package,'/user_de/0/'+package):
            item=row['image_paths'][path]
            need(item['exists'] is True and item['stat']['type']=='directory' and item['stat']['uid']==row['uid'],
                 'PREDEPLOYMENT_DIRECTORY_FACT_MISSING')
    commands=sum(value['owned_host_commands'].values(),[])
    need(len(commands)==8 and all(row.get('retirement_proved') is True and
        row['lifecycle'].get('child_reaped') is True and row['lifecycle'].get('owned_tree_cleanup_complete') is True and
        row['lifecycle'].get('remaining_owned_children')==[] and row['subreaper'].get('final_children_empty') is True
        for row in commands),'PREDEPLOYMENT_HOST_COMMAND_RETIREMENT_INCOMPLETE')
    for reference in value['raw_sources'].values():read_pinned(reference)
    for key in ('retained_baseline','retained_qualification'):read_pinned(value['old_baseline_02'][key])
    need(all(row['same_inode_uid_gid'] is True for row in value['old_baseline_02']['comparison'].values()) and
         len(value['old_baseline_02']['comparison'])==8,'OLD_FOUR_APP_DIRECTORY_COMPARISON_CHANGED')
    return value

def parse_mountinfo(raw):
    need(type(raw) is bytes and len(raw)<=4*1024*1024,'MOUNTINFO_BOUND')
    def unescape(value):return re.sub(r'\\(040|011|012|134)',lambda m:chr(int(m.group(1),8)),value)
    result=[]
    for line in raw.decode('utf-8','strict').splitlines():
        f=line.split();need(len(f)>=10 and f.count('-')==1,'MOUNTINFO_SCHEMA')
        split=f.index('-');need(split>=6 and len(f)>=split+4,'MOUNTINFO_FIELDS')
        mountpoint,root=unescape(f[4]),unescape(f[3])
        for p in (mountpoint,root):
            need(p.startswith('/') and str(PurePosixPath(p))==p and '..' not in PurePosixPath(p).parts,'MOUNT_PATH_NONCANONICAL')
        need(re.fullmatch('[0-9]+:[0-9]+',f[2]),'MOUNT_DEVICE_REQUIRED')
        result.append({'mount_id':int(f[0]),'parent_mount_id':int(f[1]),'major_minor':f[2],
            'root':root,'mountpoint':mountpoint,'mount_options':f[5],'optional_fields':f[6:split],
            'filesystem':f[split+1],'source':unescape(f[split+2]),'super_options':f[split+3]})
    need(0<len(result)<=8192 and len({row['mount_id'] for row in result})==len(result) and
         all(type(row['mount_id']) is int and row['mount_id']>0 and row['parent_mount_id']>=0 for row in result),
         'UNIQUE_REAL_MOUNT_IDS_REQUIRED')
    return result

def effective_mount(rows,path):
    candidates=[row for row in rows if path==row['mountpoint'] or path.startswith(row['mountpoint'].rstrip('/')+'/')]
    need(candidates,'PATH_HAS_NO_MOUNT_EVIDENCE')
    longest=max(len(row['mountpoint']) for row in candidates)
    matches=[row for row in candidates if len(row['mountpoint'])==longest]
    need(len(matches)==1,'AMBIGUOUS_EFFECTIVE_MOUNT')
    row=matches[0]
    suffix=path[len(row['mountpoint']):] if row['mountpoint']!='/' else path
    image_path=str(PurePosixPath(row['root'])/suffix.lstrip('/'))
    need(image_path.startswith('/') and '..' not in PurePosixPath(image_path).parts,'IMAGE_PATH_ESCAPE')
    return row,image_path

def image_identity(metadata):
    return {key:metadata[key] for key in IMAGE_ID_KEYS}

def identity_projection(proof):
    """Normal App directory writes can change timestamps and package-list bytes."""
    return {'preimage':proof['preimage'],'filesystem_uuid':proof['filesystem_uuid'],
        'backing_image_identity':proof['backing_image_identity'],'live_device':proof['live_device'],
        'package_uids':proof['package_uids'],'main_user_namespace':proof['main_user_namespace'],
        'directories':{name:{key:row[key] for key in ('android_path','image_path','device','inode','uid','gid')}
                       for name,row in proof['directories'].items()}}

def validate_live(preimage,proof,main_mapping):
    need(proof.get('schema')=='pocket4-live-data-continuity-v2' and proof.get('preimage')==PREIMAGE,
         'NEW_LIVE_DATA_PROOF_REQUIRED')
    need(proof.get('main_user_namespace')==main_mapping,'DATA_PROOF_AND_ORIGINAL_MAIN_MAPPING_DIFFER')
    mapping=userns_module()
    # This pure validator compares evidence only. The caller validates the
    # mapping against the authenticated Main owner/epoch, while measure holds
    # the exact live namespace lease across the complete directory observation.
    mapping.validate_map(main_mapping['uid_map']);mapping.validate_map(main_mapping['gid_map'])
    before=preimage['images_before']['data.img']
    need(proof['filesystem_uuid']==before['filesystem_uuid'] and
         proof['backing_image_identity']==image_identity(before['file']) and
         all(type(v) is int and v>=0 for v in proof['backing_image_identity'].values()) and
         proof['backing_image_path']==str(DATA_IMAGE),'REAL_PREIMAGE_BACKING_REQUIRED')
    dev=proof['live_device'];need(type(dev['device']) is int and dev['device']>0 and
         str(os.major(dev['device']))+':'+str(os.minor(dev['device']))==dev['major_minor'] and
         re.fullmatch(r'loop[0-9]+',dev['loop_name']) and dev['backing_file']==str(DATA_IMAGE) and
         type(dev['offset']) is int and dev['offset']==0 and
         type(dev['sizelimit']) is int and dev['sizelimit']==0,
         'ACTUAL_LOOP_TO_IMAGE_MAPPING_REQUIRED')
    need(type(proof['package_uids']) is dict and proof['package_uids']==preimage['packages'] and
         all(type(uid) is int and uid>=0 for uid in proof['package_uids'].values()),'TARGET_UID_REASSIGNED')
    wanted={kind+'/0/'+package for kind in ('user','user_de') for package in preimage['targets']}
    need(set(proof['directories'])==wanted,'ALL_90_LIVE_DIRECTORY_IDENTITIES_REQUIRED')
    mount_rows=proof['selected_mount_rows']
    need(type(mount_rows) is list and 0<len(mount_rows)<=90 and
         all(type(row['mount_id']) is int and row['mount_id']>0 for row in mount_rows) and
         len({row['mount_id'] for row in mount_rows})==len(mount_rows),'UNIQUE_SELECTED_MOUNT_IDENTITIES_REQUIRED')
    for relative,row in proof['directories'].items():
        kind,user,package=relative.split('/')
        need(row['android_path']=='/data/'+relative and row['device']==dev['device'],'LIVE_DIRECTORY_DEVICE_CHANGED')
        expected_image_path=('/data/' if kind=='user' else '/user_de/0/')+package
        need(row['image_path']==expected_image_path,'CE_DE_DIRECTORY_ROLE_REPLACED')
        entry=preimage['targets'][package]['image_paths'].get(row['image_path'])
        need(entry is not None and entry['exists'] is True and entry['stat']['type']=='directory',
             'LIVE_PATH_NOT_A_PREDEPLOYMENT_DIRECTORY')
        expected=entry['stat']
        need(type(row['inode']) is int and row['inode']==expected['inode'],
             'DATA_DIRECTORY_IDENTITY_REPLACED')
        need(type(row['uid']) is int and type(row['gid']) is int
             and row['uid']==mapping.mapped_id(main_mapping['uid_map'],expected['uid'])
             and row['gid']==mapping.mapped_id(main_mapping['gid_map'],expected['gid']),
             'DATA_DIRECTORY_LIVE_MAPPED_OWNER_DIFFERS_FROM_PREIMAGE')
        need(row['uid']==mapping.mapped_id(main_mapping['uid_map'],preimage['packages'][package]),
             'LIVE_DIRECTORY_MAPPED_UID_CHANGED')
        mount,image_path=effective_mount(proof['selected_mount_rows'],row['android_path'])
        need(mount['major_minor']==dev['major_minor'] and mount['filesystem']=='ext4' and
             image_path==row['image_path'],'ACTUAL_CE_DE_BIND_MAPPING_REQUIRED')
    need(proof.get('namespace_entry') is False and type(proof.get('Android_commands')) is int and proof['Android_commands']==0 and
         type(proof.get('app_data_writes')) is int and proof['app_data_writes']==0 and proof.get('business_accepted') is False,
         'READ_ONLY_DATA_PROOF_SCOPE_REQUIRED')
    return identity_projection(proof)

def measure(init_identity,preimage,pool,proc_fd,root_fd,deadline,main_user_namespace):
    """Caller owns pidfd/proc/root for this exact final init and tracks every FD.
    The fixed init identity and both supplied held directory handles are checked
    against the real /proc views. Production has no injected /proc adapter.
    """
    need(type(main_user_namespace) is userns_module().HeldMainUserNamespace,
         'ACTUAL_HELD_MAIN_USER_NAMESPACE_LEASE_REQUIRED')
    main_mapping=main_user_namespace.guard()
    need(main_mapping['init']=={key:init_identity[key] for key in
         ('host_pid','parent_host_pid','start_ticks','namespace_pids')}
         and main_mapping['root_uids']==init_identity['uids'],
         'DATA_MAPPING_MUST_BELONG_TO_THIS_EXACT_INIT')
    epoch=load(EPOCH_PATH,EPOCH_SHA,'business_data_epoch')
    reader=load(READER_PATH,READER_SHA,'business_data_held_reader')
    def check():
        need(time.monotonic()<deadline,'LIVE_DATA_READ_DEADLINE')
    def ensure_init():
        check();need(epoch.process_identity(init_identity['host_pid'])==init_identity,'DATA_INIT_GENERATION_CHANGED')
        need(main_user_namespace.guard()==main_mapping,'DATA_MAIN_USER_NAMESPACE_OR_MAP_CHANGED')
        st=os.stat('/proc/'+str(init_identity['host_pid']))
        own=os.fstat(proc_fd);need((st.st_dev,st.st_ino)==(own.st_dev,own.st_ino),'INIT_PROCDIR_NOT_HELD')
        st=os.stat('/proc/'+str(init_identity['host_pid'])+'/root')
        own=os.fstat(root_fd);need((st.st_dev,st.st_ino)==(own.st_dev,own.st_ino),'INIT_ROOT_NOT_HELD')
    def bounded(fd,limit):return reader.read_fd(fd,limit,deadline)
    def proc_leaf(name,limit):
        fd=pool.own(os.open(name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=proc_fd),'data_proc_leaf')
        try:return bounded(fd,limit)
        finally:pool.close(fd)
    ensure_init()
    mount_raw=proc_leaf('mountinfo',4*1024*1024);mounts=parse_mountinfo(mount_raw)
    datafd=pool.own(reader.open_in_root(root_fd,'/data',os.O_PATH|os.O_DIRECTORY),'live_data_root')
    try:
        st=os.fstat(datafd);need(stat.S_ISDIR(st.st_mode),'LIVE_DATA_ROOT_NOT_DIRECTORY');device=st.st_dev
    finally:pool.close(datafd)
    major_minor=str(os.major(device))+':'+str(os.minor(device))
    sysdev=Path('/sys/dev/block')/major_minor
    actual=sysdev.resolve(strict=True);loop_name=actual.name
    need(re.fullmatch(r'loop[0-9]+',loop_name),'DIRECT_EXT4_LOOP_REQUIRED')
    def sysleaf(name):
        check();path=actual/name;fd=pool.own(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC),'data_loop_sysfs')
        try:return bounded(fd,4096).decode('utf-8','strict').strip()
        finally:pool.close(fd)
    backing=sysleaf('loop/backing_file')
    offset=sysleaf('loop/offset');sizelimit=sysleaf('loop/sizelimit')
    need(backing==str(DATA_IMAGE) and sysleaf('dev')==major_minor and offset==sizelimit=='0',
         'LIVE_DATA_LOOP_BACKING_CHANGED')
    imagefd=pool.own(os.open(DATA_IMAGE,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NOATIME),'live_data_backing_image')
    try:
        initial=meta(imagefd);need(stat.S_ISREG(initial['st_mode']) and initial['st_nlink']==1,'LIVE_IMAGE_FILE_SHAPE')
        block=os.pread(imagefd,1024,1024);need(len(block)==1024 and block[56:58]==b'\x53\xef','LIVE_EXT4_SUPERBLOCK_REQUIRED')
        filesystem_uuid=str(uuid.UUID(bytes=block[104:120]))
        need(image_identity(meta(imagefd))==image_identity(initial),'LIVE_IMAGE_REPLACED')
    finally:pool.close(imagefd)
    packagefd=pool.own(reader.open_in_root(root_fd,'/data/system/packages.list',os.O_RDONLY|os.O_NOFOLLOW),'live_package_uid_source')
    try:
        before=meta(packagefd);need(stat.S_ISREG(before['st_mode']) and 0<before['st_size']<=1024*1024,'PACKAGE_SOURCE_BOUND')
        package_raw=bounded(packagefd,1024*1024)
        need(meta(packagefd)==before and len(package_raw)==before['st_size'],'PACKAGE_UID_SOURCE_CHANGED_DURING_READ')
    finally:pool.close(packagefd)
    found={}
    for line in package_raw.decode('utf-8','strict').splitlines():
        fields=line.split()
        if not fields or fields[0] not in preimage['packages']:continue
        need(len(fields)>=2 and fields[1].isdecimal() and fields[0] not in found,'PACKAGE_UID_SOURCE_AMBIGUOUS')
        found[fields[0]]=int(fields[1])
    package_source={'sha256':sha(package_raw),'bytes':len(package_raw),'file':before}
    del package_raw
    directories={};used={}
    for package in preimage['packages']:
        for kind in ('user','user_de'):
            relative=kind+'/0/'+package;path='/data/'+relative
            fd=pool.own(reader.open_in_root(root_fd,path,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW),'live_app_data_directory')
            try:
                st=os.fstat(fd);need(stat.S_ISDIR(st.st_mode),'LIVE_APP_DATA_NOT_DIRECTORY')
                mount,image_path=effective_mount(mounts,path);used[mount['mount_id']]=mount
                directories[relative]={'android_path':path,'image_path':image_path,'device':st.st_dev,
                    'inode':st.st_ino,'uid':st.st_uid,'gid':st.st_gid,'mode_observed':stat.S_IMODE(st.st_mode)}
            finally:pool.close(fd)
    ensure_init()
    again=parse_mountinfo(proc_leaf('mountinfo',4*1024*1024))
    for row in directories.values():
        left=effective_mount(mounts,row['android_path'])
        right=effective_mount(again,row['android_path'])
        need(left==right,'DATA_BIND_MAPPING_CHANGED_DURING_READ')
    need(sysleaf('loop/backing_file')==backing and sysleaf('dev')==major_minor and
         sysleaf('loop/offset')==offset and sysleaf('loop/sizelimit')==sizelimit and sysdev.resolve(strict=True)==actual,
         'LOOP_MAPPING_CHANGED_DURING_READ')
    proof={'schema':'pocket4-live-data-continuity-v2','main_user_namespace':main_mapping,'preimage':PREIMAGE,'filesystem_uuid':filesystem_uuid,
        'backing_image_identity':image_identity(initial),'backing_image_path':str(DATA_IMAGE),
        'live_device':{'device':device,'major_minor':major_minor,'loop_name':loop_name,'backing_file':backing,
            'offset':int(offset),'sizelimit':int(sizelimit)},
        'package_uids':found,'package_source_observation':package_source,'directories':directories,
        'selected_mount_rows':[used[k] for k in sorted(used)],
        'mountinfo_source_observation':{'sha256':sha(mount_raw),'bytes':len(mount_raw)},
        'namespace_entry':False,'Android_commands':0,'app_data_writes':0,'business_accepted':False}
    validate_live(preimage,proof,main_mapping)
    return proof
