"""Bounded offline binding of carried D1 source bytes to Git commit identity.

This inspects data only. It neither executes the archive nor trusts a locally
available Git repository, network service, tar extraction, or caller tree hash.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile

try:
    from .artifact_evidence import artifact_file, safe_relative
    from .browser_codec_reference_security import _open_regular_owned_beneath
except ImportError:
    from artifact_evidence import artifact_file, safe_relative
    from browser_codec_reference_security import _open_regular_owned_beneath

ARCHIVE = "source/source.tar"
COMMIT = "source/tested-commit.raw"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_COMMIT_BYTES = 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILES = 4096
HEX = re.compile(rb"[0-9a-f]{40}\Z")


def _read(path: Path, limit: int) -> bytes:
    # Keep the private owner through the whole read; no raw-int result handoff
    # or externally accessible concurrent close is involved in this consumer.
    owner = _open_regular_owned_beneath(Path("/"), path.absolute(), label="D1 source proof")
    try:
        descriptor = owner.fd
        if descriptor is None:
            raise ValueError("D1 source proof descriptor is absent")
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise ValueError("D1 source proof must be regular, single-link and within its byte bound")
        chunks, total = [], 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise ValueError("D1 source proof exceeds its byte bound")
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or total != before.st_size:
            raise ValueError("D1 source proof changed while reading")
        return b"".join(chunks)
    finally:
        owner.close()


def _oid(kind: bytes, payload: bytes) -> bytes:
    return hashlib.sha1(kind + b" " + str(len(payload)).encode("ascii") + b"\0" + payload).digest()


def _tree(nodes: dict) -> bytes:
    payload = bytearray()
    for name, item in sorted(nodes.items(), key=lambda row: row[0].encode("utf-8") + (b"/" if isinstance(row[1], dict) else b"")):
        mode, oid = (b"40000", _tree(item)) if isinstance(item, dict) else item
        payload.extend(mode + b" " + name.encode("utf-8") + b"\0" + oid)
    return _oid(b"tree", bytes(payload))


def _commit_identity(payload: bytes) -> tuple[str, list[str]]:
    header, separator, _message = payload.partition(b"\n\n")
    if not separator or b"\0" in payload:
        raise ValueError("D1 raw Git commit header is malformed")
    lines = header.split(b"\n")
    if not lines or not lines[0].startswith(b"tree ") or HEX.fullmatch(lines[0][5:]) is None:
        raise ValueError("D1 raw Git commit tree header is malformed")
    parents, index = [], 1
    while index < len(lines) and lines[index].startswith(b"parent "):
        value = lines[index][7:]
        if HEX.fullmatch(value) is None:
            raise ValueError("D1 raw Git commit parent is malformed")
        parents.append(value.decode("ascii"))
        index += 1
    remainder = lines[index:]
    if any(line.startswith((b"tree ", b"parent ")) for line in remainder):
        raise ValueError("D1 raw Git commit has misplaced identity headers")
    if sum(line.startswith(b"author ") for line in remainder) != 1 or sum(line.startswith(b"committer ") for line in remainder) != 1:
        raise ValueError("D1 raw Git commit author/committer headers are absent or duplicated")
    return lines[0][5:].decode("ascii"), parents


def _archive_name(value: str, *, directory: bool) -> str:
    # Check tar/PAX spelling before normalizing one directory terminator.
    if len(value.encode("utf-8")) > 4096:
        raise ValueError("D1 source archive path exceeds its bound")
    name = value.removesuffix("/") if directory else value
    result = safe_relative(name).as_posix()
    if len(result.split("/")) > 64:
        raise ValueError("D1 source archive path exceeds its bound")
    return result


def _validate_tar_headers(payload: bytes) -> None:
    # tarfile normalizes directory names before exposing TarInfo. Inspect
    # bounded physical headers too; PAX effective names are checked below.
    if len(payload) % 512:
        raise ValueError("D1 source tar is not a complete block sequence")
    offset = 0
    while offset < len(payload):
        header = payload[offset:offset + 512]
        if not any(header):
            if any(payload[offset:]):
                raise ValueError("D1 source tar hides bytes after its end marker")
            return
        try:
            member = tarfile.TarInfo.frombuf(header, "utf-8", "surrogateescape")
        except tarfile.HeaderError as error:
            raise ValueError("D1 source tar header is malformed") from error
        if header[257:263] == b"ustar " or member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE, tarfile.XHDTYPE, tarfile.XGLTYPE}:
            raise ValueError("D1 source tar uses an unsupported GNU, link or special header")
        if member.size < 0 or member.size > MAX_ARCHIVE_BYTES:
            raise ValueError("D1 source tar header size exceeds its bound")
        if member.type in {tarfile.XHDTYPE, tarfile.XGLTYPE}:
            end = offset + 512 + member.size
            if member.size > 1024 * 1024 or end > len(payload):
                raise ValueError("D1 source PAX metadata exceeds its bound or is truncated")
            body = payload[offset + 512:end]
            position, keys = 0, set()
            while position < len(body):
                marker = body.find(b" ", position, position + 10)
                number = body[position:marker] if marker != -1 else b""
                if not number or not number.isdigit() or number.startswith(b"0"):
                    raise ValueError("D1 source PAX record length is malformed")
                stop = position + int(number)
                if stop > len(body) or stop <= marker + 1 or body[stop - 1:stop] != b"\n":
                    raise ValueError("D1 source PAX record is malformed")
                key, separator, value = body[marker + 1:stop - 1].partition(b"=")
                if not separator or not key or key in keys or len(keys) >= MAX_FILES or b"\0" in key + value:
                    raise ValueError("D1 source PAX keys are duplicated, malformed or over their bound")
                keys.add(key)
                if key.startswith(b"GNU.sparse.") or key == b"size":
                    raise ValueError("D1 source PAX sparse or size override is unsupported")
                if key == b"path":
                    _archive_name(value.decode("utf-8", "strict"), directory=True)
                position = stop
        if member.type in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE}:
            name = header[:100].split(b"\0", 1)[0]
            prefix = header[345:500].split(b"\0", 1)[0] if header[257:263] == b"ustar\0" else b""
            effective = ((prefix + b"/") if prefix else b"") + name
            _archive_name(effective.decode("utf-8", "strict"), directory=member.isdir())
            if member.isdir() and member.size:
                raise ValueError("D1 source directory header has an unexpected payload")
        offset += 512 + ((member.size + 511) // 512) * 512
        if offset > len(payload):
            raise ValueError("D1 source tar member payload is truncated")
    raise ValueError("D1 source tar end marker is absent")


def verify_source(root: Path, receipt: dict, source_files: dict[str, str]) -> None:
    archive_bytes = _read(artifact_file(root, ARCHIVE), MAX_ARCHIVE_BYTES)
    raw_commit = _read(artifact_file(root, COMMIT), MAX_COMMIT_BYTES)
    proof = receipt.get("source_provenance")
    expected = {"schema": "trillionnium.desktop.d1-source-provenance.v1",
                "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
                "commit_sha256": hashlib.sha256(raw_commit).hexdigest()}
    if type(proof) is not dict or proof != expected:
        raise ValueError("D1 source provenance binding is malformed or inconsistent")
    if _oid(b"commit", raw_commit).hex() != receipt["tested_sha"]:
        raise ValueError("D1 raw Git commit does not rebuild the tested SHA")
    commit_tree, parents = _commit_identity(raw_commit)
    if commit_tree != receipt["tree_sha"]:
        raise ValueError("D1 raw Git commit does not bind the declared tree SHA")
    if receipt["evidence_role"] == "pr_synthetic_merge":
        if parents != [receipt["base_sha"], receipt["candidate_head_sha"]]:
            raise ValueError("D1 raw Git merge requires exactly two ordered base/head parents")
    elif receipt["base_sha"] != (parents[0] if parents else "0" * 40):
        raise ValueError("D1 raw Git checkout does not bind its declared first parent")
    if not source_files or len(source_files) > MAX_FILES:
        raise ValueError("D1 source file inventory exceeds its count bound or is empty")
    _validate_tar_headers(archive_bytes)
    expected_nodes: dict = {}
    for relative in source_files:
        parts = _archive_name(relative, directory=False).split("/")
        parent = expected_nodes
        for part in parts[:-1]:
            parent = parent.setdefault(part, {})
            if not isinstance(parent, dict):
                raise ValueError("D1 source manifest file/directory paths conflict")
        if parts[-1] in parent:
            raise ValueError("D1 source manifest file/directory paths conflict")
        parent[parts[-1]] = None
    observed, directories, nodes = set(), set(), {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive:
            if member.sparse is not None or any(key.startswith("GNU.sparse.") for key in member.pax_headers):
                raise ValueError("D1 source archive sparse member is unsupported")
            name = _archive_name(member.name, directory=member.isdir())
            pax_name = member.pax_headers.get("path", member.name)
            if _archive_name(pax_name, directory=member.isdir()) != name:
                raise ValueError("D1 source archive PAX path is inconsistent")
            parts = name.split("/")
            if member.isdir():
                parent = expected_nodes
                for part in parts:
                    parent = parent.get(part) if isinstance(parent, dict) else None
                    if not isinstance(parent, dict):
                        raise ValueError("D1 source archive directory is not a declared file ancestor or has a file/directory conflict")
                if name in directories or name in observed or len(directories) >= MAX_FILES * 64:
                    raise ValueError("D1 source archive directory inventory is duplicated or over its bound")
                directories.add(name)
                continue
            if not member.isfile() or name not in source_files or name in observed or name in directories:
                raise ValueError("D1 source archive contains an unsafe, duplicate or undeclared member")
            if member.mode not in {0o644, 0o664, 0o755, 0o775} or member.size < 0 or member.size > MAX_FILE_BYTES:
                raise ValueError("D1 source archive mode or file size exceeds its bound")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("D1 source archive member payload is absent")
            with stream:
                payload = stream.read(MAX_FILE_BYTES + 1)
            if len(payload) != member.size or hashlib.sha256(payload).hexdigest() != source_files[name]:
                raise ValueError("D1 source archive differs from the declared Git tree source manifest")
            observed.add(name)
            parent = nodes
            for part in parts[:-1]:
                parent = parent.setdefault(part, {})
                if not isinstance(parent, dict):
                    raise ValueError("D1 source archive file/directory paths conflict")
            if parts[-1] in parent:
                raise ValueError("D1 source archive file/directory paths conflict")
            parent[parts[-1]] = (b"100755" if member.mode & 0o111 else b"100644", _oid(b"blob", payload))
    if observed != set(source_files):
        raise ValueError("D1 source archive does not contain every declared source input")
    if _tree(nodes).hex() != receipt["tree_sha"]:
        raise ValueError("D1 source archive bytes and modes do not rebuild the declared Git tree")


def stage_source(repository: Path, root: Path) -> dict[str, str]:
    directory = root / "source"
    directory.mkdir(parents=True, exist_ok=True)
    archive = subprocess.check_output(["git", "archive", "--format=tar", "HEAD"], cwd=repository, timeout=30)
    commit = subprocess.check_output(["git", "cat-file", "commit", "HEAD"], cwd=repository, timeout=30)
    if len(archive) > MAX_ARCHIVE_BYTES or len(commit) > MAX_COMMIT_BYTES:
        raise ValueError("D1 producer source archive or commit exceeds its byte bound")
    (root / ARCHIVE).write_bytes(archive)
    (root / COMMIT).write_bytes(commit)
    return {"schema": "trillionnium.desktop.d1-source-provenance.v1",
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "commit_sha256": hashlib.sha256(commit).hexdigest()}
