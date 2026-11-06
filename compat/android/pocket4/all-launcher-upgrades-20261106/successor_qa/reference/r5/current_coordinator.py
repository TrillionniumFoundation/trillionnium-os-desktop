"""Typed current-baseline coordinator utilities. Importing performs no operations.
Fresh app workflows must use these new names and new recorder init options.
Historical activation receipts are lineage only; runtime admission is separate.
"""
import hashlib,json,os,signal,stat,subprocess,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASELINE=Path("/home/alex/work/pocket4-main-current-baseline-01/baseline.private.json")
BASELINE_SHA="163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266"
QUALIFICATION=Path("/home/alex/work/pocket4-main-current-baseline-01/qualification.json")
QUALIFICATION_SHA="f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6"
EPOCH="734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2"
EPOCH_SOURCE=HERE/'references/framework_epoch.py'
EPOCH_SOURCE_SHA='f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
GUARD_SOURCE=HERE/'current_baseline_guard.py'
GUARD_SOURCE_SHA="0ee54ef97c073857609aedb4670395db084ceacc7d28558315647ab2ffbef679"
ENV={'PATH':'/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'}

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path, maximum=1024 * 1024, expected=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_size <= maximum,
                'bounded single-link regular file required: ' + str(path))
        data = bytearray()
        while len(data) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        last = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(all(getattr(first, k) == getattr(last, k) for k in fields) and len(data) == first.st_size,
                'input changed or exceeded bound')
        if expected is not None:
            require(digest(data) == expected, 'input hash changed: ' + str(path))
        return bytes(data)
    finally:
        os.close(fd)

def write_new(path, value, mode=0o600):
    data = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}

def module(raw, filename, name):
    value = types.ModuleType(name)
    value.__file__ = str(filename)
    exec(compile(raw, str(filename), 'exec'), value.__dict__)
    return value

def run_cli(name, argv, timeout, evidence, guard):
    guard()
    write_new(evidence / (name + '.intent.json'), {'argv': argv, 'timeout_seconds': timeout,
        'separate_process': True, 'automatic_retry': False})
    observed = {'name': name, 'argv': argv, 'spawned': False, 'joined': False, 'timed_out': False,
                'returncode': None, 'secondary_errors': [], 'Main_before': True}
    process = pidfd = None
    primary = None
    streams = []
    try:
        for suffix in ('.stdout', '.stderr'):
            streams.append(open(evidence / (name + suffix), 'xb'))
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=streams[0], stderr=streams[1],
                                   env=ENV, close_fds=True)
        observed.update(spawned=True, owned_child_pid=process.pid)
        pidfd = os.pidfd_open(process.pid, 0)
        try:
            observed['returncode'] = process.wait(timeout=timeout)
            observed['joined'] = True
        except BaseException as error:
            observed['timed_out'] = isinstance(error, subprocess.TimeoutExpired)
            raise
    except BaseException as error:
        primary = error
        observed['primary_error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if process is not None and not observed['joined']:
            try:
                if process.poll() is None:
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # Exact Popen child, no intervening wait/reaper; no ambient PID selection.
                        process.kill()
                observed['returncode'] = process.wait(timeout=6)
                observed['joined'] = True
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'owned-child-retirement', 'error': repr(error)})
        if pidfd is not None:
            try:
                os.close(pidfd)
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'owned-pidfd-close', 'error': repr(error)})
        for stream in streams:
            try:
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-sync', 'error': repr(error)})
            try:
                stream.close()
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-close', 'error': repr(error)})
        try:
            observed['Main_after'] = guard()
        except BaseException as error:
            observed['secondary_errors'].append({'stage': 'Main-after', 'error': repr(error)})
        for suffix in ('.stdout', '.stderr'):
            try:
                data = read(evidence / (name + suffix))
                observed[suffix[1:]] = {'bytes': len(data), 'sha256': digest(data)}
            except BaseException as error:
                observed['secondary_errors'].append({'stage': 'output-read', 'error': repr(error)})
        try:
            write_new(evidence / (name + '.result.json'), observed)
        except BaseException as error:
            observed['secondary_errors'].append({'stage': 'phase-result-write', 'error': repr(error)})
            if primary is None:
                primary = error
            else:
                primary.add_note('phase result write: ' + repr(error))
    if primary is not None:
        raise primary
    require(observed['joined'] and observed['returncode'] == 0 and not observed['secondary_errors'],
            name + ' did not complete exactly once with a preserved Main fence')
    return json.loads(read(evidence / (name + '.stdout')))

def guard_module():
    guard=module(read(GUARD_SOURCE,expected=GUARD_SOURCE_SHA),GUARD_SOURCE,'current_coordinator_guard')
    require(guard.BASELINE_SHA==BASELINE_SHA and guard.QUALIFICATION_SHA==QUALIFICATION_SHA and
            guard.MAIN_EPOCH==EPOCH,'CURRENT_COORDINATOR_GUARD_BINDING_CHANGED')
    return guard
def current_baseline():
    return guard_module().current_baseline()
def main_guard(baseline=None,epoch=None):
    return guard_module().current_guard(baseline,action_attempted=False)
