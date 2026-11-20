"""Typed final business recorder boundary. Importing this file performs no action.

This module is used by a NEW frozen per-App adapter. It does not instantiate,
re-pin or monkeypatch any historical Flow, scope, helper, nonce or hold.
Its full_guard callback must come from the exact new task source packet and
retain the original per-App admission, phase policy, task and UID checks.
"""
import ast,datetime,hashlib,json,math,os,re,stat,subprocess,threading,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
SCHEMA='pocket4-final-business-recorder-scope-v1'
TASK_SCHEMA='pocket4-final-business-task-source-v1'
FINAL=Path('/home/alex/work/pocket4-android-final')
QUALIFICATION=Path('/var/lib/droidloom/qualification/pocket4')
LEGACY_RECORDER={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/provenance/recorder.py', 'bytes': 41689, 'sha256': 'c63cbdca615a609ebb41bcb25db6b770f43c4488c46a8f7b1dbee4bc462b4e64'}
LEGACY_TRANSPORT={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/provenance/bound_android_transport.py', 'bytes': 15601, 'sha256': 'fd9226cc6f6142eb5fb56ce81cecfa057ea14ca8ada52886d022ca79b2e45526'}
HELPER_CONTRACT={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main/helper_contract.py', 'bytes': 14350, 'sha256': 'bf8bfa382bae75b738717d03384a812a4e18c287678551081039a3144763390c'}
HELPER_PATH='/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/bin/held-namespace-entry'
HELD_HELPER_SHA256='67cfd1c212e9f40ce3f0ff7be856a05f8189c674cbfa270757a672ea596a6c3f'
HOST_ENV={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8'}
REQUIRED_ENV={'PATH','BOOTCLASSPATH','DEX2OATBOOTCLASSPATH','ANDROID_ROOT','ANDROID_DATA','ANDROID_ART_ROOT'}
ALLOWED_ENV=REQUIRED_ENV|{'ANDROID_ASSETS','ANDROID_BOOTLOGO','ANDROID_I18N_ROOT','ANDROID_STORAGE',
    'ANDROID_TZDATA_ROOT','ASEC_MOUNTPOINT','DOWNLOAD_CACHE','EXTERNAL_STORAGE','LOOP_MOUNTPOINT',
    'STANDALONE_SYSTEMSERVER_JARS','SYSTEMSERVERCLASSPATH','LANG'}

def need(ok,code):
    if not ok:raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def parse(raw):
    def pairs(items):
        out={}
        for k,v in items:
            need(k not in out,'DUPLICATE_JSON_FIELD');out[k]=v
        return out
    def reject(_):raise RuntimeError('NONFINITE_JSON_NUMBER')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=reject)
def reference(value):
    need(type(value) is dict and set(value)=={'path','bytes','sha256'} and type(value['path']) is str and
        Path(value['path']).is_absolute() and type(value['bytes']) is int and 0<value['bytes']<=16*1024*1024 and
        type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']),'EXACT_SOURCE_OR_RECEIPT_REFERENCE_REQUIRED')
    return value
def read_ref(ref,maximum=16*1024*1024):
    reference(ref);path=Path(ref['path'])
    need(path.resolve()==path and ref['bytes']<=maximum,'EXACT_CANONICAL_SOURCE_PATH_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==ref['bytes'],'SOURCE_FILE_SHAPE_CHANGED')
        raw=bytearray()
        while True:
            piece=os.read(fd,min(65536,maximum+1-len(raw)))
            if not piece:break
            raw.extend(piece);need(len(raw)<=maximum,'SOURCE_READ_BOUND')
        after=os.fstat(fd)
        keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(all(getattr(before,k)==getattr(after,k) for k in keys) and len(raw)==ref['bytes'] and
            digest(raw)==ref['sha256'],'SOURCE_OR_RECEIPT_PIN_CHANGED')
        return bytes(raw)
    finally:os.close(fd)
def private_dir(path):
    path=Path(path);info=path.lstat()
    need(path.is_absolute() and path.resolve()==path and stat.S_ISDIR(info.st_mode) and info.st_uid==0 and
         not info.st_mode&0o077,'NEW_PRIVATE_ROOT_OWNED_FLOW_DIRECTORY_REQUIRED')
    return path
def load_bundle(manifest_ref):
    manifest=parse(read_ref(manifest_ref,131072))
    need(manifest.get('schema')=='pocket4-final-business-support-v1' and
         set(manifest.get('files',{}))=={'business_commands.py','business_data.py','business_baseline.py','business_scope.py','business_ui_entry.py','business_image_capture.py'},
         'EXACT_NEW_SUPPORT_SOURCE_SET_REQUIRED')
    modules={}
    for name,item in manifest['files'].items():
        ref={'path':str(HERE/name),**item};raw=read_ref(ref,1024*1024)
        if name in ('business_baseline.py','business_commands.py','business_ui_entry.py'):
            module=types.ModuleType('frozen_'+name[:-3]);module.__file__=ref['path']
            exec(compile(raw,ref['path'],'exec'),module.__dict__);modules[name]=module
    need(manifest.get('historical_runtime_authority_transferred') is False and manifest.get('business_accepted') is False,
         'SOURCE_PUBLICATION_IS_NOT_BUSINESS_ACCEPTANCE')
    return modules

def validate_scope(scope,baseline,qualification_ref,support_ref):
    fields={'schema','business_baseline','business_qualification','support_manifest','framework_epoch_sha256',
        'package','uid','user','component','nonce','flow_root','task_source_manifest','phase_plan',
        'actual_resolution_receipt','installed_helper_receipts','recorder_source','guard_source','automatic_retry'}
    need(type(scope) is dict and set(scope)==fields and scope['schema']==SCHEMA,'DISTINCT_TYPED_FINAL_BUSINESS_SCOPE_REQUIRED')
    need(scope['business_baseline']==baseline.baseline_ref and scope['business_qualification']==qualification_ref and
         scope['support_manifest']==support_ref and
         scope['framework_epoch_sha256']==baseline.value['framework_epoch']['sha256'],'FIXED_FINAL_BUSINESS_BINDING_REQUIRED')
    for key in ('business_baseline','business_qualification','support_manifest','task_source_manifest','phase_plan',
                'actual_resolution_receipt','recorder_source','guard_source'):reference(scope[key])
    need(type(scope['package']) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+',scope['package']) and
         type(scope['uid']) is int and baseline.value['data_continuity']['package_uids'].get(scope['package'])==scope['uid'] and
         type(scope['user']) is int and scope['user']==0,'REAL_PRESERVED_TARGET_PACKAGE_UID_REQUIRED')
    need(type(scope['component']) is str and re.fullmatch(re.escape(scope['package'])+r'/[A-Za-z0-9_.$]+',scope['component']) and
         type(scope['nonce']) is str and re.fullmatch('[0-9a-f]{32}',scope['nonce']) and
         scope['automatic_retry'] is False,'EXACT_NEW_COMPONENT_NONCE_NO_RETRY_REQUIRED')
    flow=Path(scope['flow_root'])
    need(flow.is_absolute() and flow.parent==QUALIFICATION and flow.name.startswith('business-flow-') and
         flow.name.endswith(scope['nonce']),'EXPLICIT_NEW_NONCE_NAMED_FLOW_REQUIRED')
    helpers=scope['installed_helper_receipts']
    need(type(helpers) is list and len(helpers)<=16 and len({row['path'] for row in helpers})==len(helpers),'EXACT_HELPER_RECEIPT_SET_REQUIRED')
    for row in helpers:reference(row)
    return scope

def validate_packet(packet,scope):
    need(type(packet) is dict and set(packet)=={'schema','files','origins','guard_source','recorder_source',
        'target_package','target_uid','old_runtime_authority_transferred'} and packet['schema']==TASK_SCHEMA and
        packet['old_runtime_authority_transferred'] is False,'NEW_TASK_SOURCE_PACKET_REQUIRED')
    need(packet['target_package']==scope['package'] and type(packet['target_uid']) is int and packet['target_uid']==scope['uid'] and
        packet['guard_source']==scope['guard_source'] and packet['recorder_source']==scope['recorder_source'],'TASK_SOURCE_TARGET_CHANGED')
    files=packet['files'];origins=packet['origins']
    need(type(files) is list and 1<=len(files)<=128 and len({r['path'] for r in files})==len(files) and
         type(origins) is list and 1<=len(origins)<=128,'EXPLICIT_NEW_FILES_AND_HISTORICAL_ORIGINS_REQUIRED')
    for row in files+origins:reference(row)
    need(scope['guard_source'] in files and scope['recorder_source'] in files,'FULL_GUARD_AND_RECORDER_NOT_IN_NEW_PACKET')
    root=Path(scope['task_source_manifest']['path']).parent
    need(all(Path(row['path']).is_relative_to(root) for row in files),'NEW_TASK_SOURCE_MUST_BE_SEPARATE_FROZEN_COPY')
    need(all(row['path'] not in {item['path'] for item in files} for row in origins),'HISTORICAL_FILES_MUST_REMAIN_SEPARATE')
    return packet

class ScopeBinding:
    """No command/action admission is implied by constructing a scope binding.

    full_guard is the new packet's original complete per-App guard, explicitly
    migrated to the new baseline API. It must additionally validate the real
    resolution/install receipts and phase plans. Merely pinning their bytes
    here is intentionally not represented as per-App qualification.
    """
    def __init__(self,*,scope_ref,baseline_ref,qualification_ref,support_ref,full_guard):
        self.modules=load_bundle(support_ref);self.commands=self.modules['business_commands.py']
        self.baseline=self.modules['business_baseline.py'].BusinessBaseline(baseline_ref,qualification_ref)
        self.scope_ref=reference(scope_ref);self.scope_raw=read_ref(scope_ref,131072);self.scope=parse(self.scope_raw)
        self.support_ref=support_ref;self.qualification_ref=qualification_ref;self.full_guard=full_guard
        self._validate();self.root=private_dir(self.scope['flow_root'])
        need(Path(scope_ref['path'])==self.root/'scope.json','SCOPE_MUST_BE_OWNED_BY_THIS_NEW_FLOW')
        need(callable(full_guard),'FULL_NEW_PACKET_GUARD_REQUIRED')
        func=getattr(full_guard,'__func__',getattr(full_guard,'func',full_guard))
        need(hasattr(func,'__code__') and Path(func.__code__.co_filename)==Path(self.scope['guard_source']['path']),
             'FULL_GUARD_MUST_BE_THE_PINNED_NEW_SOURCE_FUNCTION')
        self.poisoned=False
    def _validate(self):
        validate_scope(self.scope,self.baseline,self.qualification_ref,self.support_ref)
        need(read_ref(self.scope_ref,131072)==self.scope_raw,'RECORDER_SCOPE_CHANGED')
        packet=validate_packet(parse(read_ref(self.scope['task_source_manifest'],131072)),self.scope)
        for row in packet['files']+packet['origins']:read_ref(row)
        for key in ('phase_plan','actual_resolution_receipt'):read_ref(self.scope[key])
        for row in self.scope['installed_helper_receipts']:read_ref(row)
        # These are provenance only. Their historical runtime admission is not reused.
        read_ref(LEGACY_RECORDER,1024*1024);read_ref(LEGACY_TRANSPORT,1024*1024)
    def hold(self,error):
        self.poisoned=True
        path=Path(self.scope['flow_root'])/'hold.json'
        value={'schema':'pocket4-final-business-hold-v1','scope_sha256':self.scope_ref['sha256'],
            'error_type':type(error).__name__,'command_observation':getattr(error,'command_observation',None),
            'automatic_retry':False,'automatic_rollback':False,'automatic_task_removal':False,
            'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False}
        try:self.commands.write_new(path,value)
        except FileExistsError:pass  # Preserve the first recorded UNKNOWN/failure.
        except BaseException as secondary:error.add_note('HOLD_EVIDENCE_UNAVAILABLE:'+type(secondary).__name__)
    def guard(self,*,action_attempted=False):
        need(type(action_attempted) is bool and not self.poisoned,'RECORDER_STOPPED_NO_AUTOMATIC_REPLAY')
        try:
            self._validate();private_dir(self.scope['flow_root'])
            need(not (Path(self.scope['flow_root'])/'hold.json').exists(),'SAVED_HOLD_REQUIRES_EXPLICIT_RECONCILIATION')
            main=self.baseline.guard(action_attempted=action_attempted)
            self.full_guard(attempted=action_attempted)
            self._validate()
            return {'schema':'pocket4-final-business-recorder-guard-v1','scope_sha256':self.scope_ref['sha256'],
                'main':main,'full_original_per_app_guard_completed':True,
                'guard_source':self.scope['guard_source'],'task_source_manifest':self.scope['task_source_manifest'],
                'host_retirement_is_not_Binder_cleanup':True,'whole_app_business_accepted':False}
        except BaseException as error:
            self.hold(error);error.action_attempted=action_attempted;error.outcome_unknown=action_attempted;error.automatic_retry=False
            raise

class RecorderBridge:
    """Drop-in command method for a new source-bound Flow.

    The adapter retains its policy.admit(), locks, intent/claim/nonce handling,
    original task parser, explicit owned-task removal and UID observations.
    bridge.command is invoked only after those original admissions.
    """
    def __init__(self,flow,binding):
        self.flow,self.binding=flow,binding
        self.step=private_dir(flow.step)
        need(self.step.parent==binding.root/'steps' and getattr(flow,'scope',None)==binding.scope,'EXACT_NEW_STEP_AND_SCOPE_REQUIRED')
        self.closed=False;self.command_index=0
    def _hold(self,error):
        self.closed=True;self.binding.poisoned=True
        observation=getattr(error,'command_observation',None)
        target=getattr(getattr(self.flow,'binding',None),'target',None)
        if target is not None:
            if observation is not None and observation.get('host_retirement_proved') is not True:
                target.poison_unjoined_command()
            else:target.seal_admission()
        self.binding.hold(error)
    def command(self,argv,timeout,*,mutation=False,label=None,pass_fds=(),check=True,host_env=None,private_output=False):
        need(not self.closed and not self.binding.poisoned,'NEW_RECORDER_STEP_CLOSED')
        need(check or (label=='Android command' and len(pass_fds)==7),'UNCHECKED_ONLY_FOR_EXACT_HELD_TRANSPORT')
        need(not private_output or (label=='Android command' and not check and len(pass_fds)==7),
             'PRIVATE_RAW_OUTPUT_REQUIRES_EXACT_HELD_ROUTE')
        self.command_index+=1;name='command-%03d'%self.command_index
        try:
            execution=list(argv);output_bound=1024*1024
            if label=='Existing android-app CLI':
                need(not pass_fds and check and not private_output and
                     argv[:2]==['/usr/local/bin/android-app','--interactive-production'],'EXACT_ORIGINAL_UI_CLIENT_ROUTE_REQUIRED')
                self.binding.guard()
                self.binding.commands.write_new(self.step/(name+'.logical.json'),
                    {'schema':'pocket4-final-ui-logical-command-v1','scope_sha256':self.binding.scope_ref['sha256'],
                     'argv':list(argv),'mutation':mutation,'label':label,'automatic_retry':False})
                entry=self.binding.modules['business_ui_entry.py']
                execution=entry.entry_argv(self.binding.scope_ref,'client',self.step.name,name,argv[1:])
                output_bound=entry.MAX_PIPE
            elif private_output:output_bound=16*1024*1024
            completed=self.binding.commands.run_recorded(name,execution,timeout,self.step,self.binding.guard,
                protected_pids=self.binding.baseline.protected_pids,mutation=mutation,pass_fds=pass_fds,
                host_env=host_env,check=check,deferred_post_guard=not check,private_output=private_output,output_bound=output_bound)
            self.flow.action_attempted|=bool(completed.command_observation['action_attempted'])
            return completed if not check else completed.stdout
        except BaseException as error:
            observed=getattr(error,'command_observation',{})
            self.flow.action_attempted|=bool(observed.get('action_attempted',False))
            self._hold(error);raise
    def runner(self,argv,**options):
        need(set(options)=={'stdout','stderr','timeout','env','pass_fds','close_fds'} and
             options['stdout']==options['stderr']==subprocess.PIPE and options['close_fds'] is True,
             'EXACT_HELD_RUNNER_OPTIONS_REQUIRED')
        return self.command(argv,options['timeout'],mutation=self.flow._android_mutation,label='Android command',
            pass_fds=options['pass_fds'],check=False,host_env=options['env'],
            private_output=self.flow._private_backend_transport)
    def run_cli(self,name,argv,timeout,*,mutation=False):
        need(not self.closed,'COORDINATOR_SCOPE_CLOSED')
        try:
            result=self.binding.commands.run_cli(name,argv,timeout,self.step,self.binding.guard,
                protected_pids=self.binding.baseline.protected_pids,mutation=mutation)
            return result
        except BaseException as error:self._hold(error);raise

# The transport below is an independent derivative of the exact R6 method.
# Epoch/package/UID are now immutable instance values from ScopeBinding.
# Its held-entry prefix, seven-FD protocol, lease-release-before-post-guard order,
# first-error retention, inner timeout and one-step poison rule stay explicit.
class TransportError(RuntimeError):
    """Code and metadata deliberately omit command text and private output."""
    def __init__(self, code, *, attempted=False, unknown=False, **metadata):
        super().__init__(code)
        self.details = {"action_attempted": attempted, "outcome_unknown": unknown,
                        "automatic_retry": False, **metadata}

class TransportTimeout(subprocess.TimeoutExpired):
    """Preserve the existing helper's explicit TimeoutExpired handling."""
    def __init__(self, code, timeout, **metadata):
        super().__init__("<owned Android command>", timeout)
        self.code = code
        self.details = {"action_attempted": True, "outcome_unknown": True,
                        "automatic_retry": False, **metadata}

    def __str__(self):
        return self.code

def require(condition, code):
    if not condition:
        raise TransportError(code)

def environment_values(values):
    require(isinstance(values, dict) and REQUIRED_ENV <= set(values) <= ALLOWED_ENV,
            "ANDROID_ENVIRONMENT_KEYS_DIFFER")
    result = {}
    for key, value in values.items():
        require(isinstance(value, str) and (key not in REQUIRED_ENV or value) and "\0" not in value
                and len(value.encode("utf-8")) <= 65536,
                "ANDROID_ENVIRONMENT_VALUE_INVALID")
        result[key] = value
    return result

class BoundArun:
    def __init__(self,*,target,environment,binding,record,runner):
        require(isinstance(binding,ScopeBinding),"NEW_TYPED_SCOPE_BINDING_REQUIRED")
        binding.guard()
        scope=binding.scope;expected=binding.baseline.value['framework_epoch']['binding']['processes']['init']
        require(target.expected['pid']==expected['host_pid'] and target.helper_path==HELPER_PATH and
                target.helper_sha256==HELD_HELPER_SHA256,"ACTUAL_FIXED_HELD_TARGET_REQUIRED")
        raw=target.expected;observed=binding.baseline.value['observation']
        require(int(raw['start'])==expected['start_ticks'] and raw['ppid']==expected['parent_host_pid'] and
                raw['uid']==[str(x) for x in expected['uids']] and [int(x) for x in raw['nspid']]==expected['namespace_pids'] and
                raw['exe']==expected['executable'] and raw['cgroup'].splitlines()==expected['cgroup'] and
                set(raw['ns'])=={'mnt','pid','uts','ipc','net','cgroup'} and
                all(raw['ns'][k]==observed['namespaces']['init'][k]['link'] for k in raw['ns']) and
                all(target.root_record[k]==observed['roots']['init'][k] for k in ('device','inode')),
                "FULL_HELD_TARGET_NOT_SAME_NEW_MAIN")
        helper_raw=read_ref(HELPER_CONTRACT,1024*1024)
        helper_contract=types.ModuleType('original_shared_helper_protocol_only');helper_contract.__file__=HELPER_CONTRACT['path']
        exec(compile(helper_raw,helper_contract.__file__,'exec'),helper_contract.__dict__)
        self.helper_qualification=helper_contract.verify_shared_helper(binding.baseline)
        require(target.main_user_namespace==binding.baseline.docs['final_baseline']['main_user_namespace'],
                'HELD_TARGET_AND_SAME_MAIN_USER_NAMESPACE_REQUIRED')
        target.verify()
        require(callable(record) and callable(runner),"TRANSPORT_CALLBACK_MISSING")
        self.target,self.environment,self.binding=target,environment_values(environment),binding
        self.guard,self.record,self.runner=binding.guard,record,runner
        self.epoch_sha256,self.package,self.uid=scope['framework_epoch_sha256'],scope['package'],scope['uid']
        self._lock=threading.Lock();self._poisoned=False;self._sequence=0
    def _check(self, attempted):
        self.guard(action_attempted=attempted)
        self.target.verify()

    def __call__(self, args, timeout=30):
        require(self._lock.acquire(blocking=False), "TRANSPORT_ALREADY_ACTIVE")
        try:
            require(not self._poisoned, "TRANSPORT_CLOSED_AFTER_FAILURE")
            require(isinstance(args, (list, tuple)) and args and
                    all(isinstance(x, str) and x and "\0" not in x for x in args)
                    and args[0].startswith("/"), "ANDROID_COMMAND_INVALID")
            require(type(timeout) in (int, float) and math.isfinite(timeout)
                    and 0 < timeout <= 70, "ANDROID_COMMAND_TIMEOUT_INVALID")
            self._check(False)
            inner = max(1, timeout - 5)
            command = ["/system/bin/env", "-i"]
            command += [key + "=" + self.environment[key] for key in sorted(self.environment)]
            command += ["/system/xbin/su", "2000", "/system/bin/timeout", "-k", "2",
                        str(inner), *args]
            self._sequence += 1
            identity = {"sequence": self._sequence, "epoch_sha256": self.epoch_sha256,
                        "package": self.package, "uid": self.uid,
                        "command_sha256": hashlib.sha256(json.dumps(args, ensure_ascii=False,
                            separators=(",", ":")).encode()).hexdigest(),
                        "timeout_seconds": timeout, "inner_timeout_seconds": inner,
                        "automatic_retry": False, "numeric_pid_target_used": False,
                        "Binder_task_cleanup_verified": False, "Binder_UID_cleanup_verified": False,
                        "whole_app_business_accepted": False}
            self.record("intent", identity)
            primary = None
            completed = None
            attempted = False
            entered = False
            manager = None
            status = {**identity, "action_attempted": False, "outcome_unknown": False}

            def remember(failure, code, phase, **metadata):
                nonlocal primary
                if primary is None:
                    if isinstance(failure, (TransportError, TransportTimeout)):
                        primary = failure
                    else:
                        primary = TransportError(code, attempted=attempted, unknown=attempted)
                        primary.__cause__ = failure
                primary.details.update(metadata)
                primary.details.setdefault("observed_errors", []).append({
                    "phase": phase, "exception_type": type(failure).__name__,
                    "errno": getattr(failure, "errno", None)})

            try:
                manager = self.target.entry(command)
                entry_value = manager.__enter__()
                entered = True
                argv, descriptors = entry_value
                require(len(descriptors) == 7 and len(set(descriptors)) == 7
                        and all(type(fd) is int and fd >= 3 for fd in descriptors),
                        "HELD_AUTHORITY_SET_DIFFERS")
                require(isinstance(argv, (list, tuple)) and
                        all(isinstance(part, str) and part and "\0" not in part for part in argv),
                        "HELD_ENTRY_ARGV_INVALID")
                try:
                    boundary = argv.index("--")
                except ValueError:
                    raise TransportError("HELD_ENTRY_SEPARATOR_MISSING")
                prefix = list(argv[:boundary])
                require("--target" not in prefix and "-t" not in prefix and
                        all(not part.startswith("--target=") for part in prefix),
                        "NUMERIC_PID_ENTRY_FORBIDDEN")
                require(list(argv[boundary + 1:]) == command,
                        "HELD_ENTRY_COMMAND_SUFFIX_DIFFERS")
                # Match the qualified R5 helper protocol and the exact passed
                # authority FDs. Only the helper prefix is a namespace entry;
                # Android command options such as pm install -t follow "--".
                expected_prefix = [str(self.target.helper_path),
                    "--parent-pid=" + str(os.getpid()),
                    "--root-fd=" + str(descriptors[0])]
                expected_prefix += ["--" + name + "-fd=" + str(fd) for name, fd in
                    zip(("mnt", "pid", "uts", "ipc", "net", "cgroup"), descriptors[1:])]
                require(prefix == expected_prefix, "HELD_ENTRY_PREFIX_DIFFERS")
                attempted = True
                try:
                    completed = self.runner(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=timeout, env=HOST_ENV, pass_fds=tuple(descriptors), close_fds=True)
                except subprocess.TimeoutExpired as failure:
                    primary = TransportTimeout("HOST_COMMAND_TIMEOUT", timeout)
                    primary.__cause__ = failure
                except BaseException as failure:
                    primary = TransportError("HOST_COMMAND_INTERRUPTED", attempted=True, unknown=True,
                                             exception_type=type(failure).__name__)
                    primary.__cause__ = failure
                    observed=getattr(failure,"command_observation",None)
                    if observed is not None:primary.details["host_command_observation"]=observed
                if completed is None:
                    status = {**identity, "first_cause": str(primary),
                        "action_attempted": True, "outcome_unknown": True}
                else:
                    status = {**identity, "returncode": completed.returncode,
                        "stdout_bytes": len(completed.stdout), "stderr_bytes": len(completed.stderr),
                        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
                        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
                        "action_attempted": True, "outcome_unknown": completed.returncode != 0}
                    if getattr(completed, "host_timed_out", False):
                        primary = TransportTimeout("HOST_COMMAND_TIMEOUT", timeout,
                                                   returncode=completed.returncode)
                    elif completed.returncode in (124, 137):
                        primary = TransportTimeout("ANDROID_COMMAND_TIMEOUT", inner,
                                                   returncode=completed.returncode)
                    elif completed.returncode != 0:
                        primary = TransportError("ANDROID_COMMAND_FAILED", attempted=True, unknown=True,
                                                 returncode=completed.returncode)
                    recorder_errors = getattr(completed, "recorder_errors", [])
                    if recorder_errors:
                        remember(TransportError("RECORDER_COMMAND_EVIDENCE_FAILED", attempted=True,
                            unknown=True), "RECORDER_COMMAND_EVIDENCE_FAILED", "recorder_command_evidence",
                            recorder_errors=recorder_errors)
                # This observation precedes lease exit: a release exception must
                # not erase a command that was already sent or replace its cause.
                try:
                    self.record("command-result", status)
                except BaseException as failure:
                    remember(failure, "COMMAND_RESULT_RECORD_FAILED", "command_result_record",
                             command_result_record_failed=True)
            except BaseException as failure:
                phase = "entry_acquire" if not entered else "command_observation"
                code = "HELD_ENTRY_ACQUIRE_FAILED" if not entered else "COMMAND_OBSERVATION_FAILED"
                remember(failure, code, phase)
            finally:
                if entered:
                    try:
                        # Even if a context manager reports suppression, an
                        # already observed command failure stays authoritative.
                        manager.__exit__(type(primary) if primary else None, primary,
                                         primary.__traceback__ if primary else None)
                    except BaseException as failure:
                        remember(failure, "HELD_ENTRY_RELEASE_FAILED", "entry_release",
                                 entry_release_failed=True)
                if attempted:
                    try:
                        self._check(True)
                    except BaseException as failure:
                        remember(failure, "POST_COMMAND_EPOCH_OR_TARGET_CHANGED", "post_command_guard",
                                 post_command_guard_failed=True)
            if primary is not None:
                try:
                    self.record("failure", {**status, "first_cause": str(primary), **primary.details})
                except BaseException:
                    primary.details["failure_record_failed"] = True
                raise primary
            self.record("verified-result", {**status, "outcome_unknown": False})
            return completed.stdout
        except BaseException as error:
            # Evidence failure or even a pre-entry guard failure cannot invite
            # another command in the same admitted recorder step.
            self._poisoned = True
            self.binding.hold(error)
            try:self.target.seal_admission()
            except BaseException as secondary:error.add_note('HELD_ADMISSION_SEAL_FAILED:'+type(secondary).__name__)
            raise
        finally:
            self._lock.release()

TASK_SOURCE={'path': '/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/inputs/a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528/task_scope_baseline.py', 'bytes': 17281, 'sha256': 'a16e347abb0de2ccbff24f6d7990f6dab1be600675054b45203e907fa8eef528'}
def task_functions():
    raw=read_ref(TASK_SOURCE,131072);names={'parse_stacks','exact_leaf','wait_for_removal'}
    nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in names]
    need({n.name for n in nodes}==names and len(nodes)==3,'ORIGINAL_TASK_PARSER_SET_CHANGED')
    scope={'re':re,'time':time,'now':lambda:datetime.datetime.now(datetime.timezone.utc).isoformat(),'require':need}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),TASK_SOURCE['path'],'exec'),scope)
    return types.SimpleNamespace(**{name:scope[name] for name in names})

def task_claim_facts(scope,baseline,pre_raw,native_raw,post_raw):
    tasks=task_functions();pre_roots,pre_tasks=tasks.parse_stacks(pre_raw.decode('utf-8','strict'))
    need(not any(c['component'].split('/')[0]==scope['package'] for r in pre_roots.values() for c in r['children']),
         'PREEXISTING_TARGET_TASK_MUST_BE_PRESERVED')
    native=parse(native_raw)
    need(type(native) is dict and native.get('ok') is True and native.get('state')=='running' and
         type(native.get('host_pid')) is int and native['host_pid']==baseline.docs['final_baseline']['daemon_status']['host_pid'] and
         native.get('outcome_unknown') is not True,'FRESH_NATIVE_LAUNCH_RECEIPT_REQUIRED')
    match=re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)',native.get('launch',''))
    need(match is not None and int(match[3])==0 and int(match[4])>0,'FRESH_DEFAULT_DISPLAY_TASK_REQUIRED')
    task=int(match[4]);roots,after=tasks.parse_stacks(post_raw.decode('utf-8','strict'))
    need(task not in pre_tasks and task not in pre_roots and after==pre_tasks|{task} and
         tasks.exact_leaf(roots,task,scope['package']),'NEW_EXACT_OWNED_LEAF_TASK_REQUIRED')
    return {'task':task,'package':scope['package'],'epoch_sha256':scope['framework_epoch_sha256'],
        'prelaunch_absent':True,'cleanup_allowed':True,'prelaunch_task_ids':sorted(pre_tasks),
        'native_receipt_sha256':digest(native_raw)}

def record_owned_task(binding,launch_step,pre_ref,native_ref,post_ref):
    """Record only actual supplied readbacks. This function sends no command."""
    binding.guard()
    need(type(launch_step) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',launch_step),'EXACT_NEW_LAUNCH_STEP_REQUIRED')
    rows=(pre_ref,native_ref,post_ref)
    for row in rows:
        reference(row);need(Path(row['path']).is_relative_to(binding.root/'steps'/launch_step),'LAUNCH_EVIDENCE_OUTSIDE_NEW_STEP')
    facts=task_claim_facts(binding.scope,binding.baseline,*[read_ref(row,1024*1024) for row in rows])
    claim={'schema':'pocket4-final-owned-task-v1','scope_sha256':binding.scope_ref['sha256'],'launch_step':launch_step,
        **facts,'prelaunch_observation':pre_ref,'native_receipt':native_ref,'postlaunch_observation':post_ref,
        'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False,'whole_app_business_accepted':False}
    return binding.commands.write_new(binding.root/'launch-scope.json',claim)

def load_owned_task(binding):
    path=binding.root/'launch-scope.json';raw=binding.commands.read(path,131072)
    claim=parse(raw)
    fields={'schema','scope_sha256','launch_step','task','package','epoch_sha256','prelaunch_absent','cleanup_allowed',
        'prelaunch_task_ids','native_receipt_sha256','prelaunch_observation','native_receipt','postlaunch_observation',
        'Binder_task_cleanup_verified','Binder_UID_cleanup_verified','whole_app_business_accepted'}
    need(type(claim) is dict and set(claim)==fields and claim['schema']=='pocket4-final-owned-task-v1' and
         claim['scope_sha256']==binding.scope_ref['sha256'] and type(claim['launch_step']) is str and
         re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',claim['launch_step']),'NEW_OWNED_TASK_SCOPE_REQUIRED')
    rows=[claim[k] for k in ('prelaunch_observation','native_receipt','postlaunch_observation')]
    for row in rows:
        reference(row);need(Path(row['path']).is_relative_to(binding.root/'steps'/claim['launch_step']),'TASK_EVIDENCE_OUTSIDE_NEW_LAUNCH')
    facts=task_claim_facts(binding.scope,binding.baseline,*[read_ref(row,1024*1024) for row in rows])
    need(all(claim[k]==v and type(claim[k]) is type(v) for k,v in facts.items()) and
         claim['Binder_task_cleanup_verified'] is False and claim['Binder_UID_cleanup_verified'] is False and
         claim['whole_app_business_accepted'] is False,'OWNED_TASK_FACTS_OR_CLEANUP_SCOPE_CHANGED')
    return claim,{'path':str(path),'bytes':len(raw),'sha256':digest(raw)}
