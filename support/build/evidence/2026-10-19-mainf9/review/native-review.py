#!/usr/bin/env python3
"""Read completed A01 native receipts without building, booting, or editing them."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
PRODUCER = "7758ffe294bb0e1eab46e20cba60e8af9d8bcd61"
MAIN = "f9e306f76154590e096a42f70ce9de0a7c859e60"
PREVIOUS_A01 = "71524be19383e2ff98f6abc90668c48988e7c8e2"
PIN_COMMIT = "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
PIN_TREE = "96605cf64aeae2d34f29b97e85eff9315fe10a8e"
TOOLCHAIN = "nightly-2026-07-21"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
CPU_PREFIX = "aster_core::fs::fs_impls::cgroupfs::controller::cpu::"
CPU_TESTS = [
    "max_config::tests::single_quota_preserves_the_current_period",
    "max_config::tests::accepts_valid_quota_period_and_range_boundaries",
    "max_config::tests::rejects_invalid_or_overflowing_quota",
    "max_config::tests::rejects_numeric_period_outside_the_supported_range",
    "max_config::tests::rejects_explicit_invalid_period_instead_of_preserving_the_old_period",
    "max_config::tests::rejects_overflowing_period_instead_of_preserving_the_old_period",
    "max_config::tests::rejects_extra_fields_instead_of_applying_a_valid_prefix",
    "config_regressions::invalid_cpu_max_write_does_not_change_budget_or_accounting",
    "config_regressions::single_quota_write_keeps_the_current_owner_period",
]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complete", action="store_true", required=True,
                        help="parent confirmed that all native execution stages have finished")
    parser.add_argument("--repo", type=Path, default=Path("/workspace/scratch/d7da9e7650f0/a01-mainf9"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--boot-stage", default="boot-retry", help="successful retry stage and output directory")
    parser.add_argument("--manifest-custody", type=Path, help="root's completed stable-FD quarantine receipt")
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.out or repo / "support/build/out/2026-10-19-mainf9"
    report = {"kind": "independent_read_only_native_evidence_review", "started_at_utc": now(),
              "execution_head": PRODUCER, "evidence_root": str(out),
              "new_builds_tests_or_qemu_executed_by_reviewer": False,
              "live_checkout_writes_by_reviewer": False, "checks": [], "observations": {},
              "limits": [
                  "The main boot recorder loads exclusive private snapshots and checks them before and after QEMU.",
                  "The ktest recorder loads live target paths after a stable-FD prelaunch hash; post-run frozen copies are compared to those hashes, not presented as prelaunch snapshots.",
                  "Source captures check selected tracked inputs. Raw full worktree status is retained separately; they are not continuous tracing of all writers.",
                  "No cause is assigned to earlier unexplained target or manifest reappearance.",
              ]}

    def check(name, condition, observed=None):
        item = {"name": name, "passed": bool(condition)}
        if observed is not None:
            item["observed"] = observed
        report["checks"].append(item)

    def git(*parts):
        return subprocess.check_output(["git", "-C", str(repo), *parts],
                                       env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})

    def profile(qemu):
        argv = qemu["argv"][1:]
        expected = {"-machine": "q35", "-accel": "tcg", "-cpu": "max", "-m": "512M",
                    "-smp": "1", "-display": "none", "-monitor": "none", "-serial": "chardev:serial",
                    "-device": "isa-debug-exit,iobase=0xf4,iosize=0x04"}
        observed = {}
        for key in expected:
            positions = [i for i, value in enumerate(argv) if value == key]
            observed[key] = argv[positions[0] + 1] if len(positions) == 1 and positions[0] + 1 < len(argv) else None
        required = ("-nodefaults", "-no-user-config", "-no-reboot", "-nographic")
        forbidden = ("-net", "-nic", "-netdev", "-drive", "-blockdev", "-cdrom", "-hda", "-hdb", "-hdc", "-hdd", "-fda", "-fdb", "-pflash", "-enable-kvm", "-gdb", "-S", "-readconfig")
        known_values = set(expected) | {"-kernel", "-initrd", "-append", "-bios", "-L", "-chardev"}
        unknown = []
        index = 0
        while index < len(argv):
            key = argv[index]
            if key in required:
                index += 1
            elif key in known_values and index + 1 < len(argv):
                index += 2
            else:
                unknown.append(key)
                index += 1
        unique_inputs = all(argv.count(key) == 1 for key in ("-kernel", "-append", "-bios", "-chardev"))
        device_ok = all(observed[key] == value for key, value in expected.items())
        no_extra_devices = argv.count("-device") == 1
        return {"observed": observed,
                "matches": device_ok and no_extra_devices and unique_inputs and not unknown and all(argv.count(k) == 1 for k in required)
                           and not any(k in argv for k in forbidden),
                "unknown_options": unknown,
                "no_extra_devices_or_network_disks": no_extra_devices and not any(k in argv for k in forbidden)}

    def artifact(artifact_record, path=None):
        p = path or Path(artifact_record["path"])
        raw = p.read_bytes()
        return len(raw) == artifact_record["size"] and digest(raw) == artifact_record["sha256"]

    def source_selected(path):
        return path in ("README.md", "support/upstream-lock.json") or path.startswith(("kernel/asterinas/", "libs/os-abi/src/")) or path.startswith("support/build/") and not path.startswith(("support/build/evidence/", "support/build/out/", "support/build/handoffs/"))

    try:
        project_tree = git("rev-parse", PRODUCER + "^{tree}").decode().strip()
        kernel_tree = git("rev-parse", PRODUCER + ":kernel/asterinas").decode().strip()
        parents = git("show", "-s", "--format=%P", PRODUCER).decode().strip().split()
        report.update(project_tree=project_tree, kernel_tree=kernel_tree)
        check("producer_contains_actual_main_then_previous_A01", parents == [MAIN, PREVIOUS_A01], parents)
        check("fixed_upstream_git_tree", git("rev-parse", PIN_COMMIT + "^{tree}").decode().strip() == PIN_TREE)

        boot_stage = args.boot_stage
        stages = {stage: read(out / "executions" / (stage + ".json")) for stage in ("kernel", boot_stage, "ktest")}
        check("all_stage_execution_receipts_completed_at_producer",
              all(r.get("producer") == PRODUCER and r.get("project_tree") == project_tree
                  and r.get("kernel_tree") == kernel_tree and r.get("exit_code") == 0
                  and r.get("finished_at") and r.get("source_after") for r in stages.values()))
        report["observations"]["stage_timing_and_status"] = {
            key: {k: value.get(k) for k in ("started_at", "finished_at", "elapsed_seconds", "exit_code",
                                           "git_status_before", "git_status_after", "public_manifest_before", "public_manifest_after")}
            for key, value in stages.items()}

        capture_names = [stage + suffix for stage in ("kernel", "boot", boot_stage, "ktest") for suffix in ("-before", "-after")]
        captures = {name: read(out / "source" / (name + ".json")) for name in capture_names}
        baseline = captures["kernel-before"]
        identities = ("head", "project_tree", "kernel_tree", "upstream_commit", "upstream_tree", "script_sha256", "selection", "files_sha256", "file_count")
        check("all_source_captures_same_selected_identity",
              all(c.get("matches_git") is True and not c.get("failures") and
                  all(c.get(k) == baseline.get(k) for k in identities) for c in captures.values())
              and baseline["head"] == PRODUCER and baseline["project_tree"] == project_tree and baseline["kernel_tree"] == kernel_tree
              and baseline["upstream_commit"] == PIN_COMMIT and baseline["upstream_tree"] == PIN_TREE)
        tree_entries = {}
        for entry in git("ls-tree", "-rz", PRODUCER).split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            mode, kind, blob = metadata.decode().split()
            path = os.fsdecode(raw_name)
            if source_selected(path):
                tree_entries[path] = (mode, kind, blob)
        files = baseline["files"]
        file_map = {item["path"]: item for item in files}
        check("selected_captured_git_blobs_are_complete_for_producer",
              set(tree_entries) == set(file_map) and len(files) == len(tree_entries)
              and all(tree_entries[e["path"]] == (e["git_mode"], e["git_kind"], e["git_blob"])
                      and e["git_blob"] == e["worktree_git_blob"] for e in files))
        check("source_capture_payload_hashes_recalculate",
              all(digest(json.dumps(c["files"], sort_keys=True, separators=(",", ":")).encode()) == c["files_sha256"]
                  for c in captures.values()))
        lock_paths = sorted(path for path in file_map if path.endswith("Cargo.lock") or path == "support/upstream-lock.json")
        check("all_captured_locks_unchanged_after_native_execution",
              all(sha(repo / path) == file_map[path]["sha256"] for path in lock_paths),
              {path: file_map[path]["sha256"] for path in lock_paths})
        check("project_root_README_stays_zero_bytes", (repo / "README.md").stat().st_size == file_map["README.md"]["size"] == 0)
        report["observations"]["selected_input_count"] = len(files)
        report["observations"]["source_statuses"] = {name: c["git_status_porcelain"] for name, c in captures.items()}
        report["observations"]["current_read_only_git_status"] = git("status", "--porcelain=v1", "--untracked-files=all").decode()
        late_path = out / "source/after-quarantine.json"
        if late_path.exists():
            late = read(late_path)
            report["observations"]["after_quarantine_source_capture"] = {
                key: late.get(key) for key in ("captured_at_utc", "head", "matches_git", "files_sha256", "file_count", "git_status_porcelain", "failures")}
            check("late_capture_selected_tracked_inputs_still_match_without_clean_status_claim",
                  late.get("matches_git") is True and all(late.get(k) == baseline.get(k) for k in identities))
        manifest = repo / "kernel/asterinas/kernel/OSDK.toml"
        if manifest.exists() or manifest.is_symlink():
            state = manifest.lstat()
            report["observations"]["public_manifest_at_review"] = {
                "path": str(manifest), "exists": True, "device": state.st_dev, "inode": state.st_ino,
                "mode": state.st_mode, "size": state.st_size, "mtime_ns": state.st_mtime_ns,
                "ctime_ns": state.st_ctime_ns, "sha256": sha(manifest) if stat.S_ISREG(state.st_mode) else None,
                "observed_at": now(), "writer_identified": False}
        else:
            report["observations"]["public_manifest_at_review"] = {"path": str(manifest), "exists": False, "observed_at": now()}
        second_custody = out / "failures/post-boot-manifest/quarantine.json"
        if second_custody.exists():
            report["observations"]["second_manifest_custody_receipt"] = {
                "path": str(second_custody), "sha256": sha(second_custody), "record": read(second_custody),
                "interpretation": "source_absent_after is the recorded rename instant, not a claim that the public path remains absent"}

        source_verifiers = [read(out / stage / "source-inputs.json") for stage in ("kernel", boot_stage, "ktest")]
        check("all_upstream_source_verifier_receipts_pass_same_pin",
              all(r.get("passed") is True and not r.get("errors") and r.get("commit") == PIN_COMMIT
                  and r.get("tree") == PIN_TREE and r.get("toolchain") == TOOLCHAIN for r in source_verifiers)
              and source_verifiers[0] == source_verifiers[1] == source_verifiers[2])

        compile_count = 0
        for stage, target in (("kernel", "kernel"), (boot_stage, "run_kernel")):
            folder = out / stage
            exits = {name: int((folder / name).read_text()) for name in
                     ("make-exit-code.txt", "log-exit-code.txt", "run-exit-code.txt", "manifest-cleanup-exit-code.txt")}
            check(stage + "_all_build_and_cleanup_exit_codes_zero", all(value == 0 for value in exits.values()), exits)
            cleanup = read(folder / "manifest-cleanup.json")
            check(stage + "_cleanup_removed_only_owned_manifest",
                  cleanup.get("passed") is True and cleanup.get("outcome") == "owned_removed"
                  and cleanup.get("anchor") == cleanup.get("captured"))
            inner = (folder / (target + ".log")).read_bytes()
            outer = (out / "executions" / (stage + ".stdout-stderr.log")).read_bytes()
            check(stage + "_full_inner_log_is_preserved_in_execution_log", bool(inner) and inner in outer)
            command = shlex.split((folder / "command.sh").read_text())
            check(stage + "_actual_upstream_make_target_and_fixed_overrides",
                  command[:3] == ["make", "-C", str(repo / "kernel/asterinas")]
                  and target in command and all(value in command for value in
                     ("TARGET_ARCH=x86_64", "SMP=1", "MEM=512M", "ENABLE_KVM=0", "BOOT_PROTOCOL=multiboot", "INITRAMFS=on", "AUTO_TEST=none")))
            init = read(folder / "initramfs-manifest.json")
            check(stage + "_small_initramfs_matches_recorded_bytes",
                  (folder / "initramfs.cpio.gz").stat().st_size == init["image_size"] < 2 * 1024 * 1024
                  and sha(folder / "initramfs.cpio.gz") == init["image_sha256"])
            if stage == "kernel":
                compile_count = len(re.findall(rb"^\s*Compiling ", inner, re.MULTILINE))
        check("fresh_build_receipt_had_no_target_and_compiler_ran",
              stages["kernel"]["target_before"].get("exists") is False
              and stages["kernel"]["osdk_target_before"].get("exists") is False and compile_count > 0,
              {"compiling_lines": compile_count, "target_before": stages["kernel"]["target_before"],
               "osdk_target_before": stages["kernel"]["osdk_target_before"]})

        failed = read(out / "executions/boot.json")
        failed_log = (out / "executions/boot.stdout-stderr.log").read_bytes()
        failed_folder = out / "boot"
        check("first_boot_failed_prelaunch_with_raw_receipts_preserved",
              failed.get("exit_code") == 1 and failed.get("producer") == PRODUCER
              and failed.get("public_manifest_before", {}).get("exists") is True
              and b"kernel/OSDK.toml already exists; refusing to replace it" in failed_log
              and not (failed_folder / "qemu.json").exists() and not (failed_folder / "serial.log").exists()
              and not (failed_folder / "command.sh").exists() and not (failed_folder / "make-exit-code.txt").exists(),
              {"first_boot": failed, "raw_log_sha256": digest(failed_log), "raw_log_size": len(failed_log)})
        custody_path = args.manifest_custody or out / "failures/boot-preflight/quarantine.json"
        custody = read(custody_path)
        unexpected = Path(custody["destination"])
        old_entry = failed["public_manifest_before"]
        build_cleanup = read(out / "kernel/manifest-cleanup.json")
        check("unexpected_manifest_is_preserved_with_same_inode_and_bytes",
              custody.get("exclusive_nonblocking_lock") is True and custody.get("writer_identified") is False
              and custody.get("bytes_equal") is True and custody.get("source_absent_after") is True
              and unexpected.stat().st_size == old_entry["size"] == custody["before"]["st_size"]
              and sha(unexpected) == old_entry["sha256"] == custody["sha256"]
              and old_entry["inode"] == custody["before"]["st_ino"] == custody["after"]["st_ino"] == unexpected.stat().st_ino
              and old_entry["device"] == custody["before"]["st_dev"] == custody["after"]["st_dev"]
              and (old_entry["device"], old_entry["inode"]) !=
                  (build_cleanup["anchor"]["device"], build_cleanup["anchor"]["inode"]))
        report["observations"]["root_manifest_custody_receipt"] = {
            "path": str(custody_path), "sha256": sha(custody_path), "record": custody}
        boot = read(out / boot_stage / "qemu.json")
        raw = (out / boot_stage / "serial.log").read_bytes()
        serial = ANSI.sub("", raw.decode(errors="replace")).replace("\r", "")
        check("boot_raw33_complete_without_timeout", boot.get("raw_exit_code") == 33
              and boot.get("recorder_exit_code") == 33 and boot.get("timed_out") is False and boot.get("stage") == "complete")
        check("boot_full_raw_serial_hash_and_size_match", digest(raw) == boot.get("serial_sha256")
              and len(raw) == boot.get("serial_size"), {"size": len(raw), "sha256": digest(raw)})
        markers = ["OSTD initialized. Preparing components.", "TRILLIONNIUM_A01_INIT_BEGIN",
                   "TRILLIONNIUM_A01_CPU_COUNT=1", "Successfully booted.", "TRILLIONNIUM_A01_BOOT_OK"]
        check("boot_has_one_complete_single_cpu_success_sequence", all(serial.count(marker) == 1 for marker in markers)
              and [serial.index(marker) for marker in markers if marker in serial] == sorted(serial.index(marker) for marker in markers if marker in serial),
              {marker: serial.count(marker) for marker in markers})
        check("boot_has_no_fatal_panic", not any(value in serial for value in
              ("panicked at", "An uncaught panic occurred:", "Uncaught panic:", "Non-resettable panic!", "The panic handler panicked")))
        observed_profile = profile(boot)
        check("boot_actual_qemu_fixed_profile", observed_profile["matches"], observed_profile)
        check("boot_QEMU_executable_bytes_match_record", sha(Path(boot["argv"][0])) == boot["qemu_sha256"])
        snap_root = Path(boot["snapshot_directory"]["path"])
        check("boot_loaded_actual_private_artifacts_match_before_and_after_record",
              all(artifact(a) and a["sha256"] == a["source"]["sha256"] and a["size"] == a["source"]["size"]
                  and Path(a["path"]).parent == snap_root and Path(a["path"]).stat().st_mode & 0o777 == 0o400
                  and boot["argv"][boot["argv"].index(option) + 1] == a["path"]
                  for option, a in boot["artifacts"].items())
              and set(boot["artifacts"]) == {"-kernel", "-initrd", "-bios"})
        first = read(out / "artifacts/first-kernel.json")
        check("freshly_built_frozen_ELF_is_byte_identical_to_actual_booted_ELF",
              first.get("stable_during_capture") is True and first.get("bytes_equal") is True
              and artifact(first["frozen"]) and first["source"]["sha256"] == first["frozen"]["sha256"] == boot["artifacts"]["-kernel"]["sha256"]
              and (out / "artifacts/first-kernel.elf").read_bytes() == Path(boot["artifacts"]["-kernel"]["path"]).read_bytes(),
              {"size": first["frozen"]["size"], "sha256": first["frozen"]["sha256"]})

        result = read(out / "ktest/result.json")
        environment = read(out / "ktest/environment.json")
        check("ktest_unfiltered_current_source_private_OSDK", result.get("passed") is True
              and environment.get("git_head") == PRODUCER and environment.get("test_name") is None
              and environment.get("toolchain") == TOOLCHAIN and environment.get("osdk_install_skipped") is False
              and environment.get("osdk_source_root") == str(repo / "kernel/asterinas")
              and sha(Path(environment["osdk_executable"])) == environment["osdk_sha256"])
        check("recorded_actual_Rust_and_Cargo_are_fixed_builds",
              "87e5904f5eb6398af6b22eac2802c78934260c48" in environment.get("rustc", "")
              and "3efb1f477e99b42974b982d939fd100303cdf7db" in environment.get("cargo", "")
              and all("87e5904f5eb6398af6b22eac2802c78934260c48" in (out / stage / "environment.log").read_text()
                      and "3efb1f477e99b42974b982d939fd100303cdf7db" in (out / stage / "environment.log").read_text()
                      for stage in ("kernel", boot_stage)))
        command_receipts = sorted((out / "ktest").rglob("*.command.json"))
        checks = [read(path) for path in command_receipts]
        check("all_ktest_command_receipts_successful_and_leaders_reaped", len(checks) >= 10
              and all(c.get("exit_code") == 0 and c.get("raw_exit_code") == 0
                      and c.get("group_cleanup", {}).get("leader_reaped") is True for c in checks),
              {"count": len(checks)})
        counts = {}
        observed_cpu = []
        for crate in ("ostd", "aster-core"):
            folder = out / "ktest" / crate
            guests = sorted((folder / "guests").glob("guest-*"))
            check(crate + "_one_recorded_guest", len(guests) == 1)
            guest = guests[0]
            qemu = read(guest / "qemu.json")
            raw = (guest / "serial.log").read_bytes()
            serial = ANSI.sub("", raw.decode(errors="replace")).replace("\r", "")
            check(crate + "_full_raw_serial_and_successful_guest_exit", digest(raw) == qemu.get("serial_sha256")
                  and qemu.get("raw_exit_code") == qemu.get("recorder_exit_code") == 33
                  and qemu.get("timed_out") is False and qemu.get("stage") == "complete" and qemu.get("crate") == crate)
            check(crate + "_no_failed_crate_or_fatal_test_panic",
                  not re.search(r"test result: FAILED\.|test result: ok\. \d+ passed; [1-9]\d* failed;", serial)
                  and not any(value in serial for value in ("An uncaught panic occurred:", "Uncaught panic:",
                      "Non-resettable panic!", "The panic handler panicked", "Panicked in `PanicGuard`, aborting the system")))
            qp = profile(qemu)
            check(crate + "_actual_qemu_fixed_profile", qp["matches"], qp)
            check(crate + "_QEMU_and_firmware_match_boot_inputs",
                  qemu["qemu_sha256"] == boot["qemu_sha256"] == sha(Path(qemu["argv"][0]))
                  and qemu["artifacts"]["-bios"]["sha256"] == boot["artifacts"]["-bios"]["sha256"]
                  and artifact(qemu["artifacts"]["-bios"]))
            frozen = read(out / "artifacts" / (crate + ".json"))
            check(crate + "_postrun_frozen_ELF_matches_prelaunch_live_path_hash",
                  frozen.get("stable_during_capture") is True and frozen.get("bytes_equal") is True
                  and artifact(frozen["frozen"]) and qemu["artifacts"]["-kernel"]["sha256"] == frozen["source"]["sha256"] == frozen["frozen"]["sha256"]
                  and qemu["argv"][qemu["argv"].index("-kernel") + 1] == qemu["artifacts"]["-kernel"]["path"])
            check(crate + "_generated_lock_equals_fixed_source_lock",
                  sha(folder / "generated.Cargo.lock") == sha(repo / "support/build/ktest/locks" / (crate + ".Cargo.lock")))
            headers = list(re.finditer(r'^running (\d+) tests in crate "([^"]+)"$', serial, re.MULTILINE))
            target = [h for h in headers if h[2] == crate]
            if len(target) != 1:
                raise ValueError(crate + ": no unique target header")
            head = target[0]
            tail = next((h.start() for h in headers if h.start() > head.start()), len(serial))
            section = serial[head.end():tail]
            summaries = re.findall(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) filtered out\.", section)
            starts = list(re.finditer(r"^test ([\w:]+) \.\.\.", section, re.MULTILINE))
            skips = re.findall(r"\[skipped: ([^\]]+)\]", section)
            if len(summaries) != 1:
                raise ValueError(crate + ": no unique test summary")
            state, passed, failed, filtered = summaries[0]
            passed, failed, filtered = int(passed), int(failed), int(filtered)
            declared = int(head[1])
            counts[crate] = {"declared": declared, "passed": passed, "failed": failed, "filtered": filtered,
                             "soft_skipped": len(skips), "soft_skip_reasons": skips,
                             "exercised_passed_lower_bound": passed - len(skips), "test_starts": len(starts)}
            check(crate + "_independent_full_crate_serial_count",
                  state == "ok" and failed == filtered == 0 and passed == declared == len(starts)
                  and len({m[1] for m in starts}) == declared and passed > len(skips)
                  and serial.count("[ktest runner] All crates tested.") == 1,
                  counts[crate])
            machine = read(folder / "result.json")["guests"][0]
            check(crate + "_machine_result_matches_independent_count",
                  all(machine[k] == value for k, value in counts[crate].items() if k != "test_starts")
                  and machine["observed_test_starts"] == len(starts))
            if crate == "aster-core":
                for expected in CPU_TESTS:
                    matches = [i for i, item in enumerate(starts) if item[1] == CPU_PREFIX + expected]
                    segment = ""
                    if len(matches) == 1:
                        i = matches[0]
                        segment = section[starts[i].end():starts[i + 1].start() if i + 1 < len(starts) else section.index("test result:")]
                    observed_cpu.append({"test": CPU_PREFIX + expected, "occurrences": len(matches),
                                         "completed_ok": bool(re.fullmatch(r"\s*ok\s*", segment)), "completion_text": segment.strip()})
        check("all_nine_new_main_CPU_config_tests_executed_and_completed_ok",
              all(t["occurrences"] == 1 and t["completed_ok"] for t in observed_cpu), observed_cpu)
        report["observations"]["ktest_counts"] = counts
        report["observations"]["total_reported_passed"] = sum(c["passed"] for c in counts.values())
        report["observations"]["total_exercised_lower_bound"] = sum(c["exercised_passed_lower_bound"] for c in counts.values())
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as error:
        check("review_completed_without_missing_or_invalid_inputs", False, f"{type(error).__name__}: {error}")

    report["finished_at_utc"] = now()
    report["review_script_sha256"] = sha(Path(__file__))
    report["passed_checks"] = sum(item["passed"] for item in report["checks"])
    report["failed_checks"] = len(report["checks"]) - report["passed_checks"]
    report["all_checked_native_evidence_consistent"] = report["failed_checks"] == 0
    print(json.dumps(report, indent=2))
    return 0 if report["all_checked_native_evidence_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
