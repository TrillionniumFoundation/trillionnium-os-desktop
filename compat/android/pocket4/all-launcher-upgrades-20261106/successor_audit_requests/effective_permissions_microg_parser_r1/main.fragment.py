def private_input_limit(path, pin):
    # Only this one fully captured microG PM body gets the corrected budget.
    return 2097152 if Path(path) == MICROG_PM_PRIVATE and pin == MICROG_PM_PIN else 262144


def public_inputs(g):
    raw = g.read(HERE / "INPUT_CLOSURE.json", 65536)
    need(len(raw) == INPUT_BYTES and sha(raw) == INPUT_SHA, "EXACT_PUBLIC_INTERPRETATION_INPUT_CLOSURE")
    closure = g.parse(raw)
    need(closure["schema"] == "pocket4-microg-exact-private-parser-inputs-v1" and
         closure["private_body_contents_included"] is False, "PUBLIC_METADATA_ONLY_CLOSURE")
    records = {}
    for pin in closure["files"]:
        need(set(pin) == {"file", "bytes", "sha256"} and type(pin["file"]) is str and not pin["file"].startswith("/") and
             all(part not in ("", ".", "..") for part in pin["file"].split("/")), "CLOSED_LOCAL_PUBLIC_FILE_PIN")
        data = g.read(PROJECT / pin["file"], 262144)
        need(len(data) == pin["bytes"] and sha(data) == pin["sha256"], "PUBLIC_SOURCE_OR_ACTUAL_RECEIPT_CHANGED")
        records[pin["file"]] = data
    return records


def main():
    need(len(sys.argv) == 1, "ONLY_FIXED_MICROG_OBSERVATION_NO_ARGUMENT_SCOPE")
    before_fds = len(os.listdir("/proc/self/fd"))
    link_path = PROJECT / LINK_FILE
    link_raw = link_path.read_bytes()
    need(len(link_raw) == 26594 and sha(link_raw) == LINK_SHA, "ACTUAL_FULL_JOINT_CAPTURE_LINKAGE_REQUIRED")
    spec = importlib.util.spec_from_file_location("fixed_microg_full_joint_linkage", link_path)
    link = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(link)
    context = link.load_linkage()
    g = context["g"]
    records = public_inputs(g)
    completed, observed, _, _ = context["correction"]
    need(completed["job_id"] == CAPTURE_JOB and completed["target_packages"] == ["com.google.android.gms"] and
         completed["whole_47_current_identity_checked"] is True and completed["original_owned_child_pidfd_retirement_verified"] is True and
         completed["original_failed_capture_reclassified"] is False, "ONLY_ACTUAL_COMPLETE_MICROG_CORRECTION")
    reports = completed["service_reports"]
    need([r["service"] for r in reports] == ["package-dump-package", "appops-get-user0"] and
         [r["stdout"] for r in reports] == [MICROG_PM_PIN, MICROG_APPOPS_PIN], "EXACT_TWO_ACTUAL_MICROG_CAPTURE_PINS")
    target = context["loaded"][2]["row"]["target_identities"]
    need(target == [{"package": "com.google.android.gms", "uid": 10118, "version_code": 252432034}], "ACTUAL_MICROG_UID_AND_VERSION")
    def record(name):
        return records[str((READBACK / name).relative_to(PROJECT))]
    plan = g.parse(record("READBACK_PLAN.json"))
    receipt = g.parse(record("actual-public/READBACK_RECEIPT.derived.json"))
    terminal_raw = record("actual-public/terminal.original.json")
    terminal = g.parse(terminal_raw)
    start = g.parse(record("actual-public/start.original.txt"))
    packet = g.parse(record("process-request.review-only.json"))
    need(plan["fixed_files"] == receipt["fixed_files"] == [MICROG_PM_PIN, MICROG_APPOPS_PIN] and
         plan["per_file_capture_limits"] == [2097152, 262144] and
         plan["capture_binding"] == receipt["capture_binding"] and
         receipt["capture_binding"]["microG_correction_linkage"] == context["linkage"] and
         receipt["schema"] == "pocket4-fixed-batch-private-readback-receipt-v2" and receipt["ok"] is True and
         receipt["readback_job"] == READBACK_JOB and receipt["terminal_sha256"] == sha(terminal_raw) and
         receipt["plan_sha256"] == sha(record("READBACK_PLAN.json")) and
         receipt["complete_original_bodies_decoded_and_rehashed"] is True and receipt["raw_bodies_published"] is False and
         receipt["permissions_interpreted"] is False and receipt["process_FDs_before"] == receipt["process_FDs_after"] == 4,
         "ACTUAL_COMPLETE_PRIVATE_READBACK_MUST_PRECEDE_INTERPRETATION")
    need(terminal["job_id"] == READBACK_JOB and terminal["state"] == "succeeded" and type(terminal["exit_code"]) is int and terminal["exit_code"] == 0 and
         all(terminal[k] is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal[k] is False for k in ("timed_out", "cancelled", "automatic_retry")) and
         terminal["log_truncated"] == {"stdout": False, "stderr": False} and terminal["log_errors"] == {"stdout": None, "stderr": None} and
         terminal["log_bytes"] == {"stdout": {"seen": receipt["private_stdout_bytes"], "stored": receipt["private_stdout_bytes"]},
                                  "stderr": {"seen": 0, "stored": 0}}, "ACTUAL_DURABLE_COMPLETE_READBACK_TERMINAL")
    job = start["job"]
    need(job["id"] == READBACK_JOB and job["idempotency_key"] == packet["idempotency_key"] and job["host"] == packet["host"] and
         job["executable"] == packet["executable"] and job["args"] == packet["args"] and job["cwd"] == packet["cwd"] and
         job["launch_state"] == "launched" and job["launch_error"] is None and start["launch"]["ok"] is True,
         "EXACT_ACTUAL_READBACK_JOB_AND_SOURCE")
    # Only here, after both actual successful jobs have been verified, read the
    # two full private bodies. The original literal parsing functions are used.
    pm = read_private(MICROG_PM_PRIVATE, MICROG_PM_PIN)
    ops = read_private(MICROG_APPOPS_PRIVATE, MICROG_APPOPS_PIN)
    evidence = {"batch": 2, "job_id": CAPTURE_JOB, "artifact_sha256": completed["artifact_sha256"],
        "terminal_sha256": completed["terminal_sha256"], "PM_private_input": MICROG_PM_PIN, "AppOps_private_input": MICROG_APPOPS_PIN,
        "raw_capture_passed": True, "capture_kind": "INDEPENDENT_MICROG_B02_CORRECTION", "original_failed_capture_reclassified": False,
        "readback_job": READBACK_JOB, "readback_terminal_sha256": sha(terminal_raw),
        "readback_receipt_sha256": sha(record("actual-public/READBACK_RECEIPT.derived.json")),
        "runtime_epoch_sha256": observed["guard_before"]["runtime_epoch_sha256"],
        "app_scope_sha256": observed["app_scope_reference"]["sha256"]}
    result = derive(pm, ops, target[0], evidence)
    need(records == public_inputs(g), "PUBLIC_INPUTS_CHANGED_DURING_LOCAL_INTERPRETATION")
    after_fds = len(os.listdir("/proc/self/fd"))
    need(before_fds == after_fds, "LOCAL_INTERPRETER_DESCRIPTOR_DIFFERENCE")
    result["local_interpreter_FDs"] = {"before": before_fds, "after": after_fds}
    result["exact_microG_PM_body_budget_exception"] = {"pin": MICROG_PM_PIN, "maximum_bytes": 2097152,
        "all_other_private_inputs_maximum_bytes": 262144, "parser_core_changed": False}
    output = HERE / "actual/PERMISSIONS.derived.json"
    need(output.parent.is_dir() and not output.parent.is_symlink(), "EXISTING_LOCAL_DERIVED_OUTPUT_PARENT")
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, "DERIVED_OUTPUT_WRITE_PROGRESS")
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(output.read_bytes() == raw, "DERIVED_OUTPUT_READBACK")
    print(json.dumps({"output": str(output), "bytes": len(raw), "sha256": sha(raw),
        "interpretation_status": result["interpretation_status"], "raw_bodies_exported": False, "runtime_queries": 0,
        "local_interpreter_FDs": result["local_interpreter_FDs"]}, sort_keys=True))
    return 0
