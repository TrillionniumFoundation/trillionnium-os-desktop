#!/usr/bin/env python3
"""Record D0C-03 exact-source host evidence without modifying tested Rust source."""
from __future__ import annotations

import json
from pathlib import Path

SOURCE_SHA = "4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb"
WORKFLOW_RUN_ID = 33176689873
WORKFLOW_JOB_ID = 98867406690
ROOT = Path(__file__).resolve().parents[1]


def read_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def write_json(relative: str, value: object) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


contract = read_json("contracts/browser-codec.v1.json")
contract["status"] = "HOST_VALIDATED_RUST_1_93_NO_DISPATCH"
contract["validation"].update(
    {
        "rust_fmt": "PASS",
        "rust_clippy": "PASS",
        "rust_tests": "PASS",
        "browserd_self_check": "PASS",
        "merge_ready": True,
        "reason": (
            "The exact tested-source commit passed Rust 1.93.0 formatting, "
            "Clippy with warnings denied, all workspace tests, browserd self-check, "
            "repository validation and the independent reference corpus."
        ),
    }
)
contract["rust_host_result"] = "docs/evidence/generated/d0c03-rust193-host-result.json"
write_json("contracts/browser-codec.v1.json", contract)

host_result = {
    "schema": "trillionnium.desktop.d0c03-rust193-host-result.v1",
    "status": "PASS",
    "validated_source_sha": SOURCE_SHA,
    "workflow_run_id": WORKFLOW_RUN_ID,
    "workflow_job_id": WORKFLOW_JOB_ID,
    "runner": "ubuntu-24.04",
    "rustc": {
        "version": "1.93.0",
        "commit_hash": "254b59607d4417e9dffbc307138ae5c86280fe4c",
        "commit_date": "2026-01-19",
        "host": "x86_64-unknown-linux-gnu",
        "llvm": "21.1.8",
    },
    "cargo": {
        "version": "1.93.0",
        "commit_hash": "083ac5135f967fd9dc906ab057a2315861c7a80d",
        "commit_date": "2025-12-15",
    },
    "commands": {
        "repository_validation": "PASS",
        "independent_python_reference_27_of_27": "PASS",
        "rust_source_contract_audit": "PASS",
        "cargo_fmt_all_check": "PASS",
        "cargo_clippy_workspace_all_targets_locked_deny_warnings": "PASS",
        "cargo_test_workspace_all_targets_locked": "PASS",
        "browserd_self_check_locked": "PASS",
        "clean_worktree_after_validation": "PASS",
        "no_agent_socket": "PASS",
        "no_agent_port_enable_marker": "PASS",
    },
    "product_listener_created": False,
    "browser_actor_dispatched": False,
    "servo_called": False,
    "external_effect_authorized": False,
}
write_json("docs/evidence/generated/d0c03-rust193-host-result.json", host_result)

docs_manifest = read_json("docs/MANIFEST.json")
docs_manifest["status"] = "IMPLEMENTATION_HOST_VALIDATED"
docs_manifest["implementation_stage"] = "D0R_D0C03_HOST_VALIDATED"
checkpoints = [
    item
    for item in docs_manifest.setdefault("implementation_checkpoints", [])
    if item.get("id") != "TOS-D0C-03"
]
checkpoints.append(
    {
        "id": "TOS-D0C-03",
        "status": "HOST_VALIDATED_NO_LISTENER_NO_DISPATCH",
        "evidence": "evidence/2026-08-28-d0c03-rust-product-codec-source.md",
        "machine_evidence": "evidence/generated/d0c03-rust193-host-result.json",
        "validated_head": SOURCE_SHA,
        "workflow_run_id": WORKFLOW_RUN_ID,
    }
)
docs_manifest["implementation_checkpoints"] = checkpoints
docs_manifest["canonical_browser_codec_product"] = True
docs_manifest["browser_codec_exact_head_rust_validation"] = True
write_json("docs/MANIFEST.json", docs_manifest)

state = read_json("manifests/repository-state.json")
state["implementation_stage"] = "D0R_D0C03_HOST_VALIDATED"
completed = state.setdefault("completed_work_packages", [])
if "D0C-03" not in completed:
    completed.append("D0C-03")
validated = [
    item
    for item in state.setdefault("host_validated_work_packages", [])
    if item.get("id") != "D0C-03"
]
validated.append(
    {
        "id": "D0C-03",
        "status": "HOST_VALIDATED_NO_LISTENER_NO_DISPATCH",
        "validated_head": SOURCE_SHA,
        "workflow_run_id": WORKFLOW_RUN_ID,
        "evidence": "docs/evidence/generated/d0c03-rust193-host-result.json",
    }
)
state["host_validated_work_packages"] = validated
state["not_claimed"] = [
    item for item in state.get("not_claimed", []) if item != "canonical_browser_codec_product"
]
state["partial_work_packages"] = [
    item for item in state.get("partial_work_packages", []) if item != "D0C-03"
]
write_json("manifests/repository-state.json", state)

current_path = ROOT / "docs/CURRENT_STATE.md"
current = current_path.read_text(encoding="utf-8")
marker = "## 2026-08-28 D0C-03 Rust 1.93 host-validation checkpoint"
if marker not in current:
    current += (
        f"\n\n{marker}\n\n"
        f"The canonical Browser API codec at `{SOURCE_SHA}` passed repository "
        f"validation, Rust 1.93.0 formatting, Clippy with warnings denied, all "
        f"workspace tests, the browserd self-check, the 27-case independent "
        f"reference corpus and the static source/contract audit in workflow run "
        f"`{WORKFLOW_RUN_ID}`. It creates no listener, dispatches no BrowserActor, "
        "invokes no Servo runtime and authorizes no external effect.\n"
    )
current_path.write_text(current, encoding="utf-8")

evidence_path = ROOT / "docs/evidence/2026-08-28-d0c03-rust-product-codec-source.md"
evidence = evidence_path.read_text(encoding="utf-8")
validation_marker = "## Exact-head Rust 1.93 host validation"
if validation_marker not in evidence:
    evidence += (
        f"\n\n{validation_marker}\n\n"
        f"Validated source commit: `{SOURCE_SHA}`  \n"
        f"Workflow run: `{WORKFLOW_RUN_ID}`  \n"
        "Result: repository validation, rustfmt, Clippy `-D warnings`, full "
        "workspace tests and `hepta-browserd --self-check` all passed. Machine "
        "evidence: `generated/d0c03-rust193-host-result.json`. This remains a "
        "no-listener, no-BrowserActor, no-Servo and no-effect checkpoint.\n"
    )
evidence_path.write_text(evidence, encoding="utf-8")

audit_path = ROOT / "tools/validate_rust_browser_codec.py"
audit = audit_path.read_text(encoding="utf-8")
old_claim = '''    for field in ["rust_fmt", "rust_clippy", "rust_tests", "browserd_self_check"]:
        require(validation[field] == "UNEXECUTED", f"claim ceiling keeps {field} UNEXECUTED", checks)
    require(validation["merge_ready"] is False, "contract remains non-merge-ready", checks)
'''
new_claim = '''    for field in ["rust_fmt", "rust_clippy", "rust_tests", "browserd_self_check"]:
        require(validation[field] == "PASS", f"host validation records {field} PASS", checks)
    require(validation["merge_ready"] is True, "contract is merge-ready after exact-head validation", checks)
    host_result = ROOT / contract["rust_host_result"]
    require(host_result.is_file(), "exact-head Rust host result exists", checks)
    host = json.loads(host_result.read_text())
    require(host["status"] == "PASS", "exact-head Rust host result is PASS", checks)
    require(host["validated_source_sha"] == "4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb",
            "host result binds the tested source commit", checks)
'''
if audit.count(old_claim) != 1:
    raise SystemExit("Rust codec audit claim-ceiling block changed unexpectedly")
audit = audit.replace(old_claim, new_claim, 1)
audit = audit.replace(
    '            "cargo_fmt": False,\n            "cargo_clippy": False,\n            "cargo_test": False,\n            "browserd_self_check": False,',
    '            "cargo_fmt": True,\n            "cargo_clippy": True,\n            "cargo_test": True,\n            "browserd_self_check": True,',
    1,
)
audit_path.write_text(audit, encoding="utf-8")

workflow_path = ROOT / ".github/workflows/browser-codec-reference.yml"
workflow = workflow_path.read_text(encoding="utf-8")
workflow = workflow.replace(
    '          assert contract["validation"]["rust_fmt"] == "UNEXECUTED"',
    '          assert contract["validation"]["rust_fmt"] == "PASS"',
)
workflow = workflow.replace(
    '          assert contract["validation"]["rust_tests"] == "UNEXECUTED"',
    '          assert contract["validation"]["rust_tests"] == "PASS"',
)
workflow = workflow.replace(
    '          assert contract["validation"]["merge_ready"] is False',
    '          assert contract["validation"]["rust_clippy"] == "PASS"\n'
    '          assert contract["validation"]["browserd_self_check"] == "PASS"\n'
    '          assert contract["validation"]["merge_ready"] is True\n'
    '          host = json.loads(Path(contract["rust_host_result"]).read_text())\n'
    f'          assert host["validated_source_sha"] == "{SOURCE_SHA}"',
)
workflow_path.write_text(workflow, encoding="utf-8")

print("D0C-03 host-validation evidence promoted")
