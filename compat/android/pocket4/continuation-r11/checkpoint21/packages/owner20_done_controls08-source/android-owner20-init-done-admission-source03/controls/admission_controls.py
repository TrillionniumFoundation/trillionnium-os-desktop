"""Actual actor-loop admission and child exec-view regressions.

The run-loop AST, admission helper, ABI3 validator, child view and failure parser
are the exact production functions. Process, namespace and file interfaces are
explicit synthetic seams. No Android executable, real child, namespace, Main
object or property is accessed. These controls do not qualify a normal run.
"""
import ast
import copy
import errno
import hashlib
import json
import stat
import struct
import types

ACTUAL_SAFE_SHA = 'a6d96c0d48c8ea2ba7f8d2b397a8aa53d7a8a60a3e9bcd3b0d06bfb83d274405'
ACTUAL_RUNTIME_SHA = '7f91108de0fbec45051dae9cb8ca8e43e6bb99986915d51f74bd2d4f6dfc843e'
BASELINE_ACTOR_SHA = 'e4edd2d14f8a699ab2bef35dd77313c06e260768414efe14d38553eddbb6c141'
BASELINE_PROPERTY_SHA = 'e5d993f3bc05cebb4c61c44c84976fca491c10714799a684fed16ef85cd87f8d'
QUALIFY_SHA = 'a843d4a0ac4da1dd1baa8707ff3d0f59e4ed4c3cd26fd6fa1eae2ed9f21a6fad'

def require(value, message):
    if not value:
        raise AssertionError(message)

def run(P, sources, observer, unused_capture_observer, diagnostics):
    rows = diagnostics['controls']
    for name, expected in (('actual-safe.json', ACTUAL_SAFE_SHA),
            ('baseline_actor.py', BASELINE_ACTOR_SHA),
            ('baseline_property_visibility.py', BASELINE_PROPERTY_SHA),
            ('qualify.py', QUALIFY_SHA)):
        require(hashlib.sha256(sources[name].encode()).hexdigest() == expected,
                'exact source/actual authority: ' + name)
    safe = json.loads(sources['actual-safe.json'])
    require(safe['original_runtime'] == {'bytes': 817470, 'sha256': ACTUAL_RUNTIME_SHA} and
            safe['original_full_hash_and_bytes_verified'] is True and
            safe['raw_init_log_or_crash_packet_exported'] is False,
            'actual safe projection authority')
    actual_actor = safe['runtime']['actor_result']
    actual = actual_actor['property_visibility_observation']
    require(actual['child_setup_failure']['stage'] == 'exact_android_exec' and
            actual['child_setup_failure']['errno'] == errno.ENOENT and
            actual['child_reaped'] is True and actual['spawn_attempts'] == 1 and
            actual['start_token_attempts'] == actual['finish_token_attempts'] == 0 and
            len(actual['init_current_checks']) == 1, 'actual ENOENT shape')
    original_audit = actual_actor['latest_status']['relay_lifecycle']
    first_eight = original_audit['records'][:8]
    require(first_eight[-1]['detail']['event'] == 'init_done_accepted' and
            actual['started_monotonic_ns'] < first_eight[-1]['observed_monotonic_ns'],
            'actual pre-DONE observer timing')
    original_clock = actual_actor['init_identity_clock_observation']
    original_snapshot = original_clock['snapshot']
    original_plan = {'canonical_spec_sha256': original_audit['canonical_spec_sha256'],
                     'spec': {'host_uid': original_audit['host_uid']}}
    def case(name, function):
        before = observer('before', name)
        primary = None
        details = None
        try:
            details = function()
        except BaseException as error:
            primary = error
        after = None
        try:
            after = observer('after', name, before)
        except BaseException as error:
            if primary is None:
                primary = error
            else:
                primary.add_note('host FD equality: ' + repr(error)[:160])
        row = {'name': name, 'passed': primary is None,
               'scope': 'exact production AST/functions; explicit clock/process/file/constructor seams',
               'before_fd_snapshot': before, 'after_fd_snapshot': after}
        if details is not None:
            row['details'] = details
        if primary is not None:
            row['error'] = {'type': type(primary).__name__, 'error': repr(primary)[:512]}
        rows.append(row)
        if primary is not None:
            raise primary

    # Load actor normally: its module top level is imports, definitions and a
    # __main__ guard. Qualify's sole imported need is replaced by the same
    # fail-closed predicate; its remaining source AST is unchanged.
    A = types.ModuleType('owner20_done_admission_actor')
    exec(compile(sources['actor.py'], 'actor.py', 'exec'), A.__dict__)
    B = types.ModuleType('owner20_pre_DONE_actual_actor')
    exec(compile(sources['baseline_actor.py'], 'baseline_actor.py', 'exec'), B.__dict__)
    qtree = ast.parse(sources['qualify.py'])
    require(isinstance(qtree.body[1], ast.ImportFrom) and
            qtree.body[1].module == 'pinned_support' and
            [x.name for x in qtree.body[1].names] == ['need'], 'sole qualifier import seam')
    qtree.body[1] = ast.Pass()
    Q = types.ModuleType('owner20_unchanged_abi3_qualifier')
    Q.need = P.need
    exec(compile(ast.fix_missing_locations(qtree), 'qualify.py', 'exec'), Q.__dict__)

    def named(tree, name):
        return next(x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x.name == name)
    def ast_equal(left, right):
        return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)
    def run_loop(module, source):
        tree = ast.parse(source)
        main = named(tree, 'run')
        main_try = next(x for x in main.body if isinstance(x, ast.Try))
        loops = [(i, x) for i, x in enumerate(main_try.body) if isinstance(x, ast.While) and
                 any(isinstance(n, ast.Constant) and n.value == 'latest_status' for n in ast.walk(x))]
        require(len(loops) == 1, 'exact one original status loop')
        index, loop = loops[0]
        end = main_try.body[index - 1]
        require(isinstance(end, ast.Assign) and isinstance(end.value, ast.BinOp) and
                isinstance(end.value.right, ast.Constant) and end.value.right.value == 65,
                'original 65-second assignment')
        following = main_try.body[index + 1]
        require(any(isinstance(n, ast.Constant) and n.value ==
                    'actual native enrollment ACTIVE deadline exceeded' for n in ast.walk(following)),
                'original no-ACTIVE failure follows loop')
        header = ast.parse('def extracted_actual_run_loop(context):\n    pass\n').body[0]
        names = ('owned', 'plan', 'prepared', 'modules', 'tools', 'evidence', 'held', 'result',
                 'daemon', 'socket_id', 'crash_capture', 'crash_capture_attempted',
                 'property_capture', 'property_capture_attempted', 'property_admission')
        assignments = [ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())],
                       value=ast.Subscript(value=ast.Name(id='context', ctx=ast.Load()),
                       slice=ast.Constant(name), ctx=ast.Load())) for name in names]
        header.body = assignments + [copy.deepcopy(end), copy.deepcopy(loop), copy.deepcopy(following)]
        exec(compile(ast.fix_missing_locations(ast.Module(body=[header], type_ignores=[])),
                     'actual_run_loop_AST.py', 'exec'), module.__dict__)
        return module.extracted_actual_run_loop

    candidate_loop = run_loop(A, sources['actor.py'])
    baseline_loop = run_loop(B, sources['baseline_actor.py'])
    def fresh_admission():
        tree = ast.parse(sources['actor.py'])
        main = named(tree, 'run')
        node = next(x for x in main.body if isinstance(x, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == 'property_admission' for t in x.targets))
        return ast.literal_eval(node.value)

    class Clock:
        def __init__(self):
            self.start = actual['started_monotonic_ns']
            self.now = self.start
        def monotonic_ns(self):
            return self.now
        def monotonic(self):
            return self.now / 1_000_000_000
        def sleep(self, seconds):
            require(seconds == 0.05, 'unchanged original polling interval')
            self.now += 50_000_000

    def live_audit(length=8):
        audit = copy.deepcopy(original_audit)
        audit['records'] = copy.deepcopy(first_eight[:length])
        audit.update(first_failure=None, retirement_failure=None, cleanup_failure=None,
                     recording_error=None, recording_incomplete=False, retained_after_exit=False)
        return audit

    def exercise_loop(variant, baseline=False):
        clock = Clock()
        calls = []
        statuses = []
        live_calls = [0]
        module, execute = (B, baseline_loop) if baseline else (A, candidate_loop)
        old_time = module.time
        class Init:
            def live(self):
                live_calls[0] += 1
            def snapshot(self):
                value = copy.deepcopy(original_snapshot)
                if variant == 'stale_init':
                    value['process']['birth'] += 1
                return value
        init = Init()
        admission = fresh_admission()
        result = {'init_identity_clock_observation': copy.deepcopy(original_clock),
                  'property_visibility_admission': admission}
        calls_to_control = [0]
        class Owned:
            need = staticmethod(P.need)
            def control(self, path, process, identity, command, timeout):
                require(command == {'command': 'status'} and timeout == 4,
                        'original one status call shape')
                calls_to_control[0] += 1
                count = calls_to_control[0]
                if variant == 'original_failure':
                    return {'ok': True, 'state': 'stopped', 'relay_lifecycle': live_audit(3)}
                if variant == 'never_done':
                    audit = live_audit(3)
                elif variant in ('hello_only', 'original_failure') and count == 1:
                    audit = live_audit(3)
                elif variant == 'late_done' and count == 1:
                    clock.now = clock.start + 63_500_000_000
                    audit = live_audit()
                    audit['records'][7]['observed_monotonic_ns'] = clock.now
                elif variant == 'delayed_done' and count == 1:
                    audit = live_audit(3)
                elif count == 1 or (variant == 'delayed_done' and count == 2):
                    audit = live_audit()
                    clock.now = max(clock.now, audit['records'][-1]['observed_monotonic_ns'] + 1_000_000)
                    if variant == 'wrong_generation':
                        audit['nonce'] = '1' * 64
                    elif variant == 'wrong_DONE_generation':
                        wire = bytearray.fromhex(audit['records'][7]['detail']['wire_hex'])
                        wire[16] ^= 1
                        audit['records'][7]['detail']['wire_hex'] = wire.hex()
                    elif variant == 'duplicate_done':
                        audit['records'].append(copy.deepcopy(audit['records'][7]))
                    elif variant == 'active':
                        audit['records'].append({'sequence': 9, 'observed_monotonic_ns': clock.now,
                                                 'detail': {'event': 'broker_active'}})
                else:
                    return {'ok': True, 'state': 'stopped', 'relay_lifecycle': live_audit()}
                statuses.append(copy.deepcopy(audit['records'][-1]['detail']['event']))
                return {'ok': True, 'state': 'running', 'relay_lifecycle': audit}
        owned = Owned()
        def constructor(*args):
            require(len(args) == 8 and args[0] is init and args[2] is plan and
                    args[3] is prepared and args[4:7] == (20001, 20002, owned),
                    'actual production call must pass all held authority arguments unchanged')
            calls.append({'at_ns': clock.now, 'last_event': args[1]['records'][-1]['detail']['event'],
                          'nonce': args[1]['nonce']})
            if variant == 'constructor_error':
                raise OSError(errno.EIO, 'explicit constructor seam')
            return types.SimpleNamespace(poll=lambda: None)
        plan = dict(copy.deepcopy(original_plan), control_socket='synthetic-owned-socket')
        prepared = {'fixture_only': True}
        modules = {'owned': owned, 'qualify': Q,
                   'property_visibility': types.SimpleNamespace(Capture=constructor)}
        context = {'owned': owned, 'plan': plan, 'prepared': prepared, 'modules': modules,
            'tools': {'sdk-visibility': 20001}, 'evidence': 20002, 'held': {'init': init},
            'result': result, 'daemon': types.SimpleNamespace(process=object()), 'socket_id': object(),
            'crash_capture': None, 'crash_capture_attempted': True,
            'property_capture': None, 'property_capture_attempted': False,
            'property_admission': admission}
        failure = None
        try:
            module.time = clock
            execute(context)
        except BaseException as error:
            failure = str(error)
        finally:
            module.time = old_time
        return {'construction_calls': len(calls), 'calls': calls, 'status_calls': calls_to_control[0],
                'admission': admission, 'original_loop_error': failure,
                'held_init_live_checks': live_calls[0],
                'active_immediate_break': 'active_response' in result,
                'new_real_child_or_device_action': False}

    def stopped(value):
        require(value['original_loop_error'] == 'actual producer stopped or failed before ACTIVE',
                'observer must retain original producer failure')
    def old_early():
        value = exercise_loop('hello_only', True)
        stopped(value)
        require(value['construction_calls'] == 1 and value['calls'][0]['last_event'] == 'init_hello',
                'old actual HELLO-only wiring reproduced')
        return value
    def blocked(variant, reason=None):
        value = exercise_loop(variant)
        if variant != 'never_done':
            stopped(value)
        require(value['construction_calls'] == 0, 'no constructor before exact admission')
        if reason:
            require(value['admission']['closed'] and reason in
                    value['admission']['first_error']['error'], 'exact admission rejection')
        return value
    def ready_once(variant):
        value = exercise_loop(variant)
        stopped(value)
        require(value['construction_calls'] == 1 and value['calls'][0]['last_event'] == 'init_done_accepted' and
                value['admission']['construction_attempts'] == 1 and value['admission']['closed'] and
                value['held_init_live_checks'] == 2 and
                value['calls'][0]['at_ns'] >= first_eight[-1]['observed_monotonic_ns'],
                'one constructor only after accepted DONE and held-init recheck')
        if variant == 'constructor_error':
            require(value['admission']['first_error']['errno'] == errno.EIO,
                    'constructor first error preserved without retry')
        else:
            require(value['admission']['state'] == 'CONSTRUCTION_RETURNED' and
                    value['admission']['first_error'] is None, 'constructor call returned')
        return value
    def never_ready():
        value = blocked('never_done')
        require(value['original_loop_error'] == 'actual native enrollment ACTIVE deadline exceeded' and
                'SDK_ADMISSION_WINDOW_EXHAUSTED' in value['admission']['first_error']['error'],
                'same 65-second outer deadline and no late constructor')
        return value
    def active_immediate():
        value = exercise_loop('active')
        require(value['construction_calls'] == 0 and value['active_immediate_break'] and
                value['original_loop_error'] is None, 'original ACTIVE wins before observation')
        return value

    def elf_fixture(interpreter=None):
        raw = bytearray(512)
        phnum = 3 if interpreter else 2
        struct.pack_into('<16sHHIQQQIHHHHHH', raw, 0,
            b'\x7fELF\x02\x01\x01' + bytes(9), 3, 62, 1, 128, 64, 0, 0,
            64, 56, phnum, 0, 0, 0)
        struct.pack_into('<IIQQQQQQ', raw, 64, 1, 5, 0, 0, 0, len(raw), len(raw), 4096)
        struct.pack_into('<IIQQQQQQ', raw, 120, 4, 4, 384, 384, 0, 32, 32, 4)
        struct.pack_into('<III', raw, 384, 4, 16, 3)
        raw[396:400] = b'GNU\0'
        raw[400:416] = bytes(range(16))
        if interpreter:
            name = interpreter.encode('ascii') + b'\0'
            raw[256:256 + len(name)] = name
            struct.pack_into('<IIQQQQQQ', raw, 176, 3, 4, 256, 256, 0, len(name), len(name), 1)
        return bytes(raw)

    def statrow(row):
        return types.SimpleNamespace(st_dev=row['device'], st_ino=row['inode'], st_mode=row['mode'],
            st_uid=row['uid'], st_gid=row['gid'], st_nlink=row['nlink'], st_size=row['bytes'],
            st_mtime_ns=row['mtime_ns'], st_ctime_ns=row['ctime_ns'])
    def fixture_meta(inode, size=512):
        return {'device': 123, 'inode': inode, 'mode': stat.S_IFREG | 0o555,
                'uid': 0, 'gid': 0, 'nlink': 1, 'bytes': size, 'mtime_ns': 123456, 'ctime_ns': 234567}

    def exercise_view(variant='visible', child=False):
        helper_body = elf_fixture('/system/bin/linker64')
        linker_body = elf_fixture()
        helper_meta = fixture_meta(10)
        linker_meta = fixture_meta(11)
        root = {'device': 456, 'inode': 1}
        root_meta = dict(fixture_meta(1), device=456, mode=stat.S_IFDIR | 0o755, bytes=0)
        helper_fd, interpreter_fd = 30001, 30002
        deadline = 3_000_000_000
        clock = types.SimpleNamespace(now=1_000_000_000)
        def now():
            clock.now += 1000
            return clock.now
        clock.monotonic_ns = now
        calls = {'open': [], 'close': [], 'read': [], 'exec': [], 'namespace': [], 'packets': [],
                 'reads_after_deadline': 0, 'expired_read_done': False}
        open_fds = set()
        view = {}
        mutation = dict(linker_meta)
        if variant == 'interpreter_writable':
            mutation['mode'] |= 0o020
        elif variant == 'interpreter_special':
            mutation['mode'] |= 0o4000
        elif variant == 'interpreter_owner':
            mutation['uid'] = 1069
        elif variant == 'interpreter_nonregular':
            mutation['mode'] = stat.S_IFIFO | 0o555
        elif variant == 'interpreter_oversize':
            mutation['bytes'] = P.LIBRARY_BYTES + 1
        class FakeOS:
            def __getattr__(self, name):
                if name.startswith('O_'):
                    return getattr(real['os'], name)
                raise AssertionError('unapproved OS seam: ' + name)
            def fstat(self, fd):
                if fd == helper_fd:
                    m = dict(helper_meta)
                    if variant == 'helper_identity':
                        m['inode'] += 1
                    return statrow(m)
                require(fd == interpreter_fd and fd in open_fds, 'only live synthetic interpreter FD')
                return statrow(mutation)
            def stat(self, path):
                if path == '/':
                    return statrow(root_meta)
                require(path == '/system/bin/linker64' and interpreter_fd in open_fds,
                        'one fixed named path only')
                m = dict(mutation)
                if variant == 'interpreter_name_race':
                    m['inode'] += 1
                return statrow(m)
            def get_inheritable(self, fd):
                require(fd in (helper_fd, interpreter_fd), 'only held source FD flag')
                return False
            def pread(self, fd, count, offset):
                require(fd in (helper_fd, interpreter_fd), 'only source FD bytes')
                if clock.now >= deadline:
                    calls['reads_after_deadline'] += 1
                calls['read'].append((fd, count, offset))
                if fd == interpreter_fd and variant == 'interpreter_read_error':
                    raise OSError(errno.EIO, 'explicit read seam')
                if fd == interpreter_fd and variant == 'read_and_close_error':
                    raise OSError(errno.EIO, 'explicit first read seam')
                body = helper_body if fd == helper_fd else linker_body
                if fd == helper_fd and variant == 'helper_hash':
                    body = body[:-1] + b'\x01'
                if fd == interpreter_fd and variant == 'interpreter_truncated' and offset == 0:
                    return b''
                part = body[offset:offset + count]
                if fd == interpreter_fd and variant == 'deadline' and offset == 0:
                    clock.now = deadline
                    calls['expired_read_done'] = True
                return part
            def open(self, path, flags):
                require(path == '/system/bin/linker64' and flags ==
                        (self.O_RDONLY | self.O_CLOEXEC | self.O_NONBLOCK),
                        'one bounded fixed interpreter open')
                calls['open'].append(path)
                if variant == 'interpreter_missing':
                    raise FileNotFoundError(errno.ENOENT, 'explicit absent fixed interpreter')
                require(not open_fds, 'no repeated interpreter open')
                open_fds.add(interpreter_fd)
                return interpreter_fd
            def close(self, fd):
                calls['close'].append(fd)
                if fd == interpreter_fd:
                    require(fd in open_fds, 'interpreter closed exactly once')
                    # The seam simulates Linux close retiring the descriptor but
                    # reporting EIO. Production must not retry or claim closed.
                    open_fds.remove(fd)
                    if variant in ('close_error', 'read_and_close_error'):
                        raise OSError(errno.EIO, 'explicit close seam')
                else:
                    require(child and fd in inherited and fd not in
                            (helper_fd, child_socket_fd, actor_pidfd, 1, 2),
                            'only declared inherited synthetic FD retired')
            def getppid(self):
                return 111
            def getpid(self):
                return 222
            def write(self, fd, body):
                require(child and fd == domain_fd and body == b'222', 'one child cgroup seam')
                return len(body)
            def setns(self, fd, flags):
                require(child and flags == 0 and fd in namespaces.values(), 'exact namespace seam')
                calls['namespace'].append(fd)
            def fchdir(self, fd):
                require(child and fd == root_fd, 'held root seam')
            def chroot(self, path):
                require(child and path == '.', 'exact chroot seam')
            def chdir(self, path):
                require(child and path == '/', 'exact cwd seam')
            def dup2(self, source, target, inheritable):
                require(child and source == stderr_fd and target in (1, 2) and inheritable is True,
                        'original stderr wiring seam')
            def set_inheritable(self, fd, flag):
                require(child and ((fd in (child_socket_fd, actor_pidfd) and flag is True) or
                        (fd == helper_fd and flag is False)), 'original exec FD policy')
            def execve(self, fd, argv, env):
                require(child and fd == helper_fd and argv == ['sdk-visibility', 'fixture-only'] and
                        env == {'fixture_only': 'true'}, 'one held-FD exec seam')
                calls['exec'].append(fd)
                raise FileNotFoundError(errno.ENOENT, 'explicit exec failure after source visibility')
            def _exit(self, status):
                require(child and status == 127, 'original setup-failure exit')
                raise ChildExited()
        class ChildExited(BaseException):
            pass
        class Fcntl:
            F_GETFL = P.fcntl.F_GETFL
            def fcntl(self, fd, command):
                require(fd in (helper_fd, interpreter_fd) and command == self.F_GETFL,
                        'read-only flag seam')
                return real['os'].O_RDONLY
        real = {name: getattr(P, name) for name in
                ('os', 'fcntl', 'time', 'HELPER_BYTES', 'HELPER_SHA256',
                 'arm_child_deadline', 'verify_child_deadline', 'resource')}
        fake_os = FakeOS()
        failure = None
        child_socket_fd, actor_pidfd, domain_fd, root_fd, stderr_fd = 30003, 30004, 30005, 30006, 30007
        namespaces = {name: 30100 + i for i, name in enumerate(P.JOIN_NAMES)}
        inherited = [helper_fd, child_socket_fd, actor_pidfd, domain_fd, root_fd, stderr_fd,
                     *namespaces.values()]
        try:
            P.os = fake_os
            P.fcntl = Fcntl()
            P.time = clock
            P.HELPER_BYTES = len(helper_body)
            P.HELPER_SHA256 = hashlib.sha256(helper_body).hexdigest()
            if not child:
                try:
                    P.child_execution_view(view, helper_fd, helper_meta, root, deadline)
                except BaseException as error:
                    failure = error
                # Run the production closed-field validator on both success and
                # partial failure facts. It never grants successful SDK proof.
                P.execution_view_record(view, 1_000_000_000, deadline)
            else:
                def alarm_seam(actual_deadline):
                    require(actual_deadline == deadline, 'same absolute observation deadline')
                    return clock.now
                P.arm_child_deadline = P.verify_child_deadline = alarm_seam
                P.resource = types.SimpleNamespace(RLIMIT_CORE=real['resource'].RLIMIT_CORE,
                    setrlimit=lambda kind, bounds: require(kind == real['resource'].RLIMIT_CORE and
                                                         bounds == (0, 0), 'original core limit'))
                class Socket:
                    def fileno(self):
                        return child_socket_fd
                    def send(self, raw, flags):
                        require(flags == P.socket.MSG_DONTWAIT | P.socket.MSG_NOSIGNAL and
                                len(raw) <= P.PACKET_BYTES, 'one bounded setup-failure datagram')
                        calls['packets'].append(raw)
                        return len(raw)
                c = P.Capture.__new__(P.Capture)
                c.actor_pid = 111
                c.libc = types.SimpleNamespace(prctl=lambda *args: 0)
                c.deadline = deadline
                c.fds = {'helper': helper_fd, 'actor_pidfd': actor_pidfd,
                         'child_domain_procs': domain_fd, 'root': root_fd, 'stderr_write': stderr_fd}
                c.fds.update({'init_ns_' + name: fd for name, fd in namespaces.items()})
                c.helper_meta = helper_meta
                c.record = {'init_root': root_meta}
                c.nonce = original_audit['nonce']
                c.child_sock = Socket()
                try:
                    c._child(inherited, ['sdk-visibility', 'fixture-only'], {'fixture_only': 'true'})
                except ChildExited:
                    pass
                require(len(calls['packets']) == 1, 'one original failure message only')
                packet = P.strict_json(calls['packets'][0])
                view = packet['execution_view']
                require(packet['nonce'] == c.nonce and packet['errno'] == errno.ENOENT,
                        'exact child first error retained')
                P.execution_view_record(view, 1_000_000_000, deadline)
                sink = P.Capture.__new__(P.Capture)
                sink.nonce = c.nonce
                sink.started = 1_000_000_000
                sink.deadline = deadline
                sink.record = {}
                try:
                    sink._accept(packet, (222, 0, 0), [])
                except RuntimeError as error:
                    require(str(error) == 'SDK_CHILD_SETUP_FAILED', 'original failure parser result')
                else:
                    raise AssertionError('setup failure must never become SDK success')
                require(sink.record.get('child_setup_failure') == packet, 'exact bounded facts retained')
                require(len(calls['exec']) == (0 if variant == 'interpreter_missing' else 1),
                        'no exec on missing interpreter; one failed exec after visibility')
                require(packet['stage'] == ('execution_view' if variant == 'interpreter_missing'
                                           else 'exact_android_exec'), 'failure stage distinction')
        finally:
            for name, value in real.items():
                setattr(P, name, value)
        require(not open_fds, 'all synthetic newly opened descriptors retired')
        require(helper_fd not in calls['close'], 'borrowed held ELF FD not closed by view')
        require(calls['reads_after_deadline'] == 0, 'no new source byte read after observation deadline')
        return {'view': view, 'failure': failure, 'calls': calls,
                'synthetic_fds_retired': True, 'real_file_or_process_access': False}

    def brief_view(value):
        view = value['view']
        return {'complete': view['complete'], 'first_error': view['first_error'],
                'close_error': view['close_error'], 'root_matches_held': view['root_matches_held'],
                'helper_full_hash_recorded': view['helper'] is not None,
                'interpreter_full_hash_recorded': view['interpreter'] is not None,
                'interpreter_open_attempts': len(value['calls']['open']),
                'interpreter_close_attempts': value['calls']['close'].count(30002),
                'interpreter_fd_closed_record': view['interpreter_fd_closed'],
                'new_byte_reads_after_deadline': value['calls']['reads_after_deadline'],
                'exec_seam_calls': len(value['calls']['exec']),
                'setup_failure_packets': len(value['calls']['packets']),
                'synthetic_fds_retired': value['synthetic_fds_retired'],
                'real_Android_exec': False}
    def visible_view():
        value = exercise_view()
        require(value['failure'] is None and value['view']['complete'] and
                value['view']['helper']['sha256'] and value['view']['interpreter']['sha256'] and
                value['view']['interpreter_named_matches_held'] and
                value['view']['interpreter_fd_closed'], 'complete bounded fixed view')
        return brief_view(value)
    def rejected_view(variant, stage, code=None):
        value = exercise_view(variant)
        require(value['failure'] is not None and not value['view']['complete'] and
                value['view']['first_error']['stage'] == stage, 'exact view rejection stage')
        if code is not None:
            require(value['view']['first_error']['errno'] == code, 'first errno preserved')
        if variant == 'deadline':
            require(str(value['failure']) == 'SDK_EXEC_VIEW_DEADLINE', 'shared original deadline error')
        if variant == 'read_and_close_error':
            require(value['view']['close_error']['errno'] == errno.EIO and
                    value['view']['first_error']['stage'] == 'interpreter_source',
                    'close error cannot replace earlier read failure')
        return brief_view(value)
    def actual_child(variant):
        return brief_view(exercise_view(variant, child=True))

    def production_boundary():
        old_a, new_a = ast.parse(sources['baseline_actor.py']), ast.parse(sources['actor.py'])
        old_names = {x.name: x for x in old_a.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))}
        new_names = {x.name: x for x in new_a.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))}
        require(set(new_names) == set(old_names) | {'property_capture_step'}, 'one actor helper added')
        for name in old_names:
            if name != 'run':
                require(ast_equal(old_names[name], new_names[name]), 'unrelated actor function changed: ' + name)
        old_try = next(x for x in old_names['run'].body if isinstance(x, ast.Try))
        new_try = next(x for x in new_names['run'].body if isinstance(x, ast.Try))
        require(ast.dump(ast.Module(body=old_try.finalbody, type_ignores=[]), include_attributes=False) ==
                ast.dump(ast.Module(body=new_try.finalbody, type_ignores=[]), include_attributes=False),
                'original Stop/child retirement/finally remains exact AST')
        pold, pnew = ast.parse(sources['baseline_property_visibility.py']), ast.parse(sources['property_visibility.py'])
        before = {x.name: x for x in pold.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))}
        after = {x.name: x for x in pnew.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))}
        require(set(after) == set(before) | {'child_execution_view', 'execution_view_record'},
                'only fixed view functions added')
        for name in before:
            if name != 'Capture':
                require(ast_equal(before[name], after[name]), 'original property function changed: ' + name)
        old_methods = {x.name: x for x in before['Capture'].body if isinstance(x, ast.FunctionDef)}
        new_methods = {x.name: x for x in after['Capture'].body if isinstance(x, ast.FunctionDef)}
        require(set(old_methods) == set(new_methods), 'no new Capture runtime methods')
        for name in old_methods:
            if name not in ('_child', '_accept'):
                require(ast_equal(old_methods[name], new_methods[name]), 'original Capture method changed: ' + name)
        original_imports = [x for x in pold.body if isinstance(x, (ast.Import, ast.ImportFrom))]
        candidate_imports = [x for x in pnew.body if isinstance(x, (ast.Import, ast.ImportFrom))]
        require(ast_equal(ast.Module(body=original_imports, type_ignores=[]),
                          ast.Module(body=candidate_imports, type_ignores=[])), 'no import lifecycle change')
        require(sources['property_visibility.py'].count('os.execve(self.fds[\'helper\'], argv, env)') == 1 and
                sources['property_visibility.py'].count('pid = os.fork()') == 1 and
                sources['property_visibility.py'].count("b'READ_ROOT_AND_1069:'") == 1 and
                sources['property_visibility.py'].count("b'OBSERVED:'") == 1,
                'one child/one exec/original two tokens only')
        child = new_methods['_child']
        view_calls = [n for n in ast.walk(child) if isinstance(n, ast.Call) and
                      isinstance(n.func, ast.Name) and n.func.id == 'child_execution_view']
        exec_calls = [n for n in ast.walk(child) if isinstance(n, ast.Call) and
                      isinstance(n.func, ast.Attribute) and n.func.attr == 'execve']
        require(len(view_calls) == len(exec_calls) == 1 and view_calls[0].lineno < exec_calls[0].lineno,
                'actual child calls fixed visibility function before its one exec')
        return {'original_actor_finally_AST_unchanged': True,
                'original_Capture_constructor_init_binding_tokens_poll_finish_AST_unchanged': True,
                'one_child_one_exec_no_retry': True, 'original_two_second_deadline_and_65_second_Stop': True}

    def reject_unbounded_view():
        value = exercise_view()
        row = copy.deepcopy(value['view'])
        row['raw_file_body'] = 'not permitted'
        try:
            P.execution_view_record(row, 1_000_000_000, 3_000_000_000)
        except RuntimeError as error:
            require(str(error) == 'SDK_EXEC_VIEW_RECORD', 'closed metadata fields')
        else:
            raise AssertionError('unbounded body accepted')
        return {'unknown_fields_rejected': True, 'no_file_body_export': True}

    case('source-delta-preserves-original-Stop-tokens-constructor-and-retirement', production_boundary)
    case('baseline-real-run-loop-reproduces-HELLO-only-early-construction', old_early)
    case('candidate-real-run-loop-HELLO-only-does-not-construct', lambda: blocked('hello_only'))
    case('candidate-real-run-loop-delayed-DONE-constructs-once', lambda: ready_once('delayed_done'))
    case('candidate-real-run-loop-ready-within-window-constructs-once', lambda: ready_once('ready'))
    case('candidate-real-run-loop-wrong-generation-rejected', lambda: blocked('wrong_generation', 'SDK_ADMISSION_GENERATION_CHANGED'))
    case('candidate-real-run-loop-DONE-wire-wrong-generation-rejected', lambda: blocked('wrong_DONE_generation', 'init ABI3/phase/actual nonce differs'))
    case('candidate-real-run-loop-duplicate-DONE-rejected', lambda: blocked('duplicate_done', 'SDK_ADMISSION_EVENT_ORDER'))
    case('candidate-real-run-loop-late-DONE-cannot-extend-window', lambda: blocked('late_done', 'SDK_ADMISSION_WINDOW_EXHAUSTED'))
    case('candidate-real-run-loop-never-DONE-keeps-original-deadline', never_ready)
    case('candidate-real-run-loop-stale-held-init-rejected', lambda: blocked('stale_init', 'SDK_ADMISSION_HELD_INIT_CHANGED'))
    case('candidate-real-run-loop-constructor-first-error-not-retried', lambda: ready_once('constructor_error'))
    case('candidate-real-run-loop-ACTIVE-takes-original-immediate-exit', active_immediate)
    case('candidate-real-run-loop-producer-failure-remains-independent', lambda: blocked('original_failure'))
    case('child-fixed-view-complete-helper-and-interpreter-source', visible_view)
    case('child-fixed-view-missing-interpreter-preserves-ENOENT', lambda: rejected_view('interpreter_missing', 'interpreter_open', errno.ENOENT))
    case('child-fixed-view-held-helper-identity-differs', lambda: rejected_view('helper_identity', 'held_helper'))
    case('child-fixed-view-helper-full-hash-differs', lambda: rejected_view('helper_hash', 'held_helper'))
    case('child-fixed-view-nonregular-interpreter-closed', lambda: rejected_view('interpreter_nonregular', 'interpreter_metadata'))
    case('child-fixed-view-writable-interpreter-closed', lambda: rejected_view('interpreter_writable', 'interpreter_metadata'))
    case('child-fixed-view-setid-interpreter-closed', lambda: rejected_view('interpreter_special', 'interpreter_metadata'))
    case('child-fixed-view-wrong-owner-interpreter-closed', lambda: rejected_view('interpreter_owner', 'interpreter_metadata'))
    case('child-fixed-view-oversize-interpreter-rejected-before-body', lambda: rejected_view('interpreter_oversize', 'interpreter_metadata'))
    case('child-fixed-view-truncated-interpreter-closed', lambda: rejected_view('interpreter_truncated', 'interpreter_source'))
    case('child-fixed-view-changed-named-interpreter-closed', lambda: rejected_view('interpreter_name_race', 'interpreter_named'))
    case('child-fixed-view-deadline-stops-new-reads-and-closes', lambda: rejected_view('deadline', 'interpreter_source'))
    case('child-fixed-view-close-error-never-claims-complete', lambda: rejected_view('close_error', 'interpreter_close', errno.EIO))
    case('child-fixed-view-read-first-error-preserved-over-close', lambda: rejected_view('read_and_close_error', 'interpreter_source', errno.EIO))
    case('actual-child-path-missing-interpreter-prevents-exec', lambda: actual_child('interpreter_missing'))
    case('actual-child-path-visible-interpreter-still-preserves-exec-ENOENT', lambda: actual_child('visible'))
    case('failure-view-parser-rejects-unbounded-body-fields', reject_unbounded_view)
    require(len(rows) == 31 and all(row['passed'] for row in rows), 'fixed 31-control total')
    return {'schema': 1, 'kind': 'owner20-DONE-admission-exec-view-controls08',
            'success': True, 'count': len(rows), 'controls': rows,
            'actual_safe_projection_sha256': ACTUAL_SAFE_SHA,
            'original_private_runtime_sha256': ACTUAL_RUNTIME_SHA,
            'actual_original_runtime_success': False,
            'baseline_actor_sha256': BASELINE_ACTOR_SHA,
            'baseline_property_sha256': BASELINE_PROPERTY_SHA,
            'candidate_actor_sha256': hashlib.sha256(sources['actor.py'].encode()).hexdigest(),
            'candidate_property_sha256': hashlib.sha256(sources['property_visibility.py'].encode()).hexdigest(),
            'original_qualify_sha256': QUALIFY_SHA,
            'Android_executed': False, 'Main_access': False,
            'actual_namespace_or_credential_changes': False, 'property_reads_or_writes': False,
            'real_child_spawned': False, 'real_init_or_bionic_qualified': False,
            'root_warmed_cache_limitation_remains': True,
            'ENOENT_cause_or_producer_failure_cause_proven': False}
