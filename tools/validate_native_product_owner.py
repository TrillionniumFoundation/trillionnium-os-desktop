#!/usr/bin/env python3
"""Validate the closed source-only native consumer contract and source wiring.

Structural maintenance checks never substitute for exact-pin compilation,
actual connected invocation or independent authority review.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
try:
    from .artifact_evidence import load
    from .prepare_native_product_owner import read, PIN
except ImportError:
    from artifact_evidence import load
    from prepare_native_product_owner import read, PIN
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/native-product-owner.v1.json"
FALSE_CLAIMS = {
    "production_agent_port_enabled", "browserd_cli_starts_servo", "retained_terminal_handoff_integrated",
    "externally_approved_production_policy_provisioned", "cross_uid_live_identity_broker",
    "human_session_arbitration_integrated", "headed_gui_qualified", "all_protocol_network_confinement",
    "installed_topology_qualified", "hardware_signing_or_release",
}
EXPECTED = {
    "schema": "trillionnium.desktop.native-product-owner.v1",
    "status": "SOURCE_CANDIDATE_REAL_SERVO_EXECUTION_PENDING", "requirements": ["G2", "G3", "S08"],
    "servo_commit": PIN, "default_activation": False,
    "profile": {"id": "immutable-read-only-v1", "persistence": "ephemeral",
        "content": "fixed_data_document_no_script_or_external_resource",
        "admitted_operations": ["health", "session_create", "session_snapshot", "page_observe", "session_close"],
        "unsupported_operations": ["page_navigate", "page_act", "page_extract", "page_wait"],
        "unsupported_before_durable_admission": True, "caller_capability_boolean": False},
    "ownership": {"actor_pair": "closed_immutable_servo_runtime_pair", "adapter": "ClosedImmutableNativeOwner",
        "creator_pid_before_state_access": True, "creator_thread_before_state_access": True,
        "foreign_child_resource_cleanup": "process_exit_only_no_immediate_descriptor_claim",
        "maximum_native_webviews": 1, "commands_in_flight": 1, "completion_use": "single",
        "session_identity": "actual_actor_session_bound_to_one_native_webview",
        "document_identity": "current_actual_accesskit_document_tree_id",
        "semantic_source": "actual_owned_webview_delegate_tree_updates", "same_owner_reconstruction_after_retirement": False},
    "bounds": {"original_connection_seconds": 20, "native_command_seconds": 5,
        "native_deadline": "min_original_request_instant_and_first_command_receipt_plus_5_seconds",
        "deadline_renewal": False, "maximum_tree_updates": 64, "maximum_tree_nodes": 256,
        "maximum_node_text_bytes": 4096, "maximum_result_bytes": 65536, "native_syscall_preemption": False},
    "close": {"native_binding_and_handle_release": "possible_effect", "pipeline_retirement_confirmed": False,
        "completion": "browser_crashed_error", "durable_lifecycle": "indeterminate",
        "coordinator_state": "replay_reconciliation_required", "automatic_replay": False,
        "successful_closed_response": False},
    "qualification": {"consumer_module": "experiments/servo-product-owner/src/native_owner.rs",
        "connected_target": "experiments/servo-product-owner/src/connected_tests.rs",
        "source_preparation": "tools/prepare_native_product_owner.py", "source_validator": "tools/validate_native_product_owner.py",
        "workflow": ".github/workflows/g2-native-product-owner.yml",
        "configured_policy": "explicit_same_uid_transient_unit_launcher_tuple_before_start",
        "procfs_source": "default_live", "managed_receipt_journal": True, "mailbox": False,
        "test_names": ["actual_connected_immutable_semantic_snapshot", "unsupported_operations_never_enter_durable_or_native_dispatch",
            "native_handle_release_is_uncertain_and_blocks_reconstruction", "wrong_live_policy_and_cancelled_original_connection_refuse_admission"]},
    "non_claims": dict.fromkeys(FALSE_CLAIMS, False),
}

def typed_equal(actual: object, expected: object, path: str = "contract") -> None:
    if type(actual) is not type(expected):
        raise ValueError(f"{path} has a different exact type")
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f"{path} has unknown or missing fields")
        for key, value in expected.items(): typed_equal(actual[key], value, path + "." + key)
    elif isinstance(expected, list):
        if len(actual) != len(expected): raise ValueError(f"{path} list length changed")
        for index, value in enumerate(expected): typed_equal(actual[index], value, f"{path}[{index}]")
    elif actual != expected:
        raise ValueError(f"{path} differs from the fixed source scope")

def validate(root: Path = ROOT) -> None:
    typed_equal(load(root / CONTRACT), EXPECTED)
    native = read(root / EXPECTED["qualification"]["consumer_module"]).decode("utf-8")
    actor = read(root / "crates/hepta-browser-actor/src/servo_runtime.rs").decode("utf-8")
    target = read(root / EXPECTED["qualification"]["connected_target"]).decode("utf-8")
    for marker in ["pub struct ClosedImmutableNativeOwner", "closed_immutable_servo_runtime_pair", "WebViewBuilder::new",
        "notify_accessibility_tree_update", "document_tree_id", "pending.completion.ensure_current_peer()", "self.creator_pid != std::process::id()",
        "self.creator_thread != thread::current().id()", "completion.deadline().min(local_stop)", "ServoRuntimeError::BrowserCrashed"]:
        if marker not in native: raise ValueError(f"actual native consumer is missing {marker}")
    for forbidden in ["evaluate_javascript", "perform_accessibility_action", "perform_checked_accessibility_action", "TcpListener", "UnixListener", "HEPTA_S08_MAILBOX"]:
        if forbidden in native: raise ValueError("closed consumer contains unsupported authority path")
    for marker in ["profile: ServoProfile", "self.finish_profile_preflight(request, refusal)", "self.profile.refusal(&request.operation)", "pub fn closed_immutable_servo_runtime_pair"]:
        if marker not in actor: raise ValueError("closed facade selection/admission wiring is absent")
    for marker in ["AcceptedProductConnection::attest", "ProcfsPeerAttestor::default()", "ProductRequestCoordinator::from_connection", "ReceiptJournal::create_managed", "ReceiptLifecycleState::Indeterminate"]:
        if marker not in target: raise ValueError("connected invocation/journal wiring is absent")
    for name in EXPECTED["qualification"]["test_names"]:
        if f"fn {name}()" not in target: raise ValueError("actual target case is absent")
    for path in [EXPECTED["qualification"]["source_preparation"], EXPECTED["qualification"]["workflow"], "docs/architecture/NATIVE_IMMUTABLE_PRODUCT_OWNER.md"]:
        read(root / path)

def main() -> int:
    try: validate()
    except (ValueError, OSError) as error:
        print(f"native immutable owner source validation failed: {error}", file=sys.stderr); return 1
    print(json.dumps({"source_contract": "PASS", "actual_servo_execution": "PENDING", "installed_activation": False}))
    return 0
if __name__ == "__main__": raise SystemExit(main())
