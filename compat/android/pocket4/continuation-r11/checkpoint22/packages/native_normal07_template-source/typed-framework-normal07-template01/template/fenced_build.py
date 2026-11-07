#!/usr/bin/env python3
"""UID1000 outer controller with fixed read-only pre/post Main observations."""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time

CONTROLLER_SHA = "__BOUND_FRAMEWORK470_CONTROLLER_SHA256__"
LIFECYCLE_SHA = '2dcf44609e6ef53e91b2d8e3a07c192fe65a7d44601f218dc8990272285d4dfe'
ROOT_SUPERVISOR_SHA = '903ae227d9231a361c61fad6fd584c97a548bb5a41b09a4e5fa8824e13e02350'
SNAPSHOT_SHA = '264100ef85e1792c437a4f450050041141288a0f25a4387af5774c52d0dcea06'
PREPARATION_SHA = 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'
ROOT = Path("/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-provider-build-07-20261106")
FENCE_ROOT = ROOT / 'build-fences-01'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(FENCE_ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def capture_support(packet):
    common = packet['lifecycle_source'].encode('utf-8')
    root = packet['root_supervisor_source'].encode('utf-8')
    require(sha(common) == LIFECYCLE_SHA and sha(root) == ROOT_SUPERVISOR_SHA,
            'fixed capture support source changed')
    scope = {'__name__': 'pinned_outer_capture_lifecycle', '__file__': '<pinned-capture-lifecycle>'}
    exec(compile(common, 'capture_lifecycle.py', 'exec'), scope, scope)
    return {'module': scope, 'common': common.decode('utf-8'), 'root': root.decode('utf-8'), 'receipts': []}


def root_bootstrap(raw, root_source_sha):
    # This bootstrap can only execute the whole-packet-pinned root supervisor.
    # The watchdog is installed before importing/hash/compiling either body.
    return (
        'import os,signal,time\n'
        'ENTRY=time.monotonic()\n'
        'def interrupted(number,frame):\n'
        '    if number==signal.SIGALRM:raise TimeoutError("root observation watchdog")\n'
        '    raise InterruptedError("root owned supervisor interrupted "+str(number))\n'
        'for number in (signal.SIGALRM,signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(number,interrupted)\n'
        'signal.setitimer(signal.ITIMER_REAL,max(0.001,ENTRY+15-time.monotonic()))\n'
        'import hashlib,json,sys\n'
        'raw=sys.stdin.buffer.read(' + str(len(raw) + 1) + ')\n'
        'if len(raw)!=' + str(len(raw)) + ' or hashlib.sha256(raw).hexdigest()!=' + repr(sha(raw)) + ':raise RuntimeError("root source packet changed")\n'
        'packet=json.loads(raw.decode("utf-8","strict"))\n'
        'source=packet["root_source"].encode("utf-8")\n'
        'if hashlib.sha256(source).hexdigest()!=' + repr(root_source_sha) + ':raise RuntimeError("root supervisor changed")\n'
        'scope={"__name__":"pinned_root_snapshot_supervisor","__file__":"<pinned-root-supervisor>"}\n'
        'exec(compile(source,"root_snapshot_supervisor.py","exec"),scope,scope)\n'
        'raise SystemExit(scope["run"](packet,ENTRY))\n')


def invoke_supervisor(label, mode, source, source_sha, support, outer_pidfd_failure=False):
    require(label in ('before', 'after', 'control-root-timeout', 'control-root-escaped',
                      'control-root-pidfd', 'control-outer-pidfd') and
            mode in ('before', 'after', 'control-timeout', 'control-escaped', 'control-pidfd') and
            sha(source) == SNAPSHOT_SHA == source_sha,
            'capture fixed mode/source differs')
    scope = support['module']
    raw = (json.dumps({'schema': 1, 'mode': mode, 'root_source': support['root'],
                      'lifecycle_source': support['common'], 'snapshot_source': source.decode('utf-8')},
                     separators=(',', ':')) + '\n').encode('utf-8')
    require(len(raw) <= 196608, 'fixed root source packet exceeds bound')
    wrapper = root_bootstrap(raw, ROOT_SUPERVISOR_SHA)
    reaper = scope['OwnChildReaper'](scope['PROTECTED_PIDS'], passive_root_wait=True)
    report = {'schema': 1, 'phase': label, 'mode': mode, 'operator_uid': os.getuid(),
              'root_source_sha256': ROOT_SUPERVISOR_SHA, 'lifecycle_sha256': LIFECYCLE_SHA,
              'snapshot_sha256': source_sha, 'root_packet_bytes': len(raw),
              'root_packet_sha256': sha(raw), 'outer_subreaper': reaper.record,
              'command': None, 'first_error': None, 'secondary_errors': [],
              'outer_pidfd_failure_control': outer_pidfd_failure,
              'Main_actions': 0, 'Android_actions': 0, 'old_QA_epoch_invalid': True,
              'new_QA_epoch_qualified': False, 'runtime_authorization_enabled': False}
    support['receipts'].append(report)
    first = None
    command = stdout = stderr = None
    previous_handlers = {}
    previous_alarm_handler = None
    outer_watchdog_installed = False
    started = time.monotonic()
    def remember(error, stage):
        nonlocal first
        value = scope['safe_error'](error, stage)
        if first is None:
            first = error
            report['first_error'] = value
        else:
            report['secondary_errors'].append(value)

    def observation_expired(number, frame):
        raise TimeoutError('outer owned snapshot observation watchdog')

    def retirement_expired(number, frame):
        raise TimeoutError('outer owned snapshot retirement watchdog')

    def enter_retirement(deadline):
        if outer_watchdog_installed:
            signal.signal(signal.SIGALRM, retirement_expired)
            signal.setitimer(signal.ITIMER_REAL, max(0.001, started + 30 - time.monotonic()))
        for number in (signal.SIGTERM, signal.SIGINT):
            if number not in previous_handlers:
                previous_handlers[number] = signal.getsignal(number)
            signal.signal(number, signal.SIG_IGN)

    def factory(input_fd, output_fd, error_fd, bound):
        # Preserve the original UID1000/sudo policy and environment exactly.
        return subprocess.Popen(['/usr/bin/sudo', '-n', '/usr/bin/python3', '-I', '-B', '-c', wrapper],
            stdin=input_fd, stdout=output_fd, stderr=error_fd, close_fds=True, start_new_session=True)

    def denied_pidfd(pid, flags):
        import errno
        raise OSError(errno.EMFILE, 'explicit outer owned-child pidfd allocation control seam')

    try:
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'outer existing timer is not idle')
        previous_alarm_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, observation_expired)
        outer_watchdog_installed = True
        signal.setitimer(signal.ITIMER_REAL, max(0.001, started + 25 - time.monotonic()))
        report['outer_watchdog_installed_before_launch'] = True
        reaper.begin()
        command, stdout, stderr, error = scope['invoke_owned'](
            reaper, factory, raw, started + 25, started + 30, output_bound=131072,
            pidfd_factory=denied_pidfd if outer_pidfd_failure else None,
            cleanup_enter=enter_retirement)
        report['command'] = command
        if error is not None:
            remember(error, 'outer_invocation')
    except BaseException as error:
        remember(error, 'outer_start')
    finally:
        try:
            enter_retirement(started + 30)
        except BaseException as error:
            remember(error, 'outer_retirement_signal_guard')
        try:
            reaper.finish()
        except BaseException as error:
            remember(error, 'outer_subreaper_finish')
        if outer_watchdog_installed:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_alarm_handler)
                report['outer_watchdog_disarmed_and_restored'] = True
            except BaseException as error:
                remember(error, 'outer_watchdog_restore')
        for number, previous in previous_handlers.items():
            try:
                signal.signal(number, previous)
            except BaseException as error:
                remember(error, 'outer_signal_restore')
        report['finished_monotonic'] = time.monotonic()
        report['within_absolute_outer_deadline'] = report['finished_monotonic'] <= started + 30
        if not report['within_absolute_outer_deadline']:
            remember(TimeoutError('outer snapshot retirement deadline'), 'outer_deadline')
        report['qualified_success'] = first is None
        if stdout is not None:
            save(label + '.root-supervisor.stdout.json', stdout)
        if stderr is not None:
            save(label + '.root-supervisor.stderr.txt', stderr)
        save(label + '.capture-lifecycle.json', report)
    return report, stdout, stderr, first


def qualified_root_envelope(report, stdout, stderr, label, mode):
    require(report['qualified_success'] and report.get('outer_watchdog_installed_before_launch') is True and
            report.get('outer_watchdog_disarmed_and_restored') is True and
            report['command']['qualified_success'] and
            report['command']['child_reaped'] and report['command']['returncode'] == 0 and
            report['command']['owned_tree_cleanup_complete'] and
            report['command']['remaining_owned_children'] == [] and
            report['command']['all_acquired_fds_closed'] and
            report['outer_subreaper']['final_children_empty'] and report['outer_subreaper']['restored'] and
            stderr == b'', 'owned sudo/root lifecycle failed: ' + label)
    value = json.loads(stdout.decode('utf-8', 'strict'))
    require(value['kind'] == 'fixed-root-main-snapshot-supervisor02' and value['mode'] == mode and
            value['ok'] is True and value['root_uids'] == [0, 0, 0] and value['dumpable'] == 0 and
            value['root_subreaper']['begin_passed'] and value['root_subreaper']['final_children_empty'] and
            value['root_subreaper']['restored'] and
            value['command']['owned_tree_cleanup_complete'] and value['command']['remaining_owned_children'] == [] and
            value['command']['all_acquired_fds_closed'] and value['command']['retirement_within_deadline'] and
            value['within_absolute_supervisor_deadline'] and value['within_final_retirement_deadline'] and
            value['old_QA_epoch_invalid'] is True and value['new_QA_epoch_qualified'] is False and
            value['runtime_authorization_enabled'] is False,
            'fixed root supervisor result did not qualify: ' + label)
    return value


def capture(label, source, source_sha, support):
    report, stdout, stderr, error = invoke_supervisor(label, label, source, source_sha, support)
    if error is not None:
        raise error
    envelope = qualified_root_envelope(report, stdout, stderr, label, label)
    require(envelope['snapshot_qualified'] is True and envelope['control_passed'] is False,
            'fixed snapshot result has a control-only scope')
    raw = envelope['child_stdout_utf8'].encode('utf-8')
    error_raw = envelope['child_stderr_utf8'].encode('utf-8')
    command = envelope['command']
    require(len(raw) == command['stdout']['bytes'] <= 65536 and
            sha(raw) == command['stdout']['sha256'] and
            len(error_raw) == command['stderr']['bytes'] == 0 and
            sha(error_raw) == command['stderr']['sha256'],
            'fixed snapshot original output differs')
    save(label + '.stdout.json', raw)
    save(label + '.stderr.txt', error_raw)
    observation = json.loads(raw.decode('utf-8', 'strict'))
    require(observation.get('ok') is True and
            observation['old_QA_epoch_invalid'] is True and observation['new_QA_epoch_qualified'] is False and
            observation['runtime_authorization_enabled'] is False and
            set(observation['protected_processes']) ==
                {'android_init', 'daemon', 'launcher', 'owner_intermediary', 'presenter', 'surfaceflinger', 'zygote64', 'system_server'},
            'Main snapshot failed: ' + label)
    return observation


def run_capture_lifecycle_controls(source, source_sha, support):
    rows = []
    qualification_started = time.monotonic()
    for label, mode in (('control-root-timeout', 'control-timeout'),
                        ('control-root-escaped', 'control-escaped'),
                        ('control-root-pidfd', 'control-pidfd')):
        require(time.monotonic() - qualification_started < 30, 'capture controls qualification window elapsed')
        report, stdout, stderr, error = invoke_supervisor(label, mode, source, source_sha, support)
        if error is not None:
            raise error
        envelope = qualified_root_envelope(report, stdout, stderr, label, mode)
        require(envelope['control_passed'] is True and envelope['snapshot_qualified'] is False and
                envelope['command']['qualified_success'] is False and
                envelope['command']['first_error'] is not None,
                'root lifecycle negative control was not exercised')
        rows.append({'name': label, 'passed': True, 'actor_uids': [0, 0, 0],
                     'owned_children_empty': True, 'Main_read_performed': False,
                     'original_expected_failure': envelope['command']['first_error'],
                     'outer_lifecycle_sha256': sha((FENCE_ROOT / (label + '.capture-lifecycle.json')).read_bytes()),
                     'root_stdout_sha256': sha(stdout)})
    # Separate post-Popen allocation fault in the UID1000 owner. It need not
    # reach root startup: all actual children must still be independently reaped.
    label = 'control-outer-pidfd'
    require(time.monotonic() - qualification_started < 30, 'capture controls qualification window elapsed')
    report, stdout, stderr, error = invoke_supervisor(
        label, 'control-timeout', source, source_sha, support, outer_pidfd_failure=True)
    import errno
    command = report['command']
    require(isinstance(error, OSError) and error.errno == errno.EMFILE and
            report['first_error']['errno'] == errno.EMFILE and
            command is not None and command['child_started'] and command['child_reaped'] and
            command.get('leader_unreaped_before_group_cleanup') is True and
            command.get('leader_alive_before_group_cleanup') is True and
            command['first_error']['stage'] == 'start_or_wait' and command['first_error']['errno'] == errno.EMFILE and
            command['qualified_success'] is False and command['owned_tree_cleanup_complete'] and
            command['remaining_owned_children'] == [] and command['all_acquired_fds_closed'] and
            command['retirement_within_deadline'] and
            command['stdout'].get('complete') and command['stderr'].get('complete') and
            report['outer_subreaper']['final_children_empty'] and report['outer_subreaper']['restored'] and
            report.get('outer_watchdog_installed_before_launch') is True and
            report.get('outer_watchdog_disarmed_and_restored') is True and
            report['within_absolute_outer_deadline'], 'outer pidfd allocation control did not retire its actual tree')
    require(report['secondary_errors'] == [], 'outer pidfd control had an unrelated finalization failure')
    permitted_permission_stages = {'owned_group_cleanup', 'direct_child_fallback_cleanup',
                                   'adopted_child_signal_permission'}
    for item in command['secondary_errors']:
        permitted = (item['stage'] in permitted_permission_stages and
                     item['type'] == 'PermissionError' and item['errno'] == errno.EPERM)
        permitted = permitted or (item['stage'] == 'driver_left_descendants' and
                                  item['type'] == 'RuntimeError')
        require(permitted, 'outer pidfd control had an unrelated retirement failure')
    rows.append({'name': label, 'passed': True, 'actor_uids': list(os.getresuid()),
                 'owned_children_empty': True, 'Main_read_performed': False,
                 'root_startup_required_for_control': False,
                 'original_expected_failure': command['first_error'],
                 'secondary_failures_retained': command['secondary_errors'],
                 'outer_lifecycle_sha256': sha((FENCE_ROOT / (label + '.capture-lifecycle.json')).read_bytes())})
    elapsed = time.monotonic() - qualification_started
    require(elapsed < 30, 'capture controls qualification window elapsed')
    result = {'schema': 1, 'kind': 'real-fixed-capture-lifecycle-controls02', 'state': 'PASS',
              'qualification_seconds_limit': 30, 'elapsed_seconds': elapsed,
              'hard_execution_deadline_claimed': False,
              'passed': len(rows), 'rows': rows, 'Python_processes_actually_run': True,
              'privileged_commands_limited_to_pinned_supervisor': True, 'Main_read_performed': False,
              'Main_actions': 0, 'Android_actions': 0, 'new_QA_epoch_qualified': False}
    require(len(rows) == 4 and all(row['passed'] for row in rows), 'capture lifecycle controls incomplete')
    save('capture-lifecycle-controls.json', result)
    return result


def compare(before, after):
    identities = ('historical_activation_sha256', 'old_invalid_QA_epoch_sha256',
                  'old_QA_epoch_invalid', 'new_QA_epoch_qualified',
                  'protected_boot_id', 'protected_identity_source_sha256',
                  'actual_baseline02_stdout_sha256', 'protected_processes',
                  'cell_sha256', 'limits', 'main_cgroup', 'main_cgroup_identity')
    require(all(row['old_QA_epoch_invalid'] is True and row['new_QA_epoch_qualified'] is False and
                row['runtime_authorization_enabled'] is False for row in [before, after]),
            'host build snapshot cannot authorize a QA epoch')
    changes = [name for name in identities if before[name] != after[name]]
    require(set(before['memory_events']) == set(after['memory_events']), 'Main memory counter schema changed')
    delta = {name: after['memory_events'][name] - value for name, value in before['memory_events'].items()}
    require(all(value >= 0 for value in delta.values()), 'Main memory counters regressed')
    oom_zero = all(delta[name] == 0 for name in ('oom', 'oom_kill', 'oom_group_kill'))
    return {'main_fence_pass': not changes and oom_zero, 'identity_or_limit_changes': changes,
            'main_memory_event_deltas': delta, 'main_oom_delta_zero': oom_zero,
            'main_current_resource_deltas': {name: after['current_resources'][name] - value
                                            for name, value in before['current_resources'].items()},
            'pressure_counter_increases_observed': {name: value for name, value in delta.items()
                                                  if value and name not in ('oom', 'oom_kill', 'oom_group_kill')},
            'unobserved_transient_effects_excluded': False,
            'causal_attribution_of_counter_changes': False,
            'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
            'scope': 'Only the pinned pre/post invariants and OOM deltas are gated; full interval absence of interference is not claimed.'}


def run(packet):
    require(len(PREPARATION_SHA) == 64 and all(c in "0123456789abcdef" for c in PREPARATION_SHA),
            "a new actual streaming preparation receipt is required")
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'outer build controller must remain UID1000')
    os.umask(0o077)
    source = packet['controller_source'].encode()
    snapshot = packet['snapshot_source'].encode()
    require(sha(source) == CONTROLLER_SHA and sha(snapshot) == SNAPSHOT_SHA == packet['snapshot_sha256'], 'embedded source changed')
    support = capture_support(packet)
    scope = {'__name__': 'frozen_combined_build', '__file__': '<frozen-combined-build>',
             'VERIFIED_CONTROLLER_SHA256': CONTROLLER_SHA}
    exec(compile(source, 'frozen_combined_build.py', 'exec'), scope, scope)
    scope['no_alias'](ROOT)
    require(sha((ROOT / 'control-source/actual-work-preparation.json').read_bytes()) == PREPARATION_SHA,
            'staged actual work preparation changed')
    require(not FENCE_ROOT.exists() and not FENCE_ROOT.is_symlink(), 'fence root already exists; reconcile exact job')
    FENCE_ROOT.mkdir(mode=0o700)
    save('claim.json', {'schema': 1, 'state': 'READONLY_MAIN_FENCE_BEFORE_FULL_BUILD',
                       'controller_sha256': CONTROLLER_SHA, 'preparation_sha256': PREPARATION_SHA,
                       'snapshot_sha256': packet['snapshot_sha256'], 'uid': os.getuid(),
                       'automatic_retry': False, 'Main_actions': 0})
    before = after = assessment = None
    lifecycle_controls = None
    inner_code = None
    failure = None
    attempted = False
    started = time.monotonic()
    def interrupted(signum, frame):
        raise InterruptedError('fenced build received signal ' + str(signum))
    old_term = signal.signal(signal.SIGTERM, interrupted)
    old_int = signal.signal(signal.SIGINT, interrupted)
    try:
        lifecycle_controls = run_capture_lifecycle_controls(snapshot, packet['snapshot_sha256'], support)
        before = capture('before', snapshot, packet['snapshot_sha256'], support)
        require(before['limits'] == {'memory.high': '5368709120', 'memory.max': '6442450944', 'memory.swap.max': 'max', 'cpu.max': '200000 100000', 'pids.max': '12288'},
                'original activation five-limit contract differs; TasksMax must remain 12288')
        save('before.json', before)
        attempted = True
        inner_code = scope['main'](['--build', '--preparation-sha256', PREPARATION_SHA])
        require(inner_code == 0, 'inner full build failed')
    except BaseException as error:
        failure = repr(error)
    finally:
        # The inner controller has already retired its owned build children.
        # Each fixed root supervisor keeps the original 15-second snapshot
        # observation budget and retires its own root children within 5 more.
        # The outer owned sudo session has a separate 25+5-second deadline.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            after = capture('after', snapshot, packet['snapshot_sha256'], support)
            require(after['limits'] == {'memory.high': '5368709120', 'memory.max': '6442450944', 'memory.swap.max': 'max', 'cpu.max': '200000 100000', 'pids.max': '12288'},
                    'original activation five-limit contract differs after build')
            save('after.json', after)
            if before is not None:
                assessment = compare(before, after)
                if not assessment['main_fence_pass'] and failure is None:
                    failure = 'current eight-role identity, historical activation, limits or OOM fence failed'
        except BaseException as error:
            if failure is None:
                failure = repr(error)
            else:
                failure += '; post-fence: ' + repr(error)
        terminal = {'schema': 1, 'state': 'BUILD_AND_OBSERVED_MAIN_FENCES_PASSED' if failure is None else 'FAILED',
                    'error': failure, 'inner_build_called': attempted, 'inner_returncode': inner_code,
                    'seconds': time.monotonic() - started, 'main_fence_assessment': assessment,
                    'before_observed': before is not None, 'after_observed': after is not None,
                    'capture_lifecycle_controls': lifecycle_controls,
                    'capture_lifecycle_receipts': support['receipts'],
                    'root_capture_lifecycle_source_sha256': LIFECYCLE_SHA,
                    'root_capture_supervisor_source_sha256': ROOT_SUPERVISOR_SHA,
                    'Main_actions': 0, 'Android_actions': 0, 'main_unchanged_not_inferred_from_actions': True,
                    'installed': False, 'production_ready': False,
                    'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
                    'runtime_authorization_enabled': False}
        try:
            save('terminal.json', terminal)
            print(json.dumps({'state': terminal['state'], 'error': failure,
                              'inner_returncode': inner_code, 'main_fence_assessment': assessment,
                              'terminal_sha256': sha((FENCE_ROOT / 'terminal.json').read_bytes())}), flush=True)
        finally:
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)
    return 0 if failure is None else 1


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps({'state': 'PLAN_ONLY', 'new_fence_root': str(FENCE_ROOT),
                          'prepared_sha256': PREPARATION_SHA, 'Main_actions': 0,
                          'build_started': False, 'feature_enabled': False}))
    else:
        try:
            raise SystemExit(run(PACKET))
        except Exception as error:
            print(json.dumps({'state': 'FENCE_ADMISSION_FAILED', 'error': repr(error),
                              'Main_actions': 0, 'production_ready': False}), flush=True)
            raise SystemExit(1)
