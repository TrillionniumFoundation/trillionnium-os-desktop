#!/usr/bin/env python3
"""Fixed installed-file observations with the original current Main fence.

No command, socket, namespace entry, service operation, action lock, signal to
another process, package-manager call or write. Source-derived paths are
candidates until observed. Base units do not establish effective systemd
configuration; a package marker does not establish package ownership.
"""
import hashlib,json,os,re,stat,time,types
from pathlib import Path

GUARD_PATH=Path('/home/alex/work/pocket4-current-host-r6-source-01/current_baseline_guard.py')
GUARD_BYTES=11541
GUARD_SHA='96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150'
BASELINE_SHA='633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA='ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
SOURCE_SHA='68379ffa989e90c72faa7574df5f1541582f302f730864c4818a976446f727ab'
EPOCH_SHA='7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
SPECS=json.loads("[{\"key\":\"supervisor_binary\",\"path\":\"/usr/bin/droidloom-supervisor\",\"kind\":\"elf\",\"limit\":67108864,\"artifact\":\"droidloom-supervisor\"},{\"key\":\"daemon_binary\",\"path\":\"/usr/bin/droidloomd\",\"kind\":\"elf\",\"limit\":67108864,\"artifact\":\"droidloomd\"},{\"key\":\"cli_binary\",\"path\":\"/usr/bin/droidloomctl\",\"kind\":\"elf\",\"limit\":67108864,\"artifact\":\"droidloomctl\"},{\"key\":\"applications_binary\",\"path\":\"/usr/bin/droidloom-applications\",\"kind\":\"elf\",\"limit\":67108864,\"artifact\":\"droidloom-applications\"},{\"key\":\"daemon_unit\",\"path\":\"/usr/lib/systemd/system/droidloomd.service\",\"kind\":\"unit\",\"limit\":32768,\"expected_exec\":\"/usr/bin/droidloomd\",\"reference_sha256\":\"3dc60679d7d65c2fb051a75733ea0cab888e501f280ff37afcf20d5167305d2d\"},{\"key\":\"session_unit\",\"path\":\"/usr/lib/systemd/user/droidloom.service\",\"kind\":\"unit\",\"limit\":32768,\"expected_exec\":\"/usr/bin/droidloom-supervisor\"},{\"key\":\"applications_unit\",\"path\":\"/usr/lib/systemd/user/droidloom-applications.service\",\"kind\":\"unit\",\"limit\":32768,\"expected_exec\":\"/usr/bin/droidloom-applications\",\"reference_sha256\":\"4ef2be1261bdcd1da489cc117cfb9ca66b078bf980354c8d6764c88c1f56d138\"},{\"key\":\"cell_config\",\"path\":\"/etc/droidloom/cell.json\",\"kind\":\"config\",\"limit\":131072,\"reference_sha256\":\"f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc\"},{\"key\":\"package_marker\",\"path\":\"/usr/share/droidloom/package.json\",\"kind\":\"marker\",\"limit\":65536}]")
RELEASE=json.loads("{\"droidloom-supervisor\":{\"path\":\"/home/alex/work/p4-sr01-20261106/attempt01/cargo-target/release/droidloom-supervisor\",\"bytes\":1997840,\"sha256\":\"c94ccb72f1a78494b65ee76e0dcaaa207d7d427bc4ef765e32b2d9c194678409\",\"profile\":{\"debug_assertions\":false,\"debuginfo\":0,\"opt_level\":\"3\",\"overflow_checks\":false,\"test\":false}},\"droidloomd\":{\"path\":\"/home/alex/work/p4-sr01-20261106/attempt01/cargo-target/release/droidloomd\",\"bytes\":1981536,\"sha256\":\"8f43a4873d57cda4bfb9cafc0debbedda88626f60a825171a1296ea42e567a7e\",\"profile\":{\"debug_assertions\":false,\"debuginfo\":0,\"opt_level\":\"3\",\"overflow_checks\":false,\"test\":false}},\"droidloomctl\":{\"path\":\"/home/alex/work/p4-sr01-20261106/attempt01/cargo-target/release/droidloomctl\",\"bytes\":1744472,\"sha256\":\"c9f9a36647dc18801f911117413f34e5240684076250e20414ac29e71f2e973a\",\"profile\":{\"debug_assertions\":false,\"debuginfo\":0,\"opt_level\":\"3\",\"overflow_checks\":false,\"test\":false}},\"droidloom-applications\":{\"path\":\"/home/alex/work/p4-sr01-20261106/attempt01/cargo-target/release/droidloom-applications\",\"bytes\":1576016,\"sha256\":\"71f51160685485fba0ef54727c66351a83b0e2dc236fd22f8c91471aac049534\",\"profile\":{\"debug_assertions\":false,\"debuginfo\":0,\"opt_level\":\"3\",\"overflow_checks\":false,\"test\":false}}}")
RELEASE_ACTUAL=json.loads("{\"tree\":\"87ccdef7ae4687cfc48ab4efdb07bfb0dde6b527\",\"git_blob\":\"459b355cfc7a4cadf4ed63706f9f6882f86084f4\",\"bytes\":146722,\"sha256\":\"cb0628aac421253277aad72b616d290503d62ca48bf8bcfd05bf97cf37640ea2\",\"job_id\":\"1a1b30c39ef-fc05-8081\"}")
META_KEYS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
DIR_KEYS=('st_dev','st_ino','st_mode','st_uid','st_gid')
MAX_TOTAL_BYTES=402653184
MAX_OWNED_FDS=128

def need(value,code):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def safe_error(error):
    result={'type':type(error).__name__}
    if isinstance(error,OSError):result['errno']=error.errno
    elif isinstance(error,(RuntimeError,TimeoutError)) and re.fullmatch('[A-Z0-9_]{1,96}',str(error)):
        result['code']=str(error)
    else:result['code']='UNEXPECTED_DIAGNOSTIC_ERROR'
    return result

def read_guard(check,report):
    fds=[];primary=None;errors=[]
    report.update(acquired=0,close_attempts=0,closed=0,remaining=0,errors=[])
    def own(fd):
        if fd<3:
            try:os.close(fd)
            finally:raise RuntimeError('INPUT_FD_ALIASED_STANDARD_STREAM')
        fds.append(fd);report['acquired']+=1;return fd
    try:
        check();directory=own(os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC))
        for part in GUARD_PATH.parts[1:-1]:
            check();directory=own(os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
        fd=own(os.open(GUARD_PATH.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
        first=os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
             first.st_size==GUARD_BYTES,'EXACT_CURRENT_GUARD_REGULAR_FILE_REQUIRED')
        raw=b''
        while True:
            check();part=os.read(fd,min(16384,GUARD_BYTES+1-len(raw)))
            if not part:break
            raw+=part;need(len(raw)<=GUARD_BYTES,'CURRENT_GUARD_BYTE_BOUND')
        last=os.fstat(fd)
        fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        need(all(getattr(first,k)==getattr(last,k) for k in fields) and
             len(raw)==GUARD_BYTES and sha(raw)==GUARD_SHA,'EXACT_CURRENT_GUARD_BYTES_CHANGED')
        return raw
    except BaseException as error:primary=error;raise
    finally:
        for fd in reversed(fds):
            report['close_attempts']+=1
            try:os.close(fd);report['closed']+=1
            except BaseException as error:errors.append(safe_error(error))
        report['remaining']=report['acquired']-report['closed'];report['errors']=errors
        if errors:
            if primary is None:raise RuntimeError('DIAGNOSTIC_INPUT_FD_CLOSE_FAILED')
            primary.add_note('DIAGNOSTIC_INPUT_FD_CLOSE_FAILED')

def file_meta(fd):
    row=os.fstat(fd)
    return {key:getattr(row,key) for key in META_KEYS}

def dir_identity(row):
    return {key:row[key] for key in DIR_KEYS}

def own(pool,fd,label):
    value=pool.own(fd,label)
    need(pool.acquired<=MAX_OWNED_FDS,'INVENTORY_DESCRIPTOR_BOUND')
    return value

def shape(row,limit):
    if stat.S_ISLNK(row['st_mode']):return 'unsupported_symlink'
    if not stat.S_ISREG(row['st_mode']):return 'unsupported_nonregular'
    if row['st_uid']!=0:return 'unsupported_owner'
    if row['st_nlink']!=1:return 'unsupported_link_count'
    if not 0<=row['st_size']<=limit:return 'unsupported_size'
    return 'regular_content_admitted'

def elf_projection(header):
    valid=bool(len(header)>=64 and header[:7]==b'\x7fELF\x02\x01\x01' and
               int.from_bytes(header[16:18],'little') in (2,3) and
               int.from_bytes(header[18:20],'little')==62)
    return {'ELF64_little_endian_x86_64_executable':valid}

def unit_projection(raw,spec):
    # Literal facts only. Do not pretend to implement systemd's merge semantics.
    text=raw.decode('utf-8','strict')
    starts=[line.strip() for line in text.splitlines() if line.strip().startswith('ExecStart=')]
    wanted='ExecStart='+spec['expected_exec']
    return {'literal_ExecStart_lines':len(starts),
            'exact_expected_ExecStart_lines':sum(line==wanted for line in starts),
            'other_ExecStart_lines':sum(line!=wanted for line in starts),
            'reference_bytes_match':sha(raw)==spec.get('reference_sha256'),
            'effective_service_configuration_qualified':False,
            'unknown_directive_values_exported':False}

def read_content(fd,limit,expected,check,budget,*,keep=False,io=os,metadata=file_meta):
    need(shape(expected,limit)=='regular_content_admitted','CONTENT_FILE_SHAPE_REQUIRED')
    check();need(metadata(fd)==expected,'CONTENT_IDENTITY_CHANGED_BEFORE_READ')
    io.lseek(fd,0,os.SEEK_SET)
    digest=hashlib.sha256();count=0;header=b'';chunks=[] if keep else None
    while True:
        check();part=io.read(fd,min(65536,limit+1-count))
        if not part:break
        count+=len(part);budget['bytes']+=len(part)
        need(count<=limit,'CONTENT_BYTE_BOUND')
        need(budget['bytes']<=MAX_TOTAL_BYTES,'INVENTORY_TOTAL_BYTE_BOUND')
        digest.update(part)
        if len(header)<64:header=(header+part)[:64]
        if keep:chunks.append(part)
    need(count==expected['st_size'] and metadata(fd)==expected,'CONTENT_CHANGED_DURING_READ')
    check()
    return {'bytes':count,'sha256':digest.hexdigest()},header,(b''.join(chunks) if keep else None)

def open_fixed(pool,root,spec,check):
    need(spec in SPECS and spec['path'].startswith('/') and
         all(part not in ('','.','..') for part in spec['path'][1:].split('/')),
         'EXACT_FIXED_INVENTORY_PATH_REQUIRED')
    parts=spec['path'][1:].split('/');parent=root;edges=[]
    entry={'spec':spec,'edges':edges,'terminal':None,'read_fd':None,'pin':None}
    for index,name in enumerate(parts):
        check()
        try:fd=own(pool,os.open(name,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent),
                   'fixed_inventory_path_component')
        except FileNotFoundError:
            entry['terminal']={'parent':parent,'name':name,'state':'absent','index':index}
            return entry
        before=file_meta(fd)
        if index<len(parts)-1:
            if not stat.S_ISDIR(before['st_mode']) or before['st_uid']!=0:
                entry['terminal']={'parent':parent,'name':name,'fd':fd,'file':before,
                                   'state':'unsupported_ancestor','index':index}
                return entry
            edges.append({'parent':parent,'name':name,'fd':fd,'identity':dir_identity(before)})
            parent=fd
        else:
            entry['terminal']={'parent':parent,'name':name,'fd':fd,'file':before,
                               'state':shape(before,spec['limit']),'index':index}
    terminal=entry['terminal']
    if terminal['state']=='regular_content_admitted':
        check()
        entry['read_fd']=own(pool,os.open(terminal['name'],os.O_RDONLY|os.O_NONBLOCK|
                                         os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=terminal['parent']),
                            'fixed_inventory_regular_content')
        need(file_meta(entry['read_fd'])==terminal['file'],'FIXED_NAMED_OPEN_IDENTITY_CHANGED')
    return entry

def entry_projection(entry):
    spec=entry['spec'];terminal=entry['terminal']
    out={'key':spec['key'],'path':spec['path'],'kind':spec['kind'],'state':terminal['state'],
         'component_index':terminal['index'],'named_path_is_install_destination_qualified':False}
    if 'file' in terminal:out['file']=terminal['file']
    if entry['pin'] is not None:
        out['content']=entry['pin']
        if spec['kind']=='elf':
            out.update(entry['elf'])
            candidate=RELEASE[spec['artifact']]
            out['matches_actual_release_content']=(entry['pin']=={k:candidate[k] for k in ('bytes','sha256')})
            out['mode_has_execute_bit']=bool(terminal['file']['st_mode']&0o111)
        elif spec['kind']=='unit':out['literal_unit_observation']=entry['unit']
        elif spec['kind']=='config':
            out['matches_current_guard_config']=entry['pin']['sha256']==spec['reference_sha256']
        elif spec['kind']=='marker':
            out['package_marker_present']=True
            out['package_ownership_qualified']=False
            out['raw_marker_body_exported']=False
    return out

def verify_fixed_entry(entry,check,budget):
    for edge in entry['edges']:
        check();need(dir_identity(file_meta(edge['fd']))==edge['identity'],'HELD_PARENT_DIRECTORY_CHANGED')
        named=os.stat(edge['name'],dir_fd=edge['parent'],follow_symlinks=False)
        need({key:getattr(named,key) for key in DIR_KEYS}==edge['identity'],'NAMED_PARENT_DIRECTORY_CHANGED')
    terminal=entry['terminal'];check()
    if terminal['state']=='absent':
        try:os.stat(terminal['name'],dir_fd=terminal['parent'],follow_symlinks=False)
        except FileNotFoundError:return
        raise RuntimeError('FIXED_ABSENT_PATH_APPEARED')
    named=os.stat(terminal['name'],dir_fd=terminal['parent'],follow_symlinks=False)
    need(file_meta(terminal['fd'])==terminal['file'] and
         {key:getattr(named,key) for key in META_KEYS}==terminal['file'],'FIXED_HELD_OR_NAMED_FILE_CHANGED')
    if entry['read_fd'] is not None:
        pin,_,_=read_content(entry['read_fd'],entry['spec']['limit'],terminal['file'],check,budget)
        need(pin==entry['pin'],'FIXED_CONTENT_CHANGED_AFTER')

def controls():
    rows=[]
    def case(name,fn):
        fn();rows.append({'name':name,'passed':True})
    def same(actual,expected):
        need(actual==expected,'INVENTORY_CONTROL_ASSERTION')
    def rejects(fn,code):
        try:fn()
        except RuntimeError as error:
            need(str(error)==code,'INVENTORY_CONTROL_WRONG_FIRST_ERROR');return
        raise RuntimeError('INVENTORY_CONTROL_FALSE_ACCEPT')
    meta={'st_dev':1,'st_ino':2,'st_mode':stat.S_IFREG|0o755,'st_uid':0,'st_gid':0,
          'st_nlink':1,'st_size':3,'st_mtime_ns':4,'st_ctime_ns':5}
    case('root_regular_file_shape',lambda:same(shape(meta,3),'regular_content_admitted'))
    case('symlink_is_not_followed',lambda:same(shape({**meta,'st_mode':stat.S_IFLNK|0o777},3),'unsupported_symlink'))
    case('hardlink_not_admitted',lambda:same(shape({**meta,'st_nlink':2},3),'unsupported_link_count'))
    case('nonroot_file_not_admitted',lambda:same(shape({**meta,'st_uid':1000},3),'unsupported_owner'))
    case('oversize_file_not_admitted',lambda:same(shape(meta,2),'unsupported_size'))
    header=bytearray(64);header[:7]=b'\x7fELF\x02\x01\x01';header[16:18]=(3).to_bytes(2,'little');header[18:20]=(62).to_bytes(2,'little')
    case('ELF64_x86_64_content',lambda:same(elf_projection(bytes(header)),{'ELF64_little_endian_x86_64_executable':True}))
    header[18:20]=(183).to_bytes(2,'little')
    case('foreign_machine_not_release_shape',lambda:same(elf_projection(bytes(header)),{'ELF64_little_endian_x86_64_executable':False}))
    unit_spec=next(s for s in SPECS if s['key']=='daemon_unit')
    raw=b'[Service]\nExecStart=/usr/bin/droidloomd\n'
    def unit_case():
        got=unit_projection(raw,unit_spec)
        same((got['exact_expected_ExecStart_lines'],got['other_ExecStart_lines'],got['effective_service_configuration_qualified']),(1,0,False))
    case('literal_unit_not_effective_service_authority',unit_case)
    def private_unit_case():
        got=unit_projection(raw+b'ExecStart=/unrecognized-private-path --secret\n',unit_spec)
        same(got['other_ExecStart_lines'],1)
        need('private-path' not in json.dumps(got) and 'secret' not in json.dumps(got),'CONTROL_PRIVATE_UNIT_EXPORT')
    case('unknown_unit_value_not_exported',private_unit_case)
    class MemoryIO:
        def __init__(self,data):self.data=data;self.offset=0;self.reads=0
        def lseek(self,fd,offset,whence):
            same((fd,offset,whence),(3,0,os.SEEK_SET));self.offset=0;return 0
        def read(self,fd,count):
            same(fd,3);self.reads+=1;out=self.data[self.offset:self.offset+count];self.offset+=len(out);return out
    data=b'z'*65539;memmeta={**meta,'st_size':len(data)}
    def exact_stream():
        io=MemoryIO(data);budget={'bytes':0}
        pin,h,body=read_content(3,len(data),memmeta,lambda:None,budget,io=io,metadata=lambda fd:dict(memmeta))
        same(pin,{'bytes':len(data),'sha256':sha(data)});same(len(h),64);same(body,None);same(io.reads,3);same(budget['bytes'],len(data))
    case('real_hash_stream_crosses_chunk_boundary',exact_stream)
    def changed_after():
        calls=[0]
        def metadata(fd):
            calls[0]+=1;return dict(memmeta) if calls[0]==1 else {**memmeta,'st_ino':9}
        rejects(lambda:read_content(3,len(data),memmeta,lambda:None,{'bytes':0},io=MemoryIO(data),metadata=metadata),'CONTENT_CHANGED_DURING_READ')
    case('hash_loop_rejects_identity_drift',changed_after)
    case('aggregate_read_budget_fail_closed',lambda:rejects(
        lambda:read_content(3,3,meta,lambda:None,{'bytes':MAX_TOTAL_BYTES-2},
                            io=MemoryIO(b'abc'),metadata=lambda fd:dict(meta)),
        'INVENTORY_TOTAL_BYTE_BOUND'))
    need(len(rows)==12 and len({row['name'] for row in rows})==12,'EXACT_TWELVE_INVENTORY_CONTROLS_REQUIRED')
    return {'count':12,'cases':rows,'IO_seam':'MemoryIO only; no real files or processes in controls'}

def execute():
    began=time.monotonic_ns();deadline=time.monotonic()+45
    result={'schema':'pocket4-fixed-installed-provenance-observation-v1',
            'source_sha256':SOURCE_SHA256,'release_actual_reference':RELEASE_ACTUAL,
            'collection_complete':False,'error':None,'secondary_errors':[],
            'original_Main_before':None,'original_Main_after':None,
            'original_Main_samples_comparable':False,'original_Main_samples_equal':False,
            'inputs_before_FDs':{},'inputs_after_FDs':{},'files':[],
            'daemon_image':None,'managed_FDs':None,'input_sources_unchanged':False,
            'fixed_files_unchanged_after':False,'daemon_unchanged_after':False,
            'Main_mutations':0,'Android_commands':0,'Status_or_Readiness_RPC':0,
            'child_processes':0,'namespace_entries':0,'action_lock_operations':0,
            'writes':0,'signals_to_other_processes':0,'private_bodies_exported':False,
            'effective_service_configuration_qualified':False,'package_ownership_qualified':False,
            'installed_Main_source_version_qualified':False,'deployment_authorized':False,
            'new_baseline_or_App_qualification':False,'old_London_outcome_reclassified':False}
    def check():
        need(time.monotonic()<deadline,'FIXED_INVENTORY_READ_DEADLINE')
    def remember(phase,error):
        row={'phase':phase,**safe_error(error)}
        if result['error'] is None:result['error']=row
        else:result['secondary_errors'].append(row)
    g=None;b=None;q=None;p=None;e=None;c=None;pool=None;root=None;root_meta=None
    daemon=None;entries=[];guard_raw=None;budget={'bytes':0};phase='pure_controls';body_complete=False
    try:
        result['controls']=controls()
        phase='pinned_original_guard';guard_raw=read_guard(check,result['inputs_before_FDs'])
        g=types.ModuleType('fixed_original_current_guard');g.__file__=str(GUARD_PATH)
        exec(compile(guard_raw,str(GUARD_PATH),'exec'),g.__dict__)
        check();b,q,p,e,_,c=g.load_current()
        need(g.BASELINE_SHA==BASELINE_SHA and g.QUALIFICATION_SHA==QUALIFICATION_SHA and
             g.SOURCE_MANIFEST_SHA==SOURCE_SHA and g.MAIN_EPOCH==EPOCH_SHA,'EXACT_CURRENT_BASELINE_BINDING_REQUIRED')
        phase='original_complete_Main_before'
        check();result['original_Main_before']=g.current_guard(b,action_attempted=False)
        pool=c.ManagedFDs()
        phase='held_exact_daemon_image'
        pid=p.EXPECTED['daemon']['pid'];need(pid==3588022,'EXACT_FIXED_DAEMON_REQUIRED')
        expected=b['all_seven_processes']['binding']['processes']['daemon']
        check();need(e.process_identity(pid)==expected,'FIXED_DAEMON_FULL_IDENTITY_CHANGED')
        pidfd=own(pool,os.pidfd_open(pid,0),'inventory_daemon_pidfd');c.require_pidfd_live(pidfd)
        proc=own(pool,os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),
                 'inventory_daemon_proc')
        exe=own(pool,os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),'inventory_daemon_executable')
        artifact=b['current_process_executables']['daemon']
        need(file_meta(exe)==artifact['file'],'FIXED_DAEMON_EXECUTABLE_IDENTITY_CHANGED')
        daemon={'pid':pid,'pidfd':pidfd,'proc':proc,'exe':exe,'expected':expected,'artifact':artifact}
        pin,header,_=read_content(exe,268435456,artifact['file'],check,budget)
        need(pin=={key:artifact[key] for key in ('bytes','sha256')},'FIXED_DAEMON_EXECUTABLE_CONTENT_CHANGED')
        need(e.process_identity(pid)==expected,'FIXED_DAEMON_IDENTITY_CHANGED_AFTER_HASH')
        link=expected['executable'].encode('utf-8')
        result['daemon_image']={'host_pid':pid,'start_ticks':expected['start_ticks'],
             'complete_identity_sha256':sha(canonical(expected)),'content':pin,'file':artifact['file'],
             'executable_path_matches_fixed_usr_bin':expected['executable']=='/usr/bin/droidloomd',
             'executable_path_utf8_bytes':len(link),'executable_path_sha256':sha(link),**elf_projection(header)}
        phase='fixed_named_file_inventory'
        root=own(pool,os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC),'inventory_host_root')
        root_meta=dir_identity(file_meta(root))
        for spec in SPECS:
            check();entry=open_fixed(pool,root,spec,check);entries.append(entry)
            if entry['read_fd'] is not None:
                pin,header,raw=read_content(entry['read_fd'],spec['limit'],entry['terminal']['file'],
                                             check,budget,keep=spec['kind']=='unit')
                entry['pin']=pin
                if spec['kind']=='elf':entry['elf']=elf_projection(header)
                elif spec['kind']=='unit':entry['unit']=unit_projection(raw,spec)
            result['files'].append(entry_projection(entry))
        named=next(row for row in result['files'] if row['key']=='daemon_binary')
        result['daemon_image']['matches_fixed_named_daemon_content']=named.get('content')==result['daemon_image']['content']
        result['daemon_image']['matches_fixed_named_daemon_file_identity']=named.get('file')==artifact['file']
        need(len(entries)==len(SPECS)==9,'EXACT_NINE_FIXED_PATHS_REQUIRED')
        body_complete=True
    except BaseException as error:remember(phase,error)
    finally:
        if pool is not None and root is not None:
            try:
                phase='independent_fixed_files_after'
                check();need(dir_identity(file_meta(root))==root_meta,'HELD_HOST_ROOT_CHANGED')
                named=os.stat('/',follow_symlinks=False)
                need({key:getattr(named,key) for key in DIR_KEYS}==root_meta,'NAMED_HOST_ROOT_CHANGED')
                for entry in entries:verify_fixed_entry(entry,check,budget)
                result['fixed_files_unchanged_after']=len(entries)==9
            except BaseException as error:remember(phase,error)
        if daemon is not None:
            try:
                phase='independent_held_daemon_after'
                check();c.require_pidfd_live(daemon['pidfd'])
                need(e.process_identity(daemon['pid'])==daemon['expected'],'FIXED_DAEMON_CHANGED_AFTER')
                need(file_meta(daemon['exe'])==daemon['artifact']['file'],'HELD_DAEMON_FILE_CHANGED_AFTER')
                fresh=own(pool,os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=daemon['proc']),
                          'inventory_daemon_named_executable_after')
                try:
                    need(file_meta(fresh)==daemon['artifact']['file'],'NAMED_DAEMON_FILE_CHANGED_AFTER')
                    pin,_,_=read_content(fresh,268435456,daemon['artifact']['file'],check,budget)
                    need(pin=={key:daemon['artifact'][key] for key in ('bytes','sha256')},'DAEMON_CONTENT_CHANGED_AFTER')
                finally:pool.close(fresh)
                c.require_pidfd_live(daemon['pidfd']);result['daemon_unchanged_after']=True
            except BaseException as error:remember(phase,error)
        if g is not None and b is not None:
            try:
                phase='independent_original_full_Main_after'
                check();result['original_Main_after']=g.current_guard(b,action_attempted=False)
                result['original_Main_samples_comparable']=result['original_Main_before'] is not None
                if result['original_Main_samples_comparable']:
                    need(result['original_Main_after']==result['original_Main_before'],'ORIGINAL_COMPLETE_MAIN_SAMPLE_CHANGED')
                    result['original_Main_samples_equal']=True
                phase='independent_fixed_source_and_full_baseline_after'
                check();b2,q2,_,_,_,_=g.load_current()
                need(b2==b and q2==q,'ORIGINAL_BASELINE_OR_QUALIFICATION_CHANGED')
                need(read_guard(check,result['inputs_after_FDs'])==guard_raw,'ORIGINAL_GUARD_SOURCE_CHANGED')
                check();result['input_sources_unchanged']=True
            except BaseException as error:remember(phase,error)
        if pool is not None:
            pool.close_all();result['managed_FDs']=pool.summary()
            try:pool.require_clean()
            except BaseException as error:remember('owned_descriptor_retirement',error)
        result['streamed_content_bytes_including_rechecks']=budget['bytes']
        result['guard_internal_descriptors']='Original guard and baseline loaders retain their own unchanged finally/close gates; not included in collector FD count.'
        result['elapsed_ns']=time.monotonic_ns()-began
        result['collection_complete']=bool(body_complete and result['fixed_files_unchanged_after'] and
            result['daemon_unchanged_after'] and result['original_Main_samples_equal'] and
            result['input_sources_unchanged'] and result['error'] is None and not result['secondary_errors'])
        raw=(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
        need(len(raw)<=131072,'FIXED_INVENTORY_PUBLIC_OUTPUT_BOUND')
        print(raw.decode('utf-8'),end='',flush=True)
    return 0 if result['collection_complete'] else 1

def main():
    return execute()
