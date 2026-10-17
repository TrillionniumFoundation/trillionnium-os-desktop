#!/usr/bin/env python3
"""Compile real Rust equality/encoder/validation mutants against host suites.

Only temporary copies of the crate are changed. A mutant is killed only when it
compiles successfully, its complete suite runs without skips, and the designated
regression fails. All five production baselines must pass first. Compiler errors,
timeouts and filtered tests never count as mutation kills. This checks host
codec/canonical-request coverage, not a kernel delivery ledger.
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
from typing import Any


EXPECTED_TEST_COUNT = 8
EXPECTED_SEMANTIC_TEST_COUNT = 12
EXPECTED_PROFILE_TEST_COUNT = 7
EXPECTED_SNAPSHOT_TEST_COUNT = 5
EXPECTED_NEGATIVE_TEST_COUNT = 21
EXPECTED_MUTANT_COUNT = 20
GENERATION_TEST = "same_sequence_and_slot_different_generation_is_conflict"
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
    "tests/semantic_edges.rs",
    "tests/profile_boundaries.rs",
    "tests/response_snapshot.rs",
    "tests/negative_vectors.rs",
)
FIXTURES = ("tests/golden/hos2.json", "tests/golden/hos2_edges.json")
SAVED_STATUS_TEST = "typed_terminal_rejection_encoders_match_all_independent_saved_status_bytes"
PROFILE_TESTS = (
    "query_abi_supported_operation_masks_match_documented_table",
    "query_abi_advertised_payload_minima_match_each_supported_profile",
    "query_abi_advertised_payload_limits_include_exact_maximum",
    "query_abi_page_sizes_accept_every_nonzero_power_of_two",
    "read_usage_accepts_zero_full_caps_and_exact_elapsed_consumption",
    "read_usage_accepts_aligned_windows_through_u64_max",
    "read_usage_rejects_impossible_or_misaligned_cpu_snapshots",
)
# These are independent changes to the same production source snapshot.
# The paired ReadUsage edits deliberately change both decoder and encoder
# validators so a shared regression cannot be caught only by round-tripping.
PROFILE_MUTANTS = (
    (
        "install_missing_history_dependencies",
        PROFILE_TESTS[0],
        ((
            "out.supported_ops & 0x08 != 0 && out.supported_ops & 0x34 != 0x34",
            "out.supported_ops & 0x08 != 0 && out.supported_ops & 0x04 != 0x04",
        ),),
    ),
    (
        "retire_accepts_read_instead_of_history",
        PROFILE_TESTS[0],
        ((
            "out.supported_ops & 0x20 != 0 && out.supported_ops & 0x10 == 0",
            "out.supported_ops & 0x20 != 0 && out.supported_ops & 0x14 == 0",
        ),),
    ),
    (
        "ignore_advertised_request_minimum",
        PROFILE_TESTS[1],
        ((
            "out.max_request_payload < min_request || out.max_response_payload < min_response",
            "out.max_response_payload < min_response",
        ),),
    ),
    (
        "read_usage_advertises_short_response",
        PROFILE_TESTS[1],
        ((
            "if out.supported_ops & 0x04 != 0 {\n"
            "        min_response = max_u32(min_response, 64);",
            "if out.supported_ops & 0x04 != 0 {\n"
            "        min_response = max_u32(min_response, 48);",
        ),),
    ),
    (
        "reject_zero_cpu_cap",
        PROFILE_TESTS[4],
        tuple(
            (
                f"|| {value}.active_cap_ns > {value}.active_period_ns",
                f"|| {value}.active_cap_ns > {value}.active_period_ns"
                f" || {value}.active_cap_ns == 0",
            )
            for value in ("out", "v")
        ),
    ),
    (
        "reject_full_period_cpu_cap",
        PROFILE_TESTS[4],
        tuple(
            (
                f"|| {value}.active_cap_ns > {value}.active_period_ns",
                f"|| {value}.active_cap_ns >= {value}.active_period_ns",
            )
            for value in ("out", "v")
        ),
    ),
    (
        "reject_exact_elapsed_cpu_consumption",
        PROFILE_TESTS[4],
        tuple(
            (
                f"|| {value}.window_consumed_ns > elapsed",
                f"|| {value}.window_consumed_ns >= elapsed",
            )
            for value in ("out", "v")
        ),
    ),
    (
        "accept_misaligned_cpu_window",
        PROFILE_TESTS[6],
        tuple(
            (
                f"|| {value}.window_start_ns != expected_start",
                f"|| {value}.window_start_ns > expected_start",
            )
            for value in ("out", "v")
        ),
    ),
    (
        "accept_cumulative_cpu_beyond_boot_elapsed",
        PROFILE_TESTS[6],
        tuple(
            (
                f"|| {value}.cumulative_cpu_ns > {value}.sample_boottime_ns",
                "|| false",
            )
            for value in ("out", "v")
        ),
    ),
)
# The new transport-bound response parser is security-critical: deliberately
# omit one guard at a time in *compiled production Rust*, then require the
# unchanged independently generated golden-byte suite to reject each variant.
# Do not count compilation failures, suite omissions or timeout as kills.
SNAPSHOT_TESTS = (
    "every_fixed_success_and_error_response_accepts_its_own_transport_bounds",
    "short_success_capacity_rejects_even_a_complete_64_byte_error_response",
    "unbounded_prefix_mutant_accepts_bytes_outside_advertised_copyout_capacity",
    "transport_descriptor_and_typed_request_must_describe_the_same_frame",
    "malformed_truncated_and_mismatched_responses_remain_rejected",
)
SNAPSHOT_MUTANTS = (
    (
        "ignore_transport_response_capacity",
        SNAPSHOT_TESTS[2],
        (("|| snapshot.len() > self.response_capacity as usize", "|| false"),),
    ),
    (
        "ignore_typed_request_frame_length",
        SNAPSHOT_TESTS[3],
        (("self.request_bytes as usize != expected_request_len",
          "self.request_bytes as usize != expected_request_len && false"),),
    ),
    (
        "ignore_success_capacity_for_error_reply",
        SNAPSHOT_TESTS[1],
        (("        self.ensure_success_response_capacity(request.opcode)?;\n"
          "        decode_response_prefix_for(snapshot, request)",
          "        decode_response_prefix_for(snapshot, request)"),),
    ),
    (
        "ignore_response_request_correlation",
        SNAPSHOT_TESTS[4],
        (("        decode_response_prefix_for(snapshot, request)",
          "        decode_response_prefix(snapshot)"),),
    ),
)


# The HOS2 write sequence and HOSR error statuses are fail-closed security
# boundaries. Change the actual Rust decoder, not a Python copy of the protocol.
# A real "kill" requires compile success and a complete designated Rust suite.
NEGATIVE_TESTS = (
    "install_response_echo_rejects_unordered_ids_in_success_and_failure",
    "malformed_frame_lengths_are_rejected_before_unknown_opcode_or_status",
)
NEGATIVE_MUTANTS = (
    (
        "ignore_sequence_id_high_half",
        NEGATIVE_TESTS[0],
        (("if !all_zero(&id[8..]) {",
          "if false && !all_zero(&id[8..]) {"),),
    ),
    (
        "accept_reserved_max_sequence",
        NEGATIVE_TESTS[0],
        (("let sequence = get_u64(id, 0);\n"
          "    if sequence == 0 || sequence == u64::MAX {",
          "let sequence = get_u64(id, 0);\n"
          "    if sequence == 0 {"),),
    ),
    (
        "treat_unknown_status_as_success",
        NEGATIVE_TESTS[1],
        (("_ => Err(Error::InvalidStatus)",
          "_ => Ok(Self::Ok)"),),
    ),
)


SUITES = {
    "mutation_kill": (
        EXPECTED_TEST_COUNT,
        tuple(expected for _, _, expected in MUTANTS) + (GENERATION_TEST,),
    ),
    "semantic_edges": (
        EXPECTED_SEMANTIC_TEST_COUNT,
        (
            SAVED_STATUS_TEST,
            "every_semantic_edge_encoder_matches_fixed_bytes_and_preserves_unused_capacity",
            "every_semantic_edge_encoder_rejects_each_short_capacity_without_writing",
        ),
    ),
    "profile_boundaries": (EXPECTED_PROFILE_TEST_COUNT, PROFILE_TESTS),
    "response_snapshot": (EXPECTED_SNAPSHOT_TEST_COUNT, SNAPSHOT_TESTS),
    "negative_vectors": (EXPECTED_NEGATIVE_TEST_COUNT, NEGATIVE_TESTS),
}


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


def mutated_saved_status_source(source: str) -> str:
    """Zero only QueryDelivery's encoded saved_status; fail if its shape changes."""
    original = (
        "        ResponsePayload::QueryDelivery(v) => {\n"
        "            put_u16(out, 0, v.state.as_u16());\n"
        "            put_u16(out, 2, v.saved_status.as_u16());"
    )
    if source.count(original) != 1:
        raise ValueError("expected exactly one QueryDelivery saved_status encoder")
    replacement = original.replace(
        "put_u16(out, 2, v.saved_status.as_u16());", "put_u16(out, 2, 0);"
    )
    return source.replace(original, replacement, 1)


def mutated_generation_source(source: str) -> str:
    """Omit only Request.target_generation from canonical equality."""
    pattern = re.compile(
        r"#\[derive\((?P<traits>[^)]+)\)\]\s*"
        r"pub struct Request\s*\{(?P<fields>[^}]+)\}"
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise ValueError("expected exactly one derived Request")
    match = matches[0]
    expected_fields = (
        "pub opcode: Opcode,",
        "pub request_id: [u8; 16],",
        "pub target_slot: u64,",
        "pub target_generation: u64,",
        "pub payload: RequestPayload,",
    )
    if tuple(line.strip() for line in match["fields"].splitlines() if line.strip()) != expected_fields:
        raise ValueError("Request fields changed; review the generation mutation")
    traits = [trait.strip() for trait in match["traits"].split(",")]
    if traits.count("PartialEq") != 1:
        raise ValueError("expected one derived Request PartialEq")
    traits.remove("PartialEq")
    replacement = (
        f"#[derive({', '.join(traits)})]\n"
        f"pub struct Request {{{match['fields']}}}\n\n"
        "impl PartialEq for Request {\n"
        "    fn eq(&self, other: &Self) -> bool {\n"
        "        self.opcode == other.opcode\n"
        "            && self.request_id == other.request_id\n"
        "            && self.target_slot == other.target_slot\n"
        "            && self.payload == other.payload\n"
        "    }\n"
        "}"
    )
    return source[: match.start()] + replacement + source[match.end() :]


def mutated_profile_source(source: str, changes: tuple[tuple[str, str], ...]) -> str:
    """Apply exact single-occurrence checks to one production snapshot."""
    changed = source
    for original, replacement in changes:
        if original == replacement or source.count(original) != 1 or changed.count(original) != 1:
            raise ValueError(f"expected exactly one unchanged profile check: {original!r}")
        changed = changed.replace(original, replacement, 1)
    return changed


def run_command(
    command: list[str], cwd: Path, timeout: float, env: dict[str, str]
) -> dict[str, Any]:
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


def suite_environment(base_env: dict[str, str], cwd: Path) -> dict[str, str]:
    """Keep one frozen toolchain selection for identity probes and Cargo runs."""
    env = base_env.copy()
    # Cargo's build.rustc and compiler wrappers can otherwise select a different
    # compiler from the one probed directly below. An empty wrapper overrides
    # Cargo configuration too; removing only the ambient variable is insufficient.
    for name in ("CARGO_BUILD_RUSTC", "CARGO_BUILD_RUSTC_WRAPPER",
                 "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER"):
        env.pop(name, None)
    env["RUSTC"] = env.get("RUSTC") or "rustc"
    env["RUSTC_WRAPPER"] = ""
    env["RUSTC_WORKSPACE_WRAPPER"] = ""
    env["CARGO_TARGET_DIR"] = str(cwd / "target")
    env["CARGO_TERM_COLOR"] = "never"
    env["CARGO_NET_OFFLINE"] = "true"
    return env


def executable_path(executable: str, cwd: Path, env: dict[str, str]) -> str | None:
    """Resolve relative commands/PATH entries as subprocess does in its cwd."""
    if os.sep in executable:
        path = Path(executable)
        candidate = str(path if path.is_absolute() else cwd / path)
        return shutil.which(candidate)
    search_path = os.pathsep.join(
        str(Path(entry) if Path(entry).is_absolute() else cwd / entry)
        for entry in env.get("PATH", os.defpath).split(os.pathsep)
    )
    return shutil.which(executable, path=search_path)


def toolchain_identity(
    cargo: str, cwd: Path, timeout: float, env: dict[str, str]
) -> dict[str, Any]:
    """Probe the compiler Cargo will use, from the suite's cwd and fixed env.

    Temporary crates do not inherit the repository's rust-toolchain.toml. In
    particular, an absolute path to a rustup proxy is not a toolchain pin.
    RUSTC is honored because callers may resolve a compiler with rustup which.
    Only the selection and executable paths are recorded, never the whole env.
    """
    rustc = env.get("RUSTC") or "rustc"
    cargo_probe = run_command([cargo, "--version"], cwd, timeout, env)
    rustc_probe = run_command([rustc, "-vV"], cwd, timeout, env)
    identity: dict[str, Any] = {
        "cwd": str(cwd),
        "effective_environment": {
            "RUSTUP_TOOLCHAIN": env.get("RUSTUP_TOOLCHAIN"),
            "RUSTC": env.get("RUSTC"),
            "RUSTC_WRAPPER": env.get("RUSTC_WRAPPER"),
            "RUSTC_WORKSPACE_WRAPPER": env.get("RUSTC_WORKSPACE_WRAPPER"),
        },
        "selection": "RUSTUP_TOOLCHAIN" if env.get("RUSTUP_TOOLCHAIN") else "rustup-default",
        "cargo_executable": cargo,
        "cargo_path": executable_path(cargo, cwd, env),
        "rustc_executable": rustc,
        "rustc_path": executable_path(rustc, cwd, env),
        "cargo": cargo_probe,
        "rustc": rustc_probe,
        "valid": False,
    }
    identity["valid"] = (
        all(
            probe["returncode"] == 0
            and not probe["timed_out"]
            and bool(probe["stdout"].strip())
            for probe in (cargo_probe, rustc_probe)
        )
        and bool(identity["cargo_path"] and identity["rustc_path"] and env.get("RUSTC"))
        and env.get("RUSTC_WRAPPER") == ""
        and env.get("RUSTC_WORKSPACE_WRAPPER") == ""
    )
    return identity


def same_toolchain(identity: dict[str, Any], reference: dict[str, Any]) -> bool:
    """Missing identity or a change in either executable/version fails closed."""
    return bool(
        identity["valid"]
        and reference["valid"]
        and all(
            identity[key] == reference[key]
            for key in (
                "effective_environment",
                "cargo_executable",
                "cargo_path",
                "rustc_executable",
                "rustc_path",
            )
        )
        and identity["cargo"]["stdout"].strip() == reference["cargo"]["stdout"].strip()
        and identity["rustc"]["stdout"].strip() == reference["rustc"]["stdout"].strip()
    )


def test_outcome(
    output: str, expected_count: int, required_tests: tuple[str, ...]
) -> dict[str, Any]:
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
        len(cases) == len(lines) == expected_count
        and counts["passed"] + counts["failed"] == expected_count
        and counts["ignored"] == counts["measured"] == counts["filtered_out"] == 0
        and sum(value == "ok" for value in cases.values()) == counts["passed"]
        and sum(value == "FAILED" for value in cases.values()) == counts["failed"]
        and all(expected in cases for expected in required_tests)
    )
    return result


def run_suite(
    directory: Path,
    inputs: dict[str, bytes],
    fixtures: dict[str, bytes],
    source: str,
    cargo: str,
    timeout: float,
    suite: str,
    base_env: dict[str, str],
    reference_identity: dict[str, Any],
) -> dict[str, Any]:
    directory.mkdir()
    crate = directory / "libs/os-abi"
    for relative, content in inputs.items():
        destination = crate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    for relative, content in fixtures.items():
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    (crate / "src/lib.rs").write_text(source, encoding="utf-8")
    expected_count, required_tests = SUITES[suite]
    command = [cargo, "test", "--offline", "--color", "never", "--test", suite]
    env = suite_environment(base_env, crate)
    identity = toolchain_identity(cargo, crate, timeout, env)
    result: dict[str, Any] = {
        "suite": suite,
        "expected_tests": expected_count,
        "required_tests": required_tests,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "toolchain_identity": identity,
        "toolchain_matches_reference": same_toolchain(identity, reference_identity),
        "compilation": None,
        "compiled": False,
        "test_toolchain_identity": None,
        "test": None,
        "tests": None,
    }
    if not result["toolchain_matches_reference"]:
        result["error"] = "toolchain identity missing, failed or differs from reference"
        return result
    compilation = run_command(command + ["--no-run"], crate, timeout, env)
    result["compilation"] = compilation
    result["compiled"] = compilation["returncode"] == 0 and not compilation["timed_out"]
    if result["compiled"]:
        test_identity = toolchain_identity(cargo, crate, timeout, env)
        result["test_toolchain_identity"] = test_identity
        if not same_toolchain(test_identity, reference_identity):
            result["toolchain_matches_reference"] = False
            result["compiled"] = False
            result["error"] = "toolchain identity changed between compilation and test"
            return result
        execution = run_command(command + ["--", "--test-threads=1"], crate, timeout, env)
        result["test"] = execution
        result["tests"] = test_outcome(execution["stdout"], expected_count, required_tests)
    return result


def baseline_passed(result: dict[str, Any]) -> bool:
    return bool(
        result["compiled"]
        and result["test"]
        and not result["test"]["timed_out"]
        and result["test"]["returncode"] == 0
        and result["tests"]
        and result["tests"]["complete"]
        and result["tests"]["passed"] == result["expected_tests"]
        and result["tests"]["failed"] == 0
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cargo", default="cargo", help="Cargo executable (default: cargo)")
    parser.add_argument(
        "--toolchain",
        default=os.environ.get("RUSTUP_TOOLCHAIN"),
        help="explicit RUSTUP_TOOLCHAIN for every probe/build/test (default: inherit env or rustup default)",
    )
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
    if args.toolchain is not None and not args.toolchain.strip():
        parser.error("--toolchain must not be empty")

    report: dict[str, Any] = {
        "schema": "hos2-rust-source-mutations-v5",
        "scope": (
            "host Rust canonical equality, fixed-byte response encoding and "
            "documented QueryAbi/ReadUsage and transport-bound response boundaries; "
            "each mutant runs its designated complete suite, not the entire crate; "
            "no kernel validation"
        ),
        "source_policy": "every mutant is derived independently from one captured production source",
        "expected_mutants": EXPECTED_MUTANT_COUNT,
        "expected_tests_by_suite": {
            suite: expected for suite, (expected, _) in SUITES.items()
        },
        "success": False,
        "requested_toolchain": args.toolchain,
        "reference_toolchain_identity": None,
        "baseline": None,
        "baseline_semantic_edges": None,
        "baseline_profile_boundaries": None,
        "baseline_response_snapshot": None,
        "baseline_negative_vectors": None,
        "mutants": [],
        "errors": [],
    }
    try:
        repo_root = args.repo_root.resolve()
        crate = repo_root / "libs/os-abi"
        inputs = {relative: (crate / relative).read_bytes() for relative in INPUTS}
        fixtures = {relative: (repo_root / relative).read_bytes() for relative in FIXTURES}
        report["input_sha256"] = {
            relative: hashlib.sha256(content).hexdigest() for relative, content in inputs.items()
        }
        report["fixture_sha256"] = {
            relative: hashlib.sha256(content).hexdigest() for relative, content in fixtures.items()
        }
        source = inputs["src/lib.rs"].decode("utf-8")
        # Preserve a rustup proxy symlink: resolving it would invoke rustup
        # under its own name instead of dispatching to Cargo.
        cargo = str(Path(args.cargo).absolute()) if os.sep in args.cargo else args.cargo
        base_env = os.environ.copy()
        if args.toolchain is not None:
            base_env["RUSTUP_TOOLCHAIN"] = args.toolchain
        with tempfile.TemporaryDirectory(prefix="hos2-rust-mutations-") as temporary:
            temporary_root = Path(temporary)
            reference_directory = temporary_root / "toolchain-reference"
            reference_directory.mkdir()
            reference_identity = toolchain_identity(
                cargo,
                reference_directory,
                args.timeout,
                suite_environment(base_env, reference_directory),
            )
            report["reference_toolchain_identity"] = reference_identity
            if not reference_identity["valid"]:
                raise ValueError("reference toolchain identity is missing or failed")
            for suite, baseline_key in (
                ("mutation_kill", "baseline"),
                ("semantic_edges", "baseline_semantic_edges"),
                ("profile_boundaries", "baseline_profile_boundaries"),
                ("response_snapshot", "baseline_response_snapshot"),
                ("negative_vectors", "baseline_negative_vectors"),
            ):
                baseline = run_suite(
                    temporary_root / baseline_key,
                    inputs,
                    fixtures,
                    source,
                    cargo,
                    args.timeout,
                    suite,
                    base_env,
                    reference_identity,
                )
                baseline["passed"] = baseline_passed(baseline)
                report[baseline_key] = baseline
                if not baseline["passed"]:
                    report["errors"].append(
                        f"production {suite} baseline did not pass its complete suite"
                    )
            if not report["errors"]:
                mutations = [
                    (
                        name,
                        "mutation_kill",
                        {"omitted_field": field},
                        expected_test,
                        mutated_source(source, field),
                    )
                    for name, field, expected_test in MUTANTS
                ]
                mutations.append(
                    (
                        "ignore_target_generation",
                        "mutation_kill",
                        {"omitted_field": "Request.target_generation"},
                        GENERATION_TEST,
                        mutated_generation_source(source),
                    )
                )
                mutations.append(
                    (
                        "zero_saved_status",
                        "semantic_edges",
                        {"zeroed_field": "saved_status"},
                        SAVED_STATUS_TEST,
                        mutated_saved_status_source(source),
                    )
                )
                mutations.extend(
                    (
                        name,
                        "profile_boundaries",
                        {"changed_checks": changes},
                        expected_test,
                        mutated_profile_source(source, changes),
                    )
                    for name, expected_test, changes in PROFILE_MUTANTS
                )
                mutations.extend(
                    (
                        name,
                        "response_snapshot",
                        {"changed_checks": changes},
                        expected_test,
                        mutated_profile_source(source, changes),
                    )
                    for name, expected_test, changes in SNAPSHOT_MUTANTS
                )
                mutations.extend(
                    (
                        name,
                        "negative_vectors",
                        {"changed_checks": changes},
                        expected_test,
                        mutated_profile_source(source, changes),
                    )
                    for name, expected_test, changes in NEGATIVE_MUTANTS
                )
                if len(mutations) != EXPECTED_MUTANT_COUNT:
                    raise ValueError("mutation count changed without updating the expected total")
                for name, suite, mutation, expected_test, changed_source in mutations:
                    mutant = run_suite(
                        temporary_root / name,
                        inputs,
                        fixtures,
                        changed_source,
                        cargo,
                        args.timeout,
                        suite,
                        base_env,
                        reference_identity,
                    )
                    mutant.update(name=name, expected_failure=expected_test, **mutation)
                    mutant["expected_test_failed"] = bool(
                        mutant["tests"]
                        and mutant["tests"]["cases"].get(expected_test) == "FAILED"
                    )
                    mutant["killed"] = bool(
                        mutant["compiled"]
                        and not mutant["test"]["timed_out"]
                        and mutant["test"]["returncode"] == 101
                        and mutant["tests"]["complete"]
                        and mutant["expected_test_failed"]
                    )
                    report["mutants"].append(mutant)
                report["success"] = (
                    len(report["mutants"]) == EXPECTED_MUTANT_COUNT
                    and all(mutant["killed"] for mutant in report["mutants"])
                )
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
