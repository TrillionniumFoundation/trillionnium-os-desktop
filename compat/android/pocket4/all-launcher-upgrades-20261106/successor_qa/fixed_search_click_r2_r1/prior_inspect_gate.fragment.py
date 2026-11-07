def completed_inspect_header(base, partial, raw, terminal):
    need(INSPECT_INPUTS_BOUND is True, 'ACTUAL_COMPLETED_R2_INSPECT_NOT_YET_BOUND')
    partial.original_terminal(terminal, INSPECT_JOB, len(raw))
    outer = partial.document(raw)
    need(outer.get('schema') == 'pocket4-fixed-r2-readonly-inspect-result-v1' and
         outer.get('ok') is True and outer.get('errors') == [] and
         outer.get('source') == INSPECT_OWNER and outer.get('request') == INSPECT_REQUEST and
         outer.get('flow') == FLOW and outer.get('task') == TASK and outer.get('kind') == 'plan' and
         outer.get('step') == 'r2-readonly-inspect-01' and outer.get('helper_uid') == HELPER_UID and
         outer.get('current_explicit_scope') == CURRENT_SCOPE and outer.get('original_result') == INSPECT_RESULT and
         outer.get('joint_artifact') == INSPECT_JOINT and
         all(outer.get(k) is True for k in ('all49_guard_before_after_equal',
             'all_owned_child_resources_retired_by_normal_pidfd_exit',
             'acceptance_requires_original_stdout_and_authoritative_durable_terminal')) and
         all(outer.get(k) is False for k in ('original_action_attempted', 'original_action_outcome_unknown',
             'outcome_unknown', 'original_UNKNOWN_rewritten', 'reconciliation_published', 'production_ready',
             'automatic_retry', 'full_PM_or_launcher_inventory_claimed',
             'allows_new_mutation_without_original_Flow_checks')),
         'EXACT_ACTUAL_READONLY_INSPECT_COMPLETE_AND_DURABLE')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    stderr = outer['child_stderr_original'].encode('utf-8')
    need(outer['child_stdout_bytes'] == len(child_raw) and outer['child_stdout_sha256'] == sha(child_raw) and
         outer['child_stderr_bytes'] == len(stderr) == 0 and outer['child_stderr_sha256'] == sha(stderr),
         'ACTUAL_PRIOR_INSPECT_CHILD_STREAMS')
    base.require_owned_exit(outer['child_lifecycle'], stderr)
    child = partial.document(child_raw)
    need(child.get('schema') == 'pocket4-fixed-r2-readonly-inspect-child-v1' and child.get('ok') is True and
         child.get('errors') == [] and child.get('source') == INSPECT_OWNER and child.get('request') == INSPECT_REQUEST and
         child.get('flow') == FLOW and child.get('task') == TASK and child.get('kind') == 'plan' and
         child.get('step') == outer['step'] and child.get('helper_uid') == HELPER_UID and
         child.get('current_explicit_scope') == CURRENT_SCOPE and child.get('original_result') == INSPECT_RESULT and
         child.get('original_entry_invoked') is True and child.get('original_returncode') == 0 and
         child.get('declared_mutation') is False and child.get('original_action_attempted') is False and
         child.get('original_action_outcome_unknown') is False and child.get('outcome_unknown') is False and
         child.get('whole_scope_before') == child.get('whole_scope_after') and
         child.get('completed_install') == outer.get('completed_install') and
         child.get('original_namespace_authority_released') is True and
         child.get('normal_process_exit_required_for_lock_and_library') is True and
         child.get('unknown_descriptors_closed') == 0 and child.get('manual_library_close') is False and
         child.get('original_private_UI_nodes_exported') is False,
         'ACTUAL_PRIOR_READONLY_CHILD_AND_NORMAL_RETIREMENT')
    original_raw = child['original_stdout'].encode('utf-8')
    need(child['original_stdout_bytes'] == len(original_raw) and child['original_stdout_sha256'] == sha(original_raw),
         'ACTUAL_PRIOR_ORIGINAL_ADAPTER_BYTES')
    return outer, child, original_raw


def prior_inspect_gate(base, core):
    """Read completed observer evidence; do not reuse its nodes for dispatch."""
    need(INSPECT_INPUTS_BOUND is True, 'ACTUAL_COMPLETED_R2_INSPECT_NOT_YET_BOUND')
    previous = base.load(INSPECT_OWNER, 'completed_readonly_inspect_definitions_only')
    install_owner = base.load(INSTALL_OWNER, 'completed_install_terminal_parser_reference_only')
    partial = base.load(install_owner.NO_ACTION_CORE, 'unchanged_original_terminal_parser_only')
    outer, child, original_raw = completed_inspect_header(base, partial, base.pinned(INSPECT_STDOUT),
        partial.document(base.pinned(INSPECT_TERMINAL)))
    joint = dict(outer); joint.pop('joint_artifact')
    need(base.pinned(INSPECT_JOINT) == canonical(joint) + b'\n',
         'ACTUAL_PRIOR_INSPECT_PUBLISHED_JOINT_EQUALS_FULL_STDOUT')
    request, body, payload = previous.outer_request(base.pinned(INSPECT_REQUEST), core)
    scope, selected = previous.launch_gate(base, core)
    original, original_pin = previous.verify_original(base, core, request, payload, False, original_raw, scope, selected)
    need(original_pin == INSPECT_RESULT and original['inspection_wire_sha256'] == INSPECT_WIRE_SHA and
         original['installed_before'] == INSTALLED_HELPER and original['installed_after'] == INSTALLED_HELPER,
         'ACTUAL_COMPLETED_R2_INSPECT_AND_SAME_INSTALLED_HELPER')
    return {'job_id': INSPECT_JOB, 'source': INSPECT_OWNER, 'request': INSPECT_REQUEST,
            'stdout': INSPECT_STDOUT, 'terminal': INSPECT_TERMINAL, 'joint': INSPECT_JOINT,
            'original_result': INSPECT_RESULT, 'inspection_wire_sha256': INSPECT_WIRE_SHA,
            'actual_helper_uid': HELPER_UID, 'actual_scope49': CURRENT_SCOPE,
            'previous_nodes_reused_for_action': False, 'search_page_navigation_proved': False,
            'current_button_presence_prejudged': False,
            'dispatch_still_requires_new_original_inspection_and_fixed_full_tree_transaction': True,
            'prior_observer_execution_entry_called': False}
