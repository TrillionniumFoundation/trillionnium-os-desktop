#!/usr/bin/env python3
"""Fixed Hyatt APK/native-member static observation; no child, App execution or file write."""
import binascii
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import struct
import sys
import time
import types
import zlib

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
OBSERVATION_SECONDS = 120
FINAL_SECONDS = 150
ALARM_SECONDS = 165
OUTPUT_LIMIT = 131072
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
    need(type(value) is dict and value.get('schema') == 1 and value.get('ok') is True and
         value.get('package') == FIXED['package'] and
         value.get('source_sha256') == FIXED['source']['sha256'] and
         value.get('metadata_before') == value.get('metadata_after') == FIXED['observed_metadata'] and
         value.get('apk_paths_before') == [row['path'] for row in FIXED['apks']] and
         value.get('error') is None and value.get('secondary_errors') == [] and
         value.get('actual_package_UID_version_APK_chain_stable') is True and
         value.get('package_read_commands_completed') == 5 and
         value.get('total_apk_bytes') == FIXED['total_apk_bytes'],
         'EXACT_PASSED_HYATT_METADATA_REPORT_REQUIRED')
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
    package = FIXED['package']
    listed = ['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',package]
    paths = ['/system/bin/cmd','package','path','--user','0',package]
    resolve = ['/system/bin/cmd','package','resolve-activity','--brief','--user','0',
               '-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER',package]
    commands = value.get('command_observations')
    need(type(commands) is list and len(commands) == 5, 'EXACT_FIVE_OLD_PM_READS_REQUIRED')
    for index,(row,argv) in enumerate(zip(commands,[listed,paths,resolve,paths,listed]),1):
        need(row.get('index') == index and row.get('argv') == argv and
             row.get('spawned') is True and row.get('joined') is True and row.get('entry_entered') is True and
             row.get('returncode') == 0 and row.get('host_timed_out') is False and
             row.get('first_error') is None and row.get('secondary_errors') == [] and
             row.get('recorder_errors') == [] and row.get('Android_UI_action') is False,
             'ORIGINAL_PM_READ_NOT_COMPLETE')
    need(all(value.get(key) == 0 for key in
             ('UI_actions','App_launches','instrumentation_calls','permission_grants','settings_writes')) and
         value.get('business_action_authority') is False and value.get('APK_bytes_exported') is False and
         value.get('whole_app_production_ready') is False, 'ORIGINAL_METADATA_SCOPE_CHANGED')
    artifacts = value.get('artifacts')
    need(type(artifacts) is list and len(artifacts) == len(FIXED['apks']) == 3,
         'THREE_EXACT_HYATT_APKS_REQUIRED')
    old_current = []
    parent = None
    for pin,row in zip(FIXED['apks'],artifacts):
        need(row.get('path') == pin['path'] and row.get('sha256') == pin['sha256'] and
             type(row.get('held_file')) is dict and row['held_file'].get('bytes') == pin['bytes'] and
             set(row['held_file']) == {'device','inode','mode','uid','gid','nlink','bytes','mtime_ns','ctime_ns'} and
             all(type(item) is int for item in row['held_file'].values()) and
             all(original_predicates(row['held_file']).values()), 'ORIGINAL_FULL_APK_PIN_REQUIRED')
        parts = pin['path'].split('/')
        need(len(parts) == 6 and parts[:3] == ['','data','app'] and
             re.fullmatch(r'~~[A-Za-z0-9_=-]+',parts[3]) and
             re.fullmatch(re.escape(package)+r'-[A-Za-z0-9_=-]+',parts[4]) and
             parts[5] in ('base.apk','split_config.arm64_v8a.apk','split_config.xxhdpi.apk'),
             'FIXED_CURRENT_HYATT_APK_PATH_REQUIRED')
        current_parent = '/'.join(parts[:-1])
        if parent is None:
            parent = current_parent
        need(current_parent == parent, 'ONE_FIXED_HYATT_INSTALL_DIRECTORY_REQUIRED')
        old_current.append({'filename':parts[5],'bytes':pin['bytes'],'sha256':pin['sha256']})
    need(old_current == FIXED['historical_apks'] and
         sum(row['bytes'] for row in FIXED['apks']) == FIXED['total_apk_bytes'] == 140798759 and
         FIXED['observed_metadata']['version_code'] == 26090096,
         'HISTORICAL_AND_CURRENT_APK_SET_NOT_EXACT')
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



MAX_ZIP_ENTRIES = 65534
MAX_CENTRAL_BYTES = 8 * 1024 * 1024
MAX_MEMBER_COMPRESSED = 32 * 1024 * 1024
MAX_ELF_BYTES = 64 * 1024 * 1024
MAX_SYMBOLS = 131072
MAX_CODE_WINDOW = 16384
APK_READ_LIMIT = 384 * 1024 * 1024
APK_READ_BYTES = 0


def bounds(offset, size, total, code='BINARY_RANGE_OUTSIDE_FIXED_INPUT'):
    need(type(offset) is int and type(size) is int and
         0 <= offset <= total and 0 <= size <= total - offset, code)


def word(raw, offset, form):
    size = struct.calcsize(form)
    bounds(offset, size, len(raw))
    return struct.unpack_from(form, raw, offset)


class VerifiedApk:
    def __init__(self, journal, target, pin, metadata):
        self.journal = journal
        self.target = target
        self.pin = pin
        self.expected = metadata
        self.edges = []
        self.path = pin['path']
        self.leaf = self.path.rsplit('/', 1)[1]
        parts = self.path[1:].split('/')
        current = target.root
        for part in parts[:-1]:
            deadline()
            parent = current
            current = journal.take(os.open(part, os.O_PATH | os.O_DIRECTORY |
                os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent), 'APK:fixed_parent')
            row = directory_identity(identity(current))
            need(stat.S_ISDIR(row['mode']) and
                 row == directory_identity(named_identity(parent, part)),
                 'APK_PARENT_NAME_DIFFERS')
            self.edges.append((parent, part, current, row))
        self.parent = current
        self.fd = journal.take(os.open(self.leaf, os.O_RDONLY | os.O_NOFOLLOW |
                                      os.O_CLOEXEC, dir_fd=current), 'APK:readonly_leaf')
        self.read_bytes = 0
        self.observe()

    def observe(self, final=False):
        self.target.verify(final)
        for parent, name, fd, expected in self.edges:
            need(directory_identity(identity(fd)) == expected ==
                 directory_identity(named_identity(parent, name)), 'APK_PARENT_CHANGED')
        row = identity(self.fd)
        need(row == self.expected == named_identity(self.parent, self.leaf) and
             row['bytes'] == self.pin['bytes'] and all(original_predicates(row).values()),
             'EXACT_CURRENT_APK_IDENTITY_OR_SHAPE_CHANGED')
        return {'path':self.path, 'held':row, 'held_equals_named':True}

    def read(self, offset, size, final=False):
        global APK_READ_BYTES
        bounds(offset, size, self.pin['bytes'])
        need(size <= 1024 * 1024, 'ONE_APK_READ_BOUND')
        chunks = []
        count = 0
        while count < size:
            deadline(final)
            need(APK_READ_BYTES + (size - count) <= APK_READ_LIMIT,
                 'TOTAL_APK_READ_BOUND')
            block = os.pread(self.fd, size - count, offset + count)
            need(bool(block), 'APK_UNEXPECTED_EOF')
            count += len(block)
            self.read_bytes += len(block)
            APK_READ_BYTES += len(block)
            chunks.append(block)
        return b''.join(chunks)

    def full_hash(self, final=False):
        global APK_READ_BYTES
        self.observe(final)
        value = hashlib.sha256()
        count = 0
        while count < self.pin['bytes']:
            block = self.read(count, min(1024 * 1024, self.pin['bytes'] - count), final)
            value.update(block)
            count += len(block)
        deadline(final)
        need(APK_READ_BYTES + 1 <= APK_READ_LIMIT, 'TOTAL_APK_READ_BOUND')
        extra = os.pread(self.fd, 1, self.pin['bytes'])
        self.read_bytes += len(extra)
        APK_READ_BYTES += len(extra)
        need(extra == b'', 'APK_SIZE_GREW')
        digest = value.hexdigest()
        need(count == self.pin['bytes'] and digest == self.pin['sha256'],
             'APK_COMPLETE_SHA256_CHANGED')
        self.observe(final)
        return {'path':self.path, 'bytes':count, 'sha256':digest, 'EOF_observed':True}


def central_member(apk):
    total = apk.pin['bytes']
    tail_start = max(0, total - 65557)
    tail = apk.read(tail_start, total - tail_start)
    candidates = []
    cursor = 0
    while True:
        offset = tail.find(b'PK\x05\x06', cursor)
        if offset < 0:
            break
        cursor = offset + 1
        if offset + 22 <= len(tail):
            comment = word(tail, offset + 20, '<H')[0]
            if offset + 22 + comment == len(tail):
                candidates.append(offset)
    need(len(candidates) == 1, 'ONE_COMPLETE_ZIP_EOCD_REQUIRED')
    index = candidates[0]
    disk, central_disk, on_disk, entries, size, start, comment = word(tail, index + 4, '<4H2IH')
    need(disk == central_disk == 0 and on_disk == entries and
         0 < entries <= MAX_ZIP_ENTRIES and size <= MAX_CENTRAL_BYTES and
         start != 0xffffffff and size != 0xffffffff, 'ZIP_DIRECTORY_LIMIT_OR_ZIP64')
    bounds(start, size, total)
    need(start + size == tail_start + index, 'ZIP_DIRECTORY_END_DIFFERS')
    chunks = []
    done = 0
    while done < size:
        chunk = apk.read(start + done, min(1024 * 1024, size - done))
        chunks.append(chunk)
        done += len(chunk)
    raw = b''.join(chunks)
    position = 0
    matches = []
    named = []
    for entry in range(entries):
        deadline()
        bounds(position, 46, len(raw))
        need(raw[position:position+4] == b'PK\x01\x02', 'ZIP_CENTRAL_SIGNATURE')
        flags, method = word(raw, position + 8, '<2H')
        crc, packed, unpacked = word(raw, position + 16, '<3I')
        name_size, extra_size, comment_size, member_disk = word(raw, position + 28, '<4H')
        external, local = word(raw, position + 38, '<2I')
        need(0 < name_size <= 4096 and member_disk == 0 and
             packed != 0xffffffff and unpacked != 0xffffffff and local != 0xffffffff,
             'ZIP_MEMBER_DIRECTORY_BOUND')
        width = 46 + name_size + extra_size + comment_size
        bounds(position, width, len(raw))
        name = raw[position+46:position+46+name_size]
        need(b'\0' not in name, 'ZIP_NAME_CONTAINS_NUL')
        if name.rsplit(b'/', 1)[-1] == b'libdexprotector.so':
            need(len(named) < 16, 'DEXPROTECTOR_BASENAME_MATCH_BOUND')
            named.append({'member_name_bytes':len(name), 'member_name_sha256':sha(name),
                          'fixed_arm64_path':name == FIXED['target_member'].encode('ascii'),
                          'method':method, 'compressed_bytes':packed, 'member_bytes':unpacked})
        if name == FIXED['target_member'].encode('ascii'):
            matches.append({'name':name, 'flags':flags, 'method':method, 'crc32':crc,
                            'compressed_bytes':packed, 'member_bytes':unpacked,
                            'external_attributes':external, 'local_offset':local,
                            'central_offset':start})
        position += width
    need(position == len(raw), 'ZIP_DIRECTORY_PARSE_NOT_COMPLETE')
    need(len(matches) <= 1, 'DUPLICATE_FIXED_NATIVE_MEMBER')
    return {'APK_filename':apk.leaf, 'entries':entries, 'directory_bytes':size,
            'directory_sha256':sha(raw), 'EOCD_and_directory_complete':True,
            'fixed_member_matches':len(matches), 'same_basename_metadata':named}, matches


def decompress_member(apk, item):
    need(item['flags'] & 1 == 0 and item['method'] in (0, 8),
         'NATIVE_MEMBER_ENCRYPTION_OR_METHOD_UNSUPPORTED')
    need(0 < item['compressed_bytes'] <= MAX_MEMBER_COMPRESSED and
         64 <= item['member_bytes'] <= MAX_ELF_BYTES, 'NATIVE_MEMBER_SIZE_BOUND')
    unix_mode = item['external_attributes'] >> 16
    need(stat.S_IFMT(unix_mode) in (0, stat.S_IFREG), 'NATIVE_MEMBER_NOT_REGULAR')
    header = apk.read(item['local_offset'], 30)
    need(header[:4] == b'PK\x03\x04', 'ZIP_LOCAL_SIGNATURE')
    flags, method = word(header, 6, '<2H')
    crc, packed, unpacked = word(header, 14, '<3I')
    name_size, extra_size = word(header, 26, '<2H')
    need(flags == item['flags'] and method == item['method'] and
         name_size == len(item['name']), 'ZIP_LOCAL_CENTRAL_MISMATCH')
    if flags & 8 == 0:
        need((crc, packed, unpacked) ==
             (item['crc32'], item['compressed_bytes'], item['member_bytes']),
             'ZIP_LOCAL_SIZES_DIFFER')
    name = apk.read(item['local_offset'] + 30, name_size)
    need(name == item['name'], 'ZIP_LOCAL_NAME_DIFFERS')
    data_start = item['local_offset'] + 30 + name_size + extra_size
    bounds(data_start, item['compressed_bytes'], apk.pin['bytes'])
    need(data_start + item['compressed_bytes'] <= item['central_offset'],
         'ZIP_MEMBER_OVERLAPS_CENTRAL_DIRECTORY')
    output = bytearray()
    compressed = hashlib.sha256()
    decoder = zlib.decompressobj(-15) if method == 8 else None
    done = 0
    while done < item['compressed_bytes']:
        block = apk.read(data_start + done, min(65536, item['compressed_bytes'] - done))
        done += len(block)
        compressed.update(block)
        if decoder is None:
            output.extend(block)
            need(len(output) <= item['member_bytes'], 'NATIVE_MEMBER_EXPANSION_BOUND')
        else:
            pending = block
            while pending:
                deadline()
                room = item['member_bytes'] + 1 - len(output)
                need(room > 0, 'NATIVE_MEMBER_EXPANSION_BOUND')
                old = len(pending)
                chunk = decoder.decompress(pending, min(65536, room))
                output.extend(chunk)
                need(len(output) <= item['member_bytes'], 'NATIVE_MEMBER_EXPANSION_BOUND')
                need(not decoder.unused_data, 'NATIVE_MEMBER_COMPRESSED_TRAILING_BYTES')
                pending = decoder.unconsumed_tail
                need(chunk or len(pending) < old, 'NATIVE_MEMBER_DECOMPRESS_NO_PROGRESS')
    if decoder is not None:
        need(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
             'NATIVE_MEMBER_DEFLATE_INCOMPLETE')
    need(len(output) == item['member_bytes'] and
         binascii.crc32(output) & 0xffffffff == item['crc32'], 'NATIVE_MEMBER_LENGTH_OR_CRC')
    return bytes(output), {'member':FIXED['target_member'], 'APK_filename':apk.leaf,
                          'method':method, 'bytes':len(output), 'sha256':sha(output),
                          'compressed_bytes':done, 'compressed_sha256':compressed.hexdigest(),
                          'CRC32_matched':True, 'extracted_to_disk':False}


def elf_metadata(raw):
    need(64 <= len(raw) <= MAX_ELF_BYTES and raw[:7] == b'\x7fELF\x02\x01\x01',
         'ELF64_LITTLE_ENDIAN_REQUIRED')
    values = word(raw, 16, '<HHIQQQIHHHHHH')
    kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phcount, shsize, shcount, shstr = values
    need(kind == 3 and machine == 183 and version == 1 and ehsize == 64 and
         phsize == 56 and 0 < phcount <= 256, 'ARM64_SHARED_ELF_HEADER_REQUIRED')
    bounds(phoff, phsize * phcount, len(raw))
    segments = []
    for index in range(phcount):
        ptype, pflags, offset, vaddr, paddr, filesz, memsz, align = word(raw, phoff + 56 * index, '<II6Q')
        bounds(offset, filesz, len(raw))
        need((ptype != 1 or filesz <= memsz) and vaddr + memsz <= (1 << 64),
             'ELF_SEGMENT_RANGE')
        segments.append({'type':ptype, 'flags':pflags, 'offset':offset,
                         'vaddr':vaddr, 'filesz':filesz, 'memsz':memsz})
    loads = [x for x in segments if x['type'] == 1]
    need(bool(loads), 'ELF_LOAD_SEGMENT_REQUIRED')

    def mapped(address, size, executable=False):
        need(type(address) is int and type(size) is int and address >= 0 and size >= 0,
             'ELF_VIRTUAL_RANGE')
        choices = [x for x in loads if address >= x['vaddr'] and
                   address - x['vaddr'] <= x['filesz'] and
                   size <= x['filesz'] - (address - x['vaddr']) and
                   (not executable or x['flags'] & 1)]
        need(len(choices) == 1, 'ELF_VIRTUAL_RANGE_NOT_UNIQUE_FILE_BACKED')
        item = choices[0]
        offset = item['offset'] + address - item['vaddr']
        bounds(offset, size, len(raw))
        return offset

    build_ids = []
    note_bytes = 0
    for segment in [x for x in segments if x['type'] == 4]:
        note_bytes += segment['filesz']
        need(note_bytes <= 1024 * 1024, 'ELF_NOTE_BYTE_BOUND')
        offset, end = segment['offset'], segment['offset'] + segment['filesz']
        while offset < end:
            deadline()
            if end - offset < 12:
                need(raw[offset:end] == b'\0' * (end-offset), 'ELF_NOTE_TRAILING_BYTES')
                break
            namesz, descsz, note_type = word(raw, offset, '<3I')
            offset += 12
            need(namesz <= 65536 and descsz <= 65536, 'ELF_NOTE_FIELD_BOUND')
            padded_name, padded_desc = (namesz+3)&~3, (descsz+3)&~3
            bounds(offset, padded_name+padded_desc, end)
            name = raw[offset:offset+namesz]
            desc = raw[offset+padded_name:offset+padded_name+descsz]
            if name == b'GNU\0' and note_type == 3:
                need(1 <= descsz <= 64 and len(build_ids) < 4, 'ELF_BUILD_ID_BOUND')
                build_ids.append(desc.hex())
            offset += padded_name+padded_desc
    need(len(set(build_ids)) <= 1, 'ELF_BUILD_ID_CONFLICT')

    dynamic = [x for x in segments if x['type'] == 2]
    need(len(dynamic) == 1 and dynamic[0]['filesz'] % 16 == 0 and
         16 <= dynamic[0]['filesz'] <= 1024*1024, 'ONE_BOUNDED_DYNAMIC_TABLE_REQUIRED')
    tags = {}
    terminated = False
    wanted = {4,5,6,10,11,14,0x6ffffef5}
    for offset in range(dynamic[0]['offset'], dynamic[0]['offset']+dynamic[0]['filesz'], 16):
        tag, value = word(raw, offset, '<qQ')
        if tag == 0:
            terminated = True
            break
        if tag in wanted:
            need(tag not in tags, 'DUPLICATE_REQUIRED_DYNAMIC_TAG')
            tags[tag] = value
    need(terminated and all(tag in tags for tag in (5,6,10,11)) and tags[11] == 24 and
         0 < tags[10] <= 16*1024*1024, 'ELF_DYNSYM_DYNAMIC_CONTRACT')
    strings = mapped(tags[5], tags[10])
    count = None
    if 4 in tags:
        table = mapped(tags[4], 8)
        buckets, chains = word(raw, table, '<2I')
        need(0 < buckets <= MAX_SYMBOLS and 0 < chains <= MAX_SYMBOLS, 'ELF_HASH_COUNT_BOUND')
        mapped(tags[4], 8+4*(buckets+chains))
        count = chains
    if 0x6ffffef5 in tags:
        address = tags[0x6ffffef5]
        at = mapped(address, 16)
        buckets, first, bloom, shift = word(raw, at, '<4I')
        need(0 < buckets <= MAX_SYMBOLS and 0 < bloom <= MAX_SYMBOLS and first < MAX_SYMBOLS,
             'ELF_GNU_HASH_COUNT_BOUND')
        size = 16 + bloom*8 + buckets*4
        at = mapped(address, size)
        values = word(raw, at+16+bloom*8, '<'+'I'*buckets)
        need(all(x == 0 or first <= x < MAX_SYMBOLS for x in values), 'ELF_GNU_HASH_BUCKET')
        last = max(values)
        derived = first
        if last:
            index = last
            while True:
                deadline()
                need(index < MAX_SYMBOLS, 'ELF_GNU_HASH_CHAIN_BOUND')
                here = mapped(address+size+4*(index-first),4)
                value = word(raw,here,'<I')[0]
                index += 1
                if value & 1:
                    derived = index
                    break
        if count is None:
            count = derived
        else:
            need(derived == count, 'ELF_HASH_COUNTS_DIFFER')
    need(type(count) is int and 0 < count <= MAX_SYMBOLS, 'BOUNDED_ELF_SYMBOL_COUNT_REQUIRED')
    table = mapped(tags[6], 24*count)
    symbols = []
    target = b'JNI_OnLoad\0'
    for index in range(count):
        if index % 512 == 0:
            deadline()
        name, info, other, section, value, size = word(raw,table+24*index,'<IBBHQQ')
        need(name < tags[10], 'ELF_DYNSYM_NAME_RANGE')
        if name+len(target) <= tags[10] and raw[strings+name:strings+name+len(target)] == target:
            symbols.append({'index':index,'binding':info>>4,'type':info&15,'visibility':other&3,
                            'section_index':section,'value':value,'size':size})
    need(len(symbols) == 1, 'ONE_JNI_ONLOAD_DYNSYM_REQUIRED')
    symbol = symbols[0]
    need(symbol['type'] == 2 and symbol['binding'] in (1,2) and
         symbol['section_index'] not in (0,0xfff1,0xfff2) and symbol['value'] % 4 == 0,
         'DEFINED_ARM64_JNI_ONLOAD_FUNCTION_REQUIRED')
    choices = [x for x in loads if x['flags'] & 1 and
               x['vaddr'] <= symbol['value'] < x['vaddr']+x['filesz']]
    need(len(choices) == 1, 'JNI_ONLOAD_EXECUTABLE_SEGMENT')
    available = choices[0]['filesz'] - (symbol['value']-choices[0]['vaddr'])
    if symbol['size']:
        need(symbol['size'] <= available, 'JNI_ONLOAD_SYMBOL_EXCEEDS_FILE_BACKED_SEGMENT')
    length = min(symbol['size'] or 4096, MAX_CODE_WINDOW, available)
    length -= length % 4
    need(length >= 4, 'JNI_ONLOAD_CODE_WINDOW_EMPTY')
    offset = mapped(symbol['value'],length,True)
    code = raw[offset:offset+length]
    counts = {'RET':0,'BR':0,'BLR':0,'B':0,'BL':0,'MOVZ_OR_MOVN_REGISTER0':0}
    observations = []
    def observe(item):
        if len(observations) < 128:
            observations.append(item)
    for index in range(0,len(code),4):
        insn = word(code,index,'<I')[0]
        base = insn & 0xfffffc1f
        at = symbol['value']+index
        if base in (0xd65f0000,0xd61f0000,0xd63f0000):
            category = {0xd65f0000:'RET',0xd61f0000:'BR',0xd63f0000:'BLR'}[base]
            counts[category] += 1
            observe({'offset':index,'kind':category,'register':(insn>>5)&31})
        elif insn & 0x7c000000 == 0x14000000:
            category = 'BL' if insn & 0x80000000 else 'B'
            displacement = insn & 0x03ffffff
            if displacement & (1<<25):
                displacement -= 1<<26
            destination = at + 4*displacement
            counts[category] += 1
            observe({'offset':index,'kind':category,'destination_vaddr':destination,
                     'destination_inside_inspected_window':
                         symbol['value'] <= destination < symbol['value']+length})
        elif insn & 31 == 0 and (insn & 0x7f800000) in (0x12800000,0x52800000):
            width = 64 if insn & 0x80000000 else 32
            half = (insn>>21)&3
            if width == 32 and half >= 2:
                continue
            immediate = ((insn>>5)&0xffff) << (16*half)
            if insn & 0x7f800000 == 0x12800000:
                immediate = (~immediate) & ((1<<width)-1)
            low = immediate & 0xffffffff
            signed = low if low < (1<<31) else low-(1<<32)
            counts['MOVZ_OR_MOVN_REGISTER0'] += 1
            # Only fixed JNI constants/sentinel are public; other immediates
            # are counted without exposing arbitrary instruction data.
            label = {-500:'MINUS_500',-1:'JNI_ERR',0x10002:'JNI_VERSION_1_2',
                     0x10004:'JNI_VERSION_1_4',0x10006:'JNI_VERSION_1_6'}.get(signed)
            if label is not None:
                observe({'offset':index,'kind':'REGISTER0_FIXED_IMMEDIATE',
                         'width':width,'constant':label,
                         'next_instruction_is_RET':index+8 <= len(code) and
                            word(code,index+4,'<I')[0]&0xfffffc1f == 0xd65f0000})
    return {'ELF_class':'ELF64','endianness':'little','machine':'EM_AARCH64',
            'type':'ET_DYN','bytes':len(raw),'sha256':sha(raw),
            'BuildId':build_ids[0] if build_ids else None,
            'BuildId_status':'OBSERVED_GNU_NOTE' if build_ids else 'NOT_PRESENT_IN_PT_NOTE',
            'program_headers':phcount,'dynamic_symbols':count,'JNI_OnLoad':symbol,
            'return_path_metadata':{
                'scope':'LINEAR_INSTRUCTION_WINDOW_NOT_CONTROL_FLOW_OR_RETURN_PROOF',
                'file_offset':offset,'vaddr':symbol['value'],'bytes':length,'sha256':sha(code),
                'whole_symbol_bytes_inspected':bool(symbol['size'] and symbol['size']==length),
                'symbol_size_unknown':symbol['size']==0,
                'opcode_counts':counts,'observations':observations,
                'observation_limit':128,
                'observation_list_may_be_truncated':sum(counts.values()) > 128,
                'function_executed':False,'actual_return_value_observed':False,
                'minus_500_cause_established':False},
            'APK_or_ELF_bytes_exported':False}

def parser_controls():
    """Pure in-memory fixtures call the production binary readers, with no OS seam."""
    passed = []
    class MemoryApk:
        def __init__(self, raw):
            self.raw = raw
            self.pin = {'bytes':len(raw)}
            self.leaf = 'synthetic.apk'
        def read(self, offset, size, final=False):
            deadline(final)
            bounds(offset,size,len(self.raw))
            need(size <= 1024*1024, 'ONE_APK_READ_BOUND')
            return self.raw[offset:offset+size]

    def synthetic_elf(gnu=False):
        raw = bytearray(1536)
        raw[:16] = b'\x7fELF\x02\x01\x01'+b'\0'*9
        struct.pack_into('<HHIQQQIHHHHHH',raw,16,3,183,1,0,64,0,0,64,56,3,0,0,0)
        struct.pack_into('<II6Q',raw,64,1,5,0,0x10000,0,1536,1536,4096)
        struct.pack_into('<II6Q',raw,120,2,4,256,0x10100,0,96,96,8)
        struct.pack_into('<II6Q',raw,176,4,4,704,0x102c0,0,20,20,4)
        table = [(5,0x10200),(6,0x10240),(10,12),(11,24),
                 (0x6ffffef5 if gnu else 4,0x10280),(0,0)]
        for index,(tag,value) in enumerate(table):
            struct.pack_into('<qQ',raw,256+16*index,tag,value)
        raw[512:524] = b'\0JNI_OnLoad\0'
        struct.pack_into('<IBBHQQ',raw,600,1,0x12,0,1,0x10300,8)
        if gnu:
            struct.pack_into('<4I',raw,640,1,1,1,5)
            struct.pack_into('<Q',raw,656,0)
            struct.pack_into('<2I',raw,664,1,1)
        else:
            struct.pack_into('<5I',raw,640,1,2,1,0,0)
        struct.pack_into('<3I',raw,704,4,4,3)
        raw[716:720] = b'GNU\0'
        raw[720:724] = b'\x11\x22\x33\x44'
        struct.pack_into('<2I',raw,768,0x12800000 | (499<<5),0xd65f03c0)
        return bytes(raw)

    def synthetic_zip(member, method=0, duplicate=False, bad_crc=False,
                      declared=None, truncate_deflate=False, append_deflate=False):
        name = FIXED['target_member'].encode('ascii')
        if method == 8:
            encoder = zlib.compressobj(6,zlib.DEFLATED,-15)
            packed = encoder.compress(member)+encoder.flush()
            if truncate_deflate:
                packed = packed[:-1]
            if append_deflate:
                packed += b'\0'
        else:
            packed = member
        crc = binascii.crc32(member)&0xffffffff
        if bad_crc:
            crc ^= 1
        size = len(member) if declared is None else declared
        local = struct.pack('<I5H3I2H',0x04034b50,20,0,method,0,0,crc,len(packed),size,len(name),0)+name+packed
        central = struct.pack('<I6H3I5H2I',0x02014b50,0x0314,20,0,method,0,0,
                              crc,len(packed),size,len(name),0,0,0,0,0o100444<<16,0)+name
        if duplicate:
            central += central
        count = 2 if duplicate else 1
        end = struct.pack('<I4H2IH',0x06054b50,0,0,count,count,len(central),len(local),0)
        return local+central+end

    def case(name, fn):
        deadline()
        fn()
        passed.append(name)
    def reject(name, code, fn):
        def run():
            try:
                fn()
            except RuntimeError as error:
                need(str(error) == code, 'PARSER_CONTROL_WRONG_REJECTION')
            else:
                raise RuntimeError('PARSER_CONTROL_EXPECTED_REJECTION')
        case(name,run)
    def inspect_zip(raw):
        apk = MemoryApk(raw)
        projection,found = central_member(apk)
        need(projection['fixed_member_matches'] == 1 and len(found) == 1,
             'PARSER_CONTROL_ONE_FIXED_MEMBER')
        return decompress_member(apk,found[0])

    elf = synthetic_elf()
    def valid_sysv():
        value = elf_metadata(elf)
        need(value['BuildId'] == '11223344' and value['dynamic_symbols'] == 2 and
             value['JNI_OnLoad']['size'] == 8 and
             value['return_path_metadata']['whole_symbol_bytes_inspected'] is True and
             value['return_path_metadata']['actual_return_value_observed'] is False and
             value['return_path_metadata']['minus_500_cause_established'] is False and
             value['return_path_metadata']['opcode_counts']['RET'] == 1 and
             any(row.get('constant') == 'MINUS_500' and row['next_instruction_is_RET']
                 for row in value['return_path_metadata']['observations']),
             'PARSER_CONTROL_SYSV_POSITIVE')
    case('elf_sysv_exact_symbol_buildid_and_fixed_immediate_metadata',valid_sysv)
    def valid_gnu():
        value = elf_metadata(synthetic_elf(True))
        need(value['dynamic_symbols'] == 2 and value['JNI_OnLoad']['value'] == 0x10300,
             'PARSER_CONTROL_GNU_POSITIVE')
    case('elf_gnu_hash_exact_symbol_count',valid_gnu)
    reject('elf_short_header_rejected','ELF64_LITTLE_ENDIAN_REQUIRED',lambda:elf_metadata(elf[:63]))
    wrong = bytearray(elf);struct.pack_into('<H',wrong,18,62)
    reject('elf_wrong_machine_rejected','ARM64_SHARED_ELF_HEADER_REQUIRED',lambda:elf_metadata(wrong))
    wrong_strings = bytearray(elf);struct.pack_into('<Q',wrong_strings,264,0x90000)
    reject('elf_unmapped_string_table_rejected','ELF_VIRTUAL_RANGE_NOT_UNIQUE_FILE_BACKED',
           lambda:elf_metadata(wrong_strings))
    wrong_syment = bytearray(elf);struct.pack_into('<Q',wrong_syment,312,8)
    reject('elf_wrong_symbol_stride_rejected','ELF_DYNSYM_DYNAMIC_CONTRACT',
           lambda:elf_metadata(wrong_syment))
    wrong_size = bytearray(elf);struct.pack_into('<Q',wrong_size,616,MAX_ELF_BYTES)
    reject('elf_symbol_size_outside_executable_segment_rejected',
           'JNI_ONLOAD_SYMBOL_EXCEEDS_FILE_BACKED_SEGMENT',lambda:elf_metadata(wrong_size))
    def stored():
        raw,proof = inspect_zip(synthetic_zip(elf))
        need(raw == elf and proof['sha256'] == sha(elf) and proof['CRC32_matched'] is True,
             'PARSER_CONTROL_STORED_POSITIVE')
    case('zip_stored_member_full_hash_and_crc',stored)
    def deflated():
        raw,proof = inspect_zip(synthetic_zip(elf,8))
        need(raw == elf and proof['sha256'] == sha(elf) and proof['CRC32_matched'] is True,
             'PARSER_CONTROL_DEFLATE_POSITIVE')
    case('zip_deflate_member_complete_and_exact',deflated)
    reject('zip_duplicate_fixed_member_rejected','DUPLICATE_FIXED_NATIVE_MEMBER',
           lambda:central_member(MemoryApk(synthetic_zip(elf,duplicate=True))))
    reject('zip_wrong_crc_rejected','NATIVE_MEMBER_LENGTH_OR_CRC',
           lambda:inspect_zip(synthetic_zip(elf,bad_crc=True)))
    reject('zip_declared_member_over_bound_rejected','NATIVE_MEMBER_SIZE_BOUND',
           lambda:inspect_zip(synthetic_zip(elf,declared=MAX_ELF_BYTES+1)))
    reject('zip_truncated_deflate_rejected','NATIVE_MEMBER_DEFLATE_INCOMPLETE',
           lambda:inspect_zip(synthetic_zip(elf,8,truncate_deflate=True)))
    reject('zip_deflate_trailing_bytes_rejected','NATIVE_MEMBER_COMPRESSED_TRAILING_BYTES',
           lambda:inspect_zip(synthetic_zip(elf,8,append_deflate=True)))
    reject('zip_truncated_eocd_rejected','ONE_COMPLETE_ZIP_EOCD_REQUIRED',
           lambda:central_member(MemoryApk(synthetic_zip(elf)[:-1])))
    need(len(passed) == 15, 'EXACT_PARSER_CONTROL_COUNT')
    return {'count':15,'passed':passed,'pure_memory_only':True,
            'real_APK_or_ELF_used':False,'Main_or_FD_lifecycle_exercised':False,
            'runtime_return_or_cause_proven':False}


class ReadDeadline(BaseException):
    pass


def alarm_handler(signum, frame):
    raise ReadDeadline('FIXED_METADATA_SELF_ALARM')


def main():
    global START, APK_READ_BYTES
    START = time.monotonic()
    APK_READ_BYTES = 0
    result = {
        'schema':1,'kind':FIXED['kind'],'package':FIXED['package'],'collection_complete':False,
        'first_error':None,'secondary_errors':[],
        'Main_actions':0,'Android_commands':0,'children_spawned':0,'namespace_entry':False,
        'files_created_or_modified':0,'APK_content_bytes_read':0,'filesystem_directory_enumeration':False,
        'private_baseline_exported':False,'App_nonce_consumed':False,'automatic_retry':False,
        'original_metadata_status':'PASS',
        'historical_runtime_failure':{'library':'libdexprotector.so','JNI_OnLoad_returned':-500,
            'failure_reclassified':False,'underlying_return_reason_established':False},
        'historical_and_current_APK_bytes_equal':False,
        'current_PM_UID_version_not_requeried':True,
        'installed_package_metadata_qualified':False,'signer_qualified':False,
        'launch_install_or_business_authority':False,'whole_app_production_ready':False,
        'global_ambient_FD_equality_asserted':False,
        'borrowed_R6_FD_cleanup_errors_propagate':True,
        'original_predicates_modified':False,'original_file_limit_bytes':ORIGINAL_FILE_LIMIT,
        'observation_seconds':OBSERVATION_SECONDS,'final_seconds':FINAL_SECONDS,
        'alarm_seconds':ALARM_SECONDS,'timer_and_handler_restored':False,
        'APK_total_read_byte_limit':APK_READ_LIMIT,
        'ZIP_central_directory_limit_per_APK':MAX_CENTRAL_BYTES,
        'ZIP_entry_limit_per_APK':MAX_ZIP_ENTRIES,
        'native_member_compressed_byte_limit':MAX_MEMBER_COMPRESSED,
        'native_member_uncompressed_byte_limit':MAX_ELF_BYTES,
        'ELF_dynamic_symbol_limit':MAX_SYMBOLS,'instruction_window_byte_limit':MAX_CODE_WINDOW,
        'APKs_before':[],'APK_hashes_before':[],'APKs_after':[],'APK_hashes_after':[],
        'APK_ZIP_directories':[],'APKs_final':[],
        'APK_or_ELF_raw_bytes_exported':False,'symbol_window_is_linear_metadata_only':True,
    }
    journal = Journal()
    lock = view = guard = None
    apks = []
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
        stage = 'pure_binary_parser_controls'
        result['parser_controls'] = parser_controls()
        stage = 'original_metadata_report'
        original = read_exact_file(journal,FIXED['result']['path'],FIXED['result']['bytes'],FIXED['result']['sha256'])
        historical = qualify_original(original)
        result['original_result'] = FIXED['result']
        result['historical_package_metadata_observation'] = historical['metadata_before']
        result['original_metadata_qualified'] = True
        result['fixed_apk_paths'] = historical['apk_paths_before']
        result['historical_and_current_APK_bytes_equal'] = True
        result['historical_current_APK_pin_comparison'] = FIXED['historical_apks']
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
        stage = 'three_fixed_APKs_full_hash_before'
        for pin,row in zip(FIXED['apks'],historical['artifacts']):
            apk = VerifiedApk(journal,view,pin,row['held_file'])
            apks.append(apk)
            result['APKs_before'].append(apk.observe())
            result['APK_hashes_before'].append(apk.full_hash())
        need(len(result['APK_hashes_before']) == 3, 'THREE_FULL_APK_HASHES_REQUIRED')
        result['all_APK_full_hashes_qualified_before_member_read'] = True
        stage = 'three_fixed_ZIP_directories'
        selected = []
        for index,apk in enumerate(apks):
            projection,matches = central_member(apk)
            result['APK_ZIP_directories'].append(projection)
            selected.extend((index,item) for item in matches)
        need(len(selected) == 1, 'ONE_FIXED_ARM64_NATIVE_MEMBER_ACROSS_THREE_APKS')
        member_index,item = selected[0]
        stage = 'fixed_native_member_complete_read'
        member,proof = decompress_member(apks[member_index],item)
        result['native_member'] = proof
        stage = 'fixed_native_member_ELF_metadata'
        result['ELF'] = elf_metadata(member)
        need(result['ELF']['sha256'] == proof['sha256'] and
             result['ELF']['bytes'] == proof['bytes'], 'ELF_AND_MEMBER_FULL_PIN_DIFFER')
        del member
        stage = 'three_fixed_APKs_full_hash_after'
        for apk in apks:
            result['APK_hashes_after'].append(apk.full_hash())
            result['APKs_after'].append(apk.observe())
        need(result['APK_hashes_before'] == result['APK_hashes_after'] and
             result['APKs_before'] == result['APKs_after'],
             'APK_CHANGED_DURING_STATIC_MEMBER_OBSERVATION')
        result['two_complete_hashes_and_held_named_observations_equal'] = True
        stage = 'original_report_after'
        again = read_exact_file(journal,FIXED['result']['path'],FIXED['result']['bytes'],FIXED['result']['sha256'])
        need(again == original, 'ORIGINAL_METADATA_REPORT_CHANGED')
        qualify_original(again)
        result['original_metadata_report_unchanged'] = True
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
        for index,apk in enumerate(apks):
            try:
                final = apk.observe(True)
                result['APKs_final'].append(final)
                need(index < len(result['APKs_before']) and
                     result['APKs_before'][index] == final, 'APK_CHANGED_BEFORE_FD_CLOSE')
            except BaseException as error:
                remember(result,'final_APK_'+str(index)+'_named_and_held',error)
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
    result['APK_content_bytes_read'] = APK_READ_BYTES
    result['APK_bytes_read_per_open_leaf'] = [{'filename':apk.leaf,'bytes':apk.read_bytes} for apk in apks]
    if time.monotonic() >= START + FINAL_SECONDS:
        remember(result,'final_collection_deadline',RuntimeError('FINAL_COLLECTION_DEADLINE'))
    result['collection_complete'] = bool(
        observed and result['first_error'] is None and not result['secondary_errors'] and
        result.get('parser_controls',{}).get('count') == 15 and
        result.get('all_APK_full_hashes_qualified_before_member_read') is True and
        result.get('two_complete_hashes_and_held_named_observations_equal') is True and
        result.get('original_metadata_report_unchanged') is True and
        result.get('final_Main_guard_passed') is True and
        result.get('original_R6_and_metadata_source_unchanged') is True and
        len(result['APKs_before']) == len(result['APKs_final']) == 3 and
        result['APKs_final'] == result['APKs_before'] and
        len(result['APK_hashes_after']) == 3 and result.get('ELF') is not None and
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
