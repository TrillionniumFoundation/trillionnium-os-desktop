#!/usr/bin/env python3
"""Explicit source-candidate native compile with one reviewed secondary input.

No original CI lane is changed. This launcher does not run native cases or
establish that upstream actually consumed the archive; that needs later traces.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import tomllib

try:
    from . import mozjs_secondary_input as archive
    from . import prepare_native_product_owner as native
    from . import prepare_approved_native_startup as approved
except ImportError:
    import mozjs_secondary_input as archive
    import prepare_native_product_owner as native
    import prepare_approved_native_startup as approved

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"native-owner": "trillionnium_product_owner", "approved-startup": "trillionnium_approved_connected"}
TIMEOUT_SECONDS = 10800
GRACE_SECONDS = 5
# A failed bounded shutdown retains input custody in a long-lived caller. It
# cannot be promoted to successful execution. Process death/SIGKILL of this
# supervisor and children that deliberately escape its group are not covered.
_PENDING_SHUTDOWNS: list[_BuildProcess] = []


def profile_environment(inherited: dict[str, str], path: str, target: Path) -> dict[str, str]:
    """Refuse inherited selectors rather than silently overwrite their meaning."""
    blocked = {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTC", "RUSTDOC"}
    for key, value in inherited.items():
        if key.startswith(("MOZJS_", "CARGO_FEATURE_", "CARGO_PROFILE_", "CARGO_TARGET_")) or key in blocked:
            raise ValueError("inherited environment overrides explicit mozjs profile")
        if key.startswith("CARGO_BUILD_") and (key != "CARGO_BUILD_JOBS" or value != "2"):
            raise ValueError("inherited Cargo build configuration overrides profile")
        if key in {"RUSTUP_TOOLCHAIN", "CARGO_INCREMENTAL", "RUST_BACKTRACE"} and value != {"RUSTUP_TOOLCHAIN": "1.97.1", "CARGO_INCREMENTAL": "0", "RUST_BACKTRACE": "1"}[key]:
            raise ValueError("inherited native build selection overrides profile")
    result = dict(inherited)
    result.update(MOZJS_ARCHIVE=path, CARGO_TARGET_DIR=str(target), RUSTUP_TOOLCHAIN="1.97.1",
                  CARGO_INCREMENTAL="0", CARGO_BUILD_JOBS="2", RUST_BACKTRACE="1")
    return result


def compile_argv(profile: str) -> list[str]:
    if profile not in TARGETS:
        raise ValueError("unknown reviewed mozjs native profile")
    return ["cargo", "test", "--locked", "--profile", "checked-release", "-p", "servo",
            "--no-default-features", "--features", "bundled,js_jit", "--test", TARGETS[profile],
            "--no-run", "--message-format=json"]


def verify_prepared(upstream: Path, original_lock: Path, profile: str) -> None:
    """Read the prepared graph; never assemble or modify an upstream checkout."""
    compile_argv(profile)
    if native.git(upstream, "rev-parse", "HEAD") != native.PIN:
        raise ValueError("prepared source differs from exact Servo PIN")
    native.verify_format_config(upstream, ROOT)
    native.verify_lock(original_lock, upstream / "Cargo.lock", approved_startup=profile == "approved-startup")
    for path in ["components/servo/tests/common/mod.rs"]:
        if native.digest(native.read(upstream / path)) != native.PIN_FILES[path]:
            raise ValueError("original native API source differs from PIN")
    sources = dict(native.SOURCES)
    if profile == "approved-startup": sources.update(approved.SOURCES)
    for source, destination in sources.items():
        if native.read(ROOT / source) != native.read(upstream / destination):
            raise ValueError("prepared native target source differs from reviewed input")
    channel = tomllib.loads(native.read(upstream / "rust-toolchain.toml").decode())["toolchain"]["channel"]
    if channel != "1.97.1": raise ValueError("prepared toolchain differs")
    original_manifest = subprocess.check_output(["git", "-C", str(upstream), "show", native.PIN + ":components/servo/Cargo.toml"], timeout=30)
    if native.digest(original_manifest) != native.PIN_FILES["components/servo/Cargo.toml"]:
        raise ValueError("original Servo manifest differs from reviewed PIN")
    extra = "\n# Explicit immutable/read-only consumer qualification graph; no installed activation.\n"
    for name, relative in native.DEPS.items():
        extra += f"\n[dev-dependencies.{name}]\npath = {json.dumps(str(ROOT / relative))}\n"
    extra += '\n[[test]]\nname = "trillionnium_product_owner"\npath = "tests/trillionnium_product_owner.rs"\n'
    expected_manifest = original_manifest + extra.encode()
    if profile == "approved-startup": expected_manifest += approved.TARGET
    actual_manifest = native.read(upstream / "components/servo/Cargo.toml")
    if actual_manifest != expected_manifest:
        raise ValueError("whole prepared Servo manifest differs from reviewed assembly")
    manifest = tomllib.loads(actual_manifest.decode())
    matches = [item for item in manifest.get("test", []) if item.get("name") == TARGETS[profile]]
    expected = {"name": TARGETS[profile], "path": "tests/" + TARGETS[profile] + ".rs"}
    if profile == "approved-startup": expected["harness"] = False
    if matches != [expected]: raise ValueError("prepared target configuration differs")


def _group_exists(pid: int) -> bool:
    try: os.killpg(pid, 0)
    except ProcessLookupError: return False
    return True


class _BuildProcess:
    """Own the Popen object before initialization can acquire a child."""
    def __init__(self, lease: archive.SealedArchiveLease):
        self.lease = lease
        self.process = subprocess.Popen.__new__(subprocess.Popen)
        self.started = False
        self.stopped = False

    def start(self, argv: list[str], cwd: Path, environment: dict[str, str]) -> None:
        self.process.__init__(argv, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                              start_new_session=True, close_fds=True)
        self.started = True

    def stop(self, deadline: float, grace: float) -> None:
        # __init__ may have acquired a PID before a caller-side interruption.
        pid = getattr(self.process, "pid", None)
        if pid is None:
            self.stopped = True
            return
        failure = None
        try:
            if _group_exists(pid):
                try: os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError: pass
                end = min(deadline, time.monotonic() + grace)
                while _group_exists(pid) and time.monotonic() < end:
                    try: self.process.wait(timeout=min(0.05, max(0.001, end - time.monotonic())))
                    except subprocess.TimeoutExpired: pass
                    time.sleep(min(0.01, max(0, end - time.monotonic())))
        except BaseException as error:
            failure = error
        finally:
            if _group_exists(pid):
                try: os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError: pass
            # Never leave a launched Cargo leader unreaped on a normal failure.
            self.process.wait(timeout=max(0.001, deadline - time.monotonic()))
            while _group_exists(pid) and time.monotonic() < deadline:
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
            self.stopped = not _group_exists(pid)
            if not self.stopped:
                raise RuntimeError("native build process group termination remains unresolved")
        if failure is not None: raise failure


def _run_with_lease(lease: archive.SealedArchiveLease, argv: list[str], cwd: Path,
                    environment: dict[str, str], timeout: float, grace: float) -> int:
    """Private host-test process primitive; public build always uses fixed Cargo."""
    if timeout <= 2 * grace or grace <= 0: raise ValueError("invalid bounded process lifecycle")
    lease.readback(); lease._creator(); owner = _BuildProcess(lease)
    deadline = time.monotonic() + timeout
    try:
        lease._active = True
        owner.start(argv, cwd, environment)
        return owner.process.wait(timeout=max(0.001, deadline - 2 * grace - time.monotonic()))
    finally:
        try:
            owner.stop(min(deadline, time.monotonic() + 2 * grace), grace)
        finally:
            if owner.stopped:
                lease._active = False
            else:
                # Retain the exact archive after a bounded shutdown failure;
                # neither an exception nor a public close discards its custody.
                _PENDING_SHUTDOWNS.append(owner)


def build(upstream: Path, original_lock: Path, archive_path: Path, target_parent: Path, profile: str) -> dict:
    archive.load_manifest()
    argv = compile_argv(profile)
    upstream = upstream.absolute(); target_parent = target_parent.absolute()
    # Refuse overrides before reading a large archive or creating a build tree.
    profile_environment(dict(os.environ), "/unused-reviewed-input", Path("/unused-fresh-target"))
    verify_prepared(upstream, original_lock, profile)
    for path in (target_parent, *target_parent.parents):
        if path.is_symlink(): raise ValueError("target parent has a symlink component")
    if not target_parent.is_dir(): raise ValueError("target parent is absent")
    if target_parent == upstream or upstream in target_parent.parents:
        raise ValueError("new target must be outside the prepared upstream checkout")
    with archive.lease_archive(archive_path) as lease:
        target = Path(tempfile.mkdtemp(prefix="mozjs-reviewed-empty-", dir=target_parent))
        if list(target.iterdir()): raise ValueError("new target directory was not initially empty")
        path = lease.stable_path(); environment = profile_environment(dict(os.environ), path, target)
        result = _run_with_lease(lease, argv, upstream, environment, TIMEOUT_SECONDS, GRACE_SECONDS)
        # Group stop was confirmed before readback/lease release, including a
        # nonzero leader exit or a lingering ordinary child.
        readback = lease.readback()
        return {"schema": "trillionnium.mozjs-locked-native-source-candidate.v1", "profile": profile,
                "cargo_returncode": result, "target_directory": str(target), "archive": readback,
                "actual_cargo_archive_consumption_proven": False, "native_cases_executed": False,
                "artifact_attestation": False, "installed_qualified": False, "production_ready": False}


def _cancel_from_signal(signum, frame) -> None:
    raise KeyboardInterrupt("source-candidate build cancellation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(TARGETS), required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--original-lock", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--target-parent", type=Path, required=True)
    args = parser.parse_args()
    previous_term = signal.signal(signal.SIGTERM, _cancel_from_signal)
    try:
        try:
            result = build(args.upstream, args.original_lock, args.archive, args.target_parent, args.profile)
        except (Exception, KeyboardInterrupt):
            print("mozjs source-candidate compile refused or failed; no qualification", file=sys.stderr)
            return 1
    finally:
        signal.signal(signal.SIGTERM, previous_term)
    print(json.dumps(result, sort_keys=True), file=sys.stderr)
    return 0 if result["cargo_returncode"] == 0 else 1


if __name__ == "__main__": raise SystemExit(main())
