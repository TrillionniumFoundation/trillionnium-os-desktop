"""Finite local parser/data controls. This file never runs the host qualifier."""
import ast
import copy
import hashlib
import json
import pathlib
import re

P = pathlib.Path
BASE = P(__file__).resolve().parents[1]
DEST = BASE / 'builder470-current-qualification-r1/source-r1'
SOURCE = DEST / 'qualify_current470.py'


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(BASE)), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    raw = SOURCE.read_bytes()
    tree = ast.parse(raw)
    compile(raw, str(SOURCE), 'exec')
    scope = {'hashlib': hashlib, 're': re, 'P': P}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                scope[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    scope['BUILD_RESULT'] = P(scope['AUTHORITIES']['current470-result']['path'])
    names = ['require', 'qualify_builder470_receipt', 'qualification_complete',
             'verify_source_ancestry', 'collect_pins', 'current_artifact']
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(functions) == len(names)
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<selected-pure-controls>', 'exec'), scope)
    checks = []

    current_path = BASE / 'builder470-hostprep-r2/root-readback-01/result.original.json'
    current = json.loads(current_path.read_bytes())
    scope['qualify_builder470_receipt'](current)
    checks.append('actual_original_current470_receipt_passes_unchanged_pure_validator')
    old491 = json.loads((BASE / 'builder470-current-qualification-r1/reference/legacy491-source-manifest.original.json').read_bytes())
    old493 = json.loads((BASE / 'source-r4/expected-builder469-manifest.json').read_bytes())
    now498 = json.loads((BASE / 'source-r4/expected-builder470-manifest.json').read_bytes())
    ancestry = scope['verify_source_ancestry'](old491, old493, now498)
    checks.append('exact_original491_493_498_manifests_match_finite_ancestry')

    changed = copy.deepcopy(current)
    changed['independent_result_gates'].pop()
    try:
        scope['qualify_builder470_receipt'](changed)
    except RuntimeError:
        checks.append('missing_original_independent_test_gate_is_rejected')
    else:
        raise AssertionError('missing original gate accepted')
    assert scope['qualification_complete']({}) is False
    checks.append('unknown_empty_current_qualification_cannot_pass')

    # This is only a synthetic parser fixture, never persisted as an execution result.
    fixture = {'errors': [], 'cleanup': {'complete': True, 'children': [], 'errors': []},
        'gates': dict.fromkeys(scope['EXPECTED_GATES'], True),
        'commands': [{'label': label, 'returncode': 0, 'timed_out': False}
                     for label in scope['EXPECTED_FRESH_LABELS']], 'command_count': 34, 'tests_passed': 28,
        'fresh_updater_independent_result_gates': [{'exact_name': name} for name in scope['TESTS']],
        'fresh_source_resume_independent_result_gates': [{'exact_name': name} for name in scope['SOURCE_TESTS']]}
    assert scope['qualification_complete'](fixture) is True
    changed = copy.deepcopy(fixture)
    changed['cleanup']['children'] = [{'pid': 12345, 'reaped': True, 'signal': 'SIGKILL'}]
    assert scope['qualification_complete'](changed) is False
    checks.append('complete_cleanup_with_killed_or_reaped_residual_child_cannot_pass')
    changed = copy.deepcopy(fixture)
    changed['fresh_updater_independent_result_gates'] = []
    changed['tests_passed'] = 9
    assert scope['qualification_complete'](changed) is False
    checks.append('nine_resume_tests_alone_cannot_qualify_current_builder')
    changed = copy.deepcopy(fixture)
    changed['commands'].pop()
    assert scope['qualification_complete'](changed) is False
    checks.append('missing_fresh_command_cannot_pass')
    changed_artifact = copy.deepcopy(current['builder'])
    changed_artifact['identity'][1] += 1
    scope['hash_pin'] = lambda unused: changed_artifact
    scope['owner_identity'] = lambda unused: {'unexpected': 'must not be reached'}
    try:
        scope['current_artifact'](current['builder'], P(current['builder']['path']))
    except RuntimeError:
        checks.append('equal_bytes_at_changed_inode_cannot_replace_current_artifact')
    else:
        raise AssertionError('changed artifact inode accepted')

    parent = (BASE / 'builder470-hostprep-r2/compile_builder470.py').read_text()
    parent_functions = {node.name: ast.get_source_segment(parent, node) for node in ast.parse(parent).body
                        if isinstance(node, ast.FunctionDef)}
    candidate_functions = {node.name: ast.get_source_segment(raw.decode(), node) for node in tree.body
                           if isinstance(node, ast.FunctionDef)}
    assert len(parent_functions) == 26
    assert all(candidate_functions[name] == source for name, source in parent_functions.items())
    checks.append('all26_previously_qualified_helper_bodies_are_byte_identical')

    stage_request = json.loads((DEST / 'exact-stage-request.json').read_bytes())
    packet_raw = (DEST / 'exact-stage-stdin.json').read_bytes()
    assert stage_request['stdin'].encode() == packet_raw and len(packet_raw) <= 1048576
    packet = json.loads(packet_raw)
    assert packet['files'] == {'qualify_current470.py': raw.decode()}
    assert packet['stage'].encode() == (DEST / 'stage_current470_qualification.py').read_bytes()
    stage_scope = {}
    for node in ast.parse(packet['stage']).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                stage_scope[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    assert stage_scope['SOURCE_BYTES'] == len(raw) and stage_scope['SOURCE_SHA'] == hashlib.sha256(raw).hexdigest()
    request = json.loads((DEST / 'exact-qualification-request.json').read_bytes())
    assert request['args'][-3:] == ['--qualify-once', '--source-sha256', hashlib.sha256(raw).hexdigest()]
    assert request['cpu_quota_percent'] == 100 and request['memory_max_bytes'] == 1073741824
    assert request['timeout_seconds'] == 1500 and request['nice'] == 10
    for value in [packet['stage'], stage_request['args'][3], request['args'][3]]:
        compile(value, '<closed-candidate-source>', 'exec')
    checks.append('closed_stage_and_qualification_transport_pins_and_bounds_match')
    report = {'schema': 'pocket4-current470-candidate-local-controls-v1',
        'state': 'LOCAL_PARSER_AND_SOURCE_CONTROLS_PASS', 'checks': checks, 'check_count': len(checks),
        'current_qualification_candidate': pin(SOURCE), 'actual_current_receipt_used_only_as_parser_input': pin(current_path),
        'source_ancestry': ancestry, 'synthetic_fixtures_used_only_for_local_gate_rejection': True,
        'host_qualification_executed': False, 'Rust_commands_executed': 0, 'SSH_calls': 0,
        'Main_actions': 0, 'Soong_invoked': False, 'new_authorization_contract_connected': False,
        'production_ready': False, 'cleanup_eligible': False}
    target = DEST / 'local-controls.json'
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'checks': len(checks), 'result': pin(target), 'actual_host_qualification': False}, indent=2))


if __name__ == '__main__':
    main()
