#!/usr/bin/env python3
"""Local admission/request controls, with explicit fixture observations."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROWS = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(name):
    result = {'__name__': 'local_control', '__file__': str(HERE / name)}
    exec(compile((HERE / name).read_bytes(), name, 'exec'), result, result)
    return result


def check(name, function):
    try:
        result = function()
        ROWS.append({'case': name, 'pass': True, 'detail': result})
    except Exception as error:
        ROWS.append({'case': name, 'pass': False, 'error': repr(error)})


def reject(function, message=None):
    try:
        function()
    except (RuntimeError, KeyError, OSError) as error:
        if message is not None:
            assert message in str(error), repr(error)
        return {'rejected': True, 'error': str(error)}
    raise AssertionError('unexpected acceptance')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    scope = load('combined_build_go6r2.py')
    generator = load('make_requests.py')
    minimum = 14 * 1024**3
    free_swap = 2 * 1024**3
    check('MemAvailable_below_14GiB_rejected', lambda: reject(lambda: scope['memory_admission'](
        {'MemAvailable': minimum-1, 'SwapFree': free_swap}), 'less than 14 GiB'))
    check('SwapFree_below_2GiB_rejected', lambda: reject(lambda: scope['memory_admission'](
        {'MemAvailable': minimum, 'SwapFree': free_swap-1}), '2 GiB free swap'))
    check('old_1GiB_swap_admission_rejected', lambda: reject(lambda: scope['memory_admission'](
        {'MemAvailable': 16*1024**3, 'SwapFree': 1024**3}), '2 GiB free swap'))

    def boundary():
        scope['memory_admission']({'MemAvailable': minimum, 'SwapFree': free_swap})
        plan = scope['plan']()
        assert plan['MemoryMax'] == 11*1024**3 and plan['MemorySwapMax'] == 1024**3
        assert plan['admission_difference_bytes'] == 3*1024**3
        assert plan['swap_admission_difference_bytes'] == 1024**3
        assert plan['physical_reservation_claimed'] is False
        return {'fixture_only': True, 'memory_difference_bytes': 3*1024**3,
                'swap_difference_bytes': 1024**3, 'remote_admission_proven': False}
    check('new_exact_resource_boundary_3GiB_and_1GiB_differences', boundary)
    zero_events = 'low 0\nhigh 0\nmax 27\noom 0\noom_kill 0\noom_group_kill 0\n'
    check('owned_zero_OOM_kills_accepts_recorded_pressure', lambda: scope['owned_resource_gate'](zero_events))
    for label, text in (
        ('OOM_kill', zero_events.replace('oom_kill 0', 'oom_kill 1')),
        ('OOM_group_kill', zero_events.replace('oom_group_kill 0', 'oom_group_kill 1')),
        ('missing_observation', None),
        ('missing_key', 'max 0\noom 0\noom_kill 0\n'),
        ('duplicate_key', zero_events+'oom_kill 0\n'),
    ):
        check('owned_resource_rejects_'+label, lambda value=text: reject(lambda: scope['owned_resource_gate'](value)))
    def actual_go4_failure():
        path = HERE.parent / 'go4-fullbuild-actual-failure-01/attempt-terminal.json'
        raw = path.read_bytes()
        assert sha(raw) == '6abfe6c9e8eb448043b3040a735b1483a93b3bf365ef99441bb0d5c48a61186d'
        return {**reject(lambda: scope['owned_resource_gate'](json.loads(raw)['memory_events']), 'owned OOM kill'),
                'actual_prior_terminal_sha256': sha(raw)}
    check('actual_Go4_own_OOM_terminal_rejected', actual_go4_failure)

    def original_manifest():
        raw = (HERE / 'expected-copied-builder-source-manifest.json').read_bytes()
        assert sha(raw) == scope['BUILDER_MANIFEST_SHA'] == generator['BASE_BUILDER_SHA']
        rows = json.loads(raw)
        assert len(rows) == 449
        patch = (HERE / 'references/0008-soong-go6.unchanged.patch').read_bytes()
        assert sha(patch) == rows[scope['GO_PATCH']]['sha256'] == scope['GO_PATCH_SHA']
        assert rows[scope['GO_PATCH']]['bytes'] == len(patch) == 583
        assert patch.count(b'"6GiB"') == 1
        assert scope['plan']()['builder_source_delta'] is None
        return {'actual_prior_449_manifest_bytes_checked': True, 'changed_source_rows': 0,
                'fresh_remote_copy_not_yet_observed': True}
    check('actual_prior_449_manifest_and_Go6_patch_unchanged', original_manifest)

    reference = {'effective_projection': {'patches': {scope['GO_PATCH']: scope['GO_PATCH_SHA'],
                                                    'unchanged.patch': 'a'*64},
                                         'files': {scope['SOONG_SOURCE']: 'b'*64}}}
    check('projection_requires_successful_Go6_actual_hash',
          lambda: {**scope['go_projection_contract'](copy.deepcopy(reference), reference),
                   'synthetic_receipt_only': True})
    for label, mutation in (
        ('old_Go4_patch', lambda v: v['effective_projection']['patches'].update({scope['GO_PATCH']: '0f51b488dfcb6200281d25d4b6d3da594870c6e747d2629f7b2e1bed8ae4ddbd'})),
        ('old_Go5_patch', lambda v: v['effective_projection']['patches'].update({scope['GO_PATCH']: '39211a784284ed319b6abbbe4b327a88896931d39c6bdb91fe727a9a7589325f'})),
        ('other_patch_drift', lambda v: v['effective_projection']['patches'].update({'unchanged.patch': 'c'*64})),
        ('Soong_source_drift', lambda v: v['effective_projection']['files'].update({scope['SOONG_SOURCE']: 'c'*64})),
    ):
        bad = copy.deepcopy(reference)
        mutation(bad)
        check('projection_rejects_'+label, lambda value=bad: reject(lambda: scope['go_projection_contract'](value, reference)))

    builder_raw = (HERE / 'expected-copied-builder-source-manifest.json').read_bytes()
    fixture = {'state': 'PREPARED_NOT_BUILT', 'candidate_manifest_sha256': scope['MANIFEST_SHA'],
               'builder_manifest_sha256': scope['BUILDER_MANIFEST_SHA'],
               'engine_file_count': 925, 'engine_files': {'explicit-fixture/'+str(i): 'a'*64 for i in range(925)},
               'base_and_candidate_unchanged': True, 'feature_default_enabled': False,
               'full_engine_built': False, 'ART_built': False, 'factory_built': False, 'installed': False,
               'Main_actions': 0, 'plan': scope['plan']()}
    encode = lambda v: (json.dumps(v, indent=2)+'\n').encode()
    def preparation_fixture():
        assert generator['validate_actual_preparation'](encode(fixture), builder_raw) == fixture
        return {'fixture_accepted': True, 'remote_preparation_claimed': False}
    check('request_accepts_only_explicit_preparation_fixture_with_exact_449_bytes', preparation_fixture)
    for label, field, value in (
        ('wrong_scope', 'feature_default_enabled', True),
        ('wrong_engine_count', 'engine_file_count', 924),
        ('wrong_builder_pin', 'builder_manifest_sha256', 'a'*64),
        ('wrong_preparation_state', 'state', 'BUILT'),
        ('Main_actions', 'Main_actions', 1),
    ):
        bad = copy.deepcopy(fixture)
        bad[field] = value
        check('request_rejects_'+label,
              lambda obj=bad: reject(lambda: generator['validate_actual_preparation'](encode(obj), builder_raw)))
    bad = copy.deepcopy(fixture)
    bad['plan']['MemoryMax'] = 9*1024**3
    check('request_rejects_old_Go4_plan', lambda: reject(lambda: generator['validate_actual_preparation'](encode(bad), builder_raw)))

    def prepare_request():
        request = generator['make_prepare']()
        assert request['stdin'].encode() == (HERE/'combined_build_go6r2.py').read_bytes()
        assert request['memory_max_bytes'] == 1024**3 and request['cpu_quota_percent'] == 100
        assert request['args'][-1] == '--prepare' and request['timeout_seconds'] == 300
        assert request['idempotency_key'] == generator['PREPARE_KEY']
        return {'preparation_only': True, 'submitted': False, 'source_exact': True}
    check('prepare_request_pins_exact_controller', prepare_request)
    fence = load('fenced_build_go6r2.template.py')
    check('placeholder_actual_preparation_rejected_before_actions',
          lambda: reject(lambda: fence['run']({}), 'actual Go6R2 preparation'))
    for name in ('combined_build_go6r2.py', 'fenced_build_go6r2.template.py', 'make_requests.py'):
        def run_plan(script=name):
            result = subprocess.run([sys.executable, '-I', str(HERE/script)], capture_output=True, timeout=10, check=True)
            parsed = json.loads(result.stdout)
            assert parsed['state'] == 'PLAN_ONLY' and not result.stderr
            return {'actual_local_cli': True, 'stdout_sha256': sha(result.stdout)}
        check('default_PLAN_'+name, run_plan)
    result = {'schema': 1, 'state': 'LOCAL_CONTROLS_PASS' if all(r['pass'] for r in ROWS) else 'FAIL',
              'count': len(ROWS), 'all_pass': all(r['pass'] for r in ROWS), 'checks': ROWS,
              'remote_preparation_performed': False, 'remote_admission_proven': False,
              'builder_executed': False, 'Main_actions': 0, 'production_ready': False,
              'scope': 'Actual Python functions and local default CLIs. Memory values, projection receipts and preparation objects are explicit fixtures; prior 449-file manifest and Go6 patch bytes are actual pinned inputs.'}
    args.output.open('x').write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'count': len(ROWS), 'all_pass': result['all_pass'], 'sha256': sha(args.output.read_bytes()),
                      'failed': [r['case'] for r in ROWS if not r['pass']]}))
    return 0 if result['all_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
