#!/usr/bin/env python3
"""Check the single original Hepta source across product manifests and locks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
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
    "codex-rs/Cargo.lock",
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


CRITICAL_PACKAGES = {"bindgen", "prettyplease", "zstd", "zstd-safe", "zstd-sys"}
CRITICAL_EDGES = {
    "bindgen": {"syn", "prettyplease"}, "prettyplease": {"syn"},
    "zstd": {"zstd-safe"}, "zstd-safe": {"zstd-sys"}, "zstd-sys": set(),
}


def package_identity(package):
    return tuple(package.get(key) for key in ("name", "version", "source", "checksum"))


def identity_record(identity):
    return dict(zip(("name", "version", "source", "checksum"), identity))


def git_output(root, *arguments):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    return subprocess.check_output(["git", "-C", str(root), *arguments], env=environment)


class LockedGraph:
    """Resolve Cargo lock edges without guessing among same-name packages."""

    def __init__(self, data, label):
        self.label = label
        self.packages = tomllib.loads(data.decode()).get("package", [])
        self.by_name = {}
        ids = set()
        for package in self.packages:
            identity = package_identity(package)
            require(isinstance(identity[0], str) and isinstance(identity[1], str),
                    f"Invalid locked package: {label}")
            require(identity[:3] not in ids, f"Duplicate locked package: {label}: {identity[:3]}")
            ids.add(identity[:3])
            self.by_name.setdefault(package["name"], []).append(package)
        # A deleted critical node must not turn a dangling reference into N/A.
        for package in self.packages:
            for dependency in package.get("dependencies", []):
                if dependency.split(" ", 1)[0] in CRITICAL_PACKAGES:
                    self.resolve(dependency)

    def resolve(self, dependency):
        match = re.fullmatch(r"([^ ]+)(?: ([^ ()]+))?(?: \(([^()]+)\))?", dependency)
        require(match is not None, f"Invalid lock dependency: {self.label}: {dependency}")
        name, version, source = match.groups()
        candidates = [p for p in self.by_name.get(name, [])
                      if (version is None or p["version"] == version)
                      and (source is None or p.get("source") == source)]
        require(len(candidates) == 1,
                f"Missing or ambiguous lock dependency: {self.label}: {dependency}")
        return candidates[0]

    def edges(self, package):
        result = {}
        selected = CRITICAL_EDGES[package["name"]]
        for dependency in package.get("dependencies", []):
            name = dependency.split(" ", 1)[0]
            if name in selected:
                require(name not in result, f"Duplicate critical edge: {self.label}: {name}")
                result[name] = package_identity(self.resolve(dependency))
        required = selected - {"prettyplease"}
        require(required <= result.keys(),
                f"Missing critical edge: {self.label}: {package['name']}")
        return result


def verify_critical_graph(data, reference, label, owner_edges=None, owner_source=None):
    graph = LockedGraph(data, label)
    allowed = {package_identity(p): p for p in reference.packages
               if p["name"] in CRITICAL_PACKAGES}
    nodes, edges = [], []
    for package in graph.packages:
        if package["name"] not in CRITICAL_PACKAGES:
            continue
        identity = package_identity(package)
        require(identity in allowed,
                f"Critical package differs from original lock: {label}: {identity}")
        actual = graph.edges(package)
        expected = reference.edges(allowed[identity])
        require(actual == {key: value for key, value in expected.items()
                           if key != "prettyplease" or key in actual},
                f"Critical dependency edge differs from original lock: {label}: {identity[:2]}")
        if package["name"] == "bindgen" and "prettyplease" in actual:
            printer = graph.resolve(next(d for d in package["dependencies"]
                                         if d.split(" ", 1)[0] == "prettyplease"))
            require(graph.edges(printer)["syn"] == actual["syn"],
                    f"Bindgen parser/printer type mismatch: {label}: {identity[:2]}")
        nodes.append(identity_record(identity))
        edges.extend({"from": identity_record(identity), "to": identity_record(target)}
                     for target in actual.values())
    incoming = []
    for package in graph.packages:
        if owner_source is None or package.get("source") != owner_source:
            continue
        for name, expected in (owner_edges or {}).get((package["name"], package["version"]), {}).items():
            matches = [dependency for dependency in package.get("dependencies", [])
                       if dependency.split(" ", 1)[0] == name]
            require(len(matches) == 1,
                    f"Missing mandatory original owner dependency: {label}: {package['name']} -> {name}")
            actual = package_identity(graph.resolve(matches[0]))
            require(actual == expected,
                    f"Mandatory original owner edge differs: {label}: {package['name']} -> {name}")
            incoming.append({"from": identity_record(package_identity(package)), "to": identity_record(actual)})
    result = {"applicable": bool(nodes), "checked": True, "nodes": nodes, "edges": edges}
    if owner_edges is not None:
        result["original_owner_edges"] = incoming
    return result


def mandatory_owner_edges(root, reference):
    """Read mandatory original-owner edges from actual tracked manifests.

    Optional features of unrelated external packages are not inferred from
    the upstream workspace's broader lock. Cargo's locked metadata remains
    required to verify those selected consumer features.
    """
    owners = {(p["name"], p["version"]): p for p in reference.packages
              if p.get("source") is None and any(
                  d.split(" ", 1)[0] in CRITICAL_PACKAGES for d in p.get("dependencies", []))}
    workspace = tomllib.loads((root / "codex-rs/Cargo.toml").read_text())["workspace"]
    records, result, found = [], {}, set()
    entries = git_output(root, "ls-tree", "-r", "-z", "HEAD", "--", "codex-rs").split(b"\0")
    for entry in entries:
        if not entry:
            continue
        header, raw_name = entry.split(b"\t", 1)
        name = raw_name.decode()
        if not name.endswith("/Cargo.toml"):
            continue
        mode, kind, blob = header.decode().split()
        require(kind == "blob" and mode == "100644", f"Original manifest is not a tracked regular file: {name}")
        path = root
        for part in Path(name).parts:
            path /= part
            require(not path.is_symlink(), f"Symlink in original manifest path: {name}")
        data = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(actual == blob, f"Changed tracked original dependency manifest: {name}")
        manifest = tomllib.loads(data.decode())
        package = manifest.get("package", {})
        version = package.get("version")
        if isinstance(version, dict) and version.get("workspace"):
            version = workspace["package"]["version"]
        identity = (package.get("name"), version)
        if identity not in owners:
            continue
        require(identity not in found, f"Ambiguous original owner manifest: {identity}")
        found.add(identity)
        tables = [manifest]
        tables.extend(manifest.get("target", {}).values())
        mandatory = set()
        for table in tables:
            for key in ("dependencies", "build-dependencies"):
                for alias, dependency in table.get(key, {}).items():
                    options = dependency if isinstance(dependency, dict) else {}
                    if options.get("optional", False):
                        continue
                    inherited = workspace.get("dependencies", {}).get(alias, {}) if options.get("workspace") else {}
                    inherited = inherited if isinstance(inherited, dict) else {}
                    target = options.get("package", inherited.get("package", alias))
                    if target in CRITICAL_PACKAGES:
                        mandatory.add(target)
        edges = {}
        for dependency in owners[identity].get("dependencies", []):
            target = dependency.split(" ", 1)[0]
            if target in mandatory:
                require(target not in edges, f"Ambiguous original owner dependency: {identity}: {target}")
                edges[target] = package_identity(reference.resolve(dependency))
        require(mandatory <= edges.keys(), f"Original owner lock omits mandatory dependencies: {identity}")
        result[identity] = edges
        records.append({"path": name, "git_blob": blob, "sha256": hashlib.sha256(data).hexdigest()})
    require(found == owners.keys(), "Original critical owner manifest is missing")
    return result, records


def reference_lock(hepta_root, files):
    name = "codex-rs/Cargo.lock"
    entry = files[name]
    data = (hepta_root / name).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    tracked = git_output(hepta_root, "ls-tree", "HEAD", "--", name).decode().strip()
    require(tracked == f"100644 blob {blob}\t{name}" and entry["git_blob"] == blob,
            "Original Cargo lock is not the recorded tracked regular blob")
    return data


def verify(root=ROOT, hepta_root=None, *, source_only=False):
    require(source_only or hepta_root is not None,
            "Full dependency verification requires the original Hepta checkout; use explicit source-only preflight")
    require(not source_only or hepta_root is None,
            "Source-only preflight cannot replace a supplied original checkout")
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
    critical = None
    if hepta_root is not None:
        def git(ref):
            return git_output(hepta_root, "rev-parse", ref).decode().strip()
        require((git("HEAD"), git("HEAD^{tree}")) == (commit, tree), "Original checkout identity differs")
        for entry in source["files"]:
            path = hepta_root / entry["path"]
            require(path.is_file() and not path.is_symlink(), f"Missing original source: {entry['path']}")
            data = path.read_bytes()
            require(len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"],
                    f"Changed original source: {entry['path']}")
        data = reference_lock(hepta_root, files)
        reference = LockedGraph(data, "original Hepta Cargo.lock")
        verify_critical_graph(data, reference, "original Hepta Cargo.lock")
        owner_edges, owner_manifests = mandatory_owner_edges(hepta_root, reference)
        critical = {"reference_lock_sha256": hashlib.sha256(data).hexdigest(),
                    "hepta_commit": commit, "hepta_tree": tree,
                    "original_owner_manifests": owner_manifests,
                    "roots": {name: verify_critical_graph((root / name).read_bytes(), reference, name,
                                                         owner_edges, expected)
                              for name in LOCKS}}
    return {"schema": "trill.product-dependencies.v2", "passed": True,
            "hepta_commit": commit, "hepta_tree": tree, "manifest_dependencies": dependency_count,
            "locked_original_packages": lock_counts, "original_source_bytes_checked": hepta_root is not None,
            "source_only": source_only, "critical_graph_checked": critical is not None,
            "critical_graph": critical}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--hepta-root", type=Path)
    parser.add_argument("--source-only", action="store_true", help="Source preflight without dependency graph qualification")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root, args.hepta_root, source_only=args.source_only), sort_keys=True))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Product dependencies refused: {error}\n")


if __name__ == "__main__":
    main()
