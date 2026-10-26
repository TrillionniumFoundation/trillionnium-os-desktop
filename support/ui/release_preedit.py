#!/usr/bin/env python3
"""Materialize and qualify the explicit preedit release without changing its base.

Only a detached task-owned worktree receives the Cargo-generated path lock.
The resulting local commit is a derived build input, not a published branch.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import build_text_product as product
import preedit_source
import verify_product_dependencies as dependencies

require = product.require
sha = product.digest
PROFILE = "preedit-callbacks"
CHECKS = {
    "atspi-receipt.json": (
        "actual-AT-SPI-role-name-and-focus",
        "OS-clipboard-CJK-combining-emoji-multiline-transaction",
        "UTF-8-selection-offsets",
        "oversized-native-paste-preserves-text-selection-and-prior-undo",
        "native-keyboard-undo-redo",
        "unauthenticated-Send-remains-disabled",
        "stale-accessibility-node-cannot-change-new-room-caret",
    ),
    "editable-text-receipt.json": (
        "standard-EditableText-set-complete-CJK-graphemes",
        "standard-EditableText-byte-prefix-and-original-undo-redo",
        "standard-EditableText-copy-cut-delete-use-original-editor-and-clipboard",
        "standard-EditableText-limit-UTF8-grapheme-and-range-refusals-preserve-history",
        "stale-EditableText-object-cannot-edit-another-original-room",
    ),
    "ibus-receipt.json": (
        "real-IBus-preedit-fences-navigation-and-local-checkpoint",
        "real-IBus-preedit-refuses-stale-EditableText-mutation",
        "real-IBus-space-commits-exact-Chinese-to-original-draft",
        "real-IME-commit-original-undo-redo",
        "owned-window-focus-loss-and-return-preserve-Chinese",
    ),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def json_file(path, value):
    product.desktop.atomic_write(Path(path), product.source_profile.canonical(value))


def compare_locks(original, prepared, sdk_source, sdk_packages):
    """Compare the complete lock graph, allowing only the reviewed SDK origins.

    Cargo may omit source qualifiers for path dependencies. Resolve references
    against each original lock first so this spelling change cannot hide a new
    version, checksum, dependency edge or non-SDK source substitution.
    """
    before, after = (tomllib.loads(raw.decode("utf-8")) for raw in (original, prepared))
    sdk_packages = set(sdk_packages)
    require(len(sdk_packages) == 102, "Expected all 102 original SDK packages")

    def normalized(document, baseline):
        packages = document.get("package", [])
        require(isinstance(packages, list) and packages, "A complete Cargo lock is required")
        sdk = {(p["name"], p["version"]) for p in packages if p.get("source") == sdk_source}
        require(sdk == sdk_packages if baseline else not sdk,
                "Baseline/prepared lock does not contain the exact SDK source transition")

        def identity(package):
            source = package.get("source")
            if source == sdk_source:
                source = None
            return package["name"], package["version"], source

        def dependency(value):
            match = re.fullmatch(r"([^ ()]+)(?: ([^ ()]+))?(?: \(([^()]+)\))?", value)
            require(match is not None, "Unrecognized Cargo dependency reference")
            name, version, source = match.groups()
            candidates = [p for p in packages if p["name"] == name and (version is None or p["version"] == version)
                          and (source is None or (p.get("source") or "").split("#", 1)[0] == source)]
            if source is None and len(candidates) > 1:
                candidates = [p for p in candidates if p.get("source") is None]
            require(len(candidates) == 1, "Ambiguous/unresolved Cargo dependency: " + value)
            return identity(candidates[0])

        result = []
        for package in packages:
            item = dict(package)
            if item.get("source") == sdk_source:
                item.pop("source")
            if "dependencies" in item:
                item["dependencies"] = sorted((dependency(value) for value in item["dependencies"]), key=repr)
            result.append(json.dumps(item, sort_keys=True, separators=(",", ":")))
        return {key: value for key, value in document.items() if key != "package"}, Counter(result)

    require(normalized(before, True) == normalized(after, False),
            "Cargo changed package versions, checksums, sources or dependency edges beyond the reviewed SDK paths")
    path_sdk = {(p["name"], p["version"]) for p in after["package"]
                if p.get("source") is None and (p["name"], p["version"]) in sdk_packages}
    require(path_sdk == sdk_packages, "Prepared lock lost one of the 102 SDK path packages")
    return {"packages": len(before["package"]), "sdk_origins_changed": 102,
            "all_versions_checksums_and_dependency_edges_preserved": True,
            "baseline_sha256": hashlib.sha256(original).hexdigest(),
            "derived_sha256": hashlib.sha256(prepared).hexdigest()}


def freeze_candidate(candidate, base_commit, environment):
    """Create one deterministic local child commit; never move a base branch."""
    def git(*args, data=None):
        return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-C", str(candidate), *args],
                                       env=environment, input=data, stderr=subprocess.PIPE)
    require(git("rev-parse", "HEAD").decode().strip() == base_commit, "Candidate no longer starts at the reviewed base")
    require(subprocess.run(["git", "-C", str(candidate), "symbolic-ref", "-q", "HEAD"],
                           env=environment, capture_output=True).returncode == 1,
            "Derived source must be a detached worktree")
    require(git("diff", "--name-only", "HEAD").decode().splitlines() == ["ui/Cargo.lock"],
            "Only the task-owned candidate UI lock may change")
    require(not git("ls-files", "--others", "--exclude-standard"), "Candidate contains untracked source")
    git("add", "--", "ui/Cargo.lock")
    tree = git("write-tree").decode().strip()
    timestamp = git("show", "-s", "--format=%ct", base_commit).decode().strip() + " +0000"
    commit_env = dict(environment, GIT_AUTHOR_NAME="Trillionnium preedit materializer",
        GIT_COMMITTER_NAME="Trillionnium preedit materializer", GIT_AUTHOR_EMAIL="preedit-build@example.invalid",
        GIT_COMMITTER_EMAIL="preedit-build@example.invalid", GIT_AUTHOR_DATE=timestamp, GIT_COMMITTER_DATE=timestamp)
    message = ("build(ui): derive reviewed preedit SDK lock\n\nBase-Desktop: " + base_commit
               + "\nSource-Scope: local derived input; no branch or production promotion\n").encode()
    commit = subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-C", str(candidate),
        "commit-tree", tree, "-p", base_commit], input=message, env=commit_env).decode().strip()
    git("update-ref", "--no-deref", "HEAD", commit, base_commit)
    product.source_profile.Repository(candidate, "derived desktop").check(commit, tree)
    require(git("rev-list", "--parents", "-n", "1", commit).decode().split() == [commit, base_commit],
            "Derived commit must have exactly the reviewed base as its parent")
    return {"commit": commit, "tree": tree, "parent": base_commit, "published": False,
            "base_branch_updated": False, "changed_paths": ["ui/Cargo.lock"]}


def extract_package(product_dir, destination, derived, hepta_commit):
    build = json.loads((product_dir / "build-receipt.json").read_bytes())
    require(build.get("status") == "passed" and build.get("exit_code") == 0,
            "Only a successful original product build can be qualified")
    require((build["source_commit"], build["source_tree"], build["hepta"]["commit"])
            == (derived["commit"], derived["tree"], hepta_commit), "Build source identity differs from the derived input")
    require(build["profile"].get("sdk_profile") == PROFILE and build["profile"]["resource_files"] == 61,
            "The explicit preedit profile and all 61 resources are required")
    archive = product_dir / "trillionnium-desktop-linux-text.tar.gz"
    require(sha(archive) == build["package"]["sha256"], "Packaged archive differs from its build receipt")
    destination.mkdir(mode=0o700)
    with tarfile.open(archive, "r:gz") as handle:
        seen = set()
        for member in handle.getmembers():
            path = Path(member.name)
            require(path.parts and path.parts[0] == "trillionnium-desktop" and not path.is_absolute()
                    and ".." not in path.parts and (member.isdir() or member.isfile()) and member.name not in seen,
                    "Unsafe, duplicate or nonregular product archive member")
            seen.add(member.name)
        handle.extractall(destination, filter="data")
    root = destination / "trillionnium-desktop"
    for name, entry in build["packaged_binaries"].items():
        binary = root / "bin" / name
        require(binary.is_file() and not binary.is_symlink() and binary.stat().st_size == entry["bytes"]
                and sha(binary) == entry["sha256"], "Extracted packaged executable differs: " + name)
    return root, build


def qualified_checks(directory, build, derived):
    report = json.loads((directory / "receipt.json").read_bytes())
    require(all(report.get(key) is True for key in ("passed", "preedit_profile_qualified",
        "supported_atspi_checks_passed", "real_virtual_x11_ibus_checks_passed",
        "atomic_editable_text_methods_passed", "private_credentials_and_state_removed"))
        and not report.get("cleanup_errors"), "Original packaged preedit/window/cleanup gate did not pass")
    origin = report["provenance"]
    require((origin.get("source_commit"), origin.get("source_tree")) == (derived["commit"], derived["tree"])
        and origin.get("build_artifact_kind") == "packaged_binaries"
        and origin["shell"]["sha256"] == build["packaged_binaries"]["trill-shell"]["sha256"],
        "Runtime receipt is not bound to this derived packaged ELF")
    checked = {}
    for name, expected in CHECKS.items():
        item = json.loads((directory / name).read_bytes())
        observed = item.get("checks", [])
        require(item.get("passed") is True and [entry.get("name") for entry in observed] == list(expected)
                and all(entry.get("passed") is True for entry in observed),
                "Missing, failed, duplicate or substituted original window checks: " + name)
        checked[name] = {"sha256": sha(directory / name), "checks": list(expected), "passed": len(expected)}
    return checked


class Release:
    def __init__(self, args):
        self.args = args
        self.profile = preedit_source.settings()
        self.original = product.source_profile.Repository(REPO, "base desktop")
        self.hepta = product.source_profile.Repository(args.hepta_repo, "original Hepta")
        self.original.check(args.desktop_commit, args.desktop_tree)
        self.hepta.check(self.profile["hepta_commit"], self.profile["hepta_tree"])
        preedit_source.verified_helper(self.hepta.path)
        dependencies.verify(REPO, self.hepta.path)
        self.hepta.prove_history()
        self.work, self.output = args.work_dir.absolute(), args.output.absolute()
        for path in (self.work, self.output):
            require(path == path.resolve() and path.parent.is_dir() and not path.exists(),
                    "Use new canonical directories with existing parents")
            require(not any(path.is_relative_to(root) for root in (REPO, self.hepta.path)),
                    "Release work and evidence must be outside both original source trees")
        require(not self.work.is_relative_to(self.output) and not self.output.is_relative_to(self.work),
                "Release source work and evidence must be separate directories")
        self.work.mkdir(mode=0o700)
        self.output.mkdir(mode=0o700)
        (self.output / "logs").mkdir(mode=0o700)
        self.candidate, self.sdk = self.work / "desktop", self.work / "sdk"
        self.config = self.output / "sdk-overrides.toml"
        self.original_metadata = self.output / "original-metadata.json"
        self.env = dict(os.environ)
        removed = []
        for key in list(self.env):
            if key.startswith(("TRILL_", "HEPTA_", "GIT_", "NEXTEST_", "CARGO_ALIAS_", "CARGO_REGISTRIES_")) or key in {
                    "DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS",
                    "IBUS_ADDRESS", "LD_PRELOAD", "NO_AT_BRIDGE"}:
                removed.append(key)
                del self.env[key]
        self.env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONOPTIMIZE="0", CARGO_INCREMENTAL="0",
                        CARGO_TERM_COLOR="never", GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0",
                        GIT_TERMINAL_PROMPT="0", LANG="C.UTF-8", LC_ALL="C.UTF-8")
        if args.offline:
            self.env["CARGO_NET_OFFLINE"] = "true"
        self.guard, bound, self.identities, self.tools = product.reviewed_tools(self.hepta.path, self.env)
        self.env, compiler_removed = product.controlled_environment(self.profile, self.work / "metadata-target", args.jobs, self.tools, bound)
        self.private = tempfile.TemporaryDirectory(prefix="trill-preedit-release-")
        for name in ("runtime", "config", "cache", "state", "data"):
            path = Path(self.private.name) / name
            path.mkdir(mode=0o700)
            self.env["XDG_" + name.upper() + ("_DIR" if name == "runtime" else "_HOME")] = str(path)
        self.receipt = {"schema": "trill.preedit-release.v1", "status": "running", "started_at": now(),
            "base_desktop": {"commit": args.desktop_commit, "tree": args.desktop_tree},
            "hepta": {"commit": self.profile["hepta_commit"], "tree": self.profile["hepta_tree"]},
            "profile_sha256": sha(HERE / "linux-preedit-profile.json"), "commands": [],
            "source_work": str(self.work), "toolchain_executables": self.identities,
            "ambient_overrides_removed": sorted(set(removed + compiler_removed)),
            "baseline_lock_sha256": sha(REPO / "ui/Cargo.lock"),
            "derived": None, "window_qualified": False, "production_authority_qualified": False,
            "physical_device_qualified": False, "published_or_installed": False,
            "scope": "local derived preedit package; virtual X11/real IBus/AT-SPI only"}
        self.save()

    def save(self):
        json_file(self.output / "release-receipt.json", self.receipt)
        suite = ET.Element("testsuite", name="preedit-release-operator-stages")
        for entry in self.receipt["commands"]:
            case = ET.SubElement(suite, "testcase", classname="operator-stage", name=entry["name"], time=str(entry.get("seconds", 0)))
            if entry.get("exit_code") is None:
                ET.SubElement(case, "skipped", message="stage has not completed")
            elif entry["exit_code"] != 0:
                ET.SubElement(case, "failure", message="stage exit " + str(entry["exit_code"]))
            ET.SubElement(case, "system-out").text = json.dumps(entry)
        if self.receipt["status"] == "failed":
            case = ET.SubElement(suite, "testcase", classname="operator-stage", name="release-validation")
            ET.SubElement(case, "failure", message=self.receipt.get("error", "release failed"))
        suite.set("tests", str(len(suite.findall("testcase"))))
        suite.set("failures", str(len(suite.findall("testcase/failure"))))
        suite.set("errors", "0")
        suite.set("skipped", str(len(suite.findall("testcase/skipped"))))
        ET.indent(suite)
        ET.ElementTree(suite).write(self.output / "stages.junit.xml", encoding="utf-8", xml_declaration=True)

    def unchanged(self):
        self.original.check(self.args.desktop_commit, self.args.desktop_tree)
        self.hepta.check(self.profile["hepta_commit"], self.profile["hepta_tree"])
        require(sha(REPO / "ui/Cargo.lock") == self.receipt["baseline_lock_sha256"], "Baseline UI lock changed")
        self.guard.verify_executables(self.identities)
        if self.receipt["derived"] is not None:
            derived = self.receipt["derived"]
            product.source_profile.Repository(self.candidate, "derived desktop").check(derived["commit"], derived["tree"])
        if hasattr(self, "original_graph"):
            require(product.verify_source_caches(self.original_graph, self.profile["hepta_commit"],
                self.profile["hepta_tree"], self.baseline_profile) == self.receipt["original_source_caches"],
                "Original dependency source caches changed during the release")
        for name, checksum in self.receipt.get("source_closure", {}).items():
            require(sha(self.output / name) == checksum, "Materialized source evidence changed: " + name)

    def run(self, name, command, *, cwd=None, output=None):
        self.unchanged()
        command = list(map(str, product.tool_command(command, self.tools)))
        out = output or self.output / "logs" / (name + ".stdout.log")
        err = self.output / "logs" / (name + ".stderr.log")
        entry = {"name": name, "argv": command, "cwd": str(cwd or self.candidate), "started_at": now(), "exit_code": None}
        self.receipt["commands"].append(entry)
        self.save()
        print("Running " + name, flush=True)
        started = time.monotonic()
        with out.open("xb") as stdout, err.open("xb") as stderr:
            process = subprocess.Popen(command, cwd=cwd or self.candidate, env=self.env,
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = process.wait()
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        # The original window gate owns separate child groups
                        # and handles SIGTERM by cleaning each of them itself.
                        process.wait(timeout=45)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                raise
            finally:
                entry.update(exit_code=process.returncode, seconds=round(time.monotonic() - started, 3),
                    stdout={"path": str(out), "sha256": sha(out)}, stderr={"path": str(err), "sha256": sha(err)})
                self.save()
        require(code == 0, f"{name} failed with exit {code}; retain {out} and {err}")
        self.unchanged()
        return out

    def materialize(self):
        self.run("detached-worktree", ["git", "-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach",
            self.candidate, self.args.desktop_commit], cwd=REPO)
        common = ["--format-version", "1", "--features", self.profile["cargo_feature"]]
        self.run("original-metadata", ["cargo", "metadata", "--manifest-path", "ui/Cargo.toml", "--locked", *common,
            *(["--offline"] if self.args.offline else [])], output=self.original_metadata)
        graph = json.loads(self.original_metadata.read_bytes())
        baseline = json.loads((HERE / "linux-text-profile.json").read_bytes())
        caches = product.verify_source_caches(graph, self.profile["hepta_commit"], self.profile["hepta_tree"], baseline)
        self.receipt["original_source_caches"] = caches
        self.original_graph, self.baseline_profile = graph, baseline
        sdk_source = "git+" + self.profile["makepad_repository"] + "?rev=" + self.profile["makepad_commit"] + "#" + self.profile["makepad_commit"]
        sdk_packages = {(p["name"], p["version"]) for p in graph["packages"] if p.get("source") == sdk_source}
        require(len(sdk_packages) == 102, "Original feature metadata must resolve all 102 SDK packages")
        lock_before = (self.candidate / "ui/Cargo.lock").read_bytes()
        require(hashlib.sha256(lock_before).hexdigest() == self.receipt["baseline_lock_sha256"], "Candidate does not start with the base lock")
        self.run("prepare-sdk", [sys.executable, "-I", "-B", self.hepta.path / "apps/hepta-control-ui/test/prepare-native-clipboard-sdk.py",
            "--profile", PROFILE, "--upstream-repo", caches["makepad"]["root"], "--destination", self.sdk,
            "--hepta-root", self.hepta.path, "--metadata", self.original_metadata, "--cargo-config-output", self.config])
        overrides = tomllib.loads(self.config.read_text())["patch"][self.profile["makepad_repository"]]
        require(len(overrides) == 102, "The release requires all 102 SDK overrides")
        prepared = self.run("prepared-metadata", ["cargo", "--config", self.config, "metadata", "--manifest-path",
            "ui/Cargo.toml", "--offline", *common], output=self.output / "prepared-metadata.json")
        self.receipt["lock_transition"] = compare_locks(lock_before, (self.candidate / "ui/Cargo.lock").read_bytes(), sdk_source, sdk_packages)
        sdk_profile = preedit_source.verify(prepared.read_bytes(), self.sdk, None, self.original_metadata, self.config, self.hepta.path)
        json_file(self.output / "sdk-source-profile.json", sdk_profile)
        self.receipt["sdk_source_profile_sha256"] = sha(self.output / "sdk-source-profile.json")
        self.receipt["resolved_packages"] = product.validate_graph(json.loads(prepared.read_bytes()), self.profile["hepta_commit"], self.profile, sdk_profile)
        self.receipt["derived"] = freeze_candidate(self.candidate, self.args.desktop_commit, self.env)
        derived = self.receipt["derived"]
        self.save()
        self.run("lock-diff", ["git", "diff", "--binary", self.args.desktop_commit, derived["commit"], "--", "ui/Cargo.lock"],
                 output=self.output / "derived-ui-lock.patch")
        self.run("source-bundle", ["git", "bundle", "create", self.output / "derived-source.bundle", "HEAD", "^" + self.args.desktop_commit])
        self.run("verify-source-bundle", ["git", "bundle", "verify", self.output / "derived-source.bundle"])
        self.run("full-source-snapshot", ["git", "archive", "--format=tar.gz", "--prefix=trillionnium-desktop-source/",
            "--output=" + str(self.output / "derived-source.tar.gz"), derived["commit"]])
        shutil.copyfile(self.candidate / "ui/Cargo.lock", self.output / "derived-Cargo.lock")
        self.receipt["source_closure"] = {name: sha(self.output / name) for name in (
            "derived-source.bundle", "derived-source.tar.gz", "derived-ui-lock.patch", "derived-Cargo.lock",
            "original-metadata.json", "prepared-metadata.json", "sdk-source-profile.json", "sdk-overrides.toml")}
        self.receipt["bundle_prerequisite"] = self.args.desktop_commit
        self.receipt["prepared_sdk_reconstruction"] = "exact original Makepad commit plus frozen H760 helper/patch; absolute paths must be freshly materialized"
        require(product.verify_source_caches(graph, self.profile["hepta_commit"], self.profile["hepta_tree"], baseline) == caches,
                "Original Cargo source caches changed during materialization")
        self.receipt["status"] = "materialized"
        self.save()

    def build_and_qualify(self):
        derived = self.receipt["derived"]
        product_dir = self.output / "product"
        command = [sys.executable, "-B", self.candidate / "support/ui/build_text_product.py", "--profile", PROFILE,
            "--desktop-commit", derived["commit"], "--desktop-tree", derived["tree"],
            "--hepta-repo", self.hepta.path, "--hepta-commit", self.profile["hepta_commit"], "--hepta-tree", self.profile["hepta_tree"],
            "--sdk-helper-repo", self.hepta.path, "--sdk-original-metadata", self.original_metadata,
            "--sdk-cargo-config", self.config, "--output", product_dir, "--jobs", str(self.args.jobs),
            "--build-profile", self.args.build_profile]
        if self.args.offline:
            command.append("--offline")
        for name in ("asset_cache", "liberation_source"):
            value = getattr(self.args, name)
            if value is not None:
                command.extend(["--" + name.replace("_", "-"), value.resolve(strict=True)])
        self.run("original-product-builder", command)
        packaged, build = extract_package(product_dir, self.output / "package", derived, self.profile["hepta_commit"])
        self.run("original-packaged-window-gates", [sys.executable, "-B", self.candidate / "tests/ui/native-makepad/qualify.py",
            "--shell", packaged / "bin/trill-shell", "--resources", packaged / "resources", "--hepta-source", self.hepta.path,
            "--build-receipt", product_dir / "build-receipt.json", "--packaged-binary", "--atomic-editable-text",
            "--output", self.output / "window"])
        self.receipt["window_checks"] = qualified_checks(self.output / "window", build, derived)
        self.receipt["build_receipt_sha256"] = sha(product_dir / "build-receipt.json")
        self.receipt["window_receipt_sha256"] = sha(self.output / "window/receipt.json")
        self.receipt["package_sha256"] = build["package"]["sha256"]
        self.receipt["packaged_shell_sha256"] = build["packaged_binaries"]["trill-shell"]["sha256"]
        self.receipt.update(status="qualified", window_qualified=True)

    def execute(self):
        code = 1
        try:
            self.materialize()
            if not self.args.materialize_only:
                self.build_and_qualify()
            self.unchanged()
            if self.receipt["derived"] is not None:
                preedit_source.verify((self.output / "prepared-metadata.json").read_bytes(), self.sdk,
                    self.output / "sdk-source-profile.json", self.original_metadata, self.config, self.hepta.path)
            code = 0
        except BaseException as error:
            self.receipt.update(status="failed", error=f"{type(error).__name__}: {error}", window_qualified=False)
        finally:
            try:
                self.unchanged()
                self.receipt["original_and_derived_sources_unchanged"] = True
            except BaseException as error:
                self.receipt.update(status="failed", error="source postcheck: " + str(error), window_qualified=False)
                code = 90
            self.private.cleanup()
            self.receipt.update(exit_code=code, finished_at=now())
            self.save()
        print(json.dumps({"status": self.receipt["status"], "exit_code": code,
                          "receipt": str(self.output / "release-receipt.json")}), flush=True)
        return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-commit", required=True)
    parser.add_argument("--desktop-tree", required=True)
    parser.add_argument("--hepta-repo", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--build-profile", choices=("debug", "release"), default="release")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--asset-cache", type=Path)
    parser.add_argument("--liberation-source", type=Path)
    parser.add_argument("--materialize-only", action="store_true", help="Freeze source closure only; no window/package qualification")
    args = parser.parse_args()
    for value in (args.desktop_commit, args.desktop_tree):
        product.source_profile.full_oid(value, "base Desktop source")
    def interrupted(number, _frame):
        raise InterruptedError("Release interrupted by signal " + str(number))
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, interrupted)
    # The shared original source verifier intentionally honors its process
    # environment. Never let caller GIT_DIR/index/worktree overrides redirect
    # those source checks; the task's Git commands need the same boundary.
    saved = {key: os.environ.pop(key) for key in list(os.environ) if key.startswith("GIT_")}
    os.environ.update(GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    try:
        return Release(args).execute()
    finally:
        for key in list(os.environ):
            if key.startswith("GIT_"):
                del os.environ[key]
        os.environ.update(saved)


if __name__ == "__main__":
    raise SystemExit(main())
