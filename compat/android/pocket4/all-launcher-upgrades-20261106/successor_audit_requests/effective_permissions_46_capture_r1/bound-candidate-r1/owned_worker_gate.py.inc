def worker_gate(value, returned):
    need(CONFIG["kind"] == "services" and type(returned) is int and returned == 0 and
         value.get("errors") == [] and value.get("automatic_retry") is False and
         value.get("production_ready") is False and
         type(value.get("process_FDs_before")) is int and
         value["process_FDs_before"] == value.get("process_FDs_after"), "ORIGINAL_WORKER_DID_NOT_PASS")
    need(value.get("guard_before") == CAPTURE_BINDING["guard"] == value.get("guard_after") and
         retired(value.get("owned_descriptors_final")) and
         value.get("owned_descriptors_final") == value.get("observation_FDs_final"),
         "ORIGINAL_RUNTIME_OR_FD_GATE_FAILED")
    need(value.get("schema") == "pocket4-fixed46-launcher-permission-raw-capture-v1" and
         value.get("ok") is True and value.get("status") == "FIXED_LAUNCHER_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE" and
         value.get("current_scope_49_unchanged") is True and value.get("packages") == CAPTURE_BINDING["packages"] and
         value.get("app_scope_reference") == CAPTURE_BINDING["app_scope"] and
         type(value.get("batch")) is int and value["batch"] == CAPTURE_BINDING["batch"] and
         value.get("target_packages") == value.get("service_target_packages") == CAPTURE_BINDING["targets"] and
         type(value.get("target_user")) is int and value["target_user"] == 0 and
         value.get("target_identities_from_pinned_scope") == CAPTURE_BINDING["identities"] and
         value.get("service_output_capture_complete") is True and
         value.get("PM_user0_installed_APK_packages_enumerated") is False and
         value.get("MAIN_LAUNCHER_resolver_queried") is False and
         type(value.get("Android_namespace_commands")) is int and
         value["Android_namespace_commands"] == CAPTURE_BINDING["command_count"] and
         type(value.get("native_command_count")) is int and value["native_command_count"] == 3 and
         len(value.get("android_commands", [])) == CAPTURE_BINDING["command_count"] and
         len(value.get("native_commands", [])) == 3 and
         all(type(row.get("returncode")) is int and row["returncode"] == 0 and
             all(row.get(k) is True for k in ("complete", "joined", "stdout_eof", "stderr_eof", "stream_artifacts_complete")) and
             row.get("termination_attempted") is False and row.get("errors") == [] for row in value["android_commands"]) and
         value.get("held_namespace_target_closed") is True and value.get("action_lock_released") is True and
         retired(value.get("lease_FDs_final")), "RAW_PERMISSION_SERVICE_CAPTURE_AND_RETIREMENT_GATE_FAILED")
    scope = value.get("scope_guard_before", {})
    need(scope == value.get("scope_guard_after") and scope.get("schema") == "pocket4-app-scope-guard-v1" and
         scope.get("app_scope_sha256") == CAPTURE_BINDING["app_scope"]["sha256"] and
         scope.get("packages") == CAPTURE_BINDING["packages"] and
         scope.get("runtime_epoch_sha256") == CAPTURE_BINDING["guard"]["runtime_epoch_sha256"] and
         scope.get("current_apk_paths_and_file_identities_match") is True and
         scope.get("new_signature_verification_performed") is False and
         scope.get("UI_or_install_runtime_admitted") is False, "EXACT_CURRENT49_SCOPE_GUARDS_REQUIRED")
    need(value.get("permission_queries_executed") is True and value.get("service_output_semantics_verified") is False and
         value.get("effective_permission_grants") == "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION" and
         value.get("effective_AppOps_modes") == "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION" and
         value.get("role_status") == "UNKNOWN_NOT_QUERIED" and value.get("package_dump_user_filter_applied") is False and
         value.get("permission_name_normalization") == "NONE_RAW_BYTES_PRESERVED" and
         set(value.get("help_results", {})) == {"package"} and
         len(value.get("service_reports", [])) == 2 * len(CAPTURE_BINDING["targets"]) and
         all(row.get("interpretation_status") == "RAW_CAPTURE_ONLY_NOT_INTERPRETED" for row in value["service_reports"]) and
         value.get("native_catalog_matches_actual46_component_reference") is True and
         value.get("native_catalog_comparison") == CAPTURE_BINDING["native_comparison"] and
         value.get("compiled_Beike_scope_modified") is False and value.get("old_Bili_unknown_reclassified") is False and
         value.get("meituan_saved_location_unchanged") is True and value.get("all_installed_APK_bytes_bound") is False,
         "READONLY_QUERY_MUST_NOT_CLAIM_GRANTS_OR_EXPAND_UI_AUTHORITY")
    policy = CAPTURE_BINDING["microg_capture_policy"]
    if policy is None:
        need("capture_policy" not in value and all("capture_limits" not in row for row in value["android_commands"]),
             "DEFAULT_LIMITS_CANNOT_GAIN_AN_EXCEPTION")
    else:
        need(CAPTURE_BINDING["batch"] == 2 and CAPTURE_BINDING["targets"] == ["com.google.android.gms"] and
             value.get("capture_policy") == policy and
             [row.get("capture_limits") for row in value["android_commands"]] == policy["stream_limits"],
             "ONLY_EXACT_MICROG_SECOND_STDOUT_HAS_2MIB_BUDGET")
    actions = ("UI_actions", "App_launches", "installs", "permission_changes", "lifecycle_commands", "ADB_commands", "business_data_content_reads")
    need(all(type(value.get(key)) is int and value[key] == 0 for key in actions), "READ_ONLY_ACTION_BOUNDARY_CHANGED")
