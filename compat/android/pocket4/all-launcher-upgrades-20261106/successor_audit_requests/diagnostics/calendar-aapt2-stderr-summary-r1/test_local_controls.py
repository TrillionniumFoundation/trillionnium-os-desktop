#!/usr/bin/env python3
"""Owned local files only; no Main, root authority or remote reads."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import tempfile
import time

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("summary_definitions", ROOT / "summarize_fixed_stderr.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def main():
    before = len(os.listdir("/proc/self/fd"))
    cases = []
    with tempfile.TemporaryDirectory(prefix="owned-calendar-stderr-control-") as tmp:
        with (Path(tmp) / "one-link.log").open("w+b") as file:
            raw = ("warning: invalid resource offset 0x123\n" * 5000 + "error: final\r\n").encode()
            file.write(raw); file.flush(); file.seek(17)
            pin = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            result = M.summarize_fd(file.fileno(), pin, time.monotonic() + 10)
            assert result["line_count"] == 5001
            assert result["keyword_line_counts_overlapping"]["warning"] == 5000
            assert result["keyword_line_counts_overlapping"]["error"] == 1
            assert file.tell() == 17 and len(result["head"]) == len(result["tail"]) == 12
            assert result["sha256"] == pin["sha256"]
            cases.append({"name": "real_stream_boundaries_hash_categories_borrowed_offset", "passed": True})
            try:
                M.summarize_fd(file.fileno(), dict(pin, sha256="0" * 64), time.monotonic() + 10)
            except RuntimeError as error:
                assert str(error) == "FULL_LOG_BYTES_HASH_OR_STAT_CHANGED"
            else:
                raise AssertionError("wrong hash accepted")
            cases.append({"name": "damaged_fullhash_rejected", "passed": True})
        with (Path(tmp) / "long-line.log").open("w+b") as file:
            raw = b"x" * 65537
            file.write(raw); file.flush()
            try:
                M.summarize_fd(file.fileno(), {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}, time.monotonic() + 10)
            except RuntimeError as error:
                assert str(error) == "LOG_LINE_BOUND"
            else:
                raise AssertionError("long line accepted")
            os.fstat(file.fileno())
            cases.append({"name": "unbounded_line_rejected_borrowed_fd_remains_live", "passed": True})
    after = len(os.listdir("/proc/self/fd"))
    assert before == after
    print(json.dumps({"schema": "pocket4-calendar-stderr-summary-local-controls-v1", "ok": True,
                      "cases": cases, "process_FDs_before": before, "process_FDs_after": after,
                      "Main_reads": 0, "remote_reads": 0, "tool_executions": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
