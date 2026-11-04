#!/usr/bin/env python3
"""Derive a new local Go4 proposal from the immutable Go5 profile. No dispatch."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GO5 = HERE.parent / 'combined05-go5-profile-01'
GO5_PINS = '6d36cd4d0763c68577d6b7e47ac29c39a9b63106e60d0ef4600d3a5bbfc658de'
GO6_PATCH = HERE.parent / 'combined05-go5-proposal-01/references/0008-soong-go6.preimage.patch'
GO6_SHA = '6aaaf5ec96a75bb6480c202d6483a5b22bdd4963d6d3b66bbfad4d80ee5ed20e'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, why):
    if not value:
        raise RuntimeError(why)


def replace_one(text, old, new):
    require(text.count(old) == 1, 'source anchor differs: ' + repr(old))
    return text.replace(old, new, 1)


def renamed(text):
    return text.replace('GO5', 'GO4').replace('Go5', 'Go4').replace('go5', 'go4')


def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def diff(name, old, new, old_name, new_name):
    put(name, ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile=old_name, tofile=new_name)).encode())


def derive():
    pins_raw = (GO5 / 'SOURCE_PINS.json').read_bytes()
    require(sha(pins_raw) == GO5_PINS, 'Go5 freeze manifest changed')
    pins = json.loads(pins_raw)
    require(len(pins['files']) == 15, 'Go5 inventory count changed')
    originals = {}
    for name, row in pins['files'].items():
        raw = (GO5 / name).read_bytes()
        require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'Go5 source changed: ' + name)
        originals[name] = raw
    go6 = GO6_PATCH.read_bytes()
    require(sha(go6) == GO6_SHA and go6.count(b'"6GiB"') == 1, 'Go6 patch preimage differs')
    go4 = go6.replace(b'"6GiB"', b'"4GiB"', 1)
    require(len(go4) == len(go6) == 583 and sum(a != b for a,b in zip(go6,go4)) == 1,
            'Go4 is not the one-byte change from original Go6')
    old_patch_sha = sha(originals['0008-soong-leaf-go-memory-budget.patch'])
    patch_sha = sha(go4)

    old_controller = originals['combined_build_go5.py'].decode()
    controller = renamed(old_controller).replace(old_patch_sha, patch_sha)
    require(controller.count('5GiB') == 4, 'Go5 budget occurrence count differs')
    controller = controller.replace('5GiB', '4GiB')
    controller = replace_one(controller, 'MEMORY_MAX = 10 * 1024**3', 'MEMORY_MAX = 9 * 1024**3')
    controller = replace_one(controller, 'MIN_AVAILABLE = 14 * 1024**3', 'MIN_AVAILABLE = 13 * 1024**3')
    controller = replace_one(controller, 'less than 14 GiB MemAvailable', 'less than 13 GiB MemAvailable')
    controller = replace_one(controller, 'Go4/10GiB profile', 'Go4/9GiB profile')
    ast.parse(controller)
    controller_sha = sha(controller.encode())
    old_controller_sha = sha(originals['combined_build_go5.py'])

    old_fence = originals['fenced_build_go5.template.py'].decode()
    fence = renamed(old_fence).replace(old_controller_sha, controller_sha)
    ast.parse(fence)
    fence_sha = sha(fence.encode())
    old_request = originals['make_requests.py'].decode()
    request = renamed(old_request).replace(old_controller_sha, controller_sha)
    request = request.replace(sha(originals['fenced_build_go5.template.py']), fence_sha)
    request = request.replace(old_patch_sha, patch_sha)
    require(request.count('10737418240') == 2 and request.count('15032385536') == 1,
            'request memory budget occurrences differ')
    request = request.replace('10737418240', '9663676416').replace('15032385536', '13958643712')
    ast.parse(request)

    old_controls = originals['verify_profile.py'].decode()
    controls = replace_one(old_controls,
        "basepatch = (HERE.parent / 'combined05-go5-proposal-01/references/0008-soong-go6.preimage.patch').read_bytes()",
        "basepatch = (HERE / 'references/0008-soong-go6.preimage.patch').read_bytes()")
    controls = renamed(controls)
    controls = replace_one(controls, "newpatch[changed[0]] == ord('5')", "newpatch[changed[0]] == ord('4')")
    controls = replace_one(controls, 'minimum = 14 * 1024**3', 'minimum = 13 * 1024**3')
    controls = controls.replace('memory_below_14GiB_rejected', 'memory_below_13GiB_rejected')
    controls = replace_one(controls, "'less than 14 GiB'", "'less than 13 GiB'")
    controls = replace_one(controls, "scope['MEMORY_MAX'] == 10 * 1024**3", "scope['MEMORY_MAX'] == 9 * 1024**3")
    ast.parse(controls)

    put('combined_build_go4.py', controller.encode())
    put('fenced_build_go4.template.py', fence.encode())
    put('make_requests.py', request.encode())
    put('verify_profile.py', controls.encode())
    put('main_snapshot.py', originals['main_snapshot.py'])
    put('0008-soong-leaf-go-memory-budget.patch', go4)
    put('references/0008-soong-go6.preimage.patch', go6)
    diff('controller-go5-to-go4.patch', old_controller, controller,
         'a/frozen-combined_build_go5.py', 'b/combined_build_go4.py')
    diff('fence-template-go5-to-go4.patch', old_fence, fence,
         'a/frozen-fenced_build_go5.template.py', 'b/fenced_build_go4.template.py')
    diff('request-generator-go5-to-go4.patch', old_request, request,
         'a/frozen-make_requests_go5.py', 'b/make_requests.py')
    diff('controls-go5-to-go4.patch', old_controls, controls,
         'a/frozen-verify_profile_go5.py', 'b/verify_profile.py')
    diff('original-go6-to-go4.patch', go6.decode(), go4.decode(),
         'a/android/apex-compat/0008-soong-leaf-go-memory-budget.patch',
         'b/android/apex-compat/0008-soong-leaf-go-memory-budget.patch')
    result = {'schema': 1, 'state': 'LOCAL_GO4_PROFILE_DERIVED_NOT_PREPARED',
              'base_Go5_profile_pins_sha256': GO5_PINS,
              'original_449_builder_manifest_sha256': 'e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017',
              'original_Go6_patch_sha256': GO6_SHA, 'Go4_patch_sha256': patch_sha,
              'Go4_patch_bytes': 583, 'original_Go6_changed_bytes': 1,
              'controller_sha256': controller_sha, 'fence_template_sha256': fence_sha,
              'new_root': '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined05-go4-01',
              'MemoryMax_bytes': 9663676416, 'minimum_MemAvailable_bytes': 13958643712,
              'admission_difference_bytes': 4294967296, 'memory_swap_max_bytes': 1073741824,
              'cpu_quota_percent': 200, 'normal_builder_jobs': 1,
              'original_Go6_profile_changed': False, 'Go5_profile_changed': False,
              'new_actual_builder_manifest_sha256': None, 'new_actual_preparation_sha256': None,
              'remote_requests_submitted': 0, 'production_ready': False}
    put('derivation.json', (json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-local', action='store_true')
    args = parser.parse_args()
    if args.write_local:
        derive()
    else:
        print(json.dumps({'state': 'PLAN_ONLY', 'output_dir': str(HERE), 'remote_requests_submitted': 0}))
