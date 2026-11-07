"""Verify retained Owner16 bytes only; never imports production or calls a device."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct

BASE = Path('/workspace/scratch/94990735b266')
EVIDENCE = BASE / 'root-recovery-20261104-02/evidence'
OUT = Path(__file__).parent
SHA = '04ed56c29b388b381bfeb13110607a8ee25b9a4d5a903c5bb421ef002f0214cb'
PREPARED_SHA = '6a7e5f8eb4532a019506c7f0f6077d0739fe51bf31c45455a53bab700ace73d9'
checks = []


def sha(body):
    return hashlib.sha256(body).hexdigest()


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


def original(relative, count, digest):
    raw = (EVIDENCE / relative).read_bytes()
    check('exact retained ' + relative, len(raw) == count and sha(raw) == digest)
    return raw, json.loads(raw)


def terminal(relative, job, state, code, count):
    row = json.loads((EVIDENCE / relative).read_bytes())
    check('authoritative terminal ' + job, row['job_id'] == job and row['state'] == state
          and row['exit_code'] == code and row['output_complete'] is True
          and row['output_durable'] is True and row['terminal_publication_confirmed'] is True
          and row['timed_out'] is False and row['cancelled'] is False
          and row['log_errors'] == {'stderr': None, 'stdout': None}
          and row['log_truncated'] == {'stderr': False, 'stdout': False}
          and row['log_synced'] == {'stderr': True, 'stdout': True}
          and row['log_bytes'] == {'stderr': {'seen': 0, 'stored': 0}, 'stdout': {'seen': count, 'stored': count}})


def main():
    raw, result = original('owner16-runtime-read01/runtime-result.json', 382901, SHA)
    _, wire = original('owner16-runtime-read01/stdout.log', 34685,
                       '4c0d29b6e8d588c46de8ef292612dadc5d83b788bef9f473aafdca597a8013f7')
    packed = base64.b64decode(wire['gzip_base64'], validate=True)
    check('complete compressed wire', len(packed) == wire['gzip_bytes'] and sha(packed) == wire['gzip_sha256'])
    plain = gzip.decompress(packed)
    check('complete envelope', len(plain) == wire['bytes'] and sha(plain) == wire['sha256']
          and wire['collection_complete'] is True and wire['qualification'] is False)
    envelope = json.loads(plain)
    member = envelope['files']['runtime-result.json']
    check('fixed single original result', set(envelope['files']) == {'runtime-result.json'}
          and member['path'] == '/opt/p4-owner16-normal-20261105-01-state/runtime-result.json'
          and member['content'].encode() == raw and member['bytes'] == len(raw) and member['sha256'] == SHA
          and envelope['collection_complete'] is True and envelope['errors'] == []
          and envelope['mutations'] is False and envelope['qualification'] is False)
    terminal('owner16-runtime-read01/status01.tool-original.json', '1a1ade6ff62-fc05-5b7a', 'succeeded', 0, 34685)
    terminal('owner16-normal-runtime01/status01.tool-original.json', '1a1ade28666-fc05-5b5b', 'failed', 1, 509)
    _, summary = original('owner16-normal-runtime01/stdout.log', 509,
                          '97077f306a0bb8bb9b3145831df6618d240e33a049d982b6d245e7ddfc8fe2a8')
    check('runtime summary binds failed original', summary['result_path'] == member['path']
          and summary['bytes'] == len(raw) and summary['sha256'] == SHA and summary['success'] is False)
    _, prepared = original('owner16-prepared-read01/prepared.json', 55140, PREPARED_SHA)
    plan = json.loads((BASE / 'android-owner16-normal01-freeze-01/plan.json').read_bytes())
    actor = result['actor_result']
    actor_raw = (json.dumps(actor, sort_keys=True, indent=2) + '\n').encode()
    check('entire actor writer serialization', sha(actor_raw) == result['actor_result_sha256'])
    check('attempt and actual prepared binding', result['attempt_nonce'] == actor['attempt_nonce'] == plan['attempt_nonce']
          and result['prepared_sha256'] == actor['prepared_sha256'] == PREPARED_SHA
          and result['gate_sha256'] == actor['gate_sha256'])
    check('failure never promoted to product success', result['success'] is False and actor['success'] is False
          and all(result[k] is False for k in ['production_ready', 'installed_owner_qualified',
                      'pressure_effect_qualified', 'rc_property_reload_qualified', 'app_qualified']))
    check('all original Main maps and pids max unchanged', result['main_before'] == result['main_before_gate']
          == result['main_after'] == prepared['main_final']
          and result['main_after']['resources']['pids.max'] == '12288'
          and result['main_after']['held_cgroup_identity'] == [30, 26651611])
    check('same actual unit and actor invocation', actor['invocation'] == result['first_unit']['InvocationID']
          == result['terminal']['InvocationID'] == result['exact_unit_cleanup']['invocation']
          and result['terminal']['ExecMainPID'] == str(actor['actor_pid'])
          and result['terminal']['ExecMainStatus'] == '1' and result['terminal']['Result'] == 'exit-code')
    check('outer resource identity and finite limits preserved', actor['outer_before']['identity']
          == actor['outer_final']['sample']['identity'] == result['first_cgroup']['identity']
          and all(actor['outer_before']['values'][k] == actor['outer_final']['sample']['values'][k]
                  for k in ['cpu.max', 'memory.high', 'memory.max', 'memory.swap.max', 'pids.max']))
    final_values = actor['outer_final']['sample']['values']
    check('no reported outer OOM or swap', final_values['memory.events'] == actor['outer_before']['values']['memory.events']
          and all(int(line.split()[1]) == 0 for line in final_values['memory.events'].splitlines())
          and final_values['memory.swap.current'] == final_values['memory.swap.max'] == final_values['memory.swap.peak'] == '0')
    check('exact four children reaped without forced kill', len(actor['child_retirement']) == 4
          and {r['role'] for r in actor['child_retirement']} == {'daemon', 'presenter', 'sway', 'bus'}
          and all(r['reaped'] is True and r['forced_kill'] is False for r in actor['child_retirement']))
    cleanup = result['exact_unit_cleanup']
    check('outer exact cleanup', cleanup['unit'] == plan['unit'] and cleanup['unit_not_found'] is True
          and cleanup['cgroup_absent'] is True and cleanup['original_actor_dead'] is True)
    latest = actor['latest_status']['relay_lifecycle']
    audit = actor['failure_cleanup_stop']['relay_lifecycle']
    check('original audit first error and complete append-only prefix', latest['first_failure'] == audit['first_failure']
          and audit['first_failure']['origin'] == 'runtime'
          and audit['first_failure']['message'] == 'real broker retired; complete old cell recovery is required'
          and latest['records'] == audit['records'][:len(latest['records'])]
          and audit['retained_after_exit'] is True and audit['recording_incomplete'] is False
          and audit['recording_error'] is None and audit['retirement_failure'] is None and audit['cleanup_failure'] is None)
    records = audit['records']
    events = [r['detail']['event'] for r in records]
    check('exact ordered lifecycle, with no ACTIVE', events == ['prepared', 'owner_attached', 'init_hello',
          'broker_ready', 'init_project_sent', 'init_projected_accepted', 'init_commit_sent', 'init_done_accepted',
          'retiring', 'broker_retired', 'processes_dead', 'domain_empty', 'retired', 'resources_removed', 'claim_released']
          and [r['sequence'] for r in records] == list(range(1, 16))
          and all(a['observed_monotonic_ns'] <= b['observed_monotonic_ns'] for a, b in zip(records, records[1:])))
    check('canonical CellSpec and generation binding', audit['canonical_spec_sha256'] == plan['canonical_spec_sha256']
          and audit['host_uid'] == plan['spec']['host_uid'] and audit['nonce'] == latest['nonce']
          == actor['init_identity_clock_observation']['generation_nonce'])
    producer = audit['producer']
    check('audit producer externally held identity binding', all(producer[k] == actor['producer'][k]
          for k in ['process', 'namespaces', 'executable', 'executable_sha256'])
          and producer['executable_sha256'] == prepared['copied_artifacts']['droidloomd']['sha256'])
    hello = records[2]['detail']['init']
    held_init = actor['init_identity_clock_observation']['snapshot']
    check('held init and actual binary identity', all(hello[k] == held_init[k]
          for k in ['process', 'namespaces', 'executable', 'executable_sha256'])
          and hello['executable_sha256'] == 'd6905d43a0dad5219b61c9759ab32352262558e1109762eec1a24be153181c73')
    frames = [hello['hello_wire_hex']] + [records[i]['detail']['wire_hex'] for i in range(4, 8)]
    frame_bytes = [bytes.fromhex(x) for x in frames]
    check('exact ABI3 HELLO PROJECT PROJECTED COMMIT DONE framing', all(len(b) == 128 and b[:8] == b'P4IBV3!!'
          and struct.unpack_from('<I', b, 8)[0] == 3 and b[16:48].hex() == audit['nonce'] for b in frame_bytes)
          and [struct.unpack_from('<I', b, 12)[0] for b in frame_bytes] == [1, 2, 3, 4, 5])
    ready = records[3]['detail']['status']
    retired = records[9]['detail']['receipt']
    check('broker was READY but never granted or ACTIVE', ready['state'] == 1 and ready['granted'] is False
          and ready['faulted'] is False and retired['faulted'] is True and retired['incomplete'] is True
          and retired['granted'] is False and retired['observations'] == 0 and retired['registrations'] == []
          and retired['packets_queued'] == retired['event_records'] == 0
          and retired['authority_generation'] == ready['generation'] and retired['cgroup'] == ready['cgroup'])
    check('six terminal retirement events complete', events[9:] == ['broker_retired', 'processes_dead',
          'domain_empty', 'retired', 'resources_removed', 'claim_released'])
    exit_record = audit['namespace_owner_exit']
    check('owned namespace child SIGHUP wait status preserved', exit_record['process'] == records[1]['detail']['process']
          and exit_record['raw_status'] == 1 and exit_record['signal'] == 1 and exit_record['core_dumped'] is False
          and exit_record['explicit_stop_requested_before_observation'] is False
          and exit_record['worker_retirement_started_before_observation'] is True)
    log = audit['init_log']
    prefix = bytes.fromhex(log['captured_hex'])
    check('full bounded prefix and same-generation logger', len(prefix) == log['captured_bytes'] == 161943
          and sha(prefix) == log['captured_sha256'] == '5390a06ec64a6af36fef0432a629b79fa3cb9898ab47ff04ccfc6a260a3c646d'
          and log['nonce'] == audit['nonce'] and log['capacity_bytes'] == 262144 and log['capacity_reached'] is False
          and log['observed_writer_offset'] == len(prefix) and log['first_error'] is None and log['secondary_errors'] == []
          and log['held_fds_closed'] is True and log['retirement_proven_before_capture'] is True
          and log['marker_verified_after_held_init_hello'] is True)
    lines = prefix.decode('utf-8').splitlines()
    check('both actual logger markers and exact definition object', lines[:3] == [
          '<6>droidloom-init-log: P4_INIT_LOG_V1 nonce=' + audit['nonce'],
          '<6>droidloom-init-log: P4_INIT_LOG_CACHED_V1 nonce=' + audit['nonce'],
          '<6>droidloom-init-log: P4_INIT_LOG_DEFINITION_V1 object=/system/lib64/libbase.so symbol=_ZN7android4base12KernelLoggerENS0_5LogIdENS0_11LogSeverityEPKcS4_jS4_'])
    check('capture attribution limits not hidden', log['exact_writer_per_line_proven'] is False
          and log['stream_completeness_claimed'] is False)
    denied = [i for i, line in enumerate(lines, 1) if "cannot execv('/droidloom/lmkd-bootstrap/lmkd')" in line]
    aborts = [(i, int(re.search(r'pid ([0-9]+)', line)[1])) for i, line in enumerate(lines, 1)
              if "Service 'hwservicemanager'" in line and 'received SIGABRT' in line]
    check('four exact LMKD exec denials', denied == [297, 679, 1250, 1691]
          and all(lines[i - 1].endswith('Permission denied') for i in denied))
    check('actual repeated critical service failure and init reboot', aborts == [(371, 563), (753, 645),
          (1107, 706), (1511, 780), (1933, 846)]
          and lines[1935] == "<2>init: critical process 'hwservicemanager' exited 4 times before boot completed"
          and lines[1936] == '<3>init: InitFatalReboot: signal 6'
          and lines[-1] == '<6>init: Reboot ending, jumping to kernel')
    check('actual restrictive service mask retained', '--property=UMask=0077' in result['launch_command'])
    report = {'schema': 1, 'scope': 'LOCAL_COMPLETE_RETAINED_OWNER16_RUNTIME_REVIEW',
              'checks_passed': checks, 'count': len(checks), 'runtime_bytes': len(raw), 'runtime_sha256': SHA,
              'runtime_job': '1a1ade28666-fc05-5b5b', 'runtime_failed_preserved': True,
              'actor_result_sha256': result['actor_result_sha256'], 'prepared_sha256': PREPARED_SHA,
              'original_Main_all_three_maps_equal': True, 'original_Main_pids_max': '12288',
              'owned_children_reaped': actor['child_retirement'], 'exact_unit_cleanup': cleanup,
              'memory_peak_bytes': int(final_values['memory.peak']), 'memory_events': final_values['memory.events'],
              'swap_peak_bytes': 0, 'generation_nonce': audit['nonce'], 'events': events,
              'broker_active_observed': False, 'broker_ready_observed': True, 'broker_retired_receipt': retired,
              'six_post_retiring_events_complete': True, 'namespace_owner_exit': exit_record,
              'actual_kernel_logger_two_markers_passed': True, 'actual_logger_definition_object': '/system/lib64/libbase.so',
              'captured_prefix_bytes': len(prefix), 'captured_prefix_sha256': sha(prefix),
              'LMKD_exec_EACCES_lines': denied, 'hwservicemanager_SIGABRT_lines_and_guest_pids': aborts,
              'critical_init_fatal_reboot_observed': True,
              'LMKD_exec_permission_cause_complete': False, 'hwservicemanager_abort_message_observed': False,
              'source_umask_directory_gap': 'Actual unit mask0077 and pinned mkdir0755 without fchmod admit0700. This source gap is being repaired only for owned guest tmpfs directories. RC also requests DAC_OVERRIDE; no claim that mode alone proves all exec EACCES causes.',
              'causal_boundary': 'This run supports an init fatal reboot preceding the namespace SIGHUP status; no claim of external sender or the same historical Owner15 cause.',
              'per_line_writer_or_complete_stream_attribution': False, 'production_ready': False,
              'full_Owner_NORMAL_qualification': False, 'App_qualification': False,
              'source_or_runtime_mutation_by_review': False, 'raw_prefix_copied_into_review_package': False}
    body = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    (OUT / 'report.json').open('xb').write(body)
    print(json.dumps({'checks': len(checks), 'report_bytes': len(body), 'report_sha256': sha(body),
                      'runtime_sha256': SHA, 'runtime_failed_preserved': True}))


if __name__ == '__main__':
    main()
