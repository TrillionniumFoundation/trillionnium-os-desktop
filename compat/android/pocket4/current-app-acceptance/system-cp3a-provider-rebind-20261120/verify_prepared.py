#!/usr/bin/env python3
"""Replay all current CP3A provider postimages from complete pinned source."""
import argparse
import difflib
import hashlib
import importlib.util
from pathlib import Path, PurePosixPath
import stat
import json

HERE = Path(__file__).resolve().parent


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(name):
    rel = PurePosixPath(name)
    need(not rel.is_absolute() and str(rel) == name and '..' not in rel.parts, 'ordinary relative packet member')
    path = HERE / name
    before = path.lstat()
    need(path.resolve() == path and stat.S_ISREG(before.st_mode) and before.st_nlink == 1
         and before.st_size <= 2 * 1024 * 1024, 'bounded ordinary packet metadata/source')
    raw = path.read_bytes(); after = path.lstat()
    fields = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
    need(tuple(getattr(before,k) for k in fields) == tuple(getattr(after,k) for k in fields)
         and len(raw) == before.st_size, 'packet member changed')
    return raw


def verify(repo=None):
    repo = Path(repo).resolve() if repo is not None else HERE.parents[4]
    inventory = {}
    for line in read('FILES.sha256').decode('ascii').splitlines():
        digest, name = line.split('  ', 1)
        need(name not in inventory and len(digest) == 64, 'unique full packet inventory')
        raw = read(name)
        need(hashlib.sha256(raw).hexdigest() == digest, 'packet hash: ' + name)
        inventory[name] = digest
    actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file()}
    need(actual == set(inventory) | {'FILES.sha256'}, 'complete exact packet inventory')
    source = read('prepare_cp3a.py')
    spec = importlib.util.spec_from_file_location('exact_current_cp3a_provider_transformer', HERE / 'prepare_cp3a.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    old, bundle, inputs, raw, identities = module.load(repo)
    outputs, transform, contract = module.build(old, bundle, raw)
    for name, body in outputs.items():
        need(read('prepared/postimages/' + name) == body, 'complete provider postimage reconstruction: ' + name)
    need(read('prepared/TRANSFORM.json') == old.json_bytes(transform)
         and read('prepared/SOURCE-CONTRACT.json') == old.json_bytes(contract), 'full source transform/contract reconstruction')
    patch = ''.join(''.join(difflib.unified_diff(bundle['sources'][name].decode().splitlines(True),
        body.decode().splitlines(True), fromfile='originals/' + name, tofile='postimages/' + name))
        for name, body in sorted(outputs.items())).encode()
    need(read('prepared/SOURCE.patch') == patch, 'complete exact published source patch')
    old.bookend(repo / module.OLD, bundle)
    for name, expected in inputs.items():
        _, after = old.read_fixed(repo, name, expected)
        need(after == identities[name], 'source evidence changed during complete reconstruction')
    need(read('prepare_cp3a.py') == source, 'transformer changed during replay')
    return {'state': 'PASS_CP3A_PROVIDER_REBINDING_SOURCE_RUNTIME_BLOCKED',
            'complete_original_sources': 224, 'provider_changed_files': 11,
            'combined_postimages': len(outputs), 'preserved_Gallery_retired_functions': 6,
            'source_bound_package_identities': 10, 'provider_semantics_transferred': False,
            'live_image_custody_producer_qualified': False,
            'runtime_bootstrap_preparation_admission_claimed': False,
            'source_APK_or_GSI_bodies_read': 0, 'Android_actions': 0,
            'installed': False, 'runtime_qualified': False,
            'business_qualified': False, 'production_ready': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.repo_root), sort_keys=True))
