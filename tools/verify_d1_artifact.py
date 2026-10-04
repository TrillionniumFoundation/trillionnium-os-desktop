#!/usr/bin/env python3
"""Strictly verify a staged or downloaded D1 qualification artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .artifact_evidence import artifact_file, artifact_root, digest as sha256, load, safe_relative, verify_outputs, verify_workflow_binding, validate_role, SHA256
    from .finalize_d1_evidence import validate_result_documents
    from .d1_evidence_semantics import verify_semantics
    from .d1_source_provenance import verify_source
except ImportError:
    from artifact_evidence import artifact_file, artifact_root, digest as sha256, load, safe_relative, verify_outputs, verify_workflow_binding, validate_role, SHA256
    from finalize_d1_evidence import validate_result_documents
    from d1_evidence_semantics import verify_semantics
    from d1_source_provenance import verify_source


RECEIPT_PATH = Path("evidence/d1-final-qualification.json")


def _same_typed_value(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (set(actual) == set(expected)
                and all(_same_typed_value(actual[key], value) for key, value in expected.items()))
    if isinstance(expected, list):
        return (len(actual) == len(expected)
                and all(_same_typed_value(left, right) for left, right in zip(actual, expected)))
    return actual == expected


def verify_artifact(path: Path) -> dict[str, Any]:
    root = artifact_root(path)
    receipt_path = artifact_file(root, RECEIPT_PATH.as_posix())
    receipt = load(receipt_path)
    if receipt.get("schema") != "trillionnium.desktop.d1-final-qualification.v4":
        raise ValueError("unexpected D1 qualification receipt schema")
    if receipt.get("status") != "PASS":
        raise ValueError("D1 qualification receipt is not a pass")

    validate_role(receipt)
    ceiling = {key: False for key in (
        "servo_started", "visible_window_created", "network_enabled_during_acceptance",
        "secure_boot_qualified", "product_agent_port_enabled", "product_release_authorized",
    )}
    if not _same_typed_value(receipt.get("claim_ceiling"), ceiling):
        raise ValueError("D1 receipt claim_ceiling must be a closed exact false map")

    output_digests = receipt.get("output_digests")
    verify_outputs(root, RECEIPT_PATH.as_posix(), output_digests, sized=False)
    documents = {}
    for field, relative in {
        "pipeline": "pipeline/pipeline-result.json",
        "reproducibility": "reproducibility/reproducibility-result.json",
        "boot": "qemu/boot-result.json",
        "acceptance": "qemu/acceptance.json",
        "host_tool": "evidence/e2fsprogs-host-tool-result.json",
        "host_environment": "evidence/host-toolchain.json",
    }.items():
        documents[field] = load(artifact_file(root, relative))
        if not _same_typed_value(receipt.get(field), documents[field]):
            raise ValueError(f"D1 receipt does not bind staged {field} evidence")
    documents["product_check"] = load(artifact_file(root, "evidence/product-daemon-self-check-host.json"))
    documents["qualification_check"] = load(artifact_file(root, "evidence/d1-qualification-self-check-host.json"))
    validate_result_documents(documents)
    verify_semantics(root, receipt, documents)

    source_manifest_path = artifact_file(root, "evidence/source-input-digests.json")
    source_manifest = load(source_manifest_path)
    if source_manifest.get("schema") != "trillionnium.desktop.source-input-digests.v1":
        raise ValueError("source input digest manifest has the wrong schema")
    source_digests = source_manifest.get("files")
    if not isinstance(source_digests, dict) or not source_digests:
        raise ValueError("source input digest manifest is empty")
    if type(source_manifest.get("file_count")) is not int or source_manifest.get("file_count") != len(source_digests):
        raise ValueError("source input digest count is inconsistent")
    for relative, expected in source_digests.items():
        safe_relative(relative)
        if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
            raise ValueError("source input digest is malformed")
    canonical = json.dumps(
        source_digests, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != source_manifest.get(
        "files_sha256"
    ):
        raise ValueError("source input aggregate digest is inconsistent")
    if receipt.get("source_input_manifest_sha256") != sha256(source_manifest_path):
        raise ValueError("receipt does not bind the staged source input manifest")
    if (receipt.get("source_input_files_sha256") != source_manifest["files_sha256"]
            or type(receipt.get("source_input_count")) is not int
            or receipt["source_input_count"] != len(source_digests)):
        raise ValueError("receipt source aggregate or count is inconsistent")
    verify_source(root, receipt, source_digests)
    verify_workflow_binding(receipt.get("workflow"), source_digests, producer=False)
    verify_workflow_binding(receipt.get("producer_workflow"), source_digests, producer=True,
                            tested_sha=receipt["tested_sha"])
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    receipt = verify_artifact(args.artifact_root)

    print(
        json.dumps(
            {
                "schema": "trillionnium.desktop.d1-artifact-verification.v1",
                "status": "PASS",
                "receipt": RECEIPT_PATH.as_posix(),
                "evidence_role": receipt["evidence_role"],
                "promotion_authoritative": receipt["promotion_authoritative"],
                "verified_output_count": len(receipt["output_digests"]),
                "source_input_count": receipt["source_input_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
