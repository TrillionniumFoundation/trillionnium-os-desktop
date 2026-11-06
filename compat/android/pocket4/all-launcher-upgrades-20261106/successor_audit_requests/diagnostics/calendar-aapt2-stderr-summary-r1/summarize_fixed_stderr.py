#!/usr/bin/env python3
"""Stream one exact existing Calendar stderr; no Android, APK or tool execution."""
from collections import Counter, deque
import hashlib
import json
import os
import re
import stat
import sys
import time

PIN = {"path": "/home/alex/work/pocket4-successor-apk-audit-20261106-calendar-aapt2-comparison-r3-01/p00-a00-badging.stderr",
       "bytes": 2486748, "sha256": "256a56fc10b83a17488572225c07cc2f04a1f5a54b06db033d578f21c18df631"}
STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
KEYWORDS = ("error", "fatal", "warning", "warn", "invalid", "failed", "entry", "chunk", "offset", "resource", "sparse")


def need(value, code):
    if not value:
        raise RuntimeError(code)


def file_record(fd):
    value = os.fstat(fd)
    return {key: getattr(value, key) for key in STAT}


def summarize_fd(fd, expected, end):
    before = file_record(fd)
    need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and before["st_size"] == expected["bytes"], "EXACT_REGULAR_LOG")
    digest, consumed, pending = hashlib.sha256(), 0, b""
    counts, severity, messages = Counter(), Counter(), Counter()
    head, tail, noteworthy = [], deque(maxlen=12), []
    lines, max_line, message_overflow = 0, 0, 0

    def observe(raw):
        nonlocal lines, max_line, message_overflow
        lines += 1
        max_line = max(max_line, len(raw))
        text = raw.decode("utf-8", "strict").rstrip("\r\n")
        lower = text.lower()
        tokens = {key for key in KEYWORDS if re.search(r"\b" + re.escape(key) + r"\b", lower)}
        counts.update(tokens)
        level = next((key for key in ("fatal", "error", "warning", "warn") if key in tokens), "no_severity_word")
        severity[level] += 1
        sample = {"line": lines, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                  "text_prefix": text[:512], "prefix_truncated": len(text) > 512}
        if len(head) < 12:
            head.append(sample)
        tail.append(sample)
        if tokens & {"fatal", "error"} and len(noteworthy) < 8:
            noteworthy.append(sample)
        normalised = re.sub(r"\b0x[0-9a-f]+\b|\b\d+\b", "#", lower)[:256]
        if normalised in messages or len(messages) < 256:
            messages[normalised] += 1
        else:
            message_overflow += 1

    while consumed <= expected["bytes"]:
        need(time.monotonic() < end, "LOG_READ_DEADLINE")
        raw = os.pread(fd, min(65536, expected["bytes"] + 1 - consumed), consumed)
        if not raw:
            break
        digest.update(raw)
        consumed += len(raw)
        need(consumed <= expected["bytes"], "LOG_SIZE_INCREASED")
        pieces = (pending + raw).split(b"\n")
        pending = pieces.pop()
        need(len(pending) <= 65536, "LOG_LINE_BOUND")
        for fragment in pieces:
            line = fragment + b"\n"
            need(len(line) <= 65536, "LOG_LINE_BOUND")
            observe(line)
    if pending:
        observe(pending)
    need(consumed == expected["bytes"] and digest.hexdigest() == expected["sha256"] and file_record(fd) == before,
         "FULL_LOG_BYTES_HASH_OR_STAT_CHANGED")
    return {"bytes": consumed, "sha256": digest.hexdigest(), "held_stat": before, "line_count": lines,
            "line_separator": "LF bytes; trailing CR removed only from text snippets",
            "max_line_bytes": max_line, "keyword_line_counts_overlapping": {key: counts[key] for key in KEYWORDS},
            "severity_word_line_counts_disjoint": dict(severity), "head": head, "tail": list(tail),
            "first_error_or_fatal_word_samples": noteworthy,
            "normalised_message_counts_top20": [{"prefix": key, "count": count} for key, count in messages.most_common(20)],
            "normalised_dictionary_limit": 256, "normalised_dictionary_overflow_lines": message_overflow,
            "classification_is_keyword_observation_only": True, "all_resource_health_proved": False}


def read_exact(pin):
    descriptors = []
    try:
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); descriptors.append(parent)
        parts = pin["path"][1:].split("/")
        need(pin["path"].startswith("/") and all(x not in ("", ".", "..") for x in parts), "CANONICAL_FIXED_PATH")
        for name in parts[:-1]:
            parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            descriptors.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent); descriptors.append(fd)
        need(os.fstat(fd).st_uid == 0 and not os.fstat(fd).st_mode & 0o022, "ROOT_PRIVATE_LOG_REQUIRED")
        result = summarize_fd(fd, pin, time.monotonic() + 20)
        again = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent); descriptors.append(again)
        need(file_record(again) == result["held_stat"], "PINNED_LOG_PATH_REPLACED")
        result.update(path=pin["path"], full_hash_verified=True, held_file_and_path_stable=True)
        return result
    finally:
        errors = []
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        need(not errors, "LOG_READER_FDS_NOT_RETIRED")


def main():
    need(os.getuid() == os.geteuid() == 0, "EXISTING_AUTHORIZED_ROOT_READER_REQUIRED")
    before = len(os.listdir("/proc/self/fd"))
    result = {"schema": "pocket4-exact-calendar-aapt2-stderr-summary-v1", "ok": False, "errors": [],
              "original_diagnostic_job": "1a1b1f10cbf-fc05-7b9c", "original_batch05_reclassified": False,
              "Main_reads": 0, "APK_reads": 0, "namespace_entries": 0, "tool_executions": 0, "UI_actions": 0,
              "installs": 0, "permission_changes": 0, "existing_files_modified": False, "automatic_retry": False,
              "production_ready": False, "action_lock_acquired": False}
    try:
        result["log"] = read_exact(PIN)
        result["ok"] = True
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:256]})
    after = len(os.listdir("/proc/self/fd"))
    result.update(process_FDs_before=before, process_FDs_after=after)
    if before != after:
        result["ok"] = False
        result["errors"].append({"reason": "WHOLE_PROCESS_FD_COUNT_CHANGED"})
    raw = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    need(len(raw) <= 65536, "SUMMARY_STDOUT_BOUND")
    print(raw.decode(), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
