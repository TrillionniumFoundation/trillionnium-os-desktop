#!/usr/bin/env python3
"""Verify and replay the exact Native601 to current Native643 global-compat maintained source capsule."""
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
    need(value and not path.is_absolute() and "\\" not in value and all(p not in ("", ".", "..", ".git") for p in value.split("/")),
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
    if "git_blob" in expected:
        need(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected["git_blob"],
             "original Git blob differs: " + str(path))
    return raw


def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def fresh_destination(path, protected):
    path = Path(path).absolute()
    need(path.resolve() == path and not os.path.lexists(path), "fresh output without any parent alias required")
    for root in protected:
        root = Path(root).absolute()
        need(root.resolve() == root and not path.is_relative_to(root), "output is inside an input or producer")
    return path


def source_snapshot(root, records, expected_count):
    root = Path(root).absolute()
    need(root.resolve() == root and root.is_dir(), "canonical independent producer directory required")
    rows = {row["path"]: row for row in records}
    need(len(rows) == len(records) == expected_count, "complete unique producer membership required")
    seen, result = set(), {}
    for directory, directories, names in os.walk(root, followlinks=False):
        need(all(not (Path(directory) / name).is_symlink() for name in directories), "producer directory alias")
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            safe_relative(relative)
            need(relative in rows and relative not in seen, "unexpected producer member: " + relative)
            row = rows[relative]
            before = identity(path.lstat())
            need(row["git_mode"] in ("100644", "100755") and stat.S_ISREG(before[2])
                 and stat.S_IMODE(before[2]) == int(row["git_mode"], 8) & 0o777, "producer file mode differs")
            check(path, row)
            need(identity(path.lstat()) == before, "producer changed during full file verification")
            result[relative] = before
            seen.add(relative)
    need(seen == set(rows), "complete producer input missing")
    need(all(identity((root / name).lstat()) == value for name, value in result.items()), "producer F9 changed across whole audit")
    return result


def test_terminal(text, expected):
    expected = set(expected)
    rows, running, summaries = [], [], []
    for line in text.splitlines():
        if line.startswith("test result:"):
            summaries.append(line)
        elif line.startswith("test "):
            match = re.fullmatch(r"test (\S+) \.\.\. (ok|FAILED|ignored(?:,.*)?)", line)
            need(match is not None, "malformed Rust terminal record")
            rows.append(match.groups())
        elif line.startswith("running "):
            match = re.fullmatch(r"running (\d+) tests?", line)
            need(match is not None, "malformed Rust harness count")
            running.append(int(match.group(1)))
    need(len(rows) == len(expected) and {name for name, _ in rows} == expected
         and all(status == "ok" for _, status in rows), "exact passing test identity set required")
    need(running == [len(expected)] and len(summaries) == 1, "one complete Rust harness required")
    match = re.fullmatch(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out; finished in [0-9]+(?:\.[0-9]+)?s", summaries[0])
    need(match is not None and tuple(map(int, match.groups()[:4])) == (len(expected), 0, 0, 0), "Rust summary contradicts complete successful identities")
    return len(rows)


def inventory(capsule, expected_sha=None):
    index = read_regular(capsule / "FILES.sha256")
    need(expected_sha is not None and re.fullmatch("[0-9a-f]{64}", expected_sha)
         and hashlib.sha256(index).hexdigest() == expected_sha, "externally fixed capsule inventory differs")
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
    need(len(rows) == len(manifest["producer_files"]) == 569, "complete captured current producer membership")
    replacements = {r["path"]: r["preimage"] for r in manifest["replay_files"]} if preimage else {}
    for name, replacement in replacements.items():
        rows[name] = {**rows[name], **replacement}
        rows[name].pop("git_blob", None)
    snapshots = source_snapshot(root, list(rows.values()), 569)
    return {"files": len(rows), "bytes": sum(rows[n]["bytes"] for n in rows), "preimage": preimage, "identities": snapshots}


def verify_capsule(capsule, inventory_sha=None, maintained_repo=None):
    capsule = Path(capsule).absolute()
    need(capsule.resolve() == capsule, "capsule path cannot be aliased")
    whole = inventory(capsule, inventory_sha)
    manifest = strict_json(read_regular(capsule / "manifest.json"))
    need(manifest["schema"] == "pocket4-native643-global-compat-current-producer-capsule-v2"
         and manifest["recipe_commit"] == "2f91fe5f81886ca24c4c562ce9491f16e17261d5"
         and manifest["recipe_tree"] == "d30800eda1b2be36ac636913171195551cfefd38",
         "exact actually tested current producer required")
    need(manifest["native_full_build_complete"] is manifest["runtime_qualified"] is manifest["production_ready"] is False,
         "source capsule cannot grant full, Android runtime or production credit")
    need(manifest["source_profiles_independent"] == {"Native643_MAX_PROJECTS": 672, "Native643_source_projects": 643, "Audio537_MAX_PROJECTS": 537, "Audio_producer_modified": False},
         "retain separate Native and Audio source bounds")
    need(manifest["actual_normal974_proof"]["different_tests"] == 89
         and manifest["actual_normal974_proof"]["executions"] == 95
         and manifest["actual_normal974_proof"]["actual29_commands_retired"] is True,
         "actual ordinary974 source evidence required")
    capture = read_regular(capsule / "capture-proof.json")
    need(digest(capture) == {"bytes": 199116, "sha256": "644636c06c10b39fb69e1568544284af8607ecc9af4bb75a1b5e28213aff4770"}, "exact original978 capture receipt required")
    captured = strict_json(capture)
    need(captured["files"] == manifest["producer_files"]
         and captured["actual_normal974_proof"] == manifest["actual_normal974_proof"]
         and captured["compile_time_include_origins"] == manifest["compile_time_include_origins"]
         and captured["captured_file_count"] == 569 and captured["frozen_full_recipe_file_count"] == 647,
         "all current original captured compile inputs required")
    patch = check(capsule / manifest["patch"]["path"], manifest["patch"])
    files = manifest["replay_files"]
    need({r["path"] for r in files} == {"android/native-generation-pair/source-lock.json", "tools/droidloom-source/src/lib.rs", "tools/droidloom-update/src/native_generation_pair_build.rs"}, "only the exact three maintained producer paths replay")
    need(set(re.findall(rb"^--- a/(.+)$", patch, re.M)) == set(re.findall(rb"^\+\+\+ b/(.+)$", patch, re.M)) == {r["path"].encode() for r in files}, "patch scope differs")
    for row in files:
        check(capsule / "preimages" / safe_relative(row["path"]), row["preimage"])
        check(capsule / "producer" / safe_relative(row["path"]), row["postimage"])
        if maintained_repo is not None:
            maintained = Path(maintained_repo).absolute()
            need(maintained.resolve() == maintained, "maintained input path cannot be aliased")
            check(maintained / safe_relative(manifest["replay_base_capsule"]) / safe_relative(row["path"]), row["preimage"])
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
    need([len(names[k]) for k in ("pair", "source", "permissions", "journal", "focused")] == [50, 26, 7, 6, 6]
         and len(set(sum((names[k] for k in ("pair", "source", "permissions", "journal")), []))) == 89,
         "exact current test names and counts")
    predecessor = strict_json(read_regular(capsule / "predecessor-files.json"))
    old_rows = {row["path"]: row for row in predecessor}
    new_rows = {row["path"]: row for row in manifest["producer_files"]}
    changed = {name for name in old_rows if old_rows[name] != new_rows.get(name)}
    added = set(new_rows) - set(old_rows)
    need(len(old_rows) == len(predecessor) == 560 and set(old_rows) <= set(new_rows)
         and changed == {row["path"] for row in files} and len(added) == 9
         and all(name.startswith("android/native-generation-pair/global-compat-fixtures/") for name in added),
         "only three current predecessor inputs and nine original compatibility fixtures may differ")
    for name in changed:
        check(capsule / "predecessor-preimages" / safe_relative(name), old_rows[name])
    check(capsule / "predecessor.patch", manifest["predecessor"]["patch"])
    if maintained_repo is not None:
        prior_capsule = Path(maintained_repo).absolute() / safe_relative(manifest["predecessor"]["capsule_path"])
        inventory(prior_capsule, manifest["predecessor"]["inventory_sha256"])
        source_snapshot(prior_capsule / "producer", predecessor, 560)
    return manifest, {"capsule_inventory": whole, "recipe_commit": manifest["recipe_commit"], "base_projects": 601, "current_projects": 643, "added_projects": 42, "all_original601_revisions_preserved": True, "complete_current_pair_includes": True, "runtime_qualified": False, "production_ready": False}


def replay(capsule, output, manifest):
    output = fresh_destination(output, [capsule])
    shutil.copytree(capsule / "producer", output)
    for row in manifest["replay_files"]:
        shutil.copyfile(capsule / "preimages" / row["path"], output / row["path"])
    verify_producer(output, manifest, preimage=True)
    patch = capsule / "source.patch"
    commands = []
    for args in (("--check",), (), ("--reverse", "--check"), ("--reverse",), ("--check",), ()):
        argv = ["git", "-c", "core.hooksPath=/dev/null", "apply", *args, str(patch)]
        result = subprocess.run(argv, cwd=output, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, umask=0o022)
        commands.append({"argv": argv, "returncode": result.returncode, "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr).hexdigest()})
        if args == ("--reverse",):
            verify_producer(output, manifest, preimage=True)
        elif args == ():
            verify_producer(output, manifest)
    return {"output": str(output), "commands": commands, "forward_replay_exact": True, "reverse_replay_exact": True, "all569_current_producer_files_verified": True}


def replay_predecessor(capsule, output, manifest):
    output = fresh_destination(output, [capsule])
    before = strict_json(read_regular(capsule / "predecessor-files.json"))
    after = manifest["producer_files"]
    changed = {row["path"] for row in manifest["replay_files"]}
    output.mkdir(mode=0o700, parents=True)
    for row in before:
        relative = safe_relative(row["path"])
        source = capsule / ("predecessor-preimages" if row["path"] in changed else "producer") / relative
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
        path.chmod(int(row["git_mode"], 8) & 0o777)
    source_snapshot(output, before, 560)
    patch = str(capsule / "predecessor.patch")
    commands = []
    for args in (("--check",), (), ("--reverse", "--check"), ("--reverse",), ("--check",), ()):
        argv = ["git", "-c", "core.hooksPath=/dev/null", "apply", *args, patch]
        result = subprocess.run(argv, cwd=output, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, umask=0o022)
        commands.append({"argv": argv, "exit_code": result.returncode, "stdout": digest(result.stdout), "stderr": digest(result.stderr)})
        if args == ("--reverse",):
            source_snapshot(output, before, 560)
        elif not args:
            source_snapshot(output, after, 569)
    return {"output": str(output), "commands": commands, "complete560_to569_round_trip": True,
            "unchanged_predecessor_files": 557, "changed_files": 3, "added_files": 9, "deleted_files": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--maintained-repo", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--predecessor-output", type=Path)
    parser.add_argument("--producer", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    capsule = args.capsule.absolute()
    protected = [capsule] + [p.absolute() for p in (args.maintained_repo, args.output, args.predecessor_output, args.producer) if p is not None]
    if args.report is not None:
        args.report = fresh_destination(args.report, protected)
    if args.output is not None:
        fresh_destination(args.output, [capsule] + ([args.maintained_repo.absolute()] if args.maintained_repo is not None else []))
    if args.predecessor_output is not None:
        fresh_destination(args.predecessor_output, [capsule] + ([args.maintained_repo.absolute()] if args.maintained_repo is not None else []) + ([args.output.absolute()] if args.output is not None else []))
    manifest, result = verify_capsule(capsule, args.inventory_sha256, args.maintained_repo)
    if args.output is not None:
        result["replay"] = replay(capsule, args.output, manifest)
    if args.predecessor_output is not None:
        result["predecessor_replay"] = replay_predecessor(capsule, args.predecessor_output, manifest)
    if args.producer is not None:
        snapshot = verify_producer(args.producer, manifest)
        result["current_producer"] = {key: value for key, value in snapshot.items() if key != "identities"}
    result["state"] = "EXACT_SOURCE_CAPSULE_VERIFIED"
    raw = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x") as stream:
            stream.write(raw)
    print(raw, end="")


if __name__ == "__main__":
    main()
