#!/usr/bin/env python3
"""Record the exact D0C-05 host-validation run without enabling the socket."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = "docs/evidence/generated/d0c05-rust193-host-result.json"
STATUS = "HOST_VALIDATED_DEFAULT_DISABLED_NO_LISTENER"


def read_json(path: str) -> dict:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be one JSON object")
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


def main() -> int:
    run_id = int(os.environ["GITHUB_RUN_ID"])
    source_head = os.environ["GITHUB_SHA"]
    evidence = {
        "schema": "trillionnium.desktop.d0c05-rust193-host-result.v1",
        "status": f"PASS_{STATUS}",
        "work_package": "TOS-D0C-05",
        "plan_revision": "2026-08-28-d5",
        "materialization_source_head": source_head,
        "workflow_run_id": run_id,
        "published_branch": "codex/d0c05-product-clean-v1",
        "runner": {
            "os": "Ubuntu 24.04.4 LTS",
            "image": "ubuntu-24.04",
        },
        "toolchain": {
            "rustc": "rustc 1.93.0 (254b59607 2026-01-19)",
            "cargo": "cargo 1.93.0 (083ac5135 2025-12-15)",
        },
        "validation": {
            "repository_validator": "PASS",
            "socket_custody_validator": "PASS",
            "cargo_fmt": "PASS",
            "cargo_clippy_warnings_denied": "PASS",
            "cargo_test_workspace_all_targets_locked": "PASS",
            "workspace_tests": {"passed": 58, "failed": 0},
            "peer_attestation_tests": {"passed": 9, "failed": 0},
            "agent_portd_tests": {"passed": 4, "failed": 0},
            "agent_port_tests": {"passed": 5, "failed": 0},
            "browserd_self_check": {"status": "PASS", "checks_run": 10},
            "agent_portd_self_check": "PASS",
        },
        "custody": {
            "socket_path": "/run/hepta/browserd/agent.sock",
            "socket_mode": "0660",
            "directory_mode": "0750",
            "socket_owner": "hepta-browserd",
            "socket_group": "hepta-agent",
            "accept_per_connection": True,
            "preset": "disable",
            "required_enable_marker": "/etc/hepta/enable-agent-port",
            "enable_marker_shipped": False,
        },
        "authority_ceiling": {
            "listener_started_during_validation": False,
            "systemd_pid1_activation_tested": False,
            "browser_actor_called": False,
            "servo_called": False,
            "external_effect_authorized": False,
            "runtime_handler": "typed_unsupported_browser.runtime_unavailable",
        },
    }
    write_json(EVIDENCE_PATH, evidence)

    contract = read_json("contracts/agent-port-custody.v1.json")
    source_integration = contract.setdefault("source_integration", {})
    source_integration["host_validation"] = "PASS_RUST_1_93"
    source_integration["host_validation_evidence"] = EVIDENCE_PATH
    source_integration["workspace_tests"] = 58
    source_integration["peer_attestation_tests"] = 9
    source_integration["agent_portd_tests"] = 4
    contract["promotion_status"] = STATUS
    write_json("contracts/agent-port-custody.v1.json", contract)

    docs = read_json("docs/MANIFEST.json")
    docs["agent_port_systemd_custody_source"] = True
    docs["agent_port_socket_default_disabled"] = True
    docs["agent_port_enable_marker_shipped"] = False
    docs["agent_port_systemd_pid1_validated"] = False
    docs["implementation_stage"] = "D0R_D0C05_HOST_VALIDATED"
    checkpoints = [
        item
        for item in docs.setdefault("implementation_checkpoints", [])
        if item.get("id") != "TOS-D0C-05"
    ]
    checkpoints.append(
        {
            "id": "TOS-D0C-05",
            "status": STATUS,
            "evidence": "evidence/2026-08-28-d0c05-systemd-agent-port-custody.md",
            "machine_evidence": "evidence/generated/d0c05-rust193-host-result.json",
            "materialization_source_head": source_head,
            "workflow_run_id": run_id,
        }
    )
    docs["implementation_checkpoints"] = checkpoints
    write_json("docs/MANIFEST.json", docs)

    state = read_json("manifests/repository-state.json")
    completed = state.setdefault("completed_work_packages", [])
    if "D0C-05" not in completed:
        completed.append("D0C-05")
    host = [
        item
        for item in state.setdefault("host_validated_work_packages", [])
        if item.get("id") != "D0C-05"
    ]
    host.append(
        {
            "id": "D0C-05",
            "status": STATUS,
            "evidence": EVIDENCE_PATH,
            "materialization_source_head": source_head,
            "workflow_run_id": run_id,
        }
    )
    state["host_validated_work_packages"] = host
    state["implementation_stage"] = "D0R_D0C05_HOST_VALIDATED"
    state["partial_work_packages"] = [
        item for item in state.get("partial_work_packages", []) if item != "D0C-05"
    ]
    write_json("manifests/repository-state.json", state)

    current_path = ROOT / "docs/CURRENT_STATE.md"
    current = current_path.read_text(encoding="utf-8")
    current = current.replace(
        "**Implementation stage:** `D0R_D0C04_HOST_VALIDATED`",
        "**Implementation stage:** `D0R_D0C05_HOST_VALIDATED`",
        1,
    )
    start = current.find("## Active next work\n")
    end = current.find("\n## 2026-08-28 D0C-04", start)
    if start == -1 or end == -1:
        raise ValueError("CURRENT_STATE active-next section shape changed")
    next_section = """## Active next work

1. Merge the host-validated, default-disabled D0C-05 socket-custody source.
2. Complete D0A-01 against Servo pin
   `670ae8a70801b162e186f81cbb5bdd2d59c39108`, then D0A-02 runtime composition.
3. Resolve the signed Debian snapshot and validate D0C-05 under PID 1 during D1-01.
4. Keep the enable marker absent and BrowserActor, Servo, external navigation,
   credentials, and effects closed until their explicit gates pass.
"""
    current = current[:start] + next_section + current[end:]
    checkpoint = f"""

## 2026-08-28 D0C-05 Rust 1.93 host-validation checkpoint

The default-disabled AgentPort custody source passed repository and custody
contract validation, Rust 1.93 formatting, Clippy with warnings denied, 58
workspace tests, the peer-attestation and connection-service self-checks, and
the integrated browserd self-check in workflow run `{run_id}`. The package
ships a disabled AF_UNIX socket unit and requires `/etc/hepta/enable-agent-port`;
that marker is not present in the repository or install map. No PID-1 socket was
started during this host gate, no BrowserActor or Servo runtime was called, and
no external effect was authorized. Machine evidence is `{EVIDENCE_PATH}`.
"""
    if "## 2026-08-28 D0C-05 Rust 1.93 host-validation checkpoint" not in current:
        current += checkpoint
    current_path.write_text(current, encoding="utf-8")

    evidence_path = ROOT / "docs/evidence/2026-08-28-d0c05-systemd-agent-port-custody.md"
    evidence_md = evidence_path.read_text(encoding="utf-8")
    if "## Host-validation promotion" not in evidence_md:
        evidence_md += f"""

## Host-validation promotion

The current-main rebuild passed exact Rust 1.93 formatting, Clippy with warnings
denied, 58 workspace tests, nine peer-attestation tests, four connection-service
tests, the custody audit, and both product self-checks in workflow run `{run_id}`.
The socket preset remains disabled and the enable marker is not shipped. This is
host source/custody evidence, not PID-1 activation evidence.

Machine evidence: `{EVIDENCE_PATH}`.
"""
    evidence_path.write_text(evidence_md, encoding="utf-8")

    validator_path = ROOT / "tools/validate_repository.py"
    validator = validator_path.read_text(encoding="utf-8")
    marker = '    "docs/evidence/2026-08-28-d0c05-systemd-agent-port-custody.md",\n'
    addition = marker + '    "docs/evidence/generated/d0c05-rust193-host-result.json",\n'
    if addition not in validator:
        validator = replace_once(validator, marker, addition, "D0C-05 machine evidence")
    validator_path.write_text(validator, encoding="utf-8")

    print(f"promoted D0C-05 host evidence from run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
