"""Read one admitted Main's actual user namespace and mapped credentials.

This module neither discovers a Main nor accepts a serialized observation as
execution authority. The caller must first authenticate the native owner and
hold its exact init proc directory, pidfd and seven namespace descriptors. The
owner namespace pin below is checked against those live handles. No namespace
entry, credential change, Android command or data-content read is performed.
"""
import copy
import fcntl
import hashlib
import os
import re
import select
import stat
import time

SCHEMA = 'pocket4-held-main-user-namespace-v1'
USER = 0x10000000
NS_GET_USERNS = 0xb701
NS_GET_PARENT = 0xb702
NS_GET_NSTYPE = 0xb703
NS_TYPES = {'mnt': 0x00020000, 'pid': 0x20000000, 'uts': 0x04000000,
            'ipc': 0x08000000, 'net': 0x40000000, 'cgroup': 0x02000000}
ANDROID_IDS = {'init': (0, 0), 'zygote64': (0, 0),
               'system_server': (1000, 1000), 'surfaceflinger': (1000, 1003)}
HOST_IDS = {'daemon': 0, 'presenter': 1000, 'applications': 1000}
REQUIRED_ENV={'PATH','BOOTCLASSPATH','DEX2OATBOOTCLASSPATH','ANDROID_ROOT','ANDROID_DATA','ANDROID_ART_ROOT'}
ALLOWED_ENV=REQUIRED_ENV|{'ANDROID_ASSETS','ANDROID_BOOTLOGO','ANDROID_I18N_ROOT','ANDROID_STORAGE',
    'ANDROID_TZDATA_ROOT','ASEC_MOUNTPOINT','DOWNLOAD_CACHE','EXTERNAL_STORAGE','LOOP_MOUNTPOINT',
    'STANDALONE_SYSTEMSERVER_JARS','SYSTEMSERVERCLASSPATH','LANG'}


def android_environment(raw):
    """Select only the original Android/classpath keys from held zygote data."""
    need(type(raw) is bytes and 0<len(raw)<=256*1024 and raw.endswith(b'\0'),
         'BOUNDED_COMPLETE_HELD_ZYGOTE_ENVIRONMENT_REQUIRED')
    values={}
    for row in raw.split(b'\0'):
        if b'=' not in row:continue
        key,value=row.split(b'=',1)
        key=key.decode('utf-8','strict')
        if key not in ALLOWED_ENV:continue
        need(key not in values and len(value)<=65536,'ANDROID_ENVIRONMENT_DUPLICATE_OR_BOUND')
        values[key]=value.decode('utf-8','strict')
    need(REQUIRED_ENV<=set(values)<=ALLOWED_ENV and all(values[key] for key in REQUIRED_ENV),
         'COMPLETE_ORIGINAL_ANDROID_ENVIRONMENT_REQUIRED')
    return values


def need(value, code):
    if not value:
        raise RuntimeError(code)


def integer(value, minimum=0, maximum=0xffffffff):
    return type(value) is int and minimum <= value <= maximum


def namespace_pin(value):
    need(type(value) is dict and set(value) == {'link', 'device', 'inode'}
         and integer(value['device'], 1, 2**64-1)
         and integer(value['inode'], 1, 2**64-1)
         and value['link'] == 'user:[' + str(value['inode']) + ']',
         'EXACT_USER_NAMESPACE_DEVICE_INODE_REQUIRED')
    return copy.deepcopy(value)


def namespace_fact(fd, kind=USER, name='user'):
    need(type(fd) is int and fd >= 3 and not os.get_inheritable(fd),
         'PRIVATE_HELD_NAMESPACE_DESCRIPTOR_REQUIRED')
    info = os.fstat(fd)
    need(fcntl.ioctl(fd, NS_GET_NSTYPE) == kind and info.st_dev > 0 and info.st_ino > 0,
         'ACTUAL_KERNEL_NAMESPACE_TYPE_REQUIRED')
    return {'link': name + ':[' + str(info.st_ino) + ']',
            'device': info.st_dev, 'inode': info.st_ino}


def map_row(raw):
    """Parse one real kernel map, retaining its exact bytes for later guards."""
    need(type(raw) is bytes and 0 < len(raw) <= 8192,
         'BOUNDED_KERNEL_ID_MAP_REQUIRED')
    match = re.fullmatch(rb'[ \t]*([0-9]{1,10})[ \t]+([0-9]{1,10})[ \t]+'
                         rb'([0-9]{1,10})[ \t]*\n', raw)
    need(match is not None, 'ONE_COMPLETE_KERNEL_ID_MAP_REQUIRED')
    inside, outside, count = (int(part) for part in match.groups())
    need(inside == 0 and 100000 <= count <= 0xffffffff
         and 0 <= outside <= 0xffffffff and outside + count <= 0x100000000,
         'COMPLETE_ANDROID_USER_ZERO_MAP_REQUIRED')
    return {'inside': inside, 'outside': outside, 'count': count,
            'raw': raw.decode('ascii'), 'sha256': hashlib.sha256(raw).hexdigest()}


def validate_map(value):
    need(type(value) is dict and set(value) == {'inside', 'outside', 'count', 'raw', 'sha256'}
         and type(value['raw']) is str and len(value['raw']) <= 8192,
         'EXACT_OBSERVED_ID_MAP_REQUIRED')
    try:
        actual = map_row(value['raw'].encode('ascii'))
    except UnicodeError as error:
        raise RuntimeError('ASCII_KERNEL_ID_MAP_REQUIRED') from error
    need(value == actual and all(type(value[key]) is int for key in ('inside', 'outside', 'count')),
         'OBSERVED_ID_MAP_FIELDS_OR_HASH_CHANGED')
    return actual


def mapped_id(value, guest):
    value = validate_map(value)
    need(integer(guest, 0, 99999) and guest < value['count'],
         'ANDROID_USER_ZERO_ID_OUTSIDE_ACTUAL_MAP')
    return value['outside'] + guest


def validate_observation(value, owner_namespace, init_identity, boot_id):
    """Validate facts only. This function cannot create a live held lease."""
    need(type(value) is dict and set(value) == {
        'schema', 'boot_id', 'init', 'user_namespace', 'parent_user_namespace',
        'uid_map', 'gid_map', 'root_uids', 'root_gids', 'owned_entry_namespaces'},
        'EXACT_HELD_MAIN_USER_NAMESPACE_OBSERVATION_REQUIRED')
    need(value['schema'] == SCHEMA and value['boot_id'] == boot_id
         and type(boot_id) is str
         and re.fullmatch('[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', boot_id),
         'SAME_MAIN_BOOT_REQUIRED')
    wanted = {key: init_identity[key] for key in
              ('host_pid', 'parent_host_pid', 'start_ticks', 'namespace_pids')}
    need(value['init'] == wanted and type(value['init']) is dict
         and all(integer(wanted[key], 1, 2**63-1) for key in
                 ('host_pid', 'parent_host_pid', 'start_ticks'))
         and type(wanted['namespace_pids']) is list and len(wanted['namespace_pids']) >= 2
         and all(integer(pid, 1, 2**31-1) for pid in wanted['namespace_pids'])
         and wanted['namespace_pids'][0] == wanted['host_pid']
         and wanted['namespace_pids'][-1] == 1,
         'EXACT_HELD_ANDROID_INIT_EPOCH_REQUIRED')
    owner = namespace_pin(owner_namespace)
    need(namespace_pin(value['user_namespace']) == owner,
         'MAIN_USER_NAMESPACE_DIFFERS_FROM_NATIVE_OWNER')
    parent = namespace_pin(value['parent_user_namespace'])
    need(parent != owner, 'ANDROID_USER_NAMESPACE_MUST_BE_CHILD_OF_HOST')
    uid, gid = validate_map(value['uid_map']), validate_map(value['gid_map'])
    need(uid['outside'] > 0 and gid['outside'] > 0,
         'MAPPED_ANDROID_ROOT_MUST_DIFFER_FROM_HOST_ROOT')
    root_uids, root_gids = [mapped_id(uid, 0)] * 4, [mapped_id(gid, 0)] * 4
    need(value['root_uids'] == init_identity['uids'] == root_uids
         and value['root_gids'] == root_gids
         and all(type(x) is int for x in value['root_uids'] + value['root_gids']),
         'SAME_MAIN_LIVE_ROOT_UID_GID_AND_MAP_REQUIRED')
    owned = value['owned_entry_namespaces']
    need(type(owned) is dict and set(owned) == set(NS_TYPES),
         'ALL_SIX_HELD_ENTRY_NAMESPACE_OWNERS_REQUIRED')
    for name, item in owned.items():
        need(type(item) is dict and set(item) == {'namespace', 'user_namespace'}
             and type(item['namespace']) is dict
             and set(item['namespace']) == {'link', 'device', 'inode'}
             and integer(item['namespace']['device'], 1, 2**64-1)
             and integer(item['namespace']['inode'], 1, 2**64-1)
             and item['namespace']['link'] == name + ':[' + str(item['namespace']['inode']) + ']'
             and namespace_pin(item['user_namespace']) == owner,
             'ENTRY_NAMESPACE_NOT_OWNED_BY_SAME_MAIN_USER_NAMESPACE')
        if name in ('pid', 'mnt'):
            need(item['namespace']['link'] == init_identity['namespaces'][name],
                 'HELD_ENTRY_NAMESPACE_DIFFERS_FROM_MAIN_EPOCH')
    return copy.deepcopy(value)


def validate_role(value, main, identity, role, host_user_namespace):
    """Apply explicit host/Android roles; identical maps never replace identity."""
    need(type(value) is dict and set(value) == {'user_namespace', 'uid_map', 'gid_map', 'uids', 'gids'},
         'EXACT_ROLE_USER_NAMESPACE_FACTS_REQUIRED')
    observed = namespace_pin(value['user_namespace'])
    if role in ANDROID_IDS:
        uid, gid = ANDROID_IDS[role]
        need(observed == main['user_namespace'], 'ANDROID_ROLE_FOREIGN_USER_NAMESPACE')
        need(value['uid_map'] == main['uid_map'] and value['gid_map'] == main['gid_map'],
             'ANDROID_ROLE_ID_MAP_DIFFERS_FROM_MAIN')
        need(value['uids'] == identity['uids'] == [mapped_id(main['uid_map'], uid)] * 4
             and value['gids'] == [mapped_id(main['gid_map'], gid)] * 4,
             'ANDROID_ROLE_MAPPED_UID_GID_DIFFERS')
    else:
        need(role in HOST_IDS, 'EXPLICIT_CURRENT_HOST_ROLE_REQUIRED')
        need(observed == namespace_pin(host_user_namespace), 'HOST_ROLE_LEFT_HOST_USER_NAMESPACE')
        need(value['uids'] == identity['uids'] == [HOST_IDS[role]] * 4
             and all(type(x) is int for x in value['uids'])
             and type(value['gids']) is list and len(value['gids']) == 4
             and all(integer(x) for x in value['gids']), 'HOST_ROLE_CREDENTIALS_CHANGED')
        need(all(type(value[key]) is str and 0 < len(value[key]) <= 8192
                 and re.fullmatch(r'[0-9 \t\n]+', value[key])
                 for key in ('uid_map', 'gid_map')), 'ACTUAL_HOST_ID_MAP_OBSERVATIONS_REQUIRED')
        # Root/UID policy and executable/ancestry checks remain the caller's
        # existing explicit host-role rules. Do not treat an unknown role as
        # Android because its numeric map happens to resemble Main's map.
    return copy.deepcopy(value)


class HeldMainUserNamespace:
    """Own read-only duplicates of one already-authenticated Main's handles."""
    def __init__(self, init_identity, handles, owner_namespace, host_namespace_fd,
                 boot_id, main_guard, seconds=3):
        need(type(handles) is dict and set(handles) >= {'proc', 'pidfd', 'namespaces'}
             and set(handles['namespaces']) == {'user', *NS_TYPES},
             'FULL_ALREADY_HELD_MAIN_DESCRIPTOR_SET_REQUIRED')
        need(callable(main_guard) and type(seconds) in (int, float) and 0 < seconds <= 3,
             'BOUNDED_ORIGINAL_MAIN_GUARD_REQUIRED')
        self._creator = os.getpid()
        self._identity = copy.deepcopy(init_identity)
        self._owner = namespace_pin(owner_namespace)
        self._boot_id = boot_id
        self._main_guard = main_guard
        self._seconds = seconds
        self._fds = []
        self._acquired = 0
        self._close_attempts = 0
        self._closed_count = 0
        self._close_errors = []
        self._closed = False
        self._value = None
        try:
            self._main_guard()
            self._proc = self._dup(handles['proc'])
            self._pidfd = self._dup(handles['pidfd'])
            self._host_userns = self._dup(host_namespace_fd)
            self._namespaces = {name: self._dup(fd) for name, fd in handles['namespaces'].items()}
            info = os.fstat(self._proc)
            need(stat.S_ISDIR(info.st_mode), 'HELD_MAIN_PROC_DIRECTORY_REQUIRED')
            self._proc_node = (info.st_dev, info.st_ino)
            self._host_pin = namespace_fact(self._host_userns)
            self._value = self._observe()
            self.guard()
        except BaseException:
            self.close()
            raise

    def _own(self, fd):
        self._fds.append(fd)
        self._acquired += 1
        need(fd >= 3 and not os.get_inheritable(fd), 'PRIVATE_READ_ONLY_MAIN_DESCRIPTOR_REQUIRED')
        return fd

    def _dup(self, fd):
        need(type(fd) is int and fd >= 3, 'ORIGINAL_HELD_MAIN_DESCRIPTOR_REQUIRED')
        return self._own(os.dup(fd))

    def _live(self):
        need(not self._closed and self._creator == os.getpid(),
             'HELD_MAIN_NAMESPACE_LEASE_CLOSED_OR_TRANSFERRED')
        poller = select.poll()
        poller.register(self._pidfd, select.POLLIN | select.POLLHUP | select.POLLERR)
        need(not poller.poll(0), 'ORIGINAL_MAIN_PIDFD_EXITED')
        node = os.fstat(self._proc)
        need((node.st_dev, node.st_ino) == self._proc_node, 'ORIGINAL_MAIN_PROC_HANDLE_CHANGED')

    @staticmethod
    def _read(proc, name, limit, deadline):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=proc)
        try:
            chunks, count = [], 0
            while True:
                need(time.monotonic() <= deadline, 'MAIN_NAMESPACE_OBSERVATION_DEADLINE')
                part = os.read(fd, min(65536, limit + 1 - count))
                if not part:
                    return b''.join(chunks)
                count += len(part)
                need(count <= limit, 'MAIN_NAMESPACE_OBSERVATION_BOUND')
                chunks.append(part)
        finally:
            os.close(fd)

    @classmethod
    def _credentials(cls, proc, deadline):
        raw = cls._read(proc, 'status', 65536, deadline)
        values = {}
        for key in ('Uid', 'Gid', 'NSpid'):
            matches = re.findall(rb'^' + key.encode() + rb':[ \t]+([0-9 \t]+)$', raw, re.M)
            need(len(matches) == 1, 'ONE_COMPLETE_LIVE_PROCESS_CREDENTIAL_ROW_REQUIRED')
            values[key] = [int(item) for item in matches[0].split()]
        need(len(values['Uid']) == len(values['Gid']) == 4,
             'FOUR_LIVE_UID_AND_GID_VALUES_REQUIRED')
        return values

    @classmethod
    def _process_fact(cls, proc, deadline):
        raw = cls._read(proc, 'stat', 8192, deadline).decode('utf-8', 'strict')
        parts = raw[raw.rindex(')') + 2:].split()
        need(len(parts) >= 20 and parts[0] not in ('Z', 'X'), 'LIVE_HELD_MAIN_PROCESS_REQUIRED')
        return int(raw.split('(', 1)[0]), int(parts[1]), int(parts[19])

    def _observe(self):
        self._live()
        self._main_guard()
        deadline = time.monotonic() + self._seconds
        first = self._process_fact(self._proc, deadline)
        expected = tuple(self._identity[key] for key in ('host_pid', 'parent_host_pid', 'start_ticks'))
        need(first == expected, 'ACTUAL_HELD_MAIN_PROCESS_EPOCH_CHANGED')
        need(self._read_boot_id() == self._boot_id, 'ACTUAL_MAIN_BOOT_CHANGED')
        host = namespace_fact(self._host_userns)
        need(host == self._host_pin, 'HELD_HOST_USER_NAMESPACE_CHANGED')
        current_host = os.open('/proc/self/ns/user', os.O_RDONLY | os.O_CLOEXEC)
        try:
            need(namespace_fact(current_host) == host, 'CONTROLLER_LEFT_ORIGINAL_HOST_USER_NAMESPACE')
        finally:
            os.close(current_host)
        user = namespace_fact(self._namespaces['user'])
        need(user == self._owner, 'HELD_MAIN_USER_NAMESPACE_DIFFERS_FROM_NATIVE_OWNER')
        named = os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=self._proc)
        try:
            need(namespace_fact(named) == user, 'ACTUAL_MAIN_CHANGED_USER_NAMESPACE')
        finally:
            os.close(named)
        parent = fcntl.ioctl(self._namespaces['user'], NS_GET_PARENT)
        try:
            parent_pin = namespace_fact(parent)
            need(parent_pin == host, 'MAIN_USER_NAMESPACE_NOT_OWNED_BY_ORIGINAL_HOST_NAMESPACE')
        finally:
            os.close(parent)
        owned = {}
        for name, kind in NS_TYPES.items():
            fixed = self._namespaces[name]
            fact = namespace_fact(fixed, kind, name)
            named = os.open('ns/' + name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=self._proc)
            try:
                need(namespace_fact(named, kind, name) == fact, 'MAIN_ENTRY_NAMESPACE_CHANGED')
            finally:
                os.close(named)
            owner = fcntl.ioctl(fixed, NS_GET_USERNS)
            try:
                owner_fact = namespace_fact(owner)
                need(owner_fact == user, 'ENTRY_NAMESPACE_OWNED_BY_FOREIGN_USER_NAMESPACE')
                owned[name] = {'namespace': fact, 'user_namespace': owner_fact}
            finally:
                os.close(owner)
        uid_raw = self._read(self._proc, 'uid_map', 8192, deadline)
        gid_raw = self._read(self._proc, 'gid_map', 8192, deadline)
        credentials = self._credentials(self._proc, deadline)
        result = {'schema': SCHEMA, 'boot_id': self._boot_id,
                  'init': {key: self._identity[key] for key in
                           ('host_pid', 'parent_host_pid', 'start_ticks', 'namespace_pids')},
                  'user_namespace': user, 'parent_user_namespace': parent_pin,
                  'uid_map': map_row(uid_raw), 'gid_map': map_row(gid_raw),
                  'root_uids': credentials['Uid'], 'root_gids': credentials['Gid'],
                  'owned_entry_namespaces': owned}
        need(credentials['NSpid'] == self._identity['namespace_pids'],
             'ACTUAL_MAIN_NAMESPACE_PID_CHANGED')
        validate_observation(result, self._owner, self._identity, self._boot_id)
        need(self._read(self._proc, 'uid_map', 8192, deadline) == uid_raw
             and self._read(self._proc, 'gid_map', 8192, deadline) == gid_raw
             and self._credentials(self._proc, deadline) == credentials
             and self._process_fact(self._proc, deadline) == first,
             'MAIN_NAMESPACE_MAP_OR_ROOT_IDENTITY_CHANGED_DURING_READ')
        named = os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=self._proc)
        try:
            need(namespace_fact(named) == user, 'MAIN_USER_NAMESPACE_CHANGED_AFTER_READ')
        finally:
            os.close(named)
        self._live()
        self._main_guard()
        return result

    @staticmethod
    def _read_boot_id():
        fd = os.open('/proc/sys/kernel/random/boot_id', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            raw = os.read(fd, 129)
            need(len(raw) <= 128, 'BOUNDED_BOOT_ID_REQUIRED')
            return raw.decode('ascii').strip()
        finally:
            os.close(fd)

    def guard(self):
        value = self._observe()
        need(value == self._value, 'SAME_MAIN_USER_NAMESPACE_OR_MAP_CHANGED')
        return copy.deepcopy(value)

    def mapped_owner(self, guest_uid, guest_gid=None):
        value = self.guard()
        guest_gid = guest_uid if guest_gid is None else guest_gid
        return mapped_id(value['uid_map'], guest_uid), mapped_id(value['gid_map'], guest_gid)

    def observe_role(self, handles, identity, role):
        main = self.guard()
        deadline = time.monotonic() + self._seconds
        proc, pidfd = handles['proc'], handles['pidfd']
        poller = select.poll()
        poller.register(pidfd, select.POLLIN | select.POLLHUP | select.POLLERR)
        need(not poller.poll(0), 'ROLE_PIDFD_EXITED')
        first = self._process_fact(proc, deadline)
        need(first == tuple(identity[key] for key in ('host_pid', 'parent_host_pid', 'start_ticks')),
             'ROLE_HELD_PROCESS_EPOCH_CHANGED')
        held = namespace_fact(handles['namespaces']['user'])
        named = os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc)
        try:
            need(namespace_fact(named) == held, 'ROLE_CHANGED_USER_NAMESPACE')
        finally:
            os.close(named)
        uid_raw = self._read(proc, 'uid_map', 8192, deadline)
        gid_raw = self._read(proc, 'gid_map', 8192, deadline)
        credentials = self._credentials(proc, deadline)
        # Host namespace maps can span all IDs; retain exact bytes. Only the
        # Android role parser demands the single Android user-zero range.
        value = {'user_namespace': held, 'uid_map': map_row(uid_raw) if role in ANDROID_IDS else uid_raw.decode('ascii'),
                 'gid_map': map_row(gid_raw) if role in ANDROID_IDS else gid_raw.decode('ascii'),
                 'uids': credentials['Uid'], 'gids': credentials['Gid']}
        validate_role(value, main, identity, role, self._host_pin)
        need(credentials['NSpid'] == identity['namespace_pids']
             and self._credentials(proc, deadline) == credentials
             and self._read(proc, 'uid_map', 8192, deadline) == uid_raw
             and self._read(proc, 'gid_map', 8192, deadline) == gid_raw
             and self._process_fact(proc, deadline) == first and not poller.poll(0),
             'ROLE_NAMESPACE_MAP_OR_CREDENTIAL_CHANGED_DURING_READ')
        named = os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc)
        try:
            need(namespace_fact(named) == held, 'ROLE_USER_NAMESPACE_CHANGED_AFTER_READ')
        finally:
            os.close(named)
        need(self.guard() == main, 'MAIN_CHANGED_DURING_ROLE_NAMESPACE_OBSERVATION')
        return value

    def close(self):
        if self._closed:
            return self.summary()
        self._closed = True
        errors = []
        for fd in reversed(self._fds):
            self._close_attempts += 1
            try:
                os.close(fd)
                self._closed_count += 1
            except OSError as error:
                errors.append(error)
                self._close_errors.append({'type': type(error).__name__, 'errno': error.errno})
        self._fds.clear()
        if errors:
            raise RuntimeError('HELD_MAIN_USER_NAMESPACE_DESCRIPTOR_CLOSE_FAILED') from errors[0]
        return self.summary()

    def summary(self):
        return {'scope': 'held_main_user_namespace_descriptors', 'acquired': self._acquired,
                'close_attempts': self._close_attempts, 'closed': self._closed_count,
                'remaining': len(self._fds), 'errors': copy.deepcopy(self._close_errors)}

    def __enter__(self):
        self.guard()
        return self

    def __exit__(self, kind, error, traceback):
        self.close()
