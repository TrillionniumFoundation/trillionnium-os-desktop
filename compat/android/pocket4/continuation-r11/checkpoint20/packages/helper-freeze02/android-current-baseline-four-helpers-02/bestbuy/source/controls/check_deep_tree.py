"""Synthetic controls for the actual R2 protocol parser; no Android API or device actions."""
import base64
import copy
import gzip
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent.parent
qa = types.ModuleType('bestbuy_r2_actual_contract')
qa.__file__ = str(HERE / 'qa_contract.py')
exec(compile((HERE / 'qa_contract.py').read_bytes(), qa.__file__, 'exec'), qa.__dict__)
HELPER_UID = 30000  # Synthetic fixture only; never an installed-device identity.
REQUEST = {'protocol': qa.PROTOCOL, 'nonce': '1' * 32, 'op': 'inspect',
           'scope': {'package': qa.PACKAGE, 'uid': qa.UID, 'user': 0, 'display': 0,
                     'activity': 'com.bestbuy.android/.SyntheticFixture',
                     'window_token': '1234', 'main_epoch_sha256': qa.MAIN_EPOCH, 'main_baseline_schema':qa.MAIN_BASELINE_SCHEMA,
                      'main_baseline_sha256':qa.MAIN_BASELINE_SHA,
                      'main_baseline_qualification_sha256':qa.MAIN_BASELINE_QUALIFICATION_SHA}}
STATE = {'accessibility_enabled': False, 'touch_exploration_enabled': False,
         'enabled_service_count': 0, 'enabled_services_sha256': qa.sha(qa.canonical([]))}
CASES = []


def node(path, children):
    value = {'path': path, 'package': qa.PACKAGE, 'enabled': True, 'clickable': False,
             'visible': True, 'focused': False, 'selected': False, 'checked': False,
             'password': False, 'child_count': children, 'editable': False,
             'supports_set_text': False, 'bounds': [0, 0, 100, 100],
             'class': 'android.view.ViewGroup', 'class_truncated': False,
             'class_sha256': qa.sha(b'android.view.ViewGroup')}
    value['node_sha256'] = qa.sha(qa.canonical(value))
    return value


def inspection(depth):
    rows = [node('0' + '/0' * n, int(n < depth)) for n in range(depth + 1)]
    window = {'package': qa.PACKAGE, 'display': 0, 'type': 1, 'focused': True,
              'bounds': [0, 0, 100, 100]}
    return {'window': window, 'window_sha256': qa.sha(qa.canonical(window)),
            'connection_scoped_window_id': 7, 'nodes': rows,
            'tree_sha256': qa.sha(qa.canonical(rows)), 'observed_elapsed_ms': 150,
            'complete': True, 'traversal': 'visible-non-password-subtrees'}


def counter(view, depth):
    return {'capture': 1, 'purpose': 'inspection', 'node_limit': qa.MAX_NODES,
            'depth_limit': qa.MAX_DEPTH, 'child_limit': 64,
            'json_byte_limit': qa.MAX_RESULT - 65536, 'attempted_nodes': len(view['nodes']),
            'emitted_nodes': len(view['nodes']), 'max_attempted_depth': depth,
            'max_observed_children': 1 if depth else 0,
            'serialized_bytes': len(qa.canonical(view)), 'complete': True,
            'began_elapsed_ms': 100, 'last_elapsed_ms': 150}


def window_observation():
    census = {'sample': 1, 'event_serial': 0, 'elapsed_ms': 0, 'displays': [0],
              'windows': [{'display': 0, 'id': 7, 'type': 1, 'focused': True,
                           'active': True, 'accessibility_focused': False, 'layer': 0}]}
    return {'requested_display': 0, 'selection': 'exact-display-0-focused-application',
            'wait_budget_ms': 2000, 'ready': True, 'recheck_max_ms': 100,
            'samples': 1, 'waited_ms': 0, 'selected_display': 0, 'selected_window_id': 7,
            'sample_timings': [{'sample': 1, 'event_serial': 0, 'elapsed_ms': 0,
                               'cache_cleared': True}],
            'cache_api': 'android.app.UiAutomation.clearCache()',
            'cache_policy': 'require_public_own_connection_clear_before_each_query',
            'cache_runtime_sdk': 34, 'cache_attempts': 1, 'cache_clears': 1,
            'cache_last_result': True, 'cache_last_exception': None,
            'first': copy.deepcopy(census), 'last': copy.deepcopy(census)}


def result(depth):
    view = inspection(depth)
    return {'protocol': qa.PROTOCOL, 'nonce': REQUEST['nonce'], 'op': 'inspect',
            'request_sha256': qa.sha(qa.validate_request(REQUEST)), 'wire_codec': 'gzip-canonical-json-v1',
            'self_uid': HELPER_UID, 'self_pid': 999, 'ok': True, 'error': None,
            'secondary_errors': [], 'claim_persistence_completed': True,
            'helper_work_completed': True, 'automatic_retry': False,
            'business_success_verified': False, 'accessibility_mode_restoration_verified': None,
            'started_elapsed_ms': 100, 'finished_elapsed_ms': 200,
            'restoration': {'service_info_verified': True, 'service_info_captured': True,
                            'connection_flags': 1, 'service_flags_before': 0,
                            'service_flags_during': 80, 'service_flags_after': 0,
                            'service_capabilities_before': 0, 'service_capabilities_after': 0},
            'host_scope_attestation': copy.deepcopy(REQUEST['scope']),
            'activity_verified_inside_helper': False, 'target_uid_verified': qa.UID,
            'requires_post_termination_state_check': True,
            'accessibility_state_before_connection': copy.deepcopy(STATE),
            'window_observation': window_observation(),
            'tree_observations': [counter(view, depth)], 'inspection': view,
            'action_attempted': False, 'outcome_unknown': False}


def wire(value, finish=-1):
    encoded = base64.b64encode(gzip.compress(qa.canonical(value), mtime=0)).decode('ascii')
    return ('INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=' + encoded +
            '\nINSTRUMENTATION_CODE: ' + str(finish) + '\n').encode('ascii')


def parsed(value):
    return qa.parse_completed(wire(value), b'', 0, REQUEST, HELPER_UID)


def mutate(depth, section, field, value):
    data = result(depth)
    target = data[section][0] if section == 'tree_observations' else data[section]
    target[field] = value
    return data


def case(name, call, rejection=None):
    try:
        call()
    except qa.ProtocolError as error:
        if rejection is None or str(error) != rejection:
            raise AssertionError(name + ': unexpected rejection ' + repr(error)) from error
    else:
        if rejection is not None:
            raise AssertionError(name + ': invalid record was accepted')
    CASES.append(name)


def diagnostic_partial():
    value = result(33)
    value.update(ok=False, error='TREE_DEPTH_BOUND')
    value.pop('inspection')
    row = value['tree_observations'][0]
    row.update(complete=False, attempted_nodes=130, emitted_nodes=129,
               max_attempted_depth=129, serialized_bytes=0)
    actual = qa.failure_diagnostic(wire(value, 0), REQUEST, HELPER_UID)
    assert actual['qualified_success'] is False and actual['error'] == 'TREE_DEPTH_BOUND'
    assert actual['tree_observations'][0] == row
    try:
        qa.parse_completed(wire(value, 0), b'', 0, REQUEST, HELPER_UID)
    except qa.ProtocolError as error:
        assert str(error) == 'EXACT_SUCCESSFUL_FINISH_REQUIRED'
    else:
        raise AssertionError('failure diagnostic became a successful parse')


def maximum_nodes():
    value = result(0)
    rows = [node('0', 8)]
    for branch in range(8):
        children = 62 if branch == 7 else 63
        rows.append(node('0/' + str(branch), children))
        rows.extend(node('0/' + str(branch) + '/' + str(n), 0) for n in range(children))
    assert len(rows) == 512
    view = value['inspection']
    view['nodes'] = rows
    view['tree_sha256'] = qa.sha(qa.canonical(rows))
    value['tree_observations'] = [counter(view, 2)]
    value['tree_observations'][0]['max_observed_children'] = 63
    parsed(value)


def deepest_action_path():
    request = {'protocol': qa.PROTOCOL, 'nonce': '2' * 32, 'op': 'click',
               'scope': copy.deepcopy(REQUEST['scope']), 'inspection_nonce': '1' * 32,
               'inspection_sha256': 'a' * 64, 'node_path': '0' + '/63' * 128,
               'node_sha256': 'b' * 64}
    assert len(request['node_path']) == 385
    qa.validate_request(request)  # Parser-only fixture, no action or transport.
    request['node_path'] += '/0'
    try:
        qa.validate_request(request)
    except qa.ProtocolError as error:
        assert str(error) == 'NODE_PATH_REQUIRED'
    else:
        raise AssertionError('129-level action path was accepted')


def old_helper_uid():
    value = result(33)
    value['self_uid'] = 10198
    return qa.parse_completed(wire(value), b'', 0, REQUEST, 10198)


def mismatched_count():
    value = result(33)
    value['tree_observations'][0]['emitted_nodes'] += 1
    value['tree_observations'][0]['attempted_nodes'] += 1
    return parsed(value)


case('complete_depth_33_previously_failed_bound', lambda: parsed(result(33)))
case('complete_depth_128_exact_boundary', lambda: parsed(result(128)))
case('complete_depth_129_rejected', lambda: qa.inspect_record(inspection(129)),
     'NODE_SCOPE_OR_PATH_FAILED')
case('partial_inspection_cannot_qualify',
     lambda: parsed(mutate(33, 'inspection', 'complete', False)), 'COMPLETE_INSPECTION_REQUIRED')
case('partial_counter_cannot_qualify',
     lambda: parsed(mutate(33, 'tree_observations', 'complete', False)), 'PARTIAL_TREE_CANNOT_QUALIFY')
case('old_32_limit_counter_rejected',
     lambda: parsed(mutate(33, 'tree_observations', 'depth_limit', 32)), 'EXACT_TREE_LIMITS_REQUIRED')
case('counter_beyond_128_rejected',
     lambda: parsed(mutate(33, 'tree_observations', 'max_attempted_depth', 129)),
     'COMPLETE_TREE_COUNTERS_INCONSISTENT')
case('child_count_65_rejected',
     lambda: parsed(mutate(33, 'tree_observations', 'max_observed_children', 65)),
     'COMPLETE_TREE_COUNTERS_INCONSISTENT')
case('tree_json_over_original_bound_rejected',
     lambda: parsed(mutate(33, 'tree_observations', 'serialized_bytes', 458753)),
     'COMPLETE_TREE_COUNTERS_INCONSISTENT')
case('complete_counter_must_match_exact_inspection_bytes',
     lambda: parsed(mutate(33, 'tree_observations', 'serialized_bytes',
                           len(qa.canonical(inspection(33))) + 1)),
     'COMPLETE_TREE_COUNTERS_MUST_MATCH_ACTUAL_INSPECTION')
case('complete_counter_must_match_exact_node_count', mismatched_count,
     'COMPLETE_TREE_COUNTERS_MUST_MATCH_ACTUAL_INSPECTION')
case('synthetic_partial_failure_shape_preserved_never_qualified', diagnostic_partial)
case('maximum_512_nodes_within_original_node_bound', maximum_nodes)
case('attempted_513_complete_counter_rejected',
     lambda: parsed(mutate(33, 'tree_observations', 'attempted_nodes', 513)),
     'COMPLETE_TREE_COUNTERS_INCONSISTENT')
case('deepest_action_path_parser_bound_without_dispatch', deepest_action_path)
case('old_helper_UID_10198_cannot_qualify_r2',
     old_helper_uid,
     'INSTALLED_HELPER_IDENTITY_REQUIRED')
assert len(CASES) == 16 and len(set(CASES)) == 16
print(json.dumps({'state': 'PASS_PROTOCOL_CONTROLS_ONLY', 'cases': len(CASES),
                  'case_names': CASES, 'max_depth': qa.MAX_DEPTH,
                  'Java_scanner_executed': False, 'Android_actions': 0,
                  'synthetic_only': True, 'whole_app_production_ready': False}, sort_keys=True))
