#!/usr/bin/env python3
"""Replay only pinned source-lock patches. No network, checkout or materialization."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def checked_read(path, expected, cap=1048576):
    data = path.read_bytes()
    require(len(data) <= cap, "input exceeds source proof limit: " + str(path))
    require(len(data) == expected["bytes"], "size mismatch: " + str(path))
    require(hashlib.sha256(data).hexdigest() == expected["sha256"], "SHA mismatch: " + str(path))
    return data

def run(repo_root, capsule):
    chain = json.loads((capsule / "source-chain.json").read_text())
    require(chain["schema"] == "pocket4-native600-tradefed-source-chain-v1", "chain schema")
    plan_bytes = checked_read(capsule / chain["provider_plan"]["path"], chain["provider_plan"])
    plan = json.loads(plan_bytes)
    require(plan["delta_sparse_paths"] == chain["expected_added_paths"], "plan delta mismatch")
    source_path = repo_root / chain["published_base"]["path"]
    before = checked_read(source_path, chain["published_base"])
    original = json.loads(before)
    require(len(original["projects"]) == chain["expected_projects"], "base count")
    stage_results = []
    with tempfile.TemporaryDirectory(prefix="p4-native-provider-chain-") as name:
        work = Path(name)
        target = work / "source-lock.json"
        target.write_bytes(before)
        env = os.environ.copy()
        env.update({"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull,"GIT_OPTIONAL_LOCKS":"0"})
        latest_owner = None
        for index, step in enumerate(chain["steps"]):
            patch_bytes = checked_read(capsule / step["patch"], step, 65536)
            patch_path = work / ("step-" + str(index) + ".patch")
            patch_path.write_bytes(patch_bytes)
            for args in (["apply","--check",str(patch_path)],["apply",str(patch_path)]):
                result = subprocess.run(["git",*args],cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
                require(result.returncode == 0, "git " + " ".join(args[:2]) + " failed: " + result.stderr.decode(errors="replace")[:1000])
            current = target.read_bytes()
            require(len(current) == step["result_bytes"], "result size")
            require(hashlib.sha256(current).hexdigest() == step["result_sha256"], "result SHA")
            document = json.loads(current)
            if index == 0:
                latest_owner = document
            stage_results.append({"patch":step["patch"],"apply_check_exit":0,"apply_exit":0,"result_bytes":len(current),"result_sha256":hashlib.sha256(current).hexdigest()})
        after = json.loads(target.read_bytes())
        require(latest_owner is not None, "missing prerequisite")
        a = {row["path"]:row for row in latest_owner["projects"]}
        b = {row["path"]:row for row in after["projects"]}
        require(len(a) == len(b) == chain["expected_projects"], "unique project count")
        require([r["path"] for r in latest_owner["projects"]] == [r["path"] for r in after["projects"]], "project order changed")
        require({k:v for k,v in latest_owner.items() if k!="projects"} == {k:v for k,v in after.items() if k!="projects"}, "non-project configuration changed")
        changed = []
        for path, row in a.items():
            expected = copy.deepcopy(row)
            additions = chain["expected_added_paths"].get(path, [])
            if additions:
                require(row["commit"] == chain["expected_project_commits"][path], "commit pin " + path)
                require(not set(additions).intersection(row["sparse_paths"]), "duplicate added path")
                expected["sparse_paths"].extend(additions)
                changed.append(path)
            require(expected == b[path], "unexpected project mutation: " + path)
        require(len(changed) == chain["expected_changed_projects"], "changed project count")
        require(len(a)-len(changed) == chain["expected_unchanged_projects"], "unchanged project count")
        require(sum(map(len,chain["expected_added_paths"].values())) == chain["expected_new_sparse_paths"], "added path count")
    require(source_path.read_bytes() == before, "original repository input changed")
    return {"schema":"pocket4-native600-tradefed-source-proof-v1","passed":True,"network_used":False,"temporary_directory_retired":True,"stages":stage_results,"changed_projects":changed,"unchanged_projects":chain["expected_unchanged_projects"],"added_sparse_paths":chain["expected_new_sparse_paths"],"project_commits_unchanged":True,"policies_and_other_inputs_unchanged":True,"materialized_provider_files_verified":False,"rust_tests_run":False,"full_builds_started":0,"runtime_qualified":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo-root",type=Path,required=True)
    parser.add_argument("--capsule",type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    print(json.dumps(run(args.repo_root.resolve(),args.capsule.resolve()),indent=2,sort_keys=True))

if __name__=="__main__":
    main()
