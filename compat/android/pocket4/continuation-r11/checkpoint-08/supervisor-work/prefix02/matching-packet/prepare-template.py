"""Stage prefix02 and run fresh Python controls, retaining the exact prior probe."""
from pathlib import Path
import datetime
import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import traceback

CFG = __CFG__
OUT = Path('/home/alex/work/pocket4-relay-prefix-r11-source-05-02')
PRIOR = Path('/home/alex/work/pocket4-relay-prefix-r11-source-05-01')
BASE = Path('/home/alex/work/pocket4-relay-prefix-r11-owned')
NAMES = {'full_prefix_control.py', 'prefix_coordinator.py', 'prefix_probe.c',
         'test_prefix_control.py', 'test_prefix_coordinator.py', 'main-cmdline-actual-diagnostic.json'}
PRIOR_SHA = '1e70d9df93309ff5be991f0a20e4b5b4493e57a0b64fcc3881075e652a5ae712'
PROBE_SHA = '79b30f9fa4a1e7635ae4786a50372b3fcaa84ad619269476e40a1badd65c0e82'
C_SHA = 'd088edf44d523a67e2881ce6c0715a4885664f11c5315938e04f52738c43a34a'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
       'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(OUT/'tmp')}

def need(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def private_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    s = os.fstat(fd)
    if not (s.st_uid == s.st_gid == 0 and stat.S_ISDIR(s.st_mode)
            and stat.S_IMODE(s.st_mode) == 0o700):
        os.close(fd)
        raise RuntimeError('existing source/base is not root-private')
    return fd

def read_file(path, maximum=65536):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0
             and before.st_nlink == 1 and before.st_mode & 0o6022 == 0
             and 0 < before.st_size <= maximum, 'owned artifact metadata differs: ' + str(path))
        value = bytearray()
        while True:
            block = os.read(fd, min(8192, maximum + 1 - len(value)))
            if not block:
                break
            value.extend(block)
            need(len(value) <= maximum, 'owned artifact grew')
        need(stamp(before) == stamp(os.fstat(fd)) and len(value) == before.st_size,
             'owned artifact changed during read')
        return bytes(value), before
    finally:
        os.close(fd)

def put(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())

def inventory():
    result = {}
    for name in sorted(NAMES):
        raw, _ = read_file(OUT/'source'/name)
        result[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    return result

def verify_prior(priorfd, basefd):
    raw, _ = read_file(PRIOR/'build-result.json')
    need(sha(raw) == PRIOR_SHA, 'exact prior matching build differs')
    prior = json.loads(raw)
    need(prior['success'] is True and prior['native_ordinary_controls_passed'] == 6
         and prior['inputs_before'] == prior['inputs_after'], 'prior native/source evidence incomplete')
    need(prior['probe'] == CFG['probe'], 'prior compiled probe identity differs')
    for key in ('namespace_actions', 'network_actions', 'systemd_unit_actions', 'Android_operations', 'Main_actions'):
        need(prior[key] == 0, 'prior compilation scope differs')
    for name in ('full_prefix_control.py', 'prefix_probe.c', 'test_prefix_control.py'):
        original, _ = read_file(PRIOR/'source'/name)
        expected = prior['inputs_before'][name]
        need(sha(original) == expected['sha256'] and len(original) == expected['bytes']
             and CFG['files'][name]['sha256'] == expected['sha256'],
             'unchanged actor/C/transport source differs: ' + name)
    need(CFG['files']['prefix_probe.c']['sha256'] == C_SHA, 'probe C code changed')
    for path, fd in ((PRIOR, priorfd), (BASE, basefd)):
        held, named = os.fstat(fd), os.stat(path, follow_symlinks=False)
        need((held.st_dev, held.st_ino) == (named.st_dev, named.st_ino), 'original directory path replaced')
    held = os.fstat(basefd)
    need([held.st_dev, held.st_ino] == [prior['owned_attempt_base']['device'], prior['owned_attempt_base']['inode']],
         'original prefix base object differs')
    return prior

def verify_probe(actor, descriptor, prior):
    s = actor['verify_fd'](descriptor, PROBE_SHA, True)
    pin = prior['probe']
    need(pin['path'] == str(PRIOR/'bin/prefix-probe') and pin['sha256'] == PROBE_SHA
         and (s.st_dev, s.st_ino, s.st_size, stat.S_IMODE(s.st_mode), s.st_uid, s.st_gid)
         == (66306, 34481448, 21752, 0o700, 0, 0), 'original compiled probe object differs')
    named = os.stat(PRIOR/'bin/prefix-probe', follow_symlinks=False)
    need(stamp(named) == stamp(s), 'original probe path/object differs')
    return pin

need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'exact root stage required')
need(set(CFG['files']) == NAMES and os.uname().machine == 'x86_64', 'complete exact host source set required')
os.umask(0o077)
OUT.mkdir(mode=0o700)
(OUT/'source').mkdir(mode=0o700)
(OUT/'tmp').mkdir(mode=0o700)
report = {'schema': 1, 'scope': 'fresh prefix02 Python controls and exact original native probe reuse',
          'success': False, 'source_freeze_manifest_sha256': CFG['manifest_sha256'], 'commands': [],
          'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'namespace_actions': 0, 'network_actions': 0, 'systemd_unit_actions': 0,
          'Android_operations': 0, 'Main_actions': 0, 'runtime_started': False,
          'runtime_prefix_qualified': False, 'actual_Rust_Owner_executed': False, 'production_ready': False,
          'new_native_build_performed': False, 'new_native_controls_executed': 0,
          'prior_native_ordinary_controls_referenced': 6, 'prior_build_result_sha256': PRIOR_SHA}
handles = []

def run(name):
    argv = ['/usr/bin/python3', '-I', '-B', str(OUT/'source'/name)]
    try:
        result = subprocess.run(argv, env=ENV, cwd=OUT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or b'', error.stderr or b''
        put(OUT/(name + '.stdout'), stdout)
        put(OUT/(name + '.stderr'), stderr)
        report['commands'].append({'argv': argv, 'returncode': None, 'timed_out': True,
                                  'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr)})
        raise
    put(OUT/(name + '.stdout'), result.stdout)
    put(OUT/(name + '.stderr'), result.stderr)
    need(len(result.stdout) <= 65536 and len(result.stderr) <= 65536, 'test output exceeded bound')
    report['commands'].append({'argv': argv, 'returncode': result.returncode,
                              'stdout': result.stdout.decode('utf-8', 'strict'),
                              'stderr': result.stderr.decode('utf-8', 'strict'),
                              'stdout_sha256': sha(result.stdout), 'stderr_sha256': sha(result.stderr)})
    return result

try:
    priorfd = private_directory(PRIOR); handles.append(priorfd)
    basefd = private_directory(BASE); handles.append(basefd)
    prior = verify_prior(priorfd, basefd)
    put(OUT/'prior-probe-build-result.json', read_file(PRIOR/'build-result.json')[0])
    for name, row in CFG['files'].items():
        raw = row['text'].encode('utf-8')
        need(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'payload differs: ' + name)
        put(OUT/'source'/name, raw)
    report['inputs_before'] = inventory()
    need(report['inputs_before'] == {name: {'bytes': row['bytes'], 'sha256': row['sha256']}
                                   for name, row in CFG['files'].items()}, 'written source closure differs')
    actor = {'__name__': 'pinned_reuse_verifier', '__file__': str(OUT/'source/full_prefix_control.py')}
    exec(compile(read_file(OUT/'source/full_prefix_control.py')[0], actor['__file__'], 'exec'), actor)
    probe = os.open(PRIOR/'bin/prefix-probe', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC); handles.append(probe)
    report['probe_before'] = verify_probe(actor, probe, prior)
    counts = {}
    for name, expected in (('test_prefix_control.py', 16), ('test_prefix_coordinator.py', 27)):
        result = run(name)
        observed = re.search(rb'Ran ([0-9]+) tests', result.stderr)
        need(result.returncode == 0 and observed is not None and int(observed.group(1)) == expected,
             'fresh matching controls failed: ' + name)
        counts[name] = expected
    report['python_tests_passed'] = counts
    report['inputs_after'] = inventory()
    need(report['inputs_before'] == report['inputs_after'], 'fresh source changed across controls')
    verify_prior(priorfd, basefd)
    report['probe_after'] = verify_probe(actor, probe, prior)
    need(report['probe_before'] == report['probe_after'], 'held probe binding changed')
    report['native_probe_reuse_verified'] = True
    report['owned_attempt_base'] = prior['owned_attempt_base']
    report['success'] = True
except BaseException as error:
    report['error'] = repr(error)
    report['traceback'] = traceback.format_exc()
finally:
    for fd in reversed(handles):
        os.close(fd)
    report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    need(len(raw) <= 65536, 'matching receipt exceeds fixed reader bound')
    put(OUT/'build-result.json', raw)
    print(json.dumps({'success': report['success'], 'path': str(OUT/'build-result.json'),
                      'bytes': len(raw), 'sha256': sha(raw), 'python_tests_passed': report.get('python_tests_passed'),
                      'native_probe_reuse_verified': report.get('native_probe_reuse_verified', False),
                      'new_native_controls_executed': 0, 'runtime_prefix_qualified': False,
                      'namespace_actions': 0}), flush=True)
raise SystemExit(0 if report['success'] else 1)
