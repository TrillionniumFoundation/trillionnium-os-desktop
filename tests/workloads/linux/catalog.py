#!/usr/bin/env python3
"""Validate the machine-readable A04 Linux workload contract.

This module does not execute workloads.  It binds every observed case to the
fixed Linux reference, records the argument vector and interface dependencies,
and checks that release facts are present before a run can be reported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "workload_catalog.json"
DEFAULT_REFERENCE = HERE / "baselines/linux-debian13-x86_64.json"

REQUIRED_INTERFACES = {
    "auxv", "mmap", "pthread_create", "futex", "AF_UNIX", "epoll", "flock",
    "fcntl_record_lock", "signal", "execve", "SQLite", "WAL", "eventfd",
    "timerfd", "SCM_RIGHTS", "PTHREAD_MUTEX_ROBUST", "NSS", "TLS", "Rust",
    "Tokio",
}


class CatalogError(ValueError):
    """Raised when the catalog/reference contract is incomplete or unsafe."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogError(f"JSON root must be an object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strings(value: Any, field: str, workload_id: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CatalogError(f"{workload_id}: {field} must be a string list")
    return value


def _string(value: Any, field: str, workload_id: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{workload_id}: {field} must be a non-empty string")
    return value


def validate(catalog: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    if catalog.get("schema") != 1:
        raise CatalogError("catalog schema must be 1")
    reference_name = _string(catalog.get("reference"), "reference", "catalog")
    if reference_name != "baselines/linux-debian13-x86_64.json":
        raise CatalogError("catalog reference must bind the pinned Linux baseline")
    workloads = catalog.get("workloads")
    cases = reference.get("cases")
    if not isinstance(workloads, list) or not workloads:
        raise CatalogError("catalog workloads must be a non-empty list")
    if not isinstance(cases, dict) or not cases:
        raise CatalogError("reference cases must be a non-empty object")
    seen: set[str] = set()
    interfaces: set[str] = set()
    by_class: dict[str, int] = {}
    for item in workloads:
        if not isinstance(item, dict):
            raise CatalogError("workload entries must be objects")
        workload_id = item.get("id")
        if not isinstance(workload_id, str) or not workload_id:
            raise CatalogError("workload id must be a non-empty string")
        if workload_id in seen:
            raise CatalogError(f"duplicate workload id: {workload_id}")
        seen.add(workload_id)
        if workload_id not in cases:
            raise CatalogError(f"{workload_id}: missing from Linux reference")
        workload_class = item.get("class")
        if workload_class not in {"elf", "python", "rust"}:
            raise CatalogError(f"{workload_id}: unsupported class {workload_class!r}")
        by_class[workload_class] = by_class.get(workload_class, 0) + 1
        if not isinstance(item.get("operation"), str) or not item["operation"]:
            raise CatalogError(f"{workload_id}: operation is required")
        _strings(item.get("command"), "command", workload_id)
        _strings(item.get("inputs"), "inputs", workload_id)
        item_interfaces = _strings(item.get("interfaces"), "interfaces", workload_id)
        interfaces.update(item_interfaces)
        release_keys = _strings(item.get("release_fact_keys"), "release_fact_keys", workload_id,
                                nonempty=False)
        expected = cases[workload_id]
        status = expected.get("status")
        if status not in {"pass", "fail", "not_run"}:
            raise CatalogError(f"{workload_id}: invalid reference status {status!r}")
        if status == "pass":
            facts = expected.get("facts")
            if not isinstance(facts, dict) or facts.get("ok") is not True:
                raise CatalogError(f"{workload_id}: passing reference lacks ok=true facts")
            missing = [key for key in release_keys if key not in facts]
            if missing:
                raise CatalogError(f"{workload_id}: release facts missing {missing}")
        elif workload_class == "rust" and not item.get("qualification_blocker"):
            raise CatalogError(f"{workload_id}: not-run Rust entry needs a blocker")
    missing_cases = sorted(set(cases) - seen)
    if missing_cases:
        raise CatalogError(f"catalog omits reference cases: {missing_cases}")
    missing_interfaces = sorted(REQUIRED_INTERFACES - interfaces)
    if missing_interfaces:
        raise CatalogError(f"catalog omits required interfaces: {missing_interfaces}")
    counts = {state: sum(value.get("status") == state for value in cases.values())
              for state in ("pass", "fail", "not_run")}
    return {
        "schema": 1,
        "profile": catalog.get("profile"),
        "catalog_workload_count": len(seen),
        "reference_case_count": len(cases),
        "reference_counts": counts,
        "workloads_by_class": dict(sorted(by_class.items())),
        "interfaces": sorted(interfaces),
        "required_interfaces": sorted(REQUIRED_INTERFACES),
    }


def validate_files(catalog_path: Path = DEFAULT_CATALOG,
                   reference_path: Path = DEFAULT_REFERENCE) -> dict[str, Any]:
    summary = validate(load_json(catalog_path), load_json(reference_path))
    summary.update({"catalog_sha256": sha256(catalog_path),
                    "reference_sha256": sha256(reference_path)})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        summary = validate_files(args.catalog, args.reference)
    except CatalogError as exc:
        parser.error(str(exc))
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists() or args.output.is_symlink():
            parser.error(f"refusing to overwrite {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(json.dumps({key: summary[key] for key in
                      ("catalog_sha256", "reference_sha256", "catalog_workload_count",
                       "reference_counts")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
