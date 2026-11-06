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
        need(stat.S_ISREG(before.st_mode) and before.st_size == pin["bytes"] and 0 <= before.st_size <= 262144,
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--pm-private", required=True)
    parser.add_argument("--appops-private", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("local_permission_capture_gate", HERE / "permission_capture_gate.py")
    gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
    g, plan, loaded = gate.load_closure()
    need(1 <= args.batch <= 13 and args.package in loaded[args.batch]["row"]["targets"], "EXACT_OBSERVED_TARGET_REQUIRED")
    state = gate.inspect(g, plan, loaded)
    completed = next((r for r in state["completed"] if r["batch"] == args.batch), None)
    need(completed is not None, "ACTUAL_DURABLE_BATCH_CAPTURE_MUST_PASS_FIRST")
    reports = [row for row in completed["service_reports"] if row["target_package"] == args.package]
    need([r["service"] for r in reports] == ["package-dump-package", "appops-get-user0"], "EXACT_TWO_SERVICE_INPUTS_REQUIRED")
    target = next(row for row in loaded[args.batch]["row"]["target_identities"] if row["package"] == args.package)
    pm = read_private(args.pm_private, reports[0]["stdout"])
    ops = read_private(args.appops_private, reports[1]["stdout"])
    evidence = {"batch": args.batch, "job_id": completed["job_id"], "artifact_sha256": completed["artifact_sha256"],
                "terminal_sha256": completed["terminal_sha256"], "PM_private_input": reports[0]["stdout"],
                "AppOps_private_input": reports[1]["stdout"], "raw_capture_passed": True}
    result = derive(pm, ops, target, evidence)
    output = Path(args.output)
    need(output.is_absolute() and output.parent.is_dir(), "EXPLICIT_EXISTING_OUTPUT_PARENT_REQUIRED")
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view); need(count > 0, "DERIVED_OUTPUT_WRITE_PROGRESS"); view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(output.read_bytes() == raw, "DERIVED_OUTPUT_READBACK")
    print(json.dumps({"output": str(output), "bytes": len(raw), "sha256": sha(raw),
                      "interpretation_status": result["interpretation_status"], "raw_bodies_exported": False, "runtime_queries": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
