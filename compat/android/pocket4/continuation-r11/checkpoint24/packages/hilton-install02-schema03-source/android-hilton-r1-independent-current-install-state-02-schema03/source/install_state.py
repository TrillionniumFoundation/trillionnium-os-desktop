#!/usr/bin/env python3
"""One independent Hilton QA install and no-UiAutomation state observation.

Default PLAN has no device or filesystem action. The exact signed new helper
must be absent, including retained records/all users. Only one explicit -R/-t
install is allowed, with no retry or automatic uninstall. Commercial Hilton
is never launched; its exact 4 current APKs are held/read-only before and
after. No Bili Flow, legacy helper, permission grant, settings, UI or audio.
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
import sys
import time
import types

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-owned-hilton-qa-r1-install-state-02')
SOURCE = ROOT/'source'
WORKER_ROOT = ROOT/'worker'
STEP = WORKER_ROOT/'steps/install-state-01'
NONCE = '679d2fb7990077af6fddb053ebafbee1'
STATE_NONCE = 'd54753e10c71f9249f2c75b0c228195b'
SELF = 'org.droidloom.qa.hilton.r1'
QA_ROOT = Path('/home/alex/work/pocket4-owned-hilton-qa-r1-source-01/source')
QA_MANIFEST = "d8e2e4b4a0ed105a94cb08a67b3e0e45f1c68bbdfa500698c65c79400776c175"
BUILD = Path('/home/alex/work/pocket4-owned-hilton-qa-r1-build-01/build-result.json')
BUILD_SHA = "7f54f1941d8ecc6c780b1cb42ad2de51f7f76369e3d2d406df4c434490db8ca3"
BUILD_BYTES = 23290
STAGE = Path('/home/alex/work/pocket4-owned-hilton-qa-r1-source-01/stage-result.json')
STAGE_SHA = "bf11dbe06054dbd7471bcf1fdad4c24e9c2bc611f132ae15207124ed3ce75f14"
STAGE_BYTES = 1947
APK = Path('/home/alex/work/pocket4-owned-hilton-qa-r1-build-01/owned-hilton-qa.apk')
APK_SHA = "7274d57e7f8d776f6a028afcea67edab2cb167064753a8ddfc6332b2e25333f4"
APK_BYTES = 24720
SIGNER_SHA = "748e14bf5b68f31f7d23bce5997dd89edc90944c697cc9e43c8c6868cf81be68"
REFERENCE_SHA = '0a4a9f0d02b2a62f2b902983e43360c751a8f1952fb9ae7399850b112cb50a89'
BASE_HOST_ROOT = Path('/home/alex/work/pocket4-current-host-r6-source-01')
RECORDER_MANIFEST = '002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'
HOST_STAGE_SHA = 'e1718fcb3561488c88011f00de0d6e992ff51a64a355da87f1fcb867545fcba6'
HOST_STAGE_BYTES = 10016
CURRENT_EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
BASELINE_SHA = '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA = 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
PARENT_HELPER_UID = 10160
READER_SHA = "b30f1e5b9b13e1cd95cc52a9b38f86c2ec421764c956dca1412a977d807d2ea6"
GUEST_DIR_NAME = 'pocket4-owned-hilton-qa-'+NONCE
GUEST_DIR = '/data/local/tmp/'+GUEST_DIR_NAME
GUEST_APK = GUEST_DIR+'/owned-hilton-qa.apk'
PACKAGE_LIST = ['/system/bin/cmd','package','list','packages','-u','-U','--user','all',SELF]
INSTALLED_ALL_USERS = ['/system/bin/cmd','package','list','packages','-U','--user','all',SELF]
INSTALL = ['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',SELF,GUEST_APK]
ACTION_LOCK_WAIT_SECONDS = 5.0
ACTION_LOCK_POLL_SECONDS = 0.05
WORK_SECONDS = 175
EXPECTED_SOURCE_FILES = {'install_state.py','hilton_context.py','hilton_transport.py','stage_execute.py',
    'make_request.py','INPUTS.json','README.md','host/source-manifest.json','host-stage-actual.json',
    'check_install_binding.py','references/target_metadata_parsers.py','target-artifact-reference.json', 'current_discovery.py', 'check_current_discovery.py', 'actual-target-metadata.json'}

def require(value, message):
    if not value:
        raise RuntimeError(message)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path, maximum=1048576, expected=None, size=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                0 <= before.st_size <= maximum, 'INPUT_SHAPE_OR_BOUND: ' + str(path))
        chunks = []; count = 0
        while True:
            part = os.read(fd, min(65536, maximum + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
            require(count <= maximum, 'INPUT_GREW: ' + str(path))
        after = os.fstat(fd)
        fields = ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        require(all(getattr(before, k) == getattr(after, k) for k in fields) and count == before.st_size,
                'INPUT_CHANGED: ' + str(path))
        raw = b''.join(chunks)
        require(expected is None or digest(raw) == expected, 'INPUT_SHA_CHANGED: ' + str(path))
        require(size is None or len(raw) == size, 'INPUT_SIZE_CHANGED: ' + str(path))
        return raw
    finally:
        os.close(fd)

def module(path, expected, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(read(path, expected=expected), str(path), 'exec'), value.__dict__)
    return value

def error_record(phase, error):
    value = {'phase':phase, 'type':type(error).__name__, 'message':str(error)}
    if isinstance(error, OSError):
        value['errno'] = error.errno
    for name in ('command_observation', 'details', '__notes__'):
        if hasattr(error, name):
            value[name] = getattr(error, name)
    return value

def remember(result, phase, error):
    value = error_record(phase, error)
    if result['error'] is None:
        result['error'] = value
    else:
        result['secondary_errors'].append(value)
    result['ok'] = False

def command(flow, argv, timeout=8, mutation=False):
    # This returns only after the real frozen command joined, the lease exited
    # and the mandatory post guard succeeded. Preserve all original failures.
    index = flow.command_index
    out = flow.android(argv, timeout, mutation=mutation)
    require(flow.command_index == index + 1, 'ONE_ACTUAL_COMMAND_REQUIRED')
    stem = flow.step / ('command-%03d' % flow.command_index)
    raw = read(str(stem)+'.result.json', 65536); row = json.loads(raw)
    err = read(str(stem)+'.stderr', 1048576)
    require(row.get('returncode') == 0 and row.get('spawned') is True and
            row.get('owned_command_joined') is True and row.get('timed_out') is False and
            row.get('errors') == [] and row.get('stdout_sha256') == digest(out) and
            row.get('stderr_sha256') == digest(err) and err == b'', 'EXACT_JOINED_QUIET_COMMAND_REQUIRED')
    return out, {'command':stem.name, 'result_sha256':digest(raw),
                 'stdout_sha256':digest(out), 'stderr_sha256':digest(err)}

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

def uid_from(raw):
    text = raw.decode('utf-8', 'strict')
    match = re.fullmatch(re.escape('package:'+SELF+' uid:') + r'([0-9]+)\n', text)
    require(match is not None, 'ONE_EXACT_NEW_PACKAGE_UID_REQUIRED')
    uid = int(match[1])
    require(10000 <= uid < 100000 and uid != PARENT_HELPER_UID and uid != 10135, 'NEW_APP_UID_REQUIRED')
    return uid

class OwnedApk:
    """Only a fresh own directory/file below the held Main root; no recursion."""
    def __init__(self, target):
        self.target = target
        self.parent = self.directory = self.file = -1
        self.directory_created = False
        self.file_created = False
        self.identity = self.directory_identity = None

    @staticmethod
    def identity_of(fd):
        s = os.fstat(fd)
        return {'device':s.st_dev, 'inode':s.st_ino, 'mode':s.st_mode,
                'uid':s.st_uid, 'gid':s.st_gid, 'nlink':s.st_nlink, 'bytes':s.st_size}

    def stage(self, data):
        require(len(data) == APK_BYTES and digest(data) == APK_SHA, 'ACTUAL_APK_BYTES_REQUIRED')
        self.parent = self.target.open_root('/data/local/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        os.mkdir(GUEST_DIR_NAME, 0o711, dir_fd=self.parent)
        self.directory_created = True
        self.directory = os.open(GUEST_DIR_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 dir_fd=self.parent)
        self.directory_identity = self.identity_of(self.directory)
        require(self.directory_identity['uid'] == 0, 'OWNED_DIRECTORY_UID_CHANGED')
        os.fchmod(self.directory, 0o711)
        self.directory_identity = self.identity_of(self.directory)
        self.file = os.open('owned-hilton-qa.apk', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                            0o600, dir_fd=self.directory)
        self.file_created = True
        count = 0
        while count < len(data):
            wrote = os.write(self.file, data[count:])
            require(wrote > 0, 'OWNED_APK_WRITE_STALLED'); count += wrote
        os.fsync(self.file)
        os.fchmod(self.file, 0o444)
        self.identity = self.identity_of(self.file)
        require(self.identity['uid'] == 0 and self.identity['nlink'] == 1 and
                stat.S_ISREG(self.identity['mode']) and self.identity['bytes'] == APK_BYTES,
                'OWNED_STAGED_APK_SHAPE_CHANGED')
        os.fsync(self.directory); os.fsync(self.parent)
        raw, meta = self.target.read_file(GUEST_APK, APK_BYTES, single_link=True)
        require(digest(raw) == APK_SHA and
                (meta['device'],meta['inode'],meta['bytes']) ==
                (self.identity['device'],self.identity['inode'],APK_BYTES), 'STAGED_PATH_NOT_OWNED_APK')
        return {'path':GUEST_APK, 'sha256':APK_SHA, 'file':self.identity, 'directory':self.directory_identity}

    def close(self):
        # Evidence/read/guard errors cannot skip independent FD closure. An
        # ambiguous name is retained, never recursively removed or overwritten.
        errors = []
        try:
            if self.file_created:
                require(self.directory >= 0 and self.file >= 0, 'OWNED_FILE_FDS_REQUIRED')
                expected = os.fstat(self.file)
                current = os.stat('owned-hilton-qa.apk', dir_fd=self.directory, follow_symlinks=False)
                require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and
                        (current.st_dev,current.st_ino) == (expected.st_dev,expected.st_ino),
                        'OWNED_APK_CLEANUP_IDENTITY_CHANGED')
                os.unlink('owned-hilton-qa.apk', dir_fd=self.directory)
                os.fsync(self.directory)
        except BaseException as error:
            errors.append(error_record('owned_staged_file_retire',error))
        try:
            if self.directory_created:
                require(self.parent >= 0 and self.directory >= 0, 'OWNED_DIRECTORY_FDS_REQUIRED')
                expected = os.fstat(self.directory)
                current = os.stat(GUEST_DIR_NAME, dir_fd=self.parent, follow_symlinks=False)
                require(stat.S_ISDIR(current.st_mode) and
                        (current.st_dev,current.st_ino) == (expected.st_dev,expected.st_ino),
                        'OWNED_DIRECTORY_CLEANUP_IDENTITY_CHANGED')
                require(os.listdir(self.directory) == [], 'OWNED_DIRECTORY_NOT_EMPTY')
                os.rmdir(GUEST_DIR_NAME, dir_fd=self.parent)
                os.fsync(self.parent)
        except BaseException as error:
            errors.append(error_record('owned_staged_directory_retire',error))
        for name in ('file','directory','parent'):
            fd = getattr(self,name); setattr(self,name,-1)
            if fd >= 0:
                try:
                    os.close(fd)
                except BaseException as error:
                    errors.append(error_record('owned_fd_close_'+name,error))
        if errors:
            error = RuntimeError('OWNED_STAGING_RETIREMENT_FAILED')
            error.details = errors
            raise error
        return {'staged_apk_created':self.file_created, 'staged_directory_created':self.directory_created,
                'staged_apk_removed':self.file_created, 'staged_directory_removed':self.directory_created,
                'authority_fds_closed':True, 'recursive_cleanup':False}

def owned_resources():
    lines = Path('/proc/self/cgroup').read_text().splitlines()
    require(len(lines) == 1 and re.fullmatch(
        r'0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-[0-9a-f-]+\.service',
        lines[0]), 'OWNED_MANAGED_CGROUP_REQUIRED')
    path = Path('/sys/fs/cgroup'+lines[0][3:])
    require(path.resolve() == path, 'OWNED_CGROUP_LINK_REJECTED')
    values = {name:(path/name).read_text().strip() for name in (
        'memory.max','memory.swap.max','cpu.max','pids.max','memory.events',
        'memory.current','memory.peak','memory.swap.current','memory.swap.peak')}
    require(values['memory.max'] == '536870912' and values['cpu.max'] == '100000 100000',
            'EXACT_MANAGED_REQUEST_LIMITS_REQUIRED')
    info = path.stat()
    return {'path':str(path),'device':info.st_dev,'inode':info.st_ino,**values}

def prepare_owned_limits():
    before = owned_resources()
    path = Path(before['path'])
    # Only the caller's exact current managed job; never any Main cgroup.
    for name,value in (('memory.swap.max','0'),('pids.max','128')):
        fd = os.open(path/name,os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            require(os.write(fd,value.encode()) == len(value),'OWNED_LIMIT_WRITE_INCOMPLETE')
        finally:
            os.close(fd)
    after = owned_resources()
    require((before['device'],before['inode']) == (after['device'],after['inode']) and
            after['memory.swap.max'] == '0' and after['pids.max'] == '128','OWNED_LIMIT_IDENTITY_CHANGED')
    return after

def resources_qualified(before, after):
    require((before['path'],before['device'],before['inode']) ==
            (after['path'],after['device'],after['inode']), 'OWNED_CGROUP_CHANGED')
    for key in ('memory.max','memory.swap.max','cpu.max','pids.max'):
        require(before[key] == after[key], 'OWNED_LIMIT_CHANGED:'+key)
    for row in (before,after):
        counters = dict(line.split() for line in row['memory.events'].splitlines())
        require(all(counters.get(key) == '0' for key in ('max','oom','oom_kill','oom_group_kill')),
                'OWNED_MEMORY_LIMIT_OR_OOM_EVENT')
    return True


def verify_source(expected):
    require(isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected),'EXTERNAL_SOURCE_PIN_REQUIRED')
    manifest=json.loads(read(HERE/'SOURCE_PINS.json',131072,expected))
    require(set(manifest['files']) == EXPECTED_SOURCE_FILES,'EXACT_HILTON_RUNTIME_SOURCE_SET_REQUIRED')
    for name,row in manifest['files'].items():
        read(HERE/name,expected=row['sha256'],size=row['bytes'])
    host_raw=read(HERE/'host/source-manifest.json',131072,RECORDER_MANIFEST)
    host_manifest=json.loads(host_raw)
    row=host_manifest['files']['current_coordinator.py']
    require(host_manifest.get('schema') == 2 and host_manifest.get('revision') == 6 and
            host_manifest.get('artifact') == 'pocket4-bilibili-current-recorder-held-r6' and
            row['sha256'] == REFERENCE_SHA and
            manifest['files']['references/target_metadata_parsers.py']['sha256'] == READER_SHA,
            'EXACT_CURRENT_SHARED_REFERENCES_REQUIRED')
    read(BASE_HOST_ROOT/'source-manifest.json',131072,RECORDER_MANIFEST,len(host_raw))
    read(BASE_HOST_ROOT/'current_coordinator.py',131072,REFERENCE_SHA,row['bytes'])
    return manifest


def references():
    return module(BASE_HOST_ROOT/'current_coordinator.py',REFERENCE_SHA,'current_target_install_reference')

def qualify_host_stage(value, manifest):
    require(type(value) is dict and
            value.get('schema') == 'pocket4-current-host-source-stage-v2' and
            value.get('ok') is True and value.get('error') is None and
            value.get('secondary_errors') == [] and
            value.get('actual_source_constructor_qualified') is True and
            value.get('all_staged_sources_unchanged') is True and
            value.get('source_root') == str(BASE_HOST_ROOT) and
            value.get('source_manifest_sha256') == RECORDER_MANIFEST,
            'ACTUAL_COMPLETE_R6_HOST_SOURCE_STAGE_REQUIRED')
    require(manifest.get('schema') == 2 and manifest.get('revision') == 6 and
            manifest.get('artifact') == 'pocket4-bilibili-current-recorder-held-r6' and
            len(manifest.get('files', {})) == 14,
            'EXACT_R6_HOST_MANIFEST_REQUIRED')
    expected_sources = {name:{'path':str(BASE_HOST_ROOT/name),**row}
                        for name,row in manifest['files'].items()}
    expected_sources['source-manifest.json'] = {
        'path':str(BASE_HOST_ROOT/'source-manifest.json'),
        'bytes':3757,'sha256':RECORDER_MANIFEST}
    require(value.get('source_pins') == expected_sources,
            'ACTUAL_R6_PUBLISHED_SOURCE_PINS_REQUIRED')
    controls = value.get('controls', {})
    require(controls.get('schema') == 'pocket4-current-host-source-controls-v2' and
            controls.get('all_passed') is True and controls.get('count') == 38 and
            len(controls.get('cases', [])) == 38 and
            len({x.get('name') for x in controls['cases']}) == 38 and
            all(x.get('passed') is True for x in controls['cases']) and
            controls.get('compiled_sources') == sorted(manifest['files']) and
            controls.get('fixture_is_not_baseline_observation') is True and
            all(type(controls.get(k)) is int and controls[k] == 0
                for k in ('Android_commands','UI_actions','children','filesystem_operations')),
            'ACTUAL_38_CURRENT_HOST_CONTROLS_REQUIRED')
    for bucket in ('source_fds','publication_fds'):
        fds = value.get(bucket, {})
        require(fds.get('scope') == 'collector_managed_descriptors' and
                all(type(fds.get(k)) is int for k in ('acquired','close_attempts','closed','remaining')) and
                fds['acquired'] > 0 and
                fds['acquired'] == fds['close_attempts'] == fds['closed'] and
                fds['remaining'] == 0 and fds.get('errors') == [],
                'ACTUAL_CURRENT_HOST_SOURCE_FDS_NOT_RETIRED')
    expected_guard = {'schema':'pocket4-current-main-guard-v2',
        'Main_epoch_sha256':CURRENT_EPOCH, 'current_baseline_sha256':BASELINE_SHA,
        'current_baseline_qualification_sha256':QUALIFICATION_SHA,
        'historical_activation_sha256':'7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615',
        'historical_verified_sha256':'2d6f2ef7953b98109044f823da56694111bd9f8ff14fff5e746afb7bd42b0387',
        'previous_current_baseline_sha256':'163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266',
        'config_sha256':'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc',
        'seven_processes_match':True, 'three_host_processes_match':True,
        'authenticated_owner_chain_matches':True, 'current_user_namespaces_match':True,
        'resource_limits_match':True, 'current_executable_and_root_backing_match':True,
        'old_helpers_and_tasks_reauthorized':False,
        'framework_exit_cause_resolved':False, 'production_ready':False}
    require(all(value.get(k) == expected_guard for k in ('Main_before','Main_after','Main_final')),
            'CURRENT_HOST_STAGE_MAIN_FENCES_CHANGED')
    require(value.get('source_only') is True and value.get('runtime_admitted') is False and
            value.get('namespace_entry') is False and
            value.get('old_helpers_and_tasks_reauthorized') is False and
            value.get('whole_app_production_ready') is False and
            all(type(value.get(k)) is int and value[k] == 0 for k in
                ('Android_commands','UI_actions','helper_installs','App_launches','children_spawned')),
            'CURRENT_HOST_STAGE_SCOPE_NOT_READONLY_SOURCE')
    durable = {k:v for k,v in value.items() if k not in ('stage_result','publication_fds')}
    raw = (json.dumps(durable,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    require(value.get('stage_result') == {
                'path':str(BASE_HOST_ROOT/'stage-result.json'),'bytes':len(raw),'sha256':digest(raw)},
            'ACTUAL_R6_DURABLE_STAGE_PIN_REQUIRED')
    return True


def qualified_inputs():
    host_manifest=json.loads(read(HERE/'host/source-manifest.json',131072,RECORDER_MANIFEST))
    qualify_host_stage(json.loads(read(HERE/'host-stage-actual.json',65536,HOST_STAGE_SHA,HOST_STAGE_BYTES)),host_manifest)
    source=json.loads(read(QA_ROOT/'SOURCE_PINS.json',131072,QA_MANIFEST))
    adapter=module(QA_ROOT/'qa_adapter.py',source['files']['qa_adapter.py']['sha256'],'hilton_actual_qa_adapter')
    manifest=adapter.own_source(QA_MANIFEST)
    qa=adapter.load(QA_ROOT/'qa_contract.py',manifest['files']['qa_contract.py']['sha256'],'hilton_actual_qa_contract')
    builder=adapter.load(QA_ROOT/'build_candidate.py',manifest['files']['build_candidate.py']['sha256'],'hilton_actual_qa_builder')
    build_receipt=json.loads(read(BUILD,expected=BUILD_SHA,size=BUILD_BYTES))
    args=types.SimpleNamespace(build_receipt=BUILD,build_receipt_sha256=BUILD_SHA,
        source_manifest_sha256=QA_MANIFEST,apk_sha256=APK_SHA,signer_certificate_sha256=SIGNER_SHA)
    proof=adapter.qualified_build(args,manifest,builder)
    require(adapter.RECORDER_MANIFEST_SHA == RECORDER_MANIFEST and
            qa.MAIN_EPOCH == CURRENT_EPOCH and qa.MAIN_BASELINE_SHA == BASELINE_SHA and
            qa.MAIN_BASELINE_QUALIFICATION_SHA == QUALIFICATION_SHA and
            qa.MAIN_BASELINE_SCHEMA == 'pocket4-main-current-baseline-v2',
            'BUILT_HELPER_AND_CURRENT_HOST_BINDING_REQUIRED')
    current_controls = build_receipt.get('current_baseline_scope_controls', {})
    report = current_controls.get('report', {})
    require(current_controls.get('source_sha256') == manifest['files']['check_current_baseline.py']['sha256'] and
            report.get('all_passed') is True and report.get('count') == 32 and
            len(report.get('cases', [])) == 32 and len({x.get('name') for x in report['cases']}) == 32 and
            all(x.get('passed') is True for x in report['cases']) and
            report.get('production_contract_sha256') == manifest['files']['qa_contract.py']['sha256'] and
            report.get('production_adapter_sha256') == manifest['files']['qa_adapter.py']['sha256'] and
            report.get('host_recorder_manifest_sha256') == RECORDER_MANIFEST and
            report.get('main_epoch_sha256') == CURRENT_EPOCH and
            report.get('main_baseline_schema') == 'pocket4-main-current-baseline-v2' and
            report.get('main_baseline_sha256') == BASELINE_SHA and
            report.get('main_baseline_qualification_sha256') == QUALIFICATION_SHA,
            'ACTUAL_32_SCOPE_AND_HOST_SESSION_CONTROLS_REQUIRED')
    require(proof['APK'] == {'path':str(APK),'bytes':APK_BYTES,'sha256':APK_SHA},'EXACT_ACTUAL_HILTON_HELPER_APK_REQUIRED')
    stage=json.loads(read(STAGE,expected=STAGE_SHA,size=STAGE_BYTES))
    require(stage.get('state') == 'OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN' and
            stage.get('source_manifest_sha256') == QA_MANIFEST and stage.get('build_returncode') == 0 and
            stage.get('error') is None and stage.get('secondary_errors') == [] and
            stage.get('build_result') == {'path':str(BUILD),'bytes':BUILD_BYTES,'sha256':BUILD_SHA},
            'ACTUAL_HILTON_BUILD_STAGE_REQUIRED')
    data=read(APK,APK_BYTES,APK_SHA,APK_BYTES)
    proof['stage_receipt_sha256']=STAGE_SHA
    require(adapter.SELF == qa.SELF == SELF and qa.PACKAGE == 'com.hilton.android.hhonors' and
            qa.UID == 10135,'EXACT_DEDICATED_HILTON_QA_REQUIRED')
    return adapter,qa,proof,data


def worker(expected):
    manifest=verify_source(expected)
    require(os.getuid()==os.geteuid()==0 and HERE==SOURCE and ROOT.is_dir(),'EXACT_ROOT_HILTON_WORKER_REQUIRED')
    require(not os.path.lexists(WORKER_ROOT),'FRESH_ONCE_WORKER_REQUIRED')
    WORKER_ROOT.mkdir(mode=0o700)
    (WORKER_ROOT/'steps').mkdir(mode=0o700)
    STEP.mkdir(mode=0o700)
    ref=references()
    ref.write_new(WORKER_ROOT/'once.claim.json',{'nonce':NONCE,'state_nonce':STATE_NONCE,
        'source_manifest_sha256':expected,'package':SELF,'automatic_retry':False})
    result={'schema':1,'ok':False,'error':None,'secondary_errors':[],
        'package':SELF,'target_package':'com.hilton.android.hhonors','nonce':NONCE,
        'state_nonce':STATE_NONCE,'source_manifest_sha256':expected,
        'install_attempted':False,'install_success_observed':False,'state_attempted':False,
        'package_retained':False,'UI_actions':0,'audio_actions':0,'App_launches':0,
        'UiAutomation_connection_requested':False,'permission_grants':0,'settings_writes':0,
        'old_v2_helper_called':False,'Bili_Flow_instantiated':False,'automatic_retry':False,
        'whole_app_production_ready':False}
    ctx=staged=artifacts=recorder=None;lock=None;guard=None;phase='source_and_build'
    started=time.monotonic()
    try:
        adapter,qa,proof,apk=qualified_inputs();result['build']=proof
        context=module(HERE/'hilton_context.py',manifest['files']['hilton_context.py']['sha256'],'hilton_install_context')
        transport=module(HERE/'hilton_transport.py',manifest['files']['hilton_transport.py']['sha256'],'hilton_r1_transport')
        reader=module(HERE/'references/target_metadata_parsers.py',READER_SHA,'hilton_metadata_primitives')
        activation=ref.current_baseline()
        epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'hilton_worker_epoch')
        guard=lambda:ref.main_guard(activation,epoch)
        result['Main_before_lock']=guard()
        shared=module(context.INSTALLED_SHARED/'source_contract.py',context.CONTRACT_SHA,'hilton_command_contract')
        shared_contract=shared.SourceContract(context.INSTALLED_SHARED/'source-manifest.json',context.SHARED_MANIFEST)
        recorder=shared_contract.load('recorder.py','hilton_original_command_body')
        phase='action_lock_admission';result['action_lock_admission']={}
        lock=acquire_action_lock(recorder.ACTION_LOCK,result['action_lock_admission'])
        guard()
        phase='held_Main_binding'
        plan=context.ordered_commands(qa,SELF,GUEST_APK,STATE_NONCE)
        util=types.SimpleNamespace(module=module,read=read)
        ctx,recorder,guard=context.open_context(ref,util,expected,verify_source,HERE,STEP,
            transport,plan,result,started+WORK_SECONDS)
        artifact_reference=json.loads(read(HERE/'target-artifact-reference.json',expected=
            manifest['files']['target-artifact-reference.json']['sha256']))
        artifacts=context.ArtifactSet(ctx,artifact_reference,reader)
        phase='target_APK_before';result['target_before']=artifacts.before()
        phase='new_helper_absence'
        absence,absence_command=command(ctx,PACKAGE_LIST)
        require(absence == b'','NEW_PACKAGE_OR_RETAINED_RECORD_ALREADY_EXISTS')
        result['absence']={'all_users':True,'include_uninstalled':True,'command':absence_command}
        phase='own_APK_staging'
        staged=OwnedApk(ctx.bind().target)
        result['staged_apk']=staged.stage(apk);del apk
        phase='single_exact_install';result['install_attempted']=True
        installed,install_command=command(ctx,INSTALL,40,mutation=True)
        require(installed == b'Success\n','INSTALL_DID_NOT_REPORT_EXACT_SUCCESS')
        result['install_success_observed']=True;result['install_command']=install_command
        phase='owned_UID_binding'
        uid_raw,uid_command=command(ctx,['/system/bin/cmd','package','list','packages','-U','--user','0',SELF])
        uid=uid_from(uid_raw);result['uid_command']=uid_command
        session=adapter.Session(ctx,recorder,qa,proof,uid)
        result['runtime_shared_recorder_manifest_sha256']=context.SHARED_MANIFEST
        result['runtime_ticket_context_sha256']=manifest['files']['hilton_context.py']['sha256']
        result['runtime_ticket_transport_sha256']=manifest['files']['hilton_transport.py']['sha256']
        phase='installed_before_state';result['installed_before_state']=session.installed()
        phase='one_state_only';result['state_attempted']=True
        result['state']=session.instrument({'protocol':qa.PROTOCOL,'nonce':STATE_NONCE,'op':'state'})
        require(result['state']['helper']['ui_automation_connected'] is False and
                result['state']['helper']['op']=='state','STATE_CANNOT_CONNECT_UIAUTOMATION')
        phase='installed_after_state';result['installed_after_state']=session.installed()
        require(result['installed_before_state']==result['installed_after_state'],'NEW_HELPER_IDENTITY_CHANGED')
        all_rows,row_command=command(ctx,INSTALLED_ALL_USERS)
        require(uid_from(all_rows)==uid,'NEW_HELPER_APPEARED_FOR_ANOTHER_USER_OR_UID')
        result['all_users_after']=row_command
        phase='target_APK_after';result['target_after']=artifacts.after()
        require(result['target_before']==result['target_after'],'HILTON_TARGET_CHANGED_DURING_OWN_INSTALL')
        require(ctx.command_index==ctx.next_command==len(plan)==13,'EXACT_THIRTEEN_JOINED_COMMANDS_REQUIRED')
        result['exact_command_count']=ctx.command_index
        result['owned_package_uid']=uid;result['package_retained']=True;result['ok']=True
    except BaseException as error:
        remember(result,phase,error)
    finally:
        if staged is not None:
            try:result['staging_cleanup']=staged.close()
            except BaseException as error:remember(result,'staging_cleanup',error)
        if artifacts is not None:
            try:
                if len(artifacts.records)==4 and 'target_after' not in result:
                    result['failure_target_files_revalidated']=artifacts.revalidate_files()
            except BaseException as error:remember(result,'failed_scope_target_revalidation',error)
            try:result['target_FD_cleanup']=artifacts.close()
            except BaseException as error:remember(result,'target_FD_cleanup',error)
        if ctx is not None:
            try:
                ctx.guard(attempted=ctx.action_attempted);result['final_Main_guard_passed']=True
            except BaseException as error:remember(result,'final_Main_guard',error)
            try:ctx.close();result['held_binding_released']=True
            except BaseException as error:remember(result,'held_binding_release',error)
        if guard is not None:
            try:
                result['Main_after']=guard()
                require(result.get('Main_before_lock')==result['Main_after'],'MAIN_BEFORE_AFTER_DIFFER')
            except BaseException as error:remember(result,'independent_final_Main',error)
        if lock is not None:
            try:os.close(lock);result['action_lock_released']=True
            except BaseException as error:remember(result,'action_lock_release',error)
    result['action_attempted']=bool(ctx is not None and ctx.action_attempted)
    result['outcome_unknown']=bool(result['action_attempted'] and not result['ok'])
    result['possible_owned_package_retained']=result['install_attempted'] and not result['ok']
    result['seconds']=time.monotonic()-started
    try:ref.write_new(WORKER_ROOT/'result.json',result)
    except BaseException as error:remember(result,'worker_result_write',error)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['ok'] else 2


def execute(expected):
    verify_source(expected)
    require(os.getuid()==os.geteuid()==0 and HERE==SOURCE,'EXACT_ROOT_HILTON_COORDINATOR_REQUIRED')
    ref=references()
    require(not os.path.lexists(WORKER_ROOT),'NO_PARTIAL_WORKER_RETRY')
    claim=json.loads(read(ROOT/'once.claim.json',65536))
    require(claim.get('nonce')==NONCE and claim.get('source_manifest_sha256')==expected and
            claim.get('automatic_retry') is False,'EXACT_ONCE_CLAIM_REQUIRED')
    evidence=ROOT/'evidence';evidence.mkdir(mode=0o700)
    result={'schema':1,'ok':False,'error':None,'secondary_errors':[],
        'source_manifest_sha256':expected,'package':SELF,'target_package':'com.hilton.android.hhonors',
        'nonce':NONCE,'worker_root':str(WORKER_ROOT),'automatic_retry':False,
        'UI_actions':0,'audio_actions':0,'App_launches':0,'whole_app_production_ready':False,
        'old_v2_helper_called':False,'Bili_Flow_instantiated':False,'install_state_worker_requested':False}
    activation=epoch=resource_before=None
    try:
        resource_before=prepare_owned_limits();result['owned_before']=resource_before
        qualified_inputs()
        activation=ref.current_baseline()
        epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'hilton_coordinator_epoch')
        guard=lambda:ref.main_guard(activation,epoch)
        result['Main_before']=guard()
        result['install_state_worker_requested']=True
        observed=ref.run_cli('01-install-state',['/usr/bin/python3','-I','-B',str(HERE/'install_state.py'),
            '--worker-once','--source-manifest-sha256',expected],190,evidence,guard)
        raw=read(WORKER_ROOT/'result.json');durable=json.loads(raw)
        require(observed==durable and durable.get('ok') is True and durable.get('package')==SELF and
                durable.get('state_attempted') is True and durable.get('install_success_observed') is True and
                durable.get('package_retained') is True and durable.get('outcome_unknown') is False and
                durable.get('exact_command_count')==13 and durable.get('target_before')==durable.get('target_after'),
                'EXACT_HILTON_INSTALL_STATE_DURABLE_SCOPE_REQUIRED')
        result['owned_package_uid']=durable['owned_package_uid']
        result['worker_result']={'path':str(WORKER_ROOT/'result.json'),'bytes':len(raw),'sha256':digest(raw)}
        result['state_wire_sha256']=durable['state']['wire_sha256']
        result['owned_package_retained_for_separate_UI_admission']=True
        result['ok']=True
    except BaseException as error:remember(result,'coordinator',error)
    finally:
        if result['install_state_worker_requested'] and 'worker_result' not in result:
            try:
                path=WORKER_ROOT/'result.json'
                if path.exists():
                    raw=read(path);result['failed_worker_result']={'path':str(path),'bytes':len(raw),'sha256':digest(raw)}
                result['package_outcome_requires_exact_worker_reconciliation']=True
            except BaseException as error:remember(result,'failed_worker_evidence',error)
        if activation is not None and epoch is not None:
            try:result['Main_after']=ref.main_guard(activation,epoch)
            except BaseException as error:remember(result,'coordinator_final_Main',error)
        try:
            verify_source(expected);qualified_inputs();result['source_and_artifact_unchanged']=True
        except BaseException as error:remember(result,'final_source_and_artifact',error)
        if resource_before is not None:
            try:
                result['owned_after']=owned_resources();resources_qualified(resource_before,result['owned_after'])
            except BaseException as error:remember(result,'owned_resources_after',error)
        try:pin=ref.write_new(ROOT/'result.json',result)
        except BaseException as error:remember(result,'final_result_write',error);pin=None
        print(json.dumps({'ok':result['ok'],'result':pin,'error':result['error'],
            'secondary_errors':result['secondary_errors'],'package':SELF,'UI_actions':0,'audio_actions':0,
            'whole_app_production_ready':False}),flush=True)
    return 0 if result['ok'] else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--execute-once',action='store_true');modes.add_argument('--worker-once',action='store_true')
    p.add_argument('--source-manifest-sha256');a=p.parse_args()
    require(re.fullmatch('[0-9a-f]{32}',NONCE) and re.fullmatch('[0-9a-f]{32}',STATE_NONCE) and
            NONCE!=STATE_NONCE,'EXACT_DISTINCT_NONCES_REQUIRED')
    if not a.execute_once and not a.worker_once:
        print(json.dumps({'state':'PLAN_ONLY','package':SELF,'target':'com.hilton.android.hhonors',
            'root':str(ROOT),'actual_build_sha256':BUILD_SHA,'APK_sha256':APK_SHA,'signer_sha256':SIGNER_SHA,
            'install_argv':INSTALL,'state_nonce':STATE_NONCE,'UiAutomation_connection_requested':False,
            'permission_grants':0,'UI_actions':0,'App_launches':0,'old_v2_helper_called':False,
            'Bili_Flow_instantiated':False,'retention':'exact owned helper retained; no automatic retry/uninstall'}))
        return 0
    os.umask(0o077)
    return worker(a.source_manifest_sha256) if a.worker_once else execute(a.source_manifest_sha256)


if __name__=='__main__':raise SystemExit(main())
