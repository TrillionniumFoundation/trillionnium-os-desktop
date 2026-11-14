#!/usr/bin/env python3
"""Verify and replay the exact Native601 to Native643 maintained source capsule."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess


def need(value, message):
    if not value:
        raise RuntimeError(message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def safe_relative(value):
    path = Path(value)
    need(value and not path.is_absolute() and all(p not in ("", ".", "..") for p in value.split("/")),
         "canonical relative source path required")
    return path


def read_regular(path):
    path = Path(path)
    need(path.resolve() == path.absolute(), "source path may not contain an alias: " + str(path))
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= 32 * 1024**2,
         "bounded single-link regular source required: " + str(path))
    raw = path.read_bytes()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(identity(before) == identity(path.lstat()) and len(raw) == before.st_size, "source changed during complete read")
    return raw


def digest(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def check(path, expected):
    raw = read_regular(path)
    need(digest(raw) == {k: expected[k] for k in ("bytes", "sha256")}, "exact source differs: " + str(path))
    return raw


def inventory(capsule, expected_sha=None):
    index = read_regular(capsule / "FILES.sha256")
    if expected_sha is not None:
        need(hashlib.sha256(index).hexdigest() == expected_sha, "capsule inventory binding differs")
    entries = {}
    for line in index.decode().splitlines():
        sha, name = line.split("  ", 1)
        need(re.fullmatch("[0-9a-f]{64}", sha) and name != "FILES.sha256" and name not in entries,
             "unique exact capsule inventory row required")
        safe_relative(name)
        entries[name] = sha
    found = set()
    for directory, directories, names in os.walk(capsule, followlinks=False):
        need(all(not (Path(directory) / name).is_symlink() for name in directories), "capsule directory alias")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(capsule).as_posix()
            if relative == "FILES.sha256":
                continue
            need(relative in entries and relative not in found, "extra capsule input: " + relative)
            need(hashlib.sha256(read_regular(path)).hexdigest() == entries[relative], "capsule input hash differs: " + relative)
            found.add(relative)
    need(found == set(entries), "missing capsule inputs")
    return {"files": len(entries), "sha256": hashlib.sha256(index).hexdigest()}


def verify_producer(root, manifest, preimage=False):
    rows = {r["path"]: r for r in manifest["producer_files"]}
    need(len(rows) == len(manifest["producer_files"]) == 560, "complete captured current producer membership")
    replacements = {r["path"]: r["preimage"] for r in manifest["replay_files"]} if preimage else {}
    seen = set()
    for directory, directories, names in os.walk(root, followlinks=False):
        need(all(not (Path(directory) / name).is_symlink() for name in directories), "producer directory alias")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            need(relative in rows and relative not in seen, "unexpected producer file: " + relative)
            check(path, replacements.get(relative, rows[relative]))
            seen.add(relative)
    need(seen == set(rows), "missing captured producer inputs")
    return {"files": len(rows), "bytes": sum(rows[n]["bytes"] for n in rows), "preimage": preimage}


def verify_capsule(capsule, inventory_sha=None, maintained_repo=None):
    capsule = Path(capsule).resolve()
    whole = inventory(capsule, inventory_sha)
    manifest = strict_json(read_regular(capsule / "manifest.json"))
    need(manifest["schema"] == "pocket4-native643-exact-current-producer-capsule-v1"
         and manifest["recipe_commit"] == "dc0288fbbee2688473ae8a61215222f598f97e86"
         and manifest["recipe_tree"] == "581f0ed04c58550811d7fddea81f736cfc3b1848",
         "exact actually tested current producer required")
    need(manifest["native_full_build_complete"] is manifest["runtime_qualified"] is manifest["production_ready"] is False,
         "source capsule cannot grant full, Android runtime or production credit")
    need(manifest["source_profiles_independent"] == {"Native643_MAX_PROJECTS": 672, "Audio536_MAX_PROJECTS": 536, "Audio536_modified": False},
         "retain separate Native and Audio source bounds")
    need(manifest["actual_normal907_proof"]["different_tests"] == 86
         and manifest["actual_normal907_proof"]["executions"] == 92
         and manifest["actual_normal907_proof"]["actual29_commands_retired"] is True,
         "actual ordinary907 source evidence required")
    patch = check(capsule / manifest["patch"]["path"], manifest["patch"])
    files = manifest["replay_files"]
    need({r["path"] for r in files} == {"android/native-generation-pair/source-lock.json", "tools/droidloom-source/src/lib.rs", "tools/droidloom-update/src/native_generation_pair_build.rs"}, "only the exact three maintained producer paths replay")
    need(set(re.findall(rb"^--- a/(.+)$", patch, re.M)) == set(re.findall(rb"^\+\+\+ b/(.+)$", patch, re.M)) == {r["path"].encode() for r in files}, "patch scope differs")
    for row in files:
        check(capsule / "preimages" / safe_relative(row["path"]), row["preimage"])
        check(capsule / "producer" / safe_relative(row["path"]), row["postimage"])
        if maintained_repo is not None:
            check(Path(maintained_repo).resolve() / safe_relative(manifest["replay_base_capsule"]) / safe_relative(row["path"]), row["preimage"])
    verify_producer(capsule / "producer", manifest)
    pair_path = capsule / "producer/tools/droidloom-update/src/native_generation_pair_build.rs"
    for relative in re.findall(r'include_(?:str|bytes)!\s*\(\s*"([^"]+)"', pair_path.read_text()):
        included = (pair_path.parent / relative).resolve()
        need(included.is_relative_to(capsule / "producer") and included.is_file(), "complete current pair include required")
    old = strict_json(read_regular(capsule / "preimages/android/native-generation-pair/source-lock.json"))
    new = strict_json(read_regular(capsule / "producer/android/native-generation-pair/source-lock.json"))
    before = {p["path"]: p for p in old["projects"]}
    after = {p["path"]: p for p in new["projects"]}
    need(len(before) == 601 and len(after) == 643 and set(before) <= set(after), "exact monotonic601 to643 project scope")
    need({k: v for k, v in old.items() if k != "projects"} == {k: v for k, v in new.items() if k != "projects"}, "unrelated source lock policy/release/links changed")
    for name, prior in before.items():
        current = after[name]
        need(all(current[k] == value for k, value in prior.items() if k != "sparse_paths")
             and all(p in current.get("sparse_paths", []) for p in prior.get("sparse_paths", [])), "prior source revision or cone changed")
    names = {k: strict_json(read_regular(capsule / "normal-test-names" / (k + "-control-test-names.json"))) for k in ("pair", "source", "permissions", "focused")}
    names["journal"] = strict_json(read_regular(capsule / "normal-test-names/journal-regression-test-names.json"))
    need([len(names[k]) for k in ("pair", "source", "permissions", "journal", "focused")] == [47, 26, 7, 6, 6]
         and len(set(sum((names[k] for k in ("pair", "source", "permissions", "journal")), []))) == 86,
         "exact current test names and counts")
    return manifest, {"capsule_inventory": whole, "recipe_commit": manifest["recipe_commit"], "base_projects": 601, "current_projects": 643, "added_projects": 42, "all_original601_revisions_preserved": True, "complete_current_pair_includes": True, "runtime_qualified": False, "production_ready": False}


def replay(capsule, output, manifest):
    output = Path(output).absolute()
    need(not output.exists() and not output.is_relative_to(capsule), "fresh replay output outside the capsule required")
    shutil.copytree(capsule / "producer", output)
    for row in manifest["replay_files"]:
        shutil.copyfile(capsule / "preimages" / row["path"], output / row["path"])
    verify_producer(output, manifest, preimage=True)
    patch = capsule / "source.patch"
    commands = []
    for args in (("--check",), (), ("--reverse", "--check"), ("--reverse",), ("--check",), ()):
        argv = ["git", "-c", "core.hooksPath=/dev/null", "apply", *args, str(patch)]
        result = subprocess.run(argv, cwd=output, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        commands.append({"argv": argv, "returncode": result.returncode, "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr).hexdigest()})
        if args == ("--reverse",):
            verify_producer(output, manifest, preimage=True)
        elif args == ():
            verify_producer(output, manifest)
    return {"output": str(output), "commands": commands, "forward_replay_exact": True, "reverse_replay_exact": True, "all560_current_producer_files_verified": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--inventory-sha256")
    parser.add_argument("--maintained-repo", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    capsule = args.capsule.resolve()
    manifest, result = verify_capsule(capsule, args.inventory_sha256, args.maintained_repo)
    if args.output is not None:
        result["replay"] = replay(capsule, args.output, manifest)
    result["state"] = "EXACT_SOURCE_CAPSULE_VERIFIED"
    raw = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(raw)
    print(raw, end="")


if __name__ == "__main__":
    main()
