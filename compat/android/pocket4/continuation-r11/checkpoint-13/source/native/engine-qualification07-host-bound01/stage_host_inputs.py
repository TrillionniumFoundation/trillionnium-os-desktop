#!/usr/bin/env python3
"""Stage one frozen candidate07 host-suite input; default PLAN has no writes."""
import hashlib
import json
import os
import stat
import sys

PARENT = "/home/alex/work"
NAME = 'pocket4-combined07-qualification-inputs-dfcacd6f6da3cf3bdbfcf797f44481c3'
FILENAME = "host-candidate-inputs.json"
DATA = b'{\n  "arm": "candidate",\n  "baseline_result": {\n    "path": "/home/alex/work/pocket4-signal-host-baseline-r11-01-ff3127ab/result.json",\n    "sha256": "d99ee51205eeab9b6d33a2fcd6b4fa3d51304b06bc2fc638a470677a8f3a5a2e"\n  },\n  "binding": {\n    "candidate_build_inputs": {\n      "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/droidloom-native-engine-inputs.json",\n      "sha256": "97c3b9e686ee2c1d2ac2a5f996cc2cee0a7f54dcb939f09bb44c3f5278f9a5b5"\n    },\n    "candidate_build_receipt": {\n      "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/droidloom-native-engine-source.json",\n      "sha256": "648cc61ba4652df24061b45cf7875f7c880d1793e8c217bc519e21e2f3677b90"\n    },\n    "engine": {\n      "path": "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/android-out/target/product/droidloom_x86_64/system/lib64/libberberis_arm64.so",\n      "sha256": "3aa9b479a9b66f56ae827477cf9f957fdeb6dcb21f1f8f981e34a1089f80048a"\n    },\n    "signal_fix_pins": {\n      "path": "/home/alex/work/pocket4-owned-signal-host-r11-source-01/candidate-attempt-01/signal-mask-r1-pins.json",\n      "sha256": "6a24ef53595e9d8da458a626effbfca4280a5de18c90ad1d5dd036ad3e936bf2"\n    }\n  },\n  "cpu": 6,\n  "evidence": "/home/alex/work/pocket4-signal-host-candidate-combined07-dfcacd6f6da3",\n  "kind": "owned-full-host-suite-r1",\n  "main": {\n    "framework_guard": {\n      "path": "/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py",\n      "sha256": "f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"\n    },\n    "main_activation": {\n      "path": "/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json",\n      "sha256": "7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615"\n    },\n    "main_resource_baseline": {\n      "cpu.max": "200000 100000",\n      "memory.high": "5368709120",\n      "memory.max": "6442450944",\n      "memory.swap.max": "max",\n      "pids.max": "12288"\n    }\n  },\n  "nonce": "dfcacd6f6da3cf3bdbfcf797f44481c3",\n  "preparation_source": "/home/alex/work/pocket4-owned-signal-host-r11-source-01/isolated-signal-canary-r1",\n  "schema": 1,\n  "tools": {\n    "/usr/bin/python3": "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41",\n    "/usr/bin/systemctl": "639bce3ce5c06b605079ea56f74e3f08216ddffcfa76e11f62073aa775180082"\n  },\n  "unit": "p4-signal-host-candidate-dfcacd6f6da3.service"\n}\n'
SHA256 = 'a8e40759ccd97c3defdb59249757e1baae00d17926944826f060f9c612fc4eac'
NONCE = 'dfcacd6f6da3cf3bdbfcf797f44481c3'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def main():
    need(hashlib.sha256(DATA).hexdigest() == SHA256, "embedded input changed")
    inputs = json.loads(DATA)
    need(inputs["nonce"] == NONCE and len(NONCE) == 32 and
         all(c in "0123456789abcdef" for c in NONCE), "nonce mismatch")
    need(NAME == "pocket4-combined07-qualification-inputs-" + NONCE,
         "fixed owned directory mismatch")
    plan = {"schema": 1, "state": "PLAN_ONLY", "directory": PARENT + "/" + NAME,
            "file": FILENAME, "bytes": len(DATA), "sha256": SHA256,
            "tests_executed": False, "Android_executed": False, "Main_actions": 0}
    if sys.argv == [sys.argv[0]]:
        print(json.dumps(plan, sort_keys=True))
        return
    need(sys.argv[1:] == ["--execute-once"], "explicit fixed execution mode required")
    need(os.getuid() == os.geteuid() == 1000 and os.getgid() == os.getegid() == 1000,
         "operator uid/gid must remain 1000")
    need(os.path.realpath(PARENT) == PARENT, "owned parent is an alias")
    parent = os.open(PARENT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    directory = None
    target = None
    try:
        ps = os.fstat(parent)
        need(stat.S_ISDIR(ps.st_mode) and ps.st_uid == 1000 and ps.st_mode & 0o022 == 0,
             "owned parent permissions differ")
        # mkdir is the create-only claim. Existing or symlink names are rejected.
        os.mkdir(NAME, 0o700, dir_fd=parent)
        directory = os.open(NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                            dir_fd=parent)
        ds = os.fstat(directory)
        need(stat.S_ISDIR(ds.st_mode) and ds.st_uid == 1000 and ds.st_gid == 1000 and
             stat.S_IMODE(ds.st_mode) == 0o700,
             "new owned directory identity differs")
        target = os.open(FILENAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                         os.O_CLOEXEC, 0o600, dir_fd=directory)
        offset = 0
        while offset < len(DATA):
            written = os.write(target, DATA[offset:])
            need(written > 0, "short input write")
            offset += written
        os.fchmod(target, 0o400)
        os.fsync(target)
        ws = os.fstat(target)
        os.close(target)
        target = None
        target = os.open(FILENAME, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory)
        before = os.fstat(target)
        actual = os.read(target, len(DATA) + 1)
        after = os.fstat(target)
        named = os.stat(FILENAME, dir_fd=directory, follow_symlinks=False)
        need(identity(ws) == identity(before) == identity(after) == identity(named),
             "written/held/named input identity differs")
        need(stat.S_ISREG(after.st_mode) and after.st_nlink == 1 and
             after.st_uid == 1000 and after.st_gid == 1000 and
             stat.S_IMODE(after.st_mode) == 0o400 and actual == DATA and
             hashlib.sha256(actual).hexdigest() == SHA256,
             "staged input content or mode differs")
        d_after = os.fstat(directory)
        d_named = os.stat(NAME, dir_fd=parent, follow_symlinks=False)
        need(d_after.st_dev == ds.st_dev and d_after.st_ino == ds.st_ino and
             identity(d_after) == identity(d_named), "new directory replaced")
        os.fsync(directory)
        os.fsync(parent)
        plan.update(state="FROZEN_HOST_INPUT_STAGED_NOT_EXECUTED",
                    held_file_identity=identity(after), held_directory_identity=identity(d_after),
                    input_writes=1, children_created=0)
        print(json.dumps(plan, sort_keys=True))
    finally:
        for fd in (target, directory, parent):
            if fd is not None:
                os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"schema": 1, "state": "FAILED", "error": repr(error),
                          "errno": getattr(error, "errno", None),
                          "filename": getattr(error, "filename", None),
                          "tests_executed": False, "Android_executed": False,
                          "Main_actions": 0}, sort_keys=True))
        raise SystemExit(1)
