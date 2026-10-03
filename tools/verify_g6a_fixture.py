#!/usr/bin/env python3
"""Check the independent G6a source profile and optional actual QEMU packet.

This verifier creates no installed facts. A source check is not a QEMU pass;
only an exact complete packet with carried serial and receipts can be reported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = ("source", "pending", "target_failure", "bad_signature", "unsigned_target", "target_data_corrupt", "target_hash_corrupt", "source_data_corrupt", "state_corrupt", "publication_orphan", "disk_full", "cut_temporary_created", "cut_temporary_written", "cut_file_synced", "cut_name_replaced", "cut_directory_synced", "cut_readback_confirmed")
FALSE_FIELDS = ("production_activation_enabled", "firmware_authenticated", "desktop_installed_qualified", "measured_health_qualified", "protected_rollback_anchor", "physical_power_cut_qualified")
CONTRACT_FALSE_FIELDS = (*FALSE_FIELDS, "commit_performed", "reproducible_build_qualified")


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    require(path.is_file() and not path.is_symlink(), "regular carried file required")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 4 * 1024**2, "bounded JSON required")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON member")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON refused")
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)


def command_profile(argv, name, number):
    require(type(argv) is list and all(type(item) is str for item in argv) and len(argv) == 35, "closed actual QEMU argv required")
    require(argv[:17] == ["qemu-system-x86_64", "-machine", "q35,accel=tcg", "-cpu", "max", "-m", "1024", "-smp", "2", "-nodefaults", "-no-reboot", "-display", "none", "-monitor", "none", "-nic", "none"], "fixed QEMU execution profile differs")
    require(argv[17] == "-kernel" and argv[19] == "-initrd" and argv[21:23] == ["-append", "console=ttyS0,115200 rdinit=/init panic=-1"] and argv[23] == "-serial", "fixed guest boot entry differs")
    kernel, initrd = Path(argv[18]), Path(argv[20])
    require(kernel.name == "vmlinuz" and initrd.name == "initrd.img" and kernel.parent == initrd.parent, "fixed kernel/initramfs tuple differs")
    require(argv[24].startswith("file:") and Path(argv[24][5:]).name == f"serial-{number}.log" and Path(argv[24][5:]).parent.name == name, "actual serial lineage differs")
    for index, expected in enumerate(("state.ext4", "root-A.ext4", "root-A.verity", "root-B.ext4", "root-B.verity")):
        require(argv[25 + index * 2] == "-drive", "fixed device ordering differs")
        parts = argv[26 + index * 2].split(",")
        require(len(parts) == 5 and all("=" in item for item in parts), "closed drive parameters required")
        pairs = [item.split("=", 1) for item in parts]
        drive = dict(pairs)
        require(len(drive) == 5 and set(drive) == {"file", "format", "if", "cache", "readonly"}, "closed drive fields required")
        require(drive["format"] == "raw" and drive["if"] == "virtio" and drive["cache"] == "none" and drive["readonly"] == ("off" if index == 0 else "on"), "actual device integrity profile differs")
        path = Path(drive["file"])
        require(path.name == expected, "fixed slot device ordering differs")
        mutated = {"source_data_corrupt": 1, "target_data_corrupt": 3, "target_hash_corrupt": 4}.get(name)
        require(path.parent.name == name if index == 0 or index == mutated else path.parent == kernel.parent, "actual device path lineage differs")
    return str(kernel), str(initrd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--qemu-result-dir", type=Path)
    args = parser.parse_args()
    root = args.root
    contract = read(root / "contracts/g6a-immutable-ab.v1.json")
    require(contract["schema"] == "trillionnium.desktop.g6a-immutable-ab-contract.v1" and contract["fixture_only"] is True, "fixture contract differs")
    require(tuple(contract["fault_cases"]) == CASES, "closed fault inventory differs")
    require(contract["boot_entry"] == "fixed_direct_kernel_initramfs_owned_by_test_harness" and contract["slot_selection"] == "guest_only_fixed_device_mapping", "boot authority differs")
    require(set(contract["authority"]) == set(CONTRACT_FALSE_FIELDS) and all(contract["authority"][field] is False for field in CONTRACT_FALSE_FIELDS), "authority ceiling differs")
    require(contract["immutable_root"]["optional_verity_options"] == [] and contract["immutable_root"]["complete_kernel_mapping_read_before_switch_root"] is True, "immutable mapping proof differs")
    require(contract["publication_boundaries"] == ["temporary_created", "temporary_written", "file_synced", "name_replaced", "directory_synced", "readback_confirmed"], "closed publication boundaries differ")
    require(contract["interruption_recovery"] == {"post_kill_host_state_writes": False, "before_directory_fsync": "exact_valid_old_or_new_attempt_state_or_explicit_refusal", "after_directory_fsync": "exact_consumed_attempt_state", "orphan_repair": False}, "interruption semantics differ")
    selection = read(root / "manifests/debian-g6a.selection.v1.json")
    require(selection["schema"] == "trillionnium.desktop.debian-g6a-selection.v1" and selection["fixture_only"] is True and selection["production_activation_enabled"] is False, "selection ceiling differs")
    lock_path = root / "manifests/debian-g6a.lock.v1.json"
    require(digest(lock_path) == selection["package_lock_sha256"], "exact lock digest differs")
    lock = read(lock_path)
    require(lock["status"] == "PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY", "signed closure required")
    require(lock["package_set_sha256"] == selection["package_set_sha256"] and lock["resolved_package_count"] == selection["package_count"] == len(lock["packages"]), "closure binding differs")
    encoded = json.dumps(lock["packages"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    require(hashlib.sha256(encoded).hexdigest() == selection["package_set_sha256"], "closure bytes differ")
    requirements = read(root / "manifests/debian-g6a.requirements.v1.json")
    roots = {item["id"]: item["primary_fingerprint"] for item in requirements["trust_roots"]}
    require(roots == {"debian-13-archive": "04B54C3CDCA79751B16BC6B5225629DF75B188BD", "debian-13-security": "5E04A1E3223A19A20706E20F9904613D4CCE68C6", "debian-13-release": "41587F7DB8C774BCCF131416762F67A0B2C39DE4"}, "independent Debian primary roots differ")
    require({item["id"]: item["primary_fingerprint"] for item in lock["archive_keyring"]["trust_roots"]} == roots, "carried signed roots differ")
    require(lock["seed_packages"] == sorted(requirements["seed_packages"]) and lock["architecture"] == "amd64" and lock["snapshot_timestamp"] == "20260828T000000Z", "fixed package requirements differ")
    for entry in lock["inrelease"]:
        require(entry["valid_primary_fingerprints"] and set(entry["valid_primary_fingerprints"]) & set(entry["accepted_primary_fingerprints"]), "accepted InRelease signer missing")
    facts = {"source_profile_valid": True, "carried_complete_packet_consistent": False, "runtime_execution_independently_qualified": False, "production_activation_enabled": False}
    if args.qemu_result_dir:
        packet = args.qemu_result_dir
        result = read(packet / "result.json")
        require(result["schema"] == "trillionnium.desktop.g6a-qemu-result.v1" and result["status"] == "PASS" and result["complete_matrix_executed"] is True and result["fixture_only"] is True and result["qemu_network_enabled"] is False, "complete actual fixture packet required")
        require(set(result["cases"]) == set(CASES) and all(result.get(field) is False for field in FALSE_FIELDS), "packet coverage or authority differs")
        require(digest(packet / "build-result.json") == result["source_build_result_sha256"], "carried build binding differs")
        build = read(packet / "build-result.json")
        require(build["package_lock_sha256"] == selection["package_lock_sha256"] and build["package_set_sha256"] == selection["package_set_sha256"] and build["fixture_only"] is True, "build profile lineage differs")
        require(all(build.get(field) is False for field in ("production_activation_enabled", "firmware_authenticated", "desktop_installed_qualified", "measured_health_qualified", "protected_rollback_anchor", "reproducible_build_qualified")), "build authority ceiling differs")
        require(result["harness_source_sha256"] == digest(root / "tests/qemu/run_g6a_qualification.py"), "tested harness source differs")
        for path, sha256 in build["source_inputs"].items():
            require(path in {"tools/build_g6a_fixture.py", "packaging/debian/g6a/init", "packaging/debian/g6a/guest_selector.py", "packaging/debian/g6a/root_probe.py", "packaging/debian/g6a/fixture-init"}, "unexpected builder source input")
            require(digest(root / path) == sha256, "tested builder/guest source differs")
        require(len(build["source_inputs"]) == 5, "complete guest and recipe source binding required")
        fixed_boot_tuple = None
        for name, case in result["cases"].items():
            require(case["status"] == "PASS" and case["source_build_result_sha256"] == result["source_build_result_sha256"], "case lineage differs")
            expected_count = 3 if name in {"pending", "target_failure"} else 2 if name.startswith("cut_") else 1
            require(len(case["boots"]) == expected_count, "actual case boot count differs")
            directory = packet / name
            require(digest(directory / "state.ext4") == case["state_sha256"], "actual final state image differs")
            for number, boot in enumerate(case["boots"], 1):
                serial = directory / f"serial-{number}.log"
                require(digest(serial) == boot["serial_sha256"] and digest(directory / f"command-{number}.json") == boot["command_sha256"], "actual serial/command bytes differ")
                actual_tuple = command_profile(read(directory / f"command-{number}.json"), name, number)
                if fixed_boot_tuple is None:
                    fixed_boot_tuple = actual_tuple
                require(actual_tuple == fixed_boot_tuple, "kernel/initramfs changed across case boots")
                lines = serial.read_text(errors="replace").splitlines()
                observations = [json.loads(line.partition(" ")[2]) for line in lines if line.startswith("G6A_ROOT_OBSERVED ")]
                refusals = [json.loads(line.partition(" ")[2]) for line in lines if line.startswith("G6A_SELECTOR_REFUSED ")]
                require(observations == boot["observed"] and refusals == boot["refused"], "carried observations differ")
                if name.startswith("cut_") and number == 1:
                    require(boot["actual_vm_interrupted"] is True and boot["returncode"] == -9 and not observations and not refusals, "actual abrupt VM interruption differs")
                    cutpoints = [json.loads(line.partition(" ")[2])["name"] for line in lines if line.startswith("G6A_CUTPOINT ")]
                    require(name.removeprefix("cut_") in cutpoints, "actual interruption boundary absent")
                    continue
                require(boot["actual_vm_interrupted"] is False and len(observations) + len(refusals) == 1, "unique actual terminal outcome required")
                uncertain = name in {"cut_temporary_created", "cut_temporary_written", "cut_file_synced", "cut_name_replaced"}
                refuse = name in {"source_data_corrupt", "state_corrupt", "publication_orphan", "disk_full"}
                require(uncertain or bool(refusals) == refuse, "actual refusal outcome differs")
                if observations:
                    observation = observations[0]
                    expected_slot = "B" if (name in {"pending", "target_failure"} and number < 3) or name.startswith("cut_") else "A"
                    require(observation["slot"] == expected_slot and observation["descriptor"] == build["descriptors"][expected_slot], "actual root descriptor/selection differs")
                    require(all(observation[field] is True for field in ("actual_root_mount_readonly", "actual_mapping_readonly", "root_write_refused")), "actual readonly observation absent")
                    require(all(observation[field] is False for field in ("production_activation_enabled", "measured_health_qualified", "commit_performed", "firmware_authenticated", "rollback_anchor_protected")), "observation authority differs")
                    if name.startswith("cut_"):
                        allowed = {1, 2} if uncertain else {2}
                        require(type(observation["attempts"]) is int and observation["attempts"] in allowed and observation["boot_number"] == observation["attempts"], "interrupted attempt preservation differs")
            ids = [boot["observed"][0]["boot_id"] for boot in case["boots"] if boot["observed"]]
            require(len(ids) == len(set(ids)), "different boots require different kernel identities")
        facts["carried_complete_packet_consistent"] = True
    print(json.dumps(facts, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("G6a verification refused: " + str(error), file=sys.stderr)
        raise SystemExit(1)
