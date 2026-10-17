#!/usr/bin/env python3
"""Reproduce the ReserveAttempt variant-import compatibility regression.

The same pre-backend consumer is compiled against byte-identical Rust sources
from the pinned pre-change main, the first public-backend commit, and the current
worktree. The historical negative must be exactly E0432 explaining that
ReserveAttempt is a type alias rather than a module. An arbitrary compiler
failure, library failure or timeout is never accepted as a negative control.
This is a source-compatibility compile check, separate from runtime assertions.
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


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "libs/os-control/src"
BEFORE_COMMIT = "1247d30b2a8d82598482512f4d614b622499e541"
BROKEN_COMMIT = "a2ef27a77fecf6ace2f822fb217a65f9454ba69d"
TOOLCHAIN = "nightly-2026-07-21"
RUSTC_VERSION = "rustc 1.99.0-nightly (87e5904f5 2026-07-20)"
CONSUMER = b"""use os_control::{DeliveryObservation, ReserveAttempt, ReserveToken};
use os_control::ReserveAttempt::{Existing, Reserved};

pub fn classify(value: ReserveAttempt) -> bool {
    match value {
        Reserved(token) => {
            let _: ReserveToken = token;
            true
        }
        Existing(observation) => {
            let _: DeliveryObservation = observation;
            false
        }
    }
}
"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(sources: dict[str, bytes]) -> list[dict[str, object]]:
    return [{"path": name, "bytes": len(data), "sha256": sha(data)}
            for name, data in sorted(sources.items())]


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def sources(commit: str | None) -> dict[str, bytes]:
    if commit is None:
        paths = sorted(SOURCE.rglob("*.rs"))
        if any(path.is_symlink() for path in paths):
            raise ValueError("symlinked production source is not accepted")
        result = {str(path.relative_to(SOURCE)): path.read_bytes() for path in paths}
    else:
        resolved = git_bytes("rev-parse", commit).decode().strip()
        if resolved != commit:
            raise ValueError("historical commit did not resolve to its full pinned SHA")
        names = git_bytes("ls-tree", "-r", "--name-only", commit, "--",
                          "libs/os-control/src").decode().splitlines()
        result = {str(Path(name).relative_to("libs/os-control/src")):
                  git_bytes("show", f"{commit}:{name}")
                  for name in names if name.endswith(".rs")}
    if "lib.rs" not in result or "sync.rs" not in result:
        raise ValueError("production source inventory lacks required modules")
    return result


def run(argv: list[str], cwd: Path, env: dict[str, str], output: Path,
        name: str) -> dict[str, object]:
    try:
        process = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                                 timeout=60, check=False)
        code, stdout, stderr, timed_out = process.returncode, process.stdout, process.stderr, False
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr, timed_out = None, error.stdout or b"", error.stderr or b"", True
    output.joinpath(f"{name}.stdout.log").write_bytes(stdout)
    output.joinpath(f"{name}.stderr.log").write_bytes(stderr)
    return {"argv": argv, "cwd": str(cwd), "returncode": code, "timed_out": timed_out,
            "stdout": f"{name}.stdout.log", "stderr": f"{name}.stderr.log",
            "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr)}


def expect_success(result: dict[str, object], name: str) -> None:
    if result["timed_out"] or result["returncode"] != 0:
        raise ValueError(f"{name} failed or timed out; not a valid negative control")


def expected_alias_error(result: dict[str, object], output: Path) -> list[dict[str, object]]:
    if result["timed_out"] or result["returncode"] != 1:
        raise ValueError("historical consumer did not fail with rustc exit 1")
    diagnostics = []
    for line in output.joinpath(str(result["stderr"])).read_text().splitlines():
        value = json.loads(line)
        if value.get("$message_type") == "diagnostic":
            diagnostics.append(value)
    all_errors = [item for item in diagnostics if item.get("level") == "error"]
    errors = [item for item in all_errors if item.get("code") is not None]
    summaries = [item for item in all_errors if item.get("code") is None]
    if (len(errors) != 1 or errors[0]["code"].get("code") != "E0432"
            or len(summaries) != 1
            or summaries[0].get("message") != "aborting due to 1 previous error"):
        raise ValueError("historical consumer failed for an error other than the designated E0432")
    diagnostic = errors[0]
    if diagnostic.get("message") != "unresolved import `os_control::ReserveAttempt`":
        raise ValueError("historical E0432 does not identify the ReserveAttempt import")
    spans = diagnostic.get("spans", [])
    if not any(item.get("is_primary") is True
               and Path(item.get("file_name", "")).name == "consumer.rs"
               and item.get("line_start") == 2
               and item.get("label") == "`ReserveAttempt` is a type alias, not a module"
               for item in spans):
        raise ValueError("historical E0432 lacks the exact alias-not-module import span")
    return [{"code": "E0432", "message": diagnostic["message"],
             "primary_label": "`ReserveAttempt` is a type alias, not a module",
             "consumer_line": 2}]


def probe(name: str, commit: str | None, rustc: str, env: dict[str, str],
          output: Path, current: dict[str, bytes]) -> dict[str, object]:
    original = sources(commit) if commit is not None else current
    receipt: dict[str, object] = {
        "source_revision": commit or "worktree", "source_inventory": inventory(original),
        "consumer_sha256": sha(CONSUMER), "expected": "E0432_alias_not_module" if name == "broken" else "compile_success",
        "passed": False,
    }
    with tempfile.TemporaryDirectory(prefix=f"a03-api-{name}-") as temporary:
        workspace = Path(temporary)
        source_dir = workspace / "src"
        source_dir.mkdir()
        for relative, data in original.items():
            target = source_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (workspace / "consumer.rs").write_bytes(CONSUMER)
        library = workspace / "libos_control.rlib"
        common = [rustc, "--edition=2021", "--forbid=unsafe_code", "--error-format=json"]
        receipt["library"] = run(
            [*common, "--crate-name=os_control", "--crate-type=rlib", "--cfg", 'feature="std"',
             str(source_dir / "lib.rs"), "-o", str(library)],
            workspace, env, output, f"{name}-library")
        expect_success(receipt["library"], f"{name} library")
        receipt["consumer"] = run(
            [*common, "--crate-name=pre_backend_consumer", "--crate-type=rlib",
             str(workspace / "consumer.rs"), "--extern", f"os_control={library}",
             "-o", str(workspace / "libconsumer.rlib")],
            workspace, env, output, f"{name}-consumer")
        if name == "broken":
            receipt["expected_diagnostics"] = expected_alias_error(receipt["consumer"], output)
        else:
            expect_success(receipt["consumer"], f"{name} consumer")
        copied = {str(path.relative_to(source_dir)): path.read_bytes()
                  for path in sorted(source_dir.rglob("*.rs"))}
        receipt["copied_source_bytes_verified_after_execution"] = copied == original
        receipt["consumer_bytes_verified_after_execution"] = (workspace / "consumer.rs").read_bytes() == CONSUMER
        if copied != original or not receipt["consumer_bytes_verified_after_execution"]:
            raise ValueError("temporary production source or consumer changed during compilation")
        receipt["passed"] = True
    receipt["temporary_workspace_removed"] = True
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if env.get("RUSTUP_TOOLCHAIN") not in (None, TOOLCHAIN):
        parser.error(f"RUSTUP_TOOLCHAIN must be {TOOLCHAIN}")
    env["RUSTUP_TOOLCHAIN"] = TOOLCHAIN
    rustc = env.get("RUSTC") or shutil.which("rustc")
    if rustc is None:
        parser.error("rustc not found; activate the project's fixed toolchain")
    rustc = os.path.abspath(rustc)
    script = HERE.joinpath("run-checks.py").read_bytes()
    report: dict[str, object] = {
        "kind": "source-compatibility compile control; not a runtime assertion or kernel proof",
        "before_commit": BEFORE_COMMIT, "broken_commit": BROKEN_COMMIT,
        "consumer": CONSUMER.decode(), "consumer_sha256": sha(CONSUMER),
        "harness_sha256": sha(script), "toolchain": TOOLCHAIN,
        "variants": {}, "passed": False,
    }
    current = None
    try:
        report["rustc"] = run([rustc, "-vV"], ROOT, env, output, "rustc")
        expect_success(report["rustc"], "rustc version")
        if output.joinpath("rustc.stdout.log").read_text().splitlines()[0] != RUSTC_VERSION:
            raise ValueError("compiler version does not match the exact pinned nightly")
        report["checkout_commit"] = git_bytes("rev-parse", "HEAD").decode().strip()
        current = sources(None)
        report["current_source_inventory"] = inventory(current)
        for name, commit in (("before", BEFORE_COMMIT), ("broken", BROKEN_COMMIT), ("current", None)):
            report["variants"][name] = probe(name, commit, rustc, env, output, current)
        report["all_variants_used_identical_consumer"] = all(
            value["consumer_sha256"] == report["consumer_sha256"]
            for value in report["variants"].values())
        report["passed"] = report["all_variants_used_identical_consumer"]
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
    finally:
        try:
            report["worktree_source_bytes_unchanged"] = current is not None and sources(None) == current
            report["harness_bytes_unchanged"] = HERE.joinpath("run-checks.py").read_bytes() == script
            if not report["worktree_source_bytes_unchanged"] or not report["harness_bytes_unchanged"]:
                report["passed"] = False
                report["error"] = "production source inventory/bytes or harness changed during compilation"
        except (OSError, ValueError) as error:
            report["passed"] = False
            report["error"] = str(error)
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "report": str(output / "results.json"),
                      "error": report.get("error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
