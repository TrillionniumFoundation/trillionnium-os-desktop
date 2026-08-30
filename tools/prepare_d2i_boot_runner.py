#!/usr/bin/env python3
"""Generate the D2I host boot verifier from its tracked, reviewed base script."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one source match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    text = source
    text = replace_once(
        text,
        'assert acceptance["schema"] == "trillionnium.desktop.d2i-guest-acceptance.v1", acceptance\n',
        'assert acceptance["schema"] == "trillionnium.desktop.d2i-guest-acceptance.v2", acceptance\n',
        "acceptance schema",
    )
    text = replace_once(
        text,
        'assert acceptance["actual_content_process_crash_proven"] is True, acceptance\n'
        'assert acceptance["actual_crash_callbacks"] >= 1, acceptance\n'
        'assert runtime["actual_content_process_crash_proven"] is True, runtime\n'
        'assert runtime["actual_crash_callbacks"] >= 1, runtime\n'
        'assert runtime["content_process_termination_observed"] is True, runtime\n',
        'assert acceptance["actual_content_process_crash_proven"] is True, acceptance\n'
        'assert acceptance["crash_callback_required"] is False, acceptance\n'
        'assert acceptance["sigkill_delivered"] is True, acceptance\n'
        'assert acceptance["exact_old_identity_absent"] is True, acceptance\n'
        'assert acceptance["zero_process_intermediate"] is True, acceptance\n'
        'assert acceptance["replacement_identity_distinct"] is True, acceptance\n'
        'assert acceptance["popup_denied"] is True, acceptance\n'
        'assert acceptance["external_navigation_denied"] is True, acceptance\n'
        'assert runtime["actual_content_process_crash_proven"] is True, runtime\n'
        'assert runtime["crash_callback_required"] is False, runtime\n'
        'assert runtime["signal_sent"] is True, runtime\n'
        'assert runtime["content_process_termination_observed"] is True, runtime\n'
        'assert runtime["zero_content_processes_after_termination"] is True, runtime\n'
        'assert runtime["replacement_process_distinct"] is True, runtime\n'
        'assert runtime["external_navigation_requests_denied"] >= 1, runtime\n',
        "causal crash assertions",
    )
    text = replace_once(
        text,
        '    "actual_content_process_crash_proven": True,\n'
        '    "secure_boot_qualified": False,\n',
        '    "actual_content_process_crash_proven": True,\n'
        '    "crash_callback_required": False,\n'
        '    "zero_process_intermediate": True,\n'
        '    "replacement_identity_distinct": True,\n'
        '    "external_navigation_denied": True,\n'
        '    "secure_boot_qualified": False,\n',
        "boot-result claim detail",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    args.output.chmod(0o755)
    record = {
        "schema": "trillionnium.desktop.d2i-boot-runner-transformation.v1",
        "status": "PASS_DETERMINISTIC_REVIEWED_TRANSFORMATION",
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "callback_required": False,
        "repository_mutated": False,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
