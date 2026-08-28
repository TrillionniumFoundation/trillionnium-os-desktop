#!/usr/bin/env python3
"""Fail-closed static and cross-contract audit for the D0C-03 Rust codec source.

This validator is deliberately not a Rust compiler. Its result may prove that
required files, constants, mappings, dependency locks and claim ceilings are
present, but it never upgrades fmt/Clippy/test/self-check to PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()

    checks: list[str] = []
    contract = json.loads((ROOT / "contracts/browser-codec.v1.json").read_text())
    errors = json.loads((ROOT / "contracts/error-codes.v1.json").read_text())["codes"]
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text())
    lock = tomllib.loads((ROOT / "Cargo.lock").read_text())
    manifest = tomllib.loads(
        (ROOT / "crates/hepta-browser-codec/Cargo.toml").read_text()
    )
    lib = (ROOT / "crates/hepta-browser-codec/src/lib.rs").read_text()
    json_source = (ROOT / "crates/hepta-browser-codec/src/json.rs").read_text()
    model_paths = [ROOT / "crates/hepta-browser-codec/src/model.rs", *sorted((ROOT / "crates/hepta-browser-codec/src/model").glob("*.rs"))]
    model = "\n".join(path.read_text() for path in model_paths)
    tests = (ROOT / "crates/hepta-browser-codec/src/tests.rs").read_text()
    browserd_manifest = tomllib.loads((ROOT / "apps/hepta-browserd/Cargo.toml").read_text())
    browserd = (ROOT / "apps/hepta-browserd/src/lib.rs").read_text()

    members = workspace["workspace"]["members"]
    defaults = workspace["workspace"]["default-members"]
    require("crates/hepta-browser-codec" in members, "codec is a workspace member", checks)
    require("crates/hepta-browser-codec" in defaults, "codec is a default workspace member", checks)
    require(
        manifest["dependencies"] == {"sha2": "=0.10.9"},
        "codec dependency closure adds only exact sha2=0.10.9",
        checks,
    )
    require(
        "hepta-browser-codec" in browserd_manifest["dependencies"],
        "browserd depends on the product codec",
        checks,
    )
    require(
        "hepta_browser_codec::self_check()" in browserd,
        "browserd self-check invokes the product codec",
        checks,
    )

    packages = {item["name"]: item for item in lock["package"]}
    require("hepta-browser-codec" in packages, "Cargo.lock contains codec package", checks)
    require(
        packages["hepta-browser-codec"].get("dependencies") == ["sha2"],
        "Cargo.lock binds codec only to sha2",
        checks,
    )
    require(
        "hepta-browser-codec" in packages["hepta-browserd"].get("dependencies", []),
        "Cargo.lock binds browserd to codec",
        checks,
    )

    require("#![forbid(unsafe_code)]" in lib, "codec forbids unsafe code", checks)
    combined = "\n".join([lib, json_source, model, tests])
    forbidden = ["TcpListener", "UnixListener", ".bind(", "WebDriver", "servo::"]
    for token in forbidden:
        require(token not in combined, f"codec source excludes authority token {token}", checks)

    require("MAX_MESSAGE_BYTES: usize = 262_144" in lib, "message byte bound matches contract", checks)
    require("MAX_JSON_DEPTH: usize = 32" in lib, "nesting bound matches contract", checks)
    require("MAX_CONTAINER_ITEMS: usize = 20_000" in lib, "container bound matches contract", checks)
    require("DuplicateMember" in json_source, "recursive duplicate-member failure exists", checks)
    require("FloatingPointForbidden" in json_source, "floating-point rejection exists", checks)
    require("Utf8Bom" in json_source, "UTF-8 BOM rejection exists", checks)
    require("BTreeMap" in json_source, "canonical object map is ordered", checks)
    require("NonCanonicalEncoding" in model, "byte-exact canonical comparison exists", checks)
    require("semantic_snapshot_revision" in model, "semantic snapshot binding exists", checks)
    require("userinfo" not in model.lower() or "authority.contains('@')" in model,
            "URL userinfo is rejected", checks)
    require("localhost\" | \"127.0.0.1\" | \"::1" in model,
            "fixture navigation is loopback-only", checks)

    operation_literals = {
        "health", "session_create", "session_snapshot", "session_close",
        "page_navigate", "page_observe", "page_act", "page_wait", "page_extract",
    }
    for operation in sorted(operation_literals):
        require(f'"{operation}"' in model, f"Rust model contains operation {operation}", checks)

    require(
        re.search(
            r"Self::PageNavigate\s*\{\s*\.\.\s*\}\s*=>\s*EffectClass::PotentialExternalEffect",
            model,
            re.S,
        ) is not None,
        "navigation is classified as potential_external_effect",
        checks,
    )
    require(
        "PageAction::Scroll { .. }" in model and "EffectClass::LocalInteraction" in model,
        "scroll is classified as local_interaction",
        checks,
    )

    for item in errors:
        code = item["code"]
        retry = item["retry"]
        require(f'"{code}"' in model, f"Rust model contains error code {code}", checks)
        require(f'"{retry}"' in model, f"Rust model contains retry policy {retry}", checks)

    golden_names = [
        "golden-health-1.wire.json",
        "golden-create-1.wire.json",
        "golden-navigate-1.wire.json",
        "golden-click-1.wire.json",
        "golden-response-ok-1.wire.json",
        "golden-response-error-1.wire.json",
    ]
    for name in golden_names:
        path = ROOT / "contracts/golden" / name
        require(path.exists(), f"golden vector exists: {name}", checks)
        require(name in tests, f"Rust tests include golden vector: {name}", checks)
        raw = path.read_bytes()
        require(raw == json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode(),
                f"golden vector is canonical: {name}", checks)

    validation = contract["validation"]
    require(validation["python_reference"] == "PASS_27_OF_27",
            "independent codec reference remains 27/27 PASS", checks)
    require(validation["rust_source_audit"] == "PASS",
            "contract records Rust source audit PASS", checks)
    for field in ["rust_fmt", "rust_clippy", "rust_tests", "browserd_self_check"]:
        require(validation[field] == "PASS", f"host validation records {field} PASS", checks)
    require(validation["merge_ready"] is True, "contract is merge-ready after exact-head validation", checks)
    host_result = ROOT / contract["rust_host_result"]
    require(host_result.is_file(), "exact-head Rust host result exists", checks)
    host = json.loads(host_result.read_text())
    require(host["status"] == "PASS", "exact-head Rust host result is PASS", checks)
    require(host["validated_source_sha"] == "4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb",
            "host result binds the tested source commit", checks)
    require(contract["listener"] == {"enabled": False, "public_network": False},
            "codec contract creates no listener", checks)

    result = {
        "schema": "trillionnium.desktop.d0c03-rust-source-audit.v1",
        "status": "PASS",
        "check_count": len(checks),
        "checks": checks,
        "source_sha256": {
            "lib_rs": sha256(ROOT / "crates/hepta-browser-codec/src/lib.rs"),
            "json_rs": sha256(ROOT / "crates/hepta-browser-codec/src/json.rs"),
            "model_rs": sha256(ROOT / "crates/hepta-browser-codec/src/model.rs"),
            **{f"model_{path.stem}_rs": sha256(path) for path in model_paths[1:]},
            "tests_rs": sha256(ROOT / "crates/hepta-browser-codec/src/tests.rs"),
            "cargo_toml": sha256(ROOT / "crates/hepta-browser-codec/Cargo.toml"),
        },
        "executed": {
            "static_contract_source_audit": True,
            "golden_vector_canonicality": True,
            "cargo_fmt": True,
            "cargo_clippy": True,
            "cargo_test": True,
            "browserd_self_check": True,
        },
        "product_listener_created": False,
        "browser_dispatched": False,
        "external_effect_authorized": False,
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write_result:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(encoded)
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"D0C-03 Rust source audit failed: {error}", file=sys.stderr)
        raise
