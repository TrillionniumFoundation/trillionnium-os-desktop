#!/usr/bin/env python3
"""Preflight, or explicitly build and probe the unchanged fixed original Agentd.

Default mode reads source/resources and never downloads, builds or launches a
daemon. --execute needs a new work directory and adequate disk. A nonzero or
blocked result never becomes an acceptance pass. See ORIGINAL_AGENTD.md.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import tempfile
import time
import tomllib


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PIN = "f8c9419df6ddeb36ff8b522a50219981fb8d9345"
UPSTREAM_TOOLCHAIN = "1.95.0"
OBSERVER_TOOLCHAIN = "1.88.0"
MIN_FREE_BYTES = 8 * 1024**3  # Conservative preflight estimate, not measured size.
RUNNER_NAME = "hepta-original-observer-probe"
GROUP_GRACE_SECONDS = 3.0
CHILD_REAP_SECONDS = 3.0
EXPECTED_CHECKS = [
    "original_starting", "original_running", "bounded_capabilities_events",
    "missing_run_read", "same_process_draining", "original_restart",
    "old_spawn_rejected", "controlled_stop",
]


class GateError(Exception):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(source, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(source), *arguments], text=True,
        stderr=subprocess.PIPE, timeout=30,
    ).strip()


def verify_source(source):
    if git(source, "rev-parse", "HEAD") != PIN:
        raise GateError("upstream_commit_mismatch")
    if git(source, "status", "--porcelain=v1", "--untracked-files=all"):
        raise GateError("upstream_checkout_is_not_clean")
    manifest = json.loads((ROOT / "services/hepta-os/UPSTREAM_CONTRACT.json").read_text())
    for entry in manifest["files"]:
        if sha256(source / entry["path"]) != entry["sha256"]:
            raise GateError("upstream_reviewed_content_mismatch")
    toolchain = tomllib.loads((source / "codex-rs/rust-toolchain.toml").read_text())
    if toolchain["toolchain"]["channel"] != UPSTREAM_TOOLCHAIN:
        raise GateError("upstream_toolchain_mismatch")
    package = tomllib.loads((source / "codex-rs/hepta-agentd/Cargo.toml").read_text())
    if package["package"]["name"] != "codex-hepta-agentd":
        raise GateError("upstream_package_mismatch")
    return {
        "commit": PIN, "tree": git(source, "rev-parse", "HEAD^{tree}"),
        "cargo_lock_sha256": sha256(source / "codex-rs/Cargo.lock"),
        "clean_checkout": True,
    }


def toml_value(value):
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(json.dumps(key) + "=" + toml_value(item) for key, item in value.items()) + "}"
    if isinstance(value, (int, float)):
        return str(value)
    raise GateError("unsupported_upstream_manifest_value")


def prepare_runner(source, destination):
    """Link original libraries; rebase upstream patches without editing them."""
    workspace = source / "codex-rs"
    upstream = tomllib.loads((workspace / "Cargo.toml").read_text())
    resolver = upstream["workspace"].get("resolver")
    if resolver not in ("1", "2", "3"):
        raise GateError("upstream_explicit_resolver_required")
    destination.mkdir(mode=0o700)
    (destination / "src").mkdir(mode=0o700)
    lines = [
        "[package]", f'name="{RUNNER_NAME}"', 'version="0.0.0"',
        'edition="2024"', "publish=false", "[workspace]",
        # This external root cannot inherit the original workspace setting.
        # Keep its resolver explicit; the package edition is not a substitute.
        "resolver=" + toml_value(resolver), "[dependencies]",
    ]
    for crate in ["hepta-contracts", "hepta-fleet", "hepta-paths", "hepta-supervisor"]:
        dependency = {"path": str(workspace / crate)}
        if crate == "hepta-supervisor":
            dependency["default-features"] = False
        lines.append(f'"codex-{crate}"=' + toml_value(dependency))
    lines.append("serde_json=" + toml_value(upstream["workspace"]["dependencies"]["serde_json"]))
    for registry, patches in upstream.get("patch", {}).items():
        lines.append("[patch." + json.dumps(registry) + "]")
        for name, original in patches.items():
            patch = original.copy()
            if "path" in patch:
                patch["path"] = str((workspace / patch["path"]).resolve(strict=True))
            lines.append(json.dumps(name) + "=" + toml_value(patch))
    for profile in ["dev", "dev-small"]:
        lines.append("[profile." + profile + "]")
        for key, value in upstream["profile"][profile].items():
            lines.append(json.dumps(key) + "=" + toml_value(value))
    (destination / "Cargo.toml").write_text("\n".join(lines) + "\n")
    shutil.copyfile(HERE / "original_agentd_probe.rs", destination / "src/main.rs")
    # Cargo adds the external probe package/prunes unused entries. Shared
    # dependencies must retain identities from the original seed lock.
    shutil.copyfile(workspace / "Cargo.lock", destination / "Cargo.lock")


def verify_runner_lock(source, runner):
    def packages(path):
        return {
            (item["name"], item["version"], item.get("source"), item.get("checksum"))
            for item in tomllib.loads(path.read_text())["package"]
        }
    original = packages(source / "codex-rs/Cargo.lock")
    resolved = packages(runner / "Cargo.lock")
    extra = {item for item in resolved - original if item[0] != RUNNER_NAME}
    if extra:
        raise GateError("probe_dependency_identity_drifted_from_original_lock")


def build_environment(target):
    # Keep only tool/cache/proxy inputs, never inherited provider/authbus flags,
    # RUSTFLAGS, custom compilers, credential variables or application config.
    environment = {
        key: os.environ[key] for key in [
            "PATH", "CARGO_HOME", "RUSTUP_HOME", "HTTP_PROXY", "HTTPS_PROXY",
            "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR",
        ] if key in os.environ
    }
    environment.update({
        "CARGO_TARGET_DIR": str(target), "CARGO_INCREMENTAL": "0",
        "CARGO_BUILD_JOBS": "1", "LANG": "C.UTF-8",
    })
    return environment


def child_anchor_available():
    # Standalone, sole-reaper contract: no ignored/custom SIGCHLD disposition,
    # native SA_NOCLDWAIT configuration, child watcher or competing waitpid.
    return (
        platform.system() == "Linux"
        and all(hasattr(os, name) for name in ["waitid", "WNOWAIT", "WEXITED", "WNOHANG", "P_PID", "killpg"])
        and signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL
    )


class ChildGroup:
    """Pin this child/session leader until every group signal is finished.

    WNOWAIT retains an exited leader as our waitable child, preventing its
    numeric PID/PGID from being recycled. Do not use Popen.wait/poll/kill before
    disarming group signals. ECHILD permanently revokes this object's anchor;
    even a later valid-looking wait result must never re-arm it.
    """

    def __init__(self, process):
        self.process = process
        self.armed = True

    def observe_exit(self):
        if not self.armed:
            raise GateError("child_identity_lost")
        try:
            status = os.waitid(
                os.P_PID, self.process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG,
            )
        except ChildProcessError:
            self.armed = False
            raise GateError("child_identity_lost") from None
        except OSError:
            self.armed = False
            raise GateError("child_anchor_unavailable") from None
        if status is not None and status.si_pid != self.process.pid:
            self.armed = False
            raise GateError("child_identity_lost")
        return status

    def wait_exit(self, timeout_seconds):
        deadline = time.monotonic() + timeout_seconds
        while True:
            status = self.observe_exit()
            if status is not None:
                return status
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(self.process.args, timeout_seconds)
            time.sleep(min(0.01, remaining))

    def signal_group(self, signum):
        self.observe_exit()  # Re-check immediately before each group signal.
        try:
            os.killpg(self.process.pid, signum)
        except ProcessLookupError:
            return False
        return True

    def reap(self):
        self.observe_exit()
        # There will be no more PID/PGID signals, even if reaping later fails.
        self.armed = False
        deadline = time.monotonic() + CHILD_REAP_SECONDS
        while True:
            try:
                pid, status = os.waitpid(self.process.pid, os.WNOHANG)
            except ChildProcessError:
                # Popen.wait() maps ECHILD to success in some cases. Use the
                # actual kernel result so a competing reaper cannot green it.
                raise GateError("child_identity_lost") from None
            if pid == self.process.pid:
                code = os.waitstatus_to_exitcode(status)
                self.process.returncode = code
                return code
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GateError("child_cleanup_incomplete")
            time.sleep(min(0.01, remaining))


def bounded_command(command, cwd, environment, log_path, timeout_seconds):
    if not child_anchor_available():
        raise GateError("waitable_child_anchor_required_before_spawn")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise GateError("positive_finite_command_deadline_required")
    with log_path.open("xb") as log:
        process = subprocess.Popen(
            command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        group = ChildGroup(process)
        try:
            status = group.wait_exit(timeout_seconds)
        except subprocess.TimeoutExpired:
            terminate_group(group)
            raise GateError("command_deadline_exceeded") from None
        except KeyboardInterrupt:
            terminate_group(group)
            raise GateError("command_interrupted") from None
        if status.si_code != os.CLD_EXITED or status.si_status != 0:
            code = terminate_group(group)
        else:
            code = group.reap()
    if code != 0:
        raise GateError(f"command_failed_exit_{code}")


def terminate_group(group):
    # Keep the leader alive or WNOWAIT-unreaped throughout TERM/grace/KILL.
    # Losing child ownership is a failure, not permission for best-effort use
    # of a stale numeric group ID. No signal is ever issued after reap starts.
    if not group.signal_group(signal.SIGTERM):
        return group.reap()
    deadline = time.monotonic() + GROUP_GRACE_SECONDS
    while time.monotonic() < deadline:
        group.observe_exit()
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    group.signal_group(signal.SIGKILL)
    return group.reap()


def execute(args, source, work, report):
    work.mkdir(mode=0o700)
    runner = work / "probe"
    prepare_runner(source, runner)
    observer_target = work / "observer-target"
    original_target = work / "original-target"
    offline = ["--offline"] if args.offline else []
    steps = [
        ("observer_build", OBSERVER_TOOLCHAIN, ROOT, observer_target, [
            "build", "--locked", *offline, "--manifest-path",
            str(ROOT / "services/hepta-os/Cargo.toml"), "--bin", "hepta-observe",
        ]),
        ("original_agentd_build", UPSTREAM_TOOLCHAIN, source / "codex-rs", original_target, [
            "build", "--locked", *offline, "--profile", "dev-small",
            "--no-default-features", "-p", "codex-hepta-agentd", "--bin", "codex-hepta-agentd", "-j1",
        ]),
        ("original_probe_resolution", UPSTREAM_TOOLCHAIN, runner, original_target, [
            "metadata", *offline, "--format-version", "1", "--manifest-path", str(runner / "Cargo.toml"),
        ]),
        ("original_library_probe_build", UPSTREAM_TOOLCHAIN, runner, original_target, [
            "build", "--locked", *offline, "--profile", "dev-small", "--manifest-path", str(runner / "Cargo.toml"), "-j1",
        ]),
    ]
    for name, version, cwd, target, cargo_args in steps:
        if name == "original_agentd_build":
            report["large_build_attempted"] = True
        # rustup run fails if this installed toolchain is absent; it does not
        # implicitly substitute another compiler or download a new toolchain.
        command = [args.rustup, "run", version, "cargo", *cargo_args]
        record = {"step": name, "command": command, "status": "running"}
        report["steps"].append(record)
        bounded_command(command, cwd, build_environment(target), work / f"{name}.log", 3600)
        if name == "original_probe_resolution":
            verify_runner_lock(source, runner)
        record["status"] = "passed"
    verify_runner_lock(source, runner)
    verify_source(source)
    binaries = {
        "agentd": original_target / "dev-small/codex-hepta-agentd",
        "observer": observer_target / "debug/hepta-observe",
        "probe": original_target / f"dev-small/{RUNNER_NAME}",
    }
    report["binary_sha256"] = {name: sha256(path) for name, path in binaries.items()}
    report["probe_resolved_lock_sha256"] = sha256(runner / "Cargo.lock")
    report["probe_source_sha256"] = sha256(runner / "src/main.rs")
    report["observer_source_sha256"] = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted((ROOT / "services/hepta-os").rglob("*"))
        if path.is_file() and "target" not in path.parts
    }
    report["runtime_probe_attempted"] = True
    report["live_agentd_acceptance"] = "failed"
    # A short fresh path is necessary for the original nested UUID Unix socket.
    with tempfile.TemporaryDirectory(prefix="hp-", dir="/tmp") as state_root:
        command = [str(binaries["probe"]), str(binaries["agentd"]), str(binaries["observer"]), state_root, str(args.hold_seconds)]
        record = {"step": "original_agentd_process_probe", "status": "running"}
        report["steps"].append(record)
        # No inherited HOME/CODEX_HOME, API key, AuthBus/Hepta provider flags or
        # existing user config. Original UnixProcessDriver assigns child roots.
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HEPTA_COGNITIVE_RETRIEVAL_MODE": "compatibility"}
        log_path = work / "original_agentd_process_probe.log"
        bounded_command(command, ROOT, environment, log_path, 240)
        if log_path.stat().st_size > 1024 * 1024:
            raise GateError("runtime_probe_log_exceeded_bound")
        records = [json.loads(line) for line in log_path.read_text().splitlines() if line.startswith("{")]
        if not records:
            raise GateError("runtime_acceptance_record_missing")
        final = records[-1]
        if final.get("event") != "acceptance_pass" or final.get("checks") != EXPECTED_CHECKS:
            raise GateError("runtime_acceptance_checks_incomplete")
        if any(final.get(key) is not False for key in ["objective_submission", "model_turn", "device_effect"]):
            raise GateError("unexpected_effect_profile")
        report["runtime_records"] = records
        record["status"] = "passed"
    verify_source(source)
    report["live_agentd_acceptance"] = "passed"
    report["status"] = "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hepta-source", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True, help="Must not exist; never reuse an existing fleet or build directory")
    parser.add_argument("--execute", action="store_true", help="Perform the resource-gated original builds and fresh private process probe")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--rustup", default=shutil.which("rustup") or "rustup")
    parser.add_argument("--hold-seconds", type=int, default=0, choices=range(31), metavar="0..30")
    parser.add_argument("--report", type=Path, help="New report file; never overwrite prior evidence")
    args = parser.parse_args()
    report = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "original_agentd_readonly_acceptance_gate",
        "status": "preflight", "large_build_attempted": False,
        "runtime_probe_attempted": False, "live_agentd_acceptance": "not_run",
        "required_toolchains": {"upstream": UPSTREAM_TOOLCHAIN, "observer": OBSERVER_TOOLCHAIN},
        "profile": {"agentd_default_features": False, "supervisor_production_authority": False,
                    "objective_issuer": False, "model_turn": False, "device_effect_provider": False},
        "steps": [],
    }
    code = 1
    try:
        source = args.hepta_source.resolve(strict=True)
        report["upstream"] = verify_source(source)
        work = args.work_dir.resolve()
        if work.is_relative_to(source) or work.is_relative_to(ROOT):
            raise GateError("work_directory_must_be_outside_source_checkouts")
        if args.report and (args.report.exists() or args.report.resolve().is_relative_to(source)):
            raise GateError("report_must_be_new_and_outside_original_source")
        if work.exists():
            raise GateError("work_directory_already_exists")
        if not work.parent.is_dir():
            raise GateError("work_parent_missing")
        free = shutil.disk_usage(work.parent).free
        report["resources"] = {"free_bytes": free, "minimum_free_bytes": MIN_FREE_BYTES,
                               "bound_kind": "conservative_build_estimate_not_measured_size"}
        blockers = []
        if platform.system() != "Linux":
            blockers.append("linux_required")
        if not child_anchor_available():
            blockers.append("waitable_child_anchor_unavailable")
        if free < MIN_FREE_BYTES:
            blockers.append("insufficient_disk_for_original_build")
        if not shutil.which(args.rustup):
            blockers.append("rustup_unavailable")
        else:
            installed = subprocess.check_output(
                [args.rustup, "toolchain", "list"], text=True,
                stderr=subprocess.PIPE, timeout=10,
            ).splitlines()
            report["installed_toolchains"] = installed
            for version in [UPSTREAM_TOOLCHAIN, OBSERVER_TOOLCHAIN]:
                if not any(line.split()[0] == version or line.startswith(version + "-") for line in installed if line.split()):
                    blockers.append(f"toolchain_not_installed:{version}")
        for tool in ["git", "cc", "c++", "cmake", "pkg-config"]:
            if not shutil.which(tool):
                blockers.append(f"build_tool_missing:{tool}")
        report["blockers"] = blockers
        if blockers:
            report["status"] = "blocked"
            code = 2
        elif args.execute:
            execute(args, source, work, report)
            code = 0
        else:
            report["status"] = "preflight_pass_build_and_runtime_not_run"
            code = 0
    except (GateError, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        report["status"] = "failed"
        report["failure"] = str(error) if isinstance(error, GateError) else type(error).__name__
    encoded = json.dumps(report, indent=2) + "\n"
    if args.report:
        with args.report.open("x", encoding="utf-8") as output:
            output.write(encoded)
    print(encoded, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
