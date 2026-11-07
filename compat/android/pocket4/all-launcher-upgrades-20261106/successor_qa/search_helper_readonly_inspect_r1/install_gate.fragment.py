def completed_install_header(base, partial, raw, terminal):
    partial.original_terminal(terminal, INSTALL_JOB, len(raw))
    outer = partial.document(raw)
    need(outer.get('schema') == 'pocket4-owned-search-helper-coexist-result-v1' and
         outer.get('ok') is True and outer.get('errors') == [] and outer.get('source') == INSTALL_OWNER and
         outer.get('request') == INSTALL_REQUEST and outer.get('flow') == FLOW and outer.get('package') == HELPER_PACKAGE and
         outer.get('helper_uid') == HELPER_UID and outer.get('next_app_scope') == CURRENT_SCOPE and
         outer.get('original_result') == INSTALL_RESULT and outer.get('joint_artifact') == INSTALL_JOINT and
         outer.get('step') == 'install-search-helper-r2-01' and
         outer.get('observed_explicit_packages') == 49 and outer.get('observed_APKs') == 89 and
         all(outer.get(k) is True for k in ('all_original48_unchanged', 'normal_PM_install_success_observed',
             'state_without_UiAutomation_verified', 'original_action_attempted',
             'all_owned_child_resources_retired_by_normal_pidfd_exit', 'parent_whole_process_FD_identity_restored',
             'current_scope_adoption_requires_this_actual_durable_terminal',
             'later_QA_permissions_and_framework_must_rebind_actual_new_scope')) and
         all(outer.get(k) is False for k in ('original_action_outcome_unknown', 'outcome_unknown',
             'original_FAILED_UNKNOWN_rewritten', 'reconciliation_published', 'old_helper_uninstalled',
             'old_products_deleted', 'production_ready', 'automatic_retry', 'full_PM_or_launcher_inventory_claimed')) and
         all(type(outer.get(k)) is int and outer[k] == 0 for k in ('UI_actions', 'permission_grants', 'target_App_launches')),
         'ACTUAL_COMPLETED_NORMAL_R2_INSTALL_AND_ALL49_SCOPE')
    child_raw = outer['child_stdout_original'].encode('utf-8')
    stderr = outer['child_stderr_original'].encode('utf-8')
    need(outer.get('child_stdout_bytes') == len(child_raw) and outer.get('child_stdout_sha256') == sha(child_raw) and
         outer.get('child_stderr_bytes') == len(stderr) == 0 and outer.get('child_stderr_sha256') == sha(stderr),
         'EXACT_INSTALL_CHILD_STREAMS')
    base.require_owned_exit(outer['child_lifecycle'], stderr)
    child = partial.document(child_raw)
    need(child.get('schema') == 'pocket4-owned-search-helper-coexist-child-v1' and child.get('ok') is True and
         child.get('errors') == [] and child.get('source') == INSTALL_OWNER and child.get('request') == INSTALL_REQUEST and
         child.get('flow') == FLOW and child.get('step') == outer['step'] and
         child.get('original_entry_invoked') is True and child.get('original_returncode') == 0 and
         child.get('original_action_attempted') is True and child.get('original_action_outcome_unknown') is False and
         child.get('outcome_unknown') is False and child.get('original_namespace_authority_released') is True and
         child.get('normal_process_exit_required_for_lock_and_library') is True and
         child.get('unknown_descriptors_closed') == 0 and child.get('manual_library_close') is False and
         child.get('original_private_UI_nodes_exported') is False and
         child.get('original_result') == outer['original_result'] and child.get('helper_uid') == HELPER_UID and
         child.get('next_app_scope') == CURRENT_SCOPE and child.get('completed_build') == outer['completed_build'] and
         child.get('completed_no_action_B') == outer['completed_no_action_B'],
         'SAME_COMPLETED_INSTALL_CHILD_PARENT_AND_NORMAL_EXIT')
    original_raw = child['original_stdout'].encode('utf-8')
    need(len(original_raw) == child['original_stdout_bytes'] and sha(original_raw) == child['original_stdout_sha256'],
         'COMPLETE_ORIGINAL_INSTALLER_STREAM')
    return outer, child, original_raw


def completed_install_gate(base, core):
    """Read only actual install/build/B evidence, never invoke those owners."""
    owner = base.load(INSTALL_OWNER, 'completed_install_readonly_definitions')
    partial = base.load(owner.NO_ACTION_CORE, 'unchanged_completed_terminal_predicate')
    outer, child, original_raw = completed_install_header(base, partial, base.pinned(INSTALL_STDOUT),
        partial.document(base.pinned(INSTALL_TERMINAL)))
    joint = dict(outer); joint.pop('joint_artifact')
    need(base.pinned(INSTALL_JOINT) == canonical(joint) + b'\n', 'ACTUAL_PUBLISHED_INSTALL_JOINT_EQUALS_ORIGINAL_STDOUT')
    request = owner.request_value(base.pinned(INSTALL_REQUEST), core)
    build = owner.completed_build_gate(base)
    no_action = owner.completed_b_gate(base)
    need(build == outer['completed_build'] and no_action == outer['completed_no_action_B'],
         'COMPLETED_BUILD_AND_NO_ACTION_B_UNCHANGED')
    original, result_pin = owner.verify_install(base, core, request, build['qualified_build'], original_raw)
    need(result_pin == INSTALL_RESULT and original['helper_uid'] == HELPER_UID and
         original['next_app_scope'] == CURRENT_SCOPE and original['installed_after_state'] == INSTALLED_HELPER and
         child['whole_scope_transition'] == original['whole_scope_after']['transition'],
         'ACTUAL_INSTALLED_R2_UID_APK_CERT_CEDE_AND_ORIGINAL_SCOPE_VALIDATOR')
    return {'job_id': INSTALL_JOB, 'source': INSTALL_OWNER, 'request': INSTALL_REQUEST,
            'stdout': INSTALL_STDOUT, 'terminal': INSTALL_TERMINAL, 'joint': INSTALL_JOINT,
            'original_result': INSTALL_RESULT, 'helper_uid': HELPER_UID, 'installed_helper': INSTALLED_HELPER,
            'actual_scope49': CURRENT_SCOPE, 'normal_PM_and_no_automation_state_verified': True,
            'actual_build_and_completed_B_rechecked_readonly': True,
            'install_or_B_execution_entries_called': False, 'production_ready': False}


def validate_scope49(value):
    need(type(value) is dict and value.get('schema') == 'pocket4-versioned-app-scope-v1' and
         value.get('kind') == 'explicit-current-app-observation' and
         value.get('runtime_epoch_sha256') == RUNTIME_EPOCH and type(value.get('apps')) is dict and
         sorted(value['apps']) == ALL_PACKAGES and len(value['apps']) == 49 and
         sum(len(row['apks']) for row in value['apps'].values()) == 89 and
         value['apps'][HELPER_PACKAGE] == INSTALLED_HELPER_SCOPE_ROW and
         value.get('fresh_signature_verification_performed') is False and
         value.get('UI_or_install_runtime_admitted') is False and
         value.get('external_evidence_policy_validated_by_this_reader') is False,
         'EXACT_ACTUAL_EXPLICIT49_NOT_SUBSET_OR_SELF_PROMOTED')
    return value


def whole_scope_guard(base, core):
    validate_scope49(core.document(base.pinned(CURRENT_SCOPE)))
    guard = base.load(CURRENT_GUARD, 'unchanged_typed_current_Main_guard')
    typed = guard.current_guard(action_attempted=False)
    need(typed.get('schema') == 'pocket4-successor-main-guard-v1' and
         typed.get('runtime_epoch_sha256') == RUNTIME_EPOCH, 'SAME_ACTUAL_CURRENT_TYPED_RUNTIME')
    current = guard.check_app_scope(CURRENT_SCOPE, ALL_PACKAGES)
    need(current.get('schema') == 'pocket4-app-scope-guard-v1' and
         current.get('runtime_epoch_sha256') == RUNTIME_EPOCH and current.get('packages') == ALL_PACKAGES and
         current.get('app_scope_sha256') == CURRENT_SCOPE['sha256'] and
         current.get('current_apk_paths_and_file_identities_match') is True and
         current.get('new_signature_verification_performed') is False and
         current.get('UI_or_install_runtime_admitted') is False, 'ALL49_FRESH_FILE_AND_UID_IDENTITIES')
    return {'typed_runtime': typed, 'current_apps': current, 'scope_pin': CURRENT_SCOPE,
            'complete_PM_or_launcher_enumeration_claimed': False}
