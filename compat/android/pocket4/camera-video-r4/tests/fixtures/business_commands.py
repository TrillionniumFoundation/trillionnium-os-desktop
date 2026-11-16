"""Bounded host commands for new business flows; no Android task cleanup authority."""
import hashlib,json,os,re,resource,signal,stat,subprocess,time,types
from pathlib import Path
CAPTURE_PATH=Path('/home/alex/work/pocket4-android-final/qualification/bounded_host_capture.py')
CAPTURE_SHA='bb6d818cbe68b6976da57a996d17b6333cdf5dae03fa743fd0cb7f27f89c2bf3'
IMAGE_CAPTURE_PATH=Path(__file__).resolve().with_name('business_image_capture.py')
IMAGE_CAPTURE_SHA='5cae43fc39b12f25517af9aabac12a766137363c395e3b1a56e279acec7ea1a8'
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
                 private_output=False,input_bytes=b'',image_channel=False):
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
    capture=load_capture(True) if image_channel else load_capture();before=guard(action_attempted=False)
    write_new(evidence/(name+'.intent.json'),{'schema':'pocket4-business-host-intent-v1',
        'argv':list(argv),'timeout_seconds':timeout,'output_bound_per_stream':output_bound,
        'authority_fds_passed':list(pass_fds),'mutation':mutation,'Main_before':before,
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
            def core_only():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            return subprocess.Popen(list(argv),stdin=input_fd,stdout=output_fd,stderr=error_fd,
                env=env,close_fds=True,pass_fds=tuple(pass_fds),start_new_session=True,preexec_fn=core_only)
        record,out,err,first=capture.invoke_owned(reaper,factory,input_bytes,now+timeout,now+timeout+8,
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
