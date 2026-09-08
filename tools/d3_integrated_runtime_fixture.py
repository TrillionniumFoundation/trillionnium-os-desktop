"""Deterministic source-only fixture for the D3 evidence verifier."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from typing import Any

from trusted_app_bundle import canonical_json
from d3_integrated_runtime_common import build_receipt_chain, load_json
from d3_integrated_runtime_verify import verify_evidence

def _fixture_identity() -> dict[str, Any]:
    return {
        "pid": 4242,
        "uid": 1002,
        "gid": 1002,
        "start_time_ticks": 123456,
        "systemd_unit": "hepta-agent.service",
        "cgroup_v2_path": "/system.slice/hepta-agent.service",
        "executable_sha256": "a" * 64,
        "pidfd_alive": True,
    }


def build_source_fixture(root: Path, contract: dict[str, Any]) -> tuple[Path, Path]:
    artifact_root = root / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    fixture_files = {
        "agent-port-receipts.jsonl": b'{"fixture":true,"receipts":2}\n',
        "browser-runtime.json": b'{"fixture":true,"servo_owned":true}\n',
        "crash-topology.json": b'{"fixture":true,"recovered":true}\n',
    }
    artifacts: list[dict[str, Any]] = []
    for name, data in fixture_files.items():
        path = artifact_root / name
        path.write_bytes(data)
        artifacts.append(
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        )
    identity = _fixture_identity()
    evidence = {
        "schema": contract["evidence_schema"],
        "status": "PASS_D3_EXACT_IMAGE_RUNTIME_CANDIDATE",
        "source": {
            "repository": contract["repository"],
            "ref": "refs/pull/0/merge",
            "head_sha": "1" * 40,
            "tree_sha": "2" * 40,
            "tested_sha": "3" * 40,
            "base_sha": "4" * 40,
            "integrated_main_sha": None,
            "fixture_evidence": True,
        },
        "image": {
            "sha256": "5" * 64,
            "qemu_machine": "q35",
            "tcg": True,
            "network_device_present": False,
            "systemd_pid1": True,
            "wayland_ready": True,
            "servo_runtime_ready": True,
            "servo_commit": contract["servo_commit"],
        },
        "principal": {
            "admission": identity,
            "dispatch": dict(identity),
            "dispatch_time_revalidated": True,
        },
        "semantic_action": {
            "servo_owned_adapter": True,
            "engine_retained_node": True,
            "same_engine_critical_section": True,
            "current_frame_only": True,
            "unique_match_count": 1,
            "role_match": True,
            "accessible_name_digest_match": True,
            "structural_fingerprint_match": True,
            "revalidated_immediately_before_action": True,
            "action_count": 1,
            "mutation_epoch_before": 7,
            "mutation_epoch_after": 8,
            "coordinate_fallback": False,
            "dom_order_fallback": False,
            "accessible_name_only_fallback": False,
            "cross_frame_fallback": False,
        },
        "cases": dict(contract["required_cases"]),
        "receipts": {
            "requested_fsync_before_dispatch": True,
            "terminal_fsync_before_response": True,
            "automatic_replay": False,
            "indeterminate_requires_reconciliation": True,
            "chains": [
                build_receipt_chain("fixture-completed", "completed"),
                build_receipt_chain("fixture-indeterminate", "indeterminate"),
            ],
        },
        "product_boundaries": {
            "production_agent_port_enabled": False,
            "external_effect_authority": False,
            "external_network_enabled": False,
            "ambient_filesystem_authority": False,
            "hardware_qualified": False,
            "signing_key_custody": False,
            "release_ready": False,
            "development_profile_explicit": True,
        },
        "artifacts": sorted(artifacts, key=lambda item: item["path"]),
        "attestations": [],
    }
    evidence_path = root / "evidence.json"
    evidence_path.write_bytes(canonical_json(evidence))
    return evidence_path, artifact_root


def run_self_test(contract_path: Path) -> dict[str, Any]:
    contract = load_json(contract_path)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        evidence_path, artifact_root = build_source_fixture(root, contract)
        return verify_evidence(
            evidence_path,
            artifact_root,
            contract_path=contract_path,
            require_exact_main=False,
        )

