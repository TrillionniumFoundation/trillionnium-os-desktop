#!/usr/bin/env python3
"""Replay preserved AF_UNIX evidence, never build or execute a kernel/payload.

The archived original oracle/parser functions are imported without changing their
assertions. This script verifies a specific preserved experiment, not a new native
execution. Only isolated patch-replay copies and a fresh review file are writable.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
HEAD = "b824d80d44456c131a6cb9d4fcc84be95c6af273"
TREE = "506d583455fa5ea2cf0c18fe10ed42c3874f7556"
ORACLE_SHA = "eefb0f272d2c396ea6fa87c0af827f795b115ca7607c6746abf80975fe544489"
PROTOCOL_SHA = "6577cd26c72c80f370cd4a654463316bf7fa5227a33a0e9ff3ade0e05eb9e680"
CORE_CHECK_SHA = "e80fc3fe31b689938b742b46efec461dadd07421b2039a9d247d6911f96bb314"
PRIMARY_SHA = "e5f8fc0d1d2be66798fe5c3974728b461dfc821148510925b0ddb4761f6fec9e"
MANIFEST_SHA = "584256beaac7c477ebbe4e144b7984ec5cd1fe48101bb3e4c308ae2a439579d1"
LAUNCH_SHA = "d23795ca537728f9434fc5692145ea201f3cd697efad48fd988c570fd9a17a3d"
ENDPOINT = "kernel/asterinas/kernel/core/src/fs/utils/endpoint.rs"
CONNECTED = "kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected.rs"
SOCKET = "kernel/asterinas/kernel/core/src/net/socket/unix/stream/socket.rs"
NETWORK = "tests/kernel/network/"
CURRENT_PINS = {
    ENDPOINT: "07e67a10fad1eb4cf84f56d37834e677da1ca03354cf22fb208e0d91ecb308ba",
    CONNECTED: "a331c8596416d56127eccd7beaa232dcb25bec5763648d322f6be5d697a904d3",
    SOCKET: "3458b0b5a9023c26b396d73e61c13c69affcf98fe23c46fc4ca5793b75db1933",
    NETWORK + "unix_stream_probe.c": "bb7e334a76c4e201b3ef33842be7f87a235a6940d783c8c741d63839519ab747",
    NETWORK + "unix_stream_protocol.json": PROTOCOL_SHA,
}
VARIANT_PINS = {
    "positive": CURRENT_PINS[CONNECTED],
    "race-fixed": "aac591b80a071aeb14d7ad337f538c7906b7a03bd64fe9ba44e26d92c9891348",
    "race-stale": "b80f1157bb9cbcb513ff6231fa72693268741b34e2fd1763df34a627a5736b0e",
    "aux-zero-progress": "c578aa3d6d2a05bc78c8100b24b39343eb8c21d9cda580e1092e6114983581e4",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": digest(data)}


def snapshot_git_tree(files):
    """Recompute Git's tree identity from every original tracked entry."""
    root = {}
    require(files, "source snapshot is empty")
    for name, entry in files.items():
        parts = name.split("/")
        require(all(part not in ("", ".", "..") and "\0" not in part for part in parts),
                "noncanonical tracked path")
        require(entry["mode"] in ("100644", "100755", "120000"), "unexpected tracked mode")
        require(re.fullmatch(r"[0-9a-f]{40}", entry["git_blob"]) is not None,
                "invalid tracked Git blob")
        require(re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None
                and type(entry["size"]) is int and entry["size"] >= 0, "invalid tracked byte identity")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            require(isinstance(node, dict), "tracked path conflicts with a file")
        require(parts[-1] not in node, "duplicate tracked path or tree conflict")
        node[parts[-1]] = (entry["mode"], entry["git_blob"])

    def tree(node):
        records = []
        for name, child in node.items():
            encoded = name.encode("utf-8")
            mode, oid = ("40000", tree(child)) if isinstance(child, dict) else child
            sort_key = encoded + (b"/" if isinstance(child, dict) else b"\0")
            records.append((sort_key, mode.encode("ascii") + b" " + encoded + b"\0" + bytes.fromhex(oid)))
        raw = b"".join(record for _, record in sorted(records))
        return hashlib.sha1(b"tree " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()

    return tree(root)


def read(path):
    return json.loads(path.read_text())


def load(name, path, expected):
    require(identity(path)["sha256"] == expected, "original parser identity differs: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def confined(root, name):
    path = root / name
    require(not Path(name).is_absolute() and path.resolve().is_relative_to(root.resolve()),
            "evidence path escapes archive root")
    return path


def verify_archive(archive_path, extracted, expected, manifest_name="manifest.json"):
    require(identity(archive_path) == expected, "archive byte identity differs")
    manifest = read(extracted / manifest_name)
    records = manifest["files"]
    require(len({row["path"] for row in records}) == len(records), "duplicate manifest path")
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        require(all(member.isfile() for member in members), "archive has non-file entries")
        names = {member.name for member in members}
        require(len(names) == len(members), "duplicate archive member")
        metadata = {manifest_name, "full-archive-manifest.json"}
        require(names == {row["path"] for row in records} | (names & metadata), "archive membership differs")
        for row in records:
            path = confined(extracted, row["path"])
            require(identity(path) == {k: row[k] for k in ("bytes", "sha256")}, "extracted identity differs")
            require(archive.extractfile(row["path"]).read() == path.read_bytes(), "archive bytes differ")
        for name in names & metadata:
            require(archive.extractfile(name).read() == confined(extracted, name).read_bytes(), "metadata differs")
    return {"original_files_verified": len(records), "archive_members_verified": len(members), **expected}


def replay_run(root, row, oracle):
    result_path, serial_path = confined(root, row["result"]), confined(root, row["serial"])
    result, raw = read(result_path), serial_path.read_bytes()
    require(result["schema"] == "asterinas.unix-stream-qualification.v1", "wrong run schema")
    require(result["source_variant"] == row["variant"], "run variant differs")
    require(result["source_head"] == row["source_head"] and result["source_tree"] == row["source_tree"],
            "run source differs from reviewed invocation")
    replayed = oracle.evaluate(raw, result["qemu_exit"], result["timed_out"], result["excessive_output"],
                               result["nonce"], row["selection"], row["variant"])
    require(replayed == result["oracle"], "full original oracle result differs")
    require(replayed["passed"] is row["expected_oracle_passed"], "unexpected semantic result")
    require(result["passed"] is replayed["passed"] and result["stage"] == "complete", "incomplete run")
    require(result["source_inputs_unchanged"] is True and result["boot_inputs_unchanged"] is True,
            "source or boot inputs changed")
    require(result["product_wrapper_exit"] == 0 and result["product_boot_raw_exit"] == 33,
            "ordinary product did not boot")
    require(result["compile_exit"] == 0 and result["qemu_exit"] == 33
            and result["timed_out"] is False and result["excessive_output"] is False, "guest transport failed")
    require(result["hepta_lifecycle_qualified"] is False and result["native_authority_qualified"] is False,
            "run scope was widened")
    argv = result["qemu_argv"]
    for flag, value in (("-smp", "1"), ("-m", "512M"), ("-accel", "tcg"), ("-machine", "q35")):
        require(argv.count(flag) == 1 and argv[argv.index(flag) + 1] == value, "QEMU profile differs")
    require(not set(argv) & {"-drive", "-hda", "-hdb", "-net", "-netdev", "-nic"}, "unexpected device input")
    if row.get("current_qualification") is True:
        expected_pins = {**CURRENT_PINS, CONNECTED: VARIANT_PINS[row["variant"]]}
        require(result["source_variant_sha256"] == expected_pins, "current source/probe pins differ")
        if row["variant"] == "positive":
            require((result["source_head"], result["source_tree"]) == (HEAD, TREE), "positive source differs")
    witnesses = [line for line in oracle.ANSI.sub("", raw.decode("ascii", errors="replace")).splitlines()
                 if any(marker in line for marker in (oracle.RACE, oracle.AUX, "event=case_fail", "UNIX_STREAM_HARNESS"))]
    return {"name": row["name"], "result": identity(result_path), "serial": identity(serial_path),
            "source_head": result["source_head"], "source_tree": result["source_tree"],
            "original_oracle_replay": replayed, "witnesses": witnesses,
            "probe_sha256": result["probe_sha256"], "kernel_sha256": result["boot_input_sha256"]["product-kernel.elf"],
            "qemu_sha256": result["qemu_sha256"], "compiler_sha256": result["compiler_sha256"],
            "bios_sha256": result["boot_input_sha256"]["bios.bin"],
            "lock_sha256": result["minimal_generated_lock_sha256"],
            "original_initramfs_sha256": result["original_initramfs_sha256"],
            "elapsed_seconds": result["elapsed_seconds"]}


def replay_core(root, row):
    checker = load("original_unix_core_checker", confined(root, row["checker"]), CORE_CHECK_SHA)
    recorded = read(confined(root, row["result"]))
    require(recorded["passed"] is True and len(recorded["crates"]) == 1, "core crate result differs")
    require(len(recorded["crates"][0]["guests"]) == 1, "unexpected core guest count")
    guest = confined(root, row["guest"])
    replayed = checker.check_guest(guest, "aster-core")
    require(replayed == recorded["crates"][0]["guests"][0], "core parser result differs")
    require(tuple(replayed[k] for k in ("declared", "passed", "failed", "filtered", "soft_skipped"))
            == (274, 274, 0, 0, 0), "core test counts differ")
    return {"original_checker_replay": replayed, "serial": identity(guest / "serial.log"),
            "qemu_record": identity(guest / "qemu.json"), "result": identity(confined(root, row["result"]))}


def verify_snapshots(root, names, head, tree, expected_files):
    require(len(names) == 3, "need original before/build/guest snapshots")
    snapshots = [read(confined(root, name)) for name in names]
    require(snapshots[0] == snapshots[1] == snapshots[2], "full source snapshot contents changed")
    first = snapshots[0]
    require(first["schema"] == "a06.g1-source-snapshot.v1", "wrong source snapshot schema")
    require(first["head"] == head and first["tree"] == tree, "snapshot source differs")
    require(snapshot_git_tree(first["files"]) == tree, "full tracked entries do not reconstruct source tree")
    for name, expected in expected_files.items():
        require(first["files"][name]["sha256"] == expected, "snapshot pin differs: " + name)
    return first, {"contents_reopened": True, "tracked_files": len(first["files"]),
                   "git_tree_recomputed_from_all_entries": tree,
                   "files": [{"path": name, **identity(confined(root, name))} for name in names]}


def verify_source_files(root, snapshot, names):
    """Bind reopened source bytes to their original full Git snapshot entries."""
    rows = []
    for name, archive_path in names.items():
        original = snapshot["files"][name]
        data = confined(root, archive_path).read_bytes()
        git_blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        require((len(data), digest(data), git_blob) ==
                (original["size"], original["sha256"], original["git_blob"]),
                "reopened source differs from full snapshot: " + name)
        rows.append({"repository_path": name, "archive_path": archive_path,
                     "bytes": len(data), "sha256": digest(data), "git_blob": git_blob,
                     "tracked_mode": original["mode"]})
    return rows


def replay_control_patches(source_root, manifest_path, patches_root):
    manifest = read(manifest_path)
    rows = []
    for variant, record in manifest["variants"].items():
        require(record["changed_paths"] == [CONNECTED], "control source scope differs")
        patch_path = patches_root / (variant + ".patch")
        require(identity(patch_path)["sha256"] == record["patch_sha256"], "control patch differs")
        with tempfile.TemporaryDirectory(prefix="unix-control-replay-") as temporary:
            destination = Path(temporary) / CONNECTED
            destination.parent.mkdir(parents=True)
            source = source_root / CONNECTED
            require(identity(source)["sha256"] == CURRENT_PINS[CONNECTED], "positive preimage differs")
            destination.write_bytes(source.read_bytes())
            for flag in ("--check", None):
                argv = ["git", "apply", *([flag] if flag else []), str(patch_path.resolve())]
                subprocess.run(argv, cwd=temporary, check=True, capture_output=True)
            require(identity(destination) == {"bytes": record["source_bytes"], "sha256": record["source_sha256"]},
                    "control postimage differs")
            require(identity(destination)["sha256"] == VARIANT_PINS[variant], "runner/control pins differ")
            rows.append({"variant": variant, "patch": identity(patch_path), "postimage": identity(destination)})
    require({row["variant"] for row in rows} == set(VARIANT_PINS) - {"positive"}, "missing control")
    return rows


def verify_full_manifest(root):
    manifest = read(root / "metadata/full-original-file-manifest.json")
    records = manifest["files"]
    by_path = {row["path"]: row for row in records}
    require(len(by_path) == len(records) == 209, "full original inventory differs")
    excluded = []
    for row in records:
        path = confined(root, row["path"])
        if row["included_in_primary"] is True:
            require(identity(path) == {k: row[k] for k in ("bytes", "sha256")},
                    "full original/primary text identity differs")
        else:
            require(row["included_in_primary"] is False and not path.exists(),
                    "host-only binary boundary differs")
            excluded.append(row)
    require(len(excluded) == 36 and manifest["binary_bytes_retained_on_execution_host"] is True
            and manifest["all_text_and_all_source_snapshots_in_primary"] is True,
            "archive scope differs")
    return by_path, {"manifest": identity(root / "metadata/full-original-file-manifest.json"),
                     "original_text_files_reopened": len(records) - len(excluded),
                     "host_only_artifact_records": excluded,
                     "host_only_binary_bytes_reopened": False}


def option(argv, flag):
    require(argv.count(flag) == 1 and argv.index(flag) + 1 < len(argv), "missing/duplicate option: " + flag)
    return argv[argv.index(flag) + 1]


def verify_product_record(root, row, snapshot, full, oracle):
    """Cross-bind original first boot and recorded binary identities, offline."""
    directory = row["directory"]
    result = read(root / row["result"])
    boot = confined(root, directory + "/product-boot")
    qemu = read(boot / "qemu.json")
    raw = (boot / "serial.log").read_bytes()
    require(qemu["raw_exit_code"] == 33 and qemu["timed_out"] is False
            and qemu["serial_sha256"] == digest(raw) and qemu["serial_size"] == len(raw),
            "ordinary product serial/exit differs")
    lines = oracle.ANSI.sub("", raw.decode("ascii", errors="replace")).splitlines()
    require(all(lines.count(marker) == 1 for marker in (oracle.INIT, oracle.CPU, oracle.BOOT)),
            "ordinary product original boot markers differ")
    require(not any(marker in "\n".join(lines) for marker in oracle.FATAL), "ordinary product fatal marker")
    require(result["host_disks_or_network_attached"] is False, "syscall guest scope differs")
    for filename in ("make-exit-code.txt", "run-exit-code.txt", "log-exit-code.txt"):
        require((boot / filename).read_text().strip() == "0", "ordinary wrapper exit differs")
    require((boot / "environment.log").read_text().splitlines().count(row["source_head"]) == 1,
            "ordinary environment source differs")
    command = shlex.split((boot / "command.sh").read_text())
    checkout = snapshot["root"]
    require(command[:8] == ["make", "-C", checkout + "/kernel/asterinas", "-f", "Makefile", "-f",
                            checkout + "/support/build/minimal.mk", "run_kernel"],
            "ordinary make invocation differs")
    required = {"TARGET_ARCH=x86_64", "SMP=1", "MEM=512M", "ENABLE_KVM=0", "BOOT_PROTOCOL=multiboot",
                "INITRAMFS=on", "AUTO_TEST=none", "A01_INITRAMFS=" + option(qemu["argv"], "-initrd"),
                "A01_QEMU_WRAPPER=" + checkout + "/support/build/record-qemu.py"}
    require(len(command) == 18 and command[8].startswith("CARGO_OSDK=") and set(command[9:]) == required,
            "ordinary build options differ")
    for flag, value in (("-smp", "1"), ("-m", "512M"), ("-accel", "tcg"), ("-machine", "q35")):
        require(option(qemu["argv"], flag) == value, "ordinary QEMU profile differs")
    require(not set(qemu["argv"]) & {"-drive", "-hda", "-hdb", "-net", "-netdev", "-nic"},
            "ordinary QEMU unexpectedly has disk/network arguments")
    require(qemu["qemu_sha256"] == result["qemu_sha256"], "QEMU changed between boots")
    for flag, sha in (("-kernel", result["boot_input_sha256"]["product-kernel.elf"]),
                      ("-bios", result["boot_input_sha256"]["bios.bin"]),
                      ("-initrd", result["original_initramfs_sha256"])):
        require(qemu["artifacts"][flag]["sha256"] == sha, "ordinary and injected boot artifact differ")
    binaries = {**result["boot_input_sha256"], "unix-stream-probe": result["probe_sha256"],
                "product-boot/initramfs.cpio.gz": result["original_initramfs_sha256"]}
    for name, sha in binaries.items():
        require(full[directory + "/" + name]["sha256"] == sha
                and full[directory + "/" + name]["included_in_primary"] is False,
                "recorded binary differs from original full inventory")
    require(snapshot["files"]["support/build/minimal/Cargo.lock"]["sha256"]
            == result["minimal_generated_lock_sha256"], "ordinary generated lock differs from source")
    source_gate = read(boot / "source-inputs.json")
    require(source_gate["passed"] is True and source_gate["errors"] == [], "original source gate failed")
    for name, sha in source_gate["input_sha256"].items():
        require(snapshot["files"]["kernel/asterinas/" + name]["sha256"] == sha,
                "ordinary source gate input differs")
    for section in ("downstream_manifests", "downstream_locks"):
        for name, entry in source_gate[section].items():
            require(snapshot["files"]["kernel/asterinas/" + name]["sha256"] == entry["derived_sha256"],
                    "ordinary derived source gate input differs")
    return {"serial": identity(boot / "serial.log"), "qemu_record": identity(boot / "qemu.json"),
            "command": identity(boot / "command.sh"), "environment": identity(boot / "environment.log"),
            "source_gate": identity(boot / "source-inputs.json"),
            "recorded_binary_identities_match_full_manifest": True,
            "binary_bytes_reopened": False}


def verify_actual_control(root, row, positive, snapshot, record):
    variant = row["variant"]
    folder = "unix-stream-controls-v5/"
    command = read(root / (folder + variant + ".command.json"))
    require(all(record[k] == value for k, value in command.items()), "control start/completion receipt differs")
    require((record["head"], record["tree"], record["positive_head"]) ==
            (row["source_head"], row["source_tree"], HEAD), "control execution source differs")
    require(record["exit_code"] == 0 and record["qualified"] is True
            and record["source_unchanged"] is True and record["probe_and_tools_unchanged"] is True,
            "control runner did not complete")
    result = read(root / row["result"])
    require(record["result_sha256"] == identity(root / row["result"])["sha256"]
            and record["oracle"] == result["oracle"], "control completion/full result differs")
    for flag, value in (("--expected-source-head", row["source_head"]), ("--expected-source-tree", row["source_tree"]),
                        ("--variant", variant), ("--selection", row["selection"]), ("--timeout", "90")):
        require(option(command["argv"], flag) == value, "control command differs")
    require(option(command["argv"], "--target-dir") == result["cargo_target_dir"], "control target differs")
    original, altered = positive["files"], snapshot["files"]
    require(original.keys() == altered.keys()
            and [name for name in original if original[name] != altered[name]] == [CONNECTED],
            "control changed more than the original connected owner")
    patch = root / (folder + variant + ".patch")
    require(identity(patch)["sha256"] == record["patch_sha256"], "actual control Git diff differs")
    require([line for line in patch.read_text().splitlines() if line.startswith("diff --git ")]
            == ["diff --git a/" + CONNECTED + " b/" + CONNECTED], "actual control patch scope differs")
    with tempfile.TemporaryDirectory(prefix="unix-actual-control-replay-") as temporary:
        destination = Path(temporary) / CONNECTED
        destination.parent.mkdir(parents=True)
        destination.write_bytes((root / "sources/positive" / CONNECTED).read_bytes())
        for flag in ("--check", None):
            subprocess.run(["git", "apply", *([flag] if flag else []), str(patch.resolve())],
                           cwd=temporary, check=True, capture_output=True)
        require(destination.read_bytes() == (root / ("sources/control/" + variant) / CONNECTED).read_bytes(),
                "actual Git diff does not reproduce archived control source")
        require(identity(destination)["sha256"] == VARIANT_PINS[variant] == record["source_sha256"],
                "actual control source differs")
    source = verify_source_files(root, snapshot, {CONNECTED: "sources/control/" + variant + "/" + CONNECTED})
    return {"variant": variant, "changed_paths": [CONNECTED], "command": identity(root / (folder + variant + ".command.json")),
            "actual_git_diff": identity(patch), "source": source[0], "full_tree_delta_verified": True}


def verify_launch_and_core_binding(root, positive):
    path = root / "metadata/original-launch-tool-responses.json"
    require(identity(path)["sha256"] == LAUNCH_SHA, "original launch responses differ")
    launches = read(path)
    require(set(launches) == {"unixFionreadNativeV5Job", "unixFionreadControlsV5Job"}, "wrong launch set")
    for launch in launches.values():
        require(launch["audit_recorded"] is True and launch["reused"] is False
                and launch["launch"]["ok"] is True and launch["job"]["launch_state"] == "launched"
                and launch["job"]["launch_error"] is None, "original launch was not admitted")
    prepared = read(root / "unix-stream-native-v5/prepared.json")
    require((prepared["head"], prepared["tree"]) == (HEAD, TREE), "prepared source differs")
    require(prepared["probe_source_sha256"] == CURRENT_PINS[NETWORK + "unix_stream_probe.c"], "prepared probe differs")
    rows = read(root / "unix-stream-native-v5/results.json")
    require([row["name"] for row in rows] == ["core", "positive"], "wrong native execution sequence")
    previous = prepared["start_ns"]
    for row in rows:
        require(row["exit_code"] == 0 and row["source_unchanged"] is True
                and previous <= row["start_ns"] < row["finish_ns"], "native wrapper or chronology differs")
        require(identity(root / ("unix-stream-native-v5/" + row["name"] + "-runner.log"))["sha256"]
                == row["log_sha256"], "native wrapper log differs")
        previous = row["finish_ns"]
    require(option(rows[0]["argv"], "--crate") == "aster-core"
            and option(rows[1]["argv"], "--expected-source-head") == HEAD
            and option(rows[1]["argv"], "--expected-source-tree") == TREE, "core/positive invocation differs")
    native_launch = launches["unixFionreadNativeV5Job"]["job"]
    control_launch = launches["unixFionreadControlsV5Job"]["job"]
    require(native_launch["created_unix_ms"] * 1000000 <= prepared["start_ns"]
            and rows[-1]["finish_ns"] <= control_launch["created_unix_ms"] * 1000000,
            "launch/result chronology differs")
    core = root / "unix-stream-native-v5/core"
    environment = read(core / "environment.json")
    require(environment["git_head"] == HEAD and environment["git_status"] == ""
            and environment["test_name"] is None and environment["ktest_profile"] == "default"
            and environment["vcpus"] == 1 and environment["features"] == [], "core source/profile differs")
    for name, sha in environment["build_inputs_sha256"].items():
        require(positive["files"][name]["sha256"] == sha, "core build input differs from full source tree")
    lock = identity(core / "aster-core/generated.Cargo.lock")
    require(lock["sha256"] == positive["files"]["support/build/ktest/locks/aster-core.Cargo.lock"]["sha256"],
            "core generated lock differs")
    require((core / "aster-core/osdk-exit-code.txt").read_text().strip() == "0", "core osdk exit differs")
    commands = read(core / "commands.json")
    require(len(commands) == 2 and commands[1]["lock_sha256"] == lock["sha256"], "core commands/lock differ")
    qemu = read(core / "aster-core/guests/guest-001/qemu.json")
    require(qemu["profile"] == {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
                                "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False},
            "core QEMU profile differs")
    collection = read(root / "metadata/collection.json")
    restored = read(root / "unix-stream-controls-v5/restored.json")
    require((collection["positive_head"], collection["positive_tree"]) == (HEAD, TREE)
            and collection["positive_restored_clean"] is True and restored["head"] == HEAD
            and restored["restored"] is True, "positive production source was not restored")
    controls = read(root / "unix-stream-controls-v5/results.json")
    require([row["variant"] for row in controls] == ["race-fixed", "race-stale", "aux-zero-progress"],
            "control execution sequence differs")
    previous = control_launch["created_unix_ms"] * 1000000
    for control in controls:
        require(previous <= control["start_ns"] < control["finish_ns"], "control chronology differs")
        previous = control["finish_ns"]
    require(previous < collection["collected_ns"], "collection preceded native completion")
    return {"original_launch_records": identity(path), "prepared": identity(root / "unix-stream-native-v5/prepared.json"),
            "actual_native_execution_rows": rows, "core_environment": identity(core / "environment.json"),
            "core_commands": identity(core / "commands.json"), "core_generated_lock": lock,
            "core_kernel_sha256_recorded_by_original_qemu": qemu["artifacts"]["-kernel"]["sha256"],
            "core_binary_bytes_reopened": False,
            "original_native_job_id": native_launch["id"], "original_control_job_id": control_launch["id"],
            "restored_positive": restored, "restoration_record": identity(root / "unix-stream-controls-v5/restored.json"),
            "collection_record": identity(root / "metadata/collection.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Original archive; overrides only its location, never its pin")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "independent review output must be fresh")
    require(not args.output.resolve().is_relative_to(args.root.resolve()),
            "independent review must not write into original evidence")
    index = read(args.index)
    require(index["schema"] == "asterinas.unix-stream-evidence-index.v1", "wrong complete evidence index")
    require(index.get("preparation_only") is False, "original input collection is incomplete")
    oracle_path = confined(args.root, index["oracle"])
    require(identity(oracle_path.with_name("unix_stream_protocol.json"))["sha256"] == PROTOCOL_SHA,
            "original protocol differs")
    oracle = load("original_unix_stream_oracle", oracle_path, ORACLE_SHA)
    require(index["archive"]["sha256"] == PRIMARY_SHA and index["archive"]["bytes"] == 554740,
            "this replay is for the frozen original archive only")
    require(identity(args.root / "manifest.json")["sha256"] == MANIFEST_SHA, "primary manifest differs")
    archive_path = args.archive or confined(args.root.parent, index["archive"]["path"])
    archive = verify_archive(archive_path, args.root, {"bytes": 554740, "sha256": PRIMARY_SHA})
    full, full_review = verify_full_manifest(args.root)
    rows = [replay_run(args.root, row, oracle) for row in index["runs"]]
    current = [row for row, spec in zip(rows, index["runs"]) if spec.get("current_qualification") is True]
    require({row["original_oracle_replay"]["variant"] for row in current} == set(VARIANT_PINS)
            and len(current) == 4, "complete four-lane evidence is required")
    for key in ("probe_sha256", "qemu_sha256", "compiler_sha256", "bios_sha256", "lock_sha256", "original_initramfs_sha256"):
        require(len({row[key] for row in current}) == 1, "current lanes differ in " + key)
    require(len(rows) == 7, "all preserved syscall runs must be replayed")
    snapshots, snapshot_reviews, product_reviews = {}, [], []
    for spec in index["runs"]:
        recorded = read(args.root / spec["result"])
        snapshot, reviewed = verify_snapshots(
            args.root, spec["snapshots"], spec["source_head"], spec["source_tree"],
            {**recorded["source_variant_sha256"], NETWORK + "unix_stream_oracle.py": ORACLE_SHA})
        require(len(snapshot["files"]) == recorded["source_file_count"] == 7716, "tracked file count differs")
        snapshots[spec["name"]] = snapshot
        snapshot_reviews.append({"name": spec["name"], **reviewed})
        product_reviews.append({"name": spec["name"], **verify_product_record(args.root, spec, snapshot, full, oracle)})
    positive = snapshots["v5-positive"]
    source_review = verify_source_files(args.root, positive, index["positive_sources"])
    require(len(source_review) == 16, "positive source collection differs")
    core = replay_core(args.root, index["core"])
    provenance = verify_launch_and_core_binding(args.root, positive)
    frozen_patches = replay_control_patches(args.root / "sources/positive",
        args.root / "sources/positive/tests/kernel/network/controls/manifest.json",
        args.root / "sources/positive/tests/kernel/network/controls")
    controls = {entry["variant"]: entry for entry in read(args.root / "unix-stream-controls-v5/results.json")}
    actual_patches = [verify_actual_control(args.root, spec, positive, snapshots[spec["name"]], controls[spec["variant"]])
                      for spec in index["runs"] if spec["current_qualification"] and spec["variant"] != "positive"]
    historical_sources = []
    for name, source_dir in (("v2-positive-rejected", "v2-positive"),
                             ("v3-race-stale-rejected", "v3-race-stale")):
        directory = args.root / ("sources/history/" + source_dir)
        paths = {str(path.relative_to(directory)): str(path.relative_to(args.root))
                 for path in directory.rglob("*") if path.is_file()}
        require(len(paths) == 7, "historical source collection differs")
        historical_sources.append({"name": name, "files": verify_source_files(args.root, snapshots[name], paths)})
    v2, v3 = rows[4], rows[6]
    require(v2["name"] == "v2-positive-rejected" and v2["original_oracle_replay"]["passed"] is False
            and any("selection=all exit=124" in line for line in v2["witnesses"]), "historical alarm was lost")
    require(v3["name"] == "v3-race-stale-rejected" and v3["original_oracle_replay"]["passed"] is False
            and any("op=race_fionread expected=0 observed=-1 errno=25" in line for line in v3["witnesses"]),
            "historical unqualified ENOTTY negative was lost")
    old_probes = {row["probe_sha256"] for row in rows[4:]}
    require(old_probes == {"052f016f9e8b8fbe60707b771d987a2e123df45ba1e9249797b7382fde11fe54"}
            and current[0]["probe_sha256"] == "701821798ff6b052aa7e2b0dd0da238ef517adf0313ad9d50175f40ebecaa56e",
            "old/final probe identities were conflated")
    format_path = args.root / "unix-stream-native-v4/format.log"
    format_text = format_path.read_text()
    require(format_text.count("Diff in ") == 1 and "State::Listen(_) =>" in format_text
            and "return_errno_with_message!(Errno::EINVAL" in format_text, "historical format output differs")
    require((args.root / "unix-stream-native-v5/format.log").read_bytes() == b"", "final format gate output differs")
    report = {
        "schema": "asterinas.unix-stream-independent-review.v1",
        "qualified_scope": "preserved ordinary x86_64 TCG one-CPU AF_UNIX directed regression and exact controls",
        "current_native_evidence_accepted": True, "new_native_execution_performed": False,
        "positive_head": HEAD, "positive_tree": TREE, "primary_archive": archive,
        "primary_manifest": identity(args.root / "manifest.json"), "full_original_inventory": full_review,
        "runs": rows, "source_snapshots": snapshot_reviews, "ordinary_product_records": product_reviews,
        "positive_source_bytes": source_review, "core": core, "original_execution_binding": provenance,
        "frozen_source_control_patches": frozen_patches, "actual_executed_control_git_diffs": actual_patches,
        "historical_source_bytes": historical_sources,
        "historical_v4_format_output": {"file": identity(format_path),
            "status": "original format diff retained; no original exit record or native guest result in primary",
            "counts_as_semantic_negative": False},
        "original_host_compatibility_runs_counted_as_native": False,
        "scope_not_qualified": ["original Agentd graceful shutdown", "HOS2/G2 native authority effects",
                                "persistent Hepta recovery", "full E isolation or memory.max",
                                "combined cross-branch release", "SMP", "hardware or phone"],
        "replay_script": identity(Path(__file__)), "evidence_index": identity(args.index),
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"review": str(args.output), "original_oracles_replayed": len(rows),
                      "source_snapshots_reopened": 3 * len(snapshot_reviews),
                      "current_native_evidence_accepted": True, "new_native_execution_performed": False}))


if __name__ == "__main__":
    main()
