#!/usr/bin/env python3
"""Copy the retained UI target byte-for-byte into one new R6 disk target."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time

BASE = Path(__file__).resolve().parent
SEED = Path('/dev/shm/trill-ui-r5-nsniox8o/target')
TARGET = BASE / 'target'
BUILD = Path('/workspace/scratch/98f315e377b2/next-tools/ui-r5-build-02/receipt.json')
FLOOR = 2 * 1024**3


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


record = {'started_utc': datetime.now(timezone.utc).isoformat(),
    'seed': str(SEED), 'target': str(TARGET), 'status': 'running',
    'source_target_mutated': False, 'cargo_executed': False,
    'minimum_free_bytes': FLOOR, 'files': []}
require(BASE.stat().st_uid == os.geteuid() and stat.S_IMODE(BASE.stat().st_mode) == 0o700,
    'new private root required')
require(not TARGET.exists() and SEED.is_dir(), 'new target and existing seed required')
receipt = json.loads(BUILD.read_text())
record['recorded_build_source'] = receipt['source_commit']
record['recorded_build_source_tree'] = receipt['source_tree']
record['seed_build_receipt_sha256'] = digest(BUILD)
original = {name: digest(SEED / 'debug' / name) for name in receipt['binaries']}
require(all(original[name] == value['sha256'] for name, value in receipt['binaries'].items()),
    'retained four production ELF identities drifted')
record['production_elf_hashes_before'] = original
started = time.monotonic()


def copy_verified(source, target):
    src, dst = Path(source), Path(target)
    require(time.monotonic() - started < 300, 'bounded copy deadline exceeded')
    require(shutil.disk_usage(BASE).free >= FLOOR + src.stat().st_size,
        'disk reserve reached before copying an owned cache file')
    before = src.stat()
    value = hashlib.sha256()
    with src.open('rb') as incoming, dst.open('xb') as outgoing:
        for block in iter(lambda: incoming.read(1024 * 1024), b''):
            value.update(block)
            outgoing.write(block)
    shutil.copystat(src, dst)
    after = src.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns), 'seed file changed during copy')
    require(dst.stat().st_size == before.st_size and digest(dst) == value.hexdigest(),
        'copied cache bytes do not match source stream')
    record['files'].append({'path': str(src.relative_to(SEED)), 'bytes': before.st_size,
        'sha256': value.hexdigest(), 'mode': stat.S_IMODE(before.st_mode)})
    return str(dst)


try:
    record['free_bytes_before'] = shutil.disk_usage(BASE).free
    shutil.copytree(SEED, TARGET, symlinks=True, copy_function=copy_verified)
    record['production_elf_hashes_after'] = {name: digest(SEED / 'debug' / name) for name in original}
    require(record['production_elf_hashes_after'] == original, 'retained original ELFs changed')
    record['copied_file_count'] = len(record['files'])
    record['copied_bytes'] = sum(item['bytes'] for item in record['files'])
    record['status'] = 'passed'
except BaseException as error:
    record['status'] = 'failed'
    record['error'] = str(error)
    raise
finally:
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    record['elapsed_seconds'] = round(time.monotonic() - started, 3)
    record['free_bytes_after'] = shutil.disk_usage(BASE).free
    (BASE / 'copy-receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: value for key, value in record.items() if key != 'files'}, indent=2), flush=True)
