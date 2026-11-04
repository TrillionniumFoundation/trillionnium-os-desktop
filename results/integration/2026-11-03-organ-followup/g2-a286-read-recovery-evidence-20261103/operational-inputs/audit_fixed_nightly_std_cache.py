"""Inventory only the exact installed nightly's standard-library lock/cache."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import stat
import tomllib

BASE = Path('/data/trill-organ-20261103-f1-build')
LOCK = BASE / 'rustup-home/toolchains/nightly-2026-07-21-x86_64-unknown-linux-gnu/lib/rustlib/src/rust/library/Cargo.lock'
LOCK_SHA = '9e87d1ac04edbf5fa61e27cb21984a83566573a007767713868965fba70acb6d'
OUT = BASE / 'fixed-nightly-std-cache-a286-v1'
REGISTRY = 'index.crates.io-1949cf8c6b5b557f'
CACHES = {
    'private': BASE / 'cargo-home',
    'old_f1_read_only': Path('/data/lan-archive-20261103/desktop/old-dev/trill-product-convergence-20261026-root/f1-cargo-home'),
}
OUT.mkdir(mode=0o700)
report = {
    'schema': 'hepta.fixed-nightly-standard-library-cache-inventory.v1',
    'passed': False,
    'started_at_utc': datetime.now(timezone.utc).isoformat(),
    'fixed_nightly': 'nightly-2026-07-21',
    'installed_rustc_commit': '87e5904f5eb6398af6b22eac2802c78934260c48',
    'compiler_identity_remeasured_by_this_inventory': False,
    'lock_path': str(LOCK),
    'required_lock_sha256': LOCK_SHA,
    'cache_modified': False,
    'lock_modified': False,
    'registry': [],
    'kernel_built': False,
    'locked_204_graph_verified': False,
    'native_execution_verified': False,
    'g2_complete': False,
}


def regular_bytes(path, bound):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > bound:
            raise ValueError('bounded regular file required: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(bound + 1)
        after = os.fstat(fd)
        if len(data) != before.st_size or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('file changed during inventory: ' + str(path))
        return data
    finally:
        os.close(fd)


def sparse_path(name):
    name = name.lower()
    if len(name) < 3:
        return str(len(name)) + '/' + name
    if len(name) == 3:
        return '3/' + name[0] + '/' + name
    return name[:2] + '/' + name[2:4] + '/' + name


def archive_info(path, checksum):
    result = {'path': str(path), 'present': False, 'checksum_matches': False}
    try:
        data = regular_bytes(path, 64 * 1024**2)
    except FileNotFoundError:
        return result
    result.update(present=True, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    result['checksum_matches'] = result['sha256'] == checksum
    return result


def index_info(path, package):
    result = {'path': str(path), 'present': False, 'exact_version_checksum_present': False}
    try:
        data = regular_bytes(path, 8 * 1024**2)
    except FileNotFoundError:
        return result
    result.update(present=True, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    for part in data.split(b'\0'):
        if not part.startswith(b'{'):
            continue
        item = json.loads(part)
        if (item.get('name'), item.get('vers'), item.get('cksum')) == (package['name'], package['version'], package['checksum']):
            result['exact_version_checksum_present'] = True
            break
    return result


try:
    locked = regular_bytes(LOCK, 65536)
    if len(locked) != 9835 or hashlib.sha256(locked).hexdigest() != LOCK_SHA:
        raise ValueError('installed fixed-nightly library lock differs')
    packages = tomllib.loads(locked.decode())['package']
    registry = [p for p in packages if p.get('source') == 'registry+https://github.com/rust-lang/crates.io-index']
    if len(packages) != 49 or len(registry) != 30:
        raise ValueError('fixed standard-library package inventory differs')
    (OUT / 'library.Cargo.lock').write_bytes(locked)
    (OUT / 'library.Cargo.lock').chmod(0o444)
    report.update(lock_bytes=len(locked), lock_sha256=LOCK_SHA, packages=len(packages), registry_packages=len(registry))
    for package in registry:
        item = {k: package[k] for k in ('name', 'version', 'checksum')}
        item['caches'] = {}
        for label, root in CACHES.items():
            archive = root / 'registry/cache' / REGISTRY / (package['name'] + '-' + package['version'] + '.crate')
            index = root / 'registry/index' / REGISTRY / '.cache' / sparse_path(package['name'])
            item['caches'][label] = {'archive': archive_info(archive, package['checksum']), 'index': index_info(index, package)}
        report['registry'].append(item)
    if regular_bytes(LOCK, 65536) != locked:
        raise ValueError('fixed library lock changed during inventory')
    report['private_missing_archives'] = [p['name'] + '@' + p['version'] for p in report['registry'] if not p['caches']['private']['archive']['checksum_matches']]
    report['private_missing_indices'] = [p['name'] + '@' + p['version'] for p in report['registry'] if not p['caches']['private']['index']['exact_version_checksum_present']]
    report['can_admit_archives_from_old_f1'] = [p['name'] + '@' + p['version'] for p in report['registry'] if not p['caches']['private']['archive']['present'] and p['caches']['old_f1_read_only']['archive']['checksum_matches']]
    report['passed'] = True
except Exception as error:
    report['error'] = type(error).__name__ + ': ' + str(error)
finally:
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: report[k] for k in ('passed', 'packages', 'registry_packages', 'private_missing_archives', 'private_missing_indices', 'can_admit_archives_from_old_f1', 'error') if k in report}))
raise SystemExit(0 if report['passed'] else 1)
