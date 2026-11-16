#!/usr/bin/env python3
"""Revision of the existing frozen Native launcher with actual timeout admission."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

D = Path('/home/alex/work/pocket4-android-final/native/attempts/full-build-native597-8gib-hostreserve5-20261108-r1')
PACKET = D / 'build-packet.json'
RUNNER_SHA = '65564ce756f3a341def2cf34b2c0d54ef3e75960923c6002c4c56db13564ebf1'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def held(path, maximum):
    path = Path(path)
    for parent in path.parents:
        need(stat.S_ISDIR(parent.lstat().st_mode), 'real launcher input ancestors required')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and 0 < before.st_size <= maximum, 'bounded single-link launcher input required')
        raw = stream.read(maximum + 1)
        need(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
             == identity(path.lstat()), 'launcher input changed during observation')
    return raw, {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def acquire_parent_work_leases(works, native_work):
    need(len(works) == len(set(works)) == 3 and native_work in works,
         'exact Native, Framework and Audio lease topology')
    held_fds, fresh, parent = [], [], []
    try:
        for work in works:
            for ancestor in (work, *work.parents):
                need(stat.S_ISDIR(ancestor.lstat().st_mode), 'real work lease ancestors required')
            journal = work / 'source-projection.json'
            need(not journal.exists() and not journal.is_symlink(), 'source journal remains: ' + str(work))
            for name in ('package-build.lock', 'aosp-source-update.lock'):
                path = work / name
                fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
                held_fds.append(fd)
                info = os.fstat(fd)
                need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 4096
                     and identity(info) == identity(path.lstat()), 'parent work lease identity')
                need((info.st_dev, info.st_ino) not in {(row['identity'][0], row['identity'][1]) for row in fresh},
                     'six work lock names must not alias an inode')
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                content = os.pread(fd, 4097, 0)
                need(len(content) == info.st_size and identity(info) == identity(os.fstat(fd))
                     == identity(path.lstat()), 'parent work lease changed during acquisition')
                fresh.append({'path': str(path), 'identity': identity(info), 'observed_free': True})
                if work != native_work:
                    parent.append({'fd': fd, 'path': str(path), 'identity': identity(info),
                        'content_sha256': hashlib.sha256(content).hexdigest(), 'acquired_ns': time.time_ns()})
        need(len(held_fds) == 6 and len(parent) == 4, 'six fresh locks and four retained parent leases required')
        keep = {row['fd'] for row in parent}
        for fd in list(held_fds):
            if fd not in keep:
                held_fds.remove(fd)
                os.close(fd)
        return parent, fresh
    except BaseException:
        for fd in reversed(held_fds):
            os.close(fd)
        raise


def verify_parent_work_leases(leases):
    need(len(leases) == 4 and len({row['fd'] for row in leases}) == 4,
         'four distinct parent work descriptors required')
    for row in leases:
        fd, path = row['fd'], Path(row['path'])
        need(identity(os.fstat(fd)) == row['identity'] == identity(path.lstat()),
             'parent work lease inode or metadata changed: ' + str(path))
        need(fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC,
             'coordination descriptor must not be inherited by ordinary updater')
        need(hashlib.sha256(os.pread(fd, 4097, 0)).hexdigest() == row['content_sha256'],
             'parent work lease bytes changed: ' + str(path))


def release_parent_work_leases(leases, *, retirement_complete, source_restore_check_completed):
    need(retirement_complete and source_restore_check_completed,
         'parent leases cannot be explicitly released before retirement and restoration checking end')
    proof = {'rows': [], 'errors': [], 'all_parent_descriptors_closed': False,
             'remaining_parent_kernel_locks': [], 'qualified': False}
    try:
        verify_parent_work_leases(leases)
    except BaseException as error:
        proof['errors'].append({'stage': 'held_identity', 'type': type(error).__name__, 'message': str(error)})
    rows = list(leases)
    leases.clear()
    for row in reversed(rows):
        entry = {key: value for key, value in row.items() if key != 'fd'}
        entry['descriptor_closed'] = False
        try:
            os.close(row['fd'])
            entry.update(descriptor_closed=True, released_ns=time.time_ns())
        except BaseException as error:
            proof['errors'].append({'stage': 'descriptor_close', 'path': row['path'],
                'type': type(error).__name__, 'message': str(error)})
        proof['rows'].append(entry)
    proof['all_parent_descriptors_closed'] = all(row['descriptor_closed'] for row in proof['rows'])
    tokens = {f'{os.major(row["identity"][0]):02x}:{os.minor(row["identity"][0]):02x}:{row["identity"][1]}' for row in rows}
    # Use the PID in the mounted procfs namespace, which is also the namespace
    # used by /proc/locks; local isolated controls may have a nested getpid().
    proc_self_pid = Path('/proc/self/stat').read_text().split(' ', 1)[0]
    need(proc_self_pid.isdecimal(), 'actual procfs parent PID required')
    for line in Path('/proc/locks').read_text().splitlines():
        fields = line.split()
        if (len(fields) == 8 and fields[1:4] == ['FLOCK', 'ADVISORY', 'WRITE']
                and fields[4] == proc_self_pid and fields[5] in tokens):
            proof['remaining_parent_kernel_locks'].append(line)
    proof['qualified'] = (proof['all_parent_descriptors_closed']
        and not proof['remaining_parent_kernel_locks'] and not proof['errors'])
    return proof


def save_parent_lease_receipt(name, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    path = D / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    actual, pin = held(path, 131072)
    need(actual == raw, 'parent lease receipt changed after publication')
    return pin


def run_with_parent_work_leases(scope, packet):
    root = D.parents[1]
    native_work = root / 'work'
    works = (native_work, root.parent / 'framework/work',
        Path('/home/alex/work/pocket4-audio-source-build-20261108-r1/work'))
    need(scope['ROOT'] == root and scope['FENCE_ROOT'] == root / 'build-fences-native597-8gib-hostreserve5-20261108-r1',
         'exact already-bound outer work and fence paths')
    leases, fresh = acquire_parent_work_leases(works, native_work)
    report = {'schema': 'native597-full-parent-work-lease-v1', 'started_ns': time.time_ns(),
        'fresh_six_locks': fresh, 'parent_leases': [{key: value for key, value in row.items() if key != 'fd'} for row in leases],
        'normal_updater_owns_native_two': True,
        'scope': 'parent retains Framework and Audio four leases through outer retirement and restoration checking',
        'automatic_source_recovery': False, 'errors': [], 'outer_invoked': False,
        'outer_returned': False, 'owned_retirement_complete': False, 'source_restore_check_completed': False}
    code = None
    try:
        report['admission_receipt'] = save_parent_lease_receipt('parent-work-lease-admission.json', report)
        verify_parent_work_leases(leases)
        report['outer_invoked'] = True
        code = scope['run'](packet)
        report['outer_returned'] = True
    except BaseException as error:
        report['errors'].append({'stage': 'outer', 'type': type(error).__name__, 'message': str(error)})
    finally:
        report['outer_returncode'] = code
        try:
            children = Path('/proc/self/task', str(os.getpid()), 'children').read_text().split()
            need(len(children) <= 128 and all(value.isdecimal() for value in children), 'bounded current child inventory')
            report['owned_children_after_outer'] = [int(value) for value in children]
            raw, pin = held(scope['FENCE_ROOT'] / 'terminal.json', 1048576)
            terminal = json.loads(raw)
            report['outer_terminal'] = pin
            need(report['outer_returned'] and type(code) is int and code in (0, 1), 'ordinary outer must finish its finally before lease release')
            inner_retired = terminal['inner_build_called'] is False
            if terminal['inner_build_called']:
                inner_raw, inner_pin = held(root / 'attempt-native597-8gib-hostreserve5-20261108-r1/terminal.json', 1048576)
                inner = json.loads(inner_raw)
                report['inner_terminal'] = inner_pin
                inner_retired = inner['cleanup']['complete'] is True
                cleanup = inner['cleanup']
                need(isinstance(cleanup.get('children'), list)
                     and isinstance(cleanup.get('errors', []), list)
                     and isinstance(cleanup.get('remaining', []), list), 'original cleanup summary shape')
                report['original_inner_cleanup_summary'] = {
                    'complete': inner_retired, 'child_record_count': len(cleanup['children']),
                    'error_count': len(cleanup.get('errors', [])),
                    'remaining_count': len(cleanup.get('remaining', [])),
                    'complete_original_in_inner_terminal_reference': True}
                report['original_input_after_qualified'] = inner['input_after_qualified']
            report['owned_retirement_complete'] = not children and inner_retired
            need(report['owned_retirement_complete'], 'actual outer/inner owned retirement must precede lease release')
            try:
                report['projection_observations'] = []
                for work in works:
                    journal = work / 'source-projection.json'
                    row = {'path': str(journal), 'absent': not journal.exists() and not journal.is_symlink()}
                    report['projection_observations'].append(row)
                    need(row['absent'], 'source projection still present after ordinary outer: ' + str(work))
                native_probes = []
                try:
                    for name in ('package-build.lock', 'aosp-source-update.lock'):
                        path = native_work / name
                        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                        native_probes.append(fd)
                        info = os.fstat(fd)
                        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                             and identity(info) == identity(path.lstat()), 'final Native lock identity')
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    report['native_two_locks_free_after_outer'] = True
                finally:
                    for fd in reversed(native_probes):
                        os.close(fd)
                report['source_projection_restored'] = True
            finally:
                report['source_restore_check_completed'] = True
                report['source_restore_check_completed_ns'] = time.time_ns()
        except BaseException as error:
            report['errors'].append({'stage': 'outer_retirement_or_restore_observation',
                'type': type(error).__name__, 'message': str(error)})
        try:
            report['lease_release'] = release_parent_work_leases(leases,
                retirement_complete=report['owned_retirement_complete'],
                source_restore_check_completed=report['source_restore_check_completed'])
            need(report['lease_release']['qualified'], 'four parent coordination descriptors did not retire cleanly')
        except BaseException as error:
            report['errors'].append({'stage': 'parent_work_lease_release',
                'type': type(error).__name__, 'message': str(error)})
            # As in the reviewed Audio parent lease correction, an unproved
            # child retirement leaves these descriptors held through the failed
            # terminal and process exit; no early explicit unlock or recovery.
            report['leases_left_to_failed_controller_exit'] = [
                {'path': row['path'], 'fd': row['fd']} for row in leases]
        report.update(finished_ns=time.time_ns(), full_build_success=code == 0 and not report['errors'],
            global_admission_granted=False)
        saved = save_parent_lease_receipt('parent-work-lease-terminal.json', report)
        print(json.dumps({'parent_work_lease_terminal': saved, 'full_build_success': report['full_build_success'],
            'owned_retirement_complete': report['owned_retirement_complete'], 'errors': report['errors']}), flush=True)
    return code if code in (0, 1) and not report['errors'] else 1


def main():
    need(os.getuid() == os.geteuid() == 1000 and len(sys.argv) == 2, 'original operator and exact packet digest required')
    packet_raw, packet_ref = held(PACKET, 1024 * 1024)
    need(packet_ref['sha256'] == sys.argv[1], 'exact frozen packet required')
    packet = json.loads(packet_raw)
    raw_cgroup = Path('/proc/self/cgroup').read_text().strip()
    need(raw_cgroup.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'),
         'actual owned outer job required')
    unit = raw_cgroup.rsplit('/', 1)[-1]
    need(unit.endswith('.service'), 'outer service name required')
    job = unit[len('hepta-runtime-job-'):-len('.service')]
    job_root = Path('/home/alex/.local/state/hepta-runtime-mac-worker/jobs') / job
    request_raw, request_ref = held(job_root / 'request.json', 65536)
    _, runner_ref = held(job_root / 'runner.py', 65536)
    request = json.loads(request_raw)
    need(runner_ref['bytes'] == 40463 and runner_ref['sha256'] == RUNNER_SHA,
         'reviewed outer monotonic-deadline implementation required')
    need(request['job_id'] == job and request['unit'] + '.service' == unit
         and request['execution_mode'] == 'operator' and request['timeout_seconds'] == 23000,
         'actual fixed outer timeout must be 23000 seconds')
    observed = subprocess.run(['/usr/bin/systemctl', '--user', 'show', unit,
                               '-p', 'ActiveState', '-p', 'RuntimeMaxUSec',
                               '-p', 'ExecMainStartTimestampMonotonic'],
                              check=True, capture_output=True, text=True, timeout=15)
    properties = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
    elapsed = time.monotonic() - int(properties['ExecMainStartTimestampMonotonic']) / 1000000
    need(properties['ActiveState'] == 'active' and properties['RuntimeMaxUSec'] == 'infinity'
         and 0 <= elapsed < 200, 'fresh actual outer runtime accounting required')
    # The pinned runtime starts its monotonic timer after child/log setup. The
    # unit's earlier start gives a conservative elapsed bound for this launch.
    margin = 23000 - elapsed - 21600
    need(margin > 1200, 'normal build must retain the reviewed outer cleanup margin')
    receipt = {'schema': 'pocket4-native597-outer-runtime-admission-v1',
               'state': 'ACTUAL_OUTER_RUNTIME_VERIFIED_BUILD_PENDING',
               'job_id': job, 'packet': packet_ref, 'outer_cgroup': raw_cgroup,
               'actual_request': request_ref, 'actual_runtime_runner': runner_ref,
               'actual_unit_properties': properties, 'outer_elapsed_seconds': elapsed,
               'outer_timeout_seconds': 23000, 'normal_build_timeout_seconds': 21600,
               'remaining_margin_before_preflight_seconds': margin,
               'inner_cleanup_seconds_unchanged': 8, 'snapshot_deadlines_unchanged': True,
               'Soong_invocations_at_admission': 0, 'runtime_qualified': False}
    raw = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    target = D / 'outer-runtime-admission.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _, published = held(target, 65536)
    need(published['sha256'] == hashlib.sha256(raw).hexdigest(), 'runtime admission publication changed')
    print(json.dumps({'state': 'NATIVE_OUTER_RUNTIME_ADMITTED', 'proof': published,
                      'job_id': job, 'normal_build_timeout_seconds': 21600,
                      'outer_timeout_seconds': 23000}), flush=True)
    scope = {'__name__': 'pinned_native597_fenced_build', '__file__': str(D / 'fenced_build.py')}
    exec(compile(packet['outer_source'], str(D / 'fenced_build.py'), 'exec'), scope, scope)
    return run_with_parent_work_leases(scope, packet)


if __name__ == '__main__':
    raise SystemExit(main())
