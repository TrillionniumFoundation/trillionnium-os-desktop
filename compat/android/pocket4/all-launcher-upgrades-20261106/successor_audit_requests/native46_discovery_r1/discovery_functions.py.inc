def prior_observations():
    """Pinned historical inputs establish the question, never current authority."""
    values = {name: parse(read_root_pin(pin)) for name, pin in PRIOR.items()}
    previous, failed, terminal = values["previous_pm"], values["failed_capture"], values["failed_terminal"]
    need(previous.get("schema") == "pocket4-current-readonly-services-observation-v1" and
         previous.get("ok") is True and previous.get("errors") == [] and
         previous.get("status") == "CURRENT_PM_AND_MAIN_LAUNCHER_OBSERVED" and
         previous.get("enumeration_samples_equal") is True and
         previous.get("guard_before") == previous.get("guard_after") and
         previous["guard_before"]["runtime_epoch_sha256"] == EPOCH,
         "EXACT_PREVIOUS_PM_OBSERVATION_REQUIRED")
    prior_components = [row["component"] for row in previous["MAIN_LAUNCHER_components"]]
    need(len(prior_components) == len(set(prior_components)) == 45 and
         {row["package"] for row in previous["MAIN_LAUNCHER_components"]} == set(LAUNCHERS) and
         len(previous["installed_packages"]) == 205 and
         NEW_PACKAGE not in {row["package"] for row in previous["installed_packages"]},
         "EXACT_HISTORICAL_ROSTER_REQUIRED")
    need(failed.get("schema") == "pocket4-fixed-launcher-permission-raw-capture-v1" and
         failed.get("ok") is False and
         failed.get("errors") == [{"reason": "EXACT_ACTUAL45_NATIVE_COMPONENT_REFERENCE_CHANGED", "type": "RuntimeError"}] and
         failed.get("Android_namespace_commands") == 0 and failed.get("android_commands") == [] and
         failed.get("native_command_count") == 2 and
         failed.get("guard_before") == previous["guard_before"] and
         failed.get("native_catalog_comparison") == {
             "actual_framework_resolver_reference_job": "1a1b22e95d0-fc05-7cd4",
             "added_components": [NEW_COMPONENT], "expected_count": 45,
             "framework_resolver_requeried_by_this_worker": False,
             "missing_components": [], "observed_count": 46},
         "ORIGINAL_B03_FAILURE_MUST_REMAIN_EXACT")
    need(terminal.get("job_id") == "1a1b2eccc8a-fc05-8033" and
         terminal.get("state") == "failed" and terminal.get("exit_code") == 1 and
         all(terminal.get(k) is True for k in ("audit_recorded", "output_complete", "output_durable",
                                               "terminal_publication_confirmed")) and
         all(terminal.get(k) is False for k in ("automatic_retry", "cancelled", "timed_out")) and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_bytes") == {"stdout": {"seen": 15781, "stored": 15781},
                                      "stderr": {"seen": 0, "stored": 0}},
         "EXACT_DURABLE_FAILED_B03_TERMINAL_REQUIRED")
    return previous


def discovery_comparison(installed, resolver, native, previous):
    """Full sets are compared before deciding whether this one-package question fits."""
    old_components = {row["component"] for row in previous["MAIN_LAUNCHER_components"]}
    current_components = {row["component"] for row in resolver}
    need(type(native.get("applications")) is list and len(native["applications"]) <= 4096,
         "DISCOVERY_NATIVE_CATALOG_BOUND")
    native_components = []
    for row in native["applications"]:
        need(type(row) is dict and type(row.get("component")) is str and type(row.get("package")) is str,
             "DISCOVERY_NATIVE_COMPONENT_SCHEMA")
        parsed = component(row["component"])
        need(parsed["package"] == row["package"], "DISCOVERY_NATIVE_COMPONENT_PACKAGE")
        native_components.append(parsed["component"])
    need(len(native_components) == len(set(native_components)), "DUPLICATE_NATIVE_DISCOVERY_COMPONENT")
    old_rows = {canonical(row) for row in previous["installed_packages"]}
    current_rows = {canonical(row) for row in installed}
    added_rows = [parse(raw) for raw in sorted(current_rows - old_rows)]
    missing_rows = [parse(raw) for raw in sorted(old_rows - current_rows)]
    new_rows = [row for row in installed if row["package"] == NEW_PACKAGE]
    expected_components = old_components | {NEW_COMPONENT}
    fits = (current_components == set(native_components) == expected_components and
            len(resolver) == len(native_components) == 46 and not missing_rows and
            len(new_rows) == len(added_rows) == 1 and added_rows == new_rows and
            len(new_rows[0]["uids"]) == 1 and 0 <= new_rows[0]["uids"][0] < 100000)
    return {"previous_resolver_reference": PRIOR["previous_pm"],
            "original_failure_reference": PRIOR["failed_capture"],
            "target_package": NEW_PACKAGE, "target_component": NEW_COMPONENT,
            "previous_component_count": len(old_components),
            "current_resolver_component_count": len(resolver),
            "current_native_component_count": len(native_components),
            "added_components": sorted(current_components - old_components),
            "missing_components": sorted(old_components - current_components),
            "framework_only_components": sorted(current_components - set(native_components)),
            "native_only_components": sorted(set(native_components) - current_components),
            "current_native_components": sorted(native_components),
            "PM_added_package_version_rows": added_rows,
            "PM_missing_package_version_rows": missing_rows,
            "PM_target_rows": new_rows,
            "matches_only_the_observed_new_component": fits,
            "native_count_alone_is_not_framework_resolver_proof": True,
            "does_not_prove_when_or_why_package_was_installed": True}


def safe_package_attributes(core, raw, package):
    root = core.A.parse_xml(raw)
    need(root.tag == "packages", "DISCOVERY_PACKAGES_ROOT")
    rows = [node for node in root.children if node.tag == "package" and node.attrs.get("name") == package]
    need(len(rows) == 1, "EXACT_NEW_PACKAGE_XML_ROW")
    allowed = ("name", "userId", "sharedUserId", "version", "versionCode", "codePath",
               "primaryCpuAbi", "secondaryCpuAbi", "nativeLibraryPath", "ft", "it", "ut",
               "firstInstallTime", "lastUpdateTime", "installer", "installerPackageName",
               "installerAttributionTag", "initiatingPackageName", "originatingPackageName", "packageSource")
    fields = {}
    for key in allowed:
        if key not in rows[0].attrs:
            fields[key] = {"status": "UNKNOWN", "reason": "ATTRIBUTE_ABSENT"}
            continue
        value = rows[0].attrs[key]
        need(type(value) in (str, int, bool) and
             (type(value) is not str or len(value.encode("utf-8")) <= 4096 and
              not any(ord(c) < 32 for c in value)), "BOUNDED_PUBLIC_PACKAGE_ATTRIBUTE")
        fields[key] = {"status": "OBSERVED_LITERAL_ATTRIBUTE", "value": value,
                       "python_type": type(value).__name__}
    return {"fields": fields, "timestamp_units_or_hex_not_inferred": True,
            "installer_value_is_not_authenticated_artifact_source": True,
            "raw_certificates_and_other_packages_not_exported": True}


def new_package_metadata(core, pool, held):
    path = "/data/system/packages.xml"
    raw, info = core.guest_read(pool, held.roots["android_init"], path, 2 * 1024 * 1024)
    row = core.package_rows(raw, [NEW_PACKAGE])[NEW_PACKAGE]
    attributes = safe_package_attributes(core, raw, NEW_PACKAGE)
    core.check_path(pool, held.roots["android_init"], path, info)
    return {"package_row": row, "safe_attributes": attributes,
            "source": {"path": path, "bytes": len(raw), "sha256": sha(raw), "file": info}}


def bind_new_package(core, pool, held, installed_row, deadline):
    """Compose frozen metadata/hash/identity primitives for this exact new package.

    Unlike the general core's 16 GiB limit, this one new package has a hard
    aggregate hash budget of 512 MiB, checked on each held FD before hashing.
    No APK or application data contents are returned or persisted.
    """
    held.verify()
    root = held.roots["android_init"]
    end, total = min(deadline - 5, time.monotonic() + 180), 0
    before = new_package_metadata(core, pool, held)
    row = before["package_row"]
    need(installed_row == {"package": NEW_PACKAGE, "version_code": row["version_code"], "uids": [row["uid"]]},
         "FRESH_PM_AND_NEW_PACKAGE_XML_IDENTITY_DIFFER")
    paths = core.apk_paths(pool, root, row["code_path"])
    apks = []
    for path in paths:
        fd = pool.own(core.H.open_in_root(root, path, os.O_RDONLY | os.O_NOFOLLOW))
        try:
            initial = core.metadata(fd)
            need(stat.S_ISREG(initial["st_mode"]) and initial["st_nlink"] == 1 and
                 0 < initial["st_size"] <= 512 * 1024 * 1024 - total and time.monotonic() < end,
                 "NEW_PACKAGE_512MIB_AGGREGATE_OR_TIME_BOUND")
            record = core.hash_fd(fd, 512 * 1024 * 1024 - total, end)
            need(record["file"] == initial, "NEW_APK_CHANGED_BEFORE_HASH")
            total += record["bytes"]
            apks.append({"path": path, **record})
        finally:
            pool.close(fd)
    dirs = {kind: core.directory_identity(pool, root, "/data/" + kind + "/0/" + NEW_PACKAGE)
            for kind in ("user", "user_de")}
    need(all(value["status"] == "ABSENT" or value["uid"] == row["uid"] for value in dirs.values()),
         "NEW_PACKAGE_DATA_DIRECTORY_UID_DIFFERS")
    identity = {NEW_PACKAGE: {**row, "apks": apks, "data_directories": dirs}}
    # This is the existing complete expected-identity contract; it checks APK
    # paths/stats, PM UID/version/signing digests and CE/DE top-level identities.
    core.app_scope(pool, held, [NEW_PACKAGE], identity, False)
    after = new_package_metadata(core, pool, held)
    need(after["package_row"] == before["package_row"] and
         after["safe_attributes"] == before["safe_attributes"], "NEW_PACKAGE_METADATA_CHANGED_DURING_BIND")
    held.verify()
    return identity, {"before": before, "after": after, "APK_hash_total_bytes": total,
                      "APK_hash_total_limit_bytes": 512 * 1024 * 1024, "APK_hash_seconds_limit": 180,
                      "raw_APK_saved": False, "data_business_content_reads": 0,
                      "fresh_signature_verification_performed": False}


def selected_dump_metadata(raw, package, uid, version_code):
    """Literal metadata inside exactly one attributed Package block only.

    Missing/ambiguous fields stay UNKNOWN. A PM versionName is labelled as a
    service observation; it is not an independently parsed APK manifest.
    Permissions, application usage, other users and business text are omitted.
    """
    keys = ("codePath", "versionCode", "versionName", "primaryCpuAbi", "secondaryCpuAbi",
            "firstInstallTime", "lastUpdateTime", "installerPackageName", "initiatingPackageName",
            "originatingPackageName", "packageSource")
    result = {"status": "UNKNOWN", "package": package, "user": 0, "UID": uid,
              "fields": {k: {"status": "UNKNOWN", "reason": "NO_ATTRIBUTED_PACKAGE_BLOCK"} for k in keys},
              "version_name_is_manifest_verified": False, "installer_is_authenticated_source": False,
              "permission_grants": "UNKNOWN_NOT_INTERPRETED", "shared_UID_membership_enumerated": False,
              "raw_dump_exported": False}
    need(type(raw) is bytes and 0 < len(raw) <= 262144, "NEW_DUMP_BOUND")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        result["reason"] = "INVALID_UTF8"
        return result
    if any(c in text for c in ("\r", "\0", "\x0b", "\x0c", "\u0085", "\u2028", "\u2029")):
        result["reason"] = "UNRECOGNIZED_LINE_SEPARATORS"
        return result
    lines = text.split("\n")
    headers = [i for i, line in enumerate(lines) if line.startswith("  Package [" + package + "]")]
    if len(headers) != 1 or re.fullmatch(r"  Package \[" + re.escape(package) + r"\] \([0-9a-fA-F]+\):", lines[headers[0]]) is None:
        result["reason"] = "MISSING_DUPLICATE_OR_UNRECOGNIZED_TARGET_PACKAGE_HEADER"
        return result
    start = headers[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i].startswith("    ")), len(lines))
    block = lines[start + 1:end]
    ids = [line for line in block if line.startswith("    appId=")]
    if ids != ["    appId=" + str(uid)]:
        result["reason"] = "PACKAGE_APPID_MISSING_DUPLICATE_OR_DIFFERENT"
        return result
    result["package_identity_matches_fresh_UID"] = True
    for key in keys:
        matches = [line for line in block if line.startswith("    " + key + "=")]
        if len(matches) != 1:
            result["fields"][key] = {"status": "UNKNOWN", "reason": "MISSING_FIELD" if not matches else "DUPLICATE_FIELD"}
            continue
        line = matches[0]
        literal = line[len("    " + key + "="):]
        if len(literal.encode("utf-8")) > 4096 or any(ord(c) < 32 for c in literal):
            result["fields"][key] = {"status": "UNKNOWN", "reason": "UNRECOGNIZED_BOUNDED_LITERAL"}
            continue
        field = {"status": "OBSERVED_LITERAL_PM_SERVICE_FIELD", "literal": literal,
                 "line_sha256": sha(line.encode("utf-8")), "normalization_applied": False}
        if key == "versionCode":
            matched = re.fullmatch(r"([0-9]+)(?: minSdk=[0-9]+ targetSdk=[0-9]+)?", literal)
            if matched is None:
                field = {"status": "UNKNOWN", "reason": "UNRECOGNIZED_VERSION_CODE_LINE", "line_sha256": sha(line.encode("utf-8"))}
            else:
                field["integer"] = int(matched[1])
                need(field["integer"] == version_code, "DUMP_AND_FRESH_PM_VERSION_CODE_DIFFER")
        result["fields"][key] = field
    result["status"] = "TARGET_PACKAGE_LITERAL_METADATA_OBSERVED_WITH_EXPLICIT_UNKNOWN_FIELDS"
    return result
