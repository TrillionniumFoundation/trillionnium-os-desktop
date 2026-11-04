#!/usr/bin/env python3
"""Bounded local source/input controls; no preparation, build or remote action."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROWS = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(name):
    scope = {"__name__": "local_source_control", "__file__": str(HERE / name)}
    exec(compile((HERE / name).read_bytes(), name, "exec"), scope, scope)
    return scope


def check(name, function):
    try:
        detail = function()
        ROWS.append({"case": name, "pass": True, "detail": detail})
    except Exception as error:
        ROWS.append({"case": name, "pass": False, "error": repr(error)})


def rejected(function, contains=None):
    try:
        function()
    except (RuntimeError, OSError, KeyError) as error:
        if contains is not None:
            assert contains in str(error), repr(error)
        return {"rejected": True, "error": str(error)}
    raise AssertionError("unexpected acceptance")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    scope = load('combined_build_go5.py')
    request = load('make_requests.py')
    basepatch = (HERE.parent / 'combined05-go5-proposal-01/references/0008-soong-go6.preimage.patch').read_bytes()
    newpatch = (HERE / '0008-soong-leaf-go-memory-budget.patch').read_bytes()
    base = {'fixture/' + str(n): {'kind': 'file', 'sha256': 'a' * 64, 'bytes': 1, 'mode': 0o644}
            for n in range(448)}
    base[scope['GO_PATCH']] = {'kind': 'file', 'sha256': sha(basepatch), 'bytes': 583, 'mode': 0o644}

    def one_byte():
        assert len(basepatch) == len(newpatch) == 583
        assert sha(newpatch) == scope['GO_PATCH_SHA']
        changed = [i for i, (a, b) in enumerate(zip(basepatch, newpatch)) if a != b]
        assert len(changed) == 1 and basepatch[changed[0]] == ord('6') and newpatch[changed[0]] == ord('5')
        return {'changed_offset': changed[0], 'bytes': 583, 'source': 'exact pinned patch pair'}
    check('actual_patch_is_only_one_byte_6_to_5', one_byte)

    def transformed():
        prior = copy.deepcopy(base)
        actual = scope['go_builder_inventory'](base)
        assert base == prior and len(actual) == 449
        assert [k for k in base if actual[k] != base[k]] == [scope['GO_PATCH']]
        assert actual[scope['GO_PATCH']]['mode'] == 0o644
        return {'fixture_only': True, 'rows': 449, 'changed_rows': 1, 'base_not_mutated': True}
    check('manifest_changes_one_row_and_preserves_base_and_modes', transformed)
    for field, bad in (('sha256', '0' * 64), ('bytes', 584), ('kind', 'symlink')):
        changed = copy.deepcopy(base)
        changed[scope['GO_PATCH']][field] = bad
        check('manifest_rejects_changed_' + field,
              lambda value=changed: rejected(lambda: scope['go_builder_inventory'](value)))
    check('manifest_rejects_wrong_count',
          lambda: rejected(lambda: scope['go_builder_inventory']({k: v for k, v in base.items() if k != 'fixture/0'})))

    with tempfile.TemporaryDirectory(prefix='go5-local-control-') as temporary:
        temp = Path(temporary)
        original_build_source = scope['BUILD_SOURCE']
        try:
            def ordinary_copy():
                source = temp / 'old.patch'
                source.write_bytes(basepatch)
                source.chmod(0o644)
                scope['BUILD_SOURCE'] = temp / 'copied'
                target = scope['BUILD_SOURCE'] / scope['GO_PATCH']
                target.parent.mkdir(parents=True)
                shutil.copy2(source, target)
                scope['write_owned_go_patch']()
                assert source.read_bytes() == basepatch and target.read_bytes() == newpatch
                assert source.stat().st_ino != target.stat().st_ino
                assert target.stat().st_mode & 0o777 == 0o644
                return {'actual_local_file_io': True, 'base_unchanged': True, 'mode_preserved': True}
            check('actual_private_copy_only_is_changed', ordinary_copy)

            def hardlink():
                source = temp / 'hardlink-original.patch'
                source.write_bytes(basepatch)
                scope['BUILD_SOURCE'] = temp / 'hardlinked'
                target = scope['BUILD_SOURCE'] / scope['GO_PATCH']
                target.parent.mkdir(parents=True)
                os.link(source, target)
                result = rejected(scope['write_owned_go_patch'], 'private regular inode')
                assert source.read_bytes() == basepatch and target.read_bytes() == basepatch
                return {**result, 'preimage_unchanged': True, 'actual_local_file_io': True}
            check('hardlink_rejected_before_mutation', hardlink)

            def symlink():
                source = temp / 'symlink-original.patch'
                source.write_bytes(basepatch)
                scope['BUILD_SOURCE'] = temp / 'symlinked'
                target = scope['BUILD_SOURCE'] / scope['GO_PATCH']
                target.parent.mkdir(parents=True)
                target.symlink_to(source)
                result = rejected(scope['write_owned_go_patch'])
                assert source.read_bytes() == basepatch
                return {**result, 'preimage_unchanged': True, 'actual_local_file_io': True}
            check('symlink_rejected_before_mutation', symlink)

            def wrong_preimage():
                scope['BUILD_SOURCE'] = temp / 'wrong-preimage'
                target = scope['BUILD_SOURCE'] / scope['GO_PATCH']
                target.parent.mkdir(parents=True)
                wrong = basepatch[:-1] + b'x'
                target.write_bytes(wrong)
                result = rejected(scope['write_owned_go_patch'], 'preimage changed')
                assert target.read_bytes() == wrong
                return {**result, 'bytes_unchanged': True, 'actual_local_file_io': True}
            check('changed_preimage_rejected_before_write', wrong_preimage)
        finally:
            scope['BUILD_SOURCE'] = original_build_source

    minimum = 14 * 1024**3
    swap = 1024**3
    check('memory_below_14GiB_rejected', lambda: rejected(lambda: scope['memory_admission'](
        {'MemAvailable': minimum - 1, 'SwapFree': swap}), 'less than 14 GiB'))
    check('free_swap_below_1GiB_rejected', lambda: rejected(lambda: scope['memory_admission'](
        {'MemAvailable': minimum, 'SwapFree': swap - 1}), 'free swap'))
    def boundary():
        scope['memory_admission']({'MemAvailable': minimum, 'SwapFree': swap})
        assert scope['MEMORY_MAX'] == 10 * 1024**3 and minimum - scope['MEMORY_MAX'] == 4 * 1024**3
        return {'fixture_values_only': True, 'minimum_bytes': minimum, 'admission_difference_bytes': 4 * 1024**3,
                'actual_host_admission_proven': False}
    check('exact_resource_boundary_retains_4GiB_difference', boundary)

    reference = {'effective_projection': {'patches': {scope['GO_PATCH']: scope['GO_PATCH_PREIMAGE_SHA'],
                                                       'unchanged.patch': 'a' * 64},
                                          'files': {scope['SOONG_SOURCE']: 'b' * 64}}}
    actual = copy.deepcopy(reference)
    actual['effective_projection']['patches'][scope['GO_PATCH']] = scope['GO_PATCH_SHA']
    actual['effective_projection']['files'][scope['SOONG_SOURCE']] = 'c' * 64
    check('projection_accepts_only_declared_patch_set_delta',
          lambda: {**scope['go_projection_contract'](actual, reference), 'synthetic_receipts_only': True})
    for label, mutate in (
        ('old_Go6_patch', lambda x: x['effective_projection']['patches'].update({scope['GO_PATCH']: scope['GO_PATCH_PREIMAGE_SHA']})),
        ('unrelated_patch_changed', lambda x: x['effective_projection']['patches'].update({'unchanged.patch': 'd' * 64})),
        ('unchanged_projected_file', lambda x: x['effective_projection']['files'].update({scope['SOONG_SOURCE']: 'b' * 64}))):
        bad = copy.deepcopy(actual)
        mutate(bad)
        check('projection_rejects_' + label,
              lambda value=bad: rejected(lambda: scope['go_projection_contract'](value, reference)))

    def request_budget():
        result = request['make_prepare']()
        assert result['stdin'].encode() == (HERE / 'combined_build_go5.py').read_bytes()
        assert result['idempotency_key'] == request['PREPARE_KEY']
        assert result['memory_max_bytes'] == 1024**3 and result['cpu_quota_percent'] == 100
        assert result['args'][-1] == '--prepare'
        return {'preparation_only': True, 'submitted': False, 'pinned_source_exact': True}
    check('preparation_request_contains_exact_controller', request_budget)
    fence = load('fenced_build_go5.template.py')
    check('fence_template_rejects_absent_actual_preparation_before_actions',
          lambda: rejected(lambda: fence['run']({}), 'actual Go5 preparation'))
    for script in ('combined_build_go5.py', 'fenced_build_go5.template.py', 'make_requests.py'):
        def default_plan(name=script):
            result = subprocess.run([sys.executable, '-I', str(HERE / name)],
                                    capture_output=True, timeout=10, check=True)
            value = json.loads(result.stdout)
            assert value['state'] == 'PLAN_ONLY' and not result.stderr
            return {'actual_local_cli': True, 'state': value['state'], 'stdout_sha256': sha(result.stdout)}
        check('default_PLAN_' + script, default_plan)

    result = {'schema': 1, 'state': 'LOCAL_PROFILE_CONTROLS_PASS' if all(r['pass'] for r in ROWS) else 'FAIL',
              'checks': ROWS, 'count': len(ROWS), 'all_pass': all(r['pass'] for r in ROWS),
              'controller_sha256': sha((HERE / 'combined_build_go5.py').read_bytes()),
              'scope': 'Actual frozen Python functions and local file syscalls; manifests, memory readings and projection receipts are explicit fixtures.',
              'actual_449_remote_inventory_read': False, 'remote_preparation_performed': False,
              'compiler_executed': False, 'remote_requests_submitted': 0, 'Main_actions': 0,
              'full_engine_built': False, 'production_ready': False}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'state': result['state'], 'checks': len(ROWS), 'sha256': sha(args.output.read_bytes()),
                      'failed': [r['case'] for r in ROWS if not r['pass']]}))
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
