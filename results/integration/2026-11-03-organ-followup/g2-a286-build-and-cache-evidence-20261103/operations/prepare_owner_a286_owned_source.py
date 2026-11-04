"""Copy the verified owned fe55 source and admit its exact canonical successor."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
BASE = Path('/data/trill-organ-20261103-f1-build')
OLD = Path('/home/qian-qi/work/trill-organ-20261103-f1/desktop-owner-fe55-owned-source')
NEW = Path('/home/qian-qi/work/trill-organ-20261103-f1/desktop-owner-a286-owned-source')
OUT = BASE / 'owner-a286-source-preparation-v1'
BUNDLE = BASE / 'desktop-owner-a286-from-fe55.bundle'
HEAD = 'a286e0f922bf8e439e8951ae1538abeac0b26477'
TREE = '342ad0840d521e97d6de5845682cbc11a115f6f7'
PARENT = 'fe55fe8e1764f4967bae295311d288d8049b6eae'
PARENT_TREE = '07cbb5e0187b4355200c2f5e0166228cecf1ecc1'
UPSTREAM_TREE = '96605cf64aeae2d34f29b97e85eff9315fe10a8e'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_LAZY_FETCH': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bundle-sha256', required=True)
args = parser.parse_args()
OUT.mkdir(mode=0o700)
record = {'schema': 'hepta.canonical-owned-source-successor.v1', 'passed': False,
          'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'source_root': str(NEW), 'source_head': HEAD, 'source_tree': TREE,
          'canonical_parent': PARENT, 'fixed_upstream_tree': UPSTREAM_TREE,
          'complete_git_history_claimed': False, 'commands': [],
          'independent_object_store_verified': False, 'kernel_built': False,
          'locked_204_graph_verified': False, 'native_execution_verified': False, 'g2_complete': False}


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def run(argv, label, cwd=BASE, timeout=300):
    result = subprocess.run(argv, cwd=cwd, env=ENV, capture_output=True, timeout=timeout, check=False)
    (OUT / (label + '.stdout')).write_bytes(result.stdout)
    (OUT / (label + '.stderr')).write_bytes(result.stderr)
    record['commands'].append({'argv': argv, 'cwd': str(cwd), 'exit_code': result.returncode, 'label': label})
    if result.returncode:
        raise ValueError(label + ' failed: ' + result.stderr.decode(errors='replace')[-4096:])
    return result.stdout


try:
    if NEW.exists() or NEW.is_symlink():
        raise ValueError('new owned canonical source required')
    if OLD.is_symlink() or OLD.resolve(strict=True) != OLD or OLD.stat().st_uid != os.geteuid():
        raise ValueError('existing task-owned source identity differs')
    if BUNDLE.is_symlink() or not BUNDLE.is_file() or sha(BUNDLE) != args.bundle_sha256:
        raise ValueError('exact canonical successor bundle differs')
    record['bundle'] = {'bytes': BUNDLE.stat().st_size, 'sha256': args.bundle_sha256}
    old_identity = run(['/usr/bin/git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], 'old-identity', OLD)
    if old_identity.decode().splitlines() != [PARENT, PARENT_TREE] or run(['/usr/bin/git', 'status', '--porcelain=v1', '--untracked-files=all'], 'old-clean', OLD):
        raise ValueError('verified parent source identity or clean state differs')
    if (OLD / '.git/objects/info/alternates').exists():
        raise ValueError('parent source must already own its objects')
    run(['/usr/bin/git', 'clone', '--no-hardlinks', '--no-checkout', str(OLD), str(NEW)], 'clone-owned-source')
    run(['/usr/bin/git', 'bundle', 'verify', str(BUNDLE)], 'verify-canonical-bundle', NEW)
    run(['/usr/bin/git', 'fetch', '--no-tags', str(BUNDLE),
         'refs/heads/codex/g2-owner-canonical-export-a286:refs/heads/canonical-a286'], 'fetch-canonical-successor', NEW)
    run(['/usr/bin/git', 'update-ref', 'refs/task-inputs/asterinas-fixed-tree', UPSTREAM_TREE, ''], 'pin-upstream-tree', NEW)
    run(['/usr/bin/git', 'checkout', '--detach', HEAD], 'checkout-canonical-successor', NEW)
    if run(['/usr/bin/git', 'rev-parse', 'HEAD', 'HEAD^{tree}', 'HEAD^'], 'identity', NEW).decode().splitlines() != [HEAD, TREE, PARENT]:
        raise ValueError('canonical successor identity differs')
    alternates = NEW / '.git/objects/info/alternates'
    counts = run(['/usr/bin/git', 'count-objects', '-v'], 'object-counts', NEW).decode()
    if alternates.exists() or alternates.is_symlink() or any(line.startswith('alternate:') for line in counts.splitlines()):
        raise ValueError('source still borrows another object store')
    if any(path.is_symlink() or path.stat().st_nlink != 1 for path in (NEW / '.git/objects/pack').iterdir()):
        raise ValueError('source pack is aliased rather than privately owned')
    boundary = (NEW / '.git/shallow').read_bytes()
    depth = int(run(['/usr/bin/git', 'rev-list', '--count', 'HEAD'], 'retained-depth', NEW))
    if boundary != (PARENT + '\n').encode() or depth != 2:
        raise ValueError('explicit two-commit snapshot boundary differs')
    run(['/usr/bin/git', 'fsck', '--full', '--no-dangling'], 'complete-owned-objects', NEW, timeout=600)
    spec = importlib.util.spec_from_file_location('canonical_original_builder', NEW / 'tests/workloads/hepta_cpu_control/build_original_entry.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    snapshot = builder.source_snapshot(NEW, HEAD, TREE)
    data = (json.dumps(snapshot, indent=2, sort_keys=True) + '\n').encode()
    (OUT / 'tracked-source-snapshot.json').write_bytes(data)
    gate = run(['/usr/bin/python3', '-I', '-B', str(NEW / 'support/build/verify-source.py')], 'source-gate', NEW)
    if run(['/usr/bin/git', 'status', '--porcelain=v1', '--untracked-files=all'], 'final-clean', NEW):
        raise ValueError('verification changed canonical source')
    if run(['/usr/bin/git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], 'old-final-identity', OLD) != old_identity or run(['/usr/bin/git', 'status', '--porcelain=v1', '--untracked-files=all'], 'old-final-clean', OLD):
        raise ValueError('parent source identity or clean state changed')
    record.update(passed=True, source_gate=json.loads(gate), snapshot_depth=depth, shallow_boundary=PARENT,
                  remaining_alternates=[], independent_object_store_verified=True,
                  tracked_files_verified=len(snapshot['files']), tracked_bytes_verified=sum(item['bytes'] for item in snapshot['files']),
                  tracked_source_snapshot_bytes=len(data), tracked_source_snapshot_sha256=hashlib.sha256(data).hexdigest(),
                  parent_source_identity_and_clean_state_unchanged=True)
except Exception as error:
    record.update(passed=False, error=type(error).__name__ + ': ' + str(error))
finally:
    record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: record[key] for key in ('passed', 'source_head', 'snapshot_depth', 'independent_object_store_verified',
                  'tracked_files_verified', 'tracked_bytes_verified', 'error') if key in record}))
raise SystemExit(0 if record['passed'] else 1)
