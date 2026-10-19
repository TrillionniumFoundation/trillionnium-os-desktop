#!/usr/bin/env python3
"""Build, execute on Linux, and replay one frozen Ubuntu 24.04 32-case image.

All three stages share one input digest. The Linux reference runs actual image
bytes under chroot; the guest consumes that exact image without rebuilding it.
Historical Debian 13 qualification and original Hepta W1 remain separate.
"""
import argparse
import base64
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROFILE_PATH = ROOT / 'compat/linux/profiles/ubuntu24.04-x86_64-20261019.json'
CAPTURE_PATH = ROOT / 'support/rootfs/ubuntu_full.py'
RLIMIT_PATH = HERE / 'run_rlimit_nofile_guest.py'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


rlimit = module('a04_full_rlimit_helpers', RLIMIT_PATH)
runtime = module('a04_ubuntu_full_capture', CAPTURE_PATH)
common, groups = rlimit.common, rlimit.groups
require, sha, read_file, read_pinned = common.require, common.sha, common.read_file, common.read_pinned
PROFILE = 'linux-ubuntu24.04-x86_64-20261019'
CASE_ORDER = (
    'dynamic.async_fd', 'dynamic.cloexec', 'dynamic.errno', 'dynamic.fd_limit',
    'dynamic.file_lock', 'dynamic.ipc_epoll', 'dynamic.mmap_cow', 'dynamic.process',
    'dynamic.robust_owner_death', 'dynamic.scm_rights', 'dynamic.smoke',
    'dynamic.threads_futex', 'dynamic.uds_peercred', 'nss_tls', 'rust_tokio',
    'sqlite_dynamic.sqlite_wal_elf', 'sqlite_static.sqlite_wal_elf', 'sqlite_wal',
    'static.async_fd', 'static.cloexec', 'static.errno', 'static.fd_limit',
    'static.file_lock', 'static.ipc_epoll', 'static.mmap_cow', 'static.process',
    'static.robust_owner_death', 'static.scm_rights', 'static.smoke',
    'static.threads_futex', 'static.uds_peercred', 'uds_path',
)
CASE_COUNT = 32
MAX_IMAGE_BYTES = 256 * 1024 * 1024
MAX_CASE_BYTES = 1024 * 1024
MAX_SERIAL_BYTES = 96 * 1024 * 1024
SCRIPT_PATH = 'usr/local/lib/a04/full_guest.sh'
ENVIRONMENT = {'PATH': '/usr/local/bin/a04:/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC',
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
               'PYTHONSAFEPATH': '1', 'OPENSSL_CONF': '/etc/ssl/openssl.cnf',
               'SSL_CERT_FILE': '/etc/ssl/certs/ca-certificates.crt',
               'SSL_CERT_DIR': '/etc/ssl/certs'}
SOURCE_PATHS = (
    'tests/workloads/linux/run_full_ubuntu_profile.py', 'support/rootfs/ubuntu_full.py',
    'compat/linux/profiles/ubuntu24.04-x86_64-20261019.json',
    'tests/workloads/linux/full_python_case.py', 'tests/workloads/linux/run.py',
    'tests/workloads/linux/probe.c', 'tests/workloads/linux/sqlite_probe.c',
    'tests/workloads/linux/rust/Cargo.toml', 'tests/workloads/linux/rust/Cargo.lock',
    'tests/workloads/linux/rust/src/main.rs', 'tests/workloads/linux/workload_catalog.json',
    'tests/workloads/linux/run_rlimit_nofile_guest.py',
    'tests/workloads/linux/run_scm_rights_cloexec_guest.py',
    'tests/organ_backend/run_guest_probe.py', 'tests/integration/hepta/run_original_agentd.py',
)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON value: ' + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def contract():
    result = strict_json(read_file(PROFILE_PATH, 1024 * 1024))
    require(result['schema'] == 'a04.linux-full-contract.v1' and result['profile'] == PROFILE,
            'unknown full-profile contract')
    require(result['case_count'] == CASE_COUNT
            and tuple(case['id'] for case in result['cases']) == CASE_ORDER,
            'full fixed 32-case denominator required')
    require(result['python'] == '/usr/bin/python3.12' and result['case_timeout_seconds'] == 45,
            'unreviewed interpreter or case deadline')
    require(sha(read_file(HERE / 'workload_catalog.json')) == result['legacy_catalog_sha256'],
            'legacy workload catalog changed')
    for case in result['cases']:
        require(case['class'] in ('elf', 'python', 'rust') and case['expected_facts']['ok'] is True,
                'missing concrete release facts')
        require(all(isinstance(arg, str) and re.fullmatch(r'[A-Za-z0-9_./-]+', arg)
                    for arg in case['argv']), 'unsafe generated guest argument')
    require(sum(case['class'] == 'elf' for case in result['cases']) == 28
            and sum(case['class'] == 'python' for case in result['cases']) == 3
            and sum(case['class'] == 'rust' for case in result['cases']) == 1,
            'profile class denominator changed')
    return result


def git(*arguments):
    # The reference is root only for its disposable chroot. Scope Git's trust
    # to this explicit reviewed checkout; do not change any global Git config.
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(ROOT),
                                    '-C', str(ROOT), *arguments], timeout=30,
                                   stderr=subprocess.PIPE).decode().strip()


def source_identity(head, tree):
    require(re.fullmatch('[0-9a-f]{40}', head) is not None
            and re.fullmatch('[0-9a-f]{40}', tree) is not None, 'invalid source identity')
    require(git('rev-parse', 'HEAD') == head and git('rev-parse', 'HEAD^{tree}') == tree,
            'source differs from reviewed head/tree')
    require(not git('status', '--porcelain=v1', '--untracked-files=all'),
            'full-profile source checkout is not clean')
    return {path: sha(read_file(ROOT / path, 1024 * 1024)) for path in SOURCE_PATHS}


def decompressed_image(data):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        raw = stream.read(MAX_IMAGE_BYTES + 1)
        require(len(raw) <= MAX_IMAGE_BYTES and stream.read(1) == b'',
                'decompressed image exceeds bound')
    return raw


def guest_script(profile):
    lines = ['#!/bin/sh', 'set -eu', 'umask 077', 'full_failed=0',
             '/bin/busybox mkdir -p /tmp/a04']
    for key, value in ENVIRONMENT.items():
        lines.append('export ' + key + '=' + value)
    lines.append('unset LD_PRELOAD LD_LIBRARY_PATH PYTHONPATH PYTHONHOME PYTHONSTARTUP')
    for case in profile['cases']:
        name, scratch = case['id'], '/tmp/a04/' + case['id']
        command = ' '.join(case['argv'])
        lines.extend([
            '/bin/busybox mkdir -p ' + scratch,
            'export HOME=' + scratch,
            'echo A04_FULL_BEGIN=' + name,
            'if /bin/busybox timeout -s KILL 45 ' + command
            + ' >' + scratch + '/stdout.log 2>' + scratch + '/stderr.log; then',
            '    case_exit=0', 'else', '    case_exit=$?', '    full_failed=$((full_failed + 1))', 'fi',
        ])
        for channel in ('stdout', 'stderr'):
            path = scratch + '/' + channel + '.log'
            lines.extend([
                '/bin/busybox base64 ' + path + ' | while IFS= read -r chunk; do',
                '    echo A04_FULL_' + channel.upper() + '=' + name + ':$chunk', 'done',
                channel + '_bytes=$(/bin/busybox wc -c <' + path + ')',
                'set -- $(/bin/busybox sha256sum ' + path + ')', channel + '_sha=$1',
            ])
        lines.append('echo A04_FULL_END=' + name
                     + ':$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha')
    lines.extend(['echo A04_FULL_COMPLETE=32:$full_failed',
                  'test "$full_failed" -eq 0'])
    return ('\n'.join(lines) + '\n').encode()


def new_entry(name, mode, data, inode):
    return (name, [inode, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0, len(data),
                   0, 0, 0, 0, len(name.encode()) + 1, 0], data)


def merge_image(original, files, script):
    entries = common.unpack(decompressed_image(original))
    require(common.unpack(common.pack(entries)) == entries, 'original newc roundtrip differs')
    by_name = {name: (fields, data) for name, fields, data in entries}
    require(len(by_name) == len(entries), 'duplicate original image entry')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    injected = b'''if /bin/busybox sh /usr/local/lib/a04/full_guest.sh; then
    full_profile_exit=0
else
    full_profile_exit=$?
fi
echo "A04_FULL_PROCESS_EXIT=$full_profile_exit"
'''
    changed, found = [], 0
    for name, fields, data in entries:
        if name == 'init':
            require(data.count(marker) == 1 and b'set -eu' in data, 'invalid original init')
            data = data.replace(marker, injected + marker)
            fields = fields.copy()
            fields[6] = len(data)
            found += 1
        changed.append((name, fields, data))
    require(found == 1, 'original init missing')
    additions = {name.lstrip('/'): (stat.S_IFREG | mode, data)
                 for name, (mode, data) in files.items()}
    require(SCRIPT_PATH not in additions, 'guest script path conflicts with runtime')
    additions[SCRIPT_PATH] = (stat.S_IFREG | 0o444, script)
    directories = set()
    for name in additions:
        runtime.destination('/' + name)
        for parent in PurePosixPath(name).parents:
            if str(parent) != '.':
                directories.add(str(parent))
    inode = max(fields[0] for _, fields, _ in entries) + 1
    for name in sorted(directories):
        if name in by_name:
            require(stat.S_ISDIR(by_name[name][0][1]), 'runtime directory conflicts with original entry')
            continue
        changed.append(new_entry(name, stat.S_IFDIR | 0o755, b'', inode))
        inode += 1
    for name, (mode, data) in sorted(additions.items()):
        require(name not in by_name, 'runtime would replace an original image entry: ' + name)
        changed.append(new_entry(name, mode, data, inode))
        inode += 1
    raw = common.pack(changed)
    require(len(raw) <= MAX_IMAGE_BYTES
            and common.unpack(raw, max_bytes=MAX_IMAGE_BYTES) == changed,
            'derived image roundtrip or size differs')
    return gzip.compress(raw, mtime=0)


def validate_image(image, original, manifest, script):
    entries = common.unpack(decompressed_image(image), max_bytes=MAX_IMAGE_BYTES)
    by_name = {name: (fields, data) for name, fields, data in entries}
    require(len(by_name) == len(entries), 'duplicate derived image entry')
    files = {}
    for record in manifest['files']:
        name = runtime.destination(record['path'])
        require(name not in files, 'duplicate manifest file')
        fields, data = by_name[name[1:]]
        require(record['mode'] in (0o444, 0o555) and fields[1] == stat.S_IFREG | record['mode']
                and len(data) == record['bytes'] and sha(data) == record['sha256'],
                'frozen runtime entry differs: ' + name)
        files[name] = (record['mode'], data)
    require(len(files) == manifest['file_count']
            and sum(len(data) for _, data in files.values()) == manifest['regular_bytes'],
            'frozen runtime denominator differs')
    expected = common.unpack(decompressed_image(merge_image(original, files, script)),
                             max_bytes=MAX_IMAGE_BYTES)
    require(entries == expected, 'frozen image changed original metadata or includes unexpected entries')
    return entries


def elf_interpreter(data):
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01'
            and data[18:20] == b'\x3e\x00', 'workload is not x86_64 ELF')
    offset, size, count = struct.unpack_from('<Q', data, 32)[0], *struct.unpack_from('<HH', data, 54)
    require(size == 56 and count > 0 and offset + size * count <= len(data),
            'invalid workload ELF program headers')
    interpreters = []
    for index in range(count):
        header = offset + index * size
        if struct.unpack_from('<I', data, header)[0] != 3:
            continue
        start = struct.unpack_from('<Q', data, header + 8)[0]
        length = struct.unpack_from('<Q', data, header + 32)[0]
        require(1 < length <= 4096 and start + length <= len(data), 'invalid PT_INTERP range')
        raw = data[start:start + length]
        require(raw.endswith(b'\x00') and b'\x00' not in raw[:-1], 'invalid PT_INTERP string')
        interpreters.append(raw[:-1].decode('ascii'))
    require(len(interpreters) <= 1, 'duplicate PT_INTERP')
    return interpreters[0] if interpreters else None


def verify_workload_matrix(entries, manifest):
    by_name = {name: data for name, _, data in entries}
    for name in ('probe_dynamic', 'probe_static', 'sqlite_dynamic', 'sqlite_static',
                 'a04-tokio-workload'):
        path = '/usr/local/bin/a04/' + name
        interpreter = elf_interpreter(by_name[path[1:]])
        metadata = manifest['elf'][path]
        require(interpreter == metadata['interpreter'], 'ELF PT_INTERP metadata differs')
        if name in ('probe_static', 'sqlite_static'):
            require(interpreter is None and metadata['needed'] == [], 'static case has dynamic dependencies')
        else:
            require(interpreter == '/lib64/ld-linux-x86-64.so.2'
                    and 'libc.so.6' in metadata['needed'], 'dynamic workload loader/libc missing')
        if name == 'sqlite_dynamic':
            require('libsqlite3.so.0' in metadata['needed'], 'dynamic SQLite workload is not dynamically linked')


def inspect_tool(name):
    executable = shutil.which(name)
    require(executable is not None, 'required tool unavailable: ' + name)
    path = Path(executable).resolve(strict=True)
    data = read_file(path, 64 * 1024 * 1024)
    # Preserve proxy argv[0], especially cargo -> rustup; resolving its command
    # pathname would turn `cargo +nightly build` into a different rustup CLI.
    return {'path': str(Path(executable).absolute()), 'resolved_path': str(path),
            'sha256': sha(data), 'bytes': len(data)}


def run_build(args, out, report):
    require(sys.executable == '/usr/bin/python3.12', 'build must use /usr/bin/python3.12')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines()
                   if '=' in line)
    require(release.get('ID', '').strip('"') == 'ubuntu'
            and release.get('VERSION_ID', '').strip('"') == '24.04'
            and os.uname().machine == 'x86_64', 'Ubuntu 24.04 x86_64 builder required')
    profile = contract()
    sources = source_identity(args.expected_source_head, args.expected_source_tree)
    packages = runtime.package_versions()
    original = read_pinned(args.a01_initramfs, common.INITRD_SHA, 8 * 1024 * 1024)
    tools = {name: inspect_tool(name) for name in
             ('/usr/bin/gcc-13', '/usr/bin/ld', '/usr/bin/readelf', '/usr/bin/python3.12', 'cargo')}
    qemu = inspect_tool(args.qemu)
    require(read_file(Path(qemu['resolved_path']))[:4] == b'\x7fELF', 'build requires the real QEMU ELF')
    tools['qemu'] = qemu
    build = out / 'build'
    build.mkdir()
    environment = {key: os.environ[key] for key in ('PATH', 'HOME', 'CARGO_HOME', 'RUSTUP_HOME')
                   if key in os.environ}
    environment.update({'LC_ALL': 'C', 'CARGO_INCREMENTAL': '0', 'CARGO_BUILD_JOBS': '2'})
    for name in ('cargo', 'rustc'):
        executable = subprocess.check_output(
            [tools['cargo']['resolved_path'], 'which', '--toolchain', 'nightly-2026-07-21', name],
            env=environment, stderr=subprocess.PIPE, timeout=20).decode().strip()
        tools[name + '_pinned'] = inspect_tool(executable)
    for name in ('/usr/bin/gcc-13', '/usr/bin/ld'):
        tools[name]['version'] = runtime.tool_output([name, '--version'])[1].splitlines()[0]
    tools['/usr/bin/python3.12']['version'] = sys.version
    commands = []
    report.update(source_head=args.expected_source_head, source_tree=args.expected_source_tree,
                  packages=packages, tools=tools, commands=commands)
    (out / 'build-input.json').write_bytes(json_bytes(report))
    version_command = [tools['rustc_pinned']['path'], '-vV']
    commands.append({'argv': version_command, 'cwd': str(ROOT), 'log': 'build/rustc-version.log'})
    groups.bounded_command(version_command, ROOT, environment, build / 'rustc-version.log', 30)
    binaries = {}
    for name, source, flags in (
        ('probe_dynamic', 'probe.c', []), ('probe_static', 'probe.c', ['-static']),
        ('sqlite_dynamic', 'sqlite_probe.c', ['-lsqlite3']),
        ('sqlite_static', 'sqlite_probe.c', ['-static', '-lsqlite3', '-lpthread', '-lm', '-ldl']),
    ):
        output = build / name
        command = ['/usr/bin/gcc-13', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pthread']
        command += (['-static'] if '-static' in flags else [])
        command += [source, '-o', str(output)]
        command += [flag for flag in flags if flag != '-static']
        commands.append({'argv': command, 'cwd': str(HERE), 'log': 'build/' + name + '.log'})
        report['stage'] = 'compile_' + name
        groups.bounded_command(command, HERE, environment, build / (name + '.log'), 120)
        binaries[name] = output
    target = build / 'cargo-target'
    cargo_command = [tools['cargo']['path'], '+nightly-2026-07-21', 'build', '--offline', '--locked',
                     '--release', '--target', 'x86_64-unknown-linux-gnu', '--manifest-path',
                     str(HERE / 'rust/Cargo.toml'), '--target-dir', str(target)]
    commands.append({'argv': cargo_command, 'cwd': str(ROOT), 'log': 'build/tokio.log'})
    report['stage'] = 'compile_tokio'
    groups.bounded_command(cargo_command, ROOT, environment, build / 'tokio.log', 600)
    binaries['a04-tokio-workload'] = target / 'x86_64-unknown-linux-gnu/release/a04-tokio-workload'
    elf_directory = out / 'workload-elf'
    elf_directory.mkdir()
    for name, path in list(binaries.items()):
        frozen_elf = elf_directory / name
        frozen_elf.write_bytes(read_file(path, 32 * 1024 * 1024))
        frozen_elf.chmod(0o555)
        binaries[name] = frozen_elf
    report['stage'] = 'capture_runtime'
    manifest = runtime.capture(out / 'runtime', binaries, HERE / 'full_python_case.py', HERE / 'run.py')
    files = runtime.verified_files(out / 'runtime', manifest)
    script = guest_script(profile)
    image = merge_image(original, files, script)
    verify_workload_matrix(validate_image(image, original, manifest, script), manifest)
    manifest_data = json_bytes(manifest)
    (out / 'runtime-manifest.json').write_bytes(manifest_data)
    (out / 'original-initramfs.cpio.gz').write_bytes(original)
    (out / 'full-initramfs.cpio.gz').write_bytes(image)
    (out / 'full_guest.sh').write_bytes(script)
    (out / 'contract.json').write_bytes(read_file(PROFILE_PATH))
    require(source_identity(args.expected_source_head, args.expected_source_tree) == sources,
            'build source changed')
    for name, tool in tools.items():
        require(sha(read_file(Path(tool['resolved_path']))) == tool['sha256'],
                'build tool changed during capture: ' + name)
    inputs = {'schema': 'a04.ubuntu-full-inputs.v1', 'profile': PROFILE,
              'source_head': args.expected_source_head, 'source_tree': args.expected_source_tree,
              'sources': sources, 'packages': packages, 'tools': tools, 'commands': commands,
              'contract_sha256': sha(read_file(PROFILE_PATH)), 'runtime_manifest_sha256': sha(manifest_data),
              'original_initramfs_sha256': common.INITRD_SHA, 'image_sha256': sha(image),
              'guest_script_sha256': sha(script), 'case_count': CASE_COUNT,
              'workload_execution_performed': False,
              'probe_elf': {name: {'sha256': sha(read_file(path)), 'bytes': path.stat().st_size}
                            for name, path in binaries.items()}}
    frozen = json_bytes(inputs)
    (out / 'inputs.json').write_bytes(frozen)
    (out / 'inputs.sha256').write_text(sha(frozen) + '  inputs.json\n')
    report.update(passed=True, build_bundle_verified=True, input_sha256=sha(frozen),
                  image_sha256=sha(image), runtime_file_count=manifest['file_count'],
                  runtime_regular_bytes=manifest['regular_bytes'], case_count=CASE_COUNT,
                  linux_qualification_passed=False, guest_qualification_passed=False, stage='complete')


def load_bundle(directory, digest):
    raw = read_pinned(directory / 'inputs.json', digest, 1024 * 1024)
    require(read_file(directory / 'inputs.sha256', 1024) == (digest + '  inputs.json\n').encode(),
            'pre-execution bundle digest differs')
    inputs = strict_json(raw)
    require(inputs['schema'] == 'a04.ubuntu-full-inputs.v1' and inputs['profile'] == PROFILE
            and inputs['case_count'] == CASE_COUNT and inputs['workload_execution_performed'] is False,
            'unknown or incomplete frozen build bundle')
    require(source_identity(inputs['source_head'], inputs['source_tree']) == inputs['sources'],
            'current helper/source bytes differ from frozen build')
    profile = contract()
    require(read_pinned(directory / 'contract.json', inputs['contract_sha256']) == read_file(PROFILE_PATH),
            'frozen 32-case contract differs')
    original = read_pinned(directory / 'original-initramfs.cpio.gz', common.INITRD_SHA, 8 * 1024 * 1024)
    manifest = strict_json(read_pinned(directory / 'runtime-manifest.json',
                                      inputs['runtime_manifest_sha256'], 8 * 1024 * 1024))
    require(manifest['schema'] == 'a04.ubuntu-full-rootfs.v1', 'unknown runtime manifest')
    image = read_pinned(directory / 'full-initramfs.cpio.gz', inputs['image_sha256'], MAX_IMAGE_BYTES)
    script = read_pinned(directory / 'full_guest.sh', inputs['guest_script_sha256'])
    require(script == guest_script(profile), 'frozen guest program differs from reviewed generator')
    entries = validate_image(image, original, manifest, script)
    verify_workload_matrix(entries, manifest)
    elf_data = {record['path'].rsplit('/', 1)[-1]: record for record in manifest['files']
                if record['role'] == 'workload_elf'}
    require(set(elf_data) == {'probe_dynamic', 'probe_static', 'sqlite_dynamic', 'sqlite_static',
                             'a04-tokio-workload'} and set(inputs['probe_elf']) == set(elf_data),
            'all five workload ELF identities required')
    for name, record in elf_data.items():
        require(inputs['probe_elf'][name] == {'sha256': record['sha256'], 'bytes': record['bytes']},
                'workload ELF identity differs from the frozen image')
        require(len(read_pinned(directory / 'workload-elf' / name, record['sha256'],
                                32 * 1024 * 1024)) == record['bytes'],
                'retained workload ELF bytes differ from the frozen image')
    return inputs, profile, entries, image


def evaluate_case(case, stdout, stderr, code, timed_out):
    facts, error = None, None
    try:
        require(len(stdout) <= MAX_CASE_BYTES and len(stderr) <= MAX_CASE_BYTES, 'case log exceeds bound')
        text = stdout.decode('utf-8', errors='strict')
        require(len(text.splitlines()) == 1, 'expected exactly one application JSON line')
        facts = strict_json(text)
        require(isinstance(facts, dict) and facts.get('ok') is True, 'application success fact missing')
        require(json_bytes(facts) == json_bytes(case['expected_facts']), 'concrete application facts differ')
        require(type(code) is int and code == 0 and timed_out is False and stderr == b'',
                'actual process exit, timeout or stderr failed')
    except (ValueError, UnicodeError, TypeError) as failure:
        error = str(failure)
    return {'name': case['id'], 'passed': error is None, 'process_exit': code, 'timed_out': timed_out,
            'facts': facts, 'error': error, 'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr),
            'stdout_bytes': len(stdout), 'stderr_bytes': len(stderr)}


def evaluate_cases(cases):
    complete = len(cases) == CASE_COUNT and tuple(case['name'] for case in cases) == CASE_ORDER
    passed = sum(case.get('passed') is True for case in cases)
    return {'cases_complete': complete, 'passed_cases': passed,
            'observed_cases': len(cases), 'required_cases': CASE_COUNT,
            'cases_passed': complete and passed == CASE_COUNT}


def extract_chroot(entries, root):
    require(not root.exists() and not root.is_symlink(), 'chroot already exists')
    root.mkdir(mode=0o755)
    for name, fields, data in entries:
        runtime.destination('/' + name)
        if stat.S_ISDIR(fields[1]):
            (root / name).mkdir(parents=True, exist_ok=True)
            (root / name).chmod(fields[1] & 0o7777)
    for name, fields, data in entries:
        target = root / name
        if stat.S_ISDIR(fields[1]):
            continue
        require(all(not parent.is_symlink() for parent in target.parents if parent != root.parent),
                'symlink ancestor in extracted image')
        if stat.S_ISREG(fields[1]):
            with target.open('xb') as stream:
                stream.write(data)
            target.chmod(fields[1] & 0o777)
        elif stat.S_ISLNK(fields[1]):
            # Only original A01 BusyBox applet links exist in an accepted image.
            require(name.startswith('bin/') and data == b'busybox', 'unreviewed image symlink')
            target.symlink_to('busybox')
        else:
            raise ValueError('special image entry is not supported')


def verify_chroot(entries, root):
    for name, fields, data in entries:
        path = root / name
        if stat.S_ISREG(fields[1]):
            require(not path.is_symlink() and read_file(path, MAX_IMAGE_BYTES) == data
                    and path.stat().st_mode & 0o777 == fields[1] & 0o777,
                    'Linux execution changed frozen image bytes or mode: ' + name)
        elif stat.S_ISLNK(fields[1]):
            require(path.is_symlink() and os.readlink(path) == data.decode(),
                    'Linux execution changed original image symlink')


def reference_invocation(root, case):
    environment = {**ENVIRONMENT, 'HOME': '/tmp/a04/' + case['id']}
    command = ['/usr/bin/env', '-i', *(key + '=' + value for key, value in sorted(environment.items())),
               '/usr/sbin/chroot', '--userspec=65534:65534', '--groups=65534',
               str(root), *case['argv']]
    return {'name': case['id'], 'argv': command,
            'profile_argv': case['argv'], 'environment': environment}


def run_reference(args, out, report):
    require(os.geteuid() == 0 and os.uname().machine == 'x86_64',
            'reference requires a disposable root/CAP_SYS_CHROOT Linux x86_64 process')
    inputs, profile, entries, image = load_bundle(args.bundle, args.expected_input_sha256)
    report.update(input_sha256=args.expected_input_sha256, image_sha256=sha(image),
                  source_head=inputs['source_head'], source_tree=inputs['source_tree'],
                  linux_kernel=os.uname().release, execution='actual_linux_chroot_uid65534',
                  host_mounts_changed=False, reference_output=str(out), cases=[])
    (out / 'cases').mkdir()
    with tempfile.TemporaryDirectory(prefix='a04-full-linux-', dir=out) as temporary:
        root = Path(temporary) / 'root'
        report['reference_chroot'] = str(root)
        (out / 'input.json').write_bytes(json_bytes(report))
        report['frozen_reference_input_sha256'] = sha(read_file(out / 'input.json'))
        extract_chroot(entries, root)
        for case in profile['cases']:
            directory = out / 'cases' / case['id']
            directory.mkdir()
            scratch = root / 'tmp/a04' / case['id']
            scratch.mkdir(parents=True, mode=0o700)
            scratch.chmod(0o700)
            os.chown(scratch, 65534, 65534)
            invocation = reference_invocation(root, case)
            case_input = json_bytes(invocation)
            (directory / 'input.json').write_bytes(case_input)
            code, timed_out = rlimit.reference_process(invocation['argv'], directory, timeout_seconds=45)
            (directory / 'exit-code.txt').write_text(str(code) + '\n')
            stdout = read_file(directory / 'stdout.log', MAX_CASE_BYTES)
            stderr = read_file(directory / 'stderr.log', MAX_CASE_BYTES)
            result = evaluate_case(case, stdout, stderr, code, timed_out)
            result['process_group_cleanup_completed'] = True
            result['frozen_case_input_sha256'] = sha(case_input)
            require(read_file(directory / 'input.json') == case_input,
                    'case invocation changed during execution')
            report['cases'].append(result)
            (directory / 'result.json').write_bytes(json_bytes(result))
        verify_chroot(entries, root)
    report.update(evaluate_cases(report['cases']), runtime_inputs_unchanged=True,
                  process_groups_cleanup_completed=True)
    load_bundle(args.bundle, args.expected_input_sha256)
    report['passed'] = report['cases_passed']


def load_reference(directory, digest, profile, image_sha):
    raw = read_file(directory / 'result.json', 4 * 1024 * 1024)
    receipt = strict_json(raw)
    require(receipt['schema'] == 'a04.ubuntu-full-reference.v1' and receipt['profile'] == PROFILE
            and receipt['passed'] is True and receipt['runtime_inputs_unchanged'] is True
            and receipt['source_inputs_unchanged'] is True
            and receipt['process_groups_cleanup_completed'] is True,
            'Linux full reference did not complete successfully')
    require(receipt['input_sha256'] == digest and receipt['image_sha256'] == image_sha,
            'Linux full reference used a different frozen image')
    frozen = strict_json(read_pinned(directory / 'input.json', receipt['frozen_reference_input_sha256']))
    require(frozen['input_sha256'] == digest and frozen['image_sha256'] == image_sha
            and frozen['cases'] == [] and frozen['passed'] is False,
            'Linux reference input was not frozen before execution')
    root = Path(frozen['reference_chroot'])
    original_output = Path(runtime.destination(frozen['reference_output']))
    require(str(root) == runtime.destination(str(root)) and root.name == 'root'
            and root.parent.parent == original_output
            and re.fullmatch(r'a04-full-linux-[A-Za-z0-9_-]+', root.parent.name) is not None
            and receipt['reference_chroot'] == str(root)
            and receipt['reference_output'] == str(original_output),
            'Linux reference did not use its owned temporary chroot')
    require(evaluate_cases(receipt['cases'])['cases_passed'], 'Linux full case list is incomplete')
    for case, recorded in zip(profile['cases'], receipt['cases']):
        child = directory / 'cases' / case['id']
        require(recorded['process_group_cleanup_completed'] is True, 'Linux case cleanup incomplete')
        invocation = strict_json(read_pinned(child / 'input.json', recorded['frozen_case_input_sha256']))
        require(invocation == reference_invocation(root, case),
                'Linux case invocation differs from the fixed profile')
        code = recorded['process_exit']
        require(type(code) is int and read_file(child / 'exit-code.txt', 64) == (str(code) + '\n').encode(),
                'Linux actual exit record differs')
        stdout = read_pinned(child / 'stdout.log', recorded['stdout_sha256'], MAX_CASE_BYTES)
        stderr = read_pinned(child / 'stderr.log', recorded['stderr_sha256'], MAX_CASE_BYTES)
        actual = evaluate_case(case, stdout, stderr, code, recorded['timed_out'])
        require(actual['passed'] and all(recorded[key] == value for key, value in actual.items()),
                'Linux original raw observation differs')
    return sha(raw)


def evaluate_guest(raw, code, timed_out, profile):
    text = re.sub(r'\x1b\[[0-9;]*m', '', raw.decode(errors='replace'))
    active, chunks, cases, anomalies, endings = None, {}, [], [], []
    encoded_sizes, overflow = {}, set()
    complete, process, boot = [], [], []
    by_name = {case['id']: case for case in profile['cases']}
    for index, line in enumerate(text.splitlines()):
        if line.startswith('A04_FULL_BEGIN='):
            name = line.partition('=')[2]
            if (active is not None or name not in by_name or len(cases) >= CASE_COUNT
                    or name != CASE_ORDER[len(cases)] or complete or process):
                anomalies.append('unexpected or out-of-order case begin')
                continue
            active, chunks = name, {'stdout': [], 'stderr': []}
            encoded_sizes, overflow = {'stdout': 0, 'stderr': 0}, set()
        elif line.startswith(('A04_FULL_STDOUT=', 'A04_FULL_STDERR=')):
            match = re.fullmatch(r'A04_FULL_(STDOUT|STDERR)=([a-z0-9_.]+):([A-Za-z0-9+/=]+)', line)
            if match is None or match[2] != active or active is None:
                anomalies.append('unmatched or malformed application byte frame')
                continue
            channel = match[1].lower()
            if channel in overflow:
                continue
            encoded_sizes[channel] += len(match[3])
            if encoded_sizes[channel] > ((MAX_CASE_BYTES + 2) // 3) * 4:
                overflow.add(channel)
                anomalies.append('application byte frame exceeds bound')
                continue
            chunks[channel].append(match[3])
        elif line.startswith('A04_FULL_END='):
            match = re.fullmatch(r'A04_FULL_END=([a-z0-9_.]+):(\d+):(\d+):([0-9a-f]{64}):(\d+):([0-9a-f]{64})', line)
            if match is None or match[1] != active or active is None:
                anomalies.append('unmatched or malformed case end')
                continue
            try:
                require(not overflow, 'case has over-bound application byte frames')
                stdout = base64.b64decode(''.join(chunks['stdout']), validate=True)
                stderr = base64.b64decode(''.join(chunks['stderr']), validate=True)
                require(len(stdout) == int(match[3]) and sha(stdout) == match[4]
                        and len(stderr) == int(match[5]) and sha(stderr) == match[6],
                        'application frame bytes or hashes differ')
                cases.append(evaluate_case(by_name[active], stdout, stderr, int(match[2]), False))
            except (ValueError, base64.binascii.Error) as error:
                anomalies.append(str(error))
            endings.append(index)
            active = None
        elif line.startswith('A04_FULL_COMPLETE='):
            complete.append((index, line))
        elif line.startswith('A04_FULL_PROCESS_EXIT='):
            process.append((index, line))
        elif line.startswith('A04_FULL_'):
            anomalies.append('unknown or malformed profile marker')
        if line == common.BOOT_MARKER:
            boot.append(index)
    result = evaluate_cases(cases)
    exact = (len(complete) == len(process) == len(boot) == 1 and active is None
             and complete[0][1] == 'A04_FULL_COMPLETE=32:0'
             and process[0][1] == 'A04_FULL_PROCESS_EXIT=0'
             and len(endings) == CASE_COUNT and max(endings) < complete[0][0] < process[0][0] < boot[0])
    no_panic = not re.search(r'(?i)kernel panic|panicked at|fatal exception|uncaught panic', text)
    observed_exit = (re.fullmatch(r'A04_FULL_PROCESS_EXIT=(\d+)', process[0][1])
                     if len(process) == 1 else None)
    result.update(cases=cases, anomalies=anomalies, exact_ordered_completion=exact,
                  no_kernel_panic=no_panic, qemu_exit=code, timed_out=timed_out,
                  process_exit=int(observed_exit[1]) if observed_exit else None,
                  passed=type(code) is int and code == 33 and timed_out is False
                  and result['cases_passed'] and exact and no_panic and not anomalies)
    return result


def run_guest(args, out, report):
    inputs, profile, _, image = load_bundle(args.bundle, args.expected_input_sha256)
    require((inputs['source_head'], inputs['source_tree'])
            == (args.expected_source_head, args.expected_source_tree),
            'build bundle source differs from reviewed product source')
    reference_sha = load_reference(args.linux_reference, args.expected_input_sha256,
                                   profile, inputs['image_sha256'])
    kernel, product_sha = common.product_input(args.product_evidence, args.expected_source_head,
                                               args.expected_source_tree)
    bios = read_pinned(args.bios, common.BIOS_SHA, 2 * 1024 * 1024)
    qemu = inspect_tool(args.qemu)
    require(qemu['sha256'] == inputs['tools']['qemu']['sha256'],
            'QEMU bytes differ from the pre-Linux frozen build tool')
    version = subprocess.check_output([qemu['path'], '--version'], timeout=10).decode()
    require(version.startswith('QEMU emulator version 8.2.2 '), 'unreviewed QEMU version')
    files = (('kernel.elf', kernel), ('bios.bin', bios), ('full-initramfs.cpio.gz', image))
    for name, data in files:
        (out / name).write_bytes(data)
    command = [qemu['path'], '-kernel', str(out / 'kernel.elf'), '-initrd', str(out / 'full-initramfs.cpio.gz'),
               '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
               '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(out / 'bios.bin'),
               '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot',
               '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
               '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    report.update(input_sha256=args.expected_input_sha256, image_sha256=sha(image), kernel_sha256=sha(kernel),
                  source_head=args.expected_source_head, source_tree=args.expected_source_tree,
                  product_receipt_sha256=product_sha, linux_reference_receipt_sha256=reference_sha,
                  qemu_sha256=qemu['sha256'], qemu_version=version, qemu_argv=command)
    (out / 'input.json').write_bytes(json_bytes(report))
    start, code, timed_out = time.monotonic(), None, False
    with (out / 'serial.log').open('xb') as log:
        try:
            code = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=args.timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    report.update(qemu_exit=code, timed_out=timed_out, elapsed_seconds=time.monotonic() - start)
    raw = read_file(out / 'serial.log', MAX_SERIAL_BYTES)
    report.update(serial_sha256=sha(raw), serial_bytes=len(raw))
    report.update(evaluate_guest(raw, code, timed_out, profile))
    for name, data in files:
        require(read_file(out / name, MAX_IMAGE_BYTES) == data, 'guest input changed: ' + name)
    load_bundle(args.bundle, args.expected_input_sha256)
    require(load_reference(args.linux_reference, args.expected_input_sha256, profile, inputs['image_sha256'])
            == reference_sha, 'Linux reference changed during guest execution')
    require(inspect_tool(args.qemu)['sha256'] == qemu['sha256'], 'QEMU changed during guest execution')
    require(common.product_input(args.product_evidence, args.expected_source_head,
                                 args.expected_source_tree) == (kernel, product_sha),
            'ordinary product evidence changed during guest execution')
    report['runtime_inputs_unchanged'] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    build = commands.add_parser('build', help='Freeze compiled ELF and complete runtime; do not execute workloads')
    build.add_argument('--a01-initramfs', type=Path, required=True)
    build.add_argument('--qemu', default='qemu-system-x86_64')
    reference = commands.add_parser('reference', help='Execute the complete frozen image on original Linux')
    guest = commands.add_parser('guest', help='Execute the same frozen image on the ordinary candidate kernel')
    guest.add_argument('--linux-reference', type=Path, required=True)
    guest.add_argument('--product-evidence', type=Path, required=True)
    guest.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    guest.add_argument('--qemu', default='qemu-system-x86_64')
    guest.add_argument('--timeout', type=int, default=1500)
    for command in (build, guest):
        command.add_argument('--expected-source-head', required=True)
        command.add_argument('--expected-source-tree', required=True)
    for command in (reference, guest):
        command.add_argument('--bundle', type=Path, required=True)
        command.add_argument('--expected-input-sha256', required=True)
    for command in (build, reference, guest):
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.resolve()
    require(not out.is_relative_to(ROOT) and not out.exists() and not out.is_symlink(),
            'output must be a new directory outside the source checkout')
    if args.mode == 'guest':
        require(type(args.timeout) is int and 1 <= args.timeout <= 1800, 'guest timeout must be 1..1800')
    os.umask(0o022)
    out.mkdir(parents=True, mode=0o755, exist_ok=False)
    sources_before = {path: sha(read_file(ROOT / path, 1024 * 1024)) for path in SOURCE_PATHS}
    report = {'schema': 'a04.ubuntu-full-' + args.mode + '.v1', 'profile': PROFILE,
              'passed': False, 'required_cases': CASE_COUNT,
              'pinned_debian13_qualification': False, 'original_hepta_w1_qualification': False,
              'storage_power_loss_qualification': False, 'source_files': sources_before}
    try:
        {'build': run_build, 'reference': run_reference, 'guest': run_guest}[args.mode](args, out, report)
        require({path: sha(read_file(ROOT / path, 1024 * 1024)) for path in SOURCE_PATHS} == sources_before,
                'runner/source bytes changed during stage')
        report['source_inputs_unchanged'] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, groups.GateError) as error:
        report.update(passed=False, error=type(error).__name__ + ': ' + str(error))
    (out / 'result.json').write_bytes(json_bytes(report))
    print(json.dumps({key: report[key] for key in
                     ('profile', 'passed', 'input_sha256', 'passed_cases', 'observed_cases',
                      'qemu_exit', 'timed_out', 'error') if key in report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
