#!/usr/bin/env python3
"""Offline verifier for D8 fixed-hardware beta evidence.

The verifier validates signed identity, exact artifact digests, raw metric and
cycle data, subsystem/security coverage, and numeric gates. A fixture bundle is
always format-only and never promotion eligible.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from trusted_app_bundle import (  # noqa: E402
    canonical_json,
    ed25519_public_from_seed,
    ed25519_sign_fixture,
    ed25519_verify,
)

CONTRACT_PATH = ROOT / "contracts" / "hardware-beta-qualification.v1.json"
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
EVIDENCE_FIELDS = {
    "schema",
    "qualification_id",
    "hardware_profile_id",
    "environment_kind",
    "lab",
    "started_at_epoch",
    "ended_at_epoch",
    "artifact_identity",
    "bom",
    "critical_outcomes",
    "artifacts",
    "known_limitations",
    "signature",
}
ARTIFACT_FIELDS = {"role", "path", "sha256", "bytes"}
LAB_FIELDS = {"lab_id", "lab_key_id", "signer_role"}
CRITICAL_FIELDS = {
    "critical_failures",
    "uncorrected_data_corruption",
    "unexpected_external_effects",
    "network_policy_bypasses",
}
METRIC_FIELDS = {
    "timestamp_epoch",
    "rss_mib",
    "fd_count",
    "pid_count",
    "native_input_latency_ms",
    "agent_observe_latency_ms",
    "agent_act_latency_ms",
}
CYCLE_FIELDS = {
    "schema",
    "cold_boot_ready_ms",
    "compositor_to_first_frame_ms",
    "content_crash_recovery_ms",
    "suspend_resume_ms",
    "update_commit_results",
    "update_rollback_results",
    "power_loss_results",
}


class HardwareEvidenceError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def fail(reason: str, detail: str | None = None) -> None:
    raise HardwareEvidenceError(reason, detail)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HardwareEvidenceError("INVALID_JSON", str(path)) from error
    if not isinstance(value, dict):
        fail("JSON_OBJECT_REQUIRED", str(path))
    return value


def signed_payload(evidence: dict[str, Any]) -> bytes:
    value = copy.deepcopy(evidence)
    value.pop("signature", None)
    return canonical_json(value)


def normalize_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        fail("INVALID_EVIDENCE_PATH")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        fail("EVIDENCE_PATH_TRAVERSAL", value)
    normalized = "/".join(path.parts)
    if normalized != value or len(value.encode("utf-8")) > 512:
        fail("NON_CANONICAL_EVIDENCE_PATH", value)
    return normalized


def require_hex(value: Any, pattern: re.Pattern[str], reason: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        fail(reason)
    return value


def require_identifier(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        fail(reason)
    return value


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        fail("METRIC_SERIES_EMPTY")
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return float(ordered[index])


def parse_json_lines(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise HardwareEvidenceError(
                "INVALID_JSONL_RECORD", f"{path}:{line_number}"
            ) from error
        if not isinstance(value, dict):
            fail("JSONL_OBJECT_REQUIRED", f"{path}:{line_number}")
        records.append(value)
    if not records:
        fail("JSONL_RECORDS_REQUIRED", str(path))
    return records


def verify_lab_signature(
    evidence: dict[str, Any], trust: dict[str, Any], now_epoch: int
) -> dict[str, Any]:
    if trust.get("schema") != "trillionnium.desktop.hardware-lab-trust.v1":
        fail("HARDWARE_LAB_TRUST_SCHEMA_MISMATCH")
    lab = evidence.get("lab")
    if not isinstance(lab, dict) or set(lab) != LAB_FIELDS:
        fail("HARDWARE_LAB_FIELD_SET_MISMATCH")
    lab_id = require_identifier(lab["lab_id"], "HARDWARE_LAB_ID_INVALID")
    key_id = require_identifier(lab["lab_key_id"], "HARDWARE_LAB_KEY_ID_INVALID")
    labs = trust.get("labs")
    record = labs.get(lab_id) if isinstance(labs, dict) else None
    keys = record.get("keys") if isinstance(record, dict) else None
    key = keys.get(key_id) if isinstance(keys, dict) else None
    if not isinstance(key, dict) or set(key) != {
        "status",
        "signer_role",
        "public_key_base64",
        "not_before_epoch",
        "expires_at_epoch",
        "production_enrolled",
    }:
        fail("HARDWARE_LAB_KEY_UNKNOWN_OR_INVALID")
    if key["status"] != "active":
        fail("HARDWARE_LAB_KEY_NOT_ACTIVE")
    if lab["signer_role"] != key["signer_role"]:
        fail("HARDWARE_LAB_ROLE_MISMATCH")
    if not isinstance(key["not_before_epoch"], int) or not isinstance(key["expires_at_epoch"], int):
        fail("HARDWARE_LAB_KEY_TIME_INVALID")
    if not key["not_before_epoch"] <= now_epoch <= key["expires_at_epoch"]:
        fail("HARDWARE_LAB_KEY_OUTSIDE_VALIDITY")
    revoked = trust.get("revoked_qualification_ids")
    if not isinstance(revoked, list) or not all(isinstance(item, str) for item in revoked):
        fail("REVOKED_QUALIFICATION_SET_INVALID")
    if evidence["qualification_id"] in revoked:
        fail("HARDWARE_QUALIFICATION_REVOKED")
    try:
        public = base64.b64decode(key["public_key_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise HardwareEvidenceError("HARDWARE_LAB_PUBLIC_KEY_INVALID") from error
    if len(public) != 32:
        fail("HARDWARE_LAB_PUBLIC_KEY_LENGTH_INVALID")
    signature = evidence.get("signature")
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "value_base64"}:
        fail("HARDWARE_EVIDENCE_SIGNATURE_FIELD_SET_MISMATCH")
    if signature["algorithm"] != "Ed25519":
        fail("HARDWARE_EVIDENCE_SIGNATURE_ALGORITHM_UNSUPPORTED")
    try:
        signature_bytes = base64.b64decode(signature["value_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise HardwareEvidenceError("HARDWARE_EVIDENCE_SIGNATURE_INVALID") from error
    if len(signature_bytes) != 64 or not ed25519_verify(
        public, signed_payload(evidence), signature_bytes
    ):
        fail("HARDWARE_EVIDENCE_SIGNATURE_REJECTED")
    return copy.deepcopy(key)


def verify_bom(bom: Any, contract: dict[str, Any]) -> None:
    required = set(contract["required_bom_fields"])
    if not isinstance(bom, dict) or set(bom) != required:
        fail("HARDWARE_BOM_FIELD_SET_MISMATCH")
    for key, value in bom.items():
        if key in {"memory_bytes"}:
            if not isinstance(value, int) or value < 4 * 1024**3:
                fail("HARDWARE_BOM_MEMORY_INVALID")
        elif key in {"tpm_present"}:
            if not isinstance(value, bool):
                fail("HARDWARE_BOM_BOOLEAN_INVALID", key)
        elif key in {
            "display_edid_hashes",
            "input_usb_ids",
            "audio_codec_ids",
            "network_device_ids",
        }:
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item for item in value
            ):
                fail("HARDWARE_BOM_LIST_INVALID", key)
        else:
            if not isinstance(value, str) or not value:
                fail("HARDWARE_BOM_STRING_INVALID", key)
    if bom["render_mode"] not in {"hardware_accelerated", "software_fallback"}:
        fail("HARDWARE_RENDER_MODE_INVALID")
    if bom["tpm_present"] and bom["tpm_version"] not in {"2.0", "2.0-compatible"}:
        fail("HARDWARE_TPM_VERSION_INVALID")


def verify_artifact_identity(value: Any, contract: dict[str, Any]) -> None:
    required = set(contract["artifact_identity_fields"])
    if not isinstance(value, dict) or set(value) != required:
        fail("ARTIFACT_IDENTITY_FIELD_SET_MISMATCH")
    for key in required:
        item = value[key]
        if key in {"image_bytes"}:
            if not isinstance(item, int) or item < 1:
                fail("ARTIFACT_IDENTITY_SIZE_INVALID", key)
        elif key in {"source_commit", "release_tree"}:
            require_hex(item, HEX_40, "ARTIFACT_IDENTITY_GIT_HASH_INVALID")
        else:
            require_hex(item, HEX_64, "ARTIFACT_IDENTITY_DIGEST_INVALID")


def verify_artifacts(
    artifacts: Any, evidence_dir: Path, contract: dict[str, Any]
) -> dict[str, Path]:
    if not evidence_dir.is_dir() or evidence_dir.is_symlink():
        fail("EVIDENCE_DIRECTORY_UNSAFE")
    if not isinstance(artifacts, list):
        fail("EVIDENCE_ARTIFACT_LIST_REQUIRED")
    by_role: dict[str, Path] = {}
    declared_paths: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != ARTIFACT_FIELDS:
            fail("EVIDENCE_ARTIFACT_FIELD_SET_MISMATCH")
        role = require_identifier(item["role"], "EVIDENCE_ARTIFACT_ROLE_INVALID")
        path_value = normalize_relative_path(item["path"])
        if role in by_role:
            fail("DUPLICATE_EVIDENCE_ARTIFACT_ROLE", role)
        if path_value in declared_paths:
            fail("DUPLICATE_EVIDENCE_ARTIFACT_PATH", path_value)
        declared_paths.add(path_value)
        path = evidence_dir / path_value
        try:
            metadata = path.lstat()
        except FileNotFoundError as error:
            raise HardwareEvidenceError("EVIDENCE_ARTIFACT_MISSING", path_value) from error
        if stat.S_ISLNK(metadata.st_mode):
            fail("EVIDENCE_ARTIFACT_SYMLINK_REJECTED", path_value)
        if not stat.S_ISREG(metadata.st_mode):
            fail("EVIDENCE_ARTIFACT_NOT_REGULAR", path_value)
        if not isinstance(item["bytes"], int) or item["bytes"] != metadata.st_size:
            fail("EVIDENCE_ARTIFACT_SIZE_MISMATCH", path_value)
        require_hex(item["sha256"], HEX_64, "EVIDENCE_ARTIFACT_DIGEST_INVALID")
        if sha256(path.read_bytes()) != item["sha256"]:
            fail("EVIDENCE_ARTIFACT_DIGEST_MISMATCH", path_value)
        by_role[role] = path
    required_roles = set(contract["required_artifact_roles"])
    if set(by_role) != required_roles:
        fail(
            "EVIDENCE_ARTIFACT_ROLE_SET_MISMATCH",
            json.dumps(
                {
                    "missing": sorted(required_roles - set(by_role)),
                    "extra": sorted(set(by_role) - required_roles),
                },
                sort_keys=True,
            ),
        )
    actual_files: set[str] = set()
    for root, dirs, files in os.walk(evidence_dir, followlinks=False):
        root_path = Path(root)
        for directory in dirs:
            if (root_path / directory).is_symlink():
                fail("EVIDENCE_DIRECTORY_SYMLINK_REJECTED")
        for name in files:
            path = root_path / name
            if path.is_symlink():
                fail("EVIDENCE_ARTIFACT_SYMLINK_REJECTED")
            actual_files.add(path.relative_to(evidence_dir).as_posix())
    if actual_files != declared_paths:
        fail(
            "EVIDENCE_ARTIFACT_SET_MISMATCH",
            json.dumps(
                {
                    "missing": sorted(declared_paths - actual_files),
                    "extra": sorted(actual_files - declared_paths),
                },
                sort_keys=True,
            ),
        )
    return by_role


def verify_metrics(
    path: Path,
    contract: dict[str, Any],
    *,
    started_at: int,
    ended_at: int,
    require_physical: bool,
) -> dict[str, Any]:
    records = parse_json_lines(path)
    timestamps: list[int] = []
    rss: list[float] = []
    fd: list[int] = []
    pid: list[int] = []
    input_latency: list[float] = []
    observe_latency: list[float] = []
    act_latency: list[float] = []
    for record in records:
        if set(record) != METRIC_FIELDS:
            fail("METRIC_RECORD_FIELD_SET_MISMATCH")
        timestamp = record["timestamp_epoch"]
        if not isinstance(timestamp, int):
            fail("METRIC_TIMESTAMP_INVALID")
        timestamps.append(timestamp)
        for key, target in (
            ("rss_mib", rss),
            ("native_input_latency_ms", input_latency),
            ("agent_observe_latency_ms", observe_latency),
            ("agent_act_latency_ms", act_latency),
        ):
            value = record[key]
            if not isinstance(value, (int, float)) or value < 0:
                fail("METRIC_VALUE_INVALID", key)
            target.append(float(value))
        for key, target in (("fd_count", fd), ("pid_count", pid)):
            value = record[key]
            if not isinstance(value, int) or value < 0:
                fail("METRIC_VALUE_INVALID", key)
            target.append(value)
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        fail("METRIC_TIMESTAMPS_NOT_STRICTLY_INCREASING")
    thresholds = contract["thresholds"]
    gaps = [right - left for left, right in zip(timestamps, timestamps[1:])]
    if gaps and max(gaps) > thresholds["maximum_sample_gap_seconds"]:
        fail("METRIC_SAMPLE_GAP_EXCEEDED")
    if require_physical:
        if len(records) < thresholds["physical_stability_samples_min"]:
            fail("METRIC_SAMPLE_COUNT_TOO_LOW")
        if timestamps[0] > started_at + thresholds["maximum_sample_gap_seconds"]:
            fail("METRIC_COVERAGE_START_MISSING")
        if timestamps[-1] < ended_at - thresholds["maximum_sample_gap_seconds"]:
            fail("METRIC_COVERAGE_END_MISSING")
    duration_hours = max((timestamps[-1] - timestamps[0]) / 3600.0, 1 / 3600.0)
    rss_growth = max(0.0, (rss[-1] - rss[0]) / duration_hours)
    result = {
        "sample_count": len(records),
        "maximum_gap_seconds": max(gaps) if gaps else 0,
        "rss_peak_mib": max(rss),
        "fd_peak": max(fd),
        "pid_peak": max(pid),
        "rss_growth_mib_per_hour": rss_growth,
        "native_input_latency_p95_ms": percentile(input_latency, 0.95),
        "native_input_latency_p99_ms": percentile(input_latency, 0.99),
        "agent_observe_latency_p95_ms": percentile(observe_latency, 0.95),
        "agent_act_latency_p95_ms": percentile(act_latency, 0.95),
    }
    checks = {
        "rss_peak_mib": "rss_peak_mib_max",
        "fd_peak": "fd_peak_max",
        "pid_peak": "pid_peak_max",
        "rss_growth_mib_per_hour": "rss_growth_mib_per_hour_max",
        "native_input_latency_p95_ms": "native_input_latency_p95_ms_max",
        "native_input_latency_p99_ms": "native_input_latency_p99_ms_max",
        "agent_observe_latency_p95_ms": "agent_observe_latency_p95_ms_max",
        "agent_act_latency_p95_ms": "agent_act_latency_p95_ms_max",
    }
    for observed_key, threshold_key in checks.items():
        if result[observed_key] > thresholds[threshold_key]:
            fail("HARDWARE_METRIC_THRESHOLD_EXCEEDED", observed_key)
    return result


def numeric_array(value: Any, name: str) -> list[float]:
    if not isinstance(value, list) or not value:
        fail("CYCLE_SERIES_REQUIRED", name)
    result: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)) or item < 0:
            fail("CYCLE_VALUE_INVALID", name)
        result.append(float(item))
    return result


def pass_array(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        fail("CYCLE_RESULT_SERIES_REQUIRED", name)
    for item in value:
        if not isinstance(item, dict) or set(item) != {"cycle", "status"}:
            fail("CYCLE_RESULT_FIELD_SET_MISMATCH", name)
        if not isinstance(item["cycle"], int) or item["cycle"] < 1 or item["status"] != "PASS":
            fail("CYCLE_RESULT_NOT_PASS", name)
    return value


def verify_cycles(path: Path, contract: dict[str, Any], require_physical: bool) -> dict[str, Any]:
    value = load_json(path)
    if set(value) != CYCLE_FIELDS or value["schema"] != "trillionnium.desktop.hardware-cycle-results.v1":
        fail("CYCLE_RESULTS_FIELD_SET_OR_SCHEMA_MISMATCH")
    boot = numeric_array(value["cold_boot_ready_ms"], "cold_boot_ready_ms")
    frame = numeric_array(value["compositor_to_first_frame_ms"], "compositor_to_first_frame_ms")
    crash = numeric_array(value["content_crash_recovery_ms"], "content_crash_recovery_ms")
    suspend = numeric_array(value["suspend_resume_ms"], "suspend_resume_ms")
    update = pass_array(value["update_commit_results"], "update_commit_results")
    rollback = pass_array(value["update_rollback_results"], "update_rollback_results")
    power = pass_array(value["power_loss_results"], "power_loss_results")
    thresholds = contract["thresholds"]
    observed = {
        "cold_boot_cycles": len(boot),
        "cold_boot_ready_ms_max_observed": max(boot),
        "compositor_to_first_frame_ms_max_observed": max(frame),
        "content_crash_recovery_cycles": len(crash),
        "content_crash_recovery_p95_ms": percentile(crash, 0.95),
        "suspend_resume_cycles": len(suspend),
        "suspend_resume_p95_ms": percentile(suspend, 0.95),
        "update_commit_cycles": len(update),
        "update_rollback_cycles": len(rollback),
        "power_loss_cycles": len(power),
    }
    if observed["cold_boot_ready_ms_max_observed"] > thresholds["cold_boot_ready_ms_max"]:
        fail("COLD_BOOT_THRESHOLD_EXCEEDED")
    if observed["compositor_to_first_frame_ms_max_observed"] > thresholds["compositor_to_first_frame_ms_max"]:
        fail("FIRST_FRAME_THRESHOLD_EXCEEDED")
    if observed["content_crash_recovery_p95_ms"] > thresholds["content_crash_recovery_p95_ms_max"]:
        fail("CRASH_RECOVERY_THRESHOLD_EXCEEDED")
    if observed["suspend_resume_p95_ms"] > thresholds["suspend_resume_p95_ms_max"]:
        fail("SUSPEND_RESUME_THRESHOLD_EXCEEDED")
    if require_physical:
        minimums = {
            "cold_boot_cycles": "cold_boot_cycles_min",
            "content_crash_recovery_cycles": "content_crash_recovery_cycles_min",
            "suspend_resume_cycles": "suspend_resume_cycles_min",
            "update_commit_cycles": "update_commit_cycles_min",
            "update_rollback_cycles": "update_rollback_cycles_min",
            "power_loss_cycles": "power_loss_cycles_min",
        }
        for observed_key, threshold_key in minimums.items():
            if observed[observed_key] < thresholds[threshold_key]:
                fail("HARDWARE_CYCLE_MINIMUM_NOT_MET", observed_key)
    return observed


def verify_subsystems(path: Path, contract: dict[str, Any], require_physical: bool) -> dict[str, int]:
    value = load_json(path)
    if value.get("schema") != "trillionnium.desktop.hardware-subsystem-results.v1":
        fail("SUBSYSTEM_RESULTS_SCHEMA_MISMATCH")
    results = value.get("results")
    required = contract["required_subsystems"]
    if not isinstance(results, dict) or set(results) != set(required):
        fail("SUBSYSTEM_CATEGORY_SET_MISMATCH")
    counts: dict[str, int] = {}
    for category, scenarios in required.items():
        category_result = results[category]
        if not isinstance(category_result, dict) or set(category_result) != set(scenarios):
            fail("SUBSYSTEM_SCENARIO_SET_MISMATCH", category)
        total = 0
        for scenario in scenarios:
            record = category_result[scenario]
            if not isinstance(record, dict) or set(record) != {"status", "cases"}:
                fail("SUBSYSTEM_SCENARIO_FIELD_SET_MISMATCH", scenario)
            if record["status"] != "PASS" or not isinstance(record["cases"], int) or record["cases"] < 1:
                fail("SUBSYSTEM_SCENARIO_NOT_PASS", scenario)
            total += record["cases"]
        counts[category] = total
    if require_physical:
        thresholds = contract["thresholds"]
        if counts["accessibility"] < thresholds["accessibility_scenarios_min"]:
            fail("ACCESSIBILITY_SCENARIO_MINIMUM_NOT_MET")
        if counts["ime"] < thresholds["ime_scenarios_min"]:
            fail("IME_SCENARIO_MINIMUM_NOT_MET")
        if counts["display"] < thresholds["multi_monitor_scenarios_min"]:
            fail("DISPLAY_SCENARIO_MINIMUM_NOT_MET")
    return counts


def verify_security(path: Path, contract: dict[str, Any], require_physical: bool) -> dict[str, Any]:
    value = load_json(path)
    expected = {
        "schema",
        "scenario_count",
        "critical_failures",
        "uncorrected_data_corruption",
        "unexpected_external_effects",
        "network_policy_bypasses",
        "categories",
    }
    if set(value) != expected or value["schema"] != "trillionnium.desktop.hardware-security-results.v1":
        fail("SECURITY_RESULTS_FIELD_SET_OR_SCHEMA_MISMATCH")
    for key in (
        "scenario_count",
        "critical_failures",
        "uncorrected_data_corruption",
        "unexpected_external_effects",
        "network_policy_bypasses",
    ):
        if not isinstance(value[key], int) or value[key] < 0:
            fail("SECURITY_RESULT_COUNT_INVALID", key)
    required_categories = set(contract["required_subsystems"]["security"])
    categories = value["categories"]
    if not isinstance(categories, dict) or set(categories) != required_categories:
        fail("SECURITY_CATEGORY_SET_MISMATCH")
    for name, record in categories.items():
        if not isinstance(record, dict) or set(record) != {"status", "cases"}:
            fail("SECURITY_CATEGORY_FIELD_SET_MISMATCH", name)
        if record["status"] != "PASS" or not isinstance(record["cases"], int) or record["cases"] < 1:
            fail("SECURITY_CATEGORY_NOT_PASS", name)
    if require_physical and value["scenario_count"] < contract["thresholds"]["security_scenarios_min"]:
        fail("SECURITY_SCENARIO_MINIMUM_NOT_MET")
    for key in (
        "critical_failures",
        "uncorrected_data_corruption",
        "unexpected_external_effects",
        "network_policy_bypasses",
    ):
        if value[key] != 0:
            fail("SECURITY_ZERO_TOLERANCE_VIOLATION", key)
    return value


def verify_known_limitations(value: Any) -> None:
    if not isinstance(value, list) or not value:
        fail("KNOWN_LIMITATIONS_REVIEW_REQUIRED")
    required = {"id", "severity", "description", "mitigation", "status", "reviewer_role"}
    for item in value:
        if not isinstance(item, dict) or set(item) != required:
            fail("KNOWN_LIMITATION_FIELD_SET_MISMATCH")
        for key in required:
            if not isinstance(item[key], str) or not item[key]:
                fail("KNOWN_LIMITATION_VALUE_INVALID", key)
        if item["status"] not in {"open", "accepted", "none_known_after_review"}:
            fail("KNOWN_LIMITATION_STATUS_INVALID")
        if item["reviewer_role"] not in {"independent_hardware_lab", "independent_security_review"}:
            fail("KNOWN_LIMITATION_REVIEWER_ROLE_INVALID")


def verify_evidence(
    evidence: dict[str, Any],
    evidence_dir: Path,
    trust: dict[str, Any],
    contract: dict[str, Any],
    *,
    now_epoch: int,
    require_physical: bool,
) -> dict[str, Any]:
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
        fail("HARDWARE_EVIDENCE_FIELD_SET_MISMATCH")
    if evidence["schema"] != contract["profile"]["evidence_schema"]:
        fail("HARDWARE_EVIDENCE_SCHEMA_MISMATCH")
    require_identifier(evidence["qualification_id"], "QUALIFICATION_ID_INVALID")
    if evidence["hardware_profile_id"] != contract["profile"]["profile_id"]:
        fail("HARDWARE_PROFILE_MISMATCH")
    if evidence["environment_kind"] not in {"fixture", "physical_hardware"}:
        fail("HARDWARE_ENVIRONMENT_KIND_INVALID")
    if require_physical and evidence["environment_kind"] != "physical_hardware":
        fail("PHYSICAL_HARDWARE_EVIDENCE_REQUIRED")
    started = evidence["started_at_epoch"]
    ended = evidence["ended_at_epoch"]
    if not isinstance(started, int) or not isinstance(ended, int) or not started < ended <= now_epoch:
        fail("HARDWARE_EVIDENCE_TIME_INVALID")
    duration = ended - started
    if require_physical and duration < contract["thresholds"]["final_stability_seconds_min"]:
        fail("FINAL_STABILITY_DURATION_NOT_MET")

    lab_key = verify_lab_signature(evidence, trust, now_epoch)
    if require_physical:
        if evidence["lab"]["signer_role"] != contract["promotion_rules"]["lab_signer_role"]:
            fail("INDEPENDENT_HARDWARE_LAB_ROLE_REQUIRED")
        if lab_key["production_enrolled"] is not True:
            fail("PRODUCTION_HARDWARE_LAB_KEY_REQUIRED")

    verify_artifact_identity(evidence["artifact_identity"], contract)
    verify_bom(evidence["bom"], contract)
    critical = evidence["critical_outcomes"]
    if not isinstance(critical, dict) or set(critical) != CRITICAL_FIELDS:
        fail("CRITICAL_OUTCOME_FIELD_SET_MISMATCH")
    if any(not isinstance(value, int) or value != 0 for value in critical.values()):
        fail("CRITICAL_OUTCOME_ZERO_TOLERANCE_VIOLATION")
    verify_known_limitations(evidence["known_limitations"])

    files = verify_artifacts(evidence["artifacts"], evidence_dir, contract)
    identity = evidence["artifact_identity"]
    role_identity = {
        "sbom": "sbom_sha256",
        "licenses": "licenses_sha256",
        "provenance": "provenance_sha256",
        "known_limitations": "known_limitations_sha256",
    }
    artifact_records = {item["role"]: item for item in evidence["artifacts"]}
    for role, identity_key in role_identity.items():
        if artifact_records[role]["sha256"] != identity[identity_key]:
            fail("ARTIFACT_IDENTITY_ROLE_DIGEST_MISMATCH", role)

    metrics = verify_metrics(
        files["metrics_samples"],
        contract,
        started_at=started,
        ended_at=ended,
        require_physical=require_physical,
    )
    cycles = verify_cycles(files["cycle_results"], contract, require_physical)
    subsystem_counts = verify_subsystems(
        files["subsystem_results"], contract, require_physical
    )
    security = verify_security(files["security_results"], contract, require_physical)

    result = {
        "schema": "trillionnium.desktop.hardware-qualification-verification-result.v1",
        "status": (
            "PASS_PHYSICAL_POLICY_ELIGIBILITY"
            if require_physical
            else "PASS_FIXTURE_FORMAT_ONLY"
        ),
        "qualification_id": evidence["qualification_id"],
        "hardware_profile_id": evidence["hardware_profile_id"],
        "environment_kind": evidence["environment_kind"],
        "duration_seconds": duration,
        "metrics": metrics,
        "cycles": cycles,
        "subsystem_case_counts": subsystem_counts,
        "security_scenario_count": security["scenario_count"],
        "evidence_manifest_sha256": sha256(canonical_json(evidence)),
        "policy_eligible": require_physical,
        "physical_hardware_run_completed_by_this_source_gate": False,
        "independent_hardware_lab_signature_obtained_by_this_source_gate": False,
        "hardware_beta_promoted": False,
        "release_ready": False,
    }
    unsigned = copy.deepcopy(result)
    result["verification_receipt_sha256"] = sha256(canonical_json(unsigned))
    return result


def artifact_record(role: str, path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256(data),
        "bytes": len(data),
    }


def fixture_bom() -> dict[str, Any]:
    return {
        "system_vendor": "Fixture Vendor",
        "system_product": "Fixture Product",
        "system_serial_hash": sha256(b"fixture-system-serial"),
        "board_vendor": "Fixture Board Vendor",
        "board_name": "Fixture Board",
        "board_version": "1",
        "firmware_vendor": "Fixture Firmware",
        "firmware_version": "1",
        "firmware_date": "2026-01-01",
        "cpu_vendor": "GenuineIntel",
        "cpu_model": "Fixture CPU",
        "cpu_microcode": "0x1",
        "memory_bytes": 8 * 1024**3,
        "storage_model": "Fixture Storage",
        "storage_firmware": "1",
        "storage_serial_hash": sha256(b"fixture-storage-serial"),
        "gpu_pci_id": "0000:0000",
        "gpu_subsystem_id": "0000:0000",
        "gpu_driver": "fixture",
        "render_mode": "software_fallback",
        "display_edid_hashes": [sha256(b"fixture-edid")],
        "input_usb_ids": ["0000:0000"],
        "audio_codec_ids": ["fixture-audio"],
        "network_device_ids": ["none-in-fixture"],
        "tpm_present": True,
        "tpm_version": "2.0",
        "secure_boot_state": "fixture-not-proven",
    }


def _reset_fixture_root(root: Path) -> None:
    """Create an empty fixture directory without following stale symlinks."""
    if root.is_symlink():
        fail("FIXTURE_ROOT_SYMLINK_REJECTED", str(root))
    if root.exists() and not root.is_dir():
        fail("FIXTURE_ROOT_NOT_DIRECTORY", str(root))
    root.mkdir(parents=True, exist_ok=True)
    for child in list(root.iterdir()):
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        else:
            shutil.rmtree(child)


def create_fixture_bundle(
    contract: dict[str, Any], root: Path, seed: bytes
) -> tuple[dict[str, Any], dict[str, Any]]:
    _reset_fixture_root(root)
    roles = contract["required_artifact_roles"]
    metrics_path = root / "metrics.jsonl"
    metrics_records = [
        {
            "timestamp_epoch": 100 + index * 60,
            "rss_mib": 512 + index * 0.01,
            "fd_count": 128,
            "pid_count": 64,
            "native_input_latency_ms": 10,
            "agent_observe_latency_ms": 50,
            "agent_act_latency_ms": 80,
        }
        for index in range(5)
    ]
    metrics_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in metrics_records),
        encoding="utf-8",
    )
    cycle_path = root / "cycles.json"
    cycle_path.write_text(
        json.dumps(
            {
                "schema": "trillionnium.desktop.hardware-cycle-results.v1",
                "cold_boot_ready_ms": [10000],
                "compositor_to_first_frame_ms": [1000],
                "content_crash_recovery_ms": [1000],
                "suspend_resume_ms": [2000],
                "update_commit_results": [{"cycle": 1, "status": "PASS"}],
                "update_rollback_results": [{"cycle": 1, "status": "PASS"}],
                "power_loss_results": [{"cycle": 1, "status": "PASS"}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    subsystem_path = root / "subsystems.json"
    subsystem_path.write_text(
        json.dumps(
            {
                "schema": "trillionnium.desktop.hardware-subsystem-results.v1",
                "results": {
                    category: {
                        scenario: {"status": "PASS", "cases": 1}
                        for scenario in scenarios
                    }
                    for category, scenarios in contract["required_subsystems"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    security_path = root / "security.json"
    security_path.write_text(
        json.dumps(
            {
                "schema": "trillionnium.desktop.hardware-security-results.v1",
                "scenario_count": len(contract["required_subsystems"]["security"]),
                "critical_failures": 0,
                "uncorrected_data_corruption": 0,
                "unexpected_external_effects": 0,
                "network_policy_bypasses": 0,
                "categories": {
                    name: {"status": "PASS", "cases": 1}
                    for name in contract["required_subsystems"]["security"]
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    content_by_role: dict[str, Path] = {
        "metrics_samples": metrics_path,
        "cycle_results": cycle_path,
        "subsystem_results": subsystem_path,
        "security_results": security_path,
    }
    for role in roles:
        if role in content_by_role:
            continue
        path = root / f"{role}.txt"
        path.write_text(f"fixture {role}; not production evidence\n", encoding="utf-8")
        content_by_role[role] = path
    artifacts = [artifact_record(role, content_by_role[role], root) for role in roles]
    by_role = {item["role"]: item for item in artifacts}
    identity = {
        "source_commit": hashlib.sha1(b"fixture source").hexdigest(),
        "release_tree": hashlib.sha1(b"fixture tree").hexdigest(),
        "image_sha256": sha256(b"fixture image"),
        "image_bytes": len(b"fixture image"),
        "kernel_sha256": sha256(b"fixture kernel"),
        "initrd_sha256": sha256(b"fixture initrd"),
        "package_lock_sha256": sha256(b"fixture package lock"),
        "sbom_sha256": by_role["sbom"]["sha256"],
        "licenses_sha256": by_role["licenses"]["sha256"],
        "provenance_sha256": by_role["provenance"]["sha256"],
        "known_limitations_sha256": by_role["known_limitations"]["sha256"],
    }
    evidence: dict[str, Any] = {
        "schema": contract["profile"]["evidence_schema"],
        "qualification_id": "fixture-qualification-1",
        "hardware_profile_id": contract["profile"]["profile_id"],
        "environment_kind": "fixture",
        "lab": {
            "lab_id": "fixture-lab",
            "lab_key_id": "fixture-lab-key-1",
            "signer_role": "fixture_only",
        },
        "started_at_epoch": 100,
        "ended_at_epoch": 340,
        "artifact_identity": identity,
        "bom": fixture_bom(),
        "critical_outcomes": {key: 0 for key in CRITICAL_FIELDS},
        "artifacts": artifacts,
        "known_limitations": [
            {
                "id": "fixture-not-physical",
                "severity": "blocking",
                "description": "This is deterministic fixture evidence, not a physical hardware run.",
                "mitigation": "Run the complete corpus on the fixed hardware profile.",
                "status": "open",
                "reviewer_role": "independent_security_review",
            }
        ],
        "signature": {"algorithm": "Ed25519", "value_base64": ""},
    }
    public = ed25519_public_from_seed(seed)
    evidence["signature"]["value_base64"] = base64.b64encode(
        ed25519_sign_fixture(seed, signed_payload(evidence))
    ).decode("ascii")
    thresholds = contract["thresholds"]
    fixture_key_expires_at = (
        100
        + max(
            thresholds["preliminary_stability_seconds_min"],
            thresholds["final_stability_seconds_min"],
        )
        + thresholds["maximum_sample_gap_seconds"]
        + 3600
    )
    trust = {
        "schema": "trillionnium.desktop.hardware-lab-trust.v1",
        "labs": {
            "fixture-lab": {
                "keys": {
                    "fixture-lab-key-1": {
                        "status": "active",
                        "signer_role": "fixture_only",
                        "public_key_base64": base64.b64encode(public).decode("ascii"),
                        "not_before_epoch": 1,
                        "expires_at_epoch": fixture_key_expires_at,
                        "production_enrolled": False,
                    }
                }
            }
        },
        "revoked_qualification_ids": [],
    }
    return evidence, trust


def self_test(contract: dict[str, Any]) -> dict[str, Any]:
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        evidence, trust = create_fixture_bundle(contract, root, seed)
        result = verify_evidence(
            evidence,
            root,
            trust,
            contract,
            now_epoch=500,
            require_physical=False,
        )
        try:
            verify_evidence(
                evidence,
                root,
                trust,
                contract,
                now_epoch=500,
                require_physical=True,
            )
        except HardwareEvidenceError as error:
            if error.reason != "PHYSICAL_HARDWARE_EVIDENCE_REQUIRED":
                raise
        else:
            raise AssertionError("fixture evidence was incorrectly promotion eligible")
    return {
        "schema": "trillionnium.desktop.hardware-evidence-self-test.v1",
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "fixture_verification_status": result["status"],
        "fixture_policy_eligible": result["policy_eligible"],
        "physical_hardware_run_completed": False,
        "independent_hardware_lab_signature_obtained": False,
        "stability_24h_completed": False,
        "stability_72h_completed": False,
        "power_loss_corpus_completed": False,
        "hardware_beta_qualified": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--evidence", type=Path, required=True)
    verify_parser.add_argument("--evidence-dir", type=Path, required=True)
    verify_parser.add_argument("--trust", type=Path, required=True)
    verify_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    verify_parser.add_argument("--now-epoch", type=int, required=True)
    verify_parser.add_argument("--require-physical", action="store_true")
    verify_parser.add_argument("--write-result", type=Path)
    self_parser = sub.add_parser("self-test")
    self_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    self_parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    try:
        contract = load_json(args.contract)
        if contract.get("status") != "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D7":
            fail("D8_CONTRACT_STATUS_WIDENED")
        if args.command == "verify":
            result = verify_evidence(
                load_json(args.evidence),
                args.evidence_dir,
                load_json(args.trust),
                contract,
                now_epoch=args.now_epoch,
                require_physical=args.require_physical,
            )
        else:
            result = self_test(contract)
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.write_result:
            args.write_result.parent.mkdir(parents=True, exist_ok=True)
            args.write_result.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except HardwareEvidenceError as error:
        print(
            json.dumps(
                {"status": "REJECTED", "reason": error.reason, "detail": error.detail},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
