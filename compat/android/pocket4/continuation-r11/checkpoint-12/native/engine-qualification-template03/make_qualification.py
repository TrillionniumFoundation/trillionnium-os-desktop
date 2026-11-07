#!/usr/bin/env python3
"""Offline receipt binding for the unchanged 3793-test/R5 four-signal gates.

Default is PLAN. This program never contacts Pocket4, executes a test, starts a
service, or writes outside a new local output directory. Each generated remote
request remains subject to the root agent's separate review and dispatch.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REFERENCES = HERE / "references"
OWNER = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01"
HOST_SOURCE = "/home/alex/work/pocket4-owned-signal-host-r11-source-01/isolated-signal-canary-runtime-r1"
R5_SOURCE = "/home/alex/work/pocket4-signal-runtime-r5-work-01/source-frozen-r5-03"
HOST_MANIFEST = "ad47718c72d7fd8ecb3ce4147fd3e6dbc2ec6f662d079103bd7ecb5a55863bc5"
R5_MANIFEST = "1825e327e039ac58779085444aa69896990eaa06f8fde24cfb4e98642508486a"
CANDIDATE_MANIFEST = "e10024548a5b2b5a391ecc9ddb3ea2f19b95a6fea3437f40207a0f4721745a93"
PARENT_MANIFEST = "3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376"
COMPOSITION_SHA = "44d4b170ed158802cd12a5f59fd3ebf31d86bce6a621b6f2904f13fed8737f08"
UAPI_TU_GATE_SHA = "5a09aa094c960a2bcc2d357fa732aac0cdb95203d25d3b690ced62497bb1c1d1"
NOFILE_ANDROID_SHA = "fbc3ca4d6e861b50da8ee537c90908b5308249015a31220acdd2d09b00f42b13"
NOFILE_HOST_SHA = "b0a03b1b95e3292131105dcb22fd59f4a767e63017197e29f4482036976a4ac2"
BUILD_ROOT = OWNER + "/full-build-combined07-go5-streaming-01"
COMPILED_BUILDER_MANIFEST = "6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4"
RUNTIME_BUILDER_MANIFEST = "776435c88ca6ddb983456c639ca051e586731140394756f33abe53dc478357e3"
BUILDER_COMPILE_SHA = "a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de"
BUILDER_SHA = "ea80146d5fc47f9927dd16a1ad91b6b48f0b30f0ce043d4eaef53f0e84f482b6"
BLUEPRINT_PATCH = "9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307"
GO_PATCH = "39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f"
SOONG_SOURCE = "4e6fb778c1aee7bfc9b3206940364edbf3502912fe692fa91b612ab389ed07d9"
SIGNAL = {
    "guest_os_primitives/arm64/guest_context_arch.h": "c4234d83ce70c526d96cbd9b843dbca1e0645c18d7f371654552d2a8e2f07140",
    "guest_os_primitives/guest_signal_handling.cc": "7ca556ea512b2262e2bf28709bbb7962d4ef5cb7e4c53c012437b6603fd9623a",
    "guest_os_primitives/guest_signal_handling_arch.cc": "5fc077ed8538255bac2ac921b1231a3bf60314659f85c79237d724c41f0460b5",
    "guest_os_primitives/include/berberis/guest_os_primitives/guest_signal.h": "ebcc5ac4e092c50916a0f9668c94d3cb2266cece0ff728bc19513e8f7eb218ca",
    "guest_os_primitives/include/berberis/guest_os_primitives/guest_thread.h": "90a35d504656e32520ab84968ae8a3b586264c835489d13f85f42444cb0764c0",
    "guest_os_primitives/scoped_guest_signal_mask.h": "52c18a437a05e00be80420c39ef03d24b4ec86a2470b66b548c29d8888eecde9",
}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(items):
    result = {}
    for key, value in items:
        need(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def read_reference(name):
    pins = parse((HERE / "reference-pins.json").read_bytes())
    need(name in pins["files"], "unlisted frozen reference")
    raw = (REFERENCES / name).read_bytes()
    need(len(raw) == pins["files"][name]["bytes"] and
         sha(raw) == pins["files"][name]["sha256"], "frozen reference changed: " + name)
    return parse(raw)


def pinned(row):
    need(set(row) == {"local_path", "path", "sha256"}, "actual local/remote pin requires exact fields")
    need(all(isinstance(row[key], str) for key in ("local_path", "path", "sha256")),
         "all actual receipt paths and hashes must be filled; placeholders are not evidence")
    need(Path(row["local_path"]).is_absolute() and Path(row["path"]).is_absolute() and
         re.fullmatch(r"[0-9a-f]{64}", row["sha256"] or ""), "explicit actual receipt pin required")
    raw = Path(row["local_path"]).read_bytes()
    need(sha(raw) == row["sha256"], "actual receipt bytes differ: " + row["local_path"])
    return parse(raw)


def remote_pin(row):
    return {"path": row["path"], "sha256": row["sha256"]}


def prior_candidate06_failure_preserved():
    # These are the original failed predecessor build receipts, never candidate07
    # acceptance evidence. The new candidate uses a fresh root and fence01.
    inner = read_reference("prior-candidate06-inner-failure.json")
    outer = read_reference("prior-candidate06-outer-failure.json")
    need(inner["state"] == "FAILED" and inner["builder_returncode"] == 1 and
         inner["artifact_gate"] is None and inner["cleanup"]["complete"] is True and
         outer["state"] == "FAILED" and outer["inner_returncode"] == 1,
         "failed candidate06 predecessor evidence was not retained exactly")


def build_binding(config):
    rows = config["build"]
    need(set(rows) == {"preparation", "terminal", "fence", "inputs", "receipt"},
         "all five actual build receipts are required")
    prep, terminal, fence, inputs, receipt = (pinned(rows[x]) for x in
                                            ("preparation", "terminal", "fence", "inputs", "receipt"))
    root = Path(rows["preparation"]["path"]).parent
    need(root == Path(BUILD_ROOT) and
         rows["preparation"]["path"] == str(root / "preparation.json"), "unreviewed build owner path")
    need(prep["state"] == "PREPARED_NOT_BUILT" and prep["candidate_manifest_sha256"] == CANDIDATE_MANIFEST and
         prep["engine_file_count"] == len(prep["engine_files"]) == 926 and
         prep["builder_sha256"] == BUILDER_SHA and prep["Blueprint_streaming_patch_sha256"] == BLUEPRINT_PATCH and
         prep["feature_default_enabled"] is False and prep["base_and_candidate_unchanged"] is True,
         "preparation is not the frozen candidate07 streaming source")
    need(prep["parent_candidate_manifest_sha256"] == PARENT_MANIFEST and
         prep["actual_candidate07_composition_sha256"] == COMPOSITION_SHA and
         prep["actual_complete_TU_gate_sha256"] == UAPI_TU_GATE_SHA and
         prep["actual_NOFILE_Android_runtime_sha256"] == NOFILE_ANDROID_SHA and
         prep["actual_NOFILE_host_runtime_sha256"] == NOFILE_HOST_SHA and
         prep["engine_files"] == read_reference("candidate07-engine926.json"),
         "candidate07 source ancestry or actual NOFILE qualifications differ")
    need(prep["builder_manifest_sha256"] == RUNTIME_BUILDER_MANIFEST and
         prep["compiled_builder_manifest_sha256"] == COMPILED_BUILDER_MANIFEST and
         prep["actual_builder_compile_sha256"] == BUILDER_COMPILE_SHA and
         prep["runtime_data_patch_sha256"] == GO_PATCH and
         prep["compiled_preimage_patch_sha256"] == "6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e" and
         prep["runtime_data_changed_files"] == ["android/apex-compat/0008-soong-leaf-go-memory-budget.patch"] and
         prep["Rust_recompiled"] is False and prep["plan"] == read_reference("candidate07-build-plan.json"),
         "actual compiled450 / derived runtime450 / resource profile differs")
    need(rows["terminal"]["path"] == str(root / "attempt-01/terminal.json") and
         rows["fence"]["path"] == str(root / "build-fences-01/terminal.json"), "build terminal path differs")
    prior_candidate06_failure_preserved()
    need(terminal["state"] == "ARTIFACTS_BUILT_QUALIFICATION_PENDING" and
         terminal["builder_returncode"] == 0 and terminal["error"] is None and
         terminal["cleanup"]["complete"] is True and not terminal.get("observation_errors") and
         terminal["owned_resource_gate"]["pass"] is True and
         terminal["owned_resource_gate"]["owned_oom_kills_zero"] is True,
         "actual engine build has not completed with artifacts/resources/cleanup")
    need(fence["state"] == "BUILD_AND_OBSERVED_MAIN_FENCES_PASSED" and
         fence["inner_returncode"] == 0 and fence["error"] is None and
         fence["before_observed"] is True and fence["after_observed"] is True and
         fence["main_fence_assessment"]["main_fence_pass"] is True and
         fence["main_fence_assessment"]["main_oom_delta_zero"] is True,
         "actual Main observation fence did not pass")
    out = root / "android-out"
    product = out / "target/product/droidloom_x86_64"
    need(rows["inputs"]["path"] == str(product / "droidloom-native-engine-inputs.json") and
         rows["receipt"]["path"] == str(product / "droidloom-native-engine-source.json") and
         inputs["output_directory"] == str(out), "actual artifact receipt output path differs")
    need(inputs["scope"] == "native-engine-only" and inputs["status"] == "inputs_captured" and
         inputs["logical_targets"] == ["libberberis_arm64", "berberis_arm64_host_tests"] and
         inputs["tests_requested"] is True and
         inputs["source_snapshot"]["files"] == prep["engine_files"], "complete926 source/targets differ")
    expected = dict(inputs)
    expected.update(status="selected_artifacts_built", engine=receipt["engine"], host_tests=receipt["host_tests"])
    need(receipt == expected, "input/final build receipts differ beyond produced artifacts")
    for path, digest in SIGNAL.items():
        need(inputs["source_snapshot"]["files"][path] == inputs["effective_teto_files"][path] == digest,
             "combined build regresses the qualified signal delta")
    for key in ("installation_performed", "runtime_compatibility_verified", "full_product_qualified", "full_runtime_rebuilt"):
        need(receipt[key] is False, "build widened its qualification scope")
    engine = receipt["engine"]
    need(engine["path"] == str(product / "system/lib64/libberberis_arm64.so") and
         engine["elf"]["machine"] == "EM_X86_64" and engine["metadata"]["soname"] == "libberberis_arm64.so",
         "actual host engine identity/layout differs")
    artifact = terminal["artifact_gate"]
    need(artifact["input_receipt_sha256"] == rows["inputs"]["sha256"] and
         artifact["final_receipt_sha256"] == rows["receipt"]["sha256"] and
         artifact["engine"] == engine and artifact["host_tests"] == receipt["host_tests"] and
         artifact["raw_source_files"] == 926 and artifact["six_signal_hashes_match"] is True and
         artifact["feature_default_enabled"] is False and artifact["private_entry_export_observed"] is True and
         artifact["go_projection"]["new_patch_sha256"] == BLUEPRINT_PATCH and
         artifact["go_projection"]["patch_sha256"] == GO_PATCH and
         artifact["go_projection"]["projected_soong_sha256"] == SOONG_SOURCE and
         artifact["go_projection"]["all_other_prior_patch_hashes_unchanged"] is True and
         artifact["go_projection"]["normal_builder_lock_and_journal_recovery_required"] is True,
         "full artifact gate is missing or belongs to another build")
    host = receipt["host_tests"]
    need(host["built"] is True and host["executed"] is False and
         host["variant"] == "linux_glibc_x86_64" and host["guest_architecture"] == "arm64" and
         len(host["data"]) == 3 and len(host["shared_libraries"]) == 3,
         "full unrun host binary/loader/corpora closure required")
    old = read_reference("old-host-candidate-inputs.json")
    return {"candidate_build_inputs": remote_pin(rows["inputs"]),
            "candidate_build_receipt": remote_pin(rows["receipt"]),
            "engine": {"path": engine["path"], "sha256": engine["sha256"]},
            "signal_fix_pins": old["binding"]["signal_fix_pins"]}


def nonce(config):
    value = config["nonce"]
    need(re.fullmatch(r"[0-9a-f]{32}", value or ""), "new explicit 32-hex nonce required")
    need(value not in {"9d630262872f4a09acf4ae710974d5f3", "ff3127ab4ee244a590a0817e586ce538",
                       "aefbacbc3c7544a6aae0ee8b1bcfe80e"}, "historical nonce may not be reused")
    return value


def input_root(config):
    return "/home/alex/work/pocket4-combined07-qualification-inputs-" + nonce(config)


def host_config(config, binding):
    value = read_reference("old-host-candidate-inputs.json")
    n = nonce(config)
    value.update(binding=binding, nonce=n,
                 unit="p4-signal-host-candidate-" + n[:12] + ".service",
                 evidence="/home/alex/work/pocket4-signal-host-candidate-combined07-" + n[:12])
    return value


def set_option(argv, name, value):
    need(argv.count(name) == 1, "ambiguous original request option: " + name)
    argv[argv.index(name) + 1] = value


def host_requests(config, binding):
    value = host_config(config, binding)
    path = input_root(config) + "/host-candidate-inputs.json"
    digest = sha(encoded(value))
    request = read_reference("baseline-run-request.json")
    args = request["args"]
    for i, arg in enumerate(args):
        if arg.startswith("--unit="):
            args[i] = "--unit=" + value["unit"]
        if arg.startswith("--description="):
            args[i] = "--description=Owned full signal host suite " + nonce(config)
    set_option(args, "--inputs", path)
    set_option(args, "--inputs-sha256", digest)
    request["idempotency_key"] = "pocket4-combined07-host3793-" + nonce(config)
    check = {"host": "pocket4", "executable": "/usr/bin/sudo", "args": ["-n", "/usr/bin/python3", "-I",
             HOST_SOURCE + "/host_suite.py", "check", "--inputs", path, "--inputs-sha256", digest,
             "--source-manifest", HOST_SOURCE + "/source-manifest.json", "--source-manifest-sha256", HOST_MANIFEST],
             "timeout_seconds": 180, "cpu_quota_percent": 25, "memory_max_bytes": 268435456, "nice": 10,
             "idempotency_key": "pocket4-combined07-host3793-check-" + nonce(config)}
    return {"host-candidate-inputs.json": value, "host-check-request.json": check,
            "host-run-request.json": request,
            "remote-inputs.json": {"files": [{"path": path, "sha256": digest, "local_name": "host-candidate-inputs.json"}],
                                   "source_upload_or_remote_dispatch_performed": False}}


def host_result(config, binding):
    value = pinned(config["host_result"])
    expected = host_config(config, binding)
    need(config["host_result"]["path"] == expected["evidence"] + "/result.json" and
         value["inputs"] == {"path": input_root(config) + "/host-candidate-inputs.json", "sha256": sha(encoded(expected))},
         "actual host result belongs to another input or attempt")
    need(value["state"] == "PASS_FULL_HOST_SUITE" and value["arm"] == "candidate" and
         value["wrapper_manifest_sha256"] == HOST_MANIFEST and value["tests_complete"] is True and
         value["main_preserved"] is True and value["resources_complete"] is True and
         value["filter"] == "*" and value["repeat"] == 1 and value["sharding"] is False and
         value["automatic_retry"] is False, "new complete3793 host result is required")
    need(value["binding_before"] == value["binding_after"] and
         value["binding_before"]["source_receipt"] == binding["candidate_build_receipt"] and
         value["binding_before"]["engine"]["sha256"] == binding["engine"]["sha256"],
         "host result did not execute this exact artifact closure")
    old = read_reference("baseline-report.json")
    need(value["assessment"] == old["actual_execution"]["assessment"] and
         value["main_config"] == expected["main"] and value["cpu"] == expected["cpu"],
         "full registration/disabled/skipped/baseline environment differs")
    return remote_pin(config["host_result"])


def android_config(config, binding):
    value = read_reference("a04-android-inputs.json")
    allocation = config["android_allocation"]
    need(set(allocation) == {"host_uid", "subid_start"} and
         type(allocation["host_uid"]) is int and 2000 <= allocation["host_uid"] < 60000 and
         allocation["host_uid"] not in (2000, 2191, 2404) and
         type(allocation["subid_start"]) is int and allocation["subid_start"] >= 100000 and
         allocation["subid_start"] + 100000 < 2**32,
         "explicit new private UID/sub-ID proposal required; live R5 checks still decide availability")
    name = "p4-signal-combined07-" + nonce(config)[:16]
    value["attempt"] = {"name": name, "stage": "/opt/" + name, "data": "/var/lib/" + name,
                        "runtime": "/run/" + name, "user_runtime": "/run/user/1000/" + name,
                        "evidence": "/home/alex/work/pocket4-signal-canary-combined07-" + nonce(config)[:16], **allocation}
    value.update(binding)
    value.pop("source_observation_index_sha256", None)
    value["note"] = ("Fresh candidate07 combined-engine qualification using unchanged frozen R5 runtime. "
                     "All 3793 host registrations and the four original ARM64 cases are required. "
                     "The inherited signal-mask-r1 preparation arm is a historical schema label. "
                     "Metadata generation remains disabled; this does not qualify enabled metadata, ART, factory or whole apps. "
                     "Main activation/epoch/resource and whole owned hierarchy retirement checks remain unchanged.")
    return value


def replace_option_values(args, replacements):
    for key, value in replacements.items():
        set_option(args, key, value)


def android_prepare(config, binding):
    host = host_result(config, binding)
    value = android_config(config, binding)
    path = input_root(config) + "/android-inputs.json"
    digest = sha(encoded(value))
    request = read_reference("prepare-request.json")
    replace_option_values(request["args"], {"--inputs": path, "--inputs-sha256": digest,
                                          "--host-suite-receipt": host["path"], "--host-suite-sha256": host["sha256"]})
    request["idempotency_key"] = "pocket4-combined07-r5-prepare-" + nonce(config)
    check = copy.deepcopy(request)
    need(check["args"][4] == "prepare", "original preparation command shape changed")
    check["args"][4] = "check-inputs"
    check["idempotency_key"] = "pocket4-combined07-r5-input-check-" + nonce(config)
    return {"android-inputs.json": value, "android-input-check-request.json": check,
            "android-prepare-request.json": request,
            "remote-inputs.json": {"files": [{"path": path, "sha256": digest, "local_name": "android-inputs.json"}],
                                   "source_upload_or_remote_dispatch_performed": False}}


def original_runtime_argv(source):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "argv":
            need(isinstance(node.value, ast.Call) and len(node.value.args) == 1, "original argv assignment shape changed")
            return parse(ast.literal_eval(node.value.args[0]))
    raise RuntimeError("original controller argv was not found")


def replace_required(source, old, new):
    need(old in source, "original request replacement target absent: " + old)
    return source.replace(old, new)


def android_runtime(config, binding, final):
    host = host_result(config, binding)
    value = android_config(config, binding)
    inputs_path = input_root(config) + "/android-inputs.json"
    inputs_sha = sha(encoded(value))
    prepared = pinned(config["prepared"])
    evidence = value["attempt"]["evidence"]
    need(config["prepared"]["path"] == evidence + "/prepared.json" and
         prepared["input_path"] == inputs_path and prepared["input_sha256"] == inputs_sha and
         prepared["engine_sha256"] == binding["engine"]["sha256"] and
         prepared["services_started"] is False and prepared["fresh_empty_data_images"] is True and
         prepared["old_userdata_read"] is False and prepared["production_ready"] is False and
         prepared["name"] == value["attempt"]["name"], "actual private preparation is missing or mismatched")
    for key in ("stage", "data", "runtime", "user_runtime", "evidence"):
        need(prepared[key] == value["attempt"][key], "prepared private path differs")
    need(set(prepared["nonces"]) == {"r2-svc", "r2-smc-handler", "r2-smc-default", "r3-smc-mask-edit"},
         "four-case preparation nonce set differs")
    check = read_reference("runtime-check-request.json")
    replace_option_values(check["args"], {"--inputs": inputs_path, "--inputs-sha256": inputs_sha,
                                         "--host-suite-receipt": host["path"], "--host-suite-sha256": host["sha256"],
                                         "--prepared-sha256": config["prepared"]["sha256"]})
    check["idempotency_key"] = "pocket4-combined07-r5-runtime-check-" + nonce(config)
    request = read_reference("runtime-request.json")
    source = request["stdin"]
    replacements = {
        "p4-signal-mask-r1-20261104-a04": value["attempt"]["name"],
        "/home/alex/work/pocket4-signal-canary-mask-r1-20261104-a04": evidence,
        "/home/alex/work/pocket4-signal-mask-a04-inputs-01.json": inputs_path,
        "152cc16040fc50d6920800d0152e3efb324682f701ac4ef64fbc35951ab279a3": inputs_sha,
        "d334430df461e2011781307992a7ae60e84a8a6cc34e2a0f118f2ccf070f2aa8": config["prepared"]["sha256"],
        "/home/alex/work/pocket4-signal-host-candidate-r11-01-9d630262/result.json": host["path"],
        "b8c9b01588d1c2a13c80ba1afc5765fcf6656147d26e630a7c2cf74f4f482283": host["sha256"],
        "aefbacbc3c7544a6aae0ee8b1bcfe80e": nonce(config),
    }
    for old, new in replacements.items():
        source = replace_required(source, old, new)
    argv = original_runtime_argv(source)
    unit = value["attempt"]["name"] + "-controller-01.service"
    description = value["attempt"]["name"] + " " + nonce(config) + " controller-01"
    need("--unit=" + unit in argv and "--property=Description=" + description in argv and
         argv[argv.index(R5_SOURCE + "/run.py") + 1] == "run", "new controller argv is malformed")
    review_path = input_root(config) + "/root-runtime-review.json"
    review = {"schema": 1, "admitted": False, "main_deployment_admitted": False,
              "controller": {"unit": unit, "description": description, "argv": argv},
              "input_sha256": inputs_sha, "prepared_sha256": config["prepared"]["sha256"],
              "host_suite_sha256": host["sha256"], "engine_sha256": binding["engine"]["sha256"],
              "runtime_manifest_sha256": R5_MANIFEST,
              "scope": "Template only. Root must review the exact actual artifacts and set admission independently."}
    result = {"android-runtime-check-request.json": check, "root-runtime-review.template.json": review}
    if not final:
        return result
    actual_review = pinned(config["root_review"])
    need(config["root_review"]["path"] == review_path and actual_review["admitted"] is True and
         actual_review["main_deployment_admitted"] is False,
         "independent exact root runtime admission is required")
    for key in ("controller", "input_sha256", "prepared_sha256", "host_suite_sha256", "engine_sha256", "runtime_manifest_sha256"):
        need(actual_review[key] == review[key], "root review differs from the exact runtime plan: " + key)
    source = replace_required(source, "/home/alex/work/pocket4-root-signal-a04-runtime-review-01.json", review_path)
    source = replace_required(source, "bc15226017249f1a275f5dfe761f8e5436187e13206566ad2786a5fa81097051", config["root_review"]["sha256"])
    ast.parse(source)
    request["stdin"] = source
    request["idempotency_key"] = "pocket4-combined07-r5-four-signal-once-" + nonce(config)
    result["android-runtime-request.json"] = request
    return result


def write_outputs(directory, outputs, binding_sha, phase):
    directory = Path(directory)
    need(directory.is_absolute() and not directory.exists() and not directory.is_symlink(), "new local output required")
    # No remote functions, imported runner, subprocess, or tool calls exist here.
    values = {name: encoded(value) for name, value in outputs.items()}
    directory.mkdir(mode=0o700)
    pins = {}
    for name, raw in values.items():
        with (directory / name).open("xb") as stream:
            stream.write(raw)
        pins[name] = {"bytes": len(raw), "sha256": sha(raw)}
    result = {"schema": 1, "state": "LOCAL_REQUESTS_BOUND_NOT_DISPATCHED", "phase": phase,
              "binding_sha256": binding_sha, "files": pins, "source_upload_performed": False,
              "tests_executed": False, "Android_executed": False, "Main_actions": 0, "production_ready": False}
    with (directory / "GENERATED_PINS.json").open("xb") as stream:
        stream.write(encoded(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", nargs="?", choices=("plan", "host", "android-prepare", "android-check", "android-runtime"), default="plan")
    parser.add_argument("--binding")
    parser.add_argument("--binding-sha256")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.phase == "plan":
        print(json.dumps({"state": "PLAN_ONLY", "registered": 3793, "executed": 3791, "completed": 3788,
                          "disabled": 2, "original_skips": 3,
                          "four_cases": ["r2-svc", "r2-smc-handler", "r2-smc-default", "r3-smc-mask-edit"],
                          "fresh_actual_build_required": True, "unchanged_execution_sources": True,
                          "remote_requests_dispatched": 0, "tests_executed": False, "Main_actions": 0}))
        return
    need(args.binding and args.binding_sha256 and args.out, "explicit binding/hash/new output required")
    raw = Path(args.binding).read_bytes()
    need(sha(raw) == args.binding_sha256, "binding changed")
    config = parse(raw)
    need(config["schema"] == 1, "unsupported binding")
    binding = build_binding(config)
    if args.phase == "host":
        outputs = host_requests(config, binding)
    elif args.phase == "android-prepare":
        outputs = android_prepare(config, binding)
    else:
        outputs = android_runtime(config, binding, args.phase == "android-runtime")
    print(json.dumps(write_outputs(args.out, outputs, sha(raw), args.phase)))


if __name__ == "__main__":
    main()
