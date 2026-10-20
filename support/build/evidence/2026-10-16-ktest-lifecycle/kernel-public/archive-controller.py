#!/usr/bin/env python3
"""Freeze this completed native boot and validate the retained byte bindings."""
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


scratch = Path(__file__).resolve().parent
project = scratch / "trillionnium-os-desktop"
work = scratch / "a01-next6-build"
run = work / "support/build/out/next7-boot-01"
archive = project / "support/build/evidence/2026-10-16-ktest-lifecycle/kernel-public"
archive.mkdir(parents=True, exist_ok=False)
for path in sorted(run.iterdir()):
    if not path.is_file():
        raise SystemExit("unexpected boot output directory")
    shutil.copyfile(path, archive / path.name)
for source, name in ((scratch / "next7-boot-invocation.json", "invocation.json"),
                     (scratch / "next7-boot-console.log", "outer-console.log"),
                     (scratch / "next7-real-run.py", "outer-controller.py"),
                     (scratch / "next7-boot-worktree-sync.json", "worktree-sync.json"),
                     (scratch / "next7-sync-boot-worktree.py", "worktree-sync-controller.py")):
    shutil.copyfile(source, archive / name)
record = json.loads((archive / "qemu.json").read_text())
invocation = json.loads((archive / "invocation.json").read_text())
cleanup = json.loads((archive / "manifest-cleanup.json").read_text())
if invocation["outer_exit_code"] != 0 or record["raw_exit_code"] != 33 or record["timed_out"]:
    raise SystemExit("boot did not pass")
if cleanup["outcome"] != "owned_removed" or not cleanup["passed"]:
    raise SystemExit("unexpected cleanup outcome")
artifacts = []
for option in ("-kernel", "-initrd"):
    expected = record["artifacts"][option]
    raw = Path(expected["path"]).read_bytes()
    if len(raw) != expected["size"] or sha(raw) != expected["sha256"]:
        raise SystemExit("artifact does not match actual QEMU record")
    if option == "-kernel":
        compressed = gzip.compress(raw, mtime=0)
        destination = archive / "kernel.elf.gz"
        destination.write_bytes(compressed)
        if gzip.decompress(destination.read_bytes()) != raw:
            raise SystemExit("kernel archive mismatch")
    else:
        destination = archive / "initramfs.cpio.gz"
        if destination.read_bytes() != raw:
            raise SystemExit("retained initramfs mismatch")
    artifacts.append({"option": option, "raw_size": len(raw), "raw_sha256": sha(raw),
                      "archive": destination.name, "archive_sha256": sha(destination.read_bytes())})
serial = (archive / "serial.log").read_bytes()
if sha(serial) != record["serial_sha256"]:
    raise SystemExit("serial byte binding differs")
checker = subprocess.run([sys.executable, "-I", str(project / "support/build/check-boot.py"), str(archive)],
                         capture_output=True, text=True)
(archive / "offline-checker.log").write_text(checker.stdout + checker.stderr)
if checker.returncode:
    raise SystemExit("offline checker rejected archive")
manifest = work / "kernel/asterinas/kernel/OSDK.toml"
observation = {"kind": "post_boot_pathname_observation_only", "path": str(manifest),
               "owned_cleanup": cleanup, "present_after_cleanup": False,
               "writer_or_cause_identified": False}
with (work / "support/build/out-kernel.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if manifest.exists() or manifest.is_symlink():
        info = manifest.lstat()
        observation.update(present_after_cleanup=True, device=info.st_dev, inode=info.st_ino,
                           size=info.st_size, mode=info.st_mode)
        if manifest.is_file() and not manifest.is_symlink():
            with manifest.open("rb") as stream:
                before = os.fstat(stream.fileno())
                raw = stream.read()
                after = os.fstat(stream.fileno())
            observation.update(sha256=sha(raw), stable_fd_read=(before == after))
            (archive / "post-boot-existing-manifest.toml").write_bytes(raw)
    observation["git_status"] = subprocess.check_output(["git", "status", "--short"], cwd=work, text=True)
(archive / "post-boot-manifest-observation.json").write_text(json.dumps(observation, indent=2) + "\n")
binding = {"source_commit": invocation["source_head"], "source_tree": invocation["source_tree"],
           "actual_outer_exit_code": 0, "raw_qemu_exit_code": 33, "offline_checker_exit_code": checker.returncode,
           "target_reuse": invocation["target_cache_reused_from"], "artifacts": artifacts,
           "serial_bytes": len(serial), "serial_sha256": sha(serial),
           "helper_sha256": cleanup["helper_sha256"], "owned_manifest_cleanup_passed": True}
(archive / "artifact-bindings.json").write_text(json.dumps(binding, indent=2) + "\n")
shutil.copyfile(Path(__file__), archive / "archive-controller.py")
(archive / "README.md").write_text("""# Actual public kernel boot after custody fix

Published source a770f31a868d805524065c65a2bcfcbcf10ede2e, exact tree
af2e1bc4d215ac4dc6eadd0cecc147e1673b1c1e. The real public
`support/build/kernel.sh run_kernel` exited 0 and QEMU exited raw33 with
complete serial and initramfs markers. Both the live wrapper check and the
offline archive check passed. Existing Cargo target reuse is explicit; this
is not a second empty-target full compilation. The separate full kernel-mode
test run in this phase built and ran both test kernels.

The standalone supervisor reaped its worker. The new cleanup helper captured
and removed the exact FD8-owned inode, removed its private custody directory,
and returned 0. `post-boot-manifest-observation.json` records any later public
entry separately. A new entry appearing after completed cleanup does not
identify its writer or change the captured inode result; this archive never
deletes that later entry. The wrapper still refuses to overwrite existing
manifests on a later call.

Actual commands, selected environment, source verification, serial, QEMU argv,
kernel/initramfs and cleanup helper hash remain byte-bound in the adjacent
records. The retained ELF matches this QEMU record; no bit reproducibility
claim is made from reusing the same target cache. No host Linux kernel or ISO
installer is used as boot acceptance.
""")
files = sorted(p for p in archive.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
(archive / "SHA256SUMS").write_text("".join(f"{sha(p.read_bytes())}  {p.relative_to(archive)}\n" for p in files))
print(json.dumps(binding, indent=2))
print("files", len(files) + 1, "manifest", sha((archive / "SHA256SUMS").read_bytes()))
