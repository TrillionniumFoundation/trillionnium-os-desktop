#!/usr/bin/env python3
"""Capture only the explicitly requested local Desktop Python gates."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/workspace/scratch/159b66073956/repos/desktop-product')
OUTPUT = Path(__file__).resolve().parent
EXPECTED_HEAD = '0a268d8928d76682a59c8cc0be88428845f40ce3'
EXPECTED_TREE = 'd7c0d61a1519db8f4b0a7178b9f6867f85719b48'
LOCKS = ('ui/Cargo.lock', 'services/hepta-session-host/Cargo.lock')
GATES = {
    'spec-normal': (['-B', '-m', 'unittest', 'discover', '-s', 'tests/spec', '-p', 'test_*.py', '-v'], 53),
    'spec-optimized': (['-B', '-O', '-m', 'unittest', 'discover', '-s', 'tests/spec', '-p', 'test_*.py', '-v'], 53),
    'product-source-normal': (['-B', 'tests/ui/test_product_source.py', '-v'], 10),
    'product-source-optimized': (['-B', '-O', 'tests/ui/test_product_source.py', '-v'], 10),
    'product-source-verify': (['-B', 'tests/ui/verify_product_source.py'], None),
    'android-device-organ': (['-B', '-m', 'unittest', 'discover', '-s', 'tests/workloads/android', '-p', 'test_device_organ.py', '-v'], 24),
    'product-tools': (['-B', '-m', 'unittest', 'discover', '-s', 'support/ui/product', '-p', 'test_*.py', '-v'], 65),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def source_state():
    untracked = subprocess.check_output(
        ['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT
    ).decode().split('\0')
    return {
        'head': git('rev-parse', 'HEAD'),
        'tree': git('rev-parse', 'HEAD^{tree}'),
        'tracked_clean': not git('status', '--porcelain', '--untracked-files=no'),
        'status_porcelain': git('status', '--porcelain'),
        'preexisting_untracked_files': [
            {'path': name, 'bytes': (ROOT / name).stat().st_size, 'sha256': sha256(ROOT / name)}
            for name in untracked if name
        ],
        'locks': {name: sha256(ROOT / name) for name in LOCKS},
    }


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def unittest_counts(output):
    found = re.search(r'^Ran (\d+) tests? in ([0-9.]+)s$', output, re.MULTILINE)
    if not found:
        return None
    last = re.findall(r'^(?:OK|FAILED)(?: \(([^\n]*)\))?$', output, re.MULTILINE)
    summary = last[-1] if last else ''
    values = {key: int(value) for key, value in re.findall(r'([a-z ]+)=(\d+)', summary)}
    total = int(found[1])
    failures, errors = values.get('failures', 0), values.get('errors', 0)
    skipped = values.get('skipped', 0)
    expected_failures = values.get('expected failures', 0)
    unexpected_successes = values.get('unexpected successes', 0)
    return {
        'tests_run': total,
        'passed': total - failures - errors - skipped - expected_failures - unexpected_successes,
        'failures': failures,
        'errors': errors,
        'skipped': skipped,
        'expected_failures': expected_failures,
        'unexpected_successes': unexpected_successes,
        'unittest_reported_seconds': float(found[2]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gate', choices=GATES)
    parser.add_argument('--attempt', default='sandbox')
    parser.add_argument('--execution-mode', choices=('workspace-sandbox', 'authorized-local-escalated'),
                        default='workspace-sandbox')
    args = parser.parse_args()
    name = f'{args.gate}-{args.attempt}'
    log_path = OUTPUT / f'{name}.log'
    receipt_path = OUTPUT / f'{name}.json'
    if log_path.exists() or receipt_path.exists():
        raise SystemExit(f'refusing to replace evidence: {name}')
    before = source_state()
    if before['head'] != EXPECTED_HEAD or before['tree'] != EXPECTED_TREE or not before['tracked_clean']:
        raise SystemExit('frozen Desktop source identity/clean tracked state does not match')
    options, expected_count = GATES[args.gate]
    argv = [sys.executable, *options]
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    started_at, started = timestamp(), time.monotonic()
    with log_path.open('xb') as log:
        result = subprocess.run(argv, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    ended_at = timestamp()
    after = source_state()
    raw_output = log_path.read_text(errors='replace')
    counts = unittest_counts(raw_output)
    verification = None
    if args.gate == 'product-source-verify' and result.returncode == 0:
        verification = json.loads(raw_output)
    stable = before == after
    scope_ok = ((counts is not None and counts['tests_run'] == expected_count)
                if expected_count is not None else isinstance(verification, dict) and verification.get('status') == 'passed')
    passed = result.returncode == 0 and stable and scope_ok
    record = {
        'schema': 'trillionnium.final-python-gate.v1',
        'gate': args.gate, 'attempt': args.attempt, 'execution_mode': args.execution_mode,
        'cwd': str(ROOT), 'argv': argv, 'environment': {'PYTHONDONTWRITEBYTECODE': '1'},
        'python_version': sys.version, 'uid': os.getuid(), 'euid': os.geteuid(),
        'head': before['head'], 'tree': before['tree'],
        'started_at': started_at, 'ended_at': ended_at, 'elapsed_seconds': round(time.monotonic() - started, 6),
        'status': ('passed' if counts is None or counts['skipped'] == 0 else 'passed-with-skips') if passed else 'failed',
        'exit_code': result.returncode, 'expected_unittest_count': expected_count,
        'unittest': counts, 'source_verification': verification,
        'source_before': before, 'source_after': after,
        'source_and_existing_untracked_unchanged': stable,
        'log': str(log_path), 'log_bytes': log_path.stat().st_size,
        'log_sha256': sha256(log_path), 'capture': 'stdout and stderr merged without rewriting',
        'runtime_or_device_actions': False,
    }
    receipt_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: record[k] for k in ('gate', 'attempt', 'status', 'exit_code', 'unittest', 'source_and_existing_untracked_unchanged', 'log')}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
