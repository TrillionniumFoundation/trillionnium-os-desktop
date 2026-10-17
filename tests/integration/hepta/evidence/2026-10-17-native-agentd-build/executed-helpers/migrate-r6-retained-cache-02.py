#!/usr/bin/env python3
"""Move only owned, fully verified R4 build caches from RAM to disk.

Preserve every file byte, mode, file mtime and symlink, keep the original access
paths as symlinks, and retain manifests before releasing the duplicate RAM.
Original Git source, historical logs, compilers and R5 UI ELFs are untouched.
"""
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

BASE = Path('/workspace/scratch/98f315e377b2')
RETAINED = Path('/dev/shm/trill-hepta-r4-enuzuex9')
WORK = BASE / 'next-tools/r6-retained-cache-migration-02'
PREVIOUS = BASE / 'next-tools/r6-retained-cache-migration-01'

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def snapshot(root):
    records = {}
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        name = str(path.relative_to(root))
        item = {'mode': stat.S_IMODE(info.st_mode), 'mtime_ns': info.st_mtime_ns}
        if stat.S_ISREG(info.st_mode):
            item.update(type='file', bytes=info.st_size, sha256=digest(path))
        elif stat.S_ISDIR(info.st_mode):
            item.update(type='directory')
            item.pop('mtime_ns')  # Directory bookkeeping time is not cache content.
        elif stat.S_ISLNK(info.st_mode):
            item.update(type='symlink', target=os.readlink(path))
        else:
            raise RuntimeError('Unsupported cache entry type: ' + name)
        records[name] = item
    return records

def resources():
    q = Path('/sys/fs/cgroup')
    return {'disk_free_bytes': shutil.disk_usage(BASE).free,
            'ram_filesystem_free_bytes': shutil.disk_usage(RETAINED).free,
            'memory_stat': (q / 'memory.stat').read_text(),
            'memory_events': (q / 'memory.events').read_text()}

def source_identity():
    source = BASE / 'next-hepta-source'
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain=v1', '--untracked-files=all'], text=True)
    assert head == 'f8c9419df6ddeb36ff8b522a50219981fb8d9345' and not status
    return {'commit': head, 'clean': True, 'lock_sha256': digest(source / 'codex-rs/Cargo.lock')}

owner = json.loads((RETAINED / 'ownership.json').read_text())
assert owner['root'] == str(RETAINED)
assert owner['source_pin'] == 'f8c9419df6ddeb36ff8b522a50219981fb8d9345'
assert RETAINED.is_dir() and RETAINED.stat().st_uid == os.geteuid()
assert not WORK.exists()
WORK.mkdir(mode=0o700)
record = {'started_at_utc': now(), 'status': 'running', 'source_before': source_identity(),
          'ownership_receipt_sha256': digest(RETAINED / 'ownership.json'),
          'resources_before': resources(), 'migrations': [],
          'previous_attempt_receipt_path': str(PREVIOUS / 'receipt.json'),
          'previous_attempt_receipt_sha256': digest(PREVIOUS / 'receipt.json'),
          'directory_mtime_equivalence_required': False,
          'directory_mtime_scope': 'Copy01 differed only in 481 directory mtimes after path swap; original was restored. Every file byte, mode and file mtime plus entry types and symlink targets remain strict.',
          'original_source_modified': False, 'historical_logs_modified': False,
          'compilers_modified': False, 'qualified_ui_elfs_modified': False,
          'cache_contents_preserved': False, 'original_cache_access_paths_preserved': False}
try:
    for label, source in [('check-target', RETAINED / 'probe-check-02/target'), ('cargo-cache', RETAINED / 'cargo')]:
        assert source.is_dir() and not source.is_symlink()
        assert source.resolve() == source and source.stat().st_uid == os.geteuid()
        destination = (PREVIOUS if label == 'check-target' else WORK) / label
        temporary_old = source.with_name(source.name + '.r6-verified-migration-old')
        assert not temporary_old.exists()
        if label == 'check-target':
            prior = json.loads((PREVIOUS / 'receipt.json').read_text())
            assert prior['status'] == 'failed' and prior['migrations'][0]['verified_copy_matches_source']
            assert destination.is_dir() and not destination.is_symlink()
        else:
            assert not destination.exists()
        item = {'source': str(source), 'destination': str(destination), 'label': label, 'status': 'copying'}
        record['migrations'].append(item)
        before_stat = source.stat()
        before = snapshot(source)
        encoded = (json.dumps(before, sort_keys=True, separators=(',', ':')) + '\n').encode()
        manifest_path = WORK / (label + '-members.json.gz')
        manifest_path.write_bytes(gzip.compress(encoded, mtime=0))
        item.update(manifest_path=str(manifest_path), manifest_sha256=digest(manifest_path),
                    uncompressed_manifest_sha256=hashlib.sha256(encoded).hexdigest(),
                    entries=len(before), files=sum(v['type'] == 'file' for v in before.values()),
                    file_bytes=sum(v.get('bytes', 0) for v in before.values()))
        print(f'Copy and verify owned {label}: {item["files"]} files / {item["file_bytes"]} bytes.', flush=True)
        if label != 'check-target':
            shutil.copytree(source, destination, symlinks=True)
        else:
            item['reuses_verified_failed_attempt_disk_copy'] = True
        assert snapshot(destination) == before, 'Copied cache differs from original manifest'
        assert snapshot(source) == before, 'Source cache changed during copy'
        item['verified_copy_matches_source'] = True
        source.rename(temporary_old)
        try:
            source.symlink_to(destination, target_is_directory=True)
            assert source.resolve(strict=True) == destination
            assert snapshot(source.resolve(strict=True)) == before
        except BaseException:
            if source.is_symlink():
                source.unlink()
            temporary_old.rename(source)
            raise
        old_stat = temporary_old.stat()
        assert (old_stat.st_dev, old_stat.st_ino) == (before_stat.st_dev, before_stat.st_ino)
        assert temporary_old.parent == source.parent and not temporary_old.is_symlink()
        # Release only the duplicate directory after the complete verified
        # disk copy and original-path access have both been proven identical.
        shutil.rmtree(temporary_old)
        assert not temporary_old.exists()
        item['status'] = 'migrated_verified_original_path_preserved'
        item['resources_after'] = resources()
        print(f'Preserved {label} bytes at the original access path; duplicate RAM released.', flush=True)
    record['source_after'] = source_identity()
    assert record['source_after'] == record['source_before']
    record['cache_contents_preserved'] = True
    record['original_cache_access_paths_preserved'] = True
    record['status'] = 'passed'
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
                      'migrated_file_bytes': sum(x.get('file_bytes', 0) for x in record['migrations']),
                      'ram_filesystem_free_bytes_after': record['resources_after']['ram_filesystem_free_bytes'],
                      'disk_free_bytes_after': record['resources_after']['disk_free_bytes']}), flush=True)
