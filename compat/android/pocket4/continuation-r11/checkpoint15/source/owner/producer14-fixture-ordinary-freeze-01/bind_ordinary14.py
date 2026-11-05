#!/usr/bin/env python3
"""Bind the immutable ordinary template to the observed compile receipt only."""
import ast
import copy
import difflib
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / 'producer14-fixture-controller-freeze-01'
ACTUAL = ROOT.parent / 'root-recovery-20261104-02/evidence/owner14-compile01/compile-result.json'
OUT = ROOT / 'producer14-fixture-ordinary-freeze-01'
ACTUAL_SHA = 'a916592cc708dc76411b482a371214410bca4662f6ff72dccd5083d88872b6a6'
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-fixture-r11-build-14-01'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    assert not OUT.exists()
    raw = ACTUAL.read_bytes()
    assert len(raw) == 39898 and sha(raw) == ACTUAL_SHA
    result = json.loads(raw)
    assert result['success'] is True and result['compile_only'] is True
    assert result['revision'] == 'producer14-retirement-fixture-repair01'
    assert result['candidate'] == REMOTE + '/candidate' and result['target'] == REMOTE + '/target'
    assert result['source_origin'] == '/home/alex/work/pocket4-supervisor-lmkd-drain-r11-build-13-01/candidate'
    assert result['prior_build_receipt_sha256'] == '9a2cf0087ff99b6834fc2b3a963e03629a14acc21af1a8d67f2b5081bbb22e8e'
    manifest = (FROZEN / 'manifest.json').read_bytes()
    assert sha(manifest) == 'd28decba583d68484b894862fd8f07a179584e53807bad5bf49515f36634d081'
    for row in json.loads(manifest)['files']:
        data = (FROZEN / row['path']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
    payload = (FROZEN / 'payload.json').read_bytes()
    cfg = json.loads(payload)
    expected = {**cfg['preimage'], **{p: {'bytes': row['bytes'], 'sha256': row['sha256']} for p, row in cfg['overlays'].items()}}
    assert result['preimage_inputs'] == cfg['preimage']
    assert result['payload_sha256'] == sha(payload)
    assert result['original_source_diff_sha256'] == cfg['original_diff_sha256']
    assert len(expected) == 32 and result['inputs_before'] == result['inputs_after'] == expected
    assert result['all_source_inventory_before_sha256'] == result['all_source_inventory_after_sha256'] == '4660754a78ccc0f78272e1786e1395672af41b7fc30a7e259c21eaf3950b7314'
    assert result['original_source_inventory_after_sha256'] == 'bbd03d6760a2ab9e584d8ea3cfc84a8804b4ec0f144742f0e1a51e9f46d061a1'
    commands = result['commands']
    common = ['/home/alex/.cargo/bin/cargo', None, '--locked', '--offline', '-j', '1',
              '-p', 'droidloom-pressure-relay', '-p', 'droidloom-supervisor']
    assert len(commands) == 2
    for index, (verb, tail) in enumerate([('build', ['--bins', '--message-format=json']),
                                        ('test', ['--lib', '--no-run', '--message-format=json'])]):
        argv = list(common); argv[1] = verb
        assert commands[index]['argv'] == argv + tail
        assert commands[index]['cwd'] == REMOTE + '/candidate'
        assert commands[index]['returncode'] == 0 and commands[index]['timed_out'] is False
        assert commands[index]['exact_child_pid'] > 0
    expected_sources = {
        'droidloomd': 'droidloom-supervisor/src/bin/droidloomd.rs',
        'droidloom-supervisor': 'droidloom-supervisor/src/main.rs',
        'droidloom-psi-owner': 'droidloom-pressure-relay/src/bin/droidloom_psi_owner.rs',
        'owned-ipc-controls': 'droidloom-pressure-relay/src/bin/owned_ipc_controls.rs',
    }
    assert set(result['artifacts']) == set(expected_sources)
    exact_artifacts = {
        'droidloomd': (6506304, '986cbe7dbe988a358706e29d41183a36f2c6967fa089cb1d82401ac130e47f19'),
        'droidloom-supervisor': (6540584, 'a89503e8b85ef55aea2324cd07b1d4a26fc028cb83aeed2d689167cf84b4d5a8'),
        'droidloom-psi-owner': (1305384, '57db1048e871addb63c5779625d7848b666857d5f28223269300c1c7ae3ba85b'),
        'owned-ipc-controls': (1595536, '861b35c9f341aede8d740e0699433fb68710fa073c4e66a60e42b27fbd756c27'),
    }
    assert {n: (row['bytes'], row['sha256']) for n, row in result['artifacts'].items()} == exact_artifacts
    for name, path in expected_sources.items():
        row = result['artifacts'][name]
        assert row['path'] == REMOTE + '/target/debug/' + name
        assert row['cargo_target_source'] == REMOTE + '/candidate/runtime/' + path
    assert {(r['target_name'], r['target_kind']) for r in result['compiled_test_artifacts']} == {
        ('droidloom_pressure_relay', 'lib'), ('droidloom_supervisor', 'lib')}
    assert len(result['compiled_test_artifacts']) == 2
    assert {row['target_name']: (row['bytes'], row['sha256']) for row in result['compiled_test_artifacts']} == {
        'droidloom_pressure_relay': (1981656, 'd68b0e32850b4f6538b5250340a234bc2c45c27451e4080a97db726ff7a09999'),
        'droidloom_supervisor': (7757336, '1c6679b1cb1a7322bb6a26958fe53386ce5dde225d38f63c028c66620c97a746'),
    }
    for row in list(result['artifacts'].values()) + result['compiled_test_artifacts']:
        assert row['bytes'] > 0 and row['inode'] > 0 and row['device'] > 0
        assert row['mode'] & 0o111 and not row['mode'] & 0o6022
        assert re.fullmatch('[0-9a-f]{64}', row['sha256'])
        assert row['cargo_package_id'].startswith('path+file://' + REMOTE + '/candidate/runtime/')
    health = result['resource_health']; before = health['before']; after = health['after']
    assert health['held_own_cgroup_gate_passed'] is True
    assert health['whole_invocation_resource_qualified'] is False and health['swap_zero_claimed'] is False
    assert before['cgroup_identity'] == after['cgroup_identity'] and before['namespaces'] == after['namespaces']
    assert before['limits'] == after['limits']
    assert after['limits']['memory.max'] == 1073741824 and after['limits']['cpu.max'] == [100000, 100000]
    assert after['memory_peak'] == 592470016 and after['memory_peak'] < after['limits']['memory.max']
    assert before['memory_swap_current'] == before['memory_swap_peak'] == after['memory_swap_current'] == after['memory_swap_peak'] == 0
    assert all(v == 0 for v in health['memory_event_delta'].values())
    assert result['test_binaries_executed'] is False and result['ordinary_controls_executed'] is False
    assert result['full_owner_runtime_qualified'] is False and result['android_runtime_started'] is False
    assert result['installed_files_changed'] is False and result['namespace_or_network_effects_requested'] is False
    template_raw = (FROZEN / 'ordinary-run-request-template.json').read_bytes()
    template = json.loads(template_raw)
    assert template['execution_ready'] is False
    request = copy.deepcopy(template['request_template'])
    assert request['args'][-1] == 'REQUIRES_ACTUAL_SUCCESSFUL_COMPILE_SHA256'
    request['args'][-1] = ACTUAL_SHA
    request['idempotency_key'] = 'p4-producer14-fixture01-ordinary01-' + ACTUAL_SHA[:16]
    source = (FROZEN / 'run.py').read_bytes()
    assert request['stdin'].encode() == source
    assert sha(source) == '9eef9bf99c688d128467c9962f7aec8d077a2e65b39042e3a1236f663cbe4ec4'
    ast.parse(source)
    back = copy.deepcopy(request)
    back['args'][-1] = template['request_template']['args'][-1]
    back['idempotency_key'] = template['request_template']['idempotency_key']
    assert back == template['request_template']
    request_raw = pretty(request)
    report = {
        'schema': 1, 'result': 'ACTUAL_MATCHING_COMPILE_VERIFIED_ORDINARY_NOT_SUBMITTED',
        'compile_receipt_sha256': ACTUAL_SHA, 'compile_receipt_bytes': len(raw),
        'exact_source_inputs_count': len(expected), 'full_source_inventory_unchanged': True,
        'compiled_binary_artifacts': result['artifacts'], 'compiled_library_test_artifacts': result['compiled_test_artifacts'],
        'actual_cargo_commands': commands, 'test_binaries_executed_during_compile': False,
        'resource': {'own_cgroup_gate_passed': True, 'memory_peak_bytes': after['memory_peak'],
            'memory_swap_limit': after['limits']['memory.swap.max'], 'memory_swap_observed_current_peak': [0, 0],
            'memory_event_delta': health['memory_event_delta'], 'whole_invocation_resource_qualified': False},
        'template_changed_fields_only': ['args[-1]', 'idempotency_key'],
        'run_source_sha256': sha(source), 'run_source_bytes': len(source),
        'request_sha256': sha(request_raw), 'request_bytes': len(request_raw),
        'expected_ordinary': {'relay_library': 37, 'supervisor_library': 122, 'IPC': 7,
            'public_retirement_targeted': 2, 'targeted_each_pass': 1, 'targeted_each_filtered': 36,
            'worker_context': True, 'actual_entry_ABI3': True},
        'ordinary_executed': False, 'actual_Owner_qualified': False, 'Hepta_called_by_this_script': False,
    }
    files = {
        'request.json': request_raw,
        'actual-compile-result.json': raw,
        'review.json': pretty(report),
        'template-to-bound.diff': ''.join(difflib.unified_diff(pretty(template['request_template']).decode().splitlines(True),
            request_raw.decode().splitlines(True), fromfile='producer14-template', tofile='producer14-bound')).encode(),
        'bind_ordinary14.py': Path(__file__).read_bytes(),
    }
    manifest = {'schema': 1, 'kind': 'producer14_actual_bound_ordinary01',
        'files': [{'path': n, 'bytes': len(b), 'sha256': sha(b)} for n,b in sorted(files.items())]}
    files['manifest.json'] = pretty(manifest)
    OUT.mkdir()
    for name, data in files.items():
        with (OUT / name).open('xb') as stream: stream.write(data)
    print(json.dumps({'root': str(OUT), 'request_bytes': len(request_raw), 'request_sha256': sha(request_raw),
        'stdin_bytes': len(source), 'stdin_sha256': sha(source), 'key': request['idempotency_key'],
        'manifest_sha256': sha(files['manifest.json']), 'review_bytes': len(files['review.json']),
        'review_sha256': sha(files['review.json'])}, indent=2))


if __name__ == '__main__': main()
