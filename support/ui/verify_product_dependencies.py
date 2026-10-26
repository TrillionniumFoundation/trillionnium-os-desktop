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
    "services/hepta-os/Cargo.toml",
)
REQUIRED_DEPENDENCIES = {
    "ui/core/Cargo.toml": {"hepta-control-core", "hepta-robrix-ui"},
    "services/hepta-session-host/Cargo.toml": {
        "codex-hepta-memory", "codex-hepta-objective", "codex-hepta-operations",
        "codex-hepta-agentd", "hepta-control-core",
        "codex-hepta-fleet", "codex-hepta-supervisor", "codex-hepta-evidence",
        "codex-app-server-client", "codex-state", "codex-utils-absolute-path",
        "codex-hepta-contracts", "codex-hepta-paths",
    },
}
LOCKS = {
    "ui/Cargo.lock": {"hepta-control-core", "hepta-robrix-ui"},
    "services/hepta-session-host/Cargo.lock": {
        "codex-hepta-memory", "codex-hepta-objective", "codex-hepta-operations",
        "codex-hepta-agentd", "codex-hepta-fleet", "codex-hepta-supervisor",
    },
    "services/hepta-os/Cargo.lock": set(),
    "support/ui/Cargo.lock": set(),
    "tests/ui/Cargo.lock": set(),
    "support/ui/preedit-sdk/Cargo.lock": {"hepta-control-core", "hepta-robrix-ui"},
}
SHARED_VERSIONS = {"serde": "1.0.229", "serde_json": "1.0.154", "tokio": "1.53.3", "libc": "0.2.191"}
REQUIRED_FILES = {
    "codex-rs/hepta-objective/src/lib.rs",
    "codex-rs/hepta-objective/src/notes_literal_source.rs",
    "codex-rs/hepta-agentd/src/notes_ui_wire.rs",
    "codex-rs/hepta-agentd/src/notes_ui_worker.rs",
    "apps/hepta-control-ui/rust/robrix-ui/src/native_presentation/mod.rs",
    "apps/hepta-control-ui/rust/robrix-ui/src/robrix/composer_transaction.rs",
    "apps/hepta-control-ui/rust/robrix-ui/src/robrix/composer_transaction_tests.rs",
    "codex-rs/hepta-agentd/src/notes_thread_seed.rs",
    "codex-rs/hepta-agentd/src/notes_thread_runtime.rs",
    "codex-rs/hepta-agentd/src/notes_thread_tool.rs",
    "codex-rs/hepta-agentd/src/notes_launch_mode.rs",
    "codex-rs/hepta-agentd/src/root_notes_startup.rs",
    "codex-rs/hepta-agentd/src/authority_host_logind.rs",
    "codex-rs/hepta-agentd/src/authority_host_notes_successor.rs",
    "codex-rs/hepta-agentd/src/authority_host_checkpoint_material.rs",
    "codex-rs/hepta-agentd/src/root_production_writer_handoff.rs",
    "codex-rs/hepta-agentd/src/authority_host_writer_rotate.rs",
    "codex-rs/hepta-memory/src/cognitive_checkpoint_image.rs",
    "codex-rs/third_party/aws-config-1.12.0/Cargo.toml",
}
MIRRORED_FIXTURES = {
    "codex-rs/hepta-agentd/tests/fixtures/notes-document-observation-v1.json":
        "tests/ui/notes-document-observation-v1.json",
    "codex-rs/hepta-agentd/tests/fixtures/notes-model-v1.json": "tests/ui/notes-model-v1.json",
    "codex-rs/hepta-memory/tests/fixtures/notes-model-v1.json": "tests/ui/notes-model-v1.json",
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
            "Source contract omits the shared literal Notes compiler or original composer transaction")
    files = {entry["path"]: entry for entry in source["files"]}
    require(len(files) == len(source["files"]), "Duplicate original source identity")
    for original, local in MIRRORED_FIXTURES.items():
        require(original in files, "Source contract omits the Notes readback wire fixture")
        data = (root / local).read_bytes()
        require(len(data) == files[original]["bytes"]
                and hashlib.sha256(data).hexdigest() == files[original]["sha256"],
                "Desktop and original Notes readback wire fixtures differ")
    dependency_count = 0
    for name in MANIFESTS:
        manifest = tomllib.loads((root / name).read_text())
        for package in REQUIRED_DEPENDENCIES.get(name, set()):
            dependency = manifest.get("dependencies", {}).get(package, {})
            require(dependency.get("git") == REPOSITORY and dependency.get("rev") == commit,
                    f"Original owner dependency substituted: {name}: {package}")
        tables = [manifest.get(key, {}) for key in ("dependencies", "dev-dependencies", "build-dependencies")]
        tables.extend(manifest.get("patch", {}).values())
        if name in ("ui/Cargo.toml", "services/hepta-session-host/Cargo.toml"):
            patch = manifest.get("patch", {}).get("crates-io", {}).get("aws-config", {})
            require(patch.get("git") == REPOSITORY and patch.get("rev") == commit,
                    f"Original AWS security patch missing: {name}")
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
        if name in ("ui/Cargo.lock", "support/ui/preedit-sdk/Cargo.lock"):
            widgets = [package for package in packages if package["name"] == "makepad-widgets"]
            require(len(widgets) == 1, f"Expected exactly one original widgets package: {name}")
            if name == "ui/Cargo.lock":
                baseline = json.loads((root / "support/ui/linux-text-profile.json").read_text())
                sdk = "git+" + baseline["makepad_repository"] + "?rev=" + baseline["makepad_commit"] + "#" + baseline["makepad_commit"]
                require(widgets[0].get("source") == sdk, "Default UI lock must retain the original Git SDK")
            else:
                require(widgets[0].get("source") is None, "Prepared UI lock must resolve the explicit path SDK")
        for package in packages:
            if package["name"] in SHARED_VERSIONS:
                require(package["version"] == SHARED_VERSIONS[package["name"]],
                        f"Shared package version differs: {name}: {package['name']}")
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
