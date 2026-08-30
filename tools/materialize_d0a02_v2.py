#!/usr/bin/env python3
from __future__ import annotations

import base64
import gzip
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "tools/.d0a02-materialize"
EXPECTED_OLD_SOURCE_BLOB = "5ac11b316863963b48ef0f6e24691c30b21b27de"
TARGETS = {
    "source": (
        ROOT / "experiments/servo-headed-runtime/src/main.rs",
        83524,
        "1bd388867565641ed38744757dedd0ad59a6f679b193c7d99ed5751a993c7013",
        "971b5db93e6a8b8eee7a37f69420953ecccd4d55",
        6,
    ),
    "fixture": (
        ROOT / "experiments/servo-headed-runtime/fixture/index.html",
        3039,
        "9a1cb3aeebec41914efb5fc45e3d9a58a8166fd2d287a5f673c28611ece24d47",
        "febfe7664f6a8494d3e99c75cf88951abbf3055c",
        1,
    ),
    "workflow": (
        ROOT / ".github/workflows/servo-headed-runtime.yml",
        24852,
        "0513294108dfe99ae5414739d78f60092ca92441bc9d33002cf53bd0c3681199",
        "b66bbb580edfff9d5cade896de62220ff92c40fc",
        3,
    ),
    "architecture": (
        ROOT / "docs/architecture/TRUSTED_WORKSPACE_COMPOSITION.md",
        4472,
        "3ab949e9946237428c25c5d63d4bc4a6fd2a27014397c7fa75125e964be9bab3",
        "b8bea40b42c5bd7e1b3178684d5352624ac6aff6",
        1,
    ),
}


def git_blob_sha(data: bytes) -> str:
    prefix = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + data).hexdigest()


def decode_parts(name: str, count: int) -> bytes:
    expected = [PARTS / f"{name}.part{index:02d}" for index in range(count)]
    actual = sorted(PARTS.glob(f"{name}.part*"))
    if actual != expected:
        raise SystemExit(f"{name}: part set mismatch: actual={actual}, expected={expected}")
    encoded = "".join(path.read_text(encoding="ascii").strip() for path in expected)
    return gzip.decompress(base64.b64decode(encoded, validate=True))


def validate(data: bytes, size: int, sha256: str, blob_sha: str, label: str) -> None:
    actual = (len(data), hashlib.sha256(data).hexdigest(), git_blob_sha(data))
    expected = (size, sha256, blob_sha)
    if actual != expected:
        raise SystemExit(f"{label}: digest mismatch: actual={actual}, expected={expected}")


old_source = TARGETS["source"][0].read_bytes()
if git_blob_sha(old_source) != EXPECTED_OLD_SOURCE_BLOB:
    raise SystemExit("refusing to overwrite an unexpected D0A-02 source revision")

materialized: dict[Path, bytes] = {}
for name, (path, size, sha256, blob_sha, part_count) in TARGETS.items():
    data = decode_parts(name, part_count)
    validate(data, size, sha256, blob_sha, name)
    materialized[path] = data

for path, data in materialized.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if path.read_bytes() != data:
        raise SystemExit(f"{path}: post-write byte verification failed")

for name, (path, size, sha256, blob_sha, _part_count) in TARGETS.items():
    validate(path.read_bytes(), size, sha256, blob_sha, f"post-write {name}")
    print(f"PASS {name} bytes={size} sha256={sha256} git_blob={blob_sha}")
