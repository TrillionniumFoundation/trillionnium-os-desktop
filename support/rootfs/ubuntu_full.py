#!/usr/bin/env python3
"""Capture actual Ubuntu 24.04 Python/OpenSSL/ELF runtime bytes for A04.

This creates a new profile. It never changes the historical Debian 13 pins.
The subsequent real Linux chroot run is required: ldd alone does not establish
that Python imports, NSS, providers, TLS or workload behavior are complete.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_ROOTFS_BYTES = 192 * 1024 * 1024
PYTHON = Path('/usr/bin/python3.12')
STDLIB = Path('/usr/lib/python3.12')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def destination(value):
    require(isinstance(value, str) and value.startswith('/') and value != '/'
            and PurePosixPath(value).as_posix() == value
            and all(part not in ('', '.', '..') for part in value[1:].split('/'))
            and '\\' not in value and '\x00' not in value, 'unsafe runtime path')
    return value


def tool_output(arguments, *, allow_failure=False):
    # These are installed, trusted metadata tools, not workload launchers.
    # Workload, compiler and cargo lifecycles use the maintained ChildGroup.
    process = subprocess.run(arguments, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=20)
    require(len(process.stdout) <= 1024 * 1024 and len(process.stderr) <= 1024 * 1024,
            'metadata tool output exceeds bound')
    if not allow_failure:
        require(process.returncode == 0,
                'metadata command failed: ' + repr(arguments) + ': '
                + process.stderr.decode(errors='replace')[-800:])
    return process.returncode, process.stdout.decode('utf-8', errors='strict')


def package_versions():
    names = ('gcc-13', 'libc6', 'libc6-dev', 'libsqlite3-0', 'libsqlite3-dev',
             'python3.12', 'python3.12-minimal', 'libpython3.12-stdlib',
             'openssl', 'ca-certificates', 'tzdata')
    result = {}
    for name in names:
        code, version = tool_output(['/usr/bin/dpkg-query', '-W', '-f=${Version}', name],
                                    allow_failure=True)
        require(code == 0 and version.strip(), 'required Ubuntu package missing: ' + name)
        result[name] = version.strip()
    return result


def elf_metadata(path):
    _, program = tool_output(['/usr/bin/readelf', '-l', str(path)])
    _, dynamic = tool_output(['/usr/bin/readelf', '-d', str(path)])
    interpreter = re.search(r'Requesting program interpreter:\s*([^]]+)', program)
    interpreter = interpreter.group(1) if interpreter else None
    needed = re.findall(r'Shared library: \[([^]]+)\]', dynamic)
    dependencies = set()
    if interpreter:
        dependencies.add(destination(interpreter))
    # Python extension/provider DSOs have DT_NEEDED but no PT_INTERP.
    # Skipping their ldd closure would silently omit libssl/libcrypto, etc.
    if needed or interpreter:
        _, listing = tool_output(['/usr/bin/ldd', str(path)])
        require('not found' not in listing, 'unresolved runtime dependency: ' + str(path))
        dependencies.update(destination(value) for value in
                            re.findall(r'(?:=>\s*)?(/[^\s(]+)\s*\(', listing))
    return {'interpreter': interpreter, 'needed': needed,
            'dependencies': sorted(dependencies)}


def capture(root, binaries, worker, legacy):
    """Copy regular runtime bytes only, preserving every source digest."""
    root = Path(root)
    require(not root.exists() and not root.is_symlink(), 'runtime directory already exists')
    root.mkdir(parents=True, mode=0o755)
    records, elf_records, sources, total = {}, {}, {}, 0

    def add(name, source=None, data=None, role='runtime'):
        nonlocal total
        name = destination(name)
        if source is not None:
            source = Path(source)
            resolved = source.resolve(strict=True)
            require(resolved.is_file() and resolved.stat().st_size <= MAX_FILE_BYTES,
                    'runtime source is absent, special or too large: ' + str(source))
            data = resolved.read_bytes()
            origin = {'path': str(source), 'resolved_path': str(resolved),
                      'sha256': sha(data)}
            sources[str(resolved)] = sha(data)
        else:
            require(isinstance(data, bytes), 'generated runtime bytes required')
            origin = {'generated': True}
        digest = sha(data)
        if name in records:
            require(records[name]['sha256'] == digest, 'conflicting runtime dependency: ' + name)
            return
        is_elf = data.startswith(b'\x7fELF')
        if is_elf:
            require(data[:6] == b'\x7fELF\x02\x01' and data[18:20] == b'\x3e\x00',
                    'runtime ELF is not little-endian x86_64: ' + name)
        mode = 0o555 if is_elf else 0o444
        total += len(data)
        require(total <= MAX_ROOTFS_BYTES, 'runtime exceeds bounded image budget')
        target = root / name[1:]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(mode)
        records[name] = {'path': name, 'sha256': digest, 'bytes': len(data),
                         'mode': mode, 'role': role, 'origin': origin}
        if is_elf:
            require(source is not None, 'ELF source provenance missing')
            elf_records[name] = {'source': str(source), 'sha256': digest}

    for name, path in binaries.items():
        add('/usr/local/bin/a04/' + name, path, role='workload_elf')
    add(str(PYTHON), PYTHON, role='python_interpreter')
    add('/usr/bin/openssl', '/usr/bin/openssl', role='openssl_cli')
    require(STDLIB.is_dir(), 'fixed distro Python stdlib missing')
    for path in sorted(STDLIB.rglob('*')):
        relative = path.relative_to(STDLIB)
        if ('__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo')
                or relative.parts[0].startswith('config-')):
            continue
        if path.is_dir():
            require(not path.is_symlink(), 'symlinked Python runtime directory is not supported')
            continue
        # Broken development-only libpython links are not runtime file bytes.
        if path.is_symlink() and not path.exists():
            require(relative.parts[0].startswith('config-'), 'broken runtime symlink: ' + str(path))
            continue
        require(path.is_file(), 'special Python runtime file: ' + str(path))
        add(str(path), path, role='python_stdlib')
    for directory in ('/usr/lib/x86_64-linux-gnu/ossl-modules',
                      '/usr/lib/x86_64-linux-gnu/engines-3'):
        source = Path(directory)
        if source.is_dir():
            for path in sorted(source.glob('*.so')):
                add(str(path), path, role='openssl_module')
    for path in ('/lib/x86_64-linux-gnu/libnss_dns.so.2',
                 '/lib/x86_64-linux-gnu/libnss_files.so.2'):
        add(path, path, role='nss')
    for path, role in (('/etc/ssl/certs/ca-certificates.crt', 'public_ca'),
                       ('/etc/ssl/openssl.cnf', 'openssl_configuration'),
                       ('/usr/share/zoneinfo/UTC', 'timezone')):
        add(path, path, role=role)
    # Also retain OpenSSL's compiled default paths, not only environment aliases.
    add('/usr/lib/ssl/cert.pem', '/etc/ssl/certs/ca-certificates.crt', role='public_ca')
    add('/usr/lib/ssl/openssl.cnf', '/etc/ssl/openssl.cnf', role='openssl_configuration')
    add('/usr/local/lib/a04/full_python_case.py', worker, role='python_case_dispatch')
    add('/usr/local/lib/a04/run.py', legacy, role='unchanged_python_workloads')
    generated = {
        '/etc/passwd': b'root:x:0:0:root:/root:/bin/sh\nnobody:x:65534:65534:nobody:/tmp:/bin/sh\n',
        '/etc/group': b'root:x:0:\nnogroup:x:65534:\n',
        '/etc/hosts': b'127.0.0.1 localhost\n::1 localhost\n',
        '/etc/nsswitch.conf': b'passwd: files\ngroup: files\nhosts: files dns\nnetworks: files\n',
        '/etc/resolv.conf': b'nameserver 127.0.0.1\noptions timeout:1 attempts:1\n',
    }
    for name, data in generated.items():
        add(name, data=data, role='synthetic_configuration')

    pending = list(elf_records)
    examined = set()
    while pending:
        name = pending.pop(0)
        if name in examined:
            continue
        metadata = elf_metadata(Path(elf_records[name]['source']))
        elf_records[name].update(metadata)
        examined.add(name)
        for dependency in metadata['dependencies']:
            add(dependency, dependency, role='elf_dependency')
            if dependency in elf_records and dependency not in examined:
                pending.append(dependency)
    for path, digest in sources.items():
        require(sha(Path(path).read_bytes()) == digest, 'host runtime changed while capturing: ' + path)
    return {'schema': 'a04.ubuntu-full-rootfs.v1', 'file_count': len(records),
            'regular_bytes': total, 'files': [records[key] for key in sorted(records)],
            'elf': {key: elf_records[key] for key in sorted(elf_records)},
            'host_sources_unchanged': True, 'guest_execution_verified': False}


def verified_files(root, manifest):
    """Return only exact manifest bytes; reject additions, aliases and drift."""
    require(manifest.get('schema') == 'a04.ubuntu-full-rootfs.v1', 'unknown runtime manifest')
    expected = {}
    for record in manifest['files']:
        name = destination(record['path'])
        require(name not in expected and record['mode'] in (0o444, 0o555),
                'duplicate runtime path or invalid mode')
        expected[name] = record
    require(len(expected) == manifest['file_count'], 'runtime count differs')
    actual = {}
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'runtime tree contains a symlink')
        if path.is_dir():
            continue
        require(path.is_file(), 'runtime tree contains a special file')
        actual['/' + path.relative_to(root).as_posix()] = path
    require(set(actual) == set(expected), 'runtime file set differs')
    result = {}
    for name, path in actual.items():
        record, data = expected[name], path.read_bytes()
        require(len(data) == record['bytes'] and sha(data) == record['sha256']
                and path.stat().st_mode & 0o777 == record['mode'], 'runtime drift: ' + name)
        result[name] = (record['mode'], data)
    require(sum(len(data) for _, data in result.values()) == manifest['regular_bytes'],
            'runtime total bytes differ')
    return result
