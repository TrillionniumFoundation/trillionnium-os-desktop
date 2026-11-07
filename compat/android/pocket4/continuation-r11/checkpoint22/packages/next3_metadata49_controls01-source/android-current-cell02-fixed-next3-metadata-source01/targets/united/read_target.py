#!/usr/bin/env python3
"""One fixed United metadata read on current cell02; no runtime authority yet.

No App launch, instrumentation, v2 helper, permission or settings operation.
The original Bili Flow/BoundArun business scope is never instantiated or patched.
Only its pinned command-observation function and shared held-entry primitives
are reused. Default PLAN performs no file or device read.
"""
import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

ROOT = Path('/home/alex/work/pocket4-current-cell02-united-metadata-01')
SOURCE_PATH = ROOT/'source/read_target.py'
NONCE = '__FRESH_METADATA_NONCE__'
PACKAGE = 'com.united.mobile.android'
USER = 0
HISTORICAL_VERSION = 3617
RECORDER_ROOT = Path('/home/alex/work/pocket4-current-host-r6-source-01')
REFERENCE_SHA = '0a4a9f0d02b2a62f2b902983e43360c751a8f1952fb9ae7399850b112cb50a89'
RECORDER_MANIFEST = '002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'
SOURCE_CONTRACT_SHA = 'f92d2598221c5bf65e783df39864879a2056da47f794680668b34df11f97da49'
CURRENT_EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
BASELINE_SHA = '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA = 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
DISCOVERY_SHA = '9ed0069897faebba50cec3d93b08da54f1c791d6e2e775d26ec798c38b227886'
DISCOVERY_BYTES = 8332
ACTION_LOCK_WAIT_SECONDS = 5.0
ACTION_LOCK_POLL_SECONDS = 0.05
LIST = ['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',PACKAGE]
PATHS = ['/system/bin/cmd','package','path','--user','0',PACKAGE]
RESOLVE = ['/system/bin/cmd','package','resolve-activity','--brief','--user','0',
           '-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER',PACKAGE]
COMMANDS = [LIST, PATHS, RESOLVE, PATHS, LIST]
FILE_LIMIT = 256 * 1024 * 1024
TOTAL_LIMIT = 512 * 1024 * 1024
HASH_SECONDS = 45
FILE_COUNT = 16
WORK_SECONDS = 140


def need(value, message):
    if not value:
        raise RuntimeError(message)


require = need


def acquire_action_lock(path, observation):
    """Wait only for the original exclusive lock; return one owned FD."""
    start = time.monotonic()
    deadline = start + ACTION_LOCK_WAIT_SECONDS
    observation.update({'path':str(path),'wait_limit_seconds':ACTION_LOCK_WAIT_SECONDS,
        'phase':'open','attempts':0,'busy_attempts':0,'acquired':False,
        'fd_closed_on_error':False,'Android_actions_attempted':0})
    fd = None
    first_busy = None
    try:
        fd = os.open(path, os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC, 0o600)
        observation['phase'] = 'validate_opened_inode'
        initial = os.fstat(fd)
        require(stat.S_ISREG(initial.st_mode) and initial.st_nlink == 1 and initial.st_uid == 0,
                'UNSAFE_ACTION_LOCK')
        observation['opened_identity'] = {'device':initial.st_dev,'inode':initial.st_ino,
            'mode':initial.st_mode,'uid':initial.st_uid,'gid':initial.st_gid,'nlink':initial.st_nlink}
        while True:
            observation['elapsed_seconds'] = time.monotonic()-start
            if time.monotonic() >= deadline:
                observation['phase'] = 'lock_deadline'
                if first_busy is not None:
                    raise first_busy
                raise TimeoutError(errno.ETIMEDOUT, 'ACTION_LOCK_ADMISSION_DEADLINE')
            observation['phase'] = 'flock_exclusive_nonblocking'
            observation['attempts'] += 1
            try:
                fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:
                observation['last_errno'] = error.errno
                if error.errno != errno.EAGAIN:
                    raise
                if first_busy is None:
                    first_busy = error
                observation['busy_attempts'] += 1
                observation['phase'] = 'waiting_same_open_inode'
                remaining = deadline-time.monotonic()
                if remaining > 0:
                    time.sleep(min(ACTION_LOCK_POLL_SECONDS,remaining))
                continue
            observation['phase'] = 'verify_locked_inode'
            held = os.fstat(fd)
            named = os.stat(path, follow_symlinks=False)
            require(all(stat.S_ISREG(row.st_mode) and row.st_nlink == 1 and row.st_uid == 0 and
                        (row.st_dev,row.st_ino) == (initial.st_dev,initial.st_ino)
                        for row in (held,named)), 'ACTION_LOCK_NAME_OR_HELD_INODE_CHANGED')
            require(time.monotonic() < deadline, 'ACTION_LOCK_ADMISSION_EXCEEDED_DEADLINE')
            observation.update({'phase':'acquired','acquired':True,
                'elapsed_seconds':time.monotonic()-start,'same_inode_confirmed':True})
            return fd
    except BaseException as original:
        observation['error_type'] = type(original).__name__
        observation['errno'] = getattr(original,'errno',None)
        observation['elapsed_seconds'] = time.monotonic()-start
        if fd is not None:
            try:
                os.close(fd)
                observation['fd_closed_on_error'] = True
            except BaseException as secondary:
                observation['close_error'] = {'type':type(secondary).__name__,
                    'errno':getattr(secondary,'errno',None),'message':str(secondary)}
                original.add_note('action lock FD close failed: '+repr(secondary))
        raise




def current_baseline_scope(reference, baseline):
    need(type(baseline) is dict and baseline.get('schema')=='pocket4-main-current-baseline-v2' and
         baseline.get('kind')=='current-cell-generation' and baseline.get('deployment_performed') is False and
         'main_deployed' not in baseline and baseline.get('framework_exit_cause_resolved') is False and
         baseline.get('whole_app_production_ready') is False and
         baseline['framework_epoch']['sha256']==reference.EPOCH==CURRENT_EPOCH and
         reference.BASELINE_SHA==BASELINE_SHA and reference.QUALIFICATION_SHA==QUALIFICATION_SHA,
         'EXACT_CURRENT_CELL02_BASELINE_REQUIRED')
    # This observation does not add PACKAGE to the immutable four-target baseline.
    return {'schema':'pocket4-fixed-new-target-metadata-scope-v1',
        'current_baseline_schema':baseline['schema'],'epoch_sha256':CURRENT_EPOCH,
        'current_baseline_sha256':BASELINE_SHA,'current_baseline_qualification_sha256':QUALIFICATION_SHA,
        'package':PACKAGE,'user':USER,'UID_version_APKs_and_data_directories_pending':True,
        'baseline_packages_modified':False,'Bili_scope_reused':False,'business_action_authority':False}


def discover_main(app, baseline, epoch, guard):
    discovery=load(SOURCE_PATH.parent/'current_discovery.py',DISCOVERY_SHA,
                   'fixed_target_current_discovery',DISCOVERY_BYTES)
    need(discovery.BASELINE_SHA==BASELINE_SHA and discovery.QUALIFICATION_SHA==QUALIFICATION_SHA and
         discovery.MAIN_EPOCH==CURRENT_EPOCH,'EXACT_CURRENT_DISCOVERY_AUTHORITY')
    return discovery.discover_current(app,baseline,epoch,guard)


def directory_identity(fd):
    value=os.fstat(fd)
    need(stat.S_ISDIR(value.st_mode),'FIXED_TARGET_DATA_DIRECTORY_REQUIRED')
    return {'device':value.st_dev,'inode':value.st_ino,'mode':value.st_mode,
            'uid':value.st_uid,'gid':value.st_gid}


class DataDirectories:
    """Hold only the two exact directory inodes; never enumerate or read contents."""
    def __init__(self,target,uid,binding,deadline):
        need(type(uid) is int and 10000<=uid<100000,'CURRENT_TARGET_UID_REQUIRED')
        self.target=target;self.uid=uid;self.binding=binding;self.deadline=deadline
        self.rows=[];self.closed=False
        try:
            for kind in ('user','user_de'):
                need(time.monotonic()<deadline,'TARGET_DIRECTORY_OBSERVATION_DEADLINE')
                path='/data/'+kind+'/0/'+PACKAGE
                fd=target.open_root(path,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
                self.rows.append({'path':path,'fd':fd})
                row=directory_identity(fd)
                need(row['device']>=0 and row['inode']>0 and row['uid']==uid,
                     'CURRENT_TARGET_DATA_DIRECTORY_OWNER_REQUIRED')
                self.rows[-1]['identity']=row
            self.verify()
        except BaseException as primary:
            try:self.close()
            except BaseException as secondary:primary.add_note('target directory close: '+repr(secondary))
            raise

    def verify(self):
        need(not self.closed and len(self.rows)==2,'TWO_OPEN_FIXED_TARGET_DIRECTORIES_REQUIRED')
        need(time.monotonic()<self.deadline,'TARGET_DIRECTORY_OBSERVATION_DEADLINE')
        self.target.verify()
        raw,_=self.target.read_file('/data/system/packages.list',1024*1024,
                                    deadline=min(self.deadline,time.monotonic()+5))
        self.binding.package_uids(raw,{PACKAGE:self.uid})
        del raw
        for row in self.rows:
            need(directory_identity(row['fd'])==row['identity'],
                 'HELD_TARGET_DATA_DIRECTORY_IDENTITY_CHANGED')
            fd=self.target.open_root(row['path'],os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
            primary=None
            try:
                need(directory_identity(fd)==row['identity'],'NAMED_TARGET_DATA_DIRECTORY_CHANGED')
            except BaseException as error:
                primary=error;raise
            finally:
                try:os.close(fd)
                except BaseException as cleanup:
                    if primary is None:raise
                    primary.add_note('named directory close: '+repr(cleanup))
        self.target.verify()

    def record(self):
        self.verify()
        return [{'path':row['path'],**row['identity']} for row in self.rows]

    def close(self):
        if self.closed:return {'held_data_directory_FDs_closed':0,'contents_read':False}
        self.closed=True;errors=[];count=len(self.rows)
        for row in reversed(self.rows):
            try:os.close(row['fd'])
            except BaseException as error:errors.append(type(error).__name__)
        self.rows=[]
        need(not errors,'TARGET_DIRECTORY_FD_CLOSE_FAILED:'+repr(errors))
        return {'held_data_directory_FDs_closed':count,'contents_read':False}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=131072, expected=None, size=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        first=os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and 0<=first.st_size<=maximum,
             'FIXED_INPUT_SHAPE_OR_BOUND')
        data=bytearray()
        while len(data)<=maximum:
            block=os.read(fd,min(65536,maximum+1-len(data)))
            if not block:break
            data.extend(block)
        last=os.fstat(fd)
        keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        need(len(data)==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),
             'FIXED_INPUT_CHANGED')
        raw=bytes(data)
        need(expected is None or sha(raw)==expected,'FIXED_INPUT_SHA_CHANGED')
        need(size is None or len(raw)==size,'FIXED_INPUT_SIZE_CHANGED')
        return raw
    finally:os.close(fd)


def load(path, expected, name, size=None):
    raw=read(path,expected=expected,size=size)
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    return value


def error_row(phase, error):
    value={'phase':phase,'type':type(error).__name__,'message':str(error)}
    if isinstance(error,OSError):value['errno']=error.errno
    for key in ('command_observation','__notes__'):
        if hasattr(error,key):value[key]=getattr(error,key)
    return value


def remember(result, phase, error):
    row=error_row(phase,error)
    if result['error'] is None:result['error']=row
    else:result['secondary_errors'].append(row)
    result['ok']=False


def metadata(raw):
    match=re.fullmatch(re.escape('package:'+PACKAGE)+r' versionCode:([0-9]+) uid:([0-9]+)\n',
                       raw.decode('utf-8','strict'))
    need(match is not None,'ONE_EXACT_TICKET12306_USER0_METADATA_ROW_REQUIRED')
    version,uid=map(int,match.groups())
    need(0<version<2**63 and 10000<=uid<100000,'TICKET12306_METADATA_RANGE')
    return {'package':PACKAGE,'user':USER,'uid':uid,'version_code':version}


def apk_paths(raw):
    text=raw.decode('utf-8','strict')
    need(text.endswith('\n') and len(raw)<=16384,'TICKET12306_PATH_OUTPUT_BOUND')
    lines=text.splitlines()
    need(1<=len(lines)<=FILE_COUNT and all(x.startswith('package:') for x in lines),
         'TICKET12306_APK_PATH_ROWS_REQUIRED')
    paths=[x[len('package:'):] for x in lines]
    need(len(set(paths))==len(paths),'DUPLICATE_APK_PATH')
    parents=set()
    for path in paths:
        need(isinstance(path,str) and '\x00' not in path and len(path.encode())<=4096,
             'TICKET12306_PATH_SHAPE')
        parts=Path(path).parts
        need(len(parts)==6 and parts[:3]==('/','data','app') and
             re.fullmatch(r'~~[A-Za-z0-9_=-]+',parts[3]) and
             re.fullmatch(re.escape(PACKAGE)+r'-[A-Za-z0-9_=-]+',parts[4]) and
             (parts[5]=='base.apk' or re.fullmatch(r'split_[A-Za-z0-9_.-]+\.apk',parts[5])),
             'ONLY_EXACT_TICKET12306_INSTALL_DIRECTORY_APKS_MAY_BE_READ')
        parents.add(str(Path(path).parent))
    need(len(parents)==1 and sum(Path(x).name=='base.apk' for x in paths)==1,
         'ONE_TICKET12306_BASE_AND_ONE_INSTALL_DIRECTORY_REQUIRED')
    return sorted(paths)


def component(raw):
    need(isinstance(raw,bytes) and 0<len(raw)<=4096,'RESOLVE_OUTPUT_BOUND')
    text=raw.decode('ascii','strict')
    need(text.endswith('\n') and '\x00' not in text and
         all(c=='\n' or 32<=ord(c)<127 for c in text),'RESOLVE_OUTPUT_TEXT_SHAPE')
    lines=text.splitlines()
    need(1<=len(lines)<=16,'RESOLVE_OUTPUT_LINE_BOUND')
    candidates=[line.strip() for line in lines if
        re.fullmatch(r'[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+',line.strip())]
    need(len(candidates)==1,'ONE_CURRENT_LAUNCHER_COMPONENT_REQUIRED')
    value=candidates[0]
    need(re.fullmatch(re.escape(PACKAGE)+r'/(?:\.[A-Za-z_][A-Za-z0-9_.$]*|[A-Za-z_][A-Za-z0-9_.$]*)',value)
         is not None,'LAUNCHER_MUST_BELONG_TO_EXACT_TICKET12306_PACKAGE')
    return {'package':PACKAGE,'user':0,'component':value,
        'query_action':'android.intent.action.MAIN','query_category':'android.intent.category.LAUNCHER',
        'resolve_stdout_sha256':sha(raw),'fallback_used':False,
        'launch_performed':False,'later_launch_requires_new_current_binding':True}


def identity(fd):
    s=os.fstat(fd)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,
            'nlink':s.st_nlink,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}


class Context:
    """Only the exact pinned Flow.command method is used, never Flow.init/launch."""
    def __init__(self, recorder, contract, target, guard, result):
        self.recorder=recorder;self.contract=contract;self.target=target;self.check_main=guard
        self.result=result;self.step=ROOT/'evidence';self.command_index=0
        self.action_attempted=False;self.binding=types.SimpleNamespace(target=target)
        self.observations=[]

    def guard(self, attempted=False):
        need(attempted is False and self.action_attempted is False,'READ_ONLY_ACTION_SCOPE_CHANGED')
        self.check_main();self.target.verify()

    def command(self, arguments, environment):
        need(self.command_index<len(COMMANDS) and arguments==COMMANDS[self.command_index],
             'ONLY_FIVE_ORDERED_FIXED_READ_ONLY_COMMANDS_ALLOWED')
        self.guard()
        expected_index=self.command_index+1
        command=['/system/bin/env','-i']
        command += [key+'='+environment[key] for key in sorted(environment)]
        command += ['/system/xbin/su','2000','/system/bin/timeout','-k','2','10',*arguments]
        manager=None;entered=False;completed=None;primary=None;secondary=[]
        def fail(phase,error):
            nonlocal primary
            if primary is None:primary=error
            else:secondary.append(error_row(phase,error))
        try:
            manager=self.target.entry(command);argv,descriptors=manager.__enter__();entered=True
            need(len(descriptors)==7 and len(set(descriptors))==7 and
                 all(type(fd) is int and fd>=3 for fd in descriptors),'HELD_AUTHORITY_SET_DIFFERS')
            expected=[str(self.target.helper_path),'--parent-pid='+str(os.getpid()),
                      '--root-fd='+str(descriptors[0])]
            expected += ['--'+name+'-fd='+str(fd) for name,fd in
                         zip(('mnt','pid','uts','ipc','net','cgroup'),descriptors[1:])]
            need(list(argv)==expected+['--',*command],'EXACT_R4_HELD_PREFIX_AND_COMMAND_REQUIRED')
            completed=self.recorder.Flow.command(self,argv,15,mutation=False,label='Android command',
                pass_fds=tuple(descriptors),check=False,
                host_env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8'})
            need(completed.recorder_spawned and completed.recorder_joined and
                 not completed.host_timed_out and completed.returncode==0 and
                 completed.recorder_errors==[],'EXACT_JOINED_READ_ONLY_COMMAND_REQUIRED')
            need(len(completed.stdout)<=16384 and completed.stderr==b'',
                 'ONE_PACKAGE_COMMAND_OUTPUT_BOUND_OR_STDERR')
        except BaseException as error:fail('read_command',error)
        finally:
            # Flow.command has already saved the first command observation.
            # Release and post-guard must run independently and cannot erase it.
            if entered:
                try:manager.__exit__(None,None,None)
                except BaseException as error:fail('entry_release',error)
            try:self.guard()
            except BaseException as error:fail('post_command_Main_guard',error)
            row={'index':self.command_index,'argv':arguments,'operation':'package_identity_or_launcher_read',
                 'Android_UI_action':False,'entry_entered':entered,
                 'first_error':error_row('command',primary) if primary else None,
                 'secondary_errors':secondary}
            if completed is not None:
                row.update(returncode=completed.returncode,joined=completed.recorder_joined,
                           spawned=completed.recorder_spawned,host_timed_out=completed.host_timed_out,
                           recorder_errors=completed.recorder_errors,
                           stdout_sha256=sha(completed.stdout),stdout_bytes=len(completed.stdout),
                           stderr_sha256=sha(completed.stderr),stderr_bytes=len(completed.stderr))
            row['command_receipt_path']=str(self.step/('command-%03d.result.json'%expected_index))
            self.observations.append(row)
        if primary is not None:
            for row in secondary:primary.add_note(json.dumps(row,sort_keys=True))
            raise primary
        return completed.stdout


def execute(source_sha):
    need(os.getuid()==os.geteuid()==0,'ROOT_FIXED_READ_ONLY_REQUIRED')
    need(Path(__file__).resolve()==SOURCE_PATH and re.fullmatch('[0-9a-f]{64}',source_sha) and
         re.fullmatch('[0-9a-f]{32}',NONCE),
         'EXACT_NEW_SOURCE_PATH_AND_EXTERNAL_PIN_REQUIRED')
    read(SOURCE_PATH,expected=source_sha)
    need(ROOT.is_dir() and not (ROOT/'claim.json').exists(),'FRESH_SINGLE_ATTEMPT_ROOT_REQUIRED')
    reference=load(RECORDER_ROOT/'current_coordinator.py',REFERENCE_SHA,'fixed_target_current_main_reference',7442)
    root_stat=ROOT.lstat()
    need(stat.S_ISDIR(root_stat.st_mode) and root_stat.st_uid==0 and not root_stat.st_mode&0o077,
         'ROOT_PRIVATE_NEW_EVIDENCE_DIRECTORY_REQUIRED')
    reference.write_new(ROOT/'claim.json',{'schema':1,'nonce':NONCE,'package':PACKAGE,
                                         'source_sha256':source_sha,'automatic_retry':False})
    (ROOT/'evidence').mkdir(mode=0o700)
    result={'schema':1,'scope':'one exact United user0 current-cell02 metadata observation',
            'nonce':NONCE,'package':PACKAGE,'source_sha256':source_sha,'ok':False,
            'error':None,'secondary_errors':[],'UI_actions':0,'App_launches':0,
            'instrumentation_calls':0,'permission_grants':0,'settings_writes':0,
            'old_v2_helper_called':False,'Bili_scope_modified':False,'automatic_retry':False,
            'whole_app_production_ready':False,'signer_certificate_independently_verified':False,
            'APK_bytes_exported':False,'current_package_inventory_scanned_or_exported':False,
            'UID_version_APK_paths_are_current_observations_not_historical_assumptions':True,
            'target_data_directory_contents_read':False,'private_baseline_exported':False,
            'immutable_baseline_packages_modified':False,'business_action_authority':False,
            'future_install_or_UI_requires_separate_target_scope':True,
            'historical_matrix_sha256':'05e74a719281abab717464978d85393dec8d0d528c1e7ccbd93691f156ce56e4'}
    target=ctx=directories=None;lock=None;opened=[];phase='source';started=time.monotonic();guard=None
    try:
        source=load(RECORDER_ROOT/'source_contract.py',SOURCE_CONTRACT_SHA,'ticket12306_shared_source_contract')
        contract=source.SourceContract(RECORDER_ROOT/'source-manifest.json',RECORDER_MANIFEST)
        recorder=contract.load('recorder.py','ticket12306_command_reference')
        held=contract.load('references/held_runtime_r5.py','ticket12306_held_reference')
        binding=contract.load('main_binding.py','ticket12306_classpath_reference')
        transport=contract.load('bound_android_transport.py','ticket12306_environment_reference')
        activation=reference.current_baseline()
        result['current_metadata_scope']=current_baseline_scope(reference,activation)
        epoch=reference.module(reference.read(reference.EPOCH_SOURCE,expected=reference.EPOCH_SOURCE_SHA),
                               reference.EPOCH_SOURCE,'ticket12306_epoch_reference')
        def fixed_guard(check_deadline=True):
            if check_deadline:
                need(time.monotonic()-started<WORK_SECONDS,'WHOLE_READ_DEADLINE')
            contract.verify();read(SOURCE_PATH,expected=source_sha)
            read(RECORDER_ROOT/'current_coordinator.py',expected=REFERENCE_SHA,size=7442)
            read(SOURCE_PATH.parent/'current_discovery.py',expected=DISCOVERY_SHA,size=DISCOVERY_BYTES)
            reference.read(recorder.APP,expected=recorder.APP_SHA)
            read(source.HELPER_PATH,maximum=source.HELPER_BYTES,
                 expected=source.HELPER_SHA,size=source.HELPER_BYTES)
            return reference.main_guard(activation,epoch)
        guard=fixed_guard
        result['Main_before']=guard()
        result['shared_helper']=source.verify_shared_helper()
        result['action_lock']={};phase='action_lock_admission'
        lock=acquire_action_lock(recorder.ACTION_LOCK,result['action_lock'])
        guard()
        expected=activation['framework_epoch']['binding']['processes']['init']
        phase='held_Main_binding'
        proc=os.open('/proc/'+str(expected['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:actual=held.proc_identity_at(proc,expected['host_pid'],time.monotonic()+3)
        finally:os.close(proc)
        need(binding.same_epoch_identity(actual,expected),'FIXED_MAIN_INIT_IDENTITY_CHANGED')
        target=held.HeldTarget(actual,source.HELPER_PATH,source.HELPER_SHA)
        guard()
        app=load(Path(recorder.APP),recorder.APP_SHA,'ticket12306_existing_discovery_reference',37574)
        init,discovered,status=discover_main(app,activation,epoch,guard)
        need(init==expected['host_pid'] and status['host_pid']==activation['status']['host_pid'],
             'FIXED_MAIN_DISCOVERY_CHANGED')
        values,classpath=binding.main_classpaths(held,target,activation['framework_epoch'],epoch,guard)
        need(all(discovered.get(key)==value for key,value in values.items()),'CLASSPATH_DISCOVERY_CHANGED')
        environment=transport.environment_values(discovered)
        reference.write_new(ROOT/'held-main-binding.json',{'target':target.record,'classpath':classpath,
                             'shared_helper':result['shared_helper'],'package_scope':PACKAGE})
        ctx=Context(recorder,contract,target,guard,result)
        phase='before_package_metadata';before=metadata(ctx.command(LIST,environment))
        result['metadata_before']=before
        phase='current_target_directory_observation'
        directories=DataDirectories(target,before['uid'],binding,started+WORK_SECONDS)
        result['data_directories_before']=directories.record()
        result['historical_version_code']=HISTORICAL_VERSION
        result['historical_version_still_matches']=before['version_code']==HISTORICAL_VERSION
        phase='before_package_paths';paths=apk_paths(ctx.command(PATHS,environment));result['apk_paths_before']=paths
        total=0;deadline=min(started+WORK_SECONDS,time.monotonic()+HASH_SECONDS);artifacts=[]
        phase='held_APK_hash'
        for path in paths:
            need(time.monotonic()<deadline,'APK_STREAM_HASH_DEADLINE')
            fd=target.open_root(path,os.O_RDONLY|os.O_NOFOLLOW);opened.append(fd)
            first=identity(fd)
            need(stat.S_ISREG(first['mode']) and first['nlink']==1 and
                 first['uid']==first['gid']==1000 and not first['mode']&0o022 and
                 0<first['bytes']<=FILE_LIMIT,'TICKET12306_INSTALLED_APK_SHAPE_OR_BOUND')
            need(total+first['bytes']<=TOTAL_LIMIT,'TICKET12306_APK_TOTAL_BOUND')
            digest=hashlib.sha256();count=0
            while True:
                need(time.monotonic()<deadline,'APK_STREAM_HASH_DEADLINE')
                block=os.read(fd,min(65536,first['bytes']+1-count))
                if not block:break
                count+=len(block);need(count<=first['bytes'],'APK_GREW_DURING_HASH');digest.update(block)
            need(count==first['bytes'] and identity(fd)==first,'APK_CHANGED_DURING_HASH')
            artifacts.append({'path':path,'sha256':digest.hexdigest(),'held_file':first})
            total+=count
        phase='current_launcher_resolution'
        result['launcher_resolution']=component(ctx.command(RESOLVE,environment))
        phase='after_package_paths'
        need(apk_paths(ctx.command(PATHS,environment))==paths,'TICKET12306_INSTALL_PATHS_CHANGED')
        phase='after_package_metadata';after=metadata(ctx.command(LIST,environment))
        result['metadata_after']=after;need(after==before,'TICKET12306_PACKAGE_METADATA_CHANGED')
        phase='held_APK_revalidation'
        for fd,row in zip(opened,artifacts):
            need(identity(fd)==row['held_file'],'HELD_APK_CHANGED_AFTER_PACKAGE_RECHECK')
            again=target.open_root(row['path'],os.O_RDONLY|os.O_NOFOLLOW)
            try:need(identity(again)==row['held_file'],'APK_PATH_NO_LONGER_NAMES_HELD_FILE')
            finally:os.close(again)
        need(ctx.command_index==len(COMMANDS)==5,'EXACT_FIVE_READ_COMMANDS_COMPLETED')
        result['data_directories_after']=directories.record()
        need(result['data_directories_before']==result['data_directories_after'],
             'CURRENT_TARGET_DATA_DIRECTORY_CHAIN_CHANGED')
        target.verify();guard()
        result.update(artifacts=artifacts,total_apk_bytes=total,actual_package_UID_version_APK_chain_stable=True,
                      package_read_commands_completed=ctx.command_index,ok=True)
    except BaseException as error:remember(result,phase,error)
    finally:
        if ctx is not None:result['command_observations']=ctx.observations
        for fd in reversed(opened):
            try:os.close(fd)
            except BaseException as error:remember(result,'held_APK_fd_close',error)
        if directories is not None:
            try:result['target_directory_cleanup']=directories.close()
            except BaseException as error:remember(result,'target_directory_fd_close',error)
        if target is not None:
            try:target.close();result['held_binding_released']=True
            except BaseException as error:remember(result,'held_binding_release',error)
        if guard is not None:
            try:
                result['Main_after']=guard(False)
                need(result.get('Main_before')==result['Main_after'],'MAIN_BEFORE_AFTER_DIFFER')
                result['final_Main_guard_passed']=True
            except BaseException as error:remember(result,'final_Main_guard',error)
        if lock is not None:
            try:os.close(lock);result['action_lock_released']=True
            except BaseException as error:remember(result,'action_lock_release',error)
        result['seconds']=time.monotonic()-started
    pin=reference.write_new(ROOT/'result.json',result)
    # This complete bounded result has no raw UI, unrelated package list or APK.
    envelope={'result_file':pin,'result':result}
    output=json.dumps(envelope,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    need(len(output.encode())<=98304,'ONE_PACKAGE_RESULT_BOUND')
    print(output,flush=True)
    return 0 if result['ok'] else 1


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collect-once',action='store_true');p.add_argument('--source-sha256')
    a=p.parse_args(argv)
    if not a.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','package':PACKAGE,'root':str(ROOT),'nonce':NONCE,
                          'ordered_commands':COMMANDS,'Android_UI_actions':0,'remote_actions':0}))
        return 0
    return execute(a.source_sha256)


if __name__=='__main__':raise SystemExit(main())
