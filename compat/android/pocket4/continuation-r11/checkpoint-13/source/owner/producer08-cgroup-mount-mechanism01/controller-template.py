#!/usr/bin/env python3
"""One create-only, bounded host kernel control; no Android or installed change."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import sys
import traceback
import types

CFG = None


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def observe(fd):
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0 and
         not before.st_mode & 0o6022 and 0 < before.st_size <= 128 * 1024 * 1024,
         'root-owned bounded nonprivileged regular input required')
    h = hashlib.sha256(); offset = 0
    while True:
        part = os.pread(fd, 65536, offset)
        if not part:
            break
        h.update(part); offset += len(part)
        need(offset <= before.st_size, 'held input grew')
    need(offset == before.st_size and stamp(before) == stamp(os.fstat(fd)), 'held input changed')
    return dict(zip(('device', 'inode', 'mode', 'uid', 'gid', 'nlink', 'bytes', 'mtime_ns', 'ctime_ns'),
                    stamp(before)), sha256=h.hexdigest())


def open_tool(expected):
    need(os.path.realpath(expected['path']) == expected['resolved_path'], 'bound compiler/tool resolution changed')
    fd = os.open(expected['resolved_path'], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        actual = observe(fd)
        need(all(actual[k] == expected[k] for k in actual if k != 'nlink'), 'actual matching-build tool changed')
        try:
            caps = os.getxattr(fd, 'security.capability')
        except OSError as error:
            need(error.errno in (61, 95), 'tool capability read failed')
        else:
            need(not caps, 'privileged tool rejected')
        return fd, actual
    except BaseException:
        os.close(fd)
        raise


def write_new(path, data, mode=0o444):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            need(n > 0, 'short fresh write')
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def note(report, stage, error):
    row = {'stage': stage, 'error': repr(error), 'traceback': traceback.format_exc()}
    if report['first_error'] is None:
        report['first_error'] = row
    report['errors'].append(row)
    report['success'] = False


def command(report, root, argv, executable_fd, pass_fds=(), timeout=20):
    record = {'argv': argv, 'timeout_seconds': timeout, 'timed_out': False, 'child_reaped': False,
              'owned_process_group_killed': False}
    index = len(report['commands']); report['commands'].append(record)
    out = root / ('command%02d.stdout' % index); err = root / ('command%02d.stderr' % index)
    process = None; pidfd = None
    with out.open('xb') as stdout, err.open('xb') as stderr:
        try:
            process = subprocess.Popen(argv, executable='/proc/self/fd/%d' % executable_fd,
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, cwd=root,
                close_fds=True, pass_fds=tuple(set((executable_fd, *pass_fds))), start_new_session=True,
                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C',
                     'TMPDIR': str(root / 'tmp'), 'PYTHONDONTWRITEBYTECODE': '1'})
            pidfd = os.pidfd_open(process.pid); record['pid'] = process.pid
            try:
                record['returncode'] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record['timed_out'] = True
                # This is the new, still-unreaped child session from Popen;
                # its PID cannot recycle before wait. No unrelated group is used.
                need(os.getsid(process.pid) == process.pid and os.getpgid(process.pid) == process.pid,
                     'owned child session changed before timeout cleanup')
                os.killpg(process.pid, signal.SIGKILL); record['owned_process_group_killed'] = True
                record['returncode'] = process.wait(timeout=3)
            record['child_reaped'] = True
        finally:
            if process is not None and process.returncode is None:
                # No poll/wait has reaped this child on this path.
                need(os.getsid(process.pid) == process.pid and os.getpgid(process.pid) == process.pid,
                     'owned child session changed before error cleanup')
                os.killpg(process.pid, signal.SIGKILL); record['owned_process_group_killed'] = True
                record['returncode'] = process.wait(timeout=3); record['child_reaped'] = True
            if pidfd is not None:
                os.close(pidfd)
    for key, path in [('stdout', out), ('stderr', err)]:
        need(path.stat().st_size <= 1048576, 'bounded command output exceeded')
        data = path.read_bytes(); record[key] = data.decode('utf-8'); record[key + '_sha256'] = sha(data)
    need(record.get('returncode') == 0 and record['child_reaped'] and not record['timed_out'],
         'owned command failed: %d' % index)
    return record


def dependencies(path, source):
    text = path.read_text('utf-8')
    need(len(text.encode()) < 262144 and ': ' in text, 'invalid bounded dependency file')
    target, payload = text.replace('\\\n', ' ').split(': ', 1)
    need(target.strip() == 'probe', 'dependency target changed')
    names = shlex.split(payload)
    need(1 <= len(names) <= 512 and len(names) == len(set(names)), 'invalid dependency set')
    need(str(source) in names, 'probe missing from dependency closure')
    need(all(Path(n).is_absolute() and (n == str(source) or n.startswith('/usr/')) for n in names),
         'dependency outside fixed source and packaged headers')
    return sorted(names)


def inputs(names):
    result = {}
    for name in names:
        resolved = os.path.realpath(name)
        fd = os.open(resolved, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            result[name] = dict(observe(fd), resolved_path=resolved)
        finally:
            os.close(fd)
    return result


def main():
    report = {'schema': 1, 'kind': 'owned-cgroup-repeat-mount-mechanism01', 'success': False,
              'first_error': None, 'errors': [], 'commands': [], 'Android_executed': False,
              'Main_modified': False, 'host_network_modified': False, 'production_qualified': False,
              'probe_nonce': CFG['nonce'], 'actual_normal08_runtime_sha256': CFG['normal08_runtime_sha256']}
    root = Path(CFG['root']); created = False
    guard = main_fence = None; modules = {}; handles = {}; tool_before = {}; deps_before = None
    try:
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'root-only owned control')
        need(re.fullmatch('[0-9a-f]{32}', CFG['nonce']) and
             str(root) == '/opt/p4-cgroup-mount-mechanism-20261105-01', 'fixed profile changed')
        decoded = {}
        for name, item in CFG['sources'].items():
            need(name in ('probe.c', 'pinned_support.py', 'resource_guard.py'), 'unexpected source')
            raw = base64.b64decode(item['base64'], validate=True)
            need(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'source packet changed')
            decoded[name] = raw
        need(set(decoded) == {'probe.c', 'pinned_support.py', 'resource_guard.py'}, 'source set differs')
        for name in ('pinned_support.py', 'resource_guard.py'):
            module = types.ModuleType(name[:-3]); module.__file__ = str(root / 'source' / name)
            exec(compile(decoded[name], module.__file__, 'exec'), module.__dict__); modules[name] = module
        support = modules['pinned_support.py']; resources = modules['resource_guard.py']
        handles['python'] = support.current_interpreter(CFG['tools_sha256']['/usr/bin/python3'])
        handles['systemctl'] = support.pinned('/usr/bin/systemctl', CFG['tools_sha256']['/usr/bin/systemctl'], True)
        guard = resources.OwnJobResources(536870912); guard.begin()
        main_fence = support.MainFence({'main': CFG['main']}, support.__dict__)
        report['Main_before'] = main_fence.check()
        report['controller_user_namespace_before'] = list((lambda s: (s.st_dev, s.st_ino))(os.stat('/proc/self/ns/user')))
        need(report['controller_user_namespace_before'] == CFG['actual_normal08_user_namespace'],
             'original NORMAL08 user namespace differs')
        parent = os.open('/opt', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            s = os.fstat(parent); need(s.st_uid == s.st_gid == 0 and not s.st_mode & 0o022, 'unsafe /opt parent')
            os.mkdir(root.name, 0o700, dir_fd=parent); created = True
        finally:
            os.close(parent)
        for name in ('source', 'tmp', 'mountpoint'):
            os.mkdir(root / name, 0o700)
        for name, raw in decoded.items():
            write_new(root / 'source' / name, raw)
        write_new(root / 'once-claim.json', (json.dumps({'nonce': CFG['nonce'], 'sources':
            {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in decoded.items()}}, sort_keys=True) + '\n').encode())
        for name, expected in CFG['host_tools'].items():
            handles[name], tool_before[name] = open_tool(expected)
        compat = CFG['compat']; handles['compat'] = support.pinned(compat['path'], compat['sha256'])
        report['compat_before'] = observe(handles['compat'])
        symbols = command(report, root, ['/usr/bin/readelf', '--dyn-syms', '--wide',
            '/proc/self/fd/%d' % handles['compat']], handles['readelf'], (handles['compat'],), 10)
        selected = ('mount', '__mount', 'syscall', 'open_tree', 'move_mount')
        report['compat_selected_dynamic_symbols'] = [line.strip() for line in symbols['stdout'].splitlines()
            if line.split() and line.split()[-1].split('@')[0] in selected]
        source = root / 'source/probe.c'
        flags = ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror']
        command(report, root, ['/usr/bin/cc', *flags, '-M', '-MF', str(root / 'preflight.d'),
            '-MT', 'probe', str(source)], handles['cc'], timeout=15)
        dependency_names = dependencies(root / 'preflight.d', source)
        deps_before = inputs(dependency_names); report['dependencies_before'] = deps_before
        command(report, root, ['/usr/bin/cc', *flags, '-MD', '-MF', str(root / 'actual.d'),
            '-MT', 'probe', str(source), '-o', str(root / 'probe')], handles['cc'], timeout=25)
        need(dependencies(root / 'actual.d', source) == dependency_names, 'actual MD differs from preflight')
        report['actual_MD_equals_preflight'] = True
        os.chmod(root / 'probe', 0o500)
        handles['probe'] = os.open(root / 'probe', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        report['probe_before'] = observe(handles['probe'])
        need(report['probe_before']['nlink'] == 1, 'new owned probe must have one link')
        result = command(report, root, [str(root / 'probe'), str(os.getpid()), str(guard.fd)],
            handles['probe'], (guard.fd,), timeout=22)
        control = json.loads(result['stdout']); report['kernel_control'] = control
        need(control['nonce'] == CFG['nonce'] and control['success'] is True and control['Android_executed'] is False,
             'kernel mechanism control did not qualify')
        need(control['parent_user_namespace'] == control['child_user_namespace'] == CFG['actual_normal08_user_namespace'],
             'kernel control user namespace topology differs from NORMAL08')
        need(control['parent_mount_namespace'] != control['child_mount_namespace'] and
             control['parent_cgroup_namespace'] != control['child_cgroup_namespace'] and
             control['first_a'] == control['fresh_b'] == {'rc': 0, 'errno': 0} and
             control['repeat_a_recursiveprot'] == control['repeat_a_plain'] == {'rc': -1, 'errno': 16},
             'first/repeated/fresh cgroup mount outcomes differ')
        need(control['cgroup_controls_written'] is False and control['child_birth_ticks'] > 0 and
             control['child_begin']['monotonic_ns'] <= control['child_end']['monotonic_ns'],
             'mechanism identity, time or no-cgroup-write contract differs')
        for label in ('domain', 'first_target', 'fresh_target'):
            actual = control[label]
            need([actual['device'], actual['inode']] == guard.identity and
                 actual['uid'] == actual['gid'] == 0 and not actual['mode'] & 0o022,
                 'mounted view does not match held finite invocation cgroup')
        need(control['child_reaped'] and not control['forced_kill'] and control['child_wait_status'] == 0 and
             control['all_private_mounts_unmounted'] and control['inherited_domain_closed'],
             'owned mechanism cleanup incomplete')
        report['probe_after'] = observe(handles['probe']); need(report['probe_after'] == report['probe_before'], 'probe bytes changed')
        report['success'] = True
    except BaseException as error:
        note(report, 'kernel_control', error)
    finally:
        if deps_before is not None:
            try:
                report['dependencies_after'] = inputs(list(deps_before))
                need(report['dependencies_after'] == deps_before, 'dependency closure changed')
            except BaseException as error:
                note(report, 'dependency_final', error)
        for name, before in tool_before.items():
            try:
                need(observe(handles[name]) == before, 'held host tool changed')
                expected = CFG['host_tools'][name]
                need(os.path.realpath(expected['path']) == expected['resolved_path'] and
                     (os.stat(expected['resolved_path']).st_dev, os.stat(expected['resolved_path']).st_ino) ==
                     (before['device'], before['inode']), 'host tool pathname replaced')
            except BaseException as error:
                note(report, 'tool_final', error)
        if 'compat' in handles:
            try:
                report['compat_after'] = observe(handles['compat'])
                need(report['compat_after'] == report['compat_before'], 'bound compat artifact changed')
            except BaseException as error:
                note(report, 'compat_final', error)
        if main_fence is not None:
            try:
                report['Main_after'] = main_fence.check()
                report['controller_user_namespace_after'] = list((lambda s: (s.st_dev, s.st_ino))(os.stat('/proc/self/ns/user')))
                need(report['controller_user_namespace_after'] == report['controller_user_namespace_before'], 'controller user namespace changed')
            except BaseException as error:
                note(report, 'Main_final', error)
            finally:
                main_fence.close()
        if guard is not None:
            resources.finish_own_resource_gate(report, guard); report['resource_health'] = guard.record
            try:
                before, after = guard.record['before'], guard.record['after']
                need(after['pids_current'] <= before['pids_current'] and
                     set(after['direct_cgroup_procs']) <= set(before['direct_cgroup_procs']),
                     'new owned processes remain after all exact waits')
            except BaseException as error:
                note(report, 'owned_process_final', error)
        for fd in handles.values():
            os.close(fd)
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    if created:
        write_new(root / 'result.json', raw)
    print(json.dumps({'success': report['success'], 'result_path': str(root / 'result.json') if created else None,
                      'bytes': len(raw), 'sha256': sha(raw), 'result_gzip_base64':
                      base64.b64encode(gzip.compress(raw, mtime=0)).decode()}))
    return 0 if report['success'] and not report['errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
