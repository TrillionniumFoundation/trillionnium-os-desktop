#!/usr/bin/env python3
"""Load the reviewed D3 validator from fixed, non-executable source fragments."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

_PARTS = (
    "_validate_d3_development_profile_impl.000.part",
    "_validate_d3_development_profile_impl.001.part",
    "_validate_d3_development_profile_impl.002.part",
)
_EXPECTED_SHA256 = "72cac859b6517395da344e94a66fb6dd3849c4b794610c446d282569ec385787"


def _read_fragment(name: str) -> bytes:
    path = Path(__file__).with_name(name)
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"D3 validator fragment is not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


_source = b"".join(_read_fragment(name) for name in _PARTS)
_actual = hashlib.sha256(_source).hexdigest()
if _actual != _EXPECTED_SHA256:
    raise RuntimeError(
        f"D3 validator source digest mismatch: expected {_EXPECTED_SHA256}, observed {_actual}"
    )
exec(compile(_source, __file__, "exec"), globals())
