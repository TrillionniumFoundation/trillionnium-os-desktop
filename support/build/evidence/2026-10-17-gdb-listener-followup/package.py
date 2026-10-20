#!/usr/bin/env python3
"""Package explicitly frozen checksum groups and distinct native byte payloads.

No directory discovery, archived-code execution, Git operation, compilation,
VM launch, extraction, or network operation is performed.
"""
import argparse
import contextlib
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile

CHUNK = 2 * 1024 * 1024
HEX = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def canonical(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("noncanonical member path")
    p = PurePosixPath(name)
    if not p.parts or p.is_absolute() or p.as_posix() != name or any(c in ("", ".", "..") for c in p.parts):
        raise ValueError("unsafe member path: " + name)
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("control character in path")
    if any(c in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache") for c in p.parts) or name.endswith((".pyc", ".pyo")):
        raise ValueError("execution-generated cache listed as evidence: " + name)
    return name


def identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


@contextlib.contextmanager
def stable_file(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("input must have an absolute canonical nonsymlink path: " + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("input is not a regular file: " + str(path))
        if identity(before) != identity(path.stat(follow_symlinks=False)):
            raise ValueError("input changed while opening: " + str(path))
        yield stream, before
        after = os.fstat(stream.fileno())
        if identity(before) != identity(after) or identity(after) != identity(path.stat(follow_symlinks=False)):
            raise ValueError("input changed while reading: " + str(path))


def hash_file(path):
    digest = hashlib.sha256()
    with stable_file(path) as (stream, meta):
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
        return digest.hexdigest(), meta.st_size, stat.S_IMODE(meta.st_mode)


def bytes_file(path):
    with stable_file(path) as (stream, _):
        return stream.read()


def sums(data):
    result = []
    seen = set()
    for line in data.decode("utf-8", errors="strict").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("checksum line must be lowercase SHA256, two spaces, canonical path")
        digest, name = match.groups()
        canonical(name)
        if name in seen or name == "SHA256SUMS":
            raise ValueError("duplicate or self-referential checksum member: " + name)
        seen.add(name)
        result.append((name, digest))
    if not result:
        raise ValueError("empty checksum group")
    return result


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def plan(config):
    if config.get("schema") != 1:
        raise ValueError("expected packaging configuration schema 1")
    entries, groups, artifacts, documents = [], [], [], []
    seen_groups = set()
    for group in config.get("groups", []):
        name = group["name"]
        if not IDENTIFIER.fullmatch(name) or name in seen_groups:
            raise ValueError("invalid or duplicate group name")
        seen_groups.add(name)
        root = Path(group["root"])
        if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
            raise ValueError("group root must be a canonical existing directory")
        sum_name = canonical(group.get("checksum_file", "SHA256SUMS"))
        sum_path = root / sum_name
        raw_sum = bytes_file(sum_path)
        sum_sha = hashlib.sha256(raw_sum).hexdigest()
        if sum_sha != group["expected_checksum_sha256"]:
            raise ValueError("frozen checksum file differs: " + name)
        members = sums(raw_sum)
        if len(members) != group["expected_members"]:
            raise ValueError("frozen checksum member count differs: " + name)
        if any(member == sum_name for member, _ in members):
            raise ValueError("group checksum self-reference")
        group_rows = [(sum_name, sum_sha), *members]
        for member, expected in group_rows:
            path = root / member
            digest, size, mode = hash_file(path)
            if digest != expected:
                raise ValueError("frozen member differs: " + name + "/" + member)
            entries.append({"path": canonical("groups/" + name + "/" + member),
                            "source": str(path), "sha256": digest, "bytes": size,
                            "mode": mode, "group": name})
        groups.append({"name": name, "checksum_file": "groups/" + name + "/" + sum_name,
                       "checksum_sha256": sum_sha, "checksum_members": len(members),
                       "retained_regular_members": len(group_rows)})
    payloads = {}
    roles = set()
    for artifact in config.get("artifacts", []):
        role = artifact["role"]
        if not isinstance(role, str) or not role or role in roles:
            raise ValueError("empty or duplicate artifact role")
        roles.add(role)
        if not HEX.fullmatch(artifact["sha256"]) or not isinstance(artifact["bytes"], int) or artifact["bytes"] < 0:
            raise ValueError("artifact requires complete expected SHA256/size")
        digest, size, mode = hash_file(artifact["source"])
        if (digest, size) != (artifact["sha256"], artifact["bytes"]):
            raise ValueError("artifact bytes differ: " + role)
        archive_name = "artifacts/" + digest
        if digest not in payloads:
            row = {"path": archive_name, "source": artifact["source"], "sha256": digest,
                   "bytes": size, "mode": 0o644, "kind": "distinct-native-payload"}
            payloads[digest] = row
            entries.append(row)
        elif payloads[digest]["bytes"] != size:
            raise ValueError("same digest with differing payload size")
        artifacts.append({**artifact, "source_mode": mode, "member": archive_name,
                          "retained": True})
    omissions = config.get("omissions", [])
    for omission in omissions:
        role = omission["role"]
        if not isinstance(role, str) or not role or role in roles or not omission.get("reason"):
            raise ValueError("omissions require distinct nonempty role and actual reason")
        roles.add(role)
        if omission.get("retained") not in (None, False):
            raise ValueError("omitted payload cannot be marked retained")
    document_names = set()
    for document in config.get("documents", []):
        name = canonical(document["path"])
        if len(PurePosixPath(name).parts) != 1 or name in ("archive", "SHA256SUMS", "capture-status.json", "manifest.json", "packaging-config.json", "package.py", "verify.py", "packaging-failure.json") or name in document_names:
            raise ValueError("invalid or reserved standalone document name")
        document_names.add(name)
        digest, size, mode = hash_file(document["source"])
        if (digest, size) != (document["sha256"], document["bytes"]) or size > CHUNK:
            raise ValueError("standalone document differs or exceeds 2MiB: " + name)
        documents.append({**document, "mode": mode})
    if not entries:
        raise ValueError("no explicit evidence inputs")
    paths = [row["path"] for row in entries]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate archive member")
    return sorted(entries, key=lambda row: row["path"]), groups, artifacts, omissions, documents


class PartsWriter:
    """Forward-only output with one open <=2MiB part and whole-stream SHA."""
    def __init__(self, root):
        self.root = root
        self.parts = []
        self.file = None
        self.part_size = 0
        self.part_hash = None
        self.digest = hashlib.sha256()
        self.total = 0

    def writable(self):
        return True

    def write(self, block):
        length = len(block)
        self.digest.update(block)
        self.total += length
        remaining = memoryview(block)
        while remaining:
            if self.file is None:
                name = f"archive/evidence.tar.gz.part-{len(self.parts):04d}"
                self.file = (self.root / name).open("xb")
                self.parts.append({"path": name})
                self.part_size = 0
                self.part_hash = hashlib.sha256()
            take = min(CHUNK - self.part_size, len(remaining))
            selected = remaining[:take]
            self.file.write(selected)
            self.part_hash.update(selected)
            self.part_size += take
            remaining = remaining[take:]
            if self.part_size == CHUNK:
                self.finish_part()
        return length

    def flush(self):
        if self.file:
            self.file.flush()

    def finish_part(self):
        if self.file is not None:
            self.file.close()
            self.parts[-1].update(bytes=self.part_size, sha256=self.part_hash.hexdigest())
            self.file = None


class HashReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size=-1):
        block = self.stream.read(size)
        self.digest.update(block)
        self.size += len(block)
        return block


def package(config_path, output, only_plan=False):
    config_raw = bytes_file(config_path)
    config = json.loads(config_raw)
    entries, groups, artifacts, omissions, documents = plan(config)
    summary = {"schema": 1, "regular_members": len(entries),
               "uncompressed_member_bytes": sum(row["bytes"] for row in entries),
               "groups": groups, "artifacts": artifacts, "omissions": omissions,
               "documents": documents,
               "notes": config.get("notes", []),
               "config_sha256": hashlib.sha256(config_raw).hexdigest(),
               "members": [{k: v for k, v in row.items() if k != "source"} for row in entries]}
    if config.get("source_bridge") is not None:
        bridge = config["source_bridge"]
        bridge_path = canonical("groups/" + bridge["group"] + "/" + canonical(bridge["member"]))
        selected = [row for row in entries if row["path"] == bridge_path]
        if len(selected) != 1 or selected[0]["bytes"] > CHUNK:
            raise ValueError("source bridge must be one explicit group member <=2MiB")
        raw = bytes_file(selected[0]["source"])
        if hashlib.sha256(raw).hexdigest() != selected[0]["sha256"]:
            raise ValueError("source bridge changed after preflight")
        summary["source_bridge"] = {"group": bridge["group"], "member": bridge_path,
                                     "sha256": selected[0]["sha256"], "index": json.loads(raw)}
    if only_plan:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    output.mkdir(parents=False, exist_ok=False)
    (output / "archive").mkdir()
    status = {"completed": False, "format": "canonical tar PAX, gzip mtime=0, <=2MiB parts"}
    (output / "capture-status.json").write_bytes(json_bytes(status))
    writer = PartsWriter(output)
    try:
        with gzip.GzipFile(filename="", fileobj=writer, mode="wb", compresslevel=9, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                for row in entries:
                    info = tarfile.TarInfo(row["path"])
                    info.size, info.mode = row["bytes"], row["mode"]
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    with stable_file(row["source"]) as (stream, meta):
                        if meta.st_size != row["bytes"]:
                            raise ValueError("input size changed after preflight: " + row["path"])
                        if "group" in row and stat.S_IMODE(meta.st_mode) != row["mode"]:
                            raise ValueError("group input mode changed after preflight")
                        checked = HashReader(stream)
                        archive.addfile(info, checked)
                        if checked.size != row["bytes"] or checked.digest.hexdigest() != row["sha256"]:
                            raise ValueError("input changed after preflight: " + row["path"])
        writer.finish_part()
        summary["archive"] = {"compression": "gzip", "gzip_mtime": 0,
                              "tar_format": "PAX", "compressed_bytes": writer.total,
                              "sha256": writer.digest.hexdigest(), "part_size_limit": CHUNK,
                              "parts": writer.parts}
        (output / "manifest.json").write_bytes(json_bytes(summary))
        (output / "packaging-config.json").write_bytes(config_raw)
        (output / "package.py").write_bytes(bytes_file(Path(__file__).resolve()))
        (output / "verify.py").write_bytes(bytes_file(Path(__file__).resolve().with_name("verify.py")))
        for document in documents:
            payload = bytes_file(document["source"])
            if (hashlib.sha256(payload).hexdigest(), len(payload)) != (document["sha256"], document["bytes"]):
                raise ValueError("standalone document changed after preflight")
            (output / document["path"]).write_bytes(payload)
        status.update(completed=True, regular_members=len(entries),
                      archive_sha256=writer.digest.hexdigest())
        (output / "capture-status.json").write_bytes(json_bytes(status))
        published = ["capture-status.json", "manifest.json", "packaging-config.json",
                     "package.py", "verify.py", *[p["path"] for p in writer.parts],
                     *[p["path"] for p in documents]]
        (output / "SHA256SUMS").write_text("".join(hash_file(output / name)[0] + "  " + name + "\n" for name in sorted(published)))
    except BaseException as exc:
        writer.finish_part()
        (output / "packaging-failure.json").write_bytes(json_bytes({"completed": False,
            "exception": type(exc).__name__, "message": str(exc)}))
        raise
    print(json.dumps({"completed": True, "output": str(output),
                      "regular_members": len(entries), "parts": len(writer.parts),
                      "archive_sha256": writer.digest.hexdigest()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if not args.plan_only and args.output is None:
        parser.error("--output is required unless --plan-only")
    package(args.config, args.output, args.plan_only)


if __name__ == "__main__":
    main()
