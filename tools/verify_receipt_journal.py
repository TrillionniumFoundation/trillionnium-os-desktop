#!/usr/bin/env python3
"""Fail-closed source/contract audit for D0C-06."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/receipt-journal.v1.json"
SOURCE = ROOT / "crates/hepta-session-core/src/receipt_journal.rs"
PUBLIC_API = ROOT / "crates/hepta-session-core/src/lib.rs"
CHAIN_SOURCE = ROOT / "crates/hepta-session-core/src/receipt_journal/chain.rs"
BINDING_SOURCE = ROOT / "crates/hepta-session-core/src/receipt_journal/binding.rs"
BINDING_TESTS = ROOT / "crates/hepta-session-core/src/receipt_journal/binding_tests.rs"
MANAGED_INPUTS = {
    "managed": "crates/hepta-session-core/src/receipt_journal/managed.rs",
    "source": "crates/hepta-session-core/src/receipt_journal.rs",
    "chain": "crates/hepta-session-core/src/receipt_journal/chain.rs",
    "api": "crates/hepta-session-core/src/lib.rs",
    "storage": "crates/hepta-d3-development/src/sessiond/storage.rs",
    "service": "crates/hepta-d3-development/src/sessiond/service.rs",
    "observer": "crates/hepta-browser-actor/src/lib.rs",
    "disk_tests": "crates/hepta-session-core/tests/journal_managed_store.rs",
    "process_tests": "crates/hepta-session-core/tests/journal_managed_process_recovery.rs",
    "storage_tests": "crates/hepta-d3-development/src/sessiond/storage_tests.rs",
    "service_tests": "crates/hepta-d3-development/src/sessiond/service_managed_tests.rs",
    "persistence_tests": "crates/hepta-session-core/src/receipt_journal/persistence_tests.rs",
    "persistence_process": "crates/hepta-session-core/tests/journal_persistence_process.rs",
    "cargo": "crates/hepta-session-core/Cargo.toml",
}
EXPECTED_MANAGED_STORE = {'schema': 'trillionnium.desktop.managed-receipt-store.v1',
 'opt_in': True,
 'directory_mode': '0700',
 'file_mode': '0600',
 'marker_name': 'store.v1',
 'marker_magic_ascii': 'HPTSTR01',
 'marker_bytes': 56,
 'marker_encoding': 'magic8 || journal_id16 || sha256(magic8 || journal_id16)',
 'segment_name': 'segment-{number:016}.journal',
 'pending_name': 'next.pending',
 'head_selection': 'entire_closed_contiguous_directory_inventory',
 'single_writer': 'pinned_directory_inode_advisory_lock_plus_all_segment_inode_locks',
 'commit_order': ['quiescent_full_chain',
                  'write_complete_pending_header',
                  'sync_pending',
                  'atomic_rename_to_next_canonical_name',
                  'sync_directory',
                  'admit_next_writer'],
 'pending_recovery': 'explicit_policy_complete_linked_empty_header_only_after_strict_full_chain_validation',
 'partial_or_corrupt_pending': 'reject_and_preserve_no_automatic_cleanup',
 'unmanaged_write_api': 'reject_managed_directory_marker',
 'automatic_rotation_threshold_bytes': 4194304,
 'maximum_segments': 64,
 'maximum_total_bytes': 134217728,
 'maximum_total_records': 131072,
 'service_configuration': 'HEPTA_D3_RECEIPT_STORE',
 'configuration_conflicts': ['HEPTA_D3_RECEIPT_JOURNAL', 'HEPTA_D3_RECEIPT_PREDECESSORS'],
 'automatic_migration': False,
 'automatic_pruning': False,
 'authenticated_offline_rollback_protection': False,
 'independent_exact_image_qualified': False,
 'physical_power_loss_qualified': False,
 'reopen_durability_order': ['validate_full_chain_and_pinned_identity',
                             'sync_active_file',
                             'sync_directory',
                             'revalidate_full_inventory_and_pinned_identity',
                             'return_writer'],
 'reopen_barrier_failure': 'no_writer_returned_preserve_complete_facts',
 'persistence_fault_corpus': {'control_boundary': 'private_cfg_test_only_no_product_switch',
                              'process_harness': 'isolated_custom_test_compiles_exact_journal_source',
                              'process_cut_cases': 64,
                              'injected_io_case_combinations': 128,
                              'injected_errno': [5, 28],
                              'incomplete_write': 'real_prefix_write_before_injected_error_or_sigkill',
                              'covered_operations': ['initialize',
                                                     'rotate',
                                                     'reopen',
                                                     'complete_pending',
                                                     'append',
                                                     'repair_tail'],
                              'storage_failure_simulation': True,
                              'physical_power_loss_qualified': False,
                              'in_kernel_syscall_interruption_qualified': False,
                              'automatic_replay_available': False}}

ERRORS: list[str] = []

# Canonical semantic contract, independently checked against implementation/tests.
EXPECTED_ADMISSION_BINDING = {'version': 'receipt-admission-binding.v1',
 'immutable_fields': ['receipt_id',
                      'plan_revision',
                      'image_id',
                      'servo_commit',
                      'browserd_version',
                      'session_id',
                      'operation',
                      'session_generation',
                      'document_generation',
                      'semantic_snapshot_revision',
                      'mutation_epoch',
                      'source',
                      'effect_class',
                      'privacy_class',
                      'request_sha256'],
 'internal_commitment': 'sha256(domain || length_prefixed_identity_strings || '
                        'big_endian_u64_revisions || enum_bytes || request_sha256)',
 'domain_hex': '68657074612e726563656970742e61646d697373696f6e2d62696e64696e672e763100',
 'enforced_at': ['append',
                 'recover_bytes',
                 'inspect_chain',
                 'open_chain',
                 'ReceiptEnvelope::from_records',
                 'export_journal_redacted_jsonl'],
 'mismatch_before_append': 'InvalidInput_without_write_or_progress_change',
 'mismatch_on_recovery': 'Corruption_never_tail_repaired',
 'disk_format_version': 1,
 'legacy_inconsistent_complete_record': 'reject_preserve_original_no_automatic_migration',
 'timestamps': 'retain_existing_multiclock_observations_and_maximum_logical_clock',
 'cryptographic_authentication_claim': False}


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


def strict_json(text: str) -> object:
    """Reject ambiguous object identities at every nesting level."""
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite JSON constant: {value}")

    return json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)


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
    require(json.dumps(contract.get("managed_store"), sort_keys=True)
            == json.dumps(EXPECTED_MANAGED_STORE, sort_keys=True),
            "managed receipt store contract drift")
    lifecycle = contract.get("lifecycle")
    require(
        isinstance(lifecycle, dict)
        and json.dumps(lifecycle.get("admission_binding"), sort_keys=True)
        == json.dumps(EXPECTED_ADMISSION_BINDING, sort_keys=True),
        "receipt immutable admission binding contract drift",
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
        receipt_schema = strict_json(
            (ROOT / RECEIPT_SCHEMA_RELATIVE).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as error:
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


def rust_function_body(code: str, name: str) -> str:
    """Locate a named Rust function in the comment/literal-masked source.

    This is a bounded structural guard, not a Rust parser or semantic proof.
    Executable Rust regressions remain mandatory.
    """
    match = re.search(r"\bfn\s+" + re.escape(name) + r"\s*(?:<[^{}]*>)?\s*\(", code)
    if match is None:
        return ""
    start = code.find("{", match.end())
    if start < 0:
        return ""
    depth = 0
    for index in range(start, len(code)):
        depth += (code[index] == "{") - (code[index] == "}")
        if depth == 0:
            return code[start + 1:index]
    return ""


def audit_source(
    source: str, public_api: str, chain_source: str,
    binding_source: str, binding_tests: str,
) -> None:
    code = mask_rust_non_code(source)
    api_code = mask_rust_non_code(public_api)
    chain_code = mask_rust_non_code(chain_source)
    binding_code = mask_rust_non_code(binding_source)
    binding_test_code = mask_rust_non_code(binding_tests)

    require_pattern(code, r"^\s*mod\s+binding\s*;", "admission binding module is not declared")
    require_pattern(code, r"#\[cfg\(test\)\]\s*mod\s+binding_tests\s*;", "admission binding regressions are not wired")
    for body, label in ((rust_function_body(code, name), name)
                        for name in ("append", "recover_bytes", "from_records", "export_journal_redacted_jsonl")):
        require_pattern(body, r"ReceiptProgress::advance\s*\(", f"{label} bypasses immutable admission binding")
    require_pattern(rust_function_body(chain_code, "validate_reports"),
                    r"ReceiptProgress::advance\s*\(", "chain validation bypasses immutable admission binding")
    advance = rust_function_body(binding_code, "advance")
    for pattern in (r"event\.validate\(\)\?", r"validate_transition\s*\(",
                    r"admission_digest\(event\)\?", r"previous\.admission_sha256\s*!=\s*admission_sha256"):
        require_pattern(advance, pattern, "admission binding helper lost executable validation")
    digest_body = rust_function_body(binding_code, "admission_digest")
    for field in EXPECTED_ADMISSION_BINDING["immutable_fields"]:
        require_pattern(digest_body, r"\bevent\." + re.escape(field) + r"\b",
                        f"admission binding omits immutable {field}")
    for pattern in (r"put_string\(&mut bytes,\s*value\)\?",
                    r"put_u64\(&mut bytes,\s*value\)", r"sha256\(&bytes\)"):
        require_pattern(digest_body, pattern, "admission binding encoding lost reviewed structure")
    for test_name in (
        "lifecycle_binding_rejects_every_identity_drift_before_writing",
        "lifecycle_binding_checks_identity_again_after_reopen",
        "lifecycle_binding_recomputed_record_digest_does_not_hide_semantic_corruption",
        "lifecycle_binding_envelope_rejects_request_effect_and_privacy_drift",
        "lifecycle_binding_preserves_multiclock_journal_and_rejects_negative_export_duration",
    ):
        require_pattern(binding_test_code, rf"#\[test\]\s*fn\s+{test_name}\s*\(",
                        f"admission binding lacks executable {test_name} regression")

    # Structural declarations and calls. These patterns are anchored to Rust
    # syntax and evaluated after comments/literals are masked.
    required_patterns = [
        (r"^\s*const\s+SEGMENT_HEADER_LEN\s*:\s*usize\s*=\s*148\s*;", "segment header source invariant is missing"),
        (r"^\s*const\s+RECORD_PREFIX_LEN\s*:\s*usize\s*=\s*208\s*;", "record prefix source invariant is missing"),
        (r"^\s*const\s+MAX_RECORD_PAYLOAD_BYTES\s*:\s*usize\s*=\s*64\s*\*\s*1024\s*;", "payload bound source invariant is missing"),
        (r"^\s*const\s+MAX_SEGMENT_BYTES\s*:\s*u64\s*=\s*64\s*\*\s*1024\s*\*\s*1024\s*;", "segment bound source invariant is missing"),
        (r"^\s*pub\s+fn\s+inspect_chain\s*<", "public inspect_chain API is missing"),
        (r"(?s)\bpub\s+fn\s+inspect_chain\b.*?\bAsRef\s*<\s*Path\s*>", "inspect_chain path-bound generic API is missing"),
        (r"^\s*mod\s+chain\s*;", "chain implementation module is not declared"),
        (r"(?s)\bpub\s+fn\s+inspect_chain\b.*?chain::inspect\(paths\)", "inspect_chain does not delegate to the audited chain module"),
        (r"Self::open_chain_impl\(\[path\],\s*None,\s*policy,\s*true\)", "single-segment open bypasses complete-chain admission"),
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

    # Audit the explicit helper as a separate source input and require the
    # parent call path above. Comments/literals cannot satisfy these checks.
    # This is structural auditing, not a substitute for Rust or fault tests.
    for pattern, message in (
        (r"^\s*pub\s+fn\s+open_chain\s*<", "complete-chain writer API is missing"),
        (r"\bexpected_journal_id\s*:\s*JournalId", "chain writer lacks an expected identity"),
        (r"report\.header\.journal_id\s*!=\s*expected", "chain writer does not compare expected identity"),
        (r"report\.tail\s*!=\s*TailStatus::Clean", "chain does not reject torn predecessors"),
        (r"previous_segment_sha256\s*!=\s*\*previous_digest", "chain does not verify segment digest links"),
        (r"previous_record_sha256\s*!=\s*previous\.last_record_sha256", "chain does not verify record digest links"),
        (r"validate_reports\(&inspected,\s*false\)", "read-only inspection bypasses complete-chain validation"),
        (r"let\s+progress\s*=\s*validate_reports\(&inspected,\s*policy\.repair_torn_tail\)", "writer does not restore validated global progress"),
        (r"lock_file\(&file\)", "chain does not retain locked inodes"),
        (r"pub\s+const\s+MAX_CHAIN_SEGMENTS\s*:\s*usize\s*=\s*64\s*;", "chain segment bound changed"),
        (r"pub\s+const\s+MAX_CHAIN_BYTES\s*:\s*u64\s*=\s*128\s*\*\s*1024\s*\*\s*1024\s*;", "chain byte bound changed"),
        (r"pub\s+const\s+MAX_CHAIN_RECORDS\s*:\s*u64\s*=\s*131_072\s*;", "chain record bound changed"),
    ):
        require_pattern(chain_code, pattern, message)

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
        forbid_pattern(code + "\n" + chain_code + "\n" + binding_code, pattern, message)


def audit_managed_source(inputs: dict[str, str]) -> None:
    """Explicitly supplied source snapshots; no hidden reads during mutation tests."""
    if set(inputs) != set(MANAGED_INPUTS):
        require(False, "managed audit input inventory mismatch")
        return
    audit_persistence_sources(inputs)
    code = {key: mask_rust_non_code(value) for key, value in inputs.items()}
    checks = {
        "managed": [
            r"pub\s+fn\s+create_managed\s*\(", r"pub\s+fn\s+open_managed\s*\(",
            r"pub\s+fn\s+rotate_managed\s*\(",
            r"pub\s+const\s+MANAGED_ROTATION_THRESHOLD_BYTES\s*:\s*u64\s*=\s*4\s*\*\s*1024\s*\*\s*1024",
            r"lock_file\(&directory\)", r"count\s*>=\s*MAX_CHAIN_SEGMENTS\s*\+\s*2",
            r"validate_existing_path_identity\(&entry.path\(\)\)",
            r"\*name\s*!=\s*segment_name\(index\s*\+\s*1\)",
            r"bytes\s*!=\s*self.marker_bytes", r"metadata.len\(\)\s*!=\s*MARKER_BYTES\s+as\s+u64",
            r"paths.len\(\)\s*!=\s*self.segments", r"!policy.complete_pending_rotation",
            r"Self::open_chain_impl\(paths,\s*Some\(id\),\s*OpenPolicy::STRICT,\s*false\)",
            r"guard.publish\(&mut next\)",
            r"self\s*\.progress\s*\.values\(\)\s*\.all\(\|item\|\s*item.last_state.is_terminal\(\)\)",
        ],
        "source": [r"mod\s+managed\s*;",r"managed:\s*Option<managed::ManagedDirectory>",
                   r"managed.verify_current\(\)",r"managed::reject_unmanaged_access\(path.as_ref\(\)\)",
                   r"managed::reject_unmanaged_access\(next_path.as_ref\(\)\)",r"self.managed.is_some\(\)"],
        "chain": [r"managed::reject_unmanaged_access\(path\)",r"path_lease:\s*bool"],
        "api": [r"pub\s+use\s+receipt_journal::\{.*?ManagedOpenPolicy"],
        "storage": [r"parse_managed_path\(",r"journal_present\s*\|\|\s*predecessors_present",
                    r"ReceiptJournal::open_managed\(",r"ReceiptJournal::create_managed\(",
                    r"validate_journal_path\(&root\)"],
        "service": [r"storage::open_configured\(\)",r"rotate_quiescent_store\(&mut state\)\?",
                    r"current.observer.rotate_managed\(now\)\?",r"mod\s+managed_tests\s*;"],
        "observer": [r"self.inflight.is_empty\(\)\s*&&\s*self.journal.managed_rotation_due\(\)",
                     r"self.journal.rotate_managed\(now_unix_ms\)\?"],
    }
    for key, patterns in checks.items():
        for pattern in patterns:
            require_pattern(code[key], pattern, f"managed {key} lost invariant: {pattern}")
    # Scope checks to each entrypoint: another safe call site must not mask a
    # missing check on create/open or a missing live-inventory comparison.
    for function in ("create", "open"):
        require_pattern(rust_function_body(code["source"],function),
                        r"managed::reject_unmanaged_access\(path.as_ref\(\)\)\?",
                        f"managed downgrade rejection missing from {function}")
    require_pattern(rust_function_body(code["source"],"rotate"),
                    r"managed::reject_unmanaged_access\(next_path.as_ref\(\)\)\?",
                    "managed downgrade rejection missing from rotate")
    for function in ("verify_current","publish"):
        require_pattern(rust_function_body(code["managed"],function),
                        r"paths.len\(\)\s*!=\s*self.segments",
                        f"managed exact head comparison missing from {function}")
    # Prevent comments/literals or reordered steps from satisfying durability.
    publish = rust_function_body(code["managed"], "publish")
    order = [r"next.file.sync_all\(\)",r"fs::rename\(&next.path,\s*&final_path\)",
             r"self.directory.sync_all\(\)",r"self.verify_current\(\)"]
    positions=[]
    for pattern in order:
        match=re.search(pattern,publish)
        require(match is not None, "managed publication lost mandatory durability step")
        if match: positions.append(match.start())
    require(positions == sorted(positions), "managed publication durability order changed")
    require_pattern(publish,r"next.end_offset\s*!=\s*SEGMENT_HEADER_LEN\s+as\s+u64",
                    "managed pending header length check missing")
    require_pattern(publish,r"!report.records.is_empty\(\)","managed pending facts must be rejected")
    for key,names in {
        "disk_tests":["managed_store_cannot_downgrade_to_any_unmanaged_writer_api",
                      "pending_cannot_authorize_repair_of_a_committed_predecessor",
                      "malformed_pending_is_never_discarded_or_truncated",
                      "automatic_rotation_trigger_waits_for_terminal_facts_and_resets_after_commit"],
        "process_tests":["managed_sigkill_after_acknowledged_rotation_selects_committed_successor",
                         "managed_sigkill_preserves_dispatched_external_facts_and_never_replays"],
        "storage_tests":["managed_configuration_is_opt_in_and_never_mixes_legacy_paths",
                         "managed_storage_reopens_latest_head_and_reconciles_without_replaying"],
        "service_tests":["service_rotates_only_an_idle_managed_writer_and_keeps_the_session",
                         "service_rotation_failure_does_not_replace_an_uncertain_writer"],
    }.items():
        for name in names:
            require_pattern(code[key],rf"#\[test\]\s*fn\s+{name}\s*\(",
                            f"managed executable regression missing: {name}")
    for pattern in (r"\bunsafe\s*\{",r"\bstd::process::Command\b",r"\bTcpListener\b",
                    r"\bServoBuilder\b",r"\bunimplemented!\s*\(",r"\btodo!\s*\("):
        forbid_pattern(code["managed"],pattern,"managed journal gained forbidden authority or stub")



def audit_persistence_sources(inputs: dict[str, str]) -> None:
    """The fault corpus is a source gate, never runtime or hardware promotion."""
    code = {key: mask_rust_non_code(value) for key, value in inputs.items()}
    barrier = rust_function_body(code["managed"], "stabilize_open")
    order = [
        r"self.verify_current\(\)\?", r"next.check_live_state\(\)\?",
        r"next.file.sync_all\(\).map_err\(map_io_error\)\?",
        r"self.directory.sync_all\(\).map_err\(map_io_error\)\?",
        r"self.verify_current\(\)\?", r"next.check_live_state\(\)\?",
    ]
    cursor = 0
    for pattern in order:
        match = re.search(pattern, barrier[cursor:])
        require(match is not None, "managed reopen barrier order or checked step missing")
        if match:
            cursor += match.end()
    require_pattern(rust_function_body(code["managed"], "open_managed"),
                    r"guard.stabilize_open\(&mut next\)\?",
                    "managed reopen bypasses the durable-head barrier")

    # No feature, environment variable, public API or release profile enables
    # fault injection. Each statement, not merely the test helper module, must
    # be conditionally compiled; the normal File/commit implementation is shared.
    require_pattern(code["source"], r"#\[cfg\(test\)\]\s*pub\(crate\)\s+mod\s+persistence_tests\s*;",
                    "persistence helper must be an exclusively cfg(test) module")
    for key in ("source", "managed", "chain"):
        for match in re.finditer(r"persistence_tests::(?:point|before_write)\s*\(", code[key]):
            require(re.search(r"#\[cfg\(test\)\]\s*$", code[key][:match.start()]) is not None,
                    f"persistence cutpoint is not cfg(test)-guarded in {key}")
    # Match the test wiring by source-local name and frozen path, not file count.
    require('#[path = "../src/receipt_journal.rs"]' in inputs["persistence_process"],
            "process harness must compile the exact journal source")
    require_pattern(code["persistence_process"], r"mod\s+receipt_journal\s*;",
                    "process harness source module is missing")
    try:
        cargo = tomllib.loads(inputs["cargo"])
        targets = cargo.get("test", [])
        target = [item for item in targets if item.get("name") == "journal_persistence_process"]
        require(len(target) == 1 and target[0].get("path") == "tests/journal_persistence_process.rs"
                and target[0].get("harness") is False,
                "isolated persistence process harness registration drift")
        require(cargo.get("lib", {}).get("test", True) is True,
                "persistence unit fault matrix was disabled")
        require(not cargo.get("features"), "session core gained a feature-controlled fault path")
    except (ValueError, TypeError, AttributeError) as error:
        require(False, f"persistence Cargo test inventory malformed: {error}")

    unit = code["persistence_tests"]
    for name in (
        "managed_reopen_requires_a_durability_barrier",
        "managed_rotation_io_failures_preserve_state_at_every_cut",
        "managed_initialization_io_failures_never_reset_partial_store",
        "managed_reopen_io_failures_return_no_writer_and_preserve_facts",
        "managed_pending_recovery_io_failures_never_lose_predecessors",
        "managed_append_io_failures_poison_writer_and_keep_complete_records",
        "managed_tail_repair_io_failures_recover_only_the_validated_prefix",
        "managed_reopen_barrier_order_and_no_receipt_changes",
        "managed_corrupt_store_is_rejected_before_barrier_or_mutation",
        "persistence_injection_is_thread_local_and_removed_on_drop",
    ):
        require_pattern(unit, rf"#\[test\]\s*fn\s+{name}\s*\(",
                        f"persistence executable unit regression missing: {name}")
    for key in ("persistence_tests", "persistence_process"):
        forbid_pattern(code[key], r"#\[ignore(?:\(|\])", "persistence regression cannot be ignored")
    require_pattern(unit, r"thread_local!", "persistence injection must be thread-local")
    require_pattern(unit, r"writer\s*\.write_all\(&bytes\[\.\.bytes.len\(\)\s*/\s*2\]\)",
                    "partial-write injection no longer writes a real bounded prefix")
    require_pattern(unit, r"WriterPoisoned", "failed append must poison the old writer")
    require_pattern(unit, r"ReplayDirective::NeverAutomatic", "reopen lost external-effect non-replay assertion")
    main = rust_function_body(code["persistence_process"], "main")
    require_pattern(main, r"assert_eq!\(\s*cases.len\(\),\s*64", "process matrix bound was weakened")
    require_pattern(main, r"for\s+\(case,\s*target,\s*state\)\s+in\s+&cases",
                    "process matrix must execute every declared case")
    killed = rust_function_body(code["persistence_process"], "killed_at")
    for pattern in (r"child.0.kill\(\).unwrap\(\)",
                    r"child.0.wait\(\).unwrap\(\).signal\(\),\s*Some\(9\)",
                    r"Instant::now\(\)\s*<\s*deadline", r"Duration::from_secs\(10\)"):
        require_pattern(killed, pattern, "process cut lost exact SIGKILL or bounded checkpoint")
    # These fixed cutpoint inventories are independent of the Rust loop lengths.
    # Commented-out or dropped targets cannot make a smaller matrix pass.
    expected = {
        "ROTATION_CUTS": ["seal.before_sync", "seal.after_sync", "segment.before_create",
            "segment.after_create", "commit.before_write", "commit.partial_write", "commit.after_write",
            "commit.before_sync", "commit.after_sync", "segment.before_parent_sync", "segment.after_parent_sync",
            "publish.before_file_sync", "publish.after_file_sync", "publish.before_rename",
            "publish.after_rename", "publish.before_directory_sync", "publish.after_directory_sync"],
        "REOPEN_CUTS": ["reopen.before_active_sync", "reopen.after_active_sync",
            "reopen.before_directory_sync", "reopen.after_directory_sync"],
        "APPEND_CUTS": ["commit.before_write", "commit.partial_write", "commit.after_write",
            "commit.before_sync", "commit.after_sync"],
        "REPAIR_CUTS": ["repair.before_truncate", "repair.after_truncate", "repair.before_sync", "repair.after_sync"],
    }
    expected["INITIALIZATION_CUTS"] = [
        "initialize.before_directory_create", "initialize.after_directory_create",
        "initialize.before_parent_sync", "initialize.after_parent_sync",
        "initialize.before_marker_create", "initialize.after_marker_create",
        "marker.before_write", "marker.partial_write", "marker.after_write",
        "initialize.before_marker_sync", "initialize.after_marker_sync",
        "initialize.before_directory_sync", "initialize.after_directory_sync",
    ] + expected["ROTATION_CUTS"][2:]
    # Strip comments while preserving strings for inventory comparison.
    text = re.sub(r"(?m)^\s*//[^\n]*", "", inputs["persistence_tests"])
    for name, points in expected.items():
        match = re.search(rf"const\s+{name}\s*:[^=]+?=\s*&\[(.*?)\];", text, re.S)
        actual = re.findall(r'"([^"\n]+)"', match.group(1)) if match else []
        require(actual == points, f"persistence cutpoint inventory drift: {name}")

def main() -> int:
    try:
        managed_inputs = {key: (ROOT / path).read_text(encoding="utf-8")
                          for key, path in MANAGED_INPUTS.items()}
        contract = strict_json(CONTRACT.read_text(encoding="utf-8"))
        source = SOURCE.read_text(encoding="utf-8")
        public_api = PUBLIC_API.read_text(encoding="utf-8")
        chain_source = CHAIN_SOURCE.read_text(encoding="utf-8")
        binding_source = BINDING_SOURCE.read_text(encoding="utf-8")
        binding_tests = BINDING_TESTS.read_text(encoding="utf-8")
        generated_evidence = strict_json(
            (ROOT / D0C06_GENERATED_EVIDENCE_RELATIVE).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as error:
        print(f"D0C-06 audit error: unable to load audit inputs: {error}", file=sys.stderr)
        return 1

    audit_contract(contract)
    audit_source(source, public_api, chain_source, binding_source, binding_tests)
    audit_managed_source(managed_inputs)
    # Explicit copy is a separate source boundary, not managed auto-recovery.
    import audit_receipt_migration
    try:
        migration_inputs = {key: (ROOT / path).read_text(encoding="utf-8")
                            for key, path in audit_receipt_migration.INPUTS.items()}
        migration_contract = (ROOT / audit_receipt_migration.CONTRACT).read_text(encoding="utf-8")
        ERRORS.extend(audit_receipt_migration.audit(migration_inputs, migration_contract))
    except (OSError, UnicodeError, ValueError) as error:
        ERRORS.append(f"receipt migration audit input failure: {error}")
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
