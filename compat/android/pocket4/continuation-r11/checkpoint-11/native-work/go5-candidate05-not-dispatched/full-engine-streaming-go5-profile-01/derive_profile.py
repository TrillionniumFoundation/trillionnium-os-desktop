#!/usr/bin/env python3
"""Derive a new Go5 runtime-data profile without altering the compiled Go6 source."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'full-engine-streaming-profile-01'
GO = 'android/apex-compat/0008-soong-leaf-go-memory-budget.patch'
GO6 = '6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e'
GO5 = '39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f'
COMPILED = '6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4'
RUNTIME = '776435c88ca6ddb983456c639ca051e586731140394756f33abe53dc478357e3'
SOONG6 = 'ea5d759aa3d57c2bc9bce434746309ee988b3554923966a1fb78ec0ce3c18343'
SOONG5 = '4e6fb778c1aee7bfc9b3206940364edbf3502912fe692fa91b612ab389ed07d9'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)

def exact(source, before, after):
    if source.count(before) != 1:
        raise RuntimeError('derivation preimage count: ' + repr(before[:120]))
    return source.replace(before, after)

def function(source, name, replacement):
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    lines = source.splitlines(True)
    return ''.join(lines[:node.lineno - 1]) + replacement.rstrip() + '\n' + ''.join(lines[node.end_lineno:])

def diff(before, after, name):
    return ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                      fromfile='a/Go6/' + name, tofile='b/Go5/' + name))

def main():
    base = (BASE / 'combined_build_streaming.py').read_bytes()
    assert sha(base) == 'edf9f49f9aa5b404eb49c4dd848c998efffc4929f38137a698ec77c0d1f48fc9'
    manifest_raw = (BASE / 'expected-copied-builder-source-manifest.json').read_bytes()
    assert sha(manifest_raw) == COMPILED
    compiled = json.loads(manifest_raw)
    assert len(compiled) == 450 and compiled[GO]['sha256'] == GO6 and compiled[GO]['bytes'] == 583
    runtime = {name: dict(row) for name, row in compiled.items()}
    runtime[GO]['sha256'] = GO5
    runtime_raw = (json.dumps(runtime, indent=2) + '\n').encode()
    assert sha(runtime_raw) == RUNTIME
    before = (HERE / 'references/0008-soong-go6.preimage.patch').read_bytes()
    after = (HERE / '0008-soong-leaf-go-memory-budget.patch').read_bytes()
    assert sha(before) == GO6 and sha(after) == GO5
    assert before.count(b'"6GiB"') == 1 and before.replace(b'"6GiB"', b'"5GiB"') == after
    soong = (HERE / 'references/actual-projected-soong-go6.go').read_bytes()
    assert sha(soong) == SOONG6
    leaf = b'invocationEnv["GOMEMLIMIT"] = "6GiB"'
    assert soong.count(leaf) == 1
    soong5 = soong.replace(leaf, leaf.replace(b'6GiB', b'5GiB'))
    assert sha(soong5) == SOONG5
    put('expected-runtime-builder-source-manifest.json', runtime_raw)
    put('references/compiled-builder-source-manifest.json', manifest_raw)
    put('references/combined_build_streaming_go6.py', base)
    put('expected-projected-soong-go5.go', soong5)
    for name in ('fenced_build_streaming.template.py', 'make_requests.py'):
        put('references/Go6-' + name, (BASE / name).read_bytes())
    put('main_snapshot.py', (BASE / 'main_snapshot.py').read_bytes())
    put('references/actual-builder-compile03-result.json', (BASE / 'actual-builder-compile03-result.json').read_bytes())

    source = base.decode()
    source = exact(source, '"""Candidate05 cold engine build with the actual qualified streaming builder. Default: plan."""',
                   '"""New Go5 runtime-data profile using the qualified Go6-compiled streaming builder. Default: plan."""')
    source = exact(source, 'full-build-combined05-go6-streaming-01', 'full-build-combined05-go5-streaming-01')
    source = exact(source, 'MEMORY_MAX = 11 * 1024**3', 'MEMORY_MAX = 10 * 1024**3')
    source = exact(source, 'MIN_AVAILABLE = 14 * 1024**3', 'MIN_AVAILABLE = 13 * 1024**3')
    source = exact(source, 'GO_PATCH_SHA = "' + GO6 + '"',
                   'GO_PATCH_SHA = "' + GO5 + '"\nCOMPILED_GO_PATCH_SHA = "' + GO6 +
                   '"\nRUNTIME_BUILDER_MANIFEST_SHA = "' + RUNTIME +
                   '"\nCOMPILED_SOONG_SOURCE_SHA = "' + SOONG6 +
                   '"\nRUNTIME_SOONG_SOURCE_SHA = "' + SOONG5 + '"')
    source = exact(source, 'less than 14 GiB MemAvailable for fresh Go6 streaming profile; no automatic retry',
                   'less than 13 GiB MemAvailable for fresh Go5 streaming profile; no automatic retry')
    source = function(source, 'go_projection_contract', '''def go_projection_contract(inputs, reference):
    # The original compiled source remains Go6. The copied runtime data changes
    # only the leaf budget; normal builder journal recovery applies both patches.
    old = reference["effective_projection"]
    actual = inputs["effective_projection"]
    require(old["patches"][GO_PATCH] == COMPILED_GO_PATCH_SHA and
            old["files"][SOONG_SOURCE] == COMPILED_SOONG_SOURCE_SHA and
            BLUEPRINT_PATCH not in old["patches"], "prior successful Go6 projection differs")
    expected = dict(old["patches"])
    expected[GO_PATCH] = GO_PATCH_SHA
    expected[BLUEPRINT_PATCH] = BLUEPRINT_PATCH_SHA
    require(actual["patches"] == expected,
            "actual normal projection did not apply exactly Go5 plus the streaming delta")
    require(actual["files"][SOONG_SOURCE] == RUNTIME_SOONG_SOURCE_SHA,
            "actual projected Soong source differs from the exact one-byte Go5 expectation")
    require(actual["files"][BLUEPRINT_SOURCE] == BLUEPRINT_SOURCE_SHA,
            "actual projected Blueprint writer differs from the tested candidate")
    return {"patch_path": GO_PATCH, "patch_sha256": GO_PATCH_SHA,
            "compiled_preimage_patch_sha256": COMPILED_GO_PATCH_SHA,
            "projected_soong_path": SOONG_SOURCE,
            "projected_soong_sha256": RUNTIME_SOONG_SOURCE_SHA,
            "compiled_preimage_projected_soong_sha256": COMPILED_SOONG_SOURCE_SHA,
            "one_prior_patch_changed": GO_PATCH, "all_other_prior_patch_hashes_unchanged": True,
            "one_new_patch": BLUEPRINT_PATCH, "new_patch_sha256": BLUEPRINT_PATCH_SHA,
            "projected_blueprint_path": BLUEPRINT_SOURCE,
            "projected_blueprint_sha256": BLUEPRINT_SOURCE_SHA,
            "normal_builder_lock_and_journal_recovery_required": True}''')
    source = exact(source, 'require(builder_files[GO_PATCH]["sha256"] == GO_PATCH_SHA and\n            builder_files[GO_PATCH]["bytes"] == 583 and\n            digest(BUILDER_ORIGIN / GO_PATCH) == GO_PATCH_SHA, "original Go6 patch changed")',
                   'require(builder_files[GO_PATCH]["sha256"] == COMPILED_GO_PATCH_SHA and\n            builder_files[GO_PATCH]["bytes"] == 583 and\n            digest(BUILDER_ORIGIN / GO_PATCH) == COMPILED_GO_PATCH_SHA, "original compiled Go6 patch changed")')
    helpers = '''def runtime_builder_manifest(compiled):
    require(len(compiled) == 450 and compiled[GO_PATCH]["kind"] == "file" and
            compiled[GO_PATCH]["sha256"] == COMPILED_GO_PATCH_SHA and
            compiled[GO_PATCH]["bytes"] == 583, "compiled runtime-data preimage differs")
    expected = {name: dict(row) for name, row in compiled.items()}
    expected[GO_PATCH]["sha256"] = GO_PATCH_SHA
    raw = (json.dumps(expected, indent=2) + "\\n").encode()
    require(hashlib.sha256(raw).hexdigest() == RUNTIME_BUILDER_MANIFEST_SHA,
            "derived runtime 450-file manifest differs")
    return expected


def write_runtime_budget_patch():
    # This is a private copy owned by the new preparation, never live AOSP or
    # the original compiled source. Keep its length, inode and mode unchanged.
    path = BUILD_SOURCE / GO_PATCH
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    with os.fdopen(fd, "r+b") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == 583,
                "copied runtime patch is not the exact regular preimage")
        raw = stream.read(584)
        require(hashlib.sha256(raw).hexdigest() == COMPILED_GO_PATCH_SHA and
                raw.count(b'"6GiB"') == 1, "copied Go6 patch changed before derivation")
        value = raw.replace(b'"6GiB"', b'"5GiB"')
        require(len(value) == len(raw) and hashlib.sha256(value).hexdigest() == GO_PATCH_SHA,
                "derived Go5 patch differs")
        stream.seek(0)
        require(stream.write(value) == len(value), "short runtime patch write")
        stream.flush()
        os.fsync(stream.fileno())
        after = os.fstat(stream.fileno())
        named = path.lstat()
        require((after.st_dev, after.st_ino, after.st_mode, after.st_size) ==
                (before.st_dev, before.st_ino, before.st_mode, before.st_size) and
                (named.st_dev, named.st_ino) == (after.st_dev, after.st_ino),
                "runtime patch identity changed")
    require(digest(path) == GO_PATCH_SHA, "written runtime patch differs")


'''
    source = exact(source, 'def plan():\n', helpers + 'def plan():\n')
    source = exact(source, '"builder_source_delta": {"changed_existing": ["tools/droidloom-update/src/android.rs"],\n                                     "added": [BLUEPRINT_PATCH], "unchanged_existing": 448},',
                   '"compiled_builder_source_delta": {"changed_existing": ["tools/droidloom-update/src/android.rs"],\n                                              "added": [BLUEPRINT_PATCH], "unchanged_existing": 448},\n            "runtime_data_delta": {"changed": [GO_PATCH], "changed_bytes": 1,\n                                   "other_449_files_unchanged": True, "Rust_recompiled": False},\n            "compiled_builder_manifest_sha256": BUILDER_MANIFEST_SHA,\n            "expected_runtime_builder_manifest_sha256": RUNTIME_BUILDER_MANIFEST_SHA,')
    source = exact(source, '"Go_soft_heap": "6GiB"', '"Go_soft_heap": "5GiB"')
    source = exact(source, 'require(inventory(BUILD_SOURCE) == builder_files, "copied builder differs")',
                   'require(inventory(BUILD_SOURCE) == builder_files, "copied compiled builder differs")\n        runtime_files = runtime_builder_manifest(builder_files)\n        write_runtime_budget_patch()\n        require(inventory(BUILD_SOURCE) == runtime_files, "runtime source is not the sole Go5 data delta")')
    source = exact(source, 'save(ROOT / "copied-builder-source-manifest.json", builder_files)',
                   'save(ROOT / "copied-builder-source-manifest.json", runtime_files)\n        require(digest(ROOT / "copied-builder-source-manifest.json") == RUNTIME_BUILDER_MANIFEST_SHA,\n                "saved runtime 450-file manifest differs")')
    source = exact(source, '"builder_manifest_sha256": BUILDER_MANIFEST_SHA, "builder_sha256": BUILDER_SHA,',
                   '"builder_manifest_sha256": RUNTIME_BUILDER_MANIFEST_SHA, "builder_sha256": BUILDER_SHA,\n                   "compiled_builder_manifest_sha256": BUILDER_MANIFEST_SHA,\n                   "runtime_data_patch_sha256": GO_PATCH_SHA,\n                   "compiled_preimage_patch_sha256": COMPILED_GO_PATCH_SHA,\n                   "runtime_data_changed_files": [GO_PATCH], "Rust_recompiled": False,')
    source = exact(source, 'require(receipt["engine_files"] == engine and receipt["builder_manifest_sha256"] == BUILDER_MANIFEST_SHA and',
                   'runtime_files = runtime_builder_manifest(builder_files)\n    require(receipt["engine_files"] == engine and\n            receipt["builder_manifest_sha256"] == RUNTIME_BUILDER_MANIFEST_SHA and\n            receipt["compiled_builder_manifest_sha256"] == BUILDER_MANIFEST_SHA and\n            receipt["runtime_data_patch_sha256"] == GO_PATCH_SHA and\n            receipt["compiled_preimage_patch_sha256"] == COMPILED_GO_PATCH_SHA and\n            receipt["runtime_data_changed_files"] == [GO_PATCH] and receipt["Rust_recompiled"] is False and')
    source = exact(source, 'require(inventory(BUILD_SOURCE) == builder_files, "copied builder source changed")',
                   'require(digest(ROOT / "copied-builder-source-manifest.json") == RUNTIME_BUILDER_MANIFEST_SHA and\n            json.loads((ROOT / "copied-builder-source-manifest.json").read_bytes()) == runtime_files and\n            inventory(BUILD_SOURCE) == runtime_files, "copied runtime builder source changed")')
    source = exact(source, 'return receipt, files, engine, builder_files, baseline, effective',
                   'return receipt, files, engine, runtime_files, baseline, effective')
    source = exact(source, 'STARTING_COMBINED05_GO6_STREAMING_FLAG0_COLD_BUILD',
                   'STARTING_COMBINED05_GO5_STREAMING_FLAG0_COLD_BUILD')
    ast.parse(source)
    put('combined_build_streaming.py', source.encode())
    put('controller-Go6-to-Go5.patch', diff(base.decode(), source, 'combined_build_streaming.py').encode())
    csha = sha(source.encode())

    old_fence = (BASE / 'fenced_build_streaming.template.py').read_text()
    fence = old_fence.replace('edf9f49f9aa5b404eb49c4dd848c998efffc4929f38137a698ec77c0d1f48fc9', csha)
    fence = exact(fence, 'full-build-combined05-go6-streaming-01', 'full-build-combined05-go5-streaming-01')
    fence = exact(fence, 'ACTUAL_STREAMING_PREPARATION_SHA_REQUIRED', 'ACTUAL_GO5_STREAMING_PREPARATION_SHA_REQUIRED')
    put('fenced_build_streaming.template.py', fence.encode())
    put('fence-Go6-to-Go5.patch', diff(old_fence, fence, 'fenced_build_streaming.template.py').encode())

    old_make = (BASE / 'make_requests.py').read_text()
    make = old_make.replace('Go6 streaming requests', 'Go5 streaming requests')
    make = make.replace('edf9f49f9aa5b404eb49c4dd848c998efffc4929f38137a698ec77c0d1f48fc9', csha)
    make = make.replace('e23ab62e00ad07e9cf6503d9f06396df454f6e088f4eb733f9a9e9f3817e86e4', sha(fence.encode()))
    make = exact(make, 'STREAMING_SHA = "' + GO6 + '"',
                 'STREAMING_SHA = "' + GO5 + '"\nRUNTIME_BUILDER_SHA = "' + RUNTIME + '"')
    make = make.replace('combined05-go6-streaming', 'combined05-go5-streaming')
    make = make.replace('ACTUAL_STREAMING_PREPARATION_SHA_REQUIRED', 'ACTUAL_GO5_STREAMING_PREPARATION_SHA_REQUIRED')
    make = make.replace('Go6 streaming preparation', 'Go5 streaming preparation')
    make = make.replace('unchanged Go6 patch', 'derived Go5 runtime patch')
    make = make.replace('"Go6_patch_sha256": STREAMING_SHA', '"Go5_runtime_patch_sha256": STREAMING_SHA')
    make = exact(make, 'preparation["builder_manifest_sha256"] == BASE_BUILDER_SHA == sha(builder_manifest_raw),',
                 'preparation["builder_manifest_sha256"] == RUNTIME_BUILDER_SHA == sha(builder_manifest_raw) and\n            preparation["compiled_builder_manifest_sha256"] == BASE_BUILDER_SHA and\n            preparation["runtime_data_patch_sha256"] == STREAMING_SHA and\n            preparation["compiled_preimage_patch_sha256"] == "' + GO6 + '" and\n            preparation["runtime_data_changed_files"] == [GO_PATCH] and preparation["Rust_recompiled"] is False,')
    make = exact(make, 'HERE / "expected-copied-builder-source-manifest.json",\n                                               BASE_BUILDER_SHA',
                 'HERE / "expected-runtime-builder-source-manifest.json",\n                                               RUNTIME_BUILDER_SHA')
    make = exact(make, '"new_actual_builder_manifest_sha256": None, "actual_preparation_observed": False',
                 '"expected_runtime_builder_manifest_sha256": RUNTIME_BUILDER_SHA,\n        "new_actual_builder_manifest_sha256": None, "actual_preparation_observed": False')
    make = make.replace('11811160064', '10737418240').replace('15032385536', '13958643712')
    ast.parse(make)
    put('make_requests.py', make.encode())
    put('request-generator-Go6-to-Go5.patch', diff(old_make, make, 'make_requests.py').encode())
    put('runtime-budget-data.patch', diff(before.decode(), after.decode(), GO).encode())
    print(json.dumps({'state': 'LOCAL_DERIVATION_ONLY', 'controller_sha256': csha,
                      'fence_template_sha256': sha(fence.encode()), 'generator_sha256': sha(make.encode()),
                      'compiled_manifest_sha256': COMPILED, 'expected_runtime_manifest_sha256': RUNTIME,
                      'original_source_modified': False, 'remote_actions': 0}, indent=2))

if __name__ == '__main__':
    main()
