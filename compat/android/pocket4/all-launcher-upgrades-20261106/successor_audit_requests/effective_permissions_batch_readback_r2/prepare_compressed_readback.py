#!/usr/bin/env python3
"""One fixed, complete batch readback; source-only, private compressed output.

No submission, claim, Main access or service-body read. The explicit corrective
linkage must validate before microG or a later original batch can be selected.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
LINK = PROJECT / "successor_audit_requests/revisions/microg-linked-permission-continuation-r1"
PILOT = PROJECT / "successor_audit_requests/beike_permission_pilot_r1/raw-readback-r1"
LINK_SHA = "bf7ee540d5e64276f1a9490b50da1381a725f52081848ec0d960353acf86c7a8"
READER_SHA = "222a42555dead8c8cf72a8de175b6318618db1e2ddab6ee6ddd6eccc7263e5c1"
PACKET_SHA = "902310c86c1bd26cc96d3cd5216f00beea7f15b3a4722f460f6571fb3ba9de35"
MAX_AGGREGATE = 2097152
MAX_ENVELOPE = 1048576


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def definitions(source):
    return {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}


def load_link():
    raw = (LINK / "linked_permission_gate.py").read_bytes()
    need(len(raw) == 26594 and sha(raw) == LINK_SHA, "EXACT_FULL_JOINT_LINKAGE_SOURCE_REQUIRED")
    link = types.ModuleType("actual_corrective_capture_linkage_only")
    link.__file__ = str(LINK / "linked_permission_gate.py")
    exec(compile(raw, link.__file__, "exec"), link.__dict__)
    context = link.load_linkage()
    return link, context, link.inspect(context)


def select_complete_batch(number, link, context, state):
    need(type(number) is int and 2 <= number <= 13, "ONLY_CORRECTION_OR_ORIGINAL_BATCHES_02_TO_13")
    rows = [row for row in state["completed"] if row["batch"] == number]
    need(len(rows) == 1, "NO_READER_FOR_FAILED_UNKNOWN_OR_UNOBSERVED_BATCH")
    complete = rows[0]
    need(complete.get("whole_47_current_identity_checked") is True and
         complete.get("original_owned_child_pidfd_retirement_verified") is True and
         complete.get("interpretation_status") == "RAW_CAPTURE_ONLY_NOT_INTERPRETED", "ACTUAL_JOINT_COMPLETE_CAPTURE_REQUIRED")
    original = context["loaded"][number]["row"]
    if number == 2:
        need(complete["job_id"] == link.CORRECTION_JOB and complete["target_packages"] == ["com.google.android.gms"] and
             complete.get("evidence_kind") == "INDEPENDENT_CORRECTION_OF_ORIGINAL_FAILED_BATCH" and
             complete.get("original_failed_capture_reclassified") is False, "ONLY_EXACT_CORRECTED_MICROG_CAPTURE")
        root, limits = link.ROOT, [2097152, 262144]
    else:
        need(complete["target_packages"] == original["targets"], "ORIGINAL_FIXED_TARGET_PARTITION_CHANGED")
        root, limits = original["output_root"], [262144] * (2 * len(original["targets"]))
    reports = complete["service_reports"]
    expected = [(p, service) for p in complete["target_packages"] for service in ("package-dump-package", "appops-get-user0")]
    need([(r["target_package"], r["service"]) for r in reports] == expected and 2 <= len(reports) <= 8,
         "EXACT_SUCCESSFUL_BATCH_TWO_SERVICE_LOGS_PER_TARGET")
    pins, mapping = [], []
    for index, (report, cap) in enumerate(zip(reports, limits), 2):
        need(report.get("complete") is True and report.get("joined") is True and report.get("stream_artifacts_complete") is True and
             type(report.get("returncode")) is int and report["returncode"] == 0 and report["target_user"] == 0,
             "ONLY_COMPLETE_SUCCESSFUL_CAPTURE_STREAMS")
        pin = report["stdout"]
        need(set(pin) == {"path", "bytes", "sha256"} and pin["path"] == root + "/android-%02d.stdout" % index and
             type(pin["bytes"]) is int and 0 <= pin["bytes"] <= cap and len(pin["sha256"]) == 64 and
             all(c in "0123456789abcdef" for c in pin["sha256"]), "ONLY_FIXED_SUCCESSFUL_LOG_PATHS_AND_BUDGETS")
        pins.append(dict(pin))
        mapping.append({"target_package": report["target_package"], "target_user": 0, "service": report["service"],
                        "maximum_body_bytes": cap, "pin": dict(pin)})
    need(len(pins) == len(limits) and len({p["path"] for p in pins}) == len(pins) and
         sum(p["bytes"] for p in pins) <= MAX_AGGREGATE, "EXACT_BOUNDED_BATCH_AGGREGATE")
    binding = {"source_capture_batch": number, "source_capture_job": complete["job_id"],
        "source_capture_artifact_sha256": complete["artifact_sha256"], "source_capture_outer_stdout_sha256": complete["outer_stdout_sha256"],
        "source_capture_terminal_sha256": complete["terminal_sha256"], "target_log_mapping": mapping,
        "microG_correction_linkage": context["linkage"], "raw_capture_is_semantic_grant_proof": False,
        "original_failed_capture_reclassified": False, "role_status": "UNKNOWN_NOT_QUERIED"}
    return pins, limits, binding


def render_reader(pins, limits, binding):
    raw = (PILOT / "read_pinned_private_permission_logs.py").read_bytes()
    need(len(raw) == 3720 and sha(raw) == READER_SHA, "ORIGINAL_PROVED_PILOT_PRIVATE_READER")
    original = raw.decode()
    source = original.replace("import hashlib\n", "import base64\nimport zlib\nimport hashlib\n", 1)
    source = source.replace("Read two exact existing Beike service logs; private raw output, no Main command.",
                            "Read one exact settled batch of private service logs; compress whole original result, no Main command.")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == "PINS" for t in n.targets))
    source = source.replace(ast.get_source_segment(source, node),
        "PINS = " + repr(tuple(pins)) + "\nCAPTURE_BINDING = " + repr(binding) +
        "\nBODY_LIMITS = " + repr(limits) + "\nACTUAL_LOG_BYTES = " + str(sum(p["bytes"] for p in pins)) +
        "\nMAX_INNER_BYTES = " + str(2 * sum(p["bytes"] for p in pins) + 32768) +
        "\nMAX_COMPRESSED_STDOUT_BYTES = " + str(MAX_ENVELOPE), 1)
    source = source.replace("    rows=[]\n", "    need(2<=len(PINS)<=8 and len(PINS)==len(BODY_LIMITS),'EXACT_FIXED_BATCH_LOG_COUNT')\n"
        "    need(all(type(p['bytes']) is int and 0<=p['bytes']<=cap for p,cap in zip(PINS,BODY_LIMITS)) and sum(p['bytes'] for p in PINS)==ACTUAL_LOG_BYTES<=2097152,'FIXED_BATCH_CAPTURE_BYTE_LIMITS')\n"
        "    rows=[]\n", 1)
    source = source.replace("pocket4-two-exact-beike-private-service-logs-v1", "pocket4-fixed-batch-private-service-log-readback-v2")
    source = source.replace("'permission_observation_job':'1a1b279845c-fc05-7e2e'", "'capture_binding':CAPTURE_BINDING")
    source = source.replace("    print(canonical(result).decode('ascii'),flush=True)",
        "    raw=canonical(result)\n"
        "    need(len(raw)<=MAX_INNER_BYTES,'COMPLETE_PRIVATE_RESULT_BYTE_BOUND')\n"
        "    compressed=zlib.compress(raw,9)\n"
        "    envelope=canonical({'encoding':'zlib-base64','artifact_bytes':len(raw),'artifact_sha256':sha(raw),'data':base64.b64encode(compressed).decode('ascii')})\n"
        "    need(len(envelope)+1<=MAX_COMPRESSED_STDOUT_BYTES,'COMPRESSED_PRIVATE_STDOUT_BOUND_NO_PARTIAL_PUBLICATION')\n"
        "    print(envelope.decode('ascii'),flush=True)")
    old_defs, new_defs = definitions(original), definitions(source)
    preserved = ["need", "sha", "canonical", "read_file", "read_host_pin"]
    need(set(old_defs) == set(new_defs) == set(preserved + ["main"]) and
         all(old_defs[name] == new_defs[name] for name in preserved), "FIVE_ORIGINAL_PER_FILE_FUNCTIONS_UNCHANGED")
    compile(source, "read_fixed_batch_private_logs.py", "exec")
    return source, original


def write_new(folder, name, raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    with (folder / name).open("xb") as stream:
        stream.write(raw)
    need((folder / name).read_bytes() == raw, "NEW_LOCAL_SOURCE_READBACK")
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=int)
    args = parser.parse_args()
    if args.batch == 1:
        raise RuntimeError("FCITX_ALREADY_FULLY_READ_BACK_USE_EXISTING_ACTUAL_RECEIPT_NO_NEW_REQUEST")
    link, context, state = load_link()
    pins, limits, binding = select_complete_batch(args.batch, link, context, state)
    source, original = render_reader(pins, limits, binding)
    packet_raw = (PILOT / "process-request.review-only.json").read_bytes()
    need(len(packet_raw) == 4091 and sha(packet_raw) == PACKET_SHA, "ORIGINAL_FIXED_HOST_READER_REQUEST")
    packet = json.loads(packet_raw)
    packet["args"][-1] = source
    packet["idempotency_key"] = "sidecar-evidence-20261106-fixed-batch-private-permission-zlib-r2-b%02d" % args.batch
    out = HERE / ("batch-%02d" % args.batch)
    out.mkdir(mode=0o700)
    rp = write_new(out, "read_fixed_batch_private_logs.py", source)
    pp = write_new(out, "process-request.review-only.json", canonical(packet))
    dp = write_new(out, "reader-against-actual-pilot.diff", "".join(difflib.unified_diff(original.splitlines(True), source.splitlines(True),
        fromfile="actual-pilot-five-file-reader-functions", tofile="one-actual-complete-batch-zlib-envelope")))
    private = PROJECT.parent / "p4_private_ui/fixed45-permissions-compressed-readback-r2" / out.name
    plan = {"schema": "pocket4-fixed-batch-compressed-private-readback-plan-v2", "source_only": True,
        "reader": rp, "process_request": pp, "diff": dp, "capture_binding": binding,
        "fixed_files": pins, "per_file_capture_limits": limits, "actual_aggregate_log_bytes": sum(p["bytes"] for p in pins),
        "maximum_aggregate_body_bytes": MAX_AGGREGATE, "maximum_inner_result_bytes": 2 * sum(p["bytes"] for p in pins) + 32768,
        "maximum_compressed_stdout_bytes": MAX_ENVELOPE, "complete_original_result_compressed": True,
        "partial_output_admitted": False, "five_original_per_file_functions_unchanged": True,
        "per_file_held_and_path_full_stat_checks": True, "whole_process_FD_gate_is_original_count_check": True,
        "private_destination_required": str(private), "private_stdout_name": "stdout.original.jsonl",
        "public_actual_directory": str(out / "actual-public"),
        "raw_output_repository_publication_admitted": False,
        "old_single_reader_and_uncompressed_batch_candidate_preserved": True,
        "existing_capture_ledger_modified": False, "remote_jobs": 0, "actual_claims": 0,
        "permission_changes": 0, "role_status": "UNKNOWN_NOT_QUERIED", "production_ready": False}
    mp = write_new(out, "READBACK_PLAN.json", canonical(plan))
    print(json.dumps({"state": "ONE_COMPLETE_BATCH_PRIVATE_READER_PREPARED_NOT_SUBMITTED", "plan": mp,
        "reader": rp, "process_request": pp, "actual_raw_log_bytes": plan["actual_aggregate_log_bytes"],
        "remote_jobs": 0, "actual_claims": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
