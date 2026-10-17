#!/usr/bin/env python3
"""Offline integrity and semantic checks; does not execute guests or contact GitHub."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.parts and str(path) == name,
            "noncanonical path: " + name)
    require(all(part not in ("", ".", "..") for part in path.parts)
            and "\\" not in name and "\x00" not in name, "unsafe path: " + name)
    return path


def decode_api(record):
    if "result" in record:
        result = record["result"]
        require(result["status"] == "fulfilled", "API promise did not fulfill")
        response = result["value"]
    else:
        response = record["response"]
    require(response.get("isError") is not True, "API error receipt")
    data = response["structuredContent"]
    return json.loads(data["content"]) if isinstance(data.get("content"), str) else data


def verify_git_tree(tree):
    require(tree["truncated"] is False, "truncated remote tree")
    entries = {}
    children = {"": []}
    for entry in tree["tree"]:
        path = safe_path(entry["path"])
        require(entry["path"] not in entries, "duplicate Git path")
        require(re.fullmatch(r"[0-9a-f]{40}", entry["sha"]) is not None, "bad Git OID")
        require(entry["mode"] in ("040000", "100644", "100755", "120000", "160000"),
                "unsupported Git mode")
        kind = "tree" if entry["mode"] == "040000" else (
            "commit" if entry["mode"] == "160000" else "blob")
        require(entry["type"] == kind, "Git type/mode mismatch")
        entries[entry["path"]] = entry
        parent = str(path.parent) if str(path.parent) != "." else ""
        children.setdefault(parent, []).append((path.name, entry))
        if kind == "tree":
            children.setdefault(entry["path"], [])
    for path, members in children.items():
        if path:
            require(path in entries and entries[path]["type"] == "tree", "missing parent tree")
        body = b""
        for name, entry in sorted(members, key=lambda item: item[0].encode("utf-8")
                                  + (b"/" if item[1]["type"] == "tree" else b"")):
            body += (entry["mode"].lstrip("0").encode("ascii") + b" "
                     + name.encode("utf-8") + b"\0" + bytes.fromhex(entry["sha"]))
        oid = hashlib.sha1(b"tree " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()
        require(oid == (tree["sha"] if not path else entries[path]["sha"]),
                "Git tree object hash mismatch: " + path)
    return entries


def main():
    checksums = {}
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        safe_path(name)
        require(name not in checksums and re.fullmatch(r"[0-9a-f]{64}", expected), "bad checksum entry")
        require(digest((ROOT / name).read_bytes()) == expected, "phase checksum mismatch: " + name)
        checksums[name] = expected
    present = {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()}
    require(present == set(checksums) | {"SHA256SUMS"}, "unindexed phase file")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    payload = b""
    for part in manifest["archive"]["parts"]:
        data = (ROOT / part["path"]).read_bytes()
        require(0 < len(data) <= 2 * 1024 * 1024, "archive part size")
        require(len(data) == part["bytes"] and digest(data) == part["sha256"], "archive part mismatch")
        payload += data
    require(digest(payload) == manifest["archive"]["sha256"], "archive digest mismatch")
    require(len(payload) == manifest["archive"]["bytes"], "archive byte count mismatch")
    index = json.loads((ROOT / "source-index.json").read_text())
    expected = {item["path"]: item for item in index["files"]}
    require(len(expected) == len(index["files"]), "duplicate source index entry")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            require(member.isfile() and member.name not in files, "nonregular or duplicate archive member")
            require(member.name in expected, "unindexed archive member")
            require(member.size == expected[member.name]["bytes"], "source member size mismatch")
            data = archive.extractfile(member).read()
            require(digest(data) == expected[member.name]["sha256"], "source member hash mismatch")
            files[member.name] = data
    require(set(files) == set(expected), "archive source set mismatch")
    def js(path):
        return json.loads(files[path])
    publication = "next-publication/"
    remote_ref = decode_api(js(publication + "main-merge-readback-0.json"))
    remote_commit = decode_api(js(publication + "main-merge-readback-1.json"))
    remote_tree = decode_api(js(publication + "main-merge-readback-2.json"))
    commit = "09aea79c71dc9f48ba519757078dd8a20f5c8fb3"
    tree = "23eba5d298ff7db98f0ba6cd8b1c363094639cd4"
    parents = ["cdf308e751e561328c556ca2ece86056d15809a0", "b75f8e4ca6f55495a10d1652107c26010cdede7d"]
    require(remote_ref["object"]["sha"] == remote_commit["sha"] == commit, "merge commit/ref mismatch")
    require(remote_commit["tree"]["sha"] == remote_tree["sha"] == tree, "merge tree mismatch")
    require([x["sha"] for x in remote_commit["parents"]] == parents, "ordered merge parents mismatch")
    entries = verify_git_tree(remote_tree)
    require(len(entries) == 9128, "recursive tree entry count")
    require(entries["README.md"]["sha"] == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391", "root README not empty")
    require(entries["kernel/asterinas"]["sha"] == "6b3cab110aa6d30d5b89f99c4389c9c3e01022da", "kernel tree changed")
    require("tests/kernel/control/queryabi_guest.c" not in entries, "conditional fixture unexpectedly present")
    require(entries[".github/workflows/g0-contracts.yml"]["sha"]
            == "9a0bbc5c37b3991760e74303e23bc69ecbaba928", "workflow blob mismatch")
    tree_call = js(publication + "main-merge-create-tree.json")
    require(tree_call["args"]["base_tree_sha"] == "895a3c1530d8ecb74b8998a70df28b3345c6df40",
            "create-tree base mismatch")
    require(tree_call["args"]["tree_elements"] == [{"path": ".github/workflows/g0-contracts.yml",
            "mode": "100644", "type": "blob", "sha": "9a0bbc5c37b3991760e74303e23bc69ecbaba928"}],
            "merge tree mutation scope mismatch")
    update_call = js(publication + "main-merge-update-ref.json")
    require(update_call["args"]["expected_sha"] == parents[0]
            and update_call["args"]["sha"] == commit and update_call["args"]["force"] is False,
            "ref update lease/force mismatch")
    result = js("round-next/main-merge/result.json")
    require(result["base"] == parents[0] and result["main"] == parents[1], "local merge base mismatch")
    for command in result["commands"]:
        if "exit" in command:
            require(command["exit"] == 0, "local merge check failed")
            data = files["round-next/main-merge/" + command["name"] + ".log"]
            require(digest(data) == command["sha256"], "merge command log mismatch")
        else:
            require(command["source_present"] is False and command["guest_executed"] is False,
                    "conditional guest result changed")
    source = js("round-next/main-merge/source.log")
    require(source["checked_files"] == 118 and source["passed"] is True and source["errors"] == [],
            "source verification mismatch")
    cdf_checks = decode_api(js("next-round-ci-audit/cdf-check-runs.json"))["check_runs"]
    require(len(cdf_checks) == 3, "cdf exact-head check count")
    require(all(x["head_sha"] == parents[0] and x["status"] == "completed"
                and x["conclusion"] == "success" for x in cdf_checks), "cdf exact-head checks mismatch")
    for run_id in (38994983786, 38994981885):
        run = decode_api(js("next-round-ci-audit/run" + str(run_id) + ".json"))
        require(run["head_sha"] == parents[0] and run["status"] == "completed"
                and run["conclusion"] == "success", "cdf workflow mismatch")
    legacy = decode_api(js("next-round-ci-audit/cdf-combined-status.json"))
    require(legacy["statuses"] == [], "cdf legacy contexts differ")
    fresh = "latest-head-ci-readback/"
    fresh_checks = decode_api(js(fresh + "09aea-check-runs.json"))["check_runs"]
    require(len(fresh_checks) == 2, "09aea exact-head check count")
    require(all(x["head_sha"] == commit and x["status"] == "queued"
                and x["conclusion"] is None for x in fresh_checks), "09aea check snapshot mismatch")
    for name, run_id in (("host-run", 39001122216), ("codeql-run", 39001120343)):
        run = decode_api(js(fresh + name + ".json"))
        require(run["id"] == run_id and run["head_sha"] == commit
                and run["status"] == "queued" and run["conclusion"] is None,
                "09aea workflow snapshot mismatch")
    require(decode_api(js(fresh + "09aea-legacy-status.json"))["statuses"] == [],
            "09aea legacy contexts differ")
    fresh_ref = decode_api(js(fresh + "a01-ref.json"))
    fresh_main = decode_api(js(fresh + "main-ref.json"))
    require(fresh_ref["object"]["sha"] == commit, "fresh A01 ref mismatch")
    require(fresh_main["object"]["sha"] == "47288c4465720d125658b392efc655b333c90868",
            "fresh main ref mismatch")
    pr = decode_api(js(fresh + "pr22.json"))
    require(pr["head"]["sha"] == commit and pr["base"]["sha"] == parents[1]
            and pr["mergeable"] is True and pr["mergeable_state"] == "unstable",
            "PR22 observed-base snapshot mismatch")
    require(pr["base"]["sha"] != fresh_main["object"]["sha"],
            "snapshot must not extrapolate old-base mergeability to fresh main")
    print(json.dumps({"passed": True, "source_files": len(files), "git_tree_entries": len(entries),
                      "merge": commit, "cdf_ci_checks": len(cdf_checks),
                      "09aea_observed_ci": "queued; not a success result",
                      "guest_executed_in_this_phase": False}, indent=2))


if __name__ == "__main__":
    main()
