"""Finite synthetic controls of the new production parser; no Android state or input."""
import base64
import copy
import gzip
import hashlib
import types


CASES = [
    'complete_search_wire_with_three_equal_trees',
    'general_and_player_operations_still_closed',
    'different_target_tree_rejected',
    'different_final_window_rejected',
    'different_connection_id_rejected',
    'changed_observed_target_hash_rejected',
    'selection_age_1001_rejected',
    'missing_second_refresh_rejected',
    'failure_keeps_complete_private_trees_and_never_passes',
    'failed_tree_hash_cannot_be_claimed_complete',
]


def run(contract_source):
    qa = types.ModuleType('owned_fixed_search_contract_controls')
    exec(compile(contract_source, 'qa_contract.py', 'exec'), qa.__dict__)
    def need(value, why):
        if not value:
            raise AssertionError(why)
    rows = []
    def check(name, body):
        body(); rows.append({'name': name, 'passed': True})
    scope = {'package': qa.PACKAGE, 'uid': qa.UID, 'user': 0, 'display': 0,
             'activity': qa.PACKAGE + '/com.lianjia.activity.MainActivity', 'window_token': 'abc',
             'main_epoch_sha256': qa.MAIN_EPOCH, 'main_baseline_schema': qa.MAIN_BASELINE_SCHEMA,
             'main_baseline_sha256': qa.MAIN_BASELINE_SHA, 'main_baseline_qualification_sha256': qa.MAIN_BASELINE_QUALIFICATION_SHA,
             'runtime_epoch_sha256': qa.RUNTIME_EPOCH, 'app_scope_sha256': qa.APP_SCOPE_SHA}
    node = {'package': qa.PACKAGE, 'path': '0', 'visible': True, 'password': False, 'enabled': True, 'clickable': True,
            'editable': False, 'supports_set_text': False, 'focused': False, 'selected': False, 'checked': False,
            'child_count': 0, 'bounds': [1, 1, 30, 30], **qa.SEARCH_SELECTOR, 'content_desc': ''}
    for field in ('resource_id', 'class', 'text', 'content_desc'):
        node[field + '_sha256'] = qa.sha(node[field].encode())
        node[field + '_truncated'] = False
    node['node_sha256'] = qa.sha(qa.canonical(node))
    window = {'package': qa.PACKAGE, 'display': 0, 'type': 1, 'focused': True, 'bounds': [0, 0, 100, 100]}
    selection = {'complete': True, 'traversal': 'visible-non-password-subtrees', 'window': window,
                 'window_sha256': qa.sha(qa.canonical(window)), 'nodes': [node], 'tree_sha256': qa.sha(qa.canonical([node])),
                 'connection_scoped_window_id': 7, 'observed_elapsed_ms': 1700}
    request = {'protocol': qa.PROTOCOL, 'nonce': '2' * 32, 'op': 'search_click', 'scope': scope,
               'inspection_nonce': '1' * 32, 'inspection_sha256': '3' * 64,
               'node_path': '0', 'node_sha256': node['node_sha256']}
    idle = {'schema': 1, 'operation': 'inspect', 'invoked': True, 'call_count': 1, 'operation_started_elapsed_ms': 1000,
            'began_elapsed_ms': 1100, 'last_elapsed_ms': 1600, 'waited_ms': 500, 'quiet_timeout_ms': 500,
            'global_timeout_cap_ms': 2000, 'global_timeout_ms': 2000, 'operation_deadline_ms': 8000,
            'api_returned': True, 'qualified': True, 'exception_class': '', 'secondary_clock_exception_class': '',
            'gate_error': '', 'event_quiet_only': True, 'content_ready_proven': False, 'future_stability_proven': False}
    state = {'accessibility_enabled': False, 'touch_exploration_enabled': False,
             'enabled_service_count': 0, 'enabled_services_sha256': '0' * 64}
    census = {'sample': 1, 'event_serial': 0, 'elapsed_ms': 0, 'displays': [0],
              'windows': [{'display': 0, 'id': 7, 'type': 1, 'focused': True, 'active': True,
                           'accessibility_focused': False, 'layer': 0}]}
    observed_window = {'requested_display': 0, 'selection': 'exact-display-0-focused-application',
                       'wait_budget_ms': 2000, 'recheck_max_ms': 100, 'ready': True, 'first': census, 'last': census,
                       'samples': 1, 'waited_ms': 0, 'selected_display': 0, 'selected_window_id': 7,
                       'sample_timings': [{'sample': 1, 'event_serial': 0, 'elapsed_ms': 0, 'cache_cleared': True}],
                       'cache_api': 'android.app.UiAutomation.clearCache()',
                       'cache_policy': 'require_public_own_connection_clear_before_each_query', 'cache_runtime_sdk': 37,
                       'cache_attempts': 1, 'cache_clears': 1, 'cache_last_result': True, 'cache_last_exception': None}
    bindings = []; counters = []
    for i, purpose in enumerate(('search_selection', 'action_target', 'action_final_window')):
        bindings.append({'tree_sha256': selection['tree_sha256'], 'window_sha256': selection['window_sha256'],
                         'connection_scoped_window_id': 7, 'observed_elapsed_ms': 1700 + i * 100})
        counters.append({'capture': i + 1, 'purpose': purpose, 'node_limit': 512, 'depth_limit': 32, 'child_limit': 64,
                         'json_byte_limit': qa.MAX_RESULT - 65536, 'attempted_nodes': 1, 'emitted_nodes': 1,
                         'max_attempted_depth': 0, 'max_observed_children': 0, 'serialized_bytes': len(qa.canonical(selection)),
                         'complete': True, 'began_elapsed_ms': 1600 + i * 100, 'last_elapsed_ms': 1700 + i * 100})
    value = {'protocol': qa.PROTOCOL, 'nonce': request['nonce'], 'op': 'search_click', 'request_sha256': qa.sha(qa.canonical(request)),
             'wire_codec': 'gzip-canonical-json-v1', 'self_uid': 30001, 'self_pid': 99999, 'ok': True, 'error': None,
             'secondary_errors': [], 'claim_persistence_completed': True, 'helper_work_completed': True,
             'automatic_retry': False, 'business_success_verified': False, 'accessibility_mode_restoration_verified': None,
             'started_elapsed_ms': 1000, 'finished_elapsed_ms': 2100, 'action_attempted': True, 'outcome_unknown': True,
             'restoration': {'service_info_verified': True, 'service_info_captured': True, 'connection_flags': 1,
                             'service_flags_before': 0, 'service_flags_during': 80, 'service_flags_after': 0,
                             'service_capabilities_before': 0, 'service_capabilities_after': 0},
             'host_scope_attestation': scope, 'activity_verified_inside_helper': False, 'target_uid_verified': qa.UID,
             'requires_post_termination_state_check': True, 'accessibility_state_before_connection': state,
             'window_observation': observed_window, 'tree_observations': counters, 'inspection_idle_observation': idle,
             'inspection_nonce': request['inspection_nonce'], 'inspection_sha256': request['inspection_sha256'],
             'prior_whole_tree_is_context_only': True, 'prior_target_and_window_still_required': True,
             'prior_window_sha256': selection['window_sha256'], 'atomic_android_transaction': False,
             'search_contract': 'fixed-beike-search-three-capture-v1', 'same_connection_full_tree_rechecks': 2,
             'search_selection': selection, 'search_selection_sha256': qa.sha(qa.canonical(selection)),
             'target_node_path': '0', 'target_node_sha256': node['node_sha256'], 'action_window': window,
             'connection_scoped_window_id': 7, 'search_capture_bindings': bindings,
             'search_action_admitted_elapsed_ms': 2000, 'search_selection_age_ms': 300,
             'search_selection_age_limit_ms': 1000, 'target_refresh_count': 2,
             'node_action': 'ACTION_CLICK', 'node_action_returned': True}
    def wire(body, finish=-1):
        return (b'INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=' +
                base64.b64encode(gzip.compress(qa.canonical(body), mtime=0)) +
                b'\nINSTRUMENTATION_CODE: ' + str(finish).encode() + b'\n')
    def parse(body):
        return qa.parse_completed(wire(body), b'', 0, request, 30001)
    check(CASES[0], lambda: parse(copy.deepcopy(value)))
    def closed():
        need(qa.ALLOWED_OPERATIONS == ('state', 'inspect', 'search_click'), 'exact new operation closure')
        for op in ('click', 'set_text', 'reveal_controls', 'player_button', 'accept'):
            altered = copy.deepcopy(request); altered['op'] = op
            try: qa.validate_request(altered)
            except qa.ProtocolError as error: need(str(error) == 'COMPILED_OPERATION_POLICY', 'closed operation reason')
            else: raise AssertionError('general operation accepted')
    check(CASES[1], closed)
    def rejects(name, mutate):
        def control():
            changed = copy.deepcopy(value); mutate(changed)
            try: parse(changed)
            except qa.ProtocolError: pass
            else: raise AssertionError('changed evidence accepted')
        check(name, control)
    rejects(CASES[2], lambda v: v['search_capture_bindings'][1].update(tree_sha256='f' * 64))
    rejects(CASES[3], lambda v: v['search_capture_bindings'][2].update(window_sha256='f' * 64))
    rejects(CASES[4], lambda v: v['search_capture_bindings'][1].update(connection_scoped_window_id=8))
    rejects(CASES[5], lambda v: v.update(target_node_sha256='f' * 64))
    rejects(CASES[6], lambda v: v.update(search_action_admitted_elapsed_ms=2701, search_selection_age_ms=1001, finished_elapsed_ms=2800))
    rejects(CASES[7], lambda v: v.update(target_refresh_count=1))
    failed = copy.deepcopy(value)
    changed_tree = copy.deepcopy(selection); changed_tree['nodes'][0]['selected'] = True
    changed_tree['nodes'][0]['node_sha256'] = qa.sha(qa.canonical({k: x for k, x in changed_tree['nodes'][0].items() if k != 'node_sha256'}))
    changed_tree['tree_sha256'] = qa.sha(qa.canonical(changed_tree['nodes'])); changed_tree['observed_elapsed_ms'] = 1800
    failed.update(ok=False, error='SEARCH_CURRENT_TREE_OR_WINDOW_CHANGED', action_attempted=False, outcome_unknown=False,
                  tree_observations=counters[:2], search_private_diagnostic={
                      'schema': 1, 'private_UI_evidence': True, 'reason': 'SEARCH_CURRENT_TREE_OR_WINDOW_CHANGED',
                      'captured_before_dispatch': True, 'current_post_action_state_proven': False,
                      'original_result_budget': qa.MAX_RESULT, 'pair_capture_budget': qa.MAX_SEARCH_CAPTURE,
                      'selection_full_omitted_for_result_budget': False, 'complete_capture_available': True,
                      'complete_captures': [{'role': 'selection', 'inspection': selection}, {'role': 'target', 'inspection': changed_tree}]})
    failed.pop('search_selection')
    def failed_complete():
        diagnostic = qa.failure_diagnostic(wire(failed, 0), request, 30001)
        need(diagnostic['qualified_success'] is False and diagnostic['search_failure']['private_full_tree_in_raw_wire'] is True and
             len(diagnostic['search_failure']['captures']) == 2 and 'inspection' not in diagnostic['search_failure'],
             'only safe metadata in diagnostic summary')
        try: qa.parse_completed(wire(failed, 0), b'', 0, request, 30001)
        except qa.ProtocolError as error: need(str(error) == 'EXACT_SUCCESSFUL_FINISH_REQUIRED', 'failed finish unchanged')
        else: raise AssertionError('failed wire passed')
    check(CASES[8], failed_complete)
    def failed_hash():
        altered = copy.deepcopy(failed); altered['search_private_diagnostic']['complete_captures'][1]['inspection']['tree_sha256'] = 'f' * 64
        try: qa.failure_diagnostic(wire(altered, 0), request, 30001)
        except qa.ProtocolError: pass
        else: raise AssertionError('bad diagnostic tree accepted')
    check(CASES[9], failed_hash)
    need([row['name'] for row in rows] == CASES, 'exact fixed control set')
    return {'schema': 1, 'all_passed': True, 'count': len(rows), 'cases': rows,
            'android_calls': 0, 'tree_captures': 0, 'input_actions': 0,
            'production_contract_sha256': hashlib.sha256(contract_source.encode()).hexdigest()}
