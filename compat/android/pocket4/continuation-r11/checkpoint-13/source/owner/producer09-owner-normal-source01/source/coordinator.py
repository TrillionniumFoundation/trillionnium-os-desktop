#!/usr/bin/env python3
"""External once-only unit/Invocation/Main binding and exact normal retirement."""
import argparse, hashlib, json, os, signal, stat, subprocess, sys, time, traceback, types
from pathlib import Path

def load(args):
    raw = Path(args.prepared).read_bytes()
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != args.prepared_sha256:
        raise RuntimeError('external prepared digest differs')
    prepared = json.loads(raw)
    if not prepared.get('success'): raise RuntimeError('preparation did not succeed')
    here = Path(__file__).parent
    modules = {}
    for name in ('pinned_support', 'owned', 'prepare', 'qualify'):
        path = here / (name + '.py'); fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd); body = os.read(fd, 256 * 1024)
            row = prepared['source_files'][name + '.py']
            if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022 or len(body) != row['bytes'] or hashlib.sha256(body).hexdigest() != row['sha256']:
                raise RuntimeError('held packaged module differs: ' + name)
        finally: os.close(fd)
        module = types.ModuleType(name); module.__file__ = str(path); sys.modules[name] = module
        exec(compile(body, str(path), 'exec'), module.__dict__); modules[name] = module
    owned = modules['owned']; plan, _ = owned.read_json(here.parent / 'plan.json', prepared['plan_sha256'])
    owned.need(str(here) == plan['package'] + '/source' and str(args.prepared) == plan['state'] + '/prepared.json', 'package/state authority differs')
    for name, row in prepared['source_files'].items():
        fd = modules['pinned_support'].pinned(here / name, row['sha256'])
        os.close(fd)
    return prepared, plan, modules


def bind_unit(current, plan, invocation=None):
    if current.get('LoadState') != 'loaded' or current.get('Description') != plan['description'] or current.get('Transient') != 'yes':
        raise RuntimeError('unit identity/description differs from owned attempt')
    value = current.get('InvocationID', '')
    if len(value) != 32 or not all(c in '0123456789abcdef' for c in value):
        raise RuntimeError('owned invocation is missing or malformed')
    if invocation is not None and value != invocation:
        raise RuntimeError('owned unit invocation changed')
    return value


def run(args, prepared, plan, modules):
    owned, support, prepare, qualify = (modules[x] for x in ('owned', 'pinned_support', 'prepare', 'qualify'))
    result = {'schema': 1, 'kind': 'owner07-normal-external-coordinator01', 'success': False,
        'attempt_nonce': plan['attempt_nonce'], 'prepared_sha256': args.prepared_sha256,
        'production_ready': False, 'installed_owner_qualified': False, 'rc_property_reload_qualified': False,
        'pressure_effect_qualified': False, 'app_qualified': False, 'errors': [], 'started_monotonic_ns': time.monotonic_ns()}
    state = group_fd = -1; actor = None; fence = None; invocation = None; launched = False; tools = {}
    try:
        owned.need(os.getuid() == os.geteuid() == os.getgid() == 0, 'external controller requires original host root')
        owned.need(plan['unit'] == 'p4-owner09-normal-20261105-01.service' and
                   plan['package'] == '/opt/p4-owner09-normal-20261105-01' and
                   plan['state'] == '/opt/p4-owner09-normal-20261105-01-state', 'this controller accepts only its fixed fresh unit/package/state')
        state = owned.root_directory(plan['state'])
        owned.need(owned.file_id(state) == prepared['state_identity'], 'prepared state replaced')
        for name in ('coordinator-claim.json', 'gate.json', 'runtime-claim.json', 'actor-result.json', 'runtime-result.json'):
            owned.need(not os.path.lexists(Path(plan['state']) / name), 'normal attempt already claimed: ' + name)
        for path in ('/usr/bin/python3', '/usr/bin/systemctl', '/usr/bin/systemd-run'):
            fd, observed = prepare.inspect_tool(path, prepared['tools'][path]['sha256'])
            tools[path] = fd; owned.need(observed == prepared['tools'][path], 'prepared controller tool replaced')
        fence = support.MainFence(plan, vars(support)); result['main_before'] = fence.check()
        result['resources_before'] = prepare.resources(plan)
        result['ids_before'] = prepare.available_ids(plan['spec'])
        owned.need(support.props(plan['unit']).get('LoadState') == 'not-found', 'normal unit already exists')
        owned.save(state, 'coordinator-claim.json', {'attempt_nonce': plan['attempt_nonce'], 'prepared_sha256': args.prepared_sha256,
            'unit': plan['unit'], 'description': plan['description'], 'retry_allowed': False})
        limits = plan['outer_limits']
        properties = ['Type=exec', 'RemainAfterExit=yes', 'Restart=no', 'KillMode=control-group', 'OOMPolicy=stop',
            'TimeoutStopSec=10', 'RuntimeMaxSec=180', 'Nice=10', 'UMask=0077', 'CPUQuota=100%', 'CPUQuotaPeriodSec=100ms',
            'MemoryMax=' + limits['memory.max'], 'MemoryHigh=' + limits['memory.high'],
            'MemorySwapMax=0', 'TasksMax=' + limits['pids.max'], 'Delegate=cpu memory pids',
            'Description=' + plan['description']]
        command = ['/usr/bin/systemd-run', '--unit=' + plan['unit'], '--slice=system.slice']
        command += ['--property=' + value for value in properties]
        command += ['--', '/usr/bin/python3', '-I', '-B', plan['package'] + '/source/actor.py',
            '--prepared', args.prepared, '--prepared-sha256', args.prepared_sha256]
        result['launch_command'] = command; launched = True
        started = subprocess.run(command, executable='/proc/self/fd/' + str(tools['/usr/bin/systemd-run']),
            pass_fds=(tools['/usr/bin/systemd-run'],), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=True, env=support.ENV, timeout=8)
        result['launch'] = {'returncode': started.returncode, 'stdout': started.stdout.decode(), 'stderr': started.stderr.decode()}
        owned.need(started.returncode == 0 and len(started.stdout) + len(started.stderr) <= 65536, 'owned unit dispatch failed')
        end = time.monotonic() + 6
        while True:
            current = support.props(plan['unit']); invocation = bind_unit(current, plan, invocation)
            if current.get('MainPID', '0').isdigit() and int(current['MainPID']) > 0: break
            owned.need(time.monotonic() < end, 'actual owned unit MainPID absent'); time.sleep(0.02)
        owned.need(current['ControlGroup'] == '/system.slice/' + plan['unit'], 'actual new unit cgroup differs')
        actor = owned.Process(int(current['MainPID']))
        owned.need(actor.exe_sha256 == prepared['tools']['/usr/bin/python3']['sha256'], 'actual actor interpreter differs')
        group_fd = owned.directory('/sys/fs/cgroup' + current['ControlGroup']); owned.require_cgroup2(group_fd)
        initial = owned.sample_cgroup(group_fd); owned.require_limits(initial, limits)
        owned.need(initial['values']['cgroup.procs'].split() == [str(actor.value['pid'])] and initial['values']['pids.current'] == '1', 'initial unit has an unexpected descendant')
        result['first_unit'] = current; result['first_cgroup'] = initial; result['first_actor'] = actor.snapshot()
        owned.need(actor.value['cgroup'] == ['0::' + current['ControlGroup']], 'first actor did not begin in exact unit root')
        result['main_before_gate'] = fence.check()
        gate = {'attempt_nonce': plan['attempt_nonce'], 'prepared_sha256': args.prepared_sha256,
                'actor_process': actor.observation(), 'cgroup_identity': initial['identity'], 'invocation': invocation}
        result['gate_sha256'] = owned.save(state, 'gate.json', gate)
        # Wait only on this retained actor; systemd's exact finite unit is the
        # independent outer boundary if the original Stop cannot finish.
        end = time.monotonic() + plan['runtime_max_seconds'] + 5
        last_fence = 0.0
        while not owned.dead(actor.pidfd):
            owned.need(time.monotonic() < end, 'owned actual actor exceeded its runtime envelope')
            current = support.props(plan['unit']); bind_unit(current, plan, invocation)
            if time.monotonic() - last_fence >= 2:
                fence.check(); last_fence = time.monotonic()
            time.sleep(0.1)
        terminal = support.props(plan['unit']); bind_unit(terminal, plan, invocation)
        result['terminal'] = terminal
        # Preserve the actual actor's first failure before qualifying its exit.
        # A missing actor record remains a failure with the original terminal.
        actual, actual_sha = owned.read_json(Path(plan['state']) / 'actor-result.json')
        result['actor_result_sha256'] = actual_sha
        result['actor_result'] = actual
        if actual.get('first_error') is not None:
            result['first_actor_error'] = actual['first_error']
        owned.need(terminal.get('ExecMainPID') == str(actor.value['pid']) and terminal.get('ExecMainCode') == '1' and
                   terminal.get('ExecMainStatus') == '0' and terminal.get('Result') == 'success',
                   'owned unit authoritative terminal failed; actor first error=' + repr(actual.get('first_error')))
        owned.need(actual['success'] is True and actual['errors'] == [] and actual['prepared_sha256'] == args.prepared_sha256 and
                   actual['gate_sha256'] == result['gate_sha256'] and actual['attempt_nonce'] == plan['attempt_nonce'], 'actual NORMAL result or gate binding failed')
        owned.need(qualify.qualify_lifecycle(plan, actual), 'independent lifecycle qualifier failed')
        final = actual['outer_final']
        owned.need(final['unit'] == plan['unit'] and final['invocation'] == invocation and
                   final['attempt_nonce'] == plan['attempt_nonce'] and final['actor_pid'] == actor.value['pid'] and
                   final['sample']['identity'] == initial['identity'], 'outer-final differs from first held unit/cgroup')
        owned.require_limits(final['sample'], limits); owned.healthy(initial, final['sample'])
        owned.need(final['sample']['values']['pids.current'] == '1' and
                   int(terminal['MemoryPeak']) < int(limits['memory.max']) and int(terminal['MemorySwapPeak']) == 0,
                   'actual terminal resource envelope failed')
        start_ns = int(terminal['ExecMainStartTimestampMonotonic']) * 1000
        exit_ns = int(terminal['ExecMainExitTimestampMonotonic']) * 1000
        owned.need(start_ns <= final['observed_monotonic_ns'] <= actual['finished_monotonic_ns'] <= exit_ns,
                   'outer-final is not inside the actual unit invocation')
        result['actual_first_owner_normal_qualified'] = True
    except BaseException as error:
        owned.record_error(result, 'normal_coordinator', error); result['traceback'] = traceback.format_exc()
    finally:
        if launched:
            try:
                current = support.props(plan['unit'])
                if current.get('LoadState') != 'not-found':
                    invocation = bind_unit(current, plan, invocation)
                    result['cleanup_before'] = current
                    cleanup = support.call(['/usr/bin/systemctl', 'stop', plan['unit']], timeout=15)
                    result['cleanup_stop_returncode'] = cleanup.returncode
                    # A failed unit is retained by systemd until reset; only this
                    # already-bound invocation may be reset after it is dead.
                    after = support.props(plan['unit'])
                    if after.get('LoadState') != 'not-found':
                        bind_unit(after, plan, invocation)
                        owned.need(after.get('MainPID', '0') == '0' and after.get('ActiveState') in ('inactive', 'failed'), 'owned unit still active after stop')
                        if after.get('ActiveState') == 'failed': support.call(['/usr/bin/systemctl', 'reset-failed', plan['unit']], timeout=5)
                    end = time.monotonic() + 8
                    while support.props(plan['unit']).get('LoadState') != 'not-found':
                        owned.need(time.monotonic() < end, 'owned transient unit retained after exact stop'); time.sleep(0.1)
                if actor is not None: owned.await_dead(actor.pidfd, 2)
                owned.need(not os.path.lexists('/sys/fs/cgroup/system.slice/' + plan['unit']), 'owned cgroup remains after exact stop')
                result['exact_unit_cleanup'] = {'unit': plan['unit'], 'invocation': invocation, 'unit_not_found': True, 'cgroup_absent': True,
                    'original_actor_dead': actor is not None and owned.dead(actor.pidfd)}
            except BaseException as error: owned.record_error(result, 'exact_unit_cleanup', error)
        if fence is not None:
            try: result['main_after'] = fence.check()
            except BaseException as error: owned.record_error(result, 'main_after', error)
            finally: fence.close()
        result['success'] = (not result['errors'] and result.get('actual_first_owner_normal_qualified') is True and
                             result.get('exact_unit_cleanup', {}).get('original_actor_dead') is True and 'main_after' in result)
        result['finished_monotonic_ns'] = time.monotonic_ns()
        if state >= 0:
            owned.save(state, 'runtime-result.json', result)
        if actor is not None: actor.close()
        if group_fd >= 0: os.close(group_fd)
        if state >= 0: os.close(state)
        for fd in tools.values(): os.close(fd)
    encoded = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    print(json.dumps({'success': result['success'], 'result_path': plan['state'] + '/runtime-result.json',
        'bytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest(), 'first_error': result.get('first_error'),
        'actual_first_owner_normal_qualified': result.get('actual_first_owner_normal_qualified', False), 'production_ready': False}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--prepared', required=True); parser.add_argument('--prepared-sha256', required=True)
    args = parser.parse_args()
    raise SystemExit(run(args, *load(args)))


