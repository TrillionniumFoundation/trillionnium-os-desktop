"""One fresh-generation, four-key Android property visibility observation.

The unchanged C accessor performs root reads before a permanent UID1069 drop.
Its bionic property cache is root-warmed. This is not an actual LMKD process or
a cold-cache experiment. Only the one observer child enters owned namespaces;
the actor's namespaces and the original NORMAL Stop ordering are unchanged.
"""
import array
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import resource
import select
import signal
import socket
import stat
import struct
import time

SCHEMA = 1
LIFETIME_NS = 2_000_000_000
PACKET_BYTES = 8192
STDERR_BYTES = 16384
MAP_BYTES = 131072
LIBRARY_BYTES = 16 * 1024 * 1024
MAX_SELF_FDS = 4096
ROOT_TMPFS = 0x01021994
KEYS = ('ro.build.version.sdk', 'ro.build.version.sdk_full',
        'ro.system.build.version.sdk', 'ro.system.build.version.sdk_full')
LIBRARIES = ('/apex/com.android.runtime/lib64/bionic/libc.so',
             '/apex/com.android.runtime/bin/linker64',
             '/apex/com.android.runtime/lib64/bionic/libdl.so')
NAMES = ('pid', 'pid_for_children', 'mnt', 'cgroup', 'user', 'net',
         'ipc', 'uts', 'time', 'time_for_children')
JOIN_NAMES = ('mnt', 'net', 'ipc', 'uts', 'cgroup')
EXPECTED_BUILD = '5cc813715a261701cad3be931b9e53145229dec7c803d828a1097e4fe4ad166b'
EXPECTED_SOURCE = '481f4ca861403f493e3192c8086b1b6a9c0e70312431b9d0354c664baf9ce7ba'
HELPER_BYTES = 22688
HELPER_SHA256 = 'd58b2492120aed1c96e0a0006ba9d61edd04fbc047e5faf1c13def572aba4036'
KNOWN_BUILD_IDS = {'libc.so': '931dd708b3792c0f68e76a20c7b8b3dc',
                   'linker64': '1116b81ad54d36f9423b714980cdb704'}
CREDENTIAL_FIELDS = {'uids', 'gids', 'group_count', 'effective', 'permitted',
                     'inheritable', 'bounding', 'ambient', 'no_new_privileges'}
FAILURE_STAGES = {'root_credentials', 'bionic_ready', 'source_authorization',
    'root_read', 'root_credentials_changed', 'root_packet', 'irreversible_drop',
    'uid1069_read', 'uid1069_credentials_changed', 'uid1069_packet',
    'post_observation_ack'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def integer(value, lower=0, upper=(1 << 63) - 1):
    return type(value) is int and lower <= value <= upper


def hex_string(value, length, nonzero=False):
    return (isinstance(value, str) and len(value) == length and
            set(value) <= set('0123456789abcdef') and
            (not nonzero or value != '0' * length))


def identity(fd):
    s = os.fstat(fd)
    return {'device': s.st_dev, 'inode': s.st_ino}


def metadata(fd):
    s = os.fstat(fd)
    return {'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode,
            'uid': s.st_uid, 'gid': s.st_gid, 'nlink': s.st_nlink,
            'bytes': s.st_size, 'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns}


def filesystem_type(fd):
    library = ctypes.CDLL(None, use_errno=True)
    library.fstatfs.argtypes = (ctypes.c_int, ctypes.c_void_p)
    library.fstatfs.restype = ctypes.c_int
    output = ctypes.create_string_buffer(256)
    if library.fstatfs(fd, output):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), 'held owned filesystem')
    return ctypes.c_long.from_buffer(output).value


def strict_json(raw):
    need(type(raw) is bytes and 0 < len(raw) <= PACKET_BYTES, 'SDK_PACKET_BOUND')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'SDK_DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid(value):
        raise RuntimeError('SDK_NONINTEGER_JSON_NUMBER')
    value = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs,
                       parse_float=invalid, parse_constant=invalid)
    need(type(value) is dict, 'SDK_PACKET_OBJECT')
    return value


def credentials(value, lower=False):
    need(type(value) is dict and set(value) == CREDENTIAL_FIELDS, 'SDK_CREDENTIAL_FIELDS')
    for key in ('uids', 'gids'):
        need(type(value[key]) is list and len(value[key]) == 3 and
             all(integer(x, 0, (1 << 32) - 1) for x in value[key]), 'SDK_CREDENTIAL_IDS')
        need(value[key] == [1069 if lower else 0] * 3, 'SDK_CREDENTIAL_ID_VALUE')
    need(integer(value['group_count'], 0, 32) and
         integer(value['no_new_privileges'], 0, 1), 'SDK_CREDENTIAL_COUNTS')
    for key in ('effective', 'permitted', 'inheritable', 'bounding', 'ambient'):
        need(hex_string(value[key], 16), 'SDK_CAPABILITY_ENCODING')
        if lower:
            need(value[key] == '0' * 16, 'SDK_RESIDUAL_CAPABILITY')
    if lower:
        need(value['group_count'] == 0 and value['no_new_privileges'] == 1,
             'SDK_LOWER_GROUPS_OR_NNP')
    return value


def ready_record(value, nonce, pid):
    expected = {'schema', 'phase', 'nonce', 'pid', 'credentials', 'getter_address',
        'getter_library_base', 'libraries', 'lifetime_ms', 'same_process_root_warmed_cache',
        'actual_LMKD_capability_simulation'}
    need(set(value) == expected and value['schema'] == SCHEMA and
         type(value['schema']) is int and value['phase'] == 'ready' and
         value['nonce'] == nonce and value['pid'] == pid and type(value['pid']) is int,
         'SDK_READY_IDENTITY')
    credentials(value['credentials'])
    need(value['libraries'] == list(LIBRARIES) and
         type(value['lifetime_ms']) is int and value['lifetime_ms'] == 2000 and
         value['same_process_root_warmed_cache'] is True and
         value['actual_LMKD_capability_simulation'] is False, 'SDK_READY_SCOPE')
    for key in ('getter_address', 'getter_library_base'):
        item = value[key]
        need(isinstance(item, str) and 1 <= len(item) <= 16 and
             set(item) <= set('0123456789abcdef') and int(item, 16) > 0,
             'SDK_GETTER_ADDRESS')
    return value


def values_record(value, phase, nonce, earliest, deadline):
    need(set(value) == {'schema', 'phase', 'nonce', 'credentials', 'before_ns',
                        'after_ns', 'values'} and type(value['schema']) is int and
         value['schema'] == SCHEMA and value['phase'] == phase and value['nonce'] == nonce,
         'SDK_VALUES_IDENTITY')
    credentials(value['credentials'], phase == 'uid1069')
    need(integer(value['before_ns']) and integer(value['after_ns']) and
         earliest <= value['before_ns'] <= value['after_ns'] < deadline,
         'SDK_VALUES_DEADLINE')
    need(type(value['values']) is list and len(value['values']) == 4, 'SDK_VALUES_COUNT')
    for key, row in zip(KEYS, value['values']):
        need(type(row) is dict and set(row) == {'key', 'return', 'errno_observation', 'value_hex'} and
             row['key'] == key and integer(row['return'], 0, 91) and
             integer(row['errno_observation'], 0, (1 << 31) - 1), 'SDK_VALUE_SCHEMA')
        n = row['return']; text = row['value_hex']
        need(hex_string(text, n * 2) and b'\0' not in bytes.fromhex(text),
             'SDK_VALUE_ENCODING')
    return value


def failure_record(value, nonce):
    need(set(value) == {'schema', 'phase', 'nonce', 'stage', 'error_code',
                        'errno_observation', 'completed'} and
         type(value['schema']) is int and value['schema'] == SCHEMA and
         value['phase'] == 'failure' and value['nonce'] == nonce and
         value['stage'] in FAILURE_STAGES and
         integer(value['error_code'], -(1 << 31), (1 << 31) - 1) and
         integer(value['errno_observation'], 0, (1 << 31) - 1) and
         integer(value['completed'], 0, 9), 'SDK_FAILURE_SCHEMA')
    return value


def elf_summary(raw, getter=False):
    """Bounded ELF64 metadata only; no code execution or guessed symbol offsets."""
    need(type(raw) is bytes and 64 <= len(raw) <= LIBRARY_BYTES, 'SDK_ELF_BOUND')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    ident, kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, shstr = header
    need(ident[:7] == b'\x7fELF\x02\x01\x01' and kind in (2, 3) and machine == 62 and
         version == 1 and ehsize == 64 and phsize == 56 and 1 <= phnum <= 256 and
         phoff <= len(raw) and phnum * phsize <= len(raw) - phoff, 'SDK_ELF_HEADER')
    loads, notes, interpreter = [], [], None
    def region(offset, size):
        need(integer(offset) and integer(size) and offset <= len(raw) and
             size <= len(raw) - offset, 'SDK_ELF_RANGE')
        return raw[offset:offset + size]
    for index in range(phnum):
        ptype, pflags, offset, virtual, physical, size, memory, align = struct.unpack_from(
            '<IIQQQQQQ', raw, phoff + index * phsize)
        region(offset, size)
        if ptype == 1:
            need(size <= memory and memory > 0 and virtual + memory < (1 << 64), 'SDK_ELF_LOAD')
            loads.append({'offset': offset, 'vaddr': virtual, 'filesz': size,
                          'memsz': memory, 'flags': pflags})
        elif ptype == 3:
            text = region(offset, size)
            need(interpreter is None and 1 < len(text) <= 256 and text[-1] == 0 and
                 b'\0' not in text[:-1], 'SDK_ELF_INTERPRETER')
            interpreter = text[:-1].decode('ascii', 'strict')
        elif ptype == 4:
            end = offset + size
            while offset < end:
                need(end - offset >= 12, 'SDK_ELF_NOTE_HEADER')
                namesz, descsz, ntype = struct.unpack_from('<III', raw, offset); offset += 12
                name_end = offset + ((namesz + 3) & ~3)
                desc_end = name_end + ((descsz + 3) & ~3)
                need(name_end <= end and desc_end <= end, 'SDK_ELF_NOTE_RANGE')
                name = raw[offset:offset + namesz]
                description = raw[name_end:name_end + descsz]
                if name == b'GNU\0' and ntype == 3:
                    need(4 <= len(description) <= 64, 'SDK_ELF_BUILD_ID')
                    notes.append(description.hex())
                offset = desc_end
    need(loads and len(set(notes)) == 1, 'SDK_ELF_BUILD_ID_UNIQUE')
    result = {'class': 64, 'machine': machine, 'type': kind, 'build_id': notes[0],
              'interpreter': interpreter, 'loads': loads}
    if getter:
        need(shsize == 64 and 1 <= shnum <= 4096 and shoff <= len(raw) and
             shnum * shsize <= len(raw) - shoff, 'SDK_ELF_SECTIONS')
        sections = [struct.unpack_from('<IIQQQQIIQQ', raw, shoff + i * shsize) for i in range(shnum)]
        matches = []
        for section in sections:
            if section[1] != 11:
                continue
            off, size, link, entsize = section[4], section[5], section[6], section[9]
            need(entsize == 24 and size % 24 == 0 and size // 24 <= 65536 and
                 0 <= link < len(sections) and sections[link][1] == 3, 'SDK_ELF_DYNSYM')
            region(off, size)
            strings = region(sections[link][4], sections[link][5])
            for i in range(size // 24):
                name, info, other, index, address, length = struct.unpack_from('<IBBHQQ', raw, off + i * 24)
                need(name < len(strings), 'SDK_ELF_SYMBOL_NAME')
                end = strings.find(b'\0', name)
                need(end >= name, 'SDK_ELF_SYMBOL_TERMINATOR')
                if strings[name:end] == b'__system_property_get':
                    need(index != 0 and info & 15 == 2 and length > 0, 'SDK_GETTER_DEFINED_FUNC')
                    matches.append({'value': address, 'size': length, 'binding': info >> 4,
                                    'visibility': other & 3})
        need(len(matches) == 1, 'SDK_GETTER_UNIQUE')
        symbol = matches[0]
        need(any(x['flags'] & 1 and x['vaddr'] <= symbol['value'] and
                 symbol['value'] + symbol['size'] <= x['vaddr'] + x['filesz'] for x in loads),
             'SDK_GETTER_EXECUTABLE_LOAD')
        result['getter'] = symbol
    return result


def parse_maps(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAP_BYTES, 'SDK_MAPS_BOUND')
    rows = []
    for line in raw.decode('utf-8', 'strict').splitlines():
        fields = line.split(None, 5)
        need(5 <= len(fields) <= 6, 'SDK_MAPS_FIELDS')
        start, end = fields[0].split('-', 1); major, minor = fields[3].split(':', 1)
        row = {'start': int(start, 16), 'end': int(end, 16), 'permissions': fields[1],
               'offset': int(fields[2], 16), 'device_major': int(major, 16),
               'device_minor': int(minor, 16), 'inode': int(fields[4]),
               'path': fields[5] if len(fields) == 6 else ''}
        need(row['start'] < row['end'] and len(row['permissions']) == 4 and
             row['permissions'][0] in 'r-' and row['permissions'][1] in 'w-' and
             row['permissions'][2] in 'x-' and row['permissions'][3] in 'ps',
             'SDK_MAPS_ROW')
        rows.append(row)
        need(len(rows) <= 1024, 'SDK_MAPS_COUNT')
    return rows


def selected_maps(rows, meta):
    found = [row for row in rows if row['inode'] == meta['inode'] and
             row['device_major'] == os.major(meta['device']) and
             row['device_minor'] == os.minor(meta['device'])]
    need(found and any('x' in row['permissions'] for row in found) and
         all(not ('w' in row['permissions'] and 'x' in row['permissions']) and
             not row['path'].endswith(' (deleted)') for row in found), 'SDK_MAPPED_FILE')
    return found


def getter_mapping(ready, elf, rows):
    base, address = int(ready['getter_library_base'], 16), int(ready['getter_address'], 16)
    symbol = elf['getter']
    need(address == base + symbol['value'], 'SDK_GETTER_SYMBOL_ADDRESS')
    loads = [load for load in elf['loads'] if load['flags'] & 1 and
             load['vaddr'] <= symbol['value'] < load['vaddr'] + load['filesz']]
    need(len(loads) == 1, 'SDK_GETTER_LOAD_UNIQUE')
    file_offset = loads[0]['offset'] + symbol['value'] - loads[0]['vaddr']
    matches = [row for row in rows if 'x' in row['permissions'] and
               row['start'] <= address < row['end'] and
               row['offset'] + address - row['start'] == file_offset]
    need(len(matches) == 1, 'SDK_GETTER_CURRENT_MAPPING')
    return {'address': ready['getter_address'], 'library_base': ready['getter_library_base'],
            'symbol': symbol, 'mapping': matches[0]}


def arm_child_deadline(deadline):
    """Only the just-forked observer calls this; the actor's timer is unchanged.

    Linux interval timers survive execve; the frozen accessor has no timer or
    SIGALRM changes. Signal delivery still has scheduler latency, so accepted
    data and proof remain independently checked against the absolute host clock.
    """
    before = time.monotonic_ns()
    remaining_us = (deadline - before) // 1000
    need(0 < remaining_us <= LIFETIME_NS // 1000, 'SDK_CHILD_DEADLINE_BEFORE_EXEC')
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM})
    signal.setitimer(signal.ITIMER_REAL, remaining_us / 1_000_000, 0)
    after = verify_child_deadline(deadline)
    return {'before_ns': before, 'after_ns': after, 'requested_us': remaining_us}


def verify_child_deadline(deadline):
    need(signal.getsignal(signal.SIGALRM) == signal.SIG_DFL, 'SDK_CHILD_ALARM_NOT_DEFAULT')
    blocked = signal.pthread_sigmask(signal.SIG_BLOCK, set())  # Empty set changes no mask.
    need(signal.SIGALRM not in blocked, 'SDK_CHILD_ALARM_BLOCKED')
    current, interval = signal.getitimer(signal.ITIMER_REAL)
    after = time.monotonic_ns()
    need(0 < current <= LIFETIME_NS / 1_000_000_000 and interval == 0 and
         after < deadline, 'SDK_CHILD_DEADLINE_ARM_FAILED')
    return after

class Capture:
    def __init__(self, init, audit, plan, prepared, helper_fd, evidence, owned, outer_deadline):
        self.init, self.plan, self.prepared, self.owned = init, plan, prepared, owned
        self.evidence = evidence  # Borrowed; the original actor closes it.
        self.fds, self.sock, self.child_sock = {}, None, None
        self.pid = None
        self.child_reaped = False
        self.close_failed = False
        self.finished = False
        self.stderr = bytearray()
        self.stderr_eof = False
        self.phase = 'WAITING_READY'
        self.library_info = []
        self.root_value = None
        self.lower_value = None
        self.actor_pid = os.getpid()
        self.started = time.monotonic_ns()
        self.deadline = min(self.started + LIFETIME_NS, int(outer_deadline * 1_000_000_000))
        self.record = {'schema': 1, 'scope': 'one owned-generation four-key Android accessor',
            'generation_nonce': audit.get('nonce'), 'attempt_nonce': plan.get('attempt_nonce'),
            'state': 'INITIALIZING', 'first_error': None, 'secondary_errors': [],
            'started_monotonic_ns': self.started, 'deadline_monotonic_ns': self.deadline,
            'spawn_attempts': 0, 'child_started': False, 'child_reaped': False,
             'observation_limit_ms': 2000, 'observation_completed': False,
             'observation_closed_monotonic_ns': None,
             'retirement_started_monotonic_ns': None, 'retirement_deadline_monotonic_ns': None,
             'retirement_limit_ms': 1000, 'retirement_deadline_met': False,
             'fd_registration_events': 0, 'fd_close_records': [], 'channel_close_records': [],
            'namespace_changes_in_actor': False, 'PID_namespace_join_requested': False,
            'helper_PID_namespace_equals_init': False,
            'same_process_root_warmed_cache': True, 'actual_LMKD_capability_simulation': False,
            'cold_cache_observation': False, 'property_writes': False,
            'Main_actions': 0, 'source_qualified_before_reads': False,
            'protocol_packets': 0, 'start_token_attempts': 0, 'finish_token_attempts': 0,
            'finish_token_sent': False, 'wire_records': [], 'init_current_checks': [],
             'held_fds_closed': False,
            'property_visibility_qualified': False, 'original_Stop_delayed': False,
            'build_result_sha256': EXPECTED_BUILD, 'source_manifest_sha256': EXPECTED_SOURCE}
        try:
            self._check()
            need(self.deadline - self.started == LIFETIME_NS, 'SDK_ORIGINAL_WINDOW_TOO_SHORT')
            self._bind_helper(helper_fd)
            self._bind_init(audit)
            self._spawn()
        except BaseException as error:
            self._failure('initialization', error)
            self._abort_nonblocking()

    def _check(self):
        need(time.monotonic_ns() < self.deadline, 'SDK_SHARED_TWO_SECOND_DEADLINE')

    def _take(self, name, fd):
        if name in self.fds:
            primary = RuntimeError('SDK_DUPLICATE_FD_OWNER')
            try:
                os.close(fd)
            except BaseException as error:
                self.close_failed = True
                primary.add_note('new FD close failed: ' + repr(error)[:160])
            raise primary
        self.fds[name] = fd
        self.record['fd_registration_events'] += 1
        return fd

    def _close(self, name):
        fd = self.fds.pop(name, None)
        if fd is not None:
            row = {'name': name, 'close_attempted_once': True, 'closed': False}
            self.record['fd_close_records'].append(row)
            try:
                os.close(fd)
                row['closed'] = True
            except BaseException as error:
                self.close_failed = True
                row['error'] = repr(error)[:160]
                raise

    def _failure(self, stage, error):
        row = {'stage': stage, 'type': type(error).__name__,
               'error': repr(error)[:512], 'errno': getattr(error, 'errno', None),
               'notes': [str(note)[:160] for note in getattr(error, '__notes__', ())][:4]}
        if self.record['first_error'] is None:
            self.record['first_error'] = row
        elif len(self.record['secondary_errors']) < 12:
            self.record['secondary_errors'].append(row)
        self.record['state'] = 'FAILED'
        if self.record['observation_closed_monotonic_ns'] is None:
            self.record['observation_closed_monotonic_ns'] = time.monotonic_ns()

    def _retirement_check(self):
        need(time.monotonic_ns() < self.retirement_deadline, 'SDK_ONE_SECOND_RETIREMENT_DEADLINE')

    def _hash(self, fd, maximum, during_observation=True):
        before = metadata(fd)
        need(stat.S_ISREG(before['mode']) and 0 < before['bytes'] <= maximum, 'SDK_FILE_BOUND')
        raw = bytearray()
        while len(raw) < before['bytes']:
            if during_observation:
                self._check()
            else:
                self._retirement_check()
            part = os.pread(fd, min(65536, before['bytes'] - len(raw)), len(raw))
            need(part, 'SDK_FILE_TRUNCATED')
            raw.extend(part)
        need(os.pread(fd, 1, len(raw)) == b'' and metadata(fd) == before, 'SDK_FILE_CHANGED')
        return bytes(raw), {'metadata': before, 'sha256': hashlib.sha256(raw).hexdigest(),
                            'bytes': len(raw)}

    def _borrowed_init_current(self):
        checked_before = time.monotonic_ns()
        self._check()
        self.init.live()
        now = self.init.snapshot()
        for key in ('process', 'namespaces', 'executable', 'executable_sha256'):
            need(now[key] == self.init_bound[key], 'SDK_INIT_HELD_IDENTITY_CHANGED')
        for name in NAMES:
            st = os.stat('ns/' + name, dir_fd=self.init.proc)
            need({'device': st.st_dev, 'inode': st.st_ino} ==
                 identity(self.fds['init_ns_' + name]), 'SDK_INIT_NAMED_NAMESPACE_CHANGED')
        st = os.stat('root', dir_fd=self.init.proc)
        need({'device': st.st_dev, 'inode': st.st_ino} == identity(self.fds['root']),
             'SDK_INIT_NAMED_ROOT_CHANGED')
        need(identity(self.fds['domain']) == self.domain_identity, 'SDK_DOMAIN_CHANGED')
        fields = dict(line.split(':', 1) for line in
            self.owned.bounded(self.init.proc, 'status', 65536).decode('ascii').splitlines() if ':' in line)
        need(int(fields['Pid']) == self.init_bound['process']['pid'] and
             [int(x) for x in fields['Uid'].split()] == [0] * 4 and
             [int(x) for x in fields['Gid'].split()] == [0] * 4, 'SDK_INIT_CURRENT_IDS')
        current_exe = os.stat('exe', dir_fd=self.init.proc)
        need(metadata(self.init.exe) == self.init_exe_metadata and
             (current_exe.st_dev, current_exe.st_ino) ==
             (self.init_exe_metadata['device'], self.init_exe_metadata['inode']),
             'SDK_INIT_CURRENT_EXECUTABLE_CHANGED')
        member = self.owned.bounded(self.init.proc, 'cgroup', 4096).decode('ascii').splitlines()
        need(len(member) == 1 and member[0].startswith('0::') and
             (member[0][3:] == self.domain_relative or
              member[0][3:].startswith(self.domain_relative + '/')), 'SDK_INIT_CURRENT_DOMAIN')
        named_domain = self._open_directory(self.domain_path, 'domain_recheck')
        primary = None
        try:
            need(identity(named_domain) == self.domain_identity, 'SDK_DOMAIN_NAMED_CHANGED')
        except BaseException as error:
            primary = error; raise
        finally:
            try: self._close('domain_recheck')
            except BaseException as error:
                if primary is None: raise
                primary.add_note('domain name close: ' + repr(error)[:160])
        self.init.live()
        self._check()
        self.record['init_current_checks'].append({'before_ns': checked_before,
            'after_ns': time.monotonic_ns(), 'held_and_named_namespaces_equal': True,
            'held_and_named_root_equal': True, 'current_uid_gid_root': True,
            'current_executable_matches_held': True, 'named_domain_equal': True,
            'current_domain_membership_matches': True})

    def _open_directory(self, path, name):
        need(isinstance(path, str) and path.startswith('/') and
             all(part not in ('', '.', '..') for part in path.split('/')[1:]),
             'SDK_DIRECTORY_PATH')
        current = self._take(name + '_walk', os.open('/',
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC))
        primary = None
        try:
            for part in path.split('/')[1:]:
                self._check()
                child = self._take(name + '_next', os.open(part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=current))
                self._close(name + '_walk')
                self.fds[name + '_walk'] = self.fds.pop(name + '_next'); current = child
            return self._take(name, self.fds.pop(name + '_walk'))
        except BaseException as error:
            primary = error; raise
        finally:
            failures = []
            for suffix in ('_next', '_walk'):
                try: self._close(name + suffix)
                except BaseException as error: failures.append(error)
            if failures:
                if primary is None: raise failures[0]
                for error in failures: primary.add_note('directory walk close: ' + repr(error)[:160])

    def _bind_helper(self, original_fd):
        expected = self.plan.get('property_visibility')
        need(type(expected) is dict and expected == {
            'schema': 1, 'build_result_sha256': EXPECTED_BUILD,
            'source_manifest_sha256': EXPECTED_SOURCE,
            'helper_bytes': HELPER_BYTES, 'helper_sha256': HELPER_SHA256,
            'lifetime_ms': 2000, 'root_warmed_cache': True,
            'actual_LMKD_capability_simulation': False}, 'SDK_FIXED_PLAN_BINDING')
        copied = self.prepared['copied_artifacts']['sdk-visibility']
        need(copied['bytes'] == HELPER_BYTES and copied['sha256'] == HELPER_SHA256 and
             copied['path'] == self.plan['package'] + '/bin/sdk-visibility',
             'SDK_PREPARED_ARTIFACT_BINDING')
        fd = self._take('helper', os.dup(original_fd))
        self.helper_meta = metadata(fd)
        need(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY and
             not os.get_inheritable(fd), 'SDK_HELPER_READONLY_CLOEXEC')
        need(identity(fd) == copied['identity'] and self.helper_meta['uid'] == 0 and
             self.helper_meta['gid'] == 0 and self.helper_meta['nlink'] == 1 and
             self.helper_meta['mode'] == stat.S_IFREG | 0o555 and
             self.helper_meta['bytes'] == HELPER_BYTES, 'SDK_HELPER_METADATA')
        try:
            capability = os.getxattr(fd, 'security.capability')
        except OSError as error:
            need(error.errno in (errno.ENODATA, errno.ENOTSUP), 'SDK_HELPER_CAPABILITY_READ')
            capability = b''
        need(not capability, 'SDK_HELPER_FILE_CAPABILITY')
        raw, observed = self._hash(fd, 262144)
        need(observed['sha256'] == HELPER_SHA256, 'SDK_HELPER_FULL_HASH')
        summary = elf_summary(raw)
        need(summary['type'] == 3 and summary['interpreter'] == '/system/bin/linker64',
             'SDK_HELPER_NORMAL_PIE')
        self.helper_path = copied['path']
        self.record['helper'] = dict(observed, elf=summary, prepared_identity=copied['identity'])

    def _bind_init(self, audit):
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
             'SDK_UNCHANGED_ROOT_ACTOR_REQUIRED')
        need(tuple(self.owned.NAMES) == NAMES, 'SDK_NAMESPACE_SCHEMA')
        nonce = audit.get('nonce')
        need(hex_string(nonce, 64, True), 'SDK_GENERATION_NONCE')
        self.nonce = nonce
        hello = [row['detail']['init'] for row in audit['records']
                 if row['detail']['event'] == 'init_hello']
        domains = [row['detail']['domain'] for row in audit['records']
                   if row['detail']['event'] == 'prepared']
        need(len(hello) == len(domains) == 1, 'SDK_SINGLE_HELLO_DOMAIN')
        snapshot = self.init.snapshot()
        for field in ('process', 'namespaces', 'executable', 'executable_sha256'):
            need(snapshot[field] == hello[0][field], 'SDK_HELLO_BINDING')
        need(snapshot['identity']['uids'] == snapshot['identity']['gids'] == [0] * 4,
             'SDK_INIT_INITIAL_USERNS_ROOT')
        self.init_bound = snapshot
        init_raw, init_source = self._hash(self.init.exe, 16 * 1024 * 1024)
        need(init_source['sha256'] == snapshot['executable_sha256'], 'SDK_INIT_HELD_FULL_HASH')
        self.init_exe_metadata = init_source['metadata']
        self.record['init_source'] = init_source
        self.actor_namespaces = {}
        for index, name in enumerate(NAMES):
            self._check()
            fd = self._take('init_ns_' + name, os.open('ns/' + name,
                os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.init.proc))
            need(identity(fd) == snapshot['namespaces'][index], 'SDK_HELD_INIT_NAMESPACE')
            actor = os.stat('/proc/self/ns/' + name)
            self.actor_namespaces[name] = {'device': actor.st_dev, 'inode': actor.st_ino}
        need(self.actor_namespaces['user'] == identity(self.fds['init_ns_user']) and
             self.actor_namespaces['pid'] != identity(self.fds['init_ns_pid']),
             'SDK_USER_OR_PID_NAMESPACE_RELATION')
        for name in ('time', 'time_for_children'):
            need(self.actor_namespaces[name] == identity(self.fds['init_ns_' + name]),
                 'SDK_TIME_NAMESPACE_DIFFERS')
        root = self._take('root', os.open('root',
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.init.proc))
        st = metadata(root)
        need(identity(root) == hello[0]['root'] and stat.S_ISDIR(st['mode']) and
             st['uid'] == st['gid'] == 0 and stat.S_IMODE(st['mode']) == 0o755 and
             st['inode'] == 1 and filesystem_type(root) == ROOT_TMPFS,
             'SDK_OWNED_SYNTHETIC_ROOT')
        domain_path = self.plan['spec']['pressure_relay']['cgroup_parent'] + '/g-' + nonce + '/android'
        need(domain_path.startswith('/sys/fs/cgroup/') and
             all(x not in ('', '.', '..') for x in domain_path.split('/')[1:]),
             'SDK_DOMAIN_PATH')
        self.domain_path = domain_path
        domain = self._open_directory(domain_path, 'domain')
        self.owned.require_cgroup2(domain)
        self.domain_identity = identity(domain)
        need(self.domain_identity == domains[0], 'SDK_AUDIT_DOMAIN_IDENTITY')
        self.domain_relative = domain_path[len('/sys/fs/cgroup'):]
        member = self.owned.bounded(self.init.proc, 'cgroup', 4096).decode('ascii').splitlines()
        need(len(member) == 1 and member[0].startswith('0::') and
             (member[0][3:] == self.domain_relative or
              member[0][3:].startswith(self.domain_relative + '/')), 'SDK_INIT_DOMAIN_MEMBERSHIP')
        self._take('child_domain_procs', os.open('cgroup.procs', os.O_WRONLY |
            os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=domain))
        need(stat.S_ISREG(os.fstat(self.fds['child_domain_procs']).st_mode), 'SDK_DOMAIN_PROCS_FILE')
        self.expected_namespaces = {name: (identity(self.fds['init_ns_' + name])
            if name in JOIN_NAMES else self.actor_namespaces[name]) for name in NAMES}
        self._borrowed_init_current()
        self.record.update(init_snapshot=snapshot, init_root=st,
            actor_namespaces=self.actor_namespaces, helper_expected_namespaces=self.expected_namespaces,
            generation_domain={'path': domain_path, **self.domain_identity},
            namespace_scope='join mnt/net/ipc/uts/cgroup only; retain actor PID namespace and same initial user/time namespaces')

    def _spawn(self):
        self._check()
        need(os.execve in os.supports_fd and hasattr(os, 'setns') and
             hasattr(os, 'fork') and hasattr(os, 'pidfd_open') and
             hasattr(os, 'waitid') and hasattr(os, 'P_PIDFD') and
             hasattr(signal, 'pidfd_send_signal') and hasattr(signal, 'setitimer') and
             hasattr(signal, 'getitimer') and hasattr(signal, 'pthread_sigmask'),
             'SDK_HOST_API_UNAVAILABLE')
        need(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL and
             len(os.listdir('/proc/self/task')) == 1, 'SDK_SINGLE_WAITER_THREAD_REQUIRED')
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                                   ctypes.c_ulong, ctypes.c_ulong)
        self.libc.prctl.restype = ctypes.c_int
        self._take('actor_pidfd', os.pidfd_open(self.actor_pid))
        self.sock, self.child_sock = socket.socketpair(socket.AF_UNIX,
            socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        read_end, write_end = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        self._take('stderr_read', read_end); self._take('stderr_write', write_end)
        descriptors = os.listdir('/proc/self/fd')
        need(len(descriptors) <= MAX_SELF_FDS and all(x.isdecimal() for x in descriptors),
             'SDK_INHERITED_FD_BOUND')
        inherited = []
        for text in descriptors:
            fd = int(text)
            try:
                os.fstat(fd)
            except OSError as error:
                need(error.errno == errno.EBADF, 'SDK_INHERITED_FD_STAT')
                continue  # The bounded listdir descriptor has already closed.
            inherited.append(fd)
        child_channel = self.child_sock.fileno()
        need(all(3 <= fd <= 65535 for fd in (child_channel, self.fds['actor_pidfd'])) and
             all(fd >= 3 for fd in self.fds.values()) and self.sock.fileno() >= 3,
             'SDK_EXEC_DESCRIPTOR_RANGE')
        argv = ['sdk-visibility', '--sdk-visibility-v1', self.nonce,
                str(child_channel), str(self.fds['actor_pidfd'])]
        env = {'PATH': '/system/bin:/system/xbin', 'LANG': 'C',
               'ANDROID_ROOT': '/system', 'ANDROID_DATA': '/data'}
        self.record['spawn_attempts'] = 1
        self._check()
        pid = os.fork()
        if pid == 0:
            self._child(inherited, argv, env)
        self.pid = pid
        self.record.update(child_started=True, helper_host_pid=pid,
                           fork_returned_monotonic_ns=time.monotonic_ns())
        # Register the child before any fallible post-fork parent operation.
        primary = None
        try:
            self._take('child_pidfd', os.pidfd_open(pid))
            self._take('child_proc', os.open('/proc/' + str(pid),
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW))
            first = self._proc_status()
            self.child_birth = first['birth']
            self.record['child_initial_process'] = {'pid': pid, 'birth': self.child_birth,
                'pidfd': identity(self.fds['child_pidfd']), 'proc_dir': identity(self.fds['child_proc'])}
            self.record['state'] = 'WAITING_READY'
        except BaseException as error:
            primary = error
            raise
        finally:
            closes = []
            if self.child_sock is not None:
                sock, self.child_sock = self.child_sock, None
                row = {'name': 'child_sock', 'close_attempted_once': True, 'closed': False}
                self.record['channel_close_records'].append(row)
                try:
                    sock.close(); row['closed'] = True
                except BaseException as error:
                    row['error'] = repr(error)[:160]
                    self.close_failed = True; closes.append(error)
            try: self._close('stderr_write')
            except BaseException as error: closes.append(error)
            if closes:
                if primary is None:
                    raise closes[0]
                for error in closes:
                    primary.add_note('post-fork FD close: ' + repr(error)[:160])

    def _child(self, inherited, argv, env):
        stage = 'parent_death'
        try:
            if self.libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
                code = ctypes.get_errno(); raise OSError(code, os.strerror(code))
            need(os.getppid() == self.actor_pid, 'SDK_CHILD_PARENT_CHANGED')
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            stage = 'deadline_arm'
            arm_child_deadline(self.deadline)
            stage = 'owned_domain'
            body = str(os.getpid()).encode('ascii')
            need(os.write(self.fds['child_domain_procs'], body) == len(body), 'SDK_CHILD_DOMAIN_WRITE')
            stage = 'namespace_entry'
            for name in JOIN_NAMES:
                os.setns(self.fds['init_ns_' + name], 0)
            stage = 'owned_root'
            os.fchdir(self.fds['root']); os.chroot('.'); os.chdir('/')
            stage = 'descriptor_retirement'
            os.dup2(self.fds['stderr_write'], 1, inheritable=True)
            os.dup2(self.fds['stderr_write'], 2, inheritable=True)
            keep = {1, 2, self.child_sock.fileno(), self.fds['actor_pidfd'], self.fds['helper']}
            for fd in inherited:
                if fd not in keep:
                    os.close(fd)
            os.set_inheritable(self.child_sock.fileno(), True)
            os.set_inheritable(self.fds['actor_pidfd'], True)
            os.set_inheritable(self.fds['helper'], False)
            stage = 'exact_android_exec'
            verify_child_deadline(self.deadline)
            os.execve(self.fds['helper'], argv, env)
            raise RuntimeError('SDK_EXEC_RETURNED')
        except BaseException as error:
            try:
                raw = json.dumps({'schema': 1, 'phase': 'setup_failure', 'nonce': self.nonce,
                    'stage': stage, 'errno': getattr(error, 'errno', None),
                    'type': type(error).__name__}, separators=(',', ':')).encode()
                self.child_sock.send(raw, socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL)
            except BaseException:
                pass
        os._exit(127)

    def _proc_status(self):
        proc = self.fds['child_proc']
        first = self.owned.bounded(proc, 'stat', 8192).decode().rsplit(')', 1)[1].split()
        fields = dict(line.split(':', 1) for line in
            self.owned.bounded(proc, 'status', 65536).decode('ascii').splitlines() if ':' in line)
        last = self.owned.bounded(proc, 'stat', 8192).decode().rsplit(')', 1)[1].split()
        need(len(first) >= 20 and len(last) >= 20 and first[19] == last[19] and
             first[0] not in ('Z', 'X') and last[0] not in ('Z', 'X') and
             int(fields['Pid']) == self.pid and int(fields['PPid']) == self.actor_pid and
             not self.owned.dead(self.fds['child_pidfd']) and
             self.owned.pidfd_pid(self.fds['child_pidfd']) == self.pid, 'SDK_CHILD_PROCESS_CHANGED')
        birth = int(first[19])
        if hasattr(self, 'child_birth'):
            need(birth == self.child_birth, 'SDK_CHILD_BIRTH_CHANGED')
        return {'pid': self.pid, 'birth': birth, 'parent': int(fields['PPid']),
            'uids': [int(x) for x in fields['Uid'].split()],
            'gids': [int(x) for x in fields['Gid'].split()],
            'groups': [int(x) for x in fields['Groups'].split()],
            'nspid': [int(x) for x in fields['NSpid'].split()],
            'threads': int(fields['Threads']), 'no_new_privileges': int(fields['NoNewPrivs']),
            **{out: fields[key].strip().lower() for out, key in (
                ('effective', 'CapEff'), ('permitted', 'CapPrm'), ('inheritable', 'CapInh'),
                ('bounding', 'CapBnd'), ('ambient', 'CapAmb'))}}

    def _process_view(self, expected_credentials):
        self._check()
        first = self._proc_status()
        uid = expected_credentials['uids'][0]
        need(first['uids'] == first['gids'] == [uid] * 4 and first['threads'] == 1 and
             len(first['groups']) == expected_credentials['group_count'] and
             first['no_new_privileges'] == expected_credentials['no_new_privileges'],
             'SDK_KERNEL_CREDENTIALS_DIFFER')
        for key in ('effective', 'permitted', 'inheritable', 'bounding', 'ambient'):
            need(first[key] == expected_credentials[key], 'SDK_KERNEL_CAPABILITIES_DIFFER')
        if uid == 1069:
            need(first['groups'] == [], 'SDK_KERNEL_RESIDUAL_GROUPS')
        namespaces = {}
        for name in NAMES:
            self._check()
            st = os.stat('ns/' + name, dir_fd=self.fds['child_proc'])
            namespaces[name] = {'device': st.st_dev, 'inode': st.st_ino}
        need(namespaces == self.expected_namespaces, 'SDK_CHILD_NAMESPACE_VIEW')
        root = os.stat('root', dir_fd=self.fds['child_proc'])
        need({'device': root.st_dev, 'inode': root.st_ino} == identity(self.fds['root']),
             'SDK_CHILD_ROOT_VIEW')
        member = self.owned.bounded(self.fds['child_proc'], 'cgroup', 4096).decode('ascii').splitlines()
        need(member == ['0::' + self.domain_relative], 'SDK_CHILD_DOMAIN_VIEW')
        exe = self._take('current_exe', os.open('exe', os.O_RDONLY | os.O_CLOEXEC,
                                               dir_fd=self.fds['child_proc']))
        primary = None
        try:
            raw, executable = self._hash(exe, 262144)
            need(executable['metadata'] == self.helper_meta and
                 executable['sha256'] == HELPER_SHA256, 'SDK_CURRENT_EXECUTABLE')
        except BaseException as error:
            primary = error
            raise
        finally:
            try: self._close('current_exe')
            except BaseException as error:
                if primary is None: raise
                primary.add_note('current exe close: ' + repr(error)[:160])
        maps_raw = self.owned.bounded(self.fds['child_proc'], 'maps', MAP_BYTES)
        maps = parse_maps(maps_raw)
        helper_maps = selected_maps(maps, self.helper_meta)
        need(self._proc_status() == first, 'SDK_CHILD_CHANGED_DURING_VIEW')
        self._borrowed_init_current()
        self._check()
        return {'process': first, 'namespaces': namespaces, 'root': identity(self.fds['root']),
                'cgroup': member, 'helper_maps': helper_maps,
                'maps_bytes': len(maps_raw), 'maps_sha256': hashlib.sha256(maps_raw).hexdigest()}, maps

    def _library_named(self, path, name):
        """Resolve only a fixed APEX path inside held root, including ordinary aliases."""
        need(path in LIBRARIES, 'SDK_LIBRARY_PATH_NOT_FIXED')
        parts = path.lstrip('/').split('/')
        links = 0
        primary = None
        current = self._take(name + '_walk', os.dup(self.fds['root']))
        prefix = []
        try:
            while parts:
                self._check()
                part = parts.pop(0)
                need(part not in ('', '.', '..') and '/' not in part, 'SDK_LIBRARY_COMPONENT')
                last = not parts
                st = os.stat(part, dir_fd=current, follow_symlinks=False)
                if stat.S_ISLNK(st.st_mode):
                    need(not last and links < 8, 'SDK_LIBRARY_FINAL_SYMLINK_OR_LOOP')
                    target = os.readlink(part, dir_fd=current)
                    need(isinstance(target, str) and 0 < len(target) <= 512 and '\0' not in target,
                         'SDK_LIBRARY_SYMLINK_BOUND')
                    normalized = [] if target.startswith('/') else list(prefix)
                    for component in target.split('/'):
                        if component in ('', '.'):
                            continue
                        if component == '..':
                            need(normalized, 'SDK_LIBRARY_SYMLINK_ESCAPE')
                            normalized.pop()
                        else:
                            normalized.append(component)
                    need(normalized and normalized[0] == 'apex' and
                         len(normalized) + len(parts) <= 32, 'SDK_LIBRARY_OUTSIDE_APEX')
                    parts = normalized + parts; prefix = []; links += 1
                    child = self._take(name + '_next', os.dup(self.fds['root']))
                    self._close(name + '_walk')
                    self.fds[name + '_walk'] = self.fds.pop(name + '_next'); current = child
                    continue
                flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
                if not last:
                    flags |= os.O_DIRECTORY
                child = self._take(name + '_next', os.open(part, flags, dir_fd=current))
                observed = os.fstat(child)
                need((observed.st_dev, observed.st_ino) == (st.st_dev, st.st_ino),
                     'SDK_LIBRARY_NAME_RACE')
                if not last:
                    need(stat.S_ISDIR(observed.st_mode) and observed.st_uid == 0 and
                         not observed.st_mode & 0o22, 'SDK_LIBRARY_PARENT')
                self._close(name + '_walk')
                self.fds[name + '_walk'] = self.fds.pop(name + '_next'); current = child
                prefix.append(part)
            fd = self.fds.pop(name + '_walk')
            return self._take(name, fd)
        except BaseException as error:
            primary = error
            raise
        finally:
            failures = []
            for suffix in ('_next', '_walk'):
                try: self._close(name + suffix)
                except BaseException as error: failures.append(error)
            if failures:
                if primary is None:
                    raise failures[0]
                for error in failures:
                    primary.add_note('library walk close: ' + repr(error)[:160])

    def _qualify_libraries(self, ready, received_names, maps):
        need(len(received_names) == 3, 'SDK_LIBRARY_RIGHTS_COUNT')
        observations = []
        for index, (path, name) in enumerate(zip(LIBRARIES, received_names)):
            fd = self.fds[name]; m = metadata(fd)
            need(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY and
                 not os.get_inheritable(fd), 'SDK_BIONIC_READONLY_CLOEXEC')
            need(stat.S_ISREG(m['mode']) and m['uid'] == m['gid'] == 0 and
                 m['nlink'] == 1 and not m['mode'] & 0o7022 and
                 0 < m['bytes'] <= LIBRARY_BYTES, 'SDK_BIONIC_FILE_METADATA')
            raw, value = self._hash(fd, LIBRARY_BYTES)
            summary = elf_summary(raw, index == 0)
            leaf = path.rsplit('/', 1)[1]
            if leaf in KNOWN_BUILD_IDS:
                need(summary['build_id'] == KNOWN_BUILD_IDS[leaf], 'SDK_KNOWN_RUNTIME_BUILD_ID')
            named = self._library_named(path, 'named_library')
            primary = None
            try:
                need(metadata(named) == m, 'SDK_BIONIC_NAMED_SOURCE')
            except BaseException as error:
                primary = error; raise
            finally:
                try: self._close('named_library')
                except BaseException as error:
                    if primary is None: raise
                    primary.add_note('bionic named close: ' + repr(error)[:160])
            selected = selected_maps(maps, m)
            row = {'path': path, **value, 'elf': summary, 'mapped_segments': selected,
                   'prior_build_id_pin': KNOWN_BUILD_IDS.get(leaf),
                   'full_hash_observed_this_generation': True}
            if index == 0:
                row['getter_mapping'] = getter_mapping(ready, summary, selected)
            observations.append(row)
        self.library_info = observations
        self.library_names = list(received_names)
        self.record['bionic_sources_before'] = observations
        self._borrowed_init_current()

    def _libraries_after(self, maps):
        after = []
        for path, name, before in zip(LIBRARIES, self.library_names, self.library_info):
            raw, observed = self._hash(self.fds[name], LIBRARY_BYTES)
            need(observed['metadata'] == before['metadata'] and
                 observed['sha256'] == before['sha256'], 'SDK_BIONIC_CHANGED_AFTER_READ')
            named = self._library_named(path, 'named_library')
            primary = None
            try:
                need(metadata(named) == before['metadata'], 'SDK_BIONIC_NAME_CHANGED_AFTER_READ')
            except BaseException as error:
                primary = error; raise
            finally:
                try: self._close('named_library')
                except BaseException as error:
                    if primary is None: raise
                    primary.add_note('bionic final named close: ' + repr(error)[:160])
            selected = selected_maps(maps, before['metadata'])
            need(selected == before['mapped_segments'], 'SDK_BIONIC_MAPPING_CHANGED')
            after.append({'path': path, **observed, 'mapped_segments': selected})
        self.record['bionic_sources_after'] = after

    def _recv(self):
        self._check()
        try:
            raw, ancillary, flags, _ = self.sock.recvmsg(PACKET_BYTES + 1,
                socket.CMSG_SPACE(12) + socket.CMSG_SPACE(8 * array.array('i').itemsize),
                socket.MSG_DONTWAIT | socket.MSG_CMSG_CLOEXEC)
        except BlockingIOError:
            return None
        received = []; creds = []; unexpected = False
        packet_number = self.record['protocol_packets']
        try:
            for level, kind, body in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    values = array.array('i')
                    values.frombytes(body[:len(body) - len(body) % values.itemsize])
                    for number, fd in enumerate(values):
                        name = 'right_%d_%d' % (packet_number, len(received))
                        self._take(name, fd); received.append(name)
                    need(len(body) % values.itemsize == 0, 'SDK_RIGHTS_ENCODING')
                elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                    need(len(body) == 12, 'SDK_KERNEL_CREDENTIAL_SIZE')
                    creds.append(struct.unpack('3i', body))
                else:
                    unexpected = True
            need(not unexpected and flags & ~(socket.MSG_EOR | socket.MSG_CMSG_CLOEXEC) == 0 and
                 len(raw) <= PACKET_BYTES, 'SDK_PACKET_TRUNCATED_OR_ANCILLARY')
            if not raw:
                need(not received and not creds, 'SDK_EOF_WITH_ANCILLARY')
                return ('EOF', None, [])
            need(len(creds) == 1 and creds[0][0] == self.pid, 'SDK_KERNEL_SENDER_PID')
            value = strict_json(raw)
            self.record['protocol_packets'] += 1
            need(self.record['protocol_packets'] <= 4, 'SDK_PACKET_COUNT')
            self.record['wire_records'].append({'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(),
                'kernel_credentials': {'pid': creds[0][0], 'uid': creds[0][1], 'gid': creds[0][2]},
                'phase': value.get('phase') if value.get('phase') in
                    ('ready', 'root', 'uid1069', 'failure', 'setup_failure') else 'UNRECOGNIZED'})
            return value, creds[0], received
        except BaseException as primary:
            for name in received:
                try: self._close(name)
                except BaseException as error:
                    primary.add_note('received FD close: ' + repr(error)[:160])
            raise

    def _send_token(self, prefix, field):
        self._check()
        need(self.record[field] == 0, 'SDK_TOKEN_REUSE')
        raw = prefix + self.nonce.encode('ascii')
        stem = field.removesuffix('_attempts')
        before = time.monotonic_ns()
        need(before < self.deadline, 'SDK_TOKEN_DEADLINE')
        self.record[field] = 1
        self.record[stem + '_send_before_ns'] = before
        try:
            sent = self.sock.send(raw, socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL)
            self.record[stem + '_sent_bytes'] = sent
        finally:
            self.record[stem + '_send_returned_ns'] = time.monotonic_ns()
        need(sent == len(raw), 'SDK_TOKEN_SHORT_SEND')
        self._check()
        # The child can run as soon as send queues the token, before send returns.
        # Its first read therefore brackets against admission, not return time.
        return before

    def _accept(self, value, creds, names):
        if value == 'EOF':
            need(self.phase == 'WAITING_EXIT', 'SDK_EARLY_CHANNEL_EOF')
            self.record['channel_eof_observed'] = True
            return
        phase = value.get('phase')
        if phase == 'setup_failure':
            need(not names and creds[1:] == (0, 0) and
                 set(value) == {'schema', 'phase', 'nonce', 'stage', 'errno', 'type'} and
                 type(value['schema']) is int and value['schema'] == 1 and
                 value['nonce'] == self.nonce and value['stage'] in {
                     'parent_death', 'deadline_arm', 'owned_domain', 'namespace_entry', 'owned_root',
                     'descriptor_retirement', 'exact_android_exec'} and
                 (value['errno'] is None or integer(value['errno'], 0, (1 << 31) - 1)) and
                 isinstance(value['type'], str) and len(value['type']) <= 64,
                 'SDK_CHILD_SETUP_FAILURE_SCHEMA')
            self.record['child_setup_failure'] = value
            raise RuntimeError('SDK_CHILD_SETUP_FAILED')
        if phase == 'failure':
            need(not names and creds[1] in (0, 1069) and creds[2] in (0, 1069), 'SDK_FAILURE_SENDER')
            self.record['accessor_failure'] = failure_record(value, self.nonce)
            raise RuntimeError('SDK_ACCESSOR_REPORTED_FAILURE')
        if self.phase == 'WAITING_READY':
            need(creds[1:] == (0, 0) and len(names) == 3, 'SDK_READY_SENDER_OR_RIGHTS')
            ready = ready_record(value, self.nonce, self.pid)
            self.record['ready'] = ready
            self.record['root_source_proof_before_ns'] = time.monotonic_ns()
            view, maps = self._process_view(ready['credentials'])
            self._qualify_libraries(ready, names, maps)
            self.record['root_source_view'] = view
            self._check()
            self.record['root_source_proof_after_ns'] = time.monotonic_ns()
            self.record['source_qualified_before_reads'] = True
            self.read_started = self._send_token(b'READ_ROOT_AND_1069:', 'start_token_attempts')
            self.record['start_token_sent_monotonic_ns'] = self.record['start_token_send_returned_ns']
            self.phase = 'WAITING_ROOT'
        elif self.phase == 'WAITING_ROOT':
            need(not names and creds[1:] == (0, 0), 'SDK_ROOT_SENDER_OR_RIGHTS')
            self.root_value = values_record(value, 'root', self.nonce, self.read_started, self.deadline)
            need(self.root_value['credentials'] == self.record['ready']['credentials'],
                 'SDK_ROOT_CREDENTIALS_CHANGED')
            self.record['root_observation'] = self.root_value
            self.phase = 'WAITING_LOWER'
        elif self.phase == 'WAITING_LOWER':
            need(not names and creds[1:] == (1069, 1069), 'SDK_LOWER_SENDER_OR_RIGHTS')
            self.lower_value = values_record(value, 'uid1069', self.nonce,
                                            self.root_value['after_ns'], self.deadline)
            self.record['uid1069_received_unqualified'] = self.lower_value
            self.record['lower_source_proof_before_ns'] = time.monotonic_ns()
            view, maps = self._process_view(self.lower_value['credentials'])
            self._libraries_after(maps)
            self._borrowed_init_current()
            self._check()
            self.record['lower_source_proof_after_ns'] = time.monotonic_ns()
            self.record['uid1069_observation'] = self.lower_value
            self.record['lower_source_view'] = view
            self._send_token(b'OBSERVED:', 'finish_token_attempts')
            self.record['finish_token_sent_monotonic_ns'] = self.record['finish_token_send_returned_ns']
            self.record['finish_token_sent'] = True
            self.record['observation_completed'] = True
            self.record['observation_closed_monotonic_ns'] = self.record['finish_token_send_returned_ns']
            self.phase = 'WAITING_EXIT'
        else:
            raise RuntimeError('SDK_EXTRA_OR_OUT_OF_ORDER_PACKET')

    def _drain_stderr(self):
        if self.stderr_eof or 'stderr_read' not in self.fds:
            return
        for unused in range(5):
            need(len(self.stderr) <= STDERR_BYTES, 'SDK_STDERR_BOUND')
            try:
                part = os.read(self.fds['stderr_read'], min(4096, STDERR_BYTES + 1 - len(self.stderr)))
            except BlockingIOError:
                return
            if not part:
                self.stderr_eof = True
                return
            self.stderr.extend(part)
            need(len(self.stderr) <= STDERR_BYTES, 'SDK_STDERR_BOUND')

    def _reap_nonblocking(self):
        if self.pid is None or self.child_reaped:
            return
        if 'child_pidfd' in self.fds:
            observed = os.waitid(os.P_PIDFD, self.fds['child_pidfd'],
                                 os.WEXITED | os.WNOWAIT | os.WNOHANG)
        else:
            # This numeric PID remains our unreaped direct child; no other
            # thread or SIGCHLD waiter is admitted. It cannot yet be reused.
            observed = os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
        if observed is None:
            return
        need(observed.si_pid == self.pid, 'SDK_WAITED_CHILD_DIFFERS')
        pid, status = os.waitpid(self.pid, os.WNOHANG)
        need(pid == self.pid, 'SDK_READY_CHILD_NOT_REAPED')
        self.child_reaped = True
        self.record.update(child_reaped=True, child_wait_status=status,
            child_returncode=os.waitstatus_to_exitcode(status),
            child_exit_signal=os.WTERMSIG(status) if os.WIFSIGNALED(status) else None,
            child_reap_observed_monotonic_ns=time.monotonic_ns(),
            child_exit_kernel_time_observed=False)

    def _abort_nonblocking(self):
        if self.pid is None or self.child_reaped:
            return
        try:
            self._reap_nonblocking()
            if self.child_reaped or self.record.get('child_kill_attempted'):
                return
            self.record['child_kill_attempted'] = True
            if 'child_pidfd' in self.fds:
                signal.pidfd_send_signal(self.fds['child_pidfd'], signal.SIGKILL, None, 0)
            else:
                # Only the still-unreaped direct child is eligible, after
                # waitid above. No guessed PID or process group is signalled.
                os.kill(self.pid, signal.SIGKILL)
            self.record['child_kill_sent'] = True
        except ProcessLookupError:
            try: self._reap_nonblocking()
            except BaseException as error: self._failure('child_reap_after_exit', error)
        except BaseException as error:
            self._failure('owned_child_abort', error)

    def poll(self):
        if self.finished:
            return
        try:
            self._drain_stderr()
            if self.record['first_error'] is not None:
                self._abort_nonblocking(); self._reap_nonblocking()
                return
            if self.phase == 'WAITING_EXIT':
                self._reap_nonblocking()
                if self.child_reaped:
                    need(self.record['child_returncode'] == 0, 'SDK_CHILD_EXIT_FAILURE')
                    self._drain_stderr()
                    self.record['state'] = 'OBSERVED_WAITING_FINAL_CLOSE'
                    return
            self._check()
            for unused in range(4):
                received = self._recv()
                if received is None:
                    break
                self._accept(*received)
                if received[0] == 'EOF':
                    break
            self._reap_nonblocking()
            if self.child_reaped:
                need(self.phase == 'WAITING_EXIT' and self.record['child_returncode'] == 0,
                     'SDK_CHILD_EXIT_BEFORE_PROTOCOL_COMPLETION')
                self._drain_stderr()
                self.record['state'] = 'OBSERVED_WAITING_FINAL_CLOSE'
        except BaseException as error:
            self._failure('bounded_observation', error)
            self._abort_nonblocking()

    def _save_stderr(self):
        # This fixed private file contains only a bounded prefix from our own
        # accessor's stdout/stderr. It is not copied into the public result.
        name = 'sdk-visibility.stderr'
        fd = self._take('stderr_evidence', os.open(name, os.O_WRONLY | os.O_CREAT |
            os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=self.evidence))
        first = metadata(fd)
        need(stat.S_ISREG(first['mode']) and first['uid'] == first['gid'] == 0 and
             stat.S_IMODE(first['mode']) == 0o600 and first['nlink'] == 1 and first['bytes'] == 0,
             'SDK_STDERR_NEW_FILE')
        self.record['private_stderr'] = {'relative': 'evidence/' + name,
            'metadata_after_create': first, 'complete': False, 'write_completed': False,
            'raw_bytes_exported_in_public_result': False}
        raw = bytes(self.stderr[:STDERR_BYTES])
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            need(count > 0, 'SDK_STDERR_WRITE')
            offset += count
        os.fchmod(fd, 0o400); os.fsync(fd)
        final = metadata(fd)
        named = os.stat(name, dir_fd=self.evidence, follow_symlinks=False)
        need(final['device'] == first['device'] and final['inode'] == first['inode'] and
             final['bytes'] == len(raw) and stat.S_IMODE(final['mode']) == 0o400 and
             (named.st_dev, named.st_ino, named.st_size, named.st_mode) ==
             (final['device'], final['inode'], len(raw), final['mode']), 'SDK_STDERR_FINAL_FILE')
        os.fsync(self.evidence)
        self.record['private_stderr'] = {'relative': 'evidence/' + name, 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'metadata': final,
            'eof_observed': self.stderr_eof, 'write_completed': True,
            'hash_basis': 'exact acknowledged write bytes; no independent file-content readback',
            'raw_bytes_exported_in_public_result': False,
            'complete': self.stderr_eof and len(self.stderr) <= STDERR_BYTES}

    def finish(self, reason):
        if self.finished:
            return self.record
        self.finished = True
        self.record['finish_reason'] = reason
        # The actor calls finish only after its original Stop and ordinary
        # direct-child retirement. No new token/property read is admitted here.
        cleanup_started = time.monotonic_ns()
        self.retirement_deadline = cleanup_started + 1_000_000_000
        self.record['retirement_started_monotonic_ns'] = cleanup_started
        self.record['retirement_deadline_monotonic_ns'] = self.retirement_deadline
        try:
            self._reap_nonblocking()
            if self.pid is not None and not self.child_reaped:
                if self.record['first_error'] is None:
                    self._failure('original_stop', RuntimeError('SDK_OBSERVER_INCOMPLETE_AT_ORIGINAL_STOP'))
                self._abort_nonblocking()
                # This bounded wait is retirement only, after original Stop.
                # It does not extend the two-second property observation.
                end = self.retirement_deadline / 1_000_000_000
                while not self.child_reaped and time.monotonic() < end:
                    self._reap_nonblocking()
                    if self.child_reaped:
                        break
                    if 'child_pidfd' in self.fds:
                        poller = select.poll(); poller.register(self.fds['child_pidfd'], select.POLLIN)
                        poller.poll(max(0, min(10, int((end - time.monotonic()) * 1000))))
                    else:
                        time.sleep(min(0.01, max(0.0, end - time.monotonic())))
                need(self.child_reaped, 'SDK_CHILD_NOT_REAPED_WITHIN_RETIREMENT_BOUND')
        except BaseException as error:
            self._failure('child_retirement', error)
        try:
            self._drain_stderr()
            if self.record['child_started']:
                need(self.stderr_eof, 'SDK_STDERR_NOT_COMPLETE_AFTER_JOIN')
        except BaseException as error:
            self._failure('stderr_retirement', error)
        if self.record['child_started']:
            try:
                self._retirement_check()
                self._save_stderr()
            except BaseException as error:
                self._failure('private_stderr_preservation', error)
        self.record['retirement_wait_limit_ms'] = 1000
        if 'helper' in self.fds:
            try:
                raw, value = self._hash(self.fds['helper'], 262144, False)
                need(value['metadata'] == self.helper_meta and value['sha256'] == HELPER_SHA256,
                     'SDK_HELPER_CHANGED_AT_CLOSE')
                named = self._take('helper_final_name', os.open(self.helper_path,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW))
                need(metadata(named) == self.helper_meta, 'SDK_HELPER_NAMED_CHANGED_AT_CLOSE')
                self.record['helper_final'] = value
            except BaseException as error:
                self._failure('helper_final_source', error)
        if hasattr(self, 'actor_namespaces'):
            try:
                after = {}
                for name in NAMES:
                    st = os.stat('/proc/self/ns/' + name)
                    after[name] = {'device': st.st_dev, 'inode': st.st_ino}
                need(after == self.actor_namespaces, 'SDK_ACTOR_NAMESPACE_CHANGED')
                self.record['actor_namespaces_after'] = after
                self.record['actor_namespaces_unchanged'] = True
            except BaseException as error:
                self._failure('actor_namespace_final', error)
        for attr in ('child_sock', 'sock'):
            sock = getattr(self, attr)
            if sock is not None:
                setattr(self, attr, None)
                row = {'name': attr, 'close_attempted_once': True, 'closed': False}
                self.record['channel_close_records'].append(row)
                try:
                    sock.close(); row['closed'] = True
                except BaseException as error:
                    row['error'] = repr(error)[:160]
                    self.close_failed = True
                    self._failure(attr + '_close', error)
        for name in list(self.fds):
            try: self._close(name)
            except BaseException as error:
                self._failure('close_' + name, error)
        self.record['held_fds_closed'] = not self.close_failed and not self.fds and self.sock is None and self.child_sock is None
        if not self.record['held_fds_closed']:
            self._failure('fd_retirement', RuntimeError('SDK_FD_RETIREMENT_INCOMPLETE'))
        retirement_finished = time.monotonic_ns()
        self.record['retirement_finished_monotonic_ns'] = retirement_finished
        self.record['retirement_elapsed_ns'] = retirement_finished - cleanup_started
        self.record['retirement_deadline_met'] = retirement_finished <= self.retirement_deadline
        if not self.record['retirement_deadline_met']:
            self._failure('retirement_deadline', RuntimeError('SDK_RETIREMENT_DEADLINE_EXCEEDED'))
        complete = bool(self.record['first_error'] is None and self.child_reaped and
            self.record.get('child_returncode') == 0 and self.record['source_qualified_before_reads'] and
            self.root_value is not None and self.lower_value is not None and
            self.record['finish_token_sent'] and self.record['observation_completed'] and
            self.record['observation_closed_monotonic_ns'] < self.deadline and
            self.record['held_fds_closed'] and self.stderr_eof and self.record['retirement_deadline_met'])
        self.record['property_visibility_qualified'] = complete
        if complete:
            self.record['state'] = 'WARM_ROOT_AND_UID1069_OBSERVED_AND_CLOSED'
        elif self.record['first_error'] is None:
            self.record['state'] = 'NOT_OBSERVED_BEFORE_ORIGINAL_STOP'
        self.record['finished_monotonic_ns'] = time.monotonic_ns()
        return self.record


if __name__ == '__main__':
    print(json.dumps({'schema': 1, 'mode': 'SOURCE_MODULE_ONLY',
        'runtime_entry': 'Capture from the pinned owned actor only',
        'Android_executed': False, 'property_reads_or_writes': False,
        'same_process_root_warmed_cache': True}))
