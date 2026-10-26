#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Reproduce the immutable post1138 fixture from actual pinned Git objects.

Default --check needs the original 623 objects. Portable source-admission
tests validate the bound archive without requiring historical Git refs.
"""
import argparse
import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HEAD = "62301dd25cc9fd57baa04dc9e86cda2bef205fa1"
TREE = "08cde53405dea5e98b26d4a2f99cb38c674527d8"
FIXTURE = HERE / "controls/post1138-kernel-v1-source.json.gz"
FIXTURE_SHA256 = "feff5349b7859c3e6368982261bdd21fd879f557cc47a89d28e72576bcc63cb2"


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def encoded_fixture():
    require(git("rev-parse", HEAD + "^{tree}").decode().strip() == TREE,
            "original source tree differs")
    source = git("show", HEAD + ":tests/kernel/network/run_unix_stream_post1138_guest.py").decode()
    parsed = ast.parse(source)
    owners = ast.literal_eval(next(node.value for node in parsed.body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "OWNERS"
                                                for t in node.targets)))
    require(len(owners) == len({r for r, _, _ in owners}) == len({p for _, p, _ in owners}) == 76,
            "historical roles/paths must be unique")
    entries = {}
    for entry in filter(None, git("ls-tree", "-r", "-z", HEAD).split(b"\0")):
        metadata, name = entry.split(b"\t", 1)
        entries[name.decode()] = metadata.decode().split()
    files = []
    for role, name, expected in owners:
        require(not Path(name).is_absolute() and ".." not in Path(name).parts,
                "unsafe historical source path")
        mode, kind, blob = entries[name]
        require(kind == "blob" and mode in ("100644", "100755"), "not a regular Git source")
        data = git("cat-file", "blob", blob)
        sha = hashlib.sha256(data).hexdigest()
        require(sha == expected and hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == blob,
                "historical bytes differ from reviewed literal/Git blob")
        files.append({"role": role, "path": name, "mode": mode, "git_blob": blob,
                      "sha256": sha, "content_base64": base64.b64encode(data).decode()})
    record = {"schema": "asterinas.post1138-kernel-v1-historical-source.v1",
              "source_head": HEAD, "source_tree": TREE, "files": files}
    return gzip.compress(json.dumps(record, sort_keys=True, separators=(",", ":")).encode(), mtime=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="create the fixed archive once; never overwrite")
    parser.add_argument("--check", action="store_true", help="default: compare to existing archive")
    args = parser.parse_args()
    require(not (args.write and args.check), "choose check or write")
    encoded = encoded_fixture()
    require(hashlib.sha256(encoded).hexdigest() == FIXTURE_SHA256, "exported archive identity differs")
    if args.write:
        with FIXTURE.open("xb") as stream:
            stream.write(encoded)
    else:
        require(FIXTURE.is_file() and not FIXTURE.is_symlink() and FIXTURE.read_bytes() == encoded,
                "fixed historical archive differs")
    print(json.dumps({"files": 76, "source_head": HEAD, "source_tree": TREE,
                      "archive_sha256": FIXTURE_SHA256, "matches_real_git_objects": True}))


if __name__ == "__main__":
    main()
