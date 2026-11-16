#!/usr/bin/env python3
"""Reconstruct the exact public Audio316 source tree without building or fetching."""

from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import stat
import subprocess


BASE_PATCHES = {
    'source-prerequisites/base-source.patch': (3814733, '40ad41624358deb27ce67ea61d557e5ae5f672c19e2b0e805679caa71cf0c2aa'),
    'source-prerequisites/audio-prerequisite.patch': (463169, 'af0e4e87db09b39407fb6689cff451fe7dbe3a6a91f3661148f38c76e1fe10d0'),
    'integrated-builder/audio-final.patch': (231428, '376e574d1a463a3d7548f73cd3aeb0db08afd4ebecf8b9b051ea06f5ec045d70'),
}
NEW_PATCHES = ['audio-actual309.patch', 'audio-api35-cts-original-providers.patch']


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read(path, expected=None):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'input must be a regular unlinked file: '+str(path))
    data = path.read_bytes()
    after = path.lstat()
    identity_fields = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink',
                       'st_size', 'st_mtime_ns', 'st_ctime_ns')
    require(all(getattr(before, name) == getattr(after, name) for name in identity_fields),
            'input changed during read: '+str(path))
    value = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    if expected is not None:
        require(value == {key: expected[key] for key in ('bytes', 'sha256')}, 'input checksum differs: '+str(path))
    return data


def run(repo, *args):
    env = {name: value for name, value in os.environ.items() if not name.startswith('GIT_')}
    env.update({'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                'GIT_CONFIG_SYSTEM': os.devnull, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0',
                'GIT_NO_LAZY_FETCH': '1'})
    result = subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.filemode=true', *args],
                            cwd=repo, env=env, capture_output=True, timeout=120)
    require(result.returncode == 0, 'git '+repr(args)+' failed: '+result.stderr.decode(errors='replace')[-4000:])
    return result.stdout


def verify(repo, expected, tree):
    actual = {}
    for record in run(repo, 'ls-files', '--stage', '-z').split(b'\0'):
        if not record:
            continue
        metadata, relative = record.split(b'\t', 1)
        mode, _, stage = metadata.decode().split()
        name = relative.decode()
        pure = PurePosixPath(name)
        require(stage == '0' and mode in ('100644', '100755') and not pure.is_absolute()
                and '..' not in pure.parts and '.git' not in pure.parts, 'unexpected index entry')
        path = repo/name
        data = read(path)
        require(bool(path.lstat().st_mode & 0o111) == (mode == '100755'), 'executable mode differs: '+name)
        actual[name] = {'git_mode': mode, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    require(actual == expected, 'reconstructed file bytes, modes, or file set differ')
    require(run(repo, 'write-tree').decode().strip() == tree, 'reconstructed Git tree differs')
    run(repo, 'diff', '--exit-code')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', type=Path, required=True,
                        help='existing build-source-repair-20261108 directory containing the three base patches')
    parser.add_argument('--output', type=Path, required=True,
                        help='new source directory; an existing path is rejected')
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    package_root = args.package_root.resolve(strict=True)
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), 'output already exists; no existing checkout will be changed')
    chain = json.loads(read(package/'source-chain.json'))
    require(chain['schema'] == 'audio316-public-source-chain-v1', 'unsupported source chain')
    require(chain['application_order'] == list(BASE_PATCHES)+['audio-api35-cts316/'+name for name in NEW_PATCHES],
            'source application order differs')
    require([row['file'] for row in chain['new_patches']] == NEW_PATCHES, 'new patch order differs')
    patches = []
    for relative, (size, sha) in BASE_PATCHES.items():
        path = package_root/relative
        read(path, {'bytes': size, 'sha256': sha})
        patches.append(path)
    for reference in chain['new_patches']:
        path = package/reference['file']
        read(path, reference)
        patches.append(path)
    base_manifest = chain['existing_base']['published_inventory']
    require(base_manifest['path'] == 'audio-final-source-files.json', 'unexpected base inventory')
    base = json.loads(read(package_root/'integrated-builder'/base_manifest['path'], base_manifest))
    actual309 = json.loads(read(package/chain['actual309_inventory']['file'], chain['actual309_inventory']))
    compiled = json.loads(read(package/chain['compiled_inventory']['file'], chain['compiled_inventory']))
    require(len(base) == 409 and len(actual309) == 411 and len(compiled) == 431, 'source inventory counts differ')
    output.mkdir()
    run(output, 'init', '-q')
    for index, patch in enumerate(patches):
        run(output, 'apply', '--index', '--whitespace=nowarn', str(patch))
        if index == 2:
            verify(output, base, chain['existing_base']['source_tree'])
        elif index == 3:
            verify(output, actual309, chain['actual309_source_tree'])
        elif index == 4:
            verify(output, compiled, chain['result_source_tree'])
    print(json.dumps({'state': 'EXACT_AUDIO316_PUBLIC_SOURCE_RECONSTRUCTED', 'files': len(compiled),
                      'source_tree': chain['result_source_tree'], 'patches_applied': len(patches),
                      'Cargo_invocations': 0, 'AOSP_source_commands': 0, 'network_requests': 0}))


if __name__ == '__main__':
    main()
