#!/usr/bin/env python3
"""Closed versioned API correspondence for configured retained ingress.

This finite source inventory is not a Rust parser, peer admission, runtime
qualification or independent approval. Compile and real kernel tests remain
separate requirements; a contract field never grants a mechanism principal.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
try:
    from .artifact_evidence import load
    from .prepare_native_product_owner import read
    from .verify_approved_native_startup import rust_inventory, signature, typed_equal
except ImportError:
    from artifact_evidence import load
    from prepare_native_product_owner import read
    from verify_approved_native_startup import rust_inventory, signature, typed_equal

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/configured-retained-bootstrap.v1.json"
SOURCE = "apps/hepta-browserd/src/product_dispatch/configured_retained_bootstrap.rs"
TYPE = "ConfiguredRetainedBootstrap"
SIGNATURES = {
    TYPE + "::from_control": "pub fn from_control(connection: RootPathControlConnection, expected_agent_path: &Path) -> Result<Self, ProductDispatchError>",
    TYPE + "::from_root_document": "pub fn from_root_document(connection: RootPathControlConnection, expected_agent_path: &Path, document: ApprovedPolicyDocument) -> Result<Self, ProductDispatchError>",
    TYPE + "::original_deadline": "pub fn original_deadline(&mut self) -> Result<Instant, ProductDispatchError>",
    TYPE + "::into_admission": "pub fn into_admission(mut self) -> Result<ApprovedRetainedAdmission, ProductDispatchError>",
}
STATE_SIGNATURE = "creator_pid: u32, original_deadline: Instant, document: ApprovedPolicyDocument, receiver: RootPathAttestedHandoffReceiver,"
EXPECTED = {
    "schema": "trillionnium.desktop.configured-retained-bootstrap.v1",
    "status": "SOURCE_CANDIDATE_INSTALLED_NATIVE_INTEGRATION_PENDING",
    "requirements": ["G1", "G2"],
    "source": SOURCE,
    "documentation": "docs/architecture/CONFIGURED_RETAINED_BOOTSTRAP.md",
    "default_policy": "/etc/hepta/approved-mechanisms.v1.conf",
    "default_activation": False,
    "state_inventory": {"creator_pid": "u32", "original_deadline": "Instant",
                        "document": "ApprovedPolicyDocument", "receiver": "RootPathAttestedHandoffReceiver"},
    "authority": {
        "policy_type": "ApprovedPolicyDocument",
        "root_custody": "existing_root_owned_component_descriptor_and_document_guard",
        "role_selections": "same_original_shared_document_owner",
        "attestor": "existing_ProcfsPeerAttestor_default",
        "principal_from_caller": False,
        "raw_stream_or_monitor_export": False,
        "agent_result": "existing_ApprovedRetainedAdmission_complete_pair",
    },
    "scope": {
        "creating_pid_checked": True,
        "original_control_instant_preserved": True,
        "accepted_seconds_maximum": 20,
        "source_ceiling_may_refuse_earlier": True,
        "receive_consumes_once": True,
        "old_receiver_retired_after_transfer": True,
        "renewed_budget": False,
        "drop_preemptively_bounded": False,
        "local_refusal_proves_remote_custodian_cleanup": False,
    },
    "api": {
        TYPE + "::from_control": {
            "signature": SIGNATURES[TYPE + "::from_control"],
            "arguments": {"connection": "consumed_original_root_path_control_scope", "expected_agent_path": "original_accepted_agent_socket_path"},
            "preconditions": ["creating_process_current", "original_connection_live", "fixed_root_policy_source_safe_current"],
            "result": "opaque_configured_bootstrap_control_challenge_may_be_published",
            "errors": {"InvalidConfiguration": "fixed_document_schema_or_original_bounds_invalid", "PeerRefused": "source_missing_unsafe_changed_or_control_peer_path_refused", "DeadlineExceeded": "original_control_or_configured_source_scope_expired"},
        },
        TYPE + "::from_root_document": {
            "signature": SIGNATURES[TYPE + "::from_root_document"],
            "arguments": {"connection": "consumed_original_root_path_control_scope", "expected_agent_path": "original_accepted_agent_socket_path", "document": "consumed_opaque_root_owned_retained_configuration"},
            "preconditions": ["creating_process_current", "original_connection_live", "document_custody_and_original_source_scope_current"],
            "result": "opaque_configured_bootstrap_both_roles_select_same_moved_document",
            "errors": {"InvalidConfiguration": "existing_selected_policy_configuration_invalid", "PeerRefused": "source_changed_or_control_peer_path_refused", "DeadlineExceeded": "original_control_or_configured_source_scope_expired"},
        },
        TYPE + "::original_deadline": {
            "signature": SIGNATURES[TYPE + "::original_deadline"],
            "arguments": {"self": "exclusive_borrow_of_original_bootstrap"},
            "preconditions": ["creating_process_current", "same_document_current", "original_control_scope_current"],
            "result": "unchanged_initial_control_instant_never_a_renewal_or_effective_minimum_grant",
            "errors": {"PeerRefused": "creating_process_source_or_control_custody_refused", "DeadlineExceeded": "original_control_or_shorter_source_scope_expired"},
        },
        TYPE + "::into_admission": {
            "signature": SIGNATURES[TYPE + "::into_admission"],
            "arguments": {"self": "consumed_single_original_bootstrap"},
            "preconditions": ["creating_process_current", "same_control_and_agent_document_current", "same_retained_handoff_and_original_agent_scope_current"],
            "result": "original_complete_approved_agent_connection_private_terminal_monitor_pair",
            "errors": {"InvalidConfiguration": "existing_approved_admission_configuration_invalid", "PeerRefused": "source_control_agent_path_cancellation_or_moved_custody_refused", "DeadlineExceeded": "original_control_agent_or_shorter_source_scope_expired"},
        },
    },
    "verification": {
        "validator": "tools/verify_configured_retained_bootstrap.py",
        "contract_regressions": "tests/test_configured_retained_bootstrap.py",
        "host_kernel": "apps/hepta-browserd/tests/configured_retained_bootstrap_kernel.rs",
        "host_cases": ["same-root-document-original-pair", "policy-drift-before-receive", "shorter-source-ceiling-no-renewal", "foreign-process-refusal-parent-retained"],
        "doctest": "ConfiguredRetainedBootstrap_not_Clone",
        "kernel_support": "explicit_prelaunch_unit_and_owned_fixture_ELF_default_live_procfs",
        "no_missing_support_skip": True,
    },
    "non_claims": {
        "installed_service_wired": False,
        "actual_servo_execution": False,
        "native_owner_lifetime_renewed": False,
        "cross_uid_identity_broker": False,
        "headed_input": False,
        "hardware_qualification": False,
        "production_policy_provisioned": False,
        "independent_human_review": False,
        "signing_release_production_ready": False,
    },
}

def check(contract, source_text: str) -> None:
    typed_equal(contract, EXPECTED)
    inventory = rust_inventory(source_text)
    if set(inventory["public_api"]) != set(SIGNATURES):
        raise ValueError("configured bootstrap public API inventory differs")
    for name, wanted in SIGNATURES.items():
        if signature(inventory["public_api"][name]) != signature(wanted):
            raise ValueError("configured bootstrap public signature differs: " + name)
    public_types = {name for name, value in inventory["types"].items() if value["public"]}
    if public_types != {TYPE} or "pub" in inventory["types"][TYPE]["body"]:
        raise ValueError("configured bootstrap is not one opaque public type")
    if inventory["types"][TYPE]["body"] != signature(STATE_SIGNATURE):
        raise ValueError("configured bootstrap private state signature differs")

def validate(root: Path = ROOT) -> None:
    check(load(root / CONTRACT), read(root / SOURCE).decode("utf-8", "strict"))
    for name in [EXPECTED["documentation"], *EXPECTED["verification"].values()]:
        # Only explicit file references are read; case names and semantic
        # descriptions are not converted into paths or execution authority.
        if isinstance(name, str) and name.startswith(("tools/", "tests/", "apps/", "docs/")):
            read(root / name)

def main() -> int:
    try:
        validate()
    except (ValueError, OSError) as error:
        print("configured retained bootstrap source validation failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"source_correspondence": "PASS", "public_api_count": 4,
                      "actual_servo_execution": False, "installed_service_wired": False}))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
