SEARCH_SELECTOR = {'resource_id': 'com.lianjia.beike:id/tv_nav_right_search_text',
                   'class': 'android.widget.TextView', 'text': '\u641c\u7d22'}
MAX_SEARCH_CAPTURE = (MAX_RESULT - 65536) // 2
MAX_SEARCH_SELECTION_AGE_MS = 1000


def fixed_search_node(inspection):
    inspect_record(inspection)
    selected = select_unique_clickable(inspection, SEARCH_SELECTOR)
    return selected


def assess_search_click(value, request, observed_window, observed_trees, observed_idle):
    require(value.get('search_contract') == 'fixed-beike-search-three-capture-v1' and
            value.get('prior_whole_tree_is_context_only') is True and value.get('prior_target_and_window_still_required') is True and
            value.get('atomic_android_transaction') is False and value.get('same_connection_full_tree_rechecks') == 2 and
            value.get('action_attempted') is True and value.get('outcome_unknown') is True and
            value.get('node_action') == 'ACTION_CLICK' and value.get('node_action_returned') is True and
            value.get('inspection_nonce') == request['inspection_nonce'] and value.get('inspection_sha256') == request['inspection_sha256'] and
            'search_private_diagnostic' not in value and 'search_diagnostic_error' not in value,
            'FIXED_SEARCH_REQUEST_AND_SINGLE_ACK_REQUIRED')
    selected = inspect_record(value.get('search_selection'))
    require(len(canonical(selected)) <= MAX_SEARCH_CAPTURE and value.get('search_selection_sha256') == sha(canonical(selected)),
            'BOUNDED_COMPLETE_NEW_SEARCH_SELECTION')
    node = fixed_search_node(selected)
    require(node == {'node_path': request['node_path'], 'node_sha256': request['node_sha256']} and
            value.get('target_node_path') == node['node_path'] and value.get('target_node_sha256') == node['node_sha256'] and
            value.get('action_window') == selected['window'] and value.get('prior_window_sha256') == selected['window_sha256'] and
            value.get('connection_scoped_window_id') == selected['connection_scoped_window_id'] == observed_window['selected_window_id'],
            'OBSERVED_SEARCH_NODE_AND_STABLE_WINDOW_REQUIRED')
    bindings = value.get('search_capture_bindings')
    require(type(bindings) is list and len(bindings) == 3 and len(observed_trees) == 3,
            'THREE_COMPLETE_SEARCH_CAPTURE_BINDINGS')
    previous = selected['observed_elapsed_ms']
    for index, row in enumerate(bindings):
        require(type(row) is dict and set(row) == {'tree_sha256', 'window_sha256', 'connection_scoped_window_id', 'observed_elapsed_ms'} and
                row['tree_sha256'] == selected['tree_sha256'] and row['window_sha256'] == selected['window_sha256'] and
                type(row['connection_scoped_window_id']) is int and row['connection_scoped_window_id'] == selected['connection_scoped_window_id'] and
                type(row['observed_elapsed_ms']) is int and previous <= row['observed_elapsed_ms'],
                'EVERY_COMPLETE_SEARCH_TREE_WINDOW_AND_CONNECTION_EQUAL')
        require(observed_trees[index]['emitted_nodes'] == len(selected['nodes']) and
                observed_trees[index]['began_elapsed_ms'] <= row['observed_elapsed_ms'] <= observed_trees[index]['last_elapsed_ms'] and
                observed_trees[index]['serialized_bytes'] <= MAX_SEARCH_CAPTURE,
                'ACTUAL_COMPLETE_SEARCH_CAPTURE_TIMING_AND_BOUND')
        previous = row['observed_elapsed_ms']
    require(bindings[0]['observed_elapsed_ms'] == selected['observed_elapsed_ms'] and
            observed_trees[0]['serialized_bytes'] == len(canonical(selected)) and
            observed_trees[0]['began_elapsed_ms'] >= observed_idle['last_elapsed_ms'] and
            type(value.get('search_action_admitted_elapsed_ms')) is int and
            value['started_elapsed_ms'] <= selected['observed_elapsed_ms'] <= previous <= value['search_action_admitted_elapsed_ms'] <= value['finished_elapsed_ms'] and
            type(value.get('search_selection_age_ms')) is int and
            value['search_selection_age_ms'] == value['search_action_admitted_elapsed_ms'] - selected['observed_elapsed_ms'] and
            0 <= value['search_selection_age_ms'] <= MAX_SEARCH_SELECTION_AGE_MS and
            value.get('search_selection_age_limit_ms') == MAX_SEARCH_SELECTION_AGE_MS and
            type(value.get('target_refresh_count')) is int and value['target_refresh_count'] == 2,
            'FRESH_SEARCH_SELECTION_AFTER_FINAL_REFRESH_REQUIRED')


def search_failure_diagnostic(value):
    """Validate private complete trees; return only hashes/roles in public failure metadata."""
    if 'search_private_diagnostic' not in value:
        return {'complete_capture_available': False, 'diagnostic_error': value.get('search_diagnostic_error'),
                'private_full_tree_in_raw_wire': False, 'qualified_success': False}
    diagnostic = value['search_private_diagnostic']
    require(type(diagnostic) is dict and diagnostic.get('schema') == 1 and diagnostic.get('private_UI_evidence') is True and
            diagnostic.get('reason') == value['error'] and diagnostic.get('captured_before_dispatch') is (not value['action_attempted']) and
            diagnostic.get('current_post_action_state_proven') is False and diagnostic.get('original_result_budget') == MAX_RESULT and
            diagnostic.get('pair_capture_budget') == MAX_SEARCH_CAPTURE and
            type(diagnostic.get('selection_full_omitted_for_result_budget')) is bool,
            'EXACT_PRIVATE_SEARCH_FAILURE_DIAGNOSTIC')
    captures = diagnostic.get('complete_captures')
    require(type(captures) is list and len(captures) <= 2 and
            diagnostic.get('complete_capture_available') is bool(captures), 'BOUNDED_FULL_SEARCH_FAILURE_CAPTURE_SET')
    rows = []; roles = set()
    for entry in captures:
        require(type(entry) is dict and set(entry) == {'role', 'inspection'} and entry['role'] in ('selection', 'target', 'final') and
                entry['role'] not in roles, 'EXACT_SEARCH_FAILURE_CAPTURE_ROLE')
        roles.add(entry['role']); captured = inspect_record(entry['inspection'])
        rows.append({'role': entry['role'], 'inspection_sha256': sha(canonical(captured)),
                     'tree_sha256': captured['tree_sha256'], 'window_sha256': captured['window_sha256'],
                     'connection_scoped_window_id': captured['connection_scoped_window_id'],
                     'observed_elapsed_ms': captured['observed_elapsed_ms'], 'nodes': len(captured['nodes'])})
    return {'complete_capture_available': bool(captures), 'captures': rows,
            'private_full_tree_in_raw_wire': bool(captures), 'qualified_success': False,
            'selection_full_omitted_for_result_budget': diagnostic['selection_full_omitted_for_result_budget'],
            'raw_wire_still_private': True}
