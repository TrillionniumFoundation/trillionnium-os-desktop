"""Retained Owner11 result review only; no remote/process/runtime effects."""
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266')
EVIDENCE = BASE / 'root-recovery-20261104-02/evidence/owner11-normal01-runtime-read01'
FROZEN = BASE / 'lmkd-recovery-20261105-01/owner11-normal01-runtime-freeze-01'
OUT = Path(__file__).resolve().parent

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

raw = (EVIDENCE / 'runtime-result.json').read_bytes()
reader_raw = (EVIDENCE / 'reader-report.json').read_bytes()
assert len(raw) == 53545 and sha(raw) == 'a04dbc0f1073c5ffb5f7fdbd549618af4b316a98688d3ecfe0622d05ef98303d'
assert len(reader_raw) == 58766 and sha(reader_raw) == 'e82237e7102f20dcfddde02e710923f21a9de2af5d89830ccb945958ad5c82cb'
runtime, reader = json.loads(raw), json.loads(reader_raw)
assert reader['collection_complete'] is True and reader['errors'] == []
assert reader['files']['runtime-result.json']['content'].encode() == raw
assert runtime['prepared_sha256'] == sha((FROZEN / 'actual-prepared.json').read_bytes())
prepared = json.loads((FROZEN / 'actual-prepared.json').read_bytes())
assert runtime['attempt_nonce'] == prepared['attempt_nonce']
terminal, first = runtime['terminal'], runtime['first_unit']
actor, cleanup = runtime['actor_result'], runtime['exact_unit_cleanup']
invocation, pid = terminal['InvocationID'], int(terminal['ExecMainPID'])
assert invocation == first['InvocationID'] == actor['invocation'] == cleanup['invocation']
assert pid == int(first['ExecMainPID']) == actor['actor_pid'] == runtime['first_actor']['process']['pid']
assert runtime['first_actor']['identity']['pid'] == pid
assert all(cleanup[k] is True for k in ('original_actor_dead', 'cgroup_absent', 'unit_not_found'))
assert runtime['main_before'] == runtime['main_before_gate'] == runtime['main_after']
assert runtime['success'] is False and actor['success'] is False and terminal['ExecMainStatus'] == '1'
assert all(runtime[k] is False for k in ('production_ready', 'app_qualified', 'installed_owner_qualified', 'pressure_effect_qualified', 'rc_property_reload_qualified'))
status = actor['latest_status']
audit = status['relay_lifecycle']
records = audit['records']
events = [r['detail']['event'] for r in records]
assert events == ['prepared', 'owner_attached', 'init_hello', 'broker_ready',
                  'init_project_sent', 'init_projected_accepted', 'init_commit_sent',
                  'init_done_accepted', 'retiring']
assert [r['sequence'] for r in records] == list(range(1, 10))
assert all(a['observed_monotonic_ns'] <= b['observed_monotonic_ns'] for a, b in zip(records, records[1:]))
assert audit['recording_error'] is None and audit['recording_incomplete'] is False
assert audit['first_failure']['message'] == 'owned process generation is dead or changed'
assert audit['retirement_failure']['message'] == 'rejected: lifecycle bootstrap disconnected'
assert status['state'] == 'cleanup_failed' and status['ok'] is False
assert actor['failure_cleanup_stop'] == status
assert [r['stage'] for r in actor['errors']] == ['normal', 'failure_cleanup_stop', 'retire_daemon', 'outer_final']
assert actor['errors'][-1]['error'] == "RuntimeError('generation cgroup residue remains')"
assert all(r['reaped'] is True and r['forced_kill'] is False for r in actor['child_retirement'])
assert next(r for r in actor['child_retirement'] if r['role'] == 'daemon')['returncode'] == 1
hello, obs = records[2]['detail']['init'], actor['init_identity_clock_observation']
for key in ('process', 'namespaces', 'executable', 'executable_sha256'):
    assert hello[key] == obs['snapshot'][key]
assert obs['generation_nonce'] == audit['nonce']
assert obs['audit_observed_monotonic_ns'] == records[2]['observed_monotonic_ns']
assert obs['audit_sequence'] == records[2]['sequence']
assert obs['monotonic_before_ns'] <= obs['monotonic_after_ns']
assert obs['global_kernel_lines_attributed'] is False and obs['atomic_clock_sample'] is False
ready = records[3]['detail']['status']
assert ready['state'] == 1 and ready['granted'] is False and ready['faulted'] is False
assert ready['nonce'] == audit['nonce'] and ready['cgroup'] == records[0]['detail']['domain'] == hello['cgroup']
report = {
    'schema': 1, 'verdict': 'ACTUAL_OWNER11_NORMAL_FAILED_ORIGINAL_RETIREMENT_INCOMPLETE_EXTERNAL_CLEANUP_COMPLETE',
    'runtime_original': {'path': str(EVIDENCE / 'runtime-result.json'), 'bytes': len(raw), 'sha256': sha(raw)},
    'protected_reader_original': {'path': str(EVIDENCE / 'reader-report.json'), 'bytes': len(reader_raw), 'sha256': sha(reader_raw)},
    'attempt_nonce': runtime['attempt_nonce'], 'prepared_sha256': runtime['prepared_sha256'],
    'invocation': invocation, 'actor_pid': pid, 'terminal': terminal,
    'actual_first_error': actor['first_error'], 'actor_errors_preserved_in_order': actor['errors'],
    'generation_nonce': audit['nonce'], 'authority_generation': ready['generation'],
    'domain_identity': ready['cgroup'], 'exact_observed_init': hello['process'],
    'actual_event_prefix': events, 'event_recording_prefix_complete': True,
    'ACTIVE_observed': False, 'normal_Stop_successful': False, 'original_Owner_joined_retirement_proved': False,
    'original_generation_residue_observed_by_actor': True, 'original_Stop_repeated_same_retained_failure': True,
    'first_failure': audit['first_failure'], 'retirement_failure': audit['retirement_failure'],
    'cleanup_failure': audit['cleanup_failure'],
    'DONE_to_first_failure_ns': audit['first_failure']['observed_monotonic_ns'] - records[7]['observed_monotonic_ns'],
    'held_init_snapshot_matches_hello_process_namespaces_executable': True,
    'global_kernel_logs_attributed': False, 'direct_children_retirement': actor['child_retirement'],
    'external_exact_unit_cleanup': cleanup, 'Main_before_gate_after_equal': True,
    'continuous_Main_noninterference_claimed': False,
    'outer_resource_initial_observation': actor['outer_before'],
    'final_owned_resource_gate_completed': False,
    'terminal_peak_is_not_complete_final_counter_proof': True,
    'root_cause_remains_unresolved_until_fixed_owned_logs': True,
    'retirement_cause_v1_originals_read': False,
    'whole_App_or_installed_or_pressure_or_property_reload_qualified': False,
    'review_process_effects': 0, 'Hepta_calls': 0,
}
output = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
with (OUT / 'report.json').open('xb') as stream:
    stream.write(output)
print(json.dumps({'path': str(OUT / 'report.json'), 'bytes': len(output), 'sha256': sha(output)}))
