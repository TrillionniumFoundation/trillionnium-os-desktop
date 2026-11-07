#!/usr/bin/env python3
"""Read retained exact build receipts and bind the unchanged ordinary template."""
import ast, base64, copy, hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha(raw): return hashlib.sha256(raw).hexdigest()
def pin(raw): return {'bytes': len(raw), 'sha256': sha(raw)}
def enc(value): return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def read(relative, size, digest):
    raw = (ROOT / relative).read_bytes()
    assert pin(raw) == {'bytes': size, 'sha256': digest}, relative
    return raw, json.loads(raw)


def literals(path):
    out = {}
    for n in ast.parse(path.read_text()).body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            try: out[n.targets[0].id] = ast.literal_eval(n.value)
            except (ValueError, TypeError): pass
    return out


def health(value, maximum):
    assert value['held_own_cgroup_gate_passed'] and value['expected_memory_max'] == maximum
    before, after = value['before'], value['after']
    assert before['cgroup_identity'] == after['cgroup_identity']
    assert before['limits'] == after['limits']
    assert before['limits']['cpu.max'] == [100000, 100000]
    assert before['limits']['memory.max'] == maximum
    assert all(v == 0 for v in value['memory_event_delta'].values())
    assert all(after['memory_events'][k] == 0 for k in ('max', 'oom', 'oom_kill', 'oom_group_kill'))
    assert 0 < after['memory_peak'] < maximum and after['memory_swap_peak'] == 0
    assert value['cgroup_files_written'] is False
    # The source only measures until its final pre-receipt sample.
    assert value['whole_invocation_resource_qualified'] is False
    return {'memory_peak': after['memory_peak'], 'memory_swap_peak': 0,
            'events': value['memory_event_delta'], 'held_pre_receipt_gate': True,
            'outer_terminal_from_parent_dispatch_record': True}


def main():
    host_sha = 'dad36fe9fd79aa782bcc255e74b8cc1b1ee241a341318e179ccaa9e7f1c785ea'
    c_sha = '2c53bba3ab02b396d2698dfd6e04d870ce69cc55724c6077003dca81ae9a2e0b'
    host_raw, host = read('root-recovery-20261104-02/evidence/owner16-host-log-compile02/compile-result.json', 49729, host_sha)
    c_raw, c = read('root-recovery-20261104-02/evidence/owner16-android-log-build01/build-result.json', 661519, c_sha)
    host_root = ROOT / 'android-owner16-host-build-freeze02'
    source_root = ROOT / 'android-owner16-init-log-source-freeze01'
    p_raw = (host_root / 'payload.json').read_bytes(); payload = json.loads(p_raw)
    constants = literals(host_root / 'compile.py')
    assert host['success'] is True and host['compile_only'] is True and host['test_binaries_executed'] is False
    assert host['revision'] == 'producer16-bounded-init-log01' and host['uid'] == 1000
    assert host['payload_sha256'] == sha(p_raw)
    assert host['original_source_diff_sha256'] == sha((source_root / 'production.diff').read_bytes())
    assert host['preimage_inputs'] == payload['preimage'] and len(host['preimage_inputs']) == 32
    expected = copy.deepcopy(payload['preimage'])
    for name, row in payload['overlays'].items():
        assert pin(row['text'].encode()) == {k: row[k] for k in ('bytes', 'sha256')}
        assert (source_root / 'candidate' / name).read_bytes() == row['text'].encode()
        expected[name] = {k: row[k] for k in ('bytes', 'sha256')}
    assert len(expected) == 33 and host['inputs_before'] == host['inputs_after'] == expected
    assert host['all_source_inventory_before_sha256'] == host['all_source_inventory_after_sha256']
    assert host['prior_build_receipt_sha256'] == constants['PRIOR_RECEIPT_SHA']
    assert host['original_source_inventory_after_sha256'] == constants['PRIOR_INVENTORY_SHA']
    assert host['direct_toolchain_before'] == host['direct_toolchain_after']
    assert {p: {k: r[k] for k in ('bytes', 'sha256')} for p, r in host['direct_toolchain_before'].items()} == constants['DIRECT_TOOL_PINS']
    assert host['direct_versions_before'] == host['direct_versions_after'] == constants['DIRECT_TOOL_VERSIONS']
    assert host['direct_tool_authority']['observation_sha256'] == constants['DIRECT_TOOL_OBSERVATION_SHA']
    assert host['direct_tool_authority']['actual_builder_compile_sha256'] == constants['DIRECT_TOOL_ACTUAL_BUILD_SHA']
    assert host['direct_tool_authority']['rustup_proxy_executed'] is False
    assert host['direct_tool_authority']['tool_install_or_update_requested'] is False
    commands = host['commands']; assert len(commands) == 6
    assert all(x['returncode'] == 0 and x['timed_out'] is False and x['exact_child_pid'] > 0 for x in commands)
    cargo = constants['CARGO']; rustc = cargo.rsplit('/', 1)[0] + '/rustc'
    assert [x['argv'][:2] for x in commands] == [[cargo, '--version'], [rustc, '-vV'],
        [cargo, 'build'], [cargo, 'test'], [cargo, '--version'], [rustc, '-vV']]
    for i in (2, 3):
        assert all(flag in commands[i]['argv'] for flag in ('--locked', '--offline', '-j', '1'))
    assert '--no-run' in commands[3]['argv']
    for i, name in ((0, 'cargo'), (1, 'rustc'), (4, 'cargo'), (5, 'rustc')):
        assert commands[i]['stdout_excerpt'] == constants['DIRECT_TOOL_VERSIONS'][name]
        assert commands[i]['stderr_pin']['bytes'] == 0
    assert set(host['artifacts']) == {'droidloomd', 'droidloom-supervisor', 'droidloom-psi-owner', 'owned-ipc-controls'}
    assert {(r['target_name'], r['target_kind']) for r in host['compiled_test_artifacts']} == {
        ('droidloom_pressure_relay', 'lib'), ('droidloom_supervisor', 'lib')}
    assert len(host['compiled_test_artifacts']) == 2
    for row in list(host['artifacts'].values()) + host['compiled_test_artifacts']:
        assert Path(row['path']).is_relative_to(Path(host['target']) / 'debug')
        assert row['bytes'] > 0 and re.fullmatch('[0-9a-f]{64}', row['sha256']) and row['mode'] == 0o700
    for flag in ('android_runtime_started', 'barrier_constructor_executed', 'full_owner_runtime_qualified',
                 'installed_files_changed', 'namespace_or_network_effects_requested', 'ordinary_controls_executed'):
        assert host[flag] is False

    cfg = literals(ROOT / 'android-owner16-init-log-android-build-freeze01/build.py')['CFG']
    assert c['success'] is True and c['errors'] == [] and c['source_snapshot_reused'] is False
    assert c['kind'] == cfg['kind'] and c['root'] == cfg['root']
    for name in ('source_manifest_sha256', 'original_input_closure_sha256', 'prior_147_input_closure_sha256', 'new_dependency_receipt_sha256'):
        assert c[name] == cfg[name]
    assert c['source_manifest_sha256'] == sha((source_root / 'SOURCE_PINS.json').read_bytes())
    assert len(cfg['original_inputs']) == len(c['original_inputs_before']) == 149
    assert set(cfg['original_inputs']) == set(c['original_inputs_before'])
    assert all({k: c['original_inputs_before'][p][k] for k in ('bytes', 'sha256')} ==
               {k: row[k] for k in ('bytes', 'sha256')} for p, row in cfg['original_inputs'].items())
    assert len(c['source_before']) == len(cfg['payload']) == 9
    assert all({k: c['source_before'][p][k] for k in ('bytes', 'sha256')} ==
               {k: row[k] for k in ('bytes', 'sha256')} for p, row in cfg['payload'].items())
    assert c['all_inputs_unchanged'] and c['Android_actual_MD_equals_preflight'] and c['Android_input_count'] == 141
    assert len(cfg['non_MD_inputs']) == 8 and c['Android_needed'] == ['libc.so', 'libdl.so']
    assert len(c['commands']) == 19
    for command in c['commands']:
        assert command['returncode'] == 0 and command['timed_out'] is False and command['child_reaped'] is True
        for stream in ('stdout', 'stderr'):
            assert sha(command[stream].encode()) == command[stream + '_sha256']
        assert command['stderr'] == ''
    assert '--no-undefined' in ' '.join(c['commands'][2]['argv'])
    elf = c['commands'][3]['stdout']
    assert 'ELF64' in elf and 'DYN (Shared object file)' in elf and 'Advanced Micro Devices X86-64' in elf and 'INIT_ARRAY' in elf
    assert [(x['name'], x['passed']) for x in c['host_control_results']] == [
        ('protocol', 20), ('protocol-close-errno', 20), ('diagnostic', 7), ('cgroup-view', 8), ('init-log', 9)]
    log_control = json.loads(c['commands'][18]['stdout'])
    assert log_control['controls'] == 9 and log_control['assertions'] == 187 and log_control['success']
    assert log_control['kernel_logger_call'] == 'explicit fixture seam' and log_control['android_or_namespace_executed'] is False
    artifact = c['Android_artifact']
    assert artifact['path'] == cfg['root'] + '/libdroidloom_init_relay.so'
    assert {k: artifact[k] for k in ('bytes', 'sha256')} == {
        'bytes': 28488, 'sha256': '5d54b0eb58dc9e8e606a1538baa6403dd2eb22b588fdc60aac01d12198769f30'}
    for flag in ('Android_constructor_executed', 'Android_runtime_qualified', 'namespace_mount_or_pressure_executed', 'installed_files_changed'):
        assert c[flag] is False
    report = {'schema': 1, 'scope': 'Exact retained build receipts and source bindings; no ordinary or Owner/Android runtime qualification',
              'host': {'receipt': pin(host_raw), 'job_id': '1a1adaaadd5-fc05-5a93', 'commands': 6,
                       'source_inputs': 33, 'source_inventory_sha256': host['all_source_inventory_before_sha256'],
                       'direct_toolchain_before_after_equal': True, 'direct_versions_before_after_equal': True,
                       'compiler_runtime_libraries_not_rehashed': True, 'artifacts': host['artifacts'],
                       'compiled_test_artifacts': host['compiled_test_artifacts'], 'resources': health(host['resource_health'], 1024**3)},
              'android_c': {'receipt': pin(c_raw), 'job_id': '1a1ada90de9-fc05-5a8f', 'commands': 19,
                            'input_closure': 149, 'exact_MD_count': 141, 'sources': 9,
                            'artifact': artifact, 'needed': c['Android_needed'], 'host_control_counts': [20, 20, 7, 8, 9],
                            'new_control_assertions': 187, 'kernel_logger_is_fixture_seam': True,
                            'resources': health(c['resource_health'], 512 * 1024**2)},
              'source_tool_artifact_binding_passed': True, 'ordinary_controls_passed': False,
              'logger_actual_definition_or_runtime_abi_qualified': False, 'owner_runtime_qualified': False}
    out = ROOT / 'android-owner16-builds-actual-review01'; out.mkdir(exist_ok=False)
    (out / 'review.json').write_bytes(enc(report)); (out / 'review_actual_builds.py').write_bytes(Path(__file__).read_bytes())
    manifest = {p.name: pin(p.read_bytes()) for p in out.iterdir() if p.is_file()}
    (out / 'SOURCE_PINS.json').write_bytes(enc(manifest))

    template_path = host_root / 'ordinary-run-request-template.json'
    template = json.loads(template_path.read_text())['request_template']
    request = copy.deepcopy(template)
    assert request['stdin'].encode() == (host_root / 'run.py').read_bytes()
    request['args'][-1] = host_sha
    request['idempotency_key'] = 'p4-producer16-init-log01-ordinary02-' + host_sha[:16]
    assert {k for k in template if template[k] != request[k]} == {'args', 'idempotency_key'}
    frozen = ROOT / 'android-owner16-host-ordinary-freeze01'; frozen.mkdir(exist_ok=False)
    (frozen / 'request.json').write_bytes(enc(request))
    (frozen / 'stdin.py').write_text(request['stdin'])
    binding = {'schema': 1, 'request_source_template': pin(template_path.read_bytes()),
               'exact_compile_receipt': pin(host_raw), 'compile_receipt_path': host['candidate'].rsplit('/', 1)[0] + '/compile-result.json',
               'only_request_fields_changed': ['args[-1]', 'idempotency_key'],
               'actual_review': pin((out / 'review.json').read_bytes()),
               'root_dispatch_required': True, 'executed': False, 'owner_runtime_allowed': False,
               'scope': '39 relay/136 supervisor library tests, two exact public retirement tests, seven IPC, worker context and ABI3'}
    (frozen / 'binding.json').write_bytes(enc(binding))
    (frozen / 'SOURCE_PINS.json').write_bytes(enc({p.name: pin(p.read_bytes()) for p in frozen.iterdir() if p.is_file()}))
    print(json.dumps({'review': pin((out / 'review.json').read_bytes()),
                      'ordinary_root': str(frozen), 'request': pin((frozen / 'request.json').read_bytes()),
                      'stdin': pin((frozen / 'stdin.py').read_bytes()), 'key': request['idempotency_key']}))


if __name__ == '__main__': main()
