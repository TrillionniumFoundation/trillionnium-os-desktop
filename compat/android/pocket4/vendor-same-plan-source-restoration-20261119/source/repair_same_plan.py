#!/usr/bin/python3
"""One ordinary, bounded same-plan droidloom-source sparse repair.

Only the already-frozen normal reconcile CLI changes the original source.
No Android execution, compiler, installation, CURRENT, owner or lease changes.
"""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
import traceback
import types

ROOT = Path('/home/qq/work/p4-sameplan-source-repair-5cd1-20261119-r2')
OUT = ROOT / 'actual'
UNIT = 'p4-sameplan-source-repair-5cd1-20261119-r2.service'
WORK = Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/work')
SOURCE = WORK / 'aosp-source'
PROJECTION = WORK / 'source-projection.json'
VENDOR = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1')
FA = Path('/home/qq/work/p4-integrated-continuation-20261118-162b-r1/unified-native-capex-asb-20261119-r2')
SOURCE_TOOL = FA / 'release-tools-r1/bin/droidloom-source'
LOCK = VENDOR / 'producer-build-r6/android/manifest/production-full-source-lock.json'
PLAN = Path('/home/qq/work/p4-broker-mac-provider-20261118-162b-r1/vendor-r12-source-inputs-r1/actual/plan651.json')
PLAN_EVIDENCE = PLAN.with_name('RESULT.json')
MANIFEST = SOURCE / '.droidloom-source-manifest.json'
BOOKEND = VENDOR / 'control/vendor_source_bookends_r13_5cd1.py'
GATE = VENDOR / 'control/vendor_build_r13_5cd1.py'
VERIFY = VENDOR / 'packet-build-r6/verify.py'
SOURCE_ROWS = FA / 'SOURCE-ROWS-TESTED.json'
PINS_SHA = 'bb17f030d84bc0b807570f89ebca84ca46839cbd649e7af7c2186dc24b8c7cfb'
PREDECESSOR = Path('/home/qq/work/p4-sameplan-source-repair-5cd1-20261119-r1')
FULL_INPUT = ROOT / 'FULL_PROJECT_MISSING.json'
FULL_MISSING = {}
DU = '/usr/lib/cargo/bin/coreutils/du'
GiB = 1024**3
MiB = 1024**2
PRE_FREE = 160 * GiB
FLOOR = 144 * GiB
GROWTH = 16 * GiB
OUTPUT_LIMIT = 64 * MiB
TREE = 'fa0382574f4fc18f59b2b5dd67a30939167d8c3a'
EXPECTED_MISSING = {
    'prebuilts/clang/host/linux-x86': {
        'commit': '29182889399818f97baa65ea238c80e8117981eb',
        'prefixes': {'clang-r547379': ('4159412de2c6a0046cfdb00548e155da58e8886c', 8510, 3918057300),
                     'clang-r563880c': ('04048f4191a5ff9fa3d35bf9dafaa828f03101dd', 9745, 3974194918)}},
    'prebuilts/rust-toolchain/linux-x86': {
        'commit': 'fa2b1777b1f5c0471bb54ad4026feb1f6e94ea70',
        'prefixes': {'1.91.1': ('65ea0ec7715ba1cace4afacab154f07cb11d3d89', 3376, 2446380062),
                     '1.92.0': ('bae12efff35531b4d5ebec923a9e0541bb609db5', 3428, 2464535574)}}}
EXACT_PIN_CONTENTS = {
    str(SOURCE_TOOL): (1939704, '59ceb228cdceb18597c2b10efbb896b38736a1ce67d3df208b5498509e907e43'),
    str(LOCK): (400363, '30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4'),
    str(PLAN): (419480, 'b68746f9408d3d0618caf28e1db0c421a1f2ae2fe37dc85c7b5f0561bf7b5982'),
    str(PLAN_EVIDENCE): (10865, 'e3e7fac5857fdc5423f408ea685721db410bfa73478b7ae75de4b715b52eb0ca'),
    str(BOOKEND): (17665, '4d192fa6738a954e0b2f4a480a8ba38a68ad47fefbd5eabbf3b8d00ca29cfad7'),
    str(GATE): (82311, 'ba8181150c2140ee161a89523f0fc1c4e7ae90bdc838650a2ed9279d80cff465'),
    str(VERIFY): (28699, '5c630d2406135ba06ea08519055ea0b411e2beec1f0660a3f2b18432e66465ce'),
    str(SOURCE_ROWS): (695778, 'fc2a18d512c621a582e5f6dd75aedff03137bdadc3c3b162a8553c125bcfa159'),
    str(FULL_INPUT): (172198, '8e7973d893ecc73dab52037cc96817423a099e30df5cbc0214142866568ceda2'),
    str(PREDECESSOR / 'actual/RESULT.json'): (1096163, 'e9fe709e0c33abbae48ba74646ac1448a9cf8af6f739cf5dbd6583072875ed2c'),
    str(PREDECESSOR / 'repair_same_plan.py'): (46003, '70903f56b3928f2d965ef43582d11cdc19fa89abec255834455df18767db9b2f'),
    str(FA / 'producer/tools/droidloom-source/src/lib.rs'): (160001, '9f8794aff44327fbd3395f98c43d670c0930f59933daeb506b8f9e152c9e74b3')}
OBS = {'schema': 'pocket4-normal-same-plan-source-repair-v2', 'state': 'RUNNING',
       'started_ns': time.time_ns(), 'source_tree': TREE, 'commands': [], 'errors': [],
       'source_reconcile_dispatched': False, 'source_reconcile_returned_success': False,
       'production_ready': False, 'runtime_qualified': False, 'Android_starts': 0,
       'compilations': 0, 'installations': 0, 'external_CURRENT_mutations': 0,
       'owner_or_lease_changes': 0, 'historical_tests_counted_as_fresh': 0}
DEADLINE = None
GUARD = None
BOOKS = None
LOCKS = []
HELD = []
ACTIVE = {}
WRITTEN = 0
PINS = None


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def process_preconditions():
    need(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL, 'default waitable SIGCHLD')
    need(threading.get_native_id() == os.getpid(), 'main native thread')
    need(os.listdir('/proc/self/task') == [str(os.getpid())], 'single-thread parent')


def read_pin(path, wanted=None, retain=False):
    path = Path(path)
    need(path.resolve() == path, 'canonical regular input: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        need(stat.S_ISREG(before[2]) and before[6] <= 64 * MiB, 'bounded regular input')
        need(before[3] in (0, 1000), 'ordinary input owner')
        # The observed system du is a root-owned multicall hardlink; exact F9
        # includes its real link count. Task inputs remain ordinary single links.
        need(before[5] == 1 or str(path) == DU, 'known shared tool or single-link input')
        body = bytearray()
        while True:
            chunk = os.read(fd, MiB)
            if not chunk:
                break
            body.extend(chunk)
        need(before == f9(os.fstat(fd)) == f9(path.lstat()) and len(body) == before[6],
             'held complete immutable input')
        pin = {'path': str(path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'f9': before}
        if wanted is not None:
            need(pin == wanted, 'exact actual input pin changed: ' + str(path))
        if str(path) in EXACT_PIN_CONTENTS:
            need((pin['bytes'], pin['sha256']) == EXACT_PIN_CONTENTS[str(path)], 'original frozen content pin')
        if retain:
            HELD.append((fd, pin)); fd = None
        return bytes(body), pin
    finally:
        if fd is not None:
            os.close(fd)


def output_reserve(size, terminal=False):
    global WRITTEN
    need(size >= 0 and WRITTEN + size + (0 if terminal else 16 * MiB) <= OUTPUT_LIMIT,
         '64 MiB aggregate evidence bound with terminal reserve')
    WRITTEN += size


def save(name, value, terminal=False):
    need(re.fullmatch(r'[A-Za-z0-9_.-]+', name), 'owned output basename')
    data = value if isinstance(value, bytes) else encoded(value)
    if terminal:
        need(len(data) <= 15*MiB, 'terminal evidence fits reserved physical 16 MiB including metadata')
    output_reserve(len(data), terminal)
    path = OUT / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view); need(n > 0, 'complete evidence write'); view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'f9': f9(path.lstat())}


def environment():
    # Only local already-present Git objects can be used; there is no fetch or
    # source install command in this controller or in its exact before admission.
    return {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C',
            'TMPDIR': str(OUT / 'tmp'), 'PYTHONDONTWRITEBYTECODE': '1',
            'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_LAZY_FETCH': '1',
            'GIT_TERMINAL_PROMPT': '0', 'GIT_ALLOW_PROTOCOL': '',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'XDG_RUNTIME_DIR': '/run/user/1000',
            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'}


class Child:
    """Same original PIDFD/WNOWAIT/wait model as the reviewed provider worker.

    Pipes are bounded before appending; no poll()/wait() consumes the original
    identity before its terminal WNOWAIT observation. Each child is independent
    so an in-flight allocation scan cannot be accidentally reaped by a query.
    """
    def __init__(self, label, argv, timeout, cap=64*MiB):
        process_preconditions()
        self.row = {'name': label, 'argv': list(map(str, argv)), 'started_ns': time.time_ns(),
                    'actual_child_reaped': False, 'original_pidfd_held_until_reaped': False}
        OBS['commands'].append(self.row)
        self.p = self.fd = self.info = None
        self.selector = selectors.DefaultSelector()
        self.buffers = [bytearray(), bytearray()]
        self.caps = [cap, MiB]
        self.until = min(DEADLINE, time.monotonic() + timeout)
        try:
            self.p = subprocess.Popen(self.row['argv'], stdin=subprocess.DEVNULL,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      env=environment(), start_new_session=True,
                                      pass_fds=tuple(fd for fd, _ in LOCKS))
            ACTIVE[self.p.pid] = self
            self.row['pid'] = self.p.pid
            self.fd = os.pidfd_open(self.p.pid)
            self.row['pidfd_inode'] = os.fstat(self.fd).st_ino
            for i, stream in enumerate((self.p.stdout, self.p.stderr)):
                os.set_blocking(stream.fileno(), False)
                self.selector.register(stream, selectors.EVENT_READ, i)
        except BaseException:
            self.stop()
            raise

    def observe(self):
        if self.info is None:
            self.info = os.waitid(os.P_PIDFD if self.fd is not None else os.P_PID,
                                  self.fd if self.fd is not None else self.p.pid,
                                  os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if self.info is not None:
            need(self.info.si_pid == self.p.pid and self.info.si_code in
                 (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED), 'original child terminal identity')
        return self.info

    def pump(self, delay=0.0):
        need(time.monotonic() < self.until, 'bounded child deadline: ' + self.row['name'])
        for key, _ in self.selector.select(delay):
            block = os.read(key.fileobj.fileno(), 65536)
            if not block:
                self.selector.unregister(key.fileobj); key.fileobj.close(); continue
            need(len(self.buffers[key.data]) + len(block) <= self.caps[key.data], 'bounded child output')
            self.buffers[key.data].extend(block)
        return self.observe() is not None and not self.selector.get_map()

    def reap(self):
        need(self.observe() is not None, 'terminal child before final wait')
        code = self.p.wait(timeout=5)
        expected = self.info.si_status if self.info.si_code == os.CLD_EXITED else -self.info.si_status
        need(code == expected, 'WNOWAIT and original reap agree')
        self.row.update(exit_code=code, actual_child_reaped=True,
                        original_pidfd_held_until_reaped=self.fd is not None,
                        waitid={'pid': self.info.si_pid, 'code': self.info.si_code, 'status': self.info.si_status})
        if self.fd is not None:
            try:
                os.waitid(os.P_PIDFD, self.fd, os.WEXITED | os.WNOHANG)
                raise RuntimeError('original child should now return ECHILD')
            except ChildProcessError:
                self.row['after_reap_echild'] = True
        self.close()
        return tuple(bytes(x) for x in self.buffers)

    def close(self):
        if self.selector is not None:
            mapping = self.selector.get_map()
            for key in list(mapping.values()) if mapping is not None else []:
                key.fileobj.close()
            self.selector.close(); self.selector = None
        if self.fd is not None:
            os.close(self.fd); self.fd = None
        if self.p is not None:
            ACTIVE.pop(self.p.pid, None)
        for key, raw in zip(('stdout', 'stderr'), self.buffers):
            self.row[key] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        self.row['finished_ns'] = time.time_ns()

    def stop(self):
        if self.p is None:
            self.close(); return
        if self.p.returncode is None:
            self.row['forced'] = True
            # The session leader is still our original unreaped child. Its PGID
            # cannot be reused before this parent performs the final wait.
            try:
                os.killpg(self.p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            until = time.monotonic() + 5
            while self.observe() is None:
                need(time.monotonic() < until, 'original forced-child retirement bound')
                time.sleep(0.01)
            self.reap()
        else:
            self.close()


class Budget:
    def __init__(self):
        self.scanner = None
        self.base = None
        self.last = 0.0
        self.next_scan = 0.0
        self.samples = []
        self.minimum_free = None
        self.maximum_growth = 0

    def free(self):
        fs = os.statvfs(SOURCE)
        value = fs.f_bavail * fs.f_frsize
        self.minimum_free = value if self.minimum_free is None else min(value, self.minimum_free)
        need(value >= FLOOR, 'actual f_bavail below 144 GiB')
        memory = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                      if line.startswith('MemAvailable:'))
        need(memory >= 8*GiB, 'actual host emergency memory reserve 8 GiB')
        return value

    def tick(self, scan=True):
        now = time.monotonic()
        need(now < DEADLINE, 'fixed worker execution deadline')
        free = self.free()
        need(not os.path.lexists(PROJECTION), 'source projection appeared')
        for fd, pin in LOCKS:
            need(f9(os.fstat(fd)) == f9(Path(pin['path']).lstat()) == pin['f9'], 'original held source lock changed')
        if self.scanner is not None and self.scanner.pump():
            scanner = self.scanner
            self.scanner = None
            raw, err = scanner.reap()
            need(scanner.row['exit_code'] == 0 and not err, 'complete allocation observation')
            lines = raw.decode('ascii').splitlines()
            values = {}
            for line in lines:
                amount, path = line.split('\t', 1)
                need(amount.isdigit() and path not in values, 'distinct allocation record')
                values[path] = int(amount)
            need(set(values) == {str(SOURCE), str(ROOT)}, 'complete source plus owned allocation')
            need(values[str(ROOT)] <= OUTPUT_LIMIT - 16*MiB, 'owned physical output with 16 MiB terminal reserve')
            total = sum(values.values())
            if self.base is None:
                self.base = total
            growth = max(0, total - self.base)
            self.maximum_growth = max(self.maximum_growth, growth)
            need(growth <= GROWTH, 'actual source plus owned growth exceeds 16 GiB')
            self.samples.append({'scan_started_ns': scanner.row['started_ns'], 'observed_ns': time.time_ns(), 'allocations': values,
                                 'growth_bytes': growth, 'free_bavail': free})
            need(len(self.samples) <= 400, 'bounded allocation observations')
            self.last = now; self.next_scan = now + 5
        if self.base is not None:
            need(now - self.last <= 60, 'allocation observation freshness')
        if scan and self.scanner is None and now >= self.next_scan:
            self.scanner = Child('allocation-%03d' % len(self.samples),
                                 [DU, '--one-file-system', '--summarize', '--block-size=1', '--', str(SOURCE), str(ROOT)],
                                 45, 65536)

    def measure(self):
        # Drain an earlier observation, then require a wholly fresh scan. This
        # makes the last measurement a real quiescent source bookend.
        while self.scanner is not None:
            self.tick(scan=False); time.sleep(0.02)
        before = len(self.samples)
        self.next_scan = 0
        while len(self.samples) == before:
            self.tick(); time.sleep(0.02)
        return self.samples[-1]

    def stop(self):
        if self.scanner is not None:
            scanner = self.scanner; self.scanner = None
            scanner.stop()


def run(label, argv, timeout=120, cap=64*MiB, preserve=False):
    GUARD.tick()
    if preserve:
        need(WRITTEN + cap + MiB + 16*MiB <= OUTPUT_LIMIT, 'normal CLI stream reservation before spawn')
    child = Child(label, argv, timeout, cap)
    try:
        while not child.pump(0.02):
            GUARD.tick()
        raw, err = child.reap()
        if preserve:
            child.row['saved_stdout'] = save(label + '.stdout', raw)
            child.row['saved_stderr'] = save(label + '.stderr', err)
        elif err:
            child.row['stderr_diagnostic'] = err[:4096].decode('utf-8', 'replace')
        need(child.row['exit_code'] == 0, 'actual command failed: ' + label)
        GUARD.tick()
        return raw, err, child.row
    finally:
        if child.p is not None and child.p.returncode is None:
            child.stop()
        if preserve and 'saved_stdout' not in child.row:
            child.row['saved_stdout'] = save(label + '.stdout', bytes(child.buffers[0]))
            child.row['saved_stderr'] = save(label + '.stderr', bytes(child.buffers[1]))
            child.row['partial_output_saved_after_failure'] = True


def git(checkout, args):
    raw, err, row = run('git-%05d' % len(OBS['commands']),
                       ['/usr/bin/git', '--no-lazy-fetch', '-c', 'core.fsmonitor=false',
                        '-c', 'core.untrackedCache=false', '-C', str(checkout), *args])
    return raw


def load_module(path, label):
    need(str(path) in EXACT_PIN_CONTENTS, 'only fixed original source helpers may be imported')
    raw, pin = read_pin(path, next((p for p in PINS['pins'] if p['path'] == str(path)), None), retain=True)
    module = types.ModuleType(label)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module, pin


def check_projects(plan, before):
    summaries = []
    sparse_count = 0
    missing = {}
    for number, project in enumerate(plan['projects']):
        GUARD.tick()
        checkout = SOURCE / project['path']
        need(checkout.resolve() == checkout and checkout.is_dir(), 'real existing project')
        need(git(checkout, ['rev-parse', 'HEAD']).decode().strip() == project['commit'], 'same pinned HEAD')
        need(git(checkout, ['remote', 'get-url', 'origin']).decode().strip() == project['url'], 'same origin')
        tree = git(checkout, ['ls-tree', '-rz', '--full-tree', 'HEAD'])
        index = git(checkout, ['ls-files', '--stage', '-z'])
        committed = BOOKS.tree_records(tree)
        tracked = BOOKS.tracked_records(index)
        need(committed == tracked, 'complete original index equals committed tree')
        cones = project['sparse_paths']
        observed_cones = []
        if cones:
            sparse_count += 1
            observed_cones = git(checkout, ['sparse-checkout', 'list']).decode().splitlines()
            wanted = BOOKS.canonical_sparse_cones(cones)
            need(len(observed_cones) == len(set(observed_cones)), 'unique actual sparse cones')
            if before and project['path'] in EXPECTED_MISSING:
                wanted_missing = set(EXPECTED_MISSING[project['path']]['prefixes'])
                need(project['commit'] == EXPECTED_MISSING[project['path']]['commit'], 'exact deficient HEAD')
                need(set(wanted) - set(observed_cones) == wanted_missing
                     and not set(observed_cones) - set(wanted), 'only four observed missing cones')
                for prefix in wanted_missing:
                    need(not os.path.lexists(checkout / prefix), 'exact missing directory remains absent')
                missing[project['path']] = sorted(wanted_missing)
            else:
                need(set(observed_cones) == set(wanted), 'all other/after canonical sparse cones exact')
        flags = git(checkout, ['ls-files', '-t', '-z'])
        observed_flags = {}
        for record in flags.split(b'\0'):
            if not record:
                continue
            flag, name = record[:1].decode(), record[2:].decode()
            need(record[1:2] == b' ' and flag in ('H', 'S') and name not in observed_flags, 'exact ordinary tracked flags')
            observed_flags[name] = flag
        need(set(observed_flags) == set(tracked), 'complete ordinary index flags')
        if not cones:
            if before and project['path'] in FULL_MISSING:
                check_exact_full_before(project, checkout, tracked, observed_flags)
            else:
                need(set(observed_flags.values()) <= {'H'}, 'complete project must not remain sparse')
                if not before:
                    need(git(checkout, ['config', '--type=bool', '--default=false', '--get',
                                        'core.sparseCheckout']).decode().strip() == 'false',
                         'complete project sparse mode must actually be disabled')
        need(not git(checkout, ['status', '--porcelain=v1', '--untracked-files=all']), 'clean actual project')
        summaries.append({'project': project['path'], 'commit': project['commit'], 'origin': project['url'],
                          'tree_entries': len(committed), 'tree_sha256': hashlib.sha256(tree).hexdigest(),
                          'index_sha256': hashlib.sha256(index).hexdigest(), 'actual_cones': observed_cones,
                          'flags_sha256': hashlib.sha256(flags).hexdigest(), 'clean': True})
        if number % 50 == 0:
            print(json.dumps({'phase': 'before' if before else 'after', 'projects': number + 1,
                              'free_bavail': GUARD.free()}), flush=True)
    need(len(summaries) == 651 and sparse_count == 446, 'exact original 651/446 plan scope')
    need(missing == {p: sorted(v['prefixes']) for p, v in EXPECTED_MISSING.items()} if before else not missing,
         'exact admitted before deficiencies or no after deficiencies')
    return {'projects': summaries, 'project_count': len(summaries), 'sparse_count': sparse_count, 'missing_cones': missing}


def load_exact_full_missing():
    global FULL_MISSING
    raw, pin = read_pin(FULL_INPUT, retain=True)
    record = BOOKS.strict_json(raw)
    need(record['schema'] == 'p4-full-plan-three-projects-exact-missing-inputs-v1'
         and record['source_writes'] is False and record['lazy_fetch_disabled'] is True
         and record['inputs_before'] == record['inputs_after'] and record['uid'] == 1000,
         'actual independent read-only original complete-project diagnosis')
    need(len(record['commands']) == 24 and all(c['exit_code'] == 0 and c['stderr'] == ''
         for c in record['commands']), 'all actual original diagnosis commands successful')
    for key, expected in record['inputs_before'].items():
        read_pin(key, expected)
    expected_counts = {'prebuilts/build-tools': (122, 284959251),
                       'prebuilts/jdk/jdk21': (864, 668468567),
                       'prebuilts/siso': (2, 62036365)}
    values = {}
    for item in record['rows']:
        name = item['project']
        need(name in expected_counts and name not in values
             and item['core_sparse_checkout'] == 'true' and item['core_sparse_checkout_cone'] == 'false'
             and item['clean'] is True and item['actual_head'] == item['plan']['commit']
             and item['actual_origin'] == item['plan']['url'], 'exact three old non-cone complete projects')
        expected_project = BOOKS.normalized_project(item['plan'])
        need(expected_project['path'] == name and expected_project['sparse_paths'] == [], 'original full project plan')
        rows = {}
        for member in item['missing_rows']:
            BOOKS.safe_relative(member['path'])
            need(member['path'] not in rows and member['kind'] == 'blob'
                 and member['git_mode'] in ('100644', '100755', '120000')
                 and BOOKS.lower_hex(member['git_blob'], 40)
                 and type(member['bytes']) is int and member['bytes'] >= 0, 'complete exact missing blob row')
            rows[member['path']] = member
        need((len(rows), sum(x['bytes'] for x in rows.values())) == expected_counts[name]
             == (item['missing_count'], item['missing_logical_bytes']), 'exact independently quantified missing scope')
        values[name] = {'observed': item, 'plan': expected_project, 'rows': rows}
    need(set(values) == set(expected_counts)
         and sum(len(v['rows']) for v in values.values()) == 988
         and sum(x['bytes'] for v in values.values() for x in v['rows'].values()) == 1015464183,
         'all988 exact additional source members, no broader admission')
    FULL_MISSING = values
    OBS['full_project_missing_diagnosis'] = pin
    return record


def check_exact_full_before(project, checkout, tracked, flags):
    expected = FULL_MISSING[project['path']]
    observed = expected['observed']
    need(project == expected['plan'], 'unchanged exact full-project source tuple')
    need({name for name, flag in flags.items() if flag == 'S'} == set(expected['rows']),
         'only the exact independently observed988 missing S entries are admitted')
    for name, row in expected['rows'].items():
        need(tracked[name] == (row['git_mode'], row['git_blob']) and not os.path.lexists(checkout / name),
             'same committed blob and real missing path before normal disable')
    need(git(checkout, ['config', '--type=bool', '--default=false', '--get', 'core.sparseCheckout']).decode().strip()
         == observed['core_sparse_checkout'] == 'true', 'existing normal complete-project disable branch is reachable')
    need(git(checkout, ['config', '--type=bool', '--default=false', '--get', 'core.sparseCheckoutCone']).decode().strip()
         == observed['core_sparse_checkout_cone'] == 'false', 'same old non-cone checkout mode')
    need(git(checkout, ['sparse-checkout', 'list']).decode().splitlines() == observed['actual_sparse_list'],
         'exact original non-cone exclusion rules')
    raw, pin = read_pin(observed['actual_sparse_file']['pin']['path'], observed['actual_sparse_file']['pin'])
    need(raw.decode() == observed['actual_sparse_file']['text'], 'exact original sparse-rule body/F9')
    # Query real local object sizes again, independent of the receipt's totals.
    actual = {}
    raw = git(checkout, ['ls-tree', '-r', '-l', '-z', 'HEAD'])
    for member in raw.split(b'\0'):
        if not member: continue
        head, name = member.split(b'\t', 1)
        path = name.decode('utf-8')
        if path not in expected['rows']: continue
        mode, kind, blob, size = head.decode('ascii').split()
        need(size.isdigit() and path not in actual, 'known local original full-project blob size')
        actual[path] = {'path': path, 'git_mode': mode, 'kind': kind, 'git_blob': blob, 'bytes': int(size)}
    need(actual == expected['rows'], 'all actual local missing object sizes/modes/blobs match diagnosis')


def verify_full_restored_bodies():
    path = OUT / 'full-project-restored-body-sha256.ndjson'
    count = byte_count = symlinks = 0
    sha = hashlib.sha256()
    with path.open('xb') as stream:
        for project, expected in FULL_MISSING.items():
            checkout = SOURCE / project
            flags = {}
            for record in git(checkout, ['ls-files', '-t', '-z']).split(b'\0'):
                if record:
                    need(record[:2] == b'H ', 'all complete-project entries actually restored to H')
                    name = record[2:].decode('utf-8')
                    need(name not in flags, 'unique complete-project index entry')
                    flags[name] = 'H'
            need(set(expected['rows']) <= set(flags), 'all formerly missing members remain tracked')
            for name, wanted in sorted(expected['rows'].items()):
                GUARD.tick()
                row, identity = BOOKS.observe_blob(checkout, name, wanted['git_mode'], wanted['git_blob'],
                                                  flags[name], [], DEADLINE, GUARD.tick)
                need(row['present'] is True and row['bytes'] == wanted['bytes'], 'complete restored regular/symlink source bytes')
                line = encoded({'project': project, **row, 'f9': identity})
                output_reserve(len(line)); stream.write(line); sha.update(line)
                count += 1; byte_count += row['bytes']; symlinks += wanted['git_mode'] == '120000'
            stream.flush()
        os.fsync(stream.fileno())
    need(count == 988 and byte_count == 1015464183 and symlinks == 486,
         'all988 additional actual bodies and486 symlink bodies verified')
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha.hexdigest(), 'f9': f9(path.lstat()),
            'members_verified': count, 'logical_bytes_verified': byte_count, 'symlink_bodies_verified': symlinks,
            'every_actual_body_Git_blob_and_SHA256_verified': True}


def predecessor_retirement():
    raw, pin = read_pin(PREDECESSOR / 'actual/RESULT.json', retain=True)
    read_pin(PREDECESSOR / 'repair_same_plan.py', retain=True)
    prior = BOOKS.strict_json(raw)
    need(prior['schema'] == 'pocket4-normal-same-plan-source-repair-v1' and prior['state'] == 'FAILED'
         and prior['source_reconcile_dispatched'] is False and prior['source_reconcile_returned_success'] is False
         and prior['all_original_children_reaped'] is True and prior['original_locks_held_through_child_retirement'] is True
         and prior['adopted_child_retirement'] == [] and len(prior['errors']) == 1
         and prior['errors'][0]['message'] == 'complete project must not remain sparse',
         'actual immutable R1 failed admission and complete original child retirement')
    need(len(prior['commands']) == 1036 and all(c['actual_child_reaped'] is True
         and c['original_pidfd_held_until_reaped'] is True and c['after_reap_echild'] is True
         and c['exit_code'] == 0 and c['waitid'] == {'pid': c['pid'], 'code': os.CLD_EXITED, 'status': 0}
         and not c.get('forced') for c in prior['commands']), 'all original1036 read-only R1 children actually retired')
    need(prior['manifest_before']['original'] == prior['actual_manifest_after_failure']['original'], 'R1 source manifest truly remained unchanged')
    read_pin(MANIFEST, prior['manifest_before']['original'])
    for copy in (prior['manifest_before']['copy'], prior['actual_manifest_after_failure']['copy']):
        read_pin(copy['path'], copy, retain=True)
    need(not os.path.lexists(PREDECESSOR / 'actual/reconcile-intent.json'), 'R1 never published reconcile dispatch')
    retired = check_retired_units({'p4-sameplan-source-repair-5cd1-20261119-r1.service'})
    return {'actual_failed_R1': pin, 'exact_units': retired, 'manifest_unchanged': prior['manifest_before']['original'],
            'R1_source_repair_credit': False}


def member_inventory(before):
    result = {}
    for project, expected in EXPECTED_MISSING.items():
        checkout = SOURCE / project
        for prefix, (oid, count, size) in expected['prefixes'].items():
            need(git(checkout, ['rev-parse', 'HEAD:' + prefix]).decode().strip() == oid, 'exact original selected subtree')
            raw = git(checkout, ['ls-tree', '-r', '-l', '-z', 'HEAD', '--', prefix])
            rows = {}
            for record in raw.split(b'\0'):
                if not record:
                    continue
                head, relative = record.split(b'\t', 1)
                mode, kind, blob, byte_count = head.decode('ascii').split()
                name = relative.decode('utf-8'); BOOKS.safe_relative(name)
                need(name.startswith(prefix + '/') and name not in rows and kind == 'blob'
                     and mode in ('100644', '100755', '120000') and byte_count.isdigit(), 'local bounded committed blob')
                rows[name] = {'mode': mode, 'git_blob': blob, 'bytes': int(byte_count)}
            need(len(rows) == count and sum(v['bytes'] for v in rows.values()) == size,
                 'exact independently observed missing subtree count and bytes')
            result[project + '/' + prefix] = {'project': project, 'prefix': prefix, 'tree': oid,
                                             'rows': rows, 'logical_bytes': size}
    need(sum(len(v['rows']) for v in result.values()) == 25059
         and sum(v['logical_bytes'] for v in result.values()) == 12803167854, 'full four-prefix local object inventory')
    return result


def verify_new_bodies(inventory):
    path = OUT / 'four-prefix-body-sha256.ndjson'
    count = byte_count = 0
    digest = hashlib.sha256()
    with path.open('xb') as stream:
        for item in inventory.values():
            checkout = SOURCE / item['project']
            prefix = checkout / item['prefix']
            need(prefix.resolve() == prefix and prefix.is_dir(), 'restored real selected directory')
            actual = set()
            for directory, dirs, files in os.walk(prefix, followlinks=False):
                GUARD.tick()
                for name in list(dirs):
                    p = Path(directory) / name
                    if p.is_symlink():
                        actual.add(p.relative_to(checkout).as_posix()); dirs.remove(name)
                    else:
                        need(p.resolve() == p and p.is_dir(), 'restored real directory')
                actual.update((Path(directory) / name).relative_to(checkout).as_posix() for name in files)
            need(actual == set(item['rows']), 'complete physical restored namespace equals committed tree')
            raw_flags = git(checkout, ['ls-files', '-t', '-z', '--', item['prefix']])
            flags = {}
            for record in raw_flags.split(b'\0'):
                if record:
                    need(record[:2] == b'H ', 'restored member has actual ordinary H index flag')
                    name = record[2:].decode('utf-8')
                    need(name not in flags, 'unique restored index flag')
                    flags[name] = 'H'
            need(set(flags) == actual, 'complete real restored index flag set')
            for relative, wanted in sorted(item['rows'].items()):
                GUARD.tick()
                observed, identity = BOOKS.observe_blob(checkout, relative, wanted['mode'], wanted['git_blob'],
                                                        flags[relative], [item['prefix']], DEADLINE, GUARD.tick)
                need(observed['present'] is True and observed['bytes'] == wanted['bytes'], 'actual restored body size')
                line = encoded({'project': item['project'], **observed, 'f9': identity})
                output_reserve(len(line)); stream.write(line); digest.update(line)
                count += 1; byte_count += observed['bytes']
            stream.flush()
        os.fsync(stream.fileno())
    need(count == 25059 and byte_count == 12803167854, 'all four restored subtrees fully hashed')
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest(), 'f9': f9(path.lstat()),
            'members_verified': count, 'logical_bytes_verified': byte_count,
            'every_actual_body_Git_blob_and_SHA256_verified': True}


def take_locks():
    expected_inodes = [60857531, 60857480, 60857481]
    expected_paths = [WORK.parent / 'native-full.serial.lock', WORK / 'package-build.lock', WORK / 'aosp-source-update.lock']
    need([x['path'] for x in PINS['locks']] == list(map(str, expected_paths)), 'only original three source locks')
    for path, inode, pin in zip(expected_paths, expected_inodes, PINS['locks']):
        need(path.resolve() == path and pin['f9'][:6] == [66306, inode, 33152, 1000, 1000, 1], 'original lock tuple')
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(f9(os.fstat(fd)) == f9(path.lstat()) == pin['f9'], 'exact original current lock identity')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            LOCKS.append((fd, pin)); fd = None
        finally:
            if fd is not None:
                os.close(fd)
    actual = []
    lines = Path('/proc/locks').read_text().splitlines()
    for fd, pin in LOCKS:
        s = os.fstat(fd)
        key = f'{os.major(s.st_dev):02x}:{os.minor(s.st_dev):02x}:{s.st_ino}'
        records = [line for line in lines if key in line.split()]
        need(len(records) == 1 and str(os.getpid()) in records[0].split()
             and 'FLOCK' in records[0].split() and 'WRITE' in records[0].split(),
             'actual original lock is held exclusively by this worker')
        actual.append({'path': pin['path'], 'f9': f9(s), 'actual_lock_records': records})
    OBS['actual_original_locks'] = actual


def cgroup_admit():
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    need(len(rows) == 1 and rows[0].startswith('0::/'), 'one ordinary cgroup v2')
    group = rows[0][3:]
    cg = Path('/sys/fs/cgroup' + group)
    need(cg.name == UNIT and '/user-1000.slice/user@1000.service/' in str(cg), 'fixed own ordinary unit')
    limits = {n: (cg / n).read_text().strip() for n in
              ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max', 'cpu.max')}
    need(limits['memory.max'] == str(2*GiB) and limits['memory.high'] == str(1536*MiB)
         and limits['memory.swap.max'] == '0' and limits['pids.max'] == '256', 'exact 2GiB/1.5GiB/swap0/Tasks256')
    quota, period = map(int, limits['cpu.max'].split())
    need(quota == 2*period and os.sched_getaffinity(0) == {22, 23}, 'two reserved CPUs22-23/200 percent')
    need((cg / 'cgroup.procs').read_text().split() == [str(os.getpid())], 'fresh own singleton worker cgroup')
    OBS['worker'] = {'unit': UNIT, 'cgroup': str(cg), 'limits': limits, 'affinity': [22, 23],
                     'pid': os.getpid(), 'start_ticks': Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()[19]}
    return cg


def all_units(value):
    result = set()
    if isinstance(value, dict):
        if isinstance(value.get('unit'), str) and value['unit'].endswith('.service'):
            result.add(value['unit'])
        for item in value.values(): result.update(all_units(item))
    elif isinstance(value, list):
        for item in value: result.update(all_units(item))
    return result


def check_retired_units(units):
    rows = []
    for unit in sorted(units):
        need(re.fullmatch(r'[A-Za-z0-9_.-]+\.service', unit), 'exact historical unit')
        raw, err, command = run('unit-%05d' % len(OBS['commands']), ['/usr/bin/systemctl', '--user', 'show', unit,
                                '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'], 15, 65536)
        fields = dict(line.split('=', 1) for line in raw.decode().splitlines() if '=' in line)
        need(not err and fields == {'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
                                    'MainPID': '0', 'ControlGroup': ''}, 'known heavy/prior vendor unit not retired')
        path = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
        need(not os.path.lexists(path), 'known retired unit cgroup remains')
        rows.append({'unit': unit, 'fields': fields, 'cgroup_absent': True})
    return rows


def no_heavy_processes():
    names = re.compile(r'^(?:clang(?:\+\+)?(?:-[0-9]+)?|cc1(?:plus)?|gcc(?:-[0-9]+)?|g\+\+(?:-[0-9]+)?|rustc|cargo|ninja|ninja-build|make|ld(?:\.lld|\.gold)?|lld|ccache|qemu-system.*|crosvm)$')
    checked = 0
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        checked += 1; need(checked <= 32768, 'bounded process metadata inventory')
        try:
            comm = (entry / 'comm').read_text().strip()
        except FileNotFoundError:
            continue
        need(not names.fullmatch(comm), 'actual heavy actor present: ' + comm)
    return {'observed_ns': time.time_ns(), 'process_names_read': checked, 'heavy_matches': []}


def verify_pins_after():
    result = []
    for fd, wanted in HELD:
        need(f9(os.fstat(fd)) == wanted['f9'], 'held immutable input identity changed')
        _, observed = read_pin(wanted['path'], wanted)
        result.append(observed)
    return result


def retire_adopted():
    # Called only after all individually tracked direct children have retired.
    need(not ACTIVE, 'direct child registry must be empty before adopted cleanup')
    rows = []
    until = time.monotonic() + 10
    while True:
        children = [int(x) for x in Path('/proc/self/task/' + str(os.getpid()) + '/children').read_text().split()]
        if not children: return rows
        need(time.monotonic() < until, 'finite owned adopted-child retirement')
        for pid in children:
            fd = os.pidfd_open(pid)
            try:
                info = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                forced = info is None
                if forced:
                    try: signal.pidfd_send_signal(fd, signal.SIGKILL)
                    except ProcessLookupError: pass
                while info is None:
                    need(time.monotonic() < until, 'adopted original PIDFD deadline')
                    info = os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    if info is None: time.sleep(0.01)
                got, status = os.waitpid(pid, 0)
                need(got == pid, 'actual adopted child reaped')
                rows.append({'pid': pid, 'forced': forced, 'wait_status': status, 'actual_child_reaped': True,
                             'original_pidfd_held_until_reaped': True})
            finally:
                os.close(fd)


def main():
    global DEADLINE, GUARD, BOOKS, PINS
    DEADLINE = time.monotonic() + 1710
    os.umask(0o077)
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000, 'normal qq only')
    process_preconditions()
    need(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, 'ordinary own child subreaper')
    need(not Path('/proc/self/task/' + str(os.getpid()) + '/children').read_text().strip(), 'no preexisting owned child')
    cg = cgroup_admit()
    need(len(sys.argv) == 3 and sys.argv[1] == '--reviewed-sha256'
         and re.fullmatch(r'[0-9a-f]{64}', sys.argv[2]), 'exact reviewed entrypoint SHA argument')
    _, self_pin = read_pin(ROOT / 'repair_same_plan.py', retain=True)
    need(self_pin['sha256'] == sys.argv[2], 'actual worker equals independently reviewed source')
    OBS['actual_worker_source'] = self_pin
    need(ROOT.resolve() == ROOT and SOURCE.resolve() == SOURCE and not os.path.lexists(OUT), 'new owned output and canonical source')
    need(not os.path.lexists(PROJECTION), 'source projection absent')
    OUT.mkdir(mode=0o700); (OUT / 'tmp').mkdir(mode=0o700)
    pins_raw, pins_identity = read_pin(ROOT / 'PINS.json', retain=True)
    need(pins_identity['sha256'] == PINS_SHA and pins_identity['bytes'] == 4473, 'exact reviewed actual PINS body')
    PINS = json.loads(pins_raw)
    GUARD = Budget()
    need(GUARD.free() >= PRE_FREE, 'fresh f_bavail must be at least 160 GiB')
    def interrupted(signum, frame):
        raise RuntimeError('owned worker interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
    try:
        take_locks()
        OBS['allocation_before'] = GUARD.measure()
        raw, err, _ = run('own-effective-service-boundary', ['/usr/bin/systemctl', '--user', 'show', UNIT,
            '--property=RuntimeMaxUSec,KillMode,TimeoutStopUSec,OOMPolicy'], 15, 65536)
        fields = dict(line.split('=', 1) for line in raw.decode().splitlines() if '=' in line)
        need(not err and fields == {'RuntimeMaxUSec': '30min', 'KillMode': 'control-group',
                                   'TimeoutStopUSec': '15s', 'OOMPolicy': 'kill'}, 'exact hard owned-unit retirement boundary')
        OBS['hard_service_boundary'] = fields
        for pin in PINS['pins']:
            if pin['path'] != str(MANIFEST):
                read_pin(pin['path'], pin, retain=True)
        BOOKS, _ = load_module(BOOKEND, 'source_repair_readonly_bookends')
        gate, _ = load_module(GATE, 'source_repair_existing_retirement_gate')
        verifier, verifier_pin = load_module(VERIFY, 'source_repair_original_source_verifier')
        rows_raw, rows_pin = read_pin(SOURCE_ROWS, retain=True)
        source_rows = BOOKS.strict_json(rows_raw)
        need(len(source_rows) == 2336 and sum(row['bytes'] for row in source_rows) == 43854389,
             'complete original canonical fa038 source rows')
        original_check = verifier.check
        def guarded_source_check(*args, **kwargs):
            GUARD.tick()
            return original_check(*args, **kwargs)
        verifier.check = guarded_source_check
        canonical_before = verifier.source_snapshot(FA / 'producer', source_rows, TREE)
        OBS['canonical_producer_before'] = save('canonical-producer-before.json', canonical_before)
        OBS['canonical_producer_rows'] = rows_pin
        def status_adapter(argv, *, stdin, stdout, stderr, timeout, check):
            need(argv[:3] == ['/usr/bin/systemctl', '--user', 'show'] and len(argv) == 5
                 and stdin == subprocess.DEVNULL and stdout == stderr == subprocess.PIPE
                 and timeout == 15 and check is False, 'existing fixed metadata gate contract')
            raw, err, record = run('retirement-%05d' % len(OBS['commands']), argv, timeout, 65536)
            return subprocess.CompletedProcess(argv, record['exit_code'], raw, err)
        gate.status_run = status_adapter
        gate.BOOKENDS = BOOKS
        OBS['actual_R1_failure_retirement'] = predecessor_retirement()
        load_exact_full_missing()
        source_contracts = gate.source_contracts()
        OBS['original_normal_source_contracts'] = save('normal-source-contracts.json', source_contracts)
        OBS['heavy_admission'] = gate.verify_serialized_retirement()
        units = all_units(OBS['heavy_admission']) | {
            'p4-sameplan-source-repair-5cd1-20261119-r1.service',
            'p4-cp3a-vendor-supervisor-20261119-5cd1-r13.service',
            'p4-cp3a-vendor-20261119-5cd1-r13.service',
            'p4-cp3a-vendor-20261119-5cd1-r13-recovery.service'}
        OBS['retired_units_before'] = check_retired_units(units)
        OBS['heavy_processes_before'] = no_heavy_processes()
        plan_raw, plan_pin = read_pin(PLAN, next(p for p in PINS['pins'] if p['path'] == str(PLAN)))
        plan = BOOKS.normalized_plan(BOOKS.strict_json(plan_raw))
        need(len(plan['projects']) == 651 and len(plan['links']) == 8, 'original complete bounded plan')
        manifest_raw, manifest_before = read_pin(MANIFEST, next(p for p in PINS['pins'] if p['path'] == str(MANIFEST)))
        expected_manifest = {'schema_version': 1, 'source_lock_sha256': EXACT_PIN_CONTENTS[str(LOCK)][1], 'plan': plan}
        need(expected_manifest == source_contracts[651], 'actual original normal CLI/lock/plan producer contract')
        need(BOOKS.normalized_manifest(BOOKS.strict_json(manifest_raw)) == expected_manifest, 'live full651 manifest equals original plan')
        OBS['manifest_before'] = {'original': manifest_before, 'copy': save('manifest-before.json', manifest_raw)}
        before = check_projects(plan, True)
        OBS['projects_before'] = save('projects-before.json', before)
        inventory = member_inventory(True)
        OBS['selected_tree_before'] = save('selected-tree-before.json', inventory)
        OBS['heavy_processes_before_reconcile'] = no_heavy_processes()
        OBS['allocation_immediately_before_reconcile'] = GUARD.measure()
        need(GUARD.free() >= PRE_FREE, 'fresh 160 GiB after allocation scan and immediately before source mutation')
        OBS['source_reconcile_dispatched'] = True
        save('reconcile-intent.json', {'argv': [str(SOURCE_TOOL), '--profile', 'production-full', 'reconcile',
             '--lock', str(LOCK), '--output', str(SOURCE)], 'manifest_before': manifest_before,
             'source_lock_pin': next(p for p in PINS['pins'] if p['path'] == str(LOCK)), 'started_ns': time.time_ns()})
        raw, err, command = run('normal-same-plan-reconcile', [str(SOURCE_TOOL), '--profile', 'production-full',
                               'reconcile', '--lock', str(LOCK), '--output', str(SOURCE)], 900, 8*MiB, preserve=True)
        OBS['normal_reconcile_stdout'] = command['saved_stdout']
        OBS['normal_reconcile_stderr'] = command['saved_stderr']
        OBS['source_reconcile_returned_success'] = True
        raw, err, command = run('normal-verify-materialized', [str(SOURCE_TOOL), '--profile', 'production-full',
                               'verify-materialized', '--lock', str(LOCK), '--output', str(SOURCE)], 300, 8*MiB, preserve=True)
        OBS['normal_verify_stdout'] = command['saved_stdout']
        OBS['normal_verify_stderr'] = command['saved_stderr']
        after = check_projects(plan, False)
        OBS['projects_after'] = save('projects-after.json', after)
        for a, b in zip(before['projects'], after['projects']):
            for key in ('project', 'commit', 'origin', 'tree_entries', 'tree_sha256', 'index_sha256', 'clean'):
                need(a[key] == b[key], 'same original project commit/index/clean after reconcile')
        need(member_inventory(False) == inventory, 'all original four selected Git trees unchanged')
        OBS['restored_body_inventory'] = verify_new_bodies(inventory)
        OBS['restored_full_project_body_inventory'] = verify_full_restored_bodies()
        OBS['restored_source_totals'] = {'members_verified': 26047, 'logical_bytes_verified': 13818632037,
                                         'actual_body_receipts': [OBS['restored_body_inventory'],
                                                                 OBS['restored_full_project_body_inventory']]}
        # A final clean check of all five touched projects follows all reads.
        for project in set(EXPECTED_MISSING) | set(FULL_MISSING):
            need(not git(SOURCE / project, ['status', '--porcelain=v1', '--untracked-files=all']), 'restored project clean after complete read')
        manifest_raw, manifest_after = read_pin(MANIFEST)
        need(BOOKS.normalized_manifest(BOOKS.strict_json(manifest_raw)) == expected_manifest, 'same exact complete manifest plan after normal atomic publication')
        OBS['manifest_after'] = {'original': manifest_after, 'copy': save('manifest-after.json', manifest_raw)}
        OBS['manifest_body_identical'] = manifest_after['sha256'] == manifest_before['sha256']
        OBS['manifest_F9_identical'] = manifest_after['f9'] == manifest_before['f9']
        OBS['retired_units_after'] = check_retired_units(units)
        OBS['heavy_processes_after'] = no_heavy_processes()
        canonical_after = verifier.source_snapshot(FA / 'producer', source_rows, TREE)
        need(canonical_after == canonical_before, 'complete original2336 canonical producer bodies/F9/tree unchanged')
        OBS['canonical_producer_after'] = save('canonical-producer-after.json', canonical_after)
        OBS['complete_original_canonical_producer_unchanged'] = True
        OBS['immutable_inputs_after'] = verify_pins_after()
        OBS['allocation_after'] = GUARD.measure()
        need(not os.path.lexists(PROJECTION), 'normal reconcile left no source projection')
        OBS['state'] = 'PASSED'
    except BaseException as error:
        OBS['state'] = 'FAILED'
        OBS['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN); signal.signal(signal.SIGINT, signal.SIG_IGN)
        for action in [GUARD.stop] + [child.stop for child in list(ACTIVE.values())]:
            try:
                action()
            except BaseException as error:
                OBS['state'] = 'FAILED'; OBS['errors'].append({'individual_retirement_error': repr(error)})
        clear = False
        try:
            OBS['adopted_child_retirement'] = retire_adopted()
            need(not ACTIVE and not Path('/proc/self/task/' + str(os.getpid()) + '/children').read_text().strip(), 'all original children actually reaped')
            need((cg / 'cgroup.procs').read_text().split() == [str(os.getpid())], 'no surviving owned cgroup child')
            clear = True
            OBS['all_original_children_reaped'] = True
            for fd, pin in LOCKS:
                need(f9(os.fstat(fd)) == f9(Path(pin['path']).lstat()) == pin['f9'], 'original locks unchanged through full child retirement')
            OBS['original_locks_held_through_child_retirement'] = len(LOCKS) == 3
            need(not OBS['adopted_child_retirement'], 'unexpected adopted children prevent successful qualification')
        except BaseException as error:
            OBS['state'] = 'FAILED'; OBS['errors'].append({'retirement_error': repr(error)})
        try:
            if clear and OBS['state'] == 'FAILED':
                try:
                    raw, pin = read_pin(MANIFEST)
                    observed = {'original': pin, 'copy': save('manifest-after-failure.json', raw),
                                'observed_after_all_source_children_retired': True}
                    if BOOKS is not None:
                        try:
                            observed['normalized_manifest'] = BOOKS.normalized_manifest(BOOKS.strict_json(raw))
                        except BaseException as error:
                            observed['parse_error'] = repr(error)
                    OBS['actual_manifest_after_failure'] = observed
                except BaseException as error:
                    OBS['errors'].append({'failed_manifest_observation_error': repr(error)})
            if clear:
                for fd, _ in reversed(LOCKS): os.close(fd)
                LOCKS.clear()
            else:
                # Never voluntarily release original locks while actual owned
                # children are unresolved. The exact systemd unit's 1800s
                # KillMode=control-group boundary remains responsible for its
                # entire cgroup; the launcher/observer must see retirement
                # before any later source task. Children inherit the lock FDs.
                OBS['locks_retained_pending_owned_unit_retirement'] = True
            for fd, _ in HELD: os.close(fd)
            HELD.clear()
            OBS['resources'] = {'preflight_free_floor': PRE_FREE, 'runtime_free_floor': FLOOR, 'growth_cap': GROWTH,
                                'minimum_free_bavail': GUARD.minimum_free, 'maximum_observed_growth': GUARD.maximum_growth,
                                'allocation_samples': GUARD.samples, 'fixed_worker_seconds': 1710, 'hard_unit_seconds': 1800}
            OBS['finished_ns'] = time.time_ns()
            if time.monotonic() >= DEADLINE:
                OBS['state'] = 'FAILED'; OBS['errors'].append({'deadline_expired': True})
            final_pin = save('RESULT.json', OBS, terminal=True)
            print(json.dumps({'state': OBS['state'], 'result': final_pin, 'errors': OBS['errors']}), flush=True)
        finally:
            # A receipt/JSON/pipe error must not implicitly close unresolved
            # source locks by letting this process exit before unit retirement.
            if not clear:
                while True:
                    time.sleep(0.1)
    return 0 if OBS['state'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
