def validate_scope_qualification(outer_raw, terminal_raw, validator):
    """Require the actual identity-only 48-scope joint; it is not APK signature evidence."""
    need(len(outer_raw.splitlines()) == 2, "EXACT_SCOPE_STAGE_AND_OUTER_STREAM")
    stage, outer = [json.loads(line) for line in outer_raw.splitlines()]
    terminal = json.loads(terminal_raw)
    need(terminal.get("job_id") == SCOPE_JOB and terminal.get("state") == "succeeded" and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == 0 and
         all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")),
         "ACTUAL_SCOPE_DURABLE_NORMAL_SUCCESS_REQUIRED")
    need(terminal.get("log_bytes") == {"stdout": {"seen": len(outer_raw), "stored": len(outer_raw)},
                                      "stderr": {"seen": 0, "stored": 0}} and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True}, "ACTUAL_SCOPE_COMPLETE_ORIGINAL_STREAMS")
    need(stage.get("schema") == "pocket4-explicit48-owned-scope-source-stage-result-v1" and stage.get("source_stage_ok") is True and
         stage.get("source_root") == SCOPE_STAGE and stage.get("bootstrap_FDs_before") == stage.get("bootstrap_FDs_after") and
         all(type(stage.get(key)) is int and stage[key] == 0 for key in
             ("stage_Main_reads", "stage_UI_actions", "stage_installs", "stage_namespace_entries")), "ACTUAL_SCOPE_SOURCE_STAGE")
    need(validator.CONFIG["kind"] == "explicit48" and validator.CONFIG["stage_root"] == SCOPE_STAGE,
         "PINNED_ACTUAL_SCOPE_VALIDATOR")
    need(outer.get("schema") == "pocket4-owned-readonly-observation-result-v1" and outer.get("ok") is True and
         outer.get("status") == "READONLY_OBSERVATION_AND_OWNED_LIFETIME_VERIFIED" and outer.get("kind") == "explicit48" and
         outer.get("errors") == [] and outer.get("automatic_retry") is False and outer.get("production_ready") is False and
         outer.get("inner_result_alone_qualifies") is False and outer.get("old_results_reclassified") is False and
         outer.get("library_FD_retired_by_original_held_owned_child_exit") is True and
         all(type(outer.get(key)) is int and outer[key] == 0 for key in ("UI_actions", "installs", "permission_changes")),
         "ACTUAL_SCOPE_OWNED_OUTER_GATE")
    child = outer["child_result"]
    need(validator.combined(outer["child_lifecycle"], child, b"") and outer["child_stderr"]["bytes"] == 0 and
         outer["child_stderr"]["sha256"] == sha(b"") and child.get("worker_invoked") is True and
         child.get("manual_library_FD_close") is False and child.get("unknown_FDs_closed") == 0 and
         child["frozen_descriptors_before_worker"] == child["frozen_descriptors_after_worker"] == child["final_descriptors"],
         "ACTUAL_SCOPE_OWNED_NORMAL_EXIT_AND_FDS")
    worker_raw = child["worker_stdout_original"].encode("utf-8")
    need(len(worker_raw) == child["worker_stdout_bytes"] == outer["worker_stdout"]["bytes"] and
         sha(worker_raw) == child["worker_stdout_sha256"] == outer["worker_stdout"]["sha256"], "ACTUAL_SCOPE_WORKER_STREAM_PIN")
    observed = validator.decode_worker(worker_raw)
    validator.worker_gate(observed, child["worker_returncode"])
    need(observed["observation"]["app_scope"] == ACTUAL_SCOPE and observed["packages"] == PROTECTED_PACKAGES and
         observed["package_count"] == 48 and observed["new_signature_verification_performed"] is False and
         observed["UI_or_install_admitted"] is False and observed["original_47_unchanged"] is True and
         observed["new_package_matches_actual_discovery"] is True, "EXACT_IDENTITY_ONLY_SCOPE_48")
    return {"job_id": SCOPE_JOB, "scope": ACTUAL_SCOPE, "outer": SCOPE_STDOUT, "terminal": SCOPE_TERMINAL,
            "validator": SCOPE_VALIDATOR, "normal_owned_joint_validated": True,
            "scope_is_signature_evidence": False, "scope_is_UI_or_install_admission": False}


def ndk_xml_root(raw, expected):
    """Read the current signed APK's actual XML root, preserving all typed attributes."""
    text = raw.decode("utf-8", "strict")
    lines = text.splitlines()
    need(lines and lines[0] == "N: android=http://schemas.android.com/apk/res/android",
         "NDK_XML_ANDROID_NAMESPACE_REQUIRED")
    roots = [i for i, line in enumerate(lines) if re.fullmatch(r"  E: manifest \(line=[0-9]+\)", line)]
    need(roots == [1], "ONE_COMPLETE_NDK_XML_MANIFEST_ROOT_REQUIRED")
    attributes = {}
    child_seen = False
    for line in lines[2:]:
        if re.fullmatch(r"    E: [A-Za-z0-9_.:-]+ \(line=[0-9]+\)", line):
            child_seen = True
            break
        match = re.fullmatch(r"    A: ([A-Za-z0-9_.:-]+)(?:\(0x[0-9a-fA-F]+\))?=(.*)", line)
        need(match is not None and match[1] not in attributes, "NDK_XML_ROOT_ATTRIBUTE_UNPARSED_OR_DUPLICATE")
        attributes[match[1]] = match[2]
    need(child_seen, "COMPLETE_ROOT_ATTRIBUTE_BLOCK_MUST_END_AT_OBSERVED_CHILD")
    value = attributes.get("package")
    literal = re.fullmatch(r'("(?:[^"\\]|\\.)*") \(Raw: ("(?:[^"\\]|\\.)*")\)', value or "")
    need(literal is not None and json.loads(literal[1]) == json.loads(literal[2]) == expected["package"],
         "CURRENT_XML_PACKAGE_MUST_MATCH_FIXED_SCOPE")
    names = ("android:versionCode", "android:versionCodeMajor", "android:versionName")
    return {"stream": {"bytes": len(raw), "sha256": sha(raw)}, "root_package": expected["package"],
            "root_attributes_original": attributes,
            "version_attribute_declarations": {key: attributes.get(key) for key in names},
            "all_three_version_attributes_absent": all(key not in attributes for key in names),
            "missing_or_partial_XML_accepted": False}


def ndk_manifest_with_observed_absence(raw, xml_raw, expected, apk, signature):
    """Use actual XML absence, normal cryptographic verification and the exact scoped APK.

    No manifest field is fabricated from PackageManager. Empty badging strings
    and absent declarations remain distinct from Android's effective default.
    The previous fixture package exception and its observed stream pins are not
    transferred to NDK. This new contract accepts only the frozen NDK identity.
    """
    need(expected == NDK_EXPECTED and expected["package"] == "com.example.ndk_tests" and
         type(expected["uid"]) is int and expected["uid"] == 10162 and expected["apks"] == [apk],
         "ONLY_EXACT_FRESH_SCOPED_NDK_IDENTITY")
    need(signature is not None and signature.get("verified") is True and
         signature.get("cryptographic_verification_performed") is True and
         signature.get("API_minimum_override_used") is False and signature.get("integrity_check_bypassed") is False and
         signature.get("signer_certificate_sha256") == expected["package_manager_certificate_sha256"],
         "NORMAL_CURRENT_SIGNATURE_MATCHING_PM_REQUIRED")
    root = ndk_xml_root(xml_raw, expected)
    text = raw.decode("utf-8", "strict")
    lines = [line for line in text.splitlines() if line.startswith("package: ")]
    need(len(lines) == 1, "UNIQUE_AAPT_PACKAGE_LINE")
    attrs, at = {}, len("package:")
    while at < len(lines[0]):
        match = re.match(r"\s+([A-Za-z][A-Za-z0-9_-]*)='([^']*)'", lines[0][at:])
        need(match is not None and match[1] not in attrs, "BADGING_ATTRIBUTE_UNPARSED_OR_DUPLICATE")
        attrs[match[1]] = match[2]
        at += match.end()
    need(attrs.get("name") == expected["package"] and "split" not in attrs, "FIXED_NDK_BASE_PACKAGE_REQUIRED")
    if attrs.get("versionCode", "").isdigit():
        value = badging_manifest(raw)
        value["xml_root_observation"] = root
        value["version_default_applied_by_this_adapter"] = False
        return value
    need(type(expected["version_code"]) is int and expected["version_code"] == 0 and
         attrs.get("versionCode") == "" and attrs.get("versionName") == "" and "versionCodeMajor" not in attrs and
         root["all_three_version_attributes_absent"] is True,
         "ACTUAL_EMPTY_BADGING_AND_COMPLETE_XML_ABSENCE_REQUIRED_FOR_DEFAULT_ZERO")
    value = {"package": expected["package"], "version_code": None, "version_code_major": None, "version_name": None,
             "version_code_raw": attrs["versionCode"], "version_name_raw": attrs["versionName"],
             "split_name": None, "package_line_raw": lines[0], "long_version_code": 0,
             "effective_version_code_source": "ANDROID_ABSENT_ATTRIBUTE_DEFAULT_CONFIRMED_BY_CURRENT_XML_AND_PM_ZERO",
             "version_default_applied_by_this_adapter": True, "xml_root_observation": root,
             "version_default_evidence": {"schema": "pocket4-current-signed-ndk-absent-version-evidence-v1",
                 "badging_stream": {"bytes": len(raw), "sha256": sha(raw)}, "xml_root": root,
                 "fixed_APK_sha256": apk["sha256"], "fixed_PM_version_code": 0,
                 "fresh_normal_signature_matches_fixed_PM": True, "declared_version_name_invented": False,
                 "historical_fixture_exception_inherited": False,
                 "Android_parser_reference": ANDROID_VERSION_DEFAULT_REFERENCE}}
    # Identical SDK/ABI extraction to the already proven generic parser.
    for name, prefixes in (("min_sdk", ("sdkVersion:", "minSdkVersion:")),
                           ("target_sdk", ("targetSdkVersion:",)), ("max_sdk", ("maxSdkVersion:",))):
        found = [line for line in text.splitlines() if line.startswith(prefixes)]
        need(len(found) <= 1, "AMBIGUOUS_AAPT_SDK")
        if found:
            parsed = re.fullmatch(r"(?:sdkVersion|minSdkVersion|targetSdkVersion|maxSdkVersion):'([^']+)'", found[0])
            need(parsed is not None, "MALFORMED_AAPT_SDK_LINE")
            value[name] = parsed[1]
        else:
            value[name] = None
    native = [line for line in text.splitlines() if line.startswith("native-code:")]
    need(len(native) <= 1, "AMBIGUOUS_AAPT_ABI")
    value["native_abis"] = re.findall(r"'([^']*)'", native[0]) if native else []
    value["native_abi_source"] = "aapt2_dump_badging_current_APK"
    return value


def clean_official_badging_observations(result):
    badging = [row for row in result["commands"] if row.get("name") == "badging"]
    expected = [(app["package"], apk["path"]) for app in result["apps"] for apk in app["apks"]]
    return bool(len(expected) == 1 and [(row.get("package"), row.get("apk_path")) for row in badging] == expected and
                all(row.get("returncode") == 0 and row.get("output_capture_complete") is True and
                    row.get("stderr", {}).get("bytes") == 0 and row.get("stderr", {}).get("sha256") ==
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" for row in badging))


def validate_request(request):
    need(set(request) == {"schema", "guard", "app_scope", "packages", "protected_packages", "output_root", "official_release_assets",
                          "legacy_candidate_aapt2", "legacy_candidate_inventory", "legacy_candidate_proof", "legacy_candidate_terminal",
                          "official_candidate_aapt2", "official_host_stdout", "official_host_terminal",
                          "scope_joint_stdout", "scope_terminal", "scope_validator"}, "CLOSED_INDEPENDENT_NDK_AUDIT_REQUEST")
    need(request["schema"] == "pocket4-ndk-current-apk-signature-metadata-request-v1" and
         request["guard"] == ACTUAL_GUARD and request["app_scope"] == ACTUAL_SCOPE and
         request["packages"] == [NDK_EXPECTED["package"]] and request["protected_packages"] == PROTECTED_PACKAGES and
         len(PROTECTED_PACKAGES) == len(set(PROTECTED_PACKAGES)) == 48 and
         request["output_root"] == OUTPUT_PREFIX and request["official_release_assets"] is None and
         request["scope_joint_stdout"] == SCOPE_STDOUT and request["scope_terminal"] == SCOPE_TERMINAL and
         request["scope_validator"] == SCOPE_VALIDATOR, "EXACT_CURRENT_48_PROTECTION_AND_ONE_NDK_AUDIT")
    validate_candidate(request["legacy_candidate_aapt2"])
    need(request["official_candidate_aapt2"] == OFFICIAL_CANDIDATE and request["official_host_stdout"] == OFFICIAL_HOST_STDOUT and
         request["official_host_terminal"] == OFFICIAL_HOST_TERMINAL, "EXACT_ACTUAL_OFFICIAL_TOOL_PROOF_REQUEST")
    need(request["legacy_candidate_proof"] == ACTUAL_PROOF and request["legacy_candidate_terminal"] == ACTUAL_PROOF_TERMINAL and
         request["legacy_candidate_inventory"] == ACTUAL_INVENTORY, "EXACT_ACTUAL_PRIOR_TOOL_PROVENANCE")
