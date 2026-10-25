#!/usr/bin/env python3
"""Check the single original Hepta source across product manifests and locks."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "support/ui/HEPTA_SHARED_PRESENTER.json"
REPOSITORY = "https://github.com/TrillionniumFoundation/hepta-private-ci"
MANIFESTS = (
    "ui/Cargo.toml",
    "ui/core/Cargo.toml",
    "services/hepta-session-host/Cargo.toml",
)
REQUIRED_DEPENDENCIES = {
    "ui/core/Cargo.toml": {"hepta-control-core", "hepta-robrix-ui"},
    "services/hepta-session-host/Cargo.toml": {
        "codex-hepta-memory", "codex-hepta-objective", "codex-hepta-operations",
        "codex-hepta-agentd", "hepta-control-core",
    },
}
LOCKS = {
    "ui/Cargo.lock": {"hepta-control-core", "hepta-robrix-ui"},
    "services/hepta-session-host/Cargo.lock": {
        "codex-hepta-memory", "codex-hepta-objective", "codex-hepta-operations",
    },
}
REQUIRED_FILES = {
    "codex-rs/hepta-objective/src/lib.rs",
    "codex-rs/hepta-objective/src/notes_literal_source.rs",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root=ROOT, hepta_root=None):
    source = json.loads((root / SOURCE).read_text())
    commit, tree = source["commit"], source["tree"]
    require(len(commit) == 40 and all(c in "0123456789abcdef" for c in commit),
            "Original Hepta source must use a full commit")
    require(len(tree) == 40 and all(c in "0123456789abcdef" for c in tree),
            "Original Hepta source must use a full tree")
    require(source["repository"] == "TrillionniumFoundation/hepta-private-ci",
            "Unexpected original repository")
    require(REQUIRED_FILES <= {entry["path"] for entry in source["files"]},
            "Source contract omits the shared literal Notes compiler")
    dependency_count = 0
    for name in MANIFESTS:
        manifest = tomllib.loads((root / name).read_text())
        for package in REQUIRED_DEPENDENCIES.get(name, set()):
            dependency = manifest.get("dependencies", {}).get(package, {})
            require(dependency.get("git") == REPOSITORY and dependency.get("rev") == commit,
                    f"Original owner dependency substituted: {name}: {package}")
        tables = [manifest.get(key, {}) for key in ("dependencies", "dev-dependencies", "build-dependencies")]
        tables.extend(manifest.get("patch", {}).values())
        for target in manifest.get("target", {}).values():
            tables.extend(target.get(key, {}) for key in ("dependencies", "dev-dependencies", "build-dependencies"))
        for table in tables:
            for package, value in table.items():
                if isinstance(value, dict) and value.get("git") == REPOSITORY:
                    require(value.get("rev") == commit and not ({"branch", "tag", "path"} & value.keys()),
                            f"Mixed original Hepta dependency: {name}: {package}")
                    dependency_count += 1
    require(dependency_count > 0, "No original Hepta dependencies found")
    expected = f"git+{REPOSITORY}?rev={commit}#{commit}"
    lock_counts = {}
    for name, required in LOCKS.items():
        packages = tomllib.loads((root / name).read_text()).get("package", [])
        original = [p for p in packages if REPOSITORY in p.get("source", "")]
        require(required <= {p["name"] for p in original}, f"Original owner packages missing from {name}")
        require(all(p["source"] == expected for p in original), f"Mixed original Hepta sources in {name}")
        lock_counts[name] = len(original)
    preedit = json.loads((root / "support/ui/linux-preedit-profile.json").read_text())
    require((preedit["hepta_commit"], preedit["hepta_tree"]) == (commit, tree),
            "Preedit profile differs from the product source")
    if hepta_root is not None:
        def git(ref):
            return subprocess.check_output(["git", "-C", str(hepta_root), "rev-parse", ref], text=True).strip()
        require((git("HEAD"), git("HEAD^{tree}")) == (commit, tree), "Original checkout identity differs")
        for entry in source["files"]:
            path = hepta_root / entry["path"]
            require(path.is_file() and not path.is_symlink(), f"Missing original source: {entry['path']}")
            data = path.read_bytes()
            require(len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"],
                    f"Changed original source: {entry['path']}")
    return {"schema": "trill.product-dependencies.v1", "passed": True,
            "hepta_commit": commit, "hepta_tree": tree, "manifest_dependencies": dependency_count,
            "locked_original_packages": lock_counts, "original_source_bytes_checked": hepta_root is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--hepta-root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root, args.hepta_root), sort_keys=True))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Product dependencies refused: {error}\n")


if __name__ == "__main__":
    main()
