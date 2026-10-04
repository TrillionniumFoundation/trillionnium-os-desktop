"""Read-only source diagnostics, never boot, signing, health or update authority."""
from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_MODULE = "hepta_update_recovery_v1"
if _MODULE not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE, Path(__file__).with_name("update_recovery.py"))
    if _spec is None or _spec.loader is None:
        raise RuntimeError("bundled update parser unavailable")
    recovery = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE] = recovery
    _spec.loader.exec_module(recovery)
else:
    recovery = sys.modules[_MODULE]

SCHEMA = "trillionnium.desktop.update-boot-observation.v1"
MAX_EVENTS = 256
MAX_RECORD_BYTES = 64 * 1024
MAX_MOUNTINFO_BYTES = 512 * 1024
MAX_MOUNTS = 4096
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_PATH_COMPONENTS = 32
_EVENT = re.compile(r"update-event-([0-9]{6})\.json\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_BOOT = re.compile(rb"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\n?\Z")
_ZERO = "0" * 64
_MARKER = "update-recovery-required.json"
_EVENT_FIELDS = {"schema", "sequence", "previous_sha256", "owner_id", "kind", "phase", "observed_unix", "configuration", "operation", "stage_receipt", "production_activation_enabled", "bootloader_effect_performed"}
_CONFIG_FIELDS = {"active_slot", "current_version", "current_image_sha256", "protected_rollback_floor", "trust_policy_sha256", "state_root_identity", "slot_root_identity"}
_OP_FIELDS = {"operation_id", "owner_id", "ticket_sequence", "manifest", "signature_admission"}
_ADMISSION_FIELDS = {"signer_id", "public_key_sha256", "signature_sha256", "signing_preimage_sha256", "trust_policy_sha256", "minimum_version", "verified_unix"}
_STAGE_FIELDS = {"target_slot", "image_sha256", "image_bytes", "manifest_sha256", "signature_sha256", "production_activation_enabled"}
_MARKER_FIELDS = {"schema", "phase", "reason", "state_root_identity", "slot_root_identity", "history_count", "last_event_sha256", "operation_id", "production_activation_enabled", "bootloader_effect_performed"}
_PHASES = {"owner_open": "idle", "manifest_verified": "verified", "stage_intent": "stage_intent", "stage_completed": "staged", "arm_intent": "arm_intent", "boot_policy_armed": "boot_pending", "owner_clean": "closed"}
_NEXT = {None: {"owner_open"}, "owner_open": {"manifest_verified", "owner_clean"}, "manifest_verified": {"stage_intent"}, "stage_intent": {"stage_completed"}, "stage_completed": {"arm_intent"}, "arm_intent": {"boot_policy_armed"}, "boot_policy_armed": set(), "owner_clean": {"owner_open"}}


class ObservationStatus(str, Enum):
    NO_PENDING_UPDATE = "no_pending_update"
    PENDING_IDENTITY_UNKNOWN = "pending_identity_unknown"
    RECOVERY_REQUIRED = "recovery_required"
    UNAVAILABLE = "observation_unavailable"


class ObservationReason(str, Enum):
    OWNER_BUSY = "owner_busy"
    CUSTODY_UNAVAILABLE = "custody_unavailable"
    JOURNAL_INVALID = "journal_invalid"
    KERNEL_UNAVAILABLE = "kernel_observation_unavailable"
    KERNEL_CHANGED = "kernel_observation_changed"
    UNFINISHED_OWNER = "unfinished_owner"
    RECOVERY_MARKER = "recovery_marker_present"
    SIGNATURE_UNAVAILABLE = "signature_authority_unavailable"
    IMAGE_MAPPING_UNKNOWN = "signed_boot_image_mapping_unknown"


class _Refused(Exception):
    def __init__(self, reason: ObservationReason):
        self.reason = reason


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


@dataclass(frozen=True)
class BootObservation:
    """Diagnostic bytes only; no API accepts this as permission or boot proof."""
    status: ObservationStatus
    reasons: tuple[ObservationReason, ...]
    _private: bytes

    def public_json(self) -> bytes:
        return _canonical({"schema": SCHEMA, "status": self.status.value,
            "reason_codes": [reason.value for reason in self.reasons],
            "signature_authority": "unavailable", "signed_boot_image_mapping": "unknown",
            "booted_image_verified": False, "production_activation_enabled": False,
            "bootloader_effect_performed": False, "continuation_authorized": False})

    def private_json(self) -> bytes:
        return self._private


class _Descriptor:
    def __init__(self):
        self._owned = []

    @property
    def fd(self):
        return self._owned[0]

    def close(self):
        if self._owned:
            os.close(self._owned.pop())

    def __del__(self):
        try:
            self.close()
        except BaseException:
            pass


def _close_all(owners):
    detached, owners[:] = list(owners), []
    first = None
    for owner in detached:
        try:
            owner.close()
        except BaseException as error:
            if first is None:
                first = error
    if first is not None:
        raise first


def _path(path: Path) -> tuple[str, ...]:
    text = os.fspath(path)
    if type(text) is not str or not text.startswith("/") or len(text.encode()) > 4096:
        raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
    parts = text.split("/")[1:]
    if not 1 <= len(parts) <= MAX_PATH_COMPONENTS or any(part in {"", ".", ".."} or "\x00" in part or len(part.encode()) > 255 for part in parts):
        raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
    return tuple(parts)


def _directory(metadata, *, private=False):
    if not stat.S_ISDIR(metadata.st_mode) or (private and (metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) & 0o077)):
        raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
    return metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid, metadata.st_gid


def _regular(metadata, *, empty=False, image=False):
    maximum = recovery.MAX_IMAGE_BYTES if image else MAX_RECORD_BYTES
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) != 0o600 or not (0 if empty else 1) <= metadata.st_size <= maximum:
        raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
    return metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid, metadata.st_gid, metadata.st_nlink, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns


class _Reader:
    """One creator-thread scan; cleanup only closes owned descriptor copies."""
    def __init__(self):
        self.pid, self.thread = os.getpid(), threading.current_thread()
        self.owners, self.directories, self.files = [], [], []

    def _check(self):
        if os.getpid() != self.pid or threading.current_thread() is not self.thread:
            raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)

    def _open(self, path, flags, *, parent=None):
        self._check()
        owner = _Descriptor()
        self.owners.append(owner)
        owner._owned = [os.open(path, flags | os.O_CLOEXEC, dir_fd=parent)]
        return owner

    def root(self, path):
        self._check()
        current = self._open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in _path(path):
            child = self._open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, parent=current.fd)
            metadata = _directory(os.fstat(child.fd))
            self.directories.append((current, part, child, metadata))
            current = child
        _directory(os.fstat(current.fd), private=True)
        return current

    def file(self, root, name, *, empty=False, image=False):
        self._check()
        child = self._open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, parent=root.fd)
        metadata = _regular(os.fstat(child.fd), empty=empty, image=image)
        self.files.append((root, name, child, metadata, empty, image))
        if _regular(os.stat(name, dir_fd=root.fd, follow_symlinks=False), empty=empty, image=image) != metadata:
            raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
        return child, metadata

    def lease(self, root):
        child, _ = self.file(root, ".coordinator.lock", empty=True)
        try:
            fcntl.flock(child.fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EAGAIN, errno.EACCES}:
                raise _Refused(ObservationReason.OWNER_BUSY) from error
            raise

    def inventory(self, root, bound):
        self._check()
        names = set()
        with os.scandir(root.fd) as entries:
            for item in entries:
                names.add(item.name)
                if len(names) > bound:
                    raise _Refused(ObservationReason.JOURNAL_INVALID)
        return names

    def record(self, root, name):
        child, metadata = self.file(root, name)
        data = bytearray()
        while len(data) <= MAX_RECORD_BYTES:
            self._check()
            chunk = os.pread(child.fd, min(65536, MAX_RECORD_BYTES + 1 - len(data)), len(data))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) != metadata[6] or len(data) > MAX_RECORD_BYTES:
            raise _Refused(ObservationReason.JOURNAL_INVALID)
        value = _json(bytes(data))
        return value, hashlib.sha256(data).hexdigest()

    def confirm(self, roots):
        self._check()
        for parent, name, child, metadata in self.directories:
            if _directory(os.fstat(child.fd)) != metadata or _directory(os.stat(name, dir_fd=parent.fd, follow_symlinks=False)) != metadata:
                raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
        for root in roots:
            _directory(os.fstat(root.fd), private=True)
        for root, name, child, metadata, empty, image in self.files:
            if _regular(os.fstat(child.fd), empty=empty, image=image) != metadata or _regular(os.stat(name, dir_fd=root.fd, follow_symlinks=False), empty=empty, image=image) != metadata:
                raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)

    def close(self):
        # A fork child may only retire copied descriptors, never LOCK_UN.
        _close_all(self.owners)

    def __del__(self):
        try:
            self.close()
        except BaseException:
            pass


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _Refused(ObservationReason.JOURNAL_INVALID)
            result[key] = value
        return result
    def invalid(_value):
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
        if type(value) is not dict or _canonical(value) != data:
            raise _Refused(ObservationReason.JOURNAL_INVALID)
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise _Refused(ObservationReason.JOURNAL_INVALID) from error


def _fields(value, fields):
    if type(value) is not dict or set(value) != fields:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    return value


def _integer(value, minimum=1, maximum=(1 << 63) - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    return value


def _hash(value):
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    return value


def _identity(value):
    if type(value) is not list or len(value) != 2:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    for number in value:
        _integer(number, 0)
    return value


def _event(event, previous, digest, sequence, state_id, slot_id):
    _fields(event, _EVENT_FIELDS)
    _integer(event["sequence"])
    kind = event["kind"]
    if event["schema"] != "trillionnium.desktop.durable-update-event.v1" or event["sequence"] != sequence or event["previous_sha256"] != digest or type(kind) is not str or kind not in _PHASES or event["phase"] != _PHASES[kind] or kind not in _NEXT[None if previous is None else previous["kind"]]:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    _integer(event["observed_unix"]); _hash(event["owner_id"])
    if previous and event["observed_unix"] < previous["observed_unix"] or event["production_activation_enabled"] is not False or event["bootloader_effect_performed"] is not False:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    config = _fields(event["configuration"], _CONFIG_FIELDS)
    _identity(config["state_root_identity"]); _identity(config["slot_root_identity"])
    _hash(config["current_image_sha256"])
    _integer(config["current_version"]); _integer(config["protected_rollback_floor"])
    if config["active_slot"] not in {"A", "B"} or config["protected_rollback_floor"] > config["current_version"] or config["state_root_identity"] != state_id or config["slot_root_identity"] != slot_id:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    if config["trust_policy_sha256"] is not None:
        _hash(config["trust_policy_sha256"])
    if previous and (_canonical(config) != _canonical(previous["configuration"]) or (kind != "owner_open" and event["owner_id"] != previous["owner_id"])):
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    operation = event["operation"]
    if kind in {"owner_open", "owner_clean"}:
        if operation is not None or event["stage_receipt"] is not None:
            raise _Refused(ObservationReason.JOURNAL_INVALID)
        return
    _fields(operation, _OP_FIELDS); _hash(operation["operation_id"])
    if operation["owner_id"] != event["owner_id"] or _integer(operation["ticket_sequence"]) != 1:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    admission = _fields(operation["signature_admission"], _ADMISSION_FIELDS)
    for key in ("public_key_sha256", "signature_sha256", "signing_preimage_sha256", "trust_policy_sha256"):
        _hash(admission[key])
    _integer(admission["minimum_version"]); _integer(admission["verified_unix"])
    if admission["verified_unix"] > event["observed_unix"]:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    try:
        manifest = recovery.UpdateManifest.parse(_canonical(operation["manifest"]), now_unix=admission["verified_unix"], active_slot=config["active_slot"], current_version=config["current_version"], current_image_sha256=config["current_image_sha256"])
        preimage = recovery.manifest_signing_bytes(_canonical(operation["manifest"]))
    except recovery.UpdateError as error:
        raise _Refused(ObservationReason.JOURNAL_INVALID) from error
    if admission["signer_id"] != manifest.signer_id or admission["signature_sha256"] != manifest.signature_sha256 or admission["trust_policy_sha256"] != config["trust_policy_sha256"] or manifest.rollback_floor < max(config["protected_rollback_floor"], admission["minimum_version"]) or admission["signing_preimage_sha256"] != hashlib.sha256(preimage).hexdigest():
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    if previous and kind != "manifest_verified" and _canonical(operation) != _canonical(previous["operation"]):
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    receipt = event["stage_receipt"]
    if kind in {"manifest_verified", "stage_intent"}:
        if receipt is not None:
            raise _Refused(ObservationReason.JOURNAL_INVALID)
    else:
        _fields(receipt, _STAGE_FIELDS)
        expected = {"target_slot": manifest.target_slot, "image_sha256": manifest.target_image_sha256, "image_bytes": manifest.target_image_bytes, "manifest_sha256": manifest.manifest_sha256, "signature_sha256": manifest.signature_sha256, "production_activation_enabled": False}
        if _canonical(receipt) != _canonical(expected):
            raise _Refused(ObservationReason.JOURNAL_INVALID)


def _history(reader, state, slots):
    names = reader.inventory(state, MAX_EVENTS + 2)
    events = sorted(name for name in names if _EVENT.fullmatch(name))
    if names != {".coordinator.lock", *events, *({_MARKER} if _MARKER in names else set())} or len(events) > MAX_EVENTS:
        raise _Refused(ObservationReason.JOURNAL_INVALID)
    state_id = list(_directory(os.fstat(state.fd))[:2])
    slot_id = list(_directory(os.fstat(slots.fd))[:2])
    previous, digest, owner_ids, records = None, _ZERO, set(), []
    for sequence, name in enumerate(events, 1):
        if name != f"update-event-{sequence:06d}.json":
            raise _Refused(ObservationReason.JOURNAL_INVALID)
        event, actual = reader.record(state, name)
        _event(event, previous, digest, sequence, state_id, slot_id)
        if event["kind"] == "owner_open":
            if event["owner_id"] in owner_ids:
                raise _Refused(ObservationReason.JOURNAL_INVALID)
            owner_ids.add(event["owner_id"])
        records.append((event, actual))
        previous, digest = event, actual
    marker = _MARKER in names
    if marker:
        value, _ = reader.record(state, _MARKER)
        _fields(value, _MARKER_FIELDS)
        count = _integer(value["history_count"], 0, MAX_EVENTS)
        _identity(value["state_root_identity"]); _identity(value["slot_root_identity"])
        _hash(value["last_event_sha256"])
        if value["operation_id"] is not None:
            _hash(value["operation_id"])
        if count > len(records):
            raise _Refused(ObservationReason.JOURNAL_INVALID)
        prefix = None if count == 0 else records[count - 1]
        operation = None if prefix is None or prefix[0]["operation"] is None else prefix[0]["operation"]["operation_id"]
        if value["schema"] != "trillionnium.desktop.durable-update-recovery.v1" or value["phase"] != "recovery_required" or type(value["reason"]) is not str or not 1 <= len(value["reason"]) <= 256 or value["production_activation_enabled"] is not False or value["bootloader_effect_performed"] is not False or value["state_root_identity"] != state_id or value["slot_root_identity"] != slot_id or value["last_event_sha256"] != (_ZERO if prefix is None else prefix[1]) or value["operation_id"] != operation:
            raise _Refused(ObservationReason.JOURNAL_INVALID)
    return names, records, marker


def _filesystem_type(fd):
    # Linux statfs starts with native signed long f_type. An oversized buffer
    # accommodates supported Linux ABIs; no structure is written to disk.
    library = ctypes.CDLL(None, use_errno=True)
    method = library.fstatfs
    method.argtypes, method.restype = [ctypes.c_int, ctypes.c_void_p], ctypes.c_int
    buffer = ctypes.create_string_buffer(512)
    if method(fd, buffer) != 0:
        raise _Refused(ObservationReason.KERNEL_UNAVAILABLE)
    return ctypes.c_long.from_buffer(buffer).value


def _proc_bytes(reader, path, limit):
    child = reader._open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    if _filesystem_type(child.fd) != 0x9FA0 or not stat.S_ISREG(os.fstat(child.fd).st_mode):
        raise _Refused(ObservationReason.KERNEL_UNAVAILABLE)
    data = bytearray()
    while len(data) <= limit:
        reader._check()
        chunk = os.read(child.fd, min(65536, limit + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
    if not data or len(data) > limit:
        raise _Refused(ObservationReason.KERNEL_UNAVAILABLE)
    return bytes(data)


def _mount_root(data, device):
    try:
        lines = data.decode("utf-8", errors="strict").splitlines()
        if not 1 <= len(lines) <= MAX_MOUNTS:
            raise ValueError()
        roots = []
        for line in lines:
            if len(line) > 16384:
                raise ValueError()
            before, after = line.split(" - ", 1)
            left, right = before.split(" "), after.split(" ")
            if len(left) < 6 or len(right) != 3 or not left[0].isdigit() or not left[1].isdigit():
                raise ValueError()
            if not re.fullmatch(r"(?:0|[1-9][0-9]*):(?:0|[1-9][0-9]*)", left[2]):
                raise ValueError()
            if left[4] == "/":
                major, minor = map(int, left[2].split(":"))
                if (major, minor) != device:
                    raise ValueError()
                roots.append({"mount_id": int(left[0]), "parent_mount_id": int(left[1]), "major": major, "minor": minor, "filesystem": right[0], "mount_source": right[1], "mount_options": left[5], "super_options": right[2]})
        if len(roots) != 1:
            raise ValueError()
        return roots[0]
    except (ValueError, UnicodeError) as error:
        raise _Refused(ObservationReason.KERNEL_UNAVAILABLE) from error


def _kernel(reader):
    reader._check()
    if sys.platform != "linux":
        raise _Refused(ObservationReason.KERNEL_UNAVAILABLE)
    # A procfs mount can expose a different PID namespace. Do not let numeric
    # getpid() accidentally name another process's namespace/mount table.
    if os.readlink("/proc/self") != str(reader.pid):
        raise _Refused(ObservationReason.KERNEL_UNAVAILABLE)
    namespace = reader._open(f"/proc/{reader.pid}/ns/mnt", os.O_RDONLY)
    if _filesystem_type(namespace.fd) != 0x6E736673:
        raise _Refused(ObservationReason.KERNEL_UNAVAILABLE)
    ns = os.fstat(namespace.fd)
    boot = _proc_bytes(reader, "/proc/sys/kernel/random/boot_id", 128)
    if _BOOT.fullmatch(boot) is None:
        raise _Refused(ObservationReason.KERNEL_UNAVAILABLE)
    root = reader._open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    identity = os.fstat(root.fd)
    mounts = _proc_bytes(reader, f"/proc/{reader.pid}/mountinfo", MAX_MOUNTINFO_BYTES)
    return {"boot_id": boot.decode("ascii").strip(), "mount_namespace_identity": [ns.st_dev, ns.st_ino],
        "root_device": [os.major(identity.st_dev), os.minor(identity.st_dev)], "root_inode": identity.st_ino,
        "mountinfo_sha256": hashlib.sha256(mounts).hexdigest(),
        "root_mount": _mount_root(mounts, (os.major(identity.st_dev), os.minor(identity.st_dev)))}


def _observation(status, reasons, details=None):
    public = {"schema": SCHEMA, "status": status.value, "reason_codes": [item.value for item in reasons],
        "signature_authority": "unavailable", "signed_boot_image_mapping": "unknown",
        "booted_image_verified": False, "production_activation_enabled": False,
        "bootloader_effect_performed": False, "continuation_authorized": False}
    private = _canonical({**public, "diagnostic": details})
    if len(private) + 1 > MAX_DIAGNOSTIC_BYTES:
        raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
    return BootObservation(status, tuple(reasons), private)


def inspect_pending_update(state_root: Path, slot_root: Path) -> BootObservation:
    """Measure fixed kernel sources and a complete locked read-only file scan.

    Existing leases are required. No store constructor, signature verifier,
    image hash, caller health assertion or continuation action is invoked.
    """
    reader = _Reader()
    try:
        before = _kernel(reader)
        state, slots = reader.root(state_root), reader.root(slot_root)
        state_id, slot_id = list(_directory(os.fstat(state.fd))[:2]), list(_directory(os.fstat(slots.fd))[:2])
        if state_id == slot_id:
            raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
        reader.lease(state); reader.lease(slots)
        names, history, marker = _history(reader, state, slots)
        slot_names = reader.inventory(slots, 3)
        if slot_names != {".coordinator.lock", "slot-A.img", "slot-B.img"}:
            raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
        slot_files = {}
        for slot in ("A", "B"):
            _, metadata = reader.file(slots, f"slot-{slot}.img", image=True)
            slot_files[slot] = {"device": metadata[0], "inode": metadata[1], "bytes": metadata[6], "mtime_ns": metadata[7], "ctime_ns": metadata[8], "content_verified": False}
        after = _kernel(reader)
        if before != after:
            raise _Refused(ObservationReason.KERNEL_CHANGED)
        reader.confirm((state, slots))
        if names != reader.inventory(state, MAX_EVENTS + 2) or slot_names != reader.inventory(slots, 3):
            raise _Refused(ObservationReason.CUSTODY_UNAVAILABLE)
        tail = None if not history else history[-1][0]
        reasons = [ObservationReason.SIGNATURE_UNAVAILABLE, ObservationReason.IMAGE_MAPPING_UNKNOWN]
        if marker:
            status = ObservationStatus.RECOVERY_REQUIRED
            reasons.insert(0, ObservationReason.RECOVERY_MARKER)
        elif tail is not None and tail["kind"] == "boot_policy_armed":
            status = ObservationStatus.PENDING_IDENTITY_UNKNOWN
        elif tail is not None and tail["kind"] != "owner_clean":
            status = ObservationStatus.RECOVERY_REQUIRED
            reasons.insert(0, ObservationReason.UNFINISHED_OWNER)
        else:
            status = ObservationStatus.NO_PENDING_UPDATE
        details = {"kernel": after, "state_root_identity": state_id, "slot_root_identity": slot_id,
            "history": {"record_count": len(history), "last_event_sha256": _ZERO if not history else history[-1][1],
                "last_kind": None if tail is None else tail["kind"], "recovery_marker": marker,
                "operation_id": None if tail is None or tail["operation"] is None else tail["operation"]["operation_id"],
                "structural_validation_only": True}, "slot_files": slot_files}
        return _observation(status, reasons, details)
    except _Refused as error:
        status = ObservationStatus.RECOVERY_REQUIRED if error.reason == ObservationReason.JOURNAL_INVALID else ObservationStatus.UNAVAILABLE
        return _observation(status, [error.reason, ObservationReason.SIGNATURE_UNAVAILABLE, ObservationReason.IMAGE_MAPPING_UNKNOWN])
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return _observation(ObservationStatus.UNAVAILABLE, [ObservationReason.CUSTODY_UNAVAILABLE, ObservationReason.SIGNATURE_UNAVAILABLE, ObservationReason.IMAGE_MAPPING_UNKNOWN])
    finally:
        reader.close()
