from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib

ROOT = Path('/data/pocket4-audio-qpr1-vendor-candidate-20261109-2840-r1')
SOURCE = ROOT / 'source'
HARNESS = ROOT / 'harness'
RESULT = ROOT / 'ci-harness-validation-r3'
frozen = json.loads((ROOT / 'SOURCE_FROZEN-r2.json').read_text())
assert os.geteuid() == 1000
assert subprocess.check_output(['/usr/bin/git', '-C', str(SOURCE), 'rev-parse', 'HEAD']).decode().strip() == frozen['commit']
for relative, reference in frozen['source_files'].items():
    raw = (SOURCE / relative).read_bytes()
    assert len(raw) == reference['bytes'] and hashlib.sha256(raw).hexdigest() == reference['sha256']
assert shutil.disk_usage(ROOT).free >= 85 * 1024**3
assert int(next(v.split()[1] for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:'))) >= 12 * 1024**2
os.sched_setaffinity(0, {8, 9})
RESULT.mkdir(mode=0o700, exist_ok=False)
for name in ['audio_vendor_candidate.rs', 'audio_vendor_candidate/tests.rs', 'audio_vendor_zip.rs']:
    target = HARNESS / 'src' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as output:
        output.write((SOURCE / 'tools/droidloom-update/src' / name).read_bytes())
(HARNESS / 'src/lib.rs').write_text('''//! Linux controls for byte-identical updater sources; no Android qualification.
#![allow(dead_code)]
mod util {
    pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
}
mod audio_vendor_candidate;
mod audio_vendor_zip;
''')
env = os.environ.copy()
env['CARGO_TARGET_DIR'] = str(ROOT / 'target-ci-harness')
env['CARGO_BUILD_JOBS'] = '2'
env['PATH'] = '/home/qian-qi/.cargo/bin:/usr/bin:/bin'
report = {'state': 'STARTED', 'source_commit': frozen['commit'], 'commands': [],
          'source_freeze_sha256': hashlib.sha256((ROOT / 'SOURCE_FROZEN-r2.json').read_bytes()).hexdigest(),
          'full_apex_build': False, 'runtime_qualified': False, 'production_ready': False,
          'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

def ref(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def run(name, argv):
    path = RESULT / (name + '.log')
    with path.open('xb') as output:
        process = subprocess.run(argv, cwd=HARNESS, env=env, stdout=output, stderr=subprocess.STDOUT, check=False)
    record = {'name': name, 'argv': argv, 'returncode': process.returncode, 'log': ref(path)}
    report['commands'].append(record)
    print(json.dumps(record), flush=True)
    assert process.returncode == 0, name + ' failed'
    return path

exit_code = 1
try:
    report['harness_lock_origin'] = 'Exact registry dependency subgraph of producer Cargo.lock; normal locked Cargo test verifies resolution'
    report['prior_lock_refresh_failure'] = ref(ROOT / 'ci-harness-validation-r1/RESULT.json')
    report['prior_module_resolution_failure'] = ref(ROOT / 'ci-harness-validation-r2/RESULT.json')
    full = tomllib.loads((SOURCE / 'Cargo.lock').read_text())['package']
    small = tomllib.loads((HARNESS / 'Cargo.lock').read_text())['package']
    known = {(p['name'], p['version'], p.get('source')): p for p in full}
    packages = []
    for package in small:
        if 'source' in package:
            original = known[(package['name'], package['version'], package['source'])]
            assert package['checksum'] == original['checksum']
            packages.append({'name': package['name'], 'version': package['version'], 'checksum': package['checksum']})
    report['registry_packages_unchanged_from_producer_lock'] = packages
    log = run('exact-source-ci-controls', ['/home/qian-qi/.cargo/bin/cargo', 'test', '--locked', '--offline', '-j2', '--', '--test-threads=2'])
    assert '21 passed; 0 failed; 0 ignored' in log.read_text()
    report['harness_files'] = {str(p.relative_to(HARNESS)): ref(p) for p in [HARNESS / name for name in ['Cargo.toml', 'Cargo.lock', 'build.rs', 'src/lib.rs', 'src/audio_vendor_candidate.rs', 'src/audio_vendor_candidate/tests.rs', 'src/audio_vendor_zip.rs']]}
    report['source_files'] = {k: v for k, v in frozen['source_files'].items() if 'audio_vendor' in k}
    for relative, reference in frozen['source_files'].items():
        assert ref(SOURCE / relative) == reference
    assert not subprocess.check_output(['/usr/bin/git', '-C', str(SOURCE), 'status', '--porcelain']).strip()
    report['state'] = 'PORTABLE_LINUX_CI_HARNESS_PASSED_21_EXACT_SOURCE_CONTROLS'
    exit_code = 0
except Exception as error:
    report['state'] = 'FAILED'
    report['error'] = repr(error)
finally:
    report['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    path = RESULT / 'RESULT.json'
    with path.open('x') as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps({'state': report['state'], 'result': ref(path)}), flush=True)
sys.exit(exit_code)
