#!/usr/bin/env python3
"""Retire only the exact original Android PID 1 stranded by native restart r1.

This is a new explicit lifecycle repair, not a retry of that restart. It does
not publish a runtime guard, adopt an Android task, enter a namespace, or touch
an App. The original failure and its UNKNOWN outcome remain immutable.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time
import types

SOURCE = '/home/alex/work/pocket4-cell-recovery-preflight-20261106-r1/source'
MANIFEST = 'b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f'
OLD_ROOT = '/home/alex/work/pocket4-cell-successor-20261106-r1'
ROOT = '/home/alex/work/pocket4-orphan-cell-retirement-20261106-r1'
PINS = {
    'predecessor.private.json': (110738, '6b781af9d0d037e14d7f4b3174937f3a101ab4cf313b7c5c34fec1c13df9dec3'),
    'native-restart-receipt.private.json': (1060, 'd329733b4073662320f2c8839d8ef43053e095a9429cd810865e7f44daec2733'),
    'result.json': (1010, 'eaf9a964fc33b77e3a8841a51b5b2e4cb4f15fa4edd247f943a336f8bbdcac0f'),
}
LINEAGE_SHA = '106e92009c87248f9a078ac454b6c2883121fc41297483cd9dba3cf88e83c867'
FRESH_JOB_IDS = {'1a1b0a21e45-fc05-71db', '1a1b0a790e3-fc05-71f9', '1a1b0ab2fab-fc05-720f'}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def bounded_source(path, maximum, expected):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        a = os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1
             and 0 < a.st_size <= maximum, 'BOUNDED_ROOT_SOURCE_REQUIRED')
        raw = bytearray()
        end = time.monotonic() + 10
        while len(raw) <= maximum:
            need(time.monotonic() < end, 'SOURCE_READ_DEADLINE')
            block = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        b, c = os.fstat(fd), os.stat(path, follow_symlinks=False)
        need(len(raw) == a.st_size and all(getattr(a, k) == getattr(b, k) == getattr(c, k) for k in keys)
             and hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_CHANGED')
        return bytes(raw)
    finally:
        os.close(fd)


def original_role_absences(core, rows):
    evidence = {}
    for role in core.RETIRED:
        if role == 'android_init':
            continue
        old = rows[role]
        try:
            current = core.E._stat(old['host_pid'])
        except FileNotFoundError:
            evidence[role] = {'host_pid': old['host_pid'], 'start_ticks': old['start_ticks'],
                              'observed': 'proc_absent', 'original_pre_restart_pidfd_evidence': False}
            continue
        need(current[2] != old['start_ticks'], 'AN_ORIGINAL_NON_INIT_ROLE_IS_STILL_PRESENT')
        evidence[role] = {'host_pid': old['host_pid'], 'start_ticks': old['start_ticks'],
                          'observed': 'pid_reused_with_different_start_ticks',
                          'current_start_ticks': current[2], 'original_pre_restart_pidfd_evidence': False}
    return evidence


def namespace_members(core, namespace):
    end = time.monotonic() + 8
    names = os.listdir('/proc')
    need(len(names) <= 65536, 'PROC_COUNT_BOUND')
    members = []
    for name in names:
        need(time.monotonic() < end, 'PROC_SCAN_DEADLINE')
        if not name.isdecimal():
            continue
        try:
            if os.readlink('/proc/' + name + '/ns/pid') == namespace:
                members.append({'host_pid': int(name), 'stat': core.E._stat(int(name))})
        except (FileNotFoundError, ProcessLookupError):
            continue
    return members


def main():
    need(os.getuid() == os.geteuid() == 0 and hasattr(signal, 'pidfd_send_signal'), 'ROOT_WITH_PIDFD_SIGNAL_REQUIRED')
    os.umask(0o077)
    manifest_raw = bounded_source(SOURCE + '/SOURCE_PINS.json', 65536, MANIFEST)
    pins = json.loads(manifest_raw)['files']
    raw = bounded_source(SOURCE + '/successor_runtime.py', 65536, pins['successor_runtime.py']['sha256'])
    core = types.ModuleType('frozen_orphan_repair_readers')
    core.__file__ = SOURCE + '/successor_runtime.py'
    exec(compile(raw, core.__file__, 'exec'), core.__dict__)
    core.configure(SOURCE, MANIFEST)
    raw = sys.stdin.buffer.read(900001)
    need(len(raw) <= 900000, 'PACKET_BOUND')
    packet = core.parse(raw)
    need(set(packet) == {'schema', 'source_text', 'source_sha256', 'lineage_text', 'terminals', 'coordination'}
         and packet['schema'] == 'pocket4-exact-orphan-retirement-packet-v1', 'CLOSED_REPAIR_PACKET')
    need(packet['coordination'] == {'all_runtime_workers_settled': True, 'agents_runtime_frozen': True,
         'unresolved_runtime_start_attempts': [], 'host_only_downloads_excluded': True}, 'COORDINATED_DRAIN_REQUIRED')
    need(hashlib.sha256(packet['source_text'].encode()).hexdigest() == packet['source_sha256'], 'REPAIR_SOURCE_DIGEST')
    need(hashlib.sha256(packet['lineage_text'].encode()).hexdigest() == LINEAGE_SHA, 'ACTUAL_LINEAGE_RECEIPT_REQUIRED')
    lineage = core.parse(packet['lineage_text'])
    need(lineage['schema'] == 'pocket4-compat-wrapper-and-retired-namespace-readonly-v1', 'LINEAGE_SCHEMA')
    observed = lineage['observations']
    original = {}
    for name, (size, sha) in PINS.items():
        original[name] = core.parse(core.pinned_record({'path': OLD_ROOT + '/' + name, 'bytes': size, 'sha256': sha}))
    before, failure = original['predecessor.private.json'], original['result.json']
    plan = before['plan']
    native_receipt = original['native-restart-receipt.private.json']
    need(core.native_running(native_receipt['stdout_utf8'].encode(), native_receipt['command'])['host_pid'] == 2747275,
         'ACTUAL_RESTART_RECEIPT_OWNER_REQUIRED')
    need(failure['restart_attempted'] is True and failure['outcome_unknown'] is True
         and failure['identity_qualified'] is False and failure['errors'] == [{
             'code': 'OLD_CELL_OR_NATIVE_OWNER_STILL_ALIVE', 'phase': 'old_native_owner_pidfd_deaths', 'type': 'Rejected'}],
         'EXACT_FAILED_RESTART_REQUIRED')
    for missing in ('retired-lifecycle.private.json', 'successor-candidate.private.json', 'baseline.private.json', 'current_baseline_guard.py'):
        need(not os.path.lexists(OLD_ROOT + '/' + missing), 'ORIGINAL_FAILURE_STATE_CHANGED')
    old_rows = before['runtime']['held']['process_snapshot']['binding']['processes']
    need(core.boot_id() == before['runtime']['held']['process_snapshot']['binding']['boot_id'], 'BOOT_CHANGED')
    expected = {
        'orphan_init': old_rows['android_init'],
        'orphan_parent': observed['previous_init_parent']['identity'],
        'new_launcher': observed['actual_native_receipt_owner']['identity'],
        'new_init': observed['diagnostic_android_init_0']['identity'],
        'daemon': old_rows['daemon'], 'presenter': old_rows['presenter'],
    }
    root_expected = {
        'orphan_init': observed['previous_android_init']['root_identity'],
        'orphan_parent': observed['previous_init_parent']['root_identity'],
        'new_launcher': observed['actual_native_receipt_owner']['root_identity'],
        'new_init': observed['diagnostic_android_init_0']['root_identity'],
    }
    need(root_expected['orphan_init'] == root_expected['orphan_parent'] == {'dev': 106, 'ino': 1}
         and root_expected['new_init'] == {'dev': 1048681, 'ino': 1}, 'EXACT_RECORDED_ROOTS_REQUIRED')
    need(expected['orphan_init'] == observed['previous_android_init']['identity']
         and (expected['orphan_init']['host_pid'], expected['orphan_init']['start_ticks']) == (3588093, 80797014)
         and expected['orphan_init']['parent_host_pid'] == expected['orphan_parent']['host_pid'] == 3588092
         and expected['orphan_parent']['parent_host_pid'] == 1
         and (expected['orphan_parent']['start_ticks'], expected['new_launcher']['host_pid'],
              expected['new_init']['host_pid']) == (80797014, 2747275, 2747279), 'EXACT_TWO_CELL_LINEAGE_REQUIRED')
    need(expected['new_init']['namespaces']['pid'] != expected['orphan_init']['namespaces']['pid'], 'DISTINCT_PID_NAMESPACES_REQUIRED')
    need(set(packet['terminals']) >= FRESH_JOB_IDS and len(packet['terminals']) == 24, 'ALL_KNOWN_RUNTIME_TERMINALS_REQUIRED')
    pool, leases = core.FDs(), core.FDs()
    result = {'schema': 'pocket4-explicit-orphan-retirement-result-v1', 'ok': False, 'signal_attempted': False,
              'outcome_unknown': False, 'automatic_retry': False, 'restart_count': 0,
              'original_restart_result_unchanged': True, 'original_pre_restart_pidfd_evidence_recreated': False,
              'guard_publication': False, 'identity_qualified': False, 'UI_actions': 0, 'installs': 0,
              'Android_commands': 0, 'namespace_entries': 0, 'permission_changes': 0, 'production_ready': False, 'errors': []}
    created = False
    phase = 'leases_and_exact_processes'
    try:
        core.acquire_lock(leases, core.ACTION_LOCK, before['action_lock_identity'])
        for lock in before['reviewed_drain']['flow_locks']:
            core.acquire_lock(leases, lock['path'], lock['identity'])
        core.unknown_evidence(plan)
        core.pinned_record(plan['native_cli'], 32 * 1024 * 1024)
        need(core.service() == before['runtime']['daemon_service']
             and core.service(True) == before['runtime']['presenter_service']
             and core.limits() == before['runtime']['limits'], 'HOST_SERVICE_OR_LIMITS_CHANGED')
        core.host_read(core.CONFIG, 131072, plan['cell_config_sha256'])
        handles = {}
        def verify_root(label):
            if label in root_expected:
                current = os.stat('/proc/' + str(expected[label]['host_pid']) + '/root')
                need({'dev': current.st_dev, 'ino': current.st_ino} == root_expected[label],
                     'RECORDED_ROOT_CHANGED_' + label)
        for label, identity in expected.items():
            need(core.E.process_identity(identity['host_pid']) == identity, 'RECORDED_PROCESS_CHANGED_' + label)
            verify_root(label)
            handles[label] = pool.own(os.pidfd_open(identity['host_pid'], 0))
            need(not core.pidfd_dead(handles[label]) and core.E.process_identity(identity['host_pid']) == identity,
                 'FRESH_PIDFD_IDENTITY_CHANGED_' + label)
        def verify_survivors():
            for label in ('new_launcher', 'new_init', 'daemon', 'presenter'):
                need(not core.pidfd_dead(handles[label]) and core.E.process_identity(expected[label]['host_pid']) == expected[label],
                     'NON_TARGET_PROCESS_CHANGED_' + label)
                verify_root(label)
            need(core.service() == before['runtime']['daemon_service']
                 and core.service(True) == before['runtime']['presenter_service'], 'NON_TARGET_SERVICE_CHANGED')
        old_ns = expected['orphan_init']['namespaces']['pid']
        need(expected['orphan_init']['namespace_pids'][-1] == 1 and expected['new_init']['namespace_pids'][-1] == 1,
             'NAMESPACE_INIT_REQUIRED')
        need(core.host_pseudo('/proc/3588092/task/3588092/children', 8192).split() == [b'3588093'], 'ORPHAN_PARENT_CHILD_CHANGED')
        before_absences = original_role_absences(core, old_rows)
        status_raw, status_err, status_command = core.bounded_child(core.native_argv('status'), 10)
        need(core.native_running(status_raw, status_command)['host_pid'] == 2747275, 'NATIVE_CURRENT_OWNER_CHANGED')
        verify_survivors()
        phase = 'durable_new_repair_checkpoint'
        need(not os.path.lexists(ROOT), 'NEW_REPAIR_DIRECTORY_REQUIRED_NO_RETRY')
        core.create_private_root(ROOT)
        created = True
        core.write_new(ROOT + '/source/retire_exact_orphan_r1.py', packet['source_text'].encode())
        core.write_new(ROOT + '/lineage.stdout.raw.json', packet['lineage_text'].encode())
        receipts = []
        for job, value in sorted(packet['terminals'].items()):
            terminal = core.parse(value)
            need(terminal['job_id'] == job and terminal['state'] in ('succeeded', 'failed')
                 and terminal['output_complete'] is True and terminal['output_durable'] is True
                 and terminal['terminal_publication_confirmed'] is True, 'ACTUAL_TERMINAL_REQUIRED')
            receipts.append(core.write_new(ROOT + '/terminal-' + job + '.json', value.encode()))
        checkpoint = {'schema': 'pocket4-exact-orphan-retirement-checkpoint-v1', 'old_failure': PINS,
                      'lineage_sha256': LINEAGE_SHA, 'expected_processes': expected,
                      'native_status': {'stdout': status_raw.decode(), 'stderr': status_err.decode(), 'command': status_command},
                      'fresh_pidfds_acquired_before_this_repair': sorted(handles),
                      'original_non_init_roles': before_absences, 'terminal_receipts': receipts,
                      'signal_target': {'role': 'orphan_init', 'host_pid': 3588093, 'start_ticks': 80797014, 'signal': 'SIGKILL'},
                      'rationale': 'Exact stranded namespace PID 1; ordinary native stop already returned; PID 1 ignores default TERM',
                      'new_cell_not_restarted': True, 'created_monotonic_ns': time.monotonic_ns()}
        checkpoint_pin = core.write_new(ROOT + '/checkpoint.private.json', core.canonical(checkpoint) + b'\n')
        verify_survivors()
        for label in ('orphan_init', 'orphan_parent'):
            need(core.E.process_identity(expected[label]['host_pid']) == expected[label]
                 and not core.pidfd_dead(handles[label]), 'ORPHAN_IDENTITY_CHANGED_BEFORE_SIGNAL')
            verify_root(label)
        core.unknown_evidence(plan)
        core.write_new(ROOT + '/signal-attempted.json', core.canonical({'schema': 'pocket4-orphan-pidfd-signal-attempt-v1',
            'checkpoint': checkpoint_pin, 'monotonic_ns': time.monotonic_ns(), 'target': expected['orphan_init'],
            'signal': int(signal.SIGKILL), 'automatic_retry': False}) + b'\n')
        phase = 'one_exact_orphan_init_pidfd_signal'
        result['signal_attempted'], result['outcome_unknown'] = True, True
        signal.pidfd_send_signal(handles['orphan_init'], signal.SIGKILL, None, 0)
        end = time.monotonic() + 30
        while not (core.pidfd_dead(handles['orphan_init']) and core.pidfd_dead(handles['orphan_parent'])):
            need(time.monotonic() < end, 'ORPHAN_INIT_OR_PARENT_DID_NOT_EXIT')
            for label in ('new_launcher', 'new_init', 'daemon', 'presenter'):
                need(not core.pidfd_dead(handles[label]), 'NON_TARGET_DIED_DURING_RETIREMENT')
            time.sleep(.1)
        phase = 'exact_post_retirement_readback'
        verify_survivors()
        members = namespace_members(core, old_ns)
        need(members == [], 'OLD_PID_NAMESPACE_MEMBERS_REMAIN')
        after_absences = original_role_absences(core, old_rows)
        status_raw, status_err, status_command = core.bounded_child(core.native_argv('status'), 10)
        need(core.native_running(status_raw, status_command)['host_pid'] == 2747275, 'POST_RETIREMENT_NATIVE_OWNER_CHANGED')
        core.unknown_evidence(plan)
        for name, (size, sha) in PINS.items():
            core.pinned_record({'path': OLD_ROOT + '/' + name, 'bytes': size, 'sha256': sha})
        verify_survivors()
        need(core.boot_id() == before['runtime']['held']['process_snapshot']['binding']['boot_id'], 'BOOT_CHANGED_AFTER_RETIREMENT')
        result.update(ok=True, outcome_unknown=False,
                      retired={'android_init': expected['orphan_init'], 'orphan_unshare_parent': expected['orphan_parent']},
                      fresh_repair_pidfd_deaths={'orphan_init': True, 'orphan_parent': True},
                      old_namespace_members_after=members, old_non_init_roles=after_absences,
                      non_target_processes_unchanged=True,
                      current_native_status={'stdout': status_raw.decode(), 'stderr': status_err.decode(), 'command': status_command})
    except BaseException as error:
        result['errors'].append({'phase': phase, 'type': type(error).__name__, 'code': str(error)[:180]})
        result['ok'] = False
    finally:
        for name, group in (('observation_fds', pool), ('lease_fds', leases)):
            try:
                group.close_all()
            except BaseException as error:
                result['errors'].append({'phase': name, 'type': type(error).__name__, 'code': str(error)[:180]})
                result['ok'] = False
            result[name] = group.summary()
    if created:
        result_pin = core.write_new(ROOT + '/result.json', core.canonical(result) + b'\n')
    else:
        result_pin = None
    print(json.dumps({'result': result, 'artifact': result_pin}, sort_keys=True, separators=(',', ':')), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
