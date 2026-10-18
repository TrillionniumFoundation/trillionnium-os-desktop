#!/usr/bin/env python3
"""Verify saved evidence bytes without extraction or payload execution.

Only the explicitly checksum-listed files beside this script are read.
No source tree, original absolute input path, network, Git, toolchain, or VM
is consulted. Ordinary checks remain active under Python -O.
"""
import argparse
import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile

CHUNK = 2 * 1024 * 1024
HEX = re.compile(r"^[0-9a-f]{64}$")
OID = re.compile(r"^[0-9a-f]{40}$")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(name):
    require(isinstance(name, str) and bool(name) and "\\" not in name,
            "noncanonical path")
    p = PurePosixPath(name)
    require(bool(p.parts) and not p.is_absolute() and p.as_posix() == name and
            all(c not in ("", ".", "..") for c in p.parts), "unsafe path: " + name)
    require(not any(ord(c) < 32 or ord(c) == 127 for c in name), "control character in path")
    require(not any(c in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache") for c in p.parts)
            and not name.endswith((".pyc", ".pyo")), "cache included as evidence")
    return name


def identity(meta):
    return (meta.st_dev, meta.st_ino, meta.st_mode, meta.st_size,
            meta.st_mtime_ns, meta.st_ctime_ns)


@contextlib.contextmanager
def stable_file(path):
    require(path.resolve(strict=True) == path, "symlink input refused")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode), "nonregular input")
        require(identity(before) == identity(path.stat(follow_symlinks=False)), "changed input path")
        yield stream, before
        after = os.fstat(stream.fileno())
        require(identity(before) == identity(after) == identity(path.stat(follow_symlinks=False)),
                "input changed while reading")


def saved_bytes(root, name, limit=None):
    path = root / canonical(name)
    with stable_file(path) as (stream, meta):
        require(limit is None or meta.st_size <= limit, "saved file exceeds bound: " + name)
        return stream.read()


def checksum_rows(raw):
    rows = []
    seen = set()
    for line in raw.decode("utf-8", errors="strict").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, "invalid checksum line")
        digest, name = match.groups()
        canonical(name)
        require(name not in seen and name != "SHA256SUMS", "duplicate/self-referential checksum")
        seen.add(name)
        rows.append((name, digest))
    require(bool(rows), "empty checksum list")
    return rows


class PartsReader(io.RawIOBase):
    def __init__(self, root, parts):
        self.root, self.parts = root, iter(parts)
        self.buffer = io.BytesIO()

    def readable(self):
        return True

    def readinto(self, target):
        while True:
            count = self.buffer.readinto(target)
            if count:
                return count
            part = next(self.parts, None)
            if part is None:
                return 0
            raw = saved_bytes(self.root, part["path"], CHUNK)
            require(len(raw) == part["bytes"] and hashlib.sha256(raw).hexdigest() == part["sha256"],
                    "archive part changed between verification passes")
            self.buffer = io.BytesIO(raw)


class HashReader:
    def __init__(self, stream):
        self.stream, self.digest, self.size = stream, hashlib.sha256(), 0

    def read(self, size=-1):
        block = self.stream.read(size)
        self.digest.update(block)
        self.size += len(block)
        return block


class HashWriter:
    def __init__(self):
        self.digest, self.size = hashlib.sha256(), 0

    def write(self, block):
        self.digest.update(block)
        self.size += len(block)
        return len(block)


def git_bridge(index, prefix, saved):
    """Authenticate raw cat-file bodies and selected commit/tree/blob paths."""
    require(index.get("schema") == 1, "unsupported source bridge schema")
    objects = {}
    for row in index["objects"]:
        oid, kind = row["oid"], row["type"]
        require(OID.fullmatch(oid) is not None and oid not in objects and
                kind in ("commit", "tree", "blob", "tag"), "invalid Git object identity")
        raw = saved[prefix + canonical(row["member"])]
        require(len(raw) == row.get("size", row.get("bytes")) and
                hashlib.sha256(raw).hexdigest() == row["sha256"], "Git object payload metadata differs")
        framed = kind.encode("ascii") + b" " + str(len(raw)).encode("ascii") + b"\0" + raw
        require(hashlib.sha1(framed).hexdigest() == oid, "Git object framed SHA1 differs")
        objects[oid] = (kind, raw)

    def obj(oid, kind):
        require(oid in objects and objects[oid][0] == kind, "missing/wrong Git proof object")
        return objects[oid][1]

    def commit_tree(oid):
        line = obj(oid, "commit").split(b"\n", 1)[0]
        require(line.startswith(b"tree ") and OID.fullmatch(line[5:].decode("ascii")) is not None,
                "invalid commit tree header")
        return line[5:].decode("ascii")

    tree_cache = {}

    def tree(oid):
        if oid in tree_cache:
            return tree_cache[oid]
        raw, position, result, order = obj(oid, "tree"), 0, {}, []
        while position < len(raw):
            space = raw.find(b" ", position)
            zero = raw.find(b"\0", space + 1)
            require(space > position and zero > space + 1 and zero + 21 <= len(raw), "malformed raw Git tree")
            mode = raw[position:space].decode("ascii")
            name_bytes = raw[space + 1:zero]
            name = name_bytes.decode("utf-8")
            require(mode in ("40000", "100644", "100755", "120000", "160000") and
                    "/" not in name and canonical(name) == name and name not in result, "invalid Git tree entry")
            child = raw[zero + 1:zero + 21].hex()
            result[name] = (mode, child)
            order.append(name_bytes + (b"/" if mode == "40000" else b""))
            position = zero + 21
        require(order == sorted(order), "Git tree ordering differs")
        tree_cache[oid] = result
        return result

    roots = index.get("root_commits", {})
    for role, oid in roots.items():
        require(isinstance(role, str) and OID.fullmatch(oid) is not None, "invalid role commit")
        commit_tree(oid)
    commits = index.get("commits", {})
    role_commits = dict(roots)
    for role, row in commits.items():
        raw = obj(row["oid"], "commit")
        headers = raw.split(b"\n\n", 1)[0].splitlines()
        parents = [line[7:].decode("ascii") for line in headers if line.startswith(b"parent ")]
        require(all(OID.fullmatch(parent) is not None for parent in parents) and
                row["tree"] == commit_tree(row["oid"]) and row["parents"] == parents,
                "raw commit tree/ordered parents differ")
        require(saved[prefix + canonical(row["member"])] == raw, "raw commit member differs")
        require(role not in roots or roots[role] == row["oid"], "role commit index differs")
        role_commits[role] = row["oid"]
    if "base" in roots and "prior" in role_commits:
        require(roots["base"] == role_commits["prior"], "base/prior aliases differ")

    def walk(commit, path):
        current, chain = commit_tree(commit), []
        pieces = PurePosixPath(canonical(path)).parts
        for number, part in enumerate(pieces):
            chain.append(current)
            item = tree(current).get(part)
            if item is None:
                return None, chain, number
            if number == len(pieces) - 1:
                return item, chain, None
            require(item[0] == "40000", "selected source parent is not a tree")
            current = item[1]
        raise ValueError("empty selected path")

    def role_row(row):
        require(not role_commits or role_commits.get(row["role"]) == row["commit"], "selected path role/commit differs")
        require(commit_tree(row["commit"]) == row["root_tree"], "selected root tree differs")
        item, chain, missing = walk(row["commit"], row["path"])
        if "tree_chain" in row:
            require(chain == row["tree_chain"], "selected path tree chain differs")
        return item, missing

    path_roles = set()
    for row in index["paths"]:
        path, role, commit = canonical(row["path"]), row["role"], row["commit"]
        require((role, path) not in path_roles, "duplicate selected role/path")
        path_roles.add((role, path))
        item, missing = role_row(row)
        require(item is not None and missing is None, "selected path absent")
        mode, oid = item
        require(mode == row["mode"] and mode in ("100644", "100755") and oid == row["blob"],
                "selected path Git mode/blob differs")
        blob = obj(oid, "blob")
        require(hashlib.sha256(blob).hexdigest() == row["sha256"], "selected blob SHA256 differs")
        require(saved[prefix + canonical(row["member"])] == blob, "saved selected source differs from Git blob")
    for row in index.get("subtrees", []):
        item, missing = role_row(row)
        require(item == (row["mode"], row["oid"]) and item[0] == "40000" and missing is None,
                "selected subtree pointer differs")
        raw = obj(item[1], "tree")
        require(hashlib.sha256(raw).hexdigest() == row["sha256"] and
                saved[prefix + canonical(row["member"])] == raw, "subtree saved bytes differ")
    for row in index.get("absent_paths", []):
        item, missing = role_row(row)
        require(item is None and missing == row["missing_component"] and row["exists"] is False,
                "asserted missing path exists or differs")

    def item_json(item):
        return None if item is None else {"mode": item[0], "oid": item[1],
            "type": "tree" if item[0] == "40000" else "blob" if item[0] in ("100644", "100755", "120000") else "commit"}

    ownership = index.get("ownership")
    owner_allowed_count = None
    if ownership is not None:
        equal, allowed = [], []
        exact_paths = "allowed_paths" in ownership
        if exact_paths:
            comparison = ownership["comparison"]
            require(isinstance(comparison, dict) and set(comparison) == {"base", "producer"},
                    "exact owner comparison must name base/producer roles")
            left_role, right_role = comparison["base"], comparison["producer"]
            require(left_role != right_role and left_role in role_commits and right_role in role_commits,
                    "owner comparison roles absent or identical")
            require(ownership.get("base_role", left_role) == left_role and
                    ownership.get("producer_role", right_role) == right_role,
                    "owner role declarations differ")
            allowed_paths = [canonical(path) for path in ownership["allowed_paths"]]
            require(bool(allowed_paths) and len(allowed_paths) == len(set(allowed_paths)) and
                    not any(a != b and b.startswith(a + "/") for a in allowed_paths for b in allowed_paths),
                    "exact owner paths empty, duplicated or nested")
            require("allowed_roots" not in ownership and "allowed_differences" not in ownership,
                    "exact owner schema mixed with root-based schema")
            delta_name, left_key, right_key = "allowed_deltas", "base", "producer"
        else:
            left_role, right_role = "main", "producer"
            allowed_roots = [canonical(path) for path in ownership["allowed_roots"]]
            delta_name, left_key, right_key = "allowed_differences", "main", "producer"

        def compare_owned(left, right, parent=""):
            a, b = tree(left), tree(right)
            for name in sorted(a.keys() | b.keys()):
                path = parent + name
                x, y = a.get(name), b.get(name)
                if x == y:
                    equal.append({"path": path, **item_json(x)})
                elif ((path in allowed_paths) if exact_paths else
                      any(path == root or path.startswith(root + "/") for root in allowed_roots)):
                    require(not exact_paths or all(item is None or item[0] in ("100644", "100755") for item in (x, y)),
                            "exact owner path is not a regular file: " + path)
                    allowed.append({"path": path, left_key: item_json(x), right_key: item_json(y)})
                else:
                    require(x is not None and y is not None and x[0] == y[0] == "40000",
                            "source changed outside approved owner roots: " + path)
                    compare_owned(x[1], y[1], path + "/")
        compare_owned(commit_tree(role_commits[left_role]), commit_tree(role_commits[right_role]))
        require(equal == ownership["equal_entries"] and allowed == ownership[delta_name],
                "owner equality/delta coverage differs")
        if exact_paths:
            require({row["path"] for row in allowed} == set(allowed_paths),
                    "actual owner deltas do not exactly cover the approved file paths")
        owner_allowed_count = len(allowed)
    return {"passed": True, "raw_git_objects": len(objects), "selected_paths": len(path_roles),
            "subtree_paths": len(index.get("subtrees", [])), "absent_paths": len(index.get("absent_paths", [])),
            "owner_equal_entries": len(ownership["equal_entries"]) if ownership else None,
            "owner_allowed_differences": owner_allowed_count,
            "role_commits": role_commits,
            "scope": "Raw Git framing hashes, ordered parent headers, selected commit/tree/blob/absence paths and explicit owner equality/delta coverage. Other bridge review claims remain saved data; no Git execution."}


def verify(root):
    root = root.resolve(strict=True)
    checksums = checksum_rows(saved_bytes(root, "SHA256SUMS", CHUNK))
    checked = {}
    for name, expected in checksums:
        raw = saved_bytes(root, name, CHUNK if name.startswith("archive/") else None)
        require(hashlib.sha256(raw).hexdigest() == expected, "root checksum differs: " + name)
        checked[name] = expected
    status = json.loads(saved_bytes(root, "capture-status.json", CHUNK))
    require(status.get("completed") is True, "capture incomplete")
    manifest = json.loads(saved_bytes(root, "manifest.json"))
    require(manifest.get("schema") == 1, "unsupported manifest schema")
    config_raw = saved_bytes(root, "packaging-config.json")
    require(hashlib.sha256(config_raw).hexdigest() == manifest["config_sha256"], "configuration differs")
    config = json.loads(config_raw)
    require(config.get("schema") == 1, "unsupported original configuration")
    archive_spec = manifest["archive"]
    require(archive_spec["compression"] == "gzip" and archive_spec["gzip_mtime"] == 0 and
            archive_spec["tar_format"] == "PAX" and archive_spec["part_size_limit"] == CHUNK,
            "archive format differs")
    parts = archive_spec["parts"]
    require(bool(parts), "no archive parts")
    digest, total = hashlib.sha256(), 0
    for index, part in enumerate(parts):
        require(part["path"] == f"archive/evidence.tar.gz.part-{index:04d}", "noncanonical part order")
        require(0 < part["bytes"] <= CHUNK and (index == len(parts) - 1 or part["bytes"] == CHUNK),
                "part size differs")
        raw = saved_bytes(root, part["path"], CHUNK)
        require(len(raw) == part["bytes"] and hashlib.sha256(raw).hexdigest() == part["sha256"],
                "part identity differs")
        if index == 0:
            require(raw[:10] == b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff", "gzip header differs")
        digest.update(raw)
        total += len(raw)
    require((total, digest.hexdigest()) == (archive_spec["compressed_bytes"], archive_spec["sha256"]),
            "whole compressed archive differs")
    require(status["archive_sha256"] == digest.hexdigest(), "capture status archive differs")
    rows = manifest["members"]
    names = [canonical(row["path"]) for row in rows]
    require(names == sorted(set(names)), "member order or uniqueness differs")
    require(len(rows) == manifest["regular_members"] == status["regular_members"], "member count differs")
    require(sum(row["bytes"] for row in rows) == manifest["uncompressed_member_bytes"], "member bytes differ")
    member_map = {row["path"]: row for row in rows}
    for row in rows:
        require(isinstance(row["bytes"], int) and row["bytes"] >= 0 and
                isinstance(row["mode"], int) and 0 <= row["mode"] <= 0o7777 and
                HEX.fullmatch(row["sha256"]) is not None, "invalid member metadata")
    retained_sums = {}
    wanted_sums = {group["checksum_file"] for group in manifest["groups"]}
    bridge = manifest.get("source_bridge")
    proof_wanted, proof_saved = set(), {}
    if config.get("source_bridge") is not None:
        expected_bridge = config["source_bridge"]
        prefix = "groups/" + expected_bridge["group"] + "/"
        require(bridge is not None and bridge["group"] == expected_bridge["group"] and
                bridge["member"] == prefix + canonical(expected_bridge["member"]) and
                bridge["sha256"] == member_map[bridge["member"]]["sha256"], "source bridge configuration differs")
        proof_wanted = {bridge["member"],
                        *[prefix + canonical(row["member"]) for row in bridge["index"]["objects"]],
                        *[prefix + canonical(row["member"]) for row in bridge["index"]["paths"]]}
        require(proof_wanted <= set(member_map), "source proof member absent")
        require(all(member_map[path]["bytes"] <= CHUNK for path in proof_wanted) and
                sum(member_map[path]["bytes"] for path in proof_wanted) <= 64 * 1024 * 1024,
                "source proof exceeds retained-memory bounds")
    else:
        require(bridge is None, "unexpected source bridge claim")
    canonical_tar = HashWriter()
    with io.BufferedReader(PartsReader(root, parts), buffer_size=CHUNK) as compressed:
        with gzip.GzipFile(fileobj=compressed, mode="rb") as gz:
            actual_tar = HashReader(gz)
            with tarfile.open(fileobj=actual_tar, mode="r|") as archive:
                with tarfile.open(fileobj=canonical_tar, mode="w|", format=tarfile.PAX_FORMAT) as normalized:
                    count = 0
                    for info in archive:
                        require(count < len(rows), "unlisted archive member")
                        row = rows[count]
                        require(info.name == row["path"] and info.type == tarfile.REGTYPE and
                                info.mode == row["mode"] and info.size == row["bytes"] and
                                info.uid == info.gid == info.mtime == 0 and
                                info.uname == info.gname == info.linkname == "", "tar metadata differs")
                        require(set(info.pax_headers) <= {"path"} and
                                (not info.pax_headers or info.pax_headers["path"] == info.name),
                                "unexpected PAX metadata")
                        payload = archive.extractfile(info)
                        require(payload is not None, "regular member missing bytes")
                        if info.name in wanted_sums | proof_wanted:
                            require(info.size <= CHUNK, "embedded control/proof file too large")
                            raw = payload.read()
                            if info.name in wanted_sums:
                                retained_sums[info.name] = raw
                            if info.name in proof_wanted:
                                proof_saved[info.name] = raw
                            payload = io.BytesIO(raw)
                        reader = HashReader(payload)
                        canonical_info = tarfile.TarInfo(row["path"])
                        canonical_info.size, canonical_info.mode = row["bytes"], row["mode"]
                        canonical_info.uid = canonical_info.gid = canonical_info.mtime = 0
                        canonical_info.uname = canonical_info.gname = ""
                        normalized.addfile(canonical_info, reader)
                        require(reader.size == row["bytes"] and reader.digest.hexdigest() == row["sha256"],
                                "archive payload differs: " + info.name)
                        count += 1
                    require(count == len(rows), "missing archive members")
            while actual_tar.read(CHUNK):
                pass
            require((actual_tar.size, actual_tar.digest.hexdigest()) ==
                    (canonical_tar.size, canonical_tar.digest.hexdigest()),
                    "tar bytes are not the exact canonical header/payload/padding stream")
    covered = set()
    group_names = set()
    require(len(config["groups"]) == len(manifest["groups"]), "group configuration count differs")
    for group, original in zip(manifest["groups"], config["groups"]):
        name = group["name"]
        require(name not in group_names and name == original["name"], "duplicate/different group")
        group_names.add(name)
        prefix = "groups/" + name + "/"
        sum_path = prefix + original.get("checksum_file", "SHA256SUMS")
        require(group["checksum_file"] == sum_path and group["checksum_sha256"] == original["expected_checksum_sha256"],
                "group checksum binding differs")
        raw = retained_sums[sum_path]
        require(hashlib.sha256(raw).hexdigest() == group["checksum_sha256"], "embedded checksum differs")
        group_rows = checksum_rows(raw)
        require(len(group_rows) == group["checksum_members"] == original["expected_members"] and
                group["retained_regular_members"] == len(group_rows) + 1, "group member count differs")
        expected_paths = {sum_path, *[prefix + path for path, _ in group_rows]}
        actual_paths = {path for path in names if path.startswith(prefix)}
        require(expected_paths == actual_paths, "group has missing/unlisted members")
        for path, sha in group_rows:
            require(member_map[prefix + path]["sha256"] == sha, "group checksum/member binding differs")
        require(all(member_map[path].get("group") == name for path in expected_paths), "group label differs")
        covered |= expected_paths
    require(len(config.get("artifacts", [])) == len(manifest["artifacts"]), "artifact role count differs")
    seen_roles = set()
    artifact_paths = set()
    for artifact, original in zip(manifest["artifacts"], config.get("artifacts", [])):
        require(all(artifact.get(key) == value for key, value in original.items()), "artifact configuration differs")
        role = artifact["role"]
        require(role not in seen_roles and bool(role) and artifact.get("retained") is True,
                "artifact role duplicate or not retained")
        seen_roles.add(role)
        name = "artifacts/" + artifact["sha256"]
        require(artifact["member"] == name and name in member_map, "retained payload absent")
        row = member_map[name]
        require((row["sha256"], row["bytes"], row["mode"], row.get("kind")) ==
                (artifact["sha256"], artifact["bytes"], 0o644, "distinct-native-payload"),
                "artifact/member binding differs")
        artifact_paths.add(name)
    require(covered | artifact_paths == set(names), "archive member without declared origin")
    require(manifest["omissions"] == config.get("omissions", []), "omissions differ")
    for omission in manifest["omissions"]:
        require(bool(omission["role"]) and omission["role"] not in seen_roles and
                bool(omission.get("reason")) and omission.get("retained") in (None, False),
                "invalid omission")
        seen_roles.add(omission["role"])
    require(len(config.get("documents", [])) == len(manifest["documents"]), "document count differs")
    documents = set()
    for document, original in zip(manifest["documents"], config.get("documents", [])):
        require(all(document.get(key) == value for key, value in original.items()), "document configuration differs")
        name = canonical(document["path"])
        require(len(PurePosixPath(name).parts) == 1 and name not in documents, "invalid standalone document")
        raw = saved_bytes(root, name, CHUNK)
        require((len(raw), hashlib.sha256(raw).hexdigest()) == (document["bytes"], document["sha256"]),
                "standalone document differs")
        documents.add(name)
    expected_root = {"capture-status.json", "manifest.json", "packaging-config.json", "package.py", "verify.py",
                     *[part["path"] for part in parts], *documents}
    require(expected_root == set(checked), "root checksum coverage differs")
    source_proof = None
    if bridge is not None:
        require(hashlib.sha256(proof_saved[bridge["member"]]).hexdigest() == bridge["sha256"] and
                json.loads(proof_saved[bridge["member"]]) == bridge["index"], "source bridge index differs from retained bytes")
        source_proof = git_bridge(bridge["index"], "groups/" + bridge["group"] + "/", proof_saved)
    return {"passed": True, "checksum_listed_files": len(checked),
            "groups": len(group_names), "archive_regular_members": len(rows),
            "distinct_native_payloads": len(artifact_paths), "retained_artifact_roles": len(manifest["artifacts"]),
            "omitted_roles": len(manifest["omissions"]), "archive_sha256": archive_spec["sha256"],
            "source_proof": source_proof,
            "scope": "Saved bytes only; no extraction, original-source access, Git, subprocess, network, compilation, or VM."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    print(json.dumps(verify(args.phase), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
