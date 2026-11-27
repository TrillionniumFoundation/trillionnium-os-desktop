"""Bounded host commands for new business flows; no Android task cleanup authority."""
import hashlib,json,os,re,resource,signal,stat,struct,subprocess,time,types
from pathlib import Path
CAPTURE_PATH=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/main/bounded_host_capture.py')
CAPTURE_SHA='8f81e5e2135419e55f7d16bcae40e021129132f169ba543dea36f9f53c786bf3'
IMAGE_CAPTURE_PATH=Path(__file__).resolve().with_name('business_image_capture.py')
IMAGE_CAPTURE_SHA='315c3af8aa21d2c27661a4ba36d1d2827c0d4f345bf380a477727c828fbad26e'
NATIVE_CHANNEL_PATH=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/main/native_leaf_channel.py')
NATIVE_CHANNEL_SHA='b87eb453836022d772c11c6fa58ca55ab35348391f2e3445726adbe56720b826'
ENV={'PATH':'/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'}
META=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def need(value,code):
    if not value:raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def parse(raw):
    def pairs(items):
        result={}
        for k,v in items:
            need(k not in result,'DUPLICATE_JSON_FIELD');result[k]=v
        return result
    def nonfinite(_):raise RuntimeError('NONFINITE_JSON_NUMBER')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)
def read(path,maximum=1024*1024,expected=None):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<=before.st_size<=maximum,'PINNED_FILE_SHAPE')
        raw=bytearray()
        while True:
            block=os.read(fd,min(65536,maximum+1-len(raw)))
            if not block:break
            raw.extend(block);need(len(raw)<=maximum,'FILE_BOUND')
        after=os.fstat(fd)
        need(len(raw)==before.st_size and all(getattr(before,k)==getattr(after,k) for k in META),'FILE_CHANGED')
        need(expected is None or digest(raw)==expected,'FILE_PIN_CHANGED')
        return bytes(raw)
    finally:os.close(fd)
def write_new(path,value):
    path=Path(path);raw=value if type(value) is bytes else (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    try:
        rest=memoryview(raw)
        while rest:
            count=os.write(fd,rest);need(count>0,'EVIDENCE_WRITE_NO_PROGRESS');rest=rest[count:]
        os.fsync(fd)
    finally:os.close(fd)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'path':str(path),'bytes':len(raw),'sha256':digest(raw)}
def load_capture(image_channel=False):
    path,pin=(IMAGE_CAPTURE_PATH,IMAGE_CAPTURE_SHA) if image_channel else (CAPTURE_PATH,CAPTURE_SHA)
    raw=read(path,expected=pin)
    module=types.ModuleType('new_business_qualified_capture');module.__file__=str(path)
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module

def native_channel_module():
    raw=read(NATIVE_CHANNEL_PATH,maximum=262144,expected=NATIVE_CHANNEL_SHA)
    module=types.ModuleType('normal_native_leaf_command_comparison');module.__file__=str(NATIVE_CHANNEL_PATH)
    exec(compile(raw,str(NATIVE_CHANNEL_PATH),'exec'),module.__dict__)
    return module


# A source-owned preparation may compile only beneath its fresh private build
# directory. This object borrows the inherited live channel; it grants no Main
# or Android authority and cannot be reconstructed from an observation file.
WORKING_BUILD_CASES={
    'documents-saf':'com.android.documentsui',
    'documents-search-sort':'com.android.documentsui',
    'ihg-london':'com.ihg.apps.android',
}
WORKING_PARENT='/system.slice/droidloom-working-qualification.service'
BUILD_PROOF=struct.Struct('>4s17Q')

def _working_build_location(live,path,*,preparation):
    runtime=live.working_runtime_root()
    if runtime is None:return None
    if preparation:
        need(live.working_preparation_owner is not None and live.working_native_source is None,
             'ONLY_ACTUAL_PREPARATION_OWNER_CAN_BUILD')
        need(os.getppid()==live.working_preparation_owner['actual_pid'],
             'ACTUAL_PREPARATION_PARENT_REQUIRED')
    path=Path(path)
    matches=[name for name,package in WORKING_BUILD_CASES.items()
             if path==runtime/'native-inputs'/name/'helper-build'
             and package==live.core['application']['package']]
    need(len(matches)==1,'ONE_COMPILED_WORKING_BUILD_DIRECTORY_REQUIRED')
    return runtime,matches[0]

def relative_build_argv(argv,root):
    need(type(argv) in (list,tuple) and 1<=len(argv)<=128 and
         all(type(v) is str and v and '\0' not in v for v in argv),
         'BOUNDED_FIXED_BUILD_ARGV_REQUIRED')
    need(Path(argv[0]).is_absolute() and Path(argv[0]).name in {
        'aapt','aapt2','javac','java','zipalign','apksigner'},
        'FIXED_ORIGINAL_BUILD_TOOL_REQUIRED')
    root=str(root);prefix=root+'/'
    out=[]
    for value in argv:
        marker='file:' if value.startswith('file:') else ''
        operand=value[len(marker):]
        if operand.startswith(prefix):
            relative=operand[len(prefix):]
            need(relative and all(part not in ('','.','..') for part in relative.split('/')),
                 'CANONICAL_BUILD_RELATIVE_OPERAND_REQUIRED')
            value=marker+'./'+relative
        else:
            need(root not in value and '/proc/self/fd/' not in value,
                 'NO_UNACCOUNTED_WORKING_BUILD_PATH_OPERAND')
        out.append(value)
    return out

def working_build_resources():
    live=native_channel_module().ComparisonChannel()
    runtime=live.working_runtime_root()
    need(runtime is not None and live.working_preparation_owner is not None
         and live.working_native_source is None,'ACTUAL_PREPARATION_BUILD_SCOPE_REQUIRED')
    parent=live.working_preparation_owner['actual_pid']
    need(os.getppid()==parent and Path('/proc/self/cgroup').read_text().splitlines()==
         ['0::'+WORKING_PARENT+'/owned-probe'] and
         Path('/proc/'+str(parent)+'/cgroup').read_text().splitlines()==['0::'+WORKING_PARENT],
         'EXACT_LIVE_REGISTERED_WORKING_PROBE_REQUIRED')
    current=Path('/sys/fs/cgroup')/(WORKING_PARENT+'/owned-probe').lstrip('/')
    keys=('cpu.max','memory.max','memory.swap.max','pids.max')
    chain=[];path=current
    while path!=Path('/sys/fs'):
        before=path.lstat()
        need(stat.S_ISDIR(before.st_mode) and before.st_uid==before.st_gid==0
             and path.resolve()==path,'ACTUAL_ROOT_CGROUP_ANCESTOR_REQUIRED')
        controls={}
        for key in keys:
            item=path/key
            if item.exists():controls[key]=item.read_text().strip()
        after=path.lstat()
        need(tuple(getattr(before,k) for k in META[:5])==
             tuple(getattr(after,k) for k in META[:5]),'BUILD_CGROUP_IDENTITY_CHANGED')
        chain.append({'path':str(path),'f9':[getattr(after,k) for k in META],'controls':controls})
        if path==Path('/sys/fs/cgroup'):break
        path=path.parent
    cpu=[];memory=[];swap=[];pids=[]
    for row in chain:
        controls=row['controls']
        if 'cpu.max' in controls:
            q,period=controls['cpu.max'].split()
            need(period.isdecimal() and int(period)>0,'FINITE_BUILD_CPU_PERIOD')
            if q!='max':
                need(q.isdecimal() and int(q)>0,'FINITE_BUILD_CPU_QUOTA')
                cpu.append((int(q),int(period)))
        for key,values in [('memory.max',memory),('memory.swap.max',swap),('pids.max',pids)]:
            raw=controls.get(key,'max')
            if raw!='max':
                need(raw.isdecimal(),'FINITE_BUILD_CGROUP_LIMIT')
                values.append(int(raw))
    need(cpu and memory and swap and pids,'FINITE_ACTUAL_BUILD_ANCESTOR_LIMITS_REQUIRED')
    quota,period=min(cpu,key=lambda v:v[0]/v[1])
    values={key:(current/key).read_text().strip() for key in
            (*keys,'memory.current','memory.peak','memory.events','cpu.stat')
            if (current/key).exists()}
    values.update(path=str(current),affinity=sorted(os.sched_getaffinity(0)),
        nice=os.getpriority(os.PRIO_PROCESS,0),working_resource_scope='actual-owned-probe-ancestors',
        cgroup_ancestors=chain,effective_limits={'cpu_quota':quota,'cpu_period':period,
            'memory_max':min(memory),'memory_swap_max':min(swap),'pids_max':min(pids)})
    live.guard()
    return values


# These are the same original formal JDK and Debian signer inputs already
# admitted by the native helper builders. Keep the actual working command
# separate from its unchanged source-level logical_argv.
WORKING_JDK='/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1/jdk/jdk21/linux-x86'
WORKING_SDK='/usr/lib/droidloom-native-leaf-toolchain/aosp-21.0.4-r1'
WORKING_SIGNER='/usr/share/java/apksigner-35.0.2.jar'
WORKING_APKSIG='/usr/share/java/apksig-0.9.jar'
WORKING_BUILD_TOOLS={
    'java':(WORKING_JDK+'/bin/java',8528,'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842'),
    'javac':(WORKING_JDK+'/bin/javac',8824,'18351d7a271f6b8bd17f9e8fef6bb04baa7cf008cbc8a3a782a93a2f5c48ecfa'),
    'apksigner_jar':(WORKING_SIGNER,521108,'98346a3200d6030e247ccba0e47b354b6113ec2068dcea6c43558b01fe5885c2'),
    'apksig_jar':(WORKING_APKSIG,489902,'61186f715a98cf2473544a4bbb1fae06ab84600cf2cd6adfa7ad50f4b0e2375e'),
}

def working_build_argv(logical,root,case):
    need(case in WORKING_BUILD_CASES,'FIXED_WORKING_BUILD_CASE_REQUIRED')
    argv=relative_build_argv(logical,root)
    need(all('/proc/' not in value and 'user.dir' not in value for value in argv),
         'NO_CALLER_PROC_OR_JVM_DIRECTORY_OVERRIDE')
    program=argv[0]
    java=[WORKING_JDK+'/bin/java','-Duser.dir=/proc/self/cwd',
          '-XX:ActiveProcessorCount=1','-XX:+UseSerialGC','-Xmx256m']
    if program==WORKING_JDK+'/bin/java':
        need(argv[1:4]==java[2:],'ORIGINAL_FIXED_JVM_RESOURCES_REQUIRED')
        tail=argv[4:]
        need((tail[:3]==['-cp',WORKING_SDK+'/cmdline-tools/tools/lib/r8.jar','com.android.tools.r8.D8']) or
             (tail[:2]==['-m','java.base/sun.security.tools.keytool.Main']) or
             (case!='ihg-london' and tail[:2]==['-jar',WORKING_SIGNER] and
              len(tail)>2 and tail[2] in ('sign','verify')),
             'ONLY_ORIGINAL_D8_KEYTOOL_OR_DOCS_SIGNER')
        return java+tail
    if program==WORKING_JDK+'/bin/javac':
        heap='256m' if case=='ihg-london' else '192m'
        need(argv[1:4]==['-J-XX:ActiveProcessorCount=1','-J-XX:+UseSerialGC','-J-Xmx'+heap],
             'ORIGINAL_FIXED_JAVAC_RESOURCES_REQUIRED')
        return [program,'-J-Duser.dir=/proc/self/cwd',*argv[1:]]
    if program=='/usr/lib/android-sdk/build-tools/debian/apksigner':
        need(case=='ihg-london','WRAPPER_MAPPING_ONLY_FOR_ORIGINAL_IHG_SIGNER')
        sign=['sign','--ks','./private-signing/owned.p12','--ks-pass',
              'file:./private-signing/password.txt','--ks-key-alias','owned-ihg-final-main',
              '--min-sdk-version','31','--v1-signing-enabled','false',
              '--v2-signing-enabled','true','--v3-signing-enabled','true',
              '--out','./owned-ihg-qa.apk','./aligned.apk']
        verify=['verify','--verbose','--print-certs','--min-sdk-version','31','./owned-ihg-qa.apk']
        need(argv[1:] in (sign,verify),'EXACT_ORIGINAL_IHG_SIGN_OR_VERIFY_REQUIRED')
        return java+['-jar',WORKING_SIGNER,*argv[1:]]
    need(program in ('/usr/lib/android-sdk/build-tools/debian/aapt',
                     WORKING_SDK+'/build-tools/linux-x86/bin/zipalign'),
         'EXACT_FORMAL_WORKING_BUILD_PROGRAM_REQUIRED')
    return argv

class WorkingBuildTools:
    """Retain only fixed original tool inputs, never a Main/source authority."""
    def __init__(self):
        self.fds={};self.refs={};self.closed=False;self.alias=None
        try:
            for name,(path,size,expected) in WORKING_BUILD_TOOLS.items():
                p=Path(path)
                need(p.resolve(strict=True)==p,'NO_WORKING_TOOL_PATH_ALIAS')
                for parent in p.parents:
                    st=parent.lstat()
                    need(stat.S_ISDIR(st.st_mode) and st.st_uid==st.st_gid==0 and
                         not st.st_mode&0o022,'ROOT_PROTECTED_FORMAL_TOOL_ANCESTOR')
                fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW);self.fds[name]=fd
                st=os.fstat(fd);identity=tuple(getattr(st,k) for k in META)
                need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and
                     st.st_nlink==1 and not st.st_mode&0o022 and st.st_size==size,
                     'EXACT_ROOT_OWNED_WORKING_TOOL_INPUT')
                raw=os.pread(fd,size+1,0)
                need(len(raw)==size and digest(raw)==expected and
                     identity==tuple(getattr(os.fstat(fd),k) for k in META)==
                     tuple(getattr(p.lstat(),k) for k in META),'WORKING_TOOL_BYTES_CHANGED')
                self.refs[name]={'path':path,'bytes':size,'sha256':expected,'f9':list(identity)}
            alias=Path('/usr/share/java/apksig.jar');st=alias.lstat()
            need(stat.S_ISLNK(st.st_mode) and st.st_uid==st.st_gid==0 and
                 alias.resolve(strict=True)==Path(WORKING_APKSIG),'EXACT_SIGNER_MANIFEST_CLASSPATH')
            self.alias={'path':str(alias),'link':os.readlink(alias),
                        'f9':[getattr(st,k) for k in META],'resolved':WORKING_APKSIG}
            self.guard()
        except BaseException:
            self.close()
            raise
    def guard(self):
        need(not self.closed and set(self.fds)==set(WORKING_BUILD_TOOLS),
             'WORKING_TOOLS_MUST_REMAIN_HELD')
        for name,fd in self.fds.items():
            row=self.refs[name];p=Path(row['path'])
            need([getattr(os.fstat(fd),k) for k in META]==row['f9']==
                 [getattr(p.lstat(),k) for k in META],'HELD_WORKING_TOOL_CHANGED')
        p=Path(self.alias['path'])
        need([getattr(p.lstat(),k) for k in META]==self.alias['f9'] and
             os.readlink(p)==self.alias['link'] and
             p.resolve(strict=True)==Path(self.alias['resolved']),
             'SIGNER_MANIFEST_CLASSPATH_CHANGED')
    def comparison(self):
        self.guard()
        for name,fd in self.fds.items():
            row=self.refs[name];raw=os.pread(fd,row['bytes']+1,0)
            need(len(raw)==row['bytes'] and digest(raw)==row['sha256'],
                 'WORKING_TOOL_COMPLETE_BYTE_BOOKEND_CHANGED')
        self.guard()
        return {'schema':'droidloom.working-build-toolchain.v1','files':self.refs,
                'signer_classpath':self.alias}
    def close(self):
        errors=[]
        for fd in self.fds.values():
            try:os.close(fd)
            except OSError as error:errors.append(error)
        self.fds.clear();self.closed=True
        if errors:raise errors[0]

def _enter_working_build_directory(directory_fd,expected,proof_write):
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    os.fchdir(directory_fd);os.close(directory_fd)
    os.setgroups([]);os.setgid(1000);os.setuid(1000)
    status=Path('/proc/self/status').read_text().splitlines()
    capabilities=[line.split()[1] for line in status
                  if line.startswith(('CapEff:','CapPrm:','CapAmb:'))]
    if len(capabilities)!=3 or any(int(v,16)!=0 for v in capabilities):
        raise RuntimeError('BUILD_MUST_DROP_ALL_PROCESS_CAPABILITIES')
    cwd=os.stat('.');identity=tuple(getattr(cwd,k) for k in META)
    uids=os.getresuid();gids=os.getresgid();groups=os.getgroups()
    if identity!=expected or uids!=(1000,1000,1000) or gids!=(1000,1000,1000) or groups:
        raise RuntimeError('ACTUAL_BUILD_CWD_OR_IDS_DIFFER')
    raw=BUILD_PROOF.pack(b'DWB1',os.getpid(),*uids,*gids,len(groups),*identity)
    if os.write(proof_write,raw)!=len(raw):raise RuntimeError('BUILD_PREEXEC_PROOF_SHORT')
    os.close(proof_write)

class WorkingBuildDirectory:
    def __init__(self,live,path):
        admitted=_working_build_location(live,path,preparation=True)
        need(admitted is not None,'ACTUAL_WORKING_BUILD_OWNER_REQUIRED')
        self.live=live;self.root=Path(path);self.runtime,self.case=admitted
        self.pid=os.getpid();self.fd=None;self.closed=False;self.tools=None
        self.last_proof=None;self.last_error=None
        need(self.root.resolve()==self.root,'NO_WORKING_BUILD_ALIAS')
        for parent in self.root.parents:
            st=parent.lstat()
            need(stat.S_ISDIR(st.st_mode) and st.st_uid==st.st_gid==0
                 and not st.st_mode&0o022,'ROOT_PROTECTED_BUILD_ANCESTORS_REQUIRED')
            if parent==self.runtime:
                need(stat.S_IMODE(st.st_mode)==0o700,'WORKING_EVIDENCE_REMAINS_PRIVATE')
                break
        self.fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            self.identity=tuple(getattr(os.fstat(self.fd),k) for k in META)
            self.tools=WorkingBuildTools()
            self.guard()
        except BaseException:self.close();raise
    def guard(self):
        need(not self.closed and self.pid==os.getpid() and self.fd is not None,
             'SAME_HELD_BUILD_CONTROLLER_REQUIRED')
        self.live.guard()
        need(self.tools is not None,'ACTUAL_WORKING_TOOL_INPUTS_REQUIRED')
        self.tools.guard()
        held=tuple(getattr(os.fstat(self.fd),k) for k in META)
        named=tuple(getattr(self.root.lstat(),k) for k in META)
        need(held==named and held[:5]==self.identity[:5] and
             held[2]==stat.S_IFDIR|0o700 and held[3]==held[4]==1000,
             'SAME_PRIVATE_UID1000_BUILD_DIRECTORY_REQUIRED')
        return held
    def close(self):
        try:
            if self.tools is not None:self.tools.close();self.tools=None
        finally:
            if self.fd is not None:os.close(self.fd);self.fd=None
            self.closed=True
    def spawn(self,argv,env,input_fd,output_fd,error_fd):
        before=self.guard();proof_read,proof_write=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK)
        process=None;self.last_proof=None;self.last_error=None
        def enter():
            _enter_working_build_directory(self.fd,before,proof_write)
        try:
            process=subprocess.Popen(list(argv),stdin=input_fd,stdout=output_fd,stderr=error_fd,
                env=env,close_fds=True,pass_fds=(self.fd,proof_write),
                start_new_session=True,preexec_fn=enter)
            os.close(proof_write);proof_write=None
            # Popen returns only after exec or its private preexec error report.
            # The sole writer was closed before exec; compilers never inherit it.
            raw=os.read(proof_read,BUILD_PROOF.size+1)
            need(len(raw)==BUILD_PROOF.size and os.read(proof_read,1)==b'',
                 'EXACT_SINGLE_CLOSED_BUILD_PREEXEC_FRAME_REQUIRED')
            fields=BUILD_PROOF.unpack(raw)
            need(fields[0]==b'DWB1' and fields[1]==process.pid and
                 fields[2:5]==fields[5:8]==(1000,1000,1000) and fields[8]==0
                 and fields[9:]==before,'ACTUAL_PREEXEC_PID_IDS_AND_HELD_CWD_REQUIRED')
            self.guard()
            self.last_proof={'schema':'droidloom.working-host-build-preexec.v1',
                'runtime_evidence_directory':str(self.runtime),'case':self.case,
                'directory':str(self.root),'directory_f9_before':list(before),
                'pid':process.pid,'uids':list(fields[2:5]),'gids':list(fields[5:8]),
                'supplementary_groups':[],'cwd_f9':list(fields[9:]),
                'fixed_frame_bytes':len(raw),'proof_eof_before_command_capture':True}
        except BaseException as error:
            if process is None:raise
            # Never lose an already created child: the ordinary capture/reaper
            # still receives it and performs its original bounded retirement.
            self.last_error=_error('working_build_preexec',error)
        finally:
            for descriptor in (proof_write,proof_read):
                if descriptor is None:continue
                try:os.close(descriptor)
                except BaseException as error:
                    if process is None:raise
                    self.last_error=_error('working_build_preexec_descriptor_close',error)
        return process

def working_build_context(path):
    live=native_channel_module().ComparisonChannel()
    if live.working_runtime_root() is None:return None
    return WorkingBuildDirectory(live,path)

def verify_working_build_record(record,logical,root,environment):
    live=native_channel_module().ComparisonChannel()
    admitted=_working_build_location(live,root,preparation=False)
    if admitted is None:return False
    runtime,case=admitted;proof=record.get('working_build_preexec')
    need(type(proof) is dict and set(proof)=={'schema','runtime_evidence_directory','case',
         'directory','directory_f9_before','pid','uids','gids','supplementary_groups','cwd_f9',
         'fixed_frame_bytes','proof_eof_before_command_capture'} and
         proof['schema']=='droidloom.working-host-build-preexec.v1' and
         proof['runtime_evidence_directory']==str(runtime) and proof['case']==case and
         proof['directory']==str(root) and proof['pid']==record['lifecycle']['pid'] and
         proof['uids']==proof['gids']==[1000,1000,1000] and proof['supplementary_groups']==[] and
         proof['cwd_f9']==proof['directory_f9_before'] and len(proof['cwd_f9'])==9 and
         proof['fixed_frame_bytes']==BUILD_PROOF.size and proof['proof_eof_before_command_capture'] is True,
         'REAL_RETIRED_WORKING_BUILD_PREEXEC_REQUIRED')
    now=Path(root).lstat()
    need(proof['cwd_f9'][:5]==[getattr(now,k) for k in META[:5]] and
         now.st_mode==stat.S_IFDIR|0o700 and now.st_uid==now.st_gid==1000 and
         record['argv']==working_build_argv(logical,root,case) and
         record['working_build_environment']==environment and
         record['authority_fds_passed']==[] and record['comparison_fds_passed']==[],
         'SAME_BUILD_DIRECTORY_ARGV_ENVIRONMENT_AND_NO_AUTHORITY_FDS')
    tools=WorkingBuildTools()
    try:
        need(record.get('working_build_toolchain')==tools.comparison(),
             'ACTUAL_FIXED_WORKING_TOOLCHAIN_BOOKEND_REQUIRED')
    finally:tools.close()
    live.guard()
    return True


class CommandCancelled(RuntimeError):pass
class CommandFailure(RuntimeError):
    def __init__(self,observation):
        super().__init__('BUSINESS_HOST_COMMAND_FAILED');self.command_observation=observation
class HostOutcomeUnknown(CommandFailure):
    """No automatic retry, rollback, App task removal or UID signal follows."""
    def __init__(self,observation):
        super().__init__(observation);self.args=('HOST_RETIREMENT_OR_EVIDENCE_UNKNOWN',)
class Cancellation:
    def __init__(self):
        self.previous={};self.retiring=False;self.signals=[];self.count=0
    def handler(self,number,frame):
        self.count+=1
        if len(self.signals)<16:self.signals.append({'signal':number,'during_retirement':self.retiring})
        if not self.retiring:
            self.retiring=True
            raise CommandCancelled('OWNED_COMMAND_CANCELLED')
    def begin(self):
        try:
            for number in (signal.SIGINT,signal.SIGTERM):
                self.previous[number]=signal.getsignal(number);signal.signal(number,self.handler)
        except BaseException:
            self.restore();raise
    def enter_retirement(self,deadline=None):self.retiring=True
    def restore(self):
        errors=[]
        for number,old in self.previous.items():
            try:signal.signal(number,old)
            except BaseException as error:errors.append(type(error).__name__)
        self.previous.clear();need(not errors,'SIGNAL_HANDLER_RESTORE_FAILED')

def _error(stage,error):
    return {'stage':stage,'type':type(error).__name__,'errno':getattr(error,'errno',None)}
def retirement_complete(record,reaper,finish_error):
    return (finish_error is None and all(record.get(k) is True for k in
        ('child_started','child_reaped','owned_tree_cleanup_complete','all_acquired_fds_closed','retirement_within_deadline'))
        and record.get('remaining_owned_children')==[] and
        all(reaper.get(k) is True for k in ('begin_passed','restored','final_children_empty')))

def run_recorded(name,argv,timeout,evidence,guard,*,protected_pids,mutation=False,
                 pass_fds=(),host_env=None,check=True,output_bound=1024*1024,deferred_post_guard=False,
                 private_output=False,input_bytes=b'',image_channel=False,working_build=None):
    """guard(action_attempted=bool) is the caller's full new recorder/Main fence.
    deferred_post_guard preserves BoundArun's command-result, lease-release,
    then mandatory post-guard order. Host tree retirement never clears Binder
    App outcome uncertainty; the real recorder observes its owned task separately.
    """
    need(type(name) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name),'EVIDENCE_NAME_REQUIRED')
    need(type(argv) in (list,tuple) and 0<len(argv)<=128 and all(type(x) is str and x and
         '\0' not in x and len(x.encode())<=65536 for x in argv),'FIXED_ARGV_REQUIRED')
    need(type(timeout) in (int,float) and 0<timeout<=3600,'FINITE_TIMEOUT_REQUIRED')
    need(type(image_channel) is bool and type(output_bound) is int and
         (output_bound in (33554432,61516460) if image_channel else 0<output_bound<=16*1024*1024),
         'NARROW_IMAGE_OR_ORDINARY_OUTPUT_BOUND_REQUIRED')
    need(type(input_bytes) is bytes and len(input_bytes)<=196608,'BOUNDED_STDIN_REQUIRED')
    need(type(mutation) is bool and type(check) is bool and type(deferred_post_guard) is bool,'EXPLICIT_COMMAND_MODE_REQUIRED')
    need(type(private_output) is bool,'EXPLICIT_PRIVATE_OUTPUT_POLICY_REQUIRED')
    need(not deferred_post_guard or (not check and len(pass_fds)==7),'DEFERRED_GUARD_ONLY_FOR_HELD_TRANSPORT')
    need(len(pass_fds)==len(set(pass_fds)) and len(pass_fds) in (0,7) and
         all(type(fd) is int and fd>=3 for fd in pass_fds),'EXACT_HELD_DESCRIPTOR_SET_REQUIRED')
    for fd in pass_fds:os.fstat(fd)
    need(type(protected_pids) in (list,tuple,set) and protected_pids and
         all(type(pid) is int and pid>1 for pid in protected_pids),'ACTUAL_PROTECTED_MAIN_PIDS_REQUIRED')
    env=dict(ENV if host_env is None else host_env)
    need(len(env)<=64 and all(type(k) is str and type(v) is str and k and '\0' not in k+v and
         '=' not in k and len(k)+len(v)<=131072 for k,v in env.items()),'EXPLICIT_HOST_ENV_REQUIRED')
    evidence=Path(evidence);st=evidence.lstat()
    need(evidence.is_absolute() and evidence.resolve()==evidence and stat.S_ISDIR(st.st_mode) and
         st.st_uid==os.geteuid() and not st.st_mode&0o077,'PRIVATE_OWNED_EVIDENCE_REQUIRED')
    comparison=native_channel_module()
    live=comparison.ComparisonChannel()
    if working_build is not None:
        need(type(working_build) is WorkingBuildDirectory and not pass_fds and not mutation
             and not deferred_post_guard and not private_output and not image_channel
             and input_bytes==b'' and set(env)=={'PATH','JAVA_HOME','LANG','LC_ALL'},
             'EXACT_SOURCE_OWNED_UNPRIVILEGED_BUILD_BRANCH_REQUIRED')
        admitted=_working_build_location(live,working_build.root,preparation=True)
        need(admitted==(working_build.runtime,working_build.case) and working_build.live.raw==live.raw,
             'BUILD_CONTEXT_MUST_BORROW_THIS_ACTUAL_SEALED_PREPARATION')
        working_build.guard()
        argv=working_build_argv(argv,working_build.root,working_build.case)
    env,comparison_inherit=comparison.inherit_for_host(argv,env,pass_fds)
    # The original transport contract is still exactly zero or seven authority
    # descriptors. The separate two comparison descriptors are host-only.
    comparison_fds=tuple(fd for fd in comparison_inherit if fd not in pass_fds)
    need(len(comparison_fds) in (0,2),'EXACT_HOST_COMPARISON_DESCRIPTOR_PAIR_REQUIRED')
    need(working_build is None or not comparison_inherit,'BUILD_EXEC_INHERITS_NO_MAIN_CHANNEL_OR_NAMESPACE_FDS')
    capture=load_capture(True) if image_channel else load_capture();before=guard(action_attempted=False)
    remaining=live.remaining(3608)
    need(remaining>8,'ORIGINAL_NATIVE_BUDGET_CANNOT_COVER_OWNED_RETIREMENT')
    timeout=min(timeout,remaining-8)

    write_new(evidence/(name+'.intent.json'),{'schema':'pocket4-business-host-intent-v1',
        'argv':list(argv),'timeout_seconds':timeout,'output_bound_per_stream':output_bound,
        'authority_fds_passed':list(pass_fds),'comparison_fds_passed':list(comparison_fds),'mutation':mutation,'Main_before':before,
        'private_output':private_output,
        'stdin_bytes':len(input_bytes),'stdin_sha256':digest(input_bytes),
        'capture_sha256':IMAGE_CAPTURE_SHA if image_channel else CAPTURE_SHA,'image_channel':image_channel,
        'automatic_retry':False,'Binder_task_cleanup_authorized':False})
    value={'schema':'pocket4-business-host-result-v1','name':name,'argv':list(argv),'Main_before':before,'Main_after':None,
        'host_retirement_proved':False,'evidence_complete':False,'action_attempted':False,
        'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False,'Android_outcome_unknown':False,
        'automatic_retry':False,'errors':[]}
    value['private_output']=private_output
    reaper=capture.OwnChildReaper(protected_pids=tuple(protected_pids));cancel=Cancellation()
    record={};out=err=None;first=finish_error=None;began=False
    try:
        cancel.begin();reaper.begin();began=True;now=time.monotonic()
        def factory(input_fd,output_fd,error_fd,bound):
            if working_build is not None:
                return working_build.spawn(argv,env,input_fd,output_fd,error_fd)
            def core_only():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            return subprocess.Popen(list(argv),stdin=input_fd,stdout=output_fd,stderr=error_fd,
                env=env,close_fds=True,pass_fds=comparison_inherit,start_new_session=True,preexec_fn=core_only)
        record,out,err,first=capture.invoke_owned(reaper,factory,input_bytes,min(now+timeout,live.deadline-8),min(now+timeout+8,live.deadline),
            output_bound=output_bound,cleanup_enter=cancel.enter_retirement,retirement_grace=5)
    except BaseException as error:
        first=error;value['errors'].append(_error('owned_capture',error))
    finally:
        cancel.enter_retirement()
        if began:
            try:reaper.finish()
            except BaseException as error:
                finish_error=error;value['errors'].append(_error('owned_scope_finish',error))
        try:cancel.restore()
        except BaseException as error:
            finish_error=finish_error or error;value['errors'].append(_error('signal_restore',error))
    value.update(lifecycle=record,subreaper=dict(reaper.record),cancellation={'count':cancel.count,'signals':cancel.signals},
        returncode=record.get('returncode'),timed_out=record.get('timed_out',False),spawned=record.get('child_started',False),
        action_attempted=mutation and record.get('child_started',False))
    value['host_retirement_proved']=retirement_complete(record,reaper.record,finish_error)
    if working_build is not None:
        value['working_build_preexec']=working_build.last_proof
        value['working_build_environment']=env
        value['authority_fds_passed']=list(pass_fds)
        value['comparison_fds_passed']=list(comparison_fds)
        if working_build.last_error is not None:value['errors'].append(working_build.last_error)
        try:
            working_build.guard()
            value['working_build_toolchain']=working_build.tools.comparison()
            need(value['working_build_preexec'] is not None and
                 value['working_build_preexec']['pid']==record.get('pid'),
                 'ACTUAL_BUILD_CHILD_MUST_MATCH_RETIRED_PIDFD_OWNER')
        except BaseException as error:value['errors'].append(_error('working_build_readback',error))
    if first is not None:value['first_error']=record.get('first_error') or _error('owned_capture',first)
    value['Android_outcome_unknown']=bool(value['action_attempted'])
    for label,raw in (('stdout',out),('stderr',err)):
        try:
            need(type(raw) is bytes,'OUTPUT_NOT_CAPTURED')
            value[label]=({'bytes':len(raw),'sha256':digest(raw),'persisted':False} if private_output
                          else write_new(evidence/(name+'.'+label),raw))
        except BaseException as error:value['errors'].append(_error(label+'_evidence',error))
    if not deferred_post_guard:
        try:value['Main_after']=guard(action_attempted=value['action_attempted'])
        except BaseException as error:value['errors'].append(_error('Main_after',error))
    value['post_guard_deferred_to_held_transport']=deferred_post_guard
    value['evidence_complete']=all(k in value for k in ('stdout','stderr'))
    try:write_new(evidence/(name+'.result.json'),value)
    except BaseException as error:
        value['evidence_complete']=False;value['errors'].append(_error('result_evidence',error))
    if not value['host_retirement_proved'] or not value['evidence_complete']:
        raise HostOutcomeUnknown(value) from (first or finish_error)
    result=subprocess.CompletedProcess(list(argv),record.get('returncode'),out,err)
    result.host_timed_out=bool(record.get('timed_out'));result.recorder_spawned=bool(record.get('child_started'))
    result.recorder_joined=result.host_tree_retired=value['host_retirement_proved'];result.command_observation=value
    nonzero_only=(record.get('returncode') not in (None,0) and
        (record.get('first_error') or {}).get('stage')=='child_exit' and not record.get('secondary_errors') and
        record.get('output_capture',{}).get('complete') is True)
    result.recorder_errors=list(value['errors'])
    if first is not None and not nonzero_only:result.recorder_errors.append(value['first_error'])
    if cancel.count and not result.recorder_errors:result.recorder_errors.append({'stage':'cancelled','type':'CommandCancelled'})
    if check and (result.returncode!=0 or result.recorder_errors):raise CommandFailure(value) from first
    return result

def run_cli(name,argv,timeout,evidence,guard,*,protected_pids,mutation=False):
    result=run_recorded(name,argv,timeout,evidence,guard,protected_pids=protected_pids,mutation=mutation)
    try:return parse(result.stdout)
    except BaseException as error:
        error.command_observation=result.command_observation
        error.action_attempted=result.command_observation['action_attempted']
        error.outcome_unknown=error.action_attempted;error.automatic_retry=False
        raise
