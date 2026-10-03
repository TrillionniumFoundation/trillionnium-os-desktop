#!/usr/bin/env python3
"""Explicit v2 source profile: verify held inputs, then original fixed Cargo.

This entry does not run native cases or qualify installed/production artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys

try:
    from . import mozjs_authenticated_input as authenticated
    from . import build_mozjs_locked_native as original
except ImportError:
    import mozjs_authenticated_input as authenticated
    import build_mozjs_locked_native as original


def build_authenticated_native(upstream: Path, original_lock: Path, archive_path: Path, bundle_path: Path,
                               tool_path: Path, target_parent: Path, profile: str) -> dict:
    """Paths select bytes; actual verification is performed inside this workflow."""
    authenticated.load_manifest(); argv = original.compile_argv(profile)
    upstream, target_parent = upstream.absolute(), target_parent.absolute()
    # Both existing directory selectors must name their canonical path. Reject
    # lexical parent aliases before admitting inputs or creating any evidence.
    # This is a selector check, not custody against concurrent source mutation.
    for directory in (upstream, target_parent):
        if ".." in directory.parts or directory.resolve(strict=True) != directory or not directory.is_dir():
            raise ValueError("build directory selector is not a canonical existing directory")
    # Refuse all original MOZJS/cache/profile/wrapper overrides before any
    # verification or target allocation. No caller stdout/bool/token is accepted.
    original.profile_environment(dict(os.environ), "/proc/not-yet-admitted", target_parent)
    if target_parent == upstream or upstream in target_parent.parents:
        raise ValueError("new target must be outside prepared upstream")
    held = authenticated._admit_inputs(archive_path.absolute(), bundle_path.absolute(), tool_path.absolute())
    try:
        evidence = authenticated._new_directory(target_parent, "mozjs-authenticated-evidence-")
        # The original helper's native Git stderr is captured in this bounded
        # private child. Its original APIs/30-second Git bounds remain intact.
        # Paths are argv values, never Python source interpolation.
        prepared = evidence / "prepared-source"; prepared.mkdir(mode=0o700)
        code = ("import pathlib,sys;sys.path.insert(0,sys.argv[1]);"
                "from tools import build_mozjs_locked_native as b;"
                "b.verify_prepared(pathlib.Path(sys.argv[2]),pathlib.Path(sys.argv[3]),sys.argv[4])")
        prepare_argv = [sys.executable, "-c", code, str(authenticated.ROOT), str(upstream), str(original_lock.absolute()), profile]
        prepare_rc, _, _ = authenticated._run_verifier(held, prepare_argv, prepared, dict(os.environ))
        if prepare_rc != 0: raise ValueError("prepared source refused")
        verification = authenticated._authenticate(held, evidence)
        # This diagnostic verification result is not a proof argument or a
        # transferable approval. Retain the same objects for the actual child.
        target = authenticated._new_directory(target_parent, "mozjs-authenticated-empty-")
        paths = held.paths(); before = held.readback()
        environment = original.profile_environment(dict(os.environ), paths["archive"], target)
        cargo = evidence / "cargo"; cargo.mkdir(mode=0o700)
        rc, _, _ = authenticated._run_verifier(held, argv, cargo, environment,
                                               original.TIMEOUT_SECONDS, original.GRACE_SECONDS,
                                               output_limit=authenticated.MAX_CARGO_OUTPUT_BYTES,
                                               cwd=upstream)
        after = held.readback()
        if before != after: raise ValueError("authenticated build inputs changed")
        return {"schema": "trillionnium.mozjs-authenticated-native-source-candidate.v2", "profile": profile,
                "cargo_returncode": rc, "target_directory": str(target), "verification": verification,
                "held_inputs_after_group_ended": after, "actual_supplier_signature_verified": True,
                "actual_cargo_archive_consumption_proven": False, "native_cases_executed": False,
                "tool_artifact_attestation_verified": False, "installed_qualified": False, "production_ready": False}
    finally:
        # Original lifecycle owner retains the complete input set in its pending
        # collection when bounded group shutdown is unresolved. Do not close it.
        if not held._active: held.close()


def main() -> int:
    parser = authenticated._FixedArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(original.TARGETS), required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--original-lock", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--target-parent", type=Path, required=True)
    args = parser.parse_args()
    previous = signal.signal(signal.SIGTERM, original._cancel_from_signal)
    try:
        try:
            result = build_authenticated_native(args.upstream, args.original_lock, args.archive,
                                                args.bundle, args.tool, args.target_parent, args.profile)
        except (Exception, KeyboardInterrupt):
            print("MOZJS_AUTHENTICATED_INPUT_REFUSED", file=sys.stderr)
            return 1
    finally: signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True), file=sys.stderr)
    return 0 if result["cargo_returncode"] == 0 else 1


if __name__ == "__main__": raise SystemExit(main())
