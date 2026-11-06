def read_raw(name, expected_sha=None):
    raw = (PROJECT / name).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None:
        assert digest == expected_sha, name
    INPUTS[name] = {"path": name, "bytes": len(raw), "sha256": digest}
    return raw


def durable_success(value, job_id, stdout_bytes):
    assert value["job_id"] == job_id and value["state"] == "succeeded"
    assert type(value["exit_code"]) is int and value["exit_code"] == 0
    assert all(value[k] is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed"))
    assert all(value[k] is False for k in ("automatic_retry", "cancelled", "timed_out"))
    assert value["log_bytes"] == {"stdout": {"seen": stdout_bytes, "stored": stdout_bytes}, "stderr": {"seen": 0, "stored": 0}}
    assert all(value["log_errors"][s] is None and value["log_truncated"][s] is False and value["log_synced"][s] is True
               for s in ("stdout", "stderr"))


def current_permission_declarations(identity, observations, source, evidence_kind):
    counts = {}
    per_apk = []
    for installed, observed in zip(identity["apks"], observations):
        assert installed["sha256"] == observed["sha256"] and installed["bytes"] == observed["bytes"]
        permissions = observed["declared_permissions"]
        assert permissions["all_names_decoded"] is True
        for entry in permissions["entries"]:
            counts[entry["tag"]] = counts.get(entry["tag"], 0) + 1
        per_apk.append({"APK_path": installed["path"], "APK_sha256": installed["sha256"],
            "observed_APK_path": observed["path"], "evidence_kind": evidence_kind,
            "source": source, "all_names_decoded": True, "entries": permissions["entries"]})
    assert len(per_apk) == len(identity["apks"]) == len(observations)
    return {"per_APK": per_apk, "counts_by_tag": counts,
            "count_is_not_unique_PM_requested_or_effective_permissions": True, "grant_inference_permitted": False,
            "static_declarations_bound_to_exact_current_APK_bytes": True, "source": source}


def apply_current_observations(rows, audits, discovery, membership_joint):
    prefix = "successor_install/source-r4-zbj-full48/candidate-r1/"
    post_path = prefix + "post_install_scope_readback_r1/actual/app-scope-after.private.json"
    scope = read(post_path, "9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a")
    assert INPUTS[post_path]["bytes"] == 59259
    before_path = "successor_audit_requests/explicit48_scope_r1/actual-readback/app-scope.private.json"
    before = read(before_path, "b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4")
    install_path = prefix + "actual-install/stdout.original.jsonl"
    install_raw = read_raw(install_path, "23998b1f6ccd501379f207e0e6534ecaf2a88ede7cdb21702a4bbdbb357fc3d2")
    records = [json.loads(line) for line in install_raw.splitlines()]
    assert len(records) == 2
    stage, install = records
    assert stage["bootstrap_Main_actions"] == 0 and stage["bootstrap_FDs_before"] == stage["bootstrap_FDs_after"]
    terminal_path = prefix + "actual-install/status-01.original.json"
    terminal = read(terminal_path, "dedccba067c70ef35d8bb51de41b98c2d0f8d8f66b3e46157c34c345e1526cf1")
    durable_success(terminal, "1a1b32567fe-fc05-80c6", len(install_raw))
    install_joint_path = prefix + "actual-install/root-validation.actual.json"
    install_joint = read(install_joint_path, "78bdda6caf7fbadaf2d26a0201c89776c69192054c11523787b0b46018f56a82")
    assert install_joint["status"] == "PASS_INSTALLED_SAME_VENDOR_BYTES_QA_PENDING"
    scope_joint_path = prefix + "post_install_scope_readback_r1/actual/root-validation.actual.json"
    scope_joint = read(scope_joint_path, "ff656c7ccf09e9e6569850c0340ac499e8bea5b810ae0a491131ca20cc0dccd4")
    assert scope_joint["status"] == "PASS_FULL_ORIGINAL_SCOPE_READBACK" and scope_joint["reconstructed"] is False
    assert scope_joint["new_global_resolver_query"] is False
    scope_terminal = read(prefix + "post_install_scope_readback_r1/actual/terminal.original.json",
                          "d291ad13e88dd37cb92d8c9ce1ec84dd7c091c89f6e827e9187e0ddd918d62a1")
    durable_success(scope_terminal, "1a1b328a3ae-fc05-80d9", scope_joint["stdout"]["bytes"])
    assert scope_joint["scope"] == install["next_app_scope"]
    assert scope["schema"] == before["schema"] == "pocket4-versioned-app-scope-v1"
    assert scope["runtime_epoch_sha256"] == before["runtime_epoch_sha256"]
    assert scope["parent_app_scope"] == {k: v for k, v in {
        "path": "/home/alex/work/pocket4-current-explicit-48-app-observation-20261106-r1/app-scope.private.json",
        "bytes": 59957, "sha256": INPUTS[before_path]["sha256"]}.items()}
    assert scope["install_scope"] == install["scope"]
    assert set(scope["apps"]) == set(before["apps"]) and len(scope["apps"]) == 48
    zbj = "com.zhubajie.client"
    assert scope["apps"][zbj] == install["after"] == install_joint["after"]
    assert before["apps"][zbj] == install["before"] == install_joint["before"]
    assert all(scope["apps"][package] == row for package, row in before["apps"].items() if package != zbj)
    assert len([package for package in scope["apps"] if package != zbj]) == 47
    assert install["install_verified"] and install["action_attempted"] and not install["outcome_unknown"] and install["errors"] == []
    assert install["guard_before"] == install["guard_after"]
    assert install["status"] == "INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING"
    assert all(install[k] is True for k in ("data_directory_identity_retained", "non_target_packages_unchanged",
        "new_installed_bytes_readback_verified", "native_artifacts_unchanged", "old_unknown_evidence_preserved"))
    assert install["meituan_location_before"] == install["meituan_location_after"]
    for key in ("observation_fds", "lease_fds"):
        assert install[key]["acquired"] == install[key]["closed"] and install[key]["remaining"] == 0 and install[key]["errors"] == []
    assert len(install["commands"]) == 4 and all(command["returncode"] == 0 and command["joined"]
        and command["output_capture_complete"] and not command.get("timed_out") and not command.get("error")
        for command in install["commands"])

    s43_path = "official_source_scripts/s43_zbj_operator_verification/actual/stdout.original.json"
    s43 = read(s43_path, "96c6931181555e575bffa3e626d704b93254298441095f318691d9d3ab70cb11")
    s43_terminal = read("official_source_scripts/s43_zbj_operator_verification/actual/terminal.original.json",
                       "c42a9fd1a5bbf4f6d6ac7e335e0f3d0545379ce754c54fd9f6c99f0ba96e9076")
    durable_success(s43_terminal, "1a1b2c8fc38-fc05-7fc4", INPUTS[s43_path]["bytes"])
    assert s43["ok"] and s43["errors"] == [] and s43["candidate_signature_verified"]
    assert s43["candidate_manifest_verified"] and s43["candidate_permission_dump_verified"]
    assert s43["all_raw_command_observations_complete"] and s43["original_descriptor_identities_restored"]
    candidate_manifest = s43["candidate_manifest_observation"]
    signature = s43["candidate_signature_observation"]
    assert candidate_manifest["version_code"] == 370 and candidate_manifest["version_name"] == "9.5.20"
    assert signature["verified"] and not signature["API_minimum_override_used"] and not signature["integrity_check_bypassed"]
    current = scope["apps"][zbj]
    assert current["uid"] == 10144 and current["version_code"] == 370
    assert current["data_directories"] == before["apps"][zbj]["data_directories"]
    assert current["package_manager_certificate_sha256"] == signature["signer_certificate_sha256"]
    assert len(current["apks"]) == 1 and all(current["apks"][0][k] == s43["candidate"][k] for k in ("bytes", "sha256"))

    ndk_path = "successor_audit_requests/ndk_signature_metadata_r1/actual/artifact.original.json"
    ndk = read(ndk_path, "c6fec2589cf3df6dfdd65c88d14d39c041c1a2449d707618fe4c7f5d6a9639c3")
    ndk_joint_path = "successor_audit_requests/ndk_signature_metadata_r1/actual/root-validation.actual.json"
    ndk_joint = read(ndk_joint_path, "24ee44259c543a51aa61c053bbcac31c5e53904d738c93f25436735b7b4e486f")
    assert ndk_joint["status"] == "PASS_NORMAL_SIGNATURE_AND_METADATA_ONLY" and ndk_joint["source_origin_still_unknown"]
    assert ndk["ndk_audit_complete"] and ndk["errors"] == [] and ndk["all_manifests_and_signatures_verified"]
    assert ndk["all_primary_commands_succeeded"] and ndk["all_tool_children_joined"] and len(ndk["commands"]) == 3
    assert len(ndk["apps"]) == 1 and ndk["apps"][0]["package"] == "com.example.ndk_tests"
    n = ndk["apps"][0]
    assert n == ndk_joint["app"] and all(n[k] for k in ("all_APKs_signature_verified", "all_current_signers_equal_PM_records",
        "all_manifests_match_PM_identity", "all_permission_names_decoded", "complete_APK_set_observed"))
    ni = scope["apps"][n["package"]]
    assert n["uid"] == ni["uid"] and n["PM_version_code"] == ni["version_code"] == 0
    assert n["PM_certificate_sha256"] == ni["package_manager_certificate_sha256"] and n["data_directories"] == ni["data_directories"]
    assert n["code_path"] == ni["code_path"] and len(n["apks"]) == len(ni["apks"]) == 1
    assert all(n["apks"][0][k] == ni["apks"][0][k] for k in ("path", "bytes", "sha256", "file"))
    nm = n["base_manifest"]
    assert nm["version_code"] is None and nm["version_name"] is None and nm["long_version_code"] == 0
    assert nm["version_code_raw"] == nm["version_name_raw"] == ""
    assert nm["xml_root_observation"]["all_three_version_attributes_absent"] is True

    comparison_path = "successor_qa/search_click_tree_analysis_r1/CURRENT_PREINSPECTION_COMPARISON.derived.json"
    comparison = read(comparison_path, "f48077c3f0983a5b5ed3f8b342041f7d99326867d251fd44e1886bbac3408231")
    assert comparison["specific_failed_action_root_cause_proven"] is False
    assert comparison["original_outer_UNKNOWN_reclassified"] is False
    comparison_public = {key: comparison[key] for key in ("schema", "comparisons", "current_node_count", "current_visible_nodes",
        "helper_reported_action_attempted", "helper_reported_outcome_unknown", "guard_changes",
        "cross_connection_hash_includes_connection_id", "original_outer_UNKNOWN_reclassified",
        "rejected_current_tree_exported", "rejected_current_tree_or_window_specific_difference", "specific_failed_action_root_cause_proven")}

    for row in rows:
        package = row["package"]
        identity = scope["apps"][package]
        row["PM_at_membership_observation"] = row["PM"]
        row["PM"] = {"package": package, "uids": [identity["uid"]], "version_code": identity["version_code"],
                     "source": post_path, "observation_kind": "BOUND_CURRENT_PACKAGES_RECORD_AND_APK_IDENTITY"}
        row["current_installed_identity"] = identity
        row["current_identity_scope_source"] = post_path
        row["effective_version_code"] = identity["version_code"]
        row["membership_source"] = "successor_audit_requests/native46_discovery_r1/actual/artifact.original.json"
        row["membership_requeried_after_latest_install"] = False
        if package not in (zbj, n["package"]):
            audit = audits[package]
            assert audit["uid"] == identity["uid"] and audit["PM_version_code"] == identity["version_code"]
            assert audit["PM_certificate_sha256"] == identity["package_manager_certificate_sha256"]
            assert sorted(audit["APK_sha256"]) == sorted(part["sha256"] for part in identity["apks"])
            assert audit["APK_count"] == len(identity["apks"])
            assert sorted(part["APK_sha256"] for part in row["manifest_permissions"]["per_APK"]) == sorted(audit["APK_sha256"])
            row["APK_audit"]["prior_normal_audit_bytes_match_current_scope"] = True
            row["APK_audit"]["fresh_tool_execution_by_this_generator"] = False
        if row["effective_permissions"]["state"] == "LITERAL_SERVICE_SNAPSHOT_INTERPRETED":
            row["effective_permissions"]["not_recaptured_after_ZBJ_upgrade"] = True
            row["effective_permissions"]["snapshot_is_not_current_global_grant_or_functional_acceptance"] = True
        if package == "com.lianjia.beike":
            row["latest_public_tree_comparison"] = {"source": comparison_path, "details": comparison_public,
                "helper_integrity_check_bypassed": False, "search_business_success_proved": False}
        if package == zbj:
            row["historical_before_latest_upgrade"] = {"APK_audit": row["APK_audit"], "manifest_permissions": row["manifest_permissions"],
                "official_source": row["official_source"], "version_name": row["version_name"], "declared_version_code": row["declared_version_code"]}
            row["version_name"], row["declared_version_code"] = candidate_manifest["version_name"], candidate_manifest["version_code"]
            row["version_name_evidence"] = "S43_NORMAL_VERIFIED_CANDIDATE_IDENTICAL_TO_ACTUAL_INSTALLED_BYTES"
            row["APK_audit"] = {"state": "S43_NORMAL_SIGNATURE_MANIFEST_AND_DECLARATIONS_LINKED_TO_INSTALLED_BYTES",
                "source": s43_path, "install_source": install_path, "scope_source": post_path,
                "fresh_apksigner_on_installed_path_claimed": False,
                "details": {"package": package, "APK_count": 1, "APK_sha256": [current["apks"][0]["sha256"]],
                    "PM_version_code": 370, "uid": current["uid"], "PM_certificate_sha256": signature["signer_certificate_sha256"],
                    "declared_version_code": 370, "declared_version_name": "9.5.20", "manifest": candidate_manifest,
                    "signature": signature, "same_byte_candidate_verified": True, "actual_installed_bytes_verified": True}}
            candidate_observation = {"path": s43["candidate"]["path"], "bytes": s43["candidate"]["bytes"],
                "sha256": s43["candidate"]["sha256"], "declared_permissions": s43["candidate_declared_permissions_observation"]}
            row["manifest_permissions"] = current_permission_declarations(identity, [candidate_observation], s43_path,
                "COMPLETE_CANDIDATE_NORMAL_AAPT_PERMISSION_DUMP_LINKED_BY_EXACT_INSTALLED_BYTES")
            row["official_source"] = {"state": "PUBLIC_COMPLETE_S43_CANDIDATE_SAME_VENDOR_SIGNED_AND_INSTALLED",
                "source": s43_path, "download_reference": s43["download_reference"],
                "version_latest_business_usable_qualified": False}
            row["upgrade"] = {"state": "INSTALLED_AND_CURRENT_BYTES_REOBSERVED_BUSINESS_QA_PENDING",
                "job_id": terminal["job_id"], "before_version_code": 369, "after_version_code": 370,
                "started_utc": install["started_utc"], "ended_utc": install["ended_utc"],
                "evidence": {"stdout": INPUTS[install_path], "terminal": INPUTS[terminal_path],
                    "root_install_joint": INPUTS[install_joint_path], "scope_readback_joint": INPUTS[scope_joint_path]},
                "after_APKs_equal_latest_bound_scope": True, "uid_retained": True, "same_installed_signer_retained": True,
                "data_directory_identity_retained_within_install": True,
                "previous_APKs_retained": install["previous_apks_retained"], "previous_APK_count_retained": 1,
                "previous_APK_bytes_retained": install["previous_complete_APK_set_bytes"],
                "latest_usable_version_qualified": False, "business_QA_qualified": False,
                "normal_install_result": install["status"], "outcome_unknown": False}
        elif package == n["package"]:
            row["version_name"], row["declared_version_code"] = None, None
            row["version_name_evidence"] = "ACTUAL_SIGNED_APK_XML_VERSION_ATTRIBUTES_ABSENT"
            row["raw_version_fields"] = {"versionCode": "", "versionName": ""}
            row["effective_version_code_evidence"] = nm["version_default_evidence"]
            row["APK_audit"] = {"state": "NORMAL_SIGNATURE_AND_MANIFEST_VERIFIED_SOURCE_ORIGIN_UNKNOWN",
                "source": ndk_path, "root_joint_source": ndk_joint_path, "details": {
                    "package": package, "APK_count": 1, "APK_sha256": [n["apks"][0]["sha256"]],
                    "uid": n["uid"], "PM_version_code": 0, "declared_version_code": None, "declared_version_name": None,
                    "PM_certificate_sha256": n["PM_certificate_sha256"], "manifest": nm,
                    "actual_app_observation": n, "current_scope_full_APK_identity_equal": True}}
            row["manifest_permissions"] = current_permission_declarations(identity, n["apks"], ndk_path,
                "ACTUAL_CURRENT_APK_NORMAL_XMLTREE")
            row["official_source"] = {"state": "UNKNOWN", "normal_signature_does_not_prove_vendor_source": True,
                "actual_audit_source": ndk_path, "vendor_artifact_source_trust": ndk["vendor_artifact_source_trust"]}

    artifact_path = "retention_inventory_r1/observer-candidate-r2/actual-public/artifact.original.json"
    retained = read(artifact_path, "19ad825b48aef18d1e2c0264228c298c0e92311932347992c15877964a4b270c")
    retention_joint_path = "retention_inventory_r1/observer-candidate-r2/actual-public/root-validation.actual.json"
    retention_joint = read(retention_joint_path)
    assert retention_joint["status"] == "PASS_BOUNDED_METADATA_ONLY" and retained["ok"]
    assert len(retained["tree_observations"]) == 16
    assert sum(t["status"] == "COMPLETE_METADATA_WALK" for t in retained["tree_observations"]) == 14
    recorded_summary_path = "retention_inventory_r1/recorded_entries_summary_r1/actual/stdout.original.json"
    recorded_summary = read(recorded_summary_path, "b567e93c585d31102fe54db71b37de967f0b99c68b012d1b8fc95cb9aa901230")
    recorded_joint_path = "retention_inventory_r1/recorded_entries_summary_r1/actual/root-validation.actual.json"
    recorded_joint = read(recorded_joint_path, "3290ca9b306e1bd938df712cb2502d897ac050469c4325d316f33e51d0d2e4fa")
    assert recorded_joint["status"] == "PASS_FIXED_PRIOR_METADATA_SUMMARY_ONLY"
    assert recorded_summary["ok"] and recorded_summary["errors"] == [] and recorded_summary["original_descriptor_identities_restored"]
    assert recorded_summary["summary"]["original_stream"] == retained["entries_private"]
    assert recorded_summary["observation_binding"]["sampled_before_ZBJ_full48_upgrade"] is True
    details = recorded_summary["summary"]
    assert len(details["previous_APKs"]) == details["selected_unique_device_inode_pairs"] == 12
    assert len(details["gap_references"]) == 21
    assert details["selected_observation_allocated_bytes_unique_inode"] == details["selected_observation_allocated_bytes_sum"] == 2137006080
    assert all(r["full_recorded_stat_matches_retained_receipt"] and r["observed_hardlink_count"] == 1 for r in details["previous_APKs"])
    assert details["reclaimable_bytes"] is None and not details["fresh_target_observation_performed"]
    old_retention_path = "retention_inventory_r1/DEPENDENCY_PROTECTION.json"
    old_retention = read(old_retention_path)
    new_old_apks = install["previous_apks_retained"]
    assert len(old_retention["retained_previous_APKs"]) == 12 and len(new_old_apks) == 1
    retained_logical_total = old_retention["retained_previous_APK_recorded_logical_bytes"] + sum(r["retained"]["bytes"] for r in new_old_apks)
    assert retained_logical_total == 2303804758
    total_apks = sum(len(row["current_installed_identity"]["apks"]) for row in rows)
    assert len(rows) == 46 and total_apks == 86
    assert sum(len(row["apks"]) for row in scope["apps"].values()) == 88
    return {"current_protected_scope": {"source": post_path, "remote_reference": install["next_app_scope"],
                "package_count": 48, "APK_count": 88, "APK_logical_bytes": scope_joint["APK_logical_bytes"],
                "install_job": terminal["job_id"], "readback_job": scope_joint["job_id"],
                "other47_rows_equal_prior48": True, "scope_is_not_global_signature_or_resolver_qualification": True,
                "helper_packages_outside46_launcher_rows": sorted(set(scope["apps"]) - {row["package"] for row in rows})},
            "membership_provenance": {"source": "successor_audit_requests/native46_discovery_r1/actual/artifact.original.json",
                "job_id": membership_joint["job_id"], "Launcher_packages": 46, "non_APEX_APK_packages": 206,
                "basis": "LAST_COMPLETE_ACTUAL_USER0_MAIN_LAUNCHER_AND_NATIVE_CATALOGUE_OBSERVATION",
                "new_global_resolver_after_ZBJ_install": False, "new_installed_package_enumeration_after_ZBJ_install": False},
            "normal_metadata_linkage": {"apps": 46, "APKs": total_apks, "prior_audited_current_unchanged_apps": 44,
                "new_NDK_direct_APK_audit_apps": 1, "S43_same_byte_verified_ZBJ_install_apps": 1,
                "all46_reaudited_in_one_new_job": False, "all_row_bytes_and_UID_and_PM_signer_match_current_scope": True,
                "old_ZBJ_audit_retained_as_history": True, "original_failed_batches_unchanged": True,
                "resource_table_health_or_business_qualification_inferred": False},
            "retention_observation": {"source": artifact_path, "joint_source": retention_joint_path,
                "job_id": retention_joint["job_id"], "sampled_before_ZBJ_upgrade": True,
                "exact_reference_summary": retained["exact_reference_summary"], "complete_trees": 14, "requested_trees": 16,
                "incomplete_trees": [{"path": t["path"], "status": t["status"], "gaps": t.get("gaps", [])}
                                     for t in retained["tree_observations"] if t["status"] != "COMPLETE_METADATA_WALK"],
                "recorded_unique_device_inode_allocation_summary": retained["allocation_summary"],
                "recorded_previous_APK_summary": {"source": recorded_summary_path, "joint_source": recorded_joint_path,
                    "job_id": recorded_joint["job_id"], "sampled_before_ZBJ_upgrade": True,
                    "12_prior_APKs_recorded_allocated_bytes": 2137006080, "details": details,
                    "new_ZBJ_retained_APK_included": False, "not_fresh_target_scan_or_freeable": True},
                "original_previous_APKs_count": 12, "original_previous_APK_recorded_logical_bytes": 2136945962,
                "new_ZBJ_previous_APK_receipt": new_old_apks[0], "new_ZBJ_previous_APK_in_preupgrade_scan": False,
                "combined_retained_receipt_count": 13, "combined_recorded_logical_bytes_not_current_allocated_or_freeable": retained_logical_total,
                "combined_current_allocated_bytes": None, "reclaimable_bytes": None,
                "all_other_task_or_project_dependencies_retained": True, "deletions": 0, "cleanup_eligible": False}}


def render_current_inventory(rows, output):
    text = ["# 最近完整观察的 46 个 Launcher App 与当前已装包证据", "",
        "本轮已完成 **12 次正常同签名升级**。最近一次完整 PackageManager resolver 与 native 目录观察为 **46 个 Launcher App、206 个非 APEX APK 包**；猪八戒此次升级后没有重新执行全局枚举。新的实际保护范围是 **48 包 / 88 APK**，包含这 46 项和两个 helper。", "",
        "现在可将正常签名、manifest 和声明权限证据与这 **46 个 App / 86 个 APK** 的当前身份关联：44 项沿既有正常审计字节，NDK 新增直接审计，猪八戒以 S43 正常验签候选与实际安装字节完全一致关联。没有把旧猪八戒版本的审计移作新版证据。**生产验收 0，已删除旧产物 0 字节。**", "",
        "以下 versionName 来自已装 APK 本身或经实际安装字节核同的候选 manifest。未声明版本保留为未声明；Android/PM 的有效 code 0 单独列示。签名有效、正常升级及版本较新均不代表最新版业务可用性已通过。", "",
        "## 46 项清单", "",
        "| App（历史标签） | 包名 | versionName / 有效 code | 当前证据 | 有效权限 |", "|---|---|---|---|---|"]
    for row in rows:
        package = row["package"]
        label = row["label_reference"] or "NDK 测试入口（显示名称未提取）"
        version = row["version_name"] if row["version_name"] is not None else "未声明"
        upgraded = row["upgrade"]["state"] == "INSTALLED_AND_CURRENT_BYTES_REOBSERVED_BUSINESS_QA_PENDING"
        status = "已正常升级；签名与当前字节关联" if upgraded else "当前字节与正常审计关联"
        if package == "com.example.ndk_tests":
            status += "；来源仍 UNKNOWN"
        elif package == "com.sankuai.meituan.takeoutnew":
            status += "；升级候选签名冲突"
        permission = "既有实际快照已解释；功能行为待验" if row["effective_permissions"]["state"] == "LITERAL_SERVICE_SNAPSHOT_INTERPRETED" else "UNKNOWN（尚无已解释有效快照）"
        text.append(f"| {label} | `{package}` | {version} / {row['PM']['version_code']} | {status} | {permission} |")
    memory = output["framework_memory_observation"]
    text += ["", "## 已确认的边界与失败路径", "",
        "猪八戒已从 code 369 正常升级到 9.5.20 / code 370，同厂商签名、UID10144 和 CE/DE inode152967/152970 保留；旧包另外留存。其他 47 个保护包的完整记录未变。业务启动、登录或访客、核心操作和长期回归仍待验。", "",
        "NDK 包的完整 APK 已通过普通验签及 manifest 审计；XML 未声明 versionCode、versionCodeMajor、versionName，原 badging 空串和派生 null 保留，有效 code 0 与 PM 一致。其 minSdk14、targetSdk24、arm64-v8a 及 WRITE_EXTERNAL_STORAGE、INTERNET 是声明观察，来源、有效授权和业务能力仍未知。", "",
        "贝壳最新公开比较显示：既有 preinspection 与两次历史观察的稳定窗口 hash、搜索节点相同，可见路径集相同；有一个其他可见节点的文本/边界/hash 变化，整树 hash 不同。但被拒动作当时的当前树没有导出，因此具体拒绝差异和根因仍 UNKNOWN。原 helper 明确未执行该点击，整个 FAILED/UNKNOWN 仍保留；没有降低一致性检查，也没有推断搜索成功。", "",
        "美团升级候选与已装包签名冲突，未绕过、重签或卸载，位置权限未主动开启。12306 尚缺合格完整新包。14 个国际 App 的完整新包仍未全部取得；万豪普通公开入口的 HTTP403 失败保留。NDK 来源未知不因验签成功而升级为官方来源。", "",
        f"本报告继承的 RAM 观察时间为 {memory['observed_utc']}，MemAvailable {memory['values_bytes']['MemAvailable']:,} B，距原 15 GiB 门槛差 {-memory['difference_from_original_minimum_bytes']:,} B；本生成器没有发起新 RAM 观察或构建。Builder 资格不等于 framework 编译、部署或生产通过。", "",
        "## 权限、回归与清理", "",
        "目前解释了贝壳、Fcitx、microG 三份实际权限快照，角色仍 UNKNOWN，AppOps 按原文字面作用域保存。它们是既有采样，未在猪八戒升级后重新采集，也不等于实际拒绝、恢复或核心功能行为测试。其余 App 不虚构有效 grants。", "",
        "逐 App 的启动、登录或访客、核心操作、网络、存储、权限行为、长时间运行、App 重启、运行时重启和故障恢复尚未全面通过。缺少运行证据的格子保留 UNKNOWN。当前内置 Android 证据不转移为已退役 reDroid 的通过结果。", "",
        "空间观察采样在猪八戒此次升级之前：797 个固定引用中 776 已观察、20 缺失、1 未解析；16 个限定目录树完成 14 个，共享工作树因原预算停止，build08 树未遍历。记录的 10,889,973,760 B inode 去重已分配量是有限观察，不是可释放空间。", "",
        "对上述已落盘观察原件的固定读取，进一步确认此前 11 次升级的 12 份旧 APK：完整 stat 均与原留存回执相同，12 个不同 inode、nlink 均为 1，记录的分配量为 2,137,006,080 B，逻辑量为 2,136,945,962 B。这仍是猪八戒升级前采样，也不证明没有其他运行依赖或可释放。猪八戒随后又留存 166,858,796 B 旧 APK；12 次升级的 13 份留存回执逻辑量合计 2,303,804,758 B。新增这一份未进入之前的分配量盘点，当前合并物理占用和可释放量仍未知。", "",
        "旧 builder/tool 与外部项目的 9 个精确 JDK 依赖继续保留。最终源码、配置、签名 APK 和复现清单未脱离旧目录依赖、生产回归未通过之前，不删除。", "",
        "继续沿既有 sidecar、容器内 UI Automator、中文输入与节点定位。Bili Accept 仅沿历史独立测试 cell 授权；不主动开启美团位置权限；不绕过签名或其他完整性检查。", "",
        "## 证据入口", ""]
    for name, item in INPUTS.items():
        text.append(f"- `{name}` — {item['bytes']} B / SHA-256 `{item['sha256']}`")
    return "\n".join(text) + "\n"
