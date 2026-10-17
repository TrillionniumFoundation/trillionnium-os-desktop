#!/usr/bin/env python3
"""Reproduce A03 failures and fixes with the pinned compiler, on a host only.

The token, native-context, status and callback baselines are genuine named commits.
Drop cleanup
and management-origin controls are explicitly synthetic mutations of CURRENT
source, not claimed historical commits. Expected assertion failures retain exit 101
and logs; this script exits zero only when every negative control and fixed
suite matches its exact expectations. Temporary Rust sources
and binaries stay outside the repository and are removed after execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


BASELINE_COMMIT = "40ca002fac0726b366726d3353916637b29adeae"
NATIVE_BASELINE_COMMIT = "86663ea5a934d085a80fcaeaacca535bfb283b77"
STATUS_BASELINE_COMMIT = "e59f8b2fce1287f1ea706dc94880824a9b586ae3"
CALLBACK_BASELINE_COMMIT = "d172babcb3d6275ee0dfb0c9a58207eb2149eef9"
PINNED_TOOLCHAIN = "nightly-2026-07-21"
PINNED_VERSION = "rustc 1.99.0-nightly (87e5904f5 2026-07-20)"
SOURCES = (
    "libs/os-control/src/lib.rs",
    "libs/os-control/src/native.rs",
    "libs/os-control/src/sync.rs",
    "libs/os-control/src/management.rs",
    "libs/os-control/src/resource_state.rs",
    "libs/os-control/src/locking.rs",
    "tests/control/token_retirement.rs",
    "tests/control/native_handoff.rs",
    "tests/control/native_context_negative.rs",
    "tests/control/native_bound_execution.rs",
    "tests/control/native_lifetime.rs",
    "tests/control/management_authority.rs",
    "tests/control/management_identity.rs",
    "tests/control/native_failure_recovery.rs",
    "tests/control/status_boundary.rs",
    "tests/control/callback_lifetime.rs",
    "tests/control/native_resource_state.rs",
    "tests/control/custom_lock_backend.rs",
    "tests/control/api_compat.rs",
)
RETIRE_FIXED = """        for _ in (ns.retired_through + 1)..=ack.through {
            if let Some(slot) = ns.slots.pop_front() {
                reclaimed.push(slot);
            }
        }
        ns.retired_through = ack.through;
        let receipt = RetireReceipt {
            retired_through: ns.retired_through,
            next_sequence: ns.next_sequence,
        };
        // The real owner's final destructor may enter its own locks or read
        // this namespace. Publish the frontier before dropping pins, without
        // holding the namespace table lock during external destruction.
        drop(ns);
        drop(reclaimed);
        Ok(receipt)"""
RETIRE_MUTATED = """        // Keep the now-unused scratch Vec's inferred type in this control.
        let _: &Vec<Arc<Slot<B>>> = &reclaimed;
        for _ in (ns.retired_through + 1)..=ack.through {
            ns.slots.pop_front();
        }
        ns.retired_through = ack.through;
        Ok(RetireReceipt {
            retired_through: ns.retired_through,
            next_sequence: ns.next_sequence,
        })"""
LOSS_FIXED = """        let reclaimed = core::mem::take(&mut ns.slots);
        ns.generation = ns.generation.saturating_add(1);
        ns.closing = false;
        drop(ns);
        drop(_loss);
        drop(reclaimed);"""
LOSS_MUTATED = """        ns.slots.clear();
        ns.generation = ns.generation.saturating_add(1);
        ns.closing = false;"""
SUMMARY = re.compile(
    r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; "
    r"(\d+) ignored; (\d+) measured; (\d+) filtered out;",
    re.MULTILINE,
)
TOKEN_FAILURES = {
    "retained_retired_token_no_longer_keeps_a_child_cap_constraint_alive",
    "lost_history_releases_result_resources_even_when_the_old_token_is_retained",
    "obsolete_token_does_not_keep_an_otherwise_unreferenced_namespace_alive",
}
DROP_FAILURES = {
    "native_owner_drop_during_retirement_can_read_same_namespace_before_return",
    "native_owner_drop_during_history_loss_can_reenter_loss_gate_before_return",
}
NATIVE_CONTEXT_FAILURES = {
    "generic_native_callback_cannot_apply_a_different_owner_with_the_same_public_ids",
    "generic_native_callback_cannot_replace_reserved_ancestry_with_fresh_context",
}
STATUS_FAILURES = {
    "out_of_order_is_not_a_serializable_saved_terminal_result",
    "retired_is_not_a_serializable_saved_terminal_result",
}
ORIGIN_FAILURES = {
    "independent_states_with_identical_config_cannot_use_each_others_snapshots",
    "revoke_then_reconstruct_same_config_does_not_reactivate_the_old_snapshot",
    "snapshot_after_state_destruction_is_metadata_and_cannot_authorize_a_new_state",
    "replacing_state_inside_the_same_owner_cannot_reauthorize_a_reserved_old_d",
}
CALLBACK_FAILURES = {
    "native_success_publishes_before_owned_capture_cleanup_and_loss",
    "host_success_releases_gate_before_owned_capture_cleanup",
    "body_unwind_releases_gate_before_capture_cleanup_and_keeps_one_effect",
    "malformed_outcome_releases_gate_before_capture_cleanup",
    "capture_destructor_panic_after_success_cannot_erase_terminal_publication",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Recorder:
    def __init__(self, output: Path, environment: dict[str, str]) -> None:
        self.output = output
        self.environment = environment
        self.commands: list[dict] = []

    def run(
        self,
        name: str,
        command: list[str],
        cwd: Path,
        expected_exit: int = 0,
        source_output: bool = False,
    ) -> str:
        record = {
            "name": name,
            "command": command,
            "cwd": str(cwd),
            "expected_exit": expected_exit,
            "timeout_seconds": 45,
        }
        self.commands.append(record)
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=self.environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            (self.output / f"{name}.stdout.log").write_bytes(error.stdout or b"")
            (self.output / f"{name}.stderr.log").write_bytes(error.stderr or b"")
            record.update(returncode=None, timed_out=True, matched_expectation=False)
            raise RuntimeError(f"{name} timed out; this cannot count as a negative control") from error
        record.update(
            returncode=result.returncode,
            timed_out=False,
            stdout_sha256=sha256(result.stdout),
            stdout_bytes=len(result.stdout),
            matched_expectation=result.returncode == expected_exit,
        )
        # Git show stdout is source, not a test log. Record its hash and size
        # instead of copying old implementation text into deliverable evidence.
        if not source_output:
            (self.output / f"{name}.stdout.log").write_bytes(result.stdout)
        (self.output / f"{name}.stderr.log").write_bytes(result.stderr)
        if result.returncode != expected_exit:
            raise RuntimeError(
                f"{name}: expected exit {expected_exit}, observed {result.returncode}; see logs"
            )
        return result.stdout.decode("utf-8")


def verify_tests(
    recorder: Recorder,
    name: str,
    executable: Path,
    passed: int,
    failed: int,
    filtered: int,
    expected_failures: set[str],
    test_filter: str | None = None,
) -> dict:
    command = [str(executable)]
    if test_filter is not None:
        command.append(test_filter)
    command.append("--test-threads=1")
    text = recorder.run(name, command, executable.parent, 101 if failed else 0)
    summaries = SUMMARY.findall(text)
    expectation = ("FAILED" if failed else "ok", passed, failed, 0, 0, filtered)
    observed = None
    if len(summaries) == 1:
        status, *counts = summaries[0]
        observed = (status, *(int(value) for value in counts))
    failed_names = set(re.findall(r"^test (\S+) \.\.\. FAILED$", text, re.MULTILINE))
    check = {
        "name": name,
        "expected": expectation,
        "observed": observed,
        "expected_failure_names": sorted(expected_failures),
        "observed_failure_names": sorted(failed_names),
        "success": observed == expectation and failed_names == expected_failures,
    }
    if not check["success"]:
        raise RuntimeError(f"{name}: Rust counts or designated failure names differ: {check}")
    return check


def compile_library(recorder: Recorder, rustc: str, name: str, root: Path) -> Path:
    library = root / "libos_control.rlib"
    recorder.run(
        f"{name}-compile-library",
        [
            rustc, "--edition", "2021", "--crate-name", "os_control",
            "--crate-type", "rlib", "--forbid=unsafe_code", "--cfg", 'feature="std"',
            str(root / "lib.rs"), "-o", str(library),
        ],
        root,
    )
    return library


def compile_tests(
    recorder: Recorder, rustc: str, name: str, root: Path, library: Path, source: str
) -> Path:
    executable = root / f"{name}-tests"
    recorder.run(
        f"{name}-compile-tests",
        [
            rustc, "--edition", "2021", "--test", "--forbid=unsafe_code",
            str(root / source), "--extern", f"os_control={library}", "-o", str(executable),
        ],
        root,
    )
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="new directory for JSON and raw execution logs")
    parser.add_argument("--rustc", default=os.environ.get("RUSTC") or shutil.which("rustc"))
    args = parser.parse_args()
    if not args.rustc:
        parser.error("provide --rustc or put the fixed compiler on PATH")
    repo = Path(__file__).resolve().parents[2]
    output = args.output_dir.absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment["RUSTUP_TOOLCHAIN"] = PINNED_TOOLCHAIN
    # Preserve the executable's rustc name if it is a rustup proxy symlink.
    rustc = os.path.abspath(args.rustc)
    recorder = Recorder(output, environment)
    report = {
        "schema": 1,
        "scope": "std host regression controls; no real kernel or durable Hepta execution",
        "success": False,
        "baseline_commit": BASELINE_COMMIT,
        "native_baseline_commit": NATIVE_BASELINE_COMMIT,
        "status_baseline_commit": STATUS_BASELINE_COMMIT,
        "callback_baseline_commit": CALLBACK_BASELINE_COMMIT,
        "synthetic_drop_control": "current source with two exact reclamation blocks reverted; not a historical commit",
        "synthetic_origin_control": "current source with only the two management origin comparisons removed; not historical",
        "synthetic_lock_role_control": "current source with SlotState lock tagged NamespaceTable; runtime assertion control, not historical",
        "rustup_toolchain": PINNED_TOOLCHAIN,
        "commands": recorder.commands,
        "checks": [],
    }
    try:
        version = recorder.run("rustc-version", [rustc, "-vV"], repo)
        report["rustc_version"] = version
        if version.splitlines()[0] != PINNED_VERSION:
            raise RuntimeError("the selected compiler is not the project's exact pinned nightly")
        report["checkout_commit"] = recorder.run("checkout-commit", ["git", "rev-parse", "HEAD"], repo).strip()
        current = {}
        for source in SOURCES:
            path = repo / source
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f"missing or symlinked source: {source}")
            current[source] = path.read_bytes()
        report["current_source_sha256"] = {path: sha256(data) for path, data in current.items()}
        baseline = {}
        for source in SOURCES[:1] + SOURCES[2:3]:
            text = recorder.run(
                "baseline-" + Path(source).stem,
                ["git", "--no-pager", "show", f"{BASELINE_COMMIT}:{source}"],
                repo,
                source_output=True,
            )
            baseline[source] = text.encode("utf-8")
        report["baseline_source_sha256"] = {path: sha256(data) for path, data in baseline.items()}
        native_baseline = {}
        for source in SOURCES[:3]:
            text = recorder.run(
                "native-baseline-" + Path(source).stem,
                ["git", "--no-pager", "show", f"{NATIVE_BASELINE_COMMIT}:{source}"],
                repo,
                source_output=True,
            )
            native_baseline[source] = text.encode("utf-8")
        report["native_baseline_source_sha256"] = {
            path: sha256(data) for path, data in native_baseline.items()
        }
        status_baseline = {}
        for source in SOURCES[:4]:
            text = recorder.run(
                "status-baseline-" + Path(source).stem,
                ["git", "--no-pager", "show", f"{STATUS_BASELINE_COMMIT}:{source}"],
                repo,
                source_output=True,
            )
            status_baseline[source] = text.encode("utf-8")
        report["status_baseline_source_sha256"] = {
            path: sha256(data) for path, data in status_baseline.items()
        }
        callback_baseline = {}
        for source in SOURCES[:4]:
            text = recorder.run(
                "callback-baseline-" + Path(source).stem,
                ["git", "--no-pager", "show", f"{CALLBACK_BASELINE_COMMIT}:{source}"],
                repo,
                source_output=True,
            )
            callback_baseline[source] = text.encode("utf-8")
        report["callback_baseline_source_sha256"] = {
            path: sha256(data) for path, data in callback_baseline.items()
        }
        mutated = current[SOURCES[0]].decode("utf-8")
        for name, fixed, old in [
            ("retire-drop-under-table-lock", RETIRE_FIXED, RETIRE_MUTATED),
            ("loss-drop-under-table-and-loss-lock", LOSS_FIXED, LOSS_MUTATED),
        ]:
            if mutated.count(fixed) != 1:
                raise RuntimeError(f"{name}: expected exactly one current block; refusing approximate mutation")
            mutated = mutated.replace(fixed, old, 1)
        report["synthetic_lib_sha256"] = sha256(mutated.encode("utf-8"))
        origin_mutated = current["libs/os-control/src/management.rs"].decode("utf-8")
        for fixed, old in [
            ("self.config == other.config && Arc::ptr_eq(&self.origin, &other.origin)",
             "self.config == other.config"),
            ("snapshot.config != self.config || !Arc::ptr_eq(&snapshot.origin, &self.origin)",
             "snapshot.config != self.config"),
        ]:
            if origin_mutated.count(fixed) != 1:
                raise RuntimeError("management origin control requires one exact comparison; refusing approximate mutation")
            origin_mutated = origin_mutated.replace(fixed, old, 1)
        report["synthetic_management_sha256"] = sha256(origin_mutated.encode("utf-8"))
        role_fixed = "state: B::new(SlotState::Reserved, LockRole::SlotState)"
        if current[SOURCES[0]].decode("utf-8").count(role_fixed) != 1:
            raise RuntimeError("lock role control requires one exact slot constructor")
        role_mutated = current[SOURCES[0]].decode("utf-8").replace(
            role_fixed, "state: B::new(SlotState::Reserved, LockRole::NamespaceTable)", 1)
        report["synthetic_lock_role_sha256"] = sha256(role_mutated.encode("utf-8"))
        with tempfile.TemporaryDirectory(prefix="a03-regressions-") as temporary:
            temporary_root = Path(temporary)
            roots = {name: temporary_root / name for name in
                     ("historical-token", "historical-native", "historical-status", "historical-callback", "synthetic-drop", "synthetic-origin", "synthetic-role", "fixed")}
            for name, root in roots.items():
                root.mkdir()
                inputs = (baseline if name == "historical-token" else
                          native_baseline if name == "historical-native" else
                          status_baseline if name == "historical-status" else
                          callback_baseline if name == "historical-callback" else current)
                for source, data in inputs.items():
                    (root / Path(source).name).write_bytes(data)
                for source in SOURCES:
                    if source.startswith("tests/control/"):
                        (root / Path(source).name).write_bytes(current[source])
            (roots["synthetic-drop"] / "lib.rs").write_text(mutated)
            (roots["synthetic-origin"] / "management.rs").write_text(origin_mutated)
            (roots["synthetic-role"] / "lib.rs").write_text(role_mutated)
            root = roots["historical-token"]
            library = compile_library(recorder, rustc, "historical-token", root)
            executable = compile_tests(recorder, rustc, "historical-token", root, library, "token_retirement.rs")
            report["checks"].append(verify_tests(recorder, "historical-token-run", executable, 2, 3, 0, TOKEN_FAILURES))
            root = roots["historical-native"]
            library = compile_library(recorder, rustc, "historical-native", root)
            executable = compile_tests(recorder, rustc, "historical-native", root, library,
                                       "native_context_negative.rs")
            report["checks"].append(verify_tests(recorder, "historical-native-run", executable,
                                                 0, 2, 0, NATIVE_CONTEXT_FAILURES))
            root = roots["historical-status"]
            library = compile_library(recorder, rustc, "historical-status", root)
            executable = compile_tests(recorder, rustc, "historical-status", root, library,
                                       "status_boundary.rs")
            report["checks"].append(verify_tests(recorder, "historical-status-run", executable,
                                                 1, 2, 0, STATUS_FAILURES))
            root = roots["historical-callback"]
            library = compile_library(recorder, rustc, "historical-callback", root)
            executable = compile_tests(recorder, rustc, "historical-callback", root, library,
                                       "callback_lifetime.rs")
            report["checks"].append(verify_tests(recorder, "historical-callback-run", executable,
                                                 2, 5, 0, CALLBACK_FAILURES))
            root = roots["synthetic-drop"]
            library = compile_library(recorder, rustc, "synthetic-drop", root)
            executable = compile_tests(recorder, rustc, "synthetic-drop", root, library, "native_handoff.rs")
            report["checks"].append(verify_tests(recorder, "synthetic-drop-run", executable, 0, 2, 13, DROP_FAILURES, "native_owner_drop_"))
            root = roots["synthetic-origin"]
            library = compile_library(recorder, rustc, "synthetic-origin", root)
            executable = compile_tests(recorder, rustc, "synthetic-origin", root, library,
                                       "management_identity.rs")
            report["checks"].append(verify_tests(recorder, "synthetic-origin-run", executable,
                                                 2, 4, 0, ORIGIN_FAILURES))
            root = roots["synthetic-role"]
            library = compile_library(recorder, rustc, "synthetic-role", root)
            executable = compile_tests(recorder, rustc, "synthetic-role", root, library,
                                       "custom_lock_backend.rs")
            report["checks"].append(verify_tests(
                recorder, "synthetic-role-run", executable, 0, 1, 5,
                {"namespace_lock_roles_route_every_native_operation"},
                "namespace_lock_roles_route_every_native_operation"))
            root = roots["fixed"]
            library = compile_library(recorder, rustc, "fixed", root)
            for suite, count in [("token_retirement", 5), ("native_handoff", 15),
                                 ("native_context_negative", 2), ("native_bound_execution", 11),
                                 ("native_lifetime", 5), ("management_authority", 15),
                                 ("management_identity", 6), ("native_failure_recovery", 3),
                                 ("status_boundary", 3), ("callback_lifetime", 7),
                                 ("native_resource_state", 7), ("custom_lock_backend", 6),
                                 ("api_compat", 3)]:
                executable = compile_tests(recorder, rustc, "fixed-" + suite, root, library, suite + ".rs")
                report["checks"].append(verify_tests(recorder, "fixed-" + suite + "-run", executable, count, 0, 0, set()))
        after = {source: sha256((repo / source).read_bytes()) for source in SOURCES}
        report["source_after_sha256"] = after
        if after != report["current_source_sha256"]:
            raise RuntimeError("current inputs changed during execution; results do not attest the final source")
        report["success"] = True
    except (OSError, RuntimeError, UnicodeError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"success": report["success"], "report": str(output / "report.json"), "error": report.get("error")}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
