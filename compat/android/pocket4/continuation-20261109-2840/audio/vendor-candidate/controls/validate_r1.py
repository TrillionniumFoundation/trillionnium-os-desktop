from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path('/data/pocket4-audio-qpr1-vendor-candidate-20261109-2840-r1')
SOURCE = ROOT / 'source'
RESULT = ROOT / 'validation-r1'
CARGO = '/home/qian-qi/.cargo/bin/cargo'
PARENT = '4caa694f25b3da022651a1078600a0eb1a5334fc'
OLD_SOURCE = Path('/data/pocket4-audio-source316-offload-20261108-8b88-r1/recipe-released-sdk35-r2')
SOURCE_TERMINAL = Path('/data/pocket4-audio-source316-offload-20261108-8b88-r1/qualification/source-released-sdk35-continuation-r2/RESULT.json')
SOURCE_SHA = 'ca309c277d3bcc962abbaadb1054b334ff2d0eb603bb091a991f60f4896e04ec'

def git(path, *args):
    return subprocess.check_output(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-C', str(path), *args]).decode().strip()

def ref(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

assert os.getuid() == os.geteuid() == 1000
assert git(SOURCE, 'rev-parse', 'HEAD') == PARENT
assert git(OLD_SOURCE, 'rev-parse', 'HEAD') == PARENT and git(OLD_SOURCE, 'status', '--porcelain') == ''
mem_available = int(next(v.split()[1] for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:'))) * 1024
assert mem_available >= 12 * 1024**3
assert shutil.disk_usage(ROOT).free >= 90 * 1024**3
assert os.cpu_count() >= 12
os.sched_setaffinity(0, {8, 9})
assert os.sched_getaffinity(0) == {8, 9}
RESULT.mkdir(mode=0o700, exist_ok=False)
env = os.environ.copy()
env['PATH'] = '/home/qian-qi/.cargo/bin:/usr/local/bin:/usr/bin:/bin'
env['CARGO_TARGET_DIR'] = str(ROOT / 'target')
env['CARGO_BUILD_JOBS'] = '2'
report = {'state': 'STARTED', 'parent': PARENT, 'source': str(SOURCE),
          'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'commands': [],
          'affinity': sorted(os.sched_getaffinity(0)), 'mem_available_before': mem_available,
          'disk_free_before': shutil.disk_usage(ROOT).free, 'android_full_builds_started': 0,
          'images_written': 0, 'deployments': 0, 'cell_actions': 0, 'production_ready': False}

def run(name, argv, expected=0, contains=None):
    start = time.monotonic()
    log = RESULT / (name + '.log')
    with log.open('xb') as output:
        completed = subprocess.run(argv, cwd=SOURCE, env=env, stdout=output, stderr=subprocess.STDOUT, check=False)
    item = {'name': name, 'argv': argv, 'returncode': completed.returncode,
            'expected_returncode': expected, 'elapsed_seconds': round(time.monotonic() - start, 3), 'log': ref(log)}
    report['commands'].append(item)
    print(json.dumps(item), flush=True)
    assert completed.returncode == expected, name + ' returned unexpected code'
    if contains is not None:
        assert contains in log.read_text(), name + ' expected diagnostic absent'

exit_code = 1
try:
    run('integrate', ['/usr/bin/python3', str(ROOT / 'control/integrate.py')])
    rust = SOURCE / 'tools/droidloom-update/src'
    run('format-new-modules', ['/home/qian-qi/.cargo/bin/rustfmt', '--edition', '2024', '--config', 'skip_children=true',
                             str(rust / 'audio_vendor_candidate.rs'), str(rust / 'audio_vendor_candidate/tests.rs'),
                             str(rust / 'audio_vendor_zip.rs')])
    run('targeted-normal-tests', [CARGO, 'test', '--locked', '--offline', '-j2', '-p', 'droidloom-update',
                                'audio_vendor', '--', '--test-threads=2'], contains='21 passed; 0 failed')
    run('normal-update-build', [CARGO, 'build', '--locked', '--offline', '-j2', '-p', 'droidloom-update'])
    executable = ROOT / 'target/debug/droidloom-update'
    run('actual-cli-help', [str(executable), 'audio-apex-stage-candidate', '--help'], contains='--terminal-sha256')
    assert ref(SOURCE_TERMINAL)['sha256'] == SOURCE_SHA
    destination = RESULT / 'rejected-source-only-candidate'
    run('actual-source58-terminal-is-not-full-build', [str(executable), 'audio-apex-stage-candidate',
        '--terminal', str(SOURCE_TERMINAL), '--terminal-sha256', SOURCE_SHA, '--destination', str(destination)],
        expected=1, contains='only the successful normal full-build terminal is accepted')
    assert not destination.exists()
    run('git-diff-check', ['/usr/bin/git', 'diff', '--check'])
    assert git(OLD_SOURCE, 'rev-parse', 'HEAD') == PARENT and git(OLD_SOURCE, 'status', '--porcelain') == ''
    assert git(SOURCE, 'rev-parse', 'HEAD') == PARENT
    report['source_files'] = {}
    for relative in ['Cargo.lock', 'tools/droidloom-update/Cargo.toml', 'tools/droidloom-update/README.md',
                     'tools/droidloom-update/src/main.rs', 'tools/droidloom-update/src/audio_vendor_candidate.rs',
                     'tools/droidloom-update/src/audio_vendor_candidate/tests.rs', 'tools/droidloom-update/src/audio_vendor_zip.rs']:
        report['source_files'][relative] = ref(SOURCE / relative)
    report['normal_tool'] = ref(executable)
    report['source_only_negative'] = {'terminal': ref(SOURCE_TERMINAL), 'output_absent': True}
    report['owner_source_modified'] = False
    report['state'] = 'RUST_VENDOR_CANDIDATE_21_CONTROLS_NORMAL_BUILD_AND_REAL_SOURCE_NEGATIVE_PASSED'
    exit_code = 0
except Exception as error:
    report['state'] = 'FAILED'
    report['error'] = repr(error)
finally:
    report['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    target = RESULT / 'RESULT.json'
    with target.open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps({'state': report['state'], 'result': ref(target)}), flush=True)
sys.exit(exit_code)
