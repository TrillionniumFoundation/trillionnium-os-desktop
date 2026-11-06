def write_empty_raw_stream(core, pool, directory, root_identity, path, raw):
    """Create only an exact empty command stream; other artifacts use frozen core."""
    name = path.rsplit("/", 1)[-1]
    need(type(raw) is bytes and raw == b"" and
         re.fullmatch(r"(?:native|android)-[0-9]{2}\.(?:stdout|stderr)", name) is not None,
         "ONLY_EMPTY_COMMAND_RAW_STREAM")
    need(all(core.metadata(directory)[key] == root_identity[key]
             for key in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")),
         "EMPTY_STREAM_PARENT_IDENTITY_CHANGED")
    fd = pool.own(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                          0o400, dir_fd=directory))
    try:
        os.fchmod(fd, 0o400)
        os.fsync(fd)
        observed = os.fstat(fd)
        need(stat.S_ISREG(observed.st_mode) and observed.st_uid == root_identity["st_uid"] and
             stat.S_IMODE(observed.st_mode) == 0o400 and observed.st_nlink == 1 and observed.st_size == 0,
             "EMPTY_RAW_STREAM_METADATA")
        os.fsync(directory)
    finally:
        pool.close(fd)
    return {"path": path, "sha256": sha(raw), "bytes": 0}


def remember_child_streams(rows, row, write, prefix, raw, stderr):
    """Retain the actual child result even if an owned receipt cannot be saved."""
    rows.append(row)
    row.update(stdout=None, stderr=None, stream_artifacts_complete=False)
    try:
        row["stdout"] = write(prefix + ".stdout", raw)
        row["stderr"] = write(prefix + ".stderr", stderr)
        row["stream_artifacts_complete"] = True
    except BaseException as error:
        row["stream_artifact_error"] = safe_error(error)
        raise


def validate_request(request):
    need(type(request) is dict and set(request) == {"schema", "guard", "app_scope", "packages", "worker", "transport", "output_root",
                                                       "target_package", "target_user", "appops_help"},
         "CLOSED_SERVICE_OBSERVATION_REQUEST")
    need(request["schema"] == "pocket4-beike-permission-raw-observation-request-v1" and request["guard"] == GUARD and
         request["app_scope"] == APP_SCOPE and request["packages"] == PACKAGES and request["transport"] == TRANSPORT and
         request["output_root"] == OUTPUT and request["target_package"] == TARGET_PACKAGE and
         type(request["target_user"]) is int and request["target_user"] == TARGET_USER and
         request["appops_help"] == APP_OPS_HELP, "EXACT_SCOPE_AND_CLOSED_OPERATION_REQUEST")
    need(request["worker"]["path"] == STAGE + "/observe_current_services.py" and str(Path(__file__).resolve()) == request["worker"]["path"],
         "EXACT_REAL_SERVICE_SOURCE_REQUIRED")
    read_root_pin(request["worker"])


def parse_packages(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 262144, "PACKAGE_LIST_BOUND")
    records, identities = [], set()
    for line in raw.decode("utf-8", "strict").splitlines():
        match = re.fullmatch(r"package:([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*) versionCode:(\d+) uid:(\d+(?:,\d+)*)", line)
        need(match is not None, "UNRECOGNISED_ACTUAL_PACKAGE_ROW")
        package, version, uids = match.groups()
        row = {"package": package, "version_code": int(version), "uids": [int(x) for x in uids.split(",")]}
        key = (package, row["version_code"], tuple(row["uids"]))
        need(key not in identities and 0 <= row["version_code"] < 2**63 and all(0 <= uid < 2**31 for uid in row["uids"]),
             "DUPLICATE_OR_OUT_OF_RANGE_PACKAGE_ROW")
        identities.add(key); records.append(row)
    need(0 < len(records) <= 4096, "INSTALLED_PACKAGE_COUNT_BOUND")
    return sorted(records, key=lambda row: (row["package"], row["version_code"], row["uids"]))


def component(raw):
    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)/([A-Za-z0-9_.$]+)", raw)
    need(match is not None, "UNRECOGNISED_COMPONENT")
    package, name = match.groups()
    return {"package": package, "component": package + "/" + (package + name if name.startswith(".") else name),
            "original_component": raw}


def parse_resolver(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 262144, "RESOLVER_OUTPUT_BOUND")
    lines = raw.decode("utf-8", "strict").splitlines()
    if lines == ["No activities found"]:
        return []
    need(0 < len(lines) <= 4096, "RESOLVER_COMPONENT_COUNT_BOUND")
    rows = [component(line) for line in lines]
    need(len({row["component"] for row in rows}) == len(rows), "DUPLICATE_RESOLVER_COMPONENT")
    return sorted(rows, key=lambda row: row["component"])


def require_help_for_closed_queries(raw):
    text = raw.decode("utf-8", "strict")
    required = ("Package manager (package) commands:", "  dump-package PACKAGE\n",
                "    Print package manager state associated with the given PACKAGE.")
    need(all(value in text for value in required), "ACTUAL_PACKAGE_HELP_DOES_NOT_SUPPORT_EXACT_READONLY_QUERIES")
    return {"actual_help_sha256": sha(raw), "required_literals": list(required), "no_guessed_service_transaction": True}


def require_appops_help(raw):
    text = raw.decode("utf-8", "strict")
    required = ("AppOps service (appops) commands:",
                "  get [--user <USER_ID>] [--attribution <ATTRIBUTION_TAG>] <PACKAGE | UID> [<OP>]\n",
                "    Return the mode for a particular application and optional operation.")
    need(all(value in text for value in required), "ACTUAL_APPOPS_HELP_DOES_NOT_SUPPORT_FIXED_GET")
    return {"historical_help_pin": APP_OPS_HELP, "required_literals": list(required),
            "original_help_returncode": 255, "original_failed_job": "1a1b21fcc13-fc05-7c7a",
            "original_help_failure_reclassified": False, "get_success_inferred_from_help": False}


def compare_catalogs(installed, resolver, native, apps):
    names = {row["package"] for row in installed}
    need(set(apps) <= names, "EXPLICIT47_MISSING_FROM_CURRENT_USER0_PM")
    for package, row in apps.items():
        matches = [value for value in installed if value["package"] == package and value["version_code"] == row["version_code"]]
        need(len(matches) == 1 and set(matches[0]["uids"]) == {row["uid"]}, "EXPLICIT47_CURRENT_PM_UID_OR_VERSION_CHANGED")
    native_rows = native.get("applications")
    need(type(native_rows) is list and len(native_rows) <= 4096, "NATIVE_CURRENT_CATALOG_BOUND")
    normal_native = []
    for row in native_rows:
        need(type(row) is dict and type(row.get("package")) is str and type(row.get("component")) is str,
             "CURRENT_NATIVE_APPLICATION_SCHEMA")
        parsed = component(row["component"])
        need(parsed["package"] == row["package"], "NATIVE_COMPONENT_PACKAGE_DIFFERS")
        normal_native.append(parsed)
    a = {row["component"] for row in resolver}
    b = {row["component"] for row in normal_native}
    return {"native_package_count": len({row["package"] for row in normal_native}), "native_component_count": len(normal_native),
            "PM_user0_package_count": len(names), "PM_user0_package_version_rows": len(installed),
            "MAIN_LAUNCHER_package_count": len({row["package"] for row in resolver}), "MAIN_LAUNCHER_component_count": len(resolver),
            "framework_only_components": sorted(a-b), "native_only_components": sorted(b-a),
            "PM_packages_outside_explicit47": sorted(names-set(apps)),
            "native_packages_added_since_original45": sorted({row["package"] for row in normal_native}-set(LAUNCHERS)),
            "native_packages_missing_since_original45": sorted(set(LAUNCHERS)-{row["package"] for row in normal_native}),
            "same_count_is_not_component_identity_proof": True}


def run(request):
    validate_request(request)
    need(os.getuid() == os.geteuid() == 0, "EXISTING_HOST_ROOT_AUTHORITY_REQUIRED")
    guard = load_source(GUARD, "new_readonly_services_successor_guard")
    core = guard._core()
    transport_module = load_source(TRANSPORT, "new_independent_readonly_services_transport")
    native_helpers = load_source(NATIVE_HELPERS, "unchanged_native_identity_helpers_only")
    pool, leases = core.FDs(), core.FDs()
    held, target, directory, lock = None, None, None, None
    result = {"schema": "pocket4-beike-permission-raw-observation-v1", "ok": False, "errors": [],
              "automatic_retry": False, "production_ready": False, "UI_actions": 0, "App_launches": 0,
              "installs": 0, "permission_changes": 0, "lifecycle_commands": 0, "ADB_commands": 0,
              "business_data_content_reads": 0, "Android_namespace_commands": 0, "native_command_count": 0,
              "android_commands": [], "native_commands": [],
              "effective_permission_grants": "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION",
              "effective_AppOps_modes": "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION",
              "role_status": "UNKNOWN_NOT_QUERIED", "service_output_semantics_verified": False,
              "service_output_capture_complete": False, "permission_name_normalization": "NONE_RAW_BYTES_PRESERVED",
              "target_package": TARGET_PACKAGE, "target_user": TARGET_USER,
              "service_target_packages": [TARGET_PACKAGE], "package_dump_user_filter_applied": False,
              "packages": PACKAGES, "app_scope_reference": APP_SCOPE,
              "old_Bili_unknown_reclassified": False,
              "compiled_Beike_scope_modified": False, "UI_or_install_admitted": False}
    deadline = time.monotonic() + 900
    root_identity, native_files, native_pins, location, scope = None, None, None, None, None

    def budget():
        need(time.monotonic() + 5 < deadline, "SERVICE_OBSERVATION_TOTAL_BUDGET")

    def write(name, raw):
        need(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None, "NEW_PRIVATE_RECEIPT_NAME")
        current = core.open_host(pool, OUTPUT, os.O_PATH | os.O_DIRECTORY)
        try:
            observed = core.metadata(current)
            need(all(observed[key] == root_identity[key] for key in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")),
                 "OBSERVATION_OUTPUT_DIRECTORY_REPLACED")
        finally:
            pool.close(current)
        if type(raw) is bytes and raw == b"":
            pin = write_empty_raw_stream(core, pool, directory, root_identity, OUTPUT + "/" + name, raw)
        else:
            pin = core.write_new(OUTPUT + "/" + name, raw)
        need(core.pinned_record(pin, max(len(raw), 1)) == raw, "EXACT_OWNED_RECEIPT_READBACK")
        return pin

    def runtime_guard(action_attempted=False):
        budget()
        need(guard.current_guard() == result["guard_before"], "NEW_SERVICE_RUNTIME_CHANGED")
        core.verify_runtime(pool, held, baseline["runtime"])
        core.app_scope(pool, held, PACKAGES, scope["apps"], False)
        if target is not None:
            target.verify()
        read_root_pin(TRANSPORT)
        verify_shared_helper()

    def native_read(operation):
        need(operation in ("status", "applications"), "ONLY_NATIVE_READS")
        runtime_guard()
        native_helpers.recheck_native(core, pool, held, native_files, native_pins)
        argv = core.as_user([native_helpers.CLI_PATH, "--socket", native_helpers.SOCKET_PATH, "--json", operation])
        index = len(result["native_commands"]) + 1
        write("native-%02d.intent.json" % index, canonical({"argv": argv, "caller_uid": 1000, "automatic_retry": False})+b"\n")
        raw, stderr, row = core.bounded_child(argv, seconds=30, limit=262144)
        result["native_command_count"] += 1
        remember_child_streams(result["native_commands"],
                               {"operation": operation, "caller_uid": 1000, "command": row},
                               write, "native-%02d" % index, raw, stderr)
        value = core.native_running(raw, row)
        need(value["host_pid"] == owner, "ACTUAL_NATIVE_OWNER_CHANGED")
        native_helpers.recheck_native(core, pool, held, native_files, native_pins)
        runtime_guard()
        return value

    def record(kind, value):
        need(kind in ("intent", "command-result", "verified-result", "failure"), "EXACT_ORIGINAL_TRANSPORT_RECORD")
        write("transport-%02d.%s.json" % (value["sequence"], kind), canonical(value)+b"\n")

    def runner(argv, **options):
        need(set(options) == {"stdout", "stderr", "timeout", "env", "pass_fds", "close_fds"} and
             options["stdout"] == subprocess.PIPE and options["stderr"] == subprocess.PIPE and options["close_fds"] is True and
             options["env"] == transport_module.HOST_ENV and tuple(options["pass_fds"]) == (target.root_fd, *target.namespaces.values()),
             "ORIGINAL_HELD_RUNNER_PROTOCOL_REQUIRED")
        budget()
        index = len(result["android_commands"]) + 1
        write("android-%02d.intent.json" % index, canonical({"argv": list(argv), "authority_fds": list(options["pass_fds"]),
              "timeout_seconds": options["timeout"], "readonly": True, "automatic_retry": False})+b"\n")
        raw, stderr, row = held_bounded_child(argv, options["timeout"], 262144, tuple(options["pass_fds"]), options["env"])
        result["Android_namespace_commands"] += 1
        try:
            remember_child_streams(result["android_commands"], row, write, "android-%02d" % index, raw, stderr)
        finally:
            if not row["joined"]:
                target.poison_unjoined_command()
        write("android-%02d.result.json" % index, canonical(row)+b"\n")
        captured = subprocess.CompletedProcess(argv, row["returncode"], raw, stderr)
        captured.host_timed_out = row["termination_attempted"]
        captured.recorder_errors = row["errors"]
        captured.recorder_spawned = "host_pid" in row
        captured.recorder_joined = row["joined"]
        return captured

    try:
        core.create_private_root(OUTPUT)
        directory = core.open_host(pool, OUTPUT, os.O_RDONLY | os.O_DIRECTORY)
        root_identity = core.metadata(directory)
        flow = pool.own(os.open("flow.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory))
        try:
            os.fsync(flow)
        finally:
            pool.close(flow)
        os.fsync(directory)
        _, result["flow_lock_identity"] = core.acquire_lock(leases, OUTPUT + "/flow.lock")
        lock, result["action_lock_identity"] = core.acquire_lock(leases, core.ACTION_LOCK)
        result["guard_before"] = guard.current_guard()
        need(result["guard_before"].get("schema") == "pocket4-successor-main-guard-v1" and
             result["guard_before"]["runtime_epoch_sha256"] == EPOCH, "EXACT_TYPED_SUCCESSOR_REQUIRED")
        baseline = guard.current_baseline()
        expected = baseline["runtime"]["held"]["process_snapshot"]["binding"]
        held = core.HeldProcesses(pool, {key: row["host_pid"] for key, row in expected["processes"].items()})
        need(held.before["binding"] == expected, "ORIGINAL_EIGHT_ROLE_BINDING_REQUIRED")
        owner = expected["processes"]["launcher"]["host_pid"]
        scope = core.parse(core.pinned_record(APP_SCOPE))
        need(scope.get("schema") == "pocket4-versioned-app-scope-v1" and scope.get("runtime_epoch_sha256") == EPOCH and
             set(scope["apps"]) == set(PACKAGES), "ACTUAL_47_REFERENCE_REQUIRED")
        result["scope_guard_before"] = guard.check_app_scope(APP_SCOPE, PACKAGES)
        result["target_identity_from_pinned_scope"] = {key: scope["apps"][TARGET_PACKAGE][key]
                    for key in ("package", "uid", "version_code")}
        result["historical_appops_get_syntax_admission"] = require_appops_help(read_root_pin(APP_OPS_HELP))
        native_helpers.original_unknown(core)
        location = native_helpers.protected_location(core, pool, held, scope["apps"])
        native_files, native_pins = native_helpers.native_bind(core, pool, held)
        result["native_artifacts"] = native_pins
        result["request"] = write("request.json", canonical(request)+b"\n")
        runtime_guard()
        result["shared_namespace_helper_qualification"] = verify_shared_helper()
        expected_init = baseline["framework_epoch"]["binding"]["processes"]["init"]
        raw_init = held.extra["android_init"]["held_proc"]
        need(same_epoch_identity(raw_init, expected_init), "FRESH_INIT_DOES_NOT_MATCH_TYPED_EPOCH")
        target = core.H.HeldTarget(raw_init, HELPER_PATH, HELPER_SHA)
        values, classpaths, environment = main_classpaths(core.H, target, baseline["framework_epoch"], core.E, runtime_guard)
        need(values == baseline["runtime"]["classpath"]["values"], "ACTUAL_CLASSPATH_REFERENCE_CHANGED")
        result["classpath_binding"] = write("classpath-binding.private.json", canonical(classpaths)+b"\n")
        result["held_target"] = target.record
        result["native_before"] = native_read("status")
        native_catalog = native_read("applications")
        result["native_catalog"] = write("native-catalog.normalised.json", canonical(native_catalog)+b"\n")
        transport = transport_module.BoundArun(target=target, environment=environment, guard=runtime_guard, record=record,
                    epoch_sha256=baseline["framework_epoch"]["sha256"], init_pid=raw_init["pid"],
                    app_scope_sha256=APP_SCOPE["sha256"], user=0, runner=runner)
        raw_outputs = []
        for index, argv in enumerate(transport_module.READ_ONLY_COMMANDS):
            if index == 1:
                result["actual_package_help_admission"] = require_help_for_closed_queries(raw_outputs[0])
            raw = transport(list(argv), timeout=30)
            need(result["android_commands"][-1]["complete"] is True, "READONLY_COMMAND_NOT_COMPLETE_CLEANLY")
            raw_outputs.append(raw)
        result["help_results"] = {"package": {"stdout": result["android_commands"][0]["stdout"],
                                                "stderr": result["android_commands"][0]["stderr"], "returncode": 0}}
        result["native_after"] = native_read("status")
        runtime_guard()
        native_helpers.original_unknown(core)
        need(native_helpers.protected_location(core, pool, held, scope["apps"]) == location, "MEITUAN_SAVED_LOCATION_STATE_CHANGED")
        result["meituan_saved_location_unchanged"] = True
        result["scope_guard_after"] = guard.check_app_scope(APP_SCOPE, PACKAGES)
        result["guard_after"] = guard.current_guard()
        need(result["guard_after"] == result["guard_before"], "FINAL_TYPED_RUNTIME_CHANGED")
        for pin in (GUARD, APP_SCOPE, TRANSPORT, NATIVE_HELPERS, APP_OPS_HELP, request["worker"]):
            read_root_pin(pin)
        need(len(result["android_commands"]) == 3 and
             all(row.get("stream_artifacts_complete") is True for row in result["android_commands"]),
             "THREE_COMPLETE_ORIGINAL_SERVICE_STREAMS_REQUIRED")
        result.update(ok=True, current_scope_47_unchanged=True, service_output_capture_complete=True,
                      PM_user0_installed_APK_packages_enumerated=False, MAIN_LAUNCHER_resolver_queried=False,
                      all_installed_APK_bytes_bound=False)
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:512]})
        details = getattr(error, "details", None)
        if type(details) is dict:
            result["transport_failure"] = details
    finally:
        if target is not None:
            try:
                target.close()
                result["held_namespace_target_closed"] = True
            except BaseException as error:
                result["errors"].append({"phase": "target_close", "type": type(error).__name__, "reason": str(error)[:256]})
        if lock is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
                result["action_lock_released"] = True
            except BaseException as error:
                result["errors"].append({"phase": "action_unlock", "type": type(error).__name__})
        for name, owned in (("observation", pool), ("lease", leases)):
            try:
                owned.close_all()
            except BaseException as error:
                result["errors"].append({"phase": name + "_FD_close", "type": type(error).__name__})
            result[name + "_FDs_final"] = owned.summary()
        result["owned_descriptors_final"] = result["observation_FDs_final"]
        if result["errors"]:
            result["ok"] = False
    result["service_reports"] = [
        {"service": service, "argv": list(transport_module.READ_ONLY_COMMANDS[index]),
         "stdout": row.get("stdout"), "stderr": row.get("stderr"), "returncode": row.get("returncode"),
         "complete": row.get("complete"), "joined": row.get("joined"),
         "stream_artifacts_complete": row.get("stream_artifacts_complete", False),
         "interpretation_status": "RAW_CAPTURE_ONLY_NOT_INTERPRETED"}
        for index, service in ((1, "package-dump-package"), (2, "appops-get-user0"))
        if len(result["android_commands"]) > index for row in (result["android_commands"][index],)]
    result["permission_queries_executed"] = any("host_pid" in row for row in result["android_commands"][1:])
    result["status"] = "BEIKE_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE" if result["ok"] else "BEIKE_PERMISSION_OBSERVATION_INCOMPLETE_NO_RETRY"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    before = len(os.listdir("/proc/self/fd"))
    try:
        size = os.stat(args.request, follow_symlinks=False).st_size
        request = parse(read_root_pin({"path": args.request, "bytes": size, "sha256": args.request_sha256}))
        result = run(request)
    except BaseException as error:
        result = {"schema": "pocket4-beike-permission-entry-rejection-v1", "ok": False, "type": type(error).__name__,
                  "reason": str(error)[:512], "automatic_retry": False, "production_ready": False}
    after = len(os.listdir("/proc/self/fd"))
    result.update(process_FDs_before=before, process_FDs_after=after)
    if before != after:
        result["ok"] = False
        result.setdefault("errors", []).append({"reason": "ORIGINAL_WHOLE_PROCESS_FD_GATE_FAILED"})
    raw = canonical(result)
    need(len(raw) <= 524288, "SERVICE_ARTIFACT_BOUND")
    envelope = {"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": sha(raw),
                "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}
    output = canonical(envelope)
    need(len(output) <= 98304, "SERVICE_STDOUT_BOUND")
    print(output.decode(), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
