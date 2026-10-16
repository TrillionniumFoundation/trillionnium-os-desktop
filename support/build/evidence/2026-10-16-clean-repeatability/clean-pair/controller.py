#!/usr/bin/env python3
"""Two real clean-target builds at one fixed path; keep all boot evidence."""
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys

scratch = Path(__file__).resolve().parent
work = scratch / "a01-next8-repeat"
destination = scratch / "next8-repeatability"
expected_head = sys.argv[1]
target = work / "kernel/asterinas/target"
sha = lambda data: hashlib.sha256(data).hexdigest()
write = lambda path, data: path.write_text(json.dumps(data, indent=2) + "\n")
identity = lambda info: {name: getattr(info, name) for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")}

if destination.exists():
    raise SystemExit("new pair output required")
destination.mkdir(mode=0o700)
if target.exists() or target.is_symlink():
    raise SystemExit("first target must be absent")
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()
if head != expected_head:
    raise SystemExit("unexpected source HEAD")
subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=work, check=True)
environment = dict(os.environ)
for variable in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"):
    environment.pop(variable, None)
selected = {
    "CARGO_HOME": str(scratch / "toolchains/cargo"), "RUSTUP_HOME": str(scratch / "toolchains/rustup"),
    "RUSTUP_TOOLCHAIN": "nightly-2026-07-21", "CARGO_NET_OFFLINE": "true",
    "CARGO_TARGET_DIR": str(target), "CARGO_BUILD_JOBS": "2",
    "VDSO_LIBRARY_DIR": str(scratch / "linux-vdso"), "A01_QEMU_TIMEOUT": "300",
    "ASTER_BUILD_TIMESTAMP": "Thu Jan  1 00:00:00 UTC 1970", "SOURCE_DATE_EPOCH": "0",
    "TZ": "UTC", "LC_ALL": "C",
}
environment.update(selected)
environment["PATH"] = selected["CARGO_HOME"] + "/bin:" + environment["PATH"]
summary = {"kind": "same_host_same_absolute_path_two_clean_target_builds", "source_commit": head,
           "source_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=work, text=True).strip(),
           "cwd": str(work), "environment": selected, "explicitly_unset": ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"],
           "controller_sha256": sha(Path(__file__).read_bytes()), "started_utc": datetime.now(timezone.utc).isoformat(),
           "host_identity": {"nodename": os.uname().nodename, "effective_uid": os.geteuid(),
                             "effective_username": pwd.getpwuid(os.geteuid()).pw_name},
           "cross_directory_or_cross_host_reproducibility_claimed": False, "runs": []}
write(destination / "pair.json", summary)
shutil.copyfile(Path(__file__), destination / "controller.py")

for label in ("a", "b"):
    if target.exists() or target.is_symlink():
        raise SystemExit("target is not clean before build " + label)
    run = work / "support/build/out" / ("next8-clean-" + label)
    output = destination / label
    output.mkdir()
    env = dict(environment, A01_RUN_DIR=str(run))
    entry = {"label": label, "argv": ["support/build/kernel.sh", "run_kernel"],
             "target_absent_before_launch": True, "run_output": str(run), "outer_exit": None,
             "started_utc": datetime.now(timezone.utc).isoformat()}
    write(output / "invocation.json", entry)
    print(json.dumps({"starting": label, "source": head, "fresh_target": str(target)}), flush=True)
    with (output / "console.log").open("wb") as log:
        process = subprocess.Popen(entry["argv"], cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        entry["entry_pid"] = process.pid
        write(output / "invocation.json", entry)
        for line in process.stdout:
            log.write(line)
            log.flush()
            if any(marker in line for marker in (b"Compiling ", b"Finished ", b"PASS:", b"error:", b"A01_KERNEL_SUPERVISOR")):
                print(label + ": " + line.decode(errors="replace").rstrip(), flush=True)
        code = process.wait()
    entry.update(outer_exit=code, completed_utc=datetime.now(timezone.utc).isoformat())
    console = (output / "console.log").read_bytes()
    entry.update(console_sha256=sha(console), console_bytes=len(console))
    write(output / "invocation.json", entry)
    if run.exists():
        shutil.copytree(run, output / "run")
    if code != 0:
        summary.update(stopped_at=label, failure="public entry nonzero", runs=summary["runs"] + [entry])
        write(destination / "pair.json", summary)
        raise SystemExit(code if code > 0 else 128 - code)
    qemu = json.loads((output / "run/qemu.json").read_text())
    if qemu["raw_exit_code"] != 33 or qemu["timed_out"]:
        raise SystemExit("native QEMU did not pass")
    initramfs = (output / "run/initramfs.cpio.gz").read_bytes()
    serial = (output / "run/serial.log").read_bytes()
    if (sha(initramfs) != qemu["artifacts"]["-initrd"]["sha256"]
            or len(initramfs) != qemu["artifacts"]["-initrd"]["size"]
            or sha(serial) != qemu["serial_sha256"]):
        raise SystemExit("copied initramfs/serial bytes differ from actual QEMU record")
    artifact = qemu["artifacts"]["-kernel"]
    with Path(artifact["path"]).open("rb") as stream:
        before = identity(os.fstat(stream.fileno()))
        raw = stream.read()
        after = identity(os.fstat(stream.fileno()))
    if before != after or len(raw) != artifact["size"] or sha(raw) != artifact["sha256"]:
        raise SystemExit("kernel bytes differ from real QEMU record")
    compressed = gzip.compress(raw, mtime=0)
    (output / "kernel.elf.gz").write_bytes(compressed)
    if gzip.decompress((output / "kernel.elf.gz").read_bytes()) != raw:
        raise SystemExit("kernel gzip verification failed")
    entry.update(raw_qemu_exit=33, kernel_sha256=sha(raw), kernel_size=len(raw), kernel_read_identity=before,
                 initramfs_sha256=qemu["artifacts"]["-initrd"]["sha256"], serial_sha256=qemu["serial_sha256"],
                 kernel_gzip_sha256=sha(compressed), git_status_after=subprocess.check_output(["git", "status", "--short"], cwd=work, text=True))
    write(output / "invocation.json", entry)
    summary["runs"].append(entry)
    write(destination / "pair.json", summary)
    print(json.dumps({"completed": label, "actual_outer_exit": code, "raw_qemu": 33, "kernel_sha256": sha(raw)}), flush=True)
    if label == "a":
        # This cache did not exist before our build. Its real kernel and all
        # output were captured above. Atomically take custody before deletion.
        with (work / "support/build/out-kernel.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if target.is_symlink() or target.resolve() != work / "kernel/asterinas/target":
                raise SystemExit("unexpected target cache path")
            subprocess.run(["git", "check-ignore", "-q", str(target)], cwd=work, check=True)
            old = target.stat()
            custody = work / "support/build/out/next8-owned-target-cache-a"
            if custody.exists() or custody.is_symlink():
                raise SystemExit("cache custody already exists")
            os.rename(target, custody)
            captured = custody.stat()
            if (old.st_dev, old.st_ino) != (captured.st_dev, captured.st_ino):
                raise SystemExit("cache identity changed; preserved without deletion")
            sizes = subprocess.check_output(["du", "-sb", str(custody)], text=True)
            cache_record = {"kind": "delete_only_this_driver_fresh_generated_target_cache", "original": str(target),
                            "custody": str(custody), "identity": identity(captured), "du_apparent": sizes,
                            "artifacts_verified_before_deletion": True}
            shutil.rmtree(custody)
            cache_record.update(custody_removed=not custody.exists(), target_absent=not target.exists())
            manifest = work / "kernel/asterinas/kernel/OSDK.toml"
            if manifest.exists() or manifest.is_symlink():
                preserved = work / "support/build/out/next8-preserved-after-a.toml"
                if preserved.exists() or preserved.is_symlink():
                    raise SystemExit("manifest preservation destination exists")
                os.rename(manifest, preserved)
                cache_record["foreign_manifest_preserved_path"] = str(preserved)
                if preserved.is_file() and not preserved.is_symlink():
                    cache_record["foreign_manifest_sha256"] = sha(preserved.read_bytes())
            write(destination / "between-builds.json", cache_record)

summary.update(completed_utc=datetime.now(timezone.utc).isoformat(), all_public_boots_passed=True,
               same_host_same_path_kernel_equal=summary["runs"][0]["kernel_sha256"] == summary["runs"][1]["kernel_sha256"],
               initramfs_equal=summary["runs"][0]["initramfs_sha256"] == summary["runs"][1]["initramfs_sha256"])
write(destination / "pair.json", summary)
print(json.dumps({key: summary[key] for key in ("all_public_boots_passed", "same_host_same_path_kernel_equal", "initramfs_equal")}), flush=True)
raise SystemExit(0 if summary["same_host_same_path_kernel_equal"] and summary["initramfs_equal"] else 2)
