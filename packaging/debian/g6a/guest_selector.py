#!/usr/bin/python3
"""G6a installed QEMU fixture. Fixed devices, real crypto and dm-verity.

This is deliberately not a product updater, a health permit or firmware trust.
The fixed direct-boot kernel/initramfs are custody of the test harness. Mutable
attempt counters have no independently protected rollback anchor.
"""
from __future__ import annotations

import array
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

DOMAIN = b"trillionnium.desktop.g6a-fixture-root.v1\0"
SCHEMA = "trillionnium.desktop.g6a-fixture-root.v1"
STATE_SCHEMA = "trillionnium.desktop.g6a-boot-state.v1"
MAX_DOCUMENT = 16384
MAX_IMAGE = 2 * 1024**3
MAX_BOOTS = 32
HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[0-9a-f]{32}\Z")
DEVICES = {"A": ("/dev/vdb", "/dev/vdc"), "B": ("/dev/vdd", "/dev/vde")}
FIELDS = {"schema", "slot", "generation", "data_sha256", "data_bytes", "hash_sha256", "hash_bytes", "verity", "signature_sha256", "fixture_only", "production_activation_enabled"}
VERITY_FIELDS = {"format", "algorithm", "data_block_size", "hash_block_size", "data_blocks", "hash_start_block", "root_hash", "salt"}
STATE_FIELDS = {"schema", "source_slot", "pending_slot", "attempts", "boot_number", "operation_id", "fixture_only", "production_activation_enabled"}
CUTPOINTS = ("temporary_created", "temporary_written", "file_synced", "name_replaced", "directory_synced", "readback_confirmed")
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C", "OPENSSL_CONF": "/dev/null", "OPENSSL_MODULES": "/nonexistent"}


class Refused(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise Refused(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def document(payload):
    require(type(payload) is bytes and 0 < len(payload) <= MAX_DOCUMENT, "document_size")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_member")
            result[key] = value
        return result
    def constant(_):
        raise Refused("nonfinite_json")
    try:
        result = json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError) as error:
        raise Refused("invalid_json") from error
    require(type(result) is dict, "object_required")
    return result


def integer(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, "integer_range")


def descriptor(payload, slot):
    value = document(payload)
    require(set(value) == FIELDS and value["schema"] == SCHEMA, "descriptor_fields")
    require(slot in DEVICES and value["slot"] == slot, "descriptor_slot")
    require(value["fixture_only"] is True and value["production_activation_enabled"] is False, "fixture_ceiling")
    integer(value["generation"], 1, 2**31 - 1)
    for field in ("data_sha256", "hash_sha256", "signature_sha256"):
        require(type(value[field]) is str and HASH.fullmatch(value[field]), "descriptor_digest")
    integer(value["data_bytes"], 4096, MAX_IMAGE)
    integer(value["hash_bytes"], 4096, MAX_IMAGE)
    parameters = value["verity"]
    require(type(parameters) is dict and set(parameters) == VERITY_FIELDS, "verity_fields")
    require(parameters["format"] == 1 and type(parameters["format"]) is int and parameters["algorithm"] == "sha256", "verity_algorithm")
    require(parameters["data_block_size"] == 4096 and type(parameters["data_block_size"]) is int and parameters["hash_block_size"] == 4096 and type(parameters["hash_block_size"]) is int, "verity_block_size")
    integer(parameters["data_blocks"], 1, MAX_IMAGE // 4096)
    require(value["data_bytes"] == parameters["data_blocks"] * 4096 and value["hash_bytes"] % 4096 == 0, "verity_geometry")
    require(type(parameters["hash_start_block"]) is int and parameters["hash_start_block"] == 0, "verity_hash_offset")
    require(type(parameters["root_hash"]) is str and HASH.fullmatch(parameters["root_hash"]), "verity_root_hash")
    require(type(parameters["salt"]) is str and HASH.fullmatch(parameters["salt"]), "verity_salt")
    return value


def signing_bytes(value):
    descriptor(canonical(value), value.get("slot"))
    return DOMAIN + canonical({key: value[key] for key in sorted(value) if key != "signature_sha256"})


def custody(metadata):
    # Reading may legitimately change atime (especially actual installed ext4).
    # Identity, privilege, linkage, bytes and modification epochs must not move.
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid,
            metadata.st_gid, metadata.st_nlink, metadata.st_size,
            metadata.st_mtime_ns, metadata.st_ctime_ns)


def private_read(path, maximum=MAX_DOCUMENT):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= maximum, "private_file_custody")
        chunks = []
        while True:
            chunk = os.read(fd, maximum + 1 - sum(map(len, chunks)))
            if not chunk:
                break
            chunks.append(chunk)
            require(sum(map(len, chunks)) <= maximum, "private_file_size")
        require(custody(os.fstat(fd)) == custody(before) and custody(os.stat(path, follow_symlinks=False)) == custody(before), "private_file_changed")
        return b"".join(chunks)
    finally:
        os.close(fd)


def verify_signature(value, signature, public_key):
    require(type(signature) is bytes and 0 < len(signature) <= MAX_DOCUMENT and hashlib.sha256(signature).hexdigest() == value["signature_sha256"], "signature_envelope")
    require(type(public_key) is bytes and 0 < len(public_key) <= MAX_DOCUMENT, "public_key_size")
    owners = []
    try:
        for name, payload in (("g6a-preimage", signing_bytes(value)), ("g6a-signature", signature), ("g6a-public-key", public_key)):
            fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            owners.append(fd)
            cursor = 0
            while cursor < len(payload):
                written = os.write(fd, payload[cursor:])
                require(written > 0, "signature_snapshot_write")
                cursor += written
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        result = subprocess.run(["/usr/bin/openssl", "dgst", "-sha256", "-verify", f"/proc/self/fd/{owners[2]}", "-signature", f"/proc/self/fd/{owners[1]}", f"/proc/self/fd/{owners[0]}"], pass_fds=tuple(owners), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV, timeout=15, check=False)
        require(result.returncode == 0, "signature_invalid")
    finally:
        for fd in owners:
            os.close(fd)


def boot_state(payload):
    value = document(payload)
    require(set(value) == STATE_FIELDS and value["schema"] == STATE_SCHEMA, "state_fields")
    require(value["source_slot"] == "A" and value["pending_slot"] in {None, "B"}, "state_slot")
    integer(value["attempts"], 0, 2)
    integer(value["boot_number"], 0, MAX_BOOTS)
    require(value["pending_slot"] is not None or value["attempts"] == 0, "state_attempts")
    require(type(value["operation_id"]) is str and ID.fullmatch(value["operation_id"]), "state_operation")
    require(value["fixture_only"] is True and value["production_activation_enabled"] is False, "state_ceiling")
    return value


def publish_state(root, value, cutpoint=lambda _: None):
    """Actual six publication boundaries, never remove an interrupted temp."""
    boot_state(canonical(value))
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        before = os.fstat(directory)
        require(before.st_uid == os.geteuid() and stat.S_IMODE(before.st_mode) == 0o700, "state_root_custody")
        name = f".g6a-tmp-{os.getpid()}"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        cutpoint(CUTPOINTS[0])
        payload = canonical(value)
        cursor = 0
        while cursor < len(payload):
            written = os.write(fd, payload[cursor:])
            require(written > 0, "state_write")
            cursor += written
        cutpoint(CUTPOINTS[1])
        os.fsync(fd)
        cutpoint(CUTPOINTS[2])
        named_root = os.stat(root, follow_symlinks=False)
        require((os.fstat(directory).st_dev, os.fstat(directory).st_ino) == (before.st_dev, before.st_ino) and (named_root.st_dev, named_root.st_ino) == (before.st_dev, before.st_ino), "state_root_changed")
        require(os.stat(name, dir_fd=directory, follow_symlinks=False) == os.fstat(fd), "temporary_publication_changed")
        os.replace(name, "boot-state.json", src_dir_fd=directory, dst_dir_fd=directory)
        cutpoint(CUTPOINTS[3])
        os.fsync(directory)
        cutpoint(CUTPOINTS[4])
        require(private_read(Path(root) / "boot-state.json") == payload, "state_readback")
        require(os.stat("boot-state.json", dir_fd=directory, follow_symlinks=False) == os.fstat(fd), "publication_inode_changed")
        cutpoint(CUTPOINTS[5])
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def command(args):
    completed = subprocess.run(args, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    require(completed.returncode == 0 and len(completed.stdout) <= 65536, "kernel_tool_refused")
    return completed.stdout.decode("ascii").strip()


def block_digest(path, expected_bytes):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        require(stat.S_ISBLK(metadata.st_mode), "actual_block_device_required")
        capacity = array.array("Q", [0])
        fcntl.ioctl(fd, 0x80081272, capacity, True)  # BLKGETSIZE64, actual kernel.
        require(capacity[0] == expected_bytes, "block_capacity")
        digest = hashlib.sha256()
        remaining = expected_bytes
        while remaining:
            chunk = os.read(fd, min(1024**2, remaining))
            require(bool(chunk), "block_short_read")
            digest.update(chunk)
            remaining -= len(chunk)
        require(os.fstat(fd).st_rdev == metadata.st_rdev and os.stat(path, follow_symlinks=False).st_rdev == metadata.st_rdev, "block_identity_changed")
        return digest.hexdigest()
    finally:
        os.close(fd)


def verity_options(value):
    p = value["verity"]
    return ["--no-superblock", "--format=1", "--hash=sha256", "--data-block-size=4096", "--hash-block-size=4096", f"--data-blocks={p['data_blocks']}", "--hash-offset=0", f"--salt={p['salt']}"]


def verify_slot(root, slot, public_key):
    value = descriptor(private_read(Path(root) / f"root-{slot}.json"), slot)
    verify_signature(value, private_read(Path(root) / f"root-{slot}.sig"), public_key)
    data, hashes = DEVICES[slot]
    require(block_digest(data, value["data_bytes"]) == value["data_sha256"], "data_digest_mismatch")
    require(block_digest(hashes, value["hash_bytes"]) == value["hash_sha256"], "hash_digest_mismatch")
    command(["/usr/sbin/veritysetup", *verity_options(value), "verify", data, hashes, value["verity"]["root_hash"]])
    return value


def mapping_table(value, table):
    fields = table.split()
    p = value["verity"]
    require(len(fields) in {13, 14} and (len(fields) == 13 or fields[13] == "0"), "unexpected_verity_options")
    data, hashes = (os.stat(path).st_rdev for path in DEVICES[value["slot"]])
    expected = ["0", str(value["data_bytes"] // 512), "verity", "1", f"{os.major(data)}:{os.minor(data)}", f"{os.major(hashes)}:{os.minor(hashes)}", "4096", "4096", str(p["data_blocks"]), "0", "sha256", p["root_hash"], p["salt"]]
    require(fields[:13] == expected, "kernel_mapping_mismatch")


def emit(marker, value):
    print(marker + " " + canonical(value).decode("ascii"), flush=True)


def main():
    require(os.geteuid() == 0 and os.getpid() == 1, "guest_pid1_required")
    root = Path("/state/g6a")
    require(not any(name.startswith(".g6a-tmp-") for name in os.listdir(root)), "interrupted_publication_requires_recovery")
    state = boot_state(private_read(root / "boot-state.json"))
    require(state["boot_number"] < MAX_BOOTS, "boot_history_capacity")
    control = document(private_read(root / "case-control.json"))
    require(set(control) == {"pause_at", "target_failure"} and control["pause_at"] in {None, *CUTPOINTS} and type(control["target_failure"]) is bool, "fixture_control_fields")
    public_key = Path("/g6a-public.pem").read_bytes()
    source = verify_slot(root, "A", public_key)
    slot, reason, selected = "A", "source_only", source
    if state["pending_slot"] == "B":
        if state["attempts"] == 2:
            reason = "target_attempts_exhausted"
        else:
            try:
                selected = verify_slot(root, "B", public_key)
                require(selected["generation"] > source["generation"], "target_generation_not_newer")
                slot, reason = "B", "pending_target"
                state["attempts"] += 1
            except (Refused, OSError, subprocess.SubprocessError) as error:
                selected = source
                reason = "target_refused:" + str(error)[:96]
    state["boot_number"] += 1
    def cutpoint(name):
        emit("G6A_CUTPOINT", {"name": name, "boot_number": state["boot_number"], "operation_id": state["operation_id"]})
        if control["pause_at"] == name:
            time.sleep(30)  # Only the isolated qualification fixture can pause.
    publish_state(root, state, cutpoint)
    data, hashes = DEVICES[slot]
    command(["/usr/sbin/veritysetup", *verity_options(selected), "open", data, "hepta-g6a-root", hashes, selected["verity"]["root_hash"]])
    table = command(["/usr/sbin/dmsetup", "table", "hepta-g6a-root"])
    mapping_table(selected, table)
    command(["/bin/busybox", "mount", "-t", "ext4", "-o", "ro,noload", "/dev/mapper/hepta-g6a-root", "/newroot"])
    # Read every mapped data block through the kernel, not just dm status V.
    require(block_digest("/dev/mapper/hepta-g6a-root", selected["data_bytes"]) == selected["data_sha256"], "mapped_full_image_mismatch")
    require(Path("/newroot/etc/g6a-slot").read_text().strip() == slot, "immutable_slot_marker_mismatch")
    receipt = {"schema": "trillionnium.desktop.g6a-selected-root.v1", "slot": slot, "reason": reason, "operation_id": state["operation_id"], "boot_number": state["boot_number"], "attempts": state["attempts"], "descriptor": selected, "kernel_verity_table": table, "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "fixture_only": True, "production_activation_enabled": False}
    path = root / "selected-root.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        payload = canonical(receipt)
        require(os.write(fd, payload) == len(payload), "receipt_write")
        os.fsync(fd)
    finally:
        os.close(fd)
    # Move /dev last: subsequent fixed subprocesses still need /dev/null for
    # their stdin. switch_root then inherits the already opened console fds.
    for mount in ("state", "proc", "sys", "dev"):
        command(["/bin/busybox", "mount", "--move", "/" + mount, "/newroot/" + mount])
    os.execv("/bin/busybox", ["busybox", "switch_root", "/newroot", "/sbin/g6a-fixture-init"])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit("G6A_SELECTOR_REFUSED", {"reason": str(error)[:160], "fixture_only": True, "production_activation_enabled": False})
        subprocess.run(["/bin/busybox", "poweroff", "-f"], check=False)
        raise SystemExit(1)
