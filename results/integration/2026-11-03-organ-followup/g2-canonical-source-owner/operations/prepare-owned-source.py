"""Plan an explicit depth-one source snapshot with two complete owned trees."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess

BASE = Path('/data/trill-organ-20261103-f1-build')
INPUT = Path('/home/qian-qi/work/trill-organ-20261103-f1/desktop-owner-image-fe55fe8e')
SOURCE = Path('/home/qian-qi/work/trill-organ-20261103-f1/desktop-owner-fe55-owned-source')
OUT = BASE / 'owner-fe55-owned-snapshot-plan-v1'
HEAD = 'fe55fe8e1764f4967bae295311d288d8049b6eae'
TREE = '07cbb5e0187b4355200c2f5e0166228cecf1ecc1'
UPSTREAM_TREE = '96605cf64aeae2d34f29b97e85eff9315fe10a8e'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'HOME': '/home/qian-qi', 'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_LAZY_FETCH': '1'}
OUT.mkdir(mode=0o700)
record = {'schema': 'hepta.canonical-owned-source-snapshot-plan.v1', 'passed': False,
          'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'input_repository': str(INPUT), 'source_root': str(SOURCE), 'source_head': HEAD, 'source_tree': TREE,
          'fixed_upstream_tree': UPSTREAM_TREE, 'snapshot_depth': 1, 'complete_git_history_claimed': False,
          'commands': [], 'independent_object_store_verified': False,
          'kernel_built': False, 'locked_204_graph_verified': False, 'native_execution_verified': False, 'g2_complete': False}


def run(argv, label, data=None, cwd=INPUT):
    result = subprocess.run(argv, input=data, cwd=cwd, env=ENV, capture_output=True, timeout=180, check=False)
    (OUT / (label + '.stdout')).write_bytes(result.stdout)
    (OUT / (label + '.stderr')).write_bytes(result.stderr)
    record['commands'].append({'argv': argv, 'cwd': str(cwd), 'exit_code': result.returncode, 'label': label})
    if result.returncode:
        raise ValueError(label + ' failed: ' + result.stderr.decode(errors='replace')[-4096:])
    return result.stdout


try:
    if SOURCE.exists() or SOURCE.is_symlink():
        raise ValueError('new owned source directory required')
    if run(['/usr/bin/git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], 'input-identity').decode().splitlines() != [HEAD, TREE]:
        raise ValueError('input source identity differs')
    commit = run(['/usr/bin/git', 'cat-file', 'commit', HEAD], 'canonical-commit')
    if hashlib.sha1(b'commit ' + str(len(commit)).encode() + b'\0' + commit).hexdigest() != HEAD:
        raise ValueError('canonical commit bytes differ')
    if not commit.startswith(('tree ' + TREE + '\n').encode()):
        raise ValueError('canonical commit names another tree')
    parents = [line[7:].decode() for line in commit.split(b'\n\n', 1)[0].splitlines() if line.startswith(b'parent ')]
    if parents != ['bf15a519e9192b063071e8b9b61ef3319bed416e']:
        raise ValueError('canonical original parent differs')
    record['canonical_parent_preserved_in_commit'] = parents
    record['canonical_commit_sha256'] = hashlib.sha256(commit).hexdigest()
    objects = {HEAD: 'commit', TREE: 'tree', UPSTREAM_TREE: 'tree'}
    tree_counts = []
    for label, tree in (('canonical-tree', TREE), ('upstream-tree', UPSTREAM_TREE)):
        raw = run(['/usr/bin/git', 'ls-tree', '-r', '-t', '-z', tree], label)
        count = 0
        for item in raw.split(b'\0'):
            if not item:
                continue
            attributes, _ = item.split(b'\t', 1)
            mode, kind, sha = attributes.decode('ascii').split()
            if kind not in ('tree', 'blob') or not re.fullmatch('[0-9a-f]{40}', sha):
                raise ValueError('unexpected canonical tree entry')
            if mode not in ('040000', '100644', '100755', '120000'):
                raise ValueError('unsupported source tree mode')
            if sha in objects and objects[sha] != kind:
                raise ValueError('conflicting source object type')
            objects[sha] = kind
            count += 1
        tree_counts.append({'tree': tree, 'recursive_entries': count})
    object_ids = sorted(objects)
    listing = ''.join(sha + '\n' for sha in object_ids).encode()
    (OUT / 'object-list.txt').write_bytes(listing)
    (OUT / 'object-list.txt').chmod(0o444)
    checked = run(['/usr/bin/git', 'cat-file', '--batch-check'], 'input-object-inventory', listing).decode().splitlines()
    if len(checked) != len(object_ids):
        raise ValueError('source object inventory is incomplete')
    inventory = []
    for sha, line in zip(object_ids, checked):
        values = line.split()
        if len(values) != 3 or values[:2] != [sha, objects[sha]] or not values[2].isdigit():
            raise ValueError('required source object is unavailable: ' + sha)
        inventory.append({'sha1': sha, 'type': objects[sha], 'bytes': int(values[2])})
    inventory_bytes = (json.dumps(inventory, indent=2) + '\n').encode()
    (OUT / 'object-inventory.json').write_bytes(inventory_bytes)
    SOURCE.mkdir(mode=0o700)
    run(['/usr/bin/git', 'init', '--quiet', '--initial-branch=canonical-fe55', str(SOURCE)], 'init-owned-source', cwd=BASE)
    # The original commit bytes and source tree remain unchanged. The parent
    # history is intentionally outside this declared depth-one input snapshot.
    (SOURCE / '.git/shallow').write_text(HEAD + '\n')
    if (SOURCE / '.git/objects/info/alternates').exists():
        raise ValueError('new owned source unexpectedly borrows another object store')
    record.update(tree_inventory=tree_counts, objects=len(inventory), object_bytes=sum(item['bytes'] for item in inventory),
                  object_list_sha256=hashlib.sha256(listing).hexdigest(),
                  object_inventory_sha256=hashlib.sha256(inventory_bytes).hexdigest(),
                  pack_prefix=str(SOURCE / '.git/objects/pack/pack'), passed=True)
except Exception as error:
    record.update(passed=False, error=type(error).__name__ + ': ' + str(error))
finally:
    record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: record[key] for key in ('passed', 'source_root', 'objects', 'object_bytes', 'object_list_sha256', 'error') if key in record}))
raise SystemExit(0 if record['passed'] else 1)
