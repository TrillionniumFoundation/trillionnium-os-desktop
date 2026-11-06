#!/usr/bin/env python3
"""Prepare one private host reader for one actually successful fixed batch.

No submission or claim. No raw service body is read locally by this preparer.
The original failed microG batch cannot qualify here. A separate reviewed
corrective linkage must explicitly supply that future case, in a new revision.
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
CAPTURE = PROJECT / "successor_audit_requests/effective_permissions_45_capture_r1"
PILOT = PROJECT / "successor_audit_requests/beike_permission_pilot_r1/raw-readback-r1"
GATE_SHA = "dc4fffb3f11e8428db732b96cd1925f0bdce239cdce81ff64ab369dc14c751f4"
READER_SHA = "222a42555dead8c8cf72a8de175b6318618db1e2ddab6ee6ddd6eccc7263e5c1"
PACKET_SHA = "902310c86c1bd26cc96d3cd5216f00beea7f15b3a4722f460f6571fb3ba9de35"
MAX_LOGS = 8
MAX_FILE = 262144
MAX_AGGREGATE = 2097152


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def write(folder, name, raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    with (folder / name).open("xb") as stream:
        stream.write(raw)
    need((folder / name).read_bytes() == raw, "NEW_LOCAL_SOURCE_READBACK")
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def definitions(source):
    return {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def load_gate():
    path = CAPTURE / "permission_capture_gate.py"
    raw = path.read_bytes()
    need(len(raw) == 27120 and sha(raw) == GATE_SHA, "EXACT_REVIEWED_CAPTURE_GATE_REQUIRED")
    gate = types.ModuleType("actual_fixed_capture_gate_only"); gate.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), gate.__dict__)
    g, plan, loaded = gate.load_closure()
    return gate, g, plan, loaded


def fixed_logs(completed, row):
    need(completed["batch"] == row["batch"] and completed["target_packages"] == row["targets"] and
         completed.get("whole_47_current_identity_checked") is True and
         completed.get("original_owned_child_pidfd_retirement_verified") is True and
         1 <= len(row["targets"]) <= 4, "ONE_SUCCESSFUL_FIXED_BATCH_CLOSURE")
    reports = completed["service_reports"]
    expected = [(p, service) for p in row["targets"] for service in ("package-dump-package", "appops-get-user0")]
    need([(r["target_package"], r["service"]) for r in reports] == expected and 2 <= len(reports) <= MAX_LOGS,
         "EVERY_TARGET_EXACTLY_TWO_FIXED_LOGS")
    pins, mapping = [], []
    for i, report in enumerate(reports, 2):
        need(report.get("target_user") == 0 and report.get("complete") is True and report.get("joined") is True and
             type(report.get("returncode")) is int and report["returncode"] == 0 and report.get("stream_artifacts_complete") is True,
             "COMPLETE_NORMAL_SERVICE_CAPTURE_REQUIRED")
        pin = report["stdout"]
        need(set(pin) == {"path", "bytes", "sha256"} and pin["path"] == row["output_root"] + "/android-%02d.stdout" % i and
             type(pin["bytes"]) is int and 0 <= pin["bytes"] <= MAX_FILE and len(pin["sha256"]) == 64 and
             all(c in "0123456789abcdef" for c in pin["sha256"]), "FIXED_SUCCESSFUL_BATCH_STDOUT_PATH_AND_BOUND")
        pins.append(dict(pin))
        mapping.append({"target_package": report["target_package"], "target_user": 0, "service": report["service"], "pin": dict(pin)})
    need(len({pin["path"] for pin in pins}) == len(pins) and sum(p["bytes"] for p in pins) <= MAX_AGGREGATE,
         "UNIQUE_PINS_AND_AGGREGATE_ACTUAL_LOG_BOUND")
    return pins, mapping


def render_reader(completed, row):
    pins, mapping = fixed_logs(completed, row)
    raw = (PILOT / "read_pinned_private_permission_logs.py").read_bytes()
    need(len(raw) == 3720 and sha(raw) == READER_SHA, "EXACT_ACTUAL_PRIVATE_PILOT_READER")
    original = raw.decode()
    assignment = next(n for n in ast.parse(original).body if isinstance(n, ast.Assign) and
                      any(isinstance(t, ast.Name) and t.id == "PINS" for t in n.targets))
    source = original.replace(ast.get_source_segment(original, assignment), "PINS = " + repr(tuple(pins)), 1)
    source = source.replace("Read two exact existing Beike service logs; private raw output, no Main command.",
                            "Read one fixed successful batch of existing private service logs; no Main command.")
    binding = {"source_capture_batch": row["batch"], "source_capture_job": completed["job_id"],
        "source_capture_artifact_sha256": completed["artifact_sha256"],
        "source_capture_terminal_sha256": completed["terminal_sha256"],
        "source_capture_outer_stdout_sha256": completed["outer_stdout_sha256"], "target_log_mapping": mapping}
    source = source.replace("PINS = ", "CAPTURE_BINDING = " + repr(binding) + "\n" +
        "ACTUAL_LOG_BYTES = " + str(sum(p["bytes"] for p in pins)) + "\n" +
        "MAX_PRIVATE_STDOUT_BYTES = " + str(2 * sum(p["bytes"] for p in pins) + 32768) + "\nPINS = ", 1)
    source = source.replace("    rows=[]\n", "    need(2<=len(PINS)<=8 and len(PINS)==2*len({r['target_package'] for r in CAPTURE_BINDING['target_log_mapping']}),'EXACT_BATCH_LOG_COUNT')\n"
        "    need(all(type(p['bytes']) is int and 0<=p['bytes']<=262144 for p in PINS) and sum(p['bytes'] for p in PINS)==ACTUAL_LOG_BYTES<=2097152,'FIXED_BATCH_ACTUAL_BYTE_BOUND')\n"
        "    rows=[]\n", 1)
    source = source.replace("pocket4-two-exact-beike-private-service-logs-v1", "pocket4-one-successful-batch-private-permission-logs-v1")
    source = source.replace("'permission_observation_job':'1a1b279845c-fc05-7e2e'", "'capture_binding':CAPTURE_BINDING")
    source = source.replace("    print(canonical(result).decode('ascii'),flush=True)",
        "    raw=canonical(result)\n    need(len(raw)<=MAX_PRIVATE_STDOUT_BYTES,'PRIVATE_BATCH_OUTPUT_BOUND')\n    print(raw.decode('ascii'),flush=True)")
    keep = [name for name in definitions(original) if name != "main"]
    need(keep == ["need", "sha", "canonical", "read_file", "read_host_pin"] and
         all(definitions(original)[name] == definitions(source)[name] for name in keep), "FIVE_ORIGINAL_PER_FILE_READER_DEFINITIONS_MUST_BE_EXACT")
    compile(source, "read_fixed_batch_private_logs.py", "exec")
    return source, original, pins, mapping, binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=int)
    args = parser.parse_args()
    need(1 <= args.batch <= 13, "ONLY_ORIGINAL_FIXED_BATCH_NUMBERS")
    gate, g, plan, loaded = load_gate()
    row = loaded[args.batch]["row"]
    folder = gate.LEDGER / ("batch-%02d" % args.batch)
    # A complete individual capture is required. This readback does not advance
    # the serial ledger, claim any later capture or waive an earlier failure.
    observation = gate.load_record(g, loaded[args.batch], folder)
    need(observation is not None, "NO_READER_FOR_UNSETTLED_CAPTURE")
    completed = observation[0]
    pins, mapping = fixed_logs(completed, row)
    if args.batch == 1:
        need(completed["job_id"] == "1a1b2b86eb1-fc05-7f76" and row["targets"] == ["org.fcitx.fcitx5.android"],
             "EXACT_ALREADY_READ_FCITX_CAPTURE")
        receipt_path = PROJECT / "successor_audit_requests/effective_permissions_private_readback_r1/batch-01-p00/actual-public/READBACK_RECEIPT.derived.json"
        receipt = g.parse(g.read(receipt_path, 65536))
        need(receipt.get("ok") is True and receipt.get("job") == "1a1b2c25ac5-fc05-7f9f" and
             receipt.get("actual_capture_job") == completed["job_id"] and receipt.get("fixed_files") == pins and
             receipt.get("private_stdout_sha256") == "04a066b827cba70c62225088b64ffa032e7a906a29141375a60cc677f393b407",
             "ACTUAL_EXISTING_FCITX_PRIVATE_READBACK_REFERENCE")
        print(json.dumps({"state": "EXISTING_FCITX_READBACK_REUSED_NO_NEW_REQUEST", "capture_job": completed["job_id"],
            "readback_job": receipt["job"], "public_receipt_reference": str(receipt_path),
            "new_reader_created": False, "remote_jobs": 0, "ledger_claims": 0}, sort_keys=True))
        return
    source, original, pins, mapping, binding = render_reader(completed, row)
    packet_raw = (PILOT / "process-request.review-only.json").read_bytes()
    need(len(packet_raw) == 4091 and sha(packet_raw) == PACKET_SHA, "EXACT_ACTUAL_PILOT_HOST_REQUEST_TEMPLATE")
    packet = g.parse(packet_raw)
    packet["args"][-1] = source
    packet["idempotency_key"] = "sidecar-evidence-20261106-fixed-batch-private-permission-logs-r1-b%02d" % args.batch
    out = HERE / ("batch-%02d" % args.batch)
    out.mkdir(mode=0o700)
    rp = write(out, "read_fixed_batch_private_logs.py", source)
    pp = write(out, "process-request.review-only.json", canonical(packet))
    dp = write(out, "reader-against-actual-pilot-reader.diff", "".join(difflib.unified_diff(original.splitlines(True), source.splitlines(True),
               fromfile="actual-pilot-private-reader", tofile="one-settled-batch-private-reader")))
    proposed = {"schema": "pocket4-one-successful-batch-private-log-readback-plan-v1", "source_only": True,
        "capture_binding": binding, "reader": rp, "process_request": pp, "diff": dp, "fixed_files": pins,
        "actual_aggregate_log_bytes": sum(p["bytes"] for p in pins), "maximum_log_count": 8,
        "maximum_one_file_bytes": MAX_FILE, "maximum_aggregate_raw_bytes": MAX_AGGREGATE,
        "maximum_private_stdout_bytes": 2 * sum(p["bytes"] for p in pins) + 32768,
        "original_five_per_file_definitions_unchanged": True,
        "private_destination_required": str(PROJECT.parent / "p4_private_ui/fixed45-permissions-batch-readback-r1" / out.name),
        "raw_private_items": ["complete stdout", "all process_read bodies", "all decoded service logs"],
        "public_items": ["source", "exact capture and file pins", "start and terminal metadata", "hash-only readback receipt"],
        "existing_files_modified": False, "raw_output_repository_publication_admitted": False,
        "whole_process_FD_gate_is_original_count_check": True, "individual_file_and_path_identity_gate_is_full_stat": True,
        "old_single_target_candidate_preserved": True, "old_capture_ledger_advanced": False,
        "remote_jobs": 0, "ledger_claims": 0, "permission_changes": 0, "production_ready": False}
    mp = write(out, "READBACK_PLAN.json", canonical(proposed))
    print(json.dumps({"state": "ONE_BATCH_PRIVATE_READER_PREPARED_NOT_SUBMITTED", "plan": mp, "reader": rp,
                      "process_request": pp, "folder": str(out), "actual_log_bytes": proposed["actual_aggregate_log_bytes"],
                      "remote_jobs": 0, "ledger_claims": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
