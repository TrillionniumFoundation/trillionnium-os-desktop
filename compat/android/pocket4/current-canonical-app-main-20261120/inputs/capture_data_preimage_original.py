"""Create one private predeployment metadata snapshot while Main remains stopped."""
import hashlib,json,os,re,stat,time,types,uuid
from pathlib import Path

FINAL=Path('/home/alex/work/pocket4-android-final')
OUTPUT=FINAL/'qualification/business-data-predeployment-resume-20261107-r2'
CELL=Path('/etc/droidloom/cell.json')
CELL_SHA='f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
DATA=Path('/var/lib/droidloom/users/1000/data')
GATES=Path('/home/alex/work/pocket4-cp13-canonical-app-gates-20261106-r12-01.json')
GATES_SHA='441289f9c04b46f38e1dd6e19f23ec6e4c6729b6a6f814cab81c0ae6fbbb1e78'
RUNNER=FINAL/'deployment/transaction-runner.py'
RUNNER_SHA='1ebd5406c5cf37d84e9b16b6caa5783554918e624537bddcd0ed64e044049de0'
OLD=Path('/home/alex/work/pocket4-main-current-baseline-02')
OLD_BASELINE_SHA='633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
OLD_QUALIFICATION_SHA='ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
DEADLINE=time.monotonic()+120
META=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def need(value,code):
    if not value:raise RuntimeError(code)

def meta(value):return {key:getattr(value,key) for key in META}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def check():need(time.monotonic()<DEADLINE,'PREDEPLOYMENT_SNAPSHOT_DEADLINE')
def safe_error(error):return {'type':type(error).__name__,'errno':getattr(error,'errno',None),'message':str(error)[:256]}

def read_file(path,maximum,expected=None):
    check();fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|getattr(os,'O_NOATIME',0))
    try:
        before=meta(os.fstat(fd));need(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1 and
            0<=before['st_size']<=maximum,'PINNED_REGULAR_FILE_BOUND')
        raw=bytearray()
        while True:
            check();block=os.read(fd,min(65536,maximum+1-len(raw)))
            if not block:break
            raw.extend(block);need(len(raw)<=maximum,'READ_BOUND')
        need(len(raw)==before['st_size'] and before==meta(os.fstat(fd)),'SOURCE_CHANGED_DURING_READ')
        raw=bytes(raw);need(expected is None or digest(raw)==expected,'SOURCE_SHA_CHANGED')
        return raw,{'path':str(path),'bytes':len(raw),'sha256':digest(raw),'file':before}
    finally:os.close(fd)

def create(path,value,mode=0o400):
    raw=value if type(value) is bytes else (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
    try:
        view=memoryview(raw)
        while view:
            count=os.write(fd,view);need(count>0,'OUTPUT_NO_PROGRESS');view=view[count:]
        os.fsync(fd)
    finally:os.close(fd)
    return {'path':str(path),'bytes':len(raw),'sha256':digest(raw)}

def path_snapshot(path):
    check();path=Path(path)
    try:
        own=path.lstat()
    except FileNotFoundError:
        return {'path':str(path),'exists':False}
    result={'path':str(path),'exists':True,'lstat':meta(own)}
    if stat.S_ISLNK(own.st_mode):result['symlink_target']=os.readlink(path)
    try:
        resolved=path.resolve(strict=True)
        need(resolved==DATA or resolved.is_relative_to(DATA),'DATA_PATH_RESOLVED_OUTSIDE_FIXED_BACKING')
        fd=os.open(resolved,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        try:
            held=os.fstat(fd);need(stat.S_ISDIR(held.st_mode),'DATA_PATH_NOT_DIRECTORY')
            result.update(resolved_path=str(resolved),directory=meta(held),
                identity={'device':held.st_dev,'inode':held.st_ino,'uid':held.st_uid,'gid':held.st_gid,'mode':stat.S_IMODE(held.st_mode)},
                device_major=os.major(held.st_dev),device_minor=os.minor(held.st_dev))
            need(meta(path.lstat())==result['lstat'] and meta(os.stat(resolved))==meta(held),
                 'DATA_PATH_CHANGED_DURING_OBSERVATION')
        finally:os.close(fd)
    except BaseException as error:
        result['observation_error']=safe_error(error)
    return result

def layout_snapshot():
    # Only the fixed mapping ancestors, never any application's file contents.
    return {name:path_snapshot(DATA/name) for name in ('user','user/0','user_de','user_de/0','data')}

def selected_packages(raw,names):
    found={};duplicates=[]
    for line in raw.decode('utf-8','strict').splitlines():
        fields=line.split()
        if not fields or fields[0] not in names:continue
        need(len(fields)>=2 and fields[1].isdecimal(),'SELECTED_PACKAGE_UID_ROW_INVALID')
        if fields[0] in found:duplicates.append(fields[0])
        found[fields[0]]=int(fields[1])
    need(not duplicates,'SELECTED_PACKAGE_UID_DUPLICATE')
    return found

def stopped(runner,phase):
    rows=[]
    for base,unit in runner.UNITS:
        check();argv=base+['show',unit,'--property=ActiveState,SubState,MainPID,ControlPID,ControlGroup,InvocationID']
        result=runner.run(argv,timeout=12,check=True)
        value=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        index=len(runner.COMMAND_AUDIT)-1
        stdout=create(OUTPUT/('command-%02d.stdout'%index),result.stdout.encode())
        stderr=create(OUTPUT/('command-%02d.stderr'%index),result.stderr.encode())
        rows.append({'unit':unit,'state':value,'stdout':stdout,'stderr':stderr,'command_index':index})
        need(value.get('ActiveState') in ('inactive','failed') and value.get('MainPID')=='0' and
             value.get('ControlPID')=='0','MAIN_MUST_REMAIN_STOPPED')
        cg=value.get('ControlGroup','')
        if cg:
            need(cg.startswith('/') and '..' not in Path(cg).parts,'CGROUP_PATH_INVALID')
            cgroot=Path('/sys/fs/cgroup')/cg.lstrip('/')
            if cgroot.exists():
                count=0
                for directory,subdirs,files in os.walk(cgroot):
                    check();count+=1;need(count<=2048,'STOPPED_CGROUP_WALK_BOUND')
                    if 'cgroup.procs' in files:
                        raw=Path(directory,'cgroup.procs').read_bytes()
                        need(len(raw)<=65536 and not raw.strip(),'STOPPED_UNIT_HAS_LIVE_PROCESSES')
                rows[-1]['empty_cgroup_directories']=count
    return {'phase':phase,'units':rows}

def mount_projection(paths):
    fd=os.open('/proc/self/mountinfo',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        raw=b''
        while True:
            check();block=os.read(fd,65536)
            if not block:break
            raw+=block;need(len(raw)<=4*1024*1024,'MOUNTINFO_BOUND')
    finally:os.close(fd)
    def unescape(value):
        return re.sub(r'\\(040|011|012|134)',lambda m:chr(int(m.group(1),8)),value)
    selected=[]
    for line in raw.decode('utf-8','strict').splitlines():
        fields=line.split();need(len(fields)>=10 and '-' in fields,'MOUNTINFO_SCHEMA')
        mountpoint=unescape(fields[4]);root=unescape(fields[3])
        if any(path==mountpoint or path.startswith(mountpoint.rstrip('/')+'/') for path in paths) or \
                mountpoint==str(DATA) or mountpoint.startswith(str(DATA)+'/'):
            selected.append({'line':line,'mountpoint':mountpoint,'root':root,'major_minor':fields[2]})
    return {'source':'/proc/self/mountinfo','source_bytes':len(raw),'source_sha256':digest(raw),
            'selected_rows':selected,'host_mount_namespace':os.readlink('/proc/self/ns/mnt')}


def image_snapshot():
    result={}
    for name in ('data.img','metadata.img'):
        path=DATA/name;fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NOATIME)
        try:
            before=meta(os.fstat(fd));need(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1,'SINGLE_LINK_IMAGE_REQUIRED')
            raw=os.pread(fd,1024,1024);need(len(raw)==1024 and raw[56:58]==b'\x53\xef','EXT_SUPERBLOCK_REQUIRED')
            need(meta(os.fstat(fd))==before,'IMAGE_CHANGED_DURING_HEADER_READ')
            result[name]={'path':str(path),'file':before,'superblock_sha256':digest(raw),
                'filesystem_uuid':str(uuid.UUID(bytes=raw[104:120])),
                'block_size':1024<<int.from_bytes(raw[24:28],'little'),
                'filesystem_state':int.from_bytes(raw[58:60],'little'),
                'incompat_features':int.from_bytes(raw[96:100],'little'),
                'journal_recovery_required':bool(int.from_bytes(raw[96:100],'little')&4),
                'runtime_st_dev_available':False}
        finally:os.close(fd)
    return result

def loop_snapshot():
    result=[];count=0
    for p in sorted(Path('/sys/class/block').glob('loop*')):
        check();count+=1;need(count<=1024,'LOOP_ENUMERATION_BOUND')
        try:backing=(p/'loop/backing_file').read_text().strip()
        except FileNotFoundError:continue
        if backing in (str(DATA/'data.img'),str(DATA/'metadata.img')):
            result.append({'name':p.name,'backing_file':backing,'major_minor':(p/'dev').read_text().strip(),
                           'read_only':(p/'ro').read_text().strip()})
    return result

def debugfs(runner,args,label):
    need(args[0] in ('-R','-f') and '-w' not in args,'READ_ONLY_DEBUGFS_REQUIRED')
    q=runner.run(['/usr/sbin/debugfs',*args,str(DATA/'data.img')],timeout=25,check=True)
    a=create(OUTPUT/(label+'.stdout'),q.stdout.encode());b=create(OUTPUT/(label+'.stderr'),q.stderr.encode())
    return q.stdout,q.stderr,{'stdout':a,'stderr':b,'command_index':len(runner.COMMAND_AUDIT)-1,'returncode':q.returncode}

def parse_stat(text):
    inode=re.search(r'^Inode: ([0-9]+)\s+Type: ([a-z]+)\s+Mode:\s+([0-7]+)\s+Flags: (0x[0-9a-f]+)$',text,re.M)
    owner=re.search(r'^User:\s+([0-9]+)\s+Group:\s+([0-9]+)\s+Project:\s+([0-9]+)\s+Size: ([0-9]+)$',text,re.M)
    generation=re.search(r'^Generation: ([0-9]+)\s+',text,re.M)
    links=re.search(r'^Links: ([0-9]+)\s+Blockcount: ([0-9]+)$',text,re.M)
    if not inode:return None
    need(owner and generation and links,'COMPLETE_DEBUGFS_STAT_REQUIRED')
    return {'inode':int(inode[1]),'type':inode[2],'mode':int(inode[3],8),'flags':int(inode[4],16),
        'uid':int(owner[1]),'gid':int(owner[2]),'project_id':int(owner[3]),'size':int(owner[4]),
        'inode_generation':int(generation[1]),'links':int(links[1]),'block_count':int(links[2]),
        'device':None,'device_reason':'Main stopped; no loop or mounted data filesystem'}

def main():
    need(os.getuid()==os.geteuid()==0,'EXISTING_ROOT_OPERATOR_REQUIRED')
    need(OUTPUT.parent.resolve()==FINAL/'qualification' and not OUTPUT.exists(),'CREATE_ONLY_OUTPUT_REQUIRED')
    OUTPUT.mkdir(mode=0o700)
    result={'schema':'pocket4-business-data-predeployment-v2','status':'incomplete',
        'captured_started_unix_ns':time.time_ns(),'Android_commands':0,'UI_actions':0,
        'Main_started':False,'app_data_writes':0,'namespace_entry':False,'filesystem_mounts_performed':0,
        'baseline_continuity_accepted':False,'source':create(OUTPUT/'capture_data_preimage.py',_SOURCE_BYTES),
        'data_root':str(DATA),'targets':{},'missing':[],'errors':[]}
    runner=None
    try:
        raw,result['cell_before']=read_file(CELL,131072,CELL_SHA);cell=json.loads(raw)
        need(cell['data_dir']==str(DATA),'EXACT_CELL_DATA_IMAGE_DIRECTORY_REQUIRED')
        create(OUTPUT/'cell.before.json',raw)
        gates,result['original_gate_contract']=read_file(GATES,131072,GATES_SHA)
        names=sorted(json.loads(gates)['packages']);need(len(names)==45 and len(set(names))==45,'EXACT_45_PACKAGES_REQUIRED')
        result['package_names']=names
        code,result['host_command_runner']=read_file(RUNNER,131072,RUNNER_SHA)
        runner=types.ModuleType('predeployment_qualified_transaction_reader');runner.__file__=str(RUNNER)
        exec(compile(code,str(RUNNER),'exec'),runner.__dict__)
        result['stopped_before']=stopped(runner,'before')
        result['images_before']=image_snapshot();result['loops_before']=loop_snapshot()
        need(not result['loops_before'],'OFFLINE_IMAGE_MUST_NOT_HAVE_EXISTING_LOOP_MAPPING')
        need(all(not v['journal_recovery_required'] and v['filesystem_state']&1 for v in result['images_before'].values()),
             'CLEAN_UNMOUNTED_FILESYSTEM_REQUIRED')
        _,result['debugfs_binary']=read_file(Path('/usr/sbin/debugfs'),1024*1024,
            '864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f')
        result['mounts_before']=mount_projection({str(DATA)})
        packages,err,ev=debugfs(runner,['-R','cat /system/packages.list'],'packages-list')
        need(packages and err=='debugfs 1.47.2 (1-Jan-2025)\n','PACKAGES_LIST_READ_FAILED')
        raw=packages.encode();need(len(raw)<=1024*1024,'PACKAGES_LIST_BOUND')
        result['packages_list']={**ev,'bytes':len(raw),'sha256':digest(raw)}
        uids=selected_packages(raw,names);result['packages']=uids
        paths=['/','/system','/system/packages.list','/data','/user','/user/0','/user_de','/user_de/0']
        paths += [prefix+'/'+name for name in names for prefix in ('/data','/user/0','/user_de/0')]
        request=create(OUTPUT/'stat-requests.txt',''.join('stat '+path+'\n' for path in paths).encode())
        stdout,stderr,ev=debugfs(runner,['-f',request['path']],'all-directory-stats')
        result['stat_request']=request;result['stat_evidence']=ev
        chunks=re.split(r'^debugfs:\s+stat ([^\r\n]+)\s*$',stdout,flags=re.M)
        need(chunks[0].strip()=='' and len(chunks)==1+2*len(paths),'DEBUGFS_FRAMING_CHANGED')
        observed={}
        for index,path in enumerate(paths):
            actual,text=chunks[index*2+1:index*2+3];need(actual==path and actual not in observed,'STAT_PATH_ORDER_CHANGED')
            row=parse_stat(text)
            if row is None:
                need(text.strip()=='' and ('while looking up '+path) in stderr,'MISSING_PATH_NEEDS_LOOKUP_ERROR')
                observed[path]={'exists':False,'raw_stat_sha256':digest(text.encode())}
            else:observed[path]={'exists':True,'stat':row,'raw_stat_sha256':digest(text.encode())}
        result['image_path_observations']=observed
        need(observed['/system/packages.list']['stat']['size']==len(raw),'PACKAGE_SOURCE_SIZE_CHANGED')
        for name in names:
            result['targets'][name]={'uid':uids.get(name),'user':0,
                'filesystem_uuid':result['images_before']['data.img']['filesystem_uuid'],
                'runtime_device_id':'unavailable_while_stopped',
                'image_paths':{path:observed[path] for path in ('/data/'+name,'/user/0/'+name,'/user_de/0/'+name)},
                'CE_runtime_path':'/data/user/0/'+name,'DE_runtime_path':'/data/user_de/0/'+name,
                'CE_mapping_to_be_revalidated_from_fresh_Main':True}
            if name not in uids:result['missing'].append({'package':name,'kind':'package_uid'})
            for kind,path in (('CE','/data/'+name),('DE','/user_de/0/'+name)):
                item=observed[path]
                if not item['exists']:result['missing'].append({'package':name,'kind':kind,'path':path,'reason':'absent_image_path'})
                elif item['stat']['type']!='directory' or item['stat']['uid']!=uids.get(name):
                    result['missing'].append({'package':name,'kind':kind,'path':path,'reason':'directory_type_or_uid_differs'})
        old_raw,old_ref=read_file(OLD/'baseline.private.json',131072,OLD_BASELINE_SHA)
        old_q_raw,old_q_ref=read_file(OLD/'qualification.json',65536,OLD_QUALIFICATION_SHA)
        old=json.loads(old_raw);oldq=json.loads(old_q_raw)
        need(oldq.get('identity_qualified') is True and oldq.get('baseline',{}).get('sha256')==OLD_BASELINE_SHA,
             'OLD_FOUR_APP_BASELINE_NOT_QUALIFIED')
        result['old_baseline_02']={'baseline':old_ref,'qualification':old_q_ref,
            'retained_baseline':create(OUTPUT/'historical-baseline-02.private.json',old_raw),
            'retained_qualification':create(OUTPUT/'historical-baseline-02.qualification.json',old_q_raw),'comparison':{}}
        for relative,old_dir in old['app_directories'].items():
            kind,user,name=relative.split('/');path=('/data/' if kind=='user' else '/user_de/0/')+name
            item=observed.get(path,{})
            result['old_baseline_02']['comparison'][relative]={'historical':old_dir,'image_path':path,
                'current_image_inode':item.get('stat'),'same_inode_uid_gid':item.get('exists') is True and
                all(item['stat'][key]==old_dir[key] for key in ('inode','uid','gid')),
                'historical_device_not_reused_as_current_runtime_device':True}
        result['stopped_after']=stopped(runner,'after')
        _,result['cell_after']=read_file(CELL,131072,CELL_SHA)
        need(result['cell_after']==result['cell_before'],'CELL_CHANGED_DURING_SNAPSHOT')
        result['images_after']=image_snapshot();result['loops_after']=loop_snapshot()
        need(result['images_after']==result['images_before'] and result['loops_after']==[],'IMAGE_OR_LOOP_MAPPING_CHANGED')
        result['mounts_after']=mount_projection({str(DATA)})
        need(result['mounts_after']['selected_rows']==result['mounts_before']['selected_rows'] and
             result['mounts_after']['host_mount_namespace']==result['mounts_before']['host_mount_namespace'],
             'HOST_BACKING_MOUNT_CHANGED')
        result['stable_image_and_metadata_double_observation']=True;result['status']='captured'
    except BaseException as error:result['errors'].append(safe_error(error))
    finally:
        result['owned_host_commands']=[] if runner is None else runner.COMMAND_AUDIT
        result['captured_finished_unix_ns']=time.time_ns()
        ref=create(OUTPUT/'result.json',result)
        dfd=os.open(OUTPUT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:os.fsync(dfd)
        finally:os.close(dfd)
        print(json.dumps({'status':result['status'],'result':ref,'targets':len(result['targets']),
            'package_uids':len(result.get('packages',{})),'missing':result['missing'],'errors':result['errors'],
            'owned_commands':len(result['owned_host_commands']),
            'all_owned_commands_retired':all(x.get('retirement_proved') is True for x in result['owned_host_commands'])},sort_keys=True))
    return 0 if result['status']=='captured' else 1

if __name__=='__main__':raise SystemExit(main())
