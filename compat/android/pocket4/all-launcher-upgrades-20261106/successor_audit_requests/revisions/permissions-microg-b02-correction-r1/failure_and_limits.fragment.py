def verify_original_failure(records):
    """Preserve the exact failed observation; a saved prefix is never full output."""
    need(set(records) == set(FAILURE_INPUTS), "ALL_ORIGINAL_FAILED_INPUTS_REQUIRED")
    for key, raw in records.items():
        pin = FAILURE_INPUTS[key]
        need(type(raw) is bytes and len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "ORIGINAL_FAILURE_INPUT_PIN_CHANGED")
    artifact, terminal, stop = (parse(records[key]) for key in ("artifact", "terminal", "gate_stop"))
    need(terminal.get("job_id") == ORIGINAL_FAILURE["job_id"] and terminal.get("state") == "failed" and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == 1 and
         all(terminal.get(k) is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(k) is False for k in ("timed_out", "automatic_retry", "cancelled")) and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_bytes") == {"stdout": {"seen": len(records["outer"]), "stored": len(records["outer"])},
                                       "stderr": {"seen": 0, "stored": 0}}, "ORIGINAL_FAILED_DURABLE_TERMINAL_MUST_REMAIN")
    need(stop.get("state") == "STOP_FAILED_OR_UNVERIFIED_BATCH" and stop.get("batch") == 2 and
         stop.get("original_failure_must_remain") is True and stop.get("automatic_retry") is False,
         "ORIGINAL_SERIAL_GATE_STOP_MUST_REMAIN")
    lines = records["outer"].splitlines()
    need(len(lines) == 2, "ORIGINAL_STAGE_AND_OWNED_OUTER_REQUIRED")
    stage, outer = (parse(line) for line in lines)
    need(stage.get("source_stage_ok") is True and outer.get("ok") is False and outer.get("kind") == "services" and
         outer.get("status") == "READONLY_OBSERVATION_OR_LIFETIME_INCOMPLETE_NO_RETRY" and outer.get("automatic_retry") is False,
         "ORIGINAL_FAILED_OUTER_NOT_RECLASSIFIED")
    life, child = outer["child_lifecycle"], outer["child_result"]
    need(type(life.get("returncode")) is int and life["returncode"] == 1 and
         all(life.get(k) is True for k in ("pidfd_acquired", "pidfd_exit_observed", "pidfd_closed", "parent_descriptors_restored")) and
         life.get("timeout") is False and life.get("owned_child_sigkill_count") == 0 and life.get("errors") == [] and
         child.get("ok") is False and child.get("worker_returncode") == 1 and
         child.get("frozen_descriptors_before_worker") == child.get("final_descriptors") and
         "frozen_descriptors_after_worker" not in child and child.get("manual_library_FD_close") is False and child.get("unknown_FDs_closed") == 0,
         "ORIGINAL_FAILED_WORKER_OWNED_RETIREMENT_REQUIRED")
    encoded = child["worker_stdout_original"].encode("utf-8")
    need(len(encoded) == child["worker_stdout_bytes"] and sha(encoded) == child["worker_stdout_sha256"], "ORIGINAL_WORKER_STREAM_PIN")
    envelope = parse(encoded)
    need(set(envelope) == {"encoding", "artifact_bytes", "artifact_sha256", "data"} and envelope["encoding"] == "zlib-base64" and
         envelope["artifact_bytes"] == len(records["artifact"]) and envelope["artifact_sha256"] == sha(records["artifact"]),
         "ORIGINAL_WORKER_ENVELOPE_PIN")
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(base64.b64decode(envelope["data"], validate=True), 524289)
    need(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data and decoded == records["artifact"],
         "ORIGINAL_WORKER_ENVELOPE_MUST_DECODE_TO_SAME_FAILED_ARTIFACT")
    need(artifact.get("ok") is False and artifact.get("status") == "FIXED_LAUNCHER_PERMISSION_CAPTURE_INCOMPLETE_NO_RETRY" and
         artifact.get("errors") == [{"reason": "HOST_COMMAND_TIMEOUT", "type": "TransportTimeout"}] and
         artifact.get("Android_namespace_commands") == 2 and len(artifact.get("android_commands", [])) == 2 and
         artifact.get("scope_guard_after") is None, "ORIGINAL_FAILED_CAPTURE_AND_MISSING_FINAL_SCOPE_REQUIRED")
    command = artifact["android_commands"][1]
    need(tuple(command["argv"][-4:]) == CORRECTION_COMMANDS[1] and command.get("complete") is False and
         command.get("errors") == [{"code": "CHILD_OUTPUT_BOUND", "type": "RuntimeError"}] and command.get("returncode") == -9 and
         command.get("joined") is True and command.get("termination_attempted") is True and
         command.get("stdout_eof") is False and command.get("stderr_eof") is False and
         command.get("stdout_bytes") == 262145 and command.get("stdout") == ORIGINAL_FAILURE["captured_stdout_prefix"] and
         command.get("stream_artifacts_complete") is True and
         len(artifact.get("service_reports", [])) == 1 and artifact["service_reports"][0].get("complete") is False,
         "ORIGINAL_CAP_PLUS_ONE_PREFIX_IS_INCOMPLETE_NOT_PERMISSION_PROOF")
    for key in ("owned_descriptors_final", "observation_FDs_final", "lease_FDs_final"):
        row = artifact[key]
        need(type(row["acquired"]) is int and row["acquired"] > 0 and row["acquired"] == row["closed"] and
             row["remaining"] == 0 and row["errors"] == [], "ORIGINAL_FAILED_RESOURCES_MUST_BE_RETIRED")
    return ORIGINAL_FAILURE


def capture_limits_for(index, argv):
    """A 2 MiB stdout budget exists for only the second exact microG dump."""
    need(type(index) is int and 1 <= index <= 3, "EXACT_THREE_READ_COMMANDS_ONLY")
    command = CORRECTION_COMMANDS[index - 1]
    need(tuple(argv[-len(command):]) == command, "EXACT_READ_COMMAND_SUFFIX_REQUIRED")
    return dict(CAPTURE_POLICY["stream_limits"][index - 1])

