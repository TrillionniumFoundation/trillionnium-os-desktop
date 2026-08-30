#!/usr/bin/env python3
"""Fail-closed static validation for the D0C-04 Rust product candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
# D0C-04 was originally validated before the D0C-05/D3 packages were added to
# the product workspace.  Keep this list explicit (rather than accepting any
# Cargo graph) while tracking the current canonical workspace graph.  A graph
# change is itself an exact-head evidence invalidation; it must not make this
# source audit fail merely because the old validator happened to know fewer
# members.
EXPECTED_MEMBERS = [
    "apps/hepta-browserd",
    "apps/hepta-agent-portd",
    "crates/hepta-agent-transport",
    "crates/hepta-browser-codec",
    "crates/hepta-agent-port",
    "crates/hepta-peer-attestation",
    "crates/trillionnium-contract-core",
    "crates/hepta-browser-contracts",
    "crates/hepta-session-core",
    "crates/hepta-workspace-composition",
    "crates/hepta-browser-actor",
]
LOCAL_PACKAGES = {
    "hepta-agent-port",
    "hepta-agent-portd",
    "hepta-agent-transport",
    "hepta-browser-actor",
    "hepta-browser-codec",
    "hepta-browser-contracts",
    "hepta-browserd",
    "hepta-peer-attestation",
    "hepta-session-core",
    "hepta-workspace-composition",
    "trillionnium-contract-core",
}
REQUIRED_PATHS = [
    "crates/hepta-agent-port/Cargo.toml",
    "crates/hepta-agent-port/README.md",
    "crates/hepta-agent-port/src/lib.rs",
    "contracts/agent-port-bridge.v1.json",
]


class ValidationError(RuntimeError):
    pass


SOURCE_STATUS = "SOURCE_IMPLEMENTED_EXACT_HEAD_RUST_VALIDATION_REQUIRED"
HOST_STATUS = "HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR"
STALE_STATUS = "STALE_EVIDENCE"
MACHINE_HOST_STATUS = "PASS_HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR"
# The checked-in host result is immutable historical evidence.  If a future
# promotion is performed, its exact source commit must be written explicitly;
# this value must never be inferred from the current tree.
HISTORICAL_HOST_SOURCE_COMMIT = "5abd71db79b75e400c1c1d7cb0eac85a68041cae"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
BROWSERD_ALLOWED_STAGES = {
    # The stage recorded by the historical D0C-04 run.
    "D0R_D0C04_SOURCE",
    # The current d6 integrated source stage.  Advancing the repository stage
    # must not make this narrowly scoped static audit reject an otherwise
    # unchanged AgentPort bridge.
    "D0R_D0C06_D0A01_COMPILE_VALIDATED",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def parse_toml(path: str) -> dict:
    with (ROOT / path).open("rb") as handle:
        return tomllib.load(handle)


def parse_json(path: str) -> dict:
    with (ROOT / path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def confined_repo_path(value: object, *, label: str) -> Path:
    """Resolve a contract path without allowing traversal or symlink escape."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValidationError(f"{label} must be a non-empty relative path")
    if "\\" in value or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValidationError(f"{label} contains unsafe characters")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or not parsed.parts
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or parsed.as_posix() != value
    ):
        raise ValidationError(f"{label} must be a canonical repository-relative path")
    candidate = ROOT.joinpath(*parsed.parts)
    try:
        candidate.relative_to(ROOT)
    except ValueError as error:
        raise ValidationError(f"{label} escapes repository root") from error
    current = ROOT
    for part in parsed.parts:
        current /= part
        if current.is_symlink():
            raise ValidationError(f"{label} contains a symlink: {value}")
    return candidate


def git_head_sha() -> str | None:
    """Return the checked-out commit, or ``None`` outside a Git checkout.

    A host-validation claim is meaningful only when the validator can bind it
    to the exact tree that was tested.  Treat an unavailable Git identity as a
    hard failure for a merge-ready contract instead of silently trusting a
    copied snapshot.
    """

    try:
        # A commit SHA alone is insufficient when a validator is run from a
        # dirty checkout: tracked edits (or untracked Cargo members) can alter
        # the candidate while leaving ``HEAD`` unchanged.  Host promotion is
        # therefore limited to a clean checkout, as it is in the permanent CI
        # gate.
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        if status.stdout.strip():
            return None
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    return value if SHA40.fullmatch(value) else None


def check_paths(checks: list[str]) -> None:
    for path in REQUIRED_PATHS:
        require((ROOT / path).is_file(), f"required path missing: {path}")
        require(not (ROOT / path).is_symlink(), f"required path is symlink: {path}")
        checks.append(f"path:{path}")


def check_workspace(checks: list[str]) -> None:
    workspace = parse_toml("Cargo.toml").get("workspace", {})
    require(workspace.get("members") == EXPECTED_MEMBERS, "workspace members drifted")
    require(workspace.get("default-members") == EXPECTED_MEMBERS, "default members drifted")
    require(workspace.get("resolver") == "3", "resolver drifted")
    package = workspace.get("package", {})
    require(package.get("edition") == "2024", "edition drifted")
    require(package.get("rust-version") == "1.93", "Rust version drifted")
    checks.extend(["workspace:members", "workspace:default-members", "workspace:toolchain"])


def check_lock(checks: list[str]) -> None:
    packages = parse_toml("Cargo.lock").get("package")
    require(isinstance(packages, list), "Cargo.lock package list missing")
    local = {p.get("name") for p in packages if "source" not in p}
    require(local == LOCAL_PACKAGES, f"local package set drifted: {sorted(local)}")
    allowlist = parse_json("manifests/cargo-external-allowlist.json")
    allowed = {(p["name"], p["version"], p["checksum"]) for p in allowlist["packages"]}
    actual = set()
    for package in packages:
        source = package.get("source")
        if source is None:
            continue
        require(source == "registry+https://github.com/rust-lang/crates.io-index", "non-crates.io source")
        require("checksum" in package, f"checksum missing for {package.get('name')}")
        actual.add((package["name"], package["version"], package["checksum"]))
    require(actual == allowed, "registry closure differs from allowlist")
    expected_direct = {
        "crates/hepta-agent-transport": {"libc": "=0.2.186", "sha2": "=0.10.9"},
        "crates/hepta-browser-codec": {"sha2": "=0.10.9"},
        "crates/hepta-agent-port": {"sha2": "=0.10.9"},
        "crates/hepta-session-core": {"sha2": "=0.10.9"},
        "crates/hepta-browser-actor": {"sha2": "=0.10.9"},
    }
    require(allowlist.get("direct_dependencies") == expected_direct, "direct allowlist drifted")
    for crate, expected in expected_direct.items():
        dependencies = parse_toml(f"{crate}/Cargo.toml").get("dependencies", {})
        for name, version in expected.items():
            require(dependencies.get(name) == version, f"{crate}: {name} pin drifted")
    checks.extend(["lock:local", "lock:registry", "lock:direct"])


def check_manifest(checks: list[str]) -> None:
    manifest = parse_toml("crates/hepta-agent-port/Cargo.toml")
    dependencies = manifest.get("dependencies", {})
    require(manifest.get("package", {}).get("name") == "hepta-agent-port", "wrong package name")
    require(dependencies.get("hepta-agent-transport", {}).get("path") == "../hepta-agent-transport", "transport is not local")
    require(dependencies.get("hepta-browser-codec", {}).get("path") == "../hepta-browser-codec", "codec is not local")
    require(dependencies.get("hepta-browser-contracts", {}).get("path") == "../hepta-browser-contracts", "contracts are not local")
    require(dependencies.get("sha2") == "=0.10.9", "sha2 pin drifted")
    require(set(dependencies) == {"hepta-agent-transport", "hepta-browser-codec", "hepta-browser-contracts", "sha2"}, "unexpected dependency")
    checks.append("agent-port:manifest")


def check_source(checks: list[str]) -> None:
    source = read("crates/hepta-agent-port/src/lib.rs")
    required = [
        "#![forbid(unsafe_code)]",
        "pub fn serve_one<",
        "pub fn serve_one_with_nonce_source<",
        "ServerConnection::accept_with_nonce_source",
        "connection.receive_request",
        "decode_request(&request_frame.payload)",
        # Keep the audit independent of whether the current implementation
        # uses ``?`` or an explicit match to record an interrupted lifecycle
        # event.  The call itself and its ordering are the security invariant.
        "handler.handle(&context, &request)",
        "bind_response(&request, outcome)",
        "connection.send_response(request_frame.sequence",
        "request_effective_deadline",
        "MAX_HANDLER_JSON_DEPTH",
        "MAX_HANDLER_CONTAINER_ITEMS",
        "EffectClass::PotentialExternalEffect",
        "BrowserErrorCode::PolicyDenied",
        "browser_runtime_available",
        "pub fn self_check()",
    ]
    for token in required:
        require(token in source, f"missing source invariant: {token}")
        checks.append(f"source:{token}")
    for token in ["UnixListener", "TcpListener", "servo::", "WebDriver", "webdriver", "tokio::net", "std::process::Command", "unsafe {", "todo!", "unimplemented!"]:
        require(token not in source, f"forbidden source/authority token: {token}")
        checks.append(f"absent:{token}")
    decode_at = source.index("decode_request(&request_frame.payload)")
    handle_at = source.index("handler.handle(&context, &request)")
    commit_at = source.index("connection.send_response(request_frame.sequence")
    require(decode_at < handle_at < commit_at, "decode/dispatch/commit order drifted")
    require(source.count("handler.handle(&context, &request)") == 1, "handler call is not exactly one")
    require("NavigationTarget::ExternalHttps {" in source, "navigation fixture does not use active struct variant")
    require("NavigationTarget::ExternalHttps(" not in source, "stale tuple-style navigation variant returned")
    checks.extend(["source:order", "source:exactly-one", "source:navigation-variant"])


def check_contract_and_browserd(checks: list[str]) -> None:
    contract = parse_json("contracts/agent-port-bridge.v1.json")
    require(contract.get("schema") == "trillionnium.desktop.agent-port-bridge.v1", "wrong contract schema")
    require(contract.get("input", {}).get("maximum_requests_per_connection") == 1, "request count drifted")
    require(contract.get("dispatch", {}).get("handler_invocations_per_connection") == "at_most_one", "handler count drifted")
    require(contract.get("response", {}).get("maximum_responses_per_connection") == 1, "response count drifted")
    require(contract.get("listener", {}).get("enabled") is False, "listener opened")
    ceiling = contract.get("effect_ceiling", {})
    require(ceiling.get("external_effect_authorized") is False, "effect authority opened")
    require(ceiling.get("browser_actor_connected") is False, "BrowserActor claim opened")
    require(ceiling.get("servo_called") is False, "Servo claim opened")
    validation = contract.get("validation", {})
    status = contract.get("status")
    top_lifecycle = contract.get("evidence_lifecycle")
    top_freshness = contract.get("evidence_freshness")
    top_merge_ready = contract.get("merge_ready")
    evidence_is_stale = (
        status == STALE_STATUS
        or validation.get("evidence_freshness") == STALE_STATUS
        or top_freshness == STALE_STATUS
    )
    remaining_gates = contract.get("remaining_gates")
    require(
        isinstance(remaining_gates, list)
        and all(isinstance(gate, str) and gate for gate in remaining_gates),
        "AgentPort remaining_gates must be a list of non-empty strings",
    )
    require(
        status in {
            SOURCE_STATUS,
            HOST_STATUS,
            STALE_STATUS,
        },
        "unknown AgentPort contract status",
    )
    validated_source_commit = validation.get("validated_source_commit")
    if status in {HOST_STATUS, STALE_STATUS}:
        require(
            isinstance(validated_source_commit, str)
            and SHA40.fullmatch(validated_source_commit) is not None,
            "AgentPort validation source commit is a well-formed SHA-1",
        )
    elif validated_source_commit is not None:
        require(
            isinstance(validated_source_commit, str)
            and SHA40.fullmatch(validated_source_commit) is not None,
            "optional AgentPort source commit is a well-formed SHA-1",
        )

    machine = validation.get("machine_evidence")
    if status in {HOST_STATUS, STALE_STATUS}:
        machine_path = confined_repo_path(machine, label="machine_evidence")
        require(
            machine_path.is_file()
            and not machine_path.is_symlink(),
            "host-validation machine evidence is missing",
        )
        if machine_path.is_file() and not machine_path.is_symlink():
            evidence = parse_json(machine)
            require(
                evidence.get("status") == MACHINE_HOST_STATUS,
                "host-validation machine evidence records the bounded status",
            )
            require(
                evidence.get("validated_source_commit") == validated_source_commit,
                "host-validation machine evidence binds the contract source commit",
            )
            if status == HOST_STATUS and not evidence_is_stale:
                evidence_hashes = evidence.get("source_sha256")
                require(
                    isinstance(evidence_hashes, dict),
                    "host-validation machine evidence records source digests",
                )
                if isinstance(evidence_hashes, dict):
                    for key, path in {
                        "agent_port": "crates/hepta-agent-port/src/lib.rs",
                        "cargo_lock": "Cargo.lock",
                        "contract": "contracts/agent-port-bridge.v1.json",
                    }.items():
                        expected_hash = evidence_hashes.get(key)
                        require(
                            isinstance(expected_hash, str)
                            and re.fullmatch(r"[0-9a-f]{64}", expected_hash) is not None,
                            f"host-validation machine evidence {key} digest is well-formed",
                        )
                        if isinstance(expected_hash, str):
                            require(
                                expected_hash == sha256(path),
                                f"host-validation machine evidence {key} digest matches the checkout",
                            )

    if status == HOST_STATUS and not evidence_is_stale:
        require(validation.get("merge_ready") is True, "host-validated contract must be merge-ready")
        require(
            "exact_head_Rust_1_93_format_clippy_tests_and_self_check"
            not in remaining_gates,
            "host-validated contract has no outstanding exact-head Rust gate",
        )
        require(validation.get("cargo_fmt") == "PASS", "host validation must record cargo fmt")
        require(validation.get("cargo_clippy") == "PASS_WARNINGS_DENIED", "host validation must record Clippy")
        require(validation.get("cargo_test") == "PASS_45", "host validation must record workspace tests")
        require(validation.get("agent_port_tests") == "PASS_5", "host validation must record AgentPort tests")
        require(validation.get("browserd_self_check") == "PASS_10", "host validation must record self-check")
        require(
            validation.get("evidence_freshness", "CURRENT") == "CURRENT",
            "host-validated contract must carry current evidence freshness",
        )
        checked_out_sha = git_head_sha()
        require(
            checked_out_sha is not None,
            "host-validated contract requires a Git checkout for exact-head comparison",
        )
        if checked_out_sha is not None:
            require(
                validated_source_commit == checked_out_sha,
                "host-validated contract source commit matches checked-out HEAD",
            )
        checks.append("contract:host-validation")
    elif evidence_is_stale:
        require(validation.get("merge_ready") is False, "stale contract must not be merge-ready")
        require(
            "exact_head_Rust_1_93_format_clippy_tests_and_self_check"
            in remaining_gates,
            "stale contract retains the exact-head Rust rerun gate",
        )
        require(
            validation.get("evidence_freshness") == STALE_STATUS,
            "stale AgentPort evidence must declare STALE_EVIDENCE freshness",
        )
        require(
            top_lifecycle == "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN",
            "stale AgentPort contract must declare exact-head rerun lifecycle",
        )
        require(
            top_freshness == STALE_STATUS and top_merge_ready is False,
            "stale AgentPort contract top-level freshness must be stale",
        )
        require(
            validated_source_commit == HISTORICAL_HOST_SOURCE_COMMIT,
            "stale AgentPort evidence retains the known historical source commit",
        )
        stale_reason = validation.get("stale_reason")
        require(
            isinstance(stale_reason, str)
            and HISTORICAL_HOST_SOURCE_COMMIT in stale_reason
            and "exact candidate head" in stale_reason,
            "stale AgentPort evidence carries an actionable exact-head rerun reason",
        )
        require(
            contract.get("stale_reason") == stale_reason,
            "stale AgentPort contract top-level reason matches validation reason",
        )
        checks.append("contract:stale-host-evidence")
    else:
        require(validation.get("merge_ready") is False, "source-only candidate must not be merge-ready")
    browserd_manifest = parse_toml("apps/hepta-browserd/Cargo.toml")
    require(browserd_manifest.get("dependencies", {}).get("hepta-agent-port", {}).get("path") == "../../crates/hepta-agent-port", "browserd AgentPort dependency missing")
    browserd = read("apps/hepta-browserd/src/lib.rs")
    require("hepta_agent_port::self_check()" in browserd, "browserd self-check omits AgentPort")
    require(
        any(
            f'IMPLEMENTATION_STAGE: &str = "{stage}"' in browserd
            for stage in BROWSERD_ALLOWED_STAGES
        ),
        "browserd stage drifted",
    )
    checks.extend(["contract:counts", "contract:ceiling", "browserd:dependency", "browserd:self-check"])


def validate() -> dict:
    checks: list[str] = []
    check_paths(checks)
    check_workspace(checks)
    check_lock(checks)
    check_manifest(checks)
    check_source(checks)
    check_contract_and_browserd(checks)
    promotion = parse_json("contracts/agent-port-bridge.v1.json").get("validation", {})
    merge_ready = promotion.get("merge_ready") is True
    return {
        "schema": "trillionnium.desktop.d0c04-rust-source-audit.v1",
        # A static audit can pass while its host result is historical.  Keep
        # that distinction explicit so callers never mistake a green source
        # check for fresh Rust execution evidence.
        "status": "PASS_HOST_VALIDATED_STATIC_RECHECK" if merge_ready else "PASS_SOURCE_STATIC_ONLY",
        "checks_passed": len(checks),
        "checks": checks,
        "source_sha256": {
            "agent_port": sha256("crates/hepta-agent-port/src/lib.rs"),
            "contract": sha256("contracts/agent-port-bridge.v1.json"),
            "cargo_lock": sha256("Cargo.lock"),
        },
        "cargo_fmt": promotion.get("cargo_fmt", "UNEXECUTED"),
        "cargo_clippy": promotion.get("cargo_clippy", "UNEXECUTED"),
        "cargo_test": promotion.get("cargo_test", "UNEXECUTED"),
        "browserd_self_check": promotion.get("browserd_self_check", "UNEXECUTED"),
        "evidence_freshness": promotion.get("evidence_freshness", "CURRENT"),
        "validated_source_commit": promotion.get("validated_source_commit"),
        "merge_ready": merge_ready,
        "listener_created": False,
        "browser_actor_called": False,
        "servo_called": False,
        "external_effect_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    try:
        result = validate()
    except (ValidationError, OSError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        print(f"D0C-04 validation failed: {error}", file=sys.stderr)
        return 1
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write is not None:
        output = args.write if args.write.is_absolute() else ROOT / args.write
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
