#!/usr/bin/env python3
"""Import exact v13 immutable Git objects; deliberately never update a ref."""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import lzma
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
BASE_COMMIT = "ff4fe3aa072fec521d0ed22dd63408f5bb38d0b5"
BASE_TREE = "c922e84bbe68455040189ac2e16bee42aa1692fc"
TARGET_TREE = "823c6a082b2b998229c49ce883669a7b47eae8e2"
PATCH_SIZE = 1_042_824
PATCH_SHA256 = "0e5a1c0e0ea5186ee0ea4287634f5fdf343085a04bd055af3c0689b08c4d6297"
XZ_SIZE = 173_588
XZ_SHA256 = "db44ac6750a575b42dacbd111b7ec6447fb12bac70ba7f50d232df2c857ea305"
PART_OIDS = [
    "d30a694d362702f85a8c66b305d04750ceb8ed07",
    "0855cb88fb683d812916eba3879c6136d21f5bf6",
    "e658c0a64fa40b482e60b64c793849079ef891cc",
    "9a9e5dafd8092e83aa7edc62b333af6de1403c98",
    "fd76a27710fbd2d0e041e07970ae21aa4eb194ba",
    "d80fd84f06d81c6157b69049df4460ab8875ae0a",
    "65aa3e30cb010fe55784da1550658fefbca1f498",
    "619dacea48799ea2ce54d42629a71e49a789ff8f",
    "773fde414f57cbbf9dd4f5c4df555313bae4dad1",
    "940f92ae2997ac34ffbc179bafc46d871f20943f",
    "7f2668c47039bed7aaaf9a6190db7ec4a0896617",
    "df6c3cdfbd3eb9d4ccf6a4fb2b1f572679950dca",
    "20f77cc92ff0ffda46fdf3e90c48dcb24b5a8902",
    "3429070865a6e3d883f651ca5957e3acfd8c8e2d",
    "69201dbc1ff69b99f1cf508c6966aff81edf6689",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args],
        input=data,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def blob_oid(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("unexpected GitHub API redirect")


OPENER = urllib.request.build_opener(NoRedirect())


def api(path: str, payload: dict[str, object]) -> dict[str, object]:
    require(path in {"git/blobs", "git/trees"}, "immutable Git object endpoint required")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/{path}",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "trillionnium-v13-immutable-object-import",
        },
    )
    try:
        with OPENER.open(request, timeout=120) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(65_536).decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API {error.code}: {detail}") from error
    require(len(raw) <= 8 * 1024 * 1024, "GitHub API response too large")
    value = json.loads(raw)
    require(isinstance(value, dict), "GitHub API response must be an object")
    return value


def main() -> None:
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "wrong repository")
    transport = Path(".github/v13-import")
    chunks: list[bytes] = []
    for index, expected_oid in enumerate(PART_OIDS):
        path = transport / f"part-{index:02d}.bin"
        data = path.read_bytes()
        expected_size = 1_556 if index == 14 else 12_288
        require(len(data) == expected_size, f"transport size mismatch: {path}")
        require(blob_oid(data) == expected_oid, f"transport object mismatch: {path}")
        chunks.append(data)
        print(f"verified transport {path.name} {expected_oid}", flush=True)

    compressed = b"".join(chunks)
    require(len(compressed) == XZ_SIZE, "compressed size mismatch")
    require(hashlib.sha256(compressed).hexdigest() == XZ_SHA256, "compressed digest mismatch")
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=256 * 1024 * 1024)
    patch = decoder.decompress(compressed, max_length=PATCH_SIZE + 1)
    require(decoder.eof and not decoder.unused_data, "compressed stream incomplete or trailing")
    require(len(patch) == PATCH_SIZE, "patch size mismatch")
    require(hashlib.sha256(patch).hexdigest() == PATCH_SHA256, "patch digest mismatch")

    git("checkout", "--detach", BASE_COMMIT)
    require(git("rev-parse", "HEAD").decode().strip() == BASE_COMMIT, "base commit drift")
    require(git("rev-parse", "HEAD^{tree}").decode().strip() == BASE_TREE, "base tree drift")
    require(not git("status", "--porcelain"), "base checkout is not clean")
    git("apply", "--check", "--cached", "--unidiff-zero", "--whitespace=error-all", "-", data=patch)
    git("apply", "--cached", "--unidiff-zero", "--whitespace=error-all", "-", data=patch)
    require(git("write-tree").decode().strip() == TARGET_TREE, "local target tree mismatch")

    changed = [p for p in git("diff", "--cached", "--name-only", "-z", "HEAD").split(b"\0") if p]
    require(len(changed) == 153, "changed path count mismatch")
    index: dict[bytes, tuple[str, str]] = {}
    for item in git("ls-files", "--stage", "-z").split(b"\0"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        require(stage == b"0", "unmerged index entry")
        index[path] = (mode.decode("ascii"), oid.decode("ascii"))

    entries: list[dict[str, str]] = []
    for raw_path in changed:
        require(raw_path in index, "unexpected source deletion")
        mode, oid = index[raw_path]
        require(mode in {"100644", "100755"}, "unexpected source mode")
        entries.append({"path": raw_path.decode("utf-8"), "mode": mode, "type": "blob", "sha": oid})

    def upload(entry: dict[str, str]) -> None:
        data = git("cat-file", "blob", entry["sha"])
        require(blob_oid(data) == entry["sha"], "local source object mismatch")
        result = api("git/blobs", {
            "content": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
        })
        require(result.get("sha") == entry["sha"], f"remote source object mismatch: {entry['path']}")
        print(f"imported {entry['path']} {entry['sha']}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(upload, entries))

    result = api("git/trees", {"base_tree": BASE_TREE, "tree": entries})
    require(result.get("sha") == TARGET_TREE, "remote target tree mismatch")
    print("IMPORTED_SOURCE_TREE=" + TARGET_TREE, flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        Path(summary).write_text(
            "## Exact v13 immutable source objects imported\n\n"
            f"Tree: `{TARGET_TREE}`\n\n"
            "153 source objects were digest-checked and imported. No source ref, pull request, "
            "approval, merge, product gate, hardware evidence, or release state was changed.\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
