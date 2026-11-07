"""Validate captured actual bytes; this file cannot invoke a remote operation."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
JOB = '1a1b35f9774-fc05-827f'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'bytes': len(raw), 'sha256': digest(raw)}


def save_once(name, raw):
    path = HERE / name
    if path.exists():
        assert path.read_bytes() == raw, name
    else:
        with path.open('xb') as stream:
            stream.write(raw)


raw = (HERE / 'stdout.original.json').read_bytes()
terminal_raw = (HERE / 'terminal.original.json').read_bytes()
assert pin(raw) == {'bytes': 24661, 'sha256': '7e4c812377d3562ad9fd236899ba151c2bb11772672c3f04956e02a469d487ed'}
assert pin(terminal_raw) == {'bytes': 733, 'sha256': 'e58b70b49e0a9e61be8d7dcfe72517652cedc8e890f135f618c9558b3c70b6f0'}
terminal = json.loads(terminal_raw)
assert terminal['job_id'] == JOB and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
for key in ('audit_recorded', 'output_complete', 'output_durable', 'terminal_publication_confirmed'):
    assert terminal[key] is True, key
for key in ('automatic_retry', 'cancelled', 'timed_out'):
    assert terminal[key] is False, key
for stream, size in (('stdout', len(raw)), ('stderr', 0)):
    assert terminal['log_bytes'][stream] == {'seen': size, 'stored': size}
    assert terminal['log_errors'][stream] is None
    assert terminal['log_synced'][stream] is True
    assert terminal['log_truncated'][stream] is False
parts = []
for offset in (0, 16384):
    page = json.loads((HERE / ('read-%05d.original.json' % offset)).read_bytes())
    assert page['job_id'] == JOB and page['audit_recorded'] is True
    item = page['stdout']
    assert item['offset'] == offset and item['size'] == len(raw)
    part = bytes.fromhex(item['bytes_hex'])
    assert item['next_offset'] == offset + len(part)
    assert item['eof'] is (item['next_offset'] == len(raw))
    assert page['stderr']['size'] == 0 and page['stderr']['eof'] is True
    assert bytes.fromhex(page['stderr']['bytes_hex']) == b''
    parts.append(part)
assert b''.join(parts) == raw
outer = json.loads(raw)
assert outer['ok'] is True and outer['errors'] == [] and outer['helper_uid'] == 10167
assert outer['schema'] == 'pocket4-fixed-r2-readonly-inspect-result-v1'
assert outer['step'] == 'r2-readonly-inspect-01' and outer['task'] == 878
life = outer['child_lifecycle']
assert life['child_pid'] == 2688910 and life['returncode'] == 0 and life['errors'] == []
assert life['owned_child_sigkill_count'] == 0 and life['timeout'] is False
for key in ('parent_descriptors_restored', 'pidfd_acquired', 'pidfd_closed', 'pidfd_exit_observed'):
    assert life[key] is True, key
child_raw = outer['child_stdout_original'].encode('utf-8')
assert pin(child_raw) == {'bytes': outer['child_stdout_bytes'], 'sha256': outer['child_stdout_sha256']}
assert child_raw == (HERE / 'child.stdout.original.json').read_bytes()
assert outer['child_stderr_bytes'] == 0 and outer['child_stderr_original'] == ''
assert outer['child_stderr_sha256'] == digest(b'')
child = json.loads(child_raw)
assert child['ok'] is True and child['errors'] == [] and child['original_returncode'] == 0
assert child['original_entry_invoked'] is True and child['original_namespace_authority_released'] is True
assert child['normal_process_exit_required_for_lock_and_library'] is True
assert child['manual_library_close'] is False and child['unknown_descriptors_closed'] == 0
assert child['whole_scope_before'] == child['whole_scope_after']
guard = child['whole_scope_before']
assert len(guard['current_apps']['packages']) == 49
assert guard['current_apps']['current_apk_paths_and_file_identities_match'] is True
assert guard['current_apps']['app_scope_sha256'] == '7187bc544cf6812ad47efdf141cd111897a1124b9532f84b7cf599b0c0fee1e3'
assert outer['all49_guard_before_after_equal'] is True
assert outer['current_explicit_scope'] == child['current_explicit_scope'] == guard['scope_pin']
assert child['declared_mutation'] is False and child['original_sources_modified'] is False
adapter_raw = child['original_stdout'].encode('utf-8')
assert pin(adapter_raw) == {'bytes': child['original_stdout_bytes'], 'sha256': child['original_stdout_sha256']}
assert adapter_raw == (HERE / 'adapter.stdout.original.json').read_bytes()
adapter = json.loads(adapter_raw)
assert adapter['ok'] is True and adapter['error'] is None and adapter['secondary_errors'] == []
assert adapter['installed_before'] == adapter['installed_after'] == outer['completed_install']['installed_helper']
assert adapter['installed_before']['uid'] == 10167
assert adapter['installed_before']['apk_sha256'] == '968c23aac929130a76dfa49d796fbe5264c073f805b7f048b68737e427d96372'
assert adapter['foreground_before'] == adapter['foreground_after']
assert adapter['foreground_before']['package'] == 'com.lianjia.beike'
assert adapter['foreground_before']['uid'] == 10143
assert adapter['owned_task']['task'] == 878 and adapter['owned_task']['prelaunch_absent'] is True
assert adapter['inspection_wire_sha256'] == 'c44cfe0deb683261c272029d938b2ae13d41bf94b09243130a08b3ff70785223'
for key in ('after_state_attempted', 'after_state_completed', 'restoration_qualified', 'post_state_matches_before'):
    assert adapter[key] is True, key
assert adapter['accessibility_restoration']['accessibility_mode_restoration_verified'] is True
assert adapter['accessibility_restoration']['state_before'] == adapter['accessibility_restoration']['state_after']
assert adapter['post_termination_state']['ui_automation_connected'] is False
assert adapter['post_termination_state']['helper_uid'] == 10167
for item in (outer, child):
    for key in ('original_action_attempted', 'original_action_outcome_unknown', 'outcome_unknown',
                'original_UNKNOWN_rewritten', 'production_ready', 'automatic_retry', 'reconciliation_published'):
        assert item[key] is False, key
    for key in ('installs', 'permission_changes', 'native_launches', 'cleanup_or_focus_actions'):
        assert item[key] == 0, key
    assert item['original_old_close_outcome'] == 'unknown_retained'
for key in ('action_attempted', 'outcome_unknown', 'business_success_verified', 'whole_app_production_ready'):
    assert adapter[key] is False, key
assert outer['old_products_deleted'] is False
joint = dict(outer)
del joint['joint_artifact']
joint_raw = json.dumps(joint, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'
assert pin(joint_raw) == {key: outer['joint_artifact'][key] for key in ('bytes', 'sha256')}
save_once('joint.reconstructed.exact.json', joint_raw)
result = {
    'schema': 'pocket4-root-actual-r2-readonly-inspect-validation-v1',
    'state': 'PASS_READONLY_INSPECT_ACTUAL49_IDENTITY_RESTORATION_OWNED_EXIT_AND_DURABLE_TERMINAL',
    'job_id': JOB, 'stdout': pin(raw), 'terminal': pin(terminal_raw),
    'child_stdout': pin(child_raw), 'adapter_stdout': pin(adapter_raw),
    'joint_artifact': outer['joint_artifact'],
    'joint_reconstruction_matches_actual_published_pin': True,
    'original_step_result': outer['original_result'],
    'owned_child': life, 'helper_UID': 10167, 'task': 878,
    'installed_helper': adapter['installed_before'],
    'current_explicit_scope': outer['current_explicit_scope'],
    'all49_guard_before_after_equal': True,
    'foreground_before_after_equal': True,
    'foreground': adapter['foreground_after'],
    'inspection_wire_sha256': adapter['inspection_wire_sha256'],
    'independent_no_automation_after_state_verified': True,
    'accessibility_mode_restoration_verified': True,
    'UI_actions': 0, 'installs': 0, 'permission_grants': 0, 'deleted_bytes': 0,
    'business_success_verified': False, 'production_ready': False,
    'old_failed_UNKNOWN_preserved': True,
    'full_global_PM_or_Launcher_inventory_repeated': False,
    'private_UI_tree_read_back_locally': False,
    'new_action_requires_original_Flow_fresh_checks': True,
}
encoded = (json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2) + '\n').encode('ascii')
save_once('root-validation.actual.json', encoded)
print(json.dumps({'state': result['state'], 'root_validation': pin(encoded), 'joint': pin(joint_raw)}, sort_keys=True))
