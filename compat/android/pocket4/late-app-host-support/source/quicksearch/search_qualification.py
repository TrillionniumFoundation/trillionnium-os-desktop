"""Read-only composition of three actual same-Main QSB branch results; common app gates stay separate."""
import os
from pathlib import Path
import re

def branch_scope(c, planner, base_ref, base, result, current):
    """Bind completed observations without reviving an expired process lease."""
    active_ref = result['active_plan']; active = c.parse(c.read_ref(active_ref))
    c.need(active_ref['path'] == base['case_root'] + '/active-plan.json'
        and active == {**base, 'schema': 'pocket4-final-quicksearch-active-plan-v1',
            'base_plan': base_ref, 'lease': active['lease'], 'action_lock': active['action_lock']},
        'COMPLETED_ACTIVE_PLAN_MUST_DERIVE_FROM_THIS_BASE')
    planner.validate(c, active, current, semantic=False)
    lease = c.parse(c.read_ref(active['lease'])); phase_ref = result['actual_business_phase']
    phase = c.parse(c.read_ref(phase_ref)); task = c.parse(c.read_ref(base['task_source_manifest']))
    c.need(active['lease']['path'] == base['case_root'] + '/lease.json'
        and lease['schema'] == 'pocket4-final-system-case-lease-v1' and lease['base_plan'] == base_ref
        and lease['kind'] == base['kind'] and lease['automatic_retry'] is False
        and lease['business_seconds'] == base['limits']['business_seconds'] == 420
        and lease['cleanup_seconds'] == base['limits']['cleanup_seconds'] == 60
        and type(lease['started_monotonic_ns']) is type(lease['business_deadline_monotonic_ns']) is int
        and lease['business_deadline_monotonic_ns'] == lease['started_monotonic_ns'] + 420000000000,
        'ORIGINAL_COMPLETED_CASE_LEASE_BOUND_TO_THIS_BASE')
    c.need(phase_ref['path'] == base['case_root'] + '/phase-business.json'
        and phase['schema'] == 'pocket4-final-system-phase-lease-v1'
        and phase['active_plan'] == active_ref and phase['lease'] == active['lease']
        and phase['phase'] == 'business' and phase['owner'] == lease['owner']
        and phase['trigger'] is None and phase['automatic_retry'] is False
        and type(phase['started_monotonic_ns']) is type(phase['deadline_monotonic_ns']) is int
        and lease['started_monotonic_ns'] <= phase['started_monotonic_ns'] < phase['deadline_monotonic_ns']
        and phase['deadline_monotonic_ns'] == lease['business_deadline_monotonic_ns'],
        'ORIGINAL_COMPLETED_BUSINESS_PHASE_BOUND_TO_THIS_ACTIVE_PLAN')
    scopes = result['recorder_scopes']
    c.need(type(scopes) is list and len(scopes) == 2 and scopes[0] != scopes[1],
        'TWO_DISTINCT_ORIGINAL_RECORDER_SCOPES')
    for index, scope_ref in enumerate(scopes):
        scope = c.parse(c.read_ref(scope_ref)); flow = base['flows'][index]
        expected = {'schema': 'pocket4-final-business-recorder-scope-v1', 'business_baseline': base['baseline'],
            'business_qualification': base['qualification'], 'support_manifest': base['support_manifest'],
            'framework_epoch_sha256': base['framework_epoch_sha256'], 'package': base['target_profile']['package'],
            'uid': base['target_profile']['uid'], 'user': 0, 'component': base['target_profile']['component'], **flow,
            'task_source_manifest': base['task_source_manifest'], 'phase_plan': active_ref,
            'actual_resolution_receipt': base['target_identity'],
            'installed_helper_receipts': [base['helper_identity'], base['browser_identity']],
            'recorder_source': task['recorder_source'], 'guard_source': task['guard_source'], 'automatic_retry': False}
        c.need(scope_ref['path'] == flow['flow_root'] + '/scope.json' and scope == expected,
            'EXACT_SAME_MAIN_RECORDER_SCOPE_FOR_THIS_ROUND')
    return [active_ref, active['lease'], active['action_lock'], phase_ref, *scopes]

def observation(c, ref, package, scope_ref, phase_ref):
    value = c.parse(c.read_ref(ref))
    c.need(value['schema'] == 'pocket4-final-original-api-result-v1' and value['api'] == 'dispatch'
        and value['scope'] == scope_ref and value['phase_lease'] == phase_ref
        and value['request']['op'] == 'observe' and value['request']['package'] == package
        and value['request']['display'] == 0 and value['request']['accessibility_mode'] == 'none'
        and value['original_error'] is None and value['action_attempted'] is False
        and value['whole_app_business_accepted'] is False and value['automatic_retry'] is False,
        'ACTUAL_UNMUTATED_OWNED_UI_OBSERVATION_REQUIRED')
    result = value['result']; native = result['native']; scope = result['screenshot']['scope']
    c.need(result.get('ok') is True and result.get('outcome_unknown') is not True
        and native.get('ok') is True and native.get('accessibility_mode_restoration_verified') is True
        and scope['package'] == package and scope['window_token'] == value['request']['window_token'],
        'UNCHANGED_SUCCESSFUL_ACTUAL_UI_RESULT')
    png = result['recorded_png']
    c.need(c.regular(png['path'], 33554432, contents=False) == png, 'ACTUAL_OBSERVATION_IMAGE_UNCHANGED')
    return value, native['nodes']

def query_field(c, nodes, package):
    rows = [n for n in nodes if n.get('package') == package and n.get('resource-id') == package + ':id/search_src_text'
        and n.get('editable') is True and n.get('visible') is True and n.get('enabled') is True and n.get('password') is False]
    c.need(len(rows) == 1 and type(rows[0].get('text')) is str, 'ONE_ACTUAL_USABLE_QUERY_FIELD')
    return rows[0]['text']

def qualify(c, preparation_ref, planner, request, output):
    c.need(os.getuid() == os.geteuid() == 0 and set(request) == {'cases'} and isinstance(request['cases'], list)
        and len(request['cases']) == 3 and all(set(row) == {'base_plan', 'result'} for row in request['cases']),
        'THREE_EXACT_ACTUAL_BRANCH_INPUTS')
    packet = planner.preparation(c, preparation_ref)
    profiles = planner.named(c, packet, 'search_profiles.py'); handoff = planner.named(c, packet, 'search_handoff.py')
    _, support = c.support(c.SUPPORT_REF); by_kind = {}; refs = [preparation_ref]; baseline = None
    for row in request['cases']:
        base = c.parse(c.read_ref(row['base_plan'])); result = c.parse(c.read_ref(row['result']))
        c.need(base['kind'] not in by_kind and base['kind'] in profiles.KINDS
            and base['source_preparation'] == preparation_ref and row['base_plan']['path'] == base['case_root'] + '/plan.json'
            and row['result']['path'] == base['case_root'] + '/result.json', 'DISTINCT_FRESH_SOURCE_BOUND_BRANCH_PATHS')
        current = support['business_baseline.py'].BusinessBaseline(base['baseline'], base['qualification'])
        planner.validate(c, base, current); current.guard()
        if baseline is None:
            baseline = current
        c.need(base['baseline'] == baseline.baseline_ref and base['qualification'] == baseline.qualification_ref
            and base['framework_epoch_sha256'] == baseline.value['framework_epoch']['sha256'], 'ALL_BRANCHES_SAME_ACTUAL_FINAL_MAIN')
        c.need(result['schema'] == 'pocket4-final-quicksearch-branch-result-v1'
            and result['state'] == 'ACTUAL_SEARCH_BRANCH_VERIFIED_CLEAN' and result['kind'] == base['kind']
            and result['plan'] == row['base_plan'] and result['branch_business_success_verified'] is True
            and result['branch_scope_completed'] is True and result.get('error') is None and result['secondary_errors'] == []
            and result['pending_input'] is None and result['received_signals'] == []
            and result['cancellation_commit']['observed_before_commit'] == []
            and result['cancellation_commit']['pending_at_commit'] == []
            and result['actual_permissions_unchanged'] is True and result['final_source_and_identity_chain_unchanged'] is True
            and result['actual_Main_and_UI_closed'] is result['whole_case_OFD_closed'] is result['evidence_witness_closed'] is True
            and result['whole_app_business_accepted'] is False and result['original_search_failure_gate_complete'] is False,
            'COMPLETE_ACTUAL_BRANCH_PRODUCER_RESULT_NOT_HOST_FIXTURE')
        c.need(result['native_tasks'] == result['closed_native_tasks'] and len(set(result['native_tasks'])) == 2
            and result['native_launch_calls'] == 2 and result['native_browser_launch_calls'] == 0
            and result['query_preimages_restored'] == [0, 1] and result['owned_primary_remaining'] is None
            and result['owned_browser_remaining'] is None and result['implicit_browser_tasks'] == result['closed_browser_tasks']
            and result['original_full_app_gates_unchanged'] is True and result['original_search_gates_unchanged'] is True
            and all(result[k] == 0 for k in ('network_configuration_writes', 'permission_writes', 'account_operations', 'package_mutations')),
            'ACTUAL_LIFECYCLE_AND_ORIGINAL_PREIMAGE_RESTORATION')
        c.need(type(result['diagnostics']) is dict
            and set(result['diagnostics']) == {profiles.SEARCH['package'], profiles.BROWSER['package']}
            and all(x['clear'] is True for x in result['diagnostics'].values()) and result['guard_after']
            and result['independent_Main_after'], 'ACTUAL_CRASH_ANR_AND_FINAL_MAIN_CHECKS')
        refs.extend(branch_scope(c, planner, row['base_plan'], base, result, current))
        c.need(len(result['empty_query_paths']) == 2
            and len({r['path'] for r in result['empty_query_paths']}) == 2, 'TWO_ACTUAL_EMPTY_QUERY_PATHS')
        for index, ref in enumerate(result['empty_query_paths']):
            _, nodes = observation(c, ref, profiles.SEARCH['package'], result['recorder_scopes'][index],
                result['actual_business_phase'])
            c.need(query_field(c, nodes, profiles.SEARCH['package']) == '', 'ACTUAL_EMPTY_FIELD_READBACK')
            refs.append(ref)
        by_kind[base['kind']] = (base, result, row); refs.extend(row.values())
    c.need(set(by_kind) == set(profiles.KINDS), 'ONLINE_OFFLINE_AND_ERROR_EVIDENCE_ALL_REQUIRED')
    base, online, _ = by_kind['search_online']; package = profiles.SEARCH['package']; browser = profiles.BROWSER['package']
    c.need(len(online['unicode_query_evidence']) == 2 and online['back_inputs'] == 1
        and len(online['implicit_browser_tasks']) == 1 and online.get('result_return'), 'FULL_ORIGINAL_QUERY_AND_OPEN_GATES')
    observed_queries = []
    for index, ref in enumerate(online['unicode_query_evidence']):
        q = c.parse(c.read_ref(ref)); _, nodes = observation(c, q['actual_observation'], package,
            online['recorder_scopes'][index], online['actual_business_phase'])
        c.need(query_field(c, nodes, package) == q['query'] and q['query'] in base['queries']
            and q['matches'] == handoff.matching_labels(nodes, package, q['query']) and q['matches'],
            'REAL_MATCHING_UNICODE_RESULT_CONTENT')
        observed_queries.append(q['query']); refs.extend([ref, q['actual_observation']])
    c.need(observed_queries == base['queries'], 'BOTH_ORIGINAL_UNICODE_QUERIES')
    returned = c.parse(c.read_ref(online['result_return'])); opened = c.parse(c.read_ref(returned['opened']))
    _, browser_nodes = observation(c, opened['actual_browser'], browser, online['recorder_scopes'][0],
        online['actual_business_phase'])
    rendered = handoff.rendered_result(browser_nodes, browser, opened['query_before_open'])
    c.need(rendered == opened['actual_rendered_document'], 'ACTUAL_RENDERED_RESULT_CONTENT_UNCHANGED')
    handoff.search_url(opened['opened']['url'], opened['known_result']['result_text'])
    _, returned_nodes = observation(c, returned['actual_return'], package, online['recorder_scopes'][0],
        online['actual_business_phase'])
    c.need(returned['query'] == opened['query_before_open'] == query_field(c, returned_nodes, package)
        and returned['same_native_search_task'] == online['native_tasks'][0]
        and returned['browser_task_retired'] is True and opened['native_launch_claim_for_browser'] is False,
        'REAL_RESULT_HANDOFF_RETURN_AND_QUERY_STATE')
    refs.extend([online['result_return'], returned['opened'], opened['actual_browser'], returned['actual_return']])
    failures = {}
    for kind in ('search_offline', 'search_error'):
        _, result, _ = by_kind[kind]
        c.need(len(result['actual_failure_branch_evidence']) == 2
            and len({r['path'] for r in result['actual_failure_branch_evidence']}) == 2 and result['back_inputs'] == 0
            and result['implicit_browser_tasks'] == [], 'BOTH_ORIGINAL_FAILURE_BRANCH_LIFECYCLES')
        recovered = []
        for index, ref in enumerate(result['actual_failure_branch_evidence']):
            item = c.parse(c.read_ref(ref)); branch = c.parse(c.read_ref(item['actual_branch']))
            c.need(branch['branch']['branch'] == kind.removeprefix('search_')
                and branch['branch']['actual_app_log_rows'] and branch['query_request_correlation'] is False
                and branch['current_query_backend_response_verified'] is False
                and item['query_request_correlation'] is False and item['current_query_backend_response_verified'] is False
                and item['two_new_native_edits_after_observed_branch'] is True,
                'ORIGINAL_UID_BRANCH_SCOPE_WITHOUT_INVENTED_QUERY_CAUSALITY')
            _, branch_nodes = observation(c, branch['actual_ui'], package, result['recorder_scopes'][index],
                result['actual_business_phase'])
            _, cleared = observation(c, item['new_clear_readback'], package, result['recorder_scopes'][index],
                result['actual_business_phase'])
            _, unicode_nodes = observation(c, item['new_unicode_readback'], package, result['recorder_scopes'][index],
                result['actual_business_phase'])
            c.need(query_field(c, cleared, package) == '' and query_field(c, unicode_nodes, package) == item['unicode_query']
                and item['unicode_query'] in profiles.QUERIES and item['same_owned_task'] == result['native_tasks'][index]
                and query_field(c, branch_nodes, package) == branch['visible_query_at_observation'],
                'NEW_USABLE_UNICODE_EDIT_AFTER_ACTUAL_APP_FAILURE')
            refs.extend([ref, item['actual_branch'], branch['actual_ui'], item['new_clear_readback'], item['new_unicode_readback']]); recovered.append(ref)
        failures[kind] = recovered
    witness = c.EvidenceWitness(refs)
    try:
        before = baseline.guard(); witness.verify()
        root = Path(output)
        c.need(root.parent == c.FINAL / 'qualification' and re.fullmatch('business-search-profile-[0-9a-f]{32}', root.name),
            'CREATE_ONLY_SEARCH_PROFILE_QUALIFICATION_PATH')
        root = c.private_dir(root, create=True)
        value = {'schema': 'pocket4-quicksearch-three-branch-business-qualification-v1',
            'state': 'THREE_ORIGINAL_SEARCH_BUSINESS_CHECKS_VERIFIED_COMMON_GATES_SEPARATE',
            'source_preparation': preparation_ref, 'cases': request['cases'], 'baseline': baseline.baseline_ref,
            'qualification': baseline.qualification_ref, 'framework_epoch_sha256': baseline.value['framework_epoch']['sha256'],
            'original_gates': c.GATES, 'original_business_checks': profiles.GATES,
            'checks': {k: True for k in profiles.GATES}, 'query_request_correlation_for_failure_logs': False,
            'failure_scope': 'Actual app UID branches followed by new acknowledged Unicode/empty UI recovery and lifecycle',
            'failure_recovery_evidence': failures, 'actual_Main_before': before, 'actual_Main_after': baseline.guard(),
            'six_common_app_gates_qualified_by_this_composition': False, 'whole_app_business_accepted': False,
            'original45_accepted': 0, 'new_Android_UI_actions': 0, 'automatic_retry': False}
        witness.verify()
        return c.write_new(root / 'result.json', value)
    finally:
        witness.close()
