#!/usr/bin/env python3
"""Strict offline verifier for independently produced S12 release evidence.

The verifier consumes a detached, externally rooted signature and one closed
JSON packet.  It does not build an image, access production signing keys,
advance time, exercise hardware, remove power, sign, promote, or publish.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
PLAN_REVISION = "2026-08-29-d6"
PACKET_SCHEMA = "trillionnium.release-evidence.v1"
RESULT_SCHEMA = "trillionnium.release-qualification-result.v1"
MAX_PACKET_BYTES = 2 * 1024 * 1024
MAX_PACKET_AGE_SECONDS = 24 * 60 * 60
MAX_CLOCK_SKEW_SECONDS = 5 * 60
MAX_EVIDENCE_AGE_SECONDS = 14 * 24 * 60 * 60
MAX_CHECKPOINT_GAP_SECONDS = 15 * 60
REQUIRED_ENDURANCE_HOURS = {24, 72}
REQUIRED_POWER_CUTPOINTS = {
    "update_staging",
    "first_boot_before_health_commit",
    "rollback_or_recovery",
}
REQUIRED_HARDWARE_RESULTS = {
    "firmware",
    "cpu",
    "memory",
    "storage",
    "gpu",
    "display",
    "input",
    "audio",
    "network",
    "suspend_resume",
    "recovery",
}
ROLE_NAMES = (
    "author",
    "reviewer",
    "builder_a",
    "builder_b",
    "hardware_attestor",
    "endurance_attestor",
    "power_attestor",
    "key_controller_a",
    "key_controller_b",
    "signer",
    "promoter",
    "publisher",
    "release_attestor",
)
TOP_FIELDS = {
    "schema",
    "repository",
    "issued_unix",
    "attestor",
    "source",
    "image",
    "s10",
    "s11",
    "builders",
    "hardware",
    "endurance",
    "power_loss",
    "key_custody",
    "roles",
    "publication",
}
SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}\Z")
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\Z")


class QualificationError(RuntimeError):
    pass


def strict_json_bytes(data: bytes) -> dict[str, Any]:
    if not isinstance(data, bytes) or not data or len(data) > MAX_PACKET_BYTES:
        raise QualificationError("evidence packet is empty, non-bytes, or over limit")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise QualificationError("evidence packet is not strict UTF-8") from error
    if text.startswith("\ufeff"):
        raise QualificationError("UTF-8 BOM is forbidden")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise QualificationError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise QualificationError(f"non-JSON numeric constant {value!r}")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise QualificationError("evidence packet is malformed JSON") from error
    if not isinstance(value, dict):
        raise QualificationError("evidence packet root must be an object")
    return value


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as error:
        raise QualificationError("evidence cannot be canonicalized") from error


def _exact(value: object, fields: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != fields:
        errors.append(
            f"{label} fields differ: missing={sorted(fields - actual)}, "
            f"extra={sorted(actual - fields)}"
        )
        return False
    return True


def _sha1(value: object, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or SHA1_RE.fullmatch(value) is None:
        errors.append(f"{label} is not a lowercase Git SHA-1")
        return None
    return value


def _sha256(value: object, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        errors.append(f"{label} is not a lowercase SHA-256")
        return None
    return value


def _identifier(value: object, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or IDENTIFIER_RE.fullmatch(value) is None:
        errors.append(f"{label} is not a bounded identifier")
        return None
    return value


def _login(value: object, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or LOGIN_RE.fullmatch(value) is None:
        errors.append(f"{label} is not a bounded GitHub login")
        return None
    return value


def _positive_int(
    value: object, label: str, errors: list[str], *, maximum: int | None = None
) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        errors.append(f"{label} must be a positive integer")
        return None
    if maximum is not None and value > maximum:
        errors.append(f"{label} exceeds its bound")
        return None
    return value


def _observed_time(
    value: object, label: str, issued_unix: int | None, errors: list[str]
) -> int | None:
    observed = _positive_int(value, label, errors)
    if observed is None or issued_unix is None:
        return observed
    if observed > issued_unix + MAX_CLOCK_SKEW_SECONDS:
        errors.append(f"{label} occurs after packet issuance")
    if issued_unix - observed > MAX_EVIDENCE_AGE_SECONDS:
        errors.append(f"{label} is older than the admitted evidence window")
    return observed


def _roles(value: object, errors: list[str]) -> dict[str, tuple[int, str]]:
    if not isinstance(value, dict) or set(value) != set(ROLE_NAMES):
        errors.append("role map is not the exact closed role set")
        return {}
    result: dict[str, tuple[int, str]] = {}
    seen_ids: set[int] = set()
    for role in ROLE_NAMES:
        entry = value.get(role)
        if not _exact(entry, {"id", "login"}, f"role {role}", errors):
            continue
        assert isinstance(entry, dict)
        actor_id = _positive_int(entry.get("id"), f"role {role} id", errors)
        login = _login(entry.get("login"), f"role {role} login", errors)
        if actor_id is None or login is None:
            continue
        if actor_id in seen_ids:
            errors.append(f"actor id {actor_id} is shared across separated roles")
        seen_ids.add(actor_id)
        result[role] = (actor_id, login)
    return result


def _matches_role(
    role_map: dict[str, tuple[int, str]],
    role: str,
    actor_id: object,
    actor_login: object,
    label: str,
    errors: list[str],
) -> None:
    expected = role_map.get(role)
    if expected is None or (actor_id, actor_login) != expected:
        errors.append(f"{label} is not bound to role {role}")


def verify_packet(
    packet: dict[str, Any],
    *,
    current_main_sha: str,
    signature_verified: bool,
    public_key_sha256: str | None,
    expected_attestor_id: int | None,
    expected_attestor_login: str | None,
    now_unix: int,
) -> list[str]:
    errors: list[str] = []
    if set(packet) != TOP_FIELDS:
        errors.append("evidence packet top-level field set is not exact")
    if packet.get("schema") != PACKET_SCHEMA:
        errors.append("release evidence schema identity is invalid")
    if packet.get("repository") != REPOSITORY:
        errors.append("release evidence repository identity is invalid")
    if SHA1_RE.fullmatch(current_main_sha) is None:
        errors.append("current main SHA input is invalid")
    if signature_verified is not True:
        errors.append("release evidence detached signature is not verified")
    if not isinstance(public_key_sha256, str) or SHA256_RE.fullmatch(public_key_sha256) is None:
        errors.append("release evidence public-key digest is not externally bound")
    if type(expected_attestor_id) is not int or expected_attestor_id <= 0:
        errors.append("expected release attestor id is not externally bound")
    if not isinstance(expected_attestor_login, str) or LOGIN_RE.fullmatch(expected_attestor_login) is None:
        errors.append("expected release attestor login is not externally bound")

    issued = _positive_int(packet.get("issued_unix"), "issued_unix", errors)
    if issued is not None:
        if issued > now_unix + MAX_CLOCK_SKEW_SECONDS:
            errors.append("release evidence packet is from the future")
        if now_unix - issued > MAX_PACKET_AGE_SECONDS:
            errors.append("release evidence packet is stale")

    role_map = _roles(packet.get("roles"), errors)
    attestor = packet.get("attestor")
    if _exact(attestor, {"id", "login", "role"}, "release attestor", errors):
        assert isinstance(attestor, dict)
        attestor_id = _positive_int(attestor.get("id"), "release attestor id", errors)
        attestor_login = _login(attestor.get("login"), "release attestor login", errors)
        if attestor.get("role") != "independent_release_attestor":
            errors.append("release attestor role is invalid")
        if (attestor_id, attestor_login) != (
            expected_attestor_id,
            expected_attestor_login,
        ):
            errors.append("release attestor does not match the external identity binding")
        _matches_role(
            role_map,
            "release_attestor",
            attestor_id,
            attestor_login,
            "release attestor",
            errors,
        )

    source = packet.get("source")
    source_fields = {"main_sha", "tree_sha", "plan_revision", "locked_inputs_sha256"}
    source_main: str | None = None
    source_tree: str | None = None
    locked_inputs: str | None = None
    if _exact(source, source_fields, "source", errors):
        assert isinstance(source, dict)
        source_main = _sha1(source.get("main_sha"), "source main SHA", errors)
        source_tree = _sha1(source.get("tree_sha"), "source tree SHA", errors)
        locked_inputs = _sha256(
            source.get("locked_inputs_sha256"), "locked inputs digest", errors
        )
        if source.get("plan_revision") != PLAN_REVISION:
            errors.append("source plan revision is not the active d6 revision")
        if source_main != current_main_sha:
            errors.append("release evidence is not bound to current main")

    image = packet.get("image")
    image_fields = {
        "sha256",
        "normalized_sha256",
        "bytes",
        "sbom_sha256",
        "license_report_sha256",
        "vulnerability_report_sha256",
    }
    image_digest: str | None = None
    normalized_digest: str | None = None
    image_bytes: int | None = None
    if _exact(image, image_fields, "image", errors):
        assert isinstance(image, dict)
        image_digest = _sha256(image.get("sha256"), "whole image digest", errors)
        normalized_digest = _sha256(
            image.get("normalized_sha256"), "normalized image digest", errors
        )
        image_bytes = _positive_int(
            image.get("bytes"), "whole image byte length", errors, maximum=1 << 44
        )
        for key in (
            "sbom_sha256",
            "license_report_sha256",
            "vulnerability_report_sha256",
        ):
            _sha256(image.get(key), key.replace("_", " "), errors)

    s10 = packet.get("s10")
    s10_fields = {
        "receipt_sha256",
        "image_sha256",
        "installed_product_path_passed",
        "content_crash_reconstruction_passed",
        "stale_reference_rejected",
        "no_automatic_replay_passed",
    }
    if _exact(s10, s10_fields, "S10 evidence", errors):
        assert isinstance(s10, dict)
        _sha256(s10.get("receipt_sha256"), "S10 receipt digest", errors)
        if s10.get("image_sha256") != image_digest:
            errors.append("S10 receipt is not bound to the release image")
        for key in s10_fields - {"receipt_sha256", "image_sha256"}:
            if s10.get(key) is not True:
                errors.append(f"S10 condition {key} is not true")

    s11 = packet.get("s11")
    s11_fields = {
        "receipt_sha256",
        "source_image_sha256",
        "target_image_sha256",
        "installed_update_recovery_passed",
        "restart_cutpoints_passed",
        "no_automatic_replay_passed",
    }
    if _exact(s11, s11_fields, "S11 evidence", errors):
        assert isinstance(s11, dict)
        _sha256(s11.get("receipt_sha256"), "S11 receipt digest", errors)
        source_image = _sha256(
            s11.get("source_image_sha256"), "S11 source image digest", errors
        )
        if s11.get("target_image_sha256") != image_digest:
            errors.append("S11 target is not the release image")
        if source_image == image_digest:
            errors.append("S11 source and target image digests are not distinct")
        for key in s11_fields - {
            "receipt_sha256",
            "source_image_sha256",
            "target_image_sha256",
        }:
            if s11.get(key) is not True:
                errors.append(f"S11 condition {key} is not true")

    builders = packet.get("builders")
    builder_fields = {
        "role",
        "actor_id",
        "actor_login",
        "builder_id",
        "runner_id",
        "administrative_domain",
        "source_sha",
        "source_tree",
        "locked_inputs_sha256",
        "image_sha256",
        "normalized_image_sha256",
        "image_bytes",
        "build_receipt_sha256",
        "observed_unix",
    }
    observed_roles: set[str] = set()
    builder_ids: set[str] = set()
    runner_ids: set[str] = set()
    domains: set[str] = set()
    if not isinstance(builders, list) or len(builders) != 2:
        errors.append("exactly two independent builder records are required")
    else:
        for index, builder in enumerate(builders):
            label = f"builder[{index}]"
            if not _exact(builder, builder_fields, label, errors):
                continue
            assert isinstance(builder, dict)
            role = builder.get("role")
            if role not in {"builder_a", "builder_b"} or role in observed_roles:
                errors.append(f"{label} role is invalid or duplicated")
            else:
                observed_roles.add(role)
                _matches_role(
                    role_map,
                    role,
                    builder.get("actor_id"),
                    builder.get("actor_login"),
                    label,
                    errors,
                )
            builder_id = _identifier(builder.get("builder_id"), f"{label} id", errors)
            runner_id = _identifier(builder.get("runner_id"), f"{label} runner", errors)
            domain = _identifier(
                builder.get("administrative_domain"), f"{label} domain", errors
            )
            if builder_id is not None:
                if builder_id in builder_ids:
                    errors.append("builder identities are not independent")
                builder_ids.add(builder_id)
            if runner_id is not None:
                if runner_id in runner_ids:
                    errors.append("builder runner identities are not independent")
                runner_ids.add(runner_id)
            if domain is not None:
                if domain in domains:
                    errors.append("builder administrative domains are not independent")
                domains.add(domain)
            if builder.get("source_sha") != source_main:
                errors.append(f"{label} source SHA mismatch")
            if builder.get("source_tree") != source_tree:
                errors.append(f"{label} source tree mismatch")
            if builder.get("locked_inputs_sha256") != locked_inputs:
                errors.append(f"{label} locked-input digest mismatch")
            if builder.get("image_sha256") != image_digest:
                errors.append(f"{label} whole-image digest mismatch")
            if builder.get("normalized_image_sha256") != normalized_digest:
                errors.append(f"{label} normalized-image digest mismatch")
            if builder.get("image_bytes") != image_bytes:
                errors.append(f"{label} image length mismatch")
            _sha256(
                builder.get("build_receipt_sha256"), f"{label} receipt digest", errors
            )
            _observed_time(
                builder.get("observed_unix"), f"{label} observation", issued, errors
            )
        if observed_roles != {"builder_a", "builder_b"}:
            errors.append("builder role inventory is incomplete")

    hardware = packet.get("hardware")
    hardware_fields = {
        "attestor_id",
        "attestor_login",
        "observed_unix",
        "image_sha256",
        "bom_sha256",
        "bom",
        "secure_boot_observed",
        "tpm_or_equivalent_observed",
        "results",
        "receipt_sha256",
    }
    bom_digest: str | None = None
    if _exact(hardware, hardware_fields, "hardware evidence", errors):
        assert isinstance(hardware, dict)
        _matches_role(
            role_map,
            "hardware_attestor",
            hardware.get("attestor_id"),
            hardware.get("attestor_login"),
            "hardware evidence",
            errors,
        )
        _observed_time(
            hardware.get("observed_unix"), "hardware observation", issued, errors
        )
        if hardware.get("image_sha256") != image_digest:
            errors.append("hardware evidence is not bound to the release image")
        bom_digest = _sha256(hardware.get("bom_sha256"), "hardware BOM digest", errors)
        _sha256(hardware.get("receipt_sha256"), "hardware receipt digest", errors)
        if hardware.get("secure_boot_observed") is not True:
            errors.append("Secure Boot was not observed on the fixed hardware")
        if hardware.get("tpm_or_equivalent_observed") is not True:
            errors.append("TPM or equivalent hardware root was not observed")
        bom = hardware.get("bom")
        bom_fields = {
            "model",
            "revision",
            "firmware_sha256",
            "cpu",
            "memory_bytes",
            "storage",
            "gpu",
            "display_edid_sha256",
            "input_inventory_sha256",
            "audio",
            "network",
        }
        if _exact(bom, bom_fields, "hardware BOM", errors):
            assert isinstance(bom, dict)
            for key in ("model", "revision", "cpu", "storage", "gpu", "audio", "network"):
                _identifier(bom.get(key), f"hardware BOM {key}", errors)
            _positive_int(
                bom.get("memory_bytes"), "hardware BOM memory", errors, maximum=1 << 50
            )
            _sha256(bom.get("firmware_sha256"), "firmware digest", errors)
            _sha256(bom.get("display_edid_sha256"), "display EDID digest", errors)
            _sha256(
                bom.get("input_inventory_sha256"), "input inventory digest", errors
            )
            if bom_digest is not None:
                observed_bom_digest = hashlib.sha256(canonical_json(bom)).hexdigest()
                if observed_bom_digest != bom_digest:
                    errors.append("hardware BOM digest does not match the exact BOM")
        results = hardware.get("results")
        if not isinstance(results, dict) or set(results) != REQUIRED_HARDWARE_RESULTS:
            errors.append("hardware result inventory is not exact")
        elif any(result != "pass" for result in results.values()):
            errors.append("one or more fixed-hardware results did not pass")

    endurance = packet.get("endurance")
    endurance_fields = {
        "duration_hours",
        "record_id",
        "attestor_id",
        "attestor_login",
        "image_sha256",
        "bom_sha256",
        "start_unix",
        "end_unix",
        "checkpoints_unix",
        "terminal_status",
        "receipt_sha256",
    }
    observed_durations: set[int] = set()
    if not isinstance(endurance, list) or len(endurance) != 2:
        errors.append("exactly one 24-hour and one 72-hour endurance record are required")
    else:
        for index, record in enumerate(endurance):
            label = f"endurance[{index}]"
            if not _exact(record, endurance_fields, label, errors):
                continue
            assert isinstance(record, dict)
            hours = record.get("duration_hours")
            if type(hours) is not int or hours not in REQUIRED_ENDURANCE_HOURS or hours in observed_durations:
                errors.append(f"{label} duration is invalid or duplicated")
                continue
            observed_durations.add(hours)
            _identifier(record.get("record_id"), f"{label} id", errors)
            _matches_role(
                role_map,
                "endurance_attestor",
                record.get("attestor_id"),
                record.get("attestor_login"),
                label,
                errors,
            )
            if record.get("image_sha256") != image_digest:
                errors.append(f"{label} image digest mismatch")
            if record.get("bom_sha256") != bom_digest:
                errors.append(f"{label} hardware BOM mismatch")
            start = _positive_int(record.get("start_unix"), f"{label} start", errors)
            end = _positive_int(record.get("end_unix"), f"{label} end", errors)
            if start is not None and end is not None:
                required = hours * 60 * 60
                elapsed = end - start
                if elapsed < required or elapsed > required + MAX_CHECKPOINT_GAP_SECONDS:
                    errors.append(f"{label} elapsed time does not prove {hours} hours")
                if issued is not None and end > issued + MAX_CLOCK_SKEW_SECONDS:
                    errors.append(f"{label} ends after packet issuance")
                if issued is not None and issued - start > MAX_EVIDENCE_AGE_SECONDS:
                    errors.append(f"{label} is outside the admitted evidence window")
            checkpoints = record.get("checkpoints_unix")
            if not isinstance(checkpoints, list) or len(checkpoints) < 2 or len(checkpoints) > 2048:
                errors.append(f"{label} checkpoints are absent or unbounded")
            elif any(type(item) is not int or item <= 0 for item in checkpoints):
                errors.append(f"{label} checkpoints are not positive integers")
            else:
                if start is not None and checkpoints[0] != start:
                    errors.append(f"{label} first checkpoint does not equal start")
                if end is not None and checkpoints[-1] != end:
                    errors.append(f"{label} final checkpoint does not equal end")
                for left, right in zip(checkpoints, checkpoints[1:]):
                    if right <= left:
                        errors.append(f"{label} checkpoints are not strictly monotonic")
                        break
                    if right - left > MAX_CHECKPOINT_GAP_SECONDS:
                        errors.append(f"{label} checkpoint gap exceeds 15 minutes")
                        break
            if record.get("terminal_status") != "pass":
                errors.append(f"{label} terminal status did not pass")
            _sha256(record.get("receipt_sha256"), f"{label} receipt digest", errors)
        if observed_durations != REQUIRED_ENDURANCE_HOURS:
            errors.append("24-hour and 72-hour endurance coverage is incomplete")

    power = packet.get("power_loss")
    power_fields = {
        "cutpoint",
        "record_id",
        "attestor_id",
        "attestor_login",
        "observed_unix",
        "image_sha256",
        "bom_sha256",
        "method",
        "filesystem_status",
        "journal_status",
        "update_reconciliation_status",
        "receipt_sha256",
    }
    observed_cutpoints: set[str] = set()
    if not isinstance(power, list) or len(power) != len(REQUIRED_POWER_CUTPOINTS):
        errors.append("raw-power evidence count is not exact")
    else:
        for index, record in enumerate(power):
            label = f"power_loss[{index}]"
            if not _exact(record, power_fields, label, errors):
                continue
            assert isinstance(record, dict)
            cutpoint = record.get("cutpoint")
            if cutpoint not in REQUIRED_POWER_CUTPOINTS or cutpoint in observed_cutpoints:
                errors.append(f"{label} cutpoint is invalid or duplicated")
            else:
                observed_cutpoints.add(cutpoint)
            _identifier(record.get("record_id"), f"{label} id", errors)
            _matches_role(
                role_map,
                "power_attestor",
                record.get("attestor_id"),
                record.get("attestor_login"),
                label,
                errors,
            )
            _observed_time(
                record.get("observed_unix"), f"{label} observation", issued, errors
            )
            if record.get("image_sha256") != image_digest:
                errors.append(f"{label} image digest mismatch")
            if record.get("bom_sha256") != bom_digest:
                errors.append(f"{label} hardware BOM mismatch")
            if record.get("method") != "non_graceful_power_removal":
                errors.append(f"{label} is not non-graceful physical power removal")
            for key in (
                "filesystem_status",
                "journal_status",
                "update_reconciliation_status",
            ):
                if record.get(key) != "pass":
                    errors.append(f"{label} {key} did not pass")
            _sha256(record.get("receipt_sha256"), f"{label} receipt digest", errors)
        if observed_cutpoints != REQUIRED_POWER_CUTPOINTS:
            errors.append("raw-power cutpoint coverage is incomplete")

    key_custody = packet.get("key_custody")
    key_fields = {
        "mode",
        "key_id",
        "key_fingerprint_sha256",
        "controller_ids",
        "controller_logins",
        "signer_id",
        "signer_login",
        "rotation_drill",
        "revocation_drill",
        "compromised_builder_drill",
    }
    if _exact(key_custody, key_fields, "key custody", errors):
        assert isinstance(key_custody, dict)
        if key_custody.get("mode") not in {"offline", "hsm"}:
            errors.append("production key custody is neither offline nor HSM-backed")
        _identifier(key_custody.get("key_id"), "production key id", errors)
        _sha256(
            key_custody.get("key_fingerprint_sha256"),
            "production key fingerprint",
            errors,
        )
        expected_controllers = {
            role_map.get("key_controller_a"),
            role_map.get("key_controller_b"),
        }
        controller_ids = key_custody.get("controller_ids")
        controller_logins = key_custody.get("controller_logins")
        observed_controllers: set[tuple[int, str]] = set()
        if (
            not isinstance(controller_ids, list)
            or not isinstance(controller_logins, list)
            or len(controller_ids) != 2
            or len(controller_logins) != 2
        ):
            errors.append("key custody requires exactly two controller identities")
        else:
            for actor_id, login in zip(controller_ids, controller_logins):
                if type(actor_id) is not int or not isinstance(login, str):
                    errors.append("key controller identity is malformed")
                else:
                    observed_controllers.add((actor_id, login))
            if observed_controllers != expected_controllers or None in expected_controllers:
                errors.append("key controllers do not match the separated role bindings")
        _matches_role(
            role_map,
            "signer",
            key_custody.get("signer_id"),
            key_custody.get("signer_login"),
            "production signer",
            errors,
        )
        drill_fields = {"status", "observed_unix", "receipt_sha256"}
        for drill_name in (
            "rotation_drill",
            "revocation_drill",
            "compromised_builder_drill",
        ):
            drill = key_custody.get(drill_name)
            if _exact(drill, drill_fields, drill_name, errors):
                assert isinstance(drill, dict)
                if drill.get("status") != "pass":
                    errors.append(f"{drill_name} did not pass")
                _observed_time(
                    drill.get("observed_unix"), f"{drill_name} observation", issued, errors
                )
                _sha256(
                    drill.get("receipt_sha256"), f"{drill_name} receipt digest", errors
                )

    publication = packet.get("publication")
    publication_fields = {
        "environment",
        "protected_environment_verified",
        "main_sha",
        "promoter_id",
        "promoter_login",
        "publisher_id",
        "publisher_login",
        "release_published",
    }
    if _exact(publication, publication_fields, "publication boundary", errors):
        assert isinstance(publication, dict)
        if publication.get("environment") != "production-publication":
            errors.append("publication environment identity is invalid")
        if publication.get("protected_environment_verified") is not True:
            errors.append("production publication environment is not verified protected")
        if publication.get("main_sha") != current_main_sha:
            errors.append("publication boundary is not bound to current main")
        _matches_role(
            role_map,
            "promoter",
            publication.get("promoter_id"),
            publication.get("promoter_login"),
            "promoter",
            errors,
        )
        _matches_role(
            role_map,
            "publisher",
            publication.get("publisher_id"),
            publication.get("publisher_login"),
            "publisher",
            errors,
        )
        if publication.get("release_published") is not False:
            errors.append("qualification packet must precede independent publication")

    return errors


def _regular_bytes(path: Path, label: str, maximum: int | None = None) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"{label} is not a regular non-symlink file")
    data = path.read_bytes()
    if maximum is not None and len(data) > maximum:
        raise QualificationError(f"{label} exceeds its byte bound")
    return data


def verify_detached_signature(
    packet_path: Path,
    signature_path: Path,
    public_key_path: Path,
    expected_public_key_sha256: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    if SHA256_RE.fullmatch(expected_public_key_sha256) is None:
        raise QualificationError("expected public-key digest is invalid")
    _regular_bytes(packet_path, "evidence packet", MAX_PACKET_BYTES)
    _regular_bytes(signature_path, "evidence signature", 64 * 1024)
    public_key = _regular_bytes(public_key_path, "release attestor public key", 64 * 1024)
    observed = hashlib.sha256(public_key).hexdigest()
    if observed != expected_public_key_sha256:
        raise QualificationError("public key does not match the external trust root")
    completed = runner(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(public_key_path),
            "-signature",
            str(signature_path),
            str(packet_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()[-1024:]
        raise QualificationError(f"detached signature verification failed: {message}")
    return observed


def qualification_result(
    packet_bytes: bytes,
    packet: dict[str, Any] | None,
    errors: list[str],
    current_main_sha: str,
) -> dict[str, Any]:
    image_digest = None
    if isinstance(packet, dict) and isinstance(packet.get("image"), dict):
        candidate = packet["image"].get("sha256")
        if isinstance(candidate, str) and SHA256_RE.fullmatch(candidate):
            image_digest = candidate
    return {
        "schema": RESULT_SCHEMA,
        "repository": REPOSITORY,
        "subject_main_sha": current_main_sha,
        "image_sha256": image_digest,
        "evidence_sha256": hashlib.sha256(packet_bytes).hexdigest(),
        "eligible_for_independent_promotion_review": not errors,
        "release_published_by_this_verifier": False,
        "external_facts_created_by_this_verifier": False,
        "verification_errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--expected-attestor-id", type=int, required=True)
    parser.add_argument("--expected-attestor-login", required=True)
    parser.add_argument("--current-main-sha", required=True)
    parser.add_argument("--now-unix", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packet_bytes = b""
    packet: dict[str, Any] | None = None
    errors: list[str] = []
    try:
        packet_bytes = _regular_bytes(args.evidence, "evidence packet", MAX_PACKET_BYTES)
        key_digest = verify_detached_signature(
            args.evidence,
            args.signature,
            args.public_key,
            args.expected_public_key_sha256,
        )
        packet = strict_json_bytes(packet_bytes)
        errors.extend(
            verify_packet(
                packet,
                current_main_sha=args.current_main_sha,
                signature_verified=True,
                public_key_sha256=key_digest,
                expected_attestor_id=args.expected_attestor_id,
                expected_attestor_login=args.expected_attestor_login,
                now_unix=args.now_unix,
            )
        )
    except (OSError, QualificationError) as error:
        errors.append(str(error))
    result = qualification_result(packet_bytes, packet, errors, args.current_main_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if errors:
        for error in errors:
            print(f"S12-RELEASE-QUALIFICATION: {error}", file=sys.stderr)
        return 1
    print(
        "S12 release evidence is eligible for independent promotion review; "
        "this verifier did not sign or publish"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
