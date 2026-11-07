#!/usr/bin/env python3
"""Narrow local future-input rejection and unchanged decoder/source controls."""
import sys
sys.dont_write_bytecode = True
import ast
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]


def main():
    before = len(os.listdir("/proc/self/fd"))
    path = HERE / "prepare_completed_readback.py"
    module = types.ModuleType("future_actual_only_readback")
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    assert not (HERE / "readbacks").exists()
    cases = []
    for number in (1, 14):
        try:
            module.select_complete(number)
        except RuntimeError as error:
            assert str(error) == "NO_READER_FOR_FAILED_UNKNOWN_OR_UNOBSERVED_NEW_BATCH", str(error)
        else:
            raise AssertionError("Unobserved batch admitted")
        assert not (HERE / "readbacks").exists()
        cases.append({"name": "unobserved_batch_%02d_rejected_before_reader_creation" % number, "pass": True})
    def defs(raw):
        text = raw.decode()
        return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    original = (PROJECT / "successor_audit_requests/effective_permissions_batch_readback_r2/decode_private_readback.py").read_bytes()
    actual = (HERE / "decode_completed_readback.py").read_bytes()
    old_defs, new_defs = defs(original), defs(actual)
    names = sorted(n for n in old_defs if n != "main")
    assert set(old_defs) == set(new_defs) and all(old_defs[n] == new_defs[n] for n in names)
    parser = (PROJECT / "successor_audit_requests/effective_permissions_microg_parser_r1/interpret_microg_exact.py").read_bytes()
    assert len(parser) == 20711 and hashlib.sha256(parser).hexdigest() == "c38b558a5c0d1b1a9649d688f0b3318622097f93e0b993ed6e0fb723adf342e1"
    for n in ("need", "sha", "unknown", "lines", "section", "parse_package", "parse_appops", "derive"):
        assert n in defs(parser)
    for filename in ("prepare_completed_readback.py", "decode_completed_readback.py", "interpret_completed_readback.py"):
        compile((HERE / filename).read_bytes(), filename, "exec")
    cases.append({"name": "seven_decoder_helpers_exact_and_eight_parser_core_functions_pinned", "pass": True})
    after = len(os.listdir("/proc/self/fd"))
    assert before == after
    print(json.dumps({"ok": True, "cases": cases, "unchanged_decoder_definitions": names,
        "uid": os.getuid(), "euid": os.geteuid(), "FDs_before": before, "FDs_after": after,
        "private_service_body_reads": 0, "reader_requests_created": 0, "capture_claims_created": 0,
        "Main_commands": 0, "remote_jobs": 0, "production_ready": False}, sort_keys=True))


if __name__ == "__main__":
    main()
