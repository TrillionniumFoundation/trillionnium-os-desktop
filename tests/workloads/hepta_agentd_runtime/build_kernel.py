#!/usr/bin/env python3
"""Build and boot the reviewed ordinary kernel; retain its original evidence."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prepare_inputs as preparation
import run_agentd_runtime as gate


def checked_boot(source, directory):
    path = source / "support/build/check-boot.py"
    spec = importlib.util.spec_from_file_location("reviewed_ordinary_boot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_boot(directory, live_artifacts=True)


def retain_build(args, roots, output, report):
    review_path = HERE / "source-review.json"
    gate.pinned(review_path, args.expected_source_review_sha256, 1024 * 1024)
    reviewed = preparation.verify_sources(roots)
    gate.require(not output.exists() and not output.is_symlink(), "output must be new")
    gate.require(all(not output.resolve().is_relative_to(root) for root in roots.values()),
                 "output must be outside source checkouts")
    gate.require(args.vdso.resolve(strict=True).is_dir(), "reviewed VDSO directory required")
    vdso = args.vdso.resolve(strict=True) / "vdso_x86_64.so"
    gate.pinned(vdso, "27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3", 1024 * 1024)
    output.mkdir(mode=0o700)
    report["output_created"] = True
    qualification = output / "product-qualification"
    product = qualification / "product-boot"
    command = ["/usr/bin/python3", "-I", "-B",
               str(roots["desktop"] / "tests/kernel/control/run_queryabi_candidate_guest.py"),
               "--expected-source-head", gate.DESKTOP["head"],
               "--expected-source-tree", gate.DESKTOP["tree"],
               "--timeout", "120", "--output", str(qualification)]
    if args.target_dir is not None:
        command.extend(["--target-dir", str(args.target_dir.absolute())])
    environment = {
        **gate.abi.ENV, "HOME": str(Path.home()),
        "PATH": str(args.cargo_home.resolve(strict=True) / "bin") + ":/usr/bin:/bin:/usr/sbin:/sbin",
        "CARGO_HOME": str(args.cargo_home.resolve(strict=True)),
        "RUSTUP_HOME": str(args.rustup_home.resolve(strict=True)),
        "VDSO_LIBRARY_DIR": str(args.vdso.resolve(strict=True)),
        "A01_QEMU_TIMEOUT": "300", "A01_SMP": "1",
        "CARGO_BUILD_JOBS": str(args.jobs), "PYTHONDONTWRITEBYTECODE": "1",
    }
    report["command"] = command
    report["environment_keys"] = sorted(environment)
    helper = preparation.original_helper(roots["desktop"])
    # OSDK_LOCAL_DEV embeds its source/OSTD directory. An installed binary
    # built in another checkout is not interchangeable even at the same version.
    cargo = args.cargo_home.resolve(strict=True) / "bin/cargo"
    gate.require(cargo.is_file(), "Cargo Rustup proxy required in cargo-home/bin")
    osdk_command = [str(cargo), "+nightly-2026-07-21", "install", "--locked", "--force",
                    "cargo-osdk", "--path", str(roots["desktop"] / "kernel/asterinas/osdk")]
    report["osdk_command"] = osdk_command
    preparation.original_call(helper, "bounded_command", osdk_command,
                              roots["desktop"] / "kernel/asterinas",
                              {**environment, "OSDK_LOCAL_DEV": "1",
                               "CARGO_TARGET_DIR": str(output / "osdk-target")},
                              output / "osdk-build.log", 7200)
    osdk = args.cargo_home.resolve(strict=True) / "bin/cargo-osdk"
    gate.require(osdk.is_file() and not osdk.is_symlink(), "source-built OSDK binary missing")
    osdk_identity = {"path": str(osdk), "sha256": gate.sha(osdk), "command": osdk_command,
                     "source": gate.DESKTOP, "local_development_source": True}
    preparation.verify_sources(roots)
    preparation.original_call(helper, "bounded_command", command, roots["desktop"], environment,
                              output / "build-and-boot.log", 7200)
    gate.require(gate.sha(osdk) == osdk_identity["sha256"], "OSDK changed during qualification")
    candidate = gate.json_value((qualification / "result.json").read_bytes())
    gate.require(candidate.get("passed") is True and candidate.get("stage") == "complete"
                 and candidate.get("source_inputs_unchanged") is True,
                 "original ordinary build/QueryAbi qualification failed")
    snapshots = [gate.json_value((qualification / name).read_bytes())
                 for name in ("source-before.json", "source-after-boot.json", "source-after-guest.json")]
    gate.require(snapshots[0] == snapshots[1] == snapshots[2], "full tracked source snapshots differ")
    for name in ("make-exit-code.txt", "log-exit-code.txt", "run-exit-code.txt"):
        gate.require((product / name).read_text().strip() == "0", "ordinary build or boot failed: " + name)
    boot = checked_boot(roots["desktop"], product)
    qemu = gate.json_value((product / "qemu.json").read_bytes())
    raw_command = (product / "command.sh").read_text()
    gate.require("HEPTA_TRUSTED_INITIAL_ELF" not in raw_command
                 and "g1c-trusted-observe" not in raw_command
                 and "g1d-trusted-control" not in raw_command,
                 "ordinary build must not select a trusted test image")
    kernel = Path(qemu["artifacts"]["-kernel"]["path"])
    if not kernel.is_absolute():
        kernel = Path(qemu["cwd"]) / kernel
    gate.pinned(kernel, qemu["artifacts"]["-kernel"]["sha256"], 64 * 1024**2)
    gate.require(preparation.verify_sources(roots) == reviewed, "source changed during ordinary build")
    gate.pinned(review_path, args.expected_source_review_sha256, 1024 * 1024)
    binaries = {"kernel.elf": kernel}
    for name, option in (("initramfs.cpio.gz", "-initrd"), ("bios.bin", "-bios")):
        path = Path(qemu["artifacts"][option]["path"])
        binaries[name] = path if path.is_absolute() else Path(qemu["cwd"]) / path
    for name, path in binaries.items():
        shutil.copyfile(path, output / name)
        (output / name).chmod(0o444)
        gate.require(gate.sha(output / name) == gate.sha(path), "boot input changed while freezing")
    checked_boot(roots["desktop"], product)
    receipt = {
        "schema": "hepta.native-original-runtime-build.v1", "sources": gate.SOURCES,
        "build_sources": {"desktop": gate.DESKTOP}, "kernel_profile": "ordinary-os",
        "built": True, "source_clean": True, "binary_sha256": {"kernel": gate.sha(output / "kernel.elf")},
        "commands": [osdk_command, command], "source_files": reviewed,
        "build_tools": {"cargo_osdk": osdk_identity},
        "source_review_sha256": args.expected_source_review_sha256,
        "ordinary_boot": boot, "ordinary_queryabi": candidate,
        "source_file_count": len(snapshots[0]["files"]),
        "kernel_built_in_this_import": True,
        "guest_executed_in_this_import": True, "runtime_executed": False,
        "f1_completed": False, "g2_completed": False,
        "attestation": "locally executed reviewed ordinary build and boot; not remote attestation",
        "original_evidence": {
            name: {"path": "product-boot/" + name,
                   "sha256": gate.sha(product / name), "bytes": (product / name).stat().st_size}
            for name in ("command.sh", "environment.log", "source-inputs.json", "qemu.json", "serial.log",
                         "run_kernel.log", "make-exit-code.txt", "log-exit-code.txt", "run-exit-code.txt")
        },
    }
    for record in receipt["original_evidence"].values():
        record["path"] = "product-qualification/" + record["path"]
    gate.save(output / "kernel-build.json", receipt)
    report.update(built=True, boot_passed=True, kernel_sha256=receipt["binary_sha256"]["kernel"],
                  kernel_receipt_sha256=gate.sha(output / "kernel-build.json"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--desktop-source", type=Path, required=True)
    parser.add_argument("--hepta-source", type=Path, required=True)
    parser.add_argument("--expected-source-review-sha256", required=True)
    parser.add_argument("--cargo-home", type=Path, default=Path.home() / ".cargo")
    parser.add_argument("--rustup-home", type=Path, default=Path.home() / ".rustup")
    parser.add_argument("--vdso", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--target-dir", type=Path, help="original Cargo target cache; source checks remain mandatory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {"schema": "hepta.native-original-kernel-build-result.v1", "built": False,
              "boot_passed": False, "executed": False, "sources": gate.SOURCES,
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    if not args.execute:
        print(json.dumps({**report, "status": "disabled; explicit --execute required"}, sort_keys=True))
        return 0
    output = args.output.absolute()
    roots = {"desktop": args.desktop_source.absolute(), "hepta": args.hepta_source.absolute()}
    try:
        report["executed"] = True
        retain_build(args, roots, output, report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created"):
        gate.save(output / "build-result.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["built"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
