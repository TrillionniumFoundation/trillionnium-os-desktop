#!/usr/bin/env python3
"""Independent evidence-only A04 audit. No imports or execution of producers.

The only child processes are read-only `git show` calls with an explicit
immutable source commit. All other work is local byte/hash/JSON/ELF/newc parsing.
Writes are restricted to this independent review directory.
"""
import ast
import base64
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess

BASE = Path('/workspace/scratch/499c7902de8e')
PRODUCT = BASE / 'r12-g1c'
E = BASE / 'r12-evidence'
OUT = E / 'g1c-review'
HEAD = '104204016dcdea57ab73c091b1edd13008ae9a19'
TREE = '179b076747d19c3e07ee19a665e3968c33c598ce'
KERNEL = '1bdc27f45afb2789447473cdf100a8fd67c84111bcec650a1fa96c18edb6163b'
INPUT = '96aa95ba2105fc9092c860f301d78454b2cb92db6e8124858c109bb83b25f20a'
BIOS = '1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735'
ORIGINAL = '86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3'
QEMU = '8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854'
SCM = 'a6f1f96753a9892df31fe2ce6a7f634bd10da2f6632b373a80f52a80e5fcddbd'
NOFILE = '80578a08abf6464dc10f2af3a1a793bbf46988981499934c9cfcbc58a590cae8'
EMPTY = hashlib.sha256(b'').hexdigest()
SCM_RUNNER = 'tests/workloads/linux/run_scm_rights_cloexec_guest.py'
NOFILE_RUNNER = 'tests/workloads/linux/run_rlimit_nofile_guest.py'
FULL_RUNNER = 'tests/workloads/linux/run_full_ubuntu_profile.py'
PROFILE = 'compat/linux/profiles/ubuntu24.04-x86_64-20261019.json'
FILES = {}
SOURCES = {}


def must(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    path = Path(path)
    must(path.is_file() and not path.is_symlink(), 'not a regular input: ' + str(path))
    data = path.read_bytes()
    FILES[str(path)] = {'bytes': len(data), 'sha256': sha(data)}
    return data


def digest(path):
    return sha(read(path))


def strict(data):
    def pairs(items):
        result = {}
        for key, value in items:
            must(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON: ' + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def js(path):
    return strict(read(path))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def src(path):
    if path not in SOURCES:
        data = subprocess.check_output(['git', '-C', str(PRODUCT), 'show', HEAD + ':' + path],
                                       stderr=subprocess.PIPE, timeout=30)
        SOURCES[path] = data
    return SOURCES[path]


def literal(path, name):
    for node in ast.parse(src(path).decode()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name
                                               for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('missing literal: ' + path + ' ' + name)


def source_hashes():
    return {k: {'bytes': len(v), 'sha256': sha(v)} for k, v in sorted(SOURCES.items())}


def identity(value):
    must(value['source_head'] == HEAD and value['source_tree'] == TREE, 'source identity differs')


def pinned(path, expected):
    data = read(path)
    must(sha(data) == expected, 'SHA differs: ' + str(path))
    return data


def clean_lines(raw):
    return re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)',
                  '', raw.decode('utf-8', errors='strict')).splitlines()


def elf(data):
    must(data[:6] == b'\x7fELF\x02\x01', 'ELF64 little endian required')
    kind, machine = struct.unpack_from('<HH', data, 16)
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    must(size == 56 and count > 0 and offset + size * count <= len(data), 'bad ELF program headers')
    interp, needed = [], []
    for i in range(count):
        p_type, flags, p_offset, vaddr, paddr, filesz, memsz, align = struct.unpack_from(
            '<IIQQQQQQ', data, offset + size * i)
        must(p_offset + filesz <= len(data), 'ELF segment exceeds input')
        if p_type == 3:
            raw = data[p_offset:p_offset + filesz]
            must(raw.endswith(b'\0') and b'\0' not in raw[:-1], 'bad PT_INTERP')
            interp.append(raw[:-1].decode('ascii'))
        if p_type == 2:
            # Resolve DT_STRTAB through an actual PT_LOAD, without readelf execution.
            dynamic = []
            for pos in range(p_offset, p_offset + filesz, 16):
                tag, val = struct.unpack_from('<QQ', data, pos)
                if tag == 0:
                    break
                dynamic.append((tag, val))
            tables = [v for t, v in dynamic if t == 5]
            if tables:
                must(len(tables) == 1, 'duplicate ELF string table')
                st = tables[0]
                bases = []
                for j in range(count):
                    t, _, po, va, _, fs, _, _ = struct.unpack_from('<IIQQQQQQ', data, offset + size*j)
                    if t == 1 and va <= st < va + fs:
                        bases.append(po + st - va)
                must(len(bases) == 1, 'cannot resolve DT_STRTAB')
                for t, v in dynamic:
                    if t == 1:
                        start = bases[0] + v
                        end = data.index(b'\0', start)
                        needed.append(data[start:end].decode('ascii'))
    must(len(interp) <= 1, 'duplicate PT_INTERP')
    return {'elf_class': 64, 'elf_type': kind, 'machine': machine,
            'interpreter': interp[0] if interp else None, 'needed': needed}


def newc(compressed):
    raw = gzip.decompress(compressed)
    must(len(raw) <= 256 * 1024 * 1024, 'image over bound')
    pos, entries = 0, []
    while True:
        must(raw[pos:pos+6] == b'070701' and pos + 110 <= len(raw), 'bad newc header')
        fields = [int(raw[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
        pos += 110
        size = fields[11]
        must(size >= 1 and raw[pos+size-1:pos+size] == b'\0', 'bad newc name')
        name = raw[pos:pos+size-1].decode('utf-8')
        must(name and '\0' not in name and not name.startswith('/')
             and '..' not in PurePosixPath(name).parts, 'unsafe newc path')
        pos = (pos + size + 3) & ~3
        data = raw[pos:pos+fields[6]]
        must(len(data) == fields[6], 'truncated newc body')
        pos = (pos + fields[6] + 3) & ~3
        if name == 'TRAILER!!!':
            must(data == b'' and not any(raw[pos:]), 'trailing newc payload')
            break
        entries.append((name, fields, data))
    must(len({n for n, _, _ in entries}) == len(entries), 'duplicate newc path')
    return entries


def compare_injection(original_entries, derived_entries, injected, added_files):
    before = {n: (f, d) for n, f, d in original_entries}
    after = {n: (f, d) for n, f, d in derived_entries}
    must(set(before) <= set(after), 'original image paths missing')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    for name, (fields, data) in before.items():
        actual_fields, actual = after[name]
        if name == 'init':
            must(data.count(marker) == 1, 'original init marker count')
            data = data.replace(marker, injected + marker)
            fields = fields.copy()
            fields[6] = len(data)
        must(actual_fields == fields and actual == data, 'original image entry altered: ' + name)
    directories = set()
    for name in added_files:
        for parent in PurePosixPath(name).parents:
            if str(parent) != '.':
                directories.add(str(parent))
    expected_added = set(added_files) | (directories - set(before))
    must(set(after) - set(before) == expected_added, 'unexpected derived image additions')
    for name, (mode, data) in added_files.items():
        fields, actual = after[name]
        must(fields[1] == stat.S_IFREG | mode and actual == data, 'injected file differs: ' + name)
    for name in directories - set(before):
        fields, data = after[name]
        must(fields[1] == stat.S_IFDIR | 0o755 and data == b'', 'added directory differs')
    return {'original_entry_count': len(before), 'derived_entry_count': len(after),
            'original_entries_preserved_except_exact_init_injection': True,
            'added_regular_files': len(added_files), 'added_directories': len(directories - set(before)),
            'no_unexpected_paths': True}


def common_guest(name, initrd_name):
    p = E / name
    r = js(p / 'result.json')
    identity(r)
    must(r['passed'] is True and r['qemu_exit'] == 33 and r['timed_out'] is False,
         'guest runner failure: ' + name)
    must(r['kernel_sha256'] == KERNEL and r['product_receipt_sha256'] == PRODUCT_SHA,
         'wrong product binding: ' + name)
    kernel = pinned(p / 'kernel.elf', KERNEL)
    must(kernel == PRODUCT_ELF, 'not same ordinary ELF')
    pinned(p / 'bios.bin', BIOS)
    must(r.get('bios_sha256', BIOS) == BIOS, 'BIOS metadata differs')
    must(r.get('qemu_sha256', r.get('qemu_launcher_sha256')) == QEMU, 'QEMU metadata differs')
    argv = ['/usr/bin/qemu-system-x86_64', '-kernel', str(p / 'kernel.elf'), '-initrd', str(p / initrd_name),
            '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
            '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(p / 'bios.bin'),
            '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot',
            '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
            '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    must(r['qemu_argv'] == argv, 'QEMU invocation differs: ' + name)
    raw = pinned(p / 'serial.log', r['serial_sha256'])
    must(len(raw) == r['serial_bytes'], 'serial length differs')
    lines = clean_lines(raw)
    must(not re.search(r'kernel panic|panicked at|fatal exception|uncaught panic', '\n'.join(lines), re.I),
         'panic in guest serial')
    return p, r, lines


def evidence_meta(prefixes):
    return {str(Path(k).relative_to(E)): v for k, v in sorted(FILES.items())
            if str(k).startswith(str(E) + '/') and any(str(Path(k).relative_to(E)).startswith(p)
                                                    for p in prefixes)}


def review_simple(kind):
    scm = kind == 'scm'
    prefix = 'SCM_CLOEXEC' if scm else 'NOFILE'
    runner = SCM_RUNNER if scm else NOFILE_RUNNER
    count = 27 if scm else 37
    order = ([socket + '.' + case for socket in ('stream', 'datagram', 'seqpacket')
              for case in literal(SCM_RUNNER, 'SCENARIOS')] if scm else list(literal(runner, 'CASE_ORDER')))
    must(len(order) == len(set(order)) == count, 'case denominator')
    probe_sha = SCM if scm else NOFILE
    build = E / ('local-scm-linux' if scm else 'local-nofile-build')
    reference = E / ('local-scm-linux-escalated' if scm else 'local-nofile-linux-escalated')
    prior = E / ('local-scm-linux' if scm else 'local-nofile-linux')
    probe = pinned(build / 'probe.elf', probe_sha)
    probe_header = elf(probe)
    must(probe_header['machine'] == 62 and probe_header['interpreter'] is None,
         'probe is not static x86_64')
    for directory in (build, reference, prior):
        must(pinned(directory / 'probe.elf', probe_sha) == probe, 'different retained ELF')
        recorded_probe_path = str(directory / 'probe.elf') if scm or directory == build else 'probe.elf'
        must(read(directory / 'probe.sha256') == (probe_sha + '  ' + recorded_probe_path + '\n').encode(),
             'preexecution ELF SHA record differs')
    source_c = 'tests/workloads/linux/' + ('scm_rights_cloexec_probe.c' if scm else 'rlimit_nofile_probe.c')
    build_input = read(build / 'inputs.sha256').decode().splitlines()
    must(build_input == [sha(src(source_c)) + '  ' + source_c,
                        probe_sha + '  ' + str(build / 'probe.elf')], 'build source/ELF binding differs')
    for f in ('compile.log', 'compiler-version.txt', 'linux-version.txt',
              'runner-tests.log', 'runner-tests-optimized.log'):
        read(build / f)
    stdout, stderr = read(reference / 'stdout.log'), read(reference / 'stderr.log')
    expected_lines = [f'{prefix}_CASE name={name} result=PASS line=0' for name in order]
    summary = f'{prefix}_COMPLETE total={count} passed={count} failed=0'
    must(stdout == ('\n'.join(expected_lines + [summary]) + '\n').encode(),
         'Linux stdout is not exact original contract')
    must(stderr == b'' and read(reference / 'exit-code.txt') == b'0\n', 'Linux exit or stderr differs')
    p, guest, lines = common_guest('local-' + kind + '-guest', 'initramfs.cpio.gz')
    must(pinned(p / 'probe.elf', probe_sha) == probe and guest['probe_sha256'] == probe_sha,
         'guest probe not same Linux/build ELF')
    must(guest['runner_sha256'] == sha(src(runner)), 'guest runner SHA differs')
    must(guest['cpio_helper_sha256'] == sha(src('tests/organ_backend/run_guest_probe.py')),
         'cpio helper SHA differs')
    observed = [line for line in lines if line.startswith(prefix + '_CASE')]
    must(observed == expected_lines, 'guest original cases differ or out of order')
    must([line for line in lines if line.startswith(prefix + '_COMPLETE')] == [summary],
         'guest summary count differs')
    exit_marker = prefix + '_PROCESS_EXIT=0'
    must([line for line in lines if line.startswith(prefix + '_PROCESS_EXIT=')] == [exit_marker],
         'guest actual probe exit differs')
    must(lines.count('TRILLIONNIUM_A01_BOOT_OK') == 1, 'boot marker count')
    must(max(lines.index(line) for line in expected_lines) < lines.index(summary)
         < lines.index(exit_marker) < lines.index('TRILLIONNIUM_A01_BOOT_OK'), 'guest completion order')
    must(not any(line.startswith((prefix + '_ASSERT', prefix + '_SETUP')) for line in lines),
         'guest assertion/setup failure')
    cases = [{'name': n, 'result': 'PASS', 'line': 0} for n in order]
    must(guest['cases'] == cases, 'guest parsed receipt differs from raw')
    must(guest['guest_inputs_unchanged'] is True, 'guest inputs not frozen')
    guest_lines_sha = sha(('\n'.join(observed + [summary]) + '\n').encode())
    must(guest_lines_sha == sha(stdout), 'guest case output differs from Linux bytes')
    initrd = pinned(p / 'initramfs.cpio.gz', guest['initramfs_sha256'])
    must(guest['original_initramfs_sha256'] == ORIGINAL, 'wrong original initrd')
    program = 'scm-rights-cloexec-probe' if scm else 'rlimit-nofile-probe'
    status_var = 'scm_probe_exit' if scm else 'nofile_probe_exit'
    injected = (f'if /bin/{program}; then\n    {status_var}=0\nelse\n    {status_var}=$?\nfi\n'
                f'echo "{prefix}_PROCESS_EXIT=${status_var}"\n').encode()
    injection = compare_injection(ORIGINAL_ENTRIES, newc(initrd), injected,
                                  {'bin/' + program: (0o755, probe)})
    prior_out, prior_err = read(prior / 'stdout.log'), read(prior / 'stderr.log')
    prior_lines = prior_out.decode().splitlines()
    pattern = re.compile(prefix + r'_CASE name=(\S+) result=(PASS|FAIL) line=(\d+)')
    parsed_prior = [pattern.fullmatch(line) for line in prior_lines if line.startswith(prefix + '_CASE')]
    must(len(parsed_prior) == count and all(parsed_prior), 'earlier failed original cases missing')
    must([m[1] for m in parsed_prior] == order, 'earlier failed case order differs')
    failed = [{'name': m[1], 'line': int(m[3])} for m in parsed_prior if m[2] == 'FAIL']
    must(len(failed) == (3 if scm else 5) and read(prior / 'exit-code.txt') == b'1\n',
         'earlier failure no longer preserved')
    expected_fail_names = ([socket + '.credentials_with_rights' for socket in ('stream', 'datagram', 'seqpacket')]
                          if scm else ['accept_preserves_queue', 'accept_copyout_fault',
                                       'reserved_dup2_collision', 'fork_ignores_reservation',
                                       'cloexec_marks_reservation'])
    must([x['name'] for x in failed] == expected_fail_names, 'earlier failure names differ')
    must(all(x['line'] == (294 if scm else 212) for x in failed), 'earlier failure line differs')
    must(prior_err.decode().count('errno=1') == len(failed), 'earlier EPERM stderr differs')
    must(prior_lines[-1] == f'{prefix}_COMPLETE total={count} passed={count-len(failed)} failed={len(failed)}',
         'earlier summary differs')
    if scm:
        ref = js(reference / 'reference-attempt.json')
        must(ref['passed'] is True and ref['exit_code'] == 0 and ref['probe_sha256'] == probe_sha
             and ref['stdout_sha256'] == sha(stdout) and ref['stderr_sha256'] == sha(stderr),
             'SCM reference attempt differs')
        must(ref['command'] == [str(reference / 'probe.elf')], 'SCM command differs')
        attempt = js(E / 'local-host/scm-guest-attempt.json')
        must(attempt['exit_code'] == 0 and digest(E / 'local-host/scm-guest.log') == attempt['log_sha256'],
             'SCM guest actual attempt differs')
        command = attempt['command']
        must(command[command.index('--probe-elf') + 1] == str(build / 'probe.elf')
             and command[command.index('--expected-probe-sha256')+1] == SCM,
             'SCM runner did not receive frozen ELF')
        binding = 'Original SCM CLI pins ELF SHA; this independent review separately joins the successful Linux stdout/exit by the same ELF bytes. SCM guest JSON has no Linux-receipt SHA field.'
    else:
        ref = js(reference / 'result.json')
        earlier_ref = js(prior / 'result.json')
        frozen = js(reference / 'input.json')
        must(ref['passed'] is True and ref['process_exit'] == 0 and ref['timed_out'] is False
             and ref['cases'] == cases and ref['stdout_sha256'] == sha(stdout)
             and ref['stderr_sha256'] == sha(stderr), 'NOFILE Linux receipt differs from raw')
        must(frozen['passed'] is False and frozen['command'] == [str(reference / 'probe.elf')]
             and frozen['probe_sha256'] == probe_sha
             and digest(reference / 'input.json') == ref['frozen_input_sha256'], 'NOFILE frozen input differs')
        must(guest['linux_reference_receipt_sha256'] == digest(reference / 'result.json'),
             'NOFILE guest reference receipt link differs')
        must(earlier_ref['passed'] is False and earlier_ref['process_exit'] == 1
             and earlier_ref['stdout_sha256'] == sha(prior_out)
             and earlier_ref['stderr_sha256'] == sha(prior_err), 'NOFILE earlier failed receipt differs')
        for item in (ref, guest, frozen, earlier_ref):
            for field, path in [('runner_sha256', NOFILE_RUNNER), ('product_helper_sha256', SCM_RUNNER),
                                ('cpio_helper_sha256', 'tests/organ_backend/run_guest_probe.py'),
                                ('process_group_helper_sha256', 'tests/integration/hepta/run_original_agentd.py')]:
                must(item[field] == sha(src(path)), 'NOFILE source helper differs')
        for key in ('runner_inputs_unchanged', 'probe_inputs_unchanged', 'process_group_cleanup_completed'):
            must(ref[key] is True, 'NOFILE reference final boundary incomplete')
        must(guest['runner_inputs_unchanged'] is True, 'NOFILE guest helper changed')
        attempt = next(p for p in A04_ATTEMPT['phases'] if p['name'] == 'nofile-guest')
        must(attempt['exit_code'] == 0 and digest(E / 'local-host/nofile-guest.log') == attempt['log_sha256'],
             'NOFILE guest actual attempt differs')
        binding = 'Original NOFILE CLI validates the pre-execution ELF SHA, complete Linux raw result, and Linux-receipt SHA before and after guest.'
    command = attempt['command']
    must(command[command.index('--expected-source-head') + 1] == HEAD
         and command[command.index('--expected-source-tree') + 1] == TREE
         and command[command.index('--product-evidence')+1] == str(E / 'local-ordinary-candidate-final'),
         'wrong original guest CLI source/product')
    return {'schema': 'g1c.independent.a04-' + kind + '-review.v1', 'source_head': HEAD,
            'source_tree': TREE, 'passed': True, 'count': count, 'case_order': order,
            'linux_passed': count, 'guest_passed': count, 'linux_stderr_bytes': 0,
            'linux_process_exit': 0, 'guest_probe_exit': 0, 'qemu_exit': 33,
            'kernel_sha256': KERNEL, 'probe_sha256': probe_sha, 'probe_bytes': len(probe),
            'probe_elf_headers': probe_header,
            'same_probe_bytes_build_original_linux_permitted_linux_guest': True,
            'linux_stdout_sha256': sha(stdout), 'guest_case_stdout_sha256': guest_lines_sha,
            'guest_stdout_contract_exactly_matches_linux': True,
            'guest_serial_sha256': guest['serial_sha256'], 'initramfs': injection,
            'reference_binding_scope': binding,
            'earlier_default_environment_failure': {'retained': True, 'passed': False,
                'process_exit': 1, 'cases_passed': count-len(failed), 'failed_cases': failed,
                'raw_stderr_errno': 1, 'same_elf': True,
                'attribution_scope': 'Raw logs prove EPERM; authorization/environment distinction is from the recorded attempt and parent operator account. No product fix inferred.'},
            'attempt': {k: attempt[k] for k in ('started_at', 'finished_at', 'seconds', 'exit_code', 'log_sha256')},
            'qualification': 'Original local supplementary one-vCPU TCG profile only; no pinned Debian13, hosted CI, G1-d, or device qualification.'}


def full_script_from_contract(contract, environment):
    lines = ['#!/bin/sh', 'set -eu', 'umask 077', 'full_failed=0', '/bin/busybox mkdir -p /tmp/a04']
    lines += ['export ' + key + '=' + value for key, value in environment.items()]
    lines += ['unset LD_PRELOAD LD_LIBRARY_PATH PYTHONPATH PYTHONHOME PYTHONSTARTUP']
    for case in contract['cases']:
        name = case['id']
        scratch = '/tmp/a04/' + name
        lines += ['/bin/busybox mkdir -p ' + scratch, 'export HOME=' + scratch,
                  'echo A04_FULL_BEGIN=' + name,
                  'if /bin/busybox timeout -s KILL 45 ' + ' '.join(case['argv'])
                  + ' >' + scratch + '/stdout.log 2>' + scratch + '/stderr.log; then',
                  '    case_exit=0', 'else', '    case_exit=$?',
                  '    full_failed=$((full_failed + 1))', 'fi']
        for channel in ('stdout', 'stderr'):
            path = scratch + '/' + channel + '.log'
            lines += ['/bin/busybox base64 ' + path + ' | while IFS= read -r chunk; do',
                      '    echo A04_FULL_' + channel.upper() + '=' + name + ':$chunk', 'done',
                      channel + '_bytes=$(/bin/busybox wc -c <' + path + ')',
                      'set -- $(/bin/busybox sha256sum ' + path + ')', channel + '_sha=$1']
        lines += ['echo A04_FULL_END=' + name + ':$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha']
    lines += ['echo A04_FULL_COMPLETE=32:$full_failed', 'test "$full_failed" -eq 0']
    return ('\n'.join(lines) + '\n').encode()


def decode_full_guest(lines, order):
    frames = [(i, line) for i, line in enumerate(lines) if line.startswith('A04_FULL_')]
    cursor, outputs = 0, []
    for name in order:
        must(frames[cursor][1] == 'A04_FULL_BEGIN=' + name, 'full begin sequence differs')
        begin = frames[cursor][0]
        cursor += 1
        channels = {'STDOUT': [], 'STDERR': []}
        while cursor < len(frames) and re.match('A04_FULL_(STDOUT|STDERR)=', frames[cursor][1]):
            match = re.fullmatch(r'A04_FULL_(STDOUT|STDERR)=([a-z0-9_.]+):([A-Za-z0-9+/=]+)', frames[cursor][1])
            must(match is not None and match[2] == name, 'full byte frame name/shape differs')
            channels[match[1]].append(match[3])
            cursor += 1
        stdout = base64.b64decode(''.join(channels['STDOUT']), validate=True)
        stderr = base64.b64decode(''.join(channels['STDERR']), validate=True)
        must(max(len(stdout), len(stderr)) <= 1024 * 1024, 'application output over bound')
        end = re.fullmatch(r'A04_FULL_END=([a-z0-9_.]+):(\d+):(\d+):([a-f0-9]{64}):(\d+):([a-f0-9]{64})',
                           frames[cursor][1])
        must(end is not None and end[1] == name and int(end[2]) == 0, 'full application end/exit differs')
        must(int(end[3]) == len(stdout) and end[4] == sha(stdout)
             and int(end[5]) == len(stderr) and end[6] == sha(stderr), 'full frame length/hash differs')
        outputs.append({'name': name, 'stdout': stdout, 'stderr': stderr,
                        'begin_line': begin + 1, 'end_line': frames[cursor][0] + 1})
        cursor += 1
    must([line for _, line in frames[cursor:]] == ['A04_FULL_COMPLETE=32:0', 'A04_FULL_PROCESS_EXIT=0'],
         'full completion/exit not exact once or unknown frame')
    boots = [i for i, line in enumerate(lines) if line == 'TRILLIONNIUM_A01_BOOT_OK']
    must(len(boots) == 1 and frames[-2][0] < frames[-1][0] < boots[0], 'full completion boot order')
    return outputs


def review_full():
    b, reference = E / 'local-full-bundle', E / 'local-full-linux'
    frozen = js(E / 'local-full-checks/frozen-input.json')
    must(frozen['input_sha256'] == INPUT and frozen['source'] == str(b / 'inputs.sha256'), 'frozen digest provenance differs')
    inputs = strict(pinned(b / 'inputs.json', INPUT))
    identity(inputs)
    must(read(b / 'inputs.sha256') == (INPUT + '  inputs.json\n').encode(), 'sole preworkload digest differs')
    must(inputs['workload_execution_performed'] is False and inputs['case_count'] == 32, 'build was not a freeze-only stage')
    contract = strict(pinned(b / 'contract.json', inputs['contract_sha256']))
    must(read(b / 'contract.json') == src(PROFILE), 'contract differs from git104')
    order = list(literal(FULL_RUNNER, 'CASE_ORDER'))
    must(order == [case['id'] for case in contract['cases']] and len(order) == len(set(order)) == 32,
         'original full32 denominator/order differs')
    classes = Counter(case['class'] for case in contract['cases'])
    must(classes == {'elf': 28, 'python': 3, 'rust': 1}, 'full32 class denominator differs')
    must(contract['case_timeout_seconds'] == 45 and contract['python'] == '/usr/bin/python3.12', 'profile runtime differs')
    must(contract['legacy_catalog_sha256'] == sha(src('tests/workloads/linux/workload_catalog.json')),
         'legacy catalog binding differs')
    manifest = strict(pinned(b / 'runtime-manifest.json', inputs['runtime_manifest_sha256']))
    original = pinned(b / 'original-initramfs.cpio.gz', ORIGINAL)
    must(original == ORIGINAL_BYTES, 'full image original differs')
    image = pinned(b / 'full-initramfs.cpio.gz', inputs['image_sha256'])
    entries = newc(image)
    by_name = {n: (f, data) for n, f, data in entries}
    files = {}
    rows = manifest['files']
    must(len(rows) == len({r['path'] for r in rows}) == manifest['file_count'] == 669, 'runtime file denominator differs')
    must(sum(r['bytes'] for r in rows) == manifest['regular_bytes'] == 43092079, 'runtime byte denominator differs')
    runtime_count = 0
    for row in rows:
        path, mode = row['path'].lstrip('/'), row['mode']
        must(mode in (0o444, 0o555), 'mutable runtime mode')
        fields, data = by_name[path]
        must(fields[1] == stat.S_IFREG | mode and len(data) == row['bytes'] and sha(data) == row['sha256'],
             'runtime image manifest differs: ' + path)
        actual = b / 'runtime' / path
        must(pinned(actual, row['sha256']) == data and stat.S_IMODE(actual.stat().st_mode) == mode,
             'retained runtime tree differs: ' + path)
        files[path] = (mode, data)
        runtime_count += 1
    env = literal(FULL_RUNNER, 'ENVIRONMENT')
    script = pinned(b / 'full_guest.sh', inputs['guest_script_sha256'])
    must(script == full_script_from_contract(contract, env), 'guest script differs from fixed source/contract')
    files['usr/local/lib/a04/full_guest.sh'] = (0o444, script)
    injection = compare_injection(ORIGINAL_ENTRIES, entries,
        b'if /bin/busybox sh /usr/local/lib/a04/full_guest.sh; then\n    full_profile_exit=0\nelse\n    full_profile_exit=$?\nfi\necho "A04_FULL_PROCESS_EXIT=$full_profile_exit"\n', files)
    workload_elf = {}
    for name, info in inputs['probe_elf'].items():
        path = '/usr/local/bin/a04/' + name
        data = pinned(b / 'workload-elf' / name, info['sha256'])
        must(len(data) == info['bytes'] and data == by_name[path.lstrip('/')][1], 'workload retained ELF differs from image')
        h = elf(data)
        must(h['machine'] == 62, 'workload ELF not x86_64')
        meta = manifest['elf'][path]
        must(h['interpreter'] == meta['interpreter'] and sorted(h['needed']) == sorted(meta['needed']),
             'ELF dynamic metadata differs: ' + name)
        if name in ('probe_static', 'sqlite_static'):
            must(h['interpreter'] is None and h['needed'] == [], 'static ELF requires loader')
        else:
            must(h['interpreter'] == '/lib64/ld-linux-x86-64.so.2' and 'libc.so.6' in h['needed'], 'dynamic ELF loader/libc missing')
        if name == 'sqlite_dynamic':
            must('libsqlite3.so.0' in h['needed'], 'SQLite dynamic linkage differs')
        workload_elf[name] = {**info, **h}
    must(set(workload_elf) == {'probe_dynamic', 'probe_static', 'sqlite_dynamic', 'sqlite_static', 'a04-tokio-workload'}, 'five ELF denominator differs')
    sources = {path: sha(src(path)) for path in literal(FULL_RUNNER, 'SOURCE_PATHS')}
    must(inputs['sources'] == sources, 'frozen full source differs from git104')
    # Read tool bytes; do not invoke a tool or compiler during review.
    for name, tool in inputs['tools'].items():
        data = pinned(Path(tool['resolved_path']), tool['sha256'])
        must(len(data) == tool['bytes'], 'tool bytes differ: ' + name)
    must(inputs['tools']['qemu']['sha256'] == QEMU, 'QEMU not frozen before Linux')
    build_report = js(b / 'result.json')
    build_input = js(b / 'build-input.json')
    for record in (build_report, build_input):
        identity(record)
        must(record['source_files'] == sources and record['tools'] == inputs['tools']
             and record['packages'] == inputs['packages'], 'full build metadata differs')
    must(build_report['passed'] is True and build_report['input_sha256'] == INPUT
         and build_report['image_sha256'] == inputs['image_sha256']
         and build_report['build_bundle_verified'] is True
         and build_report['commands'] == inputs['commands'] and build_input['commands'] == [], 'build completion differs')
    commands = inputs['commands']
    must(len(commands) == 6 and commands[-1]['argv'][1:7] == ['+nightly-2026-07-21', 'build', '--offline', '--locked', '--release', '--target'],
         'original locked Tokio build flags differ')
    build_logs = {}
    for command in commands:
        log = read(b / command['log'])
        build_logs[command['log']] = {'bytes': len(log), 'sha256': sha(log)}
    rust_version = read(b / 'build/rustc-version.log').decode()
    must('rustc 1.99.0-nightly (87e5904f5 2026-07-20)' in rust_version
         and 'commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48' in rust_version,
         'actual pinned rustc version log differs')
    stage_receipts = {}
    previous_end = None
    for stage in ('runner-tests', 'runner-tests-optimized', 'cargo-fetch', 'build', 'check-build-digest', 'reference'):
        record = js(E / 'local-full-checks' / (stage + '.attempt.json'))
        identity(record)
        must(record['name'] == stage and record['exit_code'] == 0, 'full original stage did not pass')
        for channel in ('stdout', 'stderr'):
            pinned(record[channel], record[channel + '_sha256'])
        start, end = datetime.fromisoformat(record['started_at']), datetime.fromisoformat(record['finished_at'])
        must(start < end and (previous_end is None or previous_end <= start), 'stage chronology differs')
        previous_end = end
        stage_receipts[stage] = record
    freeze_time = datetime.fromisoformat(frozen['frozen_at'])
    must(datetime.fromisoformat(stage_receipts['check-build-digest']['finished_at']) < freeze_time
         < datetime.fromisoformat(stage_receipts['reference']['started_at']), 'input freeze not before Linux')
    ref_command = stage_receipts['reference']['command']
    must(ref_command[ref_command.index('--expected-input-sha256')+1] == INPUT, 'reference did not consume prefreeze digest')
    p, guest, lines = common_guest('local-full-guest', 'full-initramfs.cpio.gz')
    guest_input, ref, ref_input = js(p / 'input.json'), js(reference / 'result.json'), js(reference / 'input.json')
    for r in (guest, guest_input, ref, ref_input):
        identity(r)
        must(r['source_files'] == sources and r['input_sha256'] == INPUT
             and r['image_sha256'] == inputs['image_sha256'], 'Linux/guest source/input/image binding differs')
        must(r['pinned_debian13_qualification'] is False and r['original_hepta_w1_qualification'] is False
             and r['storage_power_loss_qualification'] is False, 'qualification scope drift')
    must(pinned(p / 'full-initramfs.cpio.gz', inputs['image_sha256']) == image, 'guest image not byte-identical frozen bundle')
    must(guest_input['passed'] is False and guest_input['qemu_argv'] == guest['qemu_argv'], 'guest frozen input differs')
    must(ref_input['cases'] == [] and ref_input['passed'] is False
         and digest(reference / 'input.json') == ref['frozen_reference_input_sha256'], 'Linux pre-case input differs')
    must(guest['linux_reference_receipt_sha256'] == digest(reference / 'result.json'), 'full guest Linux receipt link differs')
    must(ref['passed'] is True and ref['execution'] == 'actual_linux_chroot_uid65534'
         and ref['host_mounts_changed'] is False and ref['runtime_inputs_unchanged'] is True
         and ref['source_inputs_unchanged'] is True and ref['process_groups_cleanup_completed'] is True,
         'Linux original reference boundary failed')
    for r in (ref, guest):
        must(r['observed_cases'] == r['passed_cases'] == r['required_cases'] == 32
             and [case['name'] for case in r['cases']] == order, 'full original receipt case order/count differs')
    outputs = decode_full_guest(lines, order)
    rows = []
    root = Path(ref_input['reference_chroot'])
    must(root.name == 'root' and root.parent.parent == reference
         and re.fullmatch(r'a04-full-linux-[A-Za-z0-9_-]+', root.parent.name), 'not original disposable chroot')
    retained_root = {'path': str(root), 'exists': root.exists(), 'read_only_observed_at': datetime.now(timezone.utc).isoformat(),
                     'operator_statement': 'Parent states no copy, restore, or mutation of full32 chroot; only original guest consumed the bundle and Linux reference.',
                     'creation_source': FULL_RUNNER + ': run_reference, TemporaryDirectory and extract_chroot',
                     'cleanup_source': FULL_RUNNER + ': original TemporaryDirectory context exit; process-group cleanup is a separate recorded fact',
                     'removal_cause_or_retention_mechanism': 'not established',
                     'cleanup_by_reviewer': False}
    if root.exists():
        st = root.stat()
        retained_root['root_stat'] = {'mode': oct(st.st_mode), 'uid': st.st_uid,
                                     'mtime': datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                                     'ctime': datetime.fromtimestamp(st.st_ctime, timezone.utc).isoformat()}
        count_regular, count_symlink, mismatches = 0, 0, []
        for name, fields, data in entries:
            current = root / name
            if stat.S_ISREG(fields[1]):
                count_regular += 1
                if (not current.is_file() or current.is_symlink()
                    or current.read_bytes() != data or stat.S_IMODE(current.stat().st_mode) != stat.S_IMODE(fields[1])):
                    mismatches.append(name)
            elif stat.S_ISLNK(fields[1]):
                count_symlink += 1
                if not current.is_symlink() or os.readlink(current).encode() != data:
                    mismatches.append(name)
        retained_root['auxiliary_image_comparison'] = {'regular_files': count_regular, 'symlinks': count_symlink,
                                                     'mismatching_paths': mismatches,
                                                     'same_current_bytes_and_modes_as_frozen_image': not mismatches}
    for case, observation, reported, guest_reported in zip(contract['cases'], outputs, ref['cases'], guest['cases']):
        name = case['id']
        directory = reference / 'cases' / name
        stdout, stderr = read(directory / 'stdout.log'), read(directory / 'stderr.log')
        case_input = js(directory / 'input.json')
        child_result = js(directory / 'result.json')
        must(child_result == reported, 'Linux case result differs from parent: ' + name)
        must(read(directory / 'exit-code.txt') == b'0\n' and stderr == b'', 'Linux raw process failed: ' + name)
        must(stdout == observation['stdout'] and stderr == observation['stderr'], 'guest raw stdout/stderr differs from Linux: ' + name)
        text = stdout.decode('utf-8', errors='strict')
        facts = strict(text)
        must(len(text.splitlines()) == 1 and canonical(facts) == canonical(case['expected_facts']), 'concrete application facts differ: ' + name)
        expected_result = {'name': name, 'passed': True, 'process_exit': 0, 'timed_out': False,
                           'facts': facts, 'error': None, 'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
                           'stdout_bytes': len(stdout), 'stderr_bytes': len(stderr)}
        must(guest_reported == expected_result and all(reported[k] == v for k, v in expected_result.items()),
             'parsed original case receipt differs: ' + name)
        must(reported['process_group_cleanup_completed'] is True
             and digest(directory / 'input.json') == reported['frozen_case_input_sha256'], 'Linux per-case frozen invocation changed')
        case_env = {**env, 'HOME': '/tmp/a04/' + name}
        argv = ['/usr/bin/env', '-i', *[k+'='+v for k, v in sorted(case_env.items())], '/usr/sbin/chroot',
                '--userspec=65534:65534', '--groups=65534', str(root), *case['argv']]
        must(case_input == {'name': name, 'argv': argv, 'profile_argv': case['argv'], 'environment': case_env},
             'case invocation not fixed original UID65534/env/argv: ' + name)
        rows.append({'name': name, 'class': case['class'], 'stdout_bytes': len(stdout), 'stdout_sha256': sha(stdout),
                     'stderr_empty': True, 'linux_guest_raw_bytes_equal': True, 'source_expected_facts_equal': True,
                     'linux_process_exit': 0, 'guest_process_exit': 0,
                     'case_input_sha256': reported['frozen_case_input_sha256'],
                     'linux_result_sha256': digest(directory / 'result.json'),
                     'guest_serial_begin_line': observation['begin_line'], 'guest_serial_end_line': observation['end_line']})
    attempt = next(x for x in A04_ATTEMPT['phases'] if x['name'] == 'full32-guest')
    must(attempt['exit_code'] == 0 and digest(E / 'local-host/full32-guest.log') == attempt['log_sha256'], 'full guest actual attempt differs')
    must(datetime.fromisoformat(stage_receipts['reference']['finished_at']) < datetime.fromisoformat(attempt['started_at']),
         'guest did not follow Linux')
    must(attempt['command'][attempt['command'].index('--expected-input-sha256')+1] == INPUT, 'guest did not consume frozen digest')
    sequence = js(E / 'local-full-checks/sequence.json')
    # Do not require current product checkout state: parent can run negative controls now.
    sequence_sha = digest(E / 'local-full-checks/sequence.json')
    source_workflow = src('.github/workflows/a06-kernel.yml')
    src('tests/workloads/linux/test_full_ubuntu_profile.py')
    return {'schema': 'g1c.independent.a04-full32-review.v1', 'source_head': HEAD, 'source_tree': TREE,
            'passed': True, 'count': 32, 'class_counts': dict(classes), 'case_checks': rows,
            'input_sha256': INPUT, 'image_sha256': inputs['image_sha256'], 'image_bytes': len(image),
            'input_frozen_at': frozen['frozen_at'], 'freeze_after_build_and_before_linux': True,
            'linux_then_guest': True, 'same_bundle_and_guest_image_bytes': True,
            'runtime_regular_files': runtime_count, 'runtime_regular_bytes': manifest['regular_bytes'],
            'all_retained_runtime_and_image_entries_match_manifest': True,
            'original_image_preservation': injection, 'five_workload_elf': workload_elf,
            'linux_case_uid_gid': 65534, 'linux_kernel_reported': ref['linux_kernel'],
            'every_linux_case_frozen_command_matches_original_contract': True,
            'all_32_linux_stdout_bytes_equal_guest_base64_decoded_stdout': True,
            'all_32_stdout_json_equal_git104_expected_facts': True, 'all_32_stderr_empty': True,
            'kernel_sha256': KERNEL, 'qemu_exit': 33, 'guest_process_exit': 0,
            'qemu_argv_exact_original_one_vcpu_tcg': True,
            'guest_serial_sha256': guest['serial_sha256'], 'guest_serial_bytes': guest['serial_bytes'],
            'guest_elapsed_seconds': guest['elapsed_seconds'], 'tools_hashed_without_invocation': inputs['tools'],
            'locked_tokio_build': {'cargo_lock_sha256': sources['tests/workloads/linux/rust/Cargo.lock'],
                                   'actual_argv': commands[-1]['argv'], 'rustc_version_log_sha256': sha(rust_version.encode())},
            'original_stage_attempts': {n: {k: r[k] for k in ('started_at', 'finished_at', 'seconds', 'exit_code', 'stdout_sha256', 'stderr_sha256')}
                                         for n, r in stage_receipts.items()},
            'guest_attempt': {k: attempt[k] for k in ('started_at', 'finished_at', 'seconds', 'exit_code', 'log_sha256')},
            'sequence_sha256': sequence_sha, 'original_a06_workflow_sha256': sha(source_workflow),
            'retained_chroot_observation': retained_root,
            'chroot_observation_scope': 'The recorded chroot path remains visible when reviewed. Original receipt records process-group cleanup and frozen-byte verification. This review does not infer that the disposable directory was removed or diagnose its retention.',
            'qualification': 'Actual local Ubuntu24.04 full32 supplementary profile, original fixed denominator. Not hosted A06 CI, pinned Debian13, original Hepta W1, storage power loss, SMP, G1-d, or desktop/mobile qualification.'}


def save(name, result):
    result['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    result['review_method'] = 'Read-only explicit git104 source; independent original log/serial, JSON, SHA256, ELF program/dynamic headers and newc parsing. No producer import/execution, tests, builds, toolchain invocation, product or remote writes.'
    result['reviewer_program_sha256'] = sha(Path(__file__).read_bytes())
    path = OUT / name
    data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    path.write_bytes(data)
    print(json.dumps({'path': str(path), 'bytes': len(data), 'sha256': sha(data), 'passed': result['passed']}))
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}


PRODUCT_DIR = E / 'local-ordinary-candidate-final'
PRODUCT_RECEIPT = js(PRODUCT_DIR / 'result.json')
PRODUCT_SHA = digest(PRODUCT_DIR / 'result.json')
identity(PRODUCT_RECEIPT)
must(PRODUCT_RECEIPT['passed'] is True and PRODUCT_RECEIPT['source_inputs_unchanged'] is True
     and PRODUCT_RECEIPT['product_wrapper_exit'] == 0 and PRODUCT_RECEIPT['product_boot_raw_exit'] == 33
     and PRODUCT_RECEIPT['qemu_exit'] == 33 and PRODUCT_RECEIPT['stage'] == 'complete', 'ordinary source product gate failed')
PRODUCT_ELF = pinned(PRODUCT_DIR / 'product-kernel.elf', KERNEL)
must(elf(PRODUCT_ELF)['machine'] == 3, 'ordinary multiboot ELF QEMU compatibility machine differs')
SNAPSHOTS = [js(PRODUCT_DIR / name) for name in ('source-before.json', 'source-after-boot.json', 'source-after-guest.json')]
must(SNAPSHOTS[0] == SNAPSHOTS[1] == SNAPSHOTS[2] and SNAPSHOTS[0]['head'] == HEAD
     and SNAPSHOTS[0]['tree'] == TREE and len(SNAPSHOTS[0]['files']) == 7346, 'ordinary source snapshot boundary differs')
ORDINARY_REVIEW = js(OUT / 'ordinary-10420401-review.json')
# Prior independent ordinary review already compared all 7346 source entries to git104 blobs.
ORIGINAL_BYTES = pinned(E / 'local-full-bundle/original-initramfs.cpio.gz', ORIGINAL)
ORIGINAL_ENTRIES = newc(ORIGINAL_BYTES)
pinned('/usr/bin/qemu-system-x86_64', QEMU)
A04_ATTEMPT = js(E / 'local-host/a04-guest-attempts.json')
identity(A04_ATTEMPT)
must(A04_ATTEMPT['passed'] is True and A04_ATTEMPT['source_status_after'] == '', 'A04 actual attempt incomplete')

SCM_RESULT = review_simple('scm')
NOFILE_RESULT = review_simple('nofile')
FULL_RESULT = review_full()
SIMPLE = {'schema': 'g1c.independent.a04-scm-nofile-review.v1', 'passed': True, 'source_head': HEAD,
          'source_tree': TREE, 'scm': SCM_RESULT, 'rlimit_nofile': NOFILE_RESULT,
          'source_inputs': source_hashes(),
          'artifacts': evidence_meta(['local-scm-', 'local-nofile-', 'local-host/scm-', 'local-host/nofile-',
                                      'local-host/a04-guest-attempts.json'])}
FULL_RESULT['source_inputs'] = source_hashes()
FULL_RESULT['artifacts'] = evidence_meta(['local-full-bundle/inputs', 'local-full-bundle/contract',
    'local-full-bundle/runtime-manifest', 'local-full-bundle/full-initramfs', 'local-full-bundle/original-initramfs',
    'local-full-bundle/full_guest', 'local-full-bundle/result', 'local-full-bundle/build-input',
    'local-full-linux/input', 'local-full-linux/result', 'local-full-guest/', 'local-full-checks/',
    'local-host/full32-guest', 'local-host/a04-guest-attempts.json'])
SIMPLE_META = save('a04-scm-nofile-review.json', SIMPLE)
FULL_META = save('a04-full32-review.json', FULL_RESULT)
save('a04-combined-review.json', {
    'schema': 'g1c.independent.a04-combined-review.v1', 'passed': True,
    'source_head': HEAD, 'source_tree': TREE, 'kernel_sha256': KERNEL,
    'ordinary_product_receipt_sha256': PRODUCT_SHA,
    'ordinary_previous_independent_source_review_sha256': digest(OUT / 'ordinary-10420401-review.json'),
    'ordinary_source_snapshot_sha256': digest(PRODUCT_DIR / 'source-before.json'),
    'ordinary_source_entries': 7346,
    'source_scope': 'All three original ordinary snapshots rechecked identical. Full git104 7346-blob equality is delegated to the already completed and hashed ordinary independent review; no present-HEAD or clean-state dependency during negative-control work.',
    'profiles': [
        {'name': 'SCM_RIGHTS/CLOEXEC', 'linux': 27, 'guest': 27, 'qemu_exit': 33, 'probe_sha256': SCM,
         'serial_sha256': SCM_RESULT['guest_serial_sha256']},
        {'name': 'RLIMIT_NOFILE', 'linux': 37, 'guest': 37, 'qemu_exit': 33, 'probe_sha256': NOFILE,
         'serial_sha256': NOFILE_RESULT['guest_serial_sha256']},
        {'name': 'Ubuntu24.04 full32', 'linux': 32, 'guest': 32, 'qemu_exit': 33,
         'frozen_inputs_sha256': INPUT, 'frozen_image_sha256': FULL_RESULT['image_sha256'],
         'serial_sha256': FULL_RESULT['guest_serial_sha256']}],
    'all_profile_stdout_contracts_equal_original_linux_and_guest': True,
    'all_guests_same_ordinary_kernel_bios_qemu_one_vcpu_tcg': True,
    'independent_receipts': [SIMPLE_META, FULL_META],
    'earlier_failed_default_environment_runs_retained': {'scm': '24 PASS / 3 FAIL, EPERM at SO_PASSCRED',
                                                        'nofile': '32 PASS / 5 FAIL, EPERM at AF_UNIX bind'},
    'scope': 'Original local supplementary evidence only, with unchanged runners/contracts and distinct prior default-environment failures. No hosted CI green, pinned Debian13, original Hepta W1, storage crash durability, G1-d capability grant, SMP or desktop/mobile device qualification.'})
