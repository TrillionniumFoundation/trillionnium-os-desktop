#!/usr/bin/env python3
"""Pin and check one clean Hepta/OS source combination; never grant effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

HISTORY_OWNER = "995b6fb9ef73ada7c3348b01deb28940a2c4a2d1"
OS_ROLES = {
    "hepta_adapter", "notes_broker", "notes_core", "bootstrap_core",
    "session_entry", "session_bootstrap", "notes_app", "notes_app_target",
    "session_contract", "objective_contract", "history_contract", "cpu_contract",
    "notes_persistence", "session_ipc", "ui_workspace", "ui_lock",
    "kernel_capability", "kernel_unix_credential", "kernel_anon_budget",
    "kernel_vm_charge", "kernel_cpu_config", "kernel_credentials_edit", "kernel_rcu_idle",
}
HEPTA_ROLES = {
    "production_writer_host", "notes_channel", "notes_bootstrap", "notes_owner",
    "durable_writer", "lease_outbox", "final_use_authority", "final_use_control", "history_owner",
    "hepta_workspace", "hepta_lock", "hepta_toolchain", "production_composition",
    "protected_authority", "issuer_transport", "grant_worker",
    "notes_owner_impl", "notes_recovery", "notes_readback", "notes_first_composition",
}
GOLDEN_ROLES = {"notes_target", "notes_bootstrap", "notes_bootstrap_v2", "notes_recovery"}
PRODUCTION = {
    "activation": "disabled",
    "effects_authorized": False,
    "unconfigured": [
        "production_grant_provider",
        "protected_authority_clock",
        "external_authority_frontier_store",
        "trusted_issuer_keyring",
        "revocation_head",
        "recovered_writer_configuration",
        "current_cut_authorization_state",
    ],
}


class ProfileError(Exception):
    """An input or source check did not establish a qualified combination."""


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def full_oid(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ProfileError(f"{label} must be a full lowercase 40-hex Git identity")
    return value


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProfileError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_bytes(data, label):
    try:
        return json.loads(data, object_pairs_hook=json_object)
    except ValueError as exc:
        raise ProfileError(f"cannot parse JSON {label}: {exc}") from exc


def load_json(path):
    try:
        return load_json_bytes(Path(path).read_bytes(), path)
    except OSError as exc:
        raise ProfileError(f"cannot read JSON {path}: {exc}") from exc


def source_path(value, label):
    if not isinstance(value, str) or not value:
        raise ProfileError(f"source map unresolved: {label}")
    path = PurePosixPath(value)
    if (path.is_absolute() or ".." in path.parts or str(path) != value
            or "\\" in value or ":" in value or "\x00" in value):
        raise ProfileError(f"invalid repository-relative source path for {label}: {value!r}")
    return value


def check_map(mapping):
    if not isinstance(mapping, dict) or set(mapping) != {"schema_version", "sources", "goldens"}:
        raise ProfileError("source map requires schema_version, sources, and goldens only")
    if mapping["schema_version"] != 1 or isinstance(mapping["schema_version"], bool):
        raise ProfileError("unsupported source map schema_version")
    sources = mapping["sources"]
    if not isinstance(sources, dict) or set(sources) != {"os", "hepta"}:
        raise ProfileError("source map requires both os and hepta sources")
    for name, roles in (("os", OS_ROLES), ("hepta", HEPTA_ROLES)):
        entries = sources[name]
        if not isinstance(entries, dict) or set(entries) != roles:
            raise ProfileError(f"source map requires exactly these {name} roles: {sorted(roles)}")
        for role, path in entries.items():
            source_path(path, f"{name}.{role}")
        if len(set(entries.values())) != len(entries):
            raise ProfileError(f"{name} source roles must name distinct files")
    goldens = mapping["goldens"]
    if not isinstance(goldens, dict) or set(goldens) != GOLDEN_ROLES:
        raise ProfileError("source map requires target, bootstrap v1/v2, and recovery goldens")
    for role, paths in goldens.items():
        if not isinstance(paths, dict) or set(paths) != {"os", "hepta"}:
            raise ProfileError(f"golden {role} requires os and hepta paths")
        for name, path in paths.items():
            source_path(path, f"{role}.{name}")
    for name in ("os", "hepta"):
        if len({paths[name] for paths in goldens.values()}) != len(GOLDEN_ROLES):
            raise ProfileError(f"{name} golden roles must name distinct files")


class Repository:
    def __init__(self, path, name):
        self.path = Path(path).resolve()
        self.name = name
        top = Path(self.git("rev-parse", "--show-toplevel").decode().strip()).resolve()
        if self.path != top:
            raise ProfileError(f"{name}: specify the repository root, not a subdirectory")
        grafts = Path(self.git("rev-parse", "--git-path", "info/grafts").decode().strip())
        if not grafts.is_absolute():
            grafts = self.path / grafts
        if grafts.exists() and grafts.stat().st_size:
            raise ProfileError(f"{name}: legacy Git grafts prevent original-history proof")

    def run(self, *args):
        env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0",
                   GIT_OPTIONAL_LOCKS="0")
        try:
            return subprocess.run(
                ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                 "-C", str(self.path), *args], capture_output=True, env=env, check=False,
            )
        except OSError as exc:
            raise ProfileError(f"{self.name}: cannot run git: {exc}") from exc

    def git(self, *args):
        result = self.run(*args)
        if result.returncode:
            detail = result.stderr.decode(errors="replace").strip()
            raise ProfileError(f"{self.name}: git {' '.join(args)} failed: {detail}")
        return result.stdout

    def check(self, head, tree):
        full_oid(head, f"{self.name} HEAD")
        full_oid(tree, f"{self.name} tree")
        actual_head = self.git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        actual_tree = self.git("rev-parse", "--verify", "HEAD^{tree}").decode().strip()
        if actual_head != head:
            raise ProfileError(f"{self.name}: HEAD mismatch: expected {head}, found {actual_head}")
        if actual_tree != tree:
            raise ProfileError(f"{self.name}: tree mismatch: expected {tree}, found {actual_tree}")
        status = self.git("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none")
        if status:
            raise ProfileError(f"{self.name}: dirty checkout (tracked or nonignored untracked files)")
        # These flags can hide changes from status; do not call that a clean checkout.
        flags = self.git("ls-files", "-v", "-z").split(b"\x00")
        if any(item and (item[:1].islower() or item[:1] == b"S") for item in flags):
            raise ProfileError(f"{self.name}: assume-unchanged or skip-worktree flags prevent clean proof")
        return {"commit": head, "tree": tree}

    def file(self, path):
        source_path(path, self.name)
        location = self.path / path
        if not location.is_file() or location.is_symlink() or not location.resolve().is_relative_to(self.path):
            raise ProfileError(f"{self.name}: required regular source file missing: {path}")
        entry = self.git("ls-tree", "HEAD", "--", path).decode().strip()
        fields = entry.split(None, 3)
        if len(fields) != 4 or fields[0] not in {"100644", "100755"} or fields[1] != "blob":
            raise ProfileError(f"{self.name}: required source must be a tracked regular blob: {path}")
        data = location.read_bytes()
        if data != self.git("cat-file", "blob", fields[2]):
            raise ProfileError(f"{self.name}: worktree bytes differ from HEAD blob: {path}")
        return data, {"path": path, "git_blob": fields[2], "sha256": sha256(data), "bytes": len(data)}

    def prove_history(self):
        if self.run("cat-file", "-e", f"{HISTORY_OWNER}^{{commit}}").returncode:
            raise ProfileError("hepta: original history owner object missing; ancestry unproven")
        proof = self.run("merge-base", "--is-ancestor", HISTORY_OWNER, "HEAD")
        if proof.returncode:
            raise ProfileError("hepta: original history owner ancestry unproven or nonancestor; "
                               "obtain sufficient original history, do not waive this check")
        return {"commit": HISTORY_OWNER, "method": "git merge-base --is-ancestor",
                "shallow_repository": self.git("rev-parse", "--is-shallow-repository").strip() == b"true"}


def create_manifest(os_repo, hepta_repo, os_head, os_tree, hepta_head, hepta_tree, mapping):
    check_map(mapping)
    os_identity = os_repo.check(os_head, os_tree)
    hepta_identity = hepta_repo.check(hepta_head, hepta_tree)
    proof = hepta_repo.prove_history()
    sources = {}
    for name, repo in (("os", os_repo), ("hepta", hepta_repo)):
        sources[name] = []
        for role, path in sorted(mapping["sources"][name].items()):
            _, record = repo.file(path)
            sources[name].append(dict(role=role, **record))
    goldens = []
    for role, paths in sorted(mapping["goldens"].items()):
        os_data, _ = os_repo.file(paths["os"])
        hepta_data, _ = hepta_repo.file(paths["hepta"])
        if os_data != hepta_data:
            raise ProfileError(f"golden byte mismatch: {role}")
        goldens.append({"role": role, "os_path": paths["os"], "hepta_path": paths["hepta"],
                        "sha256": sha256(os_data), "bytes": len(os_data)})
    # Detect checkout changes during the preceding reads.
    os_repo.check(os_head, os_tree)
    hepta_repo.check(hepta_head, hepta_tree)
    manifest = {
        "schema_version": 1,
        "qualification": "source-only",
        "os_identity_binding": "explicit_caller_head_and_tree_in_verification_receipt",
        "hepta": hepta_identity,
        "original_history_owner": HISTORY_OWNER,
        "source_map_sha256": sha256(canonical(mapping)),
        "production": PRODUCTION,
        "sources": sources,
        "goldens": goldens,
    }
    receipt = {
        "schema_version": 1, "qualification": "source-only", "source_checks": "passed",
        "os": os_identity, "hepta": hepta_identity,
        "original_history_proof": proof, "production": PRODUCTION,
        "runtime_tests": "not_run_by_this_tool",
    }
    return manifest, receipt


def verify_manifest(manifest, os_repo, hepta_repo, os_head, os_tree, mapping):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("hepta"), dict):
        raise ProfileError("invalid manifest: missing single hepta commit/tree")
    hepta = manifest["hepta"]
    expected, receipt = create_manifest(os_repo, hepta_repo, os_head, os_tree,
                                        hepta.get("commit"), hepta.get("tree"), mapping)
    if canonical(manifest) != canonical(expected):
        raise ProfileError("manifest mismatch: schema, source identities, goldens, or disabled production boundary changed")
    return receipt


def write_new_outside(path, data, repositories):
    target = Path(path).resolve()
    if any(target.is_relative_to(repo.path) for repo in repositories):
        raise ProfileError("generated output must be outside both source repositories; review it before committing")
    try:
        with target.open("xb") as stream:
            stream.write(data)
    except OSError as exc:
        raise ProfileError(f"cannot create output {target}: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "verify"):
        sub = subcommands.add_parser(command)
        sub.add_argument("--os-repo", required=True)
        sub.add_argument("--hepta-repo", required=True)
        sub.add_argument("--os-head", required=True)
        sub.add_argument("--os-tree", required=True)
        sub.add_argument("--source-map", default=str(Path(__file__).with_name("organ_source_map.json")))
        sub.add_argument("--receipt", help="new output path outside both repositories; otherwise print receipt")
        if command == "build":
            sub.add_argument("--hepta-head", required=True)
            sub.add_argument("--hepta-tree", required=True)
            sub.add_argument("--output", required=True, help="new manifest path outside both repositories")
        else:
            sub.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        os_repo = Repository(args.os_repo, "os")
        hepta_repo = Repository(args.hepta_repo, "hepta")
        if os_repo.path == hepta_repo.path:
            raise ProfileError("os and hepta must be distinct repository roots")
        mapping = load_json(args.source_map)
        if args.command == "build":
            manifest, receipt = create_manifest(os_repo, hepta_repo, args.os_head, args.os_tree,
                                                 args.hepta_head, args.hepta_tree, mapping)
            raw_manifest = canonical(manifest)
            write_new_outside(args.output, raw_manifest, (os_repo, hepta_repo))
        else:
            raw_manifest = Path(args.manifest).read_bytes()
            manifest = load_json_bytes(raw_manifest, args.manifest)
            receipt = verify_manifest(manifest, os_repo, hepta_repo, args.os_head, args.os_tree, mapping)
        receipt["manifest_sha256"] = sha256(raw_manifest)
        data = canonical(receipt)
        if args.receipt:
            write_new_outside(args.receipt, data, (os_repo, hepta_repo))
        else:
            sys.stdout.buffer.write(data)
        return 0
    except (ProfileError, OSError) as exc:
        print(f"organ release profile: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
