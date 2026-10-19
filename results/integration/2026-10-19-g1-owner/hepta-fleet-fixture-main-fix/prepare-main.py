#!/usr/bin/env python3
"""Prepare an independent fixed-main checkout and record actual setup commands."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/workspace/scratch/499c7902de8e')
SOURCE = ROOT / 'r10-fleet-fixture-main-fix'
OLD_SOURCE = ROOT / 'r10-fleet-fixture-fix'
OUT = ROOT / 'r10-evidence/fleet-fixture-main-fix'
OLD_OUT = ROOT / 'r10-evidence/fleet-fixture-fix'
BASE = 'f8c9419df6ddeb36ff8b522a50219981fb8d9345'
PICK = '3749e151fd1a39c4b568afdb9e03028974ad86be'
PATH = 'codex-rs/hepta-fleet/src/authority_port.rs'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(name, cwd, argv):
    log = OUT / (name + '.log')
    started = now()
    with log.open('xb') as handle:
        p = subprocess.run(argv, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT)
    data = log.read_bytes()
    receipt = {'argv': argv, 'cwd': str(cwd), 'started_at': started,
               'completed_at': now(), 'exit_code': p.returncode,
               'log': {'path': log.name, 'bytes': len(data), 'sha256': sha(data)}}
    (OUT / (name + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)
    if p.returncode:
        raise SystemExit(p.returncode)
    return data


assert not SOURCE.exists()
old_manifest = (OLD_OUT / 'files-manifest.json').read_bytes()
assert sha(old_manifest) == 'c42b3bc1774bd150d15ea563ce8fc088dd47c23cf0b1919350d912fa495c4232'
records = json.loads(old_manifest)['files']
assert len(records) == 19
for record in records:
    data = (OLD_OUT / record['path']).read_bytes()
    assert len(data) == record['bytes'] and sha(data) == record['sha256']
run('checkout-02', OLD_SOURCE, ['git', 'worktree', 'add', str(SOURCE),
                              'fix/fleet-fixture-admission-assert-main'])
actual_base = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']).decode().strip()
assert actual_base == BASE
blob = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', f'HEAD:{PATH}']).decode().strip()
assert blob == '55e117dafe84709451a638bb8f6bafa41c38bd5a'
run('cherry-pick', SOURCE, ['git', 'cherry-pick', PICK])
identity = subprocess.check_output(['git', '-C', str(SOURCE), 'show', '-s', '--format=%H%n%T%n%P', 'HEAD']).decode().splitlines()
assert identity[2] == BASE
changed = subprocess.check_output(['git', '-C', str(SOURCE), 'diff', '--name-only', BASE, 'HEAD']).decode().splitlines()
assert changed == [PATH]
assert subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain=v1', '--untracked-files=all']) == b''
result = {'schema': 1, 'recorded_at': now(), 'base': BASE,
          'base_tree': '15c9d6ea07bf3832de82825a6cc1e8c958dd3d45',
          'base_file_blob': blob, 'cherry_picked_commit': PICK,
          'commit': identity[0], 'tree': identity[1], 'parent': identity[2],
          'changed_paths': changed, 'original_evidence_files_verified': 20,
          'original_evidence_manifest_sha256': sha(old_manifest)}
(OUT / 'setup.json').write_text(json.dumps(result, indent=2) + '\n')
runner = (OLD_OUT / 'run-command.py').read_text()
runner = runner.replace("SOURCE = BASE / 'r10-fleet-fixture-fix'", "SOURCE = BASE / 'r10-fleet-fixture-main-fix'")
runner = runner.replace("EVIDENCE = BASE / 'r10-evidence/fleet-fixture-fix'", "EVIDENCE = BASE / 'r10-evidence/fleet-fixture-main-fix'")
(OUT / 'run-command.py').write_text(runner)
print(json.dumps(result, indent=2))
