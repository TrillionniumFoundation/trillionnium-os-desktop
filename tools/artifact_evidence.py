"""Closed, path-confined checks shared by portable qualification artifacts."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .browser_codec_reference_security import load_json_strict, open_regular_beneath
except ImportError:
    from browser_codec_reference_security import load_json_strict, open_regular_beneath

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_FILE_BYTES = 8 * 1024 * 1024 * 1024


def workflow_reference(reference: object) -> str:
    owner = "TrillionniumFoundation/trillionnium-os-desktop"
    prefix = owner + "/"
    if not isinstance(reference, str) or not reference.startswith(prefix):
        raise ValueError("GITHUB_WORKFLOW_REF does not identify the expected repository")
    path, marker, ref = reference[len(prefix):].partition("@")
    _workflow_path(path)
    if not marker or not ref.startswith("refs/") or len(ref) <= len("refs/") or "@" in ref or any(ord(char) < 0x20 or ord(char) == 0x7f for char in ref):
        raise ValueError("GITHUB_WORKFLOW_REF has an invalid workflow ref")
    return path


def producer_workflow(repository: Path) -> dict[str, str]:
    reference = os.environ.get("GITHUB_WORKFLOW_REF")
    path = workflow_reference(reference)
    workflow_sha = os.environ.get("GITHUB_WORKFLOW_SHA")
    if not isinstance(workflow_sha, str) or SHA1.fullmatch(workflow_sha) is None or workflow_sha != os.environ.get("TESTED_SHA"):
        raise ValueError("executing workflow commit does not bind the tested checkout")
    return {"path": path, "ref": reference, "workflow_sha": workflow_sha,
            "sha256": digest(repository / path)}


def _workflow_path(path: object) -> str:
    value = safe_relative(path)
    if len(value.parts) != 3 or value.parts[:2] != (".github", "workflows") or value.suffix not in {".yml", ".yaml"}:
        raise ValueError("producer workflow path is outside .github/workflows")
    return value.as_posix()


def verify_workflow_binding(binding: object, source_files: dict[str, str], *, producer: bool, tested_sha: str | None = None) -> None:
    fields = {"path", "sha256", "ref", "workflow_sha"} if producer else {"path", "sha256"}
    if not isinstance(binding, dict) or set(binding) != fields:
        raise ValueError("workflow provenance has a malformed field set")
    path = _workflow_path(binding["path"])
    if not isinstance(binding["sha256"], str) or SHA256.fullmatch(binding["sha256"]) is None or source_files.get(path) != binding["sha256"]:
        raise ValueError("workflow provenance digest is not bound to the source manifest")
    if producer:
        reference = binding["ref"]
        if workflow_reference(reference) != path:
            raise ValueError("producer workflow ref does not bind its recorded path")
        workflow_sha = binding.get("workflow_sha")
        if not isinstance(workflow_sha, str) or SHA1.fullmatch(workflow_sha) is None or workflow_sha != tested_sha:
            raise ValueError("producer workflow commit does not bind the tested SHA")


def validate_source_identity(repository: Path) -> None:
    def git(*arguments: str) -> str:
        return subprocess.check_output(["git", *arguments], cwd=repository, text=True,
                                       timeout=30).strip()
    if git("rev-parse", "HEAD") != os.environ.get("TESTED_SHA") or git("rev-parse", "HEAD^{tree}") != os.environ.get("TESTED_TREE_SHA"):
        raise ValueError("declared tested identity does not bind the repository HEAD and tree")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repository,
                      timeout=30, check=False).returncode != 0:
        raise ValueError("tracked source inputs differ from the tested Git tree")


def open_file(path: Path) -> int:
    # Pin every absolute component, including ancestors of the artifact root.
    descriptor = open_regular_beneath(Path("/"), path.absolute(), label="artifact file")
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        os.close(descriptor)
        raise ValueError("artifact file must be regular and have exactly one hard link")
    return descriptor


def file_size(path: Path) -> int:
    descriptor = open_file(path)
    try:
        return os.fstat(descriptor).st_size
    finally:
        os.close(descriptor)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with os.fdopen(open_file(path), "rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > MAX_ARTIFACT_FILE_BYTES:
            raise ValueError("artifact file is over its byte bound")
        total = 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if total > MAX_ARTIFACT_FILE_BYTES:
                raise ValueError("artifact file grew over its byte bound")
            value.update(chunk)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or total != before.st_size:
            raise ValueError("artifact file changed while hashing")
    return value.hexdigest()


def load(path: Path) -> dict[str, Any]:
    with os.fdopen(open_file(path), "rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > MAX_JSON_BYTES:
            raise ValueError("artifact JSON is over its byte bound")
        data = stream.read(MAX_JSON_BYTES + 1)
        after = os.fstat(stream.fileno())
        if len(data) > MAX_JSON_BYTES:
            raise ValueError("artifact JSON grew over its byte bound")
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(data) != before.st_size:
            raise ValueError("artifact JSON changed while reading")
    text = data.decode("utf-8", "strict")
    if text.startswith("\ufeff"):
        raise ValueError("artifact JSON cannot have a UTF-8 BOM")
    value = load_json_strict(text)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def safe_relative(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or value != value.strip() or "\\" in value or any(ord(char) < 0x20 or ord(char) == 0x7f for char in value):
        raise ValueError(f"unsafe artifact path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value or value == ".":
        raise ValueError(f"unsafe or noncanonical artifact path: {value!r}")
    return path


def artifact_root(path: Path) -> Path:
    # Check the spelling before resolving; resolving first loses symlink evidence.
    absolute = path.absolute()
    for ancestor in (absolute, *absolute.parents):
        if ancestor.is_symlink():
            raise ValueError(f"artifact root traverses a symbolic link: {ancestor}")
    if not absolute.is_dir():
        raise ValueError(f"artifact root is absent: {absolute}")
    return absolute.resolve()


def artifact_destination(path: Path, sources: tuple[Path, ...]) -> Path:
    absolute = path.absolute()
    for ancestor in (absolute, *absolute.parents):
        if ancestor.is_symlink():
            raise ValueError(f"artifact destination traverses a symbolic link: {ancestor}")
    destination = absolute.resolve()
    for source in sources:
        source = source.resolve()
        if destination == source or destination in source.parents or source in destination.parents:
            raise ValueError("artifact destination overlaps a source directory")
    return destination


def artifact_file(root: Path, relative: object) -> Path:
    path = root / safe_relative(relative)
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"artifact path traverses a symbolic link: {relative!r}")
    descriptor = open_file(path)
    os.close(descriptor)
    return path


def verify_outputs(root: Path, receipt: str, outputs: object, *, sized: bool) -> None:
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("receipt output digest map is absent")
    for relative, expected in outputs.items():
        if relative == receipt:
            raise ValueError("receipt cannot recursively bind itself")
        path = artifact_file(root, relative)
        if sized:
            if not isinstance(expected, dict) or set(expected) != {"sha256", "bytes"}:
                raise ValueError(f"malformed output digest: {relative!r}")
            size = expected["bytes"]
            if type(size) is not int or size < 0 or file_size(path) != size:
                raise ValueError(f"artifact size mismatch: {relative!r}")
            expected = expected["sha256"]
        if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
            raise ValueError(f"malformed SHA-256: {relative!r}")
        if digest(path) != expected:
            raise ValueError(f"artifact digest mismatch: {relative!r}")
    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"artifact contains a symbolic link: {path.relative_to(root)}")
        if path.is_file() and path.relative_to(root).as_posix() != receipt:
            actual.add(path.relative_to(root).as_posix())
        elif not path.is_file() and not path.is_dir():
            raise ValueError("artifact contains a nonregular special file")
    if actual != set(outputs):
        raise ValueError("artifact file inventory is not exactly bound by output digests")


def validate_role(receipt: dict[str, Any]) -> None:
    role = receipt.get("evidence_role")
    authoritative = receipt.get("promotion_authoritative")
    if type(authoritative) is not bool:
        raise ValueError("promotion_authoritative is not boolean")
    if receipt.get("repository") != "TrillionniumFoundation/trillionnium-os-desktop":
        raise ValueError("receipt repository identity is wrong")
    for key in ("tested_sha", "candidate_head_sha", "base_sha", "tree_sha"):
        value = receipt.get(key)
        if not isinstance(value, str) or SHA1.fullmatch(value) is None:
            raise ValueError(f"receipt {key} is not a lowercase Git SHA-1")
    if role == "exact_main_push":
        if receipt.get("event_name") != "push" or receipt.get("ref") != "refs/heads/main" or not authoritative or receipt["tested_sha"] != receipt["candidate_head_sha"]:
            raise ValueError("exact-main receipt does not identify authoritative main")
    elif role == "pr_synthetic_merge":
        ref = receipt.get("ref")
        if authoritative or receipt.get("event_name") != "pull_request" or not isinstance(ref, str) or re.fullmatch(r"refs/pull/[1-9][0-9]*/merge", ref) is None or receipt["tested_sha"] == receipt["candidate_head_sha"]:
            raise ValueError("pull-request receipt does not bind its synthetic merge identity")
    elif role == "manual_non_authoritative":
        if authoritative:
            raise ValueError("non-main receipt is marked authoritative")
        if receipt.get("event_name") != "workflow_dispatch" or receipt["tested_sha"] != receipt["candidate_head_sha"]:
            raise ValueError("manual receipt does not bind its checkout identity")
    else:
        raise ValueError(f"unknown evidence role: {role!r}")
