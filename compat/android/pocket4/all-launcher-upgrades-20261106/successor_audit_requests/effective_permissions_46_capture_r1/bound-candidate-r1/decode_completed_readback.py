#!/usr/bin/env python3
"""Decode one complete actual private readback after its durable terminal.

All inputs have fixed batch paths. Complete raw stdout and decoded bodies remain
outside the repository. Public output contains pins and observed reader metadata.
This tool does not interpret any permission, AppOps mode or role.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import zlib

HERE = Path(__file__).resolve().parent / 'readbacks'
PROJECT = Path(__file__).resolve().parents[3]
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(RuntimeError("NONFINITE_JSON")))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def read(path, limit, allow_empty=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and (0 if allow_empty else 1) <= before.st_size <= limit, "BOUNDED_LOCAL_REGULAR_INPUT")
        raw = bytearray()
        while len(raw) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after, current = os.fstat(fd), path.stat(follow_symlinks=False)
        keys = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        need(len(raw) == before.st_size and all(getattr(before, k) == getattr(after, k) == getattr(current, k) for k in keys), "LOCAL_INPUT_CHANGED")
        return bytes(raw)
    finally:
        os.close(fd)


def decode_envelope(raw, plan):
    need(0 < len(raw) <= plan["maximum_compressed_stdout_bytes"] and len(raw.splitlines()) == 1,
         "ONE_COMPLETE_BOUNDED_COMPRESSED_STDOUT")
    envelope = parse(raw)
    need(type(envelope) is dict and set(envelope) == {"encoding", "artifact_bytes", "artifact_sha256", "data"} and
         envelope["encoding"] == "zlib-base64" and type(envelope["artifact_bytes"]) is int and
         0 < envelope["artifact_bytes"] <= plan["maximum_inner_result_bytes"], "EXACT_PRIVATE_ENVELOPE_PROTOCOL")
    compressed = base64.b64decode(envelope["data"], validate=True)
    decoder = zlib.decompressobj()
    inner = decoder.decompress(compressed, plan["maximum_inner_result_bytes"] + 1)
    need(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data and
         len(inner) == envelope["artifact_bytes"] <= plan["maximum_inner_result_bytes"] and
         sha(inner) == envelope["artifact_sha256"], "COMPLETE_DECOMPRESSED_ORIGINAL_BYTES_REQUIRED")
    result = parse(inner)
    need(canonical(result) == inner, "ORIGINAL_CANONICAL_PRIVATE_RESULT_REQUIRED")
    need(result.get("schema") == "pocket4-fixed-batch-private-service-log-readback-v2" and result.get("ok") is True and
         result.get("capture_binding") == plan["capture_binding"] and type(result.get("process_FDs_before")) is int and
         result["process_FDs_before"] >= 3 and result["process_FDs_before"] == result.get("process_FDs_after") and
         all(type(result.get(k)) is int and result[k] == 0 for k in ("Main_reads", "native_commands", "Android_commands", "aapt_commands",
              "UI_actions", "installs", "namespace_entries", "permission_changes")) and
         all(result.get(k) is False for k in ("existing_files_modified", "action_lock_acquired", "automatic_retry",
              "original_failed_audit_reclassified", "raw_output_repository_publication_admitted")) and
         result.get("raw_output_may_contain_private_state") is True, "COMPLETE_READONLY_PRIVATE_READER_RESULT")
    rows = result["files"]
    need(type(rows) is list and len(rows) == len(plan["fixed_files"]), "EXACT_FIXED_PRIVATE_FILE_COUNT")
    decoded = []
    for row, pin in zip(rows, plan["fixed_files"]):
        need(set(row) == {"path", "bytes", "sha256", "encoding", "bytes_hex", "held_file_and_path_rechecked"} and
             {k: row[k] for k in ("path", "bytes", "sha256")} == pin and row["encoding"] == "hex" and
             row["held_file_and_path_rechecked"] is True and type(row["bytes_hex"]) is str and len(row["bytes_hex"]) == 2 * pin["bytes"],
             "FIXED_FULL_FILE_PIN_AND_PATH_RECHECK_REQUIRED")
        body = bytes.fromhex(row["bytes_hex"])
        need(len(body) == pin["bytes"] and sha(body) == pin["sha256"], "DECOMPRESSED_SERVICE_BODY_HASH_MISMATCH")
        decoded.append((pin, body))
    need(sum(len(body) for _, body in decoded) == plan["actual_aggregate_log_bytes"] <= plan["maximum_aggregate_body_bytes"],
         "COMPLETE_FIXED_AGGREGATE_REQUIRED")
    return result, inner, decoded


def write_private_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        body = memoryview(raw)
        while body:
            count = os.write(fd, body)
            need(count > 0, "PRIVATE_WRITE_PROGRESS")
            body = body[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(read(path, len(raw), True) == raw, "NEW_PRIVATE_OUTPUT_READBACK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args()
    need(1 <= args.batch <= 14, "FIXED_BATCH_RANGE")
    folder = HERE / ("batch-%02d" % args.batch)
    raw_plan = read(folder / "READBACK_PLAN.json", 65536)
    need(sha(raw_plan) == args.plan_sha256, "EXACT_REVIEWED_READBACK_PLAN")
    plan = parse(raw_plan)
    private = PROJECT.parent / "p4_private_ui/fixed46-permissions-compressed-readback-r1" / folder.name
    public = folder / "actual-public"
    need(plan["schema"] == "pocket4-fixed-batch-compressed-private-readback-plan-v2" and
         plan["private_destination_required"] == str(private) and plan["public_actual_directory"] == str(public) and
         plan["maximum_compressed_stdout_bytes"] == 1048576 and plan["maximum_aggregate_body_bytes"] == 2097152 and
         plan["maximum_inner_result_bytes"] == 2 * plan["actual_aggregate_log_bytes"] + 32768,
         "ONLY_REVIEWED_FIXED_PRIVATE_DESTINATION_AND_BUDGET")
    for directory in (folder, private, public):
        need(directory.is_dir() and not directory.is_symlink(), "EXISTING_REGULAR_LOCAL_DIRECTORY_REQUIRED")
    packet_raw = read(folder / "process-request.review-only.json", 65536)
    need(len(packet_raw) == plan["process_request"]["bytes"] and sha(packet_raw) == plan["process_request"]["sha256"], "EXACT_READBACK_REQUEST_PIN")
    packet = parse(packet_raw)
    reader = read(folder / "read_fixed_batch_private_logs.py", 65536)
    need(len(reader) == plan["reader"]["bytes"] and sha(reader) == plan["reader"]["sha256"] and
         packet["args"][-1] == reader.decode(), "ACTUAL_READER_SOURCE_PIN")
    start = parse(read(public / "start.original.txt", 131072))
    job = start["job"]
    need(job["idempotency_key"] == packet["idempotency_key"] and job["host"] == packet["host"] and
         job["executable"] == packet["executable"] and job["args"] == packet["args"] and job["cwd"] == packet["cwd"] and
         job["launch_state"] == "launched" and job["launch_error"] is None and start["launch"]["ok"] is True, "EXACT_ACTUAL_READBACK_JOB")
    terminal_raw = read(public / "terminal.original.json", 65536)
    terminal = parse(terminal_raw)
    raw = read(private / "stdout.original.jsonl", plan["maximum_compressed_stdout_bytes"])
    need(terminal.get("job_id") == job["id"] and terminal.get("state") == "succeeded" and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == 0 and
         all(terminal.get(k) is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(k) is False for k in ("timed_out", "automatic_retry", "cancelled")) and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_bytes") == {"stdout": {"seen": len(raw), "stored": len(raw)}, "stderr": {"seen": 0, "stored": 0}},
         "DURABLE_COMPLETE_READER_SUCCESS_REQUIRED")
    result, inner, decoded = decode_envelope(raw, plan)
    # No private output is created until all streams, hashes and terminal passed.
    write_private_new(private / "readback.decoded.original.json", inner)
    for pin, body in decoded:
        name = Path(pin["path"]).name
        need(name.startswith("android-") and name.endswith(".stdout") and "/" not in name, "FIXED_PRIVATE_LOG_BASENAME")
        write_private_new(private / name, body)
    receipt = {"schema": "pocket4-fixed-batch-private-readback-receipt-v2", "ok": True, "readback_job": job["id"],
        "capture_binding": plan["capture_binding"], "plan_sha256": args.plan_sha256,
        "private_stdout_bytes": len(raw), "private_stdout_sha256": sha(raw), "private_inner_bytes": len(inner),
        "private_inner_sha256": sha(inner), "terminal_sha256": sha(terminal_raw), "fixed_files": plan["fixed_files"],
        "process_FDs_before": result["process_FDs_before"], "process_FDs_after": result["process_FDs_after"],
        "complete_original_bodies_decoded_and_rehashed": True, "raw_bodies_published": False,
        "permissions_interpreted": False, "role_status": "UNKNOWN_NOT_QUERIED", "production_ready": False}
    write_private_new(public / "READBACK_RECEIPT.derived.json", canonical(receipt) + b"\n")
    print(json.dumps(receipt, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    main()
