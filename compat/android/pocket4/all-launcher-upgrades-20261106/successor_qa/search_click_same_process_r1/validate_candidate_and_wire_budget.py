#!/usr/bin/env python3
"""Offline source inheritance and wire-size review; no Android or process calls."""
import ast
import base64
import copy
import difflib
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
BASE = PROJECT / 'successor_qa/reconstructed/source-generation-r2/helper'
FINAL = HERE / 'candidate-r2/helper'
OLD = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'
NEW = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2'
BUNDLE = PROJECT.parent / 'p4_private_ui/beike-search-click-failure-bundle-r1/bundle.private.original.json'
BUNDLE_SHA = '85b3b9801685a427a484cc81b80de64e66df49ceb477efa99901ac2dfb01cee4'
EXPECTED_CHANGED = {
    'build_candidate.py': ['source_contract', 'build_once'],
    'check_current_baseline.py': [], 'check_idle_contract.py': [],
    'install_owned_helper.py': ['execute'],
    'qa_adapter.py': ['validate_plan', 'qualified_build', 'Session.__init__', 'Session.instrument', 'Session.sequence', 'execute', 'main'],
    'qa_contract.py': ['validate_request', 'parse_completed', 'inspection_idle_observation', 'failure_diagnostic', 'tree_observations'],
    'run_case.py': ['validate_case'],
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def save_new(name, value):
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    path = HERE / 'candidate-r2' / name
    with path.open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    assert path.read_bytes() == raw
    return pin(path)


def functions(raw):
    result = {}
    def take(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result[prefix + node.name] = ast.dump(node, include_attributes=False)
            elif isinstance(node, ast.ClassDef):
                take(node.body, prefix + node.name + '.')
    take(ast.parse(raw).body)
    return result


def main():
    old_manifest_raw = (BASE / 'SOURCE_PINS.json').read_bytes()
    final_raw = (FINAL / 'SOURCE_PINS.json').read_bytes()
    assert (len(old_manifest_raw), sha(old_manifest_raw)) == (2431, 'dfb9b6a483f1069847433152b9b2e8b0f1b2cdd571a1dbde3068fc9393ad62c4')
    assert (len(final_raw), sha(final_raw)) == (3259, '0bd7c10043f46063fdbf46e19a48e40430c02f3373d697ad7a44af8ad64b8489')
    old_manifest, final_manifest = json.loads(old_manifest_raw), json.loads(final_raw)
    bodies = []
    for root, manifest in ((BASE, old_manifest), (FINAL, final_manifest)):
        body = {}
        for name, expected in manifest['files'].items():
            raw = (root / name).read_bytes()
            assert expected == {'bytes': len(raw), 'sha256': sha(raw)}
            body[name] = raw.decode('utf-8')
        bodies.append(body)
    old, new = bodies
    assert len(old) == 13 and len(new) == 15
    normalized = {name.replace(NEW.replace('.', '/'), OLD.replace('.', '/')):
                  body.replace(NEW, OLD).replace(NEW.replace('.', '/'), OLD.replace('.', '/'))
                  for name, body in new.items()}
    comparison = {}
    for name, expected in EXPECTED_CHANGED.items():
        first, last = functions(old[name]), functions(normalized[name])
        changed = [name for name in first if name in last and first[name] != last[name]]
        assert changed == expected and not set(first) - set(last)
        added = sorted(set(last) - set(first))
        assert added == (['assess_search_click', 'fixed_search_node', 'search_failure_diagnostic'] if name == 'qa_contract.py' else [])
        comparison[name] = {'unchanged_functions': [name for name in first if first[name] == last[name]],
                            'changed_functions': changed, 'new_functions': added, 'removed_functions': []}
    java_name = 'src/' + OLD.replace('.', '/') + '/ActionRunner.java'
    java_old, java_new = old[java_name], normalized[java_name]
    assert java_old[java_old.index('    void act(JSONObject request, JSONObject result)'): ] == java_new[java_new.index('    void act(JSONObject request, JSONObject result)'): ]
    fragment = (HERE / 'fragments/search_click.java').read_text()
    reversed_java = java_new.replace(fragment + '\n', '', 1)
    reversed_java = reversed_java.replace('Arrays.asList("state", "inspect", "search_click").contains(op)',
                                         'Arrays.asList("state", "inspect", "click", "set_text").contains(op)', 1)
    reversed_java = reversed_java.replace('            else if (op.equals("search_click")) keys(request, "protocol", "nonce", "op", "scope", "inspection_nonce", "inspection_sha256", "node_path", "node_sha256");\n', '', 1)
    reversed_java = reversed_java.replace('                } else if (op.equals("search_click")) searchClick(request, result);\n                else if (op.equals("reveal_controls")) revealControls(request, result);',
                                         '                } else if (op.equals("reveal_controls")) revealControls(request, result);', 1)
    assert reversed_java == java_old
    namespace_only = [name for name in old if old[name] == normalized[name]]
    for name in ('PlayerButtonTransaction.java', 'InspectionIdleGate.java', 'TouchTransaction.java'):
        assert 'src/' + OLD.replace('.', '/') + '/' + name in namespace_only
    install_expected = old['install_owned_helper.py'].replace('Stage(held.target,args.flow_dir.name.rsplit(\'-\',1)[1])', 'Stage(held.target,args.state_nonce)')
    assert install_expected == normalized['install_owned_helper.py']
    patch = ''.join(''.join(difflib.unified_diff(old.get(name, '').splitlines(True), normalized[name].splitlines(True),
                                               fromfile='actual-r1/helper/' + name, tofile='candidate-r2/helper/' + name))
                    for name in sorted(normalized) if old.get(name) != normalized[name])
    with (HERE / 'candidate-r2/FUNCTIONAL_DIFF.patch').open('x') as f:
        f.write(patch)
    complete_patch = ''.join(''.join(difflib.unified_diff(old.get(name.replace(NEW.replace('.', '/'), OLD.replace('.', '/')), '').splitlines(True), body.splitlines(True),
                                                        fromfile='actual-r1/helper/' + name.replace(NEW.replace('.', '/'), OLD.replace('.', '/')),
                                                        tofile='candidate-r2/helper/' + name))
                             for name, body in sorted(new.items()))
    with (HERE / 'candidate-r2/SOURCE_DIFF.patch').open('x') as f:
        f.write(complete_patch)
    source = {'schema': 'pocket4-fixed-search-final-source-inheritance-v1',
              'base_manifest': pin(BASE / 'SOURCE_PINS.json'), 'candidate_manifest': pin(FINAL / 'SOURCE_PINS.json'),
              'source_closures_verified': [13, 15], 'python_functions': comparison,
              'namespace_only_files': namespace_only, 'old_act_and_following_bytes_unchanged': True,
              'all_other_Java_bytes_except_declared_policy_dispatch_and_added_fragment_unchanged': True,
              'original_PlayerButtonTransaction_body_unchanged': True,
              'installer_only_non_namespace_change': 'Stage takes the fresh validated state_nonce instead of the previously used flow nonce',
              'new_helper_requires_actual_new_build_signer_uid_and_scope': True,
              'host_build': False, 'Android_calls': 0, 'UI_actions': 0, 'production_ready': False}
    source_pin = save_new('SOURCE_INHERITANCE.derived.json', source)

    # Read only an existing private original. The specimen duplicates its tree
    # solely to measure encoding size; it is never labelled a new captured tree.
    bundle_raw = BUNDLE.read_bytes()
    assert len(bundle_raw) == 1102634 and sha(bundle_raw) == BUNDLE_SHA
    bundle = json.loads(bundle_raw)
    bodies = {}
    for name, row in bundle['files'].items():
        raw = base64.b64decode(row['base64'], validate=True)
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
        bodies[name.rsplit('/', 1)[-1]] = raw
    assessment = json.loads(bodies['125381751c22b0a94c1954d0ceddca92.assessment.json'])
    helper, tree = assessment['helper'], assessment['helper']['inspection']
    assert sha(canonical(helper)) == assessment['wire_sha256'] == '3d5cf94834c0a7234b9b0e364ebc35abd1329defada5ee26acc42a867672854e'
    assert len(canonical(tree)) == 221484 and len(tree['nodes']) == 245
    qa = types.ModuleType('offline_wire_budget_contract')
    exec(compile(new['qa_contract.py'], 'qa_contract.py', 'exec'), qa.__dict__)
    assert (qa.MAX_RESULT, qa.MAX_COMPRESSED_WIRE, qa.MAX_STDOUT, qa.MAX_SEARCH_CAPTURE) == (524288, 262144, 353624, 229376)
    model = copy.deepcopy(helper); model.pop('inspection')
    model['search_private_diagnostic'] = {'schema': 1, 'private_UI_evidence': True,
        'reason': 'SIZE_SPECIMEN_ONLY_NOT_AN_ACTUAL_SEARCH_RESULT',
        'complete_captures': [{'role': 'selection', 'inspection': tree}, {'role': 'target', 'inspection': tree}]}
    model_raw = canonical(model)
    measured = []
    # GZIPOutputStream uses zlib's default compression level (6); test that
    # level, not Python's different gzip default level (9).
    for level in (6,):
        compressed = gzip.compress(model_raw, compresslevel=level, mtime=0)
        encoded = base64.b64encode(compressed)
        wire = b'INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=' + encoded + b'\nINSTRUMENTATION_CODE: 0\n'
        assert qa.decode_wire(encoded.decode('ascii')) == model_raw
        assert len(model_raw) <= qa.MAX_RESULT and len(compressed) <= qa.MAX_COMPRESSED_WIRE and len(wire) <= qa.MAX_STDOUT
        measured.append({'gzip_level': level, 'canonical_json_bytes': len(model_raw), 'gzip_bytes': len(compressed),
                         'base64_bytes': len(encoded), 'instrumentation_stdout_bytes': len(wire),
                         'roundtrip_exact': True, 'raw_sha256': sha(model_raw), 'wire_sha256': sha(wire)})
    refs = [FINAL / ('src/' + NEW.replace('.', '/') + '/ActionRunner.java'), FINAL / 'qa_contract.py',
            FINAL / 'qa_adapter.py', FINAL / 'run_case.py',
            PROJECT / 'successor_qa/reconstructed/source-generation-r2/recorder/recorder.py',
            PROJECT / 'successor_qa/reconstructed/source-generation-r2/recorder/bound_android_transport.py',
            PROJECT / 'successor_qa/ffi_bootstrap_probe_r1/probe_ffi_bootstrap.py',
            PROJECT / 'successor_qa/reusable_owned_ui_r1/owned_ui_request_once.py']
    budget = {'schema': 'pocket4-fixed-search-wire-budget-review-v1', 'source_references': [pin(path) for path in refs],
        'raw_JSON_limit': qa.MAX_RESULT, 'gzip_limit': qa.MAX_COMPRESSED_WIRE,
        'base64_encoded_limit': 4 * ((qa.MAX_COMPRESSED_WIRE + 2) // 3), 'instrumentation_stdout_limit': qa.MAX_STDOUT,
        'single_capture_pair_limit': qa.MAX_SEARCH_CAPTURE, 'two_capture_raw_budget': 2 * qa.MAX_SEARCH_CAPTURE,
        'original_outer_owned_child_stdout_limit': 131072, 'original_outer_owned_child_stderr_limit': 16384,
        'namespace_flow_stdout_independent_byte_limit': None,
        'namespace_flow_stdout_policy': 'Original Flow.command writes complete am stdout to exclusive private command files; BoundArun records exact lengths/hashes. No second base64/JSON re-encoding into the outer child stream.',
        'outer_stream_policy': 'run_case and Session summaries only; private helper trees remain command stdout, raw helper result, and private assessment. New failure_diagnostic exposes hashes/counts, not node bodies.',
        'result_persistence_order': ['canonical raw JSON bound', 'writeNew nonce.result.json', 'gzip bound', 'base64 into instrumentation result'],
        'overflow_behavior_unchanged': 'Raw or compressed bound failure is not success. Compressed-bound failure occurs after the complete private raw result write; fixed readback still needs actual path metadata/pin. No truncation or auto retry.',
        'actual_input': {'private_original_sha256': BUNDLE_SHA, 'inspection_wire_sha256': assessment['wire_sha256'],
                         'complete_tree_bytes': len(canonical(tree)), 'complete_tree_nodes': len(tree['nodes'])},
        'measurements': measured, 'measurement_kind': 'LOCAL_SIZE_MODEL_USING_TWO_COPIES_OF_ONE_ALREADY_CAPTURED_TREE',
        'actual_new_search_result': False, 'arbitrary_future_trees_guaranteed_to_compress_under_limit': False,
        'new_capture_lost_or_truncated_to_fit': False, 'raw_private_size_model_saved': False,
        'same_existing_lossless_codec': True, 'any_existing_budget_increased': False, 'remote_execution': False}
    budget_pin = save_new('WIRE_BUDGET.derived.json', budget)
    print(json.dumps({'source_review': source_pin, 'wire_budget': budget_pin, 'size_measurements': measured,
                      'functional_diff': pin(HERE / 'candidate-r2/FUNCTIONAL_DIFF.patch'),
                      'complete_diff': pin(HERE / 'candidate-r2/SOURCE_DIFF.patch')}, sort_keys=True))


if __name__ == '__main__':
    main()
