def load_closure():
    g = primitives()
    raw = g.read(HERE / "CAPTURE_PLAN.json", 262144)
    need(len(raw) == PLAN_BYTES and sha(raw) == PLAN_SHA, "FROZEN_PERMISSION46_PLAN_CHANGED")
    plan = g.parse(raw)
    need(plan["schema"] == "pocket4-fixed46-permission-raw-capture-plan-v1" and len(plan["batches"]) == 14 and
         plan["identity_context_packages"] == 49 and plan["service_target_packages"] == 46 and
         plan["runtime_ledger_relative_path"] == str(LEDGER.relative_to(PROJECT)) and
         plan["total_Android_readonly_commands"] == 106 and plan["automatic_retry"] is False,
         "EXACT_NEW46_PERMISSION_TASK_PLAN_REQUIRED")
    old_raw = local_pin(g, plan["original_gate"])
    old = module(old_raw, PROJECT / plan["original_gate"]["file"], "preserved45_source_baseline_only")
    _, old_plan, old_loaded = old.load_closure()
    binding_raw = local_pin(g, plan["binding_validator"], HERE)
    bound = module(binding_raw, HERE / plan["binding_validator"]["file"], "exact_actual49_binding_validator").validate_binding()
    need(bound["summary"] == plan["actual49_binding"] and bound["summary"]["scope"] == plan["app_scope"] and
         bound["expected_guard"] == old_loaded[1]["expected_guard"] and plan["guard"] == old_plan["guard"],
         "REAL_INSTALL_AND_SCOPE_READBACK_OR_ORIGINAL_RUNTIME_BASELINE_CHANGED")
    scope, components = bound["scope"], bound["components"]
    original = g.parse(local_pin(g, plan["original_partition"]))
    groups = [row["packages"] for row in original["batches"]] + [["com.example.ndk_tests"]]
    targets = [package for group in groups for package in group]
    need(len(groups) == 14 and len(targets) == len(set(targets)) == 46 and
         targets == plan["target_packages"] and sorted(targets) == bound["launchers"] and
         len(scope["apps"]) == 49 and len(components) == 46 and
         plan["runtime_epoch_sha256"] == scope["runtime_epoch_sha256"],
         "ORIGINAL13_PLUS_NDK14_AND_ACTUAL46_MEMBERSHIP_REQUIRED")
    for pin in plan["preserved_old45_stop"]:
        local_pin(g, pin)
    templates = {key: local_pin(g, pin) for key, pin in plan["templates"].items()}
    old_owner = remote_local_pin(g, old_plan["batches"][0]["wrapper"],
                                 "successor_audit_requests/effective_permissions_45_capture_r1/" + old_plan["batches"][0]["wrapper_file"], PROJECT)
    baseline_defs = definitions(old_owner)
    loaded = {}
    for number, row in enumerate(plan["batches"], 1):
        group = groups[number - 1]
        need(type(row["batch"]) is int and row["batch"] == number and row["targets"] == group and
             row["original_partition_batch"] == (number if number <= 13 else None), "EXACT_PARTITION_MEMBERSHIP_REQUIRED")
        folder = "batch-%02d/" % number
        needed_commands = [["/system/bin/cmd", "package", "help"]]
        for package in group:
            needed_commands.extend((["/system/bin/cmd", "package", "dump-package", package],
                                    ["/system/bin/cmd", "appops", "get", "--user", "0", package]))
        stage_root = "/home/alex/work/pocket4-launcher46-permissions-source-20261107-r1-b%02d" % number
        output_root = "/home/alex/work/pocket4-launcher46-permissions-observation-20261107-r1-b%02d" % number
        need(row["Android_commands"] == needed_commands and row["native_operations"] == ["status", "applications", "status"] and
             row["source_root"] == stage_root and row["output_root"] == output_root and
             row["idempotency_key"] == "pocket4-fixed46-permissions-20261107-r1-b%02d" % number,
             "CLOSED_FIXED_QUERY_LIST_AND_UNIQUE_ROOTS_AND_KEY_REQUIRED")
        sources = [remote_local_pin(g, row[key], row[key + "_file"]) for key in ("worker", "transport", "wrapper")]
        request = g.parse(remote_local_pin(g, row["request"], row["request_file"]))
        wc, tc, oc = map(constants, sources)
        identities = [{key: scope["apps"][p][key] for key in ("package", "uid", "version_code")} for p in group]
        help_pin = {"path": stage_root + "/inputs/cmd-appops-help.original.txt", "bytes": 1309,
                    "sha256": "95e3137d6acd3d920eb74f5d726a59232e6db9cb4efe8a4fedd6139074cb56cc"}
        need(request == {"schema": "pocket4-fixed46-launcher-permission-capture-request-v1", "guard": plan["guard"],
            "app_scope": plan["app_scope"], "packages": sorted(scope["apps"]), "worker": row["worker"], "transport": row["transport"],
            "output_root": output_root, "target_packages": group, "target_user": 0, "batch": number, "appops_help": help_pin},
            "EXACT49_REQUEST_REQUIRED")
        need(row["target_identities"] == identities and wc["SOURCE_SEALED"] is True and wc["NEW_HELPER"] == bound["summary"]["new_helper"] and
             wc["TARGET_PACKAGES"] == group and wc["BATCH_NUMBER"] == number and wc["ACTUAL46_COMPONENTS"] == components and
             list(wc["LAUNCHERS"]) == bound["launchers"] and wc["PACKAGES"] == sorted(scope["apps"]) and
             wc["APP_SCOPE"] == plan["app_scope"] and wc["GUARD"] == plan["guard"] and
             wc["STAGE"] == stage_root and wc["OUTPUT"] == output_root and wc["TRANSPORT"] == row["transport"] and
             wc["APP_OPS_HELP"] == help_pin and [list(c) for c in tc["READ_ONLY_COMMANDS"]] == needed_commands and
             oc["CONFIG"]["worker"] == row["worker"] and oc["CONFIG"]["request"] == row["request"] and
             oc["CONFIG"]["kind"] == "services" and oc["CONFIG"]["stage_root"] == stage_root,
             "EXACT_SCOPE_TARGETS_TRANSPORT_AND_WRAPPER_REQUIRED")
        template = templates["worker_microg" if number == 2 else "worker_normal"]
        need(definitions(sources[0]) == definitions(template) and definitions(sources[1]) == definitions(templates["transport"]),
             "FROZEN_WORKER_OR_TRANSPORT_DEFINITION_CHANGED")
        owner_defs = definitions(sources[2])
        need(set(owner_defs) == set(baseline_defs) and all(owner_defs[name] == baseline_defs[name]
             for name in baseline_defs if name != "worker_gate") and
             owner_defs["worker_gate"] == definitions(local_pin(g, plan["owner_gate_fragment"], HERE))["worker_gate"],
             "ORIGINAL_OWNED_LIFETIME_OR_REVIEWED_NEW_GATE_CHANGED")
        policy = constants(templates["worker_microg"])["CAPTURE_POLICY"] if number == 2 else None
        expected_binding = {"guard": bound["expected_guard"], "app_scope": plan["app_scope"], "packages": sorted(scope["apps"]),
            "batch": number, "targets": group, "identities": identities, "command_count": len(needed_commands),
            "native_comparison": {"actual_framework_resolver_reference_job": "1a1b307f521-fc05-807a", "expected_count": 46,
                "observed_count": 46, "added_components": [], "missing_components": [], "framework_resolver_requeried_by_this_worker": False},
            "microg_capture_policy": policy}
        need(oc["CAPTURE_BINDING"] == expected_binding and row["microg_capture_policy"] == policy,
             "EXACT_OWNED_CAPTURE_BINDING_REQUIRED")
        stager_raw = local_pin(g, row["stager"], HERE)
        stage_constants = constants(stager_raw)
        need(stage_constants["ROOT"] == stage_root and stage_constants["FILES"] == row["stage_files"] and
             definitions(stager_raw) == definitions(templates["stager"]), "EXACT_ORIGINAL_SOURCE_STAGE_REQUIRED")
        payload_raw = g.read(HERE / folder / "stage.stdin.original.json", 262144)
        payload = g.parse(payload_raw)
        need(set(payload) == {"schema", "files"} and payload["schema"] == "pocket4-fixed-launcher-permission-source-stage-v1" and
             len(payload["files"]) == len(row["stage_files"]) == 5, "EXACT_STAGE_PAYLOAD_REQUIRED")
        for item, pin in zip(payload["files"], row["stage_files"]):
            body = item["text"].encode("utf-8")
            need(set(item) == {"name", "text"} and item["name"] == pin["name"] and len(body) == pin["bytes"] and sha(body) == pin["sha256"] and
                 g.read(HERE / folder / pin["name"], 262144) == body, "FULL_STAGE_TEXT_MUST_MATCH_REVIEWED_SOURCE")
        packet = g.parse(local_pin(g, row["process_request"], HERE))
        need(packet == {"host": "pocket4", "executable": "/usr/bin/sudo", "args": ["-n", "/usr/bin/python3", "-I", "-B", "-c", stager_raw.decode()],
            "cwd": "/", "stdin": payload_raw.decode(), "cpu_quota_percent": 100, "memory_max_bytes": 1073741824, "nice": 10,
            "timeout_seconds": 1100, "idempotency_key": row["idempotency_key"]}, "EXACT_SINGLE_EXISTING_HOST_PROCESS_REQUEST_REQUIRED")
        wrapper = module(sources[2], HERE / row["wrapper_file"], "batch46_%02d_local_gate" % number)
        loaded[number] = {"row": row, "request": request, "wrapper": wrapper, "expected_guard": bound["expected_guard"]}
    return g, plan, loaded
