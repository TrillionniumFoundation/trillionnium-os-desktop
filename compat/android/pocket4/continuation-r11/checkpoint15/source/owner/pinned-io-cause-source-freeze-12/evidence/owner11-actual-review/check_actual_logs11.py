"""Read the exact retained Owner11 originals; no process or remote effects."""
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266')
OWN = BASE / 'lmkd-recovery-20261105-01'
EVIDENCE = BASE / 'root-recovery-20261104-02/evidence'
OUT = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixed(path, count, digest):
    raw = path.read_bytes()
    assert len(raw) == count and sha(raw) == digest, str(path)
    return raw


runtime_path = EVIDENCE / 'owner11-normal01-runtime-read01/runtime-result.json'
runtime_raw = fixed(runtime_path, 53545, 'a04dbc0f1073c5ffb5f7fdbd549618af4b316a98688d3ecfe0622d05ef98303d')
runtime = json.loads(runtime_raw)
reader_path = EVIDENCE / 'owner11-normal01-logs01/reader-report.json'
reader_raw = fixed(reader_path, 168899, '6e5824e5ad18d3f13c39b9bf0a04d0fc9cb1639af009deba91fe72940fdd8eec')
reader = json.loads(reader_raw)
assert reader['collection_complete'] is True and reader['errors'] == []
assert len(reader['files']) == 15
members = []
for name, item in sorted(reader['files'].items()):
    raw = item['content'].encode('utf-8')
    assert len(raw) == item['bytes'] and sha(raw) == item['sha256'], name
    original = reader_path.parent / 'files' / name
    assert original.read_bytes() == raw, name
    members.append({'path': name, 'original_path': str(original), 'bytes': len(raw), 'sha256': sha(raw)})
assert reader['files']['runtime-result.json']['content'].encode() == runtime_raw
stderr_raw = reader['files']['evidence/daemon.stderr']['content'].encode()
assert len(stderr_raw) == 2017 and sha(stderr_raw) == 'ba0e15b7b1b8992f9fd77169e3f4d17b2687a0aafca9b6d28d2344cfa39dd6c6'
prefix = 'droidloom-psi-owner: retirement-cause-v1 '
lines = [line[len(prefix):] for line in stderr_raw.decode().splitlines() if line.startswith(prefix)]
assert len(lines) == 1
cause = json.loads(lines[0])
assert set(cause) == {'schema', 'nonce', 'authority_generation', 'cgroup_device', 'cgroup_inode',
                      'granted', 'faulted', 'relay_reason_utf8_hex', 'lifecycle_error_utf8_hex'}
assert cause['schema'] == 1 and cause['granted'] is False and cause['faulted'] is True
decoded = {}
for key in ('relay_reason_utf8_hex', 'lifecycle_error_utf8_hex'):
    text = cause[key]
    assert isinstance(text, str) and len(text) % 2 == 0 and text == text.lower()
    data = bytes.fromhex(text)
    assert data.hex() == text
    decoded[key.removesuffix('_utf8_hex')] = data.decode('utf-8')
assert decoded['relay_reason'] == 'open relative pinned directory: No such file or directory (os error 2)'
assert decoded['lifecycle_error'] == 'rejected: relay service retired; exact old cell requires lifecycle recovery'
actor = runtime['actor_result']
audit = actor['latest_status']['relay_lifecycle']
ready = audit['records'][3]['detail']['status']
assert cause['nonce'] == audit['nonce'] == ready['nonce']
assert cause['authority_generation'] == ready['generation']
assert {'device': cause['cgroup_device'], 'inode': cause['cgroup_inode']} == ready['cgroup']
assert runtime['success'] is False and actor['success'] is False
assert audit['first_failure']['message'] == 'owned process generation is dead or changed'
assert audit['retirement_failure']['message'] == 'rejected: lifecycle bootstrap disconnected'
assert all(runtime['exact_unit_cleanup'][key] is True
           for key in ('original_actor_dead', 'cgroup_absent', 'unit_not_found'))
assert runtime['main_before'] == runtime['main_before_gate'] == runtime['main_after']
assert actor['failure_cleanup_stop'] == actor['latest_status']
actual_path = EVIDENCE / 'producer11-retirement-compile01/result.json'
actual_raw = fixed(actual_path, 39822, 'a120890b2edeb1bf1adbe150f064987c55661420ac4021dc4d7ac9b023ad6ca6')
actual = json.loads(actual_raw)
sources = []
for relative in ('runtime/droidloom-pressure-relay/src/lib.rs', 'runtime/droidloom-pressure-relay/src/lifecycle_relay.rs'):
    path = OWN / 'pinned-io-cause-source-work-01/preimage' / relative
    raw = path.read_bytes()
    assert {'bytes': len(raw), 'sha256': sha(raw)} == actual['inputs_after'][relative]
    sources.append({'path': str(path), 'relative': relative, 'bytes': len(raw), 'sha256': sha(raw)})
lib = (OWN / 'pinned-io-cause-source-work-01/preimage/runtime/droidloom-pressure-relay/src/lib.rs').read_text()
assert lib.count('return Err(err("open relative pinned directory"))') == 1
assert 'return Err(err("openat2 beneath trusted root"))' in lib
report = {
    'schema': 1,
    'verdict': 'EXACT_OWNER11_RELAY_OPENAT_ENOENT_RETAINED_CALLSITE_STILL_UNRESOLVED',
    'original_runtime': {'path': str(runtime_path), 'bytes': len(runtime_raw), 'sha256': sha(runtime_raw)},
    'original_fixed_log_reader': {'path': str(reader_path), 'bytes': len(reader_raw), 'sha256': sha(reader_raw)},
    'all_15_originals_exact': members,
    'retirement_cause_v1': cause,
    'decoded_original_causes': decoded,
    'cause_generation_scope_matches_actual_READY_and_audit': True,
    'exact_matching_sources': sources,
    'source_label_origin': 'lib.rs::open_at syscall failure; original generic label drops relative name and base identity',
    'public_projection_lookup_uses_different_openat2_error_label': True,
    'specific_relative_name_base_or_role_observed': False,
    'missing_public_projection_proved': False,
    'blkio_cpuset_or_global_kernel_line_attribution': False,
    'process_exit_precedes_or_follows_openat_failure_proved': False,
    'original_Owner_first_failure': audit['first_failure'],
    'original_Owner_retirement_failure': audit['retirement_failure'],
    'original_Owner_retirement_completed': False,
    'original_Stop_retry_keeps_same_failure': True,
    'external_exact_unit_cleanup': runtime['exact_unit_cleanup'],
    'Main_before_gate_after_equal': True,
    'continuous_Main_noninterference_claimed': False,
    'final_owned_resource_gate_completed': False,
    'ACTIVE_observed_or_Owner_or_App_qualified': False,
    'next_candidate_scope': 'error-only typed relative name/flags/held-base identity plus validated caller role; no missing-path retry or authorization change',
    'Hepta_calls': 0,
    'process_effects': 0,
}
data = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
with (OUT / 'report.json').open('xb') as stream:
    stream.write(data)
print(json.dumps({'path': str(OUT / 'report.json'), 'bytes': len(data), 'sha256': sha(data)}))
