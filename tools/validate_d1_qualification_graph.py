#!/usr/bin/env python3
"""Verify D1 example isolation and bounded Cargo build metadata; no image authority."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "apps/hepta-agent-portd/Cargo.toml"
QUALIFICATION_FEATURE = "qualification-static-attestation"
FORBIDDEN_PRODUCT_FEATURES = {QUALIFICATION_FEATURE, "development-static-attestation"}
EXAMPLE = {
    "name": "hepta-agent-d1-fixture",
    "path": "examples/hepta-agent-d1-fixture.rs",
    "required-features": ["fixture"],
}
MAX_INPUT = 8 * 1024 * 1024


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    package = manifest.get("package", {})
    if any(package.get(key) is not False for key in ("autobins", "autoexamples", "build")):
        errors.append("implicit executables or package build scripts are enabled")
    if manifest.get("features") != {"default": [], "fixture": ["dep:hepta-agent-port"]}:
        errors.append("S04 product/fixture feature graph changed")
    expected_normal = {
        "hepta-agent-port": {"path": "../../crates/hepta-agent-port", "optional": True},
        "hepta-agent-transport": {"path": "../../crates/hepta-agent-transport"},
        "hepta-peer-attestation": {"path": "../../crates/hepta-peer-attestation"},
        "libc": "=0.2.186",
    }
    expected_dev = {
        "hepta-browser-codec": {"path": "../../crates/hepta-browser-codec"},
        "hepta-peer-attestation": {
            "path": "../../crates/hepta-peer-attestation",
            "features": [QUALIFICATION_FEATURE],
        },
    }
    if manifest.get("dependencies") != expected_normal:
        errors.append("normal dependency graph contains an unreviewed edge or feature")
    if manifest.get("dev-dependencies") != expected_dev:
        errors.append("qualification dev-dependency graph changed")
    expected_bins = [
        {"name": "hepta-agent-portd", "path": "src/main.rs"},
        {"name": "hepta-agent-port-fixture", "path": "src/bin/hepta-agent-port-fixture.rs",
         "required-features": ["fixture"]},
    ]
    if manifest.get("bin") != expected_bins:
        errors.append("product/fixture binary inventory changed")
    if manifest.get("example") != [EXAMPLE]:
        errors.append("D1 must be one explicitly selected fixture-gated example")
    if manifest.get("build-dependencies") or manifest.get("target"):
        errors.append("unreviewed build or target-specific dependency edge")
    return errors


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate JSON member")
        output[key] = value
    return output


def _reject_number(value: str) -> None:
    raise ValueError("non-integer JSON number")


def bounded_read(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_INPUT:
            raise ValueError("input is not a bounded regular file")
        raw = stream.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("input exceeded byte bound while reading")
    return raw.decode("utf-8")


def build_messages(path: Path) -> list[dict[str, Any]]:
    lines = bounded_read(path).splitlines()
    if not 1 <= len(lines) <= 20_000:
        raise ValueError("Cargo record count is missing or unbounded")
    records = [json.loads(line, object_pairs_hook=_unique, parse_constant=_reject_number,
                          parse_float=_reject_number) for line in lines]
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("Cargo message must be an object")
    return records


def validate_build(records: list[dict[str, Any]], *, qualification: bool) -> list[str]:
    errors: list[str] = []
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        return ["Cargo build messages must be objects"]
    finished = [r for r in records if r.get("reason") == "build-finished"]
    if len(finished) != 1 or finished[0].get("success") is not True or records[-1:] != finished:
        errors.append("Cargo build has no unique successful terminal record")
    artifacts = [r for r in records if r.get("reason") == "compiler-artifact"]
    for record in artifacts:
        target, features = record.get("target"), record.get("features")
        if (not isinstance(target, dict) or not isinstance(target.get("name"), str)
                or not isinstance(target.get("kind"), list)
                or any(not isinstance(k, str) for k in target["kind"])
                or not isinstance(features, list)
                or any(not isinstance(f, str) for f in features)
                or len(features) != len(set(features))):
            return ["Cargo artifact target or feature metadata is malformed"]
    name = "hepta-agent-d1-fixture" if qualification else "hepta-agent-portd"
    kind = "example" if qualification else "bin"
    selected = [r for r in artifacts if r.get("target", {}).get("name") == name]
    if len(selected) != 1 or selected[0].get("target", {}).get("kind") != [kind]:
        errors.append("selected Cargo target missing, duplicated or wrong kind")
    elif not isinstance(selected[0].get("executable"), str) or not selected[0]["executable"]:
        errors.append("selected target has no executable artifact")
    elif set(selected[0].get("features", [])) != ({"fixture"} if qualification else set()):
        errors.append("selected target feature set differs from the explicit build command")
    attestation = [r for r in artifacts
                   if r.get("target", {}).get("name") == "hepta_peer_attestation"]
    if len(attestation) != 1:
        errors.append("exactly one attestation artifact is required")
    else:
        features = set(attestation[0].get("features", []))
        if qualification and QUALIFICATION_FEATURE not in features:
            errors.append("qualification build did not enable its test-only attestation feature")
        if not qualification and features & FORBIDDEN_PRODUCT_FEATURES:
            errors.append("static qualification/development attestation leaked into product")
    names = {r.get("target", {}).get("name") for r in artifacts}
    if qualification and not {"hepta_agent_port", "hepta_browser_codec"} <= names:
        errors.append("qualification build omitted its actual mechanism dependencies")
    if not qualification and names & {"hepta_agent_port", "hepta_browser_codec", "hepta-agent-port-fixture", "hepta-agent-d1-fixture"}:
        errors.append("product build compiled a qualification-only mechanism or target")
    return errors


def validate(root: Path = ROOT) -> list[str]:
    try:
        manifest = tomllib.loads(bounded_read(root / MANIFEST))
        errors = validate_manifest(manifest)
        examples = root / "apps/hepta-agent-portd/examples"
        if examples.is_symlink():
            return errors + ["qualification example directory is a symlink"]
        entries = list(examples.iterdir())
        if len(entries) != 1 or entries[0].name != "hepta-agent-d1-fixture.rs" or entries[0].is_symlink():
            errors.append("unregistered or symlinked qualification example")
        source = bounded_read(examples / "hepta-agent-d1-fixture.rs")
        if "evidence.peer" in source:
            errors.append("qualification fixture consumes the removed product evidence identity")
        if "server_evidence_json(&evidence, peer)" not in source:
            errors.append("qualification result is not bound to the original authenticated socket peer")
        production = bounded_read(root / "packaging/debian/hepta-agent-portd.install")
        if "hepta-agent-d1-fixture" in production or "image/rootfs-overlay" in production:
            errors.append("D1 qualification target leaked into the production install map")
        return errors
    except (OSError, UnicodeError, ValueError) as error:
        return [f"D1 graph input invalid: {type(error).__name__}: {error}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-messages", nargs=2, type=Path, metavar=("PRODUCT", "QUALIFICATION"))
    args = parser.parse_args()
    errors = validate()
    if args.build_messages:
        try:
            for qualification, path in zip((False, True), args.build_messages, strict=True):
                errors.extend(validate_build(build_messages(path), qualification=qualification))
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError) as error:
            errors.append(f"invalid Cargo build metadata: {type(error).__name__}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("D1 qualification graph validation passed; source/host graph only, no installed-image or release claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
