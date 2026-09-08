#!/usr/bin/env python3
"""Stable import facade and source-evidence CLI for the D7 reference model.

Imports resolve to the hardened implementation module so tests, monkeypatches,
and callers share one set of module globals. Direct execution adds only the
bounded source-only evidence projection required by the D7 workflows.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import effect_reconciliation_reference_impl as _impl

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "recovery-update-reconciliation.v1.json"


def _source_evidence() -> dict[str, object]:
    result: dict[str, object] = dict(_impl.self_test())
    result.update(
        {
            "status": "PASS_SOURCE_REFERENCE_ONLY",
            "external_effect_executor_integrated": False,
            "external_effects_enabled": False,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()

    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"cannot load D7 contract: {error}") from error
    if contract.get("status") != "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D6":
        raise SystemExit("D7 contract status widened unexpectedly")

    payload = json.dumps(_source_evidence(), indent=2, sort_keys=True) + "\n"
    if args.write_result is not None:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Importers must receive the implementation module itself. This preserves
# monkeypatching of resource ceilings and avoids duplicate state or APIs.
sys.modules[__name__] = _impl
