#!/usr/bin/env python3
"""Offline, conservative interpretation of already captured private service bytes.

No Android/host command is executed. Capture and interpretation are independent:
unknown or missing text is UNKNOWN, never an inferred denial or grant. This
extends the literal grammar actually observed in the successful Beike pilot.
Raw dump-package/AppOps text and usage timestamps are never emitted.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
PRIVATE_ROOT = PROJECT.parent / "p4_private_ui"
LINK_FILE = "successor_audit_requests/revisions/microg-linked-permission-continuation-r1/linked_permission_gate.py"
LINK_SHA = "bf7ee540d5e64276f1a9490b50da1381a725f52081848ec0d960353acf86c7a8"
READBACK = PROJECT / "successor_audit_requests/effective_permissions_batch_readback_r2/batch-02"
CAPTURE_JOB = "1a1b2d790f2-fc05-7ffb"
READBACK_JOB = "1a1b2ea0995-fc05-8030"
MICROG_PM_PIN = {'bytes': 1478016, 'path': '/home/alex/work/pocket4-microg-permission-correction-observation-20261106-r1/android-02.stdout', 'sha256': '738586aac7aef5aafee12cc238bb0f70be69ba218d8b512b25fe168559dfab8d'}
MICROG_APPOPS_PIN = {'bytes': 1478, 'path': '/home/alex/work/pocket4-microg-permission-correction-observation-20261106-r1/android-03.stdout', 'sha256': '2c636551a798d17ebcb17ca12440f7772d486b86af9f017683fba7ed0735118c'}
MICROG_PM_PRIVATE = PRIVATE_ROOT / "fixed45-permissions-compressed-readback-r2/batch-02/android-02.stdout"
MICROG_APPOPS_PRIVATE = PRIVATE_ROOT / "fixed45-permissions-compressed-readback-r2/batch-02/android-03.stdout"
INPUT_BYTES = 1936
INPUT_SHA = 'acd18b1967e6c1f84759f34e0ba94d703797ce95bde8d21316879a2368ba3d98'

NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*")
LITERAL_NAME = re.compile(r" *[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*")
PACKAGE_HEADER = re.compile(r"  Package \[([A-Za-z_0-9.]+)\] \([0-9a-fA-F]+\):")
USER_HEADER = re.compile(r"    User ([0-9]+):(?: .*)?")
MODES = r"ignore|default|allow|deny|foreground"


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unknown(code):
    return {"status": "UNKNOWN", "reason": code, "rows": []}


def lines(raw):
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return None
    # The actual service grammar uses LF; silently accepting CR, NUL or other
    # line separators could normalize a literal permission name.
    if "\r" in text or "\x00" in text or any(c in text for c in ("\x0b", "\x0c", "\u0085", "\u2028", "\u2029")):
        return None
    return text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")


def section(block, header, prefix, kind):
    matches = [i for i, line in enumerate(block) if line == header]
    if len(matches) != 1:
        return unknown("MISSING_SECTION" if not matches else "DUPLICATE_SECTION")
    body = []
    for line in block[matches[0] + 1:]:
        if not line.startswith(prefix):
            break
        body.append(line[len(prefix):])
    if not body:
        return {"status": "OBSERVED_EMPTY_SECTION", "rows": [], "absence_does_not_imply_denied": True}
    result = []
    seen = set()
    for value in body:
        if kind == "requested":
            name, row = value, {"permission": value}
        else:
            expression = r"(.+): granted=(true|false)" if kind == "install" else r"(.+): granted=(true|false), flags=\[([^\]]*)\]"
            match = re.fullmatch(expression, value)
            if match is None:
                return unknown("UNRECOGNIZED_PERMISSION_ROW")
            name = match[1]
            row = {"permission": name, "granted": match[2] == "true"}
            if kind == "runtime":
                row["flags_raw"] = match[3]
        if LITERAL_NAME.fullmatch(name) is None:
            return unknown("UNRECOGNIZED_LITERAL_PERMISSION_NAME")
        if name in seen:
            return unknown("DUPLICATE_PERMISSION_ROW")
        seen.add(name)
        row["canonical_name_without_normalization"] = NAME.fullmatch(name) is not None
        result.append(row)
    return {"status": "LITERAL_ROWS_PARSED", "rows": result, "names_normalized": False}


def parse_package(raw, package, uid):
    result = {"status": "UNKNOWN", "package": package, "user": 0,
              "requested": unknown("NO_VERIFIED_PACKAGE_BLOCK"), "install": unknown("NO_VERIFIED_PACKAGE_BLOCK"),
              "runtime_user0": unknown("NO_VERIFIED_USER0_BLOCK"), "requested_permission_states": [],
              "normalized_permission_names_inferred": False, "other_users_or_packages_attributed": False,
              "shared_UID_membership_enumerated": False}
    text = lines(raw)
    if text is None:
        result["reason"] = "UNRECOGNIZED_TEXT_ENCODING_OR_LINE_SEPARATORS"
        return result
    headers = [i for i, line in enumerate(text) if line.startswith("  Package [" + package + "]")]
    if len(headers) != 1 or PACKAGE_HEADER.fullmatch(text[headers[0]]) is None:
        result["reason"] = "MISSING_DUPLICATE_OR_UNRECOGNIZED_TARGET_PACKAGE_HEADER"
        return result
    start = headers[0]
    # Select this exact package block. A second User 0 in another service block
    # is intentionally outside this range and cannot satisfy the runtime query.
    end = next((i for i in range(start + 1, len(text)) if text[i] and not text[i].startswith("    ")), len(text))
    block = text[start + 1:end]
    ids = [line for line in block if line.startswith("    appId=")]
    if len(ids) != 1 or ids[0] != "    appId=" + str(uid):
        result["reason"] = "TARGET_APPID_MISSING_DUPLICATE_OR_DIFFERS_FROM_PINNED_USER0_UID"
        return result
    result["package_identity_matches_pinned_scope"] = True
    result["requested"] = section(block, "    requested permissions:", "      ", "requested")
    result["install"] = section(block, "    install permissions:", "      ", "install")
    user_like = [(i, line) for i, line in enumerate(block) if line.startswith("    User ")]
    if any(USER_HEADER.fullmatch(line) is None for _, line in user_like):
        result["runtime_user0"] = unknown("UNRECOGNIZED_USER_BLOCK_BOUNDARY")
    else:
        users = [(i, int(USER_HEADER.fullmatch(line)[1])) for i, line in user_like]
        starts = [i for i, user in users if user == 0]
        if len(starts) != 1:
            result["runtime_user0"] = unknown("MISSING_OR_DUPLICATE_USER0_BLOCK")
        else:
            begin = starts[0]
            stop = next((i for i, _ in users if i > begin), len(block))
            # User-specific details are six spaces deep. Another four-space
            # section terminates this user's block even without a later user.
            stop = min(stop, next((i for i in range(begin + 1, stop) if block[i] and not block[i].startswith("      ")), stop))
            result["runtime_user0"] = section(block[begin + 1:stop], "      runtime permissions:", "        ", "runtime")
    sections = (result["requested"], result["install"], result["runtime_user0"])
    result["status"] = "LITERAL_SERVICE_ROWS_PARSED" if all(s["status"] in ("LITERAL_ROWS_PARSED", "OBSERVED_EMPTY_SECTION") for s in sections) else "PARTIAL_UNKNOWN"
    for wanted in result["requested"]["rows"]:
        name = wanted["permission"]
        observations = [{"section": kind, "granted": row["granted"]} for kind in ("install", "runtime_user0")
                        for row in result[kind]["rows"] if row["permission"] == name]
        entry = {"permission": name, "state": "UNKNOWN", "reported_grants": observations}
        if not wanted["canonical_name_without_normalization"]:
            entry["reason"] = "NONCANONICAL_LITERAL_NAME_NOT_NORMALIZED"
        elif len(observations) == 1:
            entry.update(state="PM_SERVICE_REPORTED_GRANTED" if observations[0]["granted"] else "PM_SERVICE_REPORTED_NOT_GRANTED",
                         observation_section=observations[0]["section"])
        elif not observations:
            entry["reason"] = "NO_UNIQUE_RECOGNIZED_GRANT_ROW"
        else:
            entry["reason"] = "MULTIPLE_SERVICE_SECTIONS_NOT_MERGED"
        result["requested_permission_states"].append(entry)
    return result


def parse_appops(raw):
    result = {"status": "UNKNOWN", "rows": [], "unrecognized_line_hashes": [], "duplicate_operations_in_same_reported_scope": [],
              "AppOps_requested_user": 0, "unprefixed_line_scope": "UNKNOWN_NOT_INFERRED",
              "effective_authorization": "UNKNOWN_NOT_INFERRED_FROM_MODE", "mode_is_permission_grant": False}
    text = lines(raw)
    if text is None or not text or text == [""]:
        result["reason"] = "EMPTY_OR_UNRECOGNIZED_TEXT"
        return result
    seen = set()
    for line in text:
        match = re.fullmatch(r"(Uid mode: )?([A-Z][A-Z_0-9]*): (" + MODES + r")(?:;.*)?", line)
        if match is None:
            result["unrecognized_line_hashes"].append(sha(line.encode("utf-8")))
            continue
        explicit = bool(match[1])
        scope = "UID_EXPLICIT_ON_THIS_LINE" if explicit else "UNKNOWN_UNPREFIXED_LINE"
        key = (match[2], scope)
        row = {"operation": match[2], "reported_mode": match[3], "explicit_uid_mode_prefix_on_this_line": explicit,
               "reported_scope": scope, "raw_line_sha256": sha(line.encode("utf-8"))}
        result["rows"].append(row)
        if key in seen:
            result["duplicate_operations_in_same_reported_scope"].append({"operation": key[0], "scope": key[1]})
        seen.add(key)
    if result["rows"] and not result["unrecognized_line_hashes"] and not result["duplicate_operations_in_same_reported_scope"]:
        result["status"] = "LITERAL_MODE_ROWS_PARSED"
    elif result["rows"]:
        result["status"] = "PARTIAL_UNKNOWN"
    else:
        result["reason"] = "NO_RECOGNIZED_LITERAL_MODE_ROWS"
    return result


def derive(pm_raw, appops_raw, target, evidence):
    pm = parse_package(pm_raw, target["package"], target["uid"])
    appops = parse_appops(appops_raw)
    return {"schema": "pocket4-literal-permission-service-interpretation-v1", "package": target["package"],
            "uid": target["uid"], "version_code": target["version_code"], "observation": evidence,
            "permission_service": pm, "AppOps_service": appops, "role_status": "UNKNOWN_NOT_QUERIED",
            "interpretation_status": "LITERAL_ROWS_PARSED_WITH_EXPLICIT_LIMITS" if pm["status"] == "LITERAL_SERVICE_ROWS_PARSED" and
                appops["status"] == "LITERAL_MODE_ROWS_PARSED" else "UNKNOWN_OR_PARTIAL_SERVICE_FORMAT",
            "raw_capture_result_changed": False, "permission_changes": 0, "new_runtime_queries": 0,
            "private_raw_bodies_published": False, "usage_timestamps_published": False, "production_ready": False,
            "limits": [
                "Only literal rows of the recorded service output are reported; unlisted permissions stay UNKNOWN.",
                "The exact target package and User 0 block are selected; shared UID membership is not inferred.",
                "A false PM grant is not attributed to a user denial, and true does not prove successful core operation.",
                "AppOps modes are not permission grants. Default and foreground are not unconditional allow.",
                "The explicit Uid mode prefix applies only to that literal line; unprefixed scope remains UNKNOWN.",
                "Permission names retain whitespace after removing only the exact presentation indentation.",
                "Role holders, additional policy decisions, network requests and denial/recovery behavior were not queried."]}


def read_private(path, pin):
    path = Path(path)
    need(path.is_absolute() and path.resolve().is_relative_to(PRIVATE_ROOT.resolve()) and not path.is_symlink(),
         "PRIVATE_RAW_INPUT_MUST_STAY_OUTSIDE_REPOSITORY")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size == pin["bytes"] and 0 <= before.st_size <= private_input_limit(path, pin),
             "BOUNDED_PINNED_PRIVATE_INPUT_REQUIRED")
        raw = bytearray()
        while len(raw) <= before.st_size:
            part = os.read(fd, min(65536, before.st_size + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        path_after = os.stat(path, follow_symlinks=False)
        need(all(getattr(before, k) == getattr(after, k) == getattr(path_after, k) for k in fields) and
             len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "PRIVATE_INPUT_CHANGED_OR_WRONG_CAPTURE")
        return bytes(raw)
    finally:
        os.close(fd)


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


if __name__ == "__main__":
    raise SystemExit(main())
