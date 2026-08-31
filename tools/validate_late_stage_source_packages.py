#!/usr/bin/env python3
"""Fail closed when the unified D4-D9 source-package inventory drifts."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/late-stage-source-packages.v1.json"
IMMUTABLE_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
EXPECTED = [
    ("D4-01", ["D3-01"], "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D3"),
    ("D5-01", ["D4-01"], "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D4"),
    ("D6-01", ["D5-01"], "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D5"),
    ("D7-01", ["D6-01"], "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D6"),
    ("D8-01", ["D7-01"], "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D7"),
    ("D9-01", ["D8-01"], "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D8"),
]


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def safe_path(value: object) -> Path:
    require(isinstance(value, str) and value, "package path must be a non-empty string")
    assert isinstance(value, str)
    require(not value.startswith("/") and "\\" not in value, f"unsafe package path {value!r}")
    parts = value.split("/")
    require(all(part not in {"", ".", ".."} for part in parts), f"unsafe package path {value!r}")
    path = ROOT.joinpath(*parts)
    current = ROOT
    for part in parts:
        current /= part
        metadata = os.lstat(current)
        require(not stat.S_ISLNK(metadata.st_mode), f"package path is a symlink: {value}")
    resolved = path.resolve(strict=True)
    resolved.relative_to(ROOT.resolve(strict=True))
    return resolved


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain an object")
    return value


def validate_workflow(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    require("permissions:\n  contents: read" in text, f"{path.name} is not read-only")
    require("persist-credentials: false" in text, f"{path.name} retains checkout credentials")
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("uses:"):
            continue
        action = line.split(":", 1)[1].strip().strip("\"'")
        if action.startswith("./"):
            continue
        require(IMMUTABLE_ACTION.fullmatch(action) is not None, f"{path.name} uses mutable action {action!r}")


def validate() -> dict[str, object]:
    manifest = load_json(MANIFEST)
    require(manifest.get("schema") == "trillionnium.desktop.late-stage-source-packages.v1", "late-stage schema drift")
    require(manifest.get("plan_revision") == "2026-08-29-d6", "late-stage plan revision drift")
    require(manifest.get("promotion_authoritative") is False, "source inventory claims promotion authority")
    packages = manifest.get("packages")
    require(isinstance(packages, list) and len(packages) == len(EXPECTED), "late-stage package count drift")
    assert isinstance(packages, list)

    observed: list[str] = []
    for entry, expected in zip(packages, EXPECTED, strict=True):
        require(isinstance(entry, dict), "late-stage package entry must be an object")
        assert isinstance(entry, dict)
        package_id, prerequisites, status = expected
        require(entry.get("id") == package_id, f"late-stage package order/id drift at {package_id}")
        require(entry.get("prerequisites") == prerequisites, f"{package_id} prerequisite drift")
        require(entry.get("status") == status, f"{package_id} status drift")
        require(entry.get("source_package_present") is True, f"{package_id} source package missing")
        require(entry.get("promotion_authoritative") is False, f"{package_id} claims promotion authority")
        observed.append(package_id)

        contract_path = safe_path(entry.get("contract"))
        contract = load_json(contract_path)
        require(contract.get("status") == status, f"{package_id} contract status disagrees with inventory")
        for key in ("workflows", "tools", "tests"):
            values = entry.get(key)
            require(isinstance(values, list) and values, f"{package_id} has no {key}")
            assert isinstance(values, list)
            for value in values:
                path = safe_path(value)
                if key == "workflows":
                    validate_workflow(path)

    require(len(observed) == len(set(observed)), "duplicate late-stage package IDs")
    ceiling = manifest.get("claim_ceiling")
    require(isinstance(ceiling, dict), "late-stage claim ceiling missing")
    assert isinstance(ceiling, dict)
    require(ceiling.get("source_reference_packages_only") is True, "source-only ceiling weakened")
    for key in ("D4_D7_product_runtime_integrated", "D8_physical_evidence_obtained", "D9_production_release_promoted"):
        require(ceiling.get(key) is False, f"late-stage inventory falsely claims {key}")
    external = manifest.get("external_non_synthesizable_requirements")
    require(isinstance(external, dict) and set(external) == {"D0T-03", "D8-01", "D9-01"}, "external blocker registry drift")

    unified = safe_path(".github/workflows/d4-d9-source-suite.yml").read_text(encoding="utf-8")
    require('branches:\n      - main\n      - "codex/**"' in unified, "unified suite does not cover main and codex candidates")
    return {
        "schema": "trillionnium.desktop.late-stage-source-validation.v1",
        "status": "PASS_SOURCE_INVENTORY",
        "packages": observed,
        "source_packages_present": True,
        "runtime_integration_claimed": False,
        "physical_evidence_claimed": False,
        "release_promotion_claimed": False,
        "promotion_authoritative": False,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"late-stage source-package validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
