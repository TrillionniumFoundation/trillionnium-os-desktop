#!/usr/bin/env python3
"""Fail-closed source/contract audit for D0C-06."""

from __future__ import annotations

import json
import hashlib
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
RECEIPT_SCHEMA_RELATIVE = "contracts/receipt.v1.schema.json"
RECEIPT_SCHEMA_SHA256 = "8610d2e9dd8ccc72b9803b2a51704aa282ccd96f50d19ac33074060e8cfc0eed"
RECEIPT_PLAN_REVISION_PATTERN = r"^(?:2026-08-28-d5|2026-08-29-d6)$"
D0C06_GENERATED_EVIDENCE_RELATIVE = (
    "docs/evidence/generated/d0c06-rust193-host-result.json"
)
D0C06_HISTORICAL_SOURCE_HEAD = "25d2d5882018b9974fc360aaf646128c6b6f175f"
D0C06_HISTORICAL_TREE_SHA = "b475213da8269c39ab7cc4dbfd33d0958da3a108"
D0C06_EVIDENCE_LIFECYCLE = "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN"
D0C06_EVIDENCE_FRESHNESS = "STALE_EVIDENCE"
D0C06_STATUS = "HOST_VALIDATED_NO_EXECUTION_OR_REPLAY_AUTHORITY"
D0C06_STALE_REASON = (
    "D0C-06 receipt-journal host result "
    "25d2d5882018b9974fc360aaf646128c6b6f175f was recorded before the current "
    "candidate tree. Rerun receipt-journal on the exact candidate head, then "
    "update the bound evidence and merge_ready flag under independent review."
)
D0C06_SOURCE_HASHES = {
    "crates/hepta-session-core/src/receipt_journal.rs":
        "0569bccde61684a3c04da472a100684e8e96902e64f4383ced04b4baa8a6ae37",
    "crates/hepta-session-core/src/lib.rs":
        "2d44ce6f72af967e57beeca3e1bb6ff1685f4c14dee4a26c36a23698b9f0c613",
}
D0C06_CONTRACT_HASHES = {
    "contracts/receipt-journal.v1.json":
        "ede044a60d2fcb3af7cc89cec519d33a0883bb904f61b6fd6046dfc693849d5f",
    "contracts/receipt.v1.schema.json":
        "efe2f78267a2b5607edc58ddab742b8675d8ca710375a479fc2f542b86b7d962",
}
D0C06_WORKFLOW_HASHES = {
    ".github/workflows/receipt-journal.yml":
        "7bae5c34ee92cd2df8ca99c3b2e5f30581aedaac5a89447a05e14970eea331c2",
}
D0C06_INPUT_HASHES = {
    "Cargo.toml": "00b944c420c8c950481c2f88f9cf76d9ae852122ae8ff50ba38d3afa72aba070",
    "Cargo.lock": "f5659c001ab565e2981c80f969c20152f176da73e162c784d8867d60fddc8104",
    "rust-toolchain.toml": "8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46",
    "tools/verify_receipt_journal.py": "c19ddb04b813649ba73d12e67c3992aa948e45209c1884f43f5fb566e500b377",
    "manifests/cargo-external-allowlist.json": "191c74d47406ea9ed416f2feb32e6b2bc7cfa9aff521af48c23283f5821723f8",
    "manifests/repository-state.json": "d0bd01043ea3c69bfc1b4c26ee1fc191c7ab85d6f671157e1bdea0e48177d46e",
    "docs/MANIFEST.json": "2f9dc912371dfd962d6ba8c4356d68e6efa09111d73eaa5e41e7c36e27d9a650",
    "docs/architecture/DURABLE_RECEIPT_JOURNAL.md": "34c87a9ae43c65372146f0e855574d8dfe5f4c32604392c7f30d1c1355484869",
    "docs/evidence/2026-08-29-d0c06-durable-receipts.md": "eddb9fa8ca98bd45ba2b84c517f2cebbdc4a2c462ba34cc6be714e940467f852",
}
D0C06_COMMANDS = {
    "repository_validation": "PASS",
    "receipt_journal_source_contract_audit": "PASS",
    "cargo_fmt_all_check": "PASS",
    "cargo_clippy_workspace_all_targets_locked_deny_warnings": "PASS",
    "cargo_test_workspace_all_targets_locked": "PASS",
    "browserd_self_check_locked": "PASS",
    "durable_journal_fault_corpus": "PASS",
    "claim_ceiling_recheck": "PASS",
}


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
    schema_binding = contract.get("receipt_envelope_schema")
    require(
        isinstance(schema_binding, dict),
        "receipt envelope schema binding is missing",
    )
    if isinstance(schema_binding, dict):
        require(
            schema_binding.get("path") == RECEIPT_SCHEMA_RELATIVE,
            "receipt envelope schema path drift",
        )
        digest = schema_binding.get("sha256")
        require(
            isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
            "receipt envelope schema digest is malformed",
        )
        if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
            try:
                actual_digest = hashlib.sha256(
                    (ROOT / RECEIPT_SCHEMA_RELATIVE).read_bytes()
                ).hexdigest()
            except OSError as error:
                require(False, f"receipt envelope schema cannot be read: {error}")
            else:
                require(
                    digest == actual_digest == RECEIPT_SCHEMA_SHA256,
                    "receipt envelope schema digest does not match the reviewed schema",
                )
        policy = schema_binding.get("version_policy")
        require(
            policy
            == "active_2026-08-29-d6_plus_historical_2026-08-28-d5_only",
            "receipt envelope schema version policy drift",
        )
    try:
        receipt_schema = json.loads(
            (ROOT / RECEIPT_SCHEMA_RELATIVE).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        require(False, f"receipt envelope JSON schema cannot be loaded: {error}")
    else:
        plan_revision = (
            receipt_schema.get("properties", {}).get("plan_revision", {})
            if isinstance(receipt_schema, dict)
            else {}
        )
        require(
            isinstance(plan_revision, dict)
            and plan_revision.get("pattern") == RECEIPT_PLAN_REVISION_PATTERN,
            "receipt envelope schema plan_revision policy must include d6 and historical d5",
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

    exports = contract.get("exports")
    require(isinstance(exports, dict), "receipt export contract must be an object")
    if isinstance(exports, dict):
        require(
            exports.get("public_receipt_envelope") == "export_redacted_jsonl",
            "public receipt export must use export_redacted_jsonl",
        )
        require(
            exports.get("public_receipt_envelope_schema") == RECEIPT_SCHEMA_RELATIVE,
            "public receipt export schema binding drift",
        )
        require(
            exports.get("public_receipt_envelope_lifecycle")
            == "requested_and_dispatched_are_aggregated_into_one_terminal_envelope",
            "public receipt lifecycle aggregation policy drift",
        )
        require(
            exports.get("public_receipt_envelope_unresolved")
            == "fail_closed_until_interrupted_or_indeterminate_terminal_record",
            "unresolved receipt export policy drift",
        )
        require(
            exports.get("forensic_lifecycle_export") == "export_journal_redacted_jsonl",
            "forensic lifecycle export binding drift",
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


def _audit_historical_hash_map(
    value: object, expected: dict[str, str], label: str
) -> None:
    require(isinstance(value, dict), f"{label} must be an object")
    if not isinstance(value, dict):
        return
    require(
        set(value) == set(expected),
        f"{label} keys must match the reviewed historical input set",
    )
    for path, digest in expected.items():
        actual = value.get(path)
        require(
            actual == digest,
            f"{label}.{path} does not match the reviewed historical digest",
        )
        require(
            isinstance(actual, str)
            and re.fullmatch(r"[0-9a-f]{64}", actual) is not None,
            f"{label}.{path} must be a lowercase SHA-256 digest",
        )


def audit_generated_evidence(value: object) -> None:
    """Audit the bounded, historical D0C-06 machine evidence artifact.

    The artifact is intentionally a historical snapshot: its PASS status is a
    capability claim, while the lifecycle/freshness fields prevent it from
    being mistaken for exact-head promotion evidence.  Hash maps are pinned to
    the historical source tree and are never compared with the current files.
    """

    require(isinstance(value, dict), "D0C-06 generated evidence must be an object")
    if not isinstance(value, dict):
        return
    require(
        value.get("schema") == "trillionnium.desktop.d0c06-rust193-host-result.v1",
        "D0C-06 generated evidence schema drift",
    )
    require(value.get("work_package") == "D0C-06", "D0C-06 generated work package drift")
    require(value.get("status") == D0C06_STATUS, "D0C-06 generated capability status drift")
    require(
        value.get("evidence_lifecycle") == D0C06_EVIDENCE_LIFECYCLE,
        "D0C-06 generated evidence must require an exact-head rerun",
    )
    require(
        value.get("evidence_freshness") == D0C06_EVIDENCE_FRESHNESS,
        "D0C-06 generated evidence freshness must be STALE_EVIDENCE",
    )
    require(value.get("merge_ready") is False, "D0C-06 generated evidence must not be merge-ready")
    require(
        value.get("stale_reason") == D0C06_STALE_REASON,
        "D0C-06 generated stale reason drift",
    )
    require(
        value.get("validated_source_head") == D0C06_HISTORICAL_SOURCE_HEAD,
        "D0C-06 generated historical source head drift",
    )
    require(
        value.get("validated_tree_sha") == D0C06_HISTORICAL_TREE_SHA,
        "D0C-06 generated historical tree digest drift",
    )

    runner = value.get("runner")
    require(isinstance(runner, dict), "D0C-06 generated runner metadata is missing")
    if isinstance(runner, dict):
        for key, expected in {
            "os": "Ubuntu 24.04.4 LTS",
            "image": "ubuntu-24.04",
            "rustc": "1.93.0",
            "host": "x86_64-unknown-linux-gnu",
        }.items():
            require(runner.get(key) == expected, f"D0C-06 generated runner.{key} drift")

    workflow = value.get("workflow")
    require(isinstance(workflow, dict), "D0C-06 generated workflow metadata is missing")
    if isinstance(workflow, dict):
        require(
            workflow.get("path") == ".github/workflows/receipt-journal.yml",
            "D0C-06 generated workflow path drift",
        )
        require(
            workflow.get("sha256") == D0C06_WORKFLOW_HASHES.get(workflow.get("path", "")),
            "D0C-06 generated workflow digest drift",
        )
        require(type(workflow.get("run_id")) is int and workflow.get("run_id") > 0,
                "D0C-06 generated workflow run_id must be positive")
        related = workflow.get("related_run_ids")
        require(
            isinstance(related, list)
            and all(type(run_id) is int and run_id > 0 for run_id in related),
            "D0C-06 generated related workflow run IDs are malformed",
        )
        require(workflow.get("conclusion") == "success", "D0C-06 generated workflow did not pass")

    _audit_historical_hash_map(value.get("source_hashes"), D0C06_SOURCE_HASHES, "source_hashes")
    _audit_historical_hash_map(
        value.get("contract_hashes"), D0C06_CONTRACT_HASHES, "contract_hashes"
    )
    _audit_historical_hash_map(
        value.get("workflow_hashes"), D0C06_WORKFLOW_HASHES, "workflow_hashes"
    )
    _audit_historical_hash_map(value.get("input_hashes"), D0C06_INPUT_HASHES, "input_hashes")

    commands = value.get("commands")
    require(isinstance(commands, dict), "D0C-06 generated commands are missing")
    if isinstance(commands, dict):
        require(set(commands) == set(D0C06_COMMANDS), "D0C-06 generated command set drift")
        for key, expected in D0C06_COMMANDS.items():
            require(commands.get(key) == expected, f"D0C-06 generated command {key} did not pass")

    ceiling = value.get("claim_ceiling")
    require(isinstance(ceiling, dict), "D0C-06 generated claim_ceiling is missing")
    if isinstance(ceiling, dict):
        require(set(ceiling) == EXPECTED_CLAIM_CEILING, "D0C-06 generated claim_ceiling keys drift")
        for key in sorted(EXPECTED_CLAIM_CEILING):
            require(type(ceiling.get(key)) is bool, f"D0C-06 generated claim_ceiling.{key} must be boolean")
            require(ceiling.get(key) is False, f"D0C-06 generated claim_ceiling.{key} must remain false")

    authority = value.get("authority")
    require(isinstance(authority, dict), "D0C-06 generated authority metadata is missing")
    if isinstance(authority, dict):
        expected_authority = {
            "browser_actor_dispatched",
            "servo_called",
            "listener_created",
            "external_effect_authorized",
            "automatic_replay_available",
        }
        require(set(authority) == expected_authority, "D0C-06 generated authority keys drift")
        for key in sorted(expected_authority):
            require(type(authority.get(key)) is bool, f"D0C-06 generated authority.{key} must be boolean")
            require(authority.get(key) is False, f"D0C-06 generated authority.{key} must remain false")
    require(
        value.get("remaining_gate")
        == "Rerun receipt-journal on the exact candidate head before promotion",
        "D0C-06 generated remaining gate drift",
    )


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
        (r"^\s*pub\s+enum\s+ReceiptStatus\s*\{", "receipt.v1 status enum is missing"),
        (r"^\s*pub\s+struct\s+ReceiptEnvelope\s*\{", "canonical receipt envelope is missing"),
        (r"\bpub\s+fn\s+from_records\s*\(", "lifecycle-to-envelope aggregation is missing"),
        (r"\bpub\s+fn\s+to_canonical_json\s*\(", "canonical receipt serializer is missing"),
        (r"\bpub\s+fn\s+export_receipt_envelopes_jsonl\s*\(", "canonical receipt export is missing"),
        (r"\bpub\s+fn\s+export_journal_redacted_jsonl\s*\(", "forensic journal export is missing"),
        (r"\bpub\s+fn\s+export_redacted_jsonl\s*\(", "public receipt export compatibility API is missing"),
        (r"ReceiptStatus::Indeterminate", "indeterminate status mapping is missing"),
        (r"ReceiptStatus::Interrupted", "interrupted status mapping is missing"),
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
        "canonical_export_matches_receipt_v1_envelope_shape",
        "canonical_export_maps_indeterminate_and_rejects_unresolved",
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
        generated_evidence = json.loads(
            (ROOT / D0C06_GENERATED_EVIDENCE_RELATIVE).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"D0C-06 audit error: unable to load audit inputs: {error}", file=sys.stderr)
        return 1

    audit_contract(contract)
    audit_source(source, public_api)
    audit_generated_evidence(generated_evidence)

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
