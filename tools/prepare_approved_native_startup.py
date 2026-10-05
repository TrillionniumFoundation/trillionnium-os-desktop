#!/usr/bin/env python3
"""Add the closed approved-startup target to the reviewed pristine-PIN graph.

Assembly and byte readback are source evidence only. No product activation,
code execution, downloaded authority or lock bypass is performed here.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tomllib
try:
    from . import prepare_native_product_owner as original
except ImportError:
    import prepare_native_product_owner as original
ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "experiments/servo-product-owner/src/approved_startup.rs": "components/servo/tests/trillionnium_approved_startup.rs",
    "experiments/servo-product-owner/src/approved_test_support.rs": "components/servo/tests/trillionnium_approved_test_support.rs",
    "experiments/servo-product-owner/src/approved_connected_tests.rs": "components/servo/tests/trillionnium_approved_connected.rs",
}
TARGET = b'\n[[test]]\nname = "trillionnium_approved_connected"\npath = "tests/trillionnium_approved_connected.rs"\nharness = false\n\n[dev-dependencies.libc]\nworkspace = true\n'
DIAGNOSTIC_FEATURE = "approved-native-service-error"
def diagnostic_manifest(manifest: bytes, root: Path) -> bytes:
    """Enable only this test-support feature on the already assembled edge."""
    document = tomllib.loads(manifest.decode("utf-8", "strict"))
    dependency = document.get("dev-dependencies", {}).get("hepta-browserd")
    expected = {"path": str(root / "apps/hepta-browserd")}
    if dependency != expected:
        raise ValueError("approved diagnostic dependency is not the original path-only edge")
    original_edge = ("\n[dev-dependencies.hepta-browserd]\npath = "
                     + json.dumps(expected["path"]) + "\n").encode("utf-8")
    if manifest.count(original_edge) != 1:
        raise ValueError("approved diagnostic dependency table is not unique")
    feature = ('features = ["' + DIAGNOSTIC_FEATURE + '"]\n').encode("utf-8")
    qualified = manifest.replace(original_edge, original_edge + feature, 1)
    document["dev-dependencies"]["hepta-browserd"]["features"] = [DIAGNOSTIC_FEATURE]
    if tomllib.loads(qualified.decode("utf-8", "strict")) != document:
        raise ValueError("approved diagnostic feature changed another dependency")
    return qualified

def prepare(upstream: Path, root: Path = ROOT) -> dict:
    upstream, root = upstream.absolute(), root.absolute()
    # Read the complete bounded source before modifying the pristine tree.
    inputs = {path: original.read(root / path) for path in SOURCES}
    result = original.prepare(upstream, root)
    path = upstream / "components/servo/Cargo.toml"
    manifest = original.read(path)
    qualified = diagnostic_manifest(manifest, root)
    for source, target in SOURCES.items():
        original.write_source(upstream / target, inputs[source])
    original.write_source(path, qualified + TARGET, manifest)
    for source, target in SOURCES.items():
        if original.read(upstream / target) != inputs[source]:
            raise ValueError("approved startup assembled bytes differ")
    if original.read(path) != qualified + TARGET:
        raise ValueError("approved startup target manifest differs")
    return {"schema": "trillionnium.approved-native-startup-source.v1",
        "servo_commit": original.PIN,
        "source_sha256": {path: original.digest(value) for path, value in inputs.items()},
        "original_owner_assembly": result, "actual_servo_execution": False,
        "installed_activation": False}
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("prepare"); build.add_argument("--upstream", type=Path, required=True)
    lock = commands.add_parser("verify-lock")
    lock.add_argument("--before", type=Path, required=True); lock.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.upstream) if args.command == "prepare" else original.verify_lock(args.before, args.after, approved_startup=True)
    print(json.dumps(result, sort_keys=True)); return 0
if __name__ == "__main__":
    raise SystemExit(main())
