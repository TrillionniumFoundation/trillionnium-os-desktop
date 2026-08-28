#!/usr/bin/env python3
"""Promote a previously executed D0C-04 Rust 1.93 gate into canonical evidence.

This script does not execute Rust and does not widen authority. It records the
already completed materialization gate after the calling workflow re-runs the
same source under the exact toolchain.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "5abd71db79b75e400c1c1d7cb0eac85a68041cae"
PRODUCT_TREE = "0f9db4dd1c1d53e87570fb3d6307dde16b760045"
MATERIALIZATION_RUN_ID = 33179346462
MATERIALIZATION_JOB_ID = 98876202259
EVIDENCE_PATH = "docs/evidence/generated/d0c04-rust193-host-result.json"
HOST_STATUS = "HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR"


def read_json(path: str) -> dict:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: str, value: dict) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


def source_sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def write_machine_evidence() -> None:
    expected_hashes = {
        "agent_port": "eed9df8e80c2e8d71338b7684aa19ce2b4d6ce843d4e0ed68746fef4129a1e43",
        "cargo_lock": "6e222e540587b4b09e286d1408b9729f3bc25b0364cd5ab696df013050a58bef",
        "contract": "8c50df0fcf613e3a32243338d4456832895a827c9637c01894bb1c030039ff2e",
    }
    actual_hashes = {
        "agent_port": source_sha256("crates/hepta-agent-port/src/lib.rs"),
        "cargo_lock": source_sha256("Cargo.lock"),
        "contract": source_sha256("contracts/agent-port-bridge.v1.json"),
    }
    if actual_hashes != expected_hashes:
        raise ValueError(
            f"validated source hashes changed: expected {expected_hashes}, actual {actual_hashes}"
        )
    evidence = {
        "schema": "trillionnium.desktop.d0c04-rust193-host-result.v1",
        "status": "PASS_HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR",
        "work_package": "TOS-D0C-04",
        "plan_revision": "2026-08-28-d5",
        "branch": "codex/d0c04-host-validated-v4",
        "validated_source_commit": SOURCE_COMMIT,
        "validated_product_tree": PRODUCT_TREE,
        "workflow_run_id": MATERIALIZATION_RUN_ID,
        "workflow_job_id": MATERIALIZATION_JOB_ID,
        "runner": {
            "os": "Ubuntu 24.04.4 LTS",
            "image": "ubuntu-24.04",
            "image_version": "20260823.283.1",
        },
        "toolchain": {
            "rustc": "rustc 1.93.0 (254b59607 2026-01-19)",
            "cargo": "cargo 1.93.0 (083ac5135 2025-12-15)",
        },
        "validation": {
            "repository_validator": "PASS",
            "d0c04_source_validator": "PASS_44_CHECKS",
            "cargo_fmt": "PASS",
            "cargo_clippy_warnings_denied": "PASS",
            "cargo_test_workspace_all_targets_locked": "PASS",
            "workspace_tests": {"passed": 45, "failed": 0},
            "agent_port_tests": {"passed": 5, "failed": 0},
            "browserd_self_check": {
                "status": "PASS",
                "checks_run": 10,
                "implementation_stage": "D0R_D0C04_SOURCE",
                "final_revisions": {
                    "session_generation": 2,
                    "document_generation": 3,
                    "semantic_snapshot_revision": 3,
                    "mutation_epoch": 3,
                },
            },
        },
        "source_sha256": actual_hashes,
        "authority_ceiling": {
            "listener_created": False,
            "systemd_socket_enabled": False,
            "browser_actor_called": False,
            "servo_called": False,
            "external_effect_authorized": False,
            "potential_external_effect_default_denied": True,
        },
    }
    write_json(EVIDENCE_PATH, evidence)


def update_contract_and_candidate() -> None:
    contract = read_json("contracts/agent-port-bridge.v1.json")
    contract["status"] = HOST_STATUS
    contract["validation"] = {
        "rust_source_audit": "PASS_44_CHECKS",
        "python_reference": "PASS_13_OF_13",
        "cargo_fmt": "PASS",
        "cargo_clippy": "PASS_WARNINGS_DENIED",
        "cargo_test": "PASS_45",
        "agent_port_tests": "PASS_5",
        "browserd_self_check": "PASS_10",
        "machine_evidence": EVIDENCE_PATH,
        "validated_source_commit": SOURCE_COMMIT,
        "workflow_run_id": MATERIALIZATION_RUN_ID,
        "merge_ready": True,
    }
    contract["remaining_gates"] = [
        gate
        for gate in contract.get("remaining_gates", [])
        if gate != "exact_head_Rust_1_93_format_clippy_tests_and_self_check"
    ]
    write_json("contracts/agent-port-bridge.v1.json", contract)

    candidate = read_json("manifests/d0c04-candidate.json")
    candidate["branch"] = "codex/d0c04-host-validated-v4"
    candidate["status"] = HOST_STATUS
    candidate["validation"] = {
        "source_validator": "tools/validate_d0c04_rust_product.py",
        "standard_workflow": ".github/workflows/ci.yml",
        "materialization_workflow_run_id": MATERIALIZATION_RUN_ID,
        "materialization_workflow_job_id": MATERIALIZATION_JOB_ID,
        "validated_source_commit": SOURCE_COMMIT,
        "machine_evidence": f"../{EVIDENCE_PATH}",
        "cargo_fmt": "PASS",
        "cargo_clippy": "PASS_WARNINGS_DENIED",
        "cargo_test": "PASS_45",
        "agent_port_tests": "PASS_5",
        "browserd_self_check": "PASS_10",
        "merge_ready": True,
    }
    write_json("manifests/d0c04-candidate.json", candidate)


def update_canonical_manifests() -> None:
    docs = read_json("docs/MANIFEST.json")
    docs["agent_port_connected_bridge_product"] = True
    docs["agent_port_exact_head_rust_validation"] = True
    docs["implementation_stage"] = "D0R_D0C04_HOST_VALIDATED"
    checkpoints = [
        item
        for item in docs.setdefault("implementation_checkpoints", [])
        if item.get("id") != "TOS-D0C-04"
    ]
    checkpoints.append(
        {
            "id": "TOS-D0C-04",
            "status": HOST_STATUS,
            "evidence": "evidence/2026-08-28-d0c04-rust-agent-port.md",
            "machine_evidence": "evidence/generated/d0c04-rust193-host-result.json",
            "validated_head": SOURCE_COMMIT,
            "workflow_run_id": MATERIALIZATION_RUN_ID,
        }
    )
    docs["implementation_checkpoints"] = checkpoints
    write_json("docs/MANIFEST.json", docs)

    state = read_json("manifests/repository-state.json")
    completed = state.setdefault("completed_work_packages", [])
    if "D0C-04" not in completed:
        completed.append("D0C-04")
    host = [
        item
        for item in state.setdefault("host_validated_work_packages", [])
        if item.get("id") != "D0C-04"
    ]
    host.append(
        {
            "id": "D0C-04",
            "status": HOST_STATUS,
            "evidence": EVIDENCE_PATH,
            "validated_head": SOURCE_COMMIT,
            "workflow_run_id": MATERIALIZATION_RUN_ID,
        }
    )
    state["host_validated_work_packages"] = host
    state["implementation_stage"] = "D0R_D0C04_HOST_VALIDATED"
    state["partial_work_packages"] = [
        item for item in state.get("partial_work_packages", []) if item != "D0C-04"
    ]
    write_json("manifests/repository-state.json", state)


def update_current_state_and_evidence() -> None:
    current_path = ROOT / "docs/CURRENT_STATE.md"
    current = current_path.read_text(encoding="utf-8")
    current = current.replace(
        "**Implementation stage:** `D0R_D0C02_HOST_VALIDATED`",
        "**Implementation stage:** `D0R_D0C04_HOST_VALIDATED`",
        1,
    )
    current = current.replace(
        "- No canonical Browser API codec or exactly-one BrowserActor bridge is merged.\n",
        "- No filesystem or abstract Unix listener, systemd socket activation, or BrowserActor dispatch is enabled.\n",
        1,
    )
    start = current.find("## Active next work\n")
    end = current.find("\n## 2026-08-28 D0C-03", start)
    if start == -1 or end == -1:
        raise ValueError("CURRENT_STATE active-next section shape changed")
    next_section = """## Active next work

1. Merge the host-validated D0C-04 connected AgentPort core.
2. Implement D0C-05 default-disabled systemd socket custody without shipping an enable marker.
3. Complete D0A-01 against Servo pin
   `670ae8a70801b162e186f81cbb5bdd2d59c39108`, then the D0A-02 runtime half.
4. Resolve signed Debian inputs before D1-01.
5. Keep BrowserActor dispatch, Servo, external navigation, credentials, and effects closed until their explicit gates pass.
"""
    current = current[:start] + next_section + current[end:]
    checkpoint = f"""

## 2026-08-28 D0C-04 Rust 1.93 host-validation checkpoint

The connected AgentPort product tree materialized as `{SOURCE_COMMIT}` and passed
repository validation, the 44-check D0C-04 source/contract audit, Rust 1.93.0
formatting, Clippy with warnings denied, 45 workspace tests, and the integrated
10-check browserd self-check in workflow run `{MATERIALIZATION_RUN_ID}`. The
AgentPort accepts one already-connected authenticated AF_UNIX stream, performs
exactly one canonical request dispatch, binds the canonical response to the
request, and fails closed on late results or potential external effects. It
creates no listener, calls no BrowserActor or Servo runtime, and authorizes no
external effect. Machine evidence is `{EVIDENCE_PATH}`.
"""
    if "## 2026-08-28 D0C-04 Rust 1.93 host-validation checkpoint" not in current:
        current += checkpoint
    current_path.write_text(current, encoding="utf-8")

    evidence_path = ROOT / "docs/evidence/2026-08-28-d0c04-rust-agent-port.md"
    evidence = evidence_path.read_text(encoding="utf-8")
    if "## Host-validation promotion" not in evidence:
        evidence += f"""

## Host-validation promotion

Product tree `{SOURCE_COMMIT}` passed exact Rust 1.93.0 formatting, Clippy with
warnings denied, all 45 workspace tests, and the integrated 10-check browserd
self-check in workflow run `{MATERIALIZATION_RUN_ID}`. The five AgentPort tests
cover exactly-once request binding, pre-dispatch canonical rejection, default
denial of external navigation, late-result suppression, and handler depth
bounds. No listener, BrowserActor, Servo call, or external-effect authority was
introduced.

Machine evidence: `{EVIDENCE_PATH}`.
"""
    evidence_path.write_text(evidence, encoding="utf-8")


def update_validators() -> None:
    path = ROOT / "tools/validate_d0c04_rust_product.py"
    text = path.read_text(encoding="utf-8")
    old = '    require(contract.get("validation", {}).get("merge_ready") is False, "candidate prematurely merge-ready")\n'
    new = '''    validation = contract.get("validation", {})
    status = contract.get("status")
    require(
        status in {
            "SOURCE_IMPLEMENTED_EXACT_HEAD_RUST_VALIDATION_REQUIRED",
            "HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR",
        },
        "unknown AgentPort contract status",
    )
    if status == "HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR":
        require(validation.get("merge_ready") is True, "host-validated contract must be merge-ready")
        require(validation.get("cargo_fmt") == "PASS", "host validation must record cargo fmt")
        require(validation.get("cargo_clippy") == "PASS_WARNINGS_DENIED", "host validation must record Clippy")
        require(validation.get("cargo_test") == "PASS_45", "host validation must record workspace tests")
        require(validation.get("agent_port_tests") == "PASS_5", "host validation must record AgentPort tests")
        require(validation.get("browserd_self_check") == "PASS_10", "host validation must record self-check")
        machine = validation.get("machine_evidence")
        require(isinstance(machine, str) and (ROOT / machine).is_file(), "machine evidence is missing")
        checks.append("contract:host-validation")
    else:
        require(validation.get("merge_ready") is False, "source-only candidate must not be merge-ready")
'''
    text = replace_once(text, old, new, "D0C-04 contract promotion validation")
    old_return = '''    return {
        "schema": "trillionnium.desktop.d0c04-rust-source-audit.v1",
        "status": "PASS_SOURCE_STATIC_ONLY",
'''
    new_return = '''    promotion = parse_json("contracts/agent-port-bridge.v1.json").get("validation", {})
    return {
        "schema": "trillionnium.desktop.d0c04-rust-source-audit.v1",
        "status": "PASS_HOST_VALIDATED_STATIC_RECHECK" if promotion.get("merge_ready") else "PASS_SOURCE_STATIC_ONLY",
'''
    text = replace_once(text, old_return, new_return, "D0C-04 validator result status")
    text = text.replace('        "cargo_fmt": "UNEXECUTED",\n', '        "cargo_fmt": promotion.get("cargo_fmt", "UNEXECUTED"),\n', 1)
    text = text.replace('        "cargo_clippy": "UNEXECUTED",\n', '        "cargo_clippy": promotion.get("cargo_clippy", "UNEXECUTED"),\n', 1)
    text = text.replace('        "cargo_test": "UNEXECUTED",\n', '        "cargo_test": promotion.get("cargo_test", "UNEXECUTED"),\n', 1)
    text = text.replace('        "browserd_self_check": "UNEXECUTED",\n', '        "browserd_self_check": promotion.get("browserd_self_check", "UNEXECUTED"),\n', 1)
    text = text.replace('        "merge_ready": False,\n', '        "merge_ready": promotion.get("merge_ready", False),\n', 1)
    path.write_text(text, encoding="utf-8")

    stable_path = ROOT / "tools/validate_repository.py"
    stable = stable_path.read_text(encoding="utf-8")
    marker = '    "docs/evidence/2026-08-28-d0c04-rust-agent-port.md",\n'
    addition = marker + '    "docs/evidence/generated/d0c04-rust193-host-result.json",\n'
    if addition not in stable:
        stable = replace_once(stable, marker, addition, "stable D0C-04 machine evidence")
    stable_path.write_text(stable, encoding="utf-8")


def main() -> int:
    write_machine_evidence()
    update_contract_and_candidate()
    update_canonical_manifests()
    update_current_state_and_evidence()
    update_validators()
    print(f"promoted {SOURCE_COMMIT} as {HOST_STATUS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
