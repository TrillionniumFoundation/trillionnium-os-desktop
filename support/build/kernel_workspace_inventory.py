#!/usr/bin/env python3
"""Regenerate the kernel crate inventory from one immutable Git source tree.

This command observes tracked source, not Cargo's expanded graph or test runs.
It never edits the archived inventory or manufactures execution evidence.
"""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "kernel/asterinas/"
MANIFEST = PREFIX + "Cargo.toml"
OUTPUT = ROOT / "docs/modules/kernel-workspace/inventory.json"
HISTORY = "history/inventory-10dae5ea.json"
HISTORY_SHA256 = "3a1b46def2f14f11fb3fdd12452858b8172f7c71f71e88023fd19009239e862e"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def sha(content):
    return hashlib.sha256(content).hexdigest()


def inventory(source_ref):
    commit = git("rev-parse", "--verify", source_ref + "^{commit}").decode().strip()
    tree = git("rev-parse", commit + "^{tree}").decode().strip()
    files = git("ls-tree", "-r", "--name-only", "-z", commit, "--", PREFIX).decode().split("\0")[:-1]

    def read(path):
        return git("show", commit + ":" + path)

    manifest_bytes = read(MANIFEST)
    workspace = tomllib.loads(manifest_bytes.decode())["workspace"]
    members = workspace["members"]
    if len(members) != len(set(members)) or any(
        PurePosixPath(member).is_absolute() or ".." in PurePosixPath(member).parts
        or any(char in member for char in "*?[") for member in members
    ):
        raise ValueError("inventory requires unique explicit workspace members")
    crates = []
    for member in members:
        directory = PREFIX + member
        manifest = directory + "/Cargo.toml"
        content = read(manifest)
        package = tomllib.loads(content.decode())
        name = package["package"]["name"]
        entry = directory + "/" + package.get("lib", {}).get("path", "src/lib.rs")
        if entry not in files:
            entry = directory + "/src/main.rs"
        entry_bytes = read(entry)
        sources = sorted(path for path in files if path.startswith(directory + "/src/") and path.endswith(".rs"))
        lines, tests = [], Counter()
        for path in sources:
            source = read(path)
            lines.append(path + "\0" + sha(source))
            tests.update(re.findall(r"#\[(ktest|test)(?:\([^]]*\))?\]", source.decode()))
        if member.startswith(("osdk/", "ostd")):
            handbook = "ostd-and-tooling.md"
        elif member.startswith("kernel/libs/"):
            handbook = "kernel-libraries.md"
        else:
            handbook = "kernel-components.md"
        handbook_text = read("docs/modules/kernel-workspace/" + handbook).decode()
        if not re.search(r"^## " + re.escape(name) + r"$", handbook_text, re.MULTILINE):
            raise ValueError("missing explicit handbook entry for " + name)
        crates.append({
            "package": name, "member": member,
            "manifest": manifest, "manifest_sha256": sha(content),
            "entry": entry, "entry_sha256": sha(entry_bytes),
            "directory_markdown": sorted(path for path in files
                if str(PurePosixPath(path).parent) == directory and path.endswith(".md")),
            "default_member": member in workspace["default-members"],
            "proc_macro": package.get("lib", {}).get("proc-macro", False),
            "features": package.get("features", {}),
            "direct_dependencies": list(package.get("dependencies", {})),
            "target_dependencies": {target: list(config.get("dependencies", {}))
                for target, config in package.get("target", {}).items() if config.get("dependencies")},
            "handbook": handbook + "#" + name,
            "source_file_count": len(sources),
            "source_files_sha256": sha(("\n".join(lines) + ("\n" if lines else "")).encode()),
            "static_test_declarations": dict(sorted(tests.items())),
            "validation_status": "static_source_snapshot_only",
        })
    with_markdown = sum(bool(crate["directory_markdown"]) for crate in crates)
    return {
        "schema_version": 2, "source_commit": commit, "source_tree": tree,
        "scope": f"exact {len(members)} explicit members of {MANIFEST}; excludes nested independent workspaces and evidence/results",
        "workspace_manifest": MANIFEST, "workspace_manifest_sha256": sha(manifest_bytes),
        "summary": {"members": len(members), "with_same_directory_markdown": with_markdown,
            "without_same_directory_markdown": len(members) - with_markdown, "handbook_entries": len(crates)},
        "source_hash_method": "SHA256 of sorted source-files lines: repository-relative path + NUL + SHA256(file bytes), joined by LF with terminal LF. Only tracked src/**/*.rs in each crate; root/manifest hashes separate. Static declarations are regex observations, not expanded tests or execution counts.",
        "dependency_scope": "direct_dependencies lists manifest [dependencies] keys; target_dependencies lists [target.*.dependencies] keys. Neither field is an expanded Cargo graph or a runtime dependency claim.",
        "historical_inventory": {"path": HISTORY, "sha256": HISTORY_SHA256},
        "crates": crates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", help="committed source to observe; required when regenerating")
    parser.add_argument("--check", action="store_true", help="verify the current inventory against its pinned source")
    args = parser.parse_args()
    if not args.check and not args.source_ref:
        parser.error("regeneration requires --source-ref; uncommitted working files are never silently attributed to HEAD")
    if sha((OUTPUT.parent / HISTORY).read_bytes()) != HISTORY_SHA256:
        parser.exit(1, "archived historical inventory changed; restore its exact original bytes\n")
    previous = json.loads(OUTPUT.read_text()) if args.check else None
    source = args.source_ref or previous["source_commit"]
    current = inventory(source)
    if args.check:
        if current != previous:
            parser.exit(1, "kernel inventory differs from the pinned source; regenerate explicitly\n")
    else:
        OUTPUT.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"source_commit": current["source_commit"], **current["summary"],
                      "operation": "verified" if args.check else "regenerated", "execution_evidence": False}))


if __name__ == "__main__":
    main()
