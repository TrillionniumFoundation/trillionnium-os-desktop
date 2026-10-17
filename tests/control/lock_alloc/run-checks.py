#!/usr/bin/env python3
"""Build exact-source native delivery probes with a test-only lock/allocator shim.

The production sources are copied only into a temporary Cargo workspace. All
modules except sync.rs remain byte-identical; that module re-exports a std
mutex shim from a separate test crate. Unsafe allocator hooks never enter the
production crate, whose unsafe_code=forbid lint remains enabled.

Default: require zero allocation/reallocation/deallocation under internal locks
for the current worktree. --historical-control also reproduces the pinned e59
counterexample with the same native scenarios. --historical-only records just
that counterexample and explicitly makes no claim about the current worktree.
--callback-control similarly checks the pinned pre-FnMut d172 capture-cleanup
counterexample plus current zero; --callback-only records just that negative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE_ROOT = ROOT / "libs/os-control/src"
HISTORICAL_COMMIT = "e59f8b2fce1287f1ea706dc94880824a9b586ae3"
CALLBACK_COMMIT = "d172babcb3d6275ee0dfb0c9a58207eb2149eef9"
TOOLCHAIN = "nightly-2026-07-21"
RUSTC_VERSION_LINE = "rustc 1.99.0-nightly (87e5904f5 2026-07-20)"
REPLACEMENT_SYNC = b"pub(crate) use lock_trace::{lock_unpoisoned, Arc, Mutex, Weak};\n"
SCENARIOS = (
    "reserve_new", "query_reserved", "duplicate_reserved", "native_wrong_type",
    "execute_native", "query_terminal", "duplicate_terminal", "publish_terminal_retry",
    "retire_terminal", "query_retired", "callback_capture_drop", "full_window_rejection", "loss_full_window",
    "hanging_prefix_query", "hanging_prefix_retire", "hanging_prefix_full",
    "publish_pending", "retire_released_prefix", "ten_thousand_writes",
)
COUNT_FIELDS = ("alloc", "realloc", "dealloc")
SCOPE = (
    "Native namespace scenarios using exact production modules except a std mutex shim. "
    "The shim measures thread-local internal-mutex depth and the process allocator records "
    "alloc/alloc_zeroed, realloc and dealloc calls (including injected failed attempts) "
    "while depth is nonzero. Positive controls, "
    "poison/unwind recovery and independent thread depth are checked. Summary includes "
    "scenario setup between named operations, excluding instrumentation controls. "
    "Callback coverage includes implicit cleanup of owned captures whose bodies only borrow them; "
    "explicit callback destruction, allocation and reentry remain the adapter's obligations. "
    "This is a std host harness: no Arc atomic ordering proof, exhaustive scheduling proof, "
    "portable-spin allocator proof, real kernel allocator/IRQ proof or host ResourceDomain "
    "allocation claim. Controlled allocation failures cover only the initial ring and "
    "retirement Vec try_reserve_exact paths; no general OOM guarantee is inferred."
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git_bytes(*arguments: str) -> bytes:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, timeout=30)


def sources(revision: str | None) -> dict[str, bytes]:
    if revision:
        names = git_bytes("ls-tree", "-r", "--name-only", revision, "--", "libs/os-control/src").decode().splitlines()
        return {str(Path(name).relative_to("libs/os-control/src")): git_bytes("show", f"{revision}:{name}")
                for name in names if name.endswith(".rs")}
    return {str(path.relative_to(SOURCE_ROOT)): path.read_bytes()
            for path in sorted(SOURCE_ROOT.rglob("*.rs"))}


def inventory(data: dict[str, bytes]) -> list[dict[str, object]]:
    return [{"path": name, "bytes": len(value), "sha256": sha(value)}
            for name, value in sorted(data.items())]


def command(arguments: list[str], cwd: Path, env: dict[str, str], output: Path,
            name: str, timeout: int) -> dict[str, object]:
    started = time.monotonic()
    try:
        result = subprocess.run(arguments, cwd=cwd, env=env, capture_output=True, timeout=timeout)
        code, stdout, stderr, timed_out = result.returncode, result.stdout, result.stderr, False
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr, timed_out = None, error.stdout or b"", error.stderr or b"", True
    output.joinpath(f"{name}.stdout.log").write_bytes(stdout)
    output.joinpath(f"{name}.stderr.log").write_bytes(stderr)
    return {
        "argv": arguments, "cwd": str(cwd), "returncode": code, "timed_out": timed_out,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "stdout": f"{name}.stdout.log", "stderr": f"{name}.stderr.log",
        "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
    }


def parse_events(path: Path) -> list[dict[str, object]]:
    events = []
    for line in path.read_text().splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("fixture output contains a non-object event")
        events.append(value)
    return events


def check_events(events: list[dict[str, object]], control: str) -> dict[str, object]:
    def one(event: str, name: str | None = None) -> dict[str, object]:
        selected = [row for row in events if row.get("event") == event and (name is None or row.get("name") == name)]
        if len(selected) != 1:
            raise ValueError(f"expected exactly one {event}/{name}; saw {len(selected)}")
        return selected[0]

    positive = one("control", "allocator_positive")
    if not all(isinstance(positive.get(field), int) and positive[field] > 0 for field in COUNT_FIELDS):
        raise ValueError("allocator positive control did not detect alloc/realloc/dealloc")
    if one("control", "depth_tls_poison_unwind").get("passed") is not True:
        raise ValueError("TLS/poison/unwind control failed")
    failed_call = one("control", "failed_allocator_call_under_lock")
    if tuple(failed_call.get(field) for field in COUNT_FIELDS) != (1, 0, 0):
        raise ValueError("failed allocation under lock was not recorded as an allocator call")
    scenario_rows = [row for row in events if row.get("event") == "scenario"]
    if tuple(row.get("name") for row in scenario_rows) != SCENARIOS:
        raise ValueError("scenario inventory/order differs from the complete fixture")
    for row in scenario_rows:
        if any(not isinstance(row.get(field), int) or row[field] < 0 for field in COUNT_FIELDS):
            raise ValueError(f"invalid allocation count in {row.get('name')}")
    summary = one("summary", "all_native_namespace_scenarios")
    acceptance = one("acceptance")
    if acceptance.get("scenario_count") != len(SCENARIOS) or acceptance.get("controls_ok") is not True:
        raise ValueError("fixture did not complete every scenario/control")
    zero = all(summary.get(field) == 0 for field in COUNT_FIELDS)
    if acceptance.get("zero") is not zero:
        raise ValueError("fixture acceptance disagrees with recorded counts")
    if control == "historical":
        by_name = {row["name"]: row for row in scenario_rows}
        # A compiler failure, arbitrary panic or incomplete fixture cannot be a
        # negative pass: identify the intended reserve + reclaim counterexample.
        if zero or not (by_name["reserve_new"]["alloc"] > 0
                        and by_name["retire_terminal"]["alloc"] > 0
                        and by_name["loss_full_window"]["dealloc"] > 0
                        and by_name["ten_thousand_writes"]["alloc"] >= 10_000):
            raise ValueError("pinned baseline did not reproduce the intended lock-allocation defect")
    elif control == "callback":
        by_name = {row["name"]: row for row in scenario_rows}
        captured = by_name["callback_capture_drop"]
        if zero or captured["alloc"] != 0 or captured["realloc"] != 0 or captured["dealloc"] <= 0:
            raise ValueError("pinned callback baseline did not reproduce capture cleanup under the execution gate")
        if any(any(row[field] != 0 for field in COUNT_FIELDS)
               for row in scenario_rows if row["name"] != "callback_capture_drop"):
            raise ValueError("callback-only baseline also reported unrelated lock-allocation defects")
        if any(summary.get(field) != captured[field] for field in COUNT_FIELDS):
            raise ValueError("callback-only summary includes an unrelated unlabelled lock-allocation defect")
    else:
        if not zero or any(any(row[field] != 0 for field in COUNT_FIELDS) for row in scenario_rows):
            raise ValueError("current native namespace allocated/reallocated/deallocated under an internal lock")
        fault = one("failure_control")
        if fault.get("injected_failures") != 2 or fault.get("frontier_atomic") is not True or fault.get("history_usable") is not True:
            raise ValueError("fallible allocation control did not complete correctly")
        if any(one("control", "fallible_ring_and_retirement").get(field) != 0 for field in COUNT_FIELDS):
            raise ValueError("fallible allocation control allocated under an internal lock")
    return {"scenario_count": len(scenario_rows), "summary": summary,
            "allocator_positive_control": positive, "events": events}


def run_probe(output: Path, revision: str | None, env: dict[str, str], cargo: str,
              control: str = "current") -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    historical = revision is not None
    original = sources(revision)
    if "lib.rs" not in original or "sync.rs" not in original:
        raise ValueError("production source inventory is missing lib.rs or sync.rs")
    fixture = HERE.joinpath("fixture.rs").read_bytes()
    shim = HERE.joinpath("sync_shim.rs").read_bytes()
    report: dict[str, object] = {
        "mode": f"{control}_expected_counterexample" if historical else "current_required_zero",
        "source_revision": revision or "worktree",
        "source_inventory": inventory(original), "fixture_sha256": sha(fixture),
        "shim_sha256": sha(shim), "replacement_sync_sha256": sha(REPLACEMENT_SYNC),
        "scope": SCOPE, "passed": False,
    }
    write_json(output / "execution.json", report)
    with tempfile.TemporaryDirectory(prefix="hos2-lock-alloc-") as temporary:
        workspace = Path(temporary)
        for name, data in original.items():
            target = workspace / "os-control/src" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        copied = {name: (workspace / "os-control/src" / name).read_bytes() for name in original}
        if copied != original:
            raise ValueError("production source copy changed bytes")
        workspace.joinpath("os-control/src/sync.rs").write_bytes(REPLACEMENT_SYNC)
        report["copied_source_inventory"] = inventory({name: (workspace / "os-control/src" / name).read_bytes() for name in original})
        report["only_source_substitution"] = "sync.rs"
        for subdir, source_name, data in (("lock-trace", "lib.rs", shim), ("fixture", "main.rs", fixture)):
            target = workspace / subdir / "src" / source_name
            target.parent.mkdir(parents=True)
            target.write_bytes(data)
        manifests = {
            "Cargo.toml": '[workspace]\nmembers = ["os-control", "lock-trace", "fixture"]\nresolver = "2"\n',
            "os-control/Cargo.toml": '[package]\nname = "os-control"\nversion = "0.0.0"\nedition = "2021"\n[features]\ndefault = ["std"]\nstd = []\nportable-spin = []\n[dependencies]\nlock-trace = { path = "../lock-trace" }\n[lints.rust]\nunsafe_code = "forbid"\n',
            "lock-trace/Cargo.toml": '[package]\nname = "lock-trace"\nversion = "0.0.0"\nedition = "2021"\n',
            "fixture/Cargo.toml": '[package]\nname = "lock-alloc-fixture"\nversion = "0.0.0"\nedition = "2021"\n[dependencies]\nos-control = { path = "../os-control" }\nlock-trace = { path = "../lock-trace" }\n',
        }
        for name, contents in manifests.items():
            workspace.joinpath(name).write_text(contents)
        report["generated_manifests"] = {name: {"contents": contents, "sha256": sha(contents.encode())} for name, contents in manifests.items()}
        build_env = {**env, "CARGO_TARGET_DIR": str(workspace / "target")}
        build = command([cargo, "build", "--offline", "--manifest-path", str(workspace / "Cargo.toml"), "-p", "lock-alloc-fixture"], workspace, build_env, output, "build", 180)
        report["build"] = build
        write_json(output / "execution.json", report)
        if build["returncode"] != 0 or build["timed_out"]:
            report["error"] = "fixture build failed; this is never an expected negative result"
        else:
            report["format"] = command([cargo, "fmt", "--all", "--check"], workspace, build_env, output, "format", 60)
            report["clippy"] = command([cargo, "clippy", "--offline", "--workspace", "--all-targets", "--", "-D", "warnings"], workspace, build_env, output, "clippy", 180)
            if any(report[check]["returncode"] != 0 or report[check]["timed_out"] for check in ("format", "clippy")):
                report["error"] = "generated workspace format/clippy failed; this is never an expected negative result"
            else:
                binary = workspace / "target/debug/lock-alloc-fixture"
                arguments = [str(binary)]
                if not historical:
                    arguments.append("--allocation-failure-controls")
                execution = command(arguments, workspace, build_env, output, "run", 120)
                report["run"] = execution
                expected_returncode = 101 if historical else 0
                try:
                    if execution["timed_out"] or execution["returncode"] != expected_returncode:
                        raise ValueError(f"unexpected fixture return code; expected {expected_returncode}, got {execution['returncode']}")
                    report["checks"] = check_events(parse_events(output / "run.stdout.log"), control)
                    report["passed"] = True
                except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                    report["error"] = str(error)
        copied_final = {name: (workspace / "os-control/src" / name).read_bytes() for name in original}
        expected_final = {**original, "sync.rs": REPLACEMENT_SYNC}
        report["temporary_source_bytes_verified_after_execution"] = copied_final == expected_final
        if copied_final != expected_final:
            report["passed"] = False
            report["error"] = "temporary source changed during build/execution"
        if not historical:
            report["worktree_source_bytes_unchanged_during_execution"] = sources(None) == original
            if report["worktree_source_bytes_unchanged_during_execution"] is not True:
                report["passed"] = False
                report["error"] = "worktree source changed during probe; repeat against stable source"
    report["temporary_workspace_removed"] = True
    write_json(output / "execution.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--historical-control", action="store_true")
    mode.add_argument("--historical-only", action="store_true")
    mode.add_argument("--callback-control", action="store_true")
    mode.add_argument("--callback-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if env.get("RUSTUP_TOOLCHAIN") not in (None, TOOLCHAIN):
        parser.error(f"RUSTUP_TOOLCHAIN must be {TOOLCHAIN}")
    env["RUSTUP_TOOLCHAIN"] = TOOLCHAIN
    cargo = env.get("CARGO") or shutil.which("cargo")
    rustc = env.get("RUSTC") or shutil.which("rustc")
    if not cargo or not rustc:
        parser.error("cargo/rustc not found; activate the project's fixed Rust toolchain")
    # Cargo must use the same compiler whose full version is captured below.
    env["RUSTC"] = rustc
    report: dict[str, object] = {
        "scope": SCOPE, "historical_commit": HISTORICAL_COMMIT,
        "callback_commit": CALLBACK_COMMIT,
        "current_check_executed": not (args.historical_only or args.callback_only),
        "rustup_toolchain": env["RUSTUP_TOOLCHAIN"],
        "toolchain_environment": {key: env.get(key) for key in (
            "RUSTUP_HOME", "CARGO_HOME", "RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
            "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS")},
        "fixtures": inventory({"fixture.rs": HERE.joinpath("fixture.rs").read_bytes(),
                               "sync_shim.rs": HERE.joinpath("sync_shim.rs").read_bytes(),
                               "run-checks.py": HERE.joinpath("run-checks.py").read_bytes()}),
        "probes": {}, "passed": False,
    }
    report["rustc"] = command([rustc, "-Vv"], ROOT, env, output, "rustc", 30)
    try:
        if report["rustc"]["returncode"] != 0:
            raise ValueError("fixed Rust compiler unavailable")
        if output.joinpath("rustc.stdout.log").read_text().splitlines()[0] != RUSTC_VERSION_LINE:
            raise ValueError(f"compiler is not the pinned {TOOLCHAIN} version")
        if args.historical_control or args.historical_only:
            resolved = git_bytes("rev-parse", HISTORICAL_COMMIT).decode().strip()
            if resolved != HISTORICAL_COMMIT:
                raise ValueError("historical commit pin did not resolve exactly")
            report["probes"]["historical"] = run_probe(output / "historical", HISTORICAL_COMMIT, env, cargo, "historical")
        if args.callback_control or args.callback_only:
            resolved = git_bytes("rev-parse", CALLBACK_COMMIT).decode().strip()
            if resolved != CALLBACK_COMMIT:
                raise ValueError("callback commit pin did not resolve exactly")
            report["probes"]["callback"] = run_probe(output / "callback", CALLBACK_COMMIT, env, cargo, "callback")
        if not (args.historical_only or args.callback_only):
            report["probes"]["current"] = run_probe(output / "current", None, env, cargo)
        expected_hashes = {row["path"]: row["sha256"] for row in report["fixtures"]}
        report["all_probes_used_identical_harness_bytes"] = all(
            probe["fixture_sha256"] == expected_hashes["fixture.rs"]
            and probe["shim_sha256"] == expected_hashes["sync_shim.rs"]
            for probe in report["probes"].values()
        )
        if report["all_probes_used_identical_harness_bytes"] is not True:
            raise ValueError("probe fixture or shim differs from the initial harness bytes")
        report["passed"] = all(probe["passed"] for probe in report["probes"].values())
        report["result"] = ("historical_counterexample_only_current_not_checked" if args.historical_only
                            else "callback_capture_counterexample_only_current_not_checked" if args.callback_only
                            else "current_zero_with_historical_control" if args.historical_control
                            else "current_zero_with_callback_control" if args.callback_control
                            else "current_zero") if report["passed"] else "failed"
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
    report["harness_fixtures_unchanged_during_execution"] = report["fixtures"] == inventory({
        "fixture.rs": HERE.joinpath("fixture.rs").read_bytes(),
        "sync_shim.rs": HERE.joinpath("sync_shim.rs").read_bytes(),
        "run-checks.py": HERE.joinpath("run-checks.py").read_bytes(),
    })
    if report["harness_fixtures_unchanged_during_execution"] is not True:
        report["passed"] = False
        report["result"] = "failed"
        report["error"] = "harness fixture/script/shim bytes changed during execution; repeat against stable source"
    write_json(output / "execution.json", report)
    print(json.dumps({"passed": report["passed"], "result": report.get("result", "failed"),
                      "current_check_executed": report["current_check_executed"],
                      "report": str(output / "execution.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
