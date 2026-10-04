"""Private, durable signed-app lifecycle source API; no installed engine authority.

Only the concrete bundled admission owner supplies verified bundles and policy.
All records and content are retained. An interrupted owner session requires
external operator recovery; reopening never repairs or silently resumes it.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import sys
import threading
import zipfile
from dataclasses import dataclass
from functools import wraps
from pathlib import Path

# platform is also a stdlib module. Use one stable source-module identity rather
# than sys.path mutation or an unrelated similarly named Python package.
_MODULE = "hepta_trusted_apps_v1"
if _MODULE not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE, Path(__file__).with_name("trusted_apps.py"))
    if _spec is None or _spec.loader is None:
        raise RuntimeError("bundled admission source unavailable")
    trusted_apps = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE] = trusted_apps
    _spec.loader.exec_module(trusted_apps)
else:
    trusted_apps = sys.modules[_MODULE]

SCHEMA = "trillionnium.desktop.app-storage.v1"
MAX_EVENTS = 256
MAX_SESSIONS = 256
MAX_PARTITIONS = 64
MAX_FILES = 2048
MAX_STORE_BYTES = 128 * 1024 * 1024
MAX_RECORD_BYTES = 1024 * 1024
MAX_DATA_BYTES = 1024 * 1024
MAX_PARTITION_DATA_BYTES = 4 * 1024 * 1024
MAX_DATA_KEYS = 128
LEASE = ".app-storage.lock"
_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_FILE = re.compile(r"(?:owner-[0-9]{6}\.(?:open|clean|refused)\.json|event-[0-9]{6}\.(?:intent|commit)\.json|package-[0-9]{6}\.zip|data-[0-9]{6}\.bin)\Z", re.ASCII)
_SEAL = object()


class AppStorageError(ValueError):
    """Closed source refusal, with no untrusted payload in the diagnostic."""


class RecoveryRequired(AppStorageError):
    """Storage publication/custody is uncertain; history must be preserved."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _fields(value: object, keys: set[str]) -> dict:
    if type(value) is not dict or value.keys() != keys:
        raise AppStorageError("record fields differ from the closed schema")
    return value


def _integer(value: object, maximum: int, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise AppStorageError("integer outside bound")
    return value


def _id(value: object) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise AppStorageError("invalid principal or operation identifier")
    return value


def _origin(value: object) -> str:
    if type(value) is not str or not value.startswith("https://"):
        raise AppStorageError("origin must be exact synthetic HTTPS")
    host = value[8:]
    parts = host.split(".")
    if len(parts) != 5 or parts[2:] != ["apps", "hepta", "invalid"]:
        raise AppStorageError("origin must be exact synthetic HTTPS")
    trusted_apps._label(parts[0], "app_id")
    trusted_apps._label(parts[1], "publisher")
    return value


def _key(value: object) -> str:
    path = trusted_apps._asset_path(value)
    if "/" in path:
        raise AppStorageError("data key must be one canonical opaque segment")
    return path


def _partition(principal: str, origin: str) -> str:
    return hashlib.sha256(b"trillionnium.desktop.app-storage-partition.v1\0" + _canonical([principal, origin])).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AppStorageError("duplicate record member")
        result[key] = value
    return result


def _no_number(_):
    raise AppStorageError("noninteger record number")


def _decode(payload: bytes) -> dict:
    if not 0 < len(payload) <= MAX_RECORD_BYTES:
        raise AppStorageError("record exceeds bound")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_pairs,
                           parse_float=_no_number, parse_constant=_no_number)
        if type(value) is not dict or _canonical(value) != payload:
            raise AppStorageError("record is not canonical")
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise RecoveryRequired("invalid durable record") from error


def _owned(function):
    @wraps(function)
    def call(self, *args, **kwargs):
        self._on_owner()
        if self._busy:
            raise AppStorageError("storage owner is not reentrant")
        self._busy = True
        try:
            try:
                self._custody()
                return function(self, *args, **kwargs)
            except (OSError, RecoveryRequired) as error:
                self._poisoned = True
                raise RecoveryRequired("storage requires operator recovery") from error
            except trusted_apps.AppAdmissionError as error:
                raise AppStorageError("current signed-app policy or content refused") from error
            finally:
                self._busy = False
        except AppStorageError:
            raise
        except BaseException:
            # Include busy cleanup. A completed RETURN_VALUE trace callback is
            # outside this exception region: response loss then does not undo
            # the already durable single-use local commit.
            self._poisoned = True
            self._busy = False
            raise
    return call


@dataclass(frozen=True, init=False)
class InstalledApp:
    """Store-issued app incarnation. It authenticates no engine caller."""
    _issuer: object
    _partition: str
    _install: int
    _bundle: object
    principal: str
    origin: str
    version: str

    def __init__(self, *args, **kwargs):
        raise AppStorageError("installed handles are issued only by the store")


@dataclass(frozen=True, init=False)
class InstallTransaction:
    """Concrete store-owned plan, invalidated by any intervening event."""
    _issuer: object
    _sequence: int
    _bundle: object
    _archive: bytes
    _principal: str
    _policy: bytes

    def __init__(self, *args, **kwargs):
        raise AppStorageError("install transactions are prepared only by the store")


def _issued(cls, fields: dict):
    result = object.__new__(cls)
    for key, value in fields.items():
        object.__setattr__(result, key, value)
    return result


class AppStorage:
    """Exclusive private append-only store, owned by one process/thread.

    The directory must already exist, be mode 0700 and belong to the service UID.
    No default publisher root is installed. Private source artifacts and data do
    not replace native origin interception or an engine storage partition.
    """
    def __init__(self, root: os.PathLike | str, *, admission=None, shell_version="1.0.0"):
        if admission is None:
            admission = trusted_apps.TrustedAppAdmission(shell_version=shell_version)
        if type(admission) is not trusted_apps.TrustedAppAdmission:
            raise AppStorageError("the concrete bundled admission owner is required")
        admission._on_owner()
        self._admission = admission
        self._pid, self._thread = os.getpid(), threading.current_thread()
        self._issuer = object()
        self._busy = self._closed = self._poisoned = False
        self._chain = []
        self._lease = -1
        self._sequence = self._session = 0
        self._bytes = 0
        self._apps, self._data, self._operations = {}, {}, set()
        self._policy = None
        self._root = os.fspath(root)
        try:
            self._acquire()
            self._load()
            if self._session >= MAX_SESSIONS:
                raise AppStorageError("owner session capacity exhausted")
            self._session += 1
            self._publish(self._owner_name("open"), _canonical({
                "schema": SCHEMA, "session": self._session, "start_event": self._sequence,
            }))
        except BaseException:
            self._release()
            raise

    def _on_owner(self):
        if os.getpid() != self._pid or threading.current_thread() is not self._thread:
            raise AppStorageError("storage requires its creating process and thread")
        if self._closed or self._poisoned:
            raise RecoveryRequired("storage closed or recovery required")

    def _acquire(self):
        if (type(self._root) is not str or not self._root.startswith("/")
                or self._root == "/" or os.path.normpath(self._root) != self._root
                or any(part in ("", ".", "..") for part in self._root[1:].split("/"))):
            raise AppStorageError("root must be an absolute canonical private directory")
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self._chain.append(("/", fd, os.fstat(fd)))
        for part in self._root[1:].split("/"):
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            self._chain.append((part, fd, os.fstat(fd)))
        self._root_fd = fd
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
            raise AppStorageError("storage root is not private service-owned mode 0700")
        self._lease = os.open(LEASE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=fd)
        self._private_file(os.fstat(self._lease), 0)
        try:
            fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise AppStorageError("storage already has an owner") from error
        self._lease_info = os.fstat(self._lease)
        self._custody()
        os.fsync(self._lease)
        os.fsync(self._root_fd)

    @staticmethod
    def _same(left, right):
        return (left.st_dev, left.st_ino, left.st_mode, left.st_uid, left.st_gid) == (
            right.st_dev, right.st_ino, right.st_mode, right.st_uid, right.st_gid)

    @staticmethod
    def _private_file(info, maximum):
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid() or info.st_nlink != 1 or not 0 <= info.st_size <= maximum):
            raise RecoveryRequired("file custody or byte bound refused")

    def _custody(self):
        if not self._chain or self._lease < 0:
            raise RecoveryRequired("storage descriptors unavailable")
        # Reopen the complete absolute chain, not merely the retained parent.
        fresh = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            for index, (part, retained, expected) in enumerate(self._chain):
                if index:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fresh)
                    os.close(fresh)
                    fresh = child
                if not self._same(os.fstat(retained), expected) or not self._same(os.fstat(fresh), expected):
                    raise RecoveryRequired("root or ancestor identity changed")
            lease = os.fstat(self._lease)
            self._private_file(lease, 0)
            named = os.stat(LEASE, dir_fd=self._root_fd, follow_symlinks=False)
            if not self._same(lease, self._lease_info) or not self._same(named, lease):
                raise RecoveryRequired("owner lease replaced")
        finally:
            os.close(fresh)

    def _read(self, name, maximum):
        self._custody()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=self._root_fd)
        try:
            before = os.fstat(fd)
            self._private_file(before, maximum)
            chunks, length = [], 0
            while True:
                chunk = os.read(fd, min(65536, maximum + 1 - length))
                if not chunk:
                    break
                chunks.append(chunk)
                length += len(chunk)
                if length > maximum:
                    raise RecoveryRequired("file exceeds bound")
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            if (not self._same(before, after) or not self._same(after, named)
                    or before.st_nlink != after.st_nlink or after.st_nlink != named.st_nlink
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns) !=
                    (named.st_size, named.st_mtime_ns, named.st_ctime_ns) or length != after.st_size):
                raise RecoveryRequired("file changed during read")
            self._custody()
            return b"".join(chunks)
        finally:
            os.close(fd)

    def _publish(self, name: str, payload: bytes):
        if self._bytes + len(payload) > MAX_STORE_BYTES:
            raise AppStorageError("retained storage byte capacity exhausted")
        self._custody()
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self._root_fd)
        try:
            created = os.fstat(fd)
            self._private_file(created, 0)
            offset = 0
            while offset < len(payload):
                count = os.write(fd, payload[offset:])
                if count <= 0:
                    raise RecoveryRequired("partial publication")
                offset += count
            info = os.fstat(fd)
            self._private_file(info, len(payload))
            named = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            if not self._same(info, named) or not self._same(info, created) or info.st_size != len(payload):
                raise RecoveryRequired("publication name changed")
            os.fsync(fd)
            os.fsync(self._root_fd)
            self._custody()
            # Retain the writing descriptor across readback and both barriers.
            os.lseek(fd, 0, os.SEEK_SET)
            readback = bytearray()
            while len(readback) <= len(payload):
                block = os.read(fd, min(65536, len(payload) + 1 - len(readback)))
                if not block:
                    break
                readback.extend(block)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=self._root_fd, follow_symlinks=False)
            self._private_file(after, len(payload))
            if (bytes(readback) != payload or not self._same(info, after)
                    or not self._same(named, after) or named.st_nlink != 1
                    or (info.st_size, info.st_mtime_ns, info.st_ctime_ns) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                    or (named.st_size, named.st_mtime_ns, named.st_ctime_ns) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise RecoveryRequired("publication custody or readback changed")
            self._custody()
            self._bytes += len(payload)
        finally:
            os.close(fd)
        # Never unlink a candidate, history, content or failure artifact.

    def _owner_name(self, suffix):
        return f"owner-{self._session:06d}.{suffix}.json"

    @staticmethod
    def _event_name(sequence, suffix):
        return f"event-{sequence:06d}.{suffix}.json"

    def _load(self):
        names = set(os.listdir(self._root_fd))
        if len(names) > MAX_FILES or any(name != LEASE and _FILE.fullmatch(name) is None for name in names):
            raise RecoveryRequired("unrecognized or excess store contents")
        if any(name.endswith(".refused.json") for name in names):
            raise RecoveryRequired("a failed clean-close barrier requires operator recovery")
        self._bytes = 0
        for name in names - {LEASE}:
            self._bytes += os.stat(name, dir_fd=self._root_fd, follow_symlinks=False).st_size
        if self._bytes > MAX_STORE_BYTES:
            raise RecoveryRequired("retained storage exceeds capacity")
        remaining = names - {LEASE}
        sessions = []
        while f"owner-{len(sessions) + 1:06d}.open.json" in remaining:
            number = len(sessions) + 1
            opened_name, clean_name = f"owner-{number:06d}.open.json", f"owner-{number:06d}.clean.json"
            opened = _fields(_decode(self._read(opened_name, MAX_RECORD_BYTES)), {"schema", "session", "start_event"})
            if clean_name not in remaining:
                raise RecoveryRequired("an interrupted owner session is permanently unresolved")
            clean = _fields(_decode(self._read(clean_name, MAX_RECORD_BYTES)), {"schema", "session", "last_event"})
            if (opened["schema"] != SCHEMA or clean["schema"] != SCHEMA
                    or _integer(opened["session"], MAX_SESSIONS, 1) != number
                    or _integer(clean["session"], MAX_SESSIONS, 1) != number):
                raise RecoveryRequired("owner session records disagree")
            start = _integer(opened["start_event"], MAX_EVENTS)
            end = _integer(clean["last_event"], MAX_EVENTS)
            if start != (sessions[-1][1] if sessions else 0) or end < start:
                raise RecoveryRequired("owner event boundaries disagree")
            sessions.append((start, end))
            remaining -= {opened_name, clean_name}
        if len(sessions) > MAX_SESSIONS:
            raise RecoveryRequired("owner session count exceeds bound")
        sequence = 0
        while self._event_name(sequence + 1, "intent") in remaining:
            sequence += 1
            if sequence > MAX_EVENTS:
                raise RecoveryRequired("event count exceeds bound")
            intent_name, commit_name = self._event_name(sequence, "intent"), self._event_name(sequence, "commit")
            if commit_name not in remaining:
                raise RecoveryRequired("an incomplete transaction requires recovery")
            payload = self._read(intent_name, MAX_RECORD_BYTES)
            intent = _fields(_decode(payload), {"schema", "event"})
            commit = _fields(_decode(self._read(commit_name, MAX_RECORD_BYTES)), {"schema", "intent_sha256", "event"})
            if (intent["schema"] != SCHEMA or commit["schema"] != SCHEMA
                    or intent["event"] != commit["event"]
                    or commit["intent_sha256"] != hashlib.sha256(payload).hexdigest()):
                raise RecoveryRequired("transaction records disagree")
            event = intent["event"]
            expected_session = next((number for number, (start, end) in enumerate(sessions, 1)
                                     if start < sequence <= end), None)
            if type(event) is not dict or event.get("session") != expected_session:
                raise RecoveryRequired("event does not belong to its owner session")
            artifact = self._validate_event(event, sequence)
            if artifact:
                name, maximum, digest, length = artifact
                body = self._read(name, maximum)
                if len(body) != length or hashlib.sha256(body).hexdigest() != digest:
                    raise RecoveryRequired("immutable artifact disagrees with durable event")
                if event["kind"] == "install":
                    self._stored_package(body, event["app"])
                remaining.remove(name)
            self._apply(event)
            remaining -= {intent_name, commit_name}
        if remaining or sequence != (sessions[-1][1] if sessions else 0):
            raise RecoveryRequired("orphan records or owner boundary mismatch")
        self._sequence, self._session = sequence, len(sessions)

    def _policy_snapshot(self, now_unix):
        trusted_apps._integer(now_unix, "trusted now_unix")
        self._admission._on_owner()
        policy, pins = self._admission._state
        if policy is None or not policy.valid_from_unix <= now_unix < policy.valid_until_unix:
            raise AppStorageError("current operator policy unavailable or expired")
        pins = dict(pins)
        if self._policy is not None:
            for publisher, key_id, remembered in self._policy["pins"]:
                identity = publisher, key_id
                if identity in pins and pins[identity] != remembered:
                    raise AppStorageError("durable key ID cannot be rebound")
                pins[identity] = remembered
        return {
            "revision": policy.revision, "valid_from_unix": policy.valid_from_unix,
            "valid_until_unix": policy.valid_until_unix,
            "roots": [{"publisher": root.publisher, "key_id": root.key_id,
                       "public_key": root.public_key.hex(), "pin": root.public_key_sha256,
                       "valid_from_unix": root.valid_from_unix, "valid_until_unix": root.valid_until_unix}
                      for root in sorted(policy.roots, key=lambda item: (item.publisher, item.key_id))],
            "revoked": [list(item) for item in sorted(policy.revoked_keys)],
            "pins": [[publisher, key_id, pin] for (publisher, key_id), pin in sorted(pins.items())],
        }

    def _validate_policy(self, value):
        _fields(value, {"revision", "valid_from_unix", "valid_until_unix", "roots", "revoked", "pins"})
        if (type(value["roots"]) is not list or len(value["roots"]) > trusted_apps.MAX_POLICY_KEYS
                or type(value["revoked"]) is not list or len(value["revoked"]) > trusted_apps.MAX_POLICY_REVOCATIONS
                or type(value["pins"]) is not list or len(value["pins"]) > trusted_apps.MAX_SEEN_KEYS):
            raise AppStorageError("policy history exceeds bound")
        roots = []
        for record in value["roots"]:
            _fields(record, {"publisher", "key_id", "public_key", "pin", "valid_from_unix", "valid_until_unix"})
            if type(record["public_key"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", record["public_key"]):
                raise AppStorageError("invalid historical key encoding")
            roots.append(trusted_apps.PublisherTrustRoot(record["publisher"], record["key_id"],
                bytes.fromhex(record["public_key"]), record["pin"], record["valid_from_unix"], record["valid_until_unix"]))
        revoked = []
        for identity in value["revoked"]:
            if type(identity) is not list or len(identity) != 2:
                raise AppStorageError("invalid historical revocation")
            revoked.append(tuple(identity))
        trusted_apps.PublisherTrustPolicy(value["revision"], value["valid_from_unix"], value["valid_until_unix"], tuple(roots), tuple(revoked))
        pins = {}
        for identity in value["pins"]:
            if type(identity) is not list or len(identity) != 3:
                raise AppStorageError("invalid historical key pin")
            publisher, key_id, pin = identity
            trusted_apps._label(publisher, "publisher")
            trusted_apps._key_id(key_id)
            trusted_apps._digest(pin)
            if (publisher, key_id) in pins:
                raise AppStorageError("duplicate historical key pin")
            pins[publisher, key_id] = pin
        if any(pins.get((root.publisher, root.key_id)) != root.public_key_sha256 for root in roots):
            raise AppStorageError("historical root pin not remembered")
        if self._policy is not None:
            previous = self._policy
            if value["revision"] < previous["revision"] or (value["revision"] == previous["revision"] and value != previous):
                raise AppStorageError("durable policy revision replay")
            if not set(map(tuple, previous["revoked"])) <= set(map(tuple, value["revoked"])):
                raise AppStorageError("durable revocation removed")
            if any(pins.get((pub, key)) != pin for pub, key, pin in previous["pins"]):
                raise AppStorageError("durable key pin removed or rebound")

    def _sync_policy(self, now_unix):
        policy = self._policy_snapshot(now_unix)
        self._validate_policy(policy)
        if policy != self._policy:
            try:
                self._append({"kind": "policy", "operation_id": f"policy:{policy['revision']}", "policy": policy})
            except BaseException:
                # Even a pre-intent quota refusal cannot discard an observed new
                # valid revocation snapshot and permit old policy on restart.
                self._poisoned = True
                raise
        return policy

    @_owned
    def synchronize_policy(self, *, now_unix: int):
        """Persist the actual admission owner's policy floor, pins and revocations."""
        self._sync_policy(now_unix)

    @staticmethod
    def _metadata(bundle, archive):
        return {"publisher": bundle.publisher, "app_id": bundle.app_id, "origin_host": bundle.origin_host,
                "version": bundle.version, "entrypoint": bundle.entrypoint,
                "manifest_sha256": bundle.manifest_sha256, "content_root_sha256": bundle.content_root_sha256,
                "archive_sha256": hashlib.sha256(archive).hexdigest(), "data_schema_version": bundle.data_schema_version}

    def _validate_metadata(self, value):
        _fields(value, {"publisher", "app_id", "origin_host", "version", "entrypoint", "manifest_sha256",
                        "content_root_sha256", "archive_sha256", "data_schema_version"})
        trusted_apps._label(value["publisher"], "publisher")
        trusted_apps._label(value["app_id"], "app_id")
        if value["origin_host"] != f"{value['app_id']}.{value['publisher']}.apps.hepta.invalid":
            raise AppStorageError("historical origin binding invalid")
        trusted_apps._version(value["version"], stable=True)
        if not trusted_apps._asset_path(value["entrypoint"]).endswith(".html"):
            raise AppStorageError("historical entrypoint invalid")
        for field in ("manifest_sha256", "content_root_sha256", "archive_sha256"):
            trusted_apps._digest(value[field])
        if value["data_schema_version"] is not None:
            trusted_apps._integer(value["data_schema_version"], "data_schema_version")
            if value["data_schema_version"] < 1:
                raise AppStorageError("historical schema invalid")

    @staticmethod
    def _stored_package(archive, metadata):
        # Historical keys may now be revoked. This consistency check grants no
        # execution authority; open_app still redoes current real verification.
        payload, assets = trusted_apps._zip_contents(archive)
        manifest = trusted_apps._manifest(payload)
        expected = {key: manifest[key] for key in ("publisher", "app_id", "origin_host", "version", "entrypoint", "content_root_sha256")}
        expected.update({"data_schema_version": manifest.get("data_schema_version"),
                         "manifest_sha256": hashlib.sha256(payload).hexdigest(),
                         "archive_sha256": hashlib.sha256(archive).hexdigest()})
        if (expected != metadata or manifest["entrypoint"] not in assets
                or trusted_apps.content_root_sha256(assets) != manifest["content_root_sha256"]):
            raise RecoveryRequired("historical signed metadata or complete assets disagree")

    def _validate_event(self, event, sequence):
        common = {"sequence", "session", "kind", "operation_id", "policy"}
        if type(event) is not dict or event.get("kind") not in {"policy", "install", "uninstall", "put", "delete"}:
            raise AppStorageError("invalid historical event kind")
        kind = event["kind"]
        extra = set() if kind == "policy" else {"principal", "origin"}
        if kind == "install":
            extra |= {"app", "archive_size"}
        if kind in {"put", "delete", "uninstall"}:
            extra |= {"install"}
        if kind in {"put", "delete"}:
            extra |= {"key"}
        if kind == "put":
            extra |= {"size", "sha256"}
        _fields(event, common | extra)
        if _integer(event["sequence"], MAX_EVENTS, 1) != sequence:
            raise AppStorageError("event sequence gap")
        _integer(event["session"], MAX_SESSIONS, 1)
        operation = _id(event["operation_id"])
        if operation in self._operations:
            raise AppStorageError("operation identifier replay")
        self._validate_policy(event["policy"])
        if kind == "policy":
            if operation != f"policy:{event['policy']['revision']}" or event["policy"] == self._policy:
                raise AppStorageError("invalid policy synchronization event")
            return None
        if operation.startswith("policy:"):
            raise AppStorageError("reserved operation identifier")
        principal, origin = _id(event["principal"]), _origin(event["origin"])
        partition = _partition(principal, origin)
        previous = self._apps.get(partition)
        if kind == "install":
            self._validate_metadata(event["app"])
            if origin != f"https://{event['app']['origin_host']}":
                raise AppStorageError("partition and manifest origin disagree")
            if previous:
                self._check_upgrade(previous["app"], event["app"])
            elif len(self._apps) >= MAX_PARTITIONS:
                raise AppStorageError("partition capacity exhausted")
            length = _integer(event["archive_size"], trusted_apps.MAX_ARCHIVE_BYTES, 1)
            return f"package-{sequence:06d}.zip", trusted_apps.MAX_ARCHIVE_BYTES, event["app"]["archive_sha256"], length
        if previous is None or not previous["active"] or _integer(event["install"], MAX_EVENTS, 1) != previous["install"]:
            raise AppStorageError("event lacks the current installed incarnation")
        if kind in {"put", "delete"}:
            key = _key(event["key"])
            entries = self._data.get(partition, {})
            if kind == "delete" and (key not in entries or entries[key] is None):
                raise AppStorageError("data deletion replay or missing key")
            if kind == "put":
                size = _integer(event["size"], MAX_DATA_BYTES)
                trusted_apps._digest(event["sha256"])
                if key not in entries and len(entries) >= MAX_DATA_KEYS:
                    raise AppStorageError("data key capacity exhausted")
                used = sum(record["size"] for name, record in entries.items() if record and name != key)
                if used + size > MAX_PARTITION_DATA_BYTES:
                    raise AppStorageError("partition data quota exhausted")
                return f"data-{sequence:06d}.bin", MAX_DATA_BYTES, event["sha256"], size
        return None

    @staticmethod
    def _check_upgrade(previous, current):
        if trusted_apps._version(current["version"], stable=True) <= trusted_apps._version(previous["version"], stable=True):
            raise AppStorageError("version replay or downgrade refused")
        if current["data_schema_version"] != previous["data_schema_version"]:
            raise AppStorageError("data migration is unsupported; schema must remain identical")

    def _apply(self, event):
        self._policy = event["policy"]
        self._operations.add(event["operation_id"])
        if event["kind"] == "policy":
            return
        partition = _partition(event["principal"], event["origin"])
        if event["kind"] == "install":
            self._apps[partition] = {"principal": event["principal"], "origin": event["origin"],
                                     "app": event["app"], "install": event["sequence"], "active": True,
                                     "archive_size": event["archive_size"]}
        elif event["kind"] == "uninstall":
            self._apps[partition]["active"] = False
        else:
            self._data.setdefault(partition, {})[event["key"]] = event if event["kind"] == "put" else None

    def _append(self, data, artifact=None, final_check=None):
        if self._sequence >= MAX_EVENTS:
            raise AppStorageError("event capacity exhausted")
        event = {"sequence": self._sequence + 1, "session": self._session, **data}
        descriptor = self._validate_event(event, self._sequence + 1)
        intent = _canonical({"schema": SCHEMA, "event": event})
        commit = _canonical({"schema": SCHEMA, "intent_sha256": hashlib.sha256(intent).hexdigest(), "event": event})
        if len(intent) > MAX_RECORD_BYTES or len(commit) > MAX_RECORD_BYTES:
            raise AppStorageError("canonical policy/event record exceeds byte bound")
        expected = len(intent) + len(commit) + (len(artifact) if artifact is not None else 0)
        # Preserve room for a normal clean receipt when a capacity refusal occurs.
        if self._bytes + expected + MAX_RECORD_BYTES > MAX_STORE_BYTES:
            raise AppStorageError("retained storage byte capacity exhausted")
        if (descriptor is None) != (artifact is None):
            raise AppStorageError("internal artifact binding invalid")
        try:
            self._publish(self._event_name(event["sequence"], "intent"), intent)
            if descriptor:
                name, _, digest, length = descriptor
                if type(artifact) is not bytes or len(artifact) != length or hashlib.sha256(artifact).hexdigest() != digest:
                    raise RecoveryRequired("internal artifact bytes disagree")
                self._publish(name, artifact)
            if final_check:
                final_check()
            self._publish(self._event_name(event["sequence"], "commit"), commit)
            if final_check:
                final_check()
            self._apply(event)
            self._sequence = event["sequence"]
            self._return_commit()
        except BaseException:
            self._poisoned = True
            raise

    def _return_commit(self):
        """Named interruption boundary after durable publication, before return."""

    def _valid_bundle(self, bundle, now_unix):
        # This public owner call rejects foreign/forged bundles and current
        # revocation before private immutable bundle fields are inspected.
        self._admission.asset_response(bundle, bundle.entrypoint_url if type(bundle) is trusted_apps.VerifiedAppBundle else "", now_unix=now_unix)
        trusted_apps._version(bundle.version, stable=True)

    def _archive(self, bundle, now_unix):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as writer:
            members = [(trusted_apps.MANIFEST_PATH, bundle._manifest)]
            for path in bundle.asset_paths:
                response = self._admission.asset_response(bundle, f"https://{bundle.origin_host}/{path}", now_unix=now_unix)
                members.append((path, response.body))
            for name, payload in members:
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                writer.writestr(info, payload)
                if stream.tell() > trusted_apps.MAX_ARCHIVE_BYTES:
                    raise AppStorageError("canonical stored bundle exceeds archive bound")
        archive = stream.getvalue()
        if len(archive) > trusted_apps.MAX_ARCHIVE_BYTES:
            raise AppStorageError("canonical stored bundle exceeds archive bound")
        return archive

    @_owned
    def prepare_install(self, principal: str, bundle, *, now_unix: int) -> InstallTransaction:
        """Revalidate an owner-issued bundle and prepare an exact local transaction."""
        principal = _id(principal)
        if (type(bundle) is not trusted_apps.VerifiedAppBundle
                or getattr(bundle, "_issuer", None) is not self._admission._issuer):
            raise AppStorageError("foreign admission bundle")
        policy = self._sync_policy(now_unix)
        self._valid_bundle(bundle, now_unix)
        archive = self._archive(bundle, now_unix)
        metadata = self._metadata(bundle, archive)
        previous = self._apps.get(_partition(principal, f"https://{bundle.origin_host}"))
        if previous:
            self._check_upgrade(previous["app"], metadata)
        return _issued(InstallTransaction, {"_issuer": self._issuer, "_sequence": self._sequence,
                       "_bundle": bundle, "_archive": archive, "_principal": principal,
                       "_policy": _canonical(policy)})

    @_owned
    def commit_install(self, transaction: InstallTransaction, *, operation_id: str, now_unix: int) -> InstalledApp:
        """Single-use plan; no caller approval boolean, migration hook or digest."""
        if type(transaction) is not InstallTransaction or transaction._issuer is not self._issuer:
            raise AppStorageError("foreign install transaction")
        operation_id = _id(operation_id)
        if operation_id.startswith("policy:"):
            raise AppStorageError("reserved operation identifier")
        bundle = transaction._bundle
        policy = self._sync_policy(now_unix)
        self._valid_bundle(bundle, now_unix)
        if transaction._sequence != self._sequence or transaction._policy != _canonical(policy):
            raise AppStorageError("stale install transaction")
        origin = f"https://{bundle.origin_host}"
        metadata = self._metadata(bundle, transaction._archive)
        package = f"package-{self._sequence + 1:06d}.zip"
        def final_check():
            self._valid_bundle(bundle, now_unix)
            if _canonical(self._policy_snapshot(now_unix)) != transaction._policy:
                raise RecoveryRequired("operator policy changed during publication")
            admitted = self._admission.admit_bundle_file(Path(self._root) / package, now_unix=now_unix)
            persisted = self._read(package, trusted_apps.MAX_ARCHIVE_BYTES)
            if (persisted != transaction._archive or admitted.archive_sha256 != metadata["archive_sha256"]
                    or self._metadata(admitted, persisted) != metadata):
                raise RecoveryRequired("published bundle differs from verified transaction")
        self._append({"kind": "install", "operation_id": operation_id, "policy": policy,
                      "principal": transaction._principal, "origin": origin, "app": metadata,
                      "archive_size": len(transaction._archive)}, transaction._archive, final_check)
        return self._handle(self._apps[_partition(transaction._principal, origin)], bundle)

    def _handle(self, state, bundle):
        return _issued(InstalledApp, {"_issuer": self._issuer, "_partition": _partition(state["principal"], state["origin"]),
                       "_install": state["install"], "_bundle": bundle, "principal": state["principal"],
                       "origin": state["origin"], "version": state["app"]["version"]})

    def _current(self, handle, now_unix):
        if type(handle) is not InstalledApp or handle._issuer is not self._issuer:
            raise AppStorageError("foreign installed app handle")
        state = self._apps.get(handle._partition)
        if state is None or not state["active"] or state["install"] != handle._install:
            raise AppStorageError("installed incarnation is no longer active")
        self._sync_policy(now_unix)
        self._valid_bundle(handle._bundle, now_unix)
        body = self._read(f"package-{state['install']:06d}.zip", trusted_apps.MAX_ARCHIVE_BYTES)
        if hashlib.sha256(body).hexdigest() != state["app"]["archive_sha256"] or len(body) != state["archive_size"]:
            raise RecoveryRequired("installed artifact was substituted")
        return state

    @_owned
    def open_app(self, principal: str, origin: str, *, now_unix: int) -> InstalledApp:
        """Read the active stored archive through real offline admission again."""
        principal, origin = _id(principal), _origin(origin)
        self._sync_policy(now_unix)
        state = self._apps.get(_partition(principal, origin))
        if state is None or not state["active"]:
            raise AppStorageError("partition has no active installed app")
        name = f"package-{state['install']:06d}.zip"
        archive = self._read(name, trusted_apps.MAX_ARCHIVE_BYTES)
        if hashlib.sha256(archive).hexdigest() != state["app"]["archive_sha256"] or len(archive) != state["archive_size"]:
            raise RecoveryRequired("stored bundle differs from installation")
        bundle = self._admission.admit_bundle_file(Path(self._root) / name, now_unix=now_unix)
        self._custody()
        if (bundle.archive_sha256 != state["app"]["archive_sha256"]
                or self._read(name, trusted_apps.MAX_ARCHIVE_BYTES) != archive
                or self._metadata(bundle, archive) != state["app"]):
            raise RecoveryRequired("admitted bundle differs from installation")
        return self._handle(state, bundle)

    @_owned
    def asset_response(self, handle: InstalledApp, url: str, *, now_unix: int):
        """Local response from the active exact partition and current policy."""
        self._current(handle, now_unix)
        response = self._admission.asset_response(handle._bundle, url, now_unix=now_unix)
        self._custody()
        self._sync_policy(now_unix)
        self._final_policy(handle, now_unix, self._policy)
        return response

    def _event_for(self, handle, kind, operation_id, now_unix):
        state = self._current(handle, now_unix)
        operation_id = _id(operation_id)
        if operation_id.startswith("policy:"):
            raise AppStorageError("reserved operation identifier")
        return {"kind": kind, "operation_id": operation_id, "policy": self._policy,
                "principal": state["principal"], "origin": state["origin"], "install": state["install"]}

    def _final_policy(self, handle, now_unix, policy):
        self._valid_bundle(handle._bundle, now_unix)
        if self._policy_snapshot(now_unix) != policy:
            raise RecoveryRequired("operator policy changed during publication")

    @_owned
    def uninstall(self, handle: InstalledApp, *, operation_id: str, now_unix: int):
        """Durable tombstone; preserve version floor, assets and data history."""
        event = self._event_for(handle, "uninstall", operation_id, now_unix)
        self._append(event, final_check=lambda: self._final_policy(handle, now_unix, event["policy"]))

    @_owned
    def put_data(self, handle: InstalledApp, key: str, payload: bytes, *, operation_id: str, now_unix: int):
        """Publish immutable opaque bytes; logical replacement retains old bytes."""
        key = _key(key)
        if type(payload) is not bytes or len(payload) > MAX_DATA_BYTES:
            raise AppStorageError("data value exceeds immutable byte bound")
        event = self._event_for(handle, "put", operation_id, now_unix)
        event.update({"key": key, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        self._append(event, payload, lambda: self._final_policy(handle, now_unix, event["policy"]))

    @_owned
    def read_data(self, handle: InstalledApp, key: str, *, now_unix: int) -> bytes:
        key = _key(key)
        self._current(handle, now_unix)
        record = self._data.get(handle._partition, {}).get(key)
        if record is None:
            raise AppStorageError("data key absent or tombstoned")
        body = self._read(f"data-{record['sequence']:06d}.bin", MAX_DATA_BYTES)
        if len(body) != record["size"] or hashlib.sha256(body).hexdigest() != record["sha256"]:
            raise RecoveryRequired("app data artifact changed")
        self._final_policy(handle, now_unix, self._policy)
        return body

    @_owned
    def delete_data(self, handle: InstalledApp, key: str, *, operation_id: str, now_unix: int):
        event = self._event_for(handle, "delete", operation_id, now_unix)
        event["key"] = _key(key)
        self._append(event, final_check=lambda: self._final_policy(handle, now_unix, event["policy"]))

    def close(self):
        """Release owner; clean receipt only after successful effects and custody.

        A poisoned owner releases descriptors without resolving its durable open
        record. A copied child can close its own FDs but cannot unlock the parent.
        """
        if self._closed:
            return
        inherited = os.getpid() != self._pid
        if not inherited and threading.current_thread() is not self._thread:
            raise AppStorageError("close requires the creating thread")
        if not inherited and self._busy:
            raise AppStorageError("cannot close during a storage operation")
        try:
            if not inherited and not self._poisoned:
                self._custody()
                self._publish(self._owner_name("clean"), _canonical({
                    "schema": SCHEMA, "session": self._session, "last_event": self._sequence,
                }))
        except BaseException:
            self._poisoned = True
            # A clean candidate may exist even when its final barrier failed.
            # Preserve an explicit refusal artifact too, never delete candidates.
            # Physical failure preventing even marker creation is not solvable
            # by this source store and requires external storage/rollback custody.
            try:
                if not inherited:
                    self._publish(self._owner_name("refused"), _canonical({"schema": SCHEMA, "session": self._session}))
            except BaseException:
                pass
            raise
        finally:
            self._closed = True
            self._release()

    def _release(self):
        # Closing the inherited flock description never issues LOCK_UN, which
        # would unlock the original owner's still-live description after fork.
        # Detach ALL ownership before any close syscall: a post-close interrupt
        # may occur after the kernel has reused that integer for an unrelated FD.
        # Cleanup must never retry a stale number, including through __del__.
        lease, chain = self._lease, self._chain
        self._lease, self._chain, self._root_fd = -1, [], -1
        descriptors = ([lease] if lease >= 0 else []) + [fd for _, fd, _ in reversed(chain)]
        first_error = None
        for fd in descriptors:
            try:
                os.close(fd)
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def __del__(self):
        # GC is descriptor cleanup, never a successful lifecycle/clean receipt.
        # It can run on another thread or after fork and must only close this
        # process's own descriptor copies without authority checks or LOCK_UN.
        try:
            if hasattr(self, "_chain"):
                self._closed = True
                self._release()
        except BaseException:
            pass  # During interpreter shutdown the OS closes remaining copies.
