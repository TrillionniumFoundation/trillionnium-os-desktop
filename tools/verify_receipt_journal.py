#!/usr/bin/env python3
"""Fail-closed source/contract audit for D0C-06."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/receipt-journal.v1.json"
SOURCE = ROOT / "crates/hepta-session-core/src/receipt_journal.rs"
PUBLIC_API = ROOT / "crates/hepta-session-core/src/lib.rs"
ERRORS: list[str] = []

EXPECTED_CLAIM_CEILING = frozenset(
    {
        "browser_actor_bound",
        "servo_called",
        "agent_listener_enabled",
        "external_effect_authorized",
        "automatic_replay_available",
        "product_ready",
    }
)


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def require_pattern(source: str, pattern: str, message: str) -> None:
    """Require a source-level structure, not a marker in a comment/string."""

    if re.search(pattern, source, re.MULTILINE | re.DOTALL) is None:
        ERRORS.append(message)


def forbid_pattern(source: str, pattern: str, message: str) -> None:
    """Reject a forbidden source-level structure when it is present."""

    if re.search(pattern, source, re.MULTILINE | re.DOTALL) is not None:
        ERRORS.append(message)


def mask_rust_non_code(source: str) -> str:
    """Mask comments and literals while retaining Rust token/layout structure.

    The audit is intentionally lightweight (the Rust compiler remains the
    authority), but checking declarations and call sites against this masked
    view prevents a comment or string literal from satisfying a required
    invariant or hiding a forbidden authority token.
    """

    chars = list(source)
    length = len(source)
    index = 0

    def blank(start: int, end: int) -> None:
        for position in range(start, end):
            if chars[position] not in "\r\n":
                chars[position] = " "

    while index < length:
        # Line and nested block comments.
        if source.startswith("//", index):
            end = source.find("\n", index)
            if end < 0:
                end = length
            blank(index, end)
            index = end
            continue
        if source.startswith("/*", index):
            start = index
            index += 2
            depth = 1
            while index < length and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            blank(start, index)
            continue

        # Raw strings (including byte raw strings) can contain comment-like
        # text. Detect the delimiter and mask through its matching terminator.
        raw_start = index
        if source[index] == "b" and index + 1 < length and source[index + 1] == "r":
            raw_start = index + 1
        if source[raw_start] == "r":
            delimiter = raw_start + 1
            while delimiter < length and source[delimiter] == "#":
                delimiter += 1
            if delimiter < length and source[delimiter] == '"':
                hashes = source[raw_start + 1 : delimiter]
                # A raw string closes with a quote followed by exactly the
                # opening hash sequence (for example `r#"..."#`).
                terminator = '"' + hashes
                end = source.find(terminator, delimiter + 1)
                end = length if end < 0 else end + len(terminator)
                blank(index, end)
                index = end
                continue

        # Ordinary strings. Escapes are skipped so an escaped quote cannot
        # terminate the masked range early.
        if source[index] == '"' or (
            source[index] == "b" and index + 1 < length and source[index + 1] == '"'
        ):
            start = index
            index += 2 if source[index] == "b" else 1
            escaped = False
            while index < length:
                char = source[index]
                index += 1
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    break
            blank(start, index)
            continue

        index += 1
    return "".join(chars)


def audit_contract(contract: object) -> None:
    require(isinstance(contract, dict), "receipt journal contract must be an object")
    if not isinstance(contract, dict):
        return
    require(
        contract.get("schema") == "trillionnium.desktop.receipt-journal-contract.v1",
        "wrong contract schema",
    )
    require(
        contract.get("status") == "SOURCE_CANDIDATE_NO_BROWSER_DISPATCH",
        "candidate status drift",
    )
    fmt = contract.get("format")
    require(isinstance(fmt, dict), "receipt journal format must be an object")
    if isinstance(fmt, dict):
        require(fmt.get("segment_header_bytes") == 148, "segment header contract drift")
        require(fmt.get("record_prefix_bytes") == 208, "record prefix contract drift")
        require(fmt.get("maximum_record_payload_bytes") == 65536, "payload bound drift")
        require(fmt.get("maximum_segment_bytes") == 67108864, "segment bound drift")

    effect_recovery = contract.get("effect_recovery")
    require(isinstance(effect_recovery, dict), "effect_recovery must be an object")
    if isinstance(effect_recovery, dict):
        require(
            effect_recovery.get("potential_external_effect") == "never_automatic",
            "external effects became replayable",
        )
        require(
            effect_recovery.get("journal_executes_or_replays_operations") is False,
            "journal gained execution authority",
        )

    ceiling = contract.get("claim_ceiling")
    require(isinstance(ceiling, dict), "claim_ceiling must be an object")
    if not isinstance(ceiling, dict):
        return
    actual_keys = set(ceiling)
    require(
        actual_keys == EXPECTED_CLAIM_CEILING,
        "claim_ceiling keys are incomplete or contain unknown claims",
    )
    for key in sorted(EXPECTED_CLAIM_CEILING):
        value = ceiling.get(key)
        require(type(value) is bool, f"claim_ceiling.{key} must be boolean")
        require(value is False, f"claim_ceiling.{key} must remain false")


def audit_source(source: str, public_api: str) -> None:
    code = mask_rust_non_code(source)
    api_code = mask_rust_non_code(public_api)

    # Structural declarations and calls. These patterns are anchored to Rust
    # syntax and evaluated after comments/literals are masked.
    required_patterns = [
        (r"^\s*const\s+SEGMENT_HEADER_LEN\s*:\s*usize\s*=\s*148\s*;", "segment header source invariant is missing"),
        (r"^\s*const\s+RECORD_PREFIX_LEN\s*:\s*usize\s*=\s*208\s*;", "record prefix source invariant is missing"),
        (r"^\s*const\s+MAX_RECORD_PAYLOAD_BYTES\s*:\s*usize\s*=\s*64\s*\*\s*1024\s*;", "payload bound source invariant is missing"),
        (r"^\s*const\s+MAX_SEGMENT_BYTES\s*:\s*u64\s*=\s*64\s*\*\s*1024\s*\*\s*1024\s*;", "segment bound source invariant is missing"),
        (r"^\s*pub\s+fn\s+inspect_chain\s*<", "public inspect_chain API is missing"),
        (r"(?s)\bpub\s+fn\s+inspect_chain\b.*?\bAsRef\s*<\s*Path\s*>", "inspect_chain path-bound generic API is missing"),
        (r"(?s)\bpub\s+fn\s+inspect_chain\b.*?TailStatus::Clean", "inspect_chain does not reject torn predecessors"),
        (r"(?s)\bpub\s+fn\s+inspect_chain\b.*?previous_segment_sha256\s*!=\s*\*previous_digest", "inspect_chain does not verify segment digest links"),
        (r"(?s)\bpub\s+fn\s+inspect_chain\b.*?previous_record_sha256\s*!=\s*previous\.last_record_sha256", "inspect_chain does not verify record digest links"),
        (r"(?:^\s*pub\s+fn\s+append\s*<|^\s*pub\s+fn\s+append\s*\()", "append API is missing"),
        (r"^\s*pub\s+fn\s+rotate\s*\(", "rotate API is missing"),
        (r"\bfn\s+validate_transition\s*\(", "lifecycle transition validator is missing"),
        (r"\bfn\s+commit_bytes\s*<|\bfn\s+commit_bytes\s*\(", "durable commit helper is missing"),
        (r"\bself\.poisoned\b", "writer poison state is missing"),
        (r"\bReplayDirective::NeverAutomatic\b", "external-effect replay ceiling is missing"),
        (r"\bPrivacyClass::SecretRedacted\b", "secret redaction guard is missing"),
    ]
    for pattern, message in required_patterns:
        require_pattern(code, pattern, message)

    # Public re-export is part of the API contract; a private helper alone is
    # insufficient for callers that need complete-chain verification.
    require_pattern(
        api_code,
        r"pub\s+use\s+receipt_journal\s*::\s*\{.*?\binspect_chain\b",
        "inspect_chain is not re-exported from hepta-session-core",
    )

    # Require executable tests, not just names in comments or docs.
    for test_name in (
        "chain_rejects_missing_or_reordered_segments",
        "chain_rejects_tampered_predecessor_digest_link",
    ):
        require_pattern(
            code,
            rf"^\s*#\[test\]\s*\n\s*fn\s+{test_name}\s*\(",
            f"receipt journal lacks executable {test_name} regression",
        )

    # Reject authority primitives only in code (comments/docs may discuss the
    # threat model without making the journal gain that authority).
    for pattern, message in (
        (r"\bTcpListener\b", "receipt journal contains a TCP listener"),
        (r"\bWebDriver\b", "receipt journal contains WebDriver authority"),
        (r"\bServoBuilder\b", "receipt journal contains Servo authority"),
        (r"\bstd::process::Command\b", "receipt journal contains process execution authority"),
        (r"\bunsafe\s*\{", "receipt journal contains unsafe code"),
        (r"\btodo!\s*\(", "receipt journal contains a TODO stub"),
        (r"\bunimplemented!\s*\(", "receipt journal contains an unimplemented stub"),
    ):
        forbid_pattern(code, pattern, message)


def main() -> int:
    try:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        source = SOURCE.read_text(encoding="utf-8")
        public_api = PUBLIC_API.read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"D0C-06 audit error: unable to load audit inputs: {error}", file=sys.stderr)
        return 1

    audit_contract(contract)
    audit_source(source, public_api)

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
