#!/usr/bin/env python3
"""Run real upstream OSDK kernel tests without editing upstream manifests."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

TOOLCHAIN = "nightly-2026-07-21"
CRATES = {"ostd": "ostd", "aster-core": "kernel/core",
          "osdk-frame-allocator": "osdk/deps/frame-allocator",
          "aster-mlsdisk": "kernel/core/comps/mlsdisk"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, cwd, env, log):
    with log.open("w") as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crate", choices=CRATES, action="append")
    parser.add_argument("--output", type=Path, help="must not already exist")
    parser.add_argument("--test-name", help="optional complete test-path suffix, not a substring or crate selector")
    parser.add_argument("--permission-attr-smp", action="store_true",
                        help="run the fixed permission transaction regressions with exactly two CPUs")
    parser.add_argument("--g2-initial-root", action="store_true",
                        help="run the complete original N0 core suite plus the three G2 Process-state tests")
    parser.add_argument("--trusted-initial-sha256",
                        help="explicit digest of HEPTA_TRUSTED_INITIAL_ELF, used only to compile G2 ktests")
    parser.add_argument("--skip-osdk-install", action="store_true",
                        help="reuse an already source-built OSDK carrying the explicit-lock patch")
    args = parser.parse_args()
    if args.g2_initial_root:
        if args.permission_attr_smp or args.crate not in (None, ["aster-core"]) or args.test_name is not None:
            parser.error("--g2-initial-root requires the complete aster-core N0 suite without filtering or SMP")
        if not args.trusted_initial_sha256 or len(args.trusted_initial_sha256) != 64 or any(
                byte not in "0123456789abcdef" for byte in args.trusted_initial_sha256):
            parser.error("--g2-initial-root requires --trusted-initial-sha256")
        args.crate = ["aster-core"]
    elif args.trusted_initial_sha256:
        parser.error("--trusted-initial-sha256 is only valid with --g2-initial-root")
    if args.permission_attr_smp:
        if args.crate not in (None, ["aster-core"]) or args.test_name is not None:
            parser.error("--permission-attr-smp fixes the crate and complete test-name suffix")
        args.crate = ["aster-core"]
        args.test_name = "permission_attr_smp"
    if args.test_name:
        for crate in ("osdk-frame-allocator", "aster-mlsdisk"):
            if crate in (args.crate or CRATES):
                parser.error(f"{crate} requires its complete unfiltered default N0 suite")
    profile = "permission-attr-smp" if args.permission_attr_smp else "default"
    vcpus = 2 if args.permission_attr_smp else 1
    features = (["g2-trusted-daemon"] if args.g2_initial_root else
                ["permission-attr-smp-ktest"] if args.permission_attr_smp else [])
    here = Path(__file__).resolve().parent
    project = here.parents[2]
    upstream = project / "kernel/asterinas"
    env = os.environ.copy()
    env["RUSTUP_TOOLCHAIN"] = TOOLCHAIN
    cargo_home = Path(env.get("CARGO_HOME", str(Path.home() / ".cargo")))
    env["PATH"] = str(cargo_home / "bin") + os.pathsep + env.get("PATH", "")
    env["CARGO_BUILD_JOBS"] = env.get("CARGO_BUILD_JOBS", "2")
    env["CARGO_NET_GIT_FETCH_WITH_CLI"] = "true"
    env["OSDK_LOCAL_DEV"] = "1"
    env["VDSO_LIBRARY_DIR"] = env.get("VDSO_LIBRARY_DIR", str(project / "support/build/out/linux-vdso"))
    env["NETDEV"], env["ENABLE_KVM"], env["OVMF"] = "none", "0", "off"
    env["SMP"], env["MEM"], env["CONSOLE"] = str(vcpus), "512M", "ttyS0"
    env["A01_KTEST_PROFILE"] = profile
    env["A01_KTEST_TEST_NAME"] = args.test_name or ""
    env["BOOT_METHOD"], env["BOOT_PROTOCOL"], env["QEMU_DISPLAY"] = "vmm-direct", "multiboot", "none"
    env.pop("OSDK_CARGO_LOCK", None)
    parent_output = project / "support/build/out"
    parent_output.mkdir(parents=True, exist_ok=True)
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
    else:
        prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-ktest-")
        output = Path(tempfile.mkdtemp(prefix=prefix, dir=parent_output))
    trusted = None
    if args.g2_initial_root:
        supplied = env.get("HEPTA_TRUSTED_INITIAL_ELF")
        if not supplied:
            raise SystemExit("G2 Process ktests require HEPTA_TRUSTED_INITIAL_ELF as a compilation input")
        source = Path(supplied)
        if (not source.is_absolute() or not source.is_file() or source.is_symlink()
                or source.resolve(strict=True) != source or not 0 < source.stat().st_size <= 8 * 1024**2
                or digest(source) != args.trusted_initial_sha256):
            raise SystemExit("G2 ktest input must be a canonical pinned ELF within the original 8 MiB bound")
        content = source.read_bytes()
        if content[:7] != b"\x7fELF\x02\x01\x01" or content[16:20] != b"\x02\x00\x3e\x00":
            raise SystemExit("G2 ktest compilation input must be original x86_64 static ET_EXEC")
        frozen = output / "ktest-trusted-initial.elf"
        with frozen.open("xb") as stream:
            stream.write(content)
        frozen.chmod(0o444)
        if digest(source) != args.trusted_initial_sha256 or digest(frozen) != args.trusted_initial_sha256:
            raise SystemExit("G2 ktest compilation input changed while freezing")
        env["HEPTA_TRUSTED_INITIAL_ELF"] = str(frozen)
        trusted = {"source_path": str(source), "path": str(frozen), "sha256": args.trusted_initial_sha256,
                   "bytes": len(content), "compilation_input_only": True, "native_entry_execution_claimed": False}
    lock = (project / "support/build/out-kernel.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("another kernel build/test is using this workspace")
    # Keep the shared inode in place. Closing the descriptor releases its lock.
    with lock:
        verify = [sys.executable, "-I", str(project / "support/build/verify-source.py")]
        if run(verify, project, env, output / "source-inputs.json"):
            raise SystemExit(f"source verification failed; see {output}")
        commands = []
        if not args.skip_osdk_install:
            command = ["cargo", f"+{TOOLCHAIN}", "install", "--locked", "cargo-osdk", "--path", "osdk"]
            commands.append({"argv": command, "cwd": str(upstream)})
            (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
            if run(command, upstream, env, output / "osdk-install.log"):
                raise SystemExit(f"OSDK installation failed; see {output}")
        osdk = cargo_home / "bin/cargo-osdk"
        if not osdk.is_file():
            raise SystemExit("source-built cargo-osdk is missing")
        version = subprocess.check_output(["rustc", f"+{TOOLCHAIN}", "-Vv"], env=env, text=True)
        cargo_version = subprocess.check_output(["cargo", f"+{TOOLCHAIN}", "-Vv"], env=env, text=True)
        environment = {"toolchain": TOOLCHAIN, "rustc": version, "cargo": cargo_version,
                       "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip(),
                       "git_status": subprocess.check_output(["git", "status", "--short"], cwd=project, text=True),
                       "build_inputs_sha256": {
                           str(path.relative_to(project)): digest(path) for path in sorted([
                               upstream / "osdk/src/commands/build/mod.rs",
                               project / "support/build/verify-source.py",
                               *[path for path in here.rglob("*") if path.is_file() and "__pycache__" not in path.parts],
                           ])
                       },
                       "osdk_sha256": digest(osdk), "vdso_sha256": digest(Path(env["VDSO_LIBRARY_DIR"]) / "vdso_x86_64.so"),
                       "cargo_build_jobs": env["CARGO_BUILD_JOBS"], "test_name": args.test_name,
                       "ktest_profile": profile, "vcpus": vcpus, "features": features,
                       "osdk_install_skipped": args.skip_osdk_install,
                       "g2_initial_root": args.g2_initial_root, "ktest_trusted_initial": trusted}
        (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
        env["CARGO_TARGET_DIR"] = str(upstream / "target")
        results = []
        for crate in args.crate or CRATES:
            target = output / crate
            target.mkdir()
            lock_path = here / "locks" / f"{crate}.Cargo.lock"
            if not lock_path.is_file():
                raise SystemExit("prepare the fixed test-base locks with ktest/prepare-locks.py first")
            env["OSDK_CARGO_LOCK"] = str(lock_path)
            env["A01_KTEST_GUESTS"] = str(target / "guests")
            env["A01_KTEST_CRATE"] = crate
            command = ["cargo", f"+{TOOLCHAIN}", "osdk", "test", "--release", "--boot-method=vmm-direct",
                       "--grub-boot-protocol=multiboot", "--qemu-exe=" + str(here / "record-qemu.py"),
                       "--kcmd-args=loglevel=error", "--kcmd-args=earlycon", "--kcmd-args=console=ttyS0"]
            if args.test_name:
                command.append(args.test_name)
            if features:
                command.append("--features=" + ",".join(features))
            commands.append({"argv": command, "cwd": str(upstream / CRATES[crate]), "lock_sha256": digest(lock_path)})
            (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
            code = run(command, upstream / CRATES[crate], env, target / "osdk-test.log")
            (target / "osdk-exit-code.txt").write_text(str(code) + "\n")
            generated = upstream / "target/osdk" / f"{crate}-test-base" / "Cargo.lock"
            if generated.exists():
                shutil.copyfile(generated, target / "generated.Cargo.lock")
            if code:
                raise SystemExit(f"{crate}: OSDK failed ({code}); retained evidence: {target}")
            if not generated.is_file() or digest(generated) != digest(lock_path):
                raise SystemExit(f"{crate}: generated lock differs from the fixed test-base lock")
            if args.g2_initial_root:
                if digest(Path(trusted["path"])) != trusted["sha256"]:
                    raise SystemExit("G2 ktest compilation input changed during the actual build")
                checker = [sys.executable, "-I", str(here / "check-g2.py"), str(target / "guests")]
            elif args.permission_attr_smp:
                checker = [sys.executable, "-I", str(here / "check-permission-smp.py"), str(target / "guests")]
            else:
                checker = [sys.executable, "-I", str(here / "check.py"), str(target / "guests"), "--crate", crate]
            if args.test_name and not args.permission_attr_smp:
                checker.append("--allow-filtered")
            if run(checker, project, env, target / "result.json"):
                raise SystemExit(f"{crate}: guest evidence rejected; see {target / 'result.json'}")
            results.append(json.loads((target / "result.json").read_text()))
        (output / "result.json").write_text(json.dumps({"passed": True, "crates": results}, indent=2) + "\n")
    print(f"PASS: real kernel-mode tests; evidence: {output}")


if __name__ == "__main__":
    main()
