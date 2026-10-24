#!/usr/bin/env python3
"""Build an external fixture against fixed, clean, unchanged Hepta libraries.

The default performs source preflight only. --execute performs offline builds;
no daemon, model, provider, or store process is launched by this preparer.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = "hepta-original-cognitive-store-probe"
sys.path.insert(0, str(HERE.parent / "hepta_agentd_runtime"))
import reviewed_toolchain as toolchain
import dependency_artifacts


def require(condition, message):
    if not condition:
        raise ValueError(message)


def helper_module():
    path = ROOT / "tests/integration/hepta/run_original_agentd.py"
    spec = importlib.util.spec_from_file_location("original_store_build_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Generic lock/build helpers only. The older Agentd source gate is unchanged.
    return module


HELPER = helper_module()
sha = HELPER.sha256


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify_source(source):
    review = json.loads((HERE / "source-review.json").read_text())
    require(source.is_dir() and source.resolve(strict=True) == source, "canonical source root required")
    require(HELPER.git(source, "rev-parse", "--show-toplevel") == str(source), "source must be Git root")
    for revision, expected in (("HEAD", review["head"]), ("HEAD^{tree}", review["tree"])):
        require(HELPER.git(source, "rev-parse", revision) == expected, "unreviewed original Hepta revision")
    require(not HELPER.git(source, "status", "--porcelain=v1", "--untracked-files=all"), "dirty original Hepta source")
    for item in review["files"]:
        path = source / item["path"]
        require(path.is_file() and not path.is_symlink() and sha(path) == item["sha256"], "reviewed source content differs")
        require(HELPER.git(source, "rev-parse", "HEAD:" + item["path"]) == item["git_blob"], "reviewed source blob differs")
    toolchain.verify_manifest(source, review)
    return review


def prepare_runner(source, destination):
    workspace = source / "codex-rs"
    upstream = tomllib.loads((workspace / "Cargo.toml").read_text())
    resolver = upstream["workspace"].get("resolver")
    require(resolver in ("1", "2", "3"), "explicit original resolver required")
    omission = HELPER.runner_patch_omission(upstream)
    destination.mkdir(mode=0o700)
    (destination / "src").mkdir(mode=0o700)
    lines = ["[package]", f'name="{NAME}"', 'version="0.0.0"', 'edition="2024"',
             "publish=false", "[workspace]", "resolver=" + HELPER.toml_value(resolver), "[dependencies]"]
    for crate in ("hepta-contracts", "hepta-memory", "hepta-paths"):
        lines.append(json.dumps("codex-" + crate) + "=" + HELPER.toml_value({"path": str(workspace / crate)}))
    dependencies = upstream["workspace"]["dependencies"]
    lines.append("serde_json=" + HELPER.toml_value(dependencies["serde_json"]))
    tokio = dependencies["tokio"]
    tokio = {"version": tokio} if isinstance(tokio, str) else tokio.copy()
    tokio["features"] = sorted(set(tokio.get("features", [])) | {"macros", "rt-multi-thread", "process", "io-util", "time"})
    lines.append("tokio=" + HELPER.toml_value(tokio))
    for registry, patches in upstream.get("patch", {}).items():
        if registry == omission["origin"]:
            continue
        lines.append("[patch." + json.dumps(registry) + "]")
        for name, original in patches.items():
            patch = original.copy()
            if "path" in patch:
                patch["path"] = str((workspace / patch["path"]).resolve(strict=True))
            lines.append(json.dumps(name) + "=" + HELPER.toml_value(patch))
    for profile in ("dev", "dev-small"):
        lines.append("[profile." + profile + "]")
        lines.extend(json.dumps(key) + "=" + HELPER.toml_value(value)
                     for key, value in upstream["profile"][profile].items())
    (destination / "Cargo.toml").write_text("\n".join(lines) + "\n")
    shutil.copyfile(HERE / "store_probe.rs", destination / "src/main.rs")
    shutil.copyfile(workspace / "Cargo.lock", destination / "Cargo.lock")
    return omission


def verify_lock(source, runner):
    def identities(lock):
        return {(item["name"], item["version"], item.get("source"), item.get("checksum"))
                for item in lock["package"]}
    original_lock = tomllib.loads((source / "codex-rs/Cargo.lock").read_text())
    lock = tomllib.loads((runner / "Cargo.lock").read_text())
    original, resolved = identities(original_lock), identities(lock)
    root = (NAME, "0.0.0", None, None)
    require(root in resolved and not (resolved - original - {root}), "dependency identity drift from original lock")
    omission = HELPER.runner_patch_omission(tomllib.loads((source / "codex-rs/Cargo.toml").read_text()))
    target = omission["target"]
    target_source = f'git+{target["git"]}?rev={target["rev"]}#{target["rev"]}'
    require(not any(item.get("source") == target_source for item in lock["package"]), "omitted patch target became active")
    origin = "git+" + omission["origin"].removesuffix(".git")
    require(not any(item.get("source", "").split("?", 1)[0].split("#", 1)[0].removesuffix(".git") == origin
                    for item in lock["package"]), "omitted alias origin became active")
    unused = [item for item in lock.get("patch", {}).get("unused", []) if item.get("source") == target_source]
    require(len(unused) == 1 and unused[0].get("name") == omission["package"]
            and (unused[0]["name"], unused[0]["version"], target_source, None) in original,
            "omitted patch target must remain unused exactly once")
    return {"shared_package_identities_checked": len(resolved - {root}), "omitted_patch": omission}


def build(args, source, out, review, report):
    require(not out.exists() and not out.is_symlink(), "output must be new")
    require(not out.resolve().is_relative_to(source), "output must be outside original source")
    require(shutil.disk_usage(out.parent).free >= 8 * 1024**3, "8 GiB free required")
    channel = toolchain.verify_manifest(source, review)
    tool_bin = Path(subprocess.check_output(["rustup", "which", "--toolchain", channel, "cargo"], text=True).strip()).parent
    cargo, rustc = tool_bin / "cargo", tool_bin / "rustc"
    target = args.target.absolute() if args.target else out / "target"
    environment = HELPER.build_environment(target)
    environment.update(PATH=str(tool_bin) + ":/usr/bin:/bin", RUSTC=str(rustc),
                       CARGO_PROFILE_DEV_DEBUG="0", CARGO_PROFILE_DEV_SMALL_DEBUG="0")
    versions = {}
    for name, path in (("cargo", cargo), ("rustc", rustc)):
        result = subprocess.run([str(path), "--version"], env=environment, capture_output=True, text=True, timeout=30, check=True)
        version = toolchain.validate_version(name, result.stdout, channel)
        versions[name] = {"path": str(path), "sha256": sha(path), "version": version}
    out.mkdir(mode=0o700)
    report["output_created"] = True
    environment.update(dependency_artifacts.freeze(report["dependency_artifacts"], out))
    runner = out / "runner"
    omission = prepare_runner(source, runner)
    commands = [
        ("resolution", ["metadata", "--offline", "--format-version", "1"]),
        ("locked-metadata", ["metadata", "--locked", "--offline", "--format-version", "1"]),
        ("build", ["build", "--locked", "--offline", "--profile", "dev-small"]),
        ("clippy", ["clippy", "--locked", "--offline", "--profile", "dev-small", "--", "-D", "warnings"]),
    ]
    lock_digest = None
    for name, arguments in commands:
        command = [str(cargo), *arguments]
        report["commands"].append(command)
        HELPER.bounded_command(command, runner, environment, out / (name + ".log"), 3600)
        report["lock_validation"] = verify_lock(source, runner)
        if lock_digest is None:
            lock_digest = sha(runner / "Cargo.lock")
        require(sha(runner / "Cargo.lock") == lock_digest, "resolved dependency lock changed")
    require(verify_source(source) == review, "original source changed during build")
    require(sha(runner / "src/main.rs") == sha(HERE / "store_probe.rs"), "fixture source changed during build")
    dependency_artifacts.verify_frozen(report["dependency_artifacts"])
    binary = out / NAME
    shutil.copyfile(target / "dev-small" / NAME, binary)
    binary.chmod(0o555)
    report.update(built=True, source_clean=True, source=review, toolchains=versions,
                  original_cargo_lock_sha256=sha(source / "codex-rs/Cargo.lock"),
                  resolved_cargo_lock_sha256=lock_digest, fixture_patch_omission=omission,
                  fixture_source_sha256=sha(HERE / "store_probe.rs"),
                  binary={"path": NAME, "sha256": sha(binary), "bytes": binary.stat().st_size})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hepta-source", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target", type=Path, help="optional exclusively leased cache directory")
    dependency_artifacts.add_arguments(parser)
    args = parser.parse_args(argv)
    if args.execute and args.output is None:
        parser.error("--execute requires --output")
    report = {"schema": "hepta.original-cognitive-store-build.v1", "built": False,
              "runtime_executed": False, "commands": []}
    out = args.output.absolute() if args.output else None
    try:
        report["dependency_artifacts"] = dependency_artifacts.selected(args)
        source = args.hepta_source.absolute()
        review = verify_source(source)
        report.update(preflight_passed=True, source=review)
        if args.execute:
            build(args, source, out, review, report)
    except (OSError, ValueError, KeyError, TypeError, HELPER.GateError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    if report.get("output_created"):
        save(out / "build.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("built" if args.execute else "preflight_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
