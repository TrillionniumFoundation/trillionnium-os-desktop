#!/usr/bin/env python3
"""Fail-closed source contract for the S08 exact-pin Servo vertical slice."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = "contracts/s08-servo-runtime-bridge.v1.json"
SERVO_COMMIT = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
REQUIRED_TOP = {
    "schema",
    "work_package",
    "status",
    "scope",
    "servo_commit",
    "product_bridge",
    "qualified_operations",
    "durability",
    "qualification_mailbox",
    "required_proof",
    "non_claims",
    "required_paths",
}


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON member {key!r}")
        output[key] = value
    return output


def _json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path} must contain an object")
        return {}
    return value


def _path(root: Path, relative: str, errors: list[str]) -> Path | None:
    if not relative or "\\" in relative or Path(relative).is_absolute():
        errors.append(f"invalid S08 path {relative!r}")
        return None
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        errors.append(f"non-canonical S08 path {relative!r}")
        return None
    current = root
    for index, part in enumerate(parts):
        current /= part
        try:
            mode = current.lstat().st_mode
        except OSError as error:
            errors.append(f"missing S08 path {relative}: {error}")
            return None
        if stat.S_ISLNK(mode):
            errors.append(f"S08 path traverses symlink: {relative}")
            return None
        if index < len(parts) - 1 and not stat.S_ISDIR(mode):
            errors.append(f"S08 path parent is not a directory: {relative}")
            return None
    if not current.is_file():
        errors.append(f"S08 path is not a regular file: {relative}")
        return None
    return current


def _text(root: Path, relative: str, errors: list[str]) -> str:
    path = _path(root, relative, errors)
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"cannot read {relative}: {error}")
        return ""


def _exact_keys(
    value: object, expected: set[str], label: str, errors: list[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    if set(value) != expected:
        errors.append(
            f"{label} fields differ: missing={sorted(expected - set(value))}, "
            f"unexpected={sorted(set(value) - expected)}"
        )
    return value


def _true_map(
    value: object, expected: set[str], label: str, errors: list[str]
) -> dict[str, Any]:
    mapping = _exact_keys(value, expected, label, errors)
    for key in expected:
        if mapping.get(key) is not True:
            errors.append(f"{label}.{key} must be true")
    return mapping


def validate_contract(root: Path, errors: list[str]) -> dict[str, Any]:
    contract_path = _path(root, CONTRACT_PATH, errors)
    if contract_path is None:
        return {}
    contract = _json(contract_path, errors)
    if set(contract) != REQUIRED_TOP:
        errors.append("S08 contract top-level fields differ from closed schema")
    fixed = {
        "schema": "trillionnium.desktop.s08-servo-runtime-bridge.v1",
        "work_package": "S08",
        "status": "SOURCE_CANDIDATE_EXACT_PIN_HOST_QUALIFICATION_REQUIRED",
        "scope": "attested_agentport_browseractor_exact_pin_servo_receipt_host_vertical_slice",
        "servo_commit": SERVO_COMMIT,
    }
    for key, expected in fixed.items():
        if contract.get(key) != expected:
            errors.append(f"S08 contract {key} must be {expected!r}")

    bridge = _exact_keys(
        contract.get("product_bridge"),
        {
            "concrete_actor_type",
            "generic_runtime_injection_exposed",
            "engine_owner_send",
            "engine_owner_sync",
            "commands_in_flight",
            "completion_use",
            "request_custody_rechecked_before_servo_dispatch",
            "deadline_and_cancellation_bound",
        },
        "S08 product_bridge",
        errors,
    )
    expected_bridge = {
        "concrete_actor_type": "ServoBrowserActor",
        "generic_runtime_injection_exposed": False,
        "engine_owner_send": False,
        "engine_owner_sync": False,
        "commands_in_flight": 1,
        "completion_use": "single",
        "request_custody_rechecked_before_servo_dispatch": True,
        "deadline_and_cancellation_bound": True,
    }
    for key, expected in expected_bridge.items():
        if bridge.get(key) != expected or type(expected) is int and isinstance(bridge.get(key), bool):
            errors.append(f"S08 product_bridge.{key} must be {expected!r}")

    operations = contract.get("qualified_operations")
    expected_operations = [
        "health",
        "session_create",
        "page_navigate_loopback_fixture",
        "page_observe_accessibility",
        "page_wait_element_present",
        "page_act_retained_accessibility_click",
        "session_snapshot",
        "session_close",
    ]
    if operations != expected_operations:
        errors.append("S08 qualified_operations differ from reviewed order")

    durability = _exact_keys(
        contract.get("durability"),
        {
            "requested_before_dispatch",
            "dispatched_before_runtime",
            "completed_before_transport_commit",
            "potential_effect_replay",
            "managed_receipt_store",
        },
        "S08 durability",
        errors,
    )
    if durability != {
        "requested_before_dispatch": True,
        "dispatched_before_runtime": True,
        "completed_before_transport_commit": True,
        "potential_effect_replay": "never_automatic",
        "managed_receipt_store": True,
    }:
        errors.append("S08 durability contract changed")

    mailbox = _exact_keys(
        contract.get("qualification_mailbox"),
        {
            "classification",
            "part_of_product_api",
            "part_of_install_graph",
            "maximum_record_bytes",
            "absolute_private_directory_required",
            "executes_downloaded_code",
        },
        "S08 qualification_mailbox",
        errors,
    )
    if mailbox != {
        "classification": "test_only_atomic_file_protocol",
        "part_of_product_api": False,
        "part_of_install_graph": False,
        "maximum_record_bytes": 32768,
        "absolute_private_directory_required": True,
        "executes_downloaded_code": False,
    }:
        errors.append("S08 qualification mailbox contract changed")

    _true_map(
        contract.get("required_proof"),
        {
            "exact_source_head",
            "live_prospective_merge_source_validation",
            "real_upstream_servo_webview",
            "real_accesskit_retained_node",
            "real_agentport_transport",
            "pidfd_peer_custody",
            "durable_receipt_chain",
            "stale_reference_rejection_after_navigation",
            "independent_non_author_review",
        },
        "S08 required_proof",
        errors,
    )

    nonclaims = _exact_keys(
        contract.get("non_claims"),
        {
            "production_agent_port_enabled",
            "external_navigation_or_effect_authority",
            "installed_debian_image",
            "qemu_pid1_wayland",
            "physical_hardware",
            "production_signing",
            "publication",
            "release",
        },
        "S08 non_claims",
        errors,
    )
    for key, value in nonclaims.items():
        if value is not False:
            errors.append(f"S08 non_claims.{key} must be false")

    paths = contract.get("required_paths")
    if not isinstance(paths, list) or any(not isinstance(item, str) for item in paths):
        errors.append("S08 required_paths must be a string list")
        paths = []
    if len(paths) != len(set(paths)):
        errors.append("S08 required_paths contain duplicates")
    for relative in paths:
        _path(root, relative, errors)
    return contract


def _require(text: str, marker: str, label: str, errors: list[str]) -> None:
    if marker not in text:
        errors.append(f"{label} is missing {marker!r}")


def validate_sources(root: Path, errors: list[str]) -> None:
    bridge = _text(root, "crates/hepta-browser-actor/src/servo_runtime.rs", errors)
    for marker in (
        "pub struct ServoBrowserActor",
        "pub struct ServoRuntimeEndpoint",
        "pub struct ServoRuntimeOwner",
        "pub struct ServoRuntimeCompletion",
        "pub fn servo_runtime_pair",
        "ensure_current_peer",
        "state.pending.is_some()",
        "state.retired = true",
    ):
        _require(bridge, marker, "S08 product bridge", errors)
    for forbidden in (
        "impl BrowserRequestHandler for ServoBrowserActor",
        "UnixListener",
        "TcpListener",
        "ServoBuilder",
        "servo::",
        "std::fs",
        "std::net",
        "unsafe {",
        "todo!",
        "unimplemented!",
    ):
        if forbidden in bridge:
            errors.append(f"S08 product bridge contains forbidden token {forbidden!r}")

    actor = _text(root, "crates/hepta-browser-actor/src/lib.rs", errors)
    for marker in (
        "mod servo_runtime;",
        "ServoBrowserActor",
        "ServoRuntimeOwner",
        "servo_runtime_pair",
    ):
        _require(actor, marker, "product BrowserActor facade", errors)

    product_test = _text(
        root, "crates/hepta-browser-actor/tests/s08_servo_mailbox.rs", errors
    )
    for marker in (
        "HEPTA_S08_MAILBOX",
        "serve_one_with_observer",
        "ServoBrowserActor::from_attested",
        "PeerRuntimePolicy::exact",
        "ReceiptJournal::create_managed",
        "ensure_current_peer()",
        "BrowserOperation::PageAct",
        "BrowserErrorCode::StaleDocument",
        "EXPECTED_REQUESTS * 3",
        "s08-product-result.json",
    ):
        _require(product_test, marker, "S08 product integration test", errors)
    for forbidden in (
        "D0FixtureHandler",
        "DeterministicLocalRuntime",
        "https://example",
        '"external_effect_authority": true',
    ):
        token = forbidden if isinstance(forbidden, str) else str(forbidden)
        if token in product_test:
            errors.append(f"S08 product integration test contains forbidden token {token!r}")

    servo = _text(
        root, "experiments/servo-s08-runtime/accessibility_server.rs", errors
    )
    for marker in (
        "build_webview_and_tree",
        "webview.load",
        "Role::Button",
        "action_request(button, Action::Click, None)",
        "perform_retained_action",
        "AccessibilityActionResult::Dispatched",
        "Click count 1",
        "s08-servo-result.json",
    ):
        _require(servo, marker, "S08 exact-pin Servo adapter", errors)
    for forbidden in ("WebDriver", "TcpListener", "external_https", "unsafe {"):
        if forbidden in servo:
            errors.append(f"S08 Servo adapter contains forbidden token {forbidden!r}")

    readme = _text(root, "crates/hepta-browser-actor/README.md", errors)
    for marker in (
        "candidate_exact_pin_real_servo_host_vertical_slice",
        "S08_SERVO_BROWSER_ACTOR_VERTICAL_SLICE.md",
        "s08-servo-runtime-bridge.v1.json",
        "s08_servo_mailbox.rs",
        "s08-servo-vertical-slice.yml",
    ):
        _require(readme, marker, "BrowserActor module documentation", errors)


def validate_workflow(root: Path, errors: list[str]) -> None:
    workflow = _text(root, ".github/workflows/s08-servo-vertical-slice.yml", errors)
    for marker in (
        "name: s08-servo-vertical-slice",
        "permissions:\n  contents: read",
        "github.event.pull_request.head.sha",
        "refs/pull/${{ github.event.pull_request.number }}/merge",
        "git rev-parse HEAD^1",
        "git rev-parse HEAD^2",
        SERVO_COMMIT,
        "verify-d3-patch",
        "accessibility_server.rs",
        "test_trillionnium_s08_mailbox_server",
        "real_servo_agent_port_browser_actor_receipt_chain",
        "s08-product-result.json",
        "s08-servo-result.json",
        "installed_image_proven",
        "retention-days: 30",
    ):
        _require(workflow, marker, "S08 workflow", errors)
    for forbidden in (
        "contents: write",
        "git push",
        "gh pr merge",
        "gh api -X PATCH",
        "curl | sh",
        "wget | sh",
        "workflow_run:",
    ):
        if forbidden in workflow:
            errors.append(f"S08 workflow contains forbidden mutation token {forbidden!r}")


def validate_registry(root: Path, errors: list[str]) -> None:
    path = _path(root, "manifests/modules.v1.json", errors)
    if path is None:
        return
    registry = _json(path, errors)
    modules = registry.get("modules")
    if not isinstance(modules, list):
        errors.append("module registry has no modules list")
        return
    actor = next(
        (
            entry
            for entry in modules
            if isinstance(entry, dict) and entry.get("id") == "hepta-browser-actor"
        ),
        None,
    )
    if not isinstance(actor, dict):
        errors.append("module registry lacks hepta-browser-actor")
        return
    if actor.get("status") != "candidate_exact_pin_real_servo_host_vertical_slice":
        errors.append("module registry BrowserActor status is stale")
    expected = {
        "architecture": "docs/architecture/S08_SERVO_BROWSER_ACTOR_VERTICAL_SLICE.md",
        "contracts": CONTRACT_PATH,
        "tests": "crates/hepta-browser-actor/tests/s08_servo_mailbox.rs",
        "workflows": ".github/workflows/s08-servo-vertical-slice.yml",
    }
    for field, value in expected.items():
        values = actor.get(field)
        if not isinstance(values, list) or value not in values:
            errors.append(f"module registry BrowserActor {field} lacks {value}")


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        mode = root.lstat().st_mode
    except OSError as error:
        return [f"repository root unavailable: {error}"]
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        return ["repository root must be a real directory"]
    validate_contract(root, errors)
    validate_sources(root, errors)
    validate_workflow(root, errors)
    validate_registry(root, errors)
    return errors


def main() -> int:
    errors = validate()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"S08 Servo runtime validation failed ({len(errors)} errors)", file=sys.stderr)
        return 1
    print("S08 Servo runtime validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
