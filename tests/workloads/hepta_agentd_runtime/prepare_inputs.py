#!/usr/bin/env python3
"""Build the unchanged original fixture and userspace; freeze real guest inputs.

Default mode only validates fixed clean source checkouts and the caller-retained
ordinary kernel build receipt. --execute builds with the reviewed installed Rust, offline
dependencies, and a new output directory. Both existing Cargo target caches can
be selected explicitly and leased exclusively. --fetch-dependencies explicitly
warms the two original locked dependency graphs first. No built binary is launched.
"""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_agentd_runtime as gate
import reviewed_toolchain as toolchain
import dependency_artifacts

require, sha, save = gate.require, gate.sha, gate.save
NATIVE_TARGET = "x86_64-unknown-linux-gnu"


def git(source, *arguments):
    result = subprocess.run(["git", "-C", str(source), *arguments], env=gate.abi.ENV,
                            capture_output=True, text=True, timeout=30, check=False)
    require(result.returncode == 0, "git source verification failed: " + result.stderr.strip())
    return result.stdout.strip()


def verify_sources(roots):
    review = gate.read_source_review()
    for name, source in roots.items():
        require(source.is_dir() and source.resolve(strict=True) == source, "canonical source directory required")
        require(git(source, "rev-parse", "--show-toplevel") == str(source), "source must be its Git root")
        require(git(source, "rev-parse", "HEAD") == gate.SOURCES[name]["head"], "unreviewed " + name + " commit")
        require(git(source, "rev-parse", "HEAD^{tree}") == gate.SOURCES[name]["tree"], "unreviewed " + name + " tree")
        require(not git(source, "status", "--porcelain=v1", "--untracked-files=all"), "dirty " + name + " source")
    for item in review["source_files"]:
        source = roots[item["repository"]]
        path = source / item["path"]
        require(path.is_file() and not path.is_symlink() and sha(path) == item["sha256"], "reviewed source content changed")
        require(git(source, "rev-parse", "HEAD:" + item["path"]) == item["git_blob"], "reviewed Git blob changed")
    toolchain.verify_manifest(roots["hepta"], review)
    return review["source_files"]


def identity(path, relative):
    return {"path": relative, "bytes": path.stat().st_size, "sha256": sha(path)}


def kernel_receipt(path, kernel, digest):
    gate.pinned(path, digest, 4 * 1024**2)
    value = gate.json_value(path.read_bytes())
    require(isinstance(value, dict) and value.get("schema") == "hepta.native-original-runtime-build.v1",
            "ordinary kernel build receipt schema required")
    require(value.get("sources") == gate.SOURCES and value.get("built") is True
            and value.get("source_clean") is True and value.get("kernel_profile") == "ordinary-os",
            "kernel receipt does not attest the reviewed clean ordinary build")
    gate.validate_build_sources(value, "kernel")
    require(kernel.is_file() and not kernel.is_symlink() and 0 < kernel.stat().st_size <= 64 * 1024**2,
            "regular bounded original kernel input required")
    require(value.get("binary_sha256") == {"kernel": sha(kernel)}, "kernel build receipt digest mismatch")
    commands = value.get("commands")
    require(isinstance(commands, list) and commands
            and all(isinstance(command, list) and command and all(isinstance(arg, str) and arg for arg in command)
                    for command in commands), "kernel build commands missing")
    return value


def original_helper(desktop):
    path = desktop / "tests/integration/hepta/run_original_agentd.py"
    specification = importlib.util.spec_from_file_location("fixed_original_agentd_builder", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    # Only generic prepare/lock/bounded-build helpers are used. The older host
    # gate's f8c9419 source guard remains unchanged and is never bypassed.
    return module


def original_call(helper, name, *arguments):
    """Keep original-helper failures inside this gate's recorded failure path."""
    try:
        return getattr(helper, name)(*arguments)
    except helper.GateError as error:
        raise ValueError("original " + name + " rejected build: " + str(error)) from error


def cargo_targets(args, roots, out):
    """An explicit cache is local build input, never a cold-build claim."""
    selected = {name: getattr(args, name + "_target_cache", None) for name in ("original", "observer")}
    reused = any(path is not None for path in selected.values())
    require(not reused or all(path is not None for path in selected.values()),
            "original and observer target caches must be selected together")
    if not reused:
        selected = {name: out / (name + "-target") for name in selected}
    else:
        for name, path in selected.items():
            path = path.absolute()
            require(path.is_dir() and not path.is_symlink() and path.resolve(strict=True) == path,
                    "target cache must be an existing canonical directory")
            for protected in (*roots.values(), out.resolve(), args.kernel.parent.resolve()):
                require(not path.is_relative_to(protected) and not protected.is_relative_to(path),
                        "target cache must be separate from sources, output and kernel inputs")
            selected[name] = path
        first, second = selected.values()
        require(not first.is_relative_to(second) and not second.is_relative_to(first),
                "target caches must be distinct non-overlapping directories")
    record = {"mode": "explicit-existing-cache" if reused else "new-output-targets",
              "cache_reused": reused, "cold_build_claimed": False,
              "lease_policy": "nonblocking-exclusive-flock-through-freeze" if reused else "private-new-output",
              "targets": {}}
    for name, path in selected.items():
        info = {"path": str(path), "exclusive_lease_acquired": False}
        if reused:
            metadata = path.stat()
            info.update(device=metadata.st_dev, inode=metadata.st_ino,
                        contents_authenticated=False)
        record["targets"][name] = info
    return selected, record


@contextmanager
def target_cache_lease(path, record):
    """Cooperating preparations refuse a busy cache instead of waiting on it."""
    directory = path.stat()
    require((directory.st_dev, directory.st_ino) == (record["device"], record["inode"]),
            "target cache identity changed before lease")
    lock = path / ".hepta-native-userspace.lock"
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        metadata = os.fstat(descriptor)
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
                "target cache lease must be a regular unaliased file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("target cache is already leased: " + str(path)) from error
        require(not lock.is_symlink() and (lock.stat().st_dev, lock.stat().st_ino) == (metadata.st_dev, metadata.st_ino)
                and path.stat().st_ino == directory.st_ino and path.stat().st_dev == directory.st_dev,
                "target cache or lease identity changed during acquisition")
        record.update(exclusive_lease_acquired=True,
                      lease_file={"path": str(lock), "device": metadata.st_dev, "inode": metadata.st_ino})
        yield
    finally:
        os.close(descriptor)  # Closing releases the advisory lock on every exit.


def verify_target_caches(targets, record):
    if not record["cache_reused"]:
        return
    for name, path in targets.items():
        expected = record["targets"][name]
        require(expected["exclusive_lease_acquired"] is True and path.resolve(strict=True) == path
                and (path.stat().st_dev, path.stat().st_ino) == (expected["device"], expected["inode"]),
                "leased target cache identity changed")
        lock = Path(expected["lease_file"]["path"])
        metadata = lock.stat()
        require(not lock.is_symlink() and stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
                and (metadata.st_dev, metadata.st_ino) == (expected["lease_file"]["device"], expected["lease_file"]["inode"]),
                "target cache lease identity changed")


def build(args, roots, out, report, source_files, receipt):
    require(not out.exists() and not out.is_symlink(), "output must be new")
    require(all(not out.resolve().is_relative_to(source) for source in roots.values()), "output must be outside sources")
    require(not out.resolve().is_relative_to(args.kernel.parent.resolve()), "output must be outside retained kernel inputs")
    require(shutil.disk_usage(out.parent).free >= 8 * 1024**3, "at least 8 GiB free required for original userspace build")
    cargo = Path(gate.abi.tool(str(args.cargo)))
    rustc = Path(gate.abi.tool(str(args.rustc)))
    gate.pinned(cargo, args.expected_cargo_sha256, 512 * 1024**2)
    gate.pinned(rustc, args.expected_rustc_sha256, 512 * 1024**2)
    environment = {**gate.abi.ENV, "PATH": str(cargo.parent) + ":/usr/bin:/bin:/usr/sbin:/sbin",
                   "RUSTC": str(rustc), "CARGO_HOME": str(args.cargo_home.resolve(strict=True)),
                   "CARGO_INCREMENTAL": "0", "CARGO_BUILD_JOBS": "1", "CARGO_PROFILE_DEV_DEBUG": "0",
                   "CARGO_PROFILE_DEV_SMALL_DEBUG": "0", "LANG": "C.UTF-8"}
    channel = toolchain.verify_manifest(roots["hepta"], gate.SOURCE_REVIEW)
    versions = {}
    for name, executable in (("cargo", cargo), ("rustc", rustc)):
        result = subprocess.run([str(executable), "--version"], env=environment, capture_output=True,
                                text=True, timeout=30, check=False)
        require(result.returncode == 0, "original compiler version query failed")
        version = toolchain.validate_version(name, result.stdout, channel)
        versions[name] = {"path": str(executable), "sha256": sha(executable), "version": version}
    out.mkdir(mode=0o700)
    report["output_created"] = True
    environment.update(dependency_artifacts.freeze(report["dependency_artifacts"], out))
    targets, target_record = cargo_targets(args, roots, out)
    report["cargo_targets"] = target_record
    with ExitStack() as leases:
        if target_record["cache_reused"]:
            for name in sorted(targets, key=lambda key: str(targets[key])):
                leases.enter_context(target_cache_lease(targets[name], target_record["targets"][name]))
        build_userspace(args, roots, out, report, source_files, receipt, environment, versions, targets)


def build_userspace(args, roots, out, report, source_files, receipt, environment, versions, targets):
    cargo = Path(versions["cargo"]["path"])
    helper = original_helper(roots["desktop"])
    fixture = out / "fixture-build"
    omission = original_call(helper, "prepare_runner", roots["hepta"], fixture)
    original_target, observer_target = targets["original"], targets["observer"]
    commands = []
    steps = []
    if getattr(args, "fetch_dependencies", False):
        for name, cwd, target, manifest in (
                ("observer", roots["desktop"], observer_target, roots["desktop"] / "services/hepta-os/Cargo.toml"),
                ("agentd", roots["hepta"] / "codex-rs", original_target, roots["hepta"] / "codex-rs/Cargo.toml")):
            steps.append(("fetch-" + name, cwd, target,
                          ["fetch", "--locked", "--target", NATIVE_TARGET, "--manifest-path", str(manifest)]))
    steps += [
        ("observer", roots["desktop"], observer_target,
         ["build", "--locked", "--offline", "--manifest-path", str(roots["desktop"] / "services/hepta-os/Cargo.toml"), "--bin", "hepta-observe"]),
        ("agentd", roots["hepta"] / "codex-rs", original_target,
         ["build", "--locked", "--offline", "--profile", "dev-small", "--no-default-features", "-p", "codex-hepta-agentd", "--bin", "codex-hepta-agentd", "-j1"]),
        ("fixture-resolution", fixture, original_target,
         ["metadata", "--offline", "--filter-platform", NATIVE_TARGET, "--format-version", "1",
          "--manifest-path", str(fixture / "Cargo.toml")]),
        ("fixture-locked-metadata", fixture, original_target,
         ["metadata", "--locked", "--offline", "--filter-platform", NATIVE_TARGET, "--format-version", "1",
          "--manifest-path", str(fixture / "Cargo.toml")]),
        ("fixture", fixture, original_target,
         ["build", "--locked", "--offline", "--profile", "dev-small", "--manifest-path", str(fixture / "Cargo.toml"), "-j1"]),
    ]
    lock_digest = None
    for name, cwd, target, arguments in steps:
        verify_target_caches(targets, report["cargo_targets"])
        command = [str(cargo), *arguments]
        commands.append(command)
        report["steps"].append({"name": name, "status": "running", "argv": command,
                                "cwd": str(cwd), "cargo_target_dir": str(target),
                                "command_timeout_seconds": 3600})
        original_call(helper, "bounded_command", command, cwd, {**environment, "CARGO_TARGET_DIR": str(target)},
                      out / (name + ".log"), 3600)
        if name.startswith("fixture"):
            original_call(helper, "verify_runner_lock", roots["hepta"], fixture)
            if lock_digest is None:
                lock_digest = sha(fixture / "Cargo.lock")
            require(sha(fixture / "Cargo.lock") == lock_digest, "original dependency lock changed after resolution")
        report["steps"][-1]["status"] = "passed"
    require(verify_sources(roots) == source_files, "source changed during build")
    require(kernel_receipt(args.kernel_receipt, args.kernel, args.expected_kernel_receipt_sha256) == receipt,
            "kernel input changed during userspace build")
    (out / "bin").mkdir()
    binaries = {"agentd": original_target / "dev-small/codex-hepta-agentd",
                "fixture": original_target / "dev-small/hepta-original-observer-probe",
                "observer": observer_target / "debug/hepta-observe", "kernel": args.kernel}
    identities = {}
    for name, source in binaries.items():
        filename = gate.BINARIES.get(name, "kernel.elf")
        target = out / "bin" / filename
        shutil.copyfile(source, target)
        target.chmod(0o555)
        require(sha(target) == sha(source), "built binary changed while freezing")
        identities[name] = identity(target, "bin/" + filename)
    verify_target_caches(targets, report["cargo_targets"])
    dependency_artifacts.verify_frozen(report["dependency_artifacts"])
    userspace = {"schema": "hepta.native-original-runtime-build.v1", "sources": gate.SOURCES,
                 "build_sources": gate.SOURCES,
                 "built": True, "source_clean": True, "commands": commands, "toolchains": versions,
                 "command_records": report["steps"],
                 "binary_sha256": {name: identities[name]["sha256"] for name in gate.BINARIES},
                 "fixture_patch_omission": omission, "fixture_resolved_lock_sha256": lock_digest,
                 "dependencies_prefetched": getattr(args, "fetch_dependencies", False),
                 "cargo_targets": report["cargo_targets"],
                 "dependency_artifacts": report["dependency_artifacts"],
                 "command_timeout_seconds": 3600,
                 "source_files": source_files, "runtime_executed": False}
    save(out / "userspace-build.json", userspace)
    save(out / "kernel-build.json", receipt)
    manifest = {"schema": "hepta.native-original-runtime-input.v1", "sources": gate.SOURCES,
                "kernel_profile": "ordinary-os", "source_files": source_files, "binaries": identities,
                "build_receipts": {name: identity(out / (name + "-build.json"), name + "-build.json")
                                   for name in ("kernel", "userspace")}}
    save(out / "input-manifest.json", manifest)
    gate.frozen_inputs(out / "input-manifest.json", sha(out / "input-manifest.json"))
    report.update(built=True, input_manifest_sha256=sha(out / "input-manifest.json"),
                  toolchains=versions, binary_sha256={name: value["sha256"] for name, value in identities.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--fetch-dependencies", action="store_true",
                        help="with --execute, fetch the original locked x86_64 dependency graphs before offline builds")
    parser.add_argument("--desktop-source", type=Path, required=True)
    parser.add_argument("--hepta-source", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--kernel-receipt", type=Path, required=True)
    parser.add_argument("--expected-kernel-receipt-sha256", required=True)
    parser.add_argument("--cargo", type=Path)
    parser.add_argument("--expected-cargo-sha256")
    parser.add_argument("--rustc", type=Path)
    parser.add_argument("--expected-rustc-sha256")
    parser.add_argument("--cargo-home", type=Path)
    parser.add_argument("--original-target-cache", type=Path,
                        help="with --execute, exclusively lease this existing original Cargo target cache")
    parser.add_argument("--observer-target-cache", type=Path,
                        help="with --execute, exclusively lease this existing observer Cargo target cache")
    parser.add_argument("--output", type=Path)
    dependency_artifacts.add_arguments(parser)
    args = parser.parse_args(argv)
    if args.fetch_dependencies and not args.execute:
        parser.error("--fetch-dependencies requires --execute")
    if (args.original_target_cache is not None or args.observer_target_cache is not None):
        if not args.execute or args.original_target_cache is None or args.observer_target_cache is None:
            parser.error("both --original-target-cache and --observer-target-cache require --execute")
    report = {"schema": "hepta.native-original-runtime-preparation.v1", "built": False, "runtime_executed": False,
              "sources": gate.SOURCES, "steps": [], "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if args.execute:
        for name in ("cargo", "expected_cargo_sha256", "rustc", "expected_rustc_sha256", "cargo_home", "output"):
            if getattr(args, name) is None:
                parser.error("--execute requires --" + name.replace("_", "-"))
    roots = {"desktop": args.desktop_source.absolute(), "hepta": args.hepta_source.absolute()}
    out = args.output.absolute() if args.output is not None else None
    try:
        report["dependency_artifacts"] = dependency_artifacts.selected(args)
        source_files = verify_sources(roots)
        receipt = kernel_receipt(args.kernel_receipt, args.kernel, args.expected_kernel_receipt_sha256)
        report["preflight_passed"] = True
        if args.execute:
            build(args, roots, out, report, source_files, receipt)
        else:
            report["status"] = "preflight only; explicit --execute required for builds"
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created") is True:
        save(out / "preparation-result.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("preflight_passed") and (not args.execute or report["built"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
