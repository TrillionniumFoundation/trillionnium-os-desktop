#!/usr/bin/env python3
"""Reproduce A02 host acceptance in an isolated, fixed-toolchain source snapshot.

This runs the existing codec, golden generators and mutation runner. It does not
install tools, change the source checkout, or validate a kernel driver.
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
import time
from typing import Any


SOURCE_ROOTS = ("libs/os-abi", "tests/golden", "tests/abi")
EXTRA_INPUTS = ("README.md", "support/upstream-lock.json")
EXCLUDED = {"target", "__pycache__", ".pytest_cache"}
CHECK_NAMES = (
    "golden_hos2", "golden_edges", "golden_transport", "python_discovery",
    "python", "python_optimized", "python_mutations", "rust_discovery", "rust",
    "rustfmt", "clippy", "bare_no_std", "compiled_mutations",
)
TOOLS = ("cargo", "rustc", "rustdoc", "rustfmt", "clippy-driver")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selected_inputs(repo: Path) -> dict[str, bytes]:
    """Capture regular inputs; refuse links instead of copying outside the tree."""
    captured: dict[str, bytes] = {}
    for relative in SOURCE_ROOTS:
        root = repo / relative
        if any(path.is_symlink() for path in (root, *root.parents) if path != repo and repo in path.parents) or not root.is_dir():
            raise ValueError(f"missing or linked input directory: {relative}")
        for current, directories, files in os.walk(root, followlinks=False):
            for name in list(directories):
                child = Path(current) / name
                if child.is_symlink():
                    raise ValueError(f"linked input directory: {child.relative_to(repo)}")
                if name in EXCLUDED:
                    directories.remove(name)
            for name in files:
                child = Path(current) / name
                if child.is_symlink() or not child.is_file():
                    raise ValueError(f"nonregular input: {child.relative_to(repo)}")
                relative_path = child.relative_to(repo)
                # Historical evidence is not executable input. Check its file
                # type above, but avoid recursive reports and growing snapshots.
                if (relative_path.parts[:3] == ("tests", "abi", "results")
                        or (relative_path.parent == Path("tests/abi")
                            and name.startswith("A02") and child.suffix == ".md")):
                    continue
                # Cargo generates its own dependency-free lock in the snapshot.
                if name == "Cargo.lock" or name.endswith((".pyc", ".pyo")):
                    continue
                captured[str(relative_path)] = child.read_bytes()
    for relative in EXTRA_INPUTS:
        path = repo / relative
        if any(parent.is_symlink() for parent in (path, *path.parents) if parent != repo and repo in parent.parents) or not path.is_file():
            raise ValueError(f"missing or nonregular input: {relative}")
        captured[relative] = path.read_bytes()
    return dict(sorted(captured.items()))


def snapshot_inputs(inputs: dict[str, bytes], destination: Path) -> None:
    destination.mkdir()
    for relative, data in inputs.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for relative in EXTRA_INPUTS:
        (destination / relative).chmod(0o444)


def selected_toolchain(inputs: dict[str, bytes], override: str | None) -> str:
    pin = json.loads(inputs["support/upstream-lock.json"])["kernel"]["toolchain"]
    if not isinstance(pin, str) or not pin.strip() or pin != pin.strip():
        raise ValueError("upstream kernel.toolchain must be a nonempty string")
    chosen = pin if override is None else override
    if not chosen or chosen != chosen.strip() or chosen.startswith("-"):
        raise ValueError("invalid toolchain name")
    return chosen


def run_command(argv: list[str], cwd: Path, env: dict[str, str], timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "argv": argv, "cwd": str(cwd), "returncode": None,
        "stdout": "", "stderr": "", "timed_out": False, "timeout_seconds": timeout,
    }
    try:
        completed = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                                   text=True, timeout=timeout, check=False)
        result.update(returncode=completed.returncode, stdout=completed.stdout,
                      stderr=completed.stderr)
    except subprocess.TimeoutExpired as error:
        def decoded(value: str | bytes | None) -> str:
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        result.update(timed_out=True, stdout=decoded(error.stdout), stderr=decoded(error.stderr),
                      error=f"command exceeded {timeout:g} seconds")
    except OSError as error:
        result["error"] = str(error)
    result["elapsed_seconds"] = round(time.monotonic() - started, 6)
    result["passed"] = result["returncode"] == 0 and not result["timed_out"]
    return result


# Acceptance must not trust a child mutation runner that silently lowers its
# denominator while reporting success=true. Keep this version/count explicit
# and revise it when the real compiled-source mutation set changes.
PINNED_MUTATION_SCHEMA = "hos2-rust-source-mutations-v6"
EXPECTED_COMPILED_MUTANTS = 20


def run_compiled_mutations(python: str, cargo: str, toolchain: str, snapshot: Path,
                           env: dict[str, str], command_timeout: float,
                           batch_timeout: float, mutation_path: Path) -> dict[str, Any]:
    """Bound the complete batch separately from each nested compiler command."""
    result = run_command(
        [python, "-B", "tests/abi/run_rust_mutations.py", "--cargo", cargo,
         "--toolchain", toolchain, "--repo-root", str(snapshot),
         "--output", str(mutation_path), "--timeout", str(command_timeout)],
        snapshot, env, batch_timeout)
    result.update(name="compiled_mutations", cargo_timeout_seconds=command_timeout)
    if mutation_path.is_file():
        mutation = json.loads(mutation_path.read_text())
        result["mutation_report"] = str(mutation_path)
        result["mutants_killed"] = mutation.get("mutants_killed")
        result["expected_mutants"] = mutation.get("expected_mutants")
        result["passed"] = (
            result["passed"]
            and mutation.get("success") is True
            and mutation.get("schema") == PINNED_MUTATION_SCHEMA
            and type(mutation.get("expected_mutants")) is int
            and mutation["expected_mutants"] == EXPECTED_COMPILED_MUTANTS
            and type(mutation.get("mutants_killed")) is int
            and mutation["mutants_killed"] == EXPECTED_COMPILED_MUTANTS
        )
    else:
        result["passed"] = False
        result["error"] = "compiled mutation report was not produced"
    return result


def python_outcome(output: str, expected: list[str]) -> dict[str, Any]:
    summaries = re.findall(r"^Ran (\d+) tests? in .+$", output, re.MULTILINE)
    lines = re.findall(r"^\S+ \(([^)]+)\) \.\.\. (.+)$", output, re.MULTILINE)
    cases = dict(lines)
    complete = (len(summaries) == 1 and int(summaries[0]) == len(expected)
                and len(lines) == len(cases) == len(expected)
                and set(cases) == set(expected) and all(value == "ok" for value in cases.values())
                and re.search(r"^OK$", output, re.MULTILINE) is not None)
    return {"expected": len(expected), "actual": int(summaries[0]) if len(summaries) == 1 else None,
            "cases": cases, "complete": complete}


def rust_outcome(output: str, expected: list[str]) -> dict[str, Any]:
    summaries = re.findall(
        r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; "
        r"(\d+) measured; (\d+) filtered out;", output, re.MULTILINE)
    lines = re.findall(r"^test (.*?) \.\.\. (ok|FAILED|ignored)$", output, re.MULTILINE)
    cases = dict(lines)
    counts = {key: 0 for key in ("passed", "failed", "ignored", "measured", "filtered_out")}
    for _, *values in summaries:
        for key, value in zip(counts, values):
            counts[key] += int(value)
    complete = (bool(summaries) and len(lines) == len(cases) == len(expected)
                and set(cases) == set(expected) and all(value == "ok" for value in cases.values())
                and counts["passed"] == len(expected)
                and all(counts[key] == 0 for key in counts if key != "passed")
                and all(summary[0] == "ok" for summary in summaries))
    return {"expected": len(expected), "cases": cases, **counts, "complete": complete}


PYTHON_DISCOVERY = """import json, sys, unittest
loader = unittest.TestLoader()
suite = loader.discover('tests/abi', pattern='test_*.py')
def flatten(item):
    if isinstance(item, unittest.TestSuite):
        return [name for child in item for name in flatten(child)]
    return [item.id()]
names = flatten(suite)
if loader.errors or not names or len(set(names)) != len(names):
    print(json.dumps({'errors': loader.errors, 'tests': names})); sys.exit(1)
print(json.dumps(names))
"""


def execute(args: argparse.Namespace, report: dict[str, Any], output: Path) -> None:
    repo = args.repo_root.resolve()
    if any(output == repo / relative or (repo / relative) in output.parents for relative in SOURCE_ROOTS):
        raise ValueError("output-dir must be outside A02 source/test/fixture directories")
    before = selected_inputs(repo)
    hashes = {name: digest(data) for name, data in before.items()}
    report.update(repo_root=str(repo), input_sha256=hashes,
                  fixture_sha256={name: value for name, value in hashes.items() if name.startswith("tests/golden/")},
                  original_inputs_unchanged=False, readme_bytes=len(before["README.md"]))
    if before["README.md"]:
        raise ValueError("root README.md must be zero bytes")
    snapshot = output / "snapshot"
    snapshot_inputs(before, snapshot)
    report["snapshot_root"] = str(snapshot)
    try:
        toolchain = selected_toolchain(before, args.toolchain)
        report["toolchain"] = toolchain
        report["toolchain_override"] = args.toolchain is not None
        env = os.environ.copy()
        for name in ("CARGO_BUILD_RUSTC", "CARGO_BUILD_RUSTC_WRAPPER",
                     "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS",
                     "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "CARGO_BUILD_TARGET"):
            env.pop(name, None)
        env.update(RUSTUP_TOOLCHAIN=toolchain, CARGO_NET_OFFLINE="true",
                   CARGO_TERM_COLOR="never", PYTHONDONTWRITEBYTECODE="1",
                   RUSTC_WRAPPER="", RUSTC_WORKSPACE_WRAPPER="",
                   CARGO_TARGET_DIR=str(output / "target"))
        rustup = shutil.which(args.rustup)
        if rustup is None:
            raise ValueError(f"rustup executable unavailable: {args.rustup}; no installation or fallback attempted")
        report["rustup"] = {"path": rustup, "sha256": digest(Path(rustup).read_bytes())}
        tool_paths: dict[str, str] = {}
        report["tool_resolution"] = []
        for name in TOOLS:
            resolution = run_command([rustup, "which", "--toolchain", toolchain, name], snapshot, env, args.timeout)
            report["tool_resolution"].append(resolution)
            if not resolution["passed"]:
                raise ValueError(f"fixed-toolchain executable unavailable: {name}")
            path = Path(resolution["stdout"].strip())
            if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
                raise ValueError(f"rustup returned a non-executable path for {name}")
            tool_paths[name] = str(path.resolve())
        env.update(RUSTC=tool_paths["rustc"], RUSTDOC=tool_paths["rustdoc"],
                   PATH=str(Path(tool_paths["cargo"]).parent) + os.pathsep + env.get("PATH", ""))
        report["environment"] = {name: env.get(name) for name in (
            "RUSTUP_TOOLCHAIN", "RUSTUP_HOME", "CARGO_HOME", "RUSTC", "RUSTDOC",
            "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
            "CARGO_TARGET_DIR", "CARGO_NET_OFFLINE", "PYTHONDONTWRITEBYTECODE", "PATH")}
        report["executables"] = {}
        for name, path in tool_paths.items():
            version = run_command([path, "-Vv" if name in ("cargo", "rustc") else "--version"],
                                  snapshot, env, args.timeout)
            report["executables"][name] = {"path": path, "sha256": digest(Path(path).read_bytes()), "version": version}
            if not version["passed"]:
                raise ValueError(f"could not identify fixed executable: {name}")

        def check(name: str, argv: list[str]) -> dict[str, Any]:
            result = run_command(argv, snapshot, env, args.timeout)
            result["name"] = name
            report["checks"].append(result)
            return result

        python = sys.executable
        report["python"] = {"path": python, "version": sys.version,
                            "sha256": digest(Path(python).read_bytes())}
        for name, filename, fixture in (
            ("golden_hos2", "generate_hos2.py", "hos2.json"),
            ("golden_edges", "generate_hos2_edges.py", "hos2_edges.json"),
            ("golden_transport", "generate_transport32.py", "transport32.hex"),
        ):
            result = check(name, [python, "-B", f"tests/golden/{filename}", "--check"])
            result["vectors"] = (1 if fixture.endswith(".hex") else
                                 len(json.loads(before[f"tests/golden/{fixture}"])["vectors"]))
        discovery = check("python_discovery", [python, "-B", "-c", PYTHON_DISCOVERY])
        expected_python: list[str] = []
        if discovery["passed"]:
            try:
                expected_python = json.loads(discovery["stdout"])
                if (not isinstance(expected_python, list) or not expected_python
                        or not all(isinstance(name, str) for name in expected_python)
                        or len(set(expected_python)) != len(expected_python)):
                    raise ValueError("invalid Python test discovery")
            except (ValueError, TypeError):
                discovery["passed"] = False
        report["discovered_python_tests"] = expected_python
        for name, optimization, pattern in (
            ("python", [], "test_*.py"),
            ("python_optimized", ["-O"], "test_*.py"),
            ("python_mutations", [], "test_mutations.py"),
        ):
            result = check(name, [python, "-B", *optimization, "-m", "unittest", "discover",
                                  "-s", "tests/abi", "-p", pattern, "-v"])
            expected = ([test for test in expected_python if test.startswith("test_mutations.")]
                        if name == "python_mutations" else expected_python)
            result["tests"] = python_outcome(result["stdout"] + result["stderr"], expected)
            result["passed"] = result["passed"] and bool(expected) and result["tests"]["complete"]
        cargo = tool_paths["cargo"]
        manifest = "libs/os-abi/Cargo.toml"
        discovery = check("rust_discovery", [cargo, "test", "--offline", "--manifest-path", manifest, "--", "--list"])
        expected_rust = re.findall(r"^(.+): test$", discovery["stdout"], re.MULTILINE)
        discovery["passed"] = (discovery["passed"] and bool(expected_rust)
                                and len(set(expected_rust)) == len(expected_rust))
        report["discovered_rust_tests"] = expected_rust
        result = check("rust", [cargo, "test", "--offline", "--manifest-path", manifest])
        result["tests"] = rust_outcome(result["stdout"], expected_rust)
        result["passed"] = result["passed"] and discovery["passed"] and result["tests"]["complete"]
        check("rustfmt", [cargo, "fmt", "--manifest-path", manifest, "--", "--check"])
        check("clippy", [cargo, "clippy", "--offline", "--manifest-path", manifest, "--all-targets", "--", "-D", "warnings"])
        check("bare_no_std", [cargo, "check", "--offline", "--manifest-path", manifest,
                              "--no-default-features", "--target", "x86_64-unknown-none"])
        mutation_path = output / "mutations.json"
        report["checks"].append(run_compiled_mutations(
            python, cargo, toolchain, snapshot, env, args.timeout,
            args.mutation_timeout, mutation_path))
    finally:
        after = {name: digest(data) for name, data in selected_inputs(repo).items()}
        report["original_input_sha256_after"] = after
        report["original_inputs_unchanged"] = hashes == after


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--rustup", default="rustup", help="existing rustup executable; never installs tools")
    parser.add_argument("--toolchain", help="explicit override; default is upstream-lock kernel.toolchain")
    parser.add_argument("--output-dir", type=Path, required=True, help="new output directory, outside A02 input trees")
    parser.add_argument("--timeout", type=float, default=60, help="seconds per command, greater than 0 and at most 60")
    parser.add_argument("--mutation-timeout", type=float, default=900,
                        help="seconds for the complete compiled mutation batch (default: 900, maximum: 3600)")
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 60:
        parser.error("--timeout must be greater than 0 and at most 60 seconds")
    if not args.timeout <= args.mutation_timeout <= 3600:
        parser.error("--mutation-timeout must be at least --timeout and at most 3600 seconds")
    output = args.output_dir.resolve()
    repo = args.repo_root.resolve()
    if any(output == repo / relative or (repo / relative) in output.parents for relative in SOURCE_ROOTS):
        print("output-dir must be outside A02 source/test/fixture directories", file=sys.stderr)
        return 1
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        print(f"cannot create new output directory: {error}", file=sys.stderr)
        return 1
    output = output.resolve()
    report: dict[str, Any] = {"schema": "hos2-a02-host-acceptance-v1", "scope": "host codec; no kernel validation",
                              "success": False, "checks": [], "errors": [], "timeout_seconds": args.timeout,
                              "mutation_timeout_seconds": args.mutation_timeout}
    try:
        execute(args, report, output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report["errors"].append(str(error))
    observed = {check["name"] for check in report["checks"]}
    report["not_executed"] = [name for name in CHECK_NAMES if name not in observed]
    report["success"] = (not report["errors"] and not report["not_executed"]
                         and report.get("original_inputs_unchanged") is True
                         and report.get("readme_bytes") == 0
                         and len(report["checks"]) == len(CHECK_NAMES)
                         and all(check["passed"] for check in report["checks"]))
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"success": report["success"], "report": str(output / "report.json"),
                      "errors": report["errors"], "not_executed": report["not_executed"]}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
