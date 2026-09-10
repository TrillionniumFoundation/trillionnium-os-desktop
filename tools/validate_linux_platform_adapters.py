#!/usr/bin/env python3
"""Validate the closed S09 Linux platform adapter boundary."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/linux-platform-adapters.v1.json"
SOURCE = ROOT / "platform/linux/adapters.py"
INIT = ROOT / "platform/linux/__init__.py"
README = ROOT / "platform/linux/README.md"
TEST = ROOT / "tests/test_linux_platform_adapters.py"
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def strict_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-JSON numeric constant {value!r}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        fail(f"cannot decode {path.relative_to(ROOT)} strictly: {error}")
        return {}
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain one JSON object")
        return {}
    return value


def exact_keys(value: object, expected: set[str], label: str) -> bool:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != expected:
        fail(f"{label} keys differ: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
        return False
    return True


def check_contract() -> None:
    contract = strict_json(CONTRACT)
    if not exact_keys(
        contract,
        {"schema", "stage", "claim_ceiling", "adapters", "non_claims"},
        "contract",
    ):
        return
    if contract.get("schema") != "trillionnium.desktop.linux-platform-adapters.v1":
        fail("contract schema identity is invalid")
    if contract.get("stage") != "S09":
        fail("contract stage is not S09")
    if contract.get("claim_ceiling") != (
        "host_linux_mechanism_adapters_only_no_installed_image_no_external_effect_no_hardware_no_release"
    ):
        fail("contract claim ceiling widened or changed")

    adapters = contract.get("adapters")
    required = {
        "atomic_file_store",
        "entropy",
        "monotonic_clock",
        "process_identity",
        "wayland_endpoint",
        "controlled_network",
    }
    if not exact_keys(adapters, required, "adapters"):
        return
    assert isinstance(adapters, dict)

    store = adapters["atomic_file_store"]
    if exact_keys(
        store,
        {"maximum_bytes", "mode", "path_walk", "publication", "implicit_parent_creation"},
        "atomic_file_store",
    ):
        if store["maximum_bytes"] != 16 * 1024 * 1024:
            fail("atomic file maximum changed")
        if store["mode"] != "0600":
            fail("atomic files are not private")
        if store["path_walk"] != "descriptor_relative_no_follow":
            fail("atomic path walk is not descriptor relative and no-follow")
        if store["implicit_parent_creation"] is not False:
            fail("atomic store creates unreviewed parent directories")
        expected_order = [
            "exclusive_temp_create",
            "complete_write",
            "file_fsync",
            "atomic_rename",
            "directory_fsync",
        ]
        if store["publication"] != expected_order:
            fail("atomic publication order changed")

    entropy = adapters["entropy"]
    if exact_keys(
        entropy,
        {"source", "maximum_bytes", "deterministic_fallback", "all_zero_accepted"},
        "entropy",
    ):
        if entropy != {
            "source": "getrandom",
            "maximum_bytes": 4096,
            "deterministic_fallback": False,
            "all_zero_accepted": False,
        }:
            fail("entropy policy changed")

    clock = adapters["monotonic_clock"]
    if exact_keys(clock, {"source", "regression", "deadline_overflow"}, "monotonic_clock"):
        if clock != {
            "source": "time.monotonic_ns",
            "regression": "fail_closed",
            "deadline_overflow": "fail_closed",
        }:
            fail("monotonic clock policy changed")

    process = adapters["process_identity"]
    if exact_keys(
        process,
        {"sources", "uniform_uid_gid_required", "single_unified_cgroup_required", "bounded_reads"},
        "process_identity",
    ):
        if process["sources"] != ["proc_status", "proc_stat", "proc_cgroup_v2"]:
            fail("process identity sources changed")
        if any(process[key] is not True for key in (
            "uniform_uid_gid_required",
            "single_unified_cgroup_required",
            "bounded_reads",
        )):
            fail("process identity fail-closed controls weakened")

    wayland = adapters["wayland_endpoint"]
    if exact_keys(
        wayland,
        {
            "runtime_directory_owner_required",
            "runtime_directory_other_access",
            "endpoint_owner_required",
            "endpoint_type",
            "peer_credentials_required",
            "window_or_frame_claim",
        },
        "wayland_endpoint",
    ):
        expected = {
            "runtime_directory_owner_required": True,
            "runtime_directory_other_access": False,
            "endpoint_owner_required": True,
            "endpoint_type": "descriptor_pinned_non_symlink_af_unix_socket",
            "peer_credentials_required": True,
            "window_or_frame_claim": False,
        }
        if wayland != expected:
            fail("Wayland endpoint contract changed")

    network = adapters["controlled_network"]
    if exact_keys(
        network,
        {
            "scheme",
            "userinfo",
            "unicode_hostname",
            "maximum_url_bytes",
            "maximum_redirects",
            "deny_address_classes",
            "connected_peer_must_match_dns_set",
            "performs_dns_or_network_io",
        },
        "controlled_network",
    ):
        if network["scheme"] != "https" or network["userinfo"] is not False:
            fail("network URL boundary widened")
        if network["unicode_hostname"] is not False:
            fail("Unicode hostname policy changed without IDNA contract")
        if network["maximum_url_bytes"] != 4096 or network["maximum_redirects"] != 10:
            fail("network resource bound changed")
        if network["connected_peer_must_match_dns_set"] is not True:
            fail("connected peer is no longer DNS-set bound")
        if network["performs_dns_or_network_io"] is not False:
            fail("policy adapter unexpectedly performs external network I/O")
        required_classes = {
            "private", "loopback", "link_local", "multicast",
            "unspecified", "reserved", "not_global",
        }
        if set(network["deny_address_classes"]) != required_classes:
            fail("network deny classes changed")

    non_claims = contract.get("non_claims")
    expected_nonclaims = {
        "browser_principal_authorized",
        "capability_issued",
        "external_effect_executed",
        "wayland_window_created",
        "input_or_ime_delivered",
        "installed_image_qualified",
        "hardware_qualified",
        "release_authorized",
    }
    if exact_keys(non_claims, expected_nonclaims, "non_claims"):
        assert isinstance(non_claims, dict)
        if any(value is not False for value in non_claims.values()):
            fail("a non-claim was promoted by the S09 mechanism contract")


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def check_source() -> None:
    try:
        text = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(SOURCE))
    except (OSError, UnicodeError, SyntaxError) as error:
        fail(f"cannot parse Linux adapter source: {error}")
        return

    required_functions = {
        "read_bounded_regular_file",
        "read_process_identity",
        "connect_wayland_endpoint",
        "validate_external_https",
        "globally_routable",
        "bind_connected_peer",
        "validate_redirect_chain",
    }
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted(required_functions - set(functions))
    if missing:
        fail(f"Linux adapter functions are missing: {missing}")

    required_classes = {
        "MonotonicClock", "OsEntropy", "AtomicFileStore", "ProcessIdentity", "WaylandPeer"
    }
    classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    missing_classes = sorted(required_classes - classes)
    if missing_classes:
        fail(f"Linux adapter classes are missing: {missing_classes}")

    forbidden_import_roots = {"requests", "httpx", "aiohttp", "subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in forbidden_import_roots:
                    fail(f"forbidden I/O dependency imported: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".", 1)[0] in forbidden_import_roots:
                fail(f"forbidden I/O dependency imported: {node.module}")

    parent: dict[ast.AST, ast.AST] = {}
    for owner in ast.walk(tree):
        for child in ast.iter_child_nodes(owner):
            parent[child] = owner

    def owning_function(node: ast.AST) -> str | None:
        current = node
        while current in parent:
            current = parent[current]
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current.name
        return None

    forbidden_calls = {
        "eval", "exec", "compile", "os.system", "os.popen",
        "socket.getaddrinfo", "socket.create_connection", "socket.gethostbyname",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if name in forbidden_calls:
            fail(f"forbidden call in platform adapter: {name}")
        if name and name.endswith(".connect") and owning_function(node) != "connect_wayland_endpoint":
            fail("socket connect is permitted only for the local Wayland endpoint")

    atomic_source = ast.get_source_segment(text, functions.get("write")) if "write" in functions else None
    # The method is nested in a class and can be located from all function nodes.
    writes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "write"]
    if len(writes) != 1:
        fail("AtomicFileStore must own exactly one write method")
    else:
        atomic_source = ast.get_source_segment(text, writes[0]) or ""
        order = [
            atomic_source.find("os.O_EXCL"),
            atomic_source.find("os.write"),
            atomic_source.find("os.fsync(temp_fd)"),
            atomic_source.find("os.rename"),
            atomic_source.find("os.fsync(parent_fd)"),
        ]
        if any(position < 0 for position in order) or order != sorted(order):
            fail("atomic publication operations are missing or out of order")

    for marker in (
        "os.O_NOFOLLOW",
        "os.O_NONBLOCK",
        "os.O_PATH",
        "/proc/self/fd/",
        "os.O_DIRECTORY",
        "os.getrandom",
        "time.monotonic_ns",
        "socket.SO_PEERCRED",
        "parsed.is_global",
    ):
        if marker not in text:
            fail(f"required implementation marker absent: {marker}")


def check_docs_and_tests() -> None:
    for path in (INIT, README, TEST):
        if path.is_symlink() or not path.is_file():
            fail(f"required S09 path is missing or not regular: {path.relative_to(ROOT)}")
    if README.is_file():
        text = README.read_text(encoding="utf-8")
        for heading in (
            "## Status and claim ceiling",
            "## Adapter boundaries",
            "## Failure semantics",
            "## Testing and evidence",
            "## Operations",
            "## Compatibility and change protocol",
        ):
            if heading not in text:
                fail(f"Linux adapter README is missing {heading}")
        for token in ("S09", "no external effect", "installed image", "SO_PEERCRED"):
            if token.lower() not in text.lower():
                fail(f"Linux adapter README is missing marker {token!r}")


def main() -> int:
    check_contract()
    check_source()
    check_docs_and_tests()
    for error in ERRORS:
        print(f"ERROR: {error}", file=sys.stderr)
    if ERRORS:
        print(f"S09 Linux adapter validation failed ({len(ERRORS)} errors)", file=sys.stderr)
        return 1
    print("S09 Linux adapter validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
