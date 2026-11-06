#!/usr/bin/env python3
"""Reconstruct actual generated source locally from a pinned recorded BINDING.

Only the frozen renderer functions are invoked. No source_contract is executed;
no guard, runtime, namespace, build, install, UI, network or subprocess is used.
A completed reconstruction is evidence of identical bytes, not new runtime QA.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
QA_ROOT = HERE.parent
ACTUAL = QA_ROOT/"actual/source-generation-r2/generated"
OUTPUT = QA_ROOT/"reconstructed/source-generation-r2"
CONTRACT_PIN = (20684, "0cbb8c79b494a529e7cb7fe0ce99eec444103ae7207a02a768dbc76d3bb3cbc3")
GENERATOR_PIN = (34825, "ec53b8444c068e58b0e8d9d8ae25321ed6dddbd7768f3b6a766a35fc1ed8f1ab")
CLOSURE_PIN = (5098, "ad32c98479cbb763c6c7728336f65a3e10dd1826de17ea43d0662599f7ce7436")
RECORDER_PIN = (1759, "646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4")
HELPER_PIN = (2431, "dfb9b6a483f1069847433152b9b2e8b0f1b2cdd571a1dbde3068fc9393ad62c4")
BINDING_SHA = "8f89f253350ba2fa7adce2296e36c66c9029ebd538f10870e44540feab74c980"
HELPER_PACKAGE = "org.droidloom.qa.successor.p8f89f253350ba2fa.r1"
BUILD_NAME = "pocket4-successor-qa-build-b34f158f88bbebf112840fd88df25d03"
STAT_FIELDS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
               "st_size", "st_mtime_ns", "st_ctime_ns")

class Rejection(RuntimeError):
    pass

def need(value, reason):
    if not value:
        raise Rejection(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()

def unique_object(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, "DUPLICATE_JSON_KEY")
        out[key] = value
    return out

def metadata(fd):
    observed = os.fstat(fd)
    return tuple(getattr(observed, key) for key in STAT_FIELDS)

def pinned_read(path, expected):
    fd = check = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = metadata(fd)
        need(stat.S_ISREG(before[2]) and before[5] == 1 and before[6] == expected[0],
             "PINNED_INPUT_FILE_TYPE_OR_SIZE")
        raw = bytearray()
        while len(raw) < expected[0]:
            part = os.read(fd, min(65536, expected[0] - len(raw)))
            need(part, "SHORT_PINNED_INPUT")
            raw.extend(part)
        need(not os.read(fd, 1) and metadata(fd) == before, "PINNED_INPUT_CHANGED_DURING_READ")
        check = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        need(metadata(check) == before, "PINNED_INPUT_PATH_CHANGED")
        need(sha(raw) == expected[1], "PINNED_INPUT_SHA_MISMATCH")
        return bytes(raw)
    finally:
        if check is not None:
            os.close(check)
        if fd is not None:
            os.close(fd)

def extract_binding(raw):
    """Use a literal AST and preserve integer values and dictionary order."""
    module = ast.parse(raw, filename="recorded_source_contract.py", mode="exec")
    hits = []
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "BINDING" for target in node.targets):
            need(len(node.targets) == 1 and isinstance(node.targets[0], ast.Name),
                 "SINGLE_BINDING_TARGET_REQUIRED")
            hits.append(node.value)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name) and node.target.id == "BINDING":
            raise Rejection("UNSUPPORTED_BINDING_ASSIGNMENT")
    need(len(hits) == 1, "EXACTLY_ONE_TOP_LEVEL_BINDING_LITERAL_REQUIRED")
    try:
        binding = ast.literal_eval(hits[0])
    except (ValueError, TypeError, SyntaxError) as error:
        raise Rejection("BINDING_IS_NOT_A_LITERAL") from error
    need(type(binding) is dict, "BINDING_DICTIONARY_REQUIRED")
    canonical(binding)  # validates JSON-representable values without a numeric round trip
    return binding

def valid_relative(name):
    need(type(name) is str and 0 < len(name) <= 256, "OUTPUT_PATH_BOUND")
    p = Path(name)
    need(not p.is_absolute() and str(p) == name and all(v not in ("", ".", "..") for v in name.split("/")),
         "OUTPUT_PATH_NOT_CANONICAL")
    return p

def verify_rendered_set(files, raw_manifest):
    manifest = json.loads(raw_manifest, object_pairs_hook=unique_object)
    need(type(manifest.get("files")) is dict and type(files) is dict,
         "MANIFEST_FILE_TABLE_REQUIRED")
    need(set(files) == set(manifest["files"]), "RENDERED_FILE_SET_MISMATCH")
    rows = []
    for name in sorted(files):
        valid_relative(name)
        need(type(files[name]) is str, "RENDERED_TEXT_REQUIRED")
        raw = files[name].encode("utf-8")
        actual = {"bytes": len(raw), "sha256": sha(raw)}
        need(manifest["files"][name] == actual, "RENDERED_FILE_PIN_MISMATCH:" + name)
        rows.append({"path": name, **actual})
    return rows

def reconstruct(contract_path):
    contract = pinned_read(contract_path, CONTRACT_PIN)
    recorder_raw = pinned_read(ACTUAL/"recorder/source-manifest.json", RECORDER_PIN)
    helper_raw = pinned_read(ACTUAL/"helper/SOURCE_PINS.json", HELPER_PIN)
    closure_raw = pinned_read(QA_ROOT/"GENERATOR_PINS.json", CLOSURE_PIN)
    generator_raw = pinned_read(QA_ROOT/"generate_successor_sources.py", GENERATOR_PIN)
    binding = extract_binding(contract)
    need(sha(canonical(binding)) == BINDING_SHA, "ACTUAL_BINDING_SHA_MISMATCH")
    closure = json.loads(closure_raw, object_pairs_hook=unique_object)
    need(len(closure["files"]) == 31 and
         closure["files"]["generate_successor_sources.py"] ==
         {"bytes": GENERATOR_PIN[0], "sha256": GENERATOR_PIN[1]}, "FROZEN_31_SOURCE_CLOSURE_REQUIRED")
    renderer = types.ModuleType("frozen_successor_renderer_local_reconstruction")
    renderer.__file__ = str(QA_ROOT/"generate_successor_sources.py")
    exec(compile(generator_raw, renderer.__file__, "exec"), renderer.__dict__)
    sources = renderer.reference_closure(CLOSURE_PIN[1])
    need(len(sources) == 31, "COMPLETE_RENDERER_CLOSURE_REQUIRED")
    host, rendered_recorder_manifest = renderer.render_host(sources, binding)
    need(rendered_recorder_manifest == recorder_raw, "ACTUAL_RECORDER_MANIFEST_BYTES_DIFFER")
    helper, rendered_helper_manifest, package = renderer.render_helper(
        sources, binding, RECORDER_PIN[1], BUILD_NAME)
    need(package == HELPER_PACKAGE, "ACTUAL_HELPER_PACKAGE_DIFFERS")
    need(rendered_helper_manifest == helper_raw, "ACTUAL_HELPER_MANIFEST_BYTES_DIFFER")
    recorder_rows = verify_rendered_set(host, recorder_raw)
    helper_rows = verify_rendered_set(helper, helper_raw)
    need(host["source_contract.py"].encode() == contract, "RECORDED_CONTRACT_NOT_REPRODUCED")
    need(len(host) == len(helper) == 13, "ACTUAL_GENERATED_CLOSURE_COUNT")
    # Re-read every frozen source through the original bounded reader. No remote
    # identity/qualification routine is called by reference_closure.
    need(renderer.reference_closure(CLOSURE_PIN[1]) == sources, "SOURCE_CLOSURE_CHANGED_DURING_RENDER")
    for path, pin in ((contract_path, CONTRACT_PIN),
                      (ACTUAL/"recorder/source-manifest.json", RECORDER_PIN),
                      (ACTUAL/"helper/SOURCE_PINS.json", HELPER_PIN),
                      (QA_ROOT/"GENERATOR_PINS.json", CLOSURE_PIN),
                      (QA_ROOT/"generate_successor_sources.py", GENERATOR_PIN)):
        pinned_read(path, pin)
    generated = {"recorder/"+name: text.encode() for name, text in host.items()}
    generated.update({"helper/"+name: text.encode() for name, text in helper.items()})
    generated["recorder/source-manifest.json"] = recorder_raw
    generated["helper/SOURCE_PINS.json"] = helper_raw
    report = {"schema": "pocket4-actual-source-byte-reconstruction-v1",
              "status": "ALL_ACTUAL_MANIFEST_BYTES_REPRODUCED_NOT_YET_SAVED",
              "method": "pinned recorded BINDING AST literal plus frozen deterministic render_host/render_helper",
              "binding_sha256": BINDING_SHA, "helper_package": package, "build_output_name": BUILD_NAME,
              "recorded_contract": {"local_input_path": str(contract_path), "bytes": CONTRACT_PIN[0],
                                    "sha256": CONTRACT_PIN[1]},
              "generator": {"bytes": GENERATOR_PIN[0], "sha256": GENERATOR_PIN[1]},
              "generator_manifest_sha256": CLOSURE_PIN[1], "generator_source_count": 31,
              "actual_recorder_manifest": {"bytes": RECORDER_PIN[0], "sha256": RECORDER_PIN[1]},
              "actual_helper_manifest": {"bytes": HELPER_PIN[0], "sha256": HELPER_PIN[1]},
              "recorder_files": recorder_rows, "helper_files": helper_rows,
              "reconstructed_source_file_count": 26, "original_manifest_file_count": 2,
              "direct_read_of_all_remote_generated_files": False,
              "generated_source_contract_equals_recorded_input": True,
              "integers_preserved_by_python_ast_literal_eval": True,
              "Main_reads_or_actions": 0, "subprocesses": 0, "network_requests": 0,
              "build_performed_here": False, "install_performed_here": False,
              "UI_actions": 0, "runtime_QA_claimed": False, "production_ready": False}
    return generated, report

def write_once(path, raw):
    fd = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, "WRITE_PROGRESS")
            view = view[count:]
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)
    pinned_read(path, (len(raw), sha(raw)))

def publish_once(generated, report):
    # Every generated byte has already matched the exact actual manifests.
    # The final receipt is written last; partial IO failure never publishes PASS.
    OUTPUT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    OUTPUT.mkdir(mode=0o700)
    for name, raw in sorted(generated.items()):
        path = OUTPUT/valid_relative(name)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_once(path, raw)
    for name, raw in sorted(generated.items()):
        pinned_read(OUTPUT/name, (len(raw), sha(raw)))
    final = dict(report, status="RECONSTRUCTED_SOURCE_SAVED_AND_READBACK_MATCHED_ACTUAL_MANIFESTS",
                 local_output=str(OUTPUT), publication_receipt="RECONSTRUCTION_RECEIPT.json")
    receipt = json.dumps(final, ensure_ascii=True, sort_keys=True, indent=2).encode() + b"\n"
    write_once(OUTPUT/"RECONSTRUCTION_RECEIPT.json", receipt)
    directory = os.open(OUTPUT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return final

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-contract", type=Path,
                        default=ACTUAL/"recorder/source_contract.py")
    parser.add_argument("--write-source-once", action="store_true")
    args = parser.parse_args()
    try:
        generated, result = reconstruct(args.source_contract)
        if args.write_source_once:
            result = publish_once(generated, result)
        else:
            result["status"] = "ALL_ACTUAL_MANIFEST_BYTES_REPRODUCED_VERIFY_ONLY"
            result["source_files_saved"] = False
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
        return 0
    except (OSError, Rejection, ValueError, SyntaxError) as error:
        print(json.dumps({"schema": "pocket4-actual-source-byte-reconstruction-v1",
                          "status": "RECONSTRUCTION_REJECTED_OR_INPUT_MISSING",
                          "error_type": type(error).__name__, "error": str(error),
                          "source_input": str(args.source_contract),
                          "runtime_QA_claimed": False, "production_ready": False,
                          "Main_reads_or_actions": 0, "subprocesses": 0, "network_requests": 0},
                         ensure_ascii=True, sort_keys=True, indent=2))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

