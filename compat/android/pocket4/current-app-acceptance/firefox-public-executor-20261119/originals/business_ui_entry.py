#!/usr/bin/python3 -I
"""Independent final-business entry for the exact existing client/backend.

Only a live, nonce-bound recorder command can enter. Existing UI parsing,
accessibility readback, original action flock and scoped screenshot processing
remain in the original pinned modules. Every host child uses bounded capture.
No legacy baseline/scope, replay, launch, task removal or UID signal is admitted.
"""
import argparse,base64,fcntl,functools,hashlib,io,json,os,re,stat,subprocess,sys,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
APP={'path':'/usr/local/bin/android-app','bytes':37467,
     'sha256':'4823c1a6d2434a9d102b2b6dbc369dd0cf192e7fc0a31384a68dddb370d0a340'}
BACKEND={'path':'/usr/local/libexec/android-digitalis-observe-helper','bytes':36404,
     'sha256':'76e9875d141f69976cbbafe469aa13439cf99c3214bc479a0c80cda740c8dcfa'}
CONSUMERS={'path':'/home/alex/work/pocket4-android-final/consumers/manifest.json','bytes':3621,
     'sha256':'b8cdea5cff9e67d87cfc5a11418068e25bfec5975ed9bae51b7547e936e3729b'}
RUNNER='local.pocket4.actions.v2/.ActionRunner'
MAX_PIPE=16*1024*1024
PNG_PIPE=32*1024*1024
BASE64_PNG_LIMIT=((PNG_PIPE+2)//3)*4
JSON_METADATA_LIMIT=16*1024*1024
ENCODED_PNG_PIPE=BASE64_PNG_LIMIT+JSON_METADATA_LIMIT
def need(value,code):
    if not value:raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def validate_image_envelope(raw,parse):
    """The wire budget separately covers one exact 32 MiB PNG and JSON metadata.
    Raw private pixels stay in memory; original client decoding/writing follows.
    """
    need(type(raw) is bytes and 0<len(raw)<=ENCODED_PNG_PIPE,'ENCODED_IMAGE_WIRE_BOUND')
    value=parse(raw);need(type(value) is dict,'IMAGE_BACKEND_JSON_OBJECT_REQUIRED')
    encoded=value.get('screenshot_png_base64')
    need(type(encoded) is str and 0<len(encoded)<=BASE64_PNG_LIMIT and encoded.isascii(),'BASE64_PNG_BOUND')
    need(len(raw)-len(encoded)<=JSON_METADATA_LIMIT,'IMAGE_JSON_METADATA_BOUND')
    decoded=base64.b64decode(encoded,validate=True)
    need(0<len(decoded)<=PNG_PIPE and decoded.startswith(b'\x89PNG\r\n\x1a\n'),'DECODED_PNG_BOUND_OR_SIGNATURE')
    return {'png_bytes':len(decoded),'base64_bytes':len(encoded),'json_metadata_bytes':len(raw)-len(encoded),
            'wire_bytes':len(raw),'png_sha256':digest(decoded),'whole_app_business_accepted':False}
def basic_read(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and 0<a.st_size<=limit,'PRIVATE_INPUT_FILE_REQUIRED')
        raw=bytearray()
        while True:
            block=os.read(fd,min(65536,limit+1-len(raw)))
            if not block:break
            raw.extend(block);need(len(raw)<=limit,'INPUT_BOUND')
        b=os.fstat(fd)
        need(len(raw)==a.st_size and all(getattr(a,k)==getattr(b,k) for k in
             ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')),'INPUT_CHANGED')
        return bytes(raw)
    finally:os.close(fd)
def module(ref,scope,name):
    raw=scope.read_ref(ref);value=types.ModuleType(name);value.__file__=ref['path']
    exec(compile(raw,ref['path'],'exec'),value.__dict__);return value

def final_consumer_contract(manifest,consumers):
    """The final transaction's six consumers remain one pinned source cohort.

    This is a source contract, never a claim that a pending transaction ran.
    ScopeBinding's independent actual baseline requires the committed final
    transaction before this function is reachable from either UI entry.
    """
    need(consumers.get('schema')=='pocket4-consumer-owner-fix-v1' and
         type(consumers.get('files')) is list and len(consumers['files'])==6,
         'ORIGINAL_SIX_CONSUMER_COHORT_REQUIRED')
    rows=consumers['files'];targets={row['path'] for row in rows}
    need(len(targets)==6 and {APP['path'],BACKEND['path']}<=targets,
         'EXACT_FINAL_CLIENT_BACKEND_COHORT_REQUIRED')
    payload=manifest.get('payload');need(type(payload) is list,'ACTUAL_FINAL_PAYLOAD_REQUIRED')
    installed=[]
    for row in rows:
        matches=[p for p in payload if p.get('install_target')==row['path']]
        need(len(matches)==1,'SIX_CONSUMER_DEPLOYMENT_TARGET_ABSENT_OR_AMBIGUOUS')
        item=matches[0];candidate=item.get('candidate_input',{})
        need(item.get('role')=='host_android_consumer' and item.get('bytes')==row['bytes'] and
             item.get('sha256')==row['new_sha256'] and item.get('install_mode')==row['mode']==0o755 and
             item.get('install_owner')=={'uid':0,'gid':0} and row['uid']==row['gid']==0 and
             candidate.get('path')==row['candidate'] and candidate.get('sha256')==row['new_sha256'] and
             candidate.get('manifest_path')==CONSUMERS['path'] and candidate.get('manifest_sha256')==CONSUMERS['sha256'],
             'FINAL_CONSUMER_SOURCE_OR_INSTALL_CONTRACT_CHANGED')
        installed.append({'path':row['path'],'bytes':row['bytes'],'sha256':row['new_sha256']})
    need(APP in installed and BACKEND in installed,'FINAL_UI_ENTRY_PINS_DIFFER_FROM_DEPLOYMENT')
    return installed

def verify_final_consumers(c):
    consumers=c.scope.parse(c.scope.read_ref(CONSUMERS,131072))
    rows=final_consumer_contract(c.binding.baseline.docs['deployment_manifest'],consumers)
    for row in rows:
        c.scope.read_ref(row,1024*1024)
        info=Path(row['path']).lstat()
        need(info.st_uid==info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o755,
             'ACTUAL_FINAL_CONSUMER_INSTALL_IDENTITY_CHANGED')
    return {'manifest':CONSUMERS,'installed_sources':rows,'runtime_UI_qualified':False,
            'whole_app_business_accepted':False}

def logical_argv(request,package,step):
    need(type(request) is dict and set(request)<={'op','selector','value','index','accessibility_mode','method'},
         'ORIGINAL_UI_REQUEST_FIELDS_REQUIRED')
    op=request.get('op');need(op in ('dump','find','click','set-text','observe'),'ORIGINAL_UI_OPERATION_REQUIRED')
    argv=[APP['path'],'--interactive-production',op,'--package',package]
    selectors=request.get('selector',{})
    need(type(selectors) is dict,'SELECTOR_OBJECT_REQUIRED')
    bools={'focused','editable','enabled','clickable','scrollable','selected','checked'}
    strings={'text','contains','id','desc','class'}
    for key,value in selectors.items():
        need(key in bools|strings,'ORIGINAL_SELECTOR_REQUIRED')
        if type(value) is bool:
            need(key in bools,'BOOLEAN_SELECTOR_REQUIRED');argv+=['--'+('' if value else 'no-')+key]
        else:
            need(key in strings and type(value) is str,'STRING_SELECTOR_REQUIRED');argv+=['--'+key,value]
    for key in ('index','accessibility_mode','method'):
        if key in request:argv+=['--'+key.replace('_','-'),str(request[key])]
    if op=='set-text':
        need(type(request.get('value')) is str,'EXACT_TEXT_VALUE_REQUIRED');argv+=['--',request['value']]
    if op=='observe':argv+=['--output',str(step/'observation.png')]
    return argv

def entry_argv(scope_ref,mode,step,command,forwarded=()):
    return ['/usr/bin/python3','-I',str(HERE/'business_ui_entry.py'),mode,
        '--scope',scope_ref['path'],'--expect-scope-sha256',scope_ref['sha256'],
        '--step',step,'--command',command]+(['--',*forwarded] if mode=='client' else [])

def active_command_phase(root,step,command):
    need(not os.path.lexists(step/'result.json') and not os.path.lexists(step/(command+'.result.json')) and
         not os.path.lexists(root/'hold.json'),'COMPLETED_OR_HELD_COMMAND_CANNOT_BE_REPLAYED')
    fd=os.open(root/'flow.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0,'EXISTING_PRIVATE_FLOW_LOCK_REQUIRED')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:pass
        else:
            fcntl.flock(fd,fcntl.LOCK_UN);raise RuntimeError('RECORDER_PARENT_FLOW_NOT_ACTIVE')
    finally:os.close(fd)

def load_context(args):
    need(os.getuid()==os.geteuid()==0,'EXISTING_ROOT_OPERATOR_REQUIRED')
    raw=basic_read(args.scope,131072);need(digest(raw)==args.expect_scope_sha256,'EXTERNAL_NEW_SCOPE_PIN_REQUIRED')
    provisional=json.loads(raw);support=provisional['support_manifest']
    manifest_raw=basic_read(support['path'],131072)
    need(len(manifest_raw)==support['bytes'] and digest(manifest_raw)==support['sha256'],'SUPPORT_MANIFEST_PIN_CHANGED')
    manifest=json.loads(manifest_raw);entry=manifest['files']['business_ui_entry.py']
    need(digest(basic_read(__file__,1024*1024))==entry['sha256'],'FROZEN_NEW_ENTRY_SOURCE_REQUIRED')
    spec=manifest['files']['business_scope.py'];path=HERE/'business_scope.py';code=basic_read(path,1024*1024)
    need(len(code)==spec['bytes'] and digest(code)==spec['sha256'],'FROZEN_SCOPE_SOURCE_REQUIRED')
    scope=types.ModuleType('final_business_entry_scope');scope.__file__=str(path);exec(compile(code,str(path),'exec'),scope.__dict__)
    value=scope.parse(raw);scope_ref={'path':str(args.scope),'bytes':len(raw),'sha256':digest(raw)}
    need(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',args.step) and re.fullmatch(r'command-[0-9]{3,6}',args.command),
         'EXACT_RECORDER_STEP_COMMAND_REQUIRED')
    root=scope.private_dir(value['flow_root']);scope.private_dir(root/'steps');step=scope.private_dir(root/'steps'/args.step)
    need(Path(scope_ref['path'])==root/'scope.json','SCOPE_OUTSIDE_NEW_FLOW')
    active_command_phase(root,step,args.command)
    step_raw=basic_read(step/'intent.json',131072);step_intent=scope.parse(step_raw)
    logical_raw=basic_read(step/(args.command+'.logical.json'),131072);logical=scope.parse(logical_raw)
    parent_raw=basic_read(step/(args.command+'.intent.json'),2*1024*1024);parent=scope.parse(parent_raw)
    need(step_intent['scope']==value and step_intent['operation']=='ui' and type(step_intent['request']) is dict,
         'EXACT_NEW_ORIGINAL_UI_STEP_REQUIRED')
    op=step_intent['request'].get('op');mutation=op in ('click','set-text')
    expected=logical_argv(step_intent['request'],value['package'],step)
    need(logical=={'schema':'pocket4-final-ui-logical-command-v1','scope_sha256':scope_ref['sha256'],'argv':expected,
         'mutation':mutation,'label':'Existing android-app CLI','automatic_retry':False} and
         step_intent['mutation'] is mutation,'LOGICAL_COMMAND_NOT_THIS_ORIGINAL_STEP')
    need(parent['schema']=='pocket4-business-host-intent-v1' and parent['argv']==entry_argv(scope_ref,'client',args.step,args.command,expected[1:]) and
         parent['mutation'] is mutation and parent['authority_fds_passed']==[] and parent['stdin_bytes']==0,
         'PHYSICAL_ENTRY_NOT_THE_ACTIVE_DURABLE_INTENT')
    if op=='observe':need(not os.path.lexists(step/'observation.png'),'OBSERVATION_DESTINATION_ALREADY_EXISTS')
    guard_source=value['guard_source'];guard_module=module(guard_source,scope,'new_packet_existing_ui_guard')
    guard_function=getattr(guard_module,'existing_ui_guard',None)
    need(callable(guard_function),'NEW_PACKET_MUST_EXPORT_ITS_FULL_EXISTING_UI_GUARD')
    entry_context={'scope':value,'scope_ref':scope_ref,'step':str(step),'operation':op,'mutation':mutation,
        'logical_command':logical,'logical_sha256':digest(logical_raw),'parent_intent_sha256':digest(parent_raw)}
    full_guard=functools.partial(guard_function,entry_context=entry_context)
    binding=scope.ScopeBinding(scope_ref=scope_ref,baseline_ref=value['business_baseline'],
        qualification_ref=value['business_qualification'],support_ref=support,full_guard=full_guard)
    binding.guard()
    for ref in (APP,BACKEND):scope.read_ref(ref)
    context=types.SimpleNamespace(scope=scope,binding=binding,root=root,step=step,operation=op,mutation=mutation,
        logical=logical,parent=parent,parent_sha256=digest(parent_raw),args=args,
        journal=step/(args.command+'-bound'))
    context.consumer_source_binding=verify_final_consumers(context)
    return context

def admit_android(argv,timeout,operation,package,action_used):
    need(type(argv) in (list,tuple) and type(timeout) in (int,float) and 0<timeout<=70,'BOUNDED_ORIGINAL_ANDROID_CALL_REQUIRED')
    argv=list(argv)
    if argv==['/system/bin/cmd','activity','stack','list']:
        need(timeout<=20,'TASK_READ_TIMEOUT');return False,False,None
    if argv==['/system/bin/dumpsys','window','displays']:
        need(operation in ('click','observe') and timeout==15,'FOREGROUND_ONLY_FOR_ORIGINAL_CAPTURE');return False,True,None
    if argv==['/system/bin/screencap','-p']:
        need(operation in ('click','observe') and timeout==20,'SCREEN_ONLY_FOR_ORIGINAL_CAPTURE');return False,True,None
    need(len(argv)==8 and argv[:6]==['/system/bin/am','instrument','-w','-r','-e','request'] and
         argv[7]==RUNNER and timeout==70,'ONLY_EXACT_EXISTING_ACTION_RUNNER_PROTOCOL')
    raw=base64.b64decode(argv[6],validate=True);need(0<len(raw)<=65536,'ORIGINAL_HELPER_REQUEST_BOUND')
    request=json.loads(raw);op=request.get('op')
    allowed={'dump':{'dump'},'find':{'find'},'set-text':{'set-text'},'click':{'meta','click'},'observe':{'meta','dump'}}[operation]
    need(op in allowed and request.get('expected_package')==package and
         type(request.get('display',0)) is int and request.get('display',0)==0,
         'ORIGINAL_HELPER_REQUEST_PACKAGE_OPERATION_CHANGED')
    mutation=op in ('click','set-text')
    need(not mutation or not action_used,'UI_MUTATION_ALREADY_DISPATCHED_NO_REPLAY')
    return mutation,True,request

class View:
    def __init__(self,c):
        self.context=c;self.binding=c.binding;self.target=None;self.index=0;self.action_attempted=False
        self.current_mutation=False;self.private_output=False;self.image_channel=False;self.action_used=False;self.closed=False
        base=self.binding.baseline;self.scope=c.scope
        raw=c.scope.read_ref({'path':str(base.data.READER_PATH),'bytes':22691,'sha256':base.data.READER_SHA})
        held=types.ModuleType('final_existing_ui_held_runtime');held.__file__=str(base.data.READER_PATH)
        exec(compile(raw,held.__file__,'exec'),held.__dict__)
        identity=base.value['framework_epoch']['binding']['processes']['init']
        proc=os.open('/proc/'+str(identity['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:actual=held.proc_identity_at(proc,identity['host_pid'],time.monotonic()+3)
        finally:os.close(proc)
        try:
            self.target=held.HeldTarget(actual,c.scope.HELPER_PATH,c.scope.HELD_HELPER_SHA256)
            self.transport=c.scope.BoundArun(target=self.target,environment=base.docs['final_baseline']['android_env'],
                binding=self.binding,record=self.record,runner=self.runner)
            # This new instance extends its complete ScopeBinding guard with
            # the original target/action-runner UID checks on every post guard.
            self.transport.guard=self.guard
            self.claim,self.claim_ref=c.scope.load_owned_task(self.binding)
            self.guard()
        except BaseException as error:
            if self.target is not None:
                try:self.target.close()
                except BaseException as secondary:error.add_note('HELD_TARGET_CLOSE_FAILED:'+type(secondary).__name__)
            raise
    def record(self,kind,value):
        return self.binding.commands.write_new(self.context.journal/('transport-%03d.%s.json'%(value['sequence'],kind)),value)
    def guard(self,*,action_attempted=False):
        need(not self.closed,'EXISTING_UI_VIEW_CLOSED')
        observation=self.binding.guard(action_attempted=action_attempted)
        self.target.verify()
        packages,_=self.target.read_file('/data/system/packages.list',1024*1024)
        expected={self.binding.scope['package']:self.binding.scope['uid'],'local.pocket4.actions.v2':10125};found={}
        for line in packages.decode('utf-8','strict').splitlines():
            fields=line.split()
            if fields and fields[0] in expected:
                need(len(fields)>=2 and fields[1].isdecimal() and fields[0] not in found,'ACTION_OR_TARGET_UID_AMBIGUOUS')
                found[fields[0]]=int(fields[1])
        del packages
        need(found==expected,'TARGET_OR_EXISTING_ACTION_HELPER_UID_CHANGED')
        if hasattr(self,'claim_ref'):self.scope.read_ref(self.claim_ref)
        return observation
    def runner(self,argv,**options):
        need(set(options)=={'stdout','stderr','timeout','env','pass_fds','close_fds'} and
             options['stdout']==options['stderr']==subprocess.PIPE and options['close_fds'] is True,'HELD_RUNNER_OPTIONS_CHANGED')
        self.index+=1
        try:
            result=self.binding.commands.run_recorded('held-%03d'%self.index,argv,options['timeout'],self.context.journal,self.guard,
                protected_pids=self.binding.baseline.protected_pids,mutation=self.current_mutation,
                pass_fds=options['pass_fds'],host_env=options['env'],check=False,deferred_post_guard=True,
                private_output=self.private_output,output_bound=PNG_PIPE if self.image_channel else MAX_PIPE,
                image_channel=self.image_channel)
            self.action_attempted|=result.command_observation['action_attempted'];return result
        except BaseException as error:
            row=getattr(error,'command_observation',{});self.action_attempted|=row.get('action_attempted',False)
            if row.get('host_retirement_proved') is not True:self.target.poison_unjoined_command()
            else:self.target.seal_admission()
            self.binding.hold(error);raise
    def android(self,argv,timeout=30):
        mutation,private,request=admit_android(argv,timeout,self.context.operation,self.binding.scope['package'],self.action_used)
        if mutation:
            self.binding.commands.write_new(self.context.journal/'UI-mutation-attempt.json',
                {'request_sha256':digest(json.dumps(request,sort_keys=True).encode()),'automatic_retry':False,
                 'scope_sha256':self.binding.scope_ref['sha256'],'Binder_task_cleanup_verified':False})
            self.action_used=True
        self.current_mutation,self.private_output=mutation,private
        self.image_channel=list(argv)==['/system/bin/screencap','-p']
        try:return self.transport(argv,timeout)
        finally:self.current_mutation=self.private_output=self.image_channel=False
    def check_owned_task(self):
        raw=self.android(['/system/bin/cmd','activity','stack','list'],20)
        tasks=self.scope.task_functions();roots,_=tasks.parse_stacks(raw.decode('utf-8','strict'))
        need(tasks.exact_leaf(roots,self.claim['task'],self.binding.scope['package']),'ACTUAL_OWNED_LEAF_TASK_CHANGED')
    def close(self):
        self.closed=True
        if self.target is not None:self.target.close()

class OriginalBackendHostCalls:
    """The exact original discover() still reads real facts; its CLI is bounded."""
    def __init__(self,c,view):self.c,self.view=c,view;self.count=0
    def __getattr__(self,name):return getattr(subprocess,name)
    def run(self,argv,**options):
        need(argv==['/usr/bin/droidloomctl','readiness','--json'] and
             options=={'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'timeout':8,'env':self.c.scope.HOST_ENV,'check':True},
             'NO_OTHER_ORIGINAL_BACKEND_HOST_COMMAND')
        self.count+=1
        return self.c.binding.commands.run_recorded('discover-%03d'%self.count,argv,8,self.c.journal,self.view.guard,
            protected_pids=self.c.binding.baseline.protected_pids,host_env=options['env'],output_bound=1048576)

class ClientBackendRedirect:
    def __init__(self,c):self.c=c;self.called=False
    def __getattr__(self,name):return getattr(subprocess,name)
    def run(self,argv,**options):
        c=self.c;need(not self.called and argv==['/usr/bin/sudo','-n',BACKEND['path']],'UNEXPECTED_OR_REPEATED_BACKEND_SPAWN')
        need(set(options)=={'input','stdout','stderr','timeout'} and options['stdout']==options['stderr']==subprocess.PIPE and
             options['timeout']==180,'EXACT_ORIGINAL_CLIENT_SUBPROCESS_CONTRACT')
        raw=options['input'];need(type(raw) is bytes and len(raw)<=65536 and raw.endswith(b'\n'),'EXACT_CLIENT_REQUEST_BOUND')
        request=c.scope.parse(raw);need(request.get('op')==c.operation and request.get('package')==c.binding.scope['package'],
                                       'ACTUAL_CLIENT_REQUEST_SCOPE_CHANGED')
        self.called=True;c.binding.commands.write_new(c.journal/'client-request.json',raw)
        physical=entry_argv(c.binding.scope_ref,'backend',c.args.step,c.args.command)
        c.binding.commands.write_new(c.journal/'client-dispatch.json',{'request_sha256':digest(raw),
            'parent_intent_sha256':c.parent_sha256,'execution_argv':physical,'automatic_retry':False})
        try:
            result=c.binding.commands.run_recorded('backend',physical,180,c.journal,c.binding.guard,
                protected_pids=c.binding.baseline.protected_pids,mutation=c.mutation,input_bytes=raw,
                output_bound=ENCODED_PNG_PIPE if c.operation=='observe' else MAX_PIPE,
                image_channel=c.operation=='observe')
            if c.operation=='observe':
                proof=validate_image_envelope(result.stdout,c.scope.parse)
                c.binding.commands.write_new(c.journal/'image-channel.json',proof)
            return result
        except BaseException as error:
            if 'result' in locals():error.command_observation=result.command_observation
            c.binding.hold(error)
            # Known nonzero output remains on disk with the actual first failure.
            raise

def client(c):
    need(c.args.original_argv==c.logical['argv'][1:],'CLIENT_ARGS_DIFFER_FROM_CURRENT_INTENT')
    c.journal.mkdir(mode=0o700)
    c.binding.commands.write_new(c.journal/'client.claim.json',{'parent_intent_sha256':c.parent_sha256,
        'scope_sha256':c.binding.scope_ref['sha256'],'automatic_retry':False})
    app=module(APP,c.scope,'exact_existing_client_new_business_entry');app.subprocess=ClientBackendRedirect(c)
    previous=sys.argv
    try:
        sys.argv=c.logical['argv'];return app.client()
    finally:sys.argv=previous

def backend(c):
    need(not c.args.original_argv,'NO_DIRECT_BACKEND_UI_ARGUMENTS')
    c.scope.private_dir(c.journal)
    claim=c.scope.parse(basic_read(c.journal/'client.claim.json',131072))
    need(claim=={'parent_intent_sha256':c.parent_sha256,'scope_sha256':c.binding.scope_ref['sha256'],'automatic_retry':False},
         'ACTUAL_NEW_CLIENT_CLAIM_CHANGED')
    raw=sys.stdin.buffer.readline(65537)
    need(len(raw)<=65536 and raw==basic_read(c.journal/'client-request.json',65536),'BACKEND_INPUT_IS_NOT_ACTUAL_CLIENT_REQUEST')
    dispatch=c.scope.parse(basic_read(c.journal/'client-dispatch.json',131072))
    need(dispatch=={'request_sha256':digest(raw),'parent_intent_sha256':c.parent_sha256,
        'execution_argv':entry_argv(c.binding.scope_ref,'backend',c.args.step,c.args.command),'automatic_retry':False},
        'ACTUAL_CLIENT_DISPATCH_CHANGED')
    c.binding.commands.write_new(c.journal/'backend.claim.json',{'request_sha256':digest(raw),
        'parent_intent_sha256':c.parent_sha256,'automatic_retry':False})
    view=None;primary=None;code=0;error=None
    try:
        view=View(c);view.check_owned_task()
        original=module(BACKEND,c.scope,'exact_original_backend_new_business_entry')
        original.arun=view.android;original.subprocess=OriginalBackendHostCalls(c,view)
        real_discover=original.discover
        def discover():
            view.guard();init,env,status=real_discover();base=c.binding.baseline.docs['final_baseline']
            need(init==base['init_host_pid'] and status['host_pid']==base['daemon_status']['host_pid'] and
                 env==base['android_env'],'REAL_DISCOVERY_DIFFERS_FROM_FIXED_FINAL_MAIN')
            view.guard();return init,env,status
        original.discover=discover
        original.sys=types.SimpleNamespace(stdin=types.SimpleNamespace(buffer=io.BytesIO(raw)),stdout=sys.stdout,stderr=sys.stderr)
        original.helper()  # Original request validation, private cropping and global action flock.
        view.check_owned_task();view.guard(action_attempted=view.action_attempted)
    except BaseException as exc:
        primary=exc;code=2 if isinstance(exc,subprocess.TimeoutExpired) else 1
        error={'type':type(exc).__name__,'automatic_retry':False,'outcome_unknown':bool(view and view.action_attempted)}
        c.binding.hold(exc)
    finally:
        if view is not None:
            try:view.close()
            except BaseException as exc:
                code=code or 1
                if primary is None:primary=exc;c.binding.hold(exc)
                error=error or {'type':'HeldReleaseFailure','automatic_retry':False,'outcome_unknown':view.action_attempted}
                error['held_release_error_type']=type(exc).__name__
    c.binding.commands.write_new(c.journal/'backend-result.json',{'returncode':code,'error':error,
        'action_attempted':bool(view and view.action_attempted),'scope_sha256':c.binding.scope_ref['sha256'],
        'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False,'whole_app_business_accepted':False,'automatic_retry':False})
    if error is not None:print(json.dumps({'ok':False,'error':error}),file=sys.stderr)
    return code

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('client','backend'))
    parser.add_argument('--scope',required=True,type=Path);parser.add_argument('--expect-scope-sha256',required=True)
    parser.add_argument('--step',required=True);parser.add_argument('--command',required=True)
    tokens=sys.argv[1:];split=tokens.index('--') if '--' in tokens else len(tokens);args=parser.parse_args(tokens[:split])
    args.original_argv=tokens[split+1:] if split<len(tokens) else []
    os.umask(0o077);c=load_context(args)
    return client(c) if args.mode=='client' else backend(c)
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'ok':False,'error':'FINAL_TYPED_UI_ENTRY_FAILED','exception_type':type(error).__name__,
            'automatic_retry':False,'whole_app_business_accepted':False}),file=sys.stderr);raise SystemExit(1)
