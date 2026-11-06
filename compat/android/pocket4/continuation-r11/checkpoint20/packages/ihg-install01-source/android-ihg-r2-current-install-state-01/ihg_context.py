"""IHG-only install/state context using immutable shared recorder primitives.

No Bili Flow or legacy client is instantiated. The actual Flow.command body,
held Main/root/classpath primitives and the target-specific BoundArun body are reused.
The transport's current-epoch literal is rebound; all action/cleanup bodies are unchanged.
An exact ordered command plan prevents this context being used for UI or launch.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time
import types

PACKAGE = 'com.ihg.apps.android'
UID = 10137
VERSION = 50023219
INSTALLED_SHARED = Path('/home/alex/work/pocket4-current-host-r5-source-01')
SHARED_MANIFEST = '6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
CONTRACT_SHA = '47389dc89f2257c4f80ae475d977fb63b04a994414772ed708f49b479fcd0783'
CURRENT_EPOCH = '734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'
BASELINE_SHA = '163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266'
QUALIFICATION_SHA = 'f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6'
LIST = ['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',PACKAGE]
PATHS = ['/system/bin/cmd','package','path','--user','0',PACKAGE]
FILE_LIMIT = 256*1024*1024
TOTAL_LIMIT = 512*1024*1024
HASH_SECONDS = 45


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(fd):
    s = os.fstat(fd)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,
            'nlink':s.st_nlink,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}


def ordered_commands(qa, self_package, guest_apk, state_nonce):
    require(qa.PACKAGE == PACKAGE and qa.UID == UID and
            qa.SELF == self_package == 'org.droidloom.qa.ihg.r2', 'EXACT_AMAZON_QA_SOURCE_REQUIRED')
    state = {'protocol':qa.PROTOCOL,'nonce':state_nonce,'op':'state'}
    qa.validate_request(state)
    own_uid = ['/system/bin/cmd','package','list','packages','-U','--user','0',self_package]
    own_path = ['/system/bin/cmd','package','path','--user','0',self_package]
    return [
        (LIST,15,False),(PATHS,15,False),
        (['/system/bin/cmd','package','list','packages','-u','-U','--user','all',self_package],8,False),
        (['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',self_package,guest_apk],40,True),
        (own_uid,8,False),(own_uid,8,False),(own_path,8,False),
        (qa.instrumentation_argv(state),20,False),
        (own_uid,8,False),(own_path,8,False),
        (['/system/bin/cmd','package','list','packages','-U','--user','all',self_package],8,False),
        (PATHS,15,False),(LIST,15,False),
    ]


def current_scope():
    return {'schema':'pocket4-current-recorder-scope-v1',
            'current_baseline_schema':'pocket4-main-current-baseline-v1',
            'epoch_sha256':CURRENT_EPOCH,'current_baseline_sha256':BASELINE_SHA,
            'current_baseline_qualification_sha256':QUALIFICATION_SHA,
            'package':PACKAGE,'uid':UID,'user':0}


def baseline_scope(ref, baseline):
    require(baseline.get('schema') == 'pocket4-main-current-baseline-v1' and
            baseline.get('kind') == 'current-framework-generation' and
            'main_deployed' not in baseline and baseline.get('deployment_performed') is False and
            baseline['framework_epoch']['sha256'] == CURRENT_EPOCH == ref.EPOCH and
            ref.BASELINE_SHA == BASELINE_SHA and ref.QUALIFICATION_SHA == QUALIFICATION_SHA and
            type(baseline['packages'].get(PACKAGE)) is int and baseline['packages'][PACKAGE] == UID and
            baseline.get('framework_exit_cause_resolved') is False and
            baseline.get('whole_app_production_ready') is False,
            'TYPED_CURRENT_BASELINE_AND_ACTUAL_TARGET_UID_REQUIRED')
    for kind in ('user','user_de'):
        row = baseline['app_directories'][kind+'/0/'+PACKAGE]
        require(type(row) is dict and set(row) == {'device','inode','uid','gid'} and
                all(type(v) is int and v >= 0 for v in row.values()) and
                row['inode'] > 0 and row['uid'] == UID,
                'CURRENT_TARGET_DATA_DIRECTORY_BINDING_REQUIRED')
    return {'schema':'pocket4-current-recorder-scope-v1',
            'current_baseline_schema':baseline['schema'],
            'epoch_sha256':baseline['framework_epoch']['sha256'],
            'current_baseline_sha256':ref.BASELINE_SHA,
            'current_baseline_qualification_sha256':ref.QUALIFICATION_SHA,
            'package':PACKAGE,'uid':baseline['packages'][PACKAGE],'user':0}


def verify_target_data(target, baseline, binding):
    target.verify()
    raw, _ = target.read_file('/data/system/packages.list',1024*1024)
    binding.package_uids(raw,{PACKAGE:UID})
    del raw
    for kind in ('user','user_de'):
        relative = kind+'/0/'+PACKAGE
        expected = baseline['app_directories'][relative]
        fd = target.open_root('/data/'+relative,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
        primary = None
        try:
            value = os.fstat(fd)
            require(stat.S_ISDIR(value.st_mode) and
                    (value.st_dev,value.st_ino,value.st_uid,value.st_gid) ==
                    (expected['device'],expected['inode'],expected['uid'],expected['gid']),
                    'CURRENT_TARGET_DATA_DIRECTORY_IDENTITY_CHANGED')
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                os.close(fd)
            except BaseException as cleanup:
                if primary is None:
                    raise
                primary.add_note('current target directory close: '+type(cleanup).__name__)
    target.verify()


class Context:
    def __init__(self, recorder, contract, target, environment, transport_module,
                 main_guard, step, plan, expected_init, deadline, scope):
        require(contract.sha256 == SHARED_MANIFEST and type(scope) is dict and scope == current_scope() and
                type(scope.get('uid')) is int and type(scope.get('user')) is int,
                'EXACT_TYPED_CURRENT_TARGET_CONTEXT_REQUIRED')
        self.recorder = recorder
        self.contract = contract
        self.scope = dict(scope)
        self.target = target
        self.main_guard = main_guard
        self.step = step
        self.command_index = 0
        self.action_attempted = False
        self._private_backend_transport = False
        self._android_mutation = False
        self.binding = types.SimpleNamespace(target=target)
        self.artifacts = None
        self.closed = False
        self.poisoned = False
        self.plan = [(list(argv),timeout,mutation) for argv,timeout,mutation in plan]
        self.next_command = 0
        self.deadline = deadline
        def record(kind, value):
            recorder.write_new(self.step/('transport-%03d.%s.json'%(value['sequence'],kind)),value)
        def runner(argv, **options):
            require(options['close_fds'] is True and options['stdout'] == subprocess.PIPE and
                    options['stderr'] == subprocess.PIPE,'EXACT_SHARED_RUNNER_PROTOCOL_REQUIRED')
            return recorder.Flow.command(self, argv, options['timeout'],mutation=self._android_mutation,
                label='Android command',pass_fds=options['pass_fds'],check=False,host_env=options['env'])
        self.transport = transport_module.BoundArun(target=target,environment=environment,
            guard=lambda action_attempted:self.guard(attempted=self.action_attempted),record=record,
            epoch_sha256=transport_module.FRAMEWORK_EPOCH_SHA256,init_pid=expected_init,
            package=PACKAGE,uid=UID,interactive_production=True,runner=runner)

    def guard(self, attempted=False):
        require(self.scope == current_scope() and type(self.scope.get('uid')) is int and
                type(self.scope.get('user')) is int, 'TYPED_CURRENT_TARGET_SCOPE_CHANGED')
        require(type(attempted) is bool and not self.closed, 'OPEN_AMAZON_CONTEXT_REQUIRED')
        self.main_guard()
        self.target.verify()
        if self.artifacts is not None:
            self.artifacts.verify_held()

    def bind(self):
        self.guard()
        return self.binding

    def android(self, argv, timeout=20, *, mutation=False):
        try:
            require(not self.closed and not self.poisoned and not self._private_backend_transport,
                    'CLOSED_OR_PRIVATE_AMAZON_CONTEXT_FORBIDDEN')
            require(self.next_command < len(self.plan), 'EXACT_AMAZON_COMMAND_PLAN_EXHAUSTED')
            expected = self.plan[self.next_command]
            require(type(mutation) is bool and (list(argv),timeout,mutation) == expected,
                    'ONLY_ORDERED_INSTALL_AND_NO_AUTOMATION_STATE_COMMANDS_ALLOWED')
            # Claim this command before transport entry. A failed attempt is
            # never repeated, even when no Android process was spawned.
            self.next_command += 1
            self._android_mutation = mutation
            return self.transport(argv,timeout)
        except BaseException:
            self.poisoned = True
            raise
        finally:
            self._android_mutation = False

    def close(self):
        self.closed = True
        self.target.close()


def open_context(ref, util, source_manifest, source_verify, source_root, step,
                 transport, plan, result, deadline):
    source = util.module(INSTALLED_SHARED/'source_contract.py',CONTRACT_SHA,'amazon_shared_contract')
    contract = source.SourceContract(INSTALLED_SHARED/'source-manifest.json',SHARED_MANIFEST)
    recorder = contract.load('recorder.py','amazon_shared_command_only')
    held = contract.load('references/held_runtime_r5.py','amazon_actual_held_main')
    binding = contract.load('main_binding.py','amazon_shared_classpath_only')
    activation = ref.current_baseline()
    scope = baseline_scope(ref,activation)
    epoch = ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'amazon_fixed_epoch')
    target = None
    def guard():
        require(time.monotonic() < deadline,'AMAZON_INSTALL_STATE_WORKER_DEADLINE')
        source_verify(source_manifest)
        contract.verify()
        ref.read(recorder.APP,expected=recorder.APP_SHA)
        util.read(source.HELPER_PATH,source.HELPER_BYTES,source.HELPER_SHA,source.HELPER_BYTES)
        observation = ref.main_guard(activation,epoch)
        if target is not None:
            verify_target_data(target,activation,binding)
        return observation
    result['Main_before'] = guard()
    result['shared_helper'] = source.verify_shared_helper()
    expected = activation['framework_epoch']['binding']['processes']['init']
    proc = os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        actual = held.proc_identity_at(proc,expected['host_pid'],time.monotonic()+3)
    finally:
        os.close(proc)
    require(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')
    try:
        target = held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA)
        guard()
        app = util.module(Path(recorder.APP),recorder.APP_SHA,'amazon_discovery_only')
        init,discovered,status = app.discover()
        require(init == expected['host_pid'] and status['host_pid'] == activation['status']['host_pid'],
                'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath = binding.main_classpaths(held,target,activation['framework_epoch'],epoch,guard)
        require(all(discovered.get(key) == value for key,value in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        environment = transport.environment_values(discovered)
        ctx = Context(recorder,contract,target,environment,transport,guard,step,plan,expected['host_pid'],deadline,scope)
        ref.write_new(step/'held-main-binding.json',{'target':target.record,'classpath':classpath,
            'shared_helper':result['shared_helper'],'target_package':PACKAGE,'target_uid':UID,
            'shared_recorder_primitive_manifest':SHARED_MANIFEST,
            'amazon_runtime_source_manifest':source_manifest,'Bili_Flow_instantiated':False,
            'current_target_scope':scope,'current_target_data_directory_count':2})
        return ctx,recorder,lambda:ref.main_guard(activation,epoch)
    except BaseException as primary:
        if target is not None:
            try:
                target.close()
            except BaseException as secondary:
                primary.add_note('held target close: '+repr(secondary))
        raise


class ArtifactSet:
    """The exact one installed commercial APK, read-only and held to exit."""
    def __init__(self, context, expected, reader):
        require(expected['target'] == {'package':PACKAGE,'uid':UID,'user':0,'version_code':VERSION},
                'ACTUAL_AMAZON_METADATA_REFERENCE_REQUIRED')
        self.context,self.expected,self.reader = context,expected,reader
        self.opened = []
        self.records = []
        self.closed = False

    def _metadata(self, raw):
        value = self.reader.metadata(raw)
        require(value == self.expected['target'],'ACTUAL_AMAZON_UID_OR_VERSION_CHANGED')
        return value

    def _paths(self, raw):
        values = self.reader.apk_paths(raw)
        require(values == sorted(row['path'] for row in self.expected['artifacts']) and len(values) == 1,
                'ACTUAL_ONE_IHG_APK_PATH_CHANGED')
        return values

    def _hash(self, fd, expected, deadline):
        first = identity(fd)
        require(first == expected['held_file'] and stat.S_ISREG(first['mode']) and first['nlink'] == 1 and
                first['uid'] == first['gid'] == 1000 and not first['mode']&0o022 and
                0 < first['bytes'] <= FILE_LIMIT,'ACTUAL_AMAZON_APK_IDENTITY_CHANGED')
        os.lseek(fd,0,os.SEEK_SET)
        digest = hashlib.sha256();count = 0
        while True:
            require(time.monotonic() < deadline,'AMAZON_APK_STREAM_HASH_DEADLINE')
            block = os.read(fd,min(65536,first['bytes']+1-count))
            if not block:
                break
            count += len(block)
            require(count <= first['bytes'],'AMAZON_APK_GREW')
            digest.update(block)
        require(count == first['bytes'] and identity(fd) == first and digest.hexdigest() == expected['sha256'],
                'ACTUAL_AMAZON_APK_CONTENT_CHANGED')
        return {'path':expected['path'],'sha256':digest.hexdigest(),'held_file':first}

    def before(self):
        self._metadata(self.context.android(LIST,15))
        self._paths(self.context.android(PATHS,15))
        require(sum(row['held_file']['bytes'] for row in self.expected['artifacts']) <= TOTAL_LIMIT,
                'ONE_APK_TOTAL_BOUND')
        deadline = min(self.context.deadline,time.monotonic()+HASH_SECONDS)
        for row in self.expected['artifacts']:
            fd = self.context.target.open_root(row['path'],os.O_RDONLY|os.O_NOFOLLOW)
            self.opened.append(fd)
            self.records.append(self._hash(fd,row,deadline))
        require(len(self.opened) == len(self.records) == 1,'EXACT_ONE_HELD_APK_REQUIRED')
        self.context.artifacts = self
        return {'metadata':self.expected['target'],'artifacts':self.records,
                'fresh_streaming_hashes':True,'signer_independently_verified':False}

    def verify_held(self):
        require(not self.closed and len(self.opened) == len(self.records) == 1,'OPEN_ONE_APK_SET_REQUIRED')
        for fd,row in zip(self.opened,self.records):
            require(identity(fd) == row['held_file'],'HELD_AMAZON_APK_CHANGED')

    def after(self):
        self._paths(self.context.android(PATHS,15))
        self._metadata(self.context.android(LIST,15))
        return self.revalidate_files()

    def revalidate_files(self):
        self.verify_held()
        deadline = min(self.context.deadline,time.monotonic()+HASH_SECONDS)
        after = []
        for fd,row in zip(self.opened,self.expected['artifacts']):
            after.append(self._hash(fd,row,deadline))
            named = self.context.target.open_root(row['path'],os.O_RDONLY|os.O_NOFOLLOW)
            try:
                require(identity(named) == row['held_file'],'AMAZON_APK_NAMED_PATH_CHANGED')
            finally:
                os.close(named)
        require(after == self.records,'AMAZON_APK_SET_CHANGED')
        return {'metadata':self.expected['target'],'artifacts':after,
                'fresh_streaming_hashes':True,'signer_independently_verified':False}

    def close(self):
        self.closed = True
        failures = []
        opened_count = len(self.opened)
        for fd in reversed(self.opened):
            try:
                os.close(fd)
            except BaseException as error:
                failures.append(repr(error))
        self.opened = []
        self.context.artifacts = None
        require(not failures,'AMAZON_ARTIFACT_FD_CLOSE_FAILED: '+repr(failures))
        return {'held_APK_FDs_closed':opened_count,'commercial_files_changed':False}
