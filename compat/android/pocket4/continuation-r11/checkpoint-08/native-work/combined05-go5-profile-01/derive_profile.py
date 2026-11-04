#!/usr/bin/env python3
"""Derive the isolated Go5 profile from exact already reviewed source. Local only."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
CONTROLLER_SHA = "e56f06abdbda5aa95fe42e4ecf14d7f79f53e53821a8d5b1d43d0dce0776c655"
FENCE_SHA = "befac6dc2351b6b0297c3c2352d32f659f37f09c4bdb1bed550e10b12b95c701"
SNAPSHOT_SHA = "f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb"
GO6_SHA = "6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e"
GO5_SHA = "39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f"
NEW_ROOT = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-go5-01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, wanted):
    raw = path.read_bytes()
    if sha(raw) != wanted:
        raise RuntimeError("source pin differs: " + str(path))
    return raw


def replace_one(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError("non-unique source anchor: " + repr(old))
    return source.replace(old, new, 1)


def put(name, raw):
    with (HERE / name).open("xb") as stream:
        stream.write(raw)


def derive():
    original_raw = pinned(BASE / "fullbuild05-prepare-01/combined_build05.py", CONTROLLER_SHA)
    original = original_raw.decode()
    fence_original = pinned(BASE / "fullbuild05-fenced-request-01/fenced_build05.py", FENCE_SHA).decode()
    snapshot = pinned(BASE / "fullbuild05-fenced-request-01/main_snapshot.py", SNAPSHOT_SHA)
    go6 = pinned(BASE / "combined05-go5-proposal-01/references/0008-soong-go6.preimage.patch", GO6_SHA)
    go5 = pinned(BASE / "combined05-go5-proposal-01/0008-soong-leaf-go-memory-budget.patch", GO5_SHA)
    assert len(go6) == len(go5) == 583
    assert sum(a != b for a, b in zip(go6, go5)) == 1
    assert go6.replace(b'"6GiB"', b'"5GiB"', 1) == go5
    text = replace_one(original,
        '"""Owned candidate05 preparation and normal full engine build. Default: plan."""',
        '"""Independent candidate05 Go5/10GiB profile. Default: plan; no automatic retry."""')
    text = replace_one(text, 'ROOT = OWNER / "full-build-combined05-01"',
                       'ROOT = OWNER / "full-build-combined05-go5-01"')
    text = replace_one(text, 'MEMORY_MAX = 11 * 1024**3', 'MEMORY_MAX = 10 * 1024**3')
    text = replace_one(text, 'MIN_AVAILABLE = 15 * 1024**3', 'MIN_AVAILABLE = 14 * 1024**3')
    constants = ('GO_PATCH = "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"\n'
                 'GO_PATCH_PREIMAGE_SHA = ' + repr(GO6_SHA) + '\n'
                 'GO_PATCH_SHA = ' + repr(GO5_SHA) + '\n'
                 'GO_PATCH_SOURCE = ' + repr(go5) + '\n'
                 'SOONG_SOURCE = "build/soong/ui/build/soong.go"\n')
    text = replace_one(text, 'FEATURE = "BERBERIS_PROCMAPS_RAW_METADATA_OWNER"\n',
                       constants + 'FEATURE = "BERBERIS_PROCMAPS_RAW_METADATA_OWNER"\n')
    functions = '''def go_builder_inventory(base):
    require(len(base) == 449, "base builder inventory is not the pinned 449-file set")
    row = base[GO_PATCH]
    require(row["kind"] == "file" and row["sha256"] == GO_PATCH_PREIMAGE_SHA and
            row["bytes"] == len(GO_PATCH_SOURCE) == 583,
            "base Go patch inventory changed")
    require(hashlib.sha256(GO_PATCH_SOURCE).hexdigest() == GO_PATCH_SHA and
            GO_PATCH_SOURCE.count(b'invocationEnv["GOMEMLIMIT"] = "5GiB"') == 1,
            "embedded Go5 patch changed")
    result = {name: dict(value) for name, value in base.items()}
    result[GO_PATCH]["sha256"] = GO_PATCH_SHA
    require([name for name in base if result[name] != base[name]] == [GO_PATCH],
            "unexpected builder inventory delta")
    return result


def write_owned_go_patch():
    # copytree produced a private ordinary file. Check the opened inode before
    # any write: neither a symlink nor a hardlink may redirect this mutation.
    path = BUILD_SOURCE / GO_PATCH
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                "copied Go patch is not a private regular inode")
        raw = os.pread(fd, 584, 0)
        require(len(raw) == 583 and hashlib.sha256(raw).hexdigest() == GO_PATCH_PREIMAGE_SHA,
                "copied Go patch preimage changed")
        require(raw.count(b'invocationEnv["GOMEMLIMIT"] = "6GiB"') == 1 and
                raw.replace(b'"6GiB"', b'"5GiB"', 1) == GO_PATCH_SOURCE and
                sum(a != b for a, b in zip(raw, GO_PATCH_SOURCE)) == 1,
                "Go patch is not exactly the one-byte budget change")
        require(os.pwrite(fd, GO_PATCH_SOURCE, 0) == len(GO_PATCH_SOURCE),
                "short write to owned Go patch")
        os.fsync(fd)
    finally:
        os.close(fd)


def go_projection_contract(inputs, reference):
    old = reference["effective_projection"]
    actual = inputs["effective_projection"]
    require(old["patches"][GO_PATCH] == GO_PATCH_PREIMAGE_SHA,
            "prior successful projection used a different Go patch")
    expected_patches = dict(old["patches"])
    expected_patches[GO_PATCH] = GO_PATCH_SHA
    require(actual["patches"] == expected_patches,
            "actual projection patch set differs beyond the one Go5 patch")
    projected_hash = actual["files"][SOONG_SOURCE]
    require(isinstance(projected_hash, str) and len(projected_hash) == 64 and
            all(c in "0123456789abcdef" for c in projected_hash) and
            projected_hash != old["files"][SOONG_SOURCE],
            "actual projected Soong file was not changed and pinned")
    return {"patch_path": GO_PATCH, "patch_sha256": GO_PATCH_SHA,
            "base_patch_sha256": GO_PATCH_PREIMAGE_SHA,
            "projected_soong_path": SOONG_SOURCE,
            "projected_soong_sha256": projected_hash,
            "projected_soong_precomputed_hash_comparison": False,
            "normal_builder_records_patch_after_successful_git_apply": True,
            "all_other_applied_patch_hashes_equal_reference": True}


def memory_admission(memory):
    require(MIN_AVAILABLE - MEMORY_MAX == 4 * 1024**3,
            "new profile must preserve the four-GiB admission difference")
    require(memory["MemAvailable"] >= MIN_AVAILABLE,
            "less than 14 GiB MemAvailable for independent Go5 profile; no automatic retry")
    require(memory["SwapFree"] >= SWAP_MAX,
            "less than the required 1 GiB free swap; no automatic lower-budget retry")


'''
    text = replace_one(text, 'def source_contract():\n', functions + 'def source_contract():\n')
    text = replace_one(text,
        '    require(len(builder_files) == 449 and inventory(BUILDER_ORIGIN) == builder_files,\n'
        '            "builder source changed")\n',
        '    require(len(builder_files) == 449 and inventory(BUILDER_ORIGIN) == builder_files,\n'
        '            "builder source changed")\n'
        '    go_builder_inventory(builder_files)\n'
        '    require(digest(BUILDER_ORIGIN / GO_PATCH) == GO_PATCH_PREIMAGE_SHA,\n'
        '            "original Go6 patch changed")\n')
    text = replace_one(text, '            "Go_soft_heap": "6GiB",\n',
        '            "Go_soft_heap": "5GiB", "profile": "independent-combined05-go5-01",\n'
        '            "builder_source_changed_files": [GO_PATCH], "Go_patch_sha256": GO_PATCH_SHA,\n'
        '            "base_builder_manifest_sha256": BUILDER_MANIFEST_SHA,\n'
        '            "admission_headroom_bytes": MIN_AVAILABLE - MEMORY_MAX,\n'
        '            "headroom_is_reserved": False,\n')
    text = replace_one(text,
        '        require(inventory(BUILD_SOURCE) == builder_files, "copied builder differs")\n',
        '        require(inventory(BUILD_SOURCE) == builder_files, "copied base builder differs")\n'
        '        builder_files = go_builder_inventory(builder_files)\n'
        '        write_owned_go_patch()\n'
        '        require(inventory(BUILD_SOURCE) == builder_files, "copied Go5 builder differs")\n')
    text = replace_one(text,
        '                   "builder_manifest_sha256": BUILDER_MANIFEST_SHA, "builder_sha256": BUILDER_SHA,\n',
        '                   "builder_manifest_sha256": digest(ROOT / "copied-builder-source-manifest.json"),\n'
        '                   "base_builder_manifest_sha256": BUILDER_MANIFEST_SHA, "builder_sha256": BUILDER_SHA,\n'
        '                   "builder_source_delta": {"path": GO_PATCH, "preimage_sha256": GO_PATCH_PREIMAGE_SHA,\n'
        '                                            "sha256": GO_PATCH_SHA, "bytes": 583, "changed_bytes": 1},\n')
    text = replace_one(text,
        '    require(receipt["engine_files"] == engine and receipt["builder_manifest_sha256"] == BUILDER_MANIFEST_SHA,\n'
        '            "prepared source contract differs")\n'
        '    require(inventory(BUILD_SOURCE) == builder_files, "copied builder source changed")\n',
        '    builder_files = go_builder_inventory(builder_files)\n'
        '    require(receipt["engine_files"] == engine and receipt["base_builder_manifest_sha256"] == BUILDER_MANIFEST_SHA and\n'
        '            receipt["builder_sha256"] == BUILDER_SHA and receipt["plan"] == plan(),\n'
        '            "prepared source or independent resource profile differs")\n'
        '    require(receipt["builder_source_delta"] == {"path": GO_PATCH, "preimage_sha256": GO_PATCH_PREIMAGE_SHA,\n'
        '                                                "sha256": GO_PATCH_SHA, "bytes": 583, "changed_bytes": 1},\n'
        '            "prepared builder delta differs")\n'
        '    copied_manifest = ROOT / "copied-builder-source-manifest.json"\n'
        '    require(digest(copied_manifest) == receipt["builder_manifest_sha256"] and\n'
        '            json.loads(copied_manifest.read_bytes()) == builder_files and\n'
        '            inventory(BUILD_SOURCE) == builder_files, "copied Go5 builder source or manifest changed")\n')
    text = replace_one(text,
        '    reference = reference_inputs()\n    for field in EXTERNAL_FIELDS:\n',
        '    reference = reference_inputs()\n'
        '    go_projection = go_projection_contract(inputs, reference)\n'
        '    for field in EXTERNAL_FIELDS:\n')
    text = replace_one(text,
        '            "private_entry_export_observed": True, "raw_source_files": len(engine),\n',
        '            "private_entry_export_observed": True, "Go5_projection": go_projection,\n'
        '            "raw_source_files": len(engine),\n')
    text = replace_one(text,
        '    require(memory["MemAvailable"] >= MIN_AVAILABLE, "less than 15 GiB MemAvailable; no automatic lower-budget retry")\n'
        '    require(memory["SwapFree"] >= SWAP_MAX, "less than the required 1 GiB free swap; no automatic lower-budget retry")\n',
        '    # This read occurs in this new invocation immediately before owned-unit\n'
        '    # verification and launch. No earlier diagnostic sample admits a build.\n'
        '    memory_admission(memory)\n')
    text = replace_one(text, '"STARTING_COMBINED05_FLAG0_FULL_BUILD"',
                       '"STARTING_COMBINED05_GO5_FLAG0_FULL_BUILD"')
    ast.parse(text)
    controller_raw = text.encode()
    fence = replace_one(fence_original, repr(CONTROLLER_SHA), repr(sha(controller_raw)))
    fence = replace_one(fence,
        "PREPARATION_SHA = 'bb6e0d92c8b0df36ca8ccf1f25dd4286491c09999fa9225ff9f15955e00cd9d0'",
        "PREPARATION_SHA = 'ACTUAL_GO5_PREPARATION_SHA_REQUIRED'")
    fence = replace_one(fence,
        '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-01',
        NEW_ROOT)
    fence = replace_one(fence, "FENCE_ROOT = ROOT / 'build-fences-03'",
                        "FENCE_ROOT = ROOT / 'build-fences-01'")
    fence = replace_one(fence, 'def run(packet):\n',
        'def run(packet):\n'
        '    require(len(PREPARATION_SHA) == 64 and all(c in "0123456789abcdef" for c in PREPARATION_SHA),\n'
        '            "a new actual Go5 preparation receipt is required")\n')
    ast.parse(fence)
    put('combined_build_go5.py', controller_raw)
    put('fenced_build_go5.template.py', fence.encode())
    put('main_snapshot.py', snapshot)
    put('0008-soong-leaf-go-memory-budget.patch', go5)
    put('controller05-to-go5.patch', ''.join(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
        fromfile='a/frozen-combined_build05.py', tofile='b/combined_build_go5.py')).encode())
    put('fence03-to-go5-template.patch', ''.join(difflib.unified_diff(fence_original.splitlines(True), fence.splitlines(True),
        fromfile='a/frozen-fenced_build05.py', tofile='b/fenced_build_go5.template.py')).encode())
    put('go6-to-go5.patch', ''.join(difflib.unified_diff(go6.decode().splitlines(True), go5.decode().splitlines(True),
        fromfile='a/android/apex-compat/0008-soong-leaf-go-memory-budget.patch',
        tofile='b/android/apex-compat/0008-soong-leaf-go-memory-budget.patch')).encode())
    print(json.dumps({'state': 'LOCAL_PROFILE_SOURCE_DERIVED', 'controller_sha256': sha(controller_raw),
                      'fence_template_sha256': sha(fence.encode()), 'Go5_patch_sha256': GO5_SHA,
                      'new_remote_root': NEW_ROOT, 'remote_actions': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-local', action='store_true')
    args = parser.parse_args()
    if args.write_local:
        derive()
    else:
        print(json.dumps({'state': 'PLAN_ONLY', 'output_dir': str(HERE), 'remote_actions': 0}))
