#!/usr/bin/env python3
"""Create local, immutable Go5 requests. This program never submits a request."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROLLER_SHA = "506c528d110f4b3e73d8e6c7d6d12217a8e4b9b6e7105935be3404805aba3e15"
FENCE_TEMPLATE_SHA = "004ae1a6e5843275d7ed91346c1a9c8d592212049c04ece247e24b8ba48aede2"
SNAPSHOT_SHA = "f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb"
CANDIDATE_SHA = "4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba"
BASE_BUILDER_SHA = "e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017"
GO_PATCH = "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"
GO5_SHA = "39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f"
ROOT = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-go5-01"
PREPARE_KEY = "pocket4-native-combined05-go5-full-source-preparation-01-20261104"
BUILD_KEY = "pocket4-native-combined05-go5-fenced-full-engine-flag0-build-01-20261104"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, why):
    if not value:
        raise RuntimeError(why)


def valid_sha(value):
    require(len(value) == 64 and all(c in "0123456789abcdef" for c in value), "explicit SHA required")
    return value


def read_pinned(path, wanted):
    raw = path.read_bytes()
    require(sha(raw) == valid_sha(wanted), "input changed: " + str(path))
    return raw


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def put(root, name, raw):
    with (root / name).open("xb") as stream:
        stream.write(raw)
    (root / name).chmod(0o444)


def controller():
    return read_pinned(HERE / "combined_build_go5.py", CONTROLLER_SHA)


def make_prepare():
    raw = controller()
    wrapper = ("import sys,hashlib;raw=sys.stdin.buffer.read();expected=" + repr(CONTROLLER_SHA) +
               ";assert hashlib.sha256(raw).hexdigest()==expected;"
               "scope={'__name__':'__main__','__file__':'<verified-combined05-go5-controller>',"
               "'VERIFIED_CONTROLLER_SHA256':expected};"
               "exec(compile(raw,'combined_build_go5.py','exec'),scope,scope)")
    return {"host": "pocket4", "executable": "/usr/bin/python3", "args": ["-I", "-c", wrapper, "--prepare"],
            "cwd": "/home/alex/work", "env": {"PYTHONDONTWRITEBYTECODE": "1"}, "stdin": raw.decode(),
            "idempotency_key": PREPARE_KEY, "timeout_seconds": 300,
            "cpu_quota_percent": 100, "memory_max_bytes": 1073741824, "nice": 10}


def validate_actual_preparation(preparation_raw, builder_manifest_raw):
    preparation = json.loads(preparation_raw)
    builder = json.loads(builder_manifest_raw)
    require(preparation["state"] == "PREPARED_NOT_BUILT" and
            preparation["candidate_manifest_sha256"] == CANDIDATE_SHA and
            preparation["base_builder_manifest_sha256"] == BASE_BUILDER_SHA and
            preparation["builder_manifest_sha256"] == sha(builder_manifest_raw),
            "actual Go5 preparation binding differs")
    require(preparation["engine_file_count"] == 925 and len(preparation["engine_files"]) == 925 and
            len(builder) == 449 and builder[GO_PATCH]["kind"] == "file" and
            builder[GO_PATCH]["bytes"] == 583 and builder[GO_PATCH]["sha256"] == GO5_SHA,
            "actual source inventory is incomplete or still uses the Go6 patch")
    require(preparation["base_and_candidate_unchanged"] is True and
            preparation["feature_default_enabled"] is False and preparation["full_engine_built"] is False and
            preparation["ART_built"] is False and preparation["factory_built"] is False and
            preparation["installed"] is False and preparation["Main_actions"] == 0,
            "preparation scope unexpectedly widened")
    expected_scope = {"__name__": "checked_local_profile", "__file__": str(HERE / "combined_build_go5.py")}
    exec(compile(controller(), "combined_build_go5.py", "exec"), expected_scope, expected_scope)
    require(preparation["plan"] == expected_scope["plan"](), "actual prepared plan differs from frozen profile")
    require(preparation["builder_source_delta"] == {
        "path": GO_PATCH, "preimage_sha256": expected_scope["GO_PATCH_PREIMAGE_SHA"],
        "sha256": GO5_SHA, "bytes": 583, "changed_bytes": 1}, "actual builder delta differs")
    return preparation


def write_request(root, files, metadata):
    # mkdir is intentionally exclusive. Reconcile an existing exact request;
    # never overwrite it, modify its key, or silently select another attempt.
    root.mkdir(mode=0o700)
    for name, raw in files.items():
        put(root, name, raw)
    rows = {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in files.items()}
    metadata.update({"schema": 1, "files": rows, "submitted": False, "remote_actions": 0})
    put(root, "REQUEST_PINS.json", encoded(metadata))
    print(json.dumps({"root": str(root), "request_sha256": rows["exact-request.json"]["sha256"],
                      "pins_sha256": sha((root / "REQUEST_PINS.json").read_bytes()), "submitted": False}))


def prepare_request(args):
    request = make_prepare()
    write_request(args.output_dir, {"exact-request.json": encoded(request)}, {
        "state": "GO5_PREPARATION_REQUEST_NOT_SUBMITTED", "controller_sha256": CONTROLLER_SHA,
        "new_root": ROOT, "candidate05_manifest_sha256": CANDIDATE_SHA,
        "base_builder_manifest_sha256": BASE_BUILDER_SHA, "Go5_patch_sha256": GO5_SHA,
        "new_actual_builder_manifest_sha256": None, "actual_preparation_observed": False})


def build_request(args):
    preparation_raw = read_pinned(args.preparation, args.preparation_sha256)
    builder_manifest_raw = read_pinned(args.builder_manifest, args.builder_manifest_sha256)
    preparation = validate_actual_preparation(preparation_raw, builder_manifest_raw)
    template = read_pinned(HERE / "fenced_build_go5.template.py", FENCE_TEMPLATE_SHA).decode()
    require(template.count("ACTUAL_GO5_PREPARATION_SHA_REQUIRED") == 1, "template placeholder differs")
    fence = template.replace("ACTUAL_GO5_PREPARATION_SHA_REQUIRED", args.preparation_sha256)
    snapshot = read_pinned(HERE / "main_snapshot.py", SNAPSHOT_SHA).decode()
    packet = {"schema": 1, "outer_source": fence, "outer_sha256": sha(fence.encode()),
              "controller_source": controller().decode(), "snapshot_source": snapshot,
              "snapshot_sha256": SNAPSHOT_SHA}
    packet_raw = encoded(packet)
    wrapper = ("import sys,hashlib,json;raw=sys.stdin.buffer.read();assert hashlib.sha256(raw).hexdigest()==" +
               repr(sha(packet_raw)) + ";packet=json.loads(raw);source=packet['outer_source'];"
               "assert hashlib.sha256(source.encode()).hexdigest()==" + repr(sha(fence.encode())) + ";"
               "scope={'__name__':'__main__','__file__':'<verified-combined05-go5-fenced-build>','PACKET':packet};"
               "exec(compile(source,'fenced_build_go5.py','exec'),scope,scope)")
    request = {"host": "pocket4", "executable": "/usr/bin/python3",
               "args": ["-I", "-c", wrapper, "--execute-once"], "cwd": "/home/alex/work",
               "env": {"PYTHONDONTWRITEBYTECODE": "1"}, "stdin": packet_raw.decode(),
               "idempotency_key": BUILD_KEY, "timeout_seconds": 6400, "cpu_quota_percent": 200,
               "memory_max_bytes": 10737418240, "nice": 10}
    patch = ''.join(difflib.unified_diff(template.splitlines(True), fence.splitlines(True),
                                        fromfile='a/fenced_build_go5.template.py', tofile='b/fenced_build_go5.py'))
    write_request(args.output_dir, {"fenced_build_go5.py": fence.encode(),
                                  "verified-source-packet.json": packet_raw, "exact-request.json": encoded(request),
                                  "template-to-actual-preparation.patch": patch.encode()}, {
        "state": "GO5_FENCED_BUILD_REQUEST_NOT_SUBMITTED",
        "controller_sha256": CONTROLLER_SHA, "new_root": ROOT,
        "actual_preparation_sha256": args.preparation_sha256,
        "actual_builder_manifest_sha256": preparation["builder_manifest_sha256"],
        "base_builder_manifest_sha256": BASE_BUILDER_SHA,
        "candidate05_manifest_sha256": CANDIDATE_SHA, "Go5_patch_sha256": GO5_SHA,
        "Main_snapshot_source_sha256": SNAPSHOT_SHA, "main_observed_invariants_and_oom_gate": True,
        "resource_budget": {"cpu_quota_percent": 200, "memory_max_bytes": 10737418240,
                            "minimum_MemAvailable_bytes": 15032385536,
                            "own_memory_swap_max_bytes": 1073741824, "normal_builder_jobs": 1,
                            "admission_difference_bytes": 4294967296, "physical_reservation_claimed": False},
        "feature_enabled": False, "ART_built": False, "factory_service_started": False,
        "whole_apps_ready": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    prepare = commands.add_parser("prepare-request")
    prepare.add_argument("--output-dir", type=Path, required=True)
    build = commands.add_parser("build-request")
    build.add_argument("--preparation", type=Path, required=True)
    build.add_argument("--preparation-sha256", required=True)
    build.add_argument("--builder-manifest", type=Path, required=True)
    build.add_argument("--builder-manifest-sha256", required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command is None:
        print(json.dumps({"state": "PLAN_ONLY", "new_root": ROOT, "preparation_key": PREPARE_KEY,
                          "build_key": BUILD_KEY, "actual_preparation_required_for_build": True,
                          "remote_actions": 0}))
    elif args.command == "prepare-request":
        prepare_request(args)
    else:
        build_request(args)


if __name__ == '__main__':
    main()
