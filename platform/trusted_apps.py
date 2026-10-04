"""Offline admission and local asset responses for signed app bundles v1.

This source API grants no capability, installs no origin interceptor, and performs
no network access. Callers must supply an externally authenticated trust policy
and trusted time. See docs/architecture/TRUSTED_APP_BUNDLES.md for the wire format
and the remaining installed storage and engine obligations.
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
import struct
import subprocess
import threading
import zlib
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

MANIFEST_SCHEMA = "trillionnium.desktop.app-manifest.v1"
INDEX_SCHEMA = "trillionnium.desktop.trusted-app-content-index.v1"
MANIFEST_DOMAIN = b"trillionnium.desktop.app-manifest-signature.v1\x00"
CONTENT_DOMAIN = b"trillionnium.desktop.trusted-app-content-index.v1\x00"
MANIFEST_PATH = "manifest.json"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_CONTENT_BYTES = 64 * 1024 * 1024
MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ASSETS = 512
MAX_COMPRESSION_RATIO = 128
MAX_POLICY_KEYS = 256
MAX_POLICY_REVOCATIONS = 1024
MAX_SEEN_KEYS = 4096
MAX_UNIX = (1 << 63) - 1
OPENSSL = "/usr/bin/openssl"
OPENSSL_ENV = {"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null", "LC_ALL": "C"}
ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
RESTRICTIVE_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "font-src 'self'; media-src 'self'; connect-src 'none'; object-src 'none'; "
    "base-uri 'none'; frame-src 'none'; frame-ancestors 'none'; "
    "form-action 'none'; worker-src 'none'"
)

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.ASCII)
_KEY_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}\Z", re.ASCII)
_CAPABILITY = re.compile(r"[a-z0-9_.:-]{1,128}\Z", re.ASCII)
_SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z", re.ASCII
)
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_REQUIRED_FIELDS = {
    "schema", "publisher", "app_id", "version", "entrypoint", "origin_host",
    "content_root_sha256", "capabilities", "csp", "minimum_shell_version", "signature",
}
_MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json", ".txt": "text/plain; charset=utf-8",
    ".bin": "application/octet-stream",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
    ".ttf": "font/ttf", ".otf": "font/otf", ".wasm": "application/wasm",
    ".mp3": "audio/mpeg", ".mp4": "video/mp4", ".webm": "video/webm",
}


class AppAdmissionError(ValueError):
    """Malformed, unauthenticated, expired, revoked, or nonlocal input."""


def _integer(value: object, name: str, maximum: int = MAX_UNIX) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise AppAdmissionError(f"invalid {name}")
    return value


def _label(value: object, name: str) -> str:
    if type(value) is not str or _LABEL.fullmatch(value) is None:
        raise AppAdmissionError(f"invalid {name}")
    return value


def _key_id(value: object) -> str:
    if type(value) is not str or _KEY_ID.fullmatch(value) is None:
        raise AppAdmissionError("invalid key_id")
    return value


def _digest(value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise AppAdmissionError("invalid SHA-256")
    return value


def _version(value: object, *, stable: bool = False) -> tuple[int, int, int]:
    if type(value) is not str or len(value) > 128:
        raise AppAdmissionError("invalid version")
    match = _SEMVER.fullmatch(value)
    if match is None or (stable and match[4] is not None):
        raise AppAdmissionError("invalid version")
    numbers = tuple(int(match[number]) for number in (1, 2, 3))
    if any(number > 0xFFFFFFFF for number in numbers):
        raise AppAdmissionError("version component exceeds uint32")
    if match[4] is not None and any(
        token.isdigit() and len(token) > 1 and token.startswith("0")
        for token in match[4].split(".")
    ):
        raise AppAdmissionError("noncanonical prerelease version")
    return numbers


def _asset_path(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 512:
        raise AppAdmissionError("invalid asset path")
    for segment in value.split("/"):
        if (_SEGMENT.fullmatch(segment) is None or segment.endswith(".")
                or segment.split(".", 1)[0].upper() in _RESERVED):
            raise AppAdmissionError("noncanonical or reserved asset path")
    return value


def _check_paths(paths: list[str]) -> None:
    folded = set()
    for path in paths:
        _asset_path(path)
        if path.lower() in folded:
            raise AppAdmissionError("duplicate or case-colliding archive path")
        folded.add(path.lower())
    for path in folded:
        parts = path.split("/")
        if any("/".join(parts[:length]) in folded for length in range(1, len(parts))):
            raise AppAdmissionError("file/directory path collision")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AppAdmissionError("duplicate JSON field")
        result[key] = value
    return result


def _json_integer(value: str) -> int:
    if len(value) > 20:
        raise AppAdmissionError("JSON integer exceeds bound")
    return int(value)


def _no_float(value: str) -> object:
    raise AppAdmissionError("noninteger JSON number")


def _manifest(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_MANIFEST_BYTES:
        raise AppAdmissionError("manifest bytes exceed bound")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_int=_json_integer, parse_float=_no_float,
                           parse_constant=_no_float)
        if type(value) is not dict or payload != _canonical_json(value):
            raise AppAdmissionError("manifest must be canonical JSON")
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise AppAdmissionError("invalid canonical manifest JSON") from error
    if not _REQUIRED_FIELDS <= value.keys() or value.keys() - _REQUIRED_FIELDS - {"data_schema_version"}:
        raise AppAdmissionError("manifest field set differs from v1")
    if value["schema"] != MANIFEST_SCHEMA:
        raise AppAdmissionError("unsupported manifest schema")
    publisher = _label(value["publisher"], "publisher")
    app_id = _label(value["app_id"], "app_id")
    _version(value["version"])
    _version(value["minimum_shell_version"], stable=True)
    entrypoint = _asset_path(value["entrypoint"])
    if not entrypoint.endswith(".html"):
        raise AppAdmissionError("entrypoint must be an indexed HTML asset")
    if value["origin_host"] != f"{app_id}.{publisher}.apps.hepta.invalid":
        raise AppAdmissionError("origin does not match publisher and app_id")
    _digest(value["content_root_sha256"])
    if value["csp"] != RESTRICTIVE_CSP:
        raise AppAdmissionError("CSP differs from restrictive v1 profile")
    capabilities = value["capabilities"]
    if (type(capabilities) is not list or len(capabilities) > 64
            or any(type(item) is not str or _CAPABILITY.fullmatch(item) is None for item in capabilities)
            or len(set(capabilities)) != len(capabilities)):
        raise AppAdmissionError("invalid capability declarations")
    if "data_schema_version" in value and _integer(value["data_schema_version"], "data_schema_version") < 1:
        raise AppAdmissionError("invalid data_schema_version")
    signature = value["signature"]
    if type(signature) is not dict or signature.keys() != {"algorithm", "key_id", "value"}:
        raise AppAdmissionError("invalid signature field set")
    if signature["algorithm"] != "ed25519":
        raise AppAdmissionError("unsupported signature algorithm")
    _key_id(signature["key_id"])
    _signature_value(signature["value"])
    return value


def _signature_value(value: object) -> bytes:
    if type(value) is not str or len(value) != 88:
        raise AppAdmissionError("signature must be canonical base64 of 64 bytes")
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise AppAdmissionError("invalid base64 signature") from error
    if len(result) != 64 or base64.b64encode(result).decode("ascii") != value:
        raise AppAdmissionError("noncanonical Ed25519 signature")
    return result


def _signing_bytes(value: dict[str, object]) -> bytes:
    signature = value["signature"]
    unsigned = {**value, "signature": {key: item for key, item in signature.items() if key != "value"}}
    return MANIFEST_DOMAIN + _canonical_json(unsigned)


def manifest_signing_bytes(payload: bytes) -> bytes:
    """Validate canonical v1 metadata; omit ONLY signature.value from preimage.

    A signer may use base64 of 64 zero bytes as the initial value. Algorithm,
    key_id, all manifest fields, and optional data_schema_version remain signed.
    """
    return _signing_bytes(_manifest(payload))


def content_index_bytes(assets: Mapping[str, bytes]) -> bytes:
    """Canonical complete asset index; manifest.json is excluded to avoid recursion."""
    if not isinstance(assets, Mapping) or not 1 <= len(assets) <= MAX_ASSETS:
        raise AppAdmissionError("invalid asset count")
    paths = list(assets)
    _check_paths(paths + [MANIFEST_PATH])
    total = 0
    files = []
    for path in sorted(paths):
        content = assets[path]
        if type(content) is not bytes or len(content) > MAX_ASSET_BYTES:
            raise AppAdmissionError("invalid or oversized immutable asset bytes")
        total += len(content)
        if total > MAX_CONTENT_BYTES:
            raise AppAdmissionError("content size exceeds bound")
        files.append({"path": path, "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)})
    return _canonical_json({"schema": INDEX_SCHEMA, "files": files})


def content_root_sha256(assets: Mapping[str, bytes]) -> str:
    return hashlib.sha256(CONTENT_DOMAIN + content_index_bytes(assets)).hexdigest()


@dataclass(frozen=True)
class PublisherTrustRoot:
    """An externally pinned raw Ed25519 key, scoped to one exact publisher."""

    publisher: str
    key_id: str
    public_key: bytes
    public_key_sha256: str
    valid_from_unix: int
    valid_until_unix: int

    def __post_init__(self) -> None:
        _label(self.publisher, "publisher")
        _key_id(self.key_id)
        if type(self.public_key) is not bytes or len(self.public_key) != 32:
            raise AppAdmissionError("Ed25519 root must be 32 immutable raw bytes")
        if _digest(self.public_key_sha256) != hashlib.sha256(self.public_key).hexdigest():
            raise AppAdmissionError("external public key pin mismatch")
        _integer(self.valid_from_unix, "root valid_from_unix")
        if _integer(self.valid_until_unix, "root valid_until_unix") <= self.valid_from_unix:
            raise AppAdmissionError("invalid root validity interval")


@dataclass(frozen=True)
class PublisherTrustPolicy:
    """Externally authenticated root/revocation snapshot, never bundled with an app.

    The policy and key intervals are half-open [valid_from, valid_until). Revision
    must advance within one admission owner; revoked (publisher,key_id) pairs are
    permanent for that owner. Persistent rollback resistance remains external.
    """

    revision: int
    valid_from_unix: int
    valid_until_unix: int
    roots: tuple[PublisherTrustRoot, ...] = ()
    revoked_keys: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _integer(self.revision, "policy revision")
        _integer(self.valid_from_unix, "policy valid_from_unix")
        if _integer(self.valid_until_unix, "policy valid_until_unix") <= self.valid_from_unix:
            raise AppAdmissionError("invalid policy validity interval")
        if type(self.roots) is not tuple or len(self.roots) > MAX_POLICY_KEYS:
            raise AppAdmissionError("invalid bounded root tuple")
        identities = []
        for root in self.roots:
            if type(root) is not PublisherTrustRoot:
                raise AppAdmissionError("invalid trust root")
            identities.append((root.publisher, root.key_id))
        if len(set(identities)) != len(identities):
            raise AppAdmissionError("duplicate publisher/key_id root")
        if type(self.revoked_keys) is not tuple or len(self.revoked_keys) > MAX_POLICY_REVOCATIONS:
            raise AppAdmissionError("invalid bounded revocation tuple")
        for pair in self.revoked_keys:
            if type(pair) is not tuple or len(pair) != 2:
                raise AppAdmissionError("invalid revocation identity")
            _label(pair[0], "revoked publisher")
            _key_id(pair[1])
        if len(set(self.revoked_keys)) != len(self.revoked_keys):
            raise AppAdmissionError("duplicate revocation identity")


def _ed25519_verify(public_key: bytes, signature: bytes, preimage: bytes) -> None:
    """Fixed system OpenSSL reads sealed memfds, never reopens mutable temp paths."""
    descriptors = []
    try:
        for name, payload in (("hepta-app-key", ED25519_SPKI_PREFIX + public_key),
                              ("hepta-app-signature", signature), ("hepta-app-manifest", preimage)):
            fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            descriptors.append(fd)
            remaining = memoryview(payload)
            while remaining:
                written = os.write(fd, remaining)
                if not written:
                    raise AppAdmissionError("offline verifier input write failed")
                remaining = remaining[written:]
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS,
                        fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
            os.lseek(fd, 0, os.SEEK_SET)
        paths = [f"/proc/self/fd/{fd}" for fd in descriptors]
        result = subprocess.run(
            [OPENSSL, "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER",
             "-inkey", paths[0], "-sigfile", paths[1], "-in", paths[2]],
            env=OPENSSL_ENV, stdin=subprocess.DEVNULL, capture_output=True,
            pass_fds=tuple(descriptors), timeout=5, check=False,
        )
        if result.returncode != 0:
            raise AppAdmissionError("Ed25519 signature verification refused")
    except (AttributeError, OSError, subprocess.SubprocessError) as error:
        raise AppAdmissionError("offline Ed25519 verifier unavailable or failed") from error
    finally:
        for fd in descriptors:
            os.close(fd)


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_snapshot(path: os.PathLike[str] | str) -> bytes:
    """Walk every component without following symlinks, then retain bounded bytes."""
    try:
        raw_path = os.fspath(path)
    except TypeError as error:
        raise AppAdmissionError("invalid filesystem path type") from error
    if type(raw_path) is not str or not raw_path.startswith("/") or "\x00" in raw_path:
        raise AppAdmissionError("bundle path must be an absolute filesystem path")
    parts = raw_path.split("/")[1:]
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise AppAdmissionError("noncanonical filesystem path")
    directory_fd = file_fd = None
    try:
        directory_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                          dir_fd=directory_fd)
        before = os.fstat(file_fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 1 <= before.st_size <= MAX_ARCHIVE_BYTES):
            raise AppAdmissionError("bundle must be a bounded single-link regular file")
        chunks = []
        total = 0
        while total <= before.st_size:
            chunk = os.read(file_fd, min(65536, before.st_size + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        after = os.fstat(file_fd)
        named = os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if (total != before.st_size or _file_identity(before) != _file_identity(after)
                or _file_identity(after) != _file_identity(named)):
            raise AppAdmissionError("bundle file changed while snapshotting")
        return b"".join(chunks)
    except OSError as error:
        raise AppAdmissionError("bundle custody/read refused") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _zip_contents(archive: bytes) -> tuple[bytes, Mapping[str, bytes]]:
    """Bounded classic ZIP profile; every byte/record belongs to indexed files."""
    if type(archive) is not bytes or not 22 <= len(archive) <= MAX_ARCHIVE_BYTES:
        raise AppAdmissionError("archive bytes exceed bound")
    try:
        end = struct.unpack_from("<4s4H2LH", archive, len(archive) - 22)
    except struct.error as error:
        raise AppAdmissionError("truncated ZIP end record") from error
    signature, disk, central_disk, disk_count, count, central_size, central_offset, comment_size = end
    if (signature != b"PK\x05\x06" or disk != 0 or central_disk != 0
            or disk_count != count or not 2 <= count <= MAX_ASSETS + 1 or comment_size != 0
            or central_offset + central_size != len(archive) - 22):
        raise AppAdmissionError("unsupported or incomplete ZIP directory")
    cursor = central_offset
    rows = []
    names = []
    total_size = 0
    for _ in range(count):
        try:
            row = struct.unpack_from("<4s6H3L5H2L", archive, cursor)
        except struct.error as error:
            raise AppAdmissionError("truncated ZIP directory entry") from error
        (magic, made_by, needed, flags, compression, time, date, crc, compressed, size,
         name_size, extra_size, file_comment_size, start_disk, internal, external, offset) = row
        end_name = cursor + 46 + name_size
        if (magic != b"PK\x01\x02" or made_by >> 8 not in (0, 3) or needed > 20
                or flags & ~0x800 or compression not in (0, 8) or extra_size or file_comment_size
                or start_disk or end_name > central_offset + central_size):
            raise AppAdmissionError("unsupported ZIP entry encoding or feature")
        try:
            name = archive[cursor + 46:end_name].decode("ascii")
        except UnicodeError as error:
            raise AppAdmissionError("ZIP paths must be portable ASCII") from error
        _asset_path(name)
        mode = external >> 16
        if stat.S_IFMT(mode) not in (0, stat.S_IFREG) or external & 0x10 or mode & 0o7000:
            raise AppAdmissionError("ZIP entry is not a plain regular asset")
        limit = MAX_MANIFEST_BYTES if name == MANIFEST_PATH else MAX_ASSET_BYTES
        if size > limit or size > MAX_COMPRESSION_RATIO * max(1, compressed):
            raise AppAdmissionError("ZIP asset size or compression ratio exceeds bound")
        total_size += size
        if total_size > MAX_CONTENT_BYTES:
            raise AppAdmissionError("ZIP total content exceeds bound")
        rows.append((name, needed, flags, compression, time, date, crc, compressed, size, offset))
        names.append(name)
        cursor = end_name
    if cursor != central_offset + central_size:
        raise AppAdmissionError("unindexed ZIP directory bytes")
    _check_paths(names)
    if MANIFEST_PATH not in names:
        raise AppAdmissionError("archive has no exact manifest.json")
    local_cursor = 0
    contents: dict[str, bytes] = {}
    for name, needed, flags, compression, time, date, crc, compressed, size, offset in sorted(rows, key=lambda row: row[-1]):
        if offset != local_cursor:
            raise AppAdmissionError("ZIP local records contain gaps, overlap, or preamble")
        try:
            local = struct.unpack_from("<4s5H3L2H", archive, offset)
        except struct.error as error:
            raise AppAdmissionError("truncated ZIP local entry") from error
        (magic, local_needed, local_flags, local_compression, local_time, local_date,
         local_crc, local_compressed, local_size, name_size, extra_size) = local
        content_start = offset + 30 + name_size
        content_end = content_start + compressed
        if (magic != b"PK\x03\x04" or local_needed != needed or local_flags != flags
                or local_compression != compression or local_time != time or local_date != date
                or local_crc != crc or local_compressed != compressed or local_size != size or extra_size
                or archive[offset + 30:content_start] != name.encode("ascii") or content_end > central_offset):
            raise AppAdmissionError("ZIP local/central mismatch")
        encoded = archive[content_start:content_end]
        if compression == 0:
            content = encoded
        else:
            decoder = zlib.decompressobj(-15)
            try:
                content = decoder.decompress(encoded, size + 1)
            except zlib.error as error:
                raise AppAdmissionError("invalid ZIP deflate stream") from error
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise AppAdmissionError("incomplete or trailing ZIP deflate stream")
        if len(content) != size or zlib.crc32(content) != crc:
            raise AppAdmissionError("ZIP asset length or CRC mismatch")
        contents[name] = content
        local_cursor = content_end
    if local_cursor != central_offset:
        raise AppAdmissionError("unindexed ZIP local bytes")
    payload = contents.pop(MANIFEST_PATH)
    return payload, MappingProxyType(contents)


@dataclass(frozen=True, init=False)
class VerifiedAppBundle:
    """Owner-issued immutable asset snapshot; only admission constructs this object."""

    _issuer: object
    _assets: Mapping[str, bytes]
    _manifest: bytes
    _key_id: str
    _key_pin: str
    publisher: str
    app_id: str
    version: str
    entrypoint: str
    origin_host: str
    content_root_sha256: str
    archive_sha256: str
    manifest_sha256: str
    capabilities: tuple[str, ...]
    data_schema_version: int | None

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AppAdmissionError("VerifiedAppBundle is constructed by offline admission only")

    @property
    def entrypoint_url(self) -> str:
        return f"https://{self.origin_host}/{self.entrypoint}"

    @property
    def asset_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._assets))


@dataclass(frozen=True)
class LocalAssetResponse:
    asset_path: str
    body: bytes
    headers: Mapping[str, str]
    status: int = 200


def _owned_operation(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        self._on_owner()
        if self._busy:
            raise AppAdmissionError("reentrant admission operation refused")
        self._busy = True
        try:
            return method(self, *args, **kwargs)
        finally:
            self._busy = False
    return invoke


class TrustedAppAdmission:
    """Single-owner source admission and response service; empty roots reject.

    Provisioning is trusted code. Operations require the creating process/thread;
    policy replacement and response issuance are one synchronous operation each.
    It does not activate apps or persist policy revisions across process restart.
    """

    def __init__(self, *, shell_version: str, policy: PublisherTrustPolicy | None = None) -> None:
        self._shell_version = _version(shell_version, stable=True)
        self._issuer = object()
        self._owner_process = os.getpid()
        self._owner_thread = threading.current_thread()
        self._busy = False
        self._state: tuple[PublisherTrustPolicy | None, Mapping[tuple[str, str], str]] = (None, MappingProxyType({}))
        if policy is not None:
            self.replace_policy(policy)

    def _on_owner(self) -> None:
        if os.getpid() != self._owner_process or threading.current_thread() is not self._owner_thread:
            raise AppAdmissionError("admission requires its creating process and thread")

    @_owned_operation
    def replace_policy(self, policy: PublisherTrustPolicy) -> None:
        """Accept a newer authenticated snapshot, preserving revocations and pins."""
        if type(policy) is not PublisherTrustPolicy:
            raise AppAdmissionError("invalid trust policy")
        previous, seen_pins = self._state
        if previous is not None:
            if policy.revision <= previous.revision:
                raise AppAdmissionError("trust policy revision replay")
            if not set(previous.revoked_keys) <= set(policy.revoked_keys):
                raise AppAdmissionError("trust policy removed a revocation")
        pins = dict(seen_pins)
        for root in policy.roots:
            identity = (root.publisher, root.key_id)
            if identity in pins and pins[identity] != root.public_key_sha256:
                raise AppAdmissionError("key_id cannot be rebound to another key")
            pins[identity] = root.public_key_sha256
        if len(pins) > MAX_SEEN_KEYS:
            raise AppAdmissionError("trust key history capacity exhausted")
        self._state = (policy, MappingProxyType(pins))

    def _root(self, publisher: str, key_id: str, now_unix: int) -> PublisherTrustRoot:
        now = _integer(now_unix, "trusted now_unix")
        policy = self._state[0]
        if policy is None or not policy.valid_from_unix <= now < policy.valid_until_unix:
            raise AppAdmissionError("trust policy unavailable, not yet valid, or expired")
        if (publisher, key_id) in policy.revoked_keys:
            raise AppAdmissionError("publisher key is revoked")
        matches = [root for root in policy.roots if root.publisher == publisher and root.key_id == key_id]
        if len(matches) != 1:
            raise AppAdmissionError("publisher/key_id has no externally pinned root")
        root = matches[0]
        if not root.valid_from_unix <= now < root.valid_until_unix:
            raise AppAdmissionError("publisher key is not yet valid or expired")
        return root

    @_owned_operation
    def admit_bundle_file(self, path: os.PathLike[str] | str, *, now_unix: int) -> VerifiedAppBundle:
        """Read once with nofollow custody, validate complete ZIP, verify signature."""
        archive = _read_snapshot(path)
        payload, assets = _zip_contents(archive)
        value = _manifest(payload)
        if _version(value["minimum_shell_version"], stable=True) > self._shell_version:
            raise AppAdmissionError("app requires a newer shell")
        if value["entrypoint"] not in assets:
            raise AppAdmissionError("entrypoint is absent from content index")
        if content_root_sha256(assets) != value["content_root_sha256"]:
            raise AppAdmissionError("complete asset index SHA-256 mismatch")
        root = self._root(value["publisher"], value["signature"]["key_id"], now_unix)
        _ed25519_verify(root.public_key, _signature_value(value["signature"]["value"]), _signing_bytes(value))
        bundle = object.__new__(VerifiedAppBundle)
        fields = {
            "_issuer": self._issuer, "_assets": assets, "_manifest": payload,
            "_key_id": root.key_id, "_key_pin": root.public_key_sha256,
            **{name: value[name] for name in ("publisher", "app_id", "version", "entrypoint",
                                            "origin_host", "content_root_sha256")},
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "manifest_sha256": hashlib.sha256(payload).hexdigest(),
            "capabilities": tuple(value["capabilities"]),
            "data_schema_version": value.get("data_schema_version"),
        }
        for name, field in fields.items():
            object.__setattr__(bundle, name, field)
        return bundle

    @_owned_operation
    def asset_response(self, bundle: VerifiedAppBundle, url: str, *, now_unix: int,
                       method: str = "GET") -> LocalAssetResponse:
        """Current policy plus exact HTTPS asset URL; no redirect/network fallback."""
        if type(bundle) is not VerifiedAppBundle or getattr(bundle, "_issuer", None) is not self._issuer:
            raise AppAdmissionError("bundle was not admitted by this owner")
        root = self._root(bundle.publisher, bundle._key_id, now_unix)
        if root.public_key_sha256 != bundle._key_pin:
            raise AppAdmissionError("admitted key pin differs from current policy")
        prefix = f"https://{bundle.origin_host}/"
        if (method != "GET" or type(url) is not str or len(url) > len(prefix) + 512
                or not url.startswith(prefix) or any(char in url for char in "%?#\\")):
            raise AppAdmissionError("request is not an exact local HTTPS asset URL")
        path = _asset_path(url[len(prefix):])
        if path not in bundle._assets:
            raise AppAdmissionError("asset is not in the complete signed content index")
        content = bundle._assets[path]
        extension = Path(path).suffix.lower()
        if extension not in _MIME:
            raise AppAdmissionError("asset extension has no supported local response MIME type")
        headers = MappingProxyType({
            "Content-Type": _MIME[extension],
            "Content-Length": str(len(content)), "Content-Security-Policy": RESTRICTIVE_CSP,
            "X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy": "same-origin",
            "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
        })
        return LocalAssetResponse(path, content, headers)
