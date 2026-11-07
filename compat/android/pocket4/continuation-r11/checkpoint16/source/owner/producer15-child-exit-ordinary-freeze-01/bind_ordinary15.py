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
FROZEN = ROOT / 'producer15-child-exit-controller-freeze-01'
ACTUAL = ROOT.parent / 'root-recovery-20261104-02/evidence/owner15-compile01/compile-result.json'
OUT = ROOT / 'producer15-child-exit-ordinary-freeze-01'
ACTUAL_SHA = '3327495b8cc3302dcc18ac72a7495f88d3354788404d2b05d1194d1e6e89ee30'
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-child-exit-r11-build-15-01'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    assert not OUT.exists()
    raw = ACTUAL.read_bytes()
    assert len(raw) == 39999 and sha(raw) == ACTUAL_SHA
    result = json.loads(raw)
    terminal_raw = (ACTUAL.parent / 'status01.tool-original.json').read_bytes()
    terminal = json.loads(terminal_raw)
    assert terminal['job_id'] == '1a1ac964e6f-fc05-5590' and terminal['exit_code'] == 0
    assert terminal['state'] == 'succeeded' and terminal['output_complete'] is True
    assert terminal['output_durable'] is True and terminal['terminal_publication_confirmed'] is True
    assert terminal['timed_out'] is False and terminal['cancelled'] is False
    stdout_raw = (ACTUAL.parent / 'stdout.log').read_bytes()
    stdout = json.loads(stdout_raw)
    assert len(stdout_raw) == 363 and stdout['success'] is True and stdout['error'] is None
    assert stdout['report'] == REMOTE + '/compile-result.json'
    assert stdout['bytes'] == len(raw) and stdout['sha256'] == ACTUAL_SHA
    assert stdout['commands'] == 2 and stdout['test_binaries_executed'] is False
    assert stdout['full_owner_runtime_qualified'] is False
    assert (ACTUAL.parent / 'stderr.log').read_bytes() == b''
    for stream, count in [('stdout', len(stdout_raw)), ('stderr', 0)]:
        assert terminal['log_bytes'][stream] == {'seen': count, 'stored': count}
        assert terminal['log_synced'][stream] is True and terminal['log_truncated'][stream] is False
        assert terminal['log_errors'][stream] is None
    assert result['success'] is True and result['compile_only'] is True
    assert result['revision'] == 'producer15-namespace-child-exit01'
    assert result['candidate'] == REMOTE + '/candidate' and result['target'] == REMOTE + '/target'
    assert result['source_origin'] == '/home/alex/work/pocket4-supervisor-lmkd-fixture-r11-build-14-01/candidate'
    assert result['prior_build_receipt_sha256'] == 'a916592cc708dc76411b482a371214410bca4662f6ff72dccd5083d88872b6a6'
    manifest = (FROZEN / 'manifest.json').read_bytes()
    assert sha(manifest) == 'ebe67de541ba7766944aa19749c687b8a6966bd026a43fcb80e6e358b1b94634'
    for row in json.loads(manifest)['files']:
        data = (FROZEN / row['path']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
    payload = (FROZEN / 'payload.json').read_bytes()
    cfg = json.loads(payload)
    source_root = ROOT / 'namespace-child-exit-source-freeze-15'
    source_manifest_raw = (source_root / 'manifest.json').read_bytes()
    assert sha(source_manifest_raw) == cfg['source_manifest_sha256'] == 'a50606bd1352c885fe98a20733d340b565a87849413f579321e86e40fecc2634'
    source_manifest = json.loads(source_manifest_raw)
    for row in source_manifest['files']:
        content = (source_root / row['path']).read_bytes()
        assert len(content) == row['bytes'] and sha(content) == row['sha256']
    assert len(source_manifest['files']) == 17 and len(cfg['overlays']) == 4
    for path, row in cfg['overlays'].items():
        assert row['text'].encode() == (source_root / 'candidate' / path).read_bytes()
        assert len(row['text'].encode()) == row['bytes'] and sha(row['text'].encode()) == row['sha256']
    assert sha((source_root / 'source.diff').read_bytes()) == cfg['original_diff_sha256']
    prior_raw = (FROZEN / 'evidence/prior-actual-compile-result.json').read_bytes()
    assert sha(prior_raw) == result['prior_build_receipt_sha256']
    prior = json.loads(prior_raw)
    assert prior['inputs_after'] == cfg['preimage']
    expected = {**cfg['preimage'], **{p: {'bytes': row['bytes'], 'sha256': row['sha256']} for p, row in cfg['overlays'].items()}}
    assert result['preimage_inputs'] == cfg['preimage']
    assert result['payload_sha256'] == sha(payload)
    assert result['original_source_diff_sha256'] == cfg['original_diff_sha256']
    assert len(expected) == 32 and result['inputs_before'] == result['inputs_after'] == expected
    assert result['all_source_inventory_before_sha256'] == result['all_source_inventory_after_sha256'] == 'acd7a623dc28f83363d67aec1d4befe64c85cf852fa564312783005abc7a05b8'
    assert result['original_source_inventory_after_sha256'] == '4660754a78ccc0f78272e1786e1395672af41b7fc30a7e259c21eaf3950b7314'
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
        'droidloomd': (6537576, 'bc20f626a642bb488cbe519234c8c7fcc7d30949c1fdd2ec2a6eda6e5d86c3c3'),
        'droidloom-supervisor': (6562904, 'd8b99a077fc0595f983061b8b0835051ba171645ab65d1ffd6976e70a6e0a657'),
        'droidloom-psi-owner': (1327624, '1630cdb449bd52dc6e228575f18cfe88a20bec9bf6eaac87a0b043cb8aac8a35'),
        'owned-ipc-controls': (1616024, 'e9e1dff29096fda02be9510c0119ca4d242a100d7bac2ea47b37a10ca966321b'),
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
        'droidloom_pressure_relay': (2037000, 'f0f4082747f204fbab791b5f3c15d6aee4e0e052867c0520fc1c772b141fab59'),
        'droidloom_supervisor': (7866776, 'b73775d1edecfb36aa4bf5f8197b470a19a543030bf2ea6689ba442257b41805'),
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
    assert after['memory_peak'] == 739328000 and after['memory_peak'] < after['limits']['memory.max']
    assert before['memory_swap_current'] == before['memory_swap_peak'] == after['memory_swap_current'] == after['memory_swap_peak'] == 0
    assert all(v == 0 for v in health['memory_event_delta'].values())
    assert after['membership'] == before['membership'] == '0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-1a1ac964e6f-fc05-5590.service\n'
    assert result['uid'] == 1000 and result['pid'] == before['pid'] == after['pid'] == 2522414
    assert result['pid'] in before['direct_cgroup_procs'] and result['pid'] in after['direct_cgroup_procs']
    assert health['cgroup_files_written'] is False
    assert after['limits']['memory.swap.max'] == 'max' and after['limits']['pids.max'] == 30053
    assert result['barrier_constructor_executed'] is False
    assert result['test_binaries_executed'] is False and result['ordinary_controls_executed'] is False
    assert result['full_owner_runtime_qualified'] is False and result['android_runtime_started'] is False
    assert result['installed_files_changed'] is False and result['namespace_or_network_effects_requested'] is False
    template_raw = (FROZEN / 'ordinary-run-request-template.json').read_bytes()
    template = json.loads(template_raw)
    assert template['execution_ready'] is False
    request = copy.deepcopy(template['request_template'])
    assert request['args'][-1] == 'REQUIRES_ACTUAL_SUCCESSFUL_COMPILE_SHA256'
    request['args'][-1] = ACTUAL_SHA
    request['idempotency_key'] = 'p4-producer15-child-exit01-ordinary01-' + ACTUAL_SHA[:16]
    source = (FROZEN / 'run.py').read_bytes()
    assert request['stdin'].encode() == source
    assert sha(source) == '32f3875a20fb3da3bccf77235e77937c396881f024d9a457bb2a0a17634c0e94'
    ast.parse(source)
    back = copy.deepcopy(request)
    back['args'][-1] = template['request_template']['args'][-1]
    back['idempotency_key'] = template['request_template']['idempotency_key']
    assert back == template['request_template']
    request_raw = pretty(request)
    report = {
        'schema': 1, 'result': 'ACTUAL_MATCHING_COMPILE_VERIFIED_ORDINARY_NOT_SUBMITTED',
        'compile_receipt_sha256': ACTUAL_SHA, 'compile_receipt_bytes': len(raw),
        'authoritative_terminal': {'job_id': terminal['job_id'], 'state': terminal['state'], 'exit_code': terminal['exit_code'],
            'output_complete': True, 'output_durable': True, 'terminal_publication_confirmed': True,
            'source_path': str(ACTUAL.parent / 'status01.tool-original.json'),
            'bytes': len(terminal_raw), 'sha256': sha(terminal_raw)},
        'matching_stdout': {'source_path': str(ACTUAL.parent / 'stdout.log'),
            'bytes': len(stdout_raw), 'sha256': sha(stdout_raw)},
        'source_manifest_sha256': cfg['source_manifest_sha256'], 'source_payload_count': 17,
        'overlay_count': 4, 'controller_payload_count': len(json.loads(manifest)['files']),
        'compiled_children': {'exact_direct_children_waited': [row['exact_child_pid'] for row in commands],
            'both_returncode_zero': True, 'both_no_timeout': True,
            'complete_descendant_cleanup_claimed': False},
        'exact_source_inputs_count': len(expected), 'full_source_inventory_unchanged': True,
        'compiled_binary_artifacts': result['artifacts'], 'compiled_library_test_artifacts': result['compiled_test_artifacts'],
        'actual_cargo_commands': commands, 'test_binaries_executed_during_compile': False,
        'resource': {'own_cgroup_gate_passed': True, 'memory_peak_bytes': after['memory_peak'],
            'memory_swap_limit': after['limits']['memory.swap.max'], 'memory_swap_observed_current_peak': [0, 0],
            'memory_event_delta': health['memory_event_delta'], 'whole_invocation_resource_qualified': False},
        'template_changed_fields_only': ['args[-1]', 'idempotency_key'],
        'run_source_sha256': sha(source), 'run_source_bytes': len(source),
        'request_sha256': sha(request_raw), 'request_bytes': len(request_raw),
        'expected_ordinary': {'relay_library': 39, 'supervisor_library': 128, 'IPC': 7,
            'public_retirement_targeted': 2, 'targeted_each_pass': 1, 'targeted_each_filtered': 38,
            'worker_context': True, 'actual_entry_ABI3': True},
        'ordinary_executed': False, 'actual_Owner_qualified': False, 'Hepta_called_by_this_script': False,
    }
    files = {
        'request.json': request_raw,
        'actual-compile-result.json': raw,
        'review.json': pretty(report),
        'template-to-bound.diff': ''.join(difflib.unified_diff(pretty(template['request_template']).decode().splitlines(True),
            request_raw.decode().splitlines(True), fromfile='producer15-template', tofile='producer15-bound')).encode(),
        'bind_ordinary15.py': Path(__file__).read_bytes(),
    }
    manifest = {'schema': 1, 'kind': 'producer15_actual_bound_ordinary01',
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
