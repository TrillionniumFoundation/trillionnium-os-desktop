"""Verify an owned depth-one snapshot and all canonical source bytes."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
BASE = Path('/data/trill-organ-20261103-f1-build')
SOURCE = Path('/home/qian-qi/work/trill-organ-20261103-f1/desktop-owner-fe55-owned-source')
PLAN = BASE / 'owner-fe55-owned-snapshot-plan-v1'
OUT = BASE / 'owner-fe55-owned-snapshot-verification-v1'
HEAD = 'fe55fe8e1764f4967bae295311d288d8049b6eae'
TREE = '07cbb5e0187b4355200c2f5e0166228cecf1ecc1'
UPSTREAM_TREE = '96605cf64aeae2d34f29b97e85eff9315fe10a8e'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'HOME': '/home/qian-qi', 'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_LAZY_FETCH': '1',
       'PYTHONDONTWRITEBYTECODE': '1'}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expected-plan-sha256', required=True)
parser.add_argument('--pack-job', required=True)
parser.add_argument('--pack-id', required=True)
args = parser.parse_args()
OUT.mkdir(mode=0o700)
record = {'schema': 'hepta.canonical-owned-source-snapshot-verification.v1', 'passed': False,
          'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'source_root': str(SOURCE), 'source_head': HEAD, 'source_tree': TREE,
          'snapshot_depth': 1, 'complete_git_history_claimed': False,
          'pack_job': args.pack_job, 'pack_id': args.pack_id, 'commands': [],
          'independent_object_store_verified': False, 'kernel_built': False,
          'locked_204_graph_verified': False, 'native_execution_verified': False, 'g2_complete': False}


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def run(argv, label, data=None, timeout=180):
    result = subprocess.run(argv, input=data, cwd=SOURCE, env=ENV, capture_output=True,
                            timeout=timeout, check=False)
    (OUT / (label + '.stdout')).write_bytes(result.stdout)
    (OUT / (label + '.stderr')).write_bytes(result.stderr)
    record['commands'].append({'argv': argv, 'exit_code': result.returncode, 'label': label})
    if result.returncode:
        raise ValueError(label + ' failed: ' + result.stderr.decode(errors='replace')[-4096:])
    return result.stdout


try:
    if sha(PLAN / 'result.json') != args.expected_plan_sha256:
        raise ValueError('source snapshot plan record differs')
    plan = json.loads((PLAN / 'result.json').read_bytes())
    if (plan.get('passed') is not True or plan.get('source_head') != HEAD or plan.get('source_tree') != TREE
            or plan.get('source_root') != str(SOURCE) or plan.get('fixed_upstream_tree') != UPSTREAM_TREE
            or plan.get('snapshot_depth') != 1 or plan.get('complete_git_history_claimed') is not False):
        raise ValueError('exact depth-one source snapshot plan required')
    if SOURCE.is_symlink() or SOURCE.resolve(strict=True) != SOURCE or SOURCE.stat().st_uid != os.geteuid():
        raise ValueError('owned source directory identity differs')
    if any(path.name != '.git' for path in SOURCE.iterdir()):
        raise ValueError('owned source worktree must still be empty')
    alternates = SOURCE / '.git/objects/info/alternates'
    if alternates.exists() or alternates.is_symlink() or (SOURCE / '.git/shallow').read_bytes() != (HEAD + '\n').encode():
        raise ValueError('snapshot depth or nonborrowed source metadata differs')
    if not re.fullmatch('[0-9a-f]{40}', args.pack_id):
        raise ValueError('actual Git pack identity required')
    pack = SOURCE / ('.git/objects/pack/pack-' + args.pack_id + '.pack')
    index = pack.with_suffix('.idx')
    if any(path.is_symlink() or not path.is_file() for path in (pack, index)):
        raise ValueError('actual owned source pack or index missing')
    run(['/usr/bin/git', 'verify-pack', str(index)], 'owned-pack-verification', timeout=600)
    record['own_pack'] = {'name': pack.name, 'bytes': pack.stat().st_size, 'sha256': sha(pack),
                          'index_bytes': index.stat().st_size, 'index_sha256': sha(index)}
    inventory_path = PLAN / 'object-inventory.json'
    listing_path = PLAN / 'object-list.txt'
    if sha(inventory_path) != plan['object_inventory_sha256'] or sha(listing_path) != plan['object_list_sha256']:
        raise ValueError('original complete source object inventory changed')
    inventory = json.loads(inventory_path.read_bytes())
    checked = run(['/usr/bin/git', 'cat-file', '--batch-check'], 'owned-source-object-closure', listing_path.read_bytes()).decode().splitlines()
    expected = [item['sha1'] + ' ' + item['type'] + ' ' + str(item['bytes']) for item in inventory]
    if checked != expected:
        raise ValueError('source object is missing or differs from its complete fixed inventory')
    commit = run(['/usr/bin/git', 'cat-file', 'commit', HEAD], 'owned-canonical-commit')
    if hashlib.sha256(commit).hexdigest() != plan['canonical_commit_sha256']:
        raise ValueError('original canonical commit bytes changed')
    run(['/usr/bin/git', 'update-ref', 'refs/heads/canonical-fe55', HEAD, ''], 'pin-canonical-head')
    run(['/usr/bin/git', 'update-ref', 'refs/task-inputs/asterinas-fixed-tree', UPSTREAM_TREE, ''], 'pin-fixed-upstream-tree')
    run(['/usr/bin/git', 'fsck', '--connectivity-only', '--no-dangling'], 'owned-object-connectivity', timeout=600)
    run(['/usr/bin/git', 'checkout', '--detach', HEAD], 'checkout-canonical-source')
    if run(['/usr/bin/git', 'status', '--porcelain=v1', '--untracked-files=all'], 'clean'):
        raise ValueError('owned canonical checkout is not clean')
    spec = importlib.util.spec_from_file_location('canonical_original_builder', SOURCE / 'tests/workloads/hepta_cpu_control/build_original_entry.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    snapshot = builder.source_snapshot(SOURCE, HEAD, TREE)
    data = (json.dumps(snapshot, indent=2, sort_keys=True) + '\n').encode()
    (OUT / 'tracked-source-snapshot.json').write_bytes(data)
    gate = run(['/usr/bin/python3', '-I', '-B', str(SOURCE / 'support/build/verify-source.py')], 'source-gate')
    record['source_gate'] = json.loads(gate)
    counted = run(['/usr/bin/git', 'count-objects', '-v'], 'owned-object-counts').decode()
    if alternates.exists() or alternates.is_symlink() or any(line.startswith('alternate:') for line in counted.splitlines()):
        raise ValueError('owned source still borrows another Git object store')
    if run(['/usr/bin/git', 'rev-parse', '--is-shallow-repository'], 'declared-depth').decode().strip() != 'true':
        raise ValueError('source snapshot depth was not declared')
    if run(['/usr/bin/git', 'status', '--porcelain=v1', '--untracked-files=all'], 'final-clean'):
        raise ValueError('verification changed canonical source')
    files = snapshot['files']
    record.update(source_objects_verified=len(inventory), tracked_files_verified=len(files),
                  tracked_bytes_verified=sum(item['bytes'] for item in files),
                  tracked_source_snapshot_bytes=len(data), tracked_source_snapshot_sha256=hashlib.sha256(data).hexdigest(),
                  remaining_alternates=[], independent_object_store_verified=True)
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    record['host_mem_available_bytes'] = int(memory['MemAvailable'].split()[0]) * 1024
    fs = os.statvfs(BASE)
    record['host_disk_available_bytes'] = fs.f_bavail * fs.f_frsize
    record['passed'] = True
except Exception as error:
    record.update(passed=False, error=type(error).__name__ + ': ' + str(error))
finally:
    record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: record[key] for key in ('passed', 'independent_object_store_verified', 'source_objects_verified',
                  'tracked_files_verified', 'tracked_bytes_verified', 'host_mem_available_bytes', 'host_disk_available_bytes', 'error') if key in record}))
raise SystemExit(0 if record['passed'] else 1)
