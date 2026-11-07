#!/usr/bin/env python3
"""Create the independent Go6/11GiB profile; local files only, no dispatch."""
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, wanted):
    raw = path.read_bytes()
    assert sha(raw) == wanted, str(path)
    return raw


def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def write(name, raw):
    target = HERE / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.open('xb').write(raw)


def patch(old, new, before, after):
    return ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                     fromfile=before, tofile=after)).encode()


def main():
    old = pinned(BASE / 'fullbuild05-prepare-01/combined_build05.py',
                 'e56f06abdbda5aa95fe42e4ecf14d7f79f53e53821a8d5b1d43d0dce0776c655')
    text = old.decode()
    text = once(text, 'Owned candidate05 preparation and normal full engine build. Default: plan.',
                'Independent candidate05 Go6/11GiB second profile. Default: plan; no automatic retry.')
    text = once(text, 'ROOT = OWNER / "full-build-combined05-01"',
                'ROOT = OWNER / "full-build-combined05-go6-02"')
    text = once(text, 'MIN_AVAILABLE = 15 * 1024**3',
                'MIN_AVAILABLE = 14 * 1024**3\nMIN_FREE_SWAP = 2 * 1024**3\n'
                'GO_PATCH = "android/apex-compat/0008-soong-leaf-go-memory-budget.patch"\n'
                'GO_PATCH_SHA = "6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e"\n'
                'SOONG_SOURCE = "build/soong/ui/build/soong.go"')
    helpers = '''def memory_admission(memory):
    require(MIN_AVAILABLE - MEMORY_MAX == 3 * 1024**3,
            "new profile requires an explicit three-GiB admission difference")
    require(MIN_FREE_SWAP - SWAP_MAX == 1024**3,
            "new profile requires at least one-GiB swap admission difference")
    require(memory["MemAvailable"] >= MIN_AVAILABLE,
            "less than 14 GiB MemAvailable for independent Go6 second profile; no automatic retry")
    require(memory["SwapFree"] >= MIN_FREE_SWAP,
            "less than the required 2 GiB free swap; no automatic retry")


def owned_resource_gate(text):
    require(isinstance(text, str), "owned memory.events was not observed")
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows),
            "malformed owned memory.events")
    events = {row[0]: int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(name in events for name in ("oom", "oom_kill", "oom_group_kill")),
            "incomplete or duplicate owned memory.events")
    require(events["oom_kill"] == 0 and events["oom_group_kill"] == 0,
            "owned OOM kill observed; build is not qualified")
    return {"pass": True, "events": events, "owned_oom_kills_zero": True}


def go_projection_contract(inputs, reference):
    # The entire 449-file builder copy, including its Go6 patch, is unchanged.
    # Reject a leftover Go4/Go5 projection after normal lock/journal recovery.
    old = reference["effective_projection"]
    actual = inputs["effective_projection"]
    require(old["patches"][GO_PATCH] == GO_PATCH_SHA,
            "prior successful projection used a different Go patch")
    require(actual["patches"] == old["patches"],
            "actual projection patch set differs from the successful Go6 builder")
    projected_hash = actual["files"][SOONG_SOURCE]
    require(isinstance(projected_hash, str) and len(projected_hash) == 64 and
            all(c in "0123456789abcdef" for c in projected_hash) and
            projected_hash == old["files"][SOONG_SOURCE],
            "actual projected Soong source differs from the successful Go6 builder")
    return {"patch_path": GO_PATCH, "patch_sha256": GO_PATCH_SHA,
            "projected_soong_path": SOONG_SOURCE, "projected_soong_sha256": projected_hash,
            "actual_prior_success_projected_hash_equal": True,
            "all_applied_patch_hashes_equal_reference": True,
            "normal_builder_lock_and_journal_recovery_required": True}


'''
    text = once(text, 'def source_contract():\n', helpers + 'def source_contract():\n')
    text = once(text, '            "builder source changed")\n',
                '            "builder source changed")\n'
                '    require(builder_files[GO_PATCH]["sha256"] == GO_PATCH_SHA and\n'
                '            builder_files[GO_PATCH]["bytes"] == 583 and\n'
                '            digest(BUILDER_ORIGIN / GO_PATCH) == GO_PATCH_SHA, "original Go6 patch changed")\n')
    text = once(text, '"MemAvailable_minimum": MIN_AVAILABLE, "SwapFree_minimum": SWAP_MAX,',
                '"MemAvailable_minimum": MIN_AVAILABLE, "SwapFree_minimum": MIN_FREE_SWAP,\n'
                '            "admission_difference_bytes": MIN_AVAILABLE - MEMORY_MAX,\n'
                '            "swap_admission_difference_bytes": MIN_FREE_SWAP - SWAP_MAX,\n'
                '            "physical_reservation_claimed": False, "builder_source_delta": None,')
    text = once(text, '    reference = reference_inputs()\n    for field in EXTERNAL_FIELDS:',
                '    reference = reference_inputs()\n    go_projection = go_projection_contract(inputs, reference)\n'
                '    for field in EXTERNAL_FIELDS:')
    text = once(text, '            "private_entry_export_observed": True, "raw_source_files": len(engine),',
                '            "private_entry_export_observed": True, "go_projection": go_projection,\n'
                '            "raw_source_files": len(engine),')
    text = once(text, '    require(memory["MemAvailable"] >= MIN_AVAILABLE, "less than 15 GiB MemAvailable; no automatic lower-budget retry")\n'
                '    require(memory["SwapFree"] >= SWAP_MAX, "less than the required 1 GiB free swap; no automatic lower-budget retry")',
                '    # Fresh kernel counters are read above at this actual attempt; historical\n'
                '    # diagnostic samples are evidence only, never admission authorization.\n'
                '    memory_admission(memory)')
    text = once(text, '"STARTING_COMBINED05_FLAG0_FULL_BUILD"', '"STARTING_COMBINED05_GO6R2_FLAG0_FULL_BUILD"')
    text = once(text, '"mem_available_before": memory["MemAvailable"], "cpu_affinity_before": affinity,',
                '"mem_available_before": memory["MemAvailable"], "swap_free_before": memory["SwapFree"],\n'
                '             "cpu_affinity_before": affinity,')
    text = once(text, '        if observation_errors:\n',
                '        try:\n'
                '            terminal["owned_resource_gate"] = owned_resource_gate(terminal["memory_events"])\n'
                '        except Exception as error:\n'
                '            terminal["owned_resource_gate"] = {"pass": False, "error": repr(error)}\n'
                '            if failure is None:\n'
                '                failure = "owned resource qualification failed: " + repr(error)\n'
                '                terminal["state"] = "FAILED"\n'
                '                terminal["error"] = failure\n'
                '        if observation_errors:\n')
    controller = text.encode()
    compile(controller, 'combined_build_go6r2.py', 'exec')
    write('combined_build_go6r2.py', controller)
    write('controller-original-go6-to-go6r2.patch', patch(old, controller, 'a/combined_build05.py', 'b/combined_build_go6r2.py'))
    template_old = pinned(BASE / 'combined05-go4-profile-01/fenced_build_go4.template.py',
                          'f4c4ad7788fc1d6a85b248b469a26d96341e009937e9ee69ae3d011ac66ef0f9')
    template = template_old.decode().replace('GO4', 'GO6R2').replace('Go4', 'Go6R2').replace('go4', 'go6r2')
    template = once(template, 'full-build-combined05-go6r2-01', 'full-build-combined05-go6-02')
    template = once(template, '2c569853811e0f594a805c056b68794481edac6222524c190cc2ff2f35f6ccac', sha(controller))
    compile(template, 'fenced_build_go6r2.template.py', 'exec')
    write('fenced_build_go6r2.template.py', template.encode())
    write('fence-go4-to-go6r2.patch', patch(template_old, template.encode(), 'a/fenced_build_go4.template.py', 'b/fenced_build_go6r2.template.py'))
    snapshot = pinned(BASE / 'combined05-go4-profile-01/main_snapshot.py',
                      'f909bdfcaedfef29fcc1ba6a994c49bc21e99850204bac7e0565548bcd7139cb')
    write('main_snapshot.py', snapshot)
    original_manifest = pinned(BASE / 'go5-actual-preparation-01/base-builder-source-manifest.reconstructed-exact.json',
                               'e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017')
    assert len(json.loads(original_manifest)) == 449
    write('expected-copied-builder-source-manifest.json', original_manifest)
    go6 = pinned(BASE / 'combined05-go4-profile-01/references/0008-soong-go6.preimage.patch',
                 '6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e')
    write('references/0008-soong-go6.unchanged.patch', go6)
    write('derivation.json', (json.dumps({
        'schema': 1, 'controller_preimage_sha256': sha(old), 'controller_sha256': sha(controller),
        'fence_preimage_sha256': sha(template_old), 'fence_template_sha256': sha(template.encode()),
        'snapshot_unchanged_sha256': sha(snapshot), 'builder_manifest_unchanged_sha256': sha(original_manifest),
        'builder_rows': 449, 'builder_source_changed_rows': 0, 'Go_patch_changed_bytes': 0,
        'Go_patch_sha256': sha(go6), 'remote_actions': 0,
        'new_root': '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-go6-02'
    }, indent=2) + '\n').encode())
    print(json.dumps({'controller_sha256': sha(controller), 'fence_sha256': sha(template.encode()), 'remote_actions': 0}))


if __name__ == '__main__':
    main()
