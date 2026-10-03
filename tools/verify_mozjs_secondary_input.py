#!/usr/bin/env python3
"""Finite source/API correspondence; optional actual reviewed archive readback.

This command downloads nothing and executes no Cargo, native cases or artifact.
It establishes neither artifact attestation nor actual Cargo consumption.
"""
from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
import sys

try:
    from . import mozjs_secondary_input as archive
    from . import build_mozjs_locked_native as build
    from .artifact_evidence import load
    from .prepare_native_product_owner import read
except ImportError:
    import mozjs_secondary_input as archive
    import build_mozjs_locked_native as build
    from artifact_evidence import load
    from prepare_native_product_owner import read

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/mozjs-secondary-input.v1.json"
EXPECTED = {
    "schema": "trillionnium.mozjs-secondary-input-custody.v1",
    "status": "SOURCE_CANDIDATE_NOT_QUALIFIED",
    "manifest": "manifests/mozjs-secondary-input.v1.json",
    "reader": "existing ManagedSourceReader and owned _SourceDescriptor; no original API changes",
    "api": {"lease_archive": "(path: 'Path') -> 'SealedArchiveLease'",
            "SealedArchiveLease.readback": "(self) -> 'dict[str, object]'",
            "SealedArchiveLease.stable_path": "(self) -> 'str'",
            "SealedArchiveLease.close": "(self) -> 'None'",
            "build": "(upstream: 'Path', original_lock: 'Path', archive_path: 'Path', target_parent: 'Path', profile: 'str') -> 'dict'"},
    "admission": {"manifest": "entire typed reviewed profile only; duplicate JSON rejected",
                  "source": "bounded regular single-link file; no symlink component; exact size/digest; identity readback includes source mtime/ctime",
                  "snapshot": "Linux memfd; write/grow/shrink/seal four seals; retained object/mode/uid/gid/nlink/size and complete actual proc-path SHA readback",
                  "max_archive_bytes": 33554432, "max_manifest_bytes": 16384,
                  "memfd_timestamp": "failed writes can change timestamps; sealed byte proof uses object/size/seals/full digest"},
    "lifetime": {"public_use": "creator process and thread; no reentry, closed/foreign/replaced descriptor refused",
                 "path": "borrowed /proc/creator_pid/fd/n only while owner retained; not a transferable approval",
                 "release": "after fixed Cargo leader wait and ordinary process group termination; no retry of reused FD integer",
                 "shutdown_failure": "bounded wait failure retains process+lease custody in caller and cannot be qualified",
                 "native_opcode_windows_supervisor_death_escaping_groups": False},
    "build": {"entrypoint": "tools/build_mozjs_locked_native.py", "default_ci_changed": False,
              "profiles": {"native-owner": "trillionnium_product_owner", "approved-startup": "trillionnium_approved_connected"},
              "no_run": True, "locked": True, "cargo_profile": "checked-release",
              "toolchain": "1.97.1", "features": "bundled,js_jit", "default_features": False,
              "new_target": "exclusive initially empty per invocation, outside upstream, no existing cache",
              "timeout_seconds": 10800, "termination_grace_seconds": 5,
              "override_refusal": "all MOZJS_*; Cargo features/profile/target/build overrides; rustflags/wrappers/toolchain/incremental conflicts",
              "upstream_semantics": "MOZJS_ARCHIVE tries URL base first then path fallback; cached OUT_DIR archive can override env; fresh target required",
              "actual_archive_consumption_proven": False},
    "preservation": {"old_native_four_approved_two_cases": True, "original_case_deadlines": True,
                     "all_original_source_API_Cargo_PIN_CI": True},
    "claims": {"source_custody_only": True, "official_API_digest_is_attestation": False,
               "signature_trust_minted": False, "upstream_nonzero_status_fault_injection": False,
               "actual_native_build_qualified": False, "human_approval": False,
               "installed_qualified": False, "production_ready": False},
}


def check() -> dict:
    archive.load_manifest()
    actual = load(ROOT / CONTRACT)
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(EXPECTED, sort_keys=True):
        raise ValueError("mozjs custody contract differs")
    apis = {"lease_archive": archive.lease_archive, "SealedArchiveLease.readback": archive.SealedArchiveLease.readback,
            "SealedArchiveLease.stable_path": archive.SealedArchiveLease.stable_path,
            "SealedArchiveLease.close": archive.SealedArchiveLease.close, "build": build.build}
    if {name: str(inspect.signature(value)) for name, value in apis.items()} != EXPECTED["api"]:
        raise ValueError("mozjs custody public API differs")
    if build.TARGETS != EXPECTED["build"]["profiles"] or build.TIMEOUT_SECONDS != 10800 or build.GRACE_SECONDS != 5:
        raise ValueError("explicit compile profile differs")
    document = read(ROOT / "docs/architecture/MOZJS_SECONDARY_INPUT.md").decode("utf-8", "strict")
    for marker in [CONTRACT, archive.MANIFEST, "MOZJS_ARCHIVE", "19381534", "527403045",
                   "attestation", "static", "incomplete", "10800", "32 MiB", "initially empty"]:
        if marker not in document: raise ValueError("mozjs source documentation differs")
    return {"status": "PASS_SOURCE_API_INPUT_CORRESPONDENCE_ONLY", "artifact_attestation": False,
            "actual_cargo_archive_consumption_proven": False, "actual_native_cases_executed": False,
            "installed_qualified": False, "production_ready": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    try:
        result = check()
        if args.archive is not None:
            with archive.lease_archive(args.archive) as lease: result["actual_sealed_archive_readback"] = lease.readback()
    except (Exception, KeyboardInterrupt):
        print("mozjs reviewed secondary input refused", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
