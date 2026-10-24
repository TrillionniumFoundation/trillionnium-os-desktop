#!/usr/bin/env python3
"""Build the reviewed original owner into the unchanged G2 product kernel.

Only the original source-local OSDK installation and kernel.sh kernel command
perform compilation. This wrapper retains their real outputs for the existing
native_owner_inputs.kernel_build gate. It executes neither the owner nor QEMU.
"""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import tomllib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_owner_inputs as inputs


TOOLCHAIN = "nightly-2026-07-21"
RUSTC_COMMIT = "87e5904f5eb6398af6b22eac2802c78934260c48"
CARGO_COMMIT = "3efb1f477e99b42974b982d939fd100303cdf7db"
BASE_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
LOCK_NAME = ".hepta-native-kernel-build.lock"
require = inputs.require


def save(path, value):
    """Publish a whole local receipt, never a partially written JSON object."""
    temporary = path.with_name(path.name + ".new")
    require(not temporary.exists() and not temporary.is_symlink(), "receipt temporary already exists")
    with temporary.open("xb") as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def canonical_directory(path):
    require(path.is_absolute() and path.is_dir() and not path.is_symlink()
            and path.resolve(strict=True) == path, "existing canonical directory required: " + str(path))
    return path


def disjoint(paths):
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            require(not left.is_relative_to(right) and not right.is_relative_to(left),
                    "mutable/source paths overlap: " + str(left) + " / " + str(right))
            if left.exists() and right.exists():
                require(not left.samefile(right), "directory aliases share a writable resource")


@contextmanager
def resource_lease(directory):
    """Hold a stable advisory lock for cooperating builders; never unlink it."""
    directory = canonical_directory(directory)
    initial = directory.stat()
    lock = directory / LOCK_NAME
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "build lock must be a regular file without aliases")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("build resource already leased: " + str(directory)) from error

        def unchanged():
            require(directory.resolve(strict=True) == directory and not lock.is_symlink()
                    and (directory.stat().st_dev, directory.stat().st_ino) == (initial.st_dev, initial.st_ino)
                    and (lock.stat().st_dev, lock.stat().st_ino) == (info.st_dev, info.st_ino)
                    and lock.stat().st_nlink == 1, "build directory or stable lock inode changed")

        unchanged()
        yield {"directory": str(directory), "device": initial.st_dev, "inode": initial.st_ino,
               "lock": str(lock), "lock_device": info.st_dev, "lock_inode": info.st_ino,
               "exclusive_advisory_lease_acquired": True,
               "noncooperating_writers_excluded": False}
        unchanged()
    finally:
        os.close(descriptor)


def freeze_bytes(data, path, mode=0o444):
    require(not path.exists() and not path.is_symlink(), "retained artifact must be new: " + str(path))
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(mode)
    require(path.read_bytes() == data, "retained artifact changed during publication")
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def freeze_file(source, destination, limit, mode=0o444):
    content = inputs.read(source, limit)
    result = freeze_bytes(content, destination, mode)
    require(inputs.read(source, limit, result["sha256"]) == content,
            "source artifact changed while retaining it: " + str(source))
    return {"source": str(source), **result}


def command_step(label, argv, cwd, environment, output, report, timeout):
    record = {"label": label, "argv": [str(part) for part in argv], "cwd": str(cwd),
              "log": label + ".log", "timeout_seconds": timeout, "completed": False, "timed_out": False}
    report["steps"].append(record)
    save(output / "pipeline.json", report)
    start = time.monotonic()
    print(json.dumps({"starting": label, "log": str(output / record["log"])}), flush=True)
    with (output / record["log"]).open("xb") as log:
        process = subprocess.Popen(record["argv"], cwd=cwd, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            record["exit_code"] = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            record["timed_out"] = isinstance(error, subprocess.TimeoutExpired)
            record["interrupted"] = isinstance(error, KeyboardInterrupt)
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            # Cargo can exit before a compiler that ignored TERM. Keep the
            # writable resources leased until the entire group is terminated.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
            record["exit_code"] = process.returncode
            raise
        finally:
            record["elapsed_seconds"] = time.monotonic() - start
            record["completed"] = True
            log.flush()
            os.fsync(log.fileno())
            record["log_sha256"] = inputs.sha(output / record["log"])
            save(output / "pipeline.json", report)
    print(json.dumps(record), flush=True)
    require(record["exit_code"] == 0 and not record["timed_out"], "original command failed: " + label)
    return record


def probe_tool(argv, environment):
    completed = subprocess.run([str(part) for part in argv], env=environment, capture_output=True, timeout=30, check=False)
    require(completed.returncode == 0, "installed build tool probe failed: " + str(argv[0]))
    return completed.stdout.decode("utf-8")


def build_environment(args):
    environment = {**BASE_ENV, "PATH": str(args.cargo_home / "bin") + ":" + BASE_ENV["PATH"],
                   "HOME": str(Path.home()), "CARGO_HOME": str(args.cargo_home), "RUSTUP_HOME": str(args.rustup_home),
                   "RUSTUP_TOOLCHAIN": TOOLCHAIN, "RUSTUP_AUTO_INSTALL": "0", "CARGO_NET_OFFLINE": "true",
                   "CARGO_BUILD_JOBS": str(args.jobs), "CARGO_NET_GIT_FETCH_WITH_CLI": "true",
                   "OSDK_LOCAL_DEV": "1", "PYTHONDONTWRITEBYTECODE": "1", "VDSO_LIBRARY_DIR": str(args.vdso_directory)}
    tools = {}
    rustup = args.cargo_home / "bin/rustup"
    require(rustup.is_file(), "explicit Cargo home must contain the original rustup proxy")
    for name, commit in (("cargo", CARGO_COMMIT), ("rustc", RUSTC_COMMIT)):
        invocation = args.cargo_home / "bin" / name
        require(invocation.is_file(), "explicit Cargo home is missing its original tool proxy: " + name)
        # Preserve the proxy's argv[0]. Executing its resolved rustup filename
        # would change multicall dispatch and would not run Cargo or rustc.
        version = probe_tool([invocation, "+" + TOOLCHAIN, "-Vv"], environment)
        require("commit-hash: " + commit in version.splitlines()
                and version.splitlines()[0].startswith(name + " 1.99.0-nightly "),
                "actual installed compiler differs from the pinned original nightly")
        actual = Path(probe_tool([rustup, "which", "--toolchain", TOOLCHAIN, name], environment).strip())
        content = inputs.read(actual, 512 * 1024**2)
        tools[name] = {"invocation": str(invocation), "installed_binary": str(actual),
                       "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "version": version}
    return environment, tools


def product_bundle(target, source, build_directory):
    """Follow OSDK's real Run bundle manifest, not a target-directory search.

    execute_build_command chooses target/osdk/<kernel package>/bundle.toml.
    Bundle.consume_aster_bin copies the converted boot ELF into that directory
    and stores just its filename. The original Cargo symbol ELF is not used.
    """
    package = tomllib.loads(inputs.read(source / "kernel/asterinas/kernel/Cargo.toml", 1024**2).decode())["package"]
    require(package["name"] == "asterinas", "original product kernel package changed")
    bundle = canonical_directory(target / "osdk" / package["name"])
    manifest_path = bundle / "bundle.toml"
    raw = inputs.read(manifest_path, 1024**2)
    manifest = tomllib.loads(raw.decode("utf-8"))
    require(set(manifest) == {"initramfs", "aster_bin", "config", "action", "last_modified"}
            and manifest["action"] == "Run", "actual product bundle must be the original Run action, without a VM image")
    config = manifest["config"]
    require(type(config) is dict and config.get("target_arch") == "x86_64"
            and config.get("work_dir") == str(source / "kernel/asterinas/kernel"),
            "actual product bundle belongs to another source working directory or architecture")
    for build in (config.get("build"), config.get("run", {}).get("build")):
        require(type(build) is dict and build.get("profile") == "release"
                and build.get("features") == [inputs.PROFILE] and build.get("no_default_features") is False
                and build.get("override_configs") == [] and build.get("linux_x86_legacy_boot") is False
                and build.get("strip_elf") is False and build.get("rustflags") == "",
                "actual Run bundle changed the original release/default-feature/compiler configuration")
    run = config["run"]
    require(run.get("boot", {}).get("method") == "vmm-direct"
            and run["boot"].get("initramfs") == str(build_directory / "initramfs.cpio.gz")
            and run.get("grub", {}).get("boot_protocol") == "multiboot"
            and run.get("qemu", {}).get("path") == str(source / "support/build/record-qemu.py"),
            "actual product bundle boot inputs differ from kernel.sh")
    binary = manifest["aster_bin"]
    require(type(binary) is dict and binary.get("arch") == "x86_64" and binary.get("stripped") is False
            and binary.get("typ") == {"Elf": {"has_linux_header": False, "has_pvh_header": False,
                                               "has_multiboot_header": True, "has_multiboot2_header": True}},
            "actual bundle does not identify the original multiboot boot ELF")

    def member(record, limit):
        require(type(record) is dict and type(record.get("path")) is str
                and record["path"] not in ("", ".", "..")
                and Path(record["path"]).name == record["path"], "bundle member must be its original single relative filename")
        path = bundle / record["path"]
        content = inputs.read(path, limit)
        require(type(record.get("size")) is int and record["size"] == len(content),
                "actual bundle member differs from its manifest size")
        return path, content

    product, kernel_bytes = member(binary, inputs.MAX_KERNEL_BYTES)
    require(product.suffix == ".elf" and kernel_bytes[:6] == b"\x7fELF\x02\x01"
            and kernel_bytes[18:20] == b"\x03\x00", "bundle does not contain the actual OSDK EM_386 multiboot conversion")
    initramfs_path, initramfs_bytes = member(manifest["initramfs"], 8 * 1024**2)
    require(initramfs_bytes == inputs.read(build_directory / "initramfs.cpio.gz", 8 * 1024**2),
            "bundle retained another initramfs")
    frozen = freeze_bytes(raw, build_directory / "osdk-bundle.toml")
    require(inputs.read(manifest_path, 1024**2, frozen["sha256"]) == raw,
            "actual OSDK bundle manifest changed while retaining it")
    return product, {"source_manifest": str(manifest_path), "retained_manifest": frozen,
                     "action": manifest["action"], "kernel_source": str(product),
                     "kernel_sha256": hashlib.sha256(kernel_bytes).hexdigest(), "kernel_bytes": len(kernel_bytes),
                     "initramfs_source": str(initramfs_path), "initramfs_sha256": hashlib.sha256(initramfs_bytes).hexdigest()}


def perform_build(args, output, report):
    review_bytes = inputs.read(args.source_review, 1024**2, args.source_review_sha256)
    review = inputs.review_inputs(args.source_review, args.source_review_sha256)
    freeze_bytes(review_bytes, output / "source-review.json")
    builder = inputs.load_module("g2_kernel_original_entry_builder", HERE / "build_original_entry.py")
    roots = {"desktop": args.desktop_source, "hepta": args.hepta_source}
    snapshots = inputs.source_snapshots(roots, review, builder)
    shape, ordinary, _replay = inputs.original_helpers(args.desktop_source)
    owner_receipt, owner_bytes, owner_shape, _retained = inputs.owner_build(
        args.owner_build_receipt, args.owner_build_sha256, args.owner_elf, review, snapshots, shape, args.hepta_source)
    report.update(source_root=str(args.desktop_source), source_head=review["desktop"]["head"],
                  source_tree=review["desktop"]["tree"], source_review_sha256=args.source_review_sha256,
                  owner_sha256=hashlib.sha256(owner_bytes).hexdigest(), owner_bytes=len(owner_bytes),
                  original_owner_build={"path": str(args.owner_build_receipt), "sha256": args.owner_build_sha256},
                  original_owner_shape=owner_shape)
    freeze_bytes(owner_bytes, output / "original-owner.elf", 0o555)
    freeze_bytes(inputs.read(args.owner_build_receipt, 8 * 1024**2, args.owner_build_sha256),
                 output / "original-owner-build.json")
    before = ordinary.source_snapshot(args.desktop_source, review["desktop"]["head"], review["desktop"]["tree"])
    save(output / "source-before.json", before)
    save(output / "original-owner-source-before.json", snapshots)
    vdso = args.vdso_directory / "vdso_x86_64.so"
    inputs.read(vdso, 8 * 1024**2, args.vdso_sha256)
    busybox = inputs.read(args.busybox, 16 * 1024**2, args.busybox_sha256)
    report["dependencies"] = {"vdso": {"path": str(vdso), "sha256": args.vdso_sha256},
                              "busybox": {"path": str(args.busybox), "bytes": len(busybox), "sha256": args.busybox_sha256}}
    base_environment, toolchains = build_environment(args)
    report["toolchains"] = toolchains
    report["harness"] = {str(path): inputs.sha(path) for path in
                         (Path(__file__).resolve(), HERE / "native_owner_inputs.py", HERE / "native_owner_evidence.py",
                          HERE / "build_original_entry.py")}
    save(output / "pipeline.json", report)
    with ExitStack() as stack:
        report["resource_leases"] = [stack.enter_context(resource_lease(path))
                                     for path in sorted((args.cargo_home, args.osdk_target, args.kernel_target))]
        report["resources"] = {"cargo_home": str(args.cargo_home), "rustup_home": str(args.rustup_home),
                               "osdk_target": str(args.osdk_target), "kernel_target": str(args.kernel_target)}
        osdk_source = args.desktop_source / "kernel/asterinas/osdk"
        osdk_command = [args.cargo_home / "bin/cargo", "+" + TOOLCHAIN, "install", "--offline", "--locked",
                        "--force", "cargo-osdk", "--path", osdk_source, "--target-dir", args.osdk_target]
        report["osdk_source_root"] = str(osdk_source)
        osdk_environment = {**base_environment, "CARGO_TARGET_DIR": str(args.osdk_target)}
        report["osdk_environment"] = osdk_environment
        command_step("osdk-build", osdk_command, args.desktop_source, osdk_environment, output, report, args.osdk_timeout)
        osdk = args.cargo_home / "bin/cargo-osdk"
        built_osdk = freeze_file(osdk, output / "source-built-cargo-osdk", 512 * 1024**2, 0o555)
        report["osdk_sha256"] = built_osdk["sha256"]
        build_directory = output / "kernel-build"
        kernel_environment = {**base_environment, "CARGO_TARGET_DIR": str(args.kernel_target),
                              "A01_RUN_DIR": str(build_directory), "A01_SMP": "1", "A01_BUSYBOX": str(args.busybox),
                              "HEPTA_G1C_TRUSTED_OBSERVE": "0", "HEPTA_G1D_TRUSTED_CONTROL": "0",
                              "HEPTA_G2_TRUSTED_DAEMON": "1", "HEPTA_TRUSTED_INITIAL_ELF": str(output / "original-owner.elf")}
        report["kernel_environment"] = kernel_environment
        command_step("g2-kernel", ["/bin/bash", args.desktop_source / "support/build/kernel.sh", "kernel"],
                     args.desktop_source, kernel_environment, output, report, args.kernel_timeout)
        require(inputs.sha(osdk) == built_osdk["sha256"] == inputs.sha(output / "source-built-cargo-osdk"),
                "source-built OSDK changed during product compilation")
        generated_lock = args.kernel_target / "osdk/asterinas-run-base/Cargo.lock"
        lock_bytes = inputs.read(generated_lock, 4 * 1024**2)
        require(lock_bytes == inputs.read(args.desktop_source / "support/build/minimal/Cargo.lock", 4 * 1024**2)
                and len(tomllib.loads(lock_bytes.decode())["package"]) == 204,
                "actual generated product lock is not the original fixed 204-package graph")
        freeze_bytes(lock_bytes, build_directory / "generated.Cargo.lock")
        product, bundle_records = product_bundle(args.kernel_target, args.desktop_source, build_directory)
        report["product_bundle"] = bundle_records
        kernel = freeze_file(product, output / "product-kernel.elf", inputs.MAX_KERNEL_BYTES)
        require(kernel["sha256"] == bundle_records["kernel_sha256"], "actual bundle ELF changed before retention")
        kernel_bytes = inputs.read(output / "product-kernel.elf", inputs.MAX_KERNEL_BYTES, kernel["sha256"])
        embedded_offset = kernel_bytes.find(owner_bytes)
        require(embedded_offset >= 0, "compiled kernel does not contain the complete original include_bytes owner image")
        report["embedded_original_owner_offset"] = embedded_offset
        report.update(kernel_sha256=kernel["sha256"], kernel_bytes=kernel["bytes"], compiled_product_source=str(product))
        inputs.read(vdso, 8 * 1024**2, args.vdso_sha256)
        inputs.read(args.busybox, 16 * 1024**2, args.busybox_sha256)
        require(inputs.read(args.owner_elf, inputs.MAX_OWNER_BYTES, report["owner_sha256"]) == owner_bytes,
                "original owner changed across kernel compilation")
        require(inputs.read(args.source_review, 1024**2, args.source_review_sha256) == review_bytes,
                "source review bytes changed")
        for tool in toolchains.values():
            inputs.read(Path(tool["installed_binary"]), 512 * 1024**2, tool["sha256"])
        for path, expected in report["harness"].items():
            require(inputs.sha(Path(path)) == expected, "build harness changed during compilation")
        after = ordinary.source_snapshot(args.desktop_source, review["desktop"]["head"], review["desktop"]["tree"])
        save(output / "source-after.json", after)
        owner_after = inputs.source_snapshots(roots, review, builder)
        save(output / "original-owner-source-after.json", owner_after)
        require(before == after and snapshots == owner_after, "full compiled sources changed during the actual build")
        report["source_inputs_unchanged"] = True
        # Both compilation commands and source/artifact checks have completed.
        # The consumer always replays its full existing input gate; this flag
        # alone does not qualify any artifact or native execution.
        report["passed"] = True
        save(output / "pipeline.json", report)
        inputs.kernel_build(output, inputs.sha(output / "pipeline.json"), review, owner_bytes, ordinary)
        report["existing_kernel_input_gate_verified"] = True


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-review", "desktop-source", "hepta-source", "owner-build-receipt", "owner-elf", "cargo-home",
                 "rustup-home", "osdk-target", "kernel-target", "vdso-directory", "busybox", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("source-review-sha256", "owner-build-sha256", "vdso-sha256", "busybox-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--jobs", type=int, default=2, choices=range(1, 9))
    parser.add_argument("--osdk-timeout", type=int, default=1800)
    parser.add_argument("--kernel-timeout", type=int, default=3600)
    return parser.parse_args()


def main():
    args = parse_arguments()
    for key in ("source_review_sha256", "owner_build_sha256", "vdso_sha256", "busybox_sha256"):
        inputs.check_digest(getattr(args, key), "explicit " + key)
    directories = [args.desktop_source, args.hepta_source, args.cargo_home, args.rustup_home,
                   args.osdk_target, args.kernel_target, args.vdso_directory]
    for path in directories:
        canonical_directory(path)
    require(args.output.is_absolute() and not args.output.exists() and not args.output.is_symlink(),
            "output must be an explicit new absolute directory")
    canonical_directory(args.output.parent)
    require(args.output.parent / args.output.name == args.output and ".." not in args.output.parts,
            "output must have a canonical parent and no traversal")
    disjoint([args.desktop_source, args.hepta_source, args.cargo_home, args.rustup_home,
              args.osdk_target, args.kernel_target, args.vdso_directory, args.output])
    require(30 <= args.osdk_timeout <= 14400 and 30 <= args.kernel_timeout <= 14400,
            "bounded actual build timeouts must be between 30 and 14400 seconds")
    args.output.mkdir(mode=0o700)
    start = time.monotonic()
    report = {"schema": "hepta.original-native-owner-kernel-build.v1", "started_at": datetime.now(timezone.utc).isoformat(),
              "passed": False, "source_inputs_unchanged": False, "kernel_profile": inputs.PROFILE,
              "existing_kernel_input_gate_verified": False, "steps": [], "owner_executed": False,
              "native_role_verified": False, "persistent_cpu_verified": False, "recovery_verified": False,
              "g2_complete": False, "production_ready": False, "limits_changed": False,
              "kernel_flags_changed": False, "userspace_profile_changed": False}
    save(args.output / "pipeline.json", report)
    try:
        perform_build(args, args.output, report)
    except (Exception, KeyboardInterrupt) as error:
        report.update(passed=False, error=type(error).__name__ + ": " + str(error))
    finally:
        report["elapsed_seconds"] = time.monotonic() - start
        save(args.output / "pipeline.json", report)
    print(json.dumps({"passed": report["passed"], "pipeline": str(args.output / "pipeline.json"),
                      "sha256": inputs.sha(args.output / "pipeline.json"), "owner_executed": False}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
