#!/usr/bin/env python3
"""Capture actual host-only metadata controls and one exclusive materialization."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).parent


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def main():
    validation = ROOT / 'validation-r1'
    validation.mkdir(mode=0o700)
    before = {name: pin(ROOT / name) for name in ('adapt_cp3a.py', 'test_adapt_cp3a.py', 'README.md', 'run_validation.py')}
    commands = []; failed = False
    for name, argv in [
        ('controls', [sys.executable, '-B', '-m', 'unittest', '-v', 'test_adapt_cp3a']),
        ('materialize', [sys.executable, '-B', 'adapt_cp3a.py', 'materialize', '--out', 'successor-r1']),
    ]:
        if failed:
            break
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=30, check=False,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        write_new(validation / (name + '.stdout'), result.stdout)
        write_new(validation / (name + '.stderr'), result.stderr)
        commands.append({'name': name, 'argv': argv, 'returncode': result.returncode,
            'stdout': {'path': name + '.stdout', **pin(validation / (name + '.stdout'))},
            'stderr': {'path': name + '.stderr', **pin(validation / (name + '.stderr'))},
            'local_command_completed_and_waited': True})
        failed = result.returncode != 0
    after = {name: pin(ROOT / name) for name in before}
    outputs = {}
    if not failed:
        manifest = json.loads((ROOT / 'successor-r1/MANIFEST.json').read_bytes())
        for name, expected in manifest['outputs'].items():
            actual = pin(ROOT / 'successor-r1' / name)
            if actual != expected:
                failed = True
            outputs[name] = actual
        outputs['MANIFEST.json'] = pin(ROOT / 'successor-r1/MANIFEST.json')
    passed = not failed and before == after and len(commands) == 2
    if passed:
        stderr = (validation / 'controls.stderr').read_text()
        passed = '\nRan 9 tests in ' in stderr and stderr.rstrip().endswith('OK')
    result = {'schema': 'p4-cp3a-source-adapter-host-validation-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'state': 'PASS_HOST_SOURCE_METADATA_ONLY' if passed else 'FAIL_HOST_SOURCE_METADATA',
        'test_methods_passed': 9 if passed else None, 'commands': commands,
        'source_program_pins_before': before, 'source_program_pins_after': after,
        'program_bytes_unchanged': before == after, 'output_pins_reopened': outputs,
        'initial_development_run': 'Nine same test methods previously completed once; it is not counted as nine additional controls.',
        'original_runtime_modules_imported': False, 'Android_actions': 0, 'SDK_commands': 0,
        'APK_bodies_read': 0, 'user_data_reads': 0, 'installed': False,
        'runtime_qualified': False, 'business_qualified': False, 'production_ready': False,
        'execution_authorized': False}
    write_new(validation / 'RESULT.json', (json.dumps(result, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps({'state': result['state'], 'test_methods_passed': result['test_methods_passed'],
                      'result': str(validation / 'RESULT.json'), 'pin': pin(validation / 'RESULT.json')}, sort_keys=True))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
