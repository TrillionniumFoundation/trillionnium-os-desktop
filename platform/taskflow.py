"""Typed TaskFlow admission and durable, single-use capability enforcement.

Externally provisioned issuer roots and a private consumption store are required
before dispatch. This source API creates no approval UI, signing key, native
effect adapter, receipt integration, network authority or production activation.
Untrusted proposals and permits never configure either trust roots or storage.
"""
from __future__ import annotations

import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.parse import urlsplit

PROPOSAL_SCHEMA = "trillionnium.desktop.taskflow-proposal.v1"
PERMIT_SCHEMA = "trillionnium.desktop.capability-permit.v1"
CONSUMPTION_SCHEMA = "trillionnium.desktop.taskflow-consumption.v1"
RESERVATION_SCHEMA = "trillionnium.desktop.taskflow-reservation.v1"
PROPOSAL_DOMAIN = b"trillionnium.desktop.taskflow-proposal-digest.v1\x00"
PERMIT_DOMAIN = b"trillionnium.desktop.capability-permit-signature.v1\x00"
OPENSSL = "/usr/bin/openssl"
OPENSSL_ENV = {"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null", "LC_ALL": "C"}
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
MAX_WIRE_BYTES = 32 * 1024
MAX_HISTORY = 1024
MAX_TASK_RESERVATIONS = 1024
MAX_ROOTS = 32
MAX_REVOCATIONS = 1024
MAX_TASKS = 64
MAX_TASK_ACTIONS = 32
MAX_TASK_BUDGET_MS = 60 * 60 * 1000
MAX_ACTION_BUDGET_MS = 20 * 1000
MAX_PERMIT_LIFETIME_MS = 5 * 60 * 1000
MAX_INTEGER = (1 << 63) - 1
_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SEAL = object()


class TaskFlowError(ValueError):
    """Bounded redacted refusal. No page payload or process identity is logged."""


class PermitRefused(TaskFlowError):
    pass


class ReplayRefused(TaskFlowError):
    pass


class RecoveryRequired(TaskFlowError):
    pass


class DeadlineExceeded(TaskFlowError):
    pass


class Cancelled(TaskFlowError):
    pass


def _id(value: object) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise TaskFlowError("identifier is invalid")
    return value


def _hash(value: object) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise TaskFlowError("digest is invalid")
    return value


def _integer(value: object, maximum: int = MAX_INTEGER, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TaskFlowError("integer is outside its bound")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _fields(value: object, fields: set[str]) -> dict:
    if type(value) is not dict or value.keys() != fields:
        raise TaskFlowError("object fields differ from the closed schema")
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise TaskFlowError("duplicate JSON member")
        result[key] = value
    return result


def _reject_number(_: str) -> object:
    raise TaskFlowError("noninteger JSON number is unsupported")


def _decode(payload: bytes) -> dict:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_WIRE_BYTES:
        raise TaskFlowError("wire input is empty or over limit")
    # A bounded shallow grammar also prevents recursive parser resource abuse.
    depth = 0
    quoted = escaped = False
    for byte in payload:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 8:
                raise TaskFlowError("JSON nesting exceeds the bound")
        elif byte in (93, 125):
            depth -= 1
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_float=_reject_number, parse_constant=_reject_number)
        if type(value) is not dict:
            raise TaskFlowError("wire input must be an object")
        # Reject unpaired surrogates and other non-UTF8 canonical representations.
        _canonical(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as error:
        raise TaskFlowError("wire JSON is invalid") from error


def _origin(value: object) -> str:
    if type(value) is not str or len(value) > 253 or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise TaskFlowError("origin is invalid")
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
    except ValueError as error:
        raise TaskFlowError("origin is invalid") from error
    if parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None:
        raise TaskFlowError("origin must be exact credential-free HTTPS")
    if parsed.path or parsed.query or parsed.fragment or "\\" in value or parsed.netloc != parsed.netloc.lower():
        raise TaskFlowError("origin must be canonical and contain no path")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label, re.ASCII) for label in host.split(".")):
        raise TaskFlowError("origin hostname is invalid")
    if (port is not None and not 1 <= port <= 65535) or port == 443:
        raise TaskFlowError("origin port is not canonical")
    expected = f"{parsed.scheme}://{host}" + (f":{port}" if port is not None else "")
    if value != expected:
        raise TaskFlowError("origin spelling is not canonical")
    return value


@dataclass(frozen=True)
class CurrentBinding:
    """Trusted owner snapshot, supplied independently of page/model JSON."""
    principal_id: str
    session_id: str
    session_generation: int
    origin: str
    resource_kind: str
    resource_target: str
    document_generation: int
    semantic_snapshot_revision: int
    mutation_epoch: int

    def __post_init__(self) -> None:
        _id(self.principal_id); _id(self.session_id)
        _integer(self.session_generation, minimum=1); _origin(self.origin)
        if type(self.resource_kind) is not str or self.resource_kind not in {"page", "semantic_node", "navigation", "extraction_schema"}:
            raise TaskFlowError("native resource kind is unsupported")
        _id(self.resource_target); _integer(self.document_generation, minimum=1)
        _integer(self.semantic_snapshot_revision); _integer(self.mutation_epoch)

    def resource(self) -> dict:
        return {"kind": self.resource_kind, "target": self.resource_target, "document_generation": self.document_generation,
                "semantic_snapshot_revision": self.semantic_snapshot_revision, "mutation_epoch": self.mutation_epoch}


@dataclass(frozen=True)
class TaskPolicy:
    task_id: str
    binding: CurrentBinding
    audience: str
    policy_revision: str
    max_actions: int = 1
    task_budget_ms: int = 60_000
    max_action_budget_ms: int = MAX_ACTION_BUDGET_MS

    def __post_init__(self) -> None:
        _id(self.task_id); _id(self.audience); _id(self.policy_revision)
        if type(self.binding) is not CurrentBinding:
            raise TaskFlowError("task requires a trusted owner binding")
        _integer(self.max_actions, MAX_TASK_ACTIONS, 1)
        _integer(self.task_budget_ms, MAX_TASK_BUDGET_MS, 1)
        _integer(self.max_action_budget_ms, MAX_ACTION_BUDGET_MS, 1)


PROPOSAL_FIELDS = {"schema", "task_id", "action_id", "principal_id", "audience", "policy_revision",
                   "session_id", "session_generation", "origin", "operation", "resource", "arguments", "action_budget_ms"}
TARGET_FIELDS = {"kind", "target", "document_generation", "semantic_snapshot_revision", "mutation_epoch"}
RESOURCE_FIELDS = {"task_id", "action_id", "session_id", "session_generation", "origin", "proposal_sha256",
                   "target", "arguments_sha256", "action_budget_ms"}
PERMIT_FIELDS = {"schema", "permit_id", "issuer", "subject", "audience", "operation", "resource",
                 "issued_unix_ms", "expires_unix_ms", "nonce", "policy_revision", "signature"}
OPERATIONS = {"page.observe": "page", "page.act": "semantic_node", "page.navigate": "navigation", "page.extract": "extraction_schema"}


def _target(value: object) -> dict:
    target = _fields(value, TARGET_FIELDS)
    if type(target["kind"]) is not str or target["kind"] not in set(OPERATIONS.values()):
        raise TaskFlowError("unsupported resource kind")
    _id(target["target"])
    _integer(target["document_generation"], minimum=1)
    _integer(target["semantic_snapshot_revision"])
    _integer(target["mutation_epoch"])
    return target


def _proposal(payload: bytes) -> dict:
    value = _fields(_decode(payload), PROPOSAL_FIELDS)
    if value["schema"] != PROPOSAL_SCHEMA:
        raise TaskFlowError("proposal schema is unsupported")
    for name in ("task_id", "action_id", "principal_id", "audience", "policy_revision", "session_id"):
        _id(value[name])
    _integer(value["session_generation"], minimum=1); _origin(value["origin"])
    _integer(value["action_budget_ms"], MAX_ACTION_BUDGET_MS, 1)
    operation = value["operation"]
    if type(operation) is not str or operation not in OPERATIONS:
        raise TaskFlowError("typed operation is unsupported")
    target = _target(value["resource"])
    if target["kind"] != OPERATIONS[operation]:
        raise TaskFlowError("resource kind differs from typed operation")
    arguments = value["arguments"]
    if operation == "page.observe":
        if _fields(arguments, {"mode"})["mode"] != "semantic":
            raise TaskFlowError("observation mode is unsupported")
    elif operation == "page.act":
        if _fields(arguments, {"action"})["action"] != "click":
            raise TaskFlowError("native semantic action is unsupported")
    elif operation == "page.extract":
        if _id(_fields(arguments, {"schema_id"})["schema_id"]) != target["target"]:
            raise TaskFlowError("extraction target differs from typed schema")
    else:
        url = _fields(arguments, {"url"})["url"]
        if type(url) is not str or len(url.encode("utf-8")) > 4096 or any(ord(char) <= 32 or ord(char) == 127 for char in url):
            raise TaskFlowError("navigation argument is invalid")
        try:
            parsed = urlsplit(url)
            authority = parsed.netloc
            if not url.startswith(value["origin"] + "/") or f"{parsed.scheme}://{authority}" != value["origin"] or parsed.fragment:
                raise TaskFlowError("navigation is outside the exact proposal origin")
        except ValueError as error:
            raise TaskFlowError("navigation URL is invalid") from error
    return value


def proposal_sha256(payload: bytes) -> str:
    return hashlib.sha256(PROPOSAL_DOMAIN + _canonical(_proposal(payload))).hexdigest()


def _signature(value: object) -> bytes:
    if type(value) is not str or len(value) != 88:
        raise PermitRefused("signature must be canonical base64 of 64 bytes")
    try:
        signature = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise PermitRefused("signature encoding is invalid") from error
    if len(signature) != 64 or base64.b64encode(signature).decode("ascii") != value:
        raise PermitRefused("signature encoding is noncanonical")
    return signature


def _permit(payload: bytes) -> dict:
    value = _fields(_decode(payload), PERMIT_FIELDS)
    if value["schema"] != PERMIT_SCHEMA:
        raise PermitRefused("permit schema is unsupported")
    for name in ("permit_id", "issuer", "subject", "audience", "policy_revision"):
        _id(value[name])
    if type(value["operation"]) is not str or value["operation"] not in OPERATIONS:
        raise PermitRefused("permit operation is unsupported")
    _hash(value["nonce"])
    issued = _integer(value["issued_unix_ms"]); expires = _integer(value["expires_unix_ms"])
    if not issued < expires <= issued + MAX_PERMIT_LIFETIME_MS:
        raise PermitRefused("permit lifetime is invalid")
    resource = _fields(value["resource"], RESOURCE_FIELDS)
    for name in ("task_id", "action_id", "session_id"):
        _id(resource[name])
    _integer(resource["session_generation"], minimum=1); _origin(resource["origin"])
    _hash(resource["proposal_sha256"]); _hash(resource["arguments_sha256"])
    _integer(resource["action_budget_ms"], MAX_ACTION_BUDGET_MS, 1)
    if _target(resource["target"])["kind"] != OPERATIONS[value["operation"]]:
        raise PermitRefused("permit resource kind differs from its operation")
    signature = _fields(value["signature"], {"algorithm", "key_id", "value"})
    if signature["algorithm"] != "ed25519":
        raise PermitRefused("signature algorithm is unsupported")
    _id(signature["key_id"]); _signature(signature["value"])
    return value


def permit_signing_bytes(payload: bytes) -> bytes:
    """Signing helper accepts a canonical 64-zero-byte signature placeholder.

    Only signature.value is excluded. Algorithm, key ID, issuer, all bounds and
    exact resource/proposal binding remain in the versioned signed preimage.
    """
    value = _permit(payload)
    signature = {name: item for name, item in value["signature"].items() if name != "value"}
    return PERMIT_DOMAIN + _canonical({**value, "signature": signature})


def _sealed_snapshot(name: str, content: bytes) -> int:
    descriptor = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("verification snapshot write made no progress")
            view = view[written:]
        seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, seals)
        if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & seals != seals:
            raise PermitRefused("verification snapshots are not immutable")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@dataclass(frozen=True)
class PinnedIssuerRoot:
    """Protected provisioning supplies this configuration, never proposal JSON.

    Constructing the object does not approve a key or authenticate provisioning.
    Canonical Ed25519 DER SPKI bytes must match the externally approved pin.
    """
    issuer: str
    key_id: str
    public_key_der: bytes
    public_key_sha256: str
    audience: str
    policy_revision: str
    valid_from_unix_ms: int
    valid_until_unix_ms: int

    def __post_init__(self) -> None:
        for value in (self.issuer, self.key_id, self.audience, self.policy_revision):
            _id(value)
        _hash(self.public_key_sha256)
        if type(self.public_key_der) is not bytes or len(self.public_key_der) != 44 or not self.public_key_der.startswith(ED25519_SPKI_PREFIX):
            raise PermitRefused("root must be a canonical Ed25519 public key")
        if hashlib.sha256(self.public_key_der).hexdigest() != self.public_key_sha256:
            raise PermitRefused("root does not match its externally pinned key")
        _integer(self.valid_from_unix_ms); _integer(self.valid_until_unix_ms)
        if self.valid_from_unix_ms >= self.valid_until_unix_ms:
            raise PermitRefused("root validity is invalid")


class ExternalPermitVerifier:
    def __init__(self, roots: tuple[PinnedIssuerRoot, ...] = ()):
        if type(roots) is not tuple or len(roots) > MAX_ROOTS or any(type(root) is not PinnedIssuerRoot for root in roots):
            raise PermitRefused("trust roots are invalid or over limit")
        if len({root.key_id for root in roots}) != len(roots):
            raise PermitRefused("trust key identifiers are duplicated")
        self._roots = MappingProxyType({root.key_id: root for root in roots})
        self._creator_pid = os.getpid()
        self._revoked_keys: set[str] = set()
        self._revoked_permits: set[str] = set()
        self._lock = threading.RLock()

    def _ensure_process(self) -> None:
        if os.getpid() != self._creator_pid:
            raise PermitRefused("permit verifier cannot reuse inherited fork policy")

    def revoke_key(self, key_id: str) -> None:
        self._ensure_process()
        with self._lock:
            _id(key_id)
            if len(self._revoked_keys) >= MAX_REVOCATIONS and key_id not in self._revoked_keys:
                raise PermitRefused("revocation capacity exhausted")
            self._revoked_keys.add(key_id)

    def revoke_permit(self, permit_id: str) -> None:
        self._ensure_process()
        with self._lock:
            _id(permit_id)
            if len(self._revoked_permits) >= MAX_REVOCATIONS and permit_id not in self._revoked_permits:
                raise PermitRefused("revocation capacity exhausted")
            self._revoked_permits.add(permit_id)

    def _root(self, value: dict, now_unix_ms: int) -> PinnedIssuerRoot:
        _integer(now_unix_ms)
        root = self._roots.get(value["signature"]["key_id"])
        if root is None or root.key_id in self._revoked_keys or value["permit_id"] in self._revoked_permits:
            raise PermitRefused("issuer or permit is unknown or revoked")
        if (value["issuer"], value["audience"], value["policy_revision"]) != (root.issuer, root.audience, root.policy_revision):
            raise PermitRefused("permit differs from approved issuer scope")
        if not root.valid_from_unix_ms <= value["issued_unix_ms"] <= now_unix_ms < value["expires_unix_ms"] <= root.valid_until_unix_ms:
            raise PermitRefused("root or permit validity is not current")
        return root

    def verify(self, payload: bytes, *, now_unix_ms: int, timeout: float = 2.0) -> bytes:
        self._ensure_process()
        value = _permit(payload)
        with self._lock:
            root = self._root(value, now_unix_ms)
            if type(timeout) not in {int, float} or not 0 < timeout <= 2:
                raise PermitRefused("verification deadline is invalid")
            try:
                metadata = os.lstat(OPENSSL)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
                    raise PermitRefused("offline verifier executable custody is invalid")
                snapshots = []
                try:
                    for name, content in (("hepta-permit-key", root.public_key_der), ("hepta-permit-preimage", permit_signing_bytes(payload)), ("hepta-permit-signature", _signature(value["signature"]["value"]))):
                        snapshots.append(_sealed_snapshot(name, content))
                    key, preimage, signature = snapshots
                    result = subprocess.run([OPENSSL, "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER", "-inkey", f"/proc/self/fd/{key}", "-sigfile", f"/proc/self/fd/{signature}", "-in", f"/proc/self/fd/{preimage}"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env=OPENSSL_ENV, pass_fds=tuple(snapshots), timeout=float(timeout), check=False)
                finally:
                    for descriptor in reversed(snapshots):
                        os.close(descriptor)
            except (OSError, AttributeError, subprocess.TimeoutExpired) as error:
                raise PermitRefused("offline signature verification is unavailable") from error
            if result.returncode != 0:
                raise PermitRefused("external signature verification failed")
            return _canonical(value)

    def revalidate(self, verified_payload: bytes, *, now_unix_ms: int) -> None:
        self._ensure_process()
        # Callers cannot supply an approval assertion: coordinator retains only
        # payload bytes produced by real verification and rechecks policy here.
        with self._lock:
            self._root(_permit(verified_payload), now_unix_ms)


CONSUMPTION_FIELDS = {"schema", "task_id", "action_id", "proposal_sha256", "permit_id", "issuer", "nonce", "permit_sha256"}
RESERVATION_FIELDS = {"schema", "task_id", "policy_sha256"}


def _task_name(task_id: str) -> str:
    return "task-" + hashlib.sha256(_id(task_id).encode("ascii")).hexdigest() + ".reserved"


def _consumption(value: dict) -> dict:
    _fields(value, CONSUMPTION_FIELDS)
    if value["schema"] != CONSUMPTION_SCHEMA:
        raise RecoveryRequired("consumption schema is invalid")
    for field in ("task_id", "action_id", "permit_id", "issuer"):
        _id(value[field])
    for field in ("proposal_sha256", "nonce", "permit_sha256"):
        _hash(value[field])
    return value


def _names(value: dict) -> tuple[str, str, str]:
    permit = hashlib.sha256(value["permit_id"].encode("ascii")).hexdigest()
    request = hashlib.sha256((value["task_id"] + "\x00" + value["action_id"]).encode("ascii")).hexdigest()
    return f"nonce-{value['nonce']}.used", f"permit-{permit}.used", f"request-{request}.used"


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _open_chain(path: Path) -> list[int]:
    descriptors = [os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)]
    try:
        for component in path.parts[1:]:
            if component in {".", ".."}:
                raise RecoveryRequired("store path contains traversal")
            descriptors.append(os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptors[-1]))
        return descriptors
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


class DurableGrantStore:
    """One retained private provisioned directory with immutable consumptions.

    Every nonce, permit ID, and task/action identity is durably claimed by three
    O_EXCL files before adapter dispatch. No consumption is removed or repaired.
    A historical partial set, damaged record or ambiguous sync requires separate
    recovery; a directory rollback requires an external anti-rollback authority.
    """
    def __init__(self, root: Path):
        self._creator_pid = os.getpid()
        self._lock = threading.RLock()
        self._closed = False
        self._poisoned = False
        self._files: dict[str, tuple[tuple[int, int], bytes]] = {}
        self._historical_tasks: set[str] = set()
        self._chain: list[int] = []
        self._lease: int | None = None
        self._root = Path(root).absolute()
        try:
            self._chain = _open_chain(self._root)
            self._identities = tuple(_identity(os.fstat(fd)) for fd in self._chain)
            metadata = os.fstat(self._chain[-1])
            if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
                raise RecoveryRequired("store root must be provisioned private0700 with service ownership")
            self._lease = os.open(".taskflow.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=self._chain[-1])
            self._lease_identity = _identity(os.fstat(self._lease))
            self._regular(self._lease, ".taskflow.lock", maximum=0)
            fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.fsync(self._lease); os.fsync(self._chain[-1])
            self._load()
            self._check()
        except BaseException as error:
            self.close()
            if not isinstance(error, (OSError, TaskFlowError)):
                raise
            raise RecoveryRequired("durable consumption store is unsafe, busy or damaged") from error

    def _regular(self, descriptor: int, name: str, *, maximum: int = 2048) -> os.stat_result:
        metadata = os.fstat(descriptor)
        named = os.stat(name, dir_fd=self._chain[-1], follow_symlinks=False)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > maximum or _identity(named) != _identity(metadata)):
            raise RecoveryRequired("consumption inode, mode, owner or name is unsafe")
        return metadata

    def _read(self, name: str) -> tuple[tuple[int, int], bytes]:
        descriptor = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self._chain[-1])
        try:
            metadata = self._regular(descriptor, name)
            data = os.pread(descriptor, metadata.st_size + 1, 0)
            after = self._regular(descriptor, name)
            if len(data) != metadata.st_size or metadata.st_size != after.st_size:
                raise RecoveryRequired("consumption changed during readback")
            return _identity(metadata), data
        finally:
            os.close(descriptor)

    def _load(self) -> None:
        names = os.listdir(self._chain[-1])
        if len(names) > 3 * MAX_HISTORY + MAX_TASK_RESERVATIONS + 1:
            raise RecoveryRequired("consumption history exceeds capacity")
        records = {}
        for name in names:
            if name == ".taskflow.lock":
                continue
            identity, data = self._read(name)
            value = _decode(data)
            if name.endswith(".reserved"):
                _fields(value, RESERVATION_FIELDS); _id(value["task_id"]); _hash(value["policy_sha256"])
                if value["schema"] != RESERVATION_SCHEMA or name != _task_name(value["task_id"]) or _canonical(value) != data:
                    raise RecoveryRequired("task reservation binding is invalid")
                self._files[name] = identity, data
                self._historical_tasks.add(value["task_id"])
                continue
            value = _consumption(value)
            if name not in _names(value) or _canonical(value) != data:
                raise RecoveryRequired("consumption binding or canonical bytes are invalid")
            self._files[name] = identity, data
            records[data] = value
            self._historical_tasks.add(value["task_id"])
        for data, value in records.items():
            if _task_name(value["task_id"]) not in self._files or any(name not in self._files or self._files[name][1] != data for name in _names(value)):
                raise RecoveryRequired("partial consumption requires separate recovery")
        if len(records) > MAX_HISTORY or len(self._historical_tasks) > MAX_TASK_RESERVATIONS:
            raise RecoveryRequired("task or consumption history exceeds capacity")

    def _ensure_process(self) -> None:
        if os.getpid() != self._creator_pid:
            raise RecoveryRequired("durable store cannot use inherited fork authority")

    def _check(self) -> None:
        self._ensure_process()
        try:
            self._check_custody()
        except (OSError, TaskFlowError) as error:
            self._poisoned = True
            raise RecoveryRequired("store custody requires separate recovery") from error

    def _check_custody(self) -> None:
        if self._closed or self._poisoned or not self._chain or self._lease is None:
            raise RecoveryRequired("consumption store is closed or requires recovery")
        chain = _open_chain(self._root)
        try:
            if tuple(_identity(os.fstat(fd)) for fd in chain) != self._identities:
                raise RecoveryRequired("store ancestor or root identity changed")
            root = os.fstat(chain[-1])
            if root.st_uid != os.geteuid() or stat.S_IMODE(root.st_mode) != 0o700:
                raise RecoveryRequired("store root custody changed")
        finally:
            for descriptor in reversed(chain):
                os.close(descriptor)
        if _identity(self._regular(self._lease, ".taskflow.lock", maximum=0)) != self._lease_identity:
            raise RecoveryRequired("store lease changed")
        if set(os.listdir(self._chain[-1])) != set(self._files) | {".taskflow.lock"}:
            raise RecoveryRequired("consumption namespace changed")
        for name, expected in self._files.items():
            if self._read(name) != expected:
                raise RecoveryRequired("consumption history changed")

    def refuses_task_resume(self, task_id: str) -> bool:
        self._ensure_process()
        with self._lock:
            try:
                self._check()
            except (OSError, TaskFlowError) as error:
                self._poisoned = True
                raise RecoveryRequired("store custody requires recovery") from error
            return _id(task_id) in self._historical_tasks

    def _reserve_task(self, policy: TaskPolicy) -> None:
        self._ensure_process()
        with self._lock:
            self._check()
            name = _task_name(policy.task_id)
            if name in self._files:
                raise ReplayRefused("task identity is already durably reserved")
            if len(self._historical_tasks) >= MAX_TASK_RESERVATIONS:
                raise RecoveryRequired("task reservation capacity is exhausted")
            digest = hashlib.sha256(b"trillionnium.desktop.taskflow-policy.v1\x00" + _canonical(asdict(policy))).hexdigest()
            data = _canonical({"schema": RESERVATION_SCHEMA, "task_id": policy.task_id, "policy_sha256": digest})
            self._write_records((name,), data)
            self._historical_tasks.add(policy.task_id)

    def _consume(self, value: dict) -> None:
        """Concrete persistence only; no caller acknowledgment grants dispatch."""
        self._ensure_process()
        with self._lock:
            self._check()
            data = _canonical(_consumption(value)); names = _names(value)
            if _task_name(value["task_id"]) not in self._files:
                raise RecoveryRequired("dispatch task has no durable reservation")
            if any(name in self._files for name in names):
                raise ReplayRefused("nonce, permit or action identity was already consumed")
            if sum(name.endswith(".used") for name in self._files) // 3 >= MAX_HISTORY:
                raise RecoveryRequired("consumption capacity is exhausted")
            self._write_records(names, data)

    def _write_records(self, names: tuple[str, ...], data: bytes) -> None:
        with self._lock:
            attempted = False
            retained: list[int] = []
            try:
                self._check()
                for name in names:
                    attempted = True
                    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self._chain[-1])
                    retained.append(descriptor)
                    view = memoryview(data)
                    while view:
                        written = os.write(descriptor, view)
                        if written <= 0:
                            raise OSError("consumption write made no progress")
                        view = view[written:]
                    os.fsync(descriptor)
                    metadata = self._regular(descriptor, name)
                    self._files[name] = _identity(metadata), data
                os.fsync(self._chain[-1])
                self._check()
                for name, descriptor in zip(names, retained):
                    if _identity(self._regular(descriptor, name)) != self._files[name][0]:
                        raise RecoveryRequired("consumption descriptor changed at publication")
            except ReplayRefused:
                raise
            except BaseException as error:
                self._poisoned = True
                if not isinstance(error, (OSError, TaskFlowError)):
                    raise
                raise RecoveryRequired("consumption persistence is uncertain; dispatch remains closed" if attempted else "consumption store requires recovery") from error
            finally:
                for descriptor in reversed(retained):
                    os.close(descriptor)

    def close(self) -> None:
        # Inherited mutex state may be held by a vanished thread. A forked
        # process may close its copies, never acquire or unlock parent authority.
        if os.getpid() != self._creator_pid:
            self._close_descriptors()
            return
        with self._lock:
            self._close_descriptors()

    def _close_descriptors(self) -> None:
        self._closed = True
        if self._lease is not None:
            os.close(self._lease); self._lease = None
        for descriptor in reversed(self._chain):
            os.close(descriptor)
        self._chain = []

    def __enter__(self) -> DurableGrantStore:
        self._ensure_process()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except (AttributeError, OSError):
            pass


class ActionState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    TERMINAL = "terminal"
    INDETERMINATE = "indeterminate"
    CANCELLED = "cancelled"
    HUMAN_HANDOFF = "human_handoff"


class EffectOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    REFUSED = "refused"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class ActionView:
    task_id: str
    action_id: str
    proposal_sha256: str
    state: ActionState
    operation: str


@dataclass
class _Action:
    payload: bytes
    digest: str
    deadline_ns: int
    state: ActionState = ActionState.PROPOSED
    permit: bytes | None = None
    approval_unix_ms: int | None = None


@dataclass
class _Task:
    policy: TaskPolicy
    deadline_ns: int
    actions: dict[str, _Action]
    current: str | None = None
    closed: bool = False
    cancelled: bool = False
    human_handoff: bool = False


class ActionControl:
    """Revocation/deadline control; native adapter rechecks its actual owner.

    The adapter cannot change proposal bytes, mint permits or renew budgets.
    This is an in-process trusted-code contract, not a Python sandbox.
    """
    def __init__(self, owner: TaskFlowCoordinator, task_id: str, action_id: str, seal: object):
        if seal is not _SEAL:
            raise PermitRefused("action control requires admitted dispatch")
        self._owner, self._task_id, self._action_id = owner, task_id, action_id

    def ensure_active(self, current: CurrentBinding) -> None:
        self._owner._ensure_dispatch(self._task_id, self._action_id, current)

    def is_cancelled(self) -> bool:
        self._owner._ensure_process()
        with self._owner._lock:
            task = self._owner._tasks[self._task_id]
            return task.cancelled or task.human_handoff


class TaskFlowCoordinator:
    def __init__(self, verifier: ExternalPermitVerifier | None = None, store: DurableGrantStore | None = None,
                 *, monotonic_ns: Callable[[], int] = time.monotonic_ns,
                 unix_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000):
        if verifier is not None and type(verifier) is not ExternalPermitVerifier:
            raise PermitRefused("permit verifier must be the concrete offline verifier")
        if store is not None and type(store) is not DurableGrantStore:
            raise RecoveryRequired("grant store must be the concrete durable store")
        self._verifier = verifier or ExternalPermitVerifier()
        self._creator_pid = os.getpid()
        self._store = store
        self._monotonic, self._unix = monotonic_ns, unix_ms
        self._last_monotonic = self._last_unix = -1
        self._time_failed = False
        self._tasks: dict[str, _Task] = {}
        self._lock = threading.RLock()

    def _ensure_process(self) -> None:
        if os.getpid() != self._creator_pid:
            raise RecoveryRequired("TaskFlow cannot use inherited fork authority")

    def _now(self) -> tuple[int, int]:
        if self._time_failed:
            raise RecoveryRequired("trusted time requires separate recovery")
        try:
            monotonic, unix = _integer(self._monotonic()), _integer(self._unix())
            if monotonic < self._last_monotonic or unix < self._last_unix:
                raise RecoveryRequired("trusted time regressed")
        except BaseException:
            self._time_failed = True
            for task in self._tasks.values():
                task.human_handoff = True
            raise RecoveryRequired("trusted time is unavailable; human recovery required") from None
        self._last_monotonic, self._last_unix = monotonic, unix
        return monotonic, unix

    def create_task(self, policy: TaskPolicy) -> None:
        self._ensure_process()
        with self._lock:
            if type(policy) is not TaskPolicy:
                raise TaskFlowError("task requires trusted typed policy")
            if policy.task_id in self._tasks or len(self._tasks) >= MAX_TASKS:
                raise ReplayRefused("task identifier is reused or task capacity exhausted")
            if self._store is not None and self._store.refuses_task_resume(policy.task_id):
                raise RecoveryRequired("previously reserved task cannot be resumed without a recovery protocol")
            now, _ = self._now()
            deadline = _integer(now + policy.task_budget_ms * 1_000_000)
            if self._store is not None:
                self._store._reserve_task(policy)
            after_reservation, _ = self._now()
            if after_reservation >= deadline:
                raise DeadlineExceeded("task reservation exhausted the original task budget")
            self._tasks[policy.task_id] = _Task(policy, deadline, {})

    def _task(self, task_id: str) -> _Task:
        task = self._tasks.get(_id(task_id))
        if task is None:
            raise TaskFlowError("task identifier is unknown")
        return task

    def _open(self, task: _Task, action: _Action | None = None) -> tuple[int, int]:
        now, unix = self._now()
        if task.cancelled:
            raise Cancelled("task is cancelled")
        if task.closed or task.human_handoff:
            raise RecoveryRequired("task is closed or handed to the human")
        if now >= task.deadline_ns or (action is not None and now >= action.deadline_ns):
            raise DeadlineExceeded("original task or action budget is exhausted")
        return now, unix

    def propose(self, task_id: str, payload: bytes) -> ActionView:
        self._ensure_process()
        value = _proposal(payload)
        with self._lock:
            task = self._task(task_id); now, _ = self._open(task)
            policy = task.policy; binding = policy.binding
            if (value["task_id"], value["principal_id"], value["audience"], value["policy_revision"], value["session_id"], value["session_generation"], value["origin"]) != (policy.task_id, binding.principal_id, policy.audience, policy.policy_revision, binding.session_id, binding.session_generation, binding.origin):
                raise TaskFlowError("proposal differs from trusted task binding")
            if value["resource"] != binding.resource():
                raise TaskFlowError("proposal differs from trusted retained resource binding")
            if value["action_budget_ms"] > policy.max_action_budget_ms or len(task.actions) >= policy.max_actions:
                raise TaskFlowError("task or action budget limit exceeded")
            if value["action_id"] in task.actions:
                raise ReplayRefused("action identifier cannot be reused")
            if task.current is not None and task.actions[task.current].state not in {ActionState.TERMINAL, ActionState.CANCELLED}:
                raise TaskFlowError("one unresolved proposal may be active")
            canonical = _canonical(value)
            deadline = _integer(now + value["action_budget_ms"] * 1_000_000)
            action = _Action(canonical, hashlib.sha256(PROPOSAL_DOMAIN + canonical).hexdigest(), min(task.deadline_ns, deadline))
            task.actions[value["action_id"]] = action; task.current = value["action_id"]
            return self._view(task, action)

    def _view(self, task: _Task, action: _Action) -> ActionView:
        value = _proposal(action.payload)
        return ActionView(task.policy.task_id, value["action_id"], action.digest, action.state, value["operation"])

    def current(self, task_id: str) -> ActionView:
        self._ensure_process()
        with self._lock:
            task = self._task(task_id)
            if task.current is None:
                raise TaskFlowError("task has no proposal")
            return self._view(task, task.actions[task.current])

    def _match(self, action: _Action, permit: dict) -> None:
        proposal = _proposal(action.payload)
        expected_resource = {
            "task_id": proposal["task_id"], "action_id": proposal["action_id"], "session_id": proposal["session_id"],
            "session_generation": proposal["session_generation"], "origin": proposal["origin"], "proposal_sha256": action.digest,
            "target": proposal["resource"], "arguments_sha256": hashlib.sha256(_canonical(proposal["arguments"])).hexdigest(),
            "action_budget_ms": proposal["action_budget_ms"],
        }
        if (permit["subject"], permit["audience"], permit["operation"], permit["policy_revision"]) != (proposal["principal_id"], proposal["audience"], proposal["operation"], proposal["policy_revision"]) or permit["resource"] != expected_resource:
            raise PermitRefused("permit differs from the exact current typed proposal")

    def approve(self, task_id: str, permit_payload: bytes) -> ActionView:
        self._ensure_process()
        with self._lock:
            task = self._task(task_id)
            if task.current is None:
                raise PermitRefused("there is no proposal to approve")
            action = task.actions[task.current]
            now, unix = self._open(task, action)
            if action.state != ActionState.PROPOSED:
                raise PermitRefused("only a current unapproved proposal may receive a permit")
            value = _permit(permit_payload); self._match(action, value)
            timeout = min(2.0, (min(task.deadline_ns, action.deadline_ns) - now) / 1_000_000_000)
            verified = self._verifier.verify(permit_payload, now_unix_ms=unix, timeout=timeout)
            # Pin signed wall-clock expiry to the original approval-time
            # monotonic sample. Frozen wall time cannot renew this ceiling.
            permit_deadline = _integer(now + (value["expires_unix_ms"] - unix) * 1_000_000)
            _, current_unix = self._open(task, action)
            self._verifier.revalidate(verified, now_unix_ms=current_unix)
            action.deadline_ns = min(action.deadline_ns, permit_deadline)
            self._open(task, action)
            action.permit, action.approval_unix_ms, action.state = verified, current_unix, ActionState.APPROVED
            return self._view(task, action)

    def _validate(self, task: _Task, action: _Action, current: CurrentBinding) -> None:
        _, unix = self._open(task, action)
        if type(current) is not CurrentBinding or current != task.policy.binding:
            raise PermitRefused("current native principal, session or origin differs from approved task")
        if action.permit is None:
            raise PermitRefused("action has no externally verified permit")
        self._match(action, _permit(action.permit))
        self._verifier.revalidate(action.permit, now_unix_ms=unix)

    def _ensure_dispatch(self, task_id: str, action_id: str, current: CurrentBinding) -> None:
        self._ensure_process()
        with self._lock:
            task = self._task(task_id)
            action = task.actions.get(_id(action_id))
            if action is None or task.current != action_id or action.state != ActionState.DISPATCHED:
                raise PermitRefused("native action control is not current")
            self._validate(task, action, current)

    def dispatch(self, task_id: str, current: CurrentBinding,
                 adapter: Callable[[bytes, ActionControl], EffectOutcome]) -> ActionView:
        self._ensure_process()
        with self._lock:
            task = self._task(task_id)
            if task.current is None:
                raise PermitRefused("task has no approved proposal")
            action_id = task.current; action = task.actions[action_id]
            if action.state != ActionState.APPROVED:
                raise ReplayRefused("action is not awaiting its single dispatch")
            if self._store is None:
                raise RecoveryRequired("actual dispatch requires a concrete durable grant store")
            if not callable(adapter):
                raise TaskFlowError("trusted effect adapter is unavailable")
            self._validate(task, action, current)
            permit = _permit(action.permit)
            record = {"schema": CONSUMPTION_SCHEMA, "task_id": task_id, "action_id": action_id,
                      "proposal_sha256": action.digest, "permit_id": permit["permit_id"], "issuer": permit["issuer"],
                      "nonce": permit["nonce"], "permit_sha256": hashlib.sha256(action.permit).hexdigest()}
            try:
                self._store._consume(record)
                # No lock/persistence wait follows the final local authority
                # check before calling the trusted adapter. The native adapter
                # must repeat this control check alongside its retained target.
                self._validate(task, action, current)
            except BaseException:
                action.state = ActionState.HUMAN_HANDOFF; task.human_handoff = True
                raise
            action.state = ActionState.DISPATCHED
            control = ActionControl(self, task_id, action_id, _SEAL)
            payload = action.payload
        try:
            outcome = adapter(payload, control)
            with self._lock:
                self._validate(task, action, current)
                if type(outcome) is not EffectOutcome:
                    raise TaskFlowError("adapter returned no typed completion")
                if outcome == EffectOutcome.INDETERMINATE:
                    action.state = ActionState.INDETERMINATE; task.human_handoff = True
                else:
                    action.state = ActionState.TERMINAL
                return self._view(task, action)
        except BaseException:
            with self._lock:
                action.state = ActionState.INDETERMINATE; task.human_handoff = True
            raise

    def cancel(self, task_id: str) -> ActionView | None:
        self._ensure_process()
        with self._lock:
            task = self._task(task_id); task.cancelled = True
            if task.current is None:
                return None
            action = task.actions[task.current]
            if action.state == ActionState.DISPATCHED:
                action.state = ActionState.INDETERMINATE; task.human_handoff = True
            elif action.state in {ActionState.PROPOSED, ActionState.APPROVED}:
                action.state = ActionState.CANCELLED
            return self._view(task, action)

    def handoff_to_human(self, task_id: str) -> ActionView | None:
        self._ensure_process()
        with self._lock:
            task = self._task(task_id); task.human_handoff = True
            if task.current is None:
                return None
            action = task.actions[task.current]
            if action.state == ActionState.DISPATCHED:
                action.state = ActionState.INDETERMINATE
            elif action.state in {ActionState.PROPOSED, ActionState.APPROVED}:
                action.state = ActionState.HUMAN_HANDOFF
            return self._view(task, action)

    def close_task(self, task_id: str) -> None:
        self._ensure_process()
        with self._lock:
            task = self._task(task_id)
            if task.current is not None and task.actions[task.current].state not in {ActionState.TERMINAL, ActionState.CANCELLED}:
                raise RecoveryRequired("task cannot close unresolved work")
            task.closed = True
