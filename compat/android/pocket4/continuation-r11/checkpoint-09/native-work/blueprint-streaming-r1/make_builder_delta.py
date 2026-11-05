#!/usr/bin/env python3
"""Create an isolated normal-projection delta; do not execute any builder."""
from pathlib import Path
import difflib
import hashlib
import json

HERE = Path(__file__).resolve().parent
ANDROID = 'tools/droidloom-update/src/android.rs'
PATCH = 'android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(path, data):
    if isinstance(data, str):
        data = data.encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    return {'path':str(path.relative_to(HERE)), 'bytes':len(data), 'sha256':sha(data)}

def main():
    raw_manifest = (HERE/'references/original-builder-449-manifest.json').read_bytes()
    assert sha(raw_manifest) == 'e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017'
    original_map = json.loads(raw_manifest)
    assert len(original_map) == 449
    assert (json.dumps(original_map, indent=2)+'\n').encode() == raw_manifest
    android = (HERE/'references/android.rs').read_bytes()
    assert sha(android) == original_map[ANDROID]['sha256'] == 'fa6f6a995a1cedf17c342ac900df34d1742d6177651af4db6d3c44e6f5478958'
    assert sha((HERE/'references/AGENTS.md').read_bytes()) == original_map['AGENTS.md']['sha256']
    old = b'''    if leaf_go_memory_mode(dependency_mode) {
        p.patch(source, "build/soong", &repo.join(
            "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"))?;
    }
'''
    new = b'''    if leaf_go_memory_mode(dependency_mode) {
        p.patch(source, "build/soong", &repo.join(
            "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"))?;
        p.patch(source, "build/blueprint", &repo.join(
            "android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch"))?;
    }
'''
    assert android.count(old) == 1
    candidate = android.replace(old, new)
    patch = (HERE/Path(PATCH).name).read_bytes()
    assert sha(patch) == '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307'
    root = HERE/'builder-delta'
    root.mkdir(mode=0o700)
    rows = [save(root/ANDROID, candidate), save(root/PATCH, patch)]
    diff = ''.join(difflib.unified_diff(android.decode().splitlines(True),candidate.decode().splitlines(True),fromfile='a/'+ANDROID,tofile='b/'+ANDROID))
    rows.append(save(root/'normal-projection.patch',diff))
    expected = {}
    for key, value in original_map.items():
        expected[key] = dict(value)
        if key == ANDROID:
            expected[key]['sha256'] = sha(candidate)
            expected[key]['bytes'] = len(candidate)
        if key == 'android/apex-compat/0008-soong-leaf-go-memory-budget.patch':
            expected[PATCH] = {'kind':'file','sha256':sha(patch),'bytes':len(patch),'mode':value['mode']}
    assert len(expected) == 450
    changed = [key for key in original_map if original_map[key] != expected[key]]
    assert changed == [ANDROID]
    assert set(expected)-set(original_map) == {PATCH}
    expected_raw = (json.dumps(expected,indent=2)+'\n').encode()
    rows.append(save(root/'expected-builder-450-manifest.json',expected_raw))
    strategy = {
        'schema':1, 'state':'EXPECTED_SOURCE_DELTA_ONLY_NOT_COMPILED_OR_PROJECTED',
        'original_449_manifest_sha256':sha(raw_manifest),
        'expected_450_manifest_sha256':sha(expected_raw),
        'changed':[ANDROID], 'added':[PATCH], 'removed':[], 'inherited_entries_unchanged':448,
        'new_patch_mode':expected[PATCH]['mode'],
        'go6_patch_unchanged':original_map['android/apex-compat/0008-soong-leaf-go-memory-budget.patch'],
        'engine_candidate05_files':925, 'engine_candidate05_bytes_changed':0,
        'projection_entry':'existing leaf_go_memory_mode branch -> Projection.patch(source, build/blueprint, new patch)',
        'projection_invariants':['existing apply --check','save original bytes and mtime in normal journal','normal apply and patch SHA map','normal effective file inventory','normal restore/recover and global builder locks'],
        'requires_before_full_build':['actual complete-package Go control PASS','new 450-file builder copy verified against expected map','matching new Rust builder compiled and its real binary SHA bound','normal lock/recover path; no manual AOSP edits','new fresh engine output root','existing Go6/11GiB +1GiB swap/fresh available14GiB and SwapFree2GiB admission and Main before/after fences','final engine inputs contain new Blueprint context and patch SHA','complete 3793 host suite and four isolated Android signal cases after artifact binding'],
        'not_proven':['Go test compile/runtime','Rust builder compile','full cold engine build','whole-build OOM removal','specific OOM victim','Android or whole app readiness'],
        'remote_actions':0,
    }
    rows.append(save(root/'manifest-strategy.json',json.dumps(strategy,indent=2)+'\n'))
    receipt = save(root/'SOURCE_PINS.json',json.dumps({'schema':1,'files':rows},indent=2)+'\n')
    print(json.dumps({'manifest':receipt,'files':rows},indent=2))

if __name__ == '__main__':
    main()
