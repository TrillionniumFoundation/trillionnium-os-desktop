#!/usr/bin/env python3
"""Local-only derivation from archived receipts; never execute the observer."""
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[3]
BASE = HERE.parent.relative_to(PROJECT).as_posix()
OLD = BASE + '/memory-observation-after-build08-r1'
AUDITS = 'successor_audit_requests/actual/batches-final-r1'
KEY = 'pocket4-after-apk-audit-closure-host-memory-snapshot-r1-20261106'
MINIMUM = 15 * 1024 ** 3
INPUTS = {}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(rel):
    raw = (PROJECT / rel).read_bytes()
    INPUTS[rel] = {'path': rel, 'bytes': len(raw), 'sha256': sha(raw)}
    return raw


def obj(rel):
    return json.loads(read(rel))


def pin(rel):
    if rel not in INPUTS:
        read(rel)
    return INPUTS[rel]


def emit(name, value):
    raw = value if isinstance(value, bytes) else (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                   allow_nan=False) + '\n').encode('utf-8')
    path = HERE / name
    if path.exists():
        need(path.read_bytes() == raw, 'do not overwrite frozen output: ' + name)
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    return {'path': path.relative_to(PROJECT).as_posix(),
            'bytes': len(raw), 'sha256': sha(raw)}


def utc_ms(value):
    need(type(value) is int, 'original timestamp must be integer milliseconds')
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) +
            timedelta(milliseconds=value)).isoformat(timespec='milliseconds')


def durable(t, job_id):
    need(t['job_id'] == job_id and t['state'] in ('succeeded', 'failed'),
         'matching actual terminal required')
    for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed'):
        need(t[k] is True, 'durable terminal flag absent: ' + k)
    for k in ('timed_out', 'cancelled', 'automatic_retry'):
        need(t[k] is False, 'unexpected terminal flag: ' + k)
    need(all(v is None for v in t['log_errors'].values()) and
         all(v is False for v in t['log_truncated'].values()) and
         all(v is True for v in t['log_synced'].values()), 'terminal log incomplete')
    need(all(v['seen'] == v['stored'] for v in t['log_bytes'].values()),
         'terminal stored log bytes differ')


def event(label, directory, terminal='status-01.original.txt'):
    start_path = directory + '/start.original.txt'
    terminal_path = directory + '/' + terminal
    s, t = obj(start_path), obj(terminal_path)
    j = s['job']
    need(j['launch_state'] == 'launched' and j['launch_error'] is None,
         'timeline event must have observed launch')
    durable(t, j['id'])
    need(j['created_unix_ms'] <= t['at_unix_ms'], 'event clock order differs')
    return {'label': label, 'job_id': j['id'], 'idempotency_key': j['idempotency_key'],
            'created_unix_ms': j['created_unix_ms'],
            'created_utc': utc_ms(j['created_unix_ms']),
            'terminal_record_unix_ms': t['at_unix_ms'],
            'terminal_record_utc': utc_ms(t['at_unix_ms']),
            'terminal_state': t['state'], 'exit_code': t['exit_code'],
            'start_source': pin(start_path), 'terminal_source': pin(terminal_path)}


def audit_closure(n):
    directory = AUDITS + '/batch-%02d' % n
    e = event('APK audit batch %02d' % n, directory, 'terminal.original.json')
    artifact_path = directory + '/artifact.original.json'
    a = obj(artifact_path)
    stdout_path = directory + '/stdout.original.jsonl'
    lines = [json.loads(line) for line in read(stdout_path).splitlines()]
    need(len(lines) == 2 and lines[0]['source_stage_ok'] is True,
         'actual stage and final outer stdout required')
    outer = lines[-1]
    life = outer['child_lifecycle']
    for name in ('pidfd_acquired', 'pidfd_exit_observed', 'pidfd_closed',
                 'parent_descriptors_restored'):
        need(life[name] is True, 'audit child lifetime incomplete: ' + name)
    need(life['errors'] == [] and life['timeout'] is False and
         life['owned_child_sigkill_count'] == 0, 'audit child retirement abnormal')
    need(life['returncode'] == e['exit_code'], 'outer exit code differs')
    need(a['all_tool_children_joined'] is True and a['unjoined_tool_pids'] == [] and
         a['action_lock_released'] is True and a['errors'] == [],
         'audit tools or lock not settled')
    fds = a['owned_descriptors_final']
    need(fds['acquired'] == fds['closed'] and fds['remaining'] == 0 and
         fds['errors'] == [] and a['process_FDs_before'] == a['process_FDs_after'],
         'audit descriptors not settled')
    need(all(c['joined'] is True and c['timed_out'] is False and
             c['own_group_kill_requested'] is False and c['pipes_closed'] is True
             for c in a['commands']), 'audit tool process not retired')
    env = obj(directory + '/worker.stdout.envelope.original.json')
    need(env['artifact_bytes'] == pin(artifact_path)['bytes'] and
         env['artifact_sha256'] == pin(artifact_path)['sha256'], 'artifact pin mismatch')
    gate = obj(directory + '/gate-status.stdout.original.json')
    if n < 13:
        need(e['exit_code'] == 0 and e['terminal_state'] == 'succeeded' and
             outer['ok'] is True and outer['errors'] == [], 'earlier audit failed')
        entry = next(x for x in gate['completed'] if x['batch'] == n)
        need(entry['job_id'] == e['job_id'] and
             entry['artifact_sha256'] == pin(artifact_path)['sha256'] and
             entry['artifact_bytes'] == pin(artifact_path)['bytes'] and
             entry['original_child_pidfd_retirement_proved'] is True,
             'original coordinator gate mismatch')
    else:
        need(e['exit_code'] == 1 and e['terminal_state'] == 'failed' and
             outer['ok'] is False and
             a['status'] == 'LINKED_ORIGINAL_BATCH_AUDIT_INCOMPLETE_NO_RETRY',
             'preserve original final batch failure')
        need(gate['state'] == 'STOP_NO_RETRY' and
             gate['reason'] == 'EXACT_DURABLE_TERMINAL_REQUIRED',
             'preserve original coordinator rejection')
    failures = [{'package': app['package'], 'parse_errors': apk.get('parse_errors', [])}
                for app in a['apps'] for apk in app['apks'] if apk.get('parse_errors')]
    return e, {'batch': n, 'job_id': e['job_id'], 'terminal_state': e['terminal_state'],
               'exit_code': e['exit_code'], 'audit_status': a['status'],
               'business_or_parse_failures': failures,
               'outer_errors_preserved': outer['errors'],
               'child_result_errors_preserved': outer['child_result']['errors'],
               'child_lifecycle': life, 'tool_children_all_joined': True,
               'action_lock_released': True, 'owned_descriptors_final': fds,
               'lifecycle_settled': True, 'business_result_reclassified': False,
               'artifact_source': pin(artifact_path), 'outer_stdout_source': pin(stdout_path),
               'terminal_source': e['terminal_source'],
               'coordinator_gate_source': pin(directory + '/gate-status.stdout.original.json')}


def main():
    need(PROJECT.name == 'pocket4_eight_apps', 'fixed project root differs')
    original_source = read(OLD + '/observe_host_memory_once.py')
    need(len(original_source) == 2419 and sha(original_source) ==
         'be0f84a10597fb63caad4395e4d9c32191f906f276636eb913f03307fa597b3b',
         'original byte-exact observer differs')
    ast.parse(original_source)
    original_request = obj(OLD + '/process-request.json')
    need(original_request['args'] == ['-I', '-B', '-c', original_source.decode(), '--sample-once'],
         'original request does not contain exact observer')
    request = dict(original_request, idempotency_key=KEY)
    need([k for k in request if request[k] != original_request[k]] == ['idempotency_key'],
         'only the request key may change')

    events = [
        event('earlier QA case, failed preserved', 'successor_qa/explore_home_search_case_r1/actual',
              'status-02.original.txt'),
        event('Beike permission pilot', 'successor_audit_requests/beike_permission_pilot_r1/actual'),
        event('Calendar original readback',
              'successor_audit_requests/diagnostics/calendar-official-aapt2-raw-readback-r1/actual'),
        event('permission pilot raw readback',
              'successor_audit_requests/beike_permission_pilot_r1/raw-readback-r1/actual-public'),
        event('QA case failure original readback', 'successor_qa/case_failure_reader_r1/actual-public'),
        event('build08 resource rejection', BASE + '/actual-build08'),
        event('QA inspection after rejection', 'successor_qa/inspect_after_search_rejection_r1/actual'),
        event('b05 independent correction',
              'successor_audit_requests/revisions/b05-official-tool-repair-r1/actual'),
        event('previous host RAM observer', OLD + '/actual'),
        event('QA inspection original readback',
              'successor_qa/inspect_after_search_rejection_reader_r1/actual-public'),
        event('S40 one DNS observation', 'official_source_scripts/s40_zbj_dns_probe/actual'),
    ]
    closures = []
    for n in range(6, 14):
        e, closure = audit_closure(n)
        events.append(e)
        closures.append(closure)

    rpath = BASE + '/actual-build08/resource-admission.original.json'
    r = obj(rpath)
    mpath = OLD + '/actual/stdout.original.json'
    m = obj(mpath)
    raw = r['meminfo']['raw_ascii'].encode('ascii')
    need(len(raw) == r['meminfo']['bytes'] and sha(raw) == r['meminfo']['sha256'],
         'original build meminfo digest differs')
    raw2 = m['raw_ascii'].encode('ascii')
    need(len(raw2) == m['raw_bytes'] and sha(raw2) == m['raw_sha256'],
         'original observer meminfo digest differs')
    available = int(next(line.split()[1] for line in raw.decode().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    available2 = m['values_bytes']['MemAvailable']
    need(r['profile']['minimum_fresh_MemAvailable_bytes'] == m['original_minimum_bytes'] == MINIMUM,
         'original threshold differs')
    samples = [
        {'label': 'build08 immediate resource observation', 'source': pin(rpath),
         'observed_utc': r['observed_utc'],
         'observed_unix_ns_decimal_original': r['observed_unix_ns_decimal'],
         'MemAvailable_bytes': available, 'minimum_bytes': MINIMUM,
         'shortfall_bytes': MINIMUM - available,
         'shortfall_MiB': (MINIMUM - available) / 1024 ** 2},
        {'label': 'later one-time host observation', 'source': pin(mpath),
         'observed_utc': m['observed_utc'], 'MemAvailable_bytes': available2,
         'minimum_bytes': MINIMUM, 'shortfall_bytes': MINIMUM - available2,
         'shortfall_MiB': (MINIMUM - available2) / 1024 ** 2},
    ]
    for sample in samples:
        observed = datetime.fromisoformat(sample['observed_utc'])
        sample['selected_archived_lifecycle_bounds_containing_sample'] = [
            e['job_id'] for e in events
            if datetime.fromisoformat(e['created_utc']) <= observed <=
            datetime.fromisoformat(e['terminal_record_utc'])]
    unknown_dir = 'successor_qa/actual/inspect-after-close-r1-launch-unknown'
    u = obj(unknown_dir + '/process-start.raw.json')
    if 'content' in u:
        u = json.loads(next(x['text'] for x in u['content'] if x['type'] == 'text'))
    need(u['job']['launch_state'] == 'launch_unknown', 'historical unknown changed')
    unit = obj(unknown_dir + '/unit-status.raw.json')
    need(unit['services'][0]['resolution'] == 'not_found', 'historical unit observation differs')
    unknown = {'job_id': u['job']['id'], 'launch_state': 'launch_unknown',
               'created_unix_ms': u['job']['created_unix_ms'],
               'created_utc': utc_ms(u['job']['created_unix_ms']),
               'launch_source': pin(unknown_dir + '/process-start.raw.json'),
               'same_key_reconciliation_source': pin(unknown_dir + '/process-start-reconcile1.raw.json'),
               'unit_observation_source': pin(unknown_dir + '/unit-status.raw.json'),
               'status_errors': [pin(unknown_dir + '/' + name) for name in
                   ('process-status-initial-error.raw.txt', 'process-status-recheck-error.raw.txt')],
               'interpretation': 'No durable terminal; inactive/not-found unit properties do not prove execution success or identify a RAM consumer.',
               'resolved': False, 'inferred_running': False, 'inferred_causal': False}
    fence = obj(BASE + '/actual-build08/fence-terminal.original.json')
    need(fence['main_fence_assessment']['main_fence_pass'] is True,
         'build08 original Main fence differs')
    timeline = {
        'schema': 'pocket4-local-build08-audit-memory-timeline-v1',
        'analysis_uses_only_archived_originals': True,
        'timestamps_are_created_and_terminal_record_bounds_not_CPU_execution_times': True,
        'samples': samples, 'selected_job_events': sorted(events, key=lambda x: x['created_unix_ms']),
        'MemAvailable_change_bytes': available2 - available,
        'MemAvailable_change_MiB': (available2 - available) / 1024 ** 2,
        'elapsed_sample_seconds': (datetime.fromisoformat(m['observed_utc']) -
                                   datetime.fromisoformat(r['observed_utc'])).total_seconds(),
        'b06_through_b13_started_after_both_samples': all(
            datetime.fromisoformat(e['created_utc']) > datetime.fromisoformat(m['observed_utc'])
            for e in events if e['label'].startswith('APK audit batch')),
        'b05_correction_settled_before_later_sample': next(
            e['terminal_record_unix_ms'] for e in events if e['label'] == 'b05 independent correction') <
            int(datetime.fromisoformat(m['observed_utc']).timestamp() * 1000),
        'historical_unresolved_launch': unknown,
        'build08_original_error': fence['error'],
        'build08_original_Main_fence': fence['main_fence_assessment'],
        'audit_lifecycle_closures': closures,
        'all_b06_through_b13_process_lifetimes_settled': True,
        'all_b06_through_b13_business_checks_passed': False,
        'causal_RAM_attribution': 'UNKNOWN: no per-job RSS trace or full-host process census in these inputs.',
        'coverage': 'Selected nearby archived owned jobs only; not all host processes or long-lived Main services. Historical launch_unknown remains unresolved. A memory cap is not observed memory usage.',
        'build08_compiler_or_Soong_started': False,
        'build08_inner_build_called_does_not_mean_compiler_started': True,
        'current_RAM_observed_by_this_preparation': False,
        'build_or_retry_admitted': False, 'production_ready': False,
    }
    outputs = [emit('observe_host_memory_once.py', original_source),
               emit('process-request.json', request), emit('timeline-and-closure.json', timeline)]
    s41dir = 'official_source_scripts/s41_zbj_finite_tail/candidate-r2/actual'
    s41s, s41t = obj(s41dir + '/start.original.txt'), obj(s41dir + '/status-01.original.txt')
    need(s41s['job']['id'] == s41t['job_id'] == '1a1b2aad530-fc05-7f38', 'S41 archived identity differs')
    plan = {
        'schema': 'pocket4-post-audit-one-RAM-observation-candidate-v1',
        'state': 'PREPARED_NOT_SUBMITTED', 'remote_process_submitted': False,
        'phase': 'After all b06-b13 APK audit processes settled, including preserved failed b13.',
        'observer_source_unchanged': True, 'request_changed_keys': ['idempotency_key'],
        'original_source': pin(OLD + '/observe_host_memory_once.py'),
        'original_request': pin(OLD + '/process-request.json'),
        'new_request': outputs[1], 'timeline_and_closure': outputs[2],
        'idempotency_key': KEY, 'original_threshold_bytes': MINIMUM,
        'one_fixed_read': '/proc/meminfo', 'read_bound_bytes': 16385,
        'accepted_content_max_bytes': 16384, 'worker_seconds_bound': 5,
        'process_limits_unchanged': {k: request[k] for k in
            ('timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice')},
        'S41_last_archived_status': s41t['state'],
        'S41_status_source': pin(s41dir + '/status-01.original.txt'),
        'S41_start_source': pin(s41dir + '/start.original.txt'),
        'concurrent_context': 'Root coordinates S41 host-only download and potential historical UI file readback. No idle-host assumption; this local status is not a future observation.',
        'execution_owner': 'root; review and single explicit submission remain separate',
        'fresh_build_admission_replaced': False, 'build09_packet_prepared': False,
        'build_retry_automatic': False, 'Main_commands': 0, 'Android_commands': 0,
        'settings_changes': 0, 'cache_clears': 0, 'signals': 0, 'remote_writes': 0,
        'APK_audit_business_failures_reclassified': False, 'production_ready': False,
        'local_sealing_checks': {
            'source_full_bytes_match_original': True,
            'only_request_key_changed': True,
            'b06_b13_durable_original_terminals_checked': True,
            'child_pidfd_and_FD_and_tool_and_lock_closure_checked': True,
            'b13_business_and_outer_failure_preserved': True,
            'remote_RAM_or_build_PASS_claimed': False},
    }
    outputs.append(emit('execution-plan.json', plan))
    outputs.append({'path': Path(__file__).relative_to(PROJECT).as_posix(),
                    'bytes': len(Path(__file__).read_bytes()), 'sha256': sha(Path(__file__).read_bytes())})
    manifest = emit('SOURCE_PINS.json', {'schema': 1, 'outputs': outputs,
                                        'inputs': sorted(INPUTS.values(), key=lambda x: x['path'])})
    print(json.dumps({'prepared_not_submitted': True, 'request': outputs[1],
                      'manifest': manifest, 'source_unchanged': True,
                      'b13_failed_preserved': True, 'remote_jobs_started': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
