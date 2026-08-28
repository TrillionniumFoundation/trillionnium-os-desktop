#!/usr/bin/env python3
"""Reproducible compile-only gate for the pinned Servo embedder API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "trillionnium.desktop.servo-embedder-compatibility.v1"
MAX_SOURCE_REFERENCES = 12


class GateError(RuntimeError):
    pass


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--servo-root", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe-manifest", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=14_400)
    parser.add_argument("--skip-headed-reference-check", action="store_true")
    return parser.parse_args()


def run(
    command: list[str],
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "output": completed.stdout,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_log(root: Path, name: str, result: dict[str, Any]) -> None:
    (root / f"{name}.log").write_text(
        "$ " + " ".join(result["command"]) + "\n"
        + f"cwd={result['cwd']}\n"
        + f"returncode={result['returncode']}\n\n"
        + result["output"],
        encoding="utf-8",
    )


def load_requirements(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "trillionnium.desktop.servo-api-requirements.v1":
        raise GateError("unsupported requirements schema")
    commit = value.get("servo_commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise GateError("invalid pinned Servo commit")
    return value


def validate_checkout(
    servo_root: Path,
    requirements: dict[str, Any],
    timeout: int,
    logs: Path,
) -> dict[str, Any]:
    revision = run(["git", "rev-parse", "HEAD"], servo_root, timeout)
    write_log(logs, "git-revision", revision)
    if not revision["passed"]:
        raise GateError("cannot read Servo revision")
    actual = revision["output"].strip()
    expected = requirements["servo_commit"]
    if actual != expected:
        raise GateError(f"Servo revision {actual} does not match {expected}")

    status = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        servo_root,
        timeout,
    )
    write_log(logs, "git-status", status)
    if not status["passed"] or status["output"].strip():
        raise GateError("Servo tracked source is not clean")

    cargo_lock = servo_root / "Cargo.lock"
    component_manifest = servo_root / requirements["component_manifest"]
    if not cargo_lock.is_file() or not component_manifest.is_file():
        raise GateError("Servo Cargo lock or component manifest is missing")
    return {
        "repository": requirements["servo_repository"],
        "expected_commit": expected,
        "actual_commit": actual,
        "tracked_source_clean": True,
        "cargo_lock_sha256": sha256_file(cargo_lock),
        "component_manifest": str(component_manifest.relative_to(servo_root)),
        "component_manifest_sha256": sha256_file(component_manifest),
    }


def declarations(servo_root: Path, symbol: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        rf"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:unsafe\s+)?"
        rf"(struct|trait|enum|type)\s+{re.escape(symbol)}\b"
    )
    output: list[dict[str, Any]] = []
    for top in ("components", "ports"):
        base = servo_root / top
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.rs")):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                match = pattern.search(line)
                if match:
                    output.append(
                        {
                            "path": str(path.relative_to(servo_root)),
                            "line": number,
                            "kind": match.group(1),
                            "declaration": line.strip(),
                        }
                    )
    return output


def source_references(servo_root: Path, token: str) -> list[dict[str, Any]]:
    root = servo_root / "ports" / "servoshell"
    output: list[dict[str, Any]] = []
    if not root.exists():
        return output
    pattern = re.compile(rf"\b{re.escape(token)}\b")
    for path in sorted(root.rglob("*.rs")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if pattern.search(line):
                output.append(
                    {
                        "path": str(path.relative_to(servo_root)),
                        "line": number,
                        "text": line.strip()[:240],
                    }
                )
                if len(output) >= MAX_SOURCE_REFERENCES:
                    return output
    return output


def candidate_paths(
    servo_root: Path,
    symbol: str,
    symbol_declarations: list[dict[str, Any]],
) -> list[str]:
    candidates = [f"servo::{symbol}"]
    candidates.extend(
        f"servo::{module}::{symbol}"
        for module in (
            "webview",
            "servo",
            "rendering_context",
            "embedder_traits",
            "delegate",
            "windowing",
        )
    )
    for item in symbol_declarations:
        relative = Path(item["path"])
        try:
            module_file = relative.relative_to("components/servo")
        except ValueError:
            continue
        parts = list(module_file.parts)
        if parts[-1] == "lib.rs":
            module_parts: list[str] = []
        elif parts[-1] == "mod.rs":
            module_parts = parts[:-1]
        else:
            module_parts = [*parts[:-1], Path(parts[-1]).stem]
        if module_parts:
            candidates.append("servo::" + "::".join([*module_parts, symbol]))

    result: list[str] = []
    for candidate in candidates:
        if candidate not in result:
            result.append(candidate)
    return result


def create_probe(root: Path, servo_root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(
        "[package]\n"
        "name = \"trillionnium-servo-api-probe\"\n"
        "version = \"0.0.0\"\n"
        "edition = \"2024\"\n"
        "publish = false\n\n"
        "[dependencies]\n"
        + "servo = { path = "
        + json.dumps(str(servo_root / "components" / "servo"))
        + " }\n\n[workspace]\n",
        encoding="utf-8",
    )


def check_probe(
    root: Path,
    code: str,
    timeout: int,
    logs: Path,
    name: str,
) -> dict[str, Any]:
    (root / "src" / "main.rs").write_text(code, encoding="utf-8")
    result = run(
        [
            "cargo",
            "check",
            "--manifest-path",
            str(root / "Cargo.toml"),
            "--quiet",
        ],
        root,
        timeout,
        os.environ.copy(),
    )
    write_log(logs, name, result)
    return result


def probe_symbol(
    servo_root: Path,
    probe_root: Path,
    requirement: dict[str, Any],
    timeout: int,
    logs: Path,
) -> dict[str, Any]:
    name = requirement["name"]
    kind = requirement["kind"]
    found_declarations = declarations(servo_root, name)
    attempts: list[dict[str, Any]] = []
    for path in candidate_paths(servo_root, name, found_declarations):
        modes: list[tuple[str, str]] = []
        if kind in {"trait", "type_or_trait"}:
            modes.append(
                (
                    "trait_bound_declaration",
                    f"use {path} as Target;\n"
                    "fn require<T: Target>() {}\n"
                    "fn main() {}\n",
                )
            )
        if kind in {"type", "type_or_trait"}:
            modes.append(
                (
                    "sized_type_reference",
                    f"use {path} as Target;\n"
                    "fn require<T>() {}\n"
                    "fn main() { require::<Target>(); }\n",
                )
            )
        for mode, code in modes:
            log_name = re.sub(
                r"[^A-Za-z0-9_.-]+", "_", f"symbol-{name}-{path}-{mode}"
            )
            result = check_probe(probe_root, code, timeout, logs, log_name)
            attempts.append(
                {
                    "public_path": path,
                    "assertion_kind": mode,
                    "passed": result["passed"],
                }
            )
            if result["passed"]:
                return {
                    "name": name,
                    "requirement_kind": kind,
                    "public_path": path,
                    "assertion_kind": mode,
                    "definitions": found_declarations,
                    "servoshell_references": source_references(servo_root, name),
                    "attempts": attempts,
                    "passed": True,
                }
    return {
        "name": name,
        "requirement_kind": kind,
        "public_path": None,
        "assertion_kind": None,
        "definitions": found_declarations,
        "servoshell_references": source_references(servo_root, name),
        "attempts": attempts,
        "passed": False,
    }


def probe_method_group(
    probe_root: Path,
    group: dict[str, Any],
    symbols: dict[str, dict[str, Any]],
    required: bool,
    timeout: int,
    logs: Path,
) -> dict[str, Any]:
    owner = group["owner"]
    owner_path = symbols.get(owner, {}).get("public_path")
    attempts: list[dict[str, Any]] = []
    if owner_path is not None:
        for method in group["any_of"]:
            code = (
                f"use {owner_path} as Target;\n"
                f"fn main() {{ let _ = Target::{method}; }}\n"
            )
            name = re.sub(
                r"[^A-Za-z0-9_.-]+",
                "_",
                f"method-{group['label']}-{owner}-{method}",
            )
            result = check_probe(probe_root, code, timeout, logs, name)
            attempts.append({"method": method, "passed": result["passed"]})
            if result["passed"]:
                return {
                    "label": group["label"],
                    "owner": owner,
                    "required": required,
                    "selected_method": method,
                    "attempts": attempts,
                    "passed": True,
                }
    return {
        "label": group["label"],
        "owner": owner,
        "required": required,
        "selected_method": None,
        "attempts": attempts,
        "passed": False,
    }


def final_sentinel(
    symbol_results: list[dict[str, Any]],
    method_results: list[dict[str, Any]],
) -> str:
    lines = [
        "//! Compile-only public Servo embedder API sentinel.",
        "//!",
        "//! Generated for the exact pinned Servo source. It starts no runtime",
        "//! and opens no window, network connection, or listener.",
        "",
    ]
    aliases: dict[str, str] = {}
    for index, result in enumerate(symbol_results):
        if result["public_path"] is None:
            continue
        alias = f"Api{index}_{result['name']}"
        aliases[result["name"]] = alias
        lines.append(f"use {result['public_path']} as {alias};")
    lines.append("")
    for result in symbol_results:
        alias = aliases.get(result["name"])
        if alias is None:
            continue
        if result["assertion_kind"] == "trait_bound_declaration":
            lines.append(f"fn require_{result['name']}<T: {alias}>() {{}}")
        else:
            lines.append(f"fn require_{result['name']}<T>() {{}}")
    lines.extend(["", "fn main() {"])
    for result in symbol_results:
        alias = aliases.get(result["name"])
        if alias is None:
            continue
        if result["assertion_kind"] != "trait_bound_declaration":
            lines.append(f"    require_{result['name']}::<{alias}>();")
    for result in method_results:
        selected = result["selected_method"]
        if selected is not None:
            lines.append(f"    let _ = {aliases[result['owner']]}::{selected};")
    lines.extend(["}", ""])
    return "\n".join(lines)


def headed_package(
    servo_root: Path,
    requirements: dict[str, Any],
    timeout: int,
    logs: Path,
) -> tuple[str, list[dict[str, Any]]]:
    metadata = run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"],
        servo_root,
        timeout,
    )
    write_log(logs, "cargo-metadata", metadata)
    if not metadata["passed"]:
        raise GateError("Servo cargo metadata failed")
    packages = json.loads(metadata["output"])["packages"]
    inventory = [
        {
            "name": package["name"],
            "manifest_path": os.path.relpath(package["manifest_path"], servo_root),
            "targets": [target["name"] for target in package["targets"]],
        }
        for package in packages
        if "servo" in package["name"].lower()
        or "shell" in package["name"].lower()
    ]
    names = {package["name"] for package in packages}
    for preferred in requirements["headed_reference_package_preference"]:
        if preferred in names:
            return preferred, inventory
    for name in sorted(names):
        if "servoshell" in name.lower() or "servo-shell" in name.lower():
            return name, inventory
    raise GateError("headed Servo reference package not found")


def normalize_result_for_report(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": result["command"],
        "passed": result["passed"],
        "output_sha256": sha256_bytes(result["output"].encode("utf-8")),
    }


def main() -> int:
    options = args()
    servo_root = options.servo_root.resolve()
    requirements_path = options.requirements.resolve()
    output = options.output.resolve()
    requirements = load_requirements(requirements_path)

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    logs = output / "logs"
    logs.mkdir()

    source = validate_checkout(
        servo_root, requirements, options.timeout_seconds, logs
    )

    with tempfile.TemporaryDirectory(prefix="trillionnium-servo-probe-") as temp:
        probe_root = Path(temp)
        create_probe(probe_root, servo_root)
        symbol_results = [
            probe_symbol(
                servo_root,
                probe_root,
                requirement,
                options.timeout_seconds,
                logs,
            )
            for requirement in requirements["required_public_symbols"]
        ]
        symbol_map = {result["name"]: result for result in symbol_results}
        method_results = [
            probe_method_group(
                probe_root,
                group,
                symbol_map,
                True,
                options.timeout_seconds,
                logs,
            )
            for group in requirements["required_method_groups"]
        ]
        method_results.extend(
            probe_method_group(
                probe_root,
                group,
                symbol_map,
                False,
                options.timeout_seconds,
                logs,
            )
            for group in requirements.get("informational_method_groups", [])
        )
        sentinel = final_sentinel(symbol_results, method_results)
        final_result = check_probe(
            probe_root,
            sentinel,
            options.timeout_seconds,
            logs,
            "final-public-api-sentinel",
        )
        sentinel_path = output / "servo_api_sentinel.rs"
        sentinel_path.write_text(sentinel, encoding="utf-8")

    package, inventory = headed_package(
        servo_root, requirements, options.timeout_seconds, logs
    )
    if options.skip_headed_reference_check:
        headed = {
            "package": package,
            "command": None,
            "passed": False,
            "skipped": True,
        }
    else:
        raw_headed = run(
            ["cargo", "check", "-p", package, "--locked"],
            servo_root,
            options.timeout_seconds,
            os.environ.copy(),
        )
        write_log(logs, "headed-reference-cargo-check", raw_headed)
        headed = {
            "package": package,
            **normalize_result_for_report(raw_headed),
        }

    missing_symbols = [
        result["name"] for result in symbol_results if not result["passed"]
    ]
    missing_methods = [
        result["label"]
        for result in method_results
        if result["required"] and not result["passed"]
    ]
    passed = (
        not missing_symbols
        and not missing_methods
        and final_result["passed"]
        and headed["passed"]
    )
    report = {
        "schema": REPORT_SCHEMA,
        "status": "PASS" if passed else "HOLD",
        "qualification_scope": "compile_only_no_runtime_no_window_no_network",
        "requirements_sha256": sha256_file(requirements_path),
        "source": source,
        "public_symbols": symbol_results,
        "method_groups": method_results,
        "final_public_api_sentinel": {
            **normalize_result_for_report(final_result),
            "source": "servo_api_sentinel.rs",
            "source_sha256": sha256_file(sentinel_path),
        },
        "headed_reference": headed,
        "cargo_package_inventory": inventory,
        "missing_required_symbols": missing_symbols,
        "missing_required_method_groups": missing_methods,
        "non_claims": [
            "no Servo runtime was started",
            "no window or rendered frame was produced",
            "no native input or IME was exercised",
            "no WebDriver or public listener was started",
            "no Debian image was built or booted",
        ],
    }
    report_path = output / "servo-embedder-compat.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if options.probe_manifest is not None:
        options.probe_manifest.parent.mkdir(parents=True, exist_ok=True)
        options.probe_manifest.write_text(
            json.dumps(
                {
                    "schema": "trillionnium.desktop.servo-probe-result.v1",
                    "status": report["status"],
                    "servo_commit": source["actual_commit"],
                    "report_sha256": sha256_file(report_path),
                    "sentinel_sha256": sha256_file(sentinel_path),
                    "headed_reference_package": package,
                    "headed_reference_passed": headed["passed"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    if not passed:
        print(json.dumps(report, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as error:
        print(f"Servo compatibility HOLD: {error}", file=sys.stderr)
        raise SystemExit(2)
