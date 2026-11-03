#!/usr/bin/env python3
"""Build and boot the exact old-root workload control in a fresh worktree.

Only the production credential selection changes. The actual compiled C probe,
guest runner, image verification and frozen dependencies remain identical to
the positive build. A timeout or arbitrary guest failure never passes.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_g1d_guest as guest

ROOT, require, save, digest = guest.ROOT, guest.require, guest.save_json, guest.digest
SOURCE = "kernel/asterinas/kernel/core/src/process/process/init_proc/trusted_roles.rs"
BEFORE = b"        let credentials = if index == 1 { workload_credentials()? } else { Credentials::new_root() };\n"
AFTER = b"        let credentials = if index == 1 { Credentials::new_root() } else { Credentials::new_root() };\n"
FORMATTED_BEFORE = b"""        let credentials = if index == 1 {
            workload_credentials()?
        } else {
            Credentials::new_root()
        };
"""
FORMATTED_AFTER = FORMATTED_BEFORE.replace(b"workload_credentials()?", b"Credentials::new_root()")
IDENTIFIED_BEFORE = FORMATTED_BEFORE.replace(b"workload_credentials()?", b"workload_credentials(WORKLOAD_ID)?")
IDENTIFIED_AFTER = FORMATTED_AFTER
SELECTIONS = ((BEFORE, AFTER), (FORMATTED_BEFORE, FORMATTED_AFTER),
              (IDENTIFIED_BEFORE, IDENTIFIED_AFTER))
LOG_LIMIT = 64 * 1024 * 1024


def read(path, limit=LOG_LIMIT):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit,
            "missing, linked or oversized evidence: " + str(path))
    return path.read_bytes()


def mutation(source):
    # Keep the reviewed layouts and the explicit workload-ID API. The current
    # production call shares credential construction with other initial roles;
    # the negative control must replace only this workload selection, never the
    # common helper, the probe, or the guest verdict.
    require(sum(source.count(before) for before, _ in SELECTIONS) == 1
            and not any(after in source for _, after in SELECTIONS),
            "credential selection is absent or ambiguous")
    before, after = next((before, after) for before, after in SELECTIONS if before in source)
    return source.replace(before, after)


def verify_delta(before, after, original, changed):
    require(before["files"].keys() == after["files"].keys(), "negative control changed the tracked path set")
    paths = [path for path in before["files"] if before["files"][path] != after["files"][path]]
    require(paths == [SOURCE], "negative control changed a probe, gate, dependency or unrelated source")
    require(changed == mutation(original), "negative control is not the sole root-credential substitution")
    for snapshot, data in ((before, original), (after, changed)):
        row = snapshot["files"][SOURCE]
        require(row["mode"] == "100644" and row["size"] == len(data) and row["sha256"] == digest(data),
                "credential source postimage differs from its full snapshot")


def logged(argv, out, name, *, cwd, env=None, timeout=60, expected_exit=0):
    save(out / (name + "-command.json"), argv)
    with (out / (name + ".stdout.log")).open("xb") as stdout, (out / (name + ".stderr.log")).open("xb") as stderr:
        result = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stdout,
                                stderr=stderr, timeout=timeout, check=False)
    (out / (name + ".exit-code.txt")).write_text(str(result.returncode) + "\n")
    require(result.returncode == expected_exit, name + " returned an unexpected exit; raw logs retained")


def evidence(directory, head, tree, source_files, *, negative=False):
    report_raw = read(directory / "result.json")
    report = json.loads(report_raw)
    require(report["schema"] == "a06.g1d-trusted-initial-control.v1" and report["stage"] == "complete"
            and "error" not in report and report["passed"] is (not negative)
            and report["source_inputs_unchanged"] is True and report["same_kernel_for_all_controls"] is True
            and (report["source_head"], report["source_tree"]) == (head, tree), "incomplete G1-d source/build result")
    snapshots = [json.loads(read(directory / name)) for name in
                 ("source-before.json", "source-after-build.json", "source-after-guests.json")]
    require(snapshots[0] == snapshots[1] == snapshots[2] and snapshots[0]["files"] == source_files
            and (snapshots[0]["head"], snapshots[0]["tree"]) == (head, tree), "G1-d source evidence differs")
    kernel = guest.replay.read_pinned_file(directory / "product-kernel.elf", report["kernel_elf_sha256"],
                                           guest.ordinary.MAX_KERNEL_BYTES)
    probe = guest.replay.read_pinned_file(directory / "g1d-init", report["probe_sha256"])
    info = guest.inspect_probe_elf(probe)
    require(json.loads(read(directory / "probe.json")) == info, "actual static ELF metadata differs")
    require(read(directory / "kernel-build/trusted-initial.elf") == probe, "compiled and embedded probe differ")
    require(set(report["guests"]) == {"exact", "byte-mismatch", "truncated"}, "missing or extra guest profiles")
    negative_verdict = None
    for name, reason in (("exact", None), ("byte-mismatch", "manifest-byte-mismatch"), ("truncated", "truncated-snapshot")):
        recorded = report["guests"][name]
        require(json.loads(read(directory / name / "result.json")) == recorded, "guest receipt differs")
        qemu = json.loads(read(directory / name / "qemu.json"))
        require(all(recorded[key] == value for key, value in qemu.items())
                and qemu["kernel_sha256"] == report["kernel_elf_sha256"]
                and qemu["bios_sha256"] == report["bios_sha256"]
                and qemu["qemu_sha256"] == report["qemu_sha256"], "guest execution inputs differ")
        raw = guest.replay.read_pinned_file(directory / name / "serial.log", recorded["raw_serial_sha256"],
                                           guest.replay.MAX_SERIAL_BYTES)
        verdict = (guest.evaluate_positive(raw, qemu["qemu_exit"], qemu["timed_out"], info) if reason is None
                   else guest.evaluate_rejection(raw, qemu["qemu_exit"], qemu["timed_out"], reason))
        require(all(recorded[key] == value for key, value in verdict.items()), "stored verdict differs from raw evidence")
        expected = not (negative and name == "exact")
        require(verdict["passed"] is expected, "unexpected positive or image-rejection verdict")
        if negative and name == "exact":
            negative_verdict = guest.evaluate_root_workload(raw, qemu["qemu_exit"], qemu["timed_out"], info)
            require(negative_verdict["passed"] is True, "root mutation did not produce the exact unsafe observations")
    return report, kernel, probe, digest(report_raw), negative_verdict


def run(args, out, report):
    before = guest.ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(out / "positive-source-before.json", before)
    positive, kernel, probe, receipt, _ = evidence(args.positive_guest, args.expected_source_head,
                                                  args.expected_source_tree, before["files"])
    original = read(ROOT / SOURCE)
    changed = mutation(original)
    (out / "trusted-roles-before.rs").write_bytes(original)
    (out / "trusted-roles-after.rs").write_bytes(changed)
    source = args.source_worktree.absolute()
    require(not source.exists() and not source.is_symlink() and not source.resolve().is_relative_to(ROOT.resolve())
            and not source.resolve().is_relative_to(out.resolve()), "negative source must be a fresh sibling worktree")
    logged(["git", "worktree", "add", "--detach", str(source), args.expected_source_head], out,
           "worktree-create", cwd=ROOT)
    try:
        staged = guest.ordinary.source_snapshot(source, args.expected_source_head, args.expected_source_tree)
        require(staged["files"] == before["files"], "new worktree differs from reviewed source")
        (source / SOURCE).write_bytes(changed)
        require(subprocess.check_output(["git", "diff", "--name-only"], cwd=source).decode().splitlines() == [SOURCE],
                "negative mutation touched an unrelated path")
        (out / "mutation.patch").write_bytes(subprocess.check_output(["git", "diff", "--", SOURCE], cwd=source))
        subprocess.run(["git", "add", "--", SOURCE], cwd=source, check=True)
        tree = subprocess.check_output(["git", "write-tree"], cwd=source).decode().strip()
        head = subprocess.check_output(["git", "-c", "user.name=G1-d qualification", "-c",
                                       "user.email=g1d-qualification@invalid.example", "commit-tree", tree,
                                       "-p", args.expected_source_head], cwd=source,
                                      input=b"Local cloud negative control: restore only root workload credentials\n").decode().strip()
        subprocess.run(["git", "update-ref", "HEAD", head, args.expected_source_head], cwd=source, check=True)
        after = guest.ordinary.source_snapshot(source, head, tree)
        verify_delta(staged, after, original, changed)
        save(out / "negative-source-before.json", after)
        report.update(positive_source_head=args.expected_source_head, positive_source_tree=args.expected_source_tree,
                      positive_guest_receipt_sha256=receipt, positive_kernel_sha256=digest(kernel),
                      negative_source_head=head, negative_source_tree=tree, negative_parent=args.expected_source_head,
                      mutation_path=SOURCE, mutation_patch_sha256=digest(read(out / "mutation.patch")))
        env = dict(os.environ)
        env["VDSO_LIBRARY_DIR"] = str(ROOT / "support/build/out/linux-vdso")
        negative_dir = out / "negative-guest"
        logged([sys.executable, "-I", "-B", str(source / "tests/kernel/control/run_g1d_guest.py"),
                "--expected-source-head", head, "--expected-source-tree", tree,
                "--target-dir", str(args.target_dir.absolute()), "--output", str(negative_dir),
                "--bios", str(args.bios.absolute()), "--qemu", args.qemu, "--cc", args.cc,
                "--timeout", str(args.timeout)], out, "negative-build-and-boot", cwd=source, env=env,
               timeout=3600, expected_exit=1)
        negative, bad_kernel, bad_probe, negative_receipt, verdict = evidence(negative_dir, head, tree,
                                                                            after["files"], negative=True)
        require(bad_probe == probe and bad_kernel != kernel, "probe changed or mutated kernel stayed identical")
        for key in ("original_initramfs_sha256", "bios_sha256", "qemu_sha256", "generated_lock_sha256"):
            require(negative[key] == positive[key], "positive/negative execution input differs: " + key)
        finished = guest.ordinary.source_snapshot(source, head, tree)
        require(finished == after, "negative build or guests changed tracked source")
        save(out / "negative-source-after.json", finished)
        report.update(negative_kernel_sha256=digest(bad_kernel), unchanged_probe_sha256=digest(probe),
                      negative_guest_receipt_sha256=negative_receipt, raw_negative_verdict=verdict,
                      negative_source_inputs_unchanged=True)
    finally:
        # No --force: keep unexpected source changes for diagnosis.
        logged(["git", "worktree", "remove", str(source)], out, "worktree-remove", cwd=ROOT)
        report["owned_worktree_removed"] = True
    final = guest.ordinary.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(out / "positive-source-after.json", final)
    require(final == before, "negative run changed the original positive checkout")
    report.update(passed=True, positive_source_inputs_unchanged=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("positive-guest", "source-worktree", "target-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-source-head", "expected-source-tree"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink() and not out.resolve().is_relative_to(ROOT.resolve()),
            "output must be new and outside source")
    require(1 <= args.timeout <= 120, "guest timeout must be 1..120 seconds")
    out.mkdir(parents=True, mode=0o700)
    report = {"schema": "a06.g1d-root-workload-negative.v1", "passed": False,
              "runner_sha256": digest(Path(__file__).read_bytes())}
    try:
        run(args, out, report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report.update(passed=False, error=f"{type(error).__name__}: {error}")
    save(out / "result.json", report)
    print(json.dumps({"passed": report["passed"], "output": str(out)}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
