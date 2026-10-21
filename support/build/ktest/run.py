#!/usr/bin/env python3
"""Run real upstream OSDK kernel tests without editing upstream manifests."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

TOOLCHAIN = "nightly-2026-07-21"
CRATES = {"ostd": "ostd", "aster-core": "kernel/core"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RunnerInterrupted(BaseException):
    def __init__(self, signum):
        self.signum = signum
        super().__init__(signal.Signals(signum).name)


class Shutdown:
    """Handlers only latch requests, including while Popen publishes ownership."""
    def __init__(self):
        self.signum = None
        self.received = []
        self.output = None

    def remember(self, signum, _frame):
        if self.signum is None:
            self.signum = signum
        self.received.append(signal.Signals(signum).name)

    def check(self):
        if self.signum is not None:
            raise RunnerInterrupted(self.signum)


_active_shutdown = None


@contextmanager
def interruption_handlers():
    global _active_shutdown
    if _active_shutdown is not None:
        yield _active_shutdown
        return
    shutdown = Shutdown()
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    _active_shutdown = shutdown
    try:
        for number in previous:
            signal.signal(number, shutdown.remember)
        yield shutdown
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        _active_shutdown = None


class OwnedSession:
    """Sole reaper of a leader anchoring its original descendant process group.

    Descendants must stay in that group. WNOWAIT retains its identity through
    the last group signal. ECHILD permanently disarms numeric group signaling.
    """
    def __init__(self, command, *, cwd, env, output):
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                        stderr=subprocess.STDOUT, start_new_session=True)
        self.reaped = False
        self.external_reap = False
        self.status = None

    def exited(self):
        if self.reaped:
            return True
        if self.external_reap:
            raise RuntimeError("owned session externally reaped; group signals disarmed")
        try:
            return os.waitid(os.P_PID, self.process.pid,
                             os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
        except ChildProcessError as error:
            self.external_reap = True
            raise RuntimeError("owned session externally reaped; group signals disarmed") from error

    def stop(self, grace=0.05):
        # Reap only our direct leader. Grandchild exit is asynchronous; do not
        # infer it from /proc or send any numeric group signal after leader reap.
        if self.reaped or self.external_reap:
            return self.status
        self.exited()
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            time.sleep(min(.01, max(0, deadline - time.monotonic())))
        self.exited()
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.status = self.process.wait()
        self.reaped = True
        return self.status

    def wait(self, shutdown):
        while True:
            shutdown.check()
            if self.exited():
                return self.stop()
            time.sleep(.01)


def run(command, cwd, env, log):
    """Run one owned session and retain its completion/cleanup receipt."""
    with interruption_handlers() as shutdown:
        record = {"argv": command, "cwd": str(cwd), "raw_exit_code": None, "exit_code": None}
        receipt = log.with_name(log.name + ".command.json")
        receipt.write_text(json.dumps(record, indent=2) + "\n")
        started = time.monotonic()
        owned = None
        cleanup_failed = False
        try:
            with log.open("wb") as output:
                shutdown.check()
                owned = OwnedSession(command, cwd=cwd, env=env, output=output)
                shutdown.check()
                record["raw_exit_code"] = owned.wait(shutdown)
                shutdown.check()
        except BaseException as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            try:
                if owned is not None:
                    owned.stop()
            except BaseException as error:
                cleanup_failed = True
                record["cleanup_error"] = f"{type(error).__name__}: {error}"
                raise
            finally:
                if owned is not None:
                    record["raw_exit_code"] = owned.status
                    if owned.status is not None:
                        record["exit_code"] = owned.status if owned.status >= 0 else 128 - owned.status
                    record["group_cleanup"] = {"leader_pid": owned.process.pid,
                        "leader_exit_code": owned.status, "leader_reaped": owned.reaped,
                        "external_reap_disarmed": owned.external_reap,
                        "identity_anchor": "waitid WNOWAIT; final group signal before leader reap"}
                if shutdown.signum is not None:
                    record.update(interrupted_by=signal.Signals(shutdown.signum).name,
                                  received_signals=shutdown.received,
                                  exit_code=128 + shutdown.signum)
                record["duration_seconds"] = round(time.monotonic() - started, 3)
                receipt.write_text(json.dumps(record, indent=2) + "\n")
                if not cleanup_failed:
                    shutdown.check()
        return record["exit_code"]


def checked_output(command, cwd, env, log):
    code = run(command, cwd, env, log)
    contents = log.read_text()
    if code:
        raise subprocess.CalledProcessError(code, command, output=contents)
    return contents


def cancelled_result(output, shutdown):
    path = output / "result.json"
    result = json.loads(path.read_text()) if path.is_file() else {}
    result.update(passed=False, interrupted_by=signal.Signals(shutdown.signum).name,
                  received_signals=shutdown.received, exit_code=128 + shutdown.signum)
    path.write_text(json.dumps(result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crate", choices=CRATES, action="append")
    parser.add_argument("--output", type=Path, help="must not already exist")
    parser.add_argument("--test-name", help="optional complete test-path suffix, not a substring or crate selector")
    parser.add_argument("--skip-osdk-install", action="store_true",
                        help="deprecated compatibility option, ignored; each run installs its own source-bound private OSDK")
    args = parser.parse_args()
    with interruption_handlers() as shutdown:
        try:
            output = run_main(args, shutdown)
            shutdown.check()
        except BaseException:
            if shutdown.signum is None:
                raise
        finally:
            if shutdown.signum is not None and shutdown.output is not None:
                cancelled_result(shutdown.output, shutdown)
        if shutdown.signum is not None:
            return 128 + shutdown.signum
    print(f"PASS: real kernel-mode tests; evidence: {output}")
    return 0


def run_main(args, shutdown):
    if getattr(args, "skip_osdk_install", False):
        print("warning: --skip-osdk-install is deprecated and ignored; installing a fresh private "
              "source-bound OSDK; global or previous-output SDK reuse is unsupported", file=sys.stderr)
    if "CARGO_ENCODED_RUSTFLAGS" in os.environ:
        print("CARGO_ENCODED_RUSTFLAGS overrides mandatory OSDK kernel flags; "
              "unset CARGO_ENCODED_RUSTFLAGS and retry", file=sys.stderr)
        raise SystemExit(2)
    here = Path(__file__).resolve().parent
    project = here.parents[2]
    upstream = project / "kernel/asterinas"
    env = os.environ.copy()
    env["RUSTUP_TOOLCHAIN"] = TOOLCHAIN
    cargo_home = Path(env.get("CARGO_HOME", str(Path.home() / ".cargo")))
    env["PATH"] = str(cargo_home / "bin") + os.pathsep + env.get("PATH", "")
    env["CARGO_BUILD_JOBS"] = env.get("CARGO_BUILD_JOBS", "2")
    env["CARGO_NET_GIT_FETCH_WITH_CLI"] = "true"
    env["OSDK_LOCAL_DEV"] = "1"
    env["VDSO_LIBRARY_DIR"] = env.get("VDSO_LIBRARY_DIR", str(project / "support/build/out/linux-vdso"))
    env["NETDEV"], env["ENABLE_KVM"], env["OVMF"] = "none", "0", "off"
    env["SMP"], env["MEM"], env["CONSOLE"] = "1", "512M", "ttyS0"
    env["BOOT_METHOD"], env["BOOT_PROTOCOL"], env["QEMU_DISPLAY"] = "vmm-direct", "multiboot", "none"
    env.pop("OSDK_CARGO_LOCK", None)
    # Acquire the persistent shared inode before consuming any output path.
    with (project / "support/build/out-kernel.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another kernel build/test is using this workspace")
        shutdown.check()
        if args.output:
            output = args.output.resolve()
            output.mkdir(parents=True, exist_ok=False)
        else:
            parent_output = project / "support/build/out"
            parent_output.mkdir(parents=True, exist_ok=True)
            prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-ktest-")
            output = Path(tempfile.mkdtemp(prefix=prefix, dir=parent_output))
        shutdown.output = output
        result = {"passed": False, "crates": [], "toolchain": TOOLCHAIN,
                  "runner_sha256": digest(Path(__file__))}
        try:
            result["crates"] = run_locked(args, here, project, upstream, env, cargo_home, output)
            shutdown.check()
            result["passed"] = True
        except BaseException as error:
            result["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            result["command_receipts"] = sorted(str(path.relative_to(output))
                                                for path in output.rglob("*.command.json"))
            (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            if shutdown.signum is not None:
                cancelled_result(output, shutdown)
        shutdown.check()
    return output


def run_locked(args, here, project, upstream, env, cargo_home, output):
    verify = [sys.executable, "-I", str(project / "support/build/verify-source.py")]
    if run(verify, project, env, output / "source-inputs.json"):
        raise SystemExit(f"source verification failed; see {output}")
    commands = []
    osdk_install_root = output / "osdk"
    osdk_install_root.mkdir(mode=0o700)
    command = ["cargo", f"+{TOOLCHAIN}", "install", "--locked", "cargo-osdk", "--path", "osdk",
               "--root", str(osdk_install_root)]
    commands.append({"argv": command, "cwd": str(upstream)})
    (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
    if run(command, upstream, env, output / "osdk-install.log"):
        raise SystemExit(f"OSDK installation failed; see {output}")
    osdk = osdk_install_root / "bin/cargo-osdk"
    if not osdk.is_file() or osdk.is_symlink() or not os.access(osdk, os.X_OK):
        raise SystemExit("private source-built cargo-osdk is missing, linked, or not executable")
    version = checked_output(["rustc", f"+{TOOLCHAIN}", "-Vv"], project, env, output / "rustc-version.log")
    cargo_version = checked_output(["cargo", f"+{TOOLCHAIN}", "-Vv"], project, env, output / "cargo-version.log")
    environment = {"toolchain": TOOLCHAIN, "rustc": version, "cargo": cargo_version,
                   "git_head": checked_output(["git", "rev-parse", "HEAD"], project, env, output / "git-head.log").strip(),
                   "git_status": checked_output(["git", "status", "--short"], project, env, output / "git-status.log"),
                   "build_inputs_sha256": {
                       str(path.relative_to(project)): digest(path) for path in sorted([
                           upstream / "osdk/src/commands/build/mod.rs",
                           project / "support/build/verify-source.py",
                           project / "support/build/record-qemu.py",
                           *[path for path in here.rglob("*") if path.is_file() and "__pycache__" not in path.parts],
                       ])
                   },
                   "osdk_sha256": digest(osdk), "osdk_executable": str(osdk),
                   "osdk_install_root": str(osdk_install_root), "osdk_source_root": str(upstream.resolve()),
                   "vdso_sha256": digest(Path(env["VDSO_LIBRARY_DIR"]) / "vdso_x86_64.so"),
                   "cargo_build_jobs": env["CARGO_BUILD_JOBS"], "test_name": args.test_name,
                   "osdk_install_skip_requested": bool(getattr(args, "skip_osdk_install", False)),
                   "osdk_install_skipped": False}
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    env["CARGO_TARGET_DIR"] = str(upstream / "target")
    results = []
    for crate in args.crate or CRATES:
        target = output / crate
        target.mkdir()
        lock_path = here / "locks" / f"{crate}.Cargo.lock"
        if not lock_path.is_file():
            raise SystemExit("prepare the fixed test-base locks with ktest/prepare-locks.py first")
        env["OSDK_CARGO_LOCK"] = str(lock_path)
        env["A01_KTEST_GUESTS"] = str(target / "guests")
        env["A01_KTEST_CRATE"] = crate
        command = [str(osdk), "osdk", "test", "--release", "--boot-method=vmm-direct",
                   "--grub-boot-protocol=multiboot", "--qemu-exe=" + str(here / "record-qemu.py"),
                   "--kcmd-args=loglevel=error", "--kcmd-args=earlycon", "--kcmd-args=console=ttyS0"]
        if args.test_name:
            command.append(args.test_name)
        commands.append({"argv": command, "cwd": str(upstream / CRATES[crate]), "lock_sha256": digest(lock_path)})
        (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        code = run(command, upstream / CRATES[crate], env, target / "osdk-test.log")
        (target / "osdk-exit-code.txt").write_text(str(code) + "\n")
        generated = upstream / "target/osdk" / f"{crate}-test-base" / "Cargo.lock"
        if generated.exists():
            shutil.copyfile(generated, target / "generated.Cargo.lock")
        if code:
            raise SystemExit(f"{crate}: OSDK failed ({code}); retained evidence: {target}")
        if not generated.is_file() or digest(generated) != digest(lock_path):
            raise SystemExit(f"{crate}: generated lock differs from the fixed test-base lock")
        checker = [sys.executable, "-I", str(here / "check.py"), str(target / "guests"), "--crate", crate]
        if args.test_name:
            checker.append("--allow-filtered")
        if run(checker, project, env, target / "result.json"):
            raise SystemExit(f"{crate}: guest evidence rejected; see {target / 'result.json'}")
        results.append(json.loads((target / "result.json").read_text()))
    return results


if __name__ == "__main__":
    raise SystemExit(main())
