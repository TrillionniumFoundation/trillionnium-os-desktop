#!/usr/bin/env python3
"""Verify and materialize the split exact-pin Servo retained-node patch."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

FORBIDDEN_CODE_PATTERNS = (
    (r"\bget_node_by_opaque_id\b", "get_node_by_opaque_id"),
    (r"\bopaque_node_for_id\b", "opaque_node_for_id"),
    (r"\bstruct\s+OpaqueNode\b", "struct OpaqueNode"),
    (r"\bget_opaque_node\b", "get_opaque_node"),
)
SECTION_NAMES = ("patch", "hardening", "transport_hardening")


def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def reject_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load manifest {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"manifest {path} must be an object")
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_repo_file(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ValueError(f"unsafe patch path: {relative!r}")
    path = root.joinpath(*pure.parts)
    try:
        resolved = path.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"cannot resolve patch path {relative!r}: {error}") from error
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"patch path escapes repository: {relative!r}")
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"patch path is not a regular non-symlink file: {relative!r}")
    return resolved


def verify_digest(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def load_patch_section(
    manifest: dict[str, Any],
    root: Path,
    name: str,
) -> tuple[bytes, list[str]]:
    section = manifest.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"manifest section {name!r} must be an object")
    expected_fields = {"sha256", "parts", "purpose"}
    if name == "patch":
        expected_fields.add("allowed_paths")
    if set(section) != expected_fields:
        missing = sorted(expected_fields - set(section))
        extra = sorted(set(section) - expected_fields)
        raise ValueError(
            f"manifest section {name!r} has unexpected fields: "
            f"missing={missing!r}, extra={extra!r}"
        )
    if not isinstance(section["purpose"], str) or not section["purpose"].strip():
        raise ValueError(f"manifest section {name!r} purpose must be non-empty")
    parts = section["parts"]
    if not isinstance(parts, list) or not parts:
        raise ValueError(f"manifest section {name!r} parts must be non-empty")
    data = bytearray()
    paths: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(parts):
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise ValueError(f"{name} part {index} has unexpected fields")
        relative = record["path"]
        if not isinstance(relative, str) or relative in seen:
            raise ValueError(f"{name} part {index} path is missing or duplicated")
        seen.add(relative)
        source = checked_repo_file(root, relative)
        chunk = source.read_bytes()
        expected = verify_digest(record["sha256"], f"{name} part {index} digest")
        if sha256(chunk) != expected:
            raise ValueError(f"{name} part digest mismatch: {relative}")
        data.extend(chunk)
        paths.append(relative)
    expected_combined = verify_digest(section["sha256"], f"{name} digest")
    if sha256(bytes(data)) != expected_combined:
        raise ValueError(f"{name} combined digest mismatch")
    return bytes(data), paths


def changed_paths(patch: bytes) -> list[str]:
    try:
        text = patch.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"patch is not UTF-8: {error}") from error
    output = {
        line[len("+++ b/") :]
        for line in text.splitlines()
        if line.startswith("+++ b/") and line != "+++ /dev/null"
    }
    if not output:
        raise ValueError("patch declares no changed paths")
    return sorted(output)


def added_lines_by_path(patch: bytes) -> dict[str, str]:
    """Return only added payload lines, grouped by the path that owns each hunk."""
    try:
        text = patch.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"patch is not UTF-8: {error}") from error
    current: str | None = None
    grouped: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            current = line[len("+++ b/") :]
            grouped.setdefault(current, [])
            continue
        if line.startswith("diff --git "):
            current = None
            continue
        if current is not None and line.startswith("+") and not line.startswith("+++"):
            grouped[current].append(line[1:])
    return {path: "\n".join(lines) for path, lines in grouped.items()}


def _raw_prefix(text: str, index: int) -> tuple[int, str] | None:
    start = index
    if text.startswith("br", index):
        index += 2
    elif index < len(text) and text[index] == "r":
        index += 1
    else:
        return None
    hashes = 0
    while index < len(text) and text[index] == "#":
        hashes += 1
        index += 1
    if index >= len(text) or text[index] != '"':
        return None
    return index - start + 1, '"' + ("#" * hashes)


def strip_rust_comments(text: str) -> str:
    """Strip Rust comments without treating comment markers in strings as comments."""
    output: list[str] = []
    index = 0
    state = "code"
    block_depth = 0
    raw_end = ""
    while index < len(text):
        pair = text[index : index + 2]
        char = text[index]
        if state == "line":
            if char == "\n":
                output.append(char)
                state = "code"
            else:
                output.append(" ")
            index += 1
            continue
        if state == "block":
            if pair == "/*":
                block_depth += 1
                output.extend("  ")
                index += 2
            elif pair == "*/":
                block_depth -= 1
                output.extend("  ")
                index += 2
                if block_depth == 0:
                    state = "code"
            else:
                output.append("\n" if char == "\n" else " ")
                index += 1
            continue
        if state == "raw":
            if text.startswith(raw_end, index):
                output.extend(raw_end)
                index += len(raw_end)
                state = "code"
            else:
                output.append(char)
                index += 1
            continue
        if state in {"string", "char"}:
            output.append(char)
            if char == "\\" and index + 1 < len(text):
                output.append(text[index + 1])
                index += 2
                continue
            if (state == "string" and char == '"') or (
                state == "char" and char == "'"
            ):
                state = "code"
            index += 1
            continue

        raw = _raw_prefix(text, index)
        if raw is not None:
            prefix_length, raw_end = raw
            output.extend(text[index : index + prefix_length])
            index += prefix_length
            state = "raw"
        elif pair == "//":
            output.extend("  ")
            index += 2
            state = "line"
        elif pair == "/*":
            output.extend("  ")
            index += 2
            block_depth = 1
            state = "block"
        elif char == '"':
            output.append(char)
            index += 1
            state = "string"
        elif char == "'" and re.match(r"'(?:\\.|[^\\'])'", text[index:]):
            output.append(char)
            index += 1
            state = "char"
        else:
            output.append(char)
            index += 1
    if block_depth:
        raise ValueError("unterminated Rust block comment in patch additions")
    return "".join(output)


def combine_sections(sections: list[bytes]) -> bytes:
    combined = bytearray()
    for index, data in enumerate(sections):
        if index and combined and not combined.endswith(b"\n"):
            combined.extend(b"\n")
        combined.extend(data)
    return bytes(combined)


def verify_manifest(manifest: dict[str, Any]) -> None:
    expected_fields = {
        "schema",
        "blocker",
        "carrier_branch",
        "carrier_base_commit",
        "carrier_parent_binding",
        "carrier_head_binding",
        "upstream",
        "extracted_from",
        "patch",
        "hardening",
        "transport_hardening",
        "qualification",
        "claim_ceiling",
    }
    if set(manifest) != expected_fields:
        raise ValueError("manifest top-level fields differ from the closed schema")
    if manifest["schema"] != "trillionnium.lab.servo-patch.v1":
        raise ValueError("unexpected manifest schema")
    if manifest["blocker"] != "D3-01":
        raise ValueError("unexpected blocker")
    if not isinstance(manifest["carrier_branch"], str) or not manifest["carrier_branch"]:
        raise ValueError("carrier_branch must be non-empty")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest["carrier_base_commit"])):
        raise ValueError("carrier_base_commit must be a full Git SHA")
    upstream = manifest["upstream"]
    if not isinstance(upstream, dict) or set(upstream) != {
        "repository",
        "commit",
        "accesskit",
    }:
        raise ValueError("upstream section differs from the closed schema")
    if upstream["repository"] != "servo/servo":
        raise ValueError("unexpected upstream repository")
    if not re.fullmatch(r"[0-9a-f]{40}", str(upstream["commit"])):
        raise ValueError("upstream commit must be a full Git SHA")
    if upstream["accesskit"] != "0.24.0":
        raise ValueError("unexpected AccessKit ABI")
    qualification = manifest["qualification"]
    if not isinstance(qualification, dict):
        raise ValueError("qualification must be an object")
    required_qualification_fields = {
        "required",
        "transitive_cli_sources",
        "prospective_merge_applies_complete_package",
    }
    if set(qualification) != required_qualification_fields:
        raise ValueError("qualification fields differ from the closed schema")
    if qualification["prospective_merge_applies_complete_package"] is not True:
        raise ValueError("prospective merge must apply the complete package")
    if not isinstance(qualification["required"], list) or not qualification["required"]:
        raise ValueError("qualification.required must be non-empty")
    if not isinstance(
        qualification["transitive_cli_sources"], list
    ) or not qualification["transitive_cli_sources"]:
        raise ValueError("qualification.transitive_cli_sources must be non-empty")
    if not isinstance(manifest["claim_ceiling"], str) or not manifest[
        "claim_ceiling"
    ].strip():
        raise ValueError("claim_ceiling must be non-empty")


def _require(code: str, pattern: str, label: str) -> None:
    if re.search(pattern, code, flags=re.MULTILINE | re.DOTALL) is None:
        raise ValueError(f"mandatory retained-node structure absent: {label}")


def verify_patch_contract(
    manifest: dict[str, Any],
    combined: bytes,
    base: bytes,
    hardening: bytes,
    transport_hardening: bytes,
) -> list[str]:
    patch = manifest["patch"]
    if not isinstance(patch, dict):
        raise ValueError("patch section must be an object")
    allowed = patch.get("allowed_paths")
    if (
        not isinstance(allowed, list)
        or not allowed
        or not all(isinstance(item, str) for item in allowed)
    ):
        raise ValueError("patch.allowed_paths must be a non-empty string list")
    if len(allowed) != len(set(allowed)):
        raise ValueError("patch.allowed_paths contains duplicates")

    actual = changed_paths(combined)
    if sorted(allowed) != actual:
        raise ValueError(
            f"changed-path mismatch: expected {sorted(allowed)!r}, got {actual!r}"
        )

    additions = added_lines_by_path(combined)
    code = {
        path: strip_rust_comments(text)
        for path, text in additions.items()
        if path.endswith(".rs")
    }
    all_code = "\n".join(code.values())
    for pattern, label in FORBIDDEN_CODE_PATTERNS:
        if re.search(pattern, all_code):
            raise ValueError(f"forbidden fallback added to patch: {label}")

    layout_tree = code.get("components/layout/accessibility_tree.rs", "")
    _require(
        layout_tree,
        r"\bfn\s+action_target_for_id\s*\(",
        "retained action_target_for_id resolver",
    )
    _require(
        layout_tree,
        r"self\.nodes\.get\s*\(\s*&node_id\s*\)\s*\?",
        "exact retained node lookup",
    )
    _require(
        layout_tree,
        r"supports_action\s*\(\s*action\s*\)",
        "action advertisement copied from retained node",
    )
    _require(
        layout_tree,
        r"bounds\s*\(\s*\)\.is_some\s*\(\s*\)",
        "retained accessibility bounds check",
    )

    constellation = code.get("components/constellation/constellation.rs", "")
    script = code.get("components/script/script_thread.rs", "")
    tree_guard_code = constellation + "\n" + script
    _require(
        tree_guard_code,
        r"request\.target_tree\s*==\s*(?:accesskit::)?TreeId::ROOT",
        "root tree refusal",
    )
    _require(
        tree_guard_code,
        r"request\.target_tree\s*!=\s*(?:accesskit::)?TreeId::from\s*\(\s*pipeline_id\s*\)",
        "active pipeline tree binding",
    )

    _require(
        script,
        r"window\.reflow\s*\([^;]*ReflowGoal::UpdateTheRendering",
        "same-task retained-tree refresh",
    )
    _require(
        script,
        r"accessibility_node_address\s*\(",
        "layout retained-node address query",
    )
    _require(script, r"\bis_connected\s*\(\s*\)", "connected DOM target check")
    _require(
        script,
        r"\bhas_css_layout_box\s*\(\s*\)",
        "current layout-box check",
    )
    _require(
        script,
        r"fire_synthetic_pointer_event_not_trusted\s*\(",
        "single bounded click dispatch",
    )
    refresh = script.find("window.reflow")
    resolve = script.find("accessibility_node_address", refresh)
    dispatch = script.find("fire_synthetic_pointer_event_not_trusted", resolve)
    if min(refresh, resolve, dispatch) < 0 or not refresh < resolve < dispatch:
        raise ValueError(
            "retained-tree refresh, exact resolution, and dispatch are not ordered"
        )

    webview = code.get("components/servo/webview.rs", "")
    _require(
        webview,
        r"\bpub\s+fn\s+perform_accessibility_action\s*\(",
        "public WebView accessibility action API",
    )
    _require(
        webview,
        r"\.send_accessibility_action\s*\(",
        "response-aware WebView first hop",
    )

    proxy = code.get("components/servo/proxies.rs", "")
    _require(
        proxy,
        r"\bfn\s+send_accessibility_action\s*\(",
        "dedicated response-aware constellation send",
    )
    _require(proxy, r"\btry_send\s*\(\s*message\s*\)", "fallible first-hop send")
    _require(
        proxy,
        r"response\.send\s*\(\s*AccessibilityActionResult::ConstellationDisconnected\s*\)",
        "typed first-hop disconnect completion",
    )
    for test_name in (
        "accessibility_action_normal_enqueue_completes_once",
        "accessibility_action_already_disconnected_completes_once",
        "accessibility_action_receiver_drop_after_precheck_completes_once",
        "accessibility_action_dropped_callback_receiver_does_not_panic",
    ):
        _require(proxy, rf"\bfn\s+{re.escape(test_name)}\s*\(", test_name)

    traits = code.get("components/shared/constellation/lib.rs", "")
    _require(
        traits,
        r"\bConstellationDisconnected\b",
        "closed typed transport failure",
    )
    _require(
        traits,
        r"GenericCallback\s*<\s*AccessibilityActionResult\s*>",
        "typed callback contract",
    )

    headless = code.get("ports/servoshell/desktop/headed_window.rs", "")
    _require(
        headless,
        r"active_document_accesskit_tree_id\s*\(\s*\)",
        "headless active-tree selection",
    )
    _require(
        headless,
        r"\.perform_accessibility_action\s*\(",
        "headless action forwarding",
    )

    servo_tests = code.get("components/servo/tests/accessibility.rs", "")
    for test_name in (
        "test_retained_accessibility_click_dispatches_exactly_once",
        "test_retained_accessibility_rejects_unadvertised_and_unsupported_requests",
        "test_retained_accessibility_rejects_replaced_node_identity",
        "test_retained_accessibility_rejects_inactive_and_stale_tree",
        "test_retained_accessibility_rejects_disabled_hidden_and_non_element_targets",
        "test_retained_accessibility_dropped_callback_does_not_duplicate_dispatch",
    ):
        _require(servo_tests, rf"\bfn\s+{re.escape(test_name)}\s*\(", test_name)

    if "TODO(#4344): Forward action to Servo" in all_code:
        raise ValueError("legacy unimplemented action-forwarding TODO remains in code")
    if not base or not hardening or not transport_hardening:
        raise ValueError("all three ordered patch stages must be non-empty")
    return actual


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-output", type=Path)
    parser.add_argument("--hardening-output", type=Path)
    parser.add_argument("--transport-hardening-output", type=Path)
    args = parser.parse_args(argv)

    try:
        root = args.root.resolve(strict=True)
        manifest = load_json(args.manifest)
        verify_manifest(manifest)
        loaded = {
            name: load_patch_section(manifest, root, name) for name in SECTION_NAMES
        }
        base, base_parts = loaded["patch"]
        hardening, hardening_parts = loaded["hardening"]
        transport_hardening, transport_parts = loaded["transport_hardening"]
        combined = combine_sections([base, hardening, transport_hardening])
        actual = verify_patch_contract(
            manifest,
            combined,
            base,
            hardening,
            transport_hardening,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(combined)
        if args.base_output:
            args.base_output.parent.mkdir(parents=True, exist_ok=True)
            args.base_output.write_bytes(base)
        if args.hardening_output:
            args.hardening_output.parent.mkdir(parents=True, exist_ok=True)
            args.hardening_output.write_bytes(
                combine_sections([hardening, transport_hardening])
            )
        if args.transport_hardening_output:
            args.transport_hardening_output.parent.mkdir(parents=True, exist_ok=True)
            args.transport_hardening_output.write_bytes(transport_hardening)
        result = {
            "ok": True,
            "manifest": args.manifest.as_posix(),
            "base_parts": base_parts,
            "hardening_parts": hardening_parts,
            "transport_hardening_parts": transport_parts,
            "base_sha256": sha256(base),
            "hardening_sha256": sha256(hardening),
            "transport_hardening_sha256": sha256(transport_hardening),
            "sha256": sha256(combined),
            "bytes": len(combined),
            "changed_paths": actual,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
