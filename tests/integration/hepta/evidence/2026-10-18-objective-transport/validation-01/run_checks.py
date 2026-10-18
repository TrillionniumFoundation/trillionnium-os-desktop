#!/usr/bin/env python3
"""Bounded local verification of one frozen R7 source. Never starts Agentd."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path('/workspace/scratch/98f315e377b2')
SOURCE = ROOT / 'next-r7-hepta'
EXPECTED = '19c2185d27c1d788354e14af27999406bc927c4f'
WORK = Path(__file__).resolve().parent
BIN = ROOT / 'next-tools/rust188/rustup/toolchains/1.88.0-x86_64-unknown-linux-gnu/bin'
REFERENCE = WORK / 'wire-reference'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=SOURCE, text=True).strip()

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def source_identity():
    names = git('ls-files', '--', 'services/hepta-os',
                'tests/integration/hepta/check_objective_wire.py',
                'tests/integration/hepta/check_upstream_contract.py',
                'tests/integration/hepta/README.md').splitlines()
    return {'head': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'),
            'status': git('status', '--porcelain'),
            'files': {name: digest(SOURCE / name) for name in names}}

def main():
    receipt_path = WORK / 'receipt.json'
    if receipt_path.exists():
        raise RuntimeError('refuse to overwrite a validation result')
    before = source_identity()
    if before['head'] != EXPECTED or before['status']:
        raise RuntimeError('frozen source mismatch or dirty source')
    env = os.environ.copy()
    env.update(PATH=str(BIN) + os.pathsep + env['PATH'],
               CARGO_HOME=str(ROOT / 'next-tools/rust188/cargo'),
               RUSTUP_HOME=str(ROOT / 'next-tools/rust188/rustup'),
               CARGO_TARGET_DIR=str(ROOT / 'next-tools/r7-objective-target'),
               PYTHONDONTWRITEBYTECODE='1')
    manifest = str(SOURCE / 'services/hepta-os/Cargo.toml')
    cargo = str(BIN / 'cargo')
    record = {'status': 'running', 'started_at': now(), 'source_before': before,
              'helper_sha256': digest(__file__), 'steps': [],
              'qualification': 'local feature/observer regression, disposable UDS fixtures and original wire declarations only',
              'original_agentd_started': False, 'signature_created': False,
              'original_objective_submitted': False, 'device_effect': False}
    record['toolchain'] = {
        name: {'path': str(BIN / name), 'sha256': digest(BIN / name),
               'version': subprocess.check_output([str(BIN / name), '-V'], env=env, text=True).strip()}
        for name in ['cargo', 'rustc', 'rustfmt', 'clippy-driver']}
    installed = ROOT / 'next-tools/rust188/installed-receipt.json'
    if installed.exists():
        record['toolchain_installation'] = {'path': str(installed), 'sha256': digest(installed)}
    receipt_path.write_text(json.dumps(record, indent=2) + '\n')
    commands = [
        ('feature-off-check', [cargo, 'check', '--manifest-path', manifest, '--locked', '--offline',
                               '--no-default-features', '--all-targets', '-j', '2']),
        ('feature-on-tests', [cargo, 'test', '--manifest-path', manifest, '--locked', '--offline',
                              '--features', 'objective-transport', '-j', '2']),
        ('strict-clippy', [cargo, 'clippy', '--manifest-path', manifest, '--locked', '--offline',
                           '--features', 'objective-transport', '--all-targets', '-j', '2', '--', '-D', 'warnings']),
        ('format-check', [cargo, 'fmt', '--manifest-path', manifest, '--check']),
        ('original-declaration-extract', ['python3', str(SOURCE / 'tests/integration/hepta/check_objective_wire.py'),
                                        '--source-files', str(ROOT / 'next-tools/r7-objective-upstream-files'),
                                        '--emit-reference', str(REFERENCE)]),
        ('original-declaration-wire-run', [cargo, 'run', '--manifest-path', str(REFERENCE / 'Cargo.toml'),
                                           '--locked', '--offline', '-j', '2']),
    ]
    failed = False
    for name, command in commands:
        if source_identity() != before:
            raise RuntimeError('source changed before command')
        step = {'name': name, 'command': command, 'started_at': now(), 'timeout_seconds': 120,
                'log': str(WORK / (name + '.log'))}
        began = time.monotonic()
        with (WORK / (name + '.log')).open('xb') as log:
            proc = subprocess.Popen(command, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            step['owned_process_id'] = proc.pid
            try:
                code = proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                step['deadline_reached'] = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    code = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    code = proc.wait()
        step.update(exit_code=code, elapsed_seconds=round(time.monotonic() - began, 3), completed_at=now(),
                    log_sha256=digest(WORK / (name + '.log')))
        record['steps'].append(step)
        receipt_path.write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps({'step': name, 'exit_code': code, 'elapsed_seconds': step['elapsed_seconds']}), flush=True)
        if code != 0 or step.get('deadline_reached'):
            failed = True
            break
    after = source_identity()
    record.update(source_after=after, completed_at=now(), helper_sha256_after=digest(__file__))
    if after != before or record['helper_sha256_after'] != record['helper_sha256']:
        failed = True
        record['binding_failure'] = True
    if (REFERENCE / 'SOURCE_BINDING.json').exists():
        record['reference_source_binding'] = {'path': str(REFERENCE / 'SOURCE_BINDING.json'),
                                              'sha256': digest(REFERENCE / 'SOURCE_BINDING.json')}
        original_lock = json.loads((REFERENCE / 'SOURCE_BINDING.json').read_text())['emitted_lock_sha256']
        record['reference_lock_after_sha256'] = digest(REFERENCE / 'Cargo.lock')
        if original_lock != record['reference_lock_after_sha256']:
            failed = True
            record['reference_lock_changed'] = True
    record['status'] = 'failed' if failed else 'passed'
    receipt_path.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'receipt': str(receipt_path)}), flush=True)
    raise SystemExit(1 if failed else 0)

if __name__ == '__main__':
    main()
