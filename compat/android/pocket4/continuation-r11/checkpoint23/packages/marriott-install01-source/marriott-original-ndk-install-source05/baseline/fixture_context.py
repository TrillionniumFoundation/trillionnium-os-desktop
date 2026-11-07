"""Original NDK fixture Main-only context, never a commercial App Flow.
Source only: open_context reaches the unbound gate before all Main/OS reads.
Original R6 SourceContract verification, current8 guard, explicit discovery,
paired classpaths and held six-namespace entry are used without monkeypatching.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import subprocess
import time
import types

PACKAGE = 'com.example.ndk_tests'
INSTALLED_SHARED = Path('/home/alex/work/pocket4-current-host-r6-source-01')
SHARED_MANIFEST = '002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'
CONTRACT_BYTES = 11359
CONTRACT_SHA = 'f92d2598221c5bf65e783df39864879a2056da47f794680668b34df11f97da49'
MAIN_EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
BASELINE_SHA = '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA = 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
CURRENT_GUARD_SHA = '96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150'
OUTPUT_LIMIT = 262144
APK_LIMIT = 33554432
HASH_SECONDS = 20


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(fd):
    s=os.fstat(fd)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,
            'nlink':s.st_nlink,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}


def baseline_binding(guard, baseline, fixture, scope):
    fixture.validate_scope(scope)
    need(baseline.get('schema')=='pocket4-main-current-baseline-v2' and
         baseline.get('kind')=='current-cell-generation' and
         baseline.get('deployment_performed') is False and 'main_deployed' not in baseline and
         baseline['framework_epoch']['sha256']==MAIN_EPOCH==guard.MAIN_EPOCH and
         guard.BASELINE_SHA==BASELINE_SHA and guard.QUALIFICATION_SHA==QUALIFICATION_SHA and
         baseline.get('framework_exit_cause_resolved') is False and
         baseline.get('whole_app_production_ready') is False,
         'ACTUAL_CURRENT_MAIN_BASELINE_REQUIRED')
    need(PACKAGE not in baseline['packages'],'NEW_FIXTURE_MUST_NOT_ADOPT_BASELINE_APP')
    protected=set(baseline['packages'].values())
    need(all(type(x) is int for x in protected),'BASELINE_PACKAGE_UID_SCHEMA')
    need(scope['uid'] is None or scope['uid'] not in protected,'FIXTURE_UID_ALIASES_BASELINE_APP')
    return protected


def command_with_bound(context, argv, options):
    """Preserve actual Flow.command lifecycle; constrain its private output files.
    The lower soft file-size limit is inherited by the new helper process. The
    current worker limit is restored on every path before the caller proceeds.
    This is a new fixture seam and is not yet a qualified runtime control.
    """
    need(options['close_fds'] is True and options['stdout']==subprocess.PIPE and
         options['stderr']==subprocess.PIPE,'EXACT_SHARED_RUNNER_PROTOCOL_REQUIRED')
    prior=resource.getrlimit(resource.RLIMIT_FSIZE)
    need(all(v==resource.RLIM_INFINITY or v>=OUTPUT_LIMIT for v in prior),
         'CURRENT_FILE_SIZE_LIMIT_TOO_SMALL')
    first=None
    changed=False
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT_LIMIT,prior[1]))
        changed=True
        need(resource.getrlimit(resource.RLIMIT_FSIZE)==(OUTPUT_LIMIT,prior[1]),
             'COMMAND_OUTPUT_LIMIT_NOT_APPLIED')
        result=context.recorder.Flow.command(context,argv,options['timeout'],
            mutation=context._android_mutation,label='Android command',
            pass_fds=options['pass_fds'],check=False,host_env=options['env'])
        need(type(result.stdout) is bytes and type(result.stderr) is bytes and
             len(result.stdout)<=OUTPUT_LIMIT and len(result.stderr)<=OUTPUT_LIMIT,
             'COMMAND_OUTPUT_BOUND')
        return result
    except BaseException as error:
        first=error
        raise
    finally:
        if changed:
            try:
                resource.setrlimit(resource.RLIMIT_FSIZE,prior)
                need(resource.getrlimit(resource.RLIMIT_FSIZE)==prior,
                     'COMMAND_OUTPUT_LIMIT_RESTORE_FAILED')
            except BaseException as close_error:
                if first is None:
                    raise
                first.add_note('COMMAND_OUTPUT_LIMIT_RESTORE_FAILED:'+type(close_error).__name__)


class Context:
    def __init__(self,recorder,contract,target,environment,transport,main_guard,
                 step,plan,expected_init,deadline,fixture,scope,protected_uids):
        fixture.validate_scope(scope)
        need(contract.sha256==SHARED_MANIFEST and
             scope['Main_epoch']==MAIN_EPOCH and scope['package']==PACKAGE,
             'EXACT_CURRENT_NDK_CONTEXT_REQUIRED')
        need(type(deadline) in (int,float) and time.monotonic()<deadline,
             'FRESH_FIXTURE_CONTEXT_DEADLINE')
        self.recorder,self.contract,self.fixture=recorder,contract,fixture
        self.scope=json.loads(json.dumps(scope,sort_keys=True))
        self.scope_text=json.dumps(self.scope,sort_keys=True,separators=(',',':'))
        self.target,self.main_guard,self.step=target,main_guard,step
        self.command_index=0
        self.action_attempted=False
        self._android_mutation=False
        self.binding=types.SimpleNamespace(target=target)
        self.artifacts=None
        self.closed=self.poisoned=False
        self.deadline=deadline
        self.protected_uids=set(protected_uids)
        self.plan=[(list(a),b,c) for a,b,c in plan]
        self.next_command=0
        def record(kind,value):
            recorder.write_new(self.step/('transport-%03d.%s.json'%(value['sequence'],kind)),value)
        def runner(argv,**options):
            return command_with_bound(self,argv,options)
        self.transport=transport.BoundArun(target=target,environment=environment,
            guard=lambda action_attempted:self.guard(attempted=self.action_attempted),
            record=record,epoch_sha256=MAIN_EPOCH,init_pid=expected_init,
            package=PACKAGE,uid=scope['uid'],interactive_production=True,
            fixture_scope=scope,fixture_contract=fixture,runner=runner)

    def guard(self,attempted=False):
        self.fixture.validate_scope(self.scope)
        need(type(attempted) is bool and not self.closed and time.monotonic()<self.deadline,
             'OPEN_FIXED_FIXTURE_CONTEXT_DEADLINE')
        need(json.dumps(self.scope,sort_keys=True,separators=(',',':'))==self.scope_text,
             'FIXTURE_SCOPE_CHANGED')
        self.main_guard()
        self.target.verify()
        if self.artifacts is not None:
            self.artifacts.verify_held()

    def android(self,argv,timeout=20,*,mutation=False):
        try:
            need(not self.closed and not self.poisoned,'FAILED_FIXTURE_CONTEXT_CANNOT_RETRY')
            need(self.next_command<len(self.plan),'FIXED_FIXTURE_PLAN_EXHAUSTED')
            need(type(mutation) is bool and
                 (list(argv),timeout,mutation)==self.plan[self.next_command],
                 'ONLY_EXACT_ORDERED_FIXTURE_COMMAND_ALLOWED')
            self.next_command+=1
            self._android_mutation=mutation
            return self.transport(argv,timeout)
        except BaseException:
            self.poisoned=True
            raise
        finally:
            self._android_mutation=False

    def close(self):
        self.closed=True
        self.target.close()


def open_context(sources,fixture,scope,step,plan,result,deadline):
    fixture.pending_gate()
    # The future actual binder must qualify source, build, terminal, lock,
    # nonce and installed identity before this source-only barrier is removed.
    sources.verify()
    raw=sources.fixed_reference(INSTALLED_SHARED/'source_contract.py',CONTRACT_BYTES,CONTRACT_SHA)
    source=sources.module(raw,INSTALLED_SHARED/'source_contract.py','ndk_shared_contract')
    contract=source.SourceContract(INSTALLED_SHARED/'source-manifest.json',SHARED_MANIFEST)
    recorder=contract.load('recorder.py','ndk_shared_command_only')
    held=contract.load('references/held_runtime_r5.py','ndk_actual_held_main')
    binding=contract.load('main_binding.py','ndk_shared_classpath_only')
    current=contract.load('current_baseline_guard.py','ndk_current_baseline_guard')
    need(contract.files['current_baseline_guard.py']['sha256']==CURRENT_GUARD_SHA,
         'CURRENT_GUARD_PIN_CHANGED')
    baseline=current.current_baseline()
    protected=baseline_binding(current,baseline,fixture,scope)
    _,epoch,_,_=current.source_modules()
    target=None
    def guard():
        need(time.monotonic()<deadline,'FIXTURE_PHASE_DEADLINE')
        sources.verify()
        contract.verify()
        helper=source.bounded_file(source.HELPER_PATH,source.HELPER_BYTES)
        need(len(helper)==source.HELPER_BYTES and sha(helper)==source.HELPER_SHA,
             'HELD_HELPER_CONTENT_CHANGED')
        observed=current.current_guard(baseline,action_attempted=False)
        if target is not None:
            target.verify()
        return observed
    result['Main_before']=guard()
    result['shared_helper']=source.verify_shared_helper()
    expected=baseline['framework_epoch']['binding']['processes']['init']
    proc=os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    first=None
    try:
        actual=held.proc_identity_at(proc,expected['host_pid'],min(deadline,time.monotonic()+3))
    except BaseException as error:
        first=error
        raise
    finally:
        try:
            os.close(proc)
        except BaseException as close_error:
            if first is None:
                raise
            first.add_note('fixture init proc FD close:'+type(close_error).__name__)
    need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')
    try:
        target=held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA)
        guard()
        app=contract.load('references/android_app.py','ndk_discovery_only')
        discovery=sources.load('current_discovery.py','ndk_current_discovery')
        need(discovery.BASELINE_SHA==BASELINE_SHA and
             discovery.QUALIFICATION_SHA==QUALIFICATION_SHA and discovery.MAIN_EPOCH==MAIN_EPOCH,
             'CURRENT_DISCOVERY_SOURCE_BINDING_REQUIRED')
        init,discovered,status=discovery.discover_current(app,baseline,epoch,guard)
        need(init==expected['host_pid'] and status['host_pid']==baseline['status']['host_pid'],
             'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath=binding.main_classpaths(held,target,baseline['framework_epoch'],epoch,guard)
        need(all(discovered.get(k)==v for k,v in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        transport=sources.load('fixture_transport.py','ndk_bound_transport')
        environment=transport.environment_values(discovered)
        context=Context(recorder,contract,target,environment,transport,guard,
            step,plan,expected['host_pid'],deadline,fixture,scope,protected)
        # Full classpaths/identity are retained privately at the owned step.
        recorder.write_new(step/'held-main-binding.private.json',{
            'target':target.record,'classpath':classpath,'shared_helper':result['shared_helper'],
            'fixture_scope':scope,'R6_primitive_manifest':SHARED_MANIFEST,
            'commercial_Flow_or_scope_instantiated':False})
        result['held_main_binding']={'file':'held-main-binding.private.json',
            'same_current_Main8':True,'six_namespace_FDs':6,
            'numeric_PID_namespace_entry':False,'private_body_exported':False}
        return context,binding,lambda:current.current_guard(baseline,action_attempted=False)
    except BaseException as primary:
        if target is not None:
            try:
                target.close()
            except BaseException as secondary:
                primary.add_note('held target close:'+type(secondary).__name__)
        raise


class InstalledFixture:
    """One actual APK and two exact owned data directories; no commercial data."""
    def __init__(self,context,metadata,path,build,binding,expected=None):
        self.context,self.binding,self.build=context,binding,build
        need(metadata['package']==PACKAGE and metadata['user']==0 and
             metadata['uid'] not in context.protected_uids,'NEW_FIXED_FIXTURE_UID_REQUIRED')
        need(context.scope['uid'] is None or metadata['uid']==context.scope['uid'],
             'INSTALLED_UID_DIFFERS_FROM_SCOPE')
        self.metadata=dict(metadata)
        self.path=path
        self.expected=expected
        self.opened=[]
        self.record=None
        self.closed=False
        try:
            fd=context.target.open_root(path,os.O_RDONLY|os.O_NOFOLLOW)
            self.opened.append(fd)
            row=self._hash(fd)
            directories={}
            for kind in ('user','user_de'):
                name='/data/'+kind+'/0/'+PACKAGE
                data_fd=context.target.open_root(name,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
                self.opened.append(data_fd)
                value=identity(data_fd)
                need(stat.S_ISDIR(value['mode']) and value['uid']==metadata['uid'],
                     'FIXTURE_DATA_DIRECTORY_UID_CHANGED')
                directories[kind]={'path':name,**{k:value[k] for k in
                    ('device','inode','mode','uid','gid')}}
            self.record={'package':PACKAGE,'uid':metadata['uid'],'user':0,
                'version_code':metadata['version_code'],'artifact':row,'directories':directories,
                'signer_sha256_from_identical_build_APK':build['signer_sha256'],
                'signer_independently_read_on_device':False}
            if expected is not None:
                need(self.record==expected,'ACTUAL_INSTALLED_FIXTURE_TUPLE_CHANGED')
            self.verify_held()
            context.artifacts=self
        except BaseException as primary:
            try:
                self.close()
            except BaseException as secondary:
                primary.add_note('installed fixture FD close:'+type(secondary).__name__)
            raise

    def _hash(self,fd):
        first=identity(fd)
        need(stat.S_ISREG(first['mode']) and first['nlink']==1 and
             first['uid']==first['gid']==1000 and not first['mode']&0o022 and
             first['bytes']==self.build['APK']['bytes'] and 0<first['bytes']<=APK_LIMIT,
             'ACTUAL_INSTALLED_APK_SHAPE_DIFFERS')
        os.lseek(fd,0,os.SEEK_SET)
        count=0
        digest=hashlib.sha256()
        deadline=min(self.context.deadline,time.monotonic()+HASH_SECONDS)
        while True:
            need(time.monotonic()<deadline,'FIXTURE_APK_HASH_DEADLINE')
            block=os.read(fd,min(65536,first['bytes']+1-count))
            if not block:
                break
            count+=len(block)
            need(count<=first['bytes'],'FIXTURE_APK_GREW')
            digest.update(block)
        need(count==first['bytes'] and identity(fd)==first and
             digest.hexdigest()==self.build['APK']['sha256'],
             'INSTALLED_APK_NOT_EXACT_ORIGINAL_SIGNED_BUILD')
        return {'path':self.path,'file':first,'sha256':digest.hexdigest()}

    def verify_held(self):
        need(not self.closed and self.record is not None and len(self.opened)==3,
             'OPEN_FIXED_INSTALLED_FIXTURE_REQUIRED')
        self.context.target.verify()
        need(identity(self.opened[0])==self.record['artifact']['file'],'HELD_FIXTURE_APK_CHANGED')
        for index,kind in enumerate(('user','user_de'),1):
            value=identity(self.opened[index])
            expected=self.record['directories'][kind]
            need(all(value[k]==expected[k] for k in ('device','inode','mode','uid','gid')),
                 'HELD_FIXTURE_DATA_DIRECTORY_CHANGED')
            current=self.context.target.open_root(expected['path'],os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
            first=None
            try:
                row=identity(current)
                need(all(row[k]==expected[k] for k in ('device','inode','mode','uid','gid')),
                     'NAMED_FIXTURE_DATA_DIRECTORY_CHANGED')
            except BaseException as error:
                first=error
                raise
            finally:
                try:
                    os.close(current)
                except BaseException as close_error:
                    if first is None:
                        raise
                    first.add_note('named data FD close:'+type(close_error).__name__)
        # Original RunAllTests writes /data/data, so qualify that named view
        # against the same held installed user-0 data directory. A usual alias
        # layout is not assumed, and no other package path is read.
        alias=self.context.target.open_root('/data/data/'+PACKAGE,
            os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
        primary=None
        try:
            actual=identity(alias)
            expected=self.record['directories']['user']
            need(all(actual[k]==expected[k] for k in ('device','inode','mode','uid','gid')),
                 'ORIGINAL_XML_DATA_VIEW_DIFFERS_FROM_OWN_USER_ZERO_DIRECTORY')
        except BaseException as error:
            primary=error
            raise
        finally:
            try:
                os.close(alias)
            except BaseException as close_error:
                if primary is None:
                    raise
                primary.add_note('original XML data view FD close:'+type(close_error).__name__)
        raw,_=self.context.target.read_file('/data/system/packages.list',1048576)
        self.binding.package_uids(raw,{PACKAGE:self.metadata['uid']})
        del raw
        self.context.target.verify()

    def revalidate(self):
        self.verify_held()
        row=self._hash(self.opened[0])
        named=self.context.target.open_root(self.path,os.O_RDONLY|os.O_NOFOLLOW)
        first=None
        try:
            need(identity(named)==row['file'],'NAMED_FIXTURE_APK_CHANGED')
        except BaseException as error:
            first=error
            raise
        finally:
            try:
                os.close(named)
            except BaseException as close_error:
                if first is None:
                    raise
                first.add_note('named APK FD close:'+type(close_error).__name__)
        need(row==self.record['artifact'],'FIXTURE_APK_AFTER_DIFFERS')
        return dict(self.record)

    def xml_absent(self):
        need(not self.context.target.exists(self.context.fixture.XML_PATH),
             'STALE_NATIVE_XML_PREEXISTS')

    def read_fresh_xml(self,run_observation,retirement_observation):
        need(run_observation.get('pre_run_XML_absent') is True and
             run_observation.get('instrumentation_verified') is True and
             run_observation.get('installed_before')==self.record and
             run_observation.get('scope',{}).get('phase')=='run' and
             run_observation['scope']['uid']==self.metadata['uid'] and
             retirement_observation.get('scope',{}).get('phase')=='retire' and
             retirement_observation['scope']['uid']==self.metadata['uid'] and
             run_observation['scope']['attempt_nonce'] !=
                retirement_observation['scope']['attempt_nonce'] and
             retirement_observation.get('force_stop_completed') is True and
             retirement_observation.get('two_complete_empty_own_UID_tables') is True and
             retirement_observation.get('task_set_restored') is True,
             'FRESH_INSTRUMENTATION_AND_INDEPENDENT_RETIREMENT_REQUIRED')
        self.revalidate()
        deadline=min(self.context.deadline,time.monotonic()+5)
        raw,record=self.context.target.read_file(self.context.fixture.XML_PATH,
            self.context.fixture.MAX_XML,single_link=True,deadline=deadline)
        need(record['uid']==self.metadata['uid'] and record['nlink']==1 and
             not record['mode']&0o022,'XML_IS_NOT_OWNED_BY_INSTALLED_FIXTURE')
        again,named=self.context.target.read_file(self.context.fixture.XML_PATH,
            self.context.fixture.MAX_XML,single_link=True,deadline=deadline)
        need(named==record and again==raw,'OWN_XML_NAMED_CONTENT_CHANGED')
        value=self.context.fixture.native_xml(raw)
        self.verify_held()
        value['held_file']=record
        value['same_actual_fixture_UID']=self.metadata['uid']
        value['run_attempt_nonce']=run_observation['scope']['attempt_nonce']
        value['retirement_attempt_nonce']=retirement_observation['scope']['attempt_nonce']
        value['freshness_and_same_owned_UID_binding_still_required']=False
        return value

    def close(self):
        self.closed=True
        failures=[]
        count=len(self.opened)
        for fd in reversed(self.opened):
            try:
                os.close(fd)
            except BaseException as error:
                failures.append({'type':type(error).__name__,'errno':getattr(error,'errno',None)})
        self.opened=[]
        if self.context.artifacts is self:
            self.context.artifacts=None
        need(not failures,'FIXTURE_ARTIFACT_FD_CLOSE_FAILED')
        return {'held_APK_and_data_FDs_closed':count,'all_tracked_artifact_FDs_closed':True}
