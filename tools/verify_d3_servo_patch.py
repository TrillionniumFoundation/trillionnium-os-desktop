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
    "opaque_node_for_id",
    "TreeId::from(pipeline_id)",
    "request.action != Action::Click",
    "request.action != accesskit::Action::Click",
    "fire_synthetic_pointer_event_not_trusted",
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


def load_patch(manifest: dict[str, object], root: Path) -> bytes:
    patch = manifest["patch"]
    if not isinstance(patch, dict) or patch.get("format") != "ordered_unified_diff_parts":
        raise ValueError("unsupported patch manifest format")
    parts = patch.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("patch manifest has no ordered parts")
    chunks: list[bytes] = []
    seen: set[Path] = set()
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    patch_bytes = load_patch(manifest, args.root)
    patch = patch_bytes.decode("utf-8")

    actual_digest = hashlib.sha256(patch_bytes).hexdigest()
    expected_digest = manifest["patch"]["sha256"]
    if actual_digest != expected_digest:
        raise ValueError(
            f"aggregate patch digest mismatch: expected {expected_digest}, got {actual_digest}"
        )

    actual_paths = changed_paths(patch)
    expected_paths = sorted(manifest["patch"]["allowed_paths"])
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
                "sha256": actual_digest,
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
