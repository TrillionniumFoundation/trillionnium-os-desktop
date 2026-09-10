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

FORBIDDEN_ADDED_PATTERNS = (
    "get_node_by_opaque_id",
    "opaque_node_for_id",
    "struct OpaqueNode",
    "get_opaque_node",
)
MANDATORY_PATCH_TOKENS = (
    "PerformAccessibilityAction(",
    "AccessibilityActionResult",
    "GenericCallback<AccessibilityActionResult>",
    "target_tree: TreeId",
    "target_node: NodeId",
    "supports_action(Action::Click)",
    "get_node_for_accesskit_id",
    "is_connected()",
    "has_css_layout_box()",
    "send_accessibility_action",
    "ConstellationDisconnected",
    "accessibility_action_normal_enqueue_completes_once",
    "accessibility_action_already_disconnected_completes_once",
    "accessibility_action_receiver_drop_after_precheck_completes_once",
    "accessibility_action_dropped_callback_receiver_does_not_panic",
)
MANDATORY_HEADLESS_TOKENS = (
    "target_tree != accesskit::TreeId::ROOT",
    "active_document_accesskit_tree_id()",
    "perform_accessibility_action(",
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
    if set(section) != {"sha256", "parts", "purpose"}:
        raise ValueError(f"manifest section {name!r} has unexpected fields")
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


def added_lines(patch: bytes) -> str:
    text = patch.decode("utf-8")
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


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
    if not isinstance(upstream, dict) or set(upstream) != {"repository", "commit", "accesskit"}:
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
    if not isinstance(qualification["transitive_cli_sources"], list) or not qualification["transitive_cli_sources"]:
        raise ValueError("qualification.transitive_cli_sources must be non-empty")
    if not isinstance(manifest["claim_ceiling"], str) or not manifest["claim_ceiling"].strip():
        raise ValueError("claim_ceiling must be non-empty")


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
    if not isinstance(allowed, list) or not allowed or not all(isinstance(item, str) for item in allowed):
        raise ValueError("patch.allowed_paths must be a non-empty string list")
    if len(allowed) != len(set(allowed)):
        raise ValueError("patch.allowed_paths contains duplicates")

    actual = changed_paths(combined)
    if sorted(allowed) != actual:
        raise ValueError(f"changed-path mismatch: expected {sorted(allowed)!r}, got {actual!r}")

    additions = added_lines(combined)
    for token in FORBIDDEN_ADDED_PATTERNS:
        if token in additions:
            raise ValueError(f"forbidden fallback added to patch: {token}")
    for token in MANDATORY_PATCH_TOKENS:
        if token not in additions:
            raise ValueError(f"mandatory retained-node token absent: {token}")
    for token in MANDATORY_HEADLESS_TOKENS:
        if token not in additions:
            raise ValueError(f"mandatory headless-forwarding token absent: {token}")
    if b"TODO(#4344): Forward action to Servo" in additions.encode("utf-8"):
        raise ValueError("legacy unimplemented action-forwarding TODO remains in additions")
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
            name: load_patch_section(manifest, root, name)
            for name in SECTION_NAMES
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
