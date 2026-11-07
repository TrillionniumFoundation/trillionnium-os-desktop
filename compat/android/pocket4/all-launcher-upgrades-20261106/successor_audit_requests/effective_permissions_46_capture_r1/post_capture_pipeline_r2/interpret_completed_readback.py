#!/usr/bin/env python3
"""Interpret one actually captured and read-back new46 batch offline.

The eight proved literal grammar functions and private reader are imported
unchanged. A missing/failed capture or readback is rejected before private reads.
Only the new actual microG PM pin can receive the inherited 2 MiB exception.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
SELECTOR = (8036, "4b1426f1295b5924f1821709344b2d96109e2e1647c10a7f1a1dca21cfcc298a")
DECODER = (10148, "2e3e0f8d297c3bad50b8e5489a3604783e573f6f52abab51b65c1c9df8680ad9")
PARSER = ("successor_audit_requests/effective_permissions_microg_parser_r1/interpret_microg_exact.py", 20711,
          "c38b558a5c0d1b1a9649d688f0b3318622097f93e0b993ed6e0fb723adf342e1")
CORE_NAMES = ("need", "sha", "unknown", "lines", "section", "parse_package", "parse_appops", "derive")


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def module(path, length, digest):
    raw = path.read_bytes()
    need(len(raw) == length and sha(raw) == digest, "EXACT_PROVEN_OFFLINE_SOURCE_REQUIRED")
    value = types.ModuleType(path.stem)
    value.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), value.__dict__)
    return value, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=int)
    parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args()
    before = len(os.listdir("/proc/self/fd"))
    selector, selector_raw = module(HERE / "prepare_completed_readback.py", *SELECTOR)
    selected = selector.select_complete(args.batch)
    gate, g, capture_plan, loaded, complete, pins, limits, binding = selected
    decoder, decoder_raw = module(HERE / "decode_completed_readback.py", *DECODER)
    grammar, grammar_raw = module(PROJECT / PARSER[0], PARSER[1], PARSER[2])
    folder = HERE / "readbacks" / ("batch-%02d" % args.batch)
    public = folder / "actual-public"
    private = PROJECT.parent / "p4_private_ui/fixed46-permissions-compressed-readback-r2" / folder.name
    for path in (folder, public, private):
        need(path.is_dir() and not path.is_symlink(), "ACTUAL_READBACK_DIRECTORIES_REQUIRED")
    records = {}
    def read_public(name, limit=262144):
        path = folder / name
        data = decoder.read(path, limit)
        records[name] = data
        return data
    plan_raw = read_public("READBACK_PLAN.json", 65536)
    need(sha(plan_raw) == args.plan_sha256, "REVIEWED_ACTUAL_READBACK_PLAN_PIN")
    plan = g.parse(plan_raw)
    need(plan["schema"] == "pocket4-fixed-batch-compressed-private-readback-plan-v2" and
         plan["capture_binding"] == binding and plan["fixed_files"] == pins and plan["per_file_capture_limits"] == limits and
         plan["private_destination_required"] == str(private) and plan["public_actual_directory"] == str(public) and
         plan["maximum_aggregate_body_bytes"] == 2097152 and plan["maximum_compressed_stdout_bytes"] == 1048576 and
         plan["actual_aggregate_log_bytes"] == sum(p["bytes"] for p in pins) and
         plan["maximum_inner_result_bytes"] == 2 * sum(p["bytes"] for p in pins) + 32768,
         "ACTUAL49_CAPTURE_TO_READBACK_BINDING_REQUIRED")
    packet_raw = read_public("process-request.review-only.json", 65536)
    reader_raw = read_public("read_fixed_batch_private_logs.py", 65536)
    for data, key in ((packet_raw, "process_request"), (reader_raw, "reader")):
        need(len(data) == plan[key]["bytes"] and sha(data) == plan[key]["sha256"], "REVIEWED_READBACK_SOURCE_CHANGED")
    packet = g.parse(packet_raw)
    need(packet["args"][-1] == reader_raw.decode() and packet["idempotency_key"] ==
         "pocket4-fixed46-permission-readback-20261107-r2-b%02d" % args.batch, "ACTUAL_FIXED_READER_ARGV_AND_KEY")
    start = g.parse(read_public("actual-public/start.original.txt", 131072))
    job = start["job"]
    need(job["idempotency_key"] == packet["idempotency_key"] and job["host"] == packet["host"] and
         job["executable"] == packet["executable"] and job["args"] == packet["args"] and job["cwd"] == packet["cwd"] and
         job["launch_state"] == "launched" and job["launch_error"] is None and start["launch"]["ok"] is True,
         "ACTUAL_SUCCESSFUL_EXACT_READBACK_START_REQUIRED")
    terminal_raw = read_public("actual-public/terminal.original.json", 65536)
    terminal = g.parse(terminal_raw)
    # Check the real reader terminal before opening any private body.
    need(terminal.get("job_id") == job["id"] and terminal.get("state") == "succeeded" and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == 0 and
         all(terminal.get(k) is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(k) is False for k in ("timed_out", "automatic_retry", "cancelled")) and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_bytes", {}).get("stderr") == {"seen": 0, "stored": 0},
         "ACTUAL_DURABLE_READBACK_SUCCESS_REQUIRED_BEFORE_PRIVATE_READ")
    receipt_raw = read_public("actual-public/READBACK_RECEIPT.derived.json", 65536)
    receipt = g.parse(receipt_raw)
    need(receipt["schema"] == "pocket4-fixed-batch-private-readback-receipt-v2" and receipt["ok"] is True and
         receipt["readback_job"] == job["id"] and receipt["capture_binding"] == binding and
         receipt["plan_sha256"] == sha(plan_raw) and receipt["terminal_sha256"] == sha(terminal_raw) and
         receipt["fixed_files"] == pins and receipt["complete_original_bodies_decoded_and_rehashed"] is True and
         receipt["raw_bodies_published"] is False and receipt["permissions_interpreted"] is False and
         type(receipt["process_FDs_before"]) is int and receipt["process_FDs_before"] == receipt["process_FDs_after"],
         "COMPLETE_ACTUAL_PRIVATE_READBACK_RECEIPT_REQUIRED")
    original_raw = decoder.read(private / "stdout.original.jsonl", 1048576)
    gate.terminal_gate(g, terminal, job["id"], original_raw)
    result, inner, decoded = decoder.decode_envelope(original_raw, plan)
    need(receipt["private_stdout_bytes"] == len(original_raw) and receipt["private_stdout_sha256"] == sha(original_raw) and
         receipt["private_inner_bytes"] == len(inner) and receipt["private_inner_sha256"] == sha(inner) and
         receipt["process_FDs_before"] == result["process_FDs_before"] and
         receipt["process_FDs_after"] == result["process_FDs_after"], "ACTUAL_PRIVATE_ORIGINAL_ENVELOPE_DIFFERS")
    # Retain the original exact-path-and-pin exception mechanism, but bind it
    # only to this new successful batch-02 PM observation, never its predecessor.
    grammar.MICROG_PM_PRIVATE = private / "android-02.stdout" if args.batch == 2 else None
    grammar.MICROG_PM_PIN = pins[0] if args.batch == 2 else None
    bodies = []
    for item, decoded_body in decoded:
        path = private / Path(item["path"]).name
        raw = grammar.read_private(path, item)
        need(raw == decoded_body, "PRIVATE_FILE_AND_COMPLETE_ORIGINAL_READBACK_DIFFER")
        bodies.append(raw)
    outputs = []
    for index, target in enumerate(loaded[args.batch]["row"]["target_identities"]):
        pm_pin, ops_pin = pins[2 * index:2 * index + 2]
        evidence = {"batch": args.batch, "job_id": complete["job_id"], "artifact_sha256": complete["artifact_sha256"],
            "terminal_sha256": complete["terminal_sha256"], "outer_stdout_sha256": complete["outer_stdout_sha256"],
            "PM_private_input": pm_pin, "AppOps_private_input": ops_pin, "raw_capture_passed": True,
            "capture_kind": "NEW_FIXED46_CURRENT49_CAPTURE", "original_failed_capture_reclassified": False,
            "readback_job": job["id"], "readback_terminal_sha256": sha(terminal_raw),
            "readback_receipt_sha256": sha(receipt_raw), "runtime_epoch_sha256": capture_plan["runtime_epoch_sha256"],
            "app_scope_sha256": capture_plan["app_scope"]["sha256"]}
        derived = grammar.derive(bodies[2 * index], bodies[2 * index + 1], target, evidence)
        outputs.append((target["package"], derived))
    need(selector.select_complete(args.batch)[4:] == selected[4:], "CAPTURE_CHANGED_DURING_OFFLINE_INTERPRETATION")
    need(all(decoder.read(folder / name, max(1, len(raw))) == raw for name, raw in records.items()), "PUBLIC_READBACK_INPUT_CHANGED")
    need((HERE / "prepare_completed_readback.py").read_bytes() == selector_raw and
         (HERE / "decode_completed_readback.py").read_bytes() == decoder_raw and
         (PROJECT / PARSER[0]).read_bytes() == grammar_raw, "OFFLINE_SOURCE_CHANGED")
    after = len(os.listdir("/proc/self/fd"))
    need(before == after, "OFFLINE_INTERPRETER_DESCRIPTOR_DIFFERENCE")
    published = []
    for package, result in outputs:
        result["local_interpreter_FDs"] = {"before": before, "after": after}
        raw = (json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode()
        path = public / ("PERMISSIONS." + package + ".derived.json")
        decoder.write_private_new(path, raw)
        published.append({"file": str(path.relative_to(PROJECT)), "bytes": len(raw), "sha256": sha(raw),
            "package": package, "interpretation_status": result["interpretation_status"]})
    report = {"schema": "pocket4-fixed46-offline-literal-interpretation-v1", "batch": args.batch,
        "capture_job": complete["job_id"], "readback_job": job["id"], "outputs": published,
        "original_eight_core_functions": list(CORE_NAMES), "original_eight_core_functions_changed": False,
        "raw_body_repository_publication": False, "usage_timestamps_published": False,
        "new_runtime_queries": 0, "permission_changes": 0, "role_status": "UNKNOWN_NOT_QUERIED",
        "production_ready": False, "local_interpreter_FDs": {"before": before, "after": after}}
    decoder.write_private_new(public / "INTERPRETATION_RECEIPT.derived.json", g.canonical(report) + b"\n")
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
