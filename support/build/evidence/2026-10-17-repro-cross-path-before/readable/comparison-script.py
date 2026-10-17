#!/usr/bin/python3
"""Bind two actual cold distinct-source kernel boots to complete ELF equality."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

base = Path('/workspace/scratch/ae1a8cf05419')
root = base / 'normalized-cloud'
destination = root / 'comparison'
destination.mkdir(mode=0o700, exist_ok=False)
source_commit = 'bdf7a08dcc0980fa85c0ba5abdf365b7d2c42e80'
cases = []
payloads = []

def require(condition, message):
    if not condition:
        raise ValueError(message)

for name in ('A2', 'B2'):
    output = root / name
    policy = json.loads((output / 'policy.json').read_text())
    result = json.loads((output / 'result.json').read_text())
    commands = json.loads((root / ('controller-' + name) / 'commands.json').read_text())
    record = json.loads((output / 'kernel-run/qemu.json').read_text())
    worktree = Path(policy['real_root']).parents[1]
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=worktree, text=True).strip() == source_commit,
            'source commit changed: ' + name)
    require(not subprocess.check_output(['git', 'status', '--porcelain=v1'], cwd=worktree),
            'source worktree is dirty: ' + name)
    require(all(row.get('returncode') == 0 for row in commands), 'incomplete controller: ' + name)
    require(result['returncode'] == 0 and all(result[field] for field in
            ('profile_custody_unchanged', 'source_components_unchanged', 'profile_code_unchanged')),
            'profile run failed: ' + name)
    require(policy['target_absent_at_prelaunch'] is True, 'target was not absent: ' + name)
    require(record['raw_exit_code'] == 33 and record['timed_out'] is False, 'guest did not pass: ' + name)
    check = ['python3', '-I', str(worktree / 'support/build/check-boot.py'),
             str(output / 'kernel-run'), '--live-artifacts']
    with (destination / (name + '-live-recheck.log')).open('xb') as log:
        status = subprocess.run(check, cwd=worktree, stdout=log, stderr=subprocess.STDOUT).returncode
    require(status == 0, 'fresh live artifact recheck failed: ' + name)
    inputs = {}
    loaded = {}
    for option, info in record['artifacts'].items():
        data = Path(info['path']).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        require(len(data) == info['size'] and digest == info['sha256'], 'snapshot changed: ' + name + option)
        inputs[option] = {'path': info['path'], 'size': len(data), 'sha256': digest}
        loaded[option] = data
    kernel = loaded['-kernel']
    # The pinned OSDK deliberately marks its ELF64 x86_64 Multiboot image
    # EM_386 for QEMU compatibility (commands/build/bin.rs: make_compatible).
    require(kernel[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<HH', kernel, 16) == (2, 3),
            'not the pinned OSDK ELF64/EM_386 Multiboot boot image: ' + name)
    require(kernel[:8192].find(struct.pack('<I', 0x1badb002)) >= 0,
            'missing Multiboot v1 header: ' + name)
    rows = [json.loads(line) for line in (output / 'rustc.jsonl').read_text().splitlines()]
    target_rows = [row for row in rows if 'x86_64-unknown-none' in row['effective_argv']]
    flag = '--remap-path-prefix=' + policy['real_root'] + '=' + policy['virtual_root']
    require(target_rows and all(flag in row['effective_argv'] for row in target_rows),
            'freestanding compiler call lacks policy mapping: ' + name)
    require(all([arg for arg in row['incoming_argv'] if arg != flag] ==
                [arg for arg in row['effective_argv'] if arg != flag] for row in rows),
            'original compiler arguments were changed: ' + name)
    core = next(row for row in rows if 'aster_core' in row['effective_argv'])
    actual_source = policy['real_root'] + '/kernel/core/src/lib.rs'
    require(actual_source in core['incoming_argv'], 'core was not compiled from its distinct real root: ' + name)
    serial = (output / 'kernel-run/serial.log').read_bytes()
    cases.append({'case': name, 'source_commit': source_commit, 'real_root': policy['real_root'],
        'virtual_root': policy['virtual_root'], 'actual_core_source_argument': actual_source,
        'actual_host': policy['actual_host'], 'embedded_builder': policy['embedded_builder'],
        'profile_code_sha256': policy['code_sha256'], 'components_sha256': policy['components_sha256'],
        'target_absent_at_prelaunch': True, 'compiler_calls': len(rows), 'target_calls': len(target_rows),
        'all_received_compiler_flags_preserved': True, 'live_recheck': {'argv': check, 'returncode': status},
        'inputs': inputs, 'raw_qemu_exit': 33, 'serial_size': len(serial),
        'serial_sha256': hashlib.sha256(serial).hexdigest()})
    payloads.append(loaded)

require(cases[0]['real_root'] != cases[1]['real_root'], 'source roots were identical')
require(cases[0]['virtual_root'] == cases[1]['virtual_root'], 'virtual input roots differ')
require(cases[0]['profile_code_sha256'] == cases[1]['profile_code_sha256'], 'profile code differs')
require(cases[0]['components_sha256'] == cases[1]['components_sha256'], 'Components inputs differ')
equality = {option: payloads[0][option] == payloads[1][option] for option in ('-kernel', '-initrd', '-bios')}
require(all(equality.values()), 'actual boot input bytes differ')
report = {'schema': 1, 'passed': True, 'cases': cases, 'complete_input_bytes_equal': equality,
    'scope': 'same host, two distinct actual source roots and absent targets, opt-in compiler/component path projection',
    'cross_host_claimed': False, 'immutable_host_claimed': False}
(destination / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': True, 'kernel_sha256': cases[0]['inputs']['-kernel']['sha256'],
    'kernel_size': cases[0]['inputs']['-kernel']['size'], 'actual_inputs_equal': equality,
    'raw_qemu_exits': [33, 33], 'scope': report['scope']}, indent=2))
