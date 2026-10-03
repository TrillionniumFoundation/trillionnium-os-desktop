#!/usr/bin/env python3
"""Job-private CI namespace permission; no production deployment or fallback.

Only fixed internal setup/cleanup commands use sudo. The original corpus runs
as its original runner UID with a real byte-identical private Python file.
AppArmor/sysctls remain enabled and unchanged outside the named attachment.
This trusted CI configuration is not a hostile-Python-code sandbox.
"""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('/var/lib')
PYTHON = Path('/usr/bin/python3.12')
SETSID = Path('/usr/bin/setsid')
TEMPLATE = '.github/apparmor/hepta-ci-namespace-python.v1.profile'
TEMPLATE_SHA256 = '9d6bf7dc994cc4b7e19444c1d1b633327ccc22bb202c4c7685a3125ae0b157be'
REPOSITORY = 'TrillionniumFoundation/trillionnium-os-desktop'
JOBS = {'ci': ('repository-contracts', 'repository-contracts-prospective-merge'),
        'g2-approved-native-startup': ('source-prospective',),
        'g2-native-product-owner': ('source-prospective',)}
LIMIT = 2 * 1024 * 1024
CAPS = ('CapEff', 'CapPrm', 'CapInh', 'CapAmb', 'CapBnd')
SETTINGS = ('/sys/module/apparmor/parameters/enabled',
            '/proc/sys/kernel/apparmor_restrict_unprivileged_userns',
            '/proc/sys/kernel/apparmor_restrict_unprivileged_unconfined',
            '/proc/sys/kernel/unprivileged_userns_clone')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _decimal(text, maximum):
    if type(text) is not str or not re.fullmatch(r'[1-9][0-9]{0,19}', text) or int(text) > maximum:
        raise ValueError('CI numeric context refused')
    return text


def _workflow_ref(value):
    if type(value) is not str or len(value) > 1024:
        raise ValueError('CI workflow ref bound refused')
    for workflow in JOBS:
        prefix = REPOSITORY + '/.github/workflows/' + workflow + '.yml@'
        if not value.startswith(prefix): continue
        suffix = value[len(prefix):]
        # These are the original three workflows' admitted push/PR domains.
        # The ref never becomes a pathname or an attachment selector.
        if re.fullmatch(r'refs/heads/(?:main|codex/[A-Za-z0-9._/-]+)', suffix):
            if any(part in ('', '.', '..') for part in suffix.split('/')):
                raise ValueError('CI workflow ref component refused')
            return workflow
        match = re.fullmatch(r'refs/pull/([1-9][0-9]{0,19})/merge', suffix)
        if match:
            _decimal(match[1], (1 << 64) - 1)
            return workflow
        raise ValueError('CI workflow ref suffix refused')
    raise ValueError('CI workflow file or repository refused')


def _context(workflow, run, attempt, job, uid, gid, head, tree):
    _decimal(run, (1 << 64) - 1); _decimal(attempt, 9999)
    if (type(workflow) is not str or workflow not in JOBS or type(job) is not str or
            job not in JOBS[workflow] or type(uid) is not int or not 0 < uid < (1 << 32) - 1):
        raise ValueError('CI job or non-root UID refused')
    if type(gid) is not int or not 0 <= gid < (1 << 32) - 1:
        raise ValueError('CI GID refused')
    if any(type(value) is not str or not re.fullmatch(r'[0-9a-f]{40}', value) for value in (head, tree)):
        raise ValueError('CI source tuple refused')
    name = f'hepta-ci-g1-{run}-{attempt}-{workflow}-{job}'
    return {'workflow': workflow, 'run': run, 'attempt': attempt, 'job': job, 'uid': uid, 'gid': gid,
            'head': head, 'tree': tree, 'profile': name, 'directory': str(BASE / name),
            'ledger': str(BASE / ('.' + name + '.ledger'))}


def _read(path, maximum=LIMIT):
    # The descriptor remains owned across complete bounded read and readback.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('CI regular object refused')
        raw = bytearray()
        while len(raw) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not part: break
            raw.extend(part)
        after = os.fstat(fd)
        if len(raw) > maximum or _identity(before) != _identity(after):
            raise ValueError('CI bounded readback refused')
        return bytes(raw), before
    finally: os.close(fd)


def _identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def _root_owned(path, mode=None):
    value = path.lstat()
    if value.st_uid != 0 or value.st_gid != 0 or value.st_mode & 0o022 or stat.S_ISLNK(value.st_mode):
        raise ValueError('CI root-owned boundary refused')
    if mode is not None and stat.S_IMODE(value.st_mode) != mode:
        raise ValueError('CI owned mode refused')
    return value


def _no_file_caps(path):
    try: value = os.getxattr(path, 'security.capability', follow_symlinks=False)
    except OSError as error:
        if error.errno != 61: raise
        value = b''
    if value: raise ValueError('CI executable file capabilities refused')


def _executable(path):
    value = _root_owned(path)
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1 or value.st_mode & 0o6000:
        raise ValueError('CI executable object refused')
    _no_file_caps(path)
    raw, observed = _read(path, 64 * 1024 * 1024)
    if _identity(value) != _identity(observed): raise ValueError('CI executable changed')
    return {'identity': _identity(value), 'bytes': len(raw), 'sha256': _sha(raw)}


def _global():
    values = {}
    for path in SETTINGS:
        try: values[path] = _kernel_read(Path(path), 16).decode('ascii', 'strict')
        except FileNotFoundError:
            if path in SETTINGS[:2]: raise
            values[path] = None
        if values[path] is not None and len(values[path]) > 16:
            raise ValueError('CI security setting bound refused')
    if values[SETTINGS[0]].strip() != 'Y' or values[SETTINGS[1]].strip() != '1':
        raise ValueError('CI expected enabled restriction refused')
    return values


def _profiles():
    raw = _kernel_read(Path('/sys/kernel/security/apparmor/profiles'), LIMIT)
    if len(raw) > LIMIT: raise ValueError('CI profile inventory bound refused')
    return sorted(raw.decode('utf-8', 'strict').splitlines())


def _kernel_read(path, maximum):
    # Kernel-generated files may report size zero. Bound actual bytes, rather
    # than trusting st_size or allocating the complete inventory first.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        raw = bytearray()
        while len(raw) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not part: break
            raw.extend(part)
        if len(raw) > maximum: raise ValueError('CI kernel read bound refused')
        return bytes(raw)
    finally: os.close(fd)


def _strict_json(raw):
    if type(raw) is not bytes or len(raw) > LIMIT:
        raise ValueError('CI state byte bound refused')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('CI duplicate state refused')
            result[key] = value
        return result
    reject_number = lambda value: (_ for _ in ()).throw(ValueError('CI number refused'))
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=reject_number, parse_float=reject_number)


def _write_new(path, raw, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        position = 0
        while position < len(raw):
            count = os.write(fd, raw[position:])
            if count <= 0: raise ValueError('CI short write refused')
            position += count
        os.fchmod(fd, mode); os.fsync(fd)
    finally: os.close(fd)


def _render(context, template):
    keys = {'workflow', 'run', 'attempt', 'job', 'uid', 'gid', 'head', 'tree', 'profile', 'directory', 'ledger'}
    if type(context) is not dict or set(context) != keys or type(template) is not bytes:
        raise ValueError('CI closed attachment context refused')
    expected = _context(*(context[key] for key in ('workflow', 'run', 'attempt', 'job', 'uid', 'gid', 'head', 'tree')))
    if context != expected: raise ValueError('CI fixed attachment differs')
    if _sha(template) != TEMPLATE_SHA256: raise ValueError('CI template changed')
    interpreter = context['directory'] + '/bin/python3'
    text = template.decode('ascii', 'strict')
    if text.count('@@PROFILE@@') != 1 or text.count('@@INTERPRETER@@') != 1:
        raise ValueError('CI attachment template refused')
    return text.replace('@@PROFILE@@', context['profile']).replace('@@INTERPRETER@@', interpreter).encode()


def _command(argv, *, new_session=True):
    # The output threshold is checked after the direct child completes, not a
    # strict in-flight output/disk bound. Owned temporary files avoid PIPE EOF
    # waits on descendants that inherited stdout. Timeout still waits/kills
    # only the direct child; ledger checks account for actual root descendants.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=30,
                                check=False, start_new_session=new_session)
        stdout.seek(0); output = stdout.read(LIMIT + 1)
        stderr.seek(0); errors = stderr.read(LIMIT + 1)
        if len(output) > LIMIT or len(errors) > LIMIT or result.returncode:
            raise ValueError('CI fixed operation refused')
        return output


def _proc_record(pid, proc=Path('/proc')):
    raw = _kernel_read(proc / str(pid) / 'stat', 8192)
    if not raw.startswith(str(pid).encode() + b' (') or b') ' not in raw:
        raise ValueError('CI process stat shape refused')
    fields = raw.rsplit(b') ', 1)[1].split()
    if len(fields) < 20: raise ValueError('CI process stat fields refused')
    result = {'pid': pid, 'start_ticks': int(fields[19]),
              'pgid': int(fields[2]), 'sid': int(fields[3])}
    if any(type(value) is not int or value < 0 for value in result.values()):
        raise ValueError('CI process stat identity refused')
    return result


def _capture_root_worker(context, operation):
    result = _proc_record(os.getpid())
    result['uid'] = os.getuid()
    result['exe_identity'] = _identity(Path('/proc/self/exe').stat())
    if result['uid'] != 0 or result['exe_identity'] != _executable(PYTHON)['identity']:
        raise ValueError('CI actual root worker executable refused')
    if result['pgid'] != result['pid'] or result['sid'] != result['pid']:
        raise ValueError('CI actual root operation session refused')
    supervisor = _proc_record(os.getppid())
    status = _kernel_read(Path('/proc') / str(supervisor['pid']) / 'status', 65536).decode('ascii', 'strict')
    uid = [line.split()[1:] for line in status.splitlines() if line.startswith('Uid:')]
    supervisor['uid'] = 0
    supervisor['exe_identity'] = _identity((Path('/proc') / str(supervisor['pid']) / 'exe').stat())
    arguments = [context[key] for key in ('workflow', 'run', 'attempt', 'job')]
    arguments += [str(context['uid']), str(context['gid']), context['head'], context['tree']]
    expected = [str(SETSID), '--fork', '--wait', '--', str(PYTHON), str(Path(__file__).resolve()), operation, *arguments]
    argv = _kernel_read(Path('/proc') / str(supervisor['pid']) / 'cmdline', 65536).rstrip(b'\0').split(b'\0')
    if (uid != [['0', '0', '0', '0']] or argv != [os.fsencode(part) for part in expected] or
            supervisor['exe_identity'] != _executable(SETSID)['identity']):
        raise ValueError('CI actual fixed setsid supervisor refused')
    if os.getppid() != supervisor['pid'] or _proc_record(supervisor['pid']) != {key: supervisor[key] for key in ('pid', 'start_ticks', 'pgid', 'sid')}:
        raise ValueError('CI supervisor handoff changed')
    result['supervisor'] = supervisor
    return result


def _process_entries(proc=Path('/proc')):
    with os.scandir(proc) as entries:
        count = 0
        for entry in entries:
            count += 1
            if count > 65536: raise ValueError('CI process inventory bound refused')
            if entry.name.isdecimal(): yield int(entry.name)


def _live_setup_workers(context, worker, proc=Path('/proc'), exclude=None):
    arguments = [context[key] for key in ('workflow', 'run', 'attempt', 'job')]
    arguments += [str(context['uid']), str(context['gid']), context['head'], context['tree']]
    commands = []
    for operation in ('_setup_root', '_cleanup_root'):
        command = [str(PYTHON), str(Path(__file__).resolve()), operation, *arguments]
        commands.append(command)
    commands += [['/sbin/apparmor_parser', operation, context['directory'] + '/profile']
                 for operation in ('-a', '-R')]
    encoded = [[os.fsencode(part) for part in row] for row in commands]
    live = []
    for pid in _process_entries(proc):
        try:
            record = _proc_record(pid, proc)
            argv = _kernel_read(proc / str(pid) / 'cmdline', 65536).rstrip(b'\0').split(b'\0')
            if exclude is not None and pid == exclude['pid']:
                # Exclude only the currently validating writer, never its
                # group/session or any child after argv/exec has changed.
                wanted = {key: exclude[key] for key in ('pid', 'start_ticks', 'pgid', 'sid')}
                status = _kernel_read(proc / str(pid) / 'status', 65536).decode('ascii', 'strict')
                uid = [line.split()[1:] for line in status.splitlines() if line.startswith('Uid:')]
                if (record != wanted or uid != [['0', '0', '0', '0']] or
                        _identity((proc / str(pid) / 'exe').stat()) != exclude['exe_identity']):
                    raise ValueError('CI current writer exclusion identity changed')
                continue
        except FileNotFoundError:
            if exclude is not None and pid == exclude['pid']:
                raise ValueError('CI current writer readback disappeared')
            continue
        if argv in encoded or (worker is not None and
                (pid == worker['pid'] or record['pgid'] == worker['pgid'] or record['sid'] == worker['sid'])):
            if worker is not None and pid == worker['pid']:
                record['recorded_start_matches'] = record['start_ticks'] == worker['start_ticks']
            live.append(record)
    return live


def _check_process(value, leader):
    if type(value) is not dict or set(value) != {'pid', 'start_ticks', 'pgid', 'sid', 'uid', 'exe_identity'}:
        raise ValueError('CI worker schema refused')
    for key in ('pid', 'start_ticks', 'pgid', 'sid', 'uid'):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError('CI worker numeric identity refused')
    if any(value[key] == 0 for key in ('pid', 'pgid', 'sid')) or value['uid'] != 0:
        raise ValueError('CI worker root identity refused')
    if leader and (value['pgid'] != value['pid'] or value['sid'] != value['pid']):
        raise ValueError('CI worker root session refused')
    identity = value['exe_identity']
    if type(identity) is not list or len(identity) != 9 or any(type(v) is not int for v in identity):
        raise ValueError('CI worker executable identity refused')


def _check_worker(value):
    if type(value) is not dict or set(value) != {'pid', 'start_ticks', 'pgid', 'sid', 'uid', 'exe_identity', 'supervisor'}:
        raise ValueError('CI worker and supervisor schema refused')
    writer = {key: value[key] for key in value if key != 'supervisor'}
    _check_process(writer, True); _check_process(value['supervisor'], False)
    if value['pid'] == value['supervisor']['pid'] or value['sid'] == value['supervisor']['sid']:
        raise ValueError('CI supervisor separation refused')
    return value


def _check_ledger_state(value, context):
    if type(value) is not dict or set(value) != {'schema', 'context', 'phase', 'setup_worker', 'cleanup_worker', 'private_identity', 'lock_identity'}:
        raise ValueError('CI ledger schema refused')
    supplied = value['context']
    if type(supplied) is not dict or set(supplied) != set(context):
        raise ValueError('CI ledger context shape refused')
    rebuilt = _context(*(supplied[key] for key in ('workflow', 'run', 'attempt', 'job', 'uid', 'gid', 'head', 'tree')))
    if value['schema'] != 'hepta.ci-namespace-python-ledger.v1' or supplied != context or supplied != rebuilt:
        raise ValueError('CI ledger context refused')
    if type(value['lock_identity']) is not list or len(value['lock_identity']) != 9 or any(type(v) is not int for v in value['lock_identity']):
        raise ValueError('CI ledger lock identity refused')
    if value['phase'] not in ('STARTED', 'READY', 'RETIRED'):
        raise ValueError('CI ledger phase refused')
    for field in ('setup_worker', 'cleanup_worker'):
        worker = value[field]
        if worker is None:
            if field == 'setup_worker' and (value['phase'] != 'RETIRED' or value['private_identity'] is not None):
                raise ValueError('CI missing worker identity refused')
            continue
        _check_worker(worker)
    private = value['private_identity']
    if private is not None and (type(private) is not list or len(private) != 9 or any(type(v) is not int for v in private)):
        raise ValueError('CI ledger private identity refused')
    if value['phase'] == 'READY' and private is None:
        raise ValueError('CI ready private identity missing')
    return value


@contextmanager
def _ledger_lock(context, create):
    _root_owned(Path('/')); _root_owned(Path('/var')); _root_owned(BASE)
    directory = Path(context['ledger']); made = False
    try: directory.mkdir(mode=0o700); made = True
    except FileExistsError:
        if create: raise ValueError('CI allocation or retired ledger already exists')
    boundary = _root_owned(directory, 0o700)
    lock = directory / 'lock'
    if made: _write_new(lock, b'', 0o600)
    _root_owned(lock, 0o600)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        observed = os.fstat(fd)
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1 or observed.st_size != 0:
            raise ValueError('CI ledger lock object refused')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def current():
            actual = _root_owned(directory, 0o700)
            if (actual.st_dev, actual.st_ino) != (boundary.st_dev, boundary.st_ino):
                raise ValueError('CI ledger directory replaced')
            actual = _root_owned(lock, 0o600)
            if _identity(actual) != _identity(os.fstat(fd)):
                raise ValueError('CI ledger lock inode replaced')
            if set(os.listdir(directory)) != ({'lock'} if made and not (directory / 'state.json').exists() else {'lock', 'state.json'}):
                raise ValueError('CI ledger inventory or interrupted state refused')
            return _identity(os.fstat(fd))
        current()
        yield directory, made, current
        current()
    finally: os.close(fd)


def _ledger_write(directory, value, current):
    current(); target = directory / 'state.json'
    if target.exists(): _root_owned(target, 0o600)
    pending = directory / 'pending.json'
    _write_new(pending, (json.dumps(value, sort_keys=True) + '\n').encode(), 0o600)
    os.replace(pending, target)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try: os.fsync(fd)
    finally: os.close(fd)
    current()
    return value


def _ledger_put(directory, context, phase, worker, private, current, cleanup_worker=None):
    identity = current(); target = directory / 'state.json'
    if target.exists():
        previous = _ledger_get(directory, context, current)
        if previous['phase'] == 'RETIRED' or (previous['phase'] == 'READY' and phase != 'RETIRED'):
            raise ValueError('CI phase revival refused')
        if (previous['setup_worker'] != worker or previous['cleanup_worker'] != cleanup_worker or
                (previous['private_identity'] is not None and previous['private_identity'] != private)):
            raise ValueError('CI phase handoff identity changed')
    elif phase not in ('STARTED', 'RETIRED'):
        raise ValueError('CI initial phase refused')
    value = _check_ledger_state({'schema': 'hepta.ci-namespace-python-ledger.v1', 'context': context,
                                'phase': phase, 'setup_worker': worker, 'cleanup_worker': cleanup_worker,
                                'private_identity': private, 'lock_identity': identity}, context)
    return _ledger_write(directory, value, current)


def _ledger_begin_cleanup(directory, context, cleanup_worker, current):
    previous = _ledger_get(directory, context, current)
    if cleanup_worker in (previous['setup_worker'], previous['cleanup_worker']):
        raise ValueError('CI previous operation cannot be current writer')
    # No caller assertion can authorize replacing a previous operation record.
    _no_owned_lifecycle(context, previous, cleanup_worker)
    value = dict(previous); value['cleanup_worker'] = cleanup_worker
    _check_ledger_state(value, context)
    # RETIRED remains RETIRED; only the cleanup operation identity changes.
    return _ledger_write(directory, value, current)


def _ledger_get(directory, context, current):
    path = directory / 'state.json'; _root_owned(path, 0o600)
    value = _check_ledger_state(_strict_json(_read(path, 16384)[0]), context)
    if value['lock_identity'] != current(): raise ValueError('CI original ledger lock replaced')
    return value


def _no_owned_lifecycle(context, state, current_writer=None):
    for field in ('setup_worker', 'cleanup_worker'):
        worker = state[field]
        if _live_setup_workers(context, worker, exclude=current_writer):
            raise ValueError('CI root operation session remains')
        if worker is not None and worker != current_writer and _live_setup_workers(context, worker['supervisor']):
            raise ValueError('CI previous root supervision session remains')
    if _live_private(state['private_identity'], context['profile']):
        raise ValueError('CI private interpreter remains')


def _root_setup(context):
    with _ledger_lock(context, True) as (ledger, made, current):
        worker = _capture_root_worker(context, '_setup_root')
        _ledger_put(ledger, context, 'STARTED', worker, None, current)
        return _setup_locked(context, ledger, worker, current)


def _root_cleanup(context):
    with _ledger_lock(context, False) as (ledger, made, current):
        cleanup_worker = _capture_root_worker(context, '_cleanup_root')
        if made:
            state = _ledger_put(ledger, context, 'RETIRED', None, None, current, cleanup_worker)
        else:
            state = _ledger_begin_cleanup(ledger, context, cleanup_worker, current)
        _no_owned_lifecycle(context, state, cleanup_worker)
        directory = Path(context['directory'])
        if state['phase'] == 'RETIRED':
            if directory.exists() or any(line.split(' (', 1)[0] == context['profile'] for line in _profiles()):
                raise ValueError('CI retired ledger still has active allocation')
            _no_owned_lifecycle(context, state, cleanup_worker); current()
            return {'cleanup': 'NO_ALLOCATION_RETIRED_MARKER_RECORDED' if made else 'ALREADY_RETIRED_MARKER_RECORDED',
                    'retirement_ledger_retained': True, 'active_profile_and_interpreter_absent': True,
                    'operation_worker': cleanup_worker, 'setsid_provider': _executable(SETSID),
                    'python_provider': _executable(PYTHON), 'root_worker_supervisor_all_exited': False}
        result = _cleanup_locked(context, state)
        _no_owned_lifecycle(context, state, cleanup_worker); current()
        _ledger_put(ledger, context, 'RETIRED', state['setup_worker'], state['private_identity'], current, cleanup_worker)
        _no_owned_lifecycle(context, state, cleanup_worker)
        result['retirement_ledger_retained'] = True
        result['operation_worker'] = cleanup_worker; result['setsid_provider'] = _executable(SETSID)
        result['python_provider'] = _executable(PYTHON); result['root_worker_supervisor_all_exited'] = False
        return result


def _setup_locked(context, ledger, worker, current):
    _root_owned(Path('/')); _root_owned(Path('/var')); _root_owned(BASE)
    directory = Path(context['directory'])
    before = _global(); profiles = _profiles()
    if any(line.split(' (', 1)[0] == context['profile'] for line in profiles):
        raise ValueError('CI named profile already exists')
    original = _executable(PYTHON)
    template, unused = _read(ROOT / TEMPLATE)
    profile = _render(context, template)
    directory.mkdir(mode=0o755); _root_owned(directory, 0o755)
    (directory / 'bin').mkdir(mode=0o755); _root_owned(directory / 'bin', 0o755)
    raw, observed = _read(PYTHON, 64 * 1024 * 1024)
    if _identity(observed) != original['identity'] or _sha(raw) != original['sha256']:
        raise ValueError('CI interpreter input changed')
    private = directory / 'bin/python3'
    _write_new(private, raw, 0o755)
    copied = _executable(private)
    if any(copied[key] != original[key] for key in ('bytes', 'sha256')):
        raise ValueError('CI interpreter copy differs')
    _write_new(directory / 'profile', profile, 0o600)
    state = {'schema': 'hepta.ci-namespace-python-state.v1', 'context': context,
             'global': before, 'profiles_before': profiles, 'original': original,
             'private': copied, 'profile_sha256': _sha(profile), 'setup_worker': worker}
    _write_new(directory / 'state.json', (json.dumps(state, sort_keys=True) + '\n').encode(), 0o600)
    _ledger_put(ledger, context, 'STARTED', worker, copied['identity'], current)
    _command(['/sbin/apparmor_parser', '-a', str(directory / 'profile')], new_session=False)
    expected = [line for line in _profiles() if line.split(' (', 1)[0] == context['profile']]
    if len(expected) != 1 or _global() != before:
        raise ValueError('CI profile or global security readback differs')
    _write_new(directory / 'loaded', b'verified\n', 0o600)
    _ledger_put(ledger, context, 'READY', worker, copied['identity'], current)
    return {'directory': str(directory), 'profile': context['profile'], 'private': copied,
            'global_unchanged': True, 'corpus_root': False,
            'operation_worker': worker, 'setsid_provider': _executable(SETSID),
            'python_provider': original, 'operation_ready_marker_recorded': True,
            'root_worker_supervisor_all_exited': False}


def _live_private(identity, profile, proc=Path('/proc')):
    count = 0; live = []
    with os.scandir(proc) as entries:
        for entry in entries:
            count += 1
            if count > 65536: raise ValueError('CI process inventory bound refused')
            if not entry.name.isdecimal(): continue
            try: label = _kernel_read(proc / entry.name / 'attr/current', 4096).decode('utf-8', 'strict').rstrip('\n\0')
            except FileNotFoundError: continue
            if label.startswith(profile + ' ('):
                live.append(int(entry.name)); continue
            try: value = (proc / entry.name / 'exe').stat()
            except FileNotFoundError: continue
            # Other read failures remain failures; never infer absence.
            if identity is None: continue
            if [value.st_dev, value.st_ino] == identity[:2]:
                live.append(int(entry.name)); continue
            try: maps = _kernel_read(proc / entry.name / 'maps', 4 * 1024 * 1024)
            except FileNotFoundError: continue
            for line in maps.splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) < 5: raise ValueError('CI executable maps shape refused')
                device = fields[3].split(b':')
                if len(device) != 2: raise ValueError('CI executable maps device refused')
                if ([int(device[0], 16), int(device[1], 16)] == [os.major(identity[0]), os.minor(identity[0])] and
                        int(fields[4]) == identity[1]):
                    live.append(int(entry.name)); break
    return live


def _cleanup_locked(context, ledger_state):
    directory = Path(context['directory'])
    _root_owned(Path('/')); _root_owned(Path('/var')); _root_owned(BASE)
    try: directory.lstat()
    except FileNotFoundError:
        if any(line.split(' (', 1)[0] == context['profile'] for line in _profiles()):
            raise ValueError('CI orphan named profile without owned state')
        return {'cleanup': 'NO_ALLOCATION_RETIRED_MARKER_RECORDED', 'no_owned_profile_or_directory': True}
    _root_owned(directory, 0o755); _root_owned(directory / 'bin', 0o755)
    _root_owned(directory / 'state.json', 0o600); _root_owned(directory / 'profile', 0o600)
    raw, unused = _read(directory / 'state.json')
    state = _strict_json(raw)
    if type(state) is not dict or set(state) != {'schema', 'context', 'global', 'profiles_before', 'original', 'private', 'profile_sha256', 'setup_worker'}:
        raise ValueError('CI closed state differs')
    if state['schema'] != 'hepta.ci-namespace-python-state.v1' or state['context'] != context:
        raise ValueError('CI cleanup context differs')
    if state['setup_worker'] != ledger_state['setup_worker'] or state['private']['identity'] != ledger_state['private_identity']:
        raise ValueError('CI ledger handoff differs')
    if _global() != state['global'] or _executable(PYTHON) != state['original']:
        raise ValueError('CI original host input changed')
    private = directory / 'bin/python3'
    if _executable(private) != state['private'] or _live_private(state['private']['identity'], context['profile']):
        raise ValueError('CI private interpreter changed or still executing')
    profile, unused = _read(directory / 'profile')
    template, unused = _read(ROOT / TEMPLATE)
    if profile != _render(context, template) or _sha(profile) != state['profile_sha256']:
        raise ValueError('CI owned profile changed')
    current = _profiles()
    owned = [line for line in current if line.split(' (', 1)[0] == context['profile']]
    loaded = directory / 'loaded'
    completed_setup = loaded.exists()
    if completed_setup:
        _root_owned(loaded, 0o600)
        if _read(loaded)[0] != b'verified\n': raise ValueError('CI setup marker differs')
    if ((completed_setup and len(owned) != 1) or len(owned) > 1 or
            sorted(line for line in current if line not in owned) != state['profiles_before']):
        raise ValueError('CI unrelated profile changed')
    if set(os.listdir(directory)) != {'bin', 'profile', 'state.json'} | ({'loaded'} if completed_setup else set()):
        raise ValueError('CI owned directory inventory differs')
    if os.listdir(directory / 'bin') != ['python3']:
        raise ValueError('CI owned bin inventory differs')
    if owned: _command(['/sbin/apparmor_parser', '-R', str(directory / 'profile')], new_session=False)
    _no_owned_lifecycle(context, ledger_state, ledger_state['cleanup_worker'])
    if (_profiles() != state['profiles_before'] or _global() != state['global'] or
            _live_private(state['private']['identity'], context['profile'])):
        raise ValueError('CI cleanup security or process readback differs')
    if set(os.listdir(directory)) != {'bin', 'profile', 'state.json'} | ({'loaded'} if completed_setup else set()):
        raise ValueError('CI owned directory inventory differs')
    if os.listdir(directory / 'bin') != ['python3']:
        raise ValueError('CI owned bin inventory differs')
    private.unlink(); (directory / 'bin').rmdir()
    if completed_setup: loaded.unlink()
    (directory / 'profile').unlink(); (directory / 'state.json').unlink(); directory.rmdir()
    return {'cleanup': 'RETIRED_MARKER_RECORDED', 'global_unchanged': True, 'no_owned_python_processes': True}


def _runner_preflight(context):
    status = dict(line.split(':', 1) for line in _kernel_read(Path('/proc/self/status'), 65536).decode().splitlines() if ':' in line)
    label = _kernel_read(Path('/proc/self/attr/current'), 4096).decode().rstrip('\n\0')
    if os.getuid() != context['uid'] or os.getgid() != context['gid']:
        raise ValueError('CI runner identity changed')
    if any(int(status[name].strip(), 16) for name in CAPS[:4]):
        raise ValueError('CI runner host capability gained')
    if not label.startswith(context['profile'] + ' ('):
        raise ValueError('CI private interpreter label unavailable or differs')
    return {'uid': os.getuid(), 'gid': os.getgid(), 'label': label,
            'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
            'executable': sys.executable, 'caps': {name: int(status[name].strip(), 16) for name in CAPS},
            'nnp': status['NoNewPrivs'].strip(), 'global': _global()}


def _normal_runner_fact():
    status = dict(line.split(':', 1) for line in _kernel_read(Path('/proc/self/status'), 65536).decode().splitlines() if ':' in line)
    if any(int(status[name].strip(), 16) for name in CAPS[:4]):
        raise ValueError('CI normal runner host capability differs')
    return {'uid': os.getuid(), 'gid': os.getgid(),
            'label': _kernel_read(Path('/proc/self/attr/current'), 4096).decode().rstrip('\n\0'),
            'caps': {name: int(status[name].strip(), 16) for name in CAPS},
            'nnp': status['NoNewPrivs'].strip(), 'global': _global(),
            'prefix': sys.prefix, 'base_prefix': sys.base_prefix}


def _completed_operation(context, result, provider, python_provider):
    # This runs only after sudo/setsid direct child wait completes. Neither
    # returncode nor RETIRED phase substitutes for actual remaining-process
    # readback. No writer/supervisor PID or whole group is excluded here.
    worker = _check_worker(result['operation_worker'])
    if type(result['root_worker_supervisor_all_exited']) is not bool or result['root_worker_supervisor_all_exited'] is not False:
        raise ValueError('CI premature root completion claim refused')
    if (result['setsid_provider'] != provider or _executable(SETSID) != provider or
            result['python_provider'] != python_provider or _executable(PYTHON) != python_provider or
            worker['exe_identity'] != python_provider['identity'] or worker['supervisor']['exe_identity'] != provider['identity']):
        raise ValueError('CI fixed setsid provider readback changed')
    if _live_setup_workers(context, worker) or _live_setup_workers(context, worker['supervisor']):
        raise ValueError('CI post-wait root operation or supervision remains')


def _main(argv):
    if len(argv) == 9 and argv[0] in ('_setup_root', '_cleanup_root', '_runner_preflight'):
        context = _context(argv[1], argv[2], argv[3], argv[4], int(argv[5]), int(argv[6]), argv[7], argv[8])
        if argv[0] == '_runner_preflight': return _runner_preflight(context)
        if os.geteuid() != 0 or os.environ.get('SUDO_UID') != str(context['uid']) or os.environ.get('SUDO_GID') != str(context['gid']):
            raise ValueError('CI actual sudo caller differs')
        return (_root_setup if argv[0] == '_setup_root' else _root_cleanup)(context)
    if argv not in (['setup'], ['cleanup']) or os.environ.get('GITHUB_ACTIONS') != 'true' or os.geteuid() == 0:
        raise ValueError('CI fixed normal-runner invocation refused')
    if Path(sys.executable).resolve() != PYTHON:
        raise ValueError('CI original interpreter provider differs')
    head = _command(['/usr/bin/git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip()
    tree = _command(['/usr/bin/git', '-C', str(ROOT), 'rev-parse', 'HEAD^{tree}']).decode().strip()
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise ValueError('CI runner repository differs')
    workflow = _workflow_ref(os.environ['GITHUB_WORKFLOW_REF'])
    context = _context(workflow, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], os.environ['GITHUB_JOB'],
                       os.getuid(), os.getgid(), head, tree)
    arguments = [context[key] for key in ('workflow', 'run', 'attempt', 'job')]
    arguments += [str(context['uid']), str(context['gid']), head, tree]
    normal = _normal_runner_fact()
    original_prefix = (sys.prefix, sys.base_prefix)
    provider = _executable(SETSID); python_provider = _executable(PYTHON)
    result = _strict_json(_command(['/usr/bin/sudo', '--non-interactive', str(SETSID), '--fork', '--wait', '--', str(PYTHON), str(Path(__file__).resolve()),
                                   '_setup_root' if argv == ['setup'] else '_cleanup_root', *arguments]))
    _completed_operation(context, result, provider, python_provider)
    if argv == ['cleanup']:
        markers = {'RETIRED_MARKER_RECORDED': 'PASS', 'NO_ALLOCATION_RETIRED_MARKER_RECORDED': 'NO_ALLOCATION_RETIRED', 'ALREADY_RETIRED_MARKER_RECORDED': 'ALREADY_RETIRED'}
        result['cleanup'] = markers[result['cleanup']]
    result['root_worker_supervisor_all_exited'] = True
    result['actual_root_operation_and_supervision_absent_after_wait'] = True
    if _normal_runner_fact() != normal:
        raise ValueError('CI normal runner or global security changed')
    result['actual_normal_runner_before_after'] = normal
    if argv == ['setup']:
        private = context['directory'] + '/bin/python3'
        before = _strict_json(_command([private, str(Path(__file__).resolve()), '_runner_preflight', *arguments]))
        if (before['prefix'], before['base_prefix']) != original_prefix or before['executable'] != private:
            raise ValueError('CI private stdlib or actual executable differs')
        path = Path(os.environ['GITHUB_PATH'])
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            observed = os.fstat(fd)
            if not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.getuid() or observed.st_nlink != 1:
                raise ValueError('CI runner PATH output refused')
            line = (context['directory'] + '/bin\n').encode()
            if os.write(fd, line) != len(line): raise ValueError('CI runner PATH short write')
        finally: os.close(fd)
        result['actual_runner_preflight'] = before
    return result


def main():
    try:
        result = _main(sys.argv[1:])
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, UnicodeError, RecursionError, subprocess.SubprocessError):
        print('CI_NAMESPACE_PYTHON_REFUSED', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
