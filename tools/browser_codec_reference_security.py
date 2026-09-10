#!/usr/bin/env python3
"""Race-safe repository I/O and strict JSON helpers for codec evidence gates."""

from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Callable, IO

ROOT = Path(__file__).resolve().parents[1]

_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)

AfterComponentHook = Callable[[int, str, int], None]
_JSON_DUMPS = json.dumps
_JSON_DUMP = json.dump


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number: {value}")
    return parsed


def load_json_strict(value: object) -> object:
    """Decode JSON without duplicate members or non-finite numbers."""

    options = {
        "object_pairs_hook": _reject_duplicate_json_keys,
        "parse_constant": _reject_non_json_constant,
        "parse_float": _parse_finite_float,
    }
    if hasattr(value, "read"):
        return json.load(value, **options)  # type: ignore[arg-type]
    return json.loads(value, **options)  # type: ignore[arg-type]


def strict_json_dumps(value: object, *args: object, **kwargs: object) -> str:
    """Serialize evidence with non-finite values forbidden."""

    kwargs["allow_nan"] = False
    return _JSON_DUMPS(value, *args, **kwargs)


def strict_json_dump(
    value: object,
    stream: IO[str],
    *args: object,
    **kwargs: object,
) -> None:
    kwargs["allow_nan"] = False
    _JSON_DUMP(value, stream, *args, **kwargs)


class StrictJsonProxy:
    """Small module-like proxy used by the legacy audit implementation."""

    JSONDecodeError = json.JSONDecodeError

    @staticmethod
    def dumps(value: object, *args: object, **kwargs: object) -> str:
        return strict_json_dumps(value, *args, **kwargs)

    @staticmethod
    def dump(
        value: object,
        stream: IO[str],
        *args: object,
        **kwargs: object,
    ) -> None:
        strict_json_dump(value, stream, *args, **kwargs)

    @staticmethod
    def loads(value: object, *args: object, **kwargs: object) -> object:
        if args or kwargs:
            raise TypeError("strict JSON proxy does not accept decoder overrides")
        return load_json_strict(value)

    @staticmethod
    def load(value: object, *args: object, **kwargs: object) -> object:
        if args or kwargs:
            raise TypeError("strict JSON proxy does not accept decoder overrides")
        return load_json_strict(value)


STRICT_JSON = StrictJsonProxy()


def repo_path(
    value: object,
    *,
    label: str = "repository-relative path",
    root: Path = ROOT,
) -> Path:
    """Return one canonical lexical path confined below ``root``."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    if "\\" in value or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} contains unsafe characters")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or not parsed.parts
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or parsed.as_posix() != value
    ):
        raise ValueError(f"{label} must be a canonical repository-relative path")
    return root.joinpath(*parsed.parts)


def _relative_parts(root: Path, path: Path, *, label: str) -> tuple[str, ...]:
    root = Path(os.path.abspath(os.fspath(root)))
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = Path(os.path.normpath(os.fspath(candidate)))
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes the pinned repository root") from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{label} is not a canonical repository file")
    return tuple(relative.parts)


def open_regular_beneath(
    root: Path,
    path: Path,
    *,
    label: str,
    after_component: AfterComponentHook | None = None,
) -> int:
    """Open a regular file through pinned directory descriptors.

    Every parent is opened relative to the previously pinned descriptor with
    ``O_DIRECTORY|O_NOFOLLOW``; the leaf is opened with ``O_NOFOLLOW``. A
    pathname rename or symlink swap cannot redirect a later component lookup
    outside the already-open directory chain.
    """

    parts = _relative_parts(root, path, label=label)
    root_flags = os.O_RDONLY | _O_CLOEXEC | _O_DIRECTORY | _O_NOFOLLOW
    try:
        directory_fd = os.open(root, root_flags)
    except OSError as error:
        raise ValueError(f"{label} repository root is unsafe or unreadable") from error

    try:
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
            raise ValueError(f"{label} repository root is not a directory")

        for index, component in enumerate(parts[:-1]):
            try:
                next_fd = os.open(
                    component,
                    os.O_RDONLY | _O_CLOEXEC | _O_DIRECTORY | _O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except OSError as error:
                raise ValueError(
                    f"{label} parent is absent, non-directory, or symlinked: {component}"
                ) from error
            try:
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise ValueError(f"{label} parent is not a directory: {component}")
                if after_component is not None:
                    after_component(index, component, next_fd)
            except BaseException:
                os.close(next_fd)
                raise
            os.close(directory_fd)
            directory_fd = next_fd

        leaf = parts[-1]
        try:
            descriptor = os.open(
                leaf,
                os.O_RDONLY | _O_CLOEXEC | _O_NONBLOCK | _O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError as error:
            raise ValueError(
                f"{label} leaf is absent, unsafe, or symlinked: {leaf}"
            ) from error
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"{label} is not a regular file: {path}")
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise
    finally:
        os.close(directory_fd)


def _open_regular(path: Path, *, label: str) -> int:
    return open_regular_beneath(ROOT, path, label=label)


def read_bytes_beneath(
    root: Path,
    path: Path,
    *,
    label: str = "source file",
    after_component: AfterComponentHook | None = None,
) -> bytes:
    descriptor = open_regular_beneath(
        root,
        path,
        label=label,
        after_component=after_component,
    )
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_text_nofollow(path: Path, *, label: str = "source file") -> str:
    descriptor = _open_regular(path, label=label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_bytes_nofollow(path: Path, *, label: str = "source file") -> bytes:
    descriptor = _open_regular(path, label=label)
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_json_nofollow(path: Path, *, label: str = "JSON source") -> object:
    descriptor = _open_regular(path, label=label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return load_json_strict(stream)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def regular_file_exists_nofollow(path: Path, *, label: str) -> bool:
    try:
        descriptor = _open_regular(path, label=label)
    except ValueError:
        return False
    os.close(descriptor)
    return True


def sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(read_bytes_nofollow(path, label="hashed source")).hexdigest()


def git_blob_sha1(path: Path) -> str:
    import hashlib

    payload = read_bytes_nofollow(path, label="Git-blob source")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()
