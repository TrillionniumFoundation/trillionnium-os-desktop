#!/usr/bin/env python3
"""Replay the exact production-foundation source delta without executing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def read_member(root, name, expected):
    relative = PurePosixPath(name)
    need(not relative.is_absolute() and '..' not in relative.parts and str(relative) == name,
         'canonical capsule member required')
    path = root / name
    need(not path.is_symlink() and path.resolve().is_relative_to(root), 'member escaped capsule')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and before.st_size == expected['bytes'] <= 1024 * 1024, 'bounded regular member required')
        data = bytearray()
        while True:
            piece = os.read(fd, 65536)
            if not piece:
                break
            data.extend(piece)
            need(len(data) <= before.st_size, 'member grew')
        after = os.fstat(fd)
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
             'member changed during read')
        need(len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'],
             'member digest differs: ' + name)
        return bytes(data)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'FILES.json').read_bytes())
    need(type(manifest) is dict and manifest, 'exact nonempty inventory required')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    need(actual == set(manifest) | {'FILES.json'}, 'extra or missing capsule members')
    data = {name: read_member(root, name, row) for name, row in manifest.items()}
    origins = json.loads(data['SOURCE-ORIGINS.json'])
    qualification = json.loads(data['QUALIFICATION.json'])
    need(qualification['runtime_qualified'] is False and qualification['production_ready'] is False
         and qualification['Android_starts_in_foundation'] == 0
         and qualification['application_acceptances'] == 0, 'source scope must remain explicit')
    need(len(origins['members']) == 6 and origins['ordinary_source_files'] == 415,
         'exact six-file foundation delta required')
    with tempfile.TemporaryDirectory(prefix='droidloom-foundation-replay-') as temp:
        work = Path(temp)
        for row in origins['members']:
            relative = row['relative']
            need(relative.startswith('runtime/droidloom-supervisor/src/')
                 and PurePosixPath(relative).name in {
                     'lib.rs', 'production_mounts.rs', 'production_runtime_assets.rs',
                     'production_readiness.rs', 'production_runtime_seccomp.rs', 'production_selection.rs'},
                 'fixed foundation source member required')
            destination = work / relative
            if row['preimage'] is not None:
                raw = data['preimages/' + relative]
                need(len(raw) == row['preimage']['bytes']
                     and hashlib.sha256(raw).hexdigest() == row['preimage']['sha256'], 'preimage differs')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
        patch = data['foundation.patch']
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                   GIT_TERMINAL_PROMPT='0')
        for extra in (['--check'], []):
            result = subprocess.run(['git', 'apply', '--whitespace=error', *extra, '-'],
                                    cwd=work, env=env, input=patch, capture_output=True, timeout=10)
            need(result.returncode == 0, 'exact source patch replay failed: ' + result.stderr.decode())
        for row in origins['members']:
            raw = (work / row['relative']).read_bytes()
            need(raw == data['source/' + row['relative']], 'replayed source differs')
            need(len(raw) == row['postimage']['bytes']
                 and hashlib.sha256(raw).hexdigest() == row['postimage']['sha256'], 'postimage differs')
    report = {'schema': 'production-cell-foundation-source-replay-v1',
              'source_members_replayed': 6, 'capsule_members_verified': len(manifest),
              'source_replay_passed': True, 'Rust_tests_executed': 0,
              'private_controls_executed': 0, 'Android_starts': 0,
              'runtime_qualified': False, 'production_ready': False}
    rendered = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
    print(rendered, end='')


if __name__ == '__main__':
    main()
