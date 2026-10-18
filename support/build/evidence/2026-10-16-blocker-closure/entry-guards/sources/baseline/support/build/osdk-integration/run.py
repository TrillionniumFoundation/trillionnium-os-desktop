#!/usr/bin/env python3
"""Run the real upstream OSDK integration harness with a native TCG profile."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
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
import tomllib

TOOLCHAIN = "nightly-2026-07-21"
UNIX_PROFILE = "osdk-native-unix-v1"
TCP_PROFILE = "osdk-native-local-tcp-v1"
CAPTURE_PROFILE = "osdk-native-local-tcp-gdb-capture-v2"
FIXED_PATHS = {
    "commands::new::create_kernel_in_workspace": ["/tmp/kernel_workspace"],
    "commands::new::create_lib_in_workspace": ["/tmp/lib_workspace"],
    "commands::new::create_two_crates_in_workspace": ["/tmp/my_workspace"],
    "commands::run::coverage_feature::basic_coverage": ["/tmp/kernel_test_workspace/run_command"],
    "commands::run::qemu_gdb_feature::basic_debug": ["/tmp/kernel_test_workspace/run_command"],
    "commands::run::qemu_gdb_feature::vsc::vsc_launch_file": ["/tmp/kernel_test_workspace/run_command"],
    "examples_in_book::create_os_projects::create_a_kernel_project": ["/tmp/my_foo_os"],
    "examples_in_book::create_os_projects::create_a_library_project": ["/tmp/my_foo_module"],
    "examples_in_book::test_and_run_projects::create_and_run_kernel": ["/tmp/myos"],
    "examples_in_book::test_and_run_projects::create_and_test_library": ["/tmp/mylib"],
    "examples_in_book::work_in_workspace::work_in_workspace": ["/tmp/myworkspace"],
    "examples_in_book::write_a_kernel_in_100_lines::write_a_kernel_in_100_lines": ["/tmp/kernel_in_100_lines"],
}
VM_CASES = {
    "commands::run::basic::new_kernel_and_run": 1,
    "commands::run::coverage_feature::basic_coverage": 1,
    "commands::run::qemu_gdb_feature::basic_debug": 1,
    "commands::run::qemu_gdb_feature::vsc::vsc_launch_file": 1,
    "examples_in_book::test_and_run_projects::create_and_run_kernel": 1,
    "examples_in_book::test_and_run_projects::create_and_test_library": 1,
    "examples_in_book::work_in_workspace::work_in_workspace": 3,
    "examples_in_book::write_a_hypervisor_in_100_lines::write_a_hypervisor_in_100_lines": 1,
    "examples_in_book::write_a_kernel_in_100_lines::write_a_kernel_in_100_lines": 1,
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def external(data):
    return {(p["name"], p["version"], p["source"], p.get("checksum", ""))
            for p in tomllib.loads(data.decode())["package"] if p.get("source")}


def adapt_basic_debug_to_local_tcp(contents):
    """Change isolated debug transport/readiness while retaining assertions."""
    start = contents.index("    fn basic_debug() {")
    end = contents.index("    fn wait_for<T>(", start)
    original = contents[start:end]
    unix_address = '''        let unix_socket = {
            let path = Path::new(&workspace.os_dir()).join("qemu-gdb-sock");
            path.to_string_lossy().to_string()
        };'''
    tcp_address = '''        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let gdb_address = listener.local_addr().unwrap().to_string();
        drop(listener);'''
    unix_ready = 'Ok(Path::new(&sock).exists().then_some(()))'
    tcp_ready = '''let ready = std::env::var("A01_OSDK_GDB_READY")
                    .map_err(|error| error.to_string())?;
                Ok(Path::new(&ready).is_file().then_some(()))'''
    if original.count(unix_address) != 1 or original.count(unix_ready) != 1:
        raise SystemExit("basic-debug transport setup changed; refusing a broad test rewrite")
    adapted = original.replace(unix_address, tcp_address).replace("unix_socket", "gdb_address")
    adapted = adapted.replace(unix_ready, tcp_ready)
    contents = contents[:start] + adapted + contents[end:]
    vsc_ready = '''                let symbols = wait_for(&debugger_cancelled, || launch_symbol_file(&dir))?;
                gdb_continue_via(&addr, Some(&symbols))'''
    if contents.count(vsc_ready) != 1:
        raise SystemExit("VSCode debug readiness changed; refusing a broad test rewrite")
    vsc_owned_ready = '''                let symbols = wait_for(&debugger_cancelled, || launch_symbol_file(&dir))?;
                wait_for(&debugger_cancelled, || {
                    let ready = std::env::var("A01_OSDK_GDB_READY")
                        .map_err(|error| error.to_string())?;
                    Ok(Path::new(&ready).is_file().then_some(()))
                })?;
                gdb_continue_via(&addr, Some(&symbols))'''
    return contents.replace(vsc_ready, vsc_owned_ready)


def prepare_harness(upstream, output, cargo, env, local_tcp=False):
    """Adapt only scratch paths and the local-OSTD anchor, retaining assertions."""
    root = output / "harness"
    root.mkdir()
    tests = root / "tests"
    shutil.copytree(upstream / "osdk/tests", tests)
    # Preserve the helper's original relative include_str! without rewriting it.
    shutil.copyfile(upstream / "rust-toolchain.toml", output / "rust-toolchain.toml")
    # Upstream GDB/monitor UNIX sockets must fit Linux's 108-byte sun_path.
    # This root is atomically created and owned by this run; existing /tmp
    # examples are never touched.
    fixed = Path(tempfile.mkdtemp(prefix="a01oi-", dir="/tmp"))
    identity = fixed.stat()
    (output / "fixed-root.json").write_text(json.dumps({"path": str(fixed),
        "device": identity.st_dev, "inode": identity.st_ino}, indent=2) + "\n")
    changes = []
    for path in sorted(tests.rglob("*.rs")):
        original = path.read_text()
        adapted = original.replace('"/tmp', '"' + str(fixed))
        if path == tests / "util/mod.rs":
            if original.count('env!("CARGO_MANIFEST_DIR")') != 1:
                raise SystemExit("OSDK integration helper manifest anchor changed")
            adapted = adapted.replace('env!("CARGO_MANIFEST_DIR")', json.dumps(str(upstream / "osdk")))
        if local_tcp and path == tests / "commands/run.rs":
            adapted = adapt_basic_debug_to_local_tcp(adapted)
        if path == tests / "examples_in_book/write_a_kernel_in_100_lines.rs":
            original_dependency = 'toml::Value::String("0.1.0".to_string())'
            if adapted.count(original_dependency) != 1:
                raise SystemExit("kernel100 align_ext dependency expression changed")
            local = upstream / "ostd/libs/align_ext"
            if tomllib.loads((local / "Cargo.toml").read_text())["package"]["version"] != "0.1.0":
                raise SystemExit("fixed local align_ext version changed")
            local_dependency = ('toml::Value::Table(toml::Table::from_iter(['
                '("path".to_string(), toml::Value::String(' + json.dumps(str(local)) + '.to_string())),'
                '("version".to_string(), toml::Value::String("0.1.0".to_string()))]))')
            adapted = adapted.replace(original_dependency, local_dependency)
        if adapted != original:
            path.write_text(adapted)
            relative = str(path.relative_to(root))
            changes.extend(difflib.unified_diff(original.splitlines(True), adapted.splitlines(True),
                                              fromfile="original/" + relative, tofile="adapted/" + relative))
    (output / "harness-adaptation.patch").write_text("".join(changes))
    manifest = ('[workspace]\n\n[package]\nname = "a01-osdk-integration"\nversion = "0.0.0"\n'
                'edition = "2024"\n\n[dev-dependencies]\nassert_cmd = "2.0.13"\n'
                'tempfile = "3.14.0"\ntoml = { version = "0.8.8", features = ["preserve_order"] }\n'
                'serde_json = "1.0.111"\nshlex = "1.3.0"\n')
    (root / "Cargo.toml").write_text(manifest)
    seed = (upstream / "osdk/Cargo.lock").read_bytes()
    if hashlib.sha256(seed).hexdigest() != "99a21f72f6a9f1582553b34f06e80f86e539f38e62eab7a0847afd0906e75be3":
        raise SystemExit("fixed upstream OSDK harness seed lock differs")
    (root / "Cargo.lock").write_bytes(seed)
    normalize = [str(cargo), "metadata", "--offline", "--format-version=1",
                 "--filter-platform=x86_64-unknown-linux-gnu"]
    record = command(normalize, root, env, output / "harness-lock-normalize.log", 120)
    if record["raw_exit_code"]:
        raise SystemExit("isolated harness offline lock normalization failed")
    normalized = (root / "Cargo.lock").read_bytes()
    drift = sorted(external(normalized) - external(seed))
    (output / "harness-lock.json").write_text(json.dumps({
        "seed_sha256": hashlib.sha256(seed).hexdigest(),
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "external_drift": drift, "command": record}, indent=2) + "\n")
    if drift:
        raise SystemExit(f"isolated harness lock drift: {drift}")
    return root, fixed


class RunnerInterrupted(BaseException):
    def __init__(self, signum):
        self.signum = signum
        super().__init__(signal.Signals(signum).name)


class Shutdown:
    """Record asynchronous signals; raise only at owned-command checkpoints."""

    def __init__(self):
        self.signum = None
        self.received = []

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
    """Share a cooperative signal latch across the CLI and public command()."""
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
    """Keep the direct child unreaped until its remaining process group is stopped.

    This runner is the sole reaper and descendants must stay in this session's
    original process group. ECHILD disarms numeric group signals rather than
    risking a recycled process-group ID.
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
        try:
            return os.waitid(os.P_PID, self.process.pid,
                             os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
        except ChildProcessError as error:
            self.external_reap = True
            raise RuntimeError("owned session was externally reaped; group signals disarmed") from error

    def stop(self, grace=0.05):
        """Signal the anchored group and reap its direct leader only.

        Descendant exit after SIGKILL is asynchronous; this runner does not adopt
        or claim to reap grandchildren. No numeric group signal follows reap.
        """
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

    def wait(self, timeout, shutdown=None):
        deadline = time.monotonic() + timeout
        while True:
            if shutdown is not None:
                shutdown.check()
            if self.exited():
                return self.stop()
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.process.args, timeout)
            time.sleep(.01)


@contextmanager
def locked_output(lock_path, output):
    """A busy runner must not consume the caller's new evidence directory."""
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another integration runner is active")
        output.mkdir(parents=True, exist_ok=False)
        yield


def command(command, cwd, env, output, timeout):
    # Keep the existing public call signature, including for host-only callers.
    # A standalone call installs its latch before any child can be created.
    with interruption_handlers() as shutdown:
        return _command(command, cwd, env, output, timeout, shutdown)


def _command(command, cwd, env, output, timeout, shutdown):
    record = {"argv": command, "cwd": str(cwd), "raw_exit_code": None, "timed_out": False}
    output.with_suffix(".command.json").write_text(json.dumps(record, indent=2) + "\n")
    started = time.monotonic()
    owned = None
    try:
        with output.open("wb") as log:
            shutdown.check()
            owned = OwnedSession(command, cwd=cwd, env=env, output=log)
            # Handlers only remember requests, so Popen -> owner publication
            # cannot unwind before this finally block can find the child.
            shutdown.check()
            record["raw_exit_code"] = owned.wait(timeout, shutdown)
            shutdown.check()
    except subprocess.TimeoutExpired:
        record["timed_out"] = True
        record["raw_exit_code"] = 124
        record["timeout_cleanup"] = "SIGTERM and SIGKILL own process group before leader reap"
    except (RunnerInterrupted, KeyboardInterrupt) as error:
        number = error.signum if isinstance(error, RunnerInterrupted) else signal.SIGINT
        record["interrupted_by"] = signal.Signals(number).name
        record["raw_exit_code"] = 128 + number
        raise
    except BaseException as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        cleanup_failed = False
        try:
            if owned is not None:
                owned.stop()
        except BaseException as error:
            cleanup_failed = True
            record["cleanup_error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            if owned is not None:
                record["group_cleanup"] = {"leader_pid": owned.process.pid,
                    "leader_exit_code": owned.status, "leader_reaped": owned.reaped,
                    "external_reap_disarmed": owned.external_reap,
                    "identity_anchor": "waitid WNOWAIT until group signals precede leader reap"}
            if shutdown.signum is not None:
                record["interrupted_by"] = signal.Signals(shutdown.signum).name
                record["received_signals"] = shutdown.received
                record["raw_exit_code"] = 128 + shutdown.signum
            record["duration_seconds"] = round(time.monotonic() - started, 3)
            output.with_suffix(".command.json").write_text(json.dumps(record, indent=2) + "\n")
            # Also honor cancellation first received during normal cleanup;
            # repeated signals cannot skip stop() or its completion record.
            if not cleanup_failed:
                shutdown.check()
    return record


def checked_output(argv, cwd, env, output, timeout=30):
    record = command(argv, cwd, env, output, timeout)
    text = output.read_text()
    if record["raw_exit_code"]:
        raise subprocess.CalledProcessError(record["raw_exit_code"], argv, output=text)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="must not already exist")
    parser.add_argument("--case", action="append", help="exact upstream test name; default all 22")
    parser.add_argument("--case-timeout", type=int, default=900)
    parser.add_argument("--local-tcp", action="store_true",
                        help="explicit loopback TCP control profile; original UNIX default stays separate")
    parser.add_argument("--coverage-gdb", action="store_true",
                        help="explicit v2 coverage capture at the original poweroff breakpoint; requires --local-tcp")
    parser.add_argument("--target-dir", type=Path,
                        help="reuse this runner's previous independent Cargo target cache")
    args = parser.parse_args()
    if args.case_timeout < 1:
        raise SystemExit("--case-timeout must be positive")
    if args.coverage_gdb and not args.local_tcp:
        raise SystemExit("--coverage-gdb requires explicit --local-tcp")
    here = Path(__file__).resolve().parent
    project = here.parents[2]
    upstream = project / "kernel/asterinas"
    output = args.output.resolve()
    with locked_output(project / "support/build/out-osdk-integration.lock", output):
        return run_locked(args, here, project, upstream, output)


def run_locked(args, here, project, upstream, output):
    env = os.environ.copy()
    env["RUSTUP_TOOLCHAIN"] = TOOLCHAIN
    env["RUSTUP_AUTO_INSTALL"] = "0"
    profile_id = CAPTURE_PROFILE if args.coverage_gdb else TCP_PROFILE if args.local_tcp else UNIX_PROFILE
    env["A01_OSDK_LOCAL_TCP"] = "1" if args.local_tcp else "0"
    env["A01_OSDK_PROFILE"] = profile_id
    env["A01_OSDK_COVERAGE_GDB"] = "0"
    cargo_home = Path(env.get("CARGO_HOME", str(Path.home() / ".cargo")))
    rustup_home = Path(env.get("RUSTUP_HOME", str(Path.home() / ".rustup")))
    tool_bin = rustup_home / "toolchains" / (TOOLCHAIN + "-x86_64-unknown-linux-gnu") / "bin"
    real_cargo = tool_bin / "cargo"
    env["RUSTC"], env["RUSTDOC"] = str(tool_bin / "rustc"), str(tool_bin / "rustdoc")
    compiler = checked_output([env["RUSTC"], "-Vv"], upstream, env, output / "rustc-version.log")
    if "commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48" not in compiler:
        raise SystemExit("actual compiler does not match the fixed nightly-2026-07-21")
    env["PATH"] = str(cargo_home / "bin") + os.pathsep + env.get("PATH", "")
    env["CARGO_BUILD_JOBS"] = env.get("CARGO_BUILD_JOBS", "2")
    target_dir = args.target_dir.resolve() if args.target_dir else output / "target"
    if args.target_dir and (not target_dir.is_relative_to(project / "support/build/out")
                            or not (target_dir.parent / "harness-adaptation.patch").is_file()
                            or not (target_dir.parent / "harness-lock.json").is_file()):
        raise SystemExit("--target-dir must be a prior isolated integration runner cache")
    env["CARGO_TARGET_DIR"] = str(target_dir)
    env["OSDK_LOCAL_DEV"] = "1"
    env.pop("INTEL_TDX", None)
    env.pop("OSDK_CARGO_LOCK", None)
    commands = []
    harness_root, fixed_root = prepare_harness(upstream, output, real_cargo, env, args.local_tcp)
    production = [str(real_cargo), "build", "--locked", "--bin", "cargo-osdk"]
    commands.append(command(production, upstream / "osdk", env, output / "osdk-build.log", 600))
    if commands[-1]["raw_exit_code"]:
        raise SystemExit(f"original OSDK source build failed; see {output}")
    build = [str(real_cargo), "test", "--locked", "--test", "integration", "--no-run",
             "--message-format=json"]
    commands.append(command(build, harness_root, env, output / "harness-build.log", 600))
    if commands[-1]["raw_exit_code"]:
        raise SystemExit(f"integration harness build failed; see {output}")
    artifacts = []
    for line in (output / "harness-build.log").read_text().splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if value.get("reason") == "compiler-artifact" and value.get("executable") \
                and value.get("target", {}).get("name") == "integration":
            artifacts.append(Path(value["executable"]))
    if len(artifacts) != 1:
        raise SystemExit("could not identify a unique real integration harness")
    harness = artifacts[0]
    osdk = target_dir / "debug/cargo-osdk"
    if not harness.is_file() or not osdk.is_file():
        raise SystemExit("integration harness or real source-built cargo-osdk is missing")
    listed = checked_output([str(harness), "--list"], harness_root, env,
                            output / "upstream-test-list.txt")
    available = [line.removesuffix(": test") for line in listed.splitlines() if line.endswith(": test")]
    if len(available) != 22:
        raise SystemExit(f"upstream integration case count changed: {len(available)}")
    first = ["commands::run::qemu_gdb_feature::basic_debug",
             "commands::run::qemu_gdb_feature::vsc::vsc_launch_file"]
    selected = args.case or first + [case for case in available if case not in first]
    if len(set(selected)) != len(selected) or set(selected) - set(available):
        raise SystemExit("--case must select distinct exact upstream test names")
    shim_bin = output / "bin"
    shim_bin.mkdir()
    (shim_bin / "cargo").symlink_to(here / "cargo.py")
    env["PATH"] = str(shim_bin) + os.pathsep + env["PATH"]
    env["A01_REAL_CARGO"] = str(real_cargo)
    env["A01_REAL_OSDK"] = str(osdk)
    env["CARGO_BIN_EXE_cargo-osdk"] = str(here / "osdk.py")
    env["OSDK_CARGO_LOCK"] = str(upstream / "Cargo.lock")
    env["A01_OSDK_GUEST_TIMEOUT"] = str(min(args.case_timeout, 300))
    environment = {"schema": 1, "started_utc": datetime.now(timezone.utc).isoformat(),
                   "git_head": checked_output(["git", "rev-parse", "HEAD"], project, env,
                                               output / "git-head.log").strip(),
                   "git_status": checked_output(["git", "status", "--short"], project, env,
                                                 output / "git-status.log"),
                   "rustc": compiler,
                   "cargo": checked_output([str(real_cargo), "-Vv"], upstream, env,
                                            output / "cargo-version.log"),
                   "cargo_path": str(real_cargo), "cargo_sha256": digest(real_cargo),
                   "rustc_path": str(tool_bin / "rustc"), "rustc_sha256": digest(tool_bin / "rustc"),
                   "rustup_auto_install": "0", "isolated_fixed_root": str(fixed_root),
                   "profile_id": profile_id,
                   "control_transport": "loopback-tcp" if args.local_tcp else "upstream-unix",
                   "harness_path": str(harness), "harness_sha256": digest(harness),
                   "osdk_path": str(osdk), "osdk_sha256": digest(osdk),
                   "seed_lock_sha256": digest(upstream / "Cargo.lock"),
                   "runner_inputs_sha256": {str(p.relative_to(project)): digest(p)
                       for p in sorted(here.rglob("*")) if p.is_file() and "__pycache__" not in p.parts},
                   "test_inputs_sha256": {str(p.relative_to(upstream)): digest(p)
                       for p in sorted((upstream / "osdk/tests").rglob("*")) if p.is_file()},
                   "adapted_test_inputs_sha256": {str(p.relative_to(harness_root)): digest(p)
                       for p in sorted((harness_root / "tests").rglob("*")) if p.is_file()},
                   "source_inputs_sha256": {str(p.relative_to(upstream)): digest(p)
                       for p in sorted((upstream / "osdk/src").rglob("*")) if p.is_file()},
                   "local_align_ext_inputs_sha256": {str(p.relative_to(upstream)): digest(p)
                       for p in sorted((upstream / "ostd/libs/align_ext").rglob("*")) if p.is_file()},
                   "profile": "isolated upstream harness paths, native direct multiboot, q35 TCG max 1 vCPU 512 MiB",
                   "scope": "OSDK example kernels and tooling, not complete Asterinas kernel acceptance"}
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    results = []
    for index, case in enumerate(selected, 1):
        directory = output / f"case-{index:02d}"
        directory.mkdir()
        fixed = [Path(str(fixed_root) + value.removeprefix("/tmp"))
                 for value in FIXED_PATHS.get(case, [])]
        occupied = [str(path) for path in fixed if os.path.lexists(path)]
        report = {"name": case, "profile_id": profile_id, "fixed_paths": [str(p) for p in fixed],
                  "preexisting_paths": occupied, "status": "blocked" if occupied else "running"}
        (directory / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        if occupied:
            results.append(report)
            print(f"BLOCKED {case}: preexisting {occupied}", flush=True)
            continue
        work = directory / "work"
        work.mkdir()
        temp = fixed_root / f"case-{index:02d}-tmp"
        temp.mkdir()
        case_env = env.copy()
        case_env["TMPDIR"] = str(temp)
        case_env["A01_OSDK_CASE_OUTPUT"] = str(directory)
        case_env["A01_OSDK_GDB_READY"] = str(directory / "gdb-ready.json")
        case_env["A01_OSDK_ALLOWED_ROOTS"] = json.dumps([str(output), str(target_dir), str(fixed_root),
                                                       *[str(p) for p in fixed]])
        print(f"RUN {case}", flush=True)
        invoked = command([str(harness), "--exact", case, "--nocapture", "--test-threads=1"],
                          work, case_env, directory / "harness.log", args.case_timeout)
        report.update(invoked)
        text = (directory / "harness.log").read_text(errors="replace")
        report["status"] = "passed" if invoked["raw_exit_code"] == 0 \
            and "1 passed; 0 failed;" in text else "failed"
        report["soft_skips"] = []
        report["host_blockers"] = []
        guest_reports = []
        for path in sorted((directory / "guests").glob("guest-*/qemu.json")):
            guest = json.loads(path.read_text())
            serial = path.with_name("serial.log")
            content = serial.read_text(errors="replace") if serial.exists() else ""
            stderr = path.with_name("qemu-stderr.log")
            error_text = stderr.read_text(errors="replace") if stderr.is_file() else ""
            if "Operation not permitted" in error_text and "socket" in error_text:
                report["host_blockers"].append("host denies Unix socket creation (EPERM)")
            serial_valid = serial.is_file() and serial.stat().st_size > 0 \
                and len(guest.get("serial_logs", [])) == 1 \
                and guest["serial_logs"][0]["sha256"] == digest(serial)
            if "Error: VMX is not supported by the VM" in content:
                report["soft_skips"].append("VMX unavailable; hypervisor example accepted upstream fallback")
            guest_reports.append({"record": str(path.relative_to(output)),
                                  "raw_exit_code": guest["raw_exit_code"],
                                  "timed_out": guest["timed_out"],
                                  "wrapper_exit_code": guest.get("wrapper_exit_code"),
                                  "error": guest.get("error"), "serial_valid": serial_valid,
                                  "profile_id": guest.get("profile_id")})
        report["guests"] = guest_reports
        allowed_exit = (0, 33) if case == "commands::run::coverage_feature::basic_coverage" else (33,)
        if args.local_tcp and case == "commands::run::coverage_feature::basic_coverage":
            allowed_exit = (33,) if args.coverage_gdb else (0,)
        if len(guest_reports) != VM_CASES.get(case, 0) or any(
                guest["timed_out"] or guest["error"] or not guest["serial_valid"]
                or guest["profile_id"] != profile_id
                or guest["raw_exit_code"] not in allowed_exit
                or guest["wrapper_exit_code"] != guest["raw_exit_code"] for guest in guest_reports):
            report["status"] = "failed"
        coverage = directory / "coverage/result.json"
        if coverage.exists():
            report["coverage"] = json.loads(coverage.read_text())
            if not report["coverage"]["passed"]:
                report["status"] = "failed"
        elif case == "commands::run::coverage_feature::basic_coverage":
            report["status"] = "failed"
            report["coverage"] = {"passed": False, "error": "no validated coverage artifact"}
        report["cleanup"] = []
        # Only paths absent before this exact case are eligible; never touch preexisting paths.
        for path in fixed:
            if not os.path.lexists(path):
                continue
            stat = path.lstat()
            if path.is_symlink() or not path.is_dir():
                report["cleanup"].append({"path": str(path), "removed": False,
                                          "reason": "unexpected type; preserved"})
                report["status"] = "failed"
                continue
            shutil.rmtree(path)
            report["cleanup"].append({"path": str(path), "removed": True,
                                      "device": stat.st_dev, "inode": stat.st_ino})
        (directory / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        results.append(report)
        print(f"{report['status'].upper()} {case} ({invoked['duration_seconds']}s)", flush=True)
        (output / "result.json").write_text(json.dumps({"schema": 1, "cases": results}, indent=2) + "\n")
    summary = {"schema": 1, "profile_id": profile_id,
               "control_transport": environment["control_transport"],
               "profile": environment["profile"], "scope": environment["scope"],
               "available_cases": len(available), "selected_cases": len(selected),
               "passed": sum(r["status"] == "passed" for r in results),
               "failed": sum(r["status"] == "failed" for r in results),
               "blocked": sum(r["status"] == "blocked" for r in results),
               "soft_skip_count": sum(len(r.get("soft_skips", [])) for r in results),
               "host_blocked_cases": sum(bool(r.get("host_blockers")) for r in results),
               "cases": results, "build_commands": commands}
    (output / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
    ownership = json.loads((output / "fixed-root.json").read_text())
    if fixed_root.is_dir() and not fixed_root.is_symlink():
        identity = fixed_root.stat()
        if (identity.st_dev, identity.st_ino) == (ownership["device"], ownership["inode"]):
            shutil.rmtree(fixed_root)
            ownership["removed_after_run"] = True
            (output / "fixed-root.json").write_text(json.dumps(ownership, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in ("passed", "failed", "blocked", "soft_skip_count")}))
    return int(summary["failed"] != 0 or summary["blocked"] != 0)


if __name__ == "__main__":
    try:
        with interruption_handlers() as shutdown:
            status = main()
            shutdown.check()
            raise SystemExit(status)
    except RunnerInterrupted as error:
        print(f"integration runner interrupted by {signal.Signals(error.signum).name}; owned commands stopped",
              file=sys.stderr)
        raise SystemExit(128 + error.signum)
