#!/usr/bin/env python3
"""One historically bound APK, metadata only; no command, child, APK read or file write."""
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time
import types

FIXED = json.loads(__FIXED_BINDING_JSON__)
SHARED = Path('/home/alex/work/pocket4-current-host-r6-source-01')
MANIFEST_SHA = '002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff'
SOURCE_SHA = 'f92d2598221c5bf65e783df39864879a2056da47f794680668b34df11f97da49'
GUARD_SHA = '96dbdaf7673d5298e6fe17cb1b7ebae29b37110ee59f31b0c927e2cb0ef4b150'
EPOCH_SHA = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
BASELINE_SHA = '633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
QUALIFICATION_SHA = 'ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e'
ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'
ORIGINAL_FILE_LIMIT = 256 * 1024 * 1024
OBSERVATION_SECONDS = 30
FINAL_SECONDS = 45
ALARM_SECONDS = 55
OUTPUT_LIMIT = 65536
START = None


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(fd):
    s = os.fstat(fd)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,
            'nlink':s.st_nlink,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}


def named_identity(parent, name):
    s = os.stat(name, dir_fd=parent, follow_symlinks=False)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,
            'nlink':s.st_nlink,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}


def directory_identity(row):
    # Directory contents/timestamps are not a promise about unrelated writers.
    return {key:row[key] for key in ('device','inode','mode','uid','gid')}


def deadline(final=False):
    need(time.monotonic() < START + (FINAL_SECONDS if final else OBSERVATION_SECONDS),
         'FIXED_METADATA_OBSERVATION_DEADLINE')


def public_error(phase, error):
    message = str(error)
    value = {'phase':phase,'type':type(error).__name__,'errno':getattr(error,'errno',None),
             'message_bytes':len(message.encode('utf-8','replace')),
             'message_sha256':sha(message.encode('utf-8','replace'))}
    # Source/guard error codes are public; unexpected text is never exported.
    if re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', message):
        value['code'] = message
    return value


def remember(result, phase, error):
    row = public_error(phase, error)
    if result['first_error'] is None:
        result['first_error'] = row
    else:
        result['secondary_errors'].append(row)


class Journal:
    def __init__(self):
        self.rows = []

    def take(self, fd, label):
        # Register immediately, before any fallible validation.
        row = {'fd':fd,'label':label,'closed':False,'close_error':None}
        self.rows.append(row)
        need(type(fd) is int and fd >= 3 and len(self.rows) <= 256 and
             sum(x['fd'] == fd and x['closed'] is False for x in self.rows) == 1,
             'EXACT_OWN_FD_REQUIRED')
        need(os.get_inheritable(fd) is False, 'OWN_FD_CLOEXEC_REQUIRED')
        return fd

    def close(self, fd):
        rows = [row for row in self.rows if row['fd'] == fd and row['closed'] is False]
        need(len(rows) == 1, 'EXACT_LIVE_OWN_FD_REQUIRED')
        row = rows[0]
        try:
            os.close(fd)
            row['closed'] = True
        except BaseException as error:
            # A failed close is never retried by number.
            row['closed'] = None
            row['close_error'] = public_error('own_fd_close', error)
            raise

    def finish(self, result):
        for row in reversed(self.rows):
            if row['closed'] is False:
                try:
                    self.close(row['fd'])
                except BaseException:
                    pass  # Exact exception already retained on this FD row.
        for row in self.rows:
            if row['close_error'] is not None:
                if result['first_error'] is None:
                    result['first_error'] = row['close_error']
                else:
                    result['secondary_errors'].append(row['close_error'])
        result['owned_FD_journal'] = self.rows
        result['owned_FDs_acquired'] = len(self.rows)
        result['owned_FDs_closed'] = sum(row['closed'] is True for row in self.rows)
        result['all_journal_FDs_closed'] = all(row['closed'] is True for row in self.rows)


def read_exact_file(journal, path, size, digest, final=False):
    """Fixed public authority, no-follow component chain, EOF/hash and named/held equality."""
    path = str(path)
    need(path.startswith('/') and not path.startswith('//') and '\0' not in path and
         all(x not in ('','.','..') for x in path[1:].split('/')),
         'FIXED_AUTHORITY_PATH_REQUIRED')
    need(type(size) is int and 0 < size <= 131072 and re.fullmatch('[0-9a-f]{64}',digest),
         'EXACT_AUTHORITY_PIN_REQUIRED')
    local = []
    edges = []
    primary = None
    close_errors = []
    try:
        deadline(final)
        current = journal.take(os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC),
                               'authority:/')
        local.append(current)
        first = directory_identity(identity(current))
        need(first == directory_identity(named_identity(None,'/')), 'AUTHORITY_ROOT_CHANGED')
        edges.append((None,'/',current,first))
        parts = path[1:].split('/')
        for part in parts[:-1]:
            parent = current
            current = journal.take(os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                           dir_fd=parent),'authority:directory')
            local.append(current)
            first = directory_identity(identity(current))
            need(stat.S_ISDIR(first['mode']) and
                 first == directory_identity(named_identity(parent,part)),
                 'AUTHORITY_ANCESTOR_CHANGED')
            edges.append((parent,part,current,first))
        fd = journal.take(os.open(parts[-1],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,
                                  dir_fd=current),'authority:file')
        local.append(fd)
        before = identity(fd)
        need(stat.S_ISREG(before['mode']) and before['nlink'] == 1 and before['bytes'] == size,
             'EXACT_AUTHORITY_FILE_SHAPE')
        need(named_identity(current,parts[-1]) == before, 'AUTHORITY_NAME_DIFFERS')
        chunks = []
        count = 0
        while True:
            deadline(final)
            block = os.read(fd,min(65536,size+1-count))
            if not block:
                break
            count += len(block)
            need(count <= size, 'AUTHORITY_BYTE_BOUND')
            chunks.append(block)
        raw = b''.join(chunks)
        need(count == size and sha(raw) == digest, 'AUTHORITY_BYTES_CHANGED')
        need(identity(fd) == before == named_identity(current,parts[-1]),
             'AUTHORITY_HELD_OR_NAMED_CHANGED')
        for parent,name,opened,expected in edges:
            need(directory_identity(identity(opened)) == expected ==
                 directory_identity(named_identity(parent,name)), 'AUTHORITY_ANCESTOR_CHANGED')
        return raw
    except BaseException as error:
        primary = error
        raise
    finally:
        for fd in reversed(local):
            try:
                journal.close(fd)
            except BaseException as error:
                close_errors.append(error)
        if close_errors:
            if primary is None:
                raise RuntimeError('AUTHORITY_FD_CLOSE_FAILED')
            primary.add_note('AUTHORITY_FD_CLOSE_FAILED')


def module(raw, path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    return value


def original_predicates(row):
    """Exactly the old first APK gate; evaluated, never relaxed into an admission."""
    return {
        'regular':stat.S_ISREG(row['mode']),
        'nlink_eq_1':row['nlink'] == 1,
        'uid_eq_1000':row['uid'] == 1000,
        'gid_eq_1000':row['gid'] == 1000,
        'mode_has_no_022':not bool(row['mode'] & 0o022),
        'bytes_gt_0':row['bytes'] > 0,
        'bytes_le_256_MiB':row['bytes'] <= ORIGINAL_FILE_LIMIT,
    }


def qualify_original(raw):
    value = json.loads(raw)
    need(type(value) is dict and value.get('schema') == 1 and value.get('ok') is False and
         value.get('package') == FIXED['package'] and
         value.get('source_sha256') == FIXED['source']['sha256'] and
         value.get('metadata_before') == FIXED['observed_metadata'] and
         value.get('apk_paths_before') == [FIXED['apk_path']] and
         value.get('error') == {'message':'TICKET12306_INSTALLED_APK_SHAPE_OR_BOUND',
                                'phase':'held_APK_hash','type':'RuntimeError'} and
         value.get('secondary_errors') == [], 'EXACT_FAILED_METADATA_REPORT_REQUIRED')
    need(value.get('held_binding_released') is True and value.get('action_lock_released') is True and
         value.get('final_Main_guard_passed') is True and
         value.get('target_directory_cleanup') == {'contents_read':False,'held_data_directory_FDs_closed':2},
         'ORIGINAL_METADATA_CLEANUP_NOT_QUALIFIED')
    before = value.get('Main_before')
    need(type(before) is dict and before == value.get('Main_after') and
         before.get('schema') == 'pocket4-current-main-guard-v2' and
         before.get('Main_epoch_sha256') == EPOCH_SHA and
         before.get('current_baseline_sha256') == BASELINE_SHA and
         before.get('current_baseline_qualification_sha256') == QUALIFICATION_SHA,
         'ORIGINAL_CURRENT_MAIN_BINDING_REQUIRED')
    commands = value.get('command_observations')
    expected = [
        ['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',FIXED['package']],
        ['/system/bin/cmd','package','path','--user','0',FIXED['package']],
    ]
    need(type(commands) is list and len(commands) == 2, 'EXACT_TWO_OLD_PM_READS_REQUIRED')
    for index,(row,argv) in enumerate(zip(commands,expected),1):
        need(row.get('index') == index and row.get('argv') == argv and
             row.get('spawned') is True and row.get('joined') is True and row.get('entry_entered') is True and
             row.get('returncode') == 0 and row.get('host_timed_out') is False and
             row.get('first_error') is None and row.get('secondary_errors') == [] and
             row.get('recorder_errors') == [] and row.get('Android_UI_action') is False,
             'ORIGINAL_PM_READ_NOT_COMPLETE')
    need(all(value.get(key) == 0 for key in
             ('UI_actions','App_launches','instrumentation_calls','permission_grants','settings_writes')) and
         value.get('business_action_authority') is False and
         value.get('whole_app_production_ready') is False, 'ORIGINAL_METADATA_SCOPE_CHANGED')
    path = FIXED['apk_path']
    parts = path.split('/')
    need(len(parts) == 6 and parts[:3] == ['','data','app'] and
         re.fullmatch(r'~~[A-Za-z0-9_=-]+',parts[3]) and
         re.fullmatch(re.escape(FIXED['package'])+r'-[A-Za-z0-9_=-]+',parts[4]) and
         parts[5] == 'base.apk', 'ONE_FIXED_ORIGINAL_BASE_APK_REQUIRED')
    return value


class ExistingActionLock:
    def __init__(self, journal):
        self.journal = journal
        self.edges = []
        self.fd = None
        self.parent = None
        self.expected = None
        self.acquired = False
        self.observation = {'path':ACTION_LOCK,'attempts':0,'acquired':False,'released':False,
                            'created':False,'read_only_open':True,'writes':0}

    def acquire(self):
        deadline()
        current = self.journal.take(os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC),'lock:/')
        self.edges.append((None,'/',current,directory_identity(identity(current))))
        for part in ('run','lock'):
            parent = current
            current = self.journal.take(os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                                dir_fd=parent),'lock:directory')
            row = directory_identity(identity(current))
            need(stat.S_ISDIR(row['mode']) and row == directory_identity(named_identity(parent,part)),
                 'LOCK_ANCESTOR_DIFFERS')
            self.edges.append((parent,part,current,row))
        self.parent = current
        self.fd = self.journal.take(os.open('android-digitalis-actions.lock',
            os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current),'lock:file')
        self.expected = identity(self.fd)
        need(stat.S_ISREG(self.expected['mode']) and self.expected['nlink'] == 1 and
             self.expected['uid'] == self.expected['gid'] == 0 and not self.expected['mode'] & 0o022,
             'EXISTING_ROOT_ACTION_LOCK_SHAPE')
        self.verify()
        self.observation['attempts'] = 1
        fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.acquired = True
        self.observation['acquired'] = True
        self.verify()

    def verify(self):
        for parent,name,fd,expected in self.edges:
            need(directory_identity(identity(fd)) == expected ==
                 directory_identity(named_identity(parent,name)), 'LOCK_ANCESTOR_CHANGED')
        if self.expected is not None:
            need(identity(self.fd) == self.expected ==
                 named_identity(self.parent,'android-digitalis-actions.lock'),
                 'LOCK_FILE_CHANGED')

    def release(self, result):
        try:
            self.verify()
        except BaseException as error:
            remember(result,'action_lock_final_identity',error)
        if self.acquired:
            try:
                fcntl.flock(self.fd,fcntl.LOCK_UN)
                self.observation['released'] = True
            except BaseException as error:
                remember(result,'action_lock_release',error)
        result['action_lock'] = self.observation


class HeldInitView:
    """Original R6 fixed identity/pidfd/six namespaces/root chain, with this reader's FD journal.

    No constructor-local rollback can skip a descriptor: each acquisition is
    registered with the caller before qualification, even if construction fails.
    No namespace entry or command API is exposed.
    """
    def __init__(self, journal, held, binding, baseline):
        self.journal = journal
        self.held = held
        expected = baseline['framework_epoch']['binding']['processes']['init']
        self.pid = expected['host_pid']
        self.proc = journal.take(os.open('/proc/'+str(self.pid),
            os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),'held_init:proc')
        self.pidfd = journal.take(os.pidfd_open(self.pid,0),'held_init:pidfd')
        need(held.pidfd_alive(self.pidfd), 'CURRENT_INIT_PIDFD_EXITED')
        self.actual = held.proc_identity_at(self.proc,self.pid,min(START+OBSERVATION_SECONDS,time.monotonic()+3))
        need(binding.same_epoch_identity(self.actual,expected), 'CURRENT_INIT_IDENTITY_DIFFERS')
        need(set(self.actual['ns']) == set(held.NS_TYPES), 'SIX_ORIGINAL_NAMESPACES_REQUIRED')
        self.namespaces = {}
        for name,kind in held.NS_TYPES.items():
            fd = journal.take(os.open('ns/'+name,os.O_RDONLY|os.O_CLOEXEC,dir_fd=self.proc),
                              'held_init:namespace:'+name)
            match = re.fullmatch(re.escape(name)+r':\[(\d+)\]',self.actual['ns'][name])
            need(match is not None and fcntl.ioctl(fd,0xb703) == kind and
                 os.fstat(fd).st_ino == int(match[1]), 'ORIGINAL_HELD_NAMESPACE_DIFFERS')
            self.namespaces[name] = fd
        self.root = journal.take(os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,
                                         dir_fd=self.proc),'held_init:root')
        self.root_identity = directory_identity(identity(self.root))
        need(stat.S_ISDIR(self.root_identity['mode']) and os.readlink('cwd',dir_fd=self.proc) == '/',
             'ORIGINAL_INIT_ROOT_SHAPE')
        need({key:self.root_identity[key] for key in ('device','inode')} ==
             baseline['process_roots']['android_init'], 'ROOT_DIFFERS_FROM_CURRENT_BASELINE')
        self.verify()

    def verify(self, final=False):
        deadline(final)
        need(self.held.pidfd_alive(self.pidfd), 'CURRENT_INIT_PIDFD_EXITED')
        current = self.held.proc_identity_at(self.proc,self.pid,
                    min(START+(FINAL_SECONDS if final else OBSERVATION_SECONDS),time.monotonic()+3))
        need(current == self.actual, 'HELD_CURRENT_INIT_CHANGED')
        fd = self.journal.take(os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,
                                      dir_fd=self.proc),'held_init:root_recheck')
        try:
            need(directory_identity(identity(fd)) == self.root_identity ==
                 directory_identity(identity(self.root)), 'HELD_CURRENT_ROOT_CHANGED')
        finally:
            self.journal.close(fd)
        for name,fd in self.namespaces.items():
            match = re.fullmatch(re.escape(name)+r':\[(\d+)\]',self.actual['ns'][name])
            need(match is not None and os.fstat(fd).st_ino == int(match[1]) and
                 os.readlink('ns/'+name,dir_fd=self.proc) == self.actual['ns'][name],
                 'HELD_CURRENT_NAMESPACE_CHANGED')
        need(self.held.pidfd_alive(self.pidfd), 'CURRENT_INIT_EXITED_DURING_RECHECK')


class OneApkView:
    def __init__(self, journal, target, path):
        self.journal = journal
        self.target = target
        self.edges = []
        self.path = path
        self.leaf = path.rsplit('/',1)[1]
        parts = path[1:].split('/')
        current = target.root
        for part in parts[:-1]:
            deadline()
            parent = current
            current = journal.take(os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                            dir_fd=parent),'APK:fixed_parent')
            row = directory_identity(identity(current))
            need(stat.S_ISDIR(row['mode']) and row == directory_identity(named_identity(parent,part)),
                 'APK_PARENT_NAME_DIFFERS')
            self.edges.append((parent,part,current,row))
        self.parent = current
        # O_PATH does not open the file for reading and cannot read APK contents.
        self.fd = journal.take(os.open(self.leaf,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,
                                       dir_fd=self.parent),'APK:metadata_only_leaf')

    def observe(self, final=False):
        self.target.verify(final)
        for parent,name,fd,expected in self.edges:
            need(directory_identity(identity(fd)) == expected ==
                 directory_identity(named_identity(parent,name)), 'APK_PARENT_CHANGED')
        held = identity(self.fd)
        named = named_identity(self.parent,self.leaf)
        need(held == named, 'APK_HELD_OR_NAMED_IDENTITY_DIFFERS')
        predicates = original_predicates(held)
        return {'path':self.path,'held':held,'named':named,'held_equals_named':True,
                'original_predicates':predicates,'original_predicate_conjunction':all(predicates.values()),
                'failed_original_predicates':[key for key,value in predicates.items() if not value],
                'APK_content_bytes_read':0,'APK_hash_computed':False}


class ReadDeadline(BaseException):
    pass


def alarm_handler(signum, frame):
    raise ReadDeadline('FIXED_METADATA_SELF_ALARM')


def main():
    global START
    START = time.monotonic()
    result = {
        'schema':1,'kind':FIXED['kind'],'package':FIXED['package'],'collection_complete':False,
        'first_error':None,'secondary_errors':[],
        'Main_actions':0,'Android_commands':0,'children_spawned':0,'namespace_entry':False,
        'files_created_or_modified':0,'APK_content_bytes_read':0,'directory_enumeration':False,
        'private_baseline_exported':False,'App_nonce_consumed':False,'automatic_retry':False,
        'original_metadata_status':'FAILED','original_failed_predicate_at_that_time':'UNKNOWN',
        'installed_package_metadata_qualified':False,'signer_qualified':False,
        'launch_install_or_business_authority':False,'whole_app_production_ready':False,
        'global_ambient_FD_equality_asserted':False,
        'borrowed_R6_FD_cleanup_errors_propagate':True,
        'original_predicates_modified':False,'original_file_limit_bytes':ORIGINAL_FILE_LIMIT,
        'observation_seconds':OBSERVATION_SECONDS,'final_seconds':FINAL_SECONDS,
        'alarm_seconds':ALARM_SECONDS,'timer_and_handler_restored':False,
    }
    journal = Journal()
    lock = view = apk = guard = None
    source = contract = None
    timer_set = handler_set = False
    old_handler = None
    original = None
    observed = False
    stage = 'preconditions'
    try:
        need(len(sys.argv) == 1 and os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
             'ROOT_FIXED_CHILDLESS_DIAGNOSTIC_REQUIRED')
        for fd in (0,1,2):
            os.fstat(fd)
        need(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0), 'AMBIENT_TIMER_NOT_EMPTY')
        need(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,set()), 'SIGALRM_IS_BLOCKED')
        old_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM,alarm_handler)
        handler_set = True
        signal.setitimer(signal.ITIMER_REAL,ALARM_SECONDS)
        timer_set = True
        stage = 'original_failed_report'
        original = read_exact_file(journal,FIXED['result']['path'],FIXED['result']['bytes'],FIXED['result']['sha256'])
        historical = qualify_original(original)
        result['original_result'] = FIXED['result']
        result['historical_package_metadata_observation'] = historical['metadata_before']
        result['original_error'] = historical['error']
        result['fixed_apk_path'] = historical['apk_paths_before'][0]
        stage = 'original_metadata_source'
        read_exact_file(journal,FIXED['source']['path'],FIXED['source']['bytes'],FIXED['source']['sha256'])
        stage = 'original_R6_source_contract'
        source_raw = read_exact_file(journal,SHARED/'source_contract.py',11359,SOURCE_SHA)
        source = module(source_raw,SHARED/'source_contract.py','fixed_apk_metadata_source_contract')
        contract = source.SourceContract(SHARED/'source-manifest.json',MANIFEST_SHA)
        held = contract.load('references/held_runtime_r5.py','fixed_apk_held_original')
        binding = contract.load('main_binding.py','fixed_apk_identity_original')
        current = contract.load('current_baseline_guard.py','fixed_apk_current_guard_original')
        need(contract.files['current_baseline_guard.py']['sha256'] == GUARD_SHA,
             'CURRENT_GUARD_SOURCE_PIN_CHANGED')
        baseline = current.current_baseline()
        need(baseline.get('schema') == 'pocket4-main-current-baseline-v2' and
             baseline.get('kind') == 'current-cell-generation' and
             baseline.get('deployment_performed') is False and 'main_deployed' not in baseline and
             baseline['framework_epoch']['sha256'] == EPOCH_SHA == current.MAIN_EPOCH and
             current.BASELINE_SHA == BASELINE_SHA and current.QUALIFICATION_SHA == QUALIFICATION_SHA,
             'EXACT_CURRENT_BASELINE_REQUIRED')

        def original_guard(final=False):
            deadline(final)
            contract.verify()
            read_exact_file(journal,SHARED/'source_contract.py',11359,SOURCE_SHA,final)
            read_exact_file(journal,FIXED['source']['path'],FIXED['source']['bytes'],FIXED['source']['sha256'],final)
            helper = source.bounded_file(source.HELPER_PATH,source.HELPER_BYTES)
            need(len(helper) == source.HELPER_BYTES and sha(helper) == source.HELPER_SHA,
                 'ORIGINAL_SHARED_HELPER_CHANGED')
            proof = current.current_guard(baseline,action_attempted=False)
            if lock is not None and lock.expected is not None:
                lock.verify()
            if view is not None:
                view.verify(final)
            deadline(final)
            return proof

        guard = original_guard
        result['shared_helper'] = source.verify_shared_helper()
        stage = 'Main_before'
        result['Main_before'] = guard()
        need(result['Main_before'] == historical['Main_before'], 'MAIN_DIFFERS_FROM_ORIGINAL_METADATA')
        stage = 'existing_readonly_action_lock'
        lock = ExistingActionLock(journal)
        lock.acquire()
        stage = 'held_current_init'
        view = HeldInitView(journal,held,binding,baseline)
        result['held_init_root'] = view.root_identity
        result['held_pidfd_and_six_namespaces_qualified'] = True
        stage = 'fixed_APK_first_fstat'
        apk = OneApkView(journal,view,FIXED['apk_path'])
        result['APK_before'] = apk.observe()
        stage = 'fixed_APK_second_fstat'
        result['APK_after'] = apk.observe()
        need(result['APK_after'] == result['APK_before'], 'APK_CHANGED_BETWEEN_METADATA_OBSERVATIONS')
        result['two_held_and_named_observations_equal'] = True
        stage = 'original_report_after'
        again = read_exact_file(journal,FIXED['result']['path'],FIXED['result']['bytes'],FIXED['result']['sha256'])
        need(again == original, 'ORIGINAL_FAILED_REPORT_CHANGED')
        qualify_original(again)
        result['original_failed_report_unchanged'] = True
        observed = True
    except BaseException as error:
        remember(result,stage,error)
    finally:
        if guard is not None:
            try:
                result['Main_after'] = guard(True)
                need(result.get('Main_before') == result['Main_after'], 'MAIN_CHANGED_DURING_METADATA_DIAGNOSTIC')
                result['final_Main_guard_passed'] = True
                result['original_R6_and_metadata_source_unchanged'] = True
            except BaseException as error:
                remember(result,'final_original_Main_and_source_guard',error)
        if apk is not None:
            try:
                result['APK_final'] = apk.observe(True)
                need(result.get('APK_before') == result['APK_final'], 'APK_CHANGED_BEFORE_FD_CLOSE')
            except BaseException as error:
                remember(result,'final_APK_named_and_held',error)
        if lock is not None:
            lock.release(result)
        journal.finish(result)
        if timer_set:
            try:
                signal.setitimer(signal.ITIMER_REAL,0)
            except BaseException as error:
                remember(result,'self_timer_cancel',error)
        if handler_set:
            try:
                signal.signal(signal.SIGALRM,old_handler)
                need(signal.getsignal(signal.SIGALRM) == old_handler and
                     signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0), 'SELF_TIMER_RESTORE_FAILED')
                result['timer_and_handler_restored'] = True
            except BaseException as error:
                remember(result,'self_handler_restore',error)
    if time.monotonic() >= START + ALARM_SECONDS:
        remember(result,'final_collection_deadline',RuntimeError('FINAL_COLLECTION_DEADLINE'))
    result['collection_complete'] = bool(
        observed and result['first_error'] is None and not result['secondary_errors'] and
        result.get('two_held_and_named_observations_equal') is True and
        result.get('original_failed_report_unchanged') is True and
        result.get('final_Main_guard_passed') is True and
        result.get('original_R6_and_metadata_source_unchanged') is True and
        result.get('APK_final') == result.get('APK_before') and
        result.get('all_journal_FDs_closed') is True and
        result.get('action_lock',{}).get('released') is True and
        result['timer_and_handler_restored'])
    result['observed_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    result['observation_finished_unix_ns'] = time.time_ns()
    result['elapsed_seconds'] = time.monotonic()-START
    encoded = (json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(encoded) <= OUTPUT_LIMIT, 'FIXED_PUBLIC_DIAGNOSTIC_OUTPUT_BOUND')
    sys.stdout.write(encoded.decode('utf-8'))
    sys.stdout.flush()
    return 0 if result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
