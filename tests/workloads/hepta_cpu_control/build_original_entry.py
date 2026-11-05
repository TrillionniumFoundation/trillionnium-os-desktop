#!/usr/bin/env python3
"""Measure a tracked original Agentd entry against an explicit image profile.

This performs a real locked, offline static release build and the original
release packaging. It creates no Cargo fixture, replaces no supplier, disables
no feature and never executes the result. A successful build is not G2 evidence.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import tomllib

LEGACY_IMAGE_PROFILE = "g2-trusted-daemon"
EXACT_IMAGE_PROFILE = "g2-original-owner-a39-v1"
PUBLICATION_IMAGE_PROFILE = "g2-original-owner-publish-v1"
EXACT_IMAGE_PROFILES = (EXACT_IMAGE_PROFILE, PUBLICATION_IMAGE_PROFILE)


def exact_image_module(desktop, profile=EXACT_IMAGE_PROFILE):
    path = desktop / "support/build/original_owner_image.py"
    spec = importlib.util.spec_from_file_location("original_owner_image_profile", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.select_profile(profile)

sys.dont_write_bytecode = True
TARGET = "x86_64-unknown-linux-gnu"
PACKAGE = "codex-hepta-agentd"
STATIC_FLAGS = "-C target-feature=+crt-static -C relocation-model=static -C link-arg=-no-pie"
BASE_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git(source, *arguments):
    result = subprocess.run(["/usr/bin/git", "-C", str(source), *arguments], env=BASE_ENV,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
    require(result.returncode == 0, "Git source verification failed: " + result.stderr.decode(errors="replace").strip())
    return result.stdout


def source_snapshot(source, expected_head, expected_tree):
    require(source.is_dir() and not source.is_symlink() and source.resolve(strict=True) == source,
            "source must be an existing canonical directory")
    require(re.fullmatch(r"[0-9a-f]{40}", expected_head) and re.fullmatch(r"[0-9a-f]{40}", expected_tree),
            "full lowercase source commit and tree required")
    require(git(source, "rev-parse", "--show-toplevel").decode().strip() == str(source), "source must be its Git root")
    require(git(source, "rev-parse", "HEAD").decode().strip() == expected_head, "source commit changed")
    require(git(source, "rev-parse", "HEAD^{tree}").decode().strip() == expected_tree, "source tree changed")
    require(not git(source, "status", "--porcelain=v1", "--untracked-files=all"), "source checkout is dirty")
    files = []
    for entry in git(source, "ls-files", "-s", "-z").split(b"\0"):
        if not entry:
            continue
        attributes, raw_path = entry.split(b"\t", 1)
        mode, blob, stage = attributes.decode("ascii").split()
        require(stage == "0" and mode in ("100644", "100755", "120000"), "unsupported tracked source entry")
        relative = os.fsdecode(raw_path)
        path = source / relative
        if mode == "120000":
            require(path.is_symlink(), "tracked symbolic link changed: " + relative)
            content = os.fsencode(os.readlink(path))
        else:
            require(path.is_file() and not path.is_symlink(), "tracked source file changed: " + relative)
            require(bool(path.stat().st_mode & stat.S_IXUSR) == (mode == "100755"), "source executable mode changed")
            content = path.read_bytes()
        actual_blob = hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()
        require(actual_blob == blob, "tracked source bytes differ from Git: " + relative)
        files.append({"path": relative, "mode": mode, "git_blob": blob,
                      "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
    return {"head": expected_head, "tree": expected_tree, "files": files}


def select_original_target(metadata, source, name, kind):
    """Cargo must select a tracked target in the actual original Agentd package."""
    require(len(name) <= 128 and re.fullmatch(r"[A-Za-z0-9_-]+", name), "bounded original target name required")
    expected_manifest = source / "codex-rs/hepta-agentd/Cargo.toml"
    candidates = [package for package in metadata["packages"]
                  if package["name"] == PACKAGE and Path(package["manifest_path"]) == expected_manifest]
    require(len(candidates) == 1, "exact original Agentd workspace package required")
    package = candidates[0]
    require(package["id"] in metadata["workspace_members"], "target is not an original workspace member")
    targets = [target for target in package["targets"]
               if target["name"] == name and kind in target["kind"] and "bin" in target["crate_types"]]
    require(len(targets) == 1, "selected original executable target does not exist")
    target = targets[0]
    path = Path(target["src_path"])
    require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path
            and path.is_relative_to(source / "codex-rs/hepta-agentd"), "original entry must be inside Agentd source")
    require(not target.get("required-features"), "entry needs explicit features outside the default release profile")
    return {"package": PACKAGE, "name": name, "kind": kind, "path": str(path.relative_to(source)),
            "entry_sha256": digest(path), "package_id": package["id"]}


@contextmanager
def target_lease(path):
    """Use the same exclusive lease name as the original native preparation."""
    directory = path.stat()
    lock = path / ".hepta-native-userspace.lock"
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        metadata = os.fstat(descriptor)
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, "target lease must be a regular unaliased file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Cargo target cache is already leased") from error
        require(not lock.is_symlink() and (lock.stat().st_dev, lock.stat().st_ino) == (metadata.st_dev, metadata.st_ino)
                and (path.stat().st_dev, path.stat().st_ino) == (directory.st_dev, directory.st_ino),
                "Cargo target or lease identity changed")
        yield {"path": str(path), "device": directory.st_dev, "inode": directory.st_ino,
               "lease_file": str(lock), "lease_device": metadata.st_dev, "lease_inode": metadata.st_ino,
               "exclusive_lease_acquired": True}
    finally:
        os.close(descriptor)


def run(command, cwd, environment, output, label, report, timeout):
    require(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
            "original command requires sole wait ownership and default SIGCHLD")
    require(hasattr(os, "WNOWAIT") and hasattr(signal, "pthread_sigmask"),
            "non-reaping Linux child supervision required")
    record = {"argv": [str(value) for value in command], "cwd": str(cwd), "log": label,
              "timeout_seconds": timeout, "completed": False}
    report["commands"].append(record)
    save(output / "result.json", report)
    started = time.monotonic()
    with (output / label).open("xb") as log:
        process = subprocess.Popen(record["argv"], cwd=cwd, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        may_signal_group = True
        failure = None
        try:
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    record["timed_out"] = True
                    break
                try:
                    exited = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                except ChildProcessError:
                    may_signal_group = False
                    record["wait_owner_lost"] = True
                    raise ValueError("original command wait ownership was lost") from None
                if exited is not None:
                    # wait() may reap before propagating an interruption.
                    # No later path may signal this numeric group after it.
                    may_signal_group = False
                    record["exit_code"] = process.wait()
                    break
                time.sleep(min(0.05, remaining))
        except BaseException as error:
            failure = error
            record["error"] = type(error).__name__ + ": " + str(error)
        finally:
            # Keep the caller's exclusive Cargo lease through cleanup/reap.
            # Defer another Ctrl-C until the owned child has been collected.
            previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
            try:
                if may_signal_group:
                    try:
                        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    except ChildProcessError:
                        may_signal_group = False
                        record["wait_owner_lost"] = True
                    if may_signal_group:
                        try:
                            record["cleanup_group_signal"] = "SIGKILL"
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        finally:
                            may_signal_group = False
                while process.returncode is None and not record.get("wait_owner_lost"):
                    try:
                        record["exit_code"] = process.wait()
                    except (KeyboardInterrupt, SystemExit) as error:
                        if failure is None:
                            failure = error
                            record["error"] = type(error).__name__ + ": " + str(error)
                record["exit_code"] = process.returncode
            finally:
                try:
                    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                except (KeyboardInterrupt, SystemExit) as error:
                    if failure is None:
                        failure = error
                        record["error"] = type(error).__name__ + ": " + str(error)
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            record["completed"] = process.returncode is not None
            save(output / "result.json", report)
        if failure is not None:
            raise failure
    require(not record.get("timed_out") and record["exit_code"] == 0, "original command failed: " + label)


def freeze(source, destination):
    require(source.is_file() and not source.is_symlink(), "original product must be a regular file")
    before = digest(source)
    shutil.copyfile(source, destination)
    destination.chmod(0o555)
    require(digest(source) == before == digest(destination), "built product changed while freezing")
    return {"path": destination.name, "bytes": destination.stat().st_size, "sha256": before}


@contextmanager
def packaging_copy(source, destination):
    """Allow the original strip script to edit only its private product copy."""
    freeze(source, destination)
    destination.chmod(0o600)
    try:
        yield destination
    finally:
        destination.chmod(0o555)


def environment(args, toolchain):
    cargo = args.toolchain_bin / "cargo"
    rustc = args.toolchain_bin / "rustc"
    require(args.toolchain_bin.resolve(strict=True) == args.toolchain_bin, "canonical toolchain directory required")
    versions = {}
    for name, path in (("cargo", cargo), ("rustc", rustc)):
        require(path.is_file() and not path.is_symlink(), "explicit installed toolchain binary required")
        value = subprocess.run([str(path), "--version"], env=BASE_ENV, capture_output=True, text=True,
                               timeout=30, check=False)
        require(value.returncode == 0 and value.stdout.startswith(name + " " + toolchain + " "),
                "installed toolchain differs from original rust-toolchain.toml")
        versions[name] = {"path": str(path), "sha256": digest(path), "version": value.stdout.strip()}
    result = {**BASE_ENV, "PATH": str(args.toolchain_bin) + ":" + BASE_ENV["PATH"],
              "HOME": str(Path.home()), "CARGO_HOME": str(args.cargo_home.resolve(strict=True)),
              "RUSTC": str(rustc), "RUSTUP_TOOLCHAIN": toolchain,
              "CARGO_TARGET_DIR": str(args.target_cache), "CARGO_NET_OFFLINE": "true",
              "CARGO_INCREMENTAL": "0", "CARGO_BUILD_JOBS": str(args.jobs), "OPENSSL_STATIC": "1",
              "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS": STATIC_FLAGS}
    supplied = (args.v8_archive, args.v8_bindings, args.expected_v8_archive_sha256, args.expected_v8_bindings_sha256)
    require(not any(supplied) or all(supplied), "the original V8 archive/bindings and both digests must be supplied together")
    dependencies = {}
    for key, path, expected in (("RUSTY_V8_ARCHIVE", args.v8_archive, args.expected_v8_archive_sha256),
                                ("RUSTY_V8_SRC_BINDING_PATH", args.v8_bindings, args.expected_v8_bindings_sha256)):
        if path is not None:
            require(path.is_file() and not path.is_symlink() and re.fullmatch(r"[0-9a-f]{64}", expected)
                    and digest(path) == expected, "original pinned V8 input differs")
            result[key] = str(path.resolve(strict=True))
            dependencies[key] = {"path": result[key], "sha256": expected, "bytes": path.stat().st_size}
    return result, versions, dependencies


def execute(args, report):
    roots = {"desktop": args.desktop_source, "hepta": args.hepta_source}
    require(args.output.parent.is_dir() and not args.output.exists() and not args.output.is_symlink(), "output must be new")
    require(all(not args.output.resolve().is_relative_to(root) for root in roots.values()), "output must be outside source checkouts")
    require(args.target_cache.is_dir() and not args.target_cache.is_symlink()
            and args.target_cache.resolve(strict=True) == args.target_cache, "existing canonical exclusive target cache required")
    for path in (*roots.values(), args.output.resolve()):
        require(not args.target_cache.is_relative_to(path) and not path.is_relative_to(args.target_cache),
                "Cargo target cache must not overlap source or evidence")
    args.output.mkdir(mode=0o700)
    report["output_created"] = True
    save(args.output / "result.json", report)
    before = {}
    for name, root in roots.items():
        before[name] = source_snapshot(root, getattr(args, name + "_head"), getattr(args, name + "_tree"))
    save(args.output / "source-before.json", before)
    report["sources"] = {name: {key: value[key] for key in ("head", "tree")} for name, value in before.items()}
    exact = exact_image_module(args.desktop_source, args.image_profile) if args.image_profile in EXACT_IMAGE_PROFILES else None
    if exact:
        report.update(image_profile_descriptor=exact.descriptor(),
                      image_profile_descriptor_sha256=exact.DESCRIPTOR_SHA256)
    upstream = tomllib.loads((args.hepta_source / "codex-rs/Cargo.toml").read_text())
    toolchain = tomllib.loads((args.hepta_source / "codex-rs/rust-toolchain.toml").read_text())["toolchain"]["channel"]
    require(re.fullmatch(r"\d+\.\d+\.\d+", toolchain), "original fixed release toolchain required")
    env, versions, dependencies = environment(args, toolchain)
    report.update(toolchains=versions, release_profile=upstream["profile"]["release"], dependency_inputs=dependencies,
                  original_lock_sha256=digest(args.hepta_source / "codex-rs/Cargo.lock"),
                  environment={key: value for key, value in env.items() if key != "HOME"})
    temporary = args.output / "tmp"
    temporary.mkdir(mode=0o700)
    env.update(TMPDIR=str(temporary), RUNNER_TEMP=str(temporary))
    cargo = args.toolchain_bin / "cargo"
    try:
        with target_lease(args.target_cache) as lease:
            cache_had_artifacts = any(
                path.name != ".hepta-native-userspace.lock" for path in args.target_cache.iterdir())
            report["target_cache"] = {**lease, "cache_reused": cache_had_artifacts,
                                     "cold_build_claimed": False}
            # Metadata selects a real target; it never generates a replacement root package.
            metadata_command = [cargo, "metadata", "--manifest-path", "codex-rs/Cargo.toml", "--locked", "--offline",
                                "--no-deps", "--format-version", "1"]
            run(metadata_command, args.hepta_source, env, args.output, "metadata.log", report, 120)
            metadata_lines = (args.output / "metadata.log").read_text().splitlines()
            metadata = [json.loads(line) for line in metadata_lines if line.startswith('{"packages"')]
            require(len(metadata) == 1, "one original Cargo metadata document required")
            target = select_original_target(metadata[0], args.hepta_source, args.entry, args.entry_kind)
            source_files = {record["path"]: record for record in before["hepta"]["files"]}
            require(target["path"] in source_files and source_files[target["path"]]["sha256"] == target["entry_sha256"],
                    "entry is not a frozen tracked original source file")
            report["original_entry"] = target
            if exact:
                exact.bind_build(report["sources"], target, report["original_lock_sha256"],
                                 digest(args.hepta_source / "codex-rs/rust-toolchain.toml"), toolchain)
            command = [cargo, "build", "--manifest-path", "codex-rs/Cargo.toml", "--locked", "--offline", "--release",
                       "--target", TARGET, "-p", PACKAGE, "--" + args.entry_kind, args.entry, "-j" + str(args.jobs)]
            run(command, args.hepta_source, env, args.output, "build.log", report, args.timeout)
            release = args.target_cache / TARGET / "release"
            product = release / ("examples" if args.entry_kind == "example" else "") / args.entry
            report["unstripped"] = freeze(product, args.output / (args.entry + ".unstripped"))
            report["built"] = True
            packaged = args.output / "packaged"
            packaged.mkdir(mode=0o700)
            script = args.hepta_source / ".github/scripts/archive-release-symbols-and-strip-binaries.sh"
            package_command = ["/bin/bash", script, "--target", TARGET, "--artifact-name", "hepta-original-native-entry",
                               "--release-dir", packaged, "--archive-dir", args.output / "symbols-dist", "--binaries", args.entry]
            with packaging_copy(product, packaged / args.entry):
                run(package_command, args.hepta_source, env, args.output, "original-packaging.log", report, 600)
            binary = packaged / args.entry
            report["product"] = {"path": "packaged/" + args.entry, "bytes": binary.stat().st_size, "sha256": digest(binary)}
            report["packaged"] = True
            run(["/usr/bin/readelf", "-W", "-h", "-l", "-d", binary], args.hepta_source, env, args.output,
                "original-readelf.log", report, 30)
            inspector = args.desktop_source / "tests/kernel/control/run_g1c_guest.py"
            spec = importlib.util.spec_from_file_location("original_native_shape", inspector)
            module = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(inspector.parent))
            spec.loader.exec_module(module)
            content = binary.read_bytes()
            report["original_shape"] = exact.inspect_elf(content) if exact else module.inspect_probe_elf(content)
            report["image_profile_passed" if exact else "static_profile_passed"] = True
            require(digest(product) == report["unstripped"]["sha256"], "target product changed before freeze completed")
            for item in dependencies.values():
                require(digest(Path(item["path"])) == item["sha256"], "original dependency input changed during build")
    finally:
        after = {name: source_snapshot(root, getattr(args, name + "_head"), getattr(args, name + "_tree"))
                 for name, root in roots.items()}
        save(args.output / "source-after.json", after)
        require(after == before, "source inputs changed during original build")
        report["source_inputs_unchanged"] = True
        save(args.output / "result.json", report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--image-profile", choices=(LEGACY_IMAGE_PROFILE, *EXACT_IMAGE_PROFILES),
                        default=LEGACY_IMAGE_PROFILE)
    for name in ("desktop", "hepta"):
        parser.add_argument("--" + name + "-source", type=Path, required=True)
        parser.add_argument("--" + name + "-head", required=True)
        parser.add_argument("--" + name + "-tree", required=True)
    parser.add_argument("--entry", required=True, help="tracked bin/example in original codex-hepta-agentd")
    parser.add_argument("--entry-kind", choices=("bin", "example"), default="bin")
    parser.add_argument("--toolchain-bin", type=Path, required=True)
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--target-cache", type=Path, required=True)
    parser.add_argument("--v8-archive", type=Path)
    parser.add_argument("--v8-bindings", type=Path)
    parser.add_argument("--expected-v8-archive-sha256")
    parser.add_argument("--expected-v8-bindings-sha256")
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--timeout", type=int, choices=range(1, 7201), default=7200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {"schema": "hepta.original-native-entry-build.v1", "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "commands": [], "built": False, "packaged": False, "static_profile_passed": False,
              "features_disabled": False, "profile_overridden": False, "limits_changed": False,
              "fixture_created": False, "executed_binary": False, "native_role_verified": False,
              "persistent_cpu_verified": False, "recovery_verified": False, "g2_complete": False}
    if args.image_profile in EXACT_IMAGE_PROFILES:
        # The new schema carries no legacy success field. Original v1
        # consumers cannot credit this as an 8/16 MiB static-profile pass.
        report.pop("static_profile_passed")
        report.pop("limits_changed")
        report.update(schema="hepta.original-owner-image-entry-build.v1", image_profile=args.image_profile,
                      image_profile_passed=False, legacy_static_profile_passed=False,
                      legacy_limits_unchanged=True, selected_image_limits_differ_from_legacy=True,
                      release_profile_unchanged=True, whole_guest_peak_verified=False,
                      global_memory_reserve=False, production_ready=False)
    if not args.execute:
        print(json.dumps({**report, "status": "disabled; explicit --execute required"}, sort_keys=True))
        return 0
    try:
        require(all(path.is_absolute() for path in (args.desktop_source, args.hepta_source, args.toolchain_bin,
                                                    args.cargo_home, args.target_cache, args.output)),
                "absolute source, toolchain, cache and output paths required")
        execute(args, report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, AssertionError,
            KeyboardInterrupt, SystemExit) as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created"):
        save(args.output / "result.json", report)
    print(json.dumps(report, sort_keys=True))
    admitted = report.get("image_profile_passed") if args.image_profile in EXACT_IMAGE_PROFILES else report["static_profile_passed"]
    return 0 if admitted and report.get("source_inputs_unchanged") and "error" not in report else 1


if __name__ == "__main__":
    raise SystemExit(main())
