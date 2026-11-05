#!/usr/bin/env python3
"""Create local, immutable Go5 streaming requests. This program never submits a request."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROLLER_SHA = "BOUND_CANDIDATE06_CONTROLLER_SHA_REQUIRED"
FENCE_TEMPLATE_SHA = "BOUND_CANDIDATE06_FENCE_SHA_REQUIRED"
SNAPSHOT_SHA = "f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb"
CANDIDATE_SHA = "3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376"
BASE_BUILDER_SHA = "6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4"
GO_PATCH = "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"
STREAMING_SHA = "39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f"
RUNTIME_BUILDER_SHA = "776435c88ca6ddb983456c639ca051e586731140394756f33abe53dc478357e3"
ROOT = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined06-go5-streaming-01"
PREPARE_KEY = "pocket4-native-combined06-go5-streaming-full-source-preparation-01-20261105"
BUILD_KEY = "pocket4-native-combined06-go5-streaming-fenced-cold-engine-flag0-build-01-20261105"


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
    return read_pinned(HERE / "combined_build_streaming.py", CONTROLLER_SHA)


def make_prepare():
    raw = controller()
    wrapper = ("import sys,hashlib;raw=sys.stdin.buffer.read();expected=" + repr(CONTROLLER_SHA) +
               ";assert hashlib.sha256(raw).hexdigest()==expected;"
               "scope={'__name__':'__main__','__file__':'<verified-combined06-go5-streaming-controller>',"
               "'VERIFIED_CONTROLLER_SHA256':expected};"
               "exec(compile(raw,'combined_build_streaming.py','exec'),scope,scope)")
    return {"host": "pocket4", "executable": "/usr/bin/python3", "args": ["-I", "-c", wrapper, "--prepare"],
            "cwd": "/home/alex/work", "env": {"PYTHONDONTWRITEBYTECODE": "1"}, "stdin": raw.decode(),
            "idempotency_key": PREPARE_KEY, "timeout_seconds": 300,
            "cpu_quota_percent": 100, "memory_max_bytes": 1073741824, "nice": 10}


def validate_actual_preparation(preparation_raw, builder_manifest_raw):
    preparation = json.loads(preparation_raw)
    builder = json.loads(builder_manifest_raw)
    require(preparation["state"] == "PREPARED_NOT_BUILT" and
            preparation["candidate_manifest_sha256"] == CANDIDATE_SHA and
            preparation["builder_manifest_sha256"] == RUNTIME_BUILDER_SHA == sha(builder_manifest_raw) and
            preparation["compiled_builder_manifest_sha256"] == BASE_BUILDER_SHA and
            preparation["runtime_data_patch_sha256"] == STREAMING_SHA and
            preparation["compiled_preimage_patch_sha256"] == "6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e" and
            preparation["runtime_data_changed_files"] == [GO_PATCH] and preparation["Rust_recompiled"] is False,
            "actual Go5 streaming preparation binding differs")
    require(preparation["engine_file_count"] == 925 and len(preparation["engine_files"]) == 925 and
            len(builder) == 450 and builder[GO_PATCH]["kind"] == "file" and
            builder[GO_PATCH]["bytes"] == 583 and builder[GO_PATCH]["sha256"] == STREAMING_SHA,
            "actual source inventory is incomplete or does not use the derived Go5 runtime patch")
    require(preparation["base_and_candidate_unchanged"] is True and
            preparation["feature_default_enabled"] is False and preparation["full_engine_built"] is False and
            preparation["ART_built"] is False and preparation["factory_built"] is False and
            preparation["installed"] is False and preparation["Main_actions"] == 0,
            "preparation scope unexpectedly widened")
    expected_scope = {"__name__": "checked_local_profile", "__file__": str(HERE / "combined_build_streaming.py")}
    exec(compile(controller(), "combined_build_streaming.py", "exec"), expected_scope, expected_scope)
    require(preparation["plan"] == expected_scope["plan"](), "actual prepared plan differs from frozen profile")
    require(preparation["parent_candidate_manifest_sha256"] == "4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba" and
            preparation["actual_candidate06_composition_sha256"] == expected_scope["COMPOSITION_REPORT_SHA"] and
            preparation["actual_NOFILE_Android_runtime_sha256"] == expected_scope["NOFILE_ANDROID_SHA"] and
            preparation["actual_NOFILE_host_runtime_sha256"] == expected_scope["NOFILE_HOST_SHA"],
            "actual candidate06 composition/probe binding differs")
    require(preparation["actual_builder_compile_sha256"] == 'a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de' and
            preparation["builder_sha256"] == 'ea80146d5fc47f9927dd16a1ad91b6b48f0b30f0ce043d4eaef53f0e84f482b6' and
            preparation["Blueprint_streaming_patch_sha256"] == '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307',
            "actual matching streaming builder or its compilation receipt differs")
    require(builder_manifest_raw == read_pinned(HERE / "expected-runtime-builder-source-manifest.json",
                                               RUNTIME_BUILDER_SHA), "actual 450-file manifest differs")
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
        "state": "STREAMING_PREPARATION_REQUEST_NOT_SUBMITTED", "controller_sha256": CONTROLLER_SHA,
        "new_root": ROOT, "candidate06_manifest_sha256": CANDIDATE_SHA,
        "base_builder_manifest_sha256": BASE_BUILDER_SHA, "Go5_runtime_patch_sha256": STREAMING_SHA,
        "actual_builder_compile_sha256": 'a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de',
        "Blueprint_streaming_patch_sha256": '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307',
        "expected_runtime_builder_manifest_sha256": RUNTIME_BUILDER_SHA,
        "new_actual_builder_manifest_sha256": None, "actual_preparation_observed": False})


def build_request(args):
    preparation_raw = read_pinned(args.preparation, args.preparation_sha256)
    builder_manifest_raw = read_pinned(args.builder_manifest, args.builder_manifest_sha256)
    preparation = validate_actual_preparation(preparation_raw, builder_manifest_raw)
    template = read_pinned(HERE / "fenced_build_streaming.template.py", FENCE_TEMPLATE_SHA).decode()
    require(template.count("ACTUAL_GO5_STREAMING_PREPARATION_SHA_REQUIRED") == 1, "template placeholder differs")
    fence = template.replace("ACTUAL_GO5_STREAMING_PREPARATION_SHA_REQUIRED", args.preparation_sha256)
    snapshot = read_pinned(HERE / "main_snapshot.py", SNAPSHOT_SHA).decode()
    packet = {"schema": 1, "outer_source": fence, "outer_sha256": sha(fence.encode()),
              "controller_source": controller().decode(), "snapshot_source": snapshot,
              "snapshot_sha256": SNAPSHOT_SHA}
    packet_raw = encoded(packet)
    wrapper = ("import sys,hashlib,json;raw=sys.stdin.buffer.read();assert hashlib.sha256(raw).hexdigest()==" +
               repr(sha(packet_raw)) + ";packet=json.loads(raw);source=packet['outer_source'];"
               "assert hashlib.sha256(source.encode()).hexdigest()==" + repr(sha(fence.encode())) + ";"
               "scope={'__name__':'__main__','__file__':'<verified-combined06-go5-streaming-fenced-build>','PACKET':packet};"
               "exec(compile(source,'fenced_build_streaming.py','exec'),scope,scope)")
    request = {"host": "pocket4", "executable": "/usr/bin/python3",
               "args": ["-I", "-c", wrapper, "--execute-once"], "cwd": "/home/alex/work",
               "env": {"PYTHONDONTWRITEBYTECODE": "1"}, "stdin": packet_raw.decode(),
               "idempotency_key": BUILD_KEY, "timeout_seconds": 6400, "cpu_quota_percent": 200,
               "memory_max_bytes": 10737418240, "nice": 10}
    patch = ''.join(difflib.unified_diff(template.splitlines(True), fence.splitlines(True),
                                        fromfile='a/fenced_build_streaming.template.py', tofile='b/fenced_build_streaming.py'))
    write_request(args.output_dir, {"fenced_build_streaming.py": fence.encode(),
                                  "verified-source-packet.json": packet_raw, "exact-request.json": encoded(request),
                                  "template-to-actual-preparation.patch": patch.encode()}, {
        "state": "STREAMING_FENCED_BUILD_REQUEST_NOT_SUBMITTED",
        "controller_sha256": CONTROLLER_SHA, "new_root": ROOT,
        "actual_preparation_sha256": args.preparation_sha256,
        "actual_builder_manifest_sha256": preparation["builder_manifest_sha256"],
        "base_builder_manifest_sha256": BASE_BUILDER_SHA,
        "candidate06_manifest_sha256": CANDIDATE_SHA, "Go5_runtime_patch_sha256": STREAMING_SHA,
        "actual_builder_compile_sha256": 'a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de',
        "Blueprint_streaming_patch_sha256": '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307',
        "Main_snapshot_source_sha256": SNAPSHOT_SHA, "main_observed_invariants_and_oom_gate": True,
        "resource_budget": {"cpu_quota_percent": 200, "memory_max_bytes": 10737418240,
                            "minimum_MemAvailable_bytes": 13958643712,
                            "minimum_SwapFree_bytes": 2147483648,
                            "own_memory_swap_max_bytes": 1073741824, "normal_builder_jobs": 1,
                            "admission_difference_bytes": 3221225472,
                            "swap_admission_difference_bytes": 1073741824, "physical_reservation_claimed": False},
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
