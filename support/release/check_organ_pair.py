#!/usr/bin/env python3
"""Verify one reviewed source pair, then optionally build and test its host lane."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

SPEC = importlib.util.spec_from_file_location(
    "organ_release_profile", Path(__file__).with_name("organ_release_profile.py"))
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


def host_steps(os_root, hepta_root, offline, hepta_profile="dev-small", schema_version=1):
    """Commands are code-owned; a manifest cannot inject an executable or flags."""
    network = ["--offline"] if offline else []
    owning_packages = ["codex-hepta-agentd", "codex-hepta-memory", "codex-hepta-cognitive-store"]
    if schema_version in (3, 4):
        owning_packages += ["codex-hepta-contracts", "codex-state",
                            "codex-hepta-agent-protocol", "codex-hepta-learning-ledger",
                            "codex-git-utils", "codex-hepta-memory-extension",
                            "codex-hepta-automation", "codex-hepta-fleet", "codex-hepta-supervisor",
                            "codex-arg0"]
    if schema_version == 4:
        owning_packages += ["codex-app-server-protocol", "codex-thread-store", "codex-core-plugins",
                            "codex-rollout", "codex-file-system"]
    package_flags = [flag for package in owning_packages for flag in ("-p", package)]
    steps = [
        ("ui-build", os_root, "1.88.0",
         ["cargo", "build", "--manifest-path", "ui/Cargo.toml", "--workspace",
          "--bins", "--locked", *network]),
        ("ui-tests", os_root, "1.88.0",
         ["cargo", "test", "--manifest-path", "ui/Cargo.toml", "--workspace",
          "--locked", *network]),
        ("adapter-tests", os_root, "1.88.0",
         ["cargo", "test", "--manifest-path", "services/hepta-os/Cargo.toml",
          "--features", "cpu-history", "--locked", *network]),
        ("hepta-build", hepta_root, "1.95.0",
         ["cargo", "build", "--manifest-path", "codex-rs/Cargo.toml",
          "-p", "codex-hepta-agentd", "--bin", "codex-hepta-agentd",
          "--profile", hepta_profile, "--locked", *network]),
        ("hepta-tests", hepta_root, "1.95.0",
         ["just", "test", "--locked", *network, *package_flags,
          "--test-threads", "2", "--retries", "0", "--cargo-profile", hepta_profile]),
    ]
    if schema_version in (3, 4):
        steps.insert(4, ("hepta-root-build", hepta_root, "1.95.0",
                         ["cargo", "build", "--manifest-path", "codex-rs/Cargo.toml",
                          "-p", "codex-hepta-agentd", "--bin", "hepta-authority-host",
                          "--profile", hepta_profile, "--locked", *network]))
        steps.insert(5, ("hepta-recovery-build", hepta_root, "1.95.0",
                         ["cargo", "build", "--manifest-path", "codex-rs/Cargo.toml",
                          "-p", "codex-hepta-supervisor", "--bin", "hepta-supervisor-intent-recovery",
                          "--profile", hepta_profile, "--locked", *network]))
    return steps


def execute_step(step, output, environment, timeout, targets=None):
    name, cwd, toolchain, argv = step
    log_path = output / f"{name}.log"
    target_name = "hepta" if name.startswith("hepta-") else "desktop"
    target = targets[target_name] if targets else output / f"{target_name}-target"
    env = dict(environment, RUSTUP_TOOLCHAIN=toolchain,
               CARGO_TARGET_DIR=str(target),
               CARGO_INCREMENTAL="0",
               CARGO_BUILD_JOBS=environment.get("CARGO_BUILD_JOBS", "2"))
    started = time.monotonic()
    record = {"name": name, "argv": argv, "toolchain": toolchain,
              "log": log_path.name, "exit_code": None}
    with log_path.open("xb") as stream:
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                record["exit_code"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record["error"] = "step_timeout"
                # Bound only this invocation and its children; never select by name.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        except OSError as exc:
            record["error"] = str(exc)
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    record["log_sha256"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
    return record


def output_directory(path, repositories):
    target = Path(path).resolve()
    if any(target.is_relative_to(repo.path) for repo in repositories):
        raise profile.ProfileError("output directory must be outside both source repositories")
    try:
        target.mkdir(mode=0o700)
    except OSError as exc:
        raise profile.ProfileError(f"require a new output directory: {exc}") from exc
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--os-repo", required=True)
    parser.add_argument("--hepta-repo", required=True)
    parser.add_argument("--os-head", required=True)
    parser.add_argument("--os-tree", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--required-schema", type=int, choices=(1, 2, 3, 4),
                        help="require one schema for a current release; historical verification otherwise remains available")
    parser.add_argument("--output-dir", required=True)
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--execute-host", action="store_true",
                        help="build/test the real host packages; never enables production authority")
    execution.add_argument("--build-host", action="store_true",
                           help="build real host binaries only; never claims test qualification")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--desktop-target-dir", help="optional existing external Cargo cache")
    parser.add_argument("--hepta-target-dir", help="optional existing external Cargo cache")
    parser.add_argument("--hepta-profile", choices=("dev-small", "dev"), default="dev-small",
                        help="recorded original Cargo profile; dev can reuse an existing test cache")
    parser.add_argument("--step-timeout", type=int, default=3600)
    args = parser.parse_args(argv)
    if not 1 <= args.step_timeout <= 14_400:
        parser.error("step timeout must be 1..14400 seconds")
    receipt = {"schema_version": 1, "qualification": "none", "steps": [],
               "production_authority": "not_configured_by_this_tool",
               "notes_runtime": "not_run_by_this_tool", "native_kernel": "not_run_by_this_tool"}
    output = None
    try:
        os_repo = profile.Repository(args.os_repo, "os")
        hepta_repo = profile.Repository(args.hepta_repo, "hepta")
        if os_repo.path == hepta_repo.path:
            raise profile.ProfileError("os and hepta must be distinct repository roots")
        raw_manifest = Path(args.manifest).read_bytes()
        manifest = profile.load_json_bytes(raw_manifest, args.manifest)
        if not isinstance(manifest, dict):
            raise profile.ProfileError("manifest must be an object")
        if args.required_schema is not None and manifest.get("schema_version") != args.required_schema:
            raise profile.ProfileError(f"current release requires schema {args.required_schema}")
        mapping = profile.load_json(os_repo.path / "support/release" /
                                    profile.source_map_name(manifest.get("schema_version")))
        before = profile.verify_manifest(manifest, os_repo, hepta_repo, args.os_head,
                                         args.os_tree, mapping)
        output = output_directory(args.output_dir, (os_repo, hepta_repo))
        (output / "source-manifest.json").write_bytes(raw_manifest)
        targets = {}
        for name, supplied in (("desktop", args.desktop_target_dir), ("hepta", args.hepta_target_dir)):
            target = Path(supplied).resolve() if supplied else output / f"{name}-target"
            if any(target.is_relative_to(repo.path) for repo in (os_repo, hepta_repo)):
                raise profile.ProfileError("Cargo target directories must be outside both source repositories")
            targets[name] = target
        receipt["source"] = before
        receipt["cargo_targets"] = {name: str(path) for name, path in targets.items()}
        receipt["manifest_sha256"] = profile.sha256(raw_manifest)
        receipt["qualification"] = "source-only"
        if args.execute_host or args.build_host:
            receipt["qualification"] = "none"
            receipt["passed"] = False
            (output / "pair-receipt.json").write_bytes(profile.canonical(receipt))
            for step in host_steps(os_repo.path, hepta_repo.path, args.offline, args.hepta_profile,
                                   manifest["schema_version"]):
                if args.build_host and not step[0].endswith("-build"):
                    continue
                print(f"Running {step[0]}; log: {output / (step[0] + '.log')}", flush=True)
                result = execute_step(step, output, os.environ, args.step_timeout, targets)
                receipt["steps"].append(result)
                (output / "pair-receipt.json").write_bytes(profile.canonical(receipt))
                if result["exit_code"] != 0:
                    raise profile.ProfileError(f"host step failed: {step[0]}")
            # A build may run generators. Reject any resulting source/lock drift.
            after = profile.verify_manifest(manifest, os_repo, hepta_repo, args.os_head,
                                            args.os_tree, mapping)
            if before != after:
                raise profile.ProfileError("source identity changed during host execution")
            receipt["qualification"] = "host-builds" if args.build_host else "host-build-tests"
        receipt["passed"] = True
        return_code = 0
    except (profile.ProfileError, OSError, ValueError) as exc:
        receipt["passed"] = False
        receipt["qualification"] = "none"
        receipt["error"] = str(exc)
        return_code = 1
    raw = profile.canonical(receipt)
    if output is not None:
        (output / "pair-receipt.json").write_bytes(raw)
    sys.stdout.buffer.write(raw)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
