"""Finite local parser controls; never import the runtime main or execute aapt."""
import ast
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    raw = (HERE / 'observe_manifest_as_owner.py').read_bytes()
    tree = ast.parse(raw)
    names = {'need', 'badging_manifest', 'quoted_attributes', 'permissions_dump',
             'aapt_diagnostics', 'normal_child_retired'}
    selected = [item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name in names]
    assert len(selected) == len(names)
    scope = {'re': re, 'json': json}
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<local-pure-parser-controls>', 'exec'), scope)
    reference = json.loads((HERE / 'historical-reference.json').read_bytes())
    header = reference['manifest']['package_line_raw'] + "\nsdkVersion:'23'\ntargetSdkVersion:'33'\nnative-code: 'arm64-v8a' 'armeabi-v7a'\n"
    parsed = scope['badging_manifest'](header.encode())
    assert parsed['package'] == 'com.szzc' and parsed['version_name'] == '9.6.1' and parsed['long_version_code'] == 327
    assert parsed['min_sdk'] == '23' and parsed['target_sdk'] == '33'
    checks = ['unchanged_faff_parser_extracts_explicit_historical_fixture_fields']
    rows = ['package: com.szzc']
    for item in reference['permission_tag_names']:
        rows.append(item['tag'] + ": name='" + item['name'] + "'")
    permissions = scope['permissions_dump'](('\n'.join(rows) + '\n').encode())
    assert permissions['all_names_decoded'] is True and permissions['unparsed_lines'] == []
    assert [{'tag': item['tag'], 'name': item['name']} for item in permissions['entries']] == reference['permission_tag_names']
    assert sum(item['name'] == 'android.permission.FOREGROUND_SERVICE' for item in permissions['entries']) == 3
    checks.append('duplicate_permission_rows_remain_in_order_and_are_not_deduplicated')
    value = scope['permissions_dump'](b"package: com.szzc\nuses-permission: name='android.permission.READ_EXTERNAL_STORAGE' maxSdkVersion='32'\npermission: com.szzc.permission.TEST\n")
    assert value['entries'][0]['attributes']['maxSdkVersion'] == '32'
    assert value['entries'][1]['name'] == 'com.szzc.permission.TEST'
    checks.append('raw_permission_attributes_and_bare_custom_names_remain_available')
    assert scope['aapt_diagnostics']('badging', header.encode(), b'warning retained\n')['healthy_output_shape'] is False
    assert scope['aapt_diagnostics']('badging', b'W/ResourceType(123): malformed resource\n' + header.encode(), b'')['healthy_output_shape'] is False
    checks.append('rc0_cannot_override_stderr_or_stdout_diagnostic_failure')
    assert scope['aapt_diagnostics']('badging', header.encode() + b'unclassified new output\n', b'')['healthy_output_shape'] is False
    value = scope['permissions_dump'](('\n'.join(rows) + '\nERROR: unexpected text\n').encode())
    assert len(value['unparsed_lines']) == 1
    checks.append('unrecognized_output_is_preserved_and_cannot_claim_complete_parse')
    retired = {'returncode': 0, 'joined': True, 'pipes_closed': True, 'output_capture_complete': True,
               'timed_out': False, 'own_group_kill_requested': False}
    assert scope['normal_child_retired'](retired) is True
    assert scope['normal_child_retired']({**retired, 'own_group_kill_requested': True}) is False
    assert scope['normal_child_retired']({**retired, 'output_truncated': True}) is False
    checks.append('killed_or_truncated_child_observation_cannot_pass_retirement_gate')
    request = json.loads((HERE / 'process-request.json').read_bytes())
    assert request['args'] == ['-I', '-B', '-c', raw.decode(), '--observe-candidate-manifest-as-existing-owner-once']
    assert request['executable'] == '/usr/bin/python3' and request['timeout_seconds'] == 210
    assert request['memory_max_bytes'] == 536870912 and request['cpu_quota_percent'] == 100
    checks.append('exact_request_embeds_the_complete_reviewed_source_and_original_resource_profile')
    result = {'schema': 'pocket4-s39-local-parser-controls-v1', 'state': 'LOCAL_CONTROLS_PASS',
        'source_bytes': len(raw), 'source_sha256': hashlib.sha256(raw).hexdigest(),
        'checks': checks, 'check_count': len(checks), 'fixtures_are_local_synthetic_parser_inputs': True,
        'candidate_manifest_observed': False, 'aapt_executed': False, 'SSH_calls': 0,
        'Main_actions': 0, 'production_ready': False, 'cleanup_eligible': False}
    encoded = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    with (HERE / 'local-controls.json').open('xb') as stream:
        stream.write(encoded)
    print(json.dumps({'checks': len(checks), 'bytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest()}))


if __name__ == '__main__':
    main()
