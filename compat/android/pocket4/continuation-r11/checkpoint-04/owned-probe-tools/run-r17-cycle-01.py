from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys

RUNNER = Path('/home/alex/work/pocket4-owned-probe-run-r3-r11-01.py')
APK = Path('/home/alex/work/pocket4-owned-fd-capability-r17-apk-02/fd-owner-probe-r17-source/build-attempt-1/fdownerprobe.apk')
AUDIT = Path('/home/alex/work/pocket4-owned-fd-capability-r17-audit-01/receipt.json')
ROOT = Path('/home/alex/work/pocket4-owned-fd-capability-r17-android-01')
RUNNER_SHA = '69e7be92a77e4dc3def4f0602f398b4ea93b68f0b15fdc2a0dd26ec36036f73b'
APK_SHA = '74f54c5b3bb48f4c14a6ea788b7e6df5ba80c4b2944a79be37e99a919f8dab83'
AUDIT_SHA = '1d0bda0e60460ff6114d2e699767f9aa0d8a6386a87d4904b0ea1beab8776893'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(name, value):
    data = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + '\n').encode()
    with (ROOT / name).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


assert os.geteuid() == 0
assert sha(RUNNER) == RUNNER_SHA
assert sha(APK) == APK_SHA
assert sha(AUDIT) == AUDIT_SHA
audit = json.loads(AUDIT.read_text())
assert audit['qualified_for_owned_runtime_probe'] is True
assert audit['apk_sha256'] == APK_SHA
assert audit['artifact_hashes_unchanged'] is True
assert audit['worker_closure']['qualified_worker_closure'] is True
assert not ROOT.exists() and not ROOT.is_symlink()
os.umask(0o077)
ROOT.mkdir(mode=0o700)
save('coordinator-claim.json', {
    'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'apk_sha256': APK_SHA, 'runner_sha256': RUNNER_SHA,
    'actual_elf_audit_sha256': AUDIT_SHA, 'no_automatic_retry': True,
    'scope': 'Headless owned app UID only; fixed raw metadata primitive.'})
steps = []
errors = []


def phase(name, step, extra):
    argv = ['/usr/bin/python3', '-I', str(RUNNER), name, '--kind', 'owner',
            '--root', str(ROOT), '--step', step] + extra
    item = {'phase': name, 'argv': argv}
    try:
        process = subprocess.run(argv, capture_output=True, timeout=95)
        save(step + '-coordinator.stdout', process.stdout)
        save(step + '-coordinator.stderr', process.stderr)
        item['returncode'] = process.returncode
        result_path = ROOT / step / 'result.json'
        item['report'] = (json.loads(result_path.read_text()) if result_path.is_file()
                          else {'ok': False, 'missing_result': True, 'outcome_unknown': True})
    except Exception as error:
        item['error'] = repr(error)
        item['report'] = {'ok': False, 'outcome_unknown': True}
        errors.append({'phase': name, 'error': repr(error)})
        if isinstance(error, subprocess.TimeoutExpired):
            save(step + '-coordinator-timeout.stdout', error.stdout or b'')
            save(step + '-coordinator-timeout.stderr', error.stderr or b'')
    steps.append(item)
    report = item['report']
    print(json.dumps({'phase': name, 'returncode': item.get('returncode'),
                      'ok': report.get('ok'), 'outcome_unknown': report.get('outcome_unknown'),
                      'identity': report.get('installed_identity'),
                      'cleanup': report.get('only_exact_owned_package_removed'),
                      'error': item.get('error', report.get('error'))}), flush=True)
    return report.get('ok') is True


try:
    if phase('install', '01-install', ['--apk', str(APK), '--apk-sha256', APK_SHA]):
        phase('run', '02-run', ['--nonce', 'p4r11_raw_metadata_actual_r17_20261104_a1'])
finally:
    if (ROOT / 'install-verified.json').is_file():
        phase('remove', '03-remove', [])
    else:
        errors.append({'phase': 'remove', 'reason': 'No verified owned identity; no blind removal.'})
    removed = any(item['phase'] == 'remove' and
                  item['report'].get('only_exact_owned_package_removed') is True for item in steps)
    result = {'schema': 1, 'steps': steps, 'errors': errors,
              'owned_cycle_complete': len(steps) == 3 and removed,
              'exact_owned_package_removed': removed,
              'native_pass_not_implied_by_dispatch_success': True}
    save('coordinator-result.json', result)
    run = next((item['report'] for item in steps if item['phase'] == 'run'), {})
    print(json.dumps({'instrumentation_output': run.get('instrumentation_output'),
                      'owned_cycle_complete': result['owned_cycle_complete']}), flush=True)
sys.exit(0 if result['owned_cycle_complete'] else 1)
