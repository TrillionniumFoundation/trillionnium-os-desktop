#!/usr/bin/env python3
"""Check the single original Hepta source across product manifests and locks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import tomllib

# Read this adjacent source directly, including under isolated Python. A
# cached helper must not replace the reviewed mandatory-source policy.
require_root_admin_sources = runpy.run_path(
    str(Path(__file__).with_name("root_admin_sources.py")))["require_root_admin_sources"]

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
# These locks contain the actual local product consumers. Cargo locks their
# nonoptional direct Git dependencies. Anchor that
# layer too, so deleting all inner original owners cannot become N/A.
LOCAL_CONSUMERS = {
    "ui/Cargo.lock": ("ui/core/Cargo.toml", "services/hepta-session-host/Cargo.toml"),
    "support/ui/preedit-sdk/Cargo.lock": ("ui/core/Cargo.toml", "services/hepta-session-host/Cargo.toml"),
    "services/hepta-session-host/Cargo.lock": ("services/hepta-session-host/Cargo.toml",),
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


def is_critical(name):
    return name in CRITICAL_PACKAGES or name.startswith("aws-")


def original_identity(identity, owner_source):
    # Cargo records original workspace/vendor packages as path nodes upstream,
    # and as the selected Git source in downstream product locks.
    if identity[2] is None and owner_source is not None:
        return identity[:2] + (owner_source, identity[3])
    return identity


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
                if is_critical(dependency.split(" ", 1)[0]):
                    self.resolve(dependency)

    def resolve(self, dependency):
        match = re.fullmatch(r"([^ ]+)(?: ([^ ()]+))?(?: \(([^()]+)\))?", dependency)
        require(match is not None, f"Invalid lock dependency: {self.label}: {dependency}")
        name, version, source = match.groups()
        candidates = [p for p in self.by_name.get(name, [])
                      if (version is None or p["version"] == version)
                      and (source is None or p.get("source") == source
                           or (source.startswith("git+") and "#" not in source
                               and p.get("source", "").split("#", 1)[0] == source))]
        require(len(candidates) == 1,
                f"Missing or ambiguous lock dependency: {self.label}: {dependency}")
        return candidates[0]

    def edges(self, package):
        result = {}
        fixed = CRITICAL_EDGES.get(package["name"])
        selected = fixed if fixed is not None else {
            d.split(" ", 1)[0] for d in package.get("dependencies", [])
            if is_critical(d.split(" ", 1)[0])}
        for dependency in package.get("dependencies", []):
            name = dependency.split(" ", 1)[0]
            if name in selected:
                require(name not in result, f"Duplicate critical edge: {self.label}: {name}")
                result[name] = package_identity(self.resolve(dependency))
        required = fixed - {"prettyplease"} if fixed is not None else set()
        require(required <= result.keys(),
                f"Missing critical edge: {self.label}: {package['name']}")
        return result


def verify_critical_graph(data, reference, label, owner_edges=None, owner_source=None):
    graph = LockedGraph(data, label)
    allowed = {original_identity(package_identity(p), owner_source): p for p in reference.packages
               if is_critical(p["name"])}
    nodes, edges = [], []
    for package in graph.packages:
        if not is_critical(package["name"]):
            continue
        identity = package_identity(package)
        require(identity in allowed,
                f"Critical package differs from original lock: {label}: {identity}")
        actual = graph.edges(package)
        expected = {key: original_identity(value, owner_source)
                    for key, value in reference.edges(allowed[identity]).items()}
        # AWS external optional features may select fewer edges than the
        # upstream workspace. Every present edge must keep its exact identity;
        # original owners' mandatory edges are checked from tracked manifests.
        selected_expected = ({key: value for key, value in expected.items() if key in actual}
                             if package["name"].startswith("aws-") else
                             {key: value for key, value in expected.items()
                              if key != "prettyplease" or key in actual})
        require(actual == selected_expected,
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
    # Check identities before choosing edges. Looking up only present packages
    # at the expected source lets a registry/version/checksum substitution make
    # an original intermediate owner disappear from the checks below.
    original_owners = {original_identity(package_identity(p), owner_source)
                       for p in reference.packages if p.get("source") is None}
    original_owners.update((name, version, owner_source, None)
                           for name, version in (owner_edges or {}))
    owner_names = {identity[0] for identity in original_owners}
    for package in graph.packages:
        if owner_source is None:
            continue
        identity = package_identity(package)
        if package["name"] in owner_names:
            require(identity in original_owners,
                    f"Original owner identity differs: {label}: {identity}")
        if package.get("source") != owner_source:
            continue
        require(identity in original_owners,
                f"Unknown original owner identity: {label}: {identity}")
        for name, expected in (owner_edges or {}).get((package["name"], package["version"]), {}).items():
            expected = original_identity(expected, owner_source)
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
    """Bind original owners and mandatory bridges to tracked Cargo manifests.

    Optional features of unrelated external packages are not inferred from
    the upstream workspace's broader lock. Only owners present in a consumer
    require their nonoptional normal/build (including target) dependencies.
    Dev dependencies and absent optional local packages are not made mandatory.
    Cargo's locked metadata still verifies selected consumer features.
    """
    originals = {(p["name"], p["version"]): p for p in reference.packages
                 if p.get("source") is None}
    records, manifests = [], {}
    entries = git_output(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0")
    for entry in entries:
        if not entry:
            continue
        header, raw_name = entry.split(b"\t", 1)
        name = raw_name.decode()
        if name != "Cargo.toml" and not name.endswith("/Cargo.toml"):
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
        manifests[name] = tomllib.loads(data.decode())
        records.append({"path": name, "git_blob": blob, "sha256": hashlib.sha256(data).hexdigest()})

    def manifest_path(directory, relative):
        path = Path(os.path.normpath(str(Path(directory) / relative / "Cargo.toml")))
        require(not path.is_absolute() and ".." not in path.parts,
                f"Original dependency escapes the repository: {relative}")
        name = path.as_posix()
        require(name in manifests, f"Original dependency manifest is missing: {name}")
        return name

    def workspace_for(name):
        manifest = manifests[name]
        explicit = manifest.get("package", {}).get("workspace")
        if explicit is not None:
            candidate = manifest_path(Path(name).parent, explicit)
            require("workspace" in manifests[candidate], f"Missing original workspace: {candidate}")
            return candidate, manifests[candidate]["workspace"]
        for directory in (Path(name).parent, *Path(name).parent.parents):
            candidate = (directory / "Cargo.toml").as_posix()
            if candidate in manifests and "workspace" in manifests[candidate]:
                return candidate, manifests[candidate]["workspace"]
        return None, {}

    owners, identities = {}, {}
    for name, manifest in manifests.items():
        package = manifest.get("package", {})
        if not package:
            continue
        _, workspace = workspace_for(name)
        version = package.get("version")
        if isinstance(version, dict) and version.get("workspace"):
            version = workspace["package"]["version"]
        identity = (package.get("name"), version)
        require(all(isinstance(value, str) for value in identity), f"Invalid original owner manifest: {name}")
        require(identity not in owners, f"Ambiguous original owner manifest: {identity}")
        owners[identity] = name
        identities[name] = identity + (None, None)
    require(originals.keys() <= owners.keys(), "Original owner manifest is missing")

    result = {}
    for identity, name in owners.items():
        manifest = manifests[name]
        workspace_name, workspace = workspace_for(name)
        owner = originals.get(identity)
        locked = {}
        if owner is not None:
            for dependency in owner.get("dependencies", []):
                target = reference.resolve(dependency)
                locked.setdefault(target["name"], []).append(package_identity(target))
        tables = [manifest]
        tables.extend(manifest.get("target", {}).values())
        edges = {}
        for table in tables:
            for key in ("dependencies", "build-dependencies"):
                for alias, dependency in table.get(key, {}).items():
                    options = dependency if isinstance(dependency, dict) else {}
                    if options.get("optional", False):
                        continue
                    inherited = workspace.get("dependencies", {}).get(alias, {}) if options.get("workspace") else {}
                    inherited = inherited if isinstance(inherited, dict) else {}
                    effective = inherited | options
                    target = effective.get("package", alias)
                    if "path" in effective:
                        base = workspace_name if "path" in inherited else name
                        target_path = manifest_path(Path(base).parent, effective["path"])
                        expected = identities.get(target_path)
                        require(expected is not None and expected[0] == target,
                                f"Original path dependency identity differs: {name}: {alias}")
                    else:
                        candidates = locked.get(target, [])
                        if not is_critical(target):
                            candidates = [item for item in candidates if item[2] is None]
                            if not candidates:
                                continue
                        elif owner is None:
                            candidates = [package_identity(p) for p in reference.by_name.get(target, [])]
                        require(len(candidates) == 1,
                                f"Missing or ambiguous original mandatory lock edge: {identity}: {target}")
                        expected = candidates[0]
                    require(target not in edges or edges[target] == expected,
                            f"Ambiguous original owner dependency: {identity}: {target}")
                    edges[target] = expected
        result[identity] = edges
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


def verify_consumer_edges(root, data, label, owners, owner_source):
    graph = LockedGraph(data, label)
    checked = []
    for name in LOCAL_CONSUMERS.get(label, ()):
        manifest = tomllib.loads((root / name).read_text())
        package = manifest["package"]
        identity = (package["name"], package["version"], None, None)
        matches = graph.by_name.get(package["name"], [])
        require(len(matches) == 1 and package_identity(matches[0]) == identity,
                f"Local product consumer identity differs: {label}: {name}")
        locked = matches[0]
        tables = [manifest]
        tables.extend(manifest.get("target", {}).values())
        for table in tables:
            for key in ("dependencies", "build-dependencies"):
                for alias, dependency in table.get(key, {}).items():
                    if (not isinstance(dependency, dict) or dependency.get("git") != REPOSITORY
                            or dependency.get("optional", False)):
                        continue
                    target = dependency.get("package", alias)
                    candidates = [(n, version, owner_source, None) for n, version in owners if n == target]
                    require(len(candidates) == 1, f"Ambiguous original consumer target: {name}: {target}")
                    edges = [d for d in locked.get("dependencies", []) if d.split(" ", 1)[0] == target]
                    require(len(edges) == 1, f"Missing original consumer dependency: {label}: {name} -> {target}")
                    actual = package_identity(graph.resolve(edges[0]))
                    require(actual == candidates[0], f"Original consumer dependency differs: {label}: {name} -> {target}")
                    checked.append({"manifest": name, "from": identity_record(identity), "to": identity_record(actual)})
    return checked


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
    require_root_admin_sources(source["files"])
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
        consumer_edges = {name: verify_consumer_edges(root, (root / name).read_bytes(), name,
                                                     owner_edges, expected) for name in LOCKS}
        critical = {"reference_lock_sha256": hashlib.sha256(data).hexdigest(),
                    "hepta_commit": commit, "hepta_tree": tree,
                    "original_owner_manifests": owner_manifests,
                    "local_consumer_edges": consumer_edges,
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
