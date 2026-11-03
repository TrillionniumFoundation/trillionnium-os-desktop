#!/usr/bin/env python3
"""Freeze exact completed evidence files, pack them, and verify a downloaded copy.

No remote access, builds, source checkout edits, directory-recursive archiving,
or product qualification. All archive payloads are explicitly listed in a plan.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import time

ROOT = "v14-runtime-attempts"
MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_MEMBERS = 10000
SUFFIXES = {".log", ".json", ".png", ".txt", ".md", ".sha256", ".toml", ".yaml",
            ".yml", ".py", ".pyc", ".sh", ".xml", ".stdout", ".stderr", ".out"}
QUALIFICATION = {"scope": "completed runtime attempt evidence only", "production_qualified": False,
                 "fullgate_closed": False, "all_blockers_closed": False}
RESERVED = {"ARCHIVE_MANIFEST.json", "ARCHIVE_PLAN.json", "ARCHIVE_TOOL.py", "HASH_ONLY_EVIDENCE.json"}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def object_once(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, "duplicate JSON key: " + name)
        result[name] = value
    return result


def decode(data):
    return json.loads(data, object_pairs_hook=object_once)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def relative(value):
    path = PurePosixPath(value)
    require(value and not path.is_absolute() and str(path) == value and "\\" not in value
            and all(part not in ("", ".", "..") for part in path.parts)
            and all(ord(char) >= 32 for char in value), "unsafe member path: " + value)
    return value


def absolute(value):
    path = Path(value)
    require(path.is_absolute() and str(path) == value and ".." not in path.parts,
            "source/exclusion path must be exact and absolute: " + value)
    return path


def version(value):
    return {name: getattr(value, "st_" + name) for name in
            ("dev", "ino", "mode", "size", "mtime_ns", "ctime_ns")}


def exclusions(value):
    roots = [absolute(item) for item in value["forbidden_roots"]]
    prefixes = []
    for item in value.get("forbidden_name_prefixes", []):
        prefix = item["prefix"]
        require(prefix and "/" not in prefix and "\\" not in prefix, "invalid excluded basename prefix")
        prefixes.append((absolute(item["directory"]), prefix))
    return {"roots": roots, "prefixes": prefixes}


def source_path(value, forbidden):
    path = absolute(value)
    require(not any(path == root or root in path.parents for root in forbidden["roots"])
            and not any(root in path.parents and path.relative_to(root).parts[0].startswith(prefix)
                        for root, prefix in forbidden["prefixes"]),
            "excluded/in-flight source was selected: " + value)
    for component in (*reversed(path.parents), path):
        require(not stat.S_ISLNK(component.lstat().st_mode), "source path contains a symlink: " + str(component))
    return path


def content_kind(path, first):
    require(path.suffix.lower() in SUFFIXES or path.name == "SHA256SUMS", "unapproved evidence extension: " + str(path))
    forbidden = (b"\x7fELF", b"\x1f\x8b", b"PK\x03\x04", b"!<arch>\n", b"\x00\x01\x00\x00",
                 b"OTTO", b"ttcf", b"wOFF", b"wOF2")
    require(not first.startswith(forbidden) and first[257:262] != b"ustar",
            "binary/archive/font payload is excluded: " + str(path))
    if path.suffix.lower() == ".png":
        require(first.startswith(b"\x89PNG\r\n\x1a\n"), "PNG evidence has an invalid signature")
        return "png"
    if path.suffix.lower() == ".pyc":
        require(len(first) >= 16 and first[2:4] == b"\r\n", "invalid explicitly selected Python bytecode evidence")
        return "python-bytecode-evidence"
    return "text"


def measure(path, expected=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE,
                "evidence must be a bounded regular file: " + str(path))
        if expected is not None:
            require(version(before) == expected, "evidence version changed since selection: " + str(path))
        digest, size, kind = hashlib.sha256(), 0, None
        while chunk := stream.read(1024 * 1024):
            if kind is None:
                kind = content_kind(path, chunk)
            require(kind in ("png", "python-bytecode-evidence") or b"\0" not in chunk,
                    "binary content in text evidence: " + str(path))
            size += len(chunk)
            require(size <= before.st_size, "evidence grew while reading: " + str(path))
            digest.update(chunk)
        if kind is None:
            kind = content_kind(path, b"")
        require(size == before.st_size and version(os.fstat(stream.fileno())) == version(before)
                and version(path.lstat()) == version(before), "evidence changed while reading: " + str(path))
        return {"bytes": size, "sha256": digest.hexdigest(), "source_version": version(before), "kind": kind}


def save_new(path, data):
    require(path.is_absolute() and path.parent.is_dir(), "new output needs an existing absolute parent")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def make_plan(selection_path, output):
    selection_data = selection_path.read_bytes()
    selection = decode(selection_data)
    require(selection.get("schema") == "trill.completed-evidence-selection.v1", "unsupported selection schema")
    require(not selection.get("unresolved"), "resolve the selection's explicit unknown paths before freezing")
    forbidden = exclusions(selection)
    require(forbidden["roots"], "explicit in-flight/payload exclusions are required")
    attempts = {item["id"]: item for item in selection["attempts"]}
    require(len(attempts) == len(selection["attempts"]) and all(item.get("completed") is True for item in attempts.values()),
            "only explicitly completed, uniquely named attempts may be selected")
    pending, excluded = list(selection["files"]), []
    for directory in selection.get("completed_directories", []):
        root = source_path(directory["source"], forbidden)
        require(root.is_dir() and directory["attempt"] in attempts, "invalid completed evidence directory")
        prefix = relative(directory["member_prefix"])
        # Intentionally one level only. Nested directories require their own
        # explicit selection, so SDK trees/ELF staging/resources cannot leak in.
        for path in sorted(root.iterdir()):
            if path.is_symlink():
                raise RuntimeError("symlink found in selected completed directory: " + str(path))
            if path.is_dir() or (path.suffix.lower() not in SUFFIXES and path.name != "SHA256SUMS"):
                excluded.append({"source": str(path), "reason": "directory-not-traversed-or-payload-type"})
                continue
            pending.append({"source": str(path), "member": prefix + "/" + path.name,
                            "attempt": directory["attempt"], "hash_only": directory.get("hash_only", False)})
    require(0 < len(pending) <= MAX_MEMBERS, "invalid selected file count")
    records, names, paths, total = [], set(), set(), 0
    for item in sorted(pending, key=lambda value: value["member"]):
        name = relative(item["member"])
        require(name.split("/")[0] not in RESERVED and name not in names, "duplicate/reserved archive member: " + name)
        require(item["attempt"] in attempts, "file refers to an unknown completed attempt")
        path = source_path(item["source"], forbidden)
        require(str(path) not in paths, "same source selected twice: " + str(path))
        measured = measure(path)
        require(measured["kind"] != "python-bytecode-evidence" or item.get("hash_only") is True,
                "Python bytecode is metadata/hash only, never archive payload")
        if not item.get("hash_only"):
            total += measured["bytes"]
        require(total <= MAX_TOTAL, "selected evidence exceeds the total byte bound")
        records.append(dict(item, **measured))
        names.add(name)
        paths.add(str(path))
    require({item["attempt"] for item in records} == set(attempts), "a declared completed attempt has no selected evidence")
    for identity in selection["source_identities"]:
        for key in ("commit", "tree"):
            if key in identity:
                require(re.fullmatch(r"[0-9a-f]{40}", identity[key]), "source identities must use full hashes")
        require(identity.get("proof_members") and set(identity["proof_members"]) <= names,
                "source identity proof members are missing from the exact plan")
    for item in records:
        require(version(source_path(item["source"], forbidden).lstat()) == item["source_version"],
                "evidence changed before the complete plan was frozen: " + item["source"])
    plan = {"schema": "trill.exact-evidence-plan.v1", "archive_root": ROOT,
            "selection_sha256": hashlib.sha256(selection_data).hexdigest(), "qualification": QUALIFICATION,
            "source_identities": selection["source_identities"], "attempts": selection["attempts"],
            "forbidden_roots": selection["forbidden_roots"],
            "forbidden_name_prefixes": selection.get("forbidden_name_prefixes", []), "excluded_inventory": excluded,
            "selected_directory_roots": [item["source"] for item in selection.get("completed_directories", [])],
            "files": records, "payload_bytes": total, "created_unix_ns": time.time_ns()}
    save_new(output, encoded(plan))
    print(json.dumps({"plan": str(output), "measured_files": len(records), "payload_bytes": total,
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}), flush=True)


class HashedReader:
    def __init__(self, stream):
        self.stream, self.digest, self.size = stream, hashlib.sha256(), 0

    def read(self, length):
        data = self.stream.read(length)
        self.digest.update(data)
        self.size += len(data)
        return data


def add_member(tar, name, size, stream):
    info = tarfile.TarInfo(ROOT + "/" + relative(name))
    info.size, info.mode, info.mtime = size, 0o644, 0
    info.uid = info.gid = 0
    tar.addfile(info, stream)


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pack(plan_path, output):
    plan_data = plan_path.read_bytes()
    plan = decode(plan_data)
    require(plan.get("schema") == "trill.exact-evidence-plan.v1" and plan["qualification"] == QUALIFICATION
            and plan["archive_root"] == ROOT, "unsupported or overclaimed evidence plan")
    require(output.is_absolute() and not output.exists() and not output.is_symlink() and output.parent.is_dir(),
            "archive output directory must be new and absolute")
    for value in plan["selected_directory_roots"]:
        root = absolute(value)
        require(output != root and root not in output.parents, "archive output cannot be inside a selected evidence directory")
    forbidden = exclusions(plan)
    records = plan["files"]
    payload_records = [item for item in records if not item.get("hash_only")]
    require(0 < len(records) <= MAX_MEMBERS and sum(item["bytes"] for item in payload_records) <= MAX_TOTAL,
            "evidence plan exceeds archive bounds")
    require(len({relative(item["member"]) for item in records}) == len(records)
            and not any(item["member"].split("/")[0] in RESERVED for item in records), "invalid or duplicate plan member")
    for item in records:
        actual = measure(source_path(item["source"], forbidden), item["source_version"])
        require(all(actual[key] == item[key] for key in ("bytes", "sha256", "kind")), "plan content no longer matches source")
        require(actual["kind"] != "python-bytecode-evidence" or item.get("hash_only") is True,
                "Python bytecode payload is forbidden")
    tool_data = Path(__file__).resolve().read_bytes()
    controls = {"ARCHIVE_PLAN.json": plan_data, "ARCHIVE_TOOL.py": tool_data,
                "HASH_ONLY_EVIDENCE.json": encoded([item for item in records if item.get("hash_only")])}
    manifest_records = [dict(item, archive_path=ROOT + "/" + item["member"]) for item in payload_records]
    manifest_records += [{"member": name, "archive_path": ROOT + "/" + name, "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest(), "kind": "generated-control"}
                         for name, data in controls.items()]
    manifest = {"schema": "trill.completed-runtime-evidence-archive.v1", "archive_root": ROOT,
                "qualification": QUALIFICATION, "source_identities": plan["source_identities"],
                "attempts": plan["attempts"], "excluded_inflight_and_payload_roots": plan["forbidden_roots"],
                "excluded_inflight_name_prefixes": plan.get("forbidden_name_prefixes", []),
                "members": manifest_records, "payload_bytes": sum(item["bytes"] for item in manifest_records),
                "plan_sha256": hashlib.sha256(plan_data).hexdigest(),
                "manifest_self_hash": "external archive receipt; no circular member hash"}
    manifest_data = encoded(manifest)
    output.mkdir(mode=0o700)
    partial = output / (ROOT + ".tar.gz.partial")
    archive = output / (ROOT + ".tar.gz")
    try:
        with partial.open("xb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                    add_member(tar, "ARCHIVE_MANIFEST.json", len(manifest_data), io.BytesIO(manifest_data))
                    for name, data in controls.items():
                        add_member(tar, name, len(data), io.BytesIO(data))
                    for item in payload_records:
                        path = source_path(item["source"], forbidden)
                        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                        with os.fdopen(fd, "rb") as stream:
                            require(version(os.fstat(stream.fileno())) == item["source_version"], "source changed before archive copy")
                            reader = HashedReader(stream)
                            add_member(tar, item["member"], item["bytes"], reader)
                            require(reader.size == item["bytes"] and reader.digest.hexdigest() == item["sha256"]
                                    and version(os.fstat(stream.fileno())) == item["source_version"],
                                    "source changed during archive copy: " + item["source"])
            raw.flush()
            os.fsync(raw.fileno())
        for item in records:
            require(version(source_path(item["source"], forbidden).lstat()) == item["source_version"],
                    "source changed before archive completion: " + item["source"])
        verify(partial, sha_file(partial), quiet=True)
        partial.rename(archive)
        save_new(output / "ARCHIVE_MANIFEST.json", manifest_data)
        checksum = sha_file(archive)
        save_new(output / (ROOT + ".tar.gz.sha256"), (checksum + "  " + archive.name + "\n").encode())
        receipt = {"archive": str(archive), "sha256": checksum, "bytes": archive.stat().st_size,
                   "manifest_sha256": hashlib.sha256(manifest_data).hexdigest(),
                   "members_including_control_manifest": len(manifest_records) + 1,
                   "qualification": QUALIFICATION, "source_versions_stable_through_unix_ns": time.time_ns()}
        save_new(output / "archive-receipt.json", encoded(receipt))
        print(json.dumps(receipt), flush=True)
    except BaseException as error:
        save_new(output / "archive-failure.json", encoded({"archive_complete": False, "error": str(error)}))
        raise


def verify(archive, expected_sha256, quiet=False):
    require(re.fullmatch(r"[0-9a-f]{64}", expected_sha256) and sha_file(archive) == expected_sha256,
            "downloaded archive does not match the independently recorded SHA256")
    seen, total = set(), 0
    with tarfile.open(archive, "r|gz") as tar:
        iterator = iter(tar)
        first = next(iterator, None)
        require(first and first.name == ROOT + "/ARCHIVE_MANIFEST.json" and first.isfile() and first.mode == 0o644
                and 0 <= first.size <= 16 * 1024 * 1024, "missing bounded archive manifest")
        manifest = decode(tar.extractfile(first).read())
        require(manifest.get("schema") == "trill.completed-runtime-evidence-archive.v1"
                and manifest["qualification"] == QUALIFICATION and manifest["archive_root"] == ROOT,
                "unsupported or overclaimed archive scope")
        expected = {item["archive_path"]: item for item in manifest["members"]}
        require(len(expected) == len(manifest["members"]) <= MAX_MEMBERS + 3, "duplicate or excessive manifest records")
        for name, item in expected.items():
            require(relative(name).startswith(ROOT + "/") and item["member"] == name[len(ROOT) + 1:]
                    and name != first.name and 0 <= item["bytes"] <= MAX_FILE
                    and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "invalid manifest member")
        seen.add(first.name)
        for member in iterator:
            require(member.name in expected and member.name not in seen and member.isfile() and member.mode == 0o644,
                    "unexpected, duplicate, linked or nonregular archive member")
            item = expected[member.name]
            require(member.size == item["bytes"], "archive member length differs from its manifest")
            digest, size = hashlib.sha256(), 0
            with tar.extractfile(member) as stream:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
            require(size == item["bytes"] and digest.hexdigest() == item["sha256"], "archive member checksum mismatch")
            total += size
            require(total <= MAX_TOTAL + 32 * 1024 * 1024, "archive evidence exceeds total bounds")
            seen.add(member.name)
    require(seen - {ROOT + "/ARCHIVE_MANIFEST.json"} == set(expected)
            and total == manifest["payload_bytes"], "archive is missing evidence members")
    if not quiet:
        print(json.dumps({"verified": True, "archive": str(archive), "sha256": expected_sha256,
                          "members": len(expected) + 1, "qualification": QUALIFICATION}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("plan", help="freeze explicit files and one-level completed directory selections")
    prepare.add_argument("--selection", required=True, type=Path)
    prepare.add_argument("--out", required=True, type=Path)
    bundle = commands.add_parser("pack", help="pack only the exact measured plan; reject any changed input")
    bundle.add_argument("--plan", required=True, type=Path)
    bundle.add_argument("--out", required=True, type=Path)
    check = commands.add_parser("verify", help="verify outer SHA and every member after download; no extraction")
    check.add_argument("--archive", required=True, type=Path)
    check.add_argument("--sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "plan":
        make_plan(args.selection, args.out)
    elif args.command == "pack":
        pack(args.plan, args.out)
    else:
        verify(args.archive, args.sha256)


if __name__ == "__main__":
    main()
