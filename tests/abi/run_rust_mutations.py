#!/usr/bin/env python3
"""Compile real Rust equality mutants and run the unchanged mutation_kill suite.

Only temporary copies of the crate are changed. A mutant is killed only when it
compiles successfully, all seven tests run without skips, and the corresponding
same-sequence conflict test fails. Compiler errors never count as mutation kills.
This checks host codec/canonical-request coverage, not a kernel delivery ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


EXPECTED_TEST_COUNT = 7
MUTANTS = (
    (
        "ignore_cap_ns",
        "cap_ns",
        "same_sequence_and_target_different_cap_is_conflict",
    ),
    (
        "ignore_expected_revision",
        "expected_revision",
        "same_sequence_and_target_different_revision_is_conflict",
    ),
)
INPUTS = (
    "Cargo.toml",
    "src/lib.rs",
    "tests/mutation_kill.rs",
)


def mutated_source(source: str, omitted_field: str) -> str:
    """Replace this one derived PartialEq with a field-omitting implementation.

    Fail closed if the production type changes: silently dropping a new field
    would introduce additional mutations and make the result ambiguous.
    """
    pattern = re.compile(
        r"#\[derive\((?P<traits>[^)]+)\)\]\s*"
        r"pub struct InstallBudgetRequest\s*\{(?P<fields>[^}]+)\}"
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise ValueError("expected exactly one derived InstallBudgetRequest")
    match = matches[0]
    fields = re.findall(r"pub\s+(\w+)\s*:\s*u64\s*,", match["fields"])
    if fields != ["expected_revision", "period_ns", "cap_ns", "reserved"]:
        raise ValueError("InstallBudgetRequest fields changed; review the mutation")
    residue = re.sub(r"pub\s+\w+\s*:\s*u64\s*,", "", match["fields"])
    if residue.strip():
        raise ValueError("unexpected InstallBudgetRequest field syntax")
    traits = [trait.strip() for trait in match["traits"].split(",")]
    if traits.count("PartialEq") != 1 or omitted_field not in fields:
        raise ValueError("expected one derived PartialEq and a known omitted field")
    traits.remove("PartialEq")
    comparisons = "\n            && ".join(
        f"self.{field} == other.{field}"
        for field in fields
        if field != omitted_field
    )
    replacement = (
        f"#[derive({', '.join(traits)})]\n"
        f"pub struct InstallBudgetRequest {{{match['fields']}}}\n\n"
        "impl PartialEq for InstallBudgetRequest {\n"
        "    fn eq(&self, other: &Self) -> bool {\n"
        f"        {comparisons}\n"
        "    }\n"
        "}"
    )
    return source[: match.start()] + replacement + source[match.end() :]


def run_command(command: list[str], cwd: Path, timeout: float) -> dict[str, Any]:
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(cwd / "target")
    env["CARGO_TERM_COLOR"] = "never"
    env["CARGO_NET_OFFLINE"] = "true"
    result: dict[str, Any] = {"command": command, "returncode": None}
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        result.update(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as error:
        # TimeoutExpired may retain bytes even when subprocess text=True.
        def as_text(value: str | bytes | None) -> str:
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""

        result.update(
            stdout=as_text(error.stdout),
            stderr=as_text(error.stderr),
            timed_out=True,
            error=f"command exceeded {timeout:g} seconds",
        )
    except OSError as error:
        result.update(stdout="", stderr="", timed_out=False, error=str(error))
    return result


def test_outcome(output: str) -> dict[str, Any]:
    summaries = re.findall(
        r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; "
        r"(\d+) ignored; (\d+) measured; (\d+) filtered out;",
        output,
        re.MULTILINE,
    )
    lines = re.findall(r"^test (\S+) \.\.\. (ok|FAILED|ignored)$", output, re.MULTILINE)
    cases = dict(lines)
    result: dict[str, Any] = {"cases": cases, "complete": False}
    if len(summaries) != 1:
        result["error"] = "expected exactly one Rust test-result summary"
        return result
    status, passed, failed, ignored, measured, filtered = summaries[0]
    counts = dict(
        zip(
            ("passed", "failed", "ignored", "measured", "filtered_out"),
            map(int, (passed, failed, ignored, measured, filtered)),
        )
    )
    result.update(counts, status=status)
    result["complete"] = (
        len(cases) == len(lines) == EXPECTED_TEST_COUNT
        and counts["passed"] + counts["failed"] == EXPECTED_TEST_COUNT
        and counts["ignored"] == counts["measured"] == counts["filtered_out"] == 0
        and sum(value == "ok" for value in cases.values()) == counts["passed"]
        and sum(value == "FAILED" for value in cases.values()) == counts["failed"]
        and all(expected in cases for _, _, expected in MUTANTS)
    )
    return result


def run_suite(
    directory: Path,
    inputs: dict[str, bytes],
    source: str,
    cargo: str,
    timeout: float,
) -> dict[str, Any]:
    directory.mkdir()
    for relative, content in inputs.items():
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (directory / "src/lib.rs").write_text(source, encoding="utf-8")
    command = [cargo, "test", "--offline", "--color", "never", "--test", "mutation_kill"]
    compilation = run_command(command + ["--no-run"], directory, timeout)
    result: dict[str, Any] = {
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "compilation": compilation,
        "compiled": compilation["returncode"] == 0,
        "test": None,
        "tests": None,
    }
    if result["compiled"]:
        execution = run_command(command + ["--", "--test-threads=1"], directory, timeout)
        result["test"] = execution
        result["tests"] = test_outcome(execution["stdout"])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cargo", default="cargo", help="Cargo executable (default: cargo)")
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--output", type=Path, help="also save the complete JSON report here")
    parser.add_argument(
        "--timeout", type=float, default=60, help="timeout in seconds per Cargo command"
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    report: dict[str, Any] = {
        "schema": "hos2-rust-source-mutations-v1",
        "scope": "host Rust codec/canonical-request comparison; no kernel validation",
        "expected_tests_per_suite": EXPECTED_TEST_COUNT,
        "success": False,
        "baseline": None,
        "mutants": [],
        "errors": [],
    }
    try:
        crate = args.repo_root.resolve() / "libs/os-abi"
        inputs = {relative: (crate / relative).read_bytes() for relative in INPUTS}
        report["input_sha256"] = {
            relative: hashlib.sha256(content).hexdigest() for relative, content in inputs.items()
        }
        source = inputs["src/lib.rs"].decode("utf-8")
        # Preserve a rustup proxy symlink: resolving it would invoke rustup
        # under its own name instead of dispatching to Cargo.
        cargo = str(Path(args.cargo).absolute()) if os.sep in args.cargo else args.cargo
        with tempfile.TemporaryDirectory(prefix="hos2-rust-mutations-") as temporary:
            temporary_root = Path(temporary)
            baseline = run_suite(temporary_root / "baseline", inputs, source, cargo, args.timeout)
            report["baseline"] = baseline
            baseline["passed"] = bool(
                baseline["compiled"]
                and baseline["test"]["returncode"] == 0
                and baseline["tests"]["complete"]
                and baseline["tests"]["passed"] == EXPECTED_TEST_COUNT
                and baseline["tests"]["failed"] == 0
            )
            if not baseline["passed"]:
                report["errors"].append("production baseline did not pass all seven tests")
            else:
                for name, field, expected_test in MUTANTS:
                    mutant = run_suite(
                        temporary_root / name,
                        inputs,
                        mutated_source(source, field),
                        cargo,
                        args.timeout,
                    )
                    mutant.update(name=name, omitted_field=field, expected_failure=expected_test)
                    mutant["expected_test_failed"] = bool(
                        mutant["tests"]
                        and mutant["tests"]["cases"].get(expected_test) == "FAILED"
                    )
                    mutant["killed"] = bool(
                        mutant["compiled"]
                        and mutant["test"]["returncode"] == 101
                        and mutant["tests"]["complete"]
                        and mutant["expected_test_failed"]
                    )
                    report["mutants"].append(mutant)
                report["success"] = all(mutant["killed"] for mutant in report["mutants"])
                if not report["success"]:
                    report["errors"].append("a source mutant survived or lacked valid test evidence")
    except (OSError, UnicodeError, ValueError) as error:
        report["errors"].append(str(error))

    report["mutants_killed"] = sum(mutant["killed"] for mutant in report["mutants"])
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as error:
            print(f"cannot write report: {error}", file=sys.stderr)
            print(rendered, end="")
            return 1
    print(rendered, end="")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
