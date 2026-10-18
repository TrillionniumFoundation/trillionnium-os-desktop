#!/usr/bin/env python3
"""Execute the exact committed CI step once and retain raw source-bound evidence."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

BASE = Path('/workspace/scratch/98f315e377b2')
SOURCE = BASE / 'next-r6-ci-oracle'
OUT = BASE / 'next-tools/r6-shell-oracle-ci-01'
STEP_NAME = 'Test original Shell capture contracts with disposable Linux children'
INPUTS = [
    '.github/workflows/a10-host.yml',
    'tests/ui/test_original_hepta_shell.py',
    'tests/ui/probe-original-hepta-shell.py',
    'tests/integration/hepta/run_original_agentd.py',
    'tests/ui/x11-ime-client.py',
    'support/ui/ORIGINAL_HEPTA_SHELL.md',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=SOURCE)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        handle.write(data)


def save_json(path, value):
    write(path, (json.dumps(value, indent=2) + '\n').encode())


def identity():
    files = {}
    for relative in INPUTS:
        data = (SOURCE / relative).read_bytes()
        assert data == git('show', f'HEAD:{relative}')
        files[relative] = {'git_blob': git('rev-parse', f'HEAD:{relative}').decode().strip(),
                           'sha256': sha(data), 'bytes': len(data)}
    return {'head': git('rev-parse', 'HEAD').decode().strip(),
            'tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
            'status_porcelain': git('status', '--porcelain').decode(), 'files': files}


assert not OUT.exists(), 'use a fresh one-run evidence path'
OUT.mkdir()
before = identity()
assert before['status_porcelain'] == ''
save_json(OUT / 'source-before.json', before)
for relative in INPUTS:
    write(OUT / 'sources' / relative, (SOURCE / relative).read_bytes())
write(OUT / 'run-ci-contracts-source.py', Path(__file__).read_bytes())

lines = (SOURCE / INPUTS[0]).read_text().splitlines()
start = lines.index('      - name: ' + STEP_NAME)
assert lines[start + 1] == '        run: |'
body_lines = []
for line in lines[start + 2:]:
    if not line.startswith('          '):
        break
    body_lines.append(line[10:])
expected_lines = [
    'set -euo pipefail',
    'mkdir -p "$RUNNER_TEMP/a10"',
    'python3 -B -m unittest discover -s tests/ui ' + chr(92),
    '  -p \'test_original_hepta_shell.py\' -v 2>&1 | tee "$RUNNER_TEMP/a10/original-shell-contracts.log"',
]
assert body_lines == expected_lines, 'committed workflow invocation differs from preset command'
body = ('\n'.join(body_lines) + '\n').encode()
write(OUT / 'workflow-step.sh', body)
command = ['bash', '--noprofile', '--norc', str(OUT / 'workflow-step.sh')]
env = os.environ.copy()
env['RUNNER_TEMP'] = str(OUT / 'runner-temp')
plan = {'cwd': str(SOURCE), 'command': command,
        'test_argv': ['python3', '-B', '-m', 'unittest', 'discover', '-s', 'tests/ui', '-p', 'test_original_hepta_shell.py', '-v'],
        'workflow_run_block_matches_preset': True, 'workflow_run_block_sha256': sha(body),
        'environment_override': {'RUNNER_TEMP': env['RUNNER_TEMP']}, 'timeout_seconds': 30,
        'started_unix_ms': int(time.time() * 1000), 'source_commit': before['head']}
save_json(OUT / 'execution-plan.json', plan)
result = subprocess.run(command, cwd=SOURCE, env=env, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=30, check=False)
write(OUT / 'stdout-stderr.log', result.stdout)
after = identity()
save_json(OUT / 'source-after.json', after)
tee_log = OUT / 'runner-temp/a10/original-shell-contracts.log'
assert tee_log.read_bytes() == result.stdout
text = result.stdout.decode()
passed_lines = [line for line in text.splitlines() if line.startswith('test_') and line.endswith(' ... ok')]
passed = result.returncode == 0 and before == after and len(passed_lines) == 8 and 'Ran 8 tests in ' in text and '\nOK\n' in text
receipt = {**plan, 'status': 'passed' if passed else 'failed', 'exit_code': result.returncode,
           'finished_unix_ms': int(time.time() * 1000), 'source_identity_unchanged': before == after,
           'passed_test_count': len(passed_lines), 'failed_test_count': 0 if passed else None,
           'tee_log': {'file': str(tee_log.relative_to(OUT)), 'bytes': tee_log.stat().st_size,
                       'sha256': sha(tee_log.read_bytes())},
           'tee_log_equals_raw_process_output': True,
           'qualification': 'Exact local execution of the newly committed A10 Python contract-test step; synthetic contract inputs plus actual disposable-child parent-death check. Not a GitHub run, original Agentd run, Rust rebuild, or actual window capture.'}
save_json(OUT / 'receipt.json', receipt)
files = sorted(p for p in OUT.rglob('*') if p.is_file())
write(OUT / 'SHA256SUMS', ''.join(f'{sha(p.read_bytes())}  {p.relative_to(OUT)}\n' for p in files).encode())
print(json.dumps({'status': receipt['status'], 'source': before['head'], 'tree': before['tree'],
                  'tests': len(passed_lines), 'exit_code': result.returncode,
                  'receipt_sha256': sha((OUT / 'receipt.json').read_bytes()),
                  'raw_log_sha256': receipt['tee_log']['sha256'], 'evidence': str(OUT)}, indent=2))
raise SystemExit(0 if passed else 1)
