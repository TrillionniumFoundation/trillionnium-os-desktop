#!/usr/bin/env python3
"""Derive a fresh engine-only profile from the pinned Go6R2 controller."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE / "references"
COMPILE_ROOT = "/home/alex/work/pocket4-blueprint-streaming-builder-450-compile-03-20261105"
ROOT = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-go6-streaming-01"
COMPILE_SHA = "a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de"
BUILDER_SHA = "ea80146d5fc47f9927dd16a1ad91b6b48f0b30f0ce043d4eaef53f0e84f482b6"
MANIFEST_SHA = "6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4"
BLUEPRINT_PATCH = "android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch"
BLUEPRINT_SHA = "9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307"
BLUEPRINT_SOURCE_SHA = "1559969a55db1b682401c01264dd8ba96fa224781c3af277f0996a5050f7c9fa"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write(name, text):
    raw = text.encode() if isinstance(text, str) else text
    with (HERE / name).open("xb") as stream:
        stream.write(raw)
    return {"bytes": len(raw), "sha256": sha(raw)}

def replace(source, old, new, count=1):
    assert source.count(old) == count, old[:100]
    return source.replace(old, new)

def replace_function(source, name, body):
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    lines = source.splitlines(True)
    return "".join(lines[:node.lineno-1]) + body + "\n" + "".join(lines[node.end_lineno:])

source = (REF / "0-combined_build_go6r2.py").read_text()
assert sha(source.encode()) == "714a9de0ac3615ff8a8439f6d808f1ea3e57bd13dad05f3e3cc1565281719a37"
original = source
source = replace(source, '"""Independent candidate05 Go6/11GiB second profile. Default: plan; no automatic retry."""',
                 '"""Candidate05 cold engine build with the actual qualified streaming builder. Default: plan."""')
source = replace(source, 'BUILDER_ORIGIN = P("/home/alex/work/pocket4-signal-mask-r11-build-memory-01/builder-source")',
                 'BUILDER_ORIGIN = P(' + repr(COMPILE_ROOT + "/builder-source") + ')')
source = replace(source, 'BUILDER_MANIFEST = BUILDER_ORIGIN.parent / "builder-source-after.json"',
                 'BUILDER_MANIFEST = BUILDER_ORIGIN.parent / "attempt01/copied-builder-source-manifest.json"')
source = replace(source, 'BUILDER_MANIFEST_SHA = "e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017"',
                 'BUILDER_MANIFEST_SHA = ' + repr(MANIFEST_SHA))
source = replace(source, 'BUILDER = P("/home/alex/work/pocket4-signal-semantics-r15-20261104/cargo-target/debug/droidloom-update")',
                 'BUILDER = P(' + repr(COMPILE_ROOT + "/attempt01/cargo-target/debug/droidloom-update") + ')')
source = replace(source, 'BUILDER_SHA = "16df26d88391c22c9f076917531f022907ec5608bd31e58e05c898605db9dcc4"',
                 'BUILDER_SHA = ' + repr(BUILDER_SHA) + '\n'
                 'BUILDER_COMPILE_RESULT = BUILDER_ORIGIN.parent / "attempt01/result.json"\n'
                 'BUILDER_COMPILE_SHA = ' + repr(COMPILE_SHA) + '\n'
                 'BUILDER_CONTROL_SHA = "993f59e310f6da3a48c2cd5c1042c94d183cbc886ed795627c4e3d9c025a2485"\n'
                 'BLUEPRINT_PATCH = ' + repr(BLUEPRINT_PATCH) + '\n'
                 'BLUEPRINT_PATCH_SHA = ' + repr(BLUEPRINT_SHA) + '\n'
                 'BLUEPRINT_SOURCE = "build/blueprint/context.go"\n'
                 'BLUEPRINT_SOURCE_SHA = ' + repr(BLUEPRINT_SOURCE_SHA))
source = replace(source, 'ROOT = OWNER / "full-build-combined05-go6-02"',
                 'ROOT = OWNER / "full-build-combined05-go6-streaming-01"')
source = replace(source, 'less than 14 GiB MemAvailable for independent Go6 second profile; no automatic retry',
                 'less than 14 GiB MemAvailable for fresh Go6 streaming profile; no automatic retry')

builder_contract = '''def builder_compilation_contract():
    require(digest(BUILDER_COMPILE_RESULT) == BUILDER_COMPILE_SHA,
            "actual matching builder compile receipt changed")
    require(digest(BUILDER_ORIGIN.parent / "control-source/compile_builder.py") == BUILDER_CONTROL_SHA,
            "actual matching compiler controller changed")
    compiled = json.loads(BUILDER_COMPILE_RESULT.read_bytes())
    tests = [
        "android::tests::repeated_projection_keeps_ninja_outputs_until_content_changes",
        "android::tests::restoration_preserves_original_and_removes_created_file",
        "android::patch_tests::native_engine_effective_projection_records_final_bytes_and_applied_patch",
        "android::patch_tests::patch_in_source_without_git_root_is_restored_inside_enclosing_checkout",
        "android::patch_tests::interrupted_projection_recovers_before_next_build",
        "tests::native_engine_cli_requires_prepared_workspace_and_has_no_arbitrary_targets",
        "tests::native_engine_output_selector_keeps_default_or_exact_explicit_directory",
    ]
    require(compiled["state"] == "PASS" and compiled["expected_test_names"] == tests and
            compiled["focused_tests_passed"] == 7 and len(compiled["commands"]) == 26 and
            all(row["returncode"] == 0 and not row["timed_out"] for row in compiled["commands"]),
            "actual builder compilation and original seven tests are not qualified")
    require(compiled["original_source_unchanged_after"] is True and
            compiled["copied_source_unchanged_after"] is True and
            compiled["cargo_configs_unchanged_after"] is True and
            not compiled["dependency_changes"] and not compiled["tool_changes"] and
            not compiled["observed_signals"], "actual builder inputs changed")
    cleanup = compiled["cleanup"]
    require(not cleanup["forced_cleanup"] and not cleanup["remaining"] and not cleanup["errors"] and
            compiled["owned_resource_gate"]["pass"] is True and
            all(compiled["owned_resource_gate"]["memory_events_delta"][key] == 0
                for key in ("oom", "oom_kill", "oom_group_kill")),
            "actual builder retirement or OOM qualification failed")
    require(compiled["copied_manifest"]["path"] == str(BUILDER_MANIFEST) and
            compiled["copied_manifest"]["sha256"] == BUILDER_MANIFEST_SHA and
            compiled["source_delta"] == {
                "Go6_patch_changed": False, "added": [BLUEPRINT_PATCH],
                "changed_existing": ["tools/droidloom-update/src/android.rs"],
                "engine_source_files_changed": 0, "unchanged_existing": 448},
            "actual builder source delta differs")
    require(compiled["actual_Go_comparison_gate"]["sha256"] ==
            "391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674" and
            compiled["actual_registry_archive_authority"]["sha256"] ==
            "b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993",
            "actual writer or locked-registry source qualification differs")
    elf = compiled["builder_elf"]
    require(elf["path"] == str(BUILDER) and elf["sha256"] == BUILDER_SHA and
            elf["bytes"] == 32081288 and regular(BUILDER).st_size == elf["bytes"] and
            digest(BUILDER) == BUILDER_SHA, "actual matching builder ELF changed")
    return {"receipt_sha256": BUILDER_COMPILE_SHA, "builder_sha256": BUILDER_SHA,
            "source_manifest_sha256": BUILDER_MANIFEST_SHA, "focused_tests_passed": 7,
            "upstream_vet_pass_claimed": False,
            "builder_compile_memory_max_events": compiled["owned_resource_gate"]["memory_events_delta"]["max"]}
'''
source = replace(source, 'def source_contract():\n    matched_gate_contract()',
                 builder_contract + '\n\ndef source_contract():\n    builder_compilation_contract()\n    matched_gate_contract()')
projection = '''def go_projection_contract(inputs, reference):
    # The normal builder must recover the old journal and apply exactly one new
    # Blueprint patch. The Go6 patch and all prior patch hashes stay unchanged.
    old = reference["effective_projection"]
    actual = inputs["effective_projection"]
    require(old["patches"][GO_PATCH] == GO_PATCH_SHA and BLUEPRINT_PATCH not in old["patches"],
            "prior successful projection does not match the fixed preimage")
    expected = dict(old["patches"])
    expected[BLUEPRINT_PATCH] = BLUEPRINT_PATCH_SHA
    require(actual["patches"] == expected,
            "actual normal projection did not apply exactly the streaming delta")
    projected_hash = actual["files"][SOONG_SOURCE]
    require(projected_hash == old["files"][SOONG_SOURCE],
            "actual projected Soong source differs from the successful Go6 builder")
    require(actual["files"][BLUEPRINT_SOURCE] == BLUEPRINT_SOURCE_SHA,
            "actual projected Blueprint writer differs from the tested candidate")
    return {"patch_path": GO_PATCH, "patch_sha256": GO_PATCH_SHA,
            "projected_soong_path": SOONG_SOURCE, "projected_soong_sha256": projected_hash,
            "actual_prior_success_projected_hash_equal": True,
            "unchanged_prior_patch_hashes": True, "one_new_patch": BLUEPRINT_PATCH,
            "new_patch_sha256": BLUEPRINT_PATCH_SHA,
            "projected_blueprint_path": BLUEPRINT_SOURCE,
            "projected_blueprint_sha256": BLUEPRINT_SOURCE_SHA,
            "normal_builder_lock_and_journal_recovery_required": True}
'''
source = replace_function(source, "go_projection_contract", projection)
source = replace(source, 'require(len(builder_files) == 449 and inventory(BUILDER_ORIGIN) == builder_files,',
                 'require(len(builder_files) == 450 and inventory(BUILDER_ORIGIN) == builder_files,')
source = replace(source, 'digest(BUILDER_ORIGIN / GO_PATCH) == GO_PATCH_SHA, "original Go6 patch changed")',
                 'digest(BUILDER_ORIGIN / GO_PATCH) == GO_PATCH_SHA, "original Go6 patch changed")\n'
                 '    require(builder_files[BLUEPRINT_PATCH]["sha256"] == BLUEPRINT_PATCH_SHA and\n'
                 '            builder_files[BLUEPRINT_PATCH]["bytes"] == 470 and\n'
                 '            digest(BUILDER_ORIGIN / BLUEPRINT_PATCH) == BLUEPRINT_PATCH_SHA,\n'
                 '            "tested Blueprint streaming patch changed")')
source = replace(source, '"physical_reservation_claimed": False, "builder_source_delta": None,',
                 '"physical_reservation_claimed": False,\n'
                 '            "builder_source_delta": {"changed_existing": ["tools/droidloom-update/src/android.rs"],\n'
                 '                                     "added": [BLUEPRINT_PATCH], "unchanged_existing": 448},\n'
                 '            "builder_source_files": 450, "actual_builder_compile_sha256": BUILDER_COMPILE_SHA,\n'
                 '            "Blueprint_streaming_patch_sha256": BLUEPRINT_PATCH_SHA,')
source = replace(source, '"builder_manifest_sha256": BUILDER_MANIFEST_SHA, "builder_sha256": BUILDER_SHA,',
                 '"builder_manifest_sha256": BUILDER_MANIFEST_SHA, "builder_sha256": BUILDER_SHA,\n'
                 '                   "actual_builder_compile_sha256": BUILDER_COMPILE_SHA,\n'
                 '                   "Blueprint_streaming_patch_sha256": BLUEPRINT_PATCH_SHA,')
source = replace(source, 'receipt["engine_files"] == engine and receipt["builder_manifest_sha256"] == BUILDER_MANIFEST_SHA,',
                 'receipt["engine_files"] == engine and receipt["builder_manifest_sha256"] == BUILDER_MANIFEST_SHA and\n'
                 '            receipt["builder_sha256"] == BUILDER_SHA and\n'
                 '            receipt["actual_builder_compile_sha256"] == BUILDER_COMPILE_SHA and\n'
                 '            receipt["Blueprint_streaming_patch_sha256"] == BLUEPRINT_PATCH_SHA,')
source = replace(source, 'STARTING_COMBINED05_GO6R2_FLAG0_FULL_BUILD',
                 'STARTING_COMBINED05_GO6_STREAMING_FLAG0_COLD_BUILD')
ast.parse(source)
controller_pin = write("combined_build_streaming.py", source)
write("controller-go6r2-to-streaming.patch",
      "".join(difflib.unified_diff(original.splitlines(True), source.splitlines(True),
                                 fromfile="a/combined_build_go6r2.py", tofile="b/combined_build_streaming.py")))

fence = (REF / "1-fenced_build_go6r2.template.py").read_text()
old_fence = fence
assert sha(fence.encode()) == "810710021986054213546a6dfee65c29d3cd8eb86e4de8db11f2553cbc855b0f"
fence = replace(fence, "714a9de0ac3615ff8a8439f6d808f1ea3e57bd13dad05f3e3cc1565281719a37", controller_pin["sha256"])
fence = replace(fence, "full-build-combined05-go6-02", "full-build-combined05-go6-streaming-01")
fence = replace(fence, "ACTUAL_GO6R2_PREPARATION_SHA_REQUIRED", "ACTUAL_STREAMING_PREPARATION_SHA_REQUIRED")
fence = replace(fence, "a new actual Go6R2 preparation receipt is required", "a new actual streaming preparation receipt is required")
ast.parse(fence)
fence_pin = write("fenced_build_streaming.template.py", fence)
write("fence-go6r2-to-streaming.patch",
      "".join(difflib.unified_diff(old_fence.splitlines(True), fence.splitlines(True),
                                 fromfile="a/fenced_build_go6r2.template.py", tofile="b/fenced_build_streaming.template.py")))
snapshot = (REF / "3-main_snapshot.py").read_bytes()
assert sha(snapshot) == "f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb"
write("main_snapshot.py", snapshot)

generator = (REF / "2-make_requests.py").read_text()
old_generator = generator
assert sha(generator.encode()) == "74f47fee3f13ed109c308c5b2a98e9876e20fe56a8e55ef8c19b1df27b9f09b7"
generator = generator.replace("Go6R2", "Go6 streaming").replace("GO6R2", "STREAMING")
generator = generator.replace("combined_build_go6r2", "combined_build_streaming").replace("fenced_build_go6r2", "fenced_build_streaming")
generator = generator.replace("combined05-go6r2", "combined05-go6-streaming")
generator = replace(generator, "714a9de0ac3615ff8a8439f6d808f1ea3e57bd13dad05f3e3cc1565281719a37", controller_pin["sha256"])
generator = replace(generator, "810710021986054213546a6dfee65c29d3cd8eb86e4de8db11f2553cbc855b0f", fence_pin["sha256"])
generator = replace(generator, "e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017", MANIFEST_SHA)
generator = replace(generator, "full-build-combined05-go6-02", "full-build-combined05-go6-streaming-01")
generator = replace(generator, "pocket4-native-combined05-go6-full-source-preparation-02-20261104",
                    "pocket4-native-combined05-go6-streaming-full-source-preparation-01-20261105")
generator = replace(generator, "pocket4-native-combined05-go6-fenced-full-engine-flag0-build-02-20261104",
                    "pocket4-native-combined05-go6-streaming-fenced-cold-engine-flag0-build-01-20261105")
generator = replace(generator, 'len(builder) == 449', 'len(builder) == 450')
generator = replace(generator, 'actual 449-file manifest differs', 'actual 450-file manifest differs')
generator = replace(generator, 'preparation["plan"]["builder_source_delta"] is None, "builder source must be unchanged"',
                    'preparation["actual_builder_compile_sha256"] == ' + repr(COMPILE_SHA) + ' and\n'
                    '            preparation["builder_sha256"] == ' + repr(BUILDER_SHA) + ' and\n'
                    '            preparation["Blueprint_streaming_patch_sha256"] == ' + repr(BLUEPRINT_SHA) + ',\n'
                    '            "actual matching streaming builder or its compilation receipt differs"')
generator = replace(generator, '"base_builder_manifest_sha256": BASE_BUILDER_SHA, "STREAMING_patch_sha256": STREAMING_SHA,',
                    '"base_builder_manifest_sha256": BASE_BUILDER_SHA, "Go6_patch_sha256": STREAMING_SHA,\n'
                    '        "actual_builder_compile_sha256": ' + repr(COMPILE_SHA) + ',\n'
                    '        "Blueprint_streaming_patch_sha256": ' + repr(BLUEPRINT_SHA) + ',')
generator = replace(generator, '"candidate05_manifest_sha256": CANDIDATE_SHA, "STREAMING_patch_sha256": STREAMING_SHA,',
                    '"candidate05_manifest_sha256": CANDIDATE_SHA, "Go6_patch_sha256": STREAMING_SHA,\n'
                    '        "actual_builder_compile_sha256": ' + repr(COMPILE_SHA) + ',\n'
                    '        "Blueprint_streaming_patch_sha256": ' + repr(BLUEPRINT_SHA) + ',')
ast.parse(generator)
write("make_requests.py", generator)
write("request-generator-go6r2-to-streaming.patch",
      "".join(difflib.unified_diff(old_generator.splitlines(True), generator.splitlines(True),
                                 fromfile="a/make_requests_go6r2.py", tofile="b/make_requests_streaming.py")))

expected = (HERE.parent / "builder-streaming-compile-03/final-request-01/expected-builder-450-manifest.json").read_bytes()
assert sha(expected) == MANIFEST_SHA
write("expected-copied-builder-source-manifest.json", expected)
actual = Path("/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/builder450-compile03/result.json").read_bytes()
assert sha(actual) == COMPILE_SHA
write("actual-builder-compile03-result.json", actual)
print(json.dumps({"controller": controller_pin, "fence_template": fence_pin, "root": ROOT,
                  "actual_builder_sha256": BUILDER_SHA, "remote_actions": 0}, indent=2))
