#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Strict transcript oracle for the original AF_UNIX directed syscall probe.

Synthetic oracle controls are not native executions. A semantic negative passes
only its specific bounded defect predicate, never an arbitrary guest failure.
"""
import hashlib
import json
from pathlib import Path
import re

PROTOCOL_SHA256 = "6577cd26c72c80f370cd4a654463316bf7fa5227a33a0e9ff3ade0e05eb9e680"
MAX_SERIAL_BYTES = 8 * 1024 * 1024
PREFIX = "UNIX_STREAM_V1"
HARNESS = "UNIX_STREAM_HARNESS"
INIT = "TRILLIONNIUM_A01_INIT_BEGIN"
CPU = "TRILLIONNIUM_A01_CPU_COUNT=1"
BOOT = "TRILLIONNIUM_A01_BOOT_OK"
RACE = "UNIX_STREAM_RACE_WINDOW"
AUX = "UNIX_STREAM_AUX_ZERO_PROGRESS"
VARIANTS = ("positive", "race-fixed", "race-stale", "aux-zero-progress")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
FATAL = ("panicked at", "An uncaught panic occurred:", "Uncaught panic:",
         "unknown panic payload!", "Non-resettable panic!", "The panic handler panicked",
         "Panicked in `PanicGuard`", "Kernel panic", "Segmentation fault", "core dumped")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def protocol():
    raw = Path(__file__).with_name("unix_stream_protocol.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PROTOCOL_SHA256, "protocol pin mismatch")
    return json.loads(raw)


def parse_fields(line, prefix):
    require(line.startswith(prefix + " "), "malformed record prefix")
    values = {}
    for token in line[len(prefix) + 1:].split(" "):
        require(re.fullmatch(r"[a-z_]+=[A-Za-z0-9_-]+", token) is not None,
                "malformed record field")
        key, value = token.split("=", 1)
        require(key not in values, "duplicate record key")
        values[key] = value
    return values


def integer(value, low, high, label):
    require(re.fullmatch(r"0|[1-9][0-9]*", value) is not None, "noncanonical " + label)
    number = int(value)
    require(low <= number <= high, "out of range " + label)
    return number


def expected_records(selection, spec):
    names = spec["default_case_order"] if selection == "all" else [selection]
    result = []
    for name in names:
        require(name in spec["cases"], "unknown selected case")
        result.extend({"event": entry["event"], "case": name, **entry["fields"]}
                      for entry in spec["cases"][name])
    result.append({"event": "suite_pass", "case": "suite", "cases": len(names),
                   "selection": selection})
    return result


def match_records(records, expected, nonce):
    require(len(records) == len(expected), "missing or extra probe record")
    pid = None
    for index, (actual, wanted) in enumerate(zip(records, expected), 1):
        fields = {"nonce": nonce, "seq": index, **wanted}
        require(set(actual) == set(fields), "unknown or absent field at record " + str(index))
        for key, value in fields.items():
            observed = actual[key]
            if value == "$pid":
                number = integer(observed, 1, 2147483647, "pid")
                if pid is None:
                    pid = number
                require(number == pid, "probe process identity changed")
            elif value in ("$uid", "$gid"):
                integer(observed, 0, 4294967295, key)
            elif value == "$first_payload_read":
                integer(observed, 1, 96, "first payload read")
            else:
                require(observed == str(value), "record " + str(index) + " field " + key + " mismatch")
    return pid


def validate(raw, code, timed_out, excessive, nonce, selection, variant):
    require(isinstance(raw, bytes) and len(raw) <= MAX_SERIAL_BYTES, "serial exceeds bound")
    require(type(code) is int and code == 33, "unexpected QEMU exit")
    require(timed_out is False and excessive is False, "guest deadline or output bound exceeded")
    require(re.fullmatch(r"[0-9a-f]{32}", nonce) is not None, "invalid expected nonce")
    require(variant in VARIANTS, "unknown source variant")
    if variant in ("race-fixed", "race-stale"):
        require(selection == "shutdown_race", "race control must select shutdown_race")
    if variant == "aux-zero-progress":
        require(selection == "credential_only", "aux control must select credential_only")
    spec = protocol()
    expected = expected_records(selection, spec)
    text = ANSI.sub("", raw.decode("ascii", errors="replace"))
    require(not any(marker in text for marker in FATAL), "fatal guest marker")
    records, record_lines, harnesses, race_lines, aux_lines = [], [], [], [], []
    lines = text.splitlines(keepends=True)
    for index, terminated in enumerate(lines):
        line = terminated.removesuffix("\n").removesuffix("\r")
        if any(marker in line for marker in (PREFIX, HARNESS, RACE, AUX, INIT, CPU, BOOT)):
            require(terminated.endswith("\n"), "unterminated evidence line")
        if PREFIX in line:
            require(line.isascii() and len(line) + 1 <= 768, "invalid bounded probe record")
            records.append(parse_fields(line, PREFIX))
            record_lines.append(index)
        if HARNESS in line:
            harnesses.append((index, parse_fields(line, HARNESS)))
        if RACE in line:
            require(line.count(RACE) == 1 and re.search(
                r"UNIX_STREAM_RACE_WINDOW old_len=0 queued=96 shutdown=1$", line) is not None,
                "malformed or wrong race window")
            race_lines.append(index)
        if AUX in line:
            require(line.count(AUX) == 1 and re.search(
                r"UNIX_STREAM_AUX_ZERO_PROGRESS count=3 read_bytes=13 remaining=0$", line) is not None,
                "malformed or wrong auxiliary witness")
            aux_lines.append(index)
    exact_lines = [line.removesuffix("\n").removesuffix("\r") for line in lines]
    for marker in (INIT, CPU, BOOT):
        require(exact_lines.count(marker) == 1 and text.count(marker) == 1,
                "missing, duplicate or malformed original boot marker")
    require(records and len(harnesses) == 1, "missing probe or independent harness exit")
    harness_line, harness = harnesses[0]
    negative = variant in ("race-stale", "aux-zero-progress")
    require(harness == {"nonce": nonce, "selection": selection, "exit": "1" if negative else "0"},
            "independent probe exit or identity mismatch")
    require(exact_lines.index(INIT) < exact_lines.index(CPU) < record_lines[0]
            <= record_lines[-1] < harness_line < exact_lines.index(BOOT),
            "boot, probe and termination order mismatch")
    failed_iteration = None
    if variant == "aux-zero-progress":
        require(not race_lines and len(aux_lines) == 1, "wrong auxiliary control markers")
        expected = expected[:-2]
        expected.extend([
            {"event": "case_fail", "case": selection, "op": "recv_credential_only",
             "expected": 13, "observed": -1, "errno": 40},
            {"event": "suite_fail", "case": "suite", "cases_passed": 0, "selection": selection,
             "failed_case": selection, "exit_code": 1},
        ])
        require(len(record_lines) == len(expected) and record_lines[-3] < aux_lines[0] < record_lines[-2],
                "auxiliary marker not between receive checkpoint and its failure")
    elif variant == "race-stale":
        failures = [entry for entry in records if entry.get("event") == "case_fail"]
        require(len(failures) == 1, "stale control needs exactly one semantic failure")
        failed_iteration = integer(failures[0].get("iteration", ""), 0, 63, "failed iteration")
        # begin, successful earlier pairs, then this iteration's before_recv and
        # actual reaped-writer witness. No caller-supplied successful summary.
        expected = expected[:3 + 2 * failed_iteration]
        expected[-1] = {**expected[-1], "observed_bytes": 0, "first_non_eagain": 0, "eof_read": 0}
        expected.extend([
            {"event": "case_fail", "case": selection, "op": "race_eof", "expected": 96,
             "observed": 0, "errno": 0, "queued_bytes": 96, "iteration": failed_iteration,
             "writer_bytes": 96, "shutdown_result": 0, "child_exit": 0,
             "first_non_eagain": 0, "eof_read": 0},
            {"event": "suite_fail", "case": "suite", "cases_passed": 0, "selection": selection,
             "failed_case": selection, "exit_code": 1},
        ])
    pid = match_records(records, expected, nonce)
    if variant in ("race-fixed", "race-stale"):
        require(not aux_lines and 1 <= len(race_lines) <= 64, "missing or excessive real race windows")
        intervals = []
        for i, record in enumerate(records[:-1]):
            if record.get("name") == "before_recv":
                require(records[i + 1].get("name") == "writer_reaped", "missing adjacent reaped writer")
                intervals.append((int(record["iteration"]), record_lines[i], record_lines[i + 1]))
        seen = set()
        for marker_line in race_lines:
            matches = [iteration for iteration, start, end in intervals if start < marker_line < end]
            require(len(matches) == 1 and matches[0] not in seen, "unbound or duplicate race window")
            seen.add(matches[0])
        if variant == "race-stale":
            require(failed_iteration in seen, "semantic failure lacks its own real scheduling window")
    elif variant == "positive":
        require(not race_lines and not aux_lines, "positive kernel contains control instrumentation")
    return {"record_count": len(records), "probe_pid": pid, "case_selection": selection,
            "variant": variant, "semantic_negative": negative,
            "race_windows": len(race_lines), "failed_iteration": failed_iteration,
            "expected_probe_exit": 1 if negative else 0}


def evaluate(raw, code, timed_out, excessive, nonce, selection, variant):
    result = {"schema": "asterinas.unix-stream-oracle.v1", "passed": False,
              "raw_serial_sha256": hashlib.sha256(raw).hexdigest(), "raw_serial_bytes": len(raw),
              "native_execution_inferred_from_fixture": False}
    try:
        result.update(validate(raw, code, timed_out, excessive, nonce, selection, variant))
        result["passed"] = True
    except (ValueError, KeyError, TypeError) as exc:
        result["error"] = str(exc)
    return result
