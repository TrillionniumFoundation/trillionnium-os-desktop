#!/usr/bin/env python3
"""Closed exact-pin source/patch and actual semantic-corpus result verifier.

Default verification is read-only. Upstream verification applies all patches only in a
temporary copied source set, preserving the original pristine checkout on every outcome.
The standalone Rust check compiles the actual new module, not Servo or a product runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

try:
    from .artifact_evidence import load, open_file, safe_relative, load_json_strict
except ImportError:
    from artifact_evidence import load, open_file, safe_relative, load_json_strict

PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
MANIFEST = "manifests/lab-s08-semantic-custody.v1.json"
PATCH = "manifests/servo-patches/s08-semantic-custody-v1/000.patch"
PREREQUISITE = "manifests/lab-d3-servo-retained-node-action.v1.json"
ALLOWED_PATHS = [
    "Cargo.lock", "components/constellation/constellation.rs", "components/constellation/tracing.rs",
    "components/layout/accessibility_tree.rs", "components/layout/layout_impl.rs",
    "components/script/event_loop/script_thread.rs", "components/script/messaging.rs", "components/servo/lib.rs",
    "components/servo/webview.rs", "components/shared/base/Cargo.toml",
    "components/shared/base/accessibility_semantics.rs", "components/shared/base/lib.rs",
    "components/shared/constellation/lib.rs", "components/shared/layout/lib.rs",
    "components/shared/script/lib.rs",
]
SEMANTIC_SCHEMA = {
    "version": 1, "name_encoding": "raw_utf8_without_normalization",
    "maximum_name_bytes": 1024, "maximum_ancestry_nodes": 16,
    "maximum_name_preimage_bytes": 1057, "maximum_structural_preimage_bytes": 16647,
    "maximum_result_bytes": 4096,
    "ancestry_order": "retained_leaf_to_document_root_no_graft",
    "hash": "sha2_0.11.0_sha256", "name_domain": "trillionnium.accesskit.name\\0",
    "structural_domain": "trillionnium.accesskit.semantic\\0",
    "ipc_shape": "fixed_size_serde_closed_fields",
}
NEGATIVES = {
    "same_node_label": "TargetSemanticMismatch",
    "same_node_role": "TargetSemanticMismatch",
    "same_node_ancestry": "TargetSemanticMismatch",
    "replacement": "StaleNode", "disabled": "TargetDisabled",
    "hidden": "TargetNotRendered", "stale_epoch_expectation": "TargetSemanticMismatch",
}
ORIGINAL_STIMULUS = {
    "agentport_requests": 10, "servo_commands": 9, "durable_receipt_facts": 30,
    "positive_dom_clicks": 1, "s07_patch_and_test_bodies_unchanged": True,
}
CLAIMS = {
    "actual_servo_execution_requires_exact_pin_ci": True,
    "source_fixtures_are_servo_proof": False, "installed_product_activation": False,
    "final_script_peer_control_custody": False, "external_effect_authority": False,
    "release": False,
}
MAX_SOURCE_BYTES = 1024 * 1024
MAX_PATCH_BYTES = 256 * 1024
MAX_RESULT_BYTES = 4096
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:[^\n]*)\n\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")


def read(path: Path, maximum: int = MAX_SOURCE_BYTES) -> bytes:
    with os.fdopen(open_file(path.absolute()), "rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > maximum:
            raise ValueError("source input exceeds byte bound")
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        fields = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if len(data) > maximum or len(data) != before.st_size or fields(before) != fields(after):
            raise ValueError("source input changed during retained read")
    return data


def exact(value: object, expected: object, label: str) -> None:
    # Canonical JSON distinguishes integer/bool/float aliases in source profiles and results.
    import json
    if isinstance(value, set) and isinstance(expected, set):
        if value != expected:
            raise ValueError(f"{label} differs from closed schema")
        return
    if json.dumps(value, sort_keys=True, separators=(",", ":")) != json.dumps(expected, sort_keys=True, separators=(",", ":")):
        raise ValueError(f"{label} differs from closed schema")


def fields(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    exact(set(value), expected, label)
    return value


def parse_patch(data: bytes) -> dict[str, list[str]]:
    text = data.decode("utf-8", "strict")
    chunks = text.split("diff --git ")
    if chunks[0] or len(chunks) != len(ALLOWED_PATHS) + 1:
        raise ValueError("semantic patch has unexpected section count")
    output: dict[str, list[str]] = {}
    for chunk in chunks[1:]:
        lines = chunk.splitlines(keepends=True)
        header = lines.pop(0).removesuffix("\n")
        match = re.fullmatch(r"a/(\S+) b/(\S+)", header)
        if match is None or match[1] != match[2]:
            raise ValueError("semantic patch redirects a source path")
        path = safe_relative(match[1]).as_posix()
        if path not in ALLOWED_PATHS or path in output:
            raise ValueError("semantic patch path is undeclared or repeated")
        new_file = path == "components/shared/base/accessibility_semantics.rs"
        if new_file:
            exact(lines.pop(0), "new file mode 100644\n", "semantic new-file mode")
        exact(lines.pop(0), "--- /dev/null\n" if new_file else f"--- a/{path}\n", "semantic old path")
        exact(lines.pop(0), f"+++ b/{path}\n", "semantic new path")
        if not lines or HUNK.fullmatch(lines[0]) is None:
            raise ValueError("semantic patch has no exact hunk")
        output[path] = lines
    exact(list(output), ALLOWED_PATHS, "semantic patch order")
    return output


def apply_exact(before: bytes | None, lines: list[str]) -> bytes:
    source = [] if before is None else before.decode("utf-8", "strict").splitlines(keepends=True)
    output: list[str] = []
    cursor = 0
    index = 0
    while index < len(lines):
        header = HUNK.fullmatch(lines[index])
        if header is None:
            raise ValueError("unexpected semantic hunk syntax")
        old_start, old_count, new_start, new_count = [int(header[group] or "1") for group in range(1, 5)]
        position = old_start - 1 if old_count else old_start
        if position < cursor or position > len(source):
            raise ValueError("semantic hunk range escapes original file")
        output += source[cursor:position]
        if new_start != len(output) + (1 if new_count else 0):
            raise ValueError("semantic new hunk range differs")
        cursor = position
        index += 1
        consumed = produced = 0
        while index < len(lines) and HUNK.fullmatch(lines[index]) is None:
            line = lines[index]
            if not line or line[0] not in " +-" or not line.endswith("\n"):
                raise ValueError("unsupported semantic hunk record")
            kind, body = line[0], line[1:]
            if kind in " -":
                if cursor >= len(source) or source[cursor] != body:
                    raise ValueError("semantic patch does not exactly match post-S07 source")
                cursor += 1
                consumed += 1
            if kind in " +":
                output.append(body)
                produced += 1
            index += 1
        if (consumed, produced) != (old_count, new_count):
            raise ValueError("semantic hunk counts differ")
    output += source[cursor:]
    return "".join(output).encode("utf-8")


def verify(root: Path) -> tuple[dict[str, Any], dict[str, list[str]]]:
    manifest = load(root / MANIFEST)
    exact(set(manifest), {"schema", "status", "servo_commit", "prerequisite_manifest", "prerequisite_manifest_sha256", "patch", "semantic_schema", "original_stimulus", "required_negative_cases", "claim_ceiling", "standalone_source_check"}, "semantic manifest fields")
    exact(manifest["schema"], "trillionnium.lab.s08-semantic-custody.v1", "semantic schema")
    exact(manifest["status"], "SOURCE_CANDIDATE_EXACT_PIN_RUNTIME_REQUIRED", "semantic status")
    exact(manifest["servo_commit"], PIN, "semantic Servo pin")
    exact(manifest["prerequisite_manifest"], PREREQUISITE, "prerequisite manifest path")
    exact(hashlib.sha256(read(root / PREREQUISITE)).hexdigest(), manifest["prerequisite_manifest_sha256"], "original S07 manifest digest")
    exact(manifest["semantic_schema"], SEMANTIC_SCHEMA, "bounded semantic profile")
    exact(manifest["original_stimulus"], ORIGINAL_STIMULUS, "original stimulus")
    exact(manifest["required_negative_cases"], list(NEGATIVES), "semantic negative corpus")
    exact(manifest["claim_ceiling"], CLAIMS, "semantic claim ceiling")
    standalone = fields(manifest["standalone_source_check"], {"manifest_path", "manifest_sha256", "lock_path", "lock_sha256", "fixture_only", "expected_tests"}, "standalone source profile fields")
    for key, leaf in (("manifest", "Cargo.toml"), ("lock", "Cargo.lock")):
        path = "experiments/servo-s08-runtime/semantic-source-check/" + leaf
        exact(standalone[key + "_path"], path, "standalone source path")
        exact(hashlib.sha256(read(root / path)).hexdigest(), standalone[key + "_sha256"], "standalone pinned source digest")
    exact(standalone["fixture_only"], True, "standalone evidence scope")
    exact(standalone["expected_tests"], 6, "standalone Rust corpus count")
    exact(tomllib.loads(read(root / standalone["manifest_path"]).decode()), {
        "package": {"name": "s08-semantic-standalone-source-check", "version": "0.0.0", "edition": "2024"},
        "lib": {"path": "semantic_source.rs"},
        "dependencies": {"accesskit": {"version": "=0.24.0", "features": ["serde"]},
                         "sha2": "=0.11.0", "serde": {"version": "=1.0.228", "features": ["derive"]},
                         "serde_json": "=1.0.151"},
    }, "standalone exact pinned dependency profile")
    section = fields(manifest["patch"], {"path", "sha256", "allowed_paths", "source_pins"}, "semantic patch fields")
    exact(section["path"], PATCH, "semantic patch path")
    exact(section["allowed_paths"], ALLOWED_PATHS, "semantic declared paths")
    data = read(root / PATCH, MAX_PATCH_BYTES)
    exact(hashlib.sha256(data).hexdigest(), section["sha256"], "semantic patch digest")
    parsed = parse_patch(data)
    rows = section["source_pins"]
    if not isinstance(rows, list) or len(rows) != len(ALLOWED_PATHS):
        raise ValueError("semantic source pin count differs")
    for path, row in zip(ALLOWED_PATHS, rows, strict=True):
        fields(row, {"path", "original_blob_sha1", "original_sha256", "post_s07_sha256", "semantic_sha256"}, "source pin fields")
        exact(row["path"], path, "source pin path")
        for key in ("original_blob_sha1", "original_sha256", "post_s07_sha256", "semantic_sha256"):
            value = row[key]
            if path.endswith("/accessibility_semantics.rs") and key != "semantic_sha256":
                exact(value, None, "new source absence")
            elif not isinstance(value, str) or (SHA1 if key == "original_blob_sha1" else SHA256).fullmatch(value) is None:
                raise ValueError("invalid pinned source digest")
    module = apply_exact(None, parsed["components/shared/base/accessibility_semantics.rs"])
    exact(hashlib.sha256(module).hexdigest(), rows[ALLOWED_PATHS.index("components/shared/base/accessibility_semantics.rs")]["semantic_sha256"], "semantic module source digest")
    for marker in (b"MAX_ACCESSIBILITY_NAME_BYTES: usize = 1024", b"MAX_ACCESSIBILITY_ANCESTRY: usize = 16", b"ACCESSIBILITY_SEMANTIC_VERSION: u16 = 1", b"#[serde(deny_unknown_fields)]", b"use sha2::{Digest, Sha256};", b"self.ids[..depth].contains(&id)"):
        if marker not in module:
            raise ValueError("semantic source boundary marker missing")
    script = "".join(parsed["components/script/event_loop/script_thread.rs"])
    for marker in ("if current != expected", "expected.is_well_formed()", "expected.tree_id() != request.target_tree", "expected.node_id() != request.target_node", "accessibility_semantic_expectation(", "ObserveAccessibilitySemantics"):
        if marker not in script:
            raise ValueError("final same-task semantic comparison missing")
    additions = "\n".join(line[1:] for lines in parsed.values() for line in lines if line.startswith("+"))
    for pattern in (r"evaluate_javascript|EvaluateJavaScript|WebDriver", r"query_selector|element_from_point|hit_test", r"fire_synthetic_pointer_event_not_trusted"):
        if re.search(pattern, additions):
            raise ValueError("semantic production patch adds an action fallback or extra dispatch")
    return manifest, parsed


def verify_upstream_sources(root: Path, upstream: Path, manifest: dict[str, Any], parsed: dict[str, list[str]]) -> None:
    prerequisite = load(root / PREREQUISITE)
    paths = sorted(set(prerequisite["patch"]["allowed_paths"]) | set(ALLOWED_PATHS))
    originals: dict[str, bytes | None] = {}
    for path in paths:
        originals[path] = None if path.endswith("/accessibility_semantics.rs") else read(upstream / path)
    for row in manifest["patch"]["source_pins"]:
        data = originals[row["path"]]
        if data is None:
            if (upstream / row["path"]).exists() or (upstream / row["path"]).is_symlink():
                raise ValueError("new semantic source already exists")
            continue
        exact(hashlib.sha256(data).hexdigest(), row["original_sha256"], "original exact-pin bytes")
        exact(hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest(), row["original_blob_sha1"], "original exact-pin Git blob")
    with tempfile.TemporaryDirectory(prefix="s08-semantic-pristine-") as temporary:
        stage = Path(temporary)
        for path, data in originals.items():
            if data is not None:
                destination = stage / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
        for section in (prerequisite["patch"], prerequisite["hardening"]):
            for entry in section["parts"]:
                data = read(root / safe_relative(entry["path"]), MAX_PATCH_BYTES)
                exact(hashlib.sha256(data).hexdigest(), entry["sha256"], "unchanged S07 part")
                # Original S07 part 006 has its already-qualified one-line context fuzz.
                # New semantic hunks use the exact transformer below, with zero fuzz/offset.
                result = subprocess.run(["patch", "--batch", "--forward", "-p1", "-d", str(stage)], input=data, capture_output=True, timeout=30, check=False)
                if result.returncode:
                    raise ValueError("original S07 prerequisite did not apply")
        after_sources: dict[str, bytes] = {}
        for row in manifest["patch"]["source_pins"]:
            path = row["path"]
            before = None if originals[path] is None else read(stage / path)
            exact(None if before is None else hashlib.sha256(before).hexdigest(), row["post_s07_sha256"], "post-S07 source bytes")
            after = apply_exact(before, parsed[path])
            exact(hashlib.sha256(after).hexdigest(), row["semantic_sha256"], "semantic after-source bytes")
            after_sources[path] = after
        before_lock = tomllib.loads(read(stage / "Cargo.lock").decode())
        after_lock = tomllib.loads(after_sources["Cargo.lock"].decode())
        exact(len(after_lock["package"]), len(before_lock["package"]), "upstream locked package count")
        for before, after in zip(before_lock["package"], after_lock["package"], strict=True):
            expected = dict(before)
            if before["name"] == "servo-base":
                expected["dependencies"] = sorted(before["dependencies"] + ["sha2 0.11.0"])
            exact(after, expected, "unchanged pinned package or minimal sha2 edge")
        pinned_registry = {(item["name"], item["version"], item.get("source"), item.get("checksum")) for item in before_lock["package"] if "source" in item}
        standalone_lock = tomllib.loads(read(root / manifest["standalone_source_check"]["lock_path"]).decode())
        for item in standalone_lock["package"]:
            if "source" in item and (item["name"], item["version"], item.get("source"), item.get("checksum")) not in pinned_registry:
                raise ValueError("standalone dependency drifted from exact pin registry bytes")
        # No write has been made to upstream: failures and success discard only this private copy.
    for path, original in originals.items():
        if original is not None and read(upstream / path) != original:
            raise ValueError("pristine upstream source changed during verification")


def verify_result(path: Path) -> None:
    actual = load_json_strict(read(path, MAX_RESULT_BYTES).decode("utf-8", "strict"))
    expected = {"schema": "trillionnium.desktop.s08-semantic-result.v1", "servo_commit": PIN, "case_count": len(NEGATIVES), "cases": [{"case": case, "refusal": refusal, "dom_click_count": 0} for case, refusal in NEGATIVES.items()], "final_same_script_task_check": True, "installed_image_proven": False, "final_peer_control_custody_proven": False}
    exact(actual, expected, "real semantic corpus result")


def source_check(root: Path, parsed: dict[str, list[str]]) -> None:
    toolchain = subprocess.check_output(["rustc", "--version"], text=True, timeout=15).strip()
    if toolchain != "rustc 1.93.0 (254b59607 2026-01-19)":
        raise ValueError("standalone semantic source check requires locked Rust 1.93.0")
    with tempfile.TemporaryDirectory(prefix="s08-semantic-rust-") as temporary:
        project = Path(temporary)
        for name in ("Cargo.toml", "Cargo.lock"):
            (project / name).write_bytes(read(root / "experiments/servo-s08-runtime/semantic-source-check" / name))
        (project / "semantic_source.rs").write_bytes(apply_exact(None, parsed["components/shared/base/accessibility_semantics.rs"]))
        subprocess.run(["cargo", "test", "--locked", "--manifest-path", str(project / "Cargo.toml")], stdout=sys.stderr, check=True, timeout=180)


def main(argv: list[str] | None = None) -> int:
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check-upstream", type=Path)
    parser.add_argument("--source-check", action="store_true")
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)
    manifest, parsed = verify(args.root)
    if args.check_upstream:
        pin = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.check_upstream, text=True, timeout=15).strip()
        if pin != PIN or subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=args.check_upstream, text=True, timeout=15):
            raise ValueError("upstream checkout must be pristine exact pin")
        verify_upstream_sources(args.root, args.check_upstream, manifest, parsed)
    if args.source_check:
        source_check(args.root, parsed)
    if args.result:
        verify_result(args.result)
    print(json.dumps({"schema": "trillionnium.desktop.s08-semantic-source-verification.v1", "source_verified": True, "upstream_bytes_checked": bool(args.check_upstream), "standalone_source_checked": args.source_check, "semantic_result_shape_checked": bool(args.result), "actual_servo_execution_proven": False, "patch_sha256": manifest["patch"]["sha256"], "servo_commit": PIN, "installed_product_proven": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, UnicodeError, TypeError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f"S08 semantic verification refused: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1)
