#!/usr/bin/env python3
"""Fail-closed source/contract audit for D0C-06."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/receipt-journal.v1.json"
SOURCE = ROOT / "crates/hepta-session-core/src/receipt_journal.rs"
ERRORS: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")

    require(contract.get("schema") == "trillionnium.desktop.receipt-journal-contract.v1", "wrong contract schema")
    require(contract.get("status") == "SOURCE_CANDIDATE_NO_BROWSER_DISPATCH", "candidate status drift")
    fmt = contract.get("format", {})
    require(fmt.get("segment_header_bytes") == 148, "segment header contract drift")
    require(fmt.get("record_prefix_bytes") == 208, "record prefix contract drift")
    require(fmt.get("maximum_record_payload_bytes") == 65536, "payload bound drift")
    require(fmt.get("maximum_segment_bytes") == 67108864, "segment bound drift")
    require(contract.get("effect_recovery", {}).get("potential_external_effect") == "never_automatic", "external effects became replayable")
    require(contract.get("effect_recovery", {}).get("journal_executes_or_replays_operations") is False, "journal gained execution authority")
    require(all(value is False for value in contract.get("claim_ceiling", {}).values()), "claim ceiling must remain closed")

    markers = [
        'const SEGMENT_HEADER_LEN: usize = 148;',
        'const RECORD_PREFIX_LEN: usize = 208;',
        'const MAX_RECORD_PAYLOAD_BYTES: usize = 64 * 1024;',
        'const MAX_SEGMENT_BYTES: u64 = 64 * 1024 * 1024;',
        'ReplayDirective::NeverAutomatic',
        'writer is poisoned after an interrupted append',
        'rotation requires a quiescent journal',
        'secret_redacted receipts may not persist detail',
        'commit_bytes(&mut self.file, &bytes)',
        'file.sync_data()',
    ]
    for marker in markers:
        require(marker in source, f"source is missing invariant marker: {marker}")

    forbidden = [
        "TcpListener",
        "WebDriver",
        "ServoBuilder",
        "std::process::Command",
        "unsafe {",
        "todo!",
        "unimplemented!",
    ]
    for marker in forbidden:
        require(marker not in source, f"receipt journal contains forbidden authority/stub: {marker}")

    if ERRORS:
        for error in ERRORS:
            print(f"D0C-06 audit error: {error}", file=sys.stderr)
        return 1
    print("D0C-06 receipt journal source/contract audit: PASS")
    print("browser dispatch: false")
    print("automatic external-effect replay: false")
    print("listener activation: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
