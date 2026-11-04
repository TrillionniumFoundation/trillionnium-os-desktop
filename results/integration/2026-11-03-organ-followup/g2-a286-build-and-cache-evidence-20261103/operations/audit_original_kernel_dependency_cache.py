"""Read only the two exact original lockfiles and candidate Cargo caches."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tomllib

BASE = Path('/data/trill-organ-20261103-f1-build')
SOURCE = Path('/home/qian-qi/work/trill-organ-20261103-f1/desktop-owner-a286-owned-source')
OUT = BASE / 'original-kernel-dependency-cache-a286-v1'
HOMES = [BASE / 'cargo-home', Path('/home/qian-qi/.cargo'), Path('/data/trill-organ-owner-20261103/cargo-home')]
REGISTRY = 'index.crates.io-1949cf8c6b5b557f'
LOCKS = [('kernel/asterinas/osdk/Cargo.lock', '99a21f72f6a9f1582553b34f06e80f86e539f38e62eab7a0847afd0906e75be3', 154),
         ('support/build/minimal/Cargo.lock', 'e54bc99b3df5e21a1fdcd88d89b32ac478e73c7b4bf69ae0b1084f59d56fc506', 204)]
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'}
OUT.mkdir(mode=0o700)
record = {'schema': 'hepta.original-kernel-cache-inventory.v1', 'passed': False,
          'started_at_utc': datetime.now(timezone.utc).isoformat(), 'source_head': 'a286e0f922bf8e439e8951ae1538abeac0b26477',
          'locks': [], 'registry': [], 'git': [], 'cache_modified': False,
          'locked_204_graph_verified': False, 'kernel_built': False, 'native_execution_verified': False, 'g2_complete': False}


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def sparse_path(name):
    if len(name) < 3:
        return str(len(name)) + '/' + name
    if len(name) == 3:
        return '3/' + name[0] + '/' + name
    return name[:2] + '/' + name[2:4] + '/' + name


def cache(home, package):
    name, version, checksum = package['name'], package['version'], package['checksum']
    archive = home / 'registry/cache' / REGISTRY / (name + '-' + version + '.crate')
    index = home / 'registry/index' / REGISTRY / '.cache' / sparse_path(name)
    value = {'cargo_home': str(home), 'archive': str(archive), 'archive_valid': False,
             'index': str(index), 'index_contains_pinned_version': False}
    if archive.is_file() and not archive.is_symlink():
        value.update(archive_bytes=archive.stat().st_size, archive_sha256=digest(archive))
        value['archive_valid'] = value['archive_sha256'] == checksum
    if index.is_file() and not index.is_symlink():
        data = index.read_bytes()
        value.update(index_bytes=len(data), index_sha256=hashlib.sha256(data).hexdigest())
        for part in data.split(b'\0'):
            if part.startswith(b'{'):
                entry = json.loads(part)
                if entry.get('name') == name and entry.get('vers') == version and entry.get('cksum') == checksum:
                    value['index_contains_pinned_version'] = True
    return value


try:
    packages = {}
    git_packages = {}
    for relative, expected, count in LOCKS:
        path = SOURCE / relative
        if digest(path) != expected:
            raise ValueError('original lock bytes differ: ' + relative)
        parsed = tomllib.loads(path.read_text())['package']
        if len(parsed) != count:
            raise ValueError('original lock inventory count differs')
        record['locks'].append({'path': relative, 'sha256': expected, 'declared_packages': count})
        for package in parsed:
            source = package.get('source', '')
            if source == 'registry+https://github.com/rust-lang/crates.io-index':
                key = (package['name'], package['version'])
                if key in packages and packages[key]['checksum'] != package['checksum']:
                    raise ValueError('conflicting original registry checksums')
                packages[key] = package
            elif source.startswith('git+'):
                git_packages[(package['name'], source)] = package
            elif source:
                raise ValueError('unexpected original dependency source')
    for key, package in sorted(packages.items()):
        private = cache(HOMES[0], package)
        candidates = [private]
        if not (private['archive_valid'] and private['index_contains_pinned_version']):
            candidates.extend(cache(home, package) for home in HOMES[1:])
        record['registry'].append({'name': package['name'], 'version': package['version'],
                                   'checksum': package['checksum'], 'caches': candidates})
    for (_, source), package in sorted(git_packages.items()):
        commit = source.rsplit('#', 1)[1]
        value = {'name': package['name'], 'source': source, 'commit': commit, 'caches': []}
        for home in HOMES:
            root = home / 'git/db'
            if not root.is_dir():
                continue
            for path in sorted(root.iterdir()):
                if not path.name.startswith(package['name'] + '-') or not path.is_dir() or path.is_symlink():
                    continue
                checked = subprocess.run(['/usr/bin/git', '--git-dir=' + str(path), 'cat-file', '-t', commit],
                                         env=ENV, capture_output=True, timeout=20, check=False)
                value['caches'].append({'cargo_home': str(home), 'git_db': str(path),
                                        'commit_present': checked.returncode == 0 and checked.stdout.strip() == b'commit',
                                        'exit_code': checked.returncode, 'stderr': checked.stderr.decode(errors='replace'),
                                        'alternates_present': (path / 'objects/info/alternates').exists()})
        record['git'].append(value)
    record['passed'] = True
except Exception as error:
    record['error'] = type(error).__name__ + ': ' + str(error)
finally:
    record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    data = (json.dumps(record, indent=2) + '\n').encode()
    (OUT / 'inventory.json').write_bytes(data)
    missing = []
    for item in record['registry']:
        private = item['caches'][0]
        if private['archive_valid'] and private['index_contains_pinned_version']:
            continue
        missing.append({'name': item['name'], 'version': item['version'],
                        'private_archive_valid': private['archive_valid'], 'private_index_present': private['index_contains_pinned_version'],
                        'archive_sources': [x['cargo_home'] for x in item['caches'][1:] if x['archive_valid']],
                        'index_sources': [x['cargo_home'] for x in item['caches'][1:] if x['index_contains_pinned_version']]})
    summary = {'schema': 'hepta.original-kernel-cache-summary.v1', 'passed': record['passed'], 'error': record.get('error'),
               'registry_packages': len(record['registry']), 'missing_private': missing, 'git': record['git'],
               'inventory_bytes': len(data), 'inventory_sha256': hashlib.sha256(data).hexdigest(),
               'cache_modified': False, 'locked_204_graph_verified': False, 'kernel_built': False, 'g2_complete': False}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({'passed': record['passed'], 'registry_packages': len(record['registry']), 'missing_private': len(missing),
                  'git_packages': len(record['git']), 'error': record.get('error')}))
raise SystemExit(0 if record['passed'] else 1)
