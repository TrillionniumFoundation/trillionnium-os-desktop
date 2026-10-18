#!/usr/bin/env python3
"""Opt-in clean kernel build with coherent compiler/component path projection."""
import argparse
import datetime
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import signal
import socket
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a01_repro_profile", HERE / "profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
spec = importlib.util.spec_from_file_location("a01_debug_lifecycle", HERE.parent / "debug/run.py")
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)
PROOF_CARGO_JOBS = 1


def owned_command(command, *, cwd, env, log, shutdown, pass_fds=()):
    """Reuse the debug runner's anchored group owner, including cancellation."""
    owned = None
    record = {"argv": command, "cwd": str(cwd), "pass_fds": list(pass_fds),
              "raw_exit_code": None, "exit_code": 1}
    try:
        with log.open("xb") as output:
            shutdown.check()
            owned = lifecycle.OwnedSession(command, cwd=cwd, env=env, output=output,
                                            pass_fds=pass_fds)
            shutdown.check()
            raw = owned.wait(float("inf"), shutdown)
            record["exit_code"] = raw if raw >= 0 else 128 - raw
    except lifecycle.ShutdownRequested:
        pass
    except BaseException as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        try:
            if owned is not None:
                owned.stop()
        except BaseException as error:
            record["cleanup_error"] = f"{type(error).__name__}: {error}"
            record["exit_code"] = 1
            raise
        finally:
            if owned is not None:
                record.update(raw_exit_code=owned.status, group_cleanup={
                    "leader_pid": owned.process.pid, "leader_reaped": owned.reaped,
                    "external_reap_disarmed": owned.external_reap,
                    "identity_anchor": "waitid WNOWAIT; final group signal before leader reap"})
            if shutdown.signum is not None:
                record.update(interrupted_by=signal.Signals(shutdown.signum).name,
                              received_signals=shutdown.received,
                              exit_code=128 + shutdown.signum)
            profile.exclusive(log.with_name(log.name + ".command.json"),
                              (json.dumps(record, indent=2) + "\n").encode())
    return record


def fixed_rustc_version(cargo_home, shutdown=None, output=None):
    # Match kernel.sh even when this launcher's caller defaults to stable.
    if shutdown is None:
        with lifecycle.interruption_handlers() as active, tempfile.TemporaryDirectory() as temporary:
            return fixed_rustc_version(cargo_home, active, Path(temporary))
    command = [str(cargo_home / "bin/rustc"), "+nightly-2026-07-21", "-vV"]
    log = output / "rustc-version.log"
    record = owned_command(command, cwd=HERE, env=os.environ.copy(), log=log, shutdown=shutdown)
    shutdown.check()
    if record["exit_code"]:
        raise subprocess.CalledProcessError(record["exit_code"], command, output=log.read_bytes())
    return log.read_bytes()


def proof_environment(environment):
    # Cargo always pipelines metadata. One active unit preserves the strict
    # completed-producer gate without accepting unfinished dependencies.
    return dict(environment, CARGO_BUILD_JOBS=str(PROOF_CARGO_JOBS))


def main():
    with lifecycle.interruption_handlers() as shutdown:
        try:
            status = repro_main(shutdown)
            return 128 + shutdown.signum if shutdown.signum is not None else status
        except lifecycle.ShutdownRequested as error:
            return 128 + error.signum
        except BaseException:
            shutdown.check()
            raise


def repro_main(shutdown):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--profile-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--action", choices=("kernel", "run_kernel"), default="run_kernel")
    args = parser.parse_args()
    checkout = profile.safe_root(args.checkout)
    source = profile.safe_root(checkout / "kernel/asterinas")
    root = profile.safe_root(args.profile_root)
    virtual = root / "virtual-asterinas"
    output = profile.safe_root(args.output)
    for left, right in ((source, root), (source, output), (root, output)):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError("source, profile and output must be disjoint directories")
    if "src/" in str(virtual) + "/" or "tests/" in str(virtual) + "/":
        raise ValueError("virtual prefix conflicts with the pinned runtime's first src/tests split")
    if (source / "target").exists() or (source / "target").is_symlink():
        raise ValueError("this proof profile requires an absent kernel target directory")
    if "CARGO_ENCODED_RUSTFLAGS" in os.environ or os.environ.get("RUSTC_WRAPPER") or os.environ.get("RUSTC_WORKSPACE_WRAPPER") or os.environ.get("RUSTFLAGS"):
        raise ValueError("unset inherited compiler flags/wrappers before this explicit profile")
    with lifecycle.workspace_lock(checkout) as workspace_descriptor:
        shutdown.check()
        return run_locked(args, checkout, source, root, virtual, output, shutdown, workspace_descriptor)


def run_locked(args, checkout, source, root, virtual, output, shutdown, workspace_descriptor):
    if (source / "target").exists() or (source / "target").is_symlink():
        raise ValueError("kernel target appeared while acquiring the workspace lock")
    raw_components, component_identity = profile.regular(source / "Components.toml")
    scripts = profile.code_hashes(HERE)
    owner = {"schema": profile.SCHEMA, "profile_root": str(root),
             "components_sha256": profile.digest(raw_components), "code_sha256": scripts,
             "embedded_builder": {"username": "a01-repro", "hostname": "a01-fixed-profile"}}
    created = False
    try:
        root.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        pass
    if created:
        virtual.mkdir(mode=0o700)
        profile.exclusive(virtual / "Components.toml", raw_components, 0o400)
        profile.materialize_helpers(root / "helpers", HERE)
        profile.exclusive(root / "lock", b"")
        profile.exclusive(root / "owner.json", (json.dumps(owner, sort_keys=True) + "\n").encode())
    existing = json.loads(profile.regular(root / "owner.json")[0])
    if existing != owner:
        raise ValueError("foreign or incompatible profile directory; refusing to overwrite")
    if profile.helper_hashes(root) != {name: scripts[name] for name in profile.HELPERS}:
        raise ValueError("profile executable closure differs from its recorded source")
    before_lock = profile.snapshot(root)
    lock = os.open(root / "lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if profile.identity(os.fstat(lock)) != before_lock["lock"]["identity"]:
            raise ValueError("profile lock inode changed")
        before = profile.snapshot(root)
        if before != before_lock:
            raise ValueError("profile changed while acquiring its lock")
        if (source / "target").exists() or (source / "target").is_symlink():
            raise ValueError("kernel target appeared while acquiring the profile lock")
        output.mkdir(mode=0o700)
        (output / "metadata").mkdir(mode=0o700)
        cargo_home = Path(os.environ.get("CARGO_HOME", str(Path.home() / ".cargo")))
        real_cargo = os.path.abspath(cargo_home / "bin/cargo")
        rustc_version = fixed_rustc_version(cargo_home, shutdown, output)
        lifecycle_path = Path(lifecycle.__file__).resolve()
        lifecycle_sha256 = lifecycle.sha256(lifecycle_path)
        policy = dict(owner, real_root=str(source), virtual_root=str(virtual),
                      output=str(output), real_cargo=real_cargo,
                      rustc_identity=profile.digest(rustc_version), rustc_version=rustc_version.decode(),
                      lifecycle_source={"path": str(lifecycle_path), "sha256": lifecycle_sha256},
                      execution={"cargo_build_jobs": PROOF_CARGO_JOBS,
                                 "caller_cargo_build_jobs": os.environ.get("CARGO_BUILD_JOBS"),
                                 "reason": "strict completed-producer provenance; Cargo metadata pipelining is always enabled"},
                      profile_snapshot=before, source_components_identity=component_identity,
                      target_absent_at_prelaunch=True, actual_host={"hostname": socket.gethostname(),
                      "username": pwd.getpwuid(os.getuid()).pw_name, "uid": os.getuid(),
                      "uname": list(os.uname())})
        policy_path = output / "policy.json"
        profile.exclusive(policy_path, (json.dumps(policy, indent=2) + "\n").encode())
        env = proof_environment(os.environ)
        env.update(A01_REPRO_POLICY=str(policy_path), RUSTC_WRAPPER=str(root / "helpers/rustc-wrapper.py"),
                   CARGO_TARGET_DIR=str(source / "target"), CARGO_INCREMENTAL="0",
                   RUSTFLAGS=f"--remap-path-prefix={source}={virtual}",
                   ASTER_BUILD_TIMESTAMP="Thu Jan  1 00:00:00 UTC 1970",
                   SOURCE_DATE_EPOCH="0", TZ="UTC", LC_ALL="C",
                   A01_KERNEL_WORKER="1", A01_KERNEL_LOCK_FD=str(workspace_descriptor),
                   A01_RUN_DIR=str(output / "kernel-run"))
        command = [str(checkout / "support/build/kernel.sh"), args.action]
        start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = owned_command(command, cwd=checkout, env=env, log=output / "console.log",
                               shutdown=shutdown, pass_fds=(workspace_descriptor,))
        custody_ok = profile.snapshot(root) == before
        source_ok = profile.regular(source / "Components.toml") == (raw_components, component_identity)
        code_ok = (profile.code_hashes(HERE) == scripts
                   and lifecycle.sha256(lifecycle_path) == lifecycle_sha256)
        status = result["exit_code"] if result["exit_code"] else (0 if custody_ok and source_ok and code_ok else 1)
        if shutdown.signum is not None:
            status = 128 + shutdown.signum
        receipt = {"command": command, "started": start,
                   "finished": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "child_returncode": result["raw_exit_code"], "returncode": status,
                   "owned_session_cleanup": result.get("group_cleanup"),
                   "profile_custody_unchanged": custody_ok, "source_components_unchanged": source_ok,
                   "profile_code_unchanged": code_ok,
                   "scope": "same-host opt-in path projection; independent-host reproduction not claimed"}
        if shutdown.signum is not None:
            receipt.update(interrupted_by=signal.Signals(shutdown.signum).name,
                           received_signals=shutdown.received)
        profile.exclusive(output / "result.json", (json.dumps(receipt, indent=2) + "\n").encode())
        return status
    finally:
        os.close(lock)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"reproduction profile refused: {error}", file=sys.stderr)
        raise SystemExit(2)
