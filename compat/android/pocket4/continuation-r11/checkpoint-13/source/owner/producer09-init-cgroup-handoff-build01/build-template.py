"""One create-only diagnostic DSO build; no Android/namespace/deployment action."""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import time
import traceback

CFG = None  # Filled once by the local frozen-request generator.


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def create(path, data, mode=0o444):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def snapshot(path, expected=None, root_tool=False):
    path = Path(path)
    resolved = path.resolve(strict=True)
    fd = os.open(resolved, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= 200 * 1024 * 1024,
                'input not a bounded regular file: ' + str(path))
        if root_tool:
            require(before.st_uid == 0 and before.st_gid == 0 and not (before.st_mode & 0o6022),
                    'host compiler/inspector ownership/mode changed')
            try:
                capability = os.getxattr(fd, 'security.capability')
            except OSError as error:
                if error.errno not in (61, 95):
                    raise
                capability = None
            require(not capability, 'host tool has file capabilities')
        value = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            value.update(chunk)
        after = os.fstat(fd)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode, s.st_uid, s.st_gid)
        require(stamp(before) == stamp(after), 'input changed while reading')
        require(path.resolve(strict=True) == resolved and stamp(os.stat(resolved, follow_symlinks=False)) == stamp(after),
                'input name changed while reading')
        result = {'path': str(path), 'resolved_path': str(resolved), 'device': after.st_dev,
                  'inode': after.st_ino, 'bytes': after.st_size, 'sha256': value.hexdigest(),
                  'mode': after.st_mode, 'uid': after.st_uid, 'gid': after.st_gid,
                  'mtime_ns': after.st_mtime_ns, 'ctime_ns': after.st_ctime_ns}
        if expected is not None:
            require(result['bytes'] == expected['bytes'] and result['sha256'] == expected['sha256'],
                    'externally pinned input differs: ' + str(path))
        return result
    finally:
        os.close(fd)


def dependencies(path, expected_target):
    text = path.read_text('utf-8')
    require(len(text.encode()) < 262144 and ': ' in text, 'invalid dependency file')
    target, payload = text.replace('\\\n', ' ').split(': ', 1)
    require(target.strip() == expected_target, 'unexpected dependency target')
    names = shlex.split(payload)
    require(names and len(names) == len(set(names)), 'empty/repeated dependencies')
    require(all(Path(name).is_absolute() for name in names), 'relative dependency')
    return set(names)


def command(report, root, argv, timeout=25):
    index = len(report['commands'])
    output = root / ('command%02d.stdout' % index)
    error_path = root / ('command%02d.stderr' % index)
    record = {'argv': argv, 'cwd': str(root), 'timeout_seconds': timeout,
              'timed_out': False, 'child_reaped': False}
    report['commands'].append(record)
    process = None
    pidfd = None
    with output.open('xb') as stdout, error_path.open('xb') as stderr:
        try:
            process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, close_fds=True, start_new_session=True,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C',
                     'TMPDIR': str(root / 'tmp'), 'PYTHONDONTWRITEBYTECODE': '1'})
            pidfd = os.pidfd_open(process.pid, 0)
            record['pid'] = process.pid
            try:
                record['returncode'] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record['timed_out'] = True
                signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                record['returncode'] = process.wait(timeout=5)
            record['child_reaped'] = True
        finally:
            if process is not None and process.poll() is None:
                if pidfd is not None:
                    signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    process.wait(timeout=5)
                    record['child_reaped'] = True
            if pidfd is not None:
                os.close(pidfd)
    for key, path in [('stdout', output), ('stderr', error_path)]:
        require(path.stat().st_size <= 1048576, 'command output exceeds bound')
        data = path.read_bytes()
        record[key] = data.decode('utf-8')
        record[key + '_sha256'] = digest(data)
    require(record.get('returncode') == 0 and record['child_reaped'] and not record['timed_out'],
            'matching build/control command failed: ' + str(index))
    return record


def main():
    require(CFG['kind'] == 'p4-init-cgroup-handoff-build01', 'wrong controller kind')
    guard = base64.b64decode(CFG['resource_guard']['base64'], validate=True)
    require(digest(guard) == CFG['resource_guard']['sha256'], 'resource source pin differs')
    namespace = {'__name__': 'frozen_resource_guard'}
    exec(compile(guard, '<exact-resource-guard>', 'exec'), namespace)
    resources = namespace['OwnJobResources'](536870912)
    root = Path(CFG['root'])
    report = {'schema': 1, 'kind': CFG['kind'], 'success': False, 'commands': [], 'errors': [],
              'root': str(root), 'source_manifest_sha256': CFG['source_manifest_sha256'],
              'original_input_closure_sha256': CFG['original_input_closure_sha256'],
              'resource_health': resources.record, 'Android_constructor_executed': False,
              'Android_runtime_qualified': False, 'namespace_mount_or_pressure_executed': False,
              'installed_files_changed': False, 'source_snapshot_reused': False}
    created = False
    try:
        require(os.geteuid() == 0 and os.getegid() == 0, 'root-owned sealed build required')
        resources.begin()
        require(root.parent == Path('/opt') and root.name == 'p4-init-cgroup-handoff-20261105-build-01',
                'unexpected create-only root')
        for parent in (Path('/'), root.parent):
            meta = parent.lstat()
            require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and meta.st_gid == 0 and
                    not (meta.st_mode & 0o22), 'unsafe protected build parent')
        root.mkdir(mode=0o755)
        created = True
        (root / 'source').mkdir(mode=0o755)
        (root / 'tmp').mkdir(mode=0o700)
        create(root / 'claim.json', (json.dumps({'kind': CFG['kind'], 'source_manifest_sha256': CFG['source_manifest_sha256']}, sort_keys=True) + '\n').encode())
        for name, spec in CFG['payload'].items():
            require('/' not in name and name not in ('.', '..'), 'unsafe source leaf')
            data = base64.b64decode(spec['base64'], validate=True)
            require(len(data) == spec['bytes'] and digest(data) == spec['sha256'], 'source payload differs')
            create(root / 'source' / name, data)
        source_before = {name: snapshot(root / 'source' / name, spec) for name, spec in CFG['payload'].items()}
        original_before = {path: snapshot(path, expected) for path, expected in CFG['original_inputs'].items()}
        tool_before = {path: snapshot(path, root_tool=True) for path in ['/usr/bin/cc', '/usr/bin/readelf']}
        report.update(source_before=source_before, original_inputs_before=original_before, host_tools_before=tool_before)
        old_root = CFG['original_root']
        remap = lambda arg: arg.replace(old_root, str(root))
        android = [[remap(arg) for arg in argv] for argv in CFG['original_android_argv']]
        command(report, root, android[0])
        preflight = dependencies(root / 'preflight.d', 'barrier.o')
        expected_dependencies = {remap(path) for path in CFG['original_inputs'] if path not in CFG['non_MD_inputs']}
        require(preflight == expected_dependencies, 'Android preflight differs from exact original header closure')
        android_before = {path: snapshot(path) for path in sorted(preflight)}
        command(report, root, android[1])
        require(dependencies(root / 'barrier.d', str(root / 'barrier.o')) == preflight, 'actual Android MD differs')
        command(report, root, android[2])
        elf = command(report, root, android[3])['stdout']
        needed = re.findall(r'\(NEEDED\).*\[([^\]]+)\]', elf)
        require(needed == ['libc.so'] and '(INIT_ARRAY)' in elf and
                'droidloom_init_relay_barrier_abi@@DROIDLOOM_INIT_RELAY_1' in elf and
                'Advanced Micro Devices X86-64' in elf, 'Android DSO contract differs')
        report['Android_artifact'] = snapshot(root / 'libdroidloom_init_relay.so')
        report['Android_needed'] = needed
        report['Android_actual_MD_equals_preflight'] = True
        report['Android_input_count'] = len(preflight)
        results = []
        for name, source, seam, expected_count, marker in [
            ('protocol', 'protocol_controls.c', False, 20, 'owned_controls_passed'),
            ('protocol-close-errno', 'protocol_controls.c', True, 20, 'owned_controls_passed'),
            ('diagnostic', 'diagnostic_controls.c', False, 7, 'owned_diagnostic_controls_passed'),
            ('cgroup-view', 'cgroup_view_controls.c', False, 8, 'cases')]:
            flags = ['/usr/bin/cc', '-std=c17', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
            if seam:
                flags += ['-include', str(root / 'source' / 'close_errno_seam.h')]
            source_path = str(root / 'source' / source)
            dep_path = root / (name + '.preflight.d')
            command(report, root, flags + ['-M', '-MF', str(dep_path), '-MT', 'barrier.o', source_path])
            headers = dependencies(dep_path, 'barrier.o')
            headers_before = {path: snapshot(path) for path in sorted(headers)}
            actual_md = root / (name + '.actual.d')
            command(report, root, flags + ['-MD', '-MF', str(actual_md), '-MT', 'barrier.o', source_path, '-o', str(root / name)])
            require(dependencies(actual_md, 'barrier.o') == headers, 'host MD closure differs')
            artifact = snapshot(root / name)
            result = command(report, root, [str(root / name)])
            records = [json.loads(line) for line in result['stdout'].splitlines()]
            require(len(records) == expected_count + 1 and all(item.get('ok') is True for item in records) and
                    records[-1].get(marker) == expected_count, 'owned controls result set differs')
            require(snapshot(root / name) == artifact, 'test artifact changed')
            require({path: snapshot(path) for path in headers_before} == headers_before, 'host header/source changed')
            results.append({'name': name, 'passed': expected_count, 'artifact': artifact, 'headers': headers_before})
        report['host_control_results'] = results
        require({path: snapshot(path) for path in android_before} == android_before, 'Android MD inputs changed')
        require({path: snapshot(path, expected) for path, expected in CFG['original_inputs'].items()} == original_before,
                'original compiler/link closure changed')
        require({name: snapshot(root / 'source' / name, spec) for name, spec in CFG['payload'].items()} == source_before,
                'frozen payload changed')
        require({path: snapshot(path, root_tool=True) for path in tool_before} == tool_before, 'host tool changed')
        report['all_inputs_unchanged'] = True
        report['success'] = True
    except Exception as error:
        report['errors'].append({'error': repr(error), 'traceback': traceback.format_exc()})
    finally:
        try:
            resources.finish()
        except Exception as error:
            report['errors'].append({'resource_error': repr(error), 'traceback': traceback.format_exc()})
        try:
            resources.close()
        except Exception as error:
            report['errors'].append({'resource_close_error': repr(error)})
    report['success'] = report['success'] and not report['errors'] and resources.record['held_own_cgroup_gate_passed']
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    if created:
        output = root / 'build-result.json'
        create(output, raw)
        print(json.dumps({'success': report['success'], 'path': str(output), 'bytes': len(raw), 'sha256': digest(raw),
                          'error': report['errors'][0]['error'] if report['errors'] and 'error' in report['errors'][0] else None}))
    else:
        print(raw.decode(), end='')
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
