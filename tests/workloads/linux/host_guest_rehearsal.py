#!/usr/bin/env python3
"""Run A04's exact guest-run.sh under the ORIGINAL Linux kernel in a chroot.

This validates the *guest script and the real pinned ELF/loader/SQLite files*,
not Asterinas/QEMU compatibility. No disk mounts, network or production
services are touched. The only unpinned, ephemeral host additions are BusyBox
and its loader dependencies; those are recorded independently in the result.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def import_from(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guest = import_from("a04_shell_guest", HERE / "guest.py")
capture = import_from("a04_shell_capture", ROOT / "support/rootfs/capture.py")


def busybox_dependencies(path):
    """Only inspect the explicitly supplied, trusted host BusyBox binary."""
    p = subprocess.run(["ldd", str(path)], capture_output=True, text=True,
                       check=False, timeout=10)
    if p.returncode != 0 and "not a dynamic executable" not in (p.stdout + p.stderr):
        raise ValueError("ldd could not classify trusted BusyBox dependencies")
    if "not found" in p.stdout:
        raise ValueError("host BusyBox has unresolved dependencies")
    return sorted(set(re.findall(r"(?:=>\s*)?(/[\w+.,@/-]+)\s*\(", p.stdout)))


def stage_busybox(root, busybox):
    """Never modify manifest-pinned ELF/rootfs files; track all host additions."""
    if not busybox.is_file():
        raise ValueError("trusted BusyBox input is absent")
    included = {}
    sources = [("/bin/busybox", busybox)]
    sources.extend((path, Path(path)) for path in busybox_dependencies(busybox))
    for rel, source in sources:
        if not source.is_file() or not rel.startswith(("/bin/", "/lib/", "/lib64/", "/usr/lib/")):
            raise ValueError("unsupported BusyBox runtime dependency")
        dest = root / rel.lstrip("/")
        if dest.exists():
            if guest.sha_file(dest) != guest.sha_file(source):
                raise ValueError("BusyBox dependency differs from pinned rootfs library")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
        dest.chmod(0o555)
        included[rel] = guest.sha_file(dest)
    sh = root / "bin/sh"
    if sh.exists() or sh.is_symlink():
        raise ValueError("untrusted /bin/sh already exists in the rootfs overlay")
    sh.symlink_to("busybox")
    return included


def enter_chroot(root):
    # Dedicated process group permits bounded cleanup of grandchildren.
    os.setsid()
    os.chroot(root)
    os.chdir("/")
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)


def evaluate_output(stdout, exit_code, reference):
    """Exercise the actual guest serial parser without asserting a QEMU boot."""
    rc = 0 if exit_code == 0 else 1
    # Explicitly SYNTHETIC envelope: the original-Linux host output never
    # provides A01 kernel / QEMU evidence and cannot qualify a guest boot.
    serial = ("TRILLIONNIUM_A01_INIT_BEGIN\nTRILLIONNIUM_A01_BOOT_OK\n"
              "TRILLIONNIUM_A04_WORKLOAD_BEGIN\n" + stdout +
              f"TRILLIONNIUM_A04_RUNNER_STATUS={rc}\n"
              "TRILLIONNIUM_A04_WORKLOAD_END\n")
    names = [name for name, _, _ in guest.reference_elf_cases(reference)]
    report = guest.parse_serial(serial, reference,
                                {"cases": names, "a04_initramfs_sha256": "HOST_ONLY"},
                                qemu_exit=None, kernel_sha=None, image_sha=None)
    if report["guest_execution_verified"] or report["guest_compatibility_passed"]:
        raise RuntimeError("host shell replay was incorrectly accepted as a kernel guest")
    expected_skips = len(reference["cases"]) - len(names)
    passed = (exit_code == 0 and report["counts"] ==
              {"pass": len(names), "fail": 0, "not_run": expected_skips}
              and not report["boot_evidence"]["anomalies"])
    return passed, report


def run(rootfs_tar, manifest, reference, busybox, *, timeout=120):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("original x86_64 Linux host required")
    if os.geteuid() != 0:
        raise PermissionError("chroot requires root/CAP_SYS_CHROOT in a disposable environment")
    if not 5 <= timeout <= 600:
        raise ValueError("timeout must be in 5..600 seconds")
    with tempfile.TemporaryDirectory(prefix="a04-shell-rehearsal-") as tmp:
        root = Path(tmp) / "root"
        files_verified = capture.extract_verified_tar(rootfs_tar, manifest, root)
        additions = stage_busybox(root, busybox)
        root.chmod(0o755)
        writable = root / "tmp"
        writable.mkdir(mode=0o1777)
        writable.chmod(0o1777)
        script = root / "test/a04/guest-run.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_bytes(guest.make_guest_script(guest.reference_elf_cases(reference)))
        script.chmod(0o555)
        env = {"PATH": "/bin:/usr/local/bin/a04", "LC_ALL": "C", "TZ": "UTC",
               "HOME": "/tmp"}
        proc = subprocess.Popen(["/bin/busybox", "sh", "/test/a04/guest-run.sh"],
                                cwd="/", env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                preexec_fn=lambda: enter_chroot(root))
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Shell-run probes can spawn grandchildren. Killing only the shell
            # would leave orphan C ELF tasks and file-lock holders behind.
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate(timeout=10)
        passed, facts = evaluate_output(stdout, proc.returncode, reference)
        return {"schema": 1, "kind": "a04_original_linux_chroot_guest_shell_rehearsal",
                "passed": passed and not timed_out, "exit_code": proc.returncode,
                "timed_out": timed_out,
                "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
                "rootfs_tar_sha256": guest.sha_file(rootfs_tar),
                "rootfs_manifest_sha256": guest.sha_file(manifest),
                "files_verified": files_verified,
                "host_busybox_sha256": guest.sha_file(busybox),
                "host_only_runtime_additions": additions,
                "counts": facts["counts"],
                "parser_anomalies": facts["boot_evidence"]["anomalies"],
                "qemu_used": False, "guest_execution_verified": False,
                "hepta_w1_verified": False, "writable_area": "disposable_chroot_directory_not_tmpfs"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tar", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--busybox", type=Path, default=Path("/usr/bin/busybox"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    if args.output.exists() or args.output.is_symlink():
        ap.error("refusing to overwrite previous evidence")
    try:
        baseline = json.loads(args.reference.read_text())
        result = run(args.tar, args.manifest, baseline, args.busybox, timeout=args.timeout)
        result["linux_reference_sha256"] = guest.sha_file(args.reference)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired,
            json.JSONDecodeError, KeyError) as exc:
        ap.exit(2, f"A04 original Linux guest script rehearsal blocked: {type(exc).__name__}: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"kind": result["kind"], "passed": result["passed"],
                      "counts": result["counts"], "qemu_used": False}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
