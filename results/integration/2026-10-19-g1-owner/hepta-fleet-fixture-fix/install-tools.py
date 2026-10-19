#!/usr/bin/env python3
"""Install verified prebuilt validation helpers into a separate overlay only."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tomllib
import urllib.request

BASE = Path('/workspace/scratch/499c7902de8e')
OUT = BASE / 'r10-fleet-fixture-tools'
EVIDENCE = BASE / 'r10-evidence/fleet-fixture-fix'
RUST = BASE / 'r10-cargo-deny-tools/rustup-home/toolchains/1.95.0-x86_64-unknown-linux-gnu'
BIN = OUT / 'bin'
BIN.mkdir(parents=True, exist_ok=True)
(OUT / 'downloads').mkdir(exist_ok=True)
receipt = {'schema': 1, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'install_root': str(OUT), 'reused_base_toolchain': str(RUST), 'downloads': [],
           'original_toolchain_modified': False, 'source_builds': False, 'tools': []}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, name, expected=None, evidence=False):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    request = urllib.request.Request(url, headers={'User-Agent': 'Hepta-fleet-fixture-validation'})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(50_000_001)
    assert len(data) <= 50_000_000
    if expected is not None:
        assert sha(data) == expected, name
    path = (EVIDENCE if evidence else OUT / 'downloads') / name
    path.write_bytes(data)
    receipt['downloads'].append({'url': url, 'started_at': started,
                                'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                'path': str(path), 'bytes': len(data), 'sha256': sha(data),
                                'expected_sha256': expected})
    return data


def copy_archive_binaries(data, wanted):
    found = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as tf:
        for member in tf:
            name = Path(member.name).name
            if name in wanted and member.isfile():
                assert name not in found
                content = tf.extractfile(member).read()
                destination = BIN / name
                destination.write_bytes(content)
                destination.chmod(0o755)
                receipt['tools'].append({'path': str(destination), 'bytes': len(content),
                                         'sha256': sha(content), 'archive_member': member.name})
                found.add(name)
    assert found == set(wanted), (wanted, found)


try:
    rust_url = 'https://static.rust-lang.org/dist/channel-rust-1.95.0.toml'
    checksum = fetch(rust_url + '.sha256', 'channel-rust-1.95.0.toml.sha256', evidence=True).decode().split()[0]
    manifest_bytes = fetch(rust_url, 'channel-rust-1.95.0.toml', checksum, evidence=True)
    manifest = tomllib.loads(manifest_bytes.decode())
    receipt['rust_manifest_date'] = manifest['date']
    for package, wanted in [('clippy-preview', ['cargo-clippy', 'clippy-driver']),
                            ('rustfmt-preview', ['cargo-fmt', 'rustfmt'])]:
        target = manifest['pkg'][package]['target']['x86_64-unknown-linux-gnu']
        url = target['xz_url']
        assert url.startswith('https://static.rust-lang.org/dist/')
        data = fetch(url, package + '-1.95.0.tar.xz', target['xz_hash'])
        copy_archive_binaries(data, wanted)
    release = json.loads(json.loads((EVIDENCE / 'nextest-release.json').read_text())['raw_response_content'])
    assert release['tag_name'] == 'cargo-nextest-0.9.148'
    assets = {x['name']: x for x in release['assets']}
    prefix = 'cargo-nextest-0.9.148-x86_64-unknown-linux-musl'
    checksum_asset = assets[prefix + '.sha256']
    checksum_bytes = fetch(checksum_asset['browser_download_url'], prefix + '.sha256',
                           checksum_asset['digest'].removeprefix('sha256:'), evidence=True)
    archive_asset = assets[prefix + '.tar.gz']
    expected = archive_asset['digest'].removeprefix('sha256:')
    assert checksum_bytes.decode().split()[0] == expected
    data = fetch(archive_asset['browser_download_url'], prefix + '.tar.gz', expected)
    copy_archive_binaries(data, ['cargo-nextest'])
    for name in ['cargo', 'rustc', 'rustdoc']:
        link = BIN / name
        assert not link.exists()
        link.symlink_to(RUST / 'bin' / name)
    assert not (OUT / 'lib').exists()
    (OUT / 'lib').symlink_to(RUST / 'lib', target_is_directory=True)
    just = BASE / 'r10-evidence/owner-ci/tools/bin/just'
    shutil.copyfile(just, BIN / 'just')
    (BIN / 'just').chmod(0o755)
    env = os.environ.copy()
    env.update({'PATH': str(BIN) + ':' + env.get('PATH', ''),
                'RUSTC': str(RUST / 'bin/rustc'), 'RUSTDOC': str(RUST / 'bin/rustdoc')})
    for name, args in [('cargo', ['-V']), ('rustc', ['-vV']), ('rustfmt', ['--version']),
                       ('cargo-clippy', ['--version']), ('cargo-nextest', ['nextest', '--version']),
                       ('just', ['--version'])]:
        command = [str(BIN / name), *args]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        receipt.setdefault('versions', []).append({'argv': command, 'exit_code': result.returncode,
                                                    'stdout': result.stdout, 'stderr': result.stderr})
        assert result.returncode == 0, receipt['versions'][-1]
    receipt['status'] = 'installed'
except BaseException as error:
    receipt['status'] = 'failed'
    receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
    raise
finally:
    receipt['completed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (EVIDENCE / 'tools-installation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'downloads': len(receipt['downloads']),
                      'tools': len(receipt['tools']), 'receipt': str(EVIDENCE / 'tools-installation.json')}))
