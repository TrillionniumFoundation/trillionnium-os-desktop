#!/usr/bin/env python3
"""Recover the original pinned A04 inputs from A01 Git history; execute none."""
import argparse
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile

DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
READ = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
MARKER = '.input-recovery-incomplete'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_metadata(path, limit=1024 * 1024):
    descriptor = os.open(path, READ)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError(f'not a bounded regular metadata file: {path}')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if identity(before) != identity(after) or len(data) != before.st_size:
        raise ValueError(f'metadata changed during read: {path}')
    return data


def read_git(repo, spec):
    """Read a pinned blob, bounded before allocation, without fetch or textconv."""
    command = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
               '-c', 'core.pager=cat', '-C', str(repo), 'show',
               '--no-ext-diff', '--no-textconv', spec['commit'] + ':' + spec['path']]
    environment = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LC_ALL': 'C',
                   'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0'}
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=environment) as process:
        data = process.stdout.read(spec['bytes'] + 1)
        if len(data) > spec['bytes']:
            process.kill()
        _, error = process.communicate()
        if process.returncode:
            raise ValueError('pinned Git show failed (fetch the A01 branch first if needed): '
                             + error[:4096].decode('utf-8', errors='replace'))
    if (len(data) != spec['bytes'] or git_blob(data) != spec['git_blob']
            or sha256(data) != spec['sha256']):
        raise ValueError('pinned compressed artifact size/Git blob/SHA256 differs')
    return data, command


def validate_archive(compressed, manifest, spec):
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode='rb') as stream:
        original = stream.read(spec['uncompressed_bytes'] + 1)
        if len(original) != spec['uncompressed_bytes'] or stream.read(1):
            raise ValueError('original tar length differs')
    if sha256(original) != spec['uncompressed_sha256']:
        raise ValueError('original USTAR SHA256 differs')
    expected = {}
    for entry in manifest['files']:
        name = entry['path'].lstrip('/')
        if name in expected:
            raise ValueError('duplicate manifest file')
        expected[name] = entry
    files, observed = {}, []
    with tarfile.open(fileobj=io.BytesIO(original), mode='r:') as archive:
        for member in archive:
            name = member.name
            parts = PurePosixPath(name).parts
            if name.startswith('/') or '..' in parts or not parts:
                raise ValueError('unsafe archive path')
            if member.isdir():
                continue
            if not member.isfile() or name not in expected or name in files:
                raise ValueError('unlisted, duplicate or non-regular tar file')
            entry = expected[name]
            if member.size != entry['bytes'] or member.mode != int(entry['mode'], 8):
                raise ValueError('tar member size/mode differs: ' + name)
            with archive.extractfile(member) as stream:
                payload = stream.read(entry['bytes'] + 1)
            if len(payload) != entry['bytes'] or sha256(payload) != entry['sha256']:
                raise ValueError('tar member SHA256 differs: ' + name)
            files[name] = payload
            observed.append(dict(path='/' + name, bytes=len(payload),
                                 sha256=sha256(payload), mode=entry['mode']))
    if set(files) != set(expected):
        raise ValueError('tar lacks required manifest files')
    elf = {}
    for entry in manifest['elf']:
        name = entry['name']
        if (name in elf or PurePosixPath(name).name != name or name in {'rootfs.tar',
                'verification.json', 'SHA256SUMS', MARKER, '.', '..'}):
            raise ValueError('invalid or duplicate ELF output name')
        payload = files[entry['path'].lstrip('/')]
        if not payload.startswith(b'\x7fELF') or sha256(payload) != entry['sha256']:
            raise ValueError('ELF bytes differ: ' + name)
        elf[name] = payload
    return original, elf, observed


def write_outputs(destination, payloads):
    """Reserve one new directory and write flat files through its pinned FD."""
    destination = Path(os.path.abspath(destination))
    descriptors, parent_links, written = [], [], []
    try:
        parent = os.open(destination.anchor, DIRECTORY)
        descriptors.append(parent)
        for part in destination.parts[1:-1]:
            child = os.open(part, DIRECTORY, dir_fd=parent)
            descriptors.append(child)
            parent_links.append((parent, part, child))
            parent = child
        os.mkdir(destination.name, mode=0o700, dir_fd=parent)
        created = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
        root = os.open(destination.name, DIRECTORY, dir_fd=parent)
        descriptors.append(root)
        parent_links.append((parent, destination.name, root))
        if identity(created)[:2] != identity(os.fstat(root))[:2]:
            raise ValueError('output directory changed during open')
        for name, payload in [(MARKER, b'Incomplete input recovery; do not consume.\n'),
                              *payloads.items()]:
            descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL
                                 | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=root)
            with os.fdopen(descriptor, 'w+b') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
                before = os.fstat(stream.fileno())
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or before.st_size != len(payload)):
                    raise ValueError('output changed during write: ' + name)
                stream.seek(0)
                observed = stream.read(len(payload) + 1)
                info = os.fstat(stream.fileno())
                if identity(before) != identity(info) or observed != payload:
                    raise ValueError('output content changed during FD readback: ' + name)
            written.append((name, identity(info)))
        for link_parent, name, child in parent_links:
            linked = os.stat(name, dir_fd=link_parent, follow_symlinks=False)
            if identity(linked)[:2] != identity(os.fstat(child))[:2]:
                raise ValueError('output ancestor/directory changed before completion')
        for name, expected in written:
            if identity(os.stat(name, dir_fd=root, follow_symlinks=False)) != expected:
                raise ValueError('output file changed before completion: ' + name)
        os.unlink(MARKER, dir_fd=root)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--output', type=Path, required=True,
                        help='new output directory; its parent must already exist')
    arguments = parser.parse_args()
    here = Path(__file__).resolve().parent
    bindings = json.loads(read_metadata(here / 'source-bindings.json'))
    spec, manifest_spec = bindings['artifact'], bindings['manifest']
    metadata = read_metadata(here / manifest_spec['local_file'])
    if (len(metadata) != manifest_spec['bytes'] or git_blob(metadata) != manifest_spec['git_blob']
            or sha256(metadata) != manifest_spec['sha256']):
        raise ValueError('original A04 manifest size/Git blob/SHA256 differs')
    manifest = json.loads(metadata)
    compressed, command = read_git(arguments.repo, spec)
    original, elf, files = validate_archive(compressed, manifest, spec)
    payloads = {'rootfs.tar': original, **elf}
    report = dict(schema=1, kind='exact_original_A04_input_recovery',
                  observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  source_bindings=bindings, git_show_command=command,
                  compressed_bytes=len(compressed), compressed_sha256=sha256(compressed),
                  original_tar_bytes=len(original), original_tar_sha256=sha256(original),
                  manifest_sha256=sha256(metadata), manifest_file_count=len(files),
                  all_manifest_files_exact_match=True, files=files,
                  elf={name:dict(bytes=len(data), sha256=sha256(data), exact_match=True)
                       for name, data in elf.items()},
                  payload_executed=False, new_qemu_execution=False,
                  historical_guest_report=bindings['historical_guest_report'])
    payloads['verification.json'] = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    payloads['SHA256SUMS'] = ''.join(sha256(data) + '  ' + name + '\n'
                                   for name, data in sorted(payloads.items())).encode()
    write_outputs(arguments.output, payloads)
    print(json.dumps(dict(result='exact_input_recovery_pass', output=str(arguments.output),
                         original_tar_sha256=sha256(original), files=len(files), elf=len(elf),
                         new_qemu_execution=False)))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print('input recovery failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
