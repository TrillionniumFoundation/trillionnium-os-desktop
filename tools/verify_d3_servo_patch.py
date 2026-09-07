#!/usr/bin/env python3
"""Fail-closed verifier for the exact-pin D3 retained-node Servo patch."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MANDATORY_TOKENS = (
    "PerformAccessibilityAction",
    "active_document_accesskit_tree_id",
    "accessibility_node_address",
    "action_target_for_id",
    "supports_action(action)",
    "set_action_supported(Action::Click",
    "ActionNotAdvertised",
    "opaque_node_for_id",
    "TreeId::from(pipeline_id)",
    "request.action != Action::Click",
    "request.action != accesskit::Action::Click",
    "fire_synthetic_pointer_event_not_trusted",
    "test_retained_accessibility_click_dispatches_exactly_once",
)

FORBIDDEN_ADDED_PATTERNS = {
    "javascript evaluation": re.compile(r"evaluate_javascript|EvaluateJavaScript", re.I),
    "webdriver fallback": re.compile(r"WebDriver", re.I),
    "coordinate targeting": re.compile(
        r"hit_test|element_from_point|MouseMove|MouseButtonEvent|WebViewPoint", re.I
    ),
    "text search": re.compile(r"query_selector|text_content|inner_text|find_element", re.I),
}


def added_lines(patch: str) -> list[str]:
    return [
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def changed_paths(patch: str) -> list[str]:
    paths = re.findall(r"^\+\+\+ b/(.+)$", patch, flags=re.MULTILINE)
    if not paths:
        raise ValueError("patch has no changed paths")
    return sorted(set(paths))


def load_patch_section(
    section: dict[str, object],
    root: Path,
    seen: set[Path],
) -> bytes:
    if section.get("format") != "ordered_unified_diff_parts":
        raise ValueError("unsupported patch manifest format")
    parts = section.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("patch manifest has no ordered parts")

    chunks: list[bytes] = []
    for entry in parts:
        if not isinstance(entry, dict):
            raise ValueError("invalid patch part entry")
        rel = Path(str(entry.get("path", "")))
        if rel.is_absolute() or ".." in rel.parts or rel in seen:
            raise ValueError(f"invalid or duplicate patch part path: {rel}")
        seen.add(rel)

        path = (root / rel).resolve()
        if root.resolve() not in path.parents:
            raise ValueError(f"patch part escapes root: {rel}")
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        expected = str(entry.get("sha256", ""))
        if actual != expected:
            raise ValueError(f"patch part digest mismatch for {rel}")
        chunks.append(data)
    return b"".join(chunks)


def verify_digest(section_name: str, section: dict[str, object], data: bytes) -> str:
    actual = hashlib.sha256(data).hexdigest()
    expected = str(section.get("sha256", ""))
    if actual != expected:
        raise ValueError(
            f"{section_name} aggregate digest mismatch: expected {expected}, got {actual}"
        )
    return actual


def combine_sections(base: bytes, hardening: bytes) -> bytes:
    if not hardening:
        return base
    separator = b"" if base.endswith(b"\n") else b"\n"
    return base + separator + hardening


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.root.resolve()
    seen: set[Path] = set()

    patch_section = manifest.get("patch")
    if not isinstance(patch_section, dict):
        raise ValueError("manifest.patch must be an object")
    base_bytes = load_patch_section(patch_section, root, seen)
    base_digest = verify_digest("base patch", patch_section, base_bytes)

    hardening_section = manifest.get("hardening")
    hardening_bytes = b""
    hardening_digest: str | None = None
    if hardening_section is not None:
        if not isinstance(hardening_section, dict):
            raise ValueError("manifest.hardening must be an object")
        hardening_bytes = load_patch_section(hardening_section, root, seen)
        hardening_digest = verify_digest(
            "hardening patch", hardening_section, hardening_bytes
        )

    patch_bytes = combine_sections(base_bytes, hardening_bytes)
    patch = patch_bytes.decode("utf-8")
    combined_digest = hashlib.sha256(patch_bytes).hexdigest()

    actual_paths = changed_paths(patch)
    expected_paths = sorted(str(path) for path in patch_section["allowed_paths"])
    if actual_paths != expected_paths:
        raise ValueError(
            "changed-path mismatch:\n"
            f"expected={expected_paths}\n"
            f"actual={actual_paths}"
        )

    for token in MANDATORY_TOKENS:
        if token not in patch:
            raise ValueError(f"mandatory source token missing: {token}")

    additions = "\n".join(added_lines(patch))
    for name, pattern in FORBIDDEN_ADDED_PATTERNS.items():
        match = pattern.search(additions)
        if match:
            raise ValueError(f"forbidden {name} token in added source: {match.group(0)}")

    if "TODO(#4344): Forward action to Servo" not in patch:
        raise ValueError("patch does not replace the pinned Servo TODO")

    if args.output:
        args.output.write_bytes(patch_bytes)

    print(
        json.dumps(
            {
                "ok": True,
                "sha256": combined_digest,
                "base_sha256": base_digest,
                "hardening_sha256": hardening_digest,
                "changed_paths": actual_paths,
                "source_invariants": manifest["source_invariants"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - emit one clear terminal failure.
        print(f"D3 Servo patch verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
