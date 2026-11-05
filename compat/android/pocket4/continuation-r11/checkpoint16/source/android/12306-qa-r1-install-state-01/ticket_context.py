"""12306-only install/state context using immutable shared recorder primitives.

No Bili Flow or legacy client is instantiated. The actual Flow.command body,
held Main/root/classpath primitives and R4 BoundArun body are reused; the new
transport has only its two target identity literals changed in a separate file.
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

PACKAGE = 'com.MobileTicket'
UID = 10121
VERSION = 275
INSTALLED_SHARED = Path('/home/alex/work/pocket4-owned-bili-qa-r5-install-state-03/source/recorder-r4')
SHARED_MANIFEST = '52b95328e2f07aaf4416b7f48c9046ffa465337cad7a410ea3a7027512720dc1'
CONTRACT_SHA = '51c2b3dd7df80a8fcd4881eb7216f7292db77d39c01920f10feb650824919a7d'
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
            qa.SELF == self_package == 'org.droidloom.qa.ticket.r1', 'EXACT_AMAZON_QA_SOURCE_REQUIRED')
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


class Context:
    def __init__(self, recorder, contract, target, environment, transport_module,
                 main_guard, step, plan, expected_init, deadline):
        self.recorder = recorder
        self.contract = contract
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
    activation = json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
    verified = json.loads(ref.read(ref.VERIFIED,expected=ref.VERIFIED_SHA))
    require(activation['main_deployed'] is True and verified['main_deployed'] is True and
            verified['framework_epoch_sha256'] == ref.EPOCH and activation['packages'][PACKAGE] == UID,
            'FIXED_MAIN_AND_AMAZON_UID_ACTIVATION_REQUIRED')
    epoch = ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'amazon_fixed_epoch')
    def guard():
        require(time.monotonic() < deadline,'AMAZON_INSTALL_STATE_WORKER_DEADLINE')
        source_verify(source_manifest)
        contract.verify()
        ref.read(recorder.APP,expected=recorder.APP_SHA)
        util.read(source.HELPER_PATH,source.HELPER_BYTES,source.HELPER_SHA,source.HELPER_BYTES)
        return ref.main_guard(activation,epoch)
    result['Main_before'] = guard()
    result['shared_helper'] = source.verify_shared_helper()
    expected = activation['framework_epoch']['binding']['processes']['init']
    proc = os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        actual = held.proc_identity_at(proc,expected['host_pid'],time.monotonic()+3)
    finally:
        os.close(proc)
    require(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')
    target = None
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
        ctx = Context(recorder,contract,target,environment,transport,guard,step,plan,expected['host_pid'],deadline)
        ref.write_new(step/'held-main-binding.json',{'target':target.record,'classpath':classpath,
            'shared_helper':result['shared_helper'],'target_package':PACKAGE,'target_uid':UID,
            'shared_recorder_primitive_manifest':SHARED_MANIFEST,
            'amazon_runtime_source_manifest':source_manifest,'Bili_Flow_instantiated':False})
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
                'ACTUAL_ONE_12306_APK_PATH_CHANGED')
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
