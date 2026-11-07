"""United-only install/state context using immutable shared recorder primitives.

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

PACKAGE = 'com.united.mobile.android'
UID = 10133
VERSION = 3617
INSTALLED_SHARED = Path('/home/alex/work/pocket4-current-host-r6-source-01')
SHARED_MANIFEST = '002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'
CONTRACT_SHA = 'f92d2598221c5bf65e783df39864879a2056da47f794680668b34df11f97da49'
CURRENT_EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
BASELINE_SHA = '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA = 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
LIST = ['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',PACKAGE]
PATHS = ['/system/bin/cmd','package','path','--user','0',PACKAGE]
FILE_LIMIT = 256*1024*1024
TOTAL_LIMIT = 512*1024*1024
HASH_SECONDS = 45
APK_COUNT = 4
METADATA_RESULT_BYTES = 13946
METADATA_RESULT_SHA = "7820efe97d7a8ebd55f91b6234d829576e2f0c2c0e6277710f143aca3759dc76"
TARGET_REFERENCE_SHA = "9fd00a8b3b3f88e958b75d093247e27d8736747e9191bda26b4ac9955f16cc9a"


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
            qa.SELF == self_package == 'org.droidloom.qa.united.r1', 'EXACT_UNITED_QA_SOURCE_REQUIRED')
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


def qualify_target_metadata(value, artifact_reference):
    """Qualify pinned public metadata; never extend the immutable Main baseline."""
    exact = {'package':PACKAGE,'uid':UID,'user':0,'version_code':VERSION}
    require(type(value) is dict and value.get('schema') == 1 and
            value.get('ok') is True and value.get('error') is None and
            value.get('secondary_errors') == [] and value.get('package') == PACKAGE and
            value.get('metadata_before') == value.get('metadata_after') == exact and
            all(type(value['metadata_before'][k]) is int for k in ('uid','user','version_code')) and
            value.get('actual_package_UID_version_APK_chain_stable') is True and
            value.get('package_read_commands_completed') == 5,
            'ACTUAL_INDEPENDENT_FIXED_TARGET_METADATA_REQUIRED')
    expected_scope = {'schema':'pocket4-fixed-new-target-metadata-scope-v1',
        'current_baseline_schema':'pocket4-main-current-baseline-v2',
        'epoch_sha256':CURRENT_EPOCH,'current_baseline_sha256':BASELINE_SHA,
        'current_baseline_qualification_sha256':QUALIFICATION_SHA,
        'package':PACKAGE,'user':0,'Bili_scope_reused':False,
        'UID_version_APKs_and_data_directories_pending':True,
        'baseline_packages_modified':False,'business_action_authority':False}
    require(value.get('current_metadata_scope') == expected_scope and
            type(value['current_metadata_scope']['user']) is int and
            value.get('immutable_baseline_packages_modified') is False and
            value.get('Bili_scope_modified') is False and
            value.get('future_install_or_UI_requires_separate_target_scope') is True and
            value.get('business_action_authority') is False and
            value.get('whole_app_production_ready') is False,
            'SEPARATE_CURRENT_TARGET_AUTHORITY_WITH_UNMODIFIED_BASELINE_REQUIRED')
    main = value.get('Main_before')
    require(type(main) is dict and main == value.get('Main_after') and
            main.get('schema') == 'pocket4-current-main-guard-v2' and
            main.get('Main_epoch_sha256') == CURRENT_EPOCH and
            main.get('current_baseline_sha256') == BASELINE_SHA and
            main.get('current_baseline_qualification_sha256') == QUALIFICATION_SHA and
            value.get('final_Main_guard_passed') is True and
            value.get('held_binding_released') is True and
            value.get('action_lock_released') is True,
            'ACTUAL_METADATA_CURRENT_MAIN_AND_CLOSURE_REQUIRED')
    rows = value.get('command_observations')
    resolver = ['/system/bin/cmd','package','resolve-activity','--brief','--user','0',
                '-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER',PACKAGE]
    require(type(rows) is list and len(rows) == 5 and
            [r.get('argv') for r in rows] == [LIST,PATHS,resolver,PATHS,LIST] and
            [r.get('index') for r in rows] == list(range(1,6)) and
            all(r.get('returncode') == 0 and r.get('spawned') is True and r.get('joined') is True and
                r.get('host_timed_out') is False and r.get('first_error') is None and
                r.get('secondary_errors') == [] and r.get('recorder_errors') == [] and
                r.get('stderr_bytes') == 0 and r.get('Android_UI_action') is False for r in rows) and
            all(type(value.get(k)) is int and value[k] == 0 for k in
                ('App_launches','UI_actions','instrumentation_calls','permission_grants','settings_writes')) and
            value.get('private_baseline_exported') is False and
            value.get('target_data_directory_contents_read') is False and
            value.get('APK_bytes_exported') is False,
            'FIVE_COMPLETED_READONLY_METADATA_COMMANDS_REQUIRED')
    require(type(artifact_reference) is dict and artifact_reference.get('target') == exact and
            value.get('artifacts') == artifact_reference.get('artifacts') and
            type(value.get('artifacts')) is list and len(value['artifacts']) == APK_COUNT and
            value.get('apk_paths_before') == sorted(r['path'] for r in value['artifacts']) and
            value.get('total_apk_bytes') == sum(r['held_file']['bytes'] for r in value['artifacts']),
            'ACTUAL_METADATA_AND_BUILT_TARGET_ARTIFACT_REFERENCE_MUST_MATCH')
    dirs = value.get('data_directories_before')
    require(type(dirs) is list and dirs == value.get('data_directories_after') and len(dirs) == 2 and
            [r.get('path') for r in dirs] == ['/data/user/0/'+PACKAGE,'/data/user_de/0/'+PACKAGE] and
            value.get('target_directory_cleanup') == {'contents_read':False,'held_data_directory_FDs_closed':2},
            'COMPLETE_INDEPENDENT_TARGET_DIRECTORY_PAIR_REQUIRED')
    for row in dirs:
        require(type(row) is dict and set(row) == {'path','device','inode','mode','uid','gid'} and
                all(type(row[k]) is int and row[k] >= 0 for k in ('device','inode','mode','uid','gid')) and
                row['inode'] > 0 and stat.S_ISDIR(row['mode']) and
                row['uid'] == row['gid'] == UID,
                'INDEPENDENT_TARGET_DIRECTORY_IDENTITY_REQUIRED')
    return value


def load_target_metadata(util, manifest, source_root):
    require(manifest['files']['actual-target-metadata.json'] ==
            {'bytes':METADATA_RESULT_BYTES,'sha256':METADATA_RESULT_SHA} and
            manifest['files']['target-artifact-reference.json']['sha256'] == TARGET_REFERENCE_SHA,
            'INDEPENDENT_TARGET_AUTHORITY_SOURCE_PINS_REQUIRED')
    value = json.loads(util.read(source_root/'actual-target-metadata.json',
        METADATA_RESULT_BYTES,METADATA_RESULT_SHA,METADATA_RESULT_BYTES))
    reference = json.loads(util.read(source_root/'target-artifact-reference.json',
        65536,TARGET_REFERENCE_SHA,manifest['files']['target-artifact-reference.json']['bytes']))
    return qualify_target_metadata(value, reference)


def current_scope():
    return {'schema':'pocket4-current-recorder-scope-v2',
            'current_baseline_schema':'pocket4-main-current-baseline-v2',
            'epoch_sha256':CURRENT_EPOCH,'current_baseline_sha256':BASELINE_SHA,
            'current_baseline_qualification_sha256':QUALIFICATION_SHA,
            'package':PACKAGE,'uid':UID,'user':0,
            'target_metadata_authority_sha256':METADATA_RESULT_SHA,
            'target_artifact_reference_sha256':TARGET_REFERENCE_SHA,
            'target_authority_kind':'separately-qualified-fixed-target-metadata',
            'immutable_baseline_packages_modified':False}


def baseline_scope(ref, baseline, authority):
    require(baseline.get('schema') == 'pocket4-main-current-baseline-v2' and
            baseline.get('kind') == 'current-cell-generation' and
            'main_deployed' not in baseline and baseline.get('deployment_performed') is False and
            baseline['framework_epoch']['sha256'] == CURRENT_EPOCH == ref.EPOCH and
            ref.BASELINE_SHA == BASELINE_SHA and ref.QUALIFICATION_SHA == QUALIFICATION_SHA and
            baseline.get('framework_exit_cause_resolved') is False and
            baseline.get('whole_app_production_ready') is False,
            'TYPED_CURRENT_BASELINE_AND_INDEPENDENT_TARGET_REQUIRED')
    # Separate pinned authority, never additions to B.packages/app_directories.
    qualify_target_metadata(authority, {
        'target':authority.get('metadata_before'),'artifacts':authority.get('artifacts')})
    return current_scope()


def verify_target_data(target, authority, binding):
    target.verify()
    raw, _ = target.read_file('/data/system/packages.list',1024*1024)
    binding.package_uids(raw,{PACKAGE:UID})
    del raw
    for kind in ('user','user_de'):
        relative = kind+'/0/'+PACKAGE
        expected = authority['data_directories_before'][0 if kind == 'user' else 1]
        require(expected['path'] == '/data/'+relative, 'FIXED_INDEPENDENT_TARGET_DIRECTORY_PATH_REQUIRED')
        fd = target.open_root('/data/'+relative,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
        primary = None
        try:
            value = os.fstat(fd)
            require(stat.S_ISDIR(value.st_mode) and
                    (value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid) ==
                    (expected['device'],expected['inode'],expected['mode'],expected['uid'],expected['gid']),
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
        require(type(attempted) is bool and not self.closed, 'OPEN_UNITED_CONTEXT_REQUIRED')
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
                    'CLOSED_OR_PRIVATE_UNITED_CONTEXT_FORBIDDEN')
            require(self.next_command < len(self.plan), 'EXACT_UNITED_COMMAND_PLAN_EXHAUSTED')
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


def current_discovery(util, source_manifest, source_verify, source_root,
                      app, baseline, epoch, guard):
    manifest = source_verify(source_manifest)
    row = manifest['files']['current_discovery.py']
    discovery = util.module(source_root/'current_discovery.py',row['sha256'],
                            'owned_current_discovery')
    require(discovery.BASELINE_SHA == BASELINE_SHA and
            discovery.QUALIFICATION_SHA == QUALIFICATION_SHA and
            discovery.MAIN_EPOCH == CURRENT_EPOCH,
            'CURRENT_DISCOVERY_SOURCE_BINDING_REQUIRED')
    return discovery.discover_current(app,baseline,epoch,guard)


def open_context(ref, util, source_manifest, source_verify, source_root, step,
                 transport, plan, result, deadline):
    source = util.module(INSTALLED_SHARED/'source_contract.py',CONTRACT_SHA,'united_shared_contract')
    contract = source.SourceContract(INSTALLED_SHARED/'source-manifest.json',SHARED_MANIFEST)
    recorder = contract.load('recorder.py','united_shared_command_only')
    held = contract.load('references/held_runtime_r5.py','united_actual_held_main')
    binding = contract.load('main_binding.py','united_shared_classpath_only')
    activation = ref.current_baseline()
    source_rows = source_verify(source_manifest)
    authority = load_target_metadata(util,source_rows,source_root)
    scope = baseline_scope(ref,activation,authority)
    epoch = ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'united_fixed_epoch')
    target = None
    def guard():
        require(time.monotonic() < deadline,'UNITED_INSTALL_STATE_WORKER_DEADLINE')
        source_verify(source_manifest)
        contract.verify()
        ref.read(recorder.APP,expected=recorder.APP_SHA)
        util.read(source.HELPER_PATH,source.HELPER_BYTES,source.HELPER_SHA,source.HELPER_BYTES)
        observation = ref.main_guard(activation,epoch)
        require(observation == authority['Main_before'], 'INDEPENDENT_METADATA_AND_CURRENT_MAIN_DIFFER')
        if target is not None:
            verify_target_data(target,authority,binding)
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
        app = util.module(Path(recorder.APP),recorder.APP_SHA,'united_discovery_only')
        init,discovered,status = current_discovery(util,source_manifest,source_verify,source_root,
                                                    app,activation,epoch,guard)
        require(init == expected['host_pid'] and status['host_pid'] == activation['status']['host_pid'],
                'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath = binding.main_classpaths(held,target,activation['framework_epoch'],epoch,guard)
        require(all(discovered.get(key) == value for key,value in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        environment = transport.environment_values(discovered)
        ctx = Context(recorder,contract,target,environment,transport,guard,step,plan,expected['host_pid'],deadline,scope)
        ref.write_new(step/'held-main-binding.json',{'target':target.record,'classpath':classpath,
            'shared_helper':result['shared_helper'],'target_package':PACKAGE,'target_uid':UID,
            'shared_recorder_primitive_manifest':SHARED_MANIFEST,
            'united_runtime_source_manifest':source_manifest,'Bili_Flow_instantiated':False,
            'current_target_scope':scope,'current_target_data_directory_count':2,
            'independent_target_metadata_sha256':METADATA_RESULT_SHA,
            'independent_target_artifact_reference_sha256':TARGET_REFERENCE_SHA,
            'immutable_baseline_packages_modified':False})
        return ctx,recorder,lambda:ref.main_guard(activation,epoch)
    except BaseException as primary:
        if target is not None:
            try:
                target.close()
            except BaseException as secondary:
                primary.add_note('held target close: '+repr(secondary))
        raise


class ArtifactSet:
    """The exact 4 installed commercial APKs, read-only and held to exit."""
    def __init__(self, context, expected, reader):
        require(expected['target'] == {'package':PACKAGE,'uid':UID,'user':0,'version_code':VERSION},
                'ACTUAL_UNITED_METADATA_REFERENCE_REQUIRED')
        self.context,self.expected,self.reader = context,expected,reader
        self.opened = []
        self.records = []
        self.closed = False

    def _metadata(self, raw):
        value = self.reader.metadata(raw)
        require(value == self.expected['target'],'ACTUAL_UNITED_UID_OR_VERSION_CHANGED')
        return value

    def _paths(self, raw):
        values = self.reader.apk_paths(raw)
        require(values == sorted(row['path'] for row in self.expected['artifacts']) and len(values) == APK_COUNT,
                'ACTUAL_FIXED_UNITED_APK_PATH_CHANGED')
        return values

    def _hash(self, fd, expected, deadline):
        first = identity(fd)
        require(first == expected['held_file'] and stat.S_ISREG(first['mode']) and first['nlink'] == 1 and
                first['uid'] == first['gid'] == 1000 and not first['mode']&0o022 and
                0 < first['bytes'] <= FILE_LIMIT,'ACTUAL_UNITED_APK_IDENTITY_CHANGED')
        os.lseek(fd,0,os.SEEK_SET)
        digest = hashlib.sha256();count = 0
        while True:
            require(time.monotonic() < deadline,'UNITED_APK_STREAM_HASH_DEADLINE')
            block = os.read(fd,min(65536,first['bytes']+1-count))
            if not block:
                break
            count += len(block)
            require(count <= first['bytes'],'UNITED_APK_GREW')
            digest.update(block)
        require(count == first['bytes'] and identity(fd) == first and digest.hexdigest() == expected['sha256'],
                'ACTUAL_UNITED_APK_CONTENT_CHANGED')
        return {'path':expected['path'],'sha256':digest.hexdigest(),'held_file':first}

    def before(self):
        self._metadata(self.context.android(LIST,15))
        self._paths(self.context.android(PATHS,15))
        require(sum(row['held_file']['bytes'] for row in self.expected['artifacts']) <= TOTAL_LIMIT,
                'FIXED_APK_TOTAL_BOUND')
        deadline = min(self.context.deadline,time.monotonic()+HASH_SECONDS)
        for row in self.expected['artifacts']:
            fd = self.context.target.open_root(row['path'],os.O_RDONLY|os.O_NOFOLLOW)
            self.opened.append(fd)
            self.records.append(self._hash(fd,row,deadline))
        require(len(self.opened) == len(self.records) == APK_COUNT,'EXACT_FIXED_HELD_APKS_REQUIRED')
        self.context.artifacts = self
        return {'metadata':self.expected['target'],'artifacts':self.records,
                'fresh_streaming_hashes':True,'signer_independently_verified':False}

    def verify_held(self):
        require(not self.closed and len(self.opened) == len(self.records) == APK_COUNT,'OPEN_FIXED_APK_SET_REQUIRED')
        for fd,row in zip(self.opened,self.records):
            require(identity(fd) == row['held_file'],'HELD_UNITED_APK_CHANGED')

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
                require(identity(named) == row['held_file'],'UNITED_APK_NAMED_PATH_CHANGED')
            finally:
                os.close(named)
        require(after == self.records,'UNITED_APK_SET_CHANGED')
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
        require(not failures,'UNITED_ARTIFACT_FD_CLOSE_FAILED: '+repr(failures))
        return {'held_APK_FDs_closed':opened_count,'commercial_files_changed':False}
