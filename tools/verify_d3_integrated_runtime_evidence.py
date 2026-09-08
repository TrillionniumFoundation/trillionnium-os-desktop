#!/usr/bin/env python3
"""Fail-closed verifier for independently produced D3 integrated-image evidence.

The implementation is split into normally imported, reviewable modules. It
performs no network access, browser dispatch, repository mutation, or external
effect. Source self-tests validate the verifier only and never create promotion
authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable

from trusted_app_bundle import canonical_json
from d3_integrated_runtime_common import DEFAULT_CONTRACT, EvidenceError, load_json
from d3_integrated_runtime_fixture import build_source_fixture, run_self_test
from d3_integrated_runtime_verify import attestation_payload, verify_evidence

__all__ = [
    "DEFAULT_CONTRACT",
    "EvidenceError",
    "attestation_payload",
    "build_source_fixture",
    "load_json",
    "verify_evidence",
]


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--keyring", type=Path)
    parser.add_argument("--require-exact-main", action="store_true")
    parser.add_argument("--write-result", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if not args.self_test and (args.evidence is None or args.artifact_root is None):
        parser.error("--evidence and --artifact-root are required unless --self-test is used")
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = (
            run_self_test(args.contract)
            if args.self_test
            else verify_evidence(
                args.evidence,
                args.artifact_root,
                contract_path=args.contract,
                keyring_path=args.keyring,
                require_exact_main=args.require_exact_main,
            )
        )
    except EvidenceError as error:
        print(
            json.dumps(
                {"status": "FAIL", "reason": error.reason, "detail": error.detail},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    encoded = canonical_json(result)
    if args.write_result is not None:
        args.write_result.write_bytes(encoded)
    sys.stdout.buffer.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
