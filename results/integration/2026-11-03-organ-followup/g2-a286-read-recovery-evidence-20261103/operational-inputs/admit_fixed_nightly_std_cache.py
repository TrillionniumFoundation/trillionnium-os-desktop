"""Create-only admission of four checksum-verified fixed-nightly archives."""
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import hashlib
import json
import os
import stat
import tempfile

BASE = Path('/data/trill-organ-20261103-f1-build')
PRIVATE = BASE / 'cargo-home'
OLD = Path('/data/lan-archive-20261103/desktop/old-dev/trill-product-convergence-20261026-root/f1-cargo-home')
OUT = BASE / 'fixed-nightly-std-cache-admission-a286-v1'
INVENTORY = BASE / 'fixed-nightly-std-cache-a286-v1/result.json'
LOCK = BASE / 'rustup-home/toolchains/nightly-2026-07-21-x86_64-unknown-linux-gnu/lib/rustlib/src/rust/library/Cargo.lock'
LOCK_SHA = '9e87d1ac04edbf5fa61e27cb21984a83566573a007767713868965fba70acb6d'
INVENTORY_SHA = '19b0272f0a27cf93c21efd11fe836eaa4b70c9fc101ccd2ab6462f5c42357ea3'
NAMES = {'getopts@0.2.24', 'libc@0.2.185', 'memchr@2.7.6', 'rustc-literal-escaper@0.0.8'}
REGISTRY = 'index.crates.io-1949cf8c6b5b557f'
OUT.mkdir(mode=0o700)
report = {'schema': 'hepta.fixed-nightly-standard-library-cache-admission.v1',
          'completed': False, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
          'copies': [], 'existing_archives': [], 'planned_archive_count': 4,
          'planned_archive_bytes': 954962, 'source_cache_modified': False,
          'source_files_modified': False, 'lock_files_modified': False,
          'indices_modified': False, 'kernel_built': False,
          'locked_204_graph_verified': False, 'native_execution_verified': False, 'g2_complete': False}
leases = []


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def copy_exact(source, destination, expected, expected_bytes):
    if not destination.is_relative_to(PRIVATE) or destination.exists() or destination.is_symlink():
        raise ValueError('cache admission must create a new private path')
    if destination.parent.resolve(strict=True) != destination.parent:
        raise ValueError('private cache parent must not alias another directory')
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    source_stat = os.fstat(fd)
    if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size != expected_bytes:
        os.close(fd)
        raise ValueError('source archive identity or size differs')
    tmp_fd, name = tempfile.mkstemp(prefix='.fixed-nightly-std-cache-', dir=destination.parent)
    staged = Path(name)
    staged_stat = os.fstat(tmp_fd)
    h = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, 'rb') as reader, os.fdopen(tmp_fd, 'wb') as writer:
            for block in iter(lambda: reader.read(1024 * 1024), b''):
                writer.write(block)
                h.update(block)
                total += len(block)
            writer.flush()
            if h.hexdigest() != expected or total != expected_bytes:
                raise ValueError('source archive differs from fixed library lock')
            os.fchmod(writer.fileno(), 0o444)
            os.fsync(writer.fileno())
        os.link(staged, destination, follow_symlinks=False)
        if digest(destination) != expected:
            raise ValueError('admitted private archive differs')
        report['copies'].append({'source': str(source), 'destination': str(destination),
                                 'bytes': total, 'sha256': expected, 'create_only': True})
    finally:
        if staged.exists() and (staged.stat().st_dev, staged.stat().st_ino) == (staged_stat.st_dev, staged_stat.st_ino):
            staged.unlink()


try:
    if digest(INVENTORY) != INVENTORY_SHA or digest(LOCK) != LOCK_SHA:
        raise ValueError('fixed inventory or standard-library lock differs')
    inventory = json.loads(INVENTORY.read_bytes())
    if inventory.get('passed') is not True or inventory.get('lock_sha256') != LOCK_SHA:
        raise ValueError('completed exact inventory required')
    planned = [p for p in inventory['registry'] if p['name'] + '@' + p['version'] in NAMES]
    if len(planned) != 4 or set(inventory['can_admit_archives_from_old_f1']) != NAMES:
        raise ValueError('four fixed admissions required')
    if sum(p['caches']['old_f1_read_only']['archive']['bytes'] for p in planned) != 954962:
        raise ValueError('planned copy size differs')
    report.update(inventory_sha256=INVENTORY_SHA, fixed_library_lock_sha256=LOCK_SHA,
                  fixed_nightly='nightly-2026-07-21')
    if PRIVATE.is_symlink() or PRIVATE.resolve(strict=True) != PRIVATE:
        raise ValueError('canonical task-private Cargo cache required')
    for lock in (BASE / 'kernel-target/.g2-product-build.lock', BASE / 'static-target/.hepta-native-userspace.lock'):
        descriptor = os.open(lock, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(descriptor)
            raise ValueError('existing owned build lease identity differs')
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        leases.append(descriptor)
    for package in planned:
        name, version, checksum = package['name'], package['version'], package['checksum']
        relative = Path('registry/cache') / REGISTRY / (name + '-' + version + '.crate')
        destination, source = PRIVATE / relative, OLD / relative
        old = package['caches']['old_f1_read_only']['archive']
        if old.get('checksum_matches') is not True or old['sha256'] != checksum or old['path'] != str(source):
            raise ValueError('inventory source binding differs')
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file() or digest(destination) != checksum:
                raise ValueError('existing private archive differs; left unchanged')
            report['existing_archives'].append({'path': str(destination), 'sha256': checksum})
        else:
            copy_exact(source, destination, checksum, old['bytes'])
    if digest(LOCK) != LOCK_SHA or digest(INVENTORY) != INVENTORY_SHA:
        raise ValueError('fixed inputs changed during admission')
    report['remaining_archives_not_admitted'] = [p['name'] + '@' + p['version'] for p in inventory['registry']
        if not p['caches']['private']['archive']['checksum_matches'] and p['name'] + '@' + p['version'] not in NAMES]
    report['remaining_archives_not_claimed_required_or_unneeded'] = True
    report['completed'] = True
except Exception as error:
    report['error'] = type(error).__name__ + ': ' + str(error)
finally:
    for descriptor in reversed(leases):
        os.close(descriptor)
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'completed': report['completed'], 'copies': len(report['copies']),
                  'copy_bytes': sum(item['bytes'] for item in report['copies']),
                  'existing_archives': len(report['existing_archives']), 'error': report.get('error')}))
raise SystemExit(0 if report['completed'] else 1)
