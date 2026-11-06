"""Host-only controls for the pinned collector; no Android helper execution.

Pure fixtures deliberately substitute protocol peers, clocks, namespace/source
proofs and compiled ELF bytes. Kernel checks cover only fresh owned sockets,
files and one host child at a time. They do not qualify Android execution,
setns/chroot, credentials 1069, bionic, the owned init or any Main process.
"""
import array
import ast
import copy
import ctypes
import errno
import hashlib
import json
import os
import select
import signal
import socket
import stat
import struct
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

NONCE = '0123456789abcdef' * 4


def run(P, actor_text, baseline_actor_text):
    rows = []
    def require(value, message):
        if not value:
            raise AssertionError(message)
    def case(name, function, scope='pure production-function fixture'):
        function()
        rows.append({'name': name, 'passed': True, 'scope': scope})
    def rejected(function, fragment=None):
        try:
            function()
        except Exception as error:
            if fragment:
                require(fragment in str(error), 'wrong rejection: ' + repr(error))
            return error
        raise AssertionError('negative control unexpectedly accepted')

    def caps(lower=False):
        return {'uids': [1069 if lower else 0] * 3, 'gids': [1069 if lower else 0] * 3,
            'group_count': 0, 'effective': '0000000000000000', 'permitted': '0000000000000000',
            'inheritable': '0000000000000000', 'bounding': '0000000000000000',
            'ambient': '0000000000000000', 'no_new_privileges': 1 if lower else 0}
    def ready(pid=42):
        return {'schema': 1, 'phase': 'ready', 'nonce': NONCE, 'pid': pid,
            'credentials': caps(), 'getter_address': '1000a0', 'getter_library_base': '100000',
            'libraries': list(P.LIBRARIES), 'lifetime_ms': 2000,
            'same_process_root_warmed_cache': True, 'actual_LMKD_capability_simulation': False}
    def values(phase='root', before=120, after=125):
        return {'schema': 1, 'phase': phase, 'nonce': NONCE, 'credentials': caps(phase == 'uid1069'),
            'before_ns': before, 'after_ns': after,
            'values': [{'key': key, 'return': len(value), 'errno_observation': 0,
                        'value_hex': value.hex()} for key, value in
                       zip(P.KEYS, (b'37', b'37.0', b'37', b'37.0'))]}

    def capture():
        # No constructor, spawn, namespace entry or source qualification runs.
        c = P.Capture.__new__(P.Capture)
        c.fds = {}; c.sock = c.child_sock = None; c.pid = None
        c.child_reaped = False; c.close_failed = False; c.finished = False
        c.stderr = bytearray(); c.stderr_eof = False; c.phase = 'WAITING_READY'
        c.library_info = []; c.root_value = c.lower_value = None
        c.actor_pid = os.getpid(); c.nonce = NONCE
        c.started = time.monotonic_ns(); c.deadline = c.started + 2_000_000_000
        c.record = {'schema': 1, 'first_error': None, 'secondary_errors': [], 'state': 'FIXTURE',
            'child_started': False, 'child_reaped': False, 'source_qualified_before_reads': False,
            'start_token_attempts': 0, 'finish_token_attempts': 0, 'finish_token_sent': False,
            'protocol_packets': 0, 'wire_records': [], 'held_fds_closed': False,
            'observation_completed': False, 'observation_closed_monotonic_ns': None,
            'fd_registration_events': 0, 'fd_close_records': [], 'channel_close_records': []}
        return c
    def close_capture(c):
        for attr in ('sock', 'child_sock'):
            s = getattr(c, attr)
            if s is not None:
                setattr(c, attr, None); s.close()
        for name in list(c.fds):
            c._close(name)

    def schema_positive():
        r = ready()
        require(P.ready_record(r, NONCE, 42) is r, 'ready identity')
        v = values()
        require(P.values_record(v, 'root', NONCE, 100, 1000) is v, 'root values')
        v = values('uid1069')
        v['values'][1] = dict(v['values'][1], **{'return': 0, 'errno_observation': errno.EACCES, 'value_hex': ''})
        require(P.values_record(v, 'uid1069', NONCE, 100, 1000) is v, 'empty is diagnostic')
        require(v['values'][1]['return'] == 0, 'empty not filled with guessed SDK')
    case('exact-four-keys-root-and-lowered-empty-value-preserved', schema_positive)
    case('duplicate-json-key-rejected', lambda: rejected(lambda: P.strict_json(b'{"schema":1,"schema":1}'), 'DUPLICATE'))
    case('noninteger-json-number-rejected', lambda: rejected(lambda: P.strict_json(b'{"x":1.5}'), 'NONINTEGER'))
    case('nonfinite-json-number-rejected', lambda: rejected(lambda: P.strict_json(b'{"x":NaN}'), 'NONINTEGER'))
    case('wrong-ready-nonce-rejected', lambda: rejected(lambda: P.ready_record(dict(ready(), nonce='f'*64), NONCE, 42), 'READY_IDENTITY'))
    case('root-warmed-boundary-cannot-be-relabelled-cold', lambda: rejected(lambda: P.ready_record(dict(ready(), same_process_root_warmed_cache=False), NONCE, 42), 'READY_SCOPE'))

    def values_negative(change, label):
        v = values('uid1069')
        change(v)
        rejected(lambda: P.values_record(v, 'uid1069', NONCE, 100, 1000), label)
    case('unapproved-fifth-key-rejected', lambda: values_negative(lambda v: v['values'].append(dict(v['values'][0])), 'VALUES_COUNT'))
    case('changed-key-order-rejected', lambda: values_negative(lambda v: v['values'].reverse(), 'VALUE_SCHEMA'))
    case('residual-lowered-capability-rejected', lambda: values_negative(lambda v: v['credentials'].__setitem__('ambient', '0000000000000001'), 'RESIDUAL_CAPABILITY'))
    case('residual-lowered-group-rejected', lambda: values_negative(lambda v: v['credentials'].__setitem__('group_count', 1), 'LOWER_GROUPS'))
    case('second-observation-after-deadline-rejected', lambda: values_negative(lambda v: v.__setitem__('after_ns', 1000), 'VALUES_DEADLINE'))
    case('value-length-mismatch-rejected', lambda: values_negative(lambda v: v['values'][0].__setitem__('return', 3), 'VALUE_ENCODING'))
    case('embedded-NUL-value-rejected', lambda: values_negative(lambda v: v['values'][0].__setitem__('value_hex', '0031'), 'VALUE_ENCODING'))

    def token_bracket(late):
        c = capture(); now = [100]
        old_clock = P.time.monotonic_ns
        class Sender:
            def send(self, body, flags):
                require(body == b'READ_ROOT_AND_1069:' + NONCE.encode(), 'fixed token')
                now[0] = 1001 if late else 150
                return len(body)
        c.sock = Sender(); c.deadline = 1000
        P.time.monotonic_ns = lambda: now[0]
        try:
            if late:
                rejected(lambda: c._send_token(b'READ_ROOT_AND_1069:', 'start_token_attempts'), 'DEADLINE')
                require(c.record['start_token_attempts'] == 1 and
                        c.record['start_token_send_before_ns'] == 100 and
                        c.record['start_token_send_returned_ns'] == 1001, 'late send retained')
            else:
                earliest = c._send_token(b'READ_ROOT_AND_1069:', 'start_token_attempts')
                v = values(before=120, after=140)  # Child ran before send returned at 150.
                P.values_record(v, 'root', NONCE, earliest, c.deadline)
                require(earliest == 100 and c.record['start_token_send_returned_ns'] == 150, 'admission bracket')
                rejected(lambda: P.values_record(v, 'root', NONCE, 150, c.deadline), 'VALUES_DEADLINE')
                rejected(lambda: c._send_token(b'READ_ROOT_AND_1069:', 'start_token_attempts'), 'TOKEN_REUSE')
        finally:
            P.time.monotonic_ns = old_clock
    case('child-can-read-before-send-returns-without-false-stale-rejection', lambda: token_bracket(False))
    case('token-return-after-deadline-retained-as-failure', lambda: token_bracket(True))

    def proof_failure_before_token():
        c = capture(); c.pid = 42
        c._process_view = lambda x: (_ for _ in ()).throw(RuntimeError('FIXTURE_BAD_CURRENT_EXECUTABLE'))
        rejected(lambda: c._accept(ready(), (42, 0, 0), ['one', 'two', 'three']), 'BAD_CURRENT_EXECUTABLE')
        require(c.record['start_token_attempts'] == 0 and not c.record['source_qualified_before_reads'], 'no token before proof')
    case('current-executable-proof-failure-sends-no-read-token', proof_failure_before_token)

    def lower_proof_failure_retains_root():
        c = capture(); c.pid = 42; c.phase = 'WAITING_LOWER'; c.deadline = 1000
        c.root_value = values(); c.record['root_observation'] = c.root_value
        c._process_view = lambda x: (_ for _ in ()).throw(RuntimeError('FIXTURE_CHANGED_LOWER_ROOT'))
        rejected(lambda: c._accept(values('uid1069', 126, 130), (42, 1069, 1069), []), 'CHANGED_LOWER_ROOT')
        require(c.record['root_observation'] == c.root_value and c.record['finish_token_attempts'] == 0, 'original root kept, no ack')
    case('lower-source-failure-preserves-root-and-sends-no-ack', lower_proof_failure_retains_root)

    def elf_fixture():
        raw = bytearray(1024)
        struct.pack_into('<16sHHIQQQIHHHHHH', raw, 0, b'\x7fELF\x02\x01\x01' + b'\0'*9,
                         3, 62, 1, 0, 64, 512, 0, 64, 56, 2, 64, 3, 0)
        struct.pack_into('<IIQQQQQQ', raw, 64, 1, 5, 0, 0, 0, 1024, 1024, 4096)
        struct.pack_into('<IIQQQQQQ', raw, 120, 4, 4, 256, 256, 0, 32, 32, 4)
        struct.pack_into('<III', raw, 256, 4, 16, 3)
        raw[268:272] = b'GNU\0'; raw[272:288] = bytes(range(1, 17))
        names = b'\0__system_property_get\0'
        struct.pack_into('<IIQQQQIIQQ', raw, 576, 0, 11, 0, 0, 704, 48, 2, 0, 8, 24)
        struct.pack_into('<IIQQQQIIQQ', raw, 640, 0, 3, 0, 0, 768, len(names), 0, 0, 1, 0)
        raw[768:768+len(names)] = names
        struct.pack_into('<IBBHQQ', raw, 728, 1, 0x12, 0, 1, 160, 16)
        return raw
    def elf_and_map_positive():
        summary = P.elf_summary(bytes(elf_fixture()), True)
        require(summary['build_id'] == bytes(range(1,17)).hex(), 'BuildId')
        maps = P.parse_maps(b'00100000-00101000 r-xp 00000000 01:02 12345 /apex/libc.so\n')
        selected = P.selected_maps(maps, {'device': os.makedev(1, 2), 'inode': 12345})
        m = P.getter_mapping(ready(), summary, selected)
        require(m['symbol']['value'] == 160 and m['mapping']['start'] == 0x100000, 'ELF/PT_LOAD/actual-map binding')
    case('bounded-ELF-BuildId-dynsym-and-current-getter-map', elf_and_map_positive)
    def undefined_getter():
        raw = elf_fixture(); struct.pack_into('<H', raw, 728 + 6, 0)
        rejected(lambda: P.elf_summary(bytes(raw), True), 'GETTER_DEFINED_FUNC')
    case('undefined-getter-does-not-authorize-source', undefined_getter)
    def nonexec_getter():
        raw = elf_fixture(); struct.pack_into('<I', raw, 64 + 4, 4)
        rejected(lambda: P.elf_summary(bytes(raw), True), 'GETTER_EXECUTABLE_LOAD')
    case('non-executable-getter-load-rejected', nonexec_getter)
    def mismatched_map():
        e = P.elf_summary(bytes(elf_fixture()), True)
        m = P.parse_maps(b'00100000-00101000 r-xp 00000001 01:02 12345 /apex/libc.so\n')
        rejected(lambda: P.getter_mapping(ready(), e, m), 'GETTER_CURRENT_MAPPING')
    case('right-address-but-wrong-file-offset-rejected', mismatched_map)
    def foreign_map():
        m = P.parse_maps(b'00100000-00101000 r-xp 00000000 01:02 12346 /apex/libc.so\n')
        rejected(lambda: P.selected_maps(m, {'device': os.makedev(1,2), 'inode': 12345}), 'MAPPED_FILE')
    case('same-library-name-different-inode-rejected', foreign_map)

    def unexpected_bionic_build_id():
        c = capture(); c.pid = 42
        with tempfile.TemporaryDirectory(prefix='p4-owner20-elf-control-') as temp:
            names = []
            try:
                for index in range(3):
                    path = Path(temp) / str(index)
                    path.write_bytes(bytes(elf_fixture()))
                    os.chmod(path, 0o555)
                    names.append('library' + str(index))
                    c._take(names[-1], os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW))
                c._process_view = lambda creds: ({'fixture': True}, [])
                rejected(lambda: c._accept(ready(), (42, 0, 0), names), 'KNOWN_RUNTIME_BUILD_ID')
                require(c.record['start_token_attempts'] == 0 and not c.record['source_qualified_before_reads'],
                        'wrong runtime BuildId denied before any read token')
            finally:
                close_capture(c)
    case('real-held-library-bytes-with-wrong-BuildId-send-no-read-token',
         unexpected_bionic_build_id, 'owned synthetic ELF files; current-view seam; no Android execution')

    def transport(mode):
        c = capture(); c.pid = os.getpid() + (1 if mode == 'wrong_pid' else 0)
        c.sock, c.child_sock = socket.socketpair(socket.AF_UNIX,
            socket.SOCK_SEQPACKET | socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC)
        c.sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        owned_fd = os.memfd_create('owner20-host-control', os.MFD_CLOEXEC)
        try:
            if mode == 'EOF':
                c.child_sock.close(); c.child_sock = None
                require(c._recv() == ('EOF', None, []), 'real seqpacket EOF')
                return
            body = b'not-json' if mode == 'bad_json' else b'{"phase":"ready"}'
            rights = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [owned_fd]))]
            c.child_sock.sendmsg([body], rights)
            if mode in ('bad_json', 'wrong_pid'):
                rejected(c._recv, 'SENDER_PID' if mode == 'wrong_pid' else None)
                require(not c.fds and len(c.record['fd_close_records']) == 1 and
                        c.record['fd_close_records'][0]['closed'], 'every delivered right closed')
            else:
                value, cred, names = c._recv()
                require(value == {'phase':'ready'} and cred == (os.getpid(), os.getuid(), os.getgid()) and
                        len(names) == 1, 'kernel credential/source')
                fd = c.fds[names[0]]
                require(os.fstat(fd).st_ino == os.fstat(owned_fd).st_ino and
                        not os.get_inheritable(fd), 'kernel right and CLOEXEC')
        finally:
            os.close(owned_fd); close_capture(c)
    case('real-SCM-credentials-right-and-CLOEXEC', lambda: transport('ok'), 'owned kernel socket/FD only')
    case('bad-JSON-closes-real-delivered-right', lambda: transport('bad_json'), 'owned kernel socket/FD only')
    case('wrong-kernel-sender-closes-real-delivered-right', lambda: transport('wrong_pid'), 'owned kernel socket/FD only')
    case('real-seqpacket-EOF-has-no-delivered-right', lambda: transport('EOF'), 'owned kernel socket/FD only')

    def close_failure():
        c = capture(); first = os.memfd_create('owner20-close-a', os.MFD_CLOEXEC)
        second = os.memfd_create('owner20-close-b', os.MFD_CLOEXEC)
        c._take('first', first); c._take('second', second)
        c._failure('original', RuntimeError('ORIGINAL_OBSERVATION_ERROR'))
        saved = dict(c.record['first_error']); real_close = P.os.close; calls = []
        def close(fd):
            calls.append(fd)
            real_close(fd)
            if fd == first:
                raise OSError(errno.EIO, 'explicit ambiguous-close seam after real close')
        P.os.close = close
        try:
            result = c.finish('host-control cleanup')
        finally:
            P.os.close = real_close
        require(result['first_error'] == saved and result['held_fds_closed'] is False and
                not result['property_visibility_qualified'] and calls.count(first) == calls.count(second) == 1,
                'first error and all other closes')
        for fd in (first, second):
            error = rejected(lambda: os.fstat(fd))
            require(error.errno == errno.EBADF, 'real descriptor is closed')
    case('ambiguous-close-preserves-first-error-and-closes-other-FDs-once',
         close_failure, 'real owned FD; explicit close-EIO seam')

    def directory_close_failure():
        c = capture()
        with tempfile.TemporaryDirectory(prefix='p4-owner20-path-control-') as temp:
            before = set(os.listdir('/proc/self/fd')); real_close = P.os.close; injected = [False]
            def close(fd):
                real_close(fd)
                if not injected[0]:
                    injected[0] = True
                    raise OSError(errno.EIO, 'explicit first parent close seam')
            P.os.close = close
            try:
                rejected(lambda: c._open_directory(temp, 'owned_directory'))
            finally:
                P.os.close = real_close
            require(injected[0] and c.close_failed and not c.fds, 'registered child closed on parent close failure')
            require(set(os.listdir('/proc/self/fd')) == before, 'owned directory FD set recovered')
    case('directory-construction-parent-close-failure-does-not-leak-child',
         directory_close_failure, 'real owned directory/FD; explicit close-EIO seam')

    def stderr_overflow():
        c = capture(); c.stderr = bytearray(b'x' * (P.STDERR_BYTES + 1))
        read_fd, write_fd = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        c._take('stderr_read', read_fd)
        try:
            rejected(c._drain_stderr, 'STDERR_BOUND')
            require(not c.stderr_eof, 'zero-length read must not fabricate EOF')
        finally:
            os.close(write_fd); close_capture(c)
    case('stderr-overflow-cannot-fabricate-EOF', stderr_overflow, 'real owned pipe plus bounded-prefix fixture')

    def retirement_no_reads():
        c = capture(); c._failure('original', RuntimeError('ORIGINAL_STOP_FAILURE'))
        c._recv = lambda: (_ for _ in ()).throw(AssertionError('retirement recv forbidden'))
        c._send_token = lambda *args: (_ for _ in ()).throw(AssertionError('retirement token forbidden'))
        result = c.finish('original Stop already returned')
        require(result['held_fds_closed'] and not result['property_visibility_qualified'] and
                result['first_error']['stage'] == 'original' and
                result['retirement_deadline_monotonic_ns'] - result['retirement_started_monotonic_ns'] == 1_000_000_000,
                'separate bounded retirement, no new reads')
    case('retirement-never-receives-property-or-sends-token', retirement_no_reads)

    def owned_child(use_pidfd):
        c = capture(); read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
        parent = os.getpid(); pid = None; reaped = False
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong)
        libc.prctl.restype = ctypes.c_int
        try:
            pid = os.fork()
            if pid == 0:
                try:
                    os.close(read_fd)
                    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != parent:
                        os._exit(90)
                    if os.write(write_fd, b'R') != 1:
                        os._exit(91)
                    os.close(write_fd)
                    while True:
                        signal.pause()
                except BaseException:
                    os._exit(92)
            c.pid = pid; c.record['child_started'] = True
            os.close(write_fd); write_fd = -1
            poller = select.poll(); poller.register(read_fd, select.POLLIN)
            require(poller.poll(1000) and os.read(read_fd, 1) == b'R', 'owned child readiness')
            if use_pidfd:
                c._take('child_pidfd', os.pidfd_open(pid))
            c._failure('original', OSError(errno.EMFILE if not use_pidfd else errno.EIO,
                                           'explicit post-fork admission seam'))
            original = dict(c.record['first_error'])
            c._abort_nonblocking()
            end = time.monotonic() + 1
            while not c.child_reaped and time.monotonic() < end:
                c._reap_nonblocking()
                if not c.child_reaped:
                    time.sleep(.001)
            reaped = c.child_reaped
            require(reaped and c.record['child_returncode'] == -signal.SIGKILL, 'exact direct child reaped')
            require(c.record['first_error'] == original and c.record['child_kill_sent'], 'first error intact')
            before = dict(c.record); c._abort_nonblocking()
            require(c.record == before, 'no second kill after reap')
        finally:
            if pid and pid > 0 and not reaped and not c.child_reaped:
                # Still our unreaped direct child, with default SIGCHLD and no
                # other waiter. Never signal a PID after this fixture reaped it.
                observed = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
                if observed is None:
                    try: os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                cleanup_end = time.monotonic() + 1
                while time.monotonic() < cleanup_end:
                    waited, status = os.waitpid(pid, os.WNOHANG)
                    if waited == pid:
                        reaped = True; break
                    time.sleep(.001)
                require(reaped, 'fixture direct child did not reap within cleanup bound')
            if read_fd >= 0: os.close(read_fd)
            if write_fd >= 0: os.close(write_fd)
            close_capture(c)
    case('real-owned-child-pidfd-kill-and-exact-reap', lambda: owned_child(True),
         'one fresh host child; no exec/setns/chroot/credential change')
    case('post-fork-pidfd-allocation-failure-still-reaps-exact-direct-child', lambda: owned_child(False),
         'one fresh host child; explicit allocation-failure seam, no actual EMFILE pressure')

    def expired_child_timer():
        real_clock = P.time.monotonic_ns; real_signal = P.signal.signal
        real_mask = P.signal.pthread_sigmask; real_set = P.signal.setitimer
        calls = []
        P.time.monotonic_ns = lambda: 1000
        P.signal.signal = lambda *x: calls.append('signal')
        P.signal.pthread_sigmask = lambda *x: calls.append('mask')
        P.signal.setitimer = lambda *x: calls.append('timer')
        try:
            rejected(lambda: P.arm_child_deadline(1000), 'DEADLINE_BEFORE_EXEC')
            require(calls == [], 'expired child admission made no signal change')
        finally:
            P.time.monotonic_ns = real_clock; P.signal.signal = real_signal
            P.signal.pthread_sigmask = real_mask; P.signal.setitimer = real_set
    case('expired-child-budget-does-not-arm-or-reset-signals', expired_child_timer)

    def alarm_gate(which):
        old_disposition = P.signal.getsignal; old_mask = P.signal.pthread_sigmask
        old_timer = P.signal.getitimer; old_clock = P.time.monotonic_ns
        P.signal.getsignal = lambda unused: signal.SIG_IGN if which == 'ignored' else signal.SIG_DFL
        P.signal.pthread_sigmask = lambda *unused: {signal.SIGALRM} if which == 'blocked' else set()
        P.signal.getitimer = lambda unused: (0.5, 0)
        P.time.monotonic_ns = lambda: 100
        try:
            rejected(lambda: P.verify_child_deadline(1000), 'ALARM_NOT_DEFAULT' if which == 'ignored' else 'ALARM_BLOCKED')
        finally:
            P.signal.getsignal = old_disposition; P.signal.pthread_sigmask = old_mask
            P.signal.getitimer = old_timer; P.time.monotonic_ns = old_clock
    case('ignored-SIGALRM-is-rejected-before-exec', lambda: alarm_gate('ignored'))
    case('blocked-SIGALRM-is-rejected-before-exec', lambda: alarm_gate('blocked'))

    def timer_survives_host_exec():
        # Execute only this host Python ELF, held from this process's /proc
        # entry. This is not the Android artifact and enters no namespace.
        exe = os.open('/proc/self/exe', os.O_RDONLY | os.O_CLOEXEC)
        read_fd, write_fd = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        pid = None; reaped = False; pidfd = None
        parent = os.getpid()
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong)
        libc.prctl.restype = ctypes.c_int
        try:
            s = os.fstat(exe)
            require(stat.S_ISREG(s.st_mode) and 0 < s.st_size <= 32*1024*1024, 'current host Python bound')
            body = os.pread(exe, s.st_size + 1, 0)
            require(len(body) == s.st_size and body[:4] == b'\x7fELF', 'current host Python ELF')
            host_elf_sha = hashlib.sha256(body).hexdigest()
            code = 'import os,signal; os.write(' + str(write_fd) + ',b"E"); signal.pause()'
            pid = os.fork()
            if pid == 0:
                try:
                    os.close(read_fd)
                    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != parent:
                        os._exit(94)
                    os.set_inheritable(write_fd, True)
                    deadline = time.monotonic_ns() + 500_000_000
                    P.arm_child_deadline(deadline)
                    P.verify_child_deadline(deadline)
                    os.execve(exe, ['owner20-host-timer-control', '-I', '-B', '-c', code],
                              {'PATH': '/usr/bin:/bin', 'LANG': 'C'})
                except BaseException:
                    os._exit(95)
            os.close(write_fd); write_fd = -1
            pidfd = os.pidfd_open(pid)
            poller = select.poll(); poller.register(read_fd, select.POLLIN)
            require(poller.poll(1500) and os.read(read_fd, 1) == b'E', 'fixed host exec actually reached its code')
            poller = select.poll(); poller.register(pidfd, select.POLLIN)
            require(poller.poll(1500), 'child timer did not terminate fixed host exec')
            waited, status = os.waitpid(pid, os.WNOHANG)
            reaped = waited == pid
            require(reaped and os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGALRM,
                    'exec-preserved interval timer actual terminal')
            require(hashlib.sha256(os.pread(exe, s.st_size + 1, 0)).hexdigest() == host_elf_sha,
                    'held host executable unchanged')
        finally:
            if pid and pid > 0 and not reaped:
                observed = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
                if observed is None:
                    try: os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                end = time.monotonic() + 1
                while time.monotonic() < end:
                    waited, status = os.waitpid(pid, os.WNOHANG)
                    if waited == pid:
                        reaped = True; break
                    time.sleep(.001)
                require(reaped, 'host timer fixture cleanup did not reap')
            if pidfd is not None: os.close(pidfd)
            if read_fd >= 0: os.close(read_fd)
            if write_fd >= 0: os.close(write_fd)
            os.close(exe)
    case('real-single-host-exec-keeps-child-interval-timer-and-reaps',
         timer_survives_host_exec, 'one host Python exec; no Android ELF/namespace/credential changes')

    def actor_boundaries():
        old = ast.parse(baseline_actor_text); new = ast.parse(actor_text)
        old_defs = {n.name: ast.dump(n, include_attributes=False) for n in old.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        new_defs = {n.name: ast.dump(n, include_attributes=False) for n in new.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        require(old_defs.keys() == new_defs.keys() and
                [k for k in old_defs if old_defs[k] != new_defs[k]] == ['load', 'run'], 'only two actor functions')
        require("end = time.monotonic() + 65" in actor_text and
                actor_text.count("modules['property_visibility'].Capture(") == 1, 'one capture in old window')
        stop = actor_text.index("result['failure_cleanup_stop'] =")
        retire = actor_text.index("for child in reversed(children):", stop)
        finish = actor_text.index("observation = property_capture.finish(", retire)
        require(stop < retire < finish and "property_visibility_is_actual_LMKD_or_cold_cache'] = False" in actor_text,
                'unchanged Stop before new child finish and scope false')
    case('actor-only-load-run-delta-and-original-Stop-order', actor_boundaries, 'source AST and exact call-site control')
    require(len(rows) == 38, 'fixed control count')
    return {'schema': 1, 'kind': 'owner20-property-host-controls01', 'success': True,
        'controls': rows, 'count': len(rows), 'Android_executed': False, 'property_reads_or_writes': False,
        'namespace_entry_or_UID_changes': False, 'Main_access': False,
        'runtime_source_or_bionic_qualified': False, 'same_process_root_warmed_cache_remains': True}
