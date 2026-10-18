#!/usr/bin/env python3
"""Complete the verified cache relocation after preserving both failed attempts."""
import ast
import gzip
import json
import os
from pathlib import Path
import shutil

BASE = Path('/workspace/scratch/98f315e377b2')
RETAINED = Path('/dev/shm/trill-hepta-r4-enuzuex9')
WORK = BASE / 'next-tools/r6-retained-cache-migration-03'
PREVIOUS = BASE / 'next-tools/r6-retained-cache-migration-02'
FIRST = BASE / 'next-tools/r6-retained-cache-migration-01'
definition_path = BASE / 'next-tools/migrate-r6-retained-cache-02.py'
module = ast.parse(definition_path.read_text())
namespace = {'BASE': BASE, 'RETAINED': RETAINED}
# Reuse only the exact pure manifest/hash/resource functions, without running
# either previous script's mutation body or rewriting its failed receipt.
definitions = [n for n in module.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
exec(compile(ast.Module(body=definitions, type_ignores=[]), str(definition_path), 'exec'), namespace)
snapshot, digest, resources, source_identity, now = [namespace[name] for name in
    ['snapshot', 'digest', 'resources', 'source_identity', 'now']]

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

require(not WORK.exists(), 'continuation evidence directory must be new')
WORK.mkdir(mode=0o700)
previous_path = PREVIOUS / 'receipt.json'
previous = json.loads(previous_path.read_text())
require(previous['status'] == 'failed', 'previous overall failure must be preserved')
require(json.loads((FIRST / 'receipt.json').read_text())['status'] == 'failed', 'first failure must remain failed')
record = {'started_at_utc': now(), 'status': 'running', 'migrations': [],
          'source_before': source_identity(), 'resources_before': resources(),
          'previous_failed_attempts': [
              {'receipt_path': str(root / 'receipt.json'), 'sha256': digest(root / 'receipt.json'), 'status': 'failed'}
              for root in [FIRST, PREVIOUS]],
          'definition_source_sha256': digest(definition_path),
          'directory_mtime_equivalence_required': False,
          'file_bytes_modes_mtimes_types_and_symlinks_strict': True,
          'original_source_modified': False, 'historical_logs_modified': False,
          'compilers_modified': False, 'qualified_ui_elfs_modified': False,
          'cache_contents_preserved': False, 'original_cache_access_paths_preserved': False}
try:
    carried = previous['migrations'][0]
    require(carried['label'] == 'check-target' and carried['status'] == 'migrated_verified_original_path_preserved',
            'check-target migration did not complete in the previous attempt')
    target = Path(carried['source'])
    destination = Path(carried['destination'])
    manifest_path = Path(carried['manifest_path'])
    require(digest(manifest_path) == carried['manifest_sha256'], 'carried manifest hash differs')
    expected = json.loads(gzip.decompress(manifest_path.read_bytes()))
    require(target.is_symlink() and target.resolve(strict=True) == destination.resolve(strict=True), 'carried original path differs')
    require(snapshot(destination) == expected, 'carried cache contents or modes differ')
    carried['independently_reverified_in_continuation'] = True
    record['migrations'].append(carried)

    source = RETAINED / 'cargo'
    destination = PREVIOUS / 'cargo-cache'
    old = RETAINED / 'cargo.r6-verified-migration-old'
    require(source.is_dir() and not source.is_symlink() and not old.exists(), 'Cargo source must be the restored owned original')
    require(source.stat().st_uid == os.geteuid() and destination.stat().st_uid == os.geteuid(), 'Cargo copy ownership differs')
    cargo_item = previous['migrations'][1]
    manifest_path = Path(cargo_item['manifest_path'])
    require(digest(manifest_path) == cargo_item['manifest_sha256'], 'Cargo manifest hash differs')
    expected = json.loads(gzip.decompress(manifest_path.read_bytes()))
    require(snapshot(source) == expected, 'original Cargo cache changed after rollback')
    item = dict(cargo_item)
    item.update(status='verifying_existing_copy', copied_root_mode_before=destination.stat().st_mode & 0o777)
    record['migrations'].append(item)
    destination.chmod(expected['.']['mode'])
    require(snapshot(destination) == expected, 'verified Cargo copy differs after restoring private root mode')
    original_stat = source.stat()
    print('Completing Cargo cache relocation; all 56,912 file hashes and modes match, copied root mode restored to 0700.', flush=True)
    source.rename(old)
    try:
        source.symlink_to(destination, target_is_directory=True)
        # The prior filesystem path swap changed only the disk directory root
        # mode. Restore it explicitly after the swap, then verify everything.
        destination.chmod(expected['.']['mode'])
        require(source.resolve(strict=True) == destination.resolve(strict=True), 'Cargo access path points elsewhere')
        require(snapshot(source.resolve(strict=True)) == expected, 'Cargo post-swap full manifest differs')
    except BaseException:
        if source.is_symlink():
            source.unlink()
        old.rename(source)
        raise
    moved_stat = old.stat()
    require((moved_stat.st_dev, moved_stat.st_ino) == (original_stat.st_dev, original_stat.st_ino)
            and not old.is_symlink(), 'duplicate RAM directory identity changed')
    shutil.rmtree(old)
    require(not old.exists(), 'duplicate Cargo RAM directory remained')
    item.update(status='migrated_verified_original_path_preserved', copied_root_mode_after=destination.stat().st_mode & 0o777,
                resources_after=resources())
    record['source_after'] = source_identity()
    require(record['source_after'] == record['source_before'], 'original source changed during recovery')
    record.update(status='passed', cache_contents_preserved=True, original_cache_access_paths_preserved=True)
except BaseException as error:
    record['status'] = 'failed'
    record['error'] = {'type': type(error).__name__, 'detail': str(error)}
    raise
finally:
    record['resources_after'] = resources()
    record['ended_at_utc'] = now()
    with (WORK / 'receipt.json').open('x') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': record['status'], 'receipt': str(WORK / 'receipt.json'),
                      'ram_filesystem_free_bytes_after': record['resources_after']['ram_filesystem_free_bytes'],
                      'disk_free_bytes_after': record['resources_after']['disk_free_bytes']}), flush=True)
