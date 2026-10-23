#!/usr/bin/env python3
"""Fail closed unless the candidate uses both unchanged original Git packages."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

REPOSITORY = "TrillionniumFoundation/hepta-private-ci"
PACKAGES = {
    "hepta-control-core": "apps/hepta-control-ui/rust/core/Cargo.toml",
    "hepta-robrix-ui": "apps/hepta-control-ui/rust/robrix-ui/Cargo.toml",
}
REQUIRED_SOURCES = {
    "apps/hepta-control-ui/rust/core/src/chat.rs",
    "apps/hepta-control-ui/rust/core/src/chat_owner.rs",
    "apps/hepta-control-ui/rust/core/src/chat_timeline.rs",
    "apps/hepta-control-ui/rust/robrix-ui/src/presentation.rs",
}
LICENSE_COPIES = {
    "HEPTA-LICENSE.txt": "LICENSE",
    "HEPTA-NOTICE.txt": "NOTICE",
    "ROBRIX-MIT.txt": "apps/hepta-control-ui/rust/robrix-ui/licenses/ROBRIX-MIT.txt",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_manifest(value: dict) -> None:
    require(value.get("schema") == "trillionnium.original-shared-presenter.v1", "wrong source schema")
    require(value.get("repository") == REPOSITORY, "wrong upstream repository")
    for field in ("commit", "tree"):
        require(bool(re.fullmatch(r"[0-9a-f]{40}", value.get(field, ""))), f"invalid {field}")
    paths = set()
    for item in value.get("files", []):
        path = item.get("path", "")
        pure = PurePosixPath(path)
        require(bool(path) and not pure.is_absolute() and ".." not in pure.parts
                and str(pure) == path, "unsafe source path")
        require(path not in paths, "duplicate source path")
        paths.add(path)
        require(bool(re.fullmatch(r"[0-9a-f]{40}", item.get("git_blob", ""))), "invalid blob")
        require(bool(re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", ""))), "invalid SHA256")
        require(type(item.get("bytes")) is int and item["bytes"] >= 0, "invalid size")
    require(REQUIRED_SOURCES <= paths, "missing original presenter/model source")
    require({"LICENSE", "NOTICE", "apps/hepta-control-ui/rust/robrix-ui/licenses/ROBRIX-MIT.txt"} <= paths,
            "missing upstream license/notice provenance")


def check_packages(metadata: dict, source: dict) -> Path:
    expected = f"git+https://github.com/{REPOSITORY}?rev={source['commit']}#{source['commit']}"
    roots = []
    ids = {}
    for name, original_path in PACKAGES.items():
        matches = [p for p in metadata.get("packages", []) if p.get("name") == name]
        require(len(matches) == 1, f"expected one original {name} package")
        package = matches[0]
        require(package.get("source") == expected, f"{name} is not the exact original Git package")
        require(package.get("version") == "0.1.0", f"unexpected {name} version")
        manifest = Path(package["manifest_path"]).resolve()
        root = manifest
        for _ in PurePosixPath(original_path).parts:
            root = root.parent
        require(root / original_path == manifest, f"wrong original {name} manifest path")
        roots.append(root)
        ids[name] = package["id"]
    require(roots[0] == roots[1], "model and presenter came from different checkouts")
    nodes = metadata.get("resolve", {}).get("nodes", [])
    selected = [node for node in nodes if node.get("id") == ids["hepta-robrix-ui"]]
    require(len(selected) == 1, "presenter was not actually resolved for the enabled feature")
    require(not ({"ui", "native-host"} & set(selected[0].get("features", []))),
            "this gate does not qualify a Makepad renderer or native owner host")
    for name in ("trill-ui-core", "trill-shell"):
        packages = [p for p in metadata.get("packages", []) if p.get("name") == name]
        require(len(packages) == 1, f"missing Desktop {name}")
        require(packages[0].get("features", {}).get("default", []) == [],
                "candidate must remain default-off")
        active = [node for node in nodes if node.get("id") == packages[0]["id"]]
        require(len(active) == 1 and "hepta-shared-presenter" in active[0].get("features", []),
                f"{name} candidate feature was not enabled in this validation")
    return roots[0]


def check_files(root: Path, source: dict) -> None:
    for item in source["files"]:
        path = root
        for part in PurePosixPath(item["path"]).parts:
            path = path / part
            require(not path.is_symlink(), f"symlink in original source path: {item['path']}")
        require(path.is_file(), f"missing source: {item['path']}")
        data = path.read_bytes()
        require(len(data) == item["bytes"], f"source size changed: {item['path']}")
        require(hashlib.sha256(data).hexdigest() == item["sha256"], f"source SHA256 changed: {item['path']}")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(blob == item["git_blob"], f"source Git blob changed: {item['path']}")


def check_checkout(root: Path, source: dict) -> int:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    require(git("rev-parse", "HEAD") == source["commit"], "checkout HEAD differs from source pin")
    require(git("rev-parse", "HEAD^{tree}") == source["tree"], "checkout tree differs from source pin")
    paths = sorted({str(PurePosixPath(p).parent) for p in PACKAGES.values()}
                   | {item["path"] for item in source["files"]})
    # Check every original package file, including modules beyond the four
    # directly reviewed presenter/model files. A patched local checkout fails.
    require(not git("status", "--porcelain=v1", "--untracked-files=all", "--", *paths),
            "original package checkout contains modifications or extra files")
    # Do not let index assume-unchanged/skip-worktree flags hide a modified
    # module outside the small review manifest. Hash every original package
    # file from the pinned HEAD tree directly, independently of Git's index.
    entries = subprocess.check_output(
        ["git", "-C", str(root), "ls-tree", "-r", "-z", "--full-tree", "HEAD", "--", *paths]
    ).split(b"\0")
    verified = 0
    for entry in entries:
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, expected_blob = header.decode().split()
        require(kind == "blob" and mode in ("100644", "100755"),
                "original package contains an unqualified source entry")
        path = root
        for part in PurePosixPath(name.decode()).parts:
            path /= part
            require(not path.is_symlink(), "symlink in original package checkout")
        require(path.is_file(), "original package checkout file is missing")
        data = path.read_bytes()
        actual_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(actual_blob == expected_blob, "original package bytes differ from pinned tree")
        verified += 1
    require(verified > 0, "original package tree is empty")
    return verified


def check_license_copies(directory: Path, source: dict) -> None:
    records = {item["path"]: item for item in source["files"]}
    require(not directory.is_symlink(), "license directory must not be a symlink")
    for name, upstream_path in LICENSE_COPIES.items():
        path = directory / name
        require(path.is_file() and not path.is_symlink(), f"missing local upstream notice: {name}")
        data = path.read_bytes()
        require(len(data) == records[upstream_path]["bytes"]
                and hashlib.sha256(data).hexdigest() == records[upstream_path]["sha256"],
                f"local upstream notice changed: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path("support/ui/HEPTA_SHARED_PRESENTER.json"))
    args = parser.parse_args()
    source = json.loads(args.source.read_text())
    validate_manifest(source)
    root = check_packages(json.loads(args.metadata.read_text()), source)
    checkout_files = check_checkout(root, source)
    check_files(root, source)
    check_license_copies(args.source.parent / "licenses", source)
    print(json.dumps({"status": "passed", "commit": source["commit"], "tree": source["tree"],
                      "source_files_verified": len(source["files"]), "original_packages": sorted(PACKAGES),
                      "checkout_files_verified": checkout_files,
                      "local_license_copies_verified": len(LICENSE_COPIES),
                      "makepad_renderer_enabled": False, "send_authority_installed": False}))


if __name__ == "__main__":
    main()
