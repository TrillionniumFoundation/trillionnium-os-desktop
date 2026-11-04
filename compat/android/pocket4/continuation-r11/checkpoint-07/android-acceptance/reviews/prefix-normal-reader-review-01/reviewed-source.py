"""Read the fixed normal attempt's owned JSON evidence; never start or clean a unit."""
import argparse
import hashlib
import json
import os
import re
import stat

SOURCE_ROOT = "/home/alex/work/pocket4-relay-prefix-r11-source-05-01"
BASE = "/home/alex/work/pocket4-relay-prefix-r11-owned"
LEAF = "p4-relay-prefix-5dcff218dbef5869c213de3c-normal"
NAMESPACE = "p4-relay-prefix-5dcff218dbef5869c213de3c"
NONCE = "5dcff218dbef5869c213de3c4bcf475ff76111794ac3bb302fac2d73d396f2be"
PLAN_SHA = "dd9c420ae36678e3dc6fc4cbac4b08730a133a6b4b37ae11496c6f4b46babaef"
MEMBERS = ("coordinator-result.json", "prefix-result.json", "coordinator-claim.json", "once.claim.json",
           "actor-input.json", "actor-admission.json", "namespace-created.json", "unit-first-observation.json")

def need(value, message):
    if not value:
        raise RuntimeError(message)

def metadata(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def directory(path, parent=None):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                 dir_fd=parent)
    s = os.fstat(fd)
    if not (stat.S_ISDIR(s.st_mode) and s.st_uid == s.st_gid == 0
            and stat.S_IMODE(s.st_mode) == 0o700):
        os.close(fd)
        raise RuntimeError("fixed evidence directory is not root-private")
    return fd

def read_member(parent, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0
             and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600
             and 0 < before.st_size <= 65536, "fixed JSON file metadata/bound differs: " + name)
        raw = bytearray()
        while True:
            part = os.read(fd, min(8192, 65537 - len(raw)))
            if not part:
                break
            raw.extend(part)
            need(len(raw) <= 65536, "fixed JSON file grew: " + name)
        need(metadata(before) == metadata(os.fstat(fd)) and len(raw) == before.st_size,
             "fixed JSON file changed during read: " + name)
        text = bytes(raw).decode("utf-8", "strict")
        value = json.loads(text)
        need(isinstance(value, dict), "fixed JSON file is not an object: " + name)
        return {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "device": before.st_dev, "inode": before.st_ino, "text": text}, value
    finally:
        os.close(fd)

parser = argparse.ArgumentParser(description=__doc__)
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--expected-result-sha256")
mode.add_argument("--expect-result-missing", action="store_true")
args = parser.parse_args()
need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, "exact root reader required")
if args.expected_result_sha256 is not None:
    need(re.fullmatch("[0-9a-f]{64}", args.expected_result_sha256) is not None,
         "observed external result digest required")
handles = []
output = {"schema": 1, "scope": "READ_ONLY_FIXED_NORMAL_PREFIX_EVIDENCE",
          "nonce": NONCE, "plan_sha256": PLAN_SHA, "root": BASE + "/" + LEAF,
          "namespace_actions": 0, "unit_actions": 0, "Android_operations": 0,
          "qualification_performed_by_reader": False, "files": [], "missing": []}
try:
    source = directory(SOURCE_ROOT); handles.append(source)
    plan_row, plan = read_member(source, "normal-plan-01.json")
    need(plan_row["sha256"] == PLAN_SHA and plan["nonce"] == NONCE and plan["mode"] == "normal"
         and plan["scope"] == "OWNED_HOST_PREFIX_ONLY_NO_ANDROID" and plan["predecessor"] is None,
         "fixed externally admitted normal plan differs")
    base = directory(BASE); handles.append(base)
    try:
        evidence = directory(LEAF, base)
    except FileNotFoundError:
        need(args.expect_result_missing, "expected terminal result directory is absent")
        output["evidence_directory_absent"] = True
        output["missing"] = list(MEMBERS)
    else:
        handles.append(evidence)
        info = os.fstat(evidence)
        output["held_directory_identity"] = [info.st_dev, info.st_ino]
        values = {}
        for name in MEMBERS:
            try:
                row, value = read_member(evidence, name)
            except FileNotFoundError:
                output["missing"].append(name)
                continue
            output["files"].append(row)
            values[name] = value
            need(sum(item["bytes"] for item in output["files"]) <= 262144,
                 "aggregate fixed evidence bound exceeded")
        if args.expect_result_missing:
            need("coordinator-result.json" not in values, "terminal result exists; bind its observed SHA first")
        else:
            rows = [row for row in output["files"] if row["path"] == "coordinator-result.json"]
            need(len(rows) == 1 and rows[0]["sha256"] == args.expected_result_sha256,
                 "actual terminal result differs from observed external SHA")
        if values:
            need("coordinator-claim.json" in values, "no original one-shot claim for nonempty evidence")
            claim = values["coordinator-claim.json"]
            need(claim["nonce"] == NONCE and claim["plan_sha256"] == PLAN_SHA
                 and claim["unit"] == LEAF + ".service" and claim["namespace"] == NAMESPACE,
                 "original claim does not bind this fixed normal attempt")
        for name, value in values.items():
            need(value.get("nonce") == NONCE, "foreign nonce in fixed owned record: " + name)
            if "plan_sha256" in value:
                need(value["plan_sha256"] == PLAN_SHA, "foreign plan in fixed owned record: " + name)
        result = values.get("coordinator-result.json")
        if result is not None:
            need(result["mode"] == "normal" and result["scope"] == plan["scope"]
                 and result["sources"] == plan["sources"] and result["tools"] == plan["tools"],
                 "terminal result scope/source contract differs")
        after = os.stat(LEAF, dir_fd=base, follow_symlinks=False)
        need([after.st_dev, after.st_ino] == [info.st_dev, info.st_ino], "evidence directory replaced during read")
    raw = (json.dumps(output, ensure_ascii=True, sort_keys=True) + "\n").encode()
    need(len(raw) <= 524288, "fixed evidence stdout envelope exceeded")
    print(raw.decode("ascii"), end="", flush=True)
finally:
    for fd in reversed(handles):
        os.close(fd)
