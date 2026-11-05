#!/usr/bin/env python3
"""Read retained actual evidence only; never dispatch or execute native controls."""
import ast
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path('/workspace/scratch/94990735b266')
WORK = ROOT / 'lmkd-recovery-20261105-01'
EVIDENCE = ROOT / 'root-recovery-20261104-02/evidence'
HERE = Path(__file__).resolve().parent
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-child-exit-r11-build-15-01'
COMPILE_SHA = '3327495b8cc3302dcc18ac72a7495f88d3354788404d2b05d1194d1e6e89ee30'
RUN_SHA = 'ae364c528e0fca047357b13d91814bd461cc539320e78450a096ed64f889c76e'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    return raw


def evidence(kind, filename, size, digest, job):
    directory = EVIDENCE / kind
    raw = pinned(directory / filename, size, digest)
    result = json.loads(raw)
    status_raw = (directory / 'status01.tool-original.json').read_bytes()
    status = json.loads(status_raw)
    assert status['job_id'] == job and status['state'] == 'succeeded' and status['exit_code'] == 0
    assert all(status[k] is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert status['timed_out'] is False and status['cancelled'] is False
    stdout_raw = (directory / 'stdout.log').read_bytes()
    stdout = json.loads(stdout_raw)
    assert stdout['success'] is True and stdout['error'] is None
    assert stdout['bytes'] == size and stdout['sha256'] == digest
    assert (directory / 'stderr.log').read_bytes() == b''
    for stream, count in [('stdout', len(stdout_raw)), ('stderr', 0)]:
        assert status['log_bytes'][stream] == {'seen': count, 'stored': count}
        assert status['log_synced'][stream] is True and status['log_truncated'][stream] is False
        assert status['log_errors'][stream] is None
    assert result['success'] is True and 'error' not in result and 'traceback' not in result
    return result, {'path': str(directory / filename), 'bytes': len(raw), 'sha256': sha(raw),
        'job_id': job, 'terminal_state': 'succeeded', 'exit_code': 0,
        'complete': True, 'durable': True, 'stdout_bytes': len(stdout_raw),
        'stdout_sha256': sha(stdout_raw), 'terminal_sha256': sha(status_raw)}, stdout


def manifest(directory, digest):
    raw = (directory / 'manifest.json').read_bytes()
    assert sha(raw) == digest
    rows = json.loads(raw)['files']
    for row in rows:
        pinned(directory / row['path'], row['bytes'], row['sha256'])
    return rows


def resource(result, job, budget, peak):
    health = result['resource_health']
    before, after = health['before'], health['after']
    assert health['held_own_cgroup_gate_passed'] is True and health['cgroup_files_written'] is False
    assert health['whole_invocation_resource_qualified'] is False and health['swap_zero_claimed'] is False
    for key in ('cgroup_identity', 'mount_identity', 'namespaces', 'limits', 'membership', 'pid'):
        assert before[key] == after[key]
    assert after['membership'] == '0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-' + job + '.service\n'
    assert after['limits'] == {'cpu.max': [100000, 100000], 'memory.high': 'max',
        'memory.max': budget, 'memory.swap.max': 'max', 'pids.max': 30053}
    assert after['memory_peak'] == peak < budget
    assert before['pid'] in before['direct_cgroup_procs'] and after['pid'] in after['direct_cgroup_procs']
    assert before['memory_swap_current'] == before['memory_swap_peak'] == after['memory_swap_current'] == after['memory_swap_peak'] == 0
    assert all(v == 0 for v in health['memory_event_delta'].values())
    assert before['memory_events'] == after['memory_events']
    assert all(v == 0 for v in after['memory_events'].values())
    assert before['started_monotonic_ns'] <= before['completed_monotonic_ns'] < after['started_monotonic_ns'] <= after['completed_monotonic_ns']
    return {'own_gate_passed': True, 'observed_memory_peak_bytes': peak, 'memory_max_bytes': budget,
        'observed_swap_current_and_peak': [0, 0], 'memory_swap_max': 'max', 'pids_max': 30053,
        'memory_event_delta': health['memory_event_delta'], 'whole_invocation_resource_qualified': False}


def main():
    cb, cp, cs = evidence('owner15-compile01', 'compile-result.json', 39999, COMPILE_SHA, '1a1ac964e6f-fc05-5590')
    run, rp, rs = evidence('owner15-ordinary01', 'run-result.json', 37356, RUN_SHA, '1a1ac9ce04c-fc05-55dc')
    assert cp['stdout_bytes'] == 363 and rp['stdout_bytes'] == 388
    assert rp['stdout_sha256'] == '58a440bf1d3af992e905d3aa6b9cf6569b400be1102f15b8aac41f8383b6ad23'
    assert cs['report'] == REMOTE + '/compile-result.json'
    assert rs['report'] == REMOTE + '/ordinary-run-01/run-result.json'
    controller = WORK / 'producer15-child-exit-controller-freeze-01'
    source = WORK / 'namespace-child-exit-source-freeze-15'
    source_rows = manifest(source, 'a50606bd1352c885fe98a20733d340b565a87849413f579321e86e40fecc2634')
    controller_rows = manifest(controller, 'ebe67de541ba7766944aa19749c687b8a6966bd026a43fcb80e6e358b1b94634')
    ordinary = WORK / 'producer15-child-exit-ordinary-freeze-01'
    manifest(ordinary, 'eece86ca742535962b1823931dc9c9619145b050b385bdcc1136fe70fd083eaa')
    cfg_raw = (controller / 'payload.json').read_bytes(); cfg = json.loads(cfg_raw)
    assert cb['payload_sha256'] == sha(cfg_raw)
    assert cb['original_source_diff_sha256'] == cfg['original_diff_sha256'] == sha((source / 'source.diff').read_bytes())
    assert len(cfg['preimage']) == 32 and len(cfg['overlays']) == 4
    for path, row in cfg['overlays'].items():
        assert row['text'].encode() == pinned(source / 'candidate' / path, row['bytes'], row['sha256'])
    expected = {**cfg['preimage'], **{p: {'bytes': v['bytes'], 'sha256': v['sha256']} for p, v in cfg['overlays'].items()}}
    assert cb['preimage_inputs'] == cfg['preimage']
    assert cb['inputs_before'] == cb['inputs_after'] == run['inputs_before'] == run['inputs_after'] == expected
    inv = 'acd7a623dc28f83363d67aec1d4befe64c85cf852fa564312783005abc7a05b8'
    assert cb['all_source_inventory_before_sha256'] == cb['all_source_inventory_after_sha256'] == inv
    assert run['all_source_inventory_before_sha256'] == run['all_source_inventory_after_sha256'] == inv
    assert cb['original_source_inventory_after_sha256'] == '4660754a78ccc0f78272e1786e1395672af41b7fc30a7e259c21eaf3950b7314'
    assert cb['revision'] == run['revision'] == cfg['revision'] == 'producer15-namespace-child-exit01'
    assert run['external_compile_sha256'] == COMPILE_SHA
    request = json.loads((ordinary / 'request.json').read_bytes())
    run_source = (controller / 'run.py').read_bytes()
    assert request['stdin'].encode() == run_source and sha(run_source) == '32f3875a20fb3da3bccf77235e77937c396881f024d9a457bb2a0a17634c0e94'
    assert request['args'] == ['-I', '-B', '-', '--compile-sha256', COMPILE_SHA]
    assert request['idempotency_key'] == 'p4-producer15-child-exit01-ordinary01-' + COMPILE_SHA[:16]
    ast.parse(run_source)
    libs = {x['target_name']: x for x in cb['compiled_test_artifacts']}
    assert set(libs) == {'droidloom_pressure_relay', 'droidloom_supervisor'}
    assert set(cb['artifacts']) == {'droidloomd', 'droidloom-supervisor', 'droidloom-psi-owner', 'owned-ipc-controls'}
    targets = ['lifecycle_bootstrap::tests::producer05_three_second_retirement_is_rejected_before_transport',
        'lifecycle_bootstrap::tests::shared_retirement_bound_sends_exact_request_and_receives_terminal_ack']
    expectations = [(libs['droidloom_pressure_relay'], ['--exact', name, '--test-threads=1', '--nocapture'], 8) for name in targets]
    expectations += [(libs['droidloom_pressure_relay'], ['--test-threads=1'], 30),
        (libs['droidloom_supervisor'], ['--test-threads=1'], 45),
        (cb['artifacts']['owned-ipc-controls'], [], 30),
        (cb['artifacts']['owned-ipc-controls'], ['--worker-context-control'], 10),
        (cb['artifacts']['droidloom-supervisor'], ['relay-entry-abi'], 5)]
    assert len(run['commands']) == len(expectations) == 7
    held_keys = ('path', 'sha256', 'bytes', 'device', 'inode', 'mode')
    child_pids = []
    for i, (command, (elf, args, timeout)) in enumerate(zip(run['commands'], expectations)):
        assert command['actual_held_elf'] == {k: elf[k] for k in held_keys}
        assert re.fullmatch(r'/proc/self/fd/[0-9]+', command['argv'][0])
        assert command['argv'][1:] == args and command['timeout_seconds'] == timeout
        assert command['cwd'] == REMOTE + '/candidate'
        assert command['returncode'] == 0 and command['timed_out'] is False
        child_pids.append(command['exact_child_pid'])
        assert child_pids[-1] > 0
        assert datetime.fromisoformat(run['started_at']) <= datetime.fromisoformat(command['started_at']) <= datetime.fromisoformat(command['finished_at']) <= datetime.fromisoformat(run['finished_at'])
        assert command['stderr_excerpt'] == '' and command['stderr_pin']['bytes'] == 0
        assert command['stderr_pin']['sha256'] == sha(b'')
        for stream in ('stdout', 'stderr'):
            assert command[stream + '_path'] == REMOTE + '/ordinary-run-01/command-%02d.%s' % (i, stream)
            assert command[stream + '_pin']['path'] == command[stream + '_path']
            if command[stream + '_pin']['bytes'] <= 4096:
                text = command[stream + '_excerpt'].encode()
                assert len(text) == command[stream + '_pin']['bytes'] and sha(text) == command[stream + '_pin']['sha256']
    assert len(set(child_pids)) == 7
    for i, (passed, filtered) in enumerate([(1, 38), (1, 38), (39, 0), (128, 0)]):
        found = re.findall(r'^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', run['commands'][i]['stdout_excerpt'], re.M)
        assert found == [('ok', str(passed), '0', '0', '0', str(filtered))]
    assert run['targeted_public_retirement_controls'] == [dict(name=n, passed=1, failed=0, ignored=0, measured=0, filtered_out=38) for n in targets]
    assert run['rust_tests_passed'] == {'droidloom-pressure-relay': 39, 'droidloom-supervisor': 128}
    assert run['rust_test_binary_counts'] == {'droidloom_pressure_relay:lib': 39, 'droidloom_supervisor:lib': 128}
    assert run['ordinary_ipc_passed'] == 7 and run['worker_context_passed'] is True and run['actual_compiled_entry_abi_passed'] is True
    assert len(re.findall(r'^PASS ', run['commands'][4]['stdout_excerpt'], re.M)) == 7
    assert run['commands'][4]['stdout_excerpt'].endswith('RESULT PASS mode=host-negative-controls\n')
    assert run['commands'][5]['stdout_excerpt'].endswith('RESULT PASS mode=worker-context-without-namespace-or-pressure-effects\n')
    assert run['commands'][6]['stdout_excerpt'] == 'droidloom-relay-entry-v3\n'
    assert run['ordinary_controls_only'] is True
    for key in ('cargo_invoked', 'full_owner_runtime_qualified', 'real_broker_generation_qualified', 'android_runtime_started', 'barrier_constructor_executed', 'pressure_or_namespace_effects_requested', 'installed_files_changed', 'main_fence_claimed'):
        assert run[key] is False
    assert cb['compile_only'] is True and cb['test_binaries_executed'] is False
    old = WORK / 'owner14-normal01-freeze-01'
    old_rows = manifest(old, '80ba3a2d6caaae90cc11e4997a8fc58c527f25e318b0571bc29d827259981e32')
    plan = json.loads((old / 'plan.json').read_bytes())
    assert plan['main']['resources']['pids.max'] == '12288'
    report = {'schema': 1, 'result': 'ACTUAL_COMPILE_AND_ORDINARY15_VERIFIED',
        'scope': 'Retained actual source/artifact/command/resource review, no new native or device execution',
        'compile': cp, 'ordinary': rp, 'source_payload_count': len(source_rows),
        'controller_payload_count': len(controller_rows), 'exact_input_count': len(expected), 'overlay_count': 4,
        'full_candidate_inventory_sha256': inv, 'original14_source_unchanged': True,
        'compiled_artifacts': cb['artifacts'], 'compiled_test_artifacts': cb['compiled_test_artifacts'],
        'actual_test_counts': run['rust_tests_passed'], 'targeted_public_retirement_controls': run['targeted_public_retirement_controls'],
        'ordinary_IPC_passed': 7, 'worker_context_passed': True, 'actual_entry_ABI3_passed': True,
        'seven_exact_direct_children_waited': child_pids, 'all_commands_zero_no_timeout': True,
        'raw_full_command_logs_independently_collected': False,
        'log_review_scope': 'All seven structured command records; complete embedded stdout independently hashed where <=4096B; supervisor larger stdout is a pinned final excerpt with actual summary',
        'compile_resource': resource(cb, cp['job_id'], 1073741824, 739328000),
        'ordinary_resource': resource(run, rp['job_id'], 536870912, 48242688),
        'actual_Owner_qualified': False, 'Android_or_Main_execution_by_this_review': False,
        'original_Owner14_boot_FAILURE_preserved': True,
        'next_prepare': {'original14_payloads_verified': len(old_rows), 'Main_pids_max_fence_retained': '12288',
            'Main_fence_relaxed': False, 'new_nonce_or_UID_or_request_generated': False,
            'admission': 'BLOCKED pending Root resolution and original exact Main fence; ordinary does not authorize Main mutation'}}
    raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    with (HERE / 'report.json').open('xb') as f:
        f.write(raw)
    print(json.dumps({'report': str(HERE / 'report.json'), 'bytes': len(raw), 'sha256': sha(raw),
        'result': report['result'], 'new_native_or_remote_execution': False}, indent=2))


if __name__ == '__main__':
    main()
