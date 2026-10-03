#!/usr/bin/env python3
"""Job-private CI namespace permission; no production deployment or fallback.

Only fixed internal setup/cleanup commands use sudo. The original corpus runs
as its original runner UID with a real byte-identical private Python file.
AppArmor/sysctls remain enabled and unchanged outside the named attachment.
This trusted CI configuration is not a hostile-Python-code sandbox.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('/var/lib')
PYTHON = Path('/usr/bin/python3.12')
TEMPLATE = '.github/apparmor/hepta-ci-namespace-python.v1.profile'
TEMPLATE_SHA256 = '9d6bf7dc994cc4b7e19444c1d1b633327ccc22bb202c4c7685a3125ae0b157be'
JOBS = ('repository-contracts', 'repository-contracts-prospective-merge')
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


def _context(run, attempt, job, uid, gid, head, tree):
    _decimal(run, (1 << 64) - 1); _decimal(attempt, 9999)
    if type(job) is not str or job not in JOBS or type(uid) is not int or not 0 < uid < (1 << 32) - 1:
        raise ValueError('CI job or non-root UID refused')
    if type(gid) is not int or not 0 <= gid < (1 << 32) - 1:
        raise ValueError('CI GID refused')
    if any(type(value) is not str or not re.fullmatch(r'[0-9a-f]{40}', value) for value in (head, tree)):
        raise ValueError('CI source tuple refused')
    name = f'hepta-ci-g1-{run}-{attempt}-{job}'
    return {'run': run, 'attempt': attempt, 'job': job, 'uid': uid, 'gid': gid,
            'head': head, 'tree': tree, 'profile': name, 'directory': str(BASE / name)}


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
    keys = {'run', 'attempt', 'job', 'uid', 'gid', 'head', 'tree', 'profile', 'directory'}
    if type(context) is not dict or set(context) != keys or type(template) is not bytes:
        raise ValueError('CI closed attachment context refused')
    expected = _context(*(context[key] for key in ('run', 'attempt', 'job', 'uid', 'gid', 'head', 'tree')))
    if context != expected: raise ValueError('CI fixed attachment differs')
    if _sha(template) != TEMPLATE_SHA256: raise ValueError('CI template changed')
    interpreter = context['directory'] + '/bin/python3'
    text = template.decode('ascii', 'strict')
    if text.count('@@PROFILE@@') != 1 or text.count('@@INTERPRETER@@') != 1:
        raise ValueError('CI attachment template refused')
    return text.replace('@@PROFILE@@', context['profile']).replace('@@INTERPRETER@@', interpreter).encode()


def _command(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    if len(result.stdout) > LIMIT or len(result.stderr) > LIMIT or result.returncode:
        raise ValueError('CI fixed operation refused')
    return result.stdout


def _root_setup(context):
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
             'private': copied, 'profile_sha256': _sha(profile)}
    _write_new(directory / 'state.json', (json.dumps(state, sort_keys=True) + '\n').encode(), 0o600)
    _command(['/sbin/apparmor_parser', '-a', str(directory / 'profile')])
    expected = [line for line in _profiles() if line.split(' (', 1)[0] == context['profile']]
    if len(expected) != 1 or _global() != before:
        raise ValueError('CI profile or global security readback differs')
    _write_new(directory / 'loaded', b'verified\n', 0o600)
    return {'directory': str(directory), 'profile': context['profile'], 'private': copied,
            'global_unchanged': True, 'corpus_root': False}


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
            if [value.st_dev, value.st_ino] == identity[:2]: live.append(int(entry.name))
    return live


def _root_cleanup(context):
    directory = Path(context['directory'])
    _root_owned(Path('/')); _root_owned(Path('/var')); _root_owned(BASE)
    try: directory.lstat()
    except FileNotFoundError:
        if any(line.split(' (', 1)[0] == context['profile'] for line in _profiles()):
            raise ValueError('CI orphan named profile without owned state')
        return {'cleanup': 'NO_ALLOCATION', 'no_owned_profile_or_directory': True}
    _root_owned(directory, 0o755); _root_owned(directory / 'bin', 0o755)
    _root_owned(directory / 'state.json', 0o600); _root_owned(directory / 'profile', 0o600)
    raw, unused = _read(directory / 'state.json')
    state = _strict_json(raw)
    if type(state) is not dict or set(state) != {'schema', 'context', 'global', 'profiles_before', 'original', 'private', 'profile_sha256'}:
        raise ValueError('CI closed state differs')
    if state['schema'] != 'hepta.ci-namespace-python-state.v1' or state['context'] != context:
        raise ValueError('CI cleanup context differs')
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
    if owned: _command(['/sbin/apparmor_parser', '-R', str(directory / 'profile')])
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
    return {'cleanup': 'PASS', 'global_unchanged': True, 'no_owned_python_processes': True}


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


def _main(argv):
    if len(argv) == 8 and argv[0] in ('_setup_root', '_cleanup_root', '_runner_preflight'):
        context = _context(argv[1], argv[2], argv[3], int(argv[4]), int(argv[5]), argv[6], argv[7])
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
    context = _context(os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], os.environ['GITHUB_JOB'],
                       os.getuid(), os.getgid(), head, tree)
    arguments = [context[key] for key in ('run', 'attempt', 'job')]
    arguments += [str(context['uid']), str(context['gid']), head, tree]
    normal = _normal_runner_fact()
    original_prefix = (sys.prefix, sys.base_prefix)
    result = _strict_json(_command(['/usr/bin/sudo', '--non-interactive', str(PYTHON), str(Path(__file__).resolve()),
                                   '_setup_root' if argv == ['setup'] else '_cleanup_root', *arguments]))
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
