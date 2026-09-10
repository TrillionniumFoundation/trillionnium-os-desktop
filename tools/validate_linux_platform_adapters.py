#!/usr/bin/env python3
"""Validate the closed S09 Linux platform adapter boundary."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any, Iterable

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

    def reject_float(value: str) -> None:
        raise ValueError(f"floating JSON number is not permitted: {value!r}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
            parse_float=reject_float,
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
        fail(
            f"{label} keys differ: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
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
    if contract["schema"] != "trillionnium.desktop.linux-platform-adapters.v1":
        fail("contract schema identity is invalid")
    if contract["stage"] != "S09":
        fail("contract stage is not S09")
    if contract["claim_ceiling"] != (
        "host_linux_mechanism_adapters_only_no_installed_image_"
        "no_external_effect_no_hardware_no_release"
    ):
        fail("contract claim ceiling widened or changed")

    adapters = contract["adapters"]
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
    store_keys = {
        "maximum_bytes",
        "mode",
        "path_walk",
        "publication",
        "replacement_policy",
        "post_publication_failure",
        "implicit_parent_creation",
    }
    if exact_keys(store, store_keys, "atomic_file_store"):
        expected_store = {
            "maximum_bytes": 16 * 1024 * 1024,
            "mode": "0600",
            "path_walk": "descriptor_relative_no_follow",
            "publication": [
                "exclusive_temp_create",
                "complete_write",
                "file_fsync",
                "atomic_noreplace_link",
                "destination_readback",
                "directory_fsync",
                "staging_unlink",
                "directory_fsync",
            ],
            "replacement_policy": "never_replace",
            "post_publication_failure": "typed_indeterminate_reconcile_only",
            "implicit_parent_creation": False,
        }
        if store != expected_store:
            fail("atomic file-store contract changed")

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
    if exact_keys(
        clock, {"source", "regression", "deadline_overflow"}, "monotonic_clock"
    ):
        if clock != {
            "source": "time.monotonic_ns",
            "regression": "fail_closed",
            "deadline_overflow": "fail_closed",
        }:
            fail("monotonic clock policy changed")

    process = adapters["process_identity"]
    if exact_keys(
        process,
        {
            "sources",
            "uniform_uid_gid_required",
            "single_unified_cgroup_required",
            "bounded_reads",
        },
        "process_identity",
    ):
        if process["sources"] != ["proc_status", "proc_stat", "proc_cgroup_v2"]:
            fail("process identity sources changed")
        if any(
            process[key] is not True
            for key in (
                "uniform_uid_gid_required",
                "single_unified_cgroup_required",
                "bounded_reads",
            )
        ):
            fail("process identity fail-closed controls weakened")

    wayland = adapters["wayland_endpoint"]
    wayland_keys = {
        "runtime_directory_owner_required",
        "runtime_directory_other_access",
        "endpoint_owner_required",
        "endpoint_type",
        "peer_credentials_required",
        "window_or_frame_claim",
    }
    if exact_keys(wayland, wayland_keys, "wayland_endpoint"):
        if wayland != {
            "runtime_directory_owner_required": True,
            "runtime_directory_other_access": False,
            "endpoint_owner_required": True,
            "endpoint_type": "descriptor_pinned_non_symlink_af_unix_socket",
            "peer_credentials_required": True,
            "window_or_frame_claim": False,
        }:
            fail("Wayland endpoint contract changed")

    network = adapters["controlled_network"]
    network_keys = {
        "scheme",
        "userinfo",
        "unicode_hostname",
        "maximum_url_bytes",
        "maximum_redirects",
        "deny_address_classes",
        "connected_peer_must_match_dns_set",
        "performs_dns_or_network_io",
    }
    if exact_keys(network, network_keys, "controlled_network"):
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
            "private",
            "loopback",
            "link_local",
            "multicast",
            "unspecified",
            "reserved",
            "not_global",
        }
        if set(network["deny_address_classes"]) != required_classes:
            fail("network deny classes changed")

    non_claims = contract["non_claims"]
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
        if any(type(value) is not bool or value for value in non_claims.values()):
            fail("a non-claim was promoted by the S09 mechanism contract")


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def source_segment(text: str, node: ast.AST) -> str:
    return ast.get_source_segment(text, node) or ""


def first_after(positions: Iterable[int], floor: int) -> int:
    candidates = [position for position in positions if position > floor]
    return min(candidates) if candidates else -1


def check_atomic_write(text: str, tree: ast.Module) -> None:
    store_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AtomicFileStore"
    ]
    if len(store_classes) != 1:
        fail("AtomicFileStore must be defined exactly once")
        return
    methods = {
        node.name: node
        for node in store_classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    write = methods.get("write")
    reconcile = methods.get("reconcile")
    if write is None:
        fail("AtomicFileStore.write is missing")
        return
    if reconcile is None:
        fail("AtomicFileStore.reconcile is missing")

    calls: list[tuple[int, str, str, ast.Call]] = []
    for node in ast.walk(write):
        if isinstance(node, ast.Call):
            calls.append(
                (
                    getattr(node, "lineno", -1) * 10000
                    + getattr(node, "col_offset", 0),
                    dotted_name(node.func) or "",
                    source_segment(text, node),
                    node,
                )
            )
    calls.sort(key=lambda item: item[0])

    def matching(name: str, token: str | None = None) -> list[int]:
        return [
            position
            for position, call_name, segment, _ in calls
            if call_name == name and (token is None or token in segment)
        ]

    open_positions = [
        position
        for position, name, segment, _ in calls
        if name == "os.open"
        and "temp_name" in segment
        and "os.O_EXCL" in segment
        and "os.O_NOFOLLOW" in segment
    ]
    write_positions = matching("os.write", "temp_fd")
    temp_sync_positions = matching("os.fsync", "temp_fd")
    link_positions = matching("os.link", "temp_name")
    readback_positions = matching("self._read_destination")
    parent_sync_positions = matching("os.fsync", "parent_fd")
    unlink_positions = matching("os.unlink", "temp_name")

    sequence: list[int] = []
    floor = -1
    for positions in (
        open_positions,
        write_positions,
        temp_sync_positions,
        link_positions,
        readback_positions,
        parent_sync_positions,
        unlink_positions,
        parent_sync_positions,
    ):
        position = first_after(positions, floor)
        sequence.append(position)
        floor = position
    if any(position < 0 for position in sequence):
        fail("no-replace publication operations are missing or out of order")

    link_calls = [
        node
        for _, name, segment, node in calls
        if name == "os.link" and "temp_name" in segment
    ]
    if len(link_calls) != 1:
        fail("AtomicFileStore.write must contain exactly one publication link")
    else:
        keywords = {keyword.arg: keyword.value for keyword in link_calls[0].keywords}
        follow = keywords.get("follow_symlinks")
        if not isinstance(follow, ast.Constant) or follow.value is not False:
            fail("publication link must explicitly disable symlink following")
        for key in ("src_dir_fd", "dst_dir_fd"):
            value = keywords.get(key)
            if not isinstance(value, ast.Name) or value.id != "parent_fd":
                fail(f"publication link must bind {key} to parent_fd")

    write_text = source_segment(text, write)
    for marker in (
        "except FileExistsError",
        "destination exists; replacement is not authorized",
        "published = True",
        "PublicationIndeterminate",
        "self._destination_identity",
    ):
        if marker not in write_text:
            fail(f"atomic write is missing fail-closed marker: {marker}")

    if reconcile is not None:
        reconcile_text = source_segment(text, reconcile)
        if "self._read_destination" not in reconcile_text:
            fail("reconcile does not read back the existing destination")
        if ".write(" in reconcile_text or "self.write" in reconcile_text:
            fail("reconcile must not replay or replace the publication")


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
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted(required_functions - functions)
    if missing:
        fail(f"Linux adapter functions are missing: {missing}")

    required_classes = {
        "MonotonicClock",
        "OsEntropy",
        "AtomicFileStore",
        "ProcessIdentity",
        "WaylandPeer",
    }
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
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
        "eval",
        "exec",
        "compile",
        "os.system",
        "os.popen",
        "socket.getaddrinfo",
        "socket.create_connection",
        "socket.gethostbyname",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if name in forbidden_calls:
            fail(f"forbidden call in platform adapter: {name}")
        if (
            name
            and name.endswith(".connect")
            and owning_function(node) != "connect_wayland_endpoint"
        ):
            fail("socket connect is permitted only for the local Wayland endpoint")

    check_atomic_write(text, tree)

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
        for token in (
            "S09",
            "no external effect",
            "installed image",
            "SO_PEERCRED",
            "no-replace",
            "PublicationIndeterminate",
        ):
            if token.lower() not in text.lower():
                fail(f"Linux adapter README is missing marker {token!r}")

    if TEST.is_file():
        test_text = TEST.read_text(encoding="utf-8")
        for marker in (
            "test_atomic_file_store_refuses_existing_destination",
            "test_atomic_file_store_reports_post_publication_uncertainty",
            "test_bounded_reader_rejects_fifo_without_blocking_and_reads_procfs",
            "test_wayland_connection_remains_bound_across_endpoint_replacement",
            "test_literal_url_policy_matches_connected_address_policy",
        ):
            if marker not in test_text:
                fail(f"S09 hostile corpus is missing {marker}")


def main() -> int:
    check_contract()
    check_source()
    check_docs_and_tests()
    for error in ERRORS:
        print(f"ERROR: {error}", file=sys.stderr)
    if ERRORS:
        print(
            f"S09 Linux adapter validation failed ({len(ERRORS)} errors)",
            file=sys.stderr,
        )
        return 1
    print("S09 Linux adapter validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
