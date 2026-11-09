#!/usr/bin/env python3
"""Verify this frozen source/input capsule; this never grants runtime acceptance."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def verify(root):
    root = root.resolve(strict=True)
    manifest = json.loads((root / 'FILES.json').read_bytes())
    require(manifest.get('schema') == 'pocket4-continuation-source-inputs-v1', 'Unexpected manifest schema')
    require(manifest.get('runtime_qualified') is False, 'Source inventory cannot qualify runtime')
    require(manifest.get('production_ready') is False, 'Source inventory cannot qualify production')
    members = manifest.get('files')
    require(type(members) is list and members, 'Nonempty exact inventory required')
    expected = set()
    total = 0
    for entry in members:
        name = entry.get('path')
        require(type(name) is str, 'Member path must be text')
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and all(p not in ('', '.', '..') for p in relative.parts), 'Unsafe member path')
        require(name == relative.as_posix() and name not in expected and name != 'FILES.json', 'Duplicate or noncanonical member')
        expected.add(name)
        path = root.joinpath(*relative.parts)
        for parent in (path, *path.parents):
            if parent == root:
                break
            require(not parent.is_symlink(), 'Symlink member or parent: ' + name)
        require(stat.S_ISREG(path.lstat().st_mode), 'Nonregular member: ' + name)
        raw = path.read_bytes()
        require(type(entry.get('bytes')) is int and len(raw) == entry['bytes'], 'Size differs: ' + name)
        require(hashlib.sha256(raw).hexdigest() == entry.get('sha256'), 'SHA256 differs: ' + name)
        total += len(raw)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    require(actual == expected | {'FILES.json'}, 'Unexpected or absent capsule members')

    native = json.loads((root / 'native/HANDOFF.json').read_bytes())
    require(native['actual_tests'] == {
        'droidloom_source_library': {'failed': 0, 'ignored': 0, 'passed': 26},
        'native_generation_pair_build': {'failed': 0, 'ignored': 0, 'passed': 16},
    }, 'Native executed test counts changed')
    require(native['normal_cli_verify_lock']['projects'] == 600 and native['normal_cli_verify_lock']['returncode'] == 0,
            'Native lock verification absent')
    for key in ('production_ready', 'runtime_qualified', 'shared_aosp_mutated', 'new_aosp_source_materialized_qualified'):
        require(native['limits'][key] is False, 'Native host result cannot grant ' + key)
    audio = json.loads((root / 'audio/test-receipt-rust193.json').read_bytes())
    require(audio['compile_tests']['returncode'] == 0 and audio['tests']['returncode'] == 0, 'Audio actual controls failed')
    marker = 'test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;'
    require(audio['tests']['stdout'].count(marker) == 1, 'All seven Audio controls must have executed')
    broker = json.loads((root / 'broker/qualification.json').read_bytes())
    require(broker['unique_ordinary_passed'] == 184 and broker['ordinary_ignored'] == 24,
            'Integrated supervisor ordinary test counts changed')
    for key in ('production_admission', 'runtime_qualified', 'production_ready'):
        require(broker[key] is False, 'Integrated source controls cannot grant ' + key)
    private = json.loads((root / 'broker/private-userns.json').read_bytes())
    require(private['returncode'] == 0 and private['actual_private_control_passed'] is True,
            'Fixed private syscall control did not pass')
    require(private['protected_equal'] is True and private['terminal_cgroup_retired'] is True,
            'Fixed private control did not preserve or retire its scope')
    require(private['production_admission'] is False and private['android'] == 0,
            'Private control cannot grant production admission or Android acceptance')
    replay = json.loads((root / 'broker/source-replay.json').read_bytes())
    require(replay['replay_passed'] is True and len(replay['files']) == 13,
            'Thirteen-file integrated source replay absent')
    firefox = json.loads((root / 'firefox/delivery.json').read_bytes())['result']
    readback = json.loads((root / 'firefox/independent-readback.json').read_bytes())
    require(firefox['artifact'] == readback['artifact'], 'Firefox delivery/readback identity differs')
    require(readback['full_readback_passed'] is True and readback['bytes_read'] == firefox['artifact']['bytes'],
            'Firefox independent full readback absent')
    require(firefox['installed'] is False and readback['runtime_accepted'] is False,
            'Physical delivery cannot grant application acceptance')
    return {'schema': 'pocket4-continuation-source-verification-v1', 'files': len(expected), 'bytes': total,
            'source_and_receipt_integrity': True, 'runtime_qualified': False, 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).parent)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = verify(args.root)
    rendered = json.dumps(result, sort_keys=True, indent=2) + '\n'
    if args.out:
        args.out.write_text(rendered, encoding='utf-8')
    print(rendered, end='')


if __name__ == '__main__':
    main()
