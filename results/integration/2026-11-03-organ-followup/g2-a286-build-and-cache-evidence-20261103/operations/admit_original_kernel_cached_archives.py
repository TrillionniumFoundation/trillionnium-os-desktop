"""Create-only admission of original-lock archives from the known old F1 cache."""
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
OUT = BASE / 'original-kernel-cache-admission-a286-v1'
INVENTORY = BASE / 'original-kernel-dependency-cache-a286-v1/inventory.json'
REGISTRY = 'index.crates.io-1949cf8c6b5b557f'
OUT.mkdir(mode=0o700)
report = {'schema': 'hepta.original-lock-cache-admission.v1', 'completed': False,
          'started_at_utc': datetime.now(timezone.utc).isoformat(), 'copies': [], 'existing_archives': 0,
          'remaining_archives': [], 'index_versions_present': 0, 'remaining_indices': [],
          'source_cache_modified': False, 'lock_files_modified': False,
          'kernel_built': False, 'locked_204_graph_verified': False, 'native_execution_verified': False, 'g2_complete': False}
leases = []


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def sparse_path(name):
    name = name.lower()
    if len(name) < 3:
        return str(len(name)) + '/' + name
    if len(name) == 3:
        return '3/' + name[0] + '/' + name
    return name[:2] + '/' + name[2:4] + '/' + name


def index_contains(path, package):
    if not path.is_file() or path.is_symlink():
        return False
    for part in path.read_bytes().split(b'\0'):
        if part.startswith(b'{'):
            item = json.loads(part)
            if item.get('name') == package['name'] and item.get('vers') == package['version'] and item.get('cksum') == package['checksum']:
                return True
    return False


def copy_exact(source, destination, expected, kind):
    if not destination.is_relative_to(PRIVATE) or destination.exists() or destination.is_symlink():
        raise ValueError('cache admission must create a new private path')
    if destination.parent.resolve() != destination.parent:
        raise ValueError('private cache parent must not alias another directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    source_stat = os.fstat(fd)
    if not stat.S_ISREG(source_stat.st_mode):
        os.close(fd)
        raise ValueError('source cache entry must be a regular file')
    tmp_fd, name = tempfile.mkstemp(prefix='.original-kernel-cache-', dir=destination.parent)
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
            if h.hexdigest() != expected or total != source_stat.st_size:
                raise ValueError('source cache changed or differs from original checksum')
            os.fchmod(writer.fileno(), 0o444)
            os.fsync(writer.fileno())
        os.link(staged, destination, follow_symlinks=False)
        if digest(destination) != expected:
            raise ValueError('admitted private cache bytes differ')
        report['copies'].append({'kind': kind, 'source': str(source), 'destination': str(destination),
                                 'bytes': total, 'sha256': expected, 'create_only': True})
    finally:
        if staged.exists() and (staged.stat().st_dev, staged.stat().st_ino) == (staged_stat.st_dev, staged_stat.st_ino):
            staged.unlink()


try:
    if digest(INVENTORY) != '455fad0fbc8d06de27fb11fbabe5379b045293ecbcd9e21457a160f9e606e7a8':
        raise ValueError('exact original lock cache inventory differs')
    inventory = json.loads(INVENTORY.read_bytes())
    if inventory.get('passed') is not True:
        raise ValueError('completed original lock inventory required')
    report['inventory_sha256'] = digest(INVENTORY)
    report['original_locks'] = inventory['locks']
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
    for package in inventory['registry']:
        name, version, checksum = package['name'], package['version'], package['checksum']
        relative = Path('registry/cache') / REGISTRY / (name + '-' + version + '.crate')
        destination, source = PRIVATE / relative, OLD / relative
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file() or digest(destination) != checksum:
                raise ValueError('existing private archive differs; left unchanged: ' + str(destination))
            report['existing_archives'] += 1
        elif source.is_file() and not source.is_symlink() and digest(source) == checksum:
            copy_exact(source, destination, checksum, 'original-lock-crate')
        else:
            unpacked = PRIVATE / 'registry/src' / REGISTRY / (name + '-' + version) / '.cargo-checksum.json'
            package_record = json.loads(unpacked.read_bytes()) if unpacked.is_file() and not unpacked.is_symlink() else {}
            report['remaining_archives'].append({'name': name, 'version': version,
                                                 'unpacked_package_checksum_matches': package_record.get('package') == checksum,
                                                 'unpacked_source_files_rehashed': False})
        relative = Path('registry/index') / REGISTRY / '.cache' / sparse_path(name)
        destination, source = PRIVATE / relative, OLD / relative
        if index_contains(destination, package):
            report['index_versions_present'] += 1
        elif not destination.exists() and not destination.is_symlink() and index_contains(source, package):
            copy_exact(source, destination, digest(source), 'original-registry-index')
            if not index_contains(destination, package):
                raise ValueError('admitted index does not contain original locked checksum')
            report['index_versions_present'] += 1
        else:
            report['remaining_indices'].append({'name': name, 'version': version, 'path': str(destination)})
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
                  'existing_archives': report['existing_archives'], 'remaining_archives': len(report['remaining_archives']),
                  'index_versions_present': report['index_versions_present'], 'remaining_indices': len(report['remaining_indices']),
                  'error': report.get('error')}))
raise SystemExit(0 if report['completed'] else 1)
