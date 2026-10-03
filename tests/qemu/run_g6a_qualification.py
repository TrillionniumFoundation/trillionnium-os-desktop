#!/usr/bin/env python3
"""Real same-disk G6a QEMU boots and abrupt VM interruption matrix.

Fixed direct kernel/initramfs and fixed device ordering for every boot. Only the
guest selector chooses a root. Receipts never grant production/health authority.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("g6a_guest_harness", ROOT / "packaging/debian/g6a/guest_selector.py")
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def debugfs(image, command):
    completed = subprocess.run(["debugfs", "-w", "-R", command, str(image)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    if completed.returncode:
        raise RuntimeError("debugfs command failed")
    return completed.stdout + completed.stderr


def read_file(image, name, directory):
    destination = directory / ("read-" + name.replace("/", "-") + ".json")
    if destination.exists():
        destination.unlink()
    debugfs(image, f"dump /g6a/{name} {destination}")
    if not destination.is_file():
        raise RuntimeError("actual guest file missing: " + name)
    return destination.read_bytes()


def write_file(image, name, payload, directory):
    destination = directory / "write-input"
    destination.write_bytes(payload)
    debugfs(image, "rm /g6a/" + name)
    debugfs(image, f"write {destination} /g6a/{name}")
    for key, value in (("uid", "0"), ("gid", "0"), ("mode", "0100600")):
        debugfs(image, f"set_inode_field /g6a/{name} {key} {value}")
    if read_file(image, name, directory) != payload:
        raise RuntimeError("actual state image readback mismatch")


def boot(artifacts, state_image, images, directory, number, kill_at=None):
    directory.mkdir(exist_ok=True)
    serial = directory / f"serial-{number}.log"
    console = directory / f"qemu-{number}.log"
    args = ["qemu-system-x86_64", "-machine", "q35,accel=tcg", "-cpu", "max", "-m", "1024", "-smp", "2", "-nodefaults", "-no-reboot", "-display", "none", "-monitor", "none", "-nic", "none", "-kernel", str(artifacts / "vmlinuz"), "-initrd", str(artifacts / "initrd.img"), "-append", "console=ttyS0,115200 rdinit=/init panic=-1", "-serial", "file:" + str(serial)]
    # All five *actual* disks have stable ordering. No host root=slot parameter.
    for index, path in enumerate([state_image, *images]):
        readonly = "off" if index == 0 else "on"
        args += ["-drive", f"file={path},format=raw,if=virtio,cache=none,readonly={readonly}"]
    (directory / f"command-{number}.json").write_bytes(guest.canonical(args))
    start = time.monotonic()
    interrupted = False
    with console.open("wb") as stream:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream)
        try:
            while process.poll() is None:
                if time.monotonic() - start > 120:
                    raise RuntimeError("real guest boot deadline exhausted")
                if kill_at and serial.exists():
                    lines = serial.read_text(errors="replace").splitlines()
                    if any(line.startswith("G6A_CUTPOINT ") and json.loads(line.partition(" ")[2]).get("name") == kill_at for line in lines):
                        process.kill()  # Actual SIGKILL of a running VM, no graceful sync.
                        interrupted = True
                        break
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
    text = serial.read_text(errors="replace") if serial.exists() else ""
    observed = [json.loads(line.partition(" ")[2]) for line in text.splitlines() if line.startswith("G6A_ROOT_OBSERVED ")]
    refused = [json.loads(line.partition(" ")[2]) for line in text.splitlines() if line.startswith("G6A_SELECTOR_REFUSED ")]
    if kill_at:
        if not interrupted or observed:
            raise RuntimeError("requested real interruption not observed")
    elif len(observed) + len(refused) != 1:
        raise RuntimeError("real guest produced no unique terminal observation; inspect " + str(serial))
    for receipt in observed:
        for field in ("production_activation_enabled", "measured_health_qualified", "commit_performed", "firmware_authenticated", "rollback_anchor_protected"):
            if receipt[field] is not False:
                raise RuntimeError("fixture authority ceiling changed")
        if not all(receipt[field] is True for field in ("actual_root_mount_readonly", "actual_mapping_readonly", "root_write_refused")):
            raise RuntimeError("actual immutable root not observed")
        actual = json.loads(read_file(state_image, f"boot-{receipt['boot_number']:02d}.json", directory))
        if actual != receipt:
            raise RuntimeError("serial and actual installed durable receipt differ")
    return {"returncode": process.returncode, "actual_vm_interrupted": interrupted, "observed": observed, "refused": refused, "target_failure": "G6A_TARGET_FAILURE" in text, "serial_sha256": digest(serial), "command_sha256": digest(directory / f"command-{number}.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cases", default="all")
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    output = args.output_dir.absolute()
    if output.exists() or any(character in str(output) for character in ('"', "\n", " ")):
        raise RuntimeError("new simple output path required")
    report = json.loads((artifacts / "build-result.json").read_bytes())
    if report["fixture_only"] is not True or report["production_activation_enabled"] is not False:
        raise RuntimeError("only test fixture artifacts permitted")
    if set(report["artifacts"]) != {"state.ext4", "root-A.ext4", "root-A.verity", "root-B.ext4", "root-B.verity", "vmlinuz", "initrd.img"}:
        raise RuntimeError("closed fixture artifact inventory required")
    for name, entry in report["artifacts"].items():
        path = artifacts / name
        if path.is_symlink() or path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise RuntimeError("actual build artifact changed: " + name)
    output.mkdir()
    shutil.copyfile(artifacts / "build-result.json", output / "build-result.json")
    matrix = ["source", "pending", "target_failure", "bad_signature", "unsigned_target", "target_data_corrupt", "target_hash_corrupt", "source_data_corrupt", "state_corrupt", "publication_orphan", "disk_full", *["cut_" + name for name in guest.CUTPOINTS]]
    requested = matrix if args.cases == "all" else args.cases.split(",")
    if any(name not in matrix for name in requested) or len(set(requested)) != len(requested):
        raise RuntimeError("closed finite case inventory required")
    results = {}
    for name in requested:
        directory = output / name
        directory.mkdir()
        state = directory / "state.ext4"
        shutil.copyfile(artifacts / "state.ext4", state)
        images = [artifacts / filename for filename in ("root-A.ext4", "root-A.verity", "root-B.ext4", "root-B.verity")]
        value = guest.boot_state(read_file(state, "boot-state.json", directory))
        if name != "source":
            value["pending_slot"] = "B"
        write_file(state, "boot-state.json", guest.canonical(value), directory)
        control = {"pause_at": None, "target_failure": name == "target_failure"}
        if name.startswith("cut_"):
            control["pause_at"] = name.removeprefix("cut_")
        write_file(state, "case-control.json", guest.canonical(control), directory)
        if name == "bad_signature":
            signature = bytearray(read_file(state, "root-B.sig", directory))
            signature[len(signature) // 2] ^= 1
            descriptor = guest.descriptor(read_file(state, "root-B.json", directory), "B")
            descriptor["signature_sha256"] = hashlib.sha256(signature).hexdigest()
            write_file(state, "root-B.sig", bytes(signature), directory)
            write_file(state, "root-B.json", guest.canonical(descriptor), directory)
        if name == "unsigned_target":
            debugfs(state, "rm /g6a/root-B.sig")
        mutation = {"target_data_corrupt": 2, "target_hash_corrupt": 3, "source_data_corrupt": 0}.get(name)
        if mutation is not None:
            changed = directory / images[mutation].name
            shutil.copyfile(images[mutation], changed)
            with changed.open("r+b") as stream:
                offset = changed.stat().st_size // 2
                stream.seek(offset)
                byte = stream.read(1)
                stream.seek(offset)
                stream.write(bytes([byte[0] ^ 1]))
            images[mutation] = changed
        if name == "state_corrupt":
            write_file(state, "boot-state.json", b"{", directory)
        if name == "publication_orphan":
            write_file(state, ".g6a-tmp-99999", b"interrupted", directory)
        if name == "disk_full":
            payload = directory / "fill"
            with payload.open("wb") as stream:
                for _ in range(32):
                    stream.write(os.urandom(1024**2))
            debugfs(state, f"write {payload} /g6a/fill")
            stats = debugfs(state, "stats").decode(errors="replace")
            if "Free blocks:              0" not in stats:
                import re
                if not re.search(r"Free blocks:\s+0\b", stats):
                    raise RuntimeError("actual ext4 ENOSPC fixture not established")
        boots = []
        if name.startswith("cut_"):
            boots.append(boot(artifacts, state, images, directory, 1, control["pause_at"]))
            # Reboot the exact interrupted disk. An offline debugfs write before
            # journal recovery would alter the fact being tested. The fixture
            # pause expires naturally if startup reaches that boundary again.
            boots.append(boot(artifacts, state, images, directory, 2))
            uncertain = name.removeprefix("cut_") in guest.CUTPOINTS[:4]
            expect_refused = uncertain and bool(boots[-1]["refused"])
        else:
            count = 3 if name in {"pending", "target_failure"} else 1
            boots = [boot(artifacts, state, images, directory, number) for number in range(1, count + 1)]
            expect_refused = name in {"source_data_corrupt", "state_corrupt", "publication_orphan", "disk_full"}
        terminal = boots[-1]
        if expect_refused:
            if len(terminal["refused"]) != 1 or terminal["observed"]:
                raise RuntimeError("fault did not refuse actual boot: " + name)
        else:
            slots = [item["observed"][0]["slot"] for item in boots if item["observed"]]
            expected = ["B", "B", "A"] if name in {"pending", "target_failure"} else ["B"] if name.startswith("cut_") else ["A"]
            if slots != expected:
                raise RuntimeError("guest slot selection differs: " + name + ": " + str(slots))
            ids = [item["observed"][0]["boot_id"] for item in boots if item["observed"]]
            if len(ids) != len(set(ids)):
                raise RuntimeError("boots reuse a kernel boot identity")
            if name == "target_failure" and [item["target_failure"] for item in boots] != [True, True, False]:
                raise RuntimeError("actual failed target boot/fallback missing")
            if name.startswith("cut_"):
                receipt = terminal["observed"][0]
                allowed = {1, 2} if uncertain else {2}
                if receipt["attempts"] not in allowed or receipt["boot_number"] != receipt["attempts"]:
                    raise RuntimeError("interrupted attempt was silently reset or extended: " + name)
                if receipt["operation_id"] != value["operation_id"]:
                    raise RuntimeError("interrupted operation identity changed: " + name)
        results[name] = {"status": "PASS", "boots": boots, "state_sha256": digest(state), "source_build_result_sha256": digest(artifacts / "build-result.json")}
        (output / "partial-result.json").write_bytes(guest.canonical(results))
    result = {"schema": "trillionnium.desktop.g6a-qemu-result.v1", "status": "PASS", "cases": results, "fixture_only": True,
              "complete_matrix_executed": requested == matrix,
              "harness_source_sha256": digest(Path(__file__)),
              "qemu_version": subprocess.check_output(["qemu-system-x86_64", "--version"], text=True).splitlines()[0],
              "source_build_result_sha256": digest(artifacts / "build-result.json"), "qemu_network_enabled": False,
              "physical_power_cut_qualified": False, "firmware_authenticated": False, "measured_health_qualified": False,
              "protected_rollback_anchor": False, "desktop_installed_qualified": False, "production_activation_enabled": False}
    (output / "result.json").write_bytes(guest.canonical(result))
    print(json.dumps({"status": "PASS", "actual_cases": len(results), "fixture_only": True, "production_activation_enabled": False}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("G6a actual qualification refused: " + str(error), file=sys.stderr)
        raise SystemExit(1)
