#!/usr/bin/env python3
"""Independent local byte/AST checks. Never executes the decoded build stage."""
import ast
import datetime
import difflib
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

WORK = Path('/workspace/scratch/94990735b266')
NATIVE = WORK / 'native-recovery-20261105-02'
OLD = NATIVE / 'paired-builder451-compile02'
NEW = NATIVE / 'paired-builder462-compile01'
TRANSPORT = NATIVE / 'paired-builder462-compile01-transport02'
PROJECTION = NATIVE / 'art-normal-projection-next03'
OUT = Path(__file__).resolve().parent
PARENT_ACTUAL = WORK / 'root-recovery-20261104-02/evidence/paired-builder451-compile02/result.json'


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': sha(raw)}


def manifest(root, expected_sha):
    raw = (root / 'SOURCE_PINS.json').read_bytes()
    require(sha(raw) == expected_sha, f'{root.name}: manifest pin')
    data = json.loads(raw)
    for name, row in data['files'].items():
        observed = pin(root / name)
        require(observed == {'bytes': row['bytes'], 'sha256': row['sha256']}, f'{root.name}: {name}')
    return {'manifest': pin(root / 'SOURCE_PINS.json'), 'verified_members': len(data['files'])}


def dump(node):
    return ast.dump(node, include_attributes=False)


def simple_assignments(raw):
    """Evaluate only literal/list TESTS assignments, never import the controller."""
    selected = {'TESTS', 'ORIGINAL_TESTS', 'PAIR_TESTS', 'ART_PROJECTION_TESTS', 'FIXED_ART_DELTA'}
    values = {}

    def value(node):
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return value(node.left) + value(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'list':
            require(len(node.args) == 1 and not node.keywords, 'unexpected list expression')
            return list(value(node.args[0]))
        return ast.literal_eval(node)

    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in selected:
                values[key] = value(node.value)
    return values


def exact_diff(old, new, path):
    expected = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                          fromfile='a/' + path, tofile='b/' + path))
    return expected


def main():
    checks = {}
    checks['frozen_manifests'] = {
        'compile462': manifest(NEW, 'b4f3e78c61ddabd06fdf0e6c13cf4ed8206330b21448b928166890ebb59cd7d5'),
        'transport02': manifest(TRANSPORT, '5f8b187e82392010248b673f4db2c8dc41a7be66eac4bb5ccd9c893a343a2aaf'),
        'projection_next03': manifest(PROJECTION, 'd77b529f4295bafa19a91196354e14e70a64c5e7b63de4643fe267211e106566'),
    }
    actual_raw = PARENT_ACTUAL.read_bytes()
    require(actual_raw == (NEW / 'compiled-parent451-result.json').read_bytes(), 'actual451 original differs')
    require(sha(actual_raw) == '8c72e771c9ed5bd440b36aa8c7c3379b31ce8acccdc2b222fadad9e64cb28096', 'actual451 hash')
    actual = json.loads(actual_raw)
    require(actual['state'] == 'PASS' and actual['focused_tests_passed'] == 22 and
            actual['actual_registered_test_count'] == 195, 'actual451 scope')
    require(actual['cleanup']['forced_cleanup'] is False and not actual['cleanup']['errors'] and
            not actual['cleanup']['remaining'], 'actual451 cleanup')
    require(actual['platform_APEX_signature_validated'] is False and
            actual['actual_enabled_ART_lifecycle_validated'] is False, 'actual451 qualification boundary')
    old_map_raw = (NEW / 'compiled-parent451-manifest.json').read_bytes()
    new_map_raw = (NEW / 'expected-builder462-manifest.json').read_bytes()
    require(sha(old_map_raw) == actual['copied_manifest']['sha256'] and
            len(old_map_raw) == actual['copied_manifest']['bytes'], 'actual451 source manifest')
    require(old_map_raw == (PROJECTION / 'references/parent451-source-manifest.json').read_bytes(),
            'projection source manifest differs')
    old_map, new_map = json.loads(old_map_raw), json.loads(new_map_raw)
    require(len(old_map) == 451 and len(new_map) == 462 and set(old_map) <= set(new_map), 'manifest membership')
    changed = sorted(name for name in old_map if old_map[name] != new_map[name])
    added = sorted(set(new_map) - set(old_map))
    unchanged = sorted(name for name in old_map if old_map[name] == new_map[name])
    require(len(changed) == 2 and len(added) == 11 and len(unchanged) == 449, '13-file source delta')
    for name in changed + added:
        raw = (NEW / 'delta' / name).read_bytes()
        require(raw == (PROJECTION / 'delta' / name).read_bytes(), 'projection delta differs: ' + name)
        require({'bytes': len(raw), 'sha256': sha(raw)} ==
                {key: new_map[name][key] for key in ['bytes', 'sha256']}, 'new manifest: ' + name)
    for name in changed:
        require(pin(PROJECTION / 'preimage' / name) ==
                {key: old_map[name][key] for key in ['bytes', 'sha256']}, 'actual preimage: ' + name)
    checks['actual451_to_462_source'] = {
        'actual_result': pin(PARENT_ACTUAL), 'parent_manifest': pin(NEW / 'compiled-parent451-manifest.json'),
        'expected_manifest': pin(NEW / 'expected-builder462-manifest.json'),
        'changed_existing': changed, 'added': added, 'unchanged_existing': len(unchanged),
        'all_13_delta_bytes_equal_projection_next03': True, 'both_preimages_equal_actual451_manifest': True,
        'engine_source_changed': False, 'APEX_validated': False, 'ART_runtime_validated': False,
        'actual451_swap_max': actual['owned_resource_gate']['swap_max_observed_only'],
    }

    old_controller = (OLD / 'compile_builder.py').read_text()
    new_controller = (NEW / 'compile_builder.py').read_text()
    require(exact_diff(old_controller, new_controller, 'compile_builder.py') ==
            (NEW / 'compiler451-to462.patch').read_text(), 'stored compiler diff differs')
    old_stage, new_stage = (OLD / 'stage.py').read_text(), (NEW / 'stage.py').read_text()
    require(exact_diff(old_stage, new_stage, 'stage.py') == (NEW / 'stage451-to462.patch').read_text(),
            'stored stage diff differs')
    old_functions = {x.name: dump(x) for x in ast.parse(old_controller).body if isinstance(x, ast.FunctionDef)}
    new_functions = {x.name: dump(x) for x in ast.parse(new_controller).body if isinstance(x, ast.FunctionDef)}
    require(set(old_functions) == set(new_functions), 'controller function set changed')
    modified = sorted(name for name in old_functions if old_functions[name] != new_functions[name])
    require(modified == ['execute'], 'unexpected controller function changes')
    old_main = next(x for x in ast.parse(old_stage).body if isinstance(x, ast.FunctionDef) and x.name == 'main')
    new_main = next(x for x in ast.parse(new_stage).body if isinstance(x, ast.FunctionDef) and x.name == 'main')
    require(dump(old_main) == dump(new_main), 'stage main changed')
    old_tests, new_tests = simple_assignments(old_controller), simple_assignments(new_controller)
    require(new_tests['TESTS'][:22] == old_tests['TESTS'] == actual['expected_test_names'], 'old 22 tests changed')
    require(len(new_tests['TESTS']) == len(set(new_tests['TESTS'])) == 24 and
            len(new_tests['ART_PROJECTION_TESTS']) == 2, 'new focused tests')
    require(new_tests['FIXED_ART_DELTA'] == sorted(changed + added), 'controller delta list')
    require([x['exact_name'] for x in actual['focused_result_gates']] == old_tests['TESTS'] and
            all(x['summary_and_independent_result_agree'] is True for x in actual['focused_result_gates']),
            'actual451 test result binding')
    checks['controller_and_test_scope'] = {
        'compiler_diff_reconstructed': True, 'stage_diff_reconstructed': True,
        'controller_functions': len(old_functions), 'modified_functions': modified,
        'unchanged_functions': len(old_functions) - 1, 'stage_main_AST_unchanged': True,
        'old_actual_registered': 195, 'old_actual_focused_executed': 22,
        'new_required_registered': 197, 'new_planned_focused': 24,
        'new_full_197_suite_claimed': False, 'old_22_order_and_names_preserved': True,
        'new_two_exact_names': new_tests['ART_PROJECTION_TESTS'],
    }

    original_request = json.loads((NEW / 'exact-request.json').read_bytes())
    request = json.loads((TRANSPORT / 'exact-request.json').read_bytes())
    original_stdin = original_request['stdin'].encode()
    require(original_stdin.startswith(new_stage.encode()), 'original stage prefix differs')
    stage_ast = ast.parse(new_stage)
    body = ast.parse(original_stdin).body
    require(len(body) == len(stage_ast.body) + 2 and
            all(dump(a) == dump(b) for a, b in zip(body[:-2], stage_ast.body)), 'stage AST prefix')
    assignment = body[-2]
    require(isinstance(assignment, ast.Assign) and len(assignment.targets) == 1 and
            isinstance(assignment.targets[0], ast.Name) and assignment.targets[0].id == 'PACKET', 'packet assignment')
    require(isinstance(assignment.value, ast.Call) and dump(assignment.value.func) ==
            dump(ast.parse('json.loads').body[0].value) and len(assignment.value.args) == 1 and
            not assignment.value.keywords, 'packet decoding expression')
    packet = json.loads(ast.literal_eval(assignment.value.args[0]))
    require(packet == json.loads((NEW / 'verified-source-packet.json').read_bytes()), 'embedded packet differs')
    require(dump(body[-1]) == dump(ast.parse('main(PACKET)').body[0]), 'stage final call differs')
    expected = ast.literal_eval(next(x for x in stage_ast.body if isinstance(x, ast.Assign) and
                                    any(isinstance(t, ast.Name) and t.id == 'EXPECTED' for t in x.targets)).value)
    require(set(packet) == set(expected) and len(packet) == 23, 'packet members')
    for name, text in packet.items():
        raw = text.encode()
        require(raw == (NEW / name).read_bytes(), 'packet content differs: ' + name)
        require({'bytes': len(raw), 'sha256': sha(raw)} == expected[name], 'packet expected pin: ' + name)
    changed_request_fields = sorted(key for key in set(original_request) | set(request)
                                    if original_request.get(key) != request.get(key))
    require(changed_request_fields == ['args', 'idempotency_key', 'stdin'], 'transport request scope')
    boundary_raw = (TRANSPORT / 'transport-boundary.py').read_bytes()
    require(original_request['args'] == ['-I', '-B', '-'] and
            request['args'] == ['-I', '-B', '-c', boundary_raw.decode()], 'transport argv binding')
    boundary_ast = ast.parse(boundary_raw)
    require(dump(boundary_ast.body[-1]) ==
            dump(ast.parse("exec(compile(raw,'<stdin>','exec'),scope,scope)").body[0]), 'boundary final exec shape')
    # Deliberately remove the sole final exec. Every fixed decoder guard remains.
    prefix = ast.Module(body=boundary_ast.body[:-1], type_ignores=[])
    prefix_code = compile(ast.fix_missing_locations(prefix), '<review-boundary-without-final-exec>', 'exec')
    wire = request['stdin'].encode()

    def decode_only(value):
        saved = sys.stdin
        scope = {'__name__': 'independent_local_transport_review'}
        try:
            sys.stdin = SimpleNamespace(buffer=io.BytesIO(value))
            exec(prefix_code, scope, scope)
            return scope['raw']
        finally:
            sys.stdin = saved

    require(decode_only(wire) == original_stdin, 'bounded decoded stdin is not exact original')
    negative_results = []
    mutations = {'one_trailing_byte': wire + b'\0', 'one_byte_truncated': wire[:-1],
                 'same_size_last_byte_changed': wire[:-1] + bytes([wire[-1] ^ 1]),
                 'uncompressed_original_as_envelope': original_stdin}
    for name, value in mutations.items():
        try:
            decode_only(value)
        except RuntimeError as error:
            require(str(error) == 'fixed compiler transport length/hash mismatch', 'unexpected reject reason')
            negative_results.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise AssertionError('malformed transport accepted: ' + name)
    checks['transport'] = {
        'original_request': pin(NEW / 'exact-request.json'), 'request': pin(TRANSPORT / 'exact-request.json'),
        'boundary': pin(TRANSPORT / 'transport-boundary.py'), 'changed_fields': changed_request_fields,
        'packet_files': 23, 'packet_content_and_expected_pins_match': True,
        'stage_AST_only_PACKET_assignment_and_main_call_added': True,
        'envelope': {'bytes': len(wire), 'sha256': sha(wire)},
        'decoded': {'bytes': len(original_stdin), 'sha256': sha(original_stdin)},
        'actual_frozen_decoder_prefix_positive': True, 'negative_controls': negative_results,
        'only_final_exec_removed_for_local_control': True, 'decoded_stage_executed': False,
        'new_CPU_RAM_timeout_nice_unchanged': True,
    }
    checks.update({'schema': 1, 'result': 'PASS_LOCAL_BYTE_AST_TRANSPORT_ONLY',
                   'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'Rust_build_or_tests_executed': False, 'Hepta_calls': 0, 'Android_or_Main_actions': 0})
    raw = (json.dumps(checks, indent=2, ensure_ascii=False) + '\n').encode()
    with (OUT / 'checks-result.json').open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'success': True, 'path': str(OUT / 'checks-result.json'),
                      'bytes': len(raw), 'sha256': sha(raw)}))


if __name__ == '__main__':
    main()
