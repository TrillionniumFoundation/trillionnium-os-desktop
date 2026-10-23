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
CRATES = {"ostd": "ostd", "aster-core": "kernel/core"}


def clean_source_identity(project):
    """Pin a complete committed source tree for the opt-in qualification."""
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=project, text=True)
    if status:
        raise SystemExit("g1c post-exec ktests require a committed, unchanged tracked source tree")
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=project).decode().split("\0")
    source_prefixes = ("kernel/asterinas/", "libs/", "support/build/")
    if any(name.startswith(source_prefixes) and name.endswith((".rs", ".py", ".toml", ".lock"))
           for name in untracked):
        raise SystemExit("g1c post-exec ktests refuse untracked build/test source inputs")
    return {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip(),
            "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=project, text=True).strip()}


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
    parser.add_argument("--g1c-postexec-observe", action="store_true",
                        help="run the complete one-CPU core suite with g1c and all post-exec fence regressions")
    parser.add_argument("--trusted-initial-elf", type=Path,
                        help="reviewed static ELF to freeze for --g1c-postexec-observe; never a role credential")
    parser.add_argument("--skip-osdk-install", action="store_true",
                        help="reuse an already source-built OSDK carrying the explicit-lock patch")
    args = parser.parse_args()
    if args.g1c_postexec_observe:
        if args.permission_attr_smp or args.crate not in (None, ["aster-core"]) or args.test_name is not None:
            parser.error("--g1c-postexec-observe requires the complete aster-core suite on one CPU")
        if args.trusted_initial_elf is None:
            parser.error("--g1c-postexec-observe requires --trusted-initial-elf")
        args.crate = ["aster-core"]
    elif args.trusted_initial_elf is not None:
        parser.error("--trusted-initial-elf is only valid with --g1c-postexec-observe")
    if args.permission_attr_smp:
        if args.crate not in (None, ["aster-core"]) or args.test_name is not None:
            parser.error("--permission-attr-smp fixes the crate and complete test-name suffix")
        args.crate = ["aster-core"]
        args.test_name = "permission_attr_smp"
    profile = "permission-attr-smp" if args.permission_attr_smp else "default"
    vcpus = 2 if args.permission_attr_smp else 1
    features = ["permission-attr-smp-ktest"] if args.permission_attr_smp else []
    if args.g1c_postexec_observe:
        profile, features = "g1c-postexec-observe", ["g1c-trusted-observe"]
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
    lock = (project / "support/build/out-kernel.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("another kernel build/test is using this workspace")
    # Keep the shared inode in place. Closing the descriptor releases its lock.
    with lock:
        source_identity = clean_source_identity(project) if args.g1c_postexec_observe else None
        verify = [sys.executable, "-I", str(project / "support/build/verify-source.py")]
        if run(verify, project, env, output / "source-inputs.json"):
            raise SystemExit(f"source verification failed; see {output}")
        commands = []
        trusted_manifest = None
        if args.g1c_postexec_observe:
            command = [sys.executable, "-I", str(project / "support/build/prepare-trusted-image.py"),
                       "--input", str(args.trusted_initial_elf.resolve(strict=True)),
                       "--output", str(output / "trusted-initial.elf"),
                       "--manifest", str(output / "trusted-initial-manifest.json"),
                       "--profile", "g1c-trusted-observe"]
            commands.append({"argv": command, "cwd": str(project)})
            (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
            if run(command, project, env, output / "trusted-initial-prepare.log"):
                raise SystemExit(f"trusted initial ELF preparation failed; see {output}")
            env["HEPTA_TRUSTED_INITIAL_ELF"] = str(output / "trusted-initial.elf")
            trusted_manifest = json.loads((output / "trusted-initial-manifest.json").read_text())
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
                       "osdk_install_skipped": args.skip_osdk_install}
        if args.g1c_postexec_observe:
            environment.update(source_identity=source_identity, trusted_initial=trusted_manifest,
                               qualification="kernel-object-tests-only", native_sealed_launch_qualified=False,
                               g2_qualified=False)
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
            if args.permission_attr_smp:
                checker = [sys.executable, "-I", str(here / "check-permission-smp.py"), str(target / "guests")]
            elif args.g1c_postexec_observe:
                checker = [sys.executable, "-I", str(here / "check-g1c-postexec.py"), str(target / "guests"),
                           "--environment", str(output / "environment.json"),
                           "--commands", str(output / "commands.json")]
            else:
                checker = [sys.executable, "-I", str(here / "check.py"), str(target / "guests"), "--crate", crate]
            if args.test_name and not args.permission_attr_smp:
                checker.append("--allow-filtered")
            if run(checker, project, env, target / "result.json"):
                raise SystemExit(f"{crate}: guest evidence rejected; see {target / 'result.json'}")
            results.append(json.loads((target / "result.json").read_text()))
        if args.g1c_postexec_observe and clean_source_identity(project) != source_identity:
            raise SystemExit("source identity changed during g1c post-exec ktests")
        (output / "result.json").write_text(json.dumps({"passed": True, "crates": results}, indent=2) + "\n")
    print(f"PASS: real kernel-mode tests; evidence: {output}")


if __name__ == "__main__":
    main()
