#!/usr/bin/env python3
"""Bind native CI to its clean checkout and the single product Hepta contract.

The retained source-review.json remains historical. A current review is emitted
outside both repositories and independently reconstructed whenever it is loaded.
No build, guest, owner or model execution is performed here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

CONTRACT = "support/ui/HEPTA_SHARED_PRESENTER.json"
TEMPLATE = "tests/workloads/hepta_agentd_runtime/source-review.json"
SCHEMA = "hepta.native-original-runtime-source-review.v1"
REPOSITORY = "TrillionniumFoundation/hepta-private-ci"
LIMIT = 1024 * 1024
PACKAGES = ("hepta-agentd", "hepta-memory", "hepta-fleet", "hepta-paths", "hepta-supervisor")
MANIFESTS = ("ui/Cargo.toml", "ui/core/Cargo.toml", "services/hepta-session-host/Cargo.toml")
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def full_oid(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value), "full immutable Git identity required")
    return value


def relative(value):
    require(isinstance(value, str) and value and "\\" not in value and not value.startswith("/")
            and all(part not in ("", ".", "..") for part in value.split("/")), "normalized source path required")
    return value


def json_object(raw):
    require(len(raw) <= LIMIT, "source JSON exceeds bound")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate source JSON field")
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError("non-finite source JSON")

    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    require(isinstance(result, dict), "source JSON object required")
    return result


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= LIMIT,
            "bounded regular source JSON required")
    return path.read_bytes()


def git(source, *arguments):
    result = subprocess.run(["git", "-C", str(source), *arguments], env=ENV,
                            capture_output=True, timeout=30, check=False)
    require(result.returncode == 0, "Git source identity verification failed")
    return result.stdout


def clean_source(source):
    require(source.is_dir() and source.resolve(strict=True) == source, "canonical source directory required")
    require(git(source, "rev-parse", "--show-toplevel").decode().strip() == str(source), "source Git root required")
    require(not git(source, "status", "--porcelain=v1", "--untracked-files=all").strip(), "clean source required")
    return {"head": full_oid(git(source, "rev-parse", "HEAD").decode().strip()),
            "tree": full_oid(git(source, "rev-parse", "HEAD^{tree}").decode().strip())}


def record(source, name, repository):
    name = relative(name)
    path = source / name
    require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(source),
            "regular tracked source file required")
    actual = path.read_bytes()
    require(actual == git(source, "show", "HEAD:" + name), "working bytes differ from original Git blob")
    blob = full_oid(git(source, "rev-parse", "HEAD:" + name).decode().strip())
    return {"repository": repository, "path": name, "git_blob": blob, "sha256": digest(actual)}


def selection(desktop):
    identity = clean_source(desktop)
    raw = read(desktop / CONTRACT)
    authority = json_object(raw)
    require(set(authority) == {"schema", "repository", "commit", "tree", "contract", "desktop_base",
                               "initial_pull_request", "files"}, "unknown product source contract field")
    require(authority["schema"] == "trillionnium.original-shared-presenter.v1"
            and authority["repository"] == REPOSITORY, "canonical product Hepta contract required")
    hepta = {"head": full_oid(authority["commit"]), "tree": full_oid(authority["tree"])}
    # The product contract selects the pin. All actual Cargo entry points must
    # agree; a new JSON label cannot silently compile another Hepta revision.
    def pins(value):
        result = []
        if isinstance(value, dict):
            if isinstance(value.get("git"), str) and value["git"].removesuffix(".git") == "https://github.com/" + REPOSITORY:
                result.append(value.get("rev"))
            for child in value.values():
                result.extend(pins(child))
        return result

    for name in MANIFESTS:
        record(desktop, name, "desktop")
        revisions = pins(tomllib.loads((desktop / name).read_text()))
        require(revisions and all(revision == hepta["head"] for revision in revisions),
                "Cargo source differs from canonical product Hepta contract")
    contract = record(desktop, CONTRACT, "desktop")
    return {"schema": "hepta.current-original-runtime-selection.v1", "desktop": identity, "hepta": hepta,
            "authority": {"path": CONTRACT, "git_blob": contract["git_blob"], "sha256": digest(raw)}}, authority


def derive(desktop, hepta):
    selected, authority = selection(desktop)
    require(clean_source(hepta) == selected["hepta"], "Hepta differs from canonical product source contract")
    template = json_object(read(desktop / TEMPLATE))
    require(set(template) == {"schema", "desktop", "hepta", "scope", "source_files", "userspace_toolchain"}
            and template["schema"] == SCHEMA, "fixed historical source review schema required")
    names = set()
    for item in template["source_files"]:
        require(set(item) == {"repository", "path", "git_blob", "sha256"}
                and item["repository"] in ("desktop", "hepta"), "historical source inventory required")
        names.add((item["repository"], relative(item["path"])))
    require(isinstance(authority["files"], list) and authority["files"], "canonical source closure required")
    closure = set()
    for item in authority["files"]:
        require(set(item) == {"path", "git_blob", "sha256", "bytes"}, "unknown canonical source item field")
        name = relative(item["path"])
        require(name not in closure, "duplicate canonical source item")
        closure.add(name)
        actual = record(hepta, name, "hepta")
        require(actual["git_blob"] == item["git_blob"] and actual["sha256"] == item["sha256"]
                and type(item["bytes"]) is int and (hepta / name).stat().st_size == item["bytes"],
                "canonical product source closure differs from actual Hepta")
        names.add(("hepta", name))
    # Bind new owner/authority modules too, rather than only refreshing the old
    # selected inventory. Complete clean trees continue to bind all other files.
    for name in git(hepta, "ls-files", "-z", "--", *("codex-rs/" + package for package in PACKAGES)).split(b"\0"):
        if name:
            names.add(("hepta", relative(name.decode())))
    for name in git(desktop, "ls-files", "-z", "--", "tests/workloads/hepta_agentd_runtime").split(b"\0"):
        if name:
            names.add(("desktop", relative(name.decode())))
    names.add(("desktop", CONTRACT))
    names.update(("desktop", name) for name in MANIFESTS)
    names.add(("hepta", "codex-rs/Cargo.lock"))
    manifest = "codex-rs/rust-toolchain.toml"
    names.add(("hepta", manifest))
    channel = tomllib.loads((hepta / manifest).read_text())["toolchain"]["channel"]
    require(isinstance(channel, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", channel),
            "exact original userspace toolchain required")
    roots = {"desktop": desktop, "hepta": hepta}
    result = {"schema": SCHEMA, "desktop": selected["desktop"], "hepta": selected["hepta"],
              "scope": "Current clean CI checkout plus canonical product Hepta contract; source binding only, no execution qualification.",
              "selection": selected,
              "source_files": [record(roots[repository], name, repository) for repository, name in sorted(names)],
              "userspace_toolchain": {"channel": channel, "manifest": manifest,
                                      "sha256": digest((hepta / manifest).read_bytes())}}
    require(selection(desktop)[0] == selected and clean_source(hepta) == selected["hepta"],
            "source identity changed while constructing review")
    return result


def load_external(path, expected_sha256, desktop, hepta):
    require(isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256),
            "explicit current review SHA256 required")
    require(path.is_absolute() and path.resolve() == path
            and not any(path.is_relative_to(root) for root in (desktop, hepta)),
            "canonical external review path required")
    raw = read(path)
    require(digest(raw) == expected_sha256, "current review digest differs")
    review = json_object(raw)
    # Equality to a fresh independent reconstruction refuses unknown fields,
    # arbitrary pairs, missing inventory, fake blobs and caller-selected paths.
    require(review == derive(desktop, hepta), "current review differs from canonical tracked source reconstruction")
    return review


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select", "freeze"))
    parser.add_argument("--desktop-source", type=Path, required=True)
    parser.add_argument("--hepta-source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    args = parser.parse_args()
    roots = [args.desktop_source] + ([args.hepta_source] if args.hepta_source else [])
    require(args.output.absolute().resolve() == args.output.absolute()
            and not any(args.output.absolute().is_relative_to(root) for root in roots),
            "canonical review output must be outside sources")
    if args.mode == "select":
        value, _ = selection(args.desktop_source)
        exports = {"DESKTOP_SOURCE_PIN": value["desktop"]["head"], "HEPTA_SOURCE_PIN": value["hepta"]["head"]}
    else:
        require(args.hepta_source is not None, "canonical Hepta checkout required")
        value = derive(args.desktop_source, args.hepta_source)
        raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
        require(len(raw) <= LIMIT, "current review exceeds bound")
        exports = {"F1_SOURCE_REVIEW_PATH": str(args.output.absolute()), "F1_SOURCE_REVIEW_SHA256": digest(raw),
                   "F1_HEPTA_SOURCE_ROOT": str(args.hepta_source),
                   "USERSPACE_TOOLCHAIN_PIN": value["userspace_toolchain"]["channel"]}
    write_new(args.output, value)
    with args.github_env.open("a", encoding="utf-8") as output:
        output.write("".join(key + "=" + val + "\n" for key, val in exports.items()))


if __name__ == "__main__":
    main()
