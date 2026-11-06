#!/usr/bin/env python3
"""Local, create-only Owner16 binder. Requires an external actual ordinary receipt.

This program does not import the six runtime modules, contact a device, or run
preparation/runtime. No executable package is produced without the supplied
ordinary bytes, full SHA and successful exact compile/artifact/source chain.
"""
import argparse
import ast
import base64
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / 'lmkd-recovery-20261105-01/owner15-normal01-freeze-01'
CORE = ROOT / 'android-owner16-init-log-source-freeze01'
HOST = ROOT / 'android-owner16-host-build-freeze02'
ANDROID = ROOT / 'android-owner16-init-log-android-build-freeze01'
CONSUMER = ROOT / 'android-owner16-runtime-log-bounds-source-freeze02'
REVIEW = ROOT / 'android-owner16-builds-actual-review01'
EVIDENCE = ROOT / 'root-recovery-20261104-02/evidence'
OUT = ROOT / 'android-owner16-normal01-freeze-01'
OLD_PREFIX = 'p4-owner15-normal-20261105-01'
PREFIX = 'p4-owner16-normal-20261105-01'
OLD_KIND = 'owned-real-producer15-normal01-namespace-child-exit01'
KIND = 'owned-real-producer16-normal01-bounded-init-log01'
SCOPE = 'REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT'
REVISION = 'producer16-bounded-init-log01'
BUILD_ROOT = '/home/alex/work/pocket4-supervisor-lmkd-init-log-r11-build-16-02'
SOURCE_NAMES = ('actor.py', 'coordinator.py', 'prepare.py', 'owned.py', 'pinned_support.py', 'qualify.py')
HOST_SHA = 'dad36fe9fd79aa782bcc255e74b8cc1b1ee241a341318e179ccaa9e7f1c785ea'
ANDROID_SHA = '2c53bba3ab02b396d2698dfd6e04d870ce69cc55724c6077003dca81ae9a2e0b'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    # Preserve insertion order for the reviewed CellSpec declaration order.
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def pinned(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    raw.decode('utf-8')
    return raw, json.loads(raw)


def manifest(directory, name, digest, count):
    raw = (directory / name).read_bytes()
    assert sha(raw) == digest, str(directory)
    value = json.loads(raw)
    rows = value.get('files', value)
    if isinstance(rows, list):
        assert len(rows) == len({row['path'] for row in rows})
        rows = {row['path']: row for row in rows}
    assert isinstance(rows, dict) and len(rows) == count
    for relative, row in rows.items():
        assert not Path(relative).is_absolute() and '..' not in Path(relative).parts
        body = (directory / relative).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256'], relative
        body.decode('utf-8')
    return raw


def file_record(path, raw):
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def literals(path):
    result = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return result


def resource_gate(report, memory_max):
    health = report['resource_health']
    assert health['held_own_cgroup_gate_passed'] is True
    assert health['expected_cpu_count'] == 1 and health['expected_memory_max'] == memory_max
    assert health['cgroup_files_written'] is False
    assert health['whole_invocation_resource_qualified'] is False
    assert health['swap_zero_claimed'] is False
    assert all(value == 0 for value in health['memory_event_delta'].values())
    before, after = health['before'], health['after']
    for key in ('membership', 'cgroup_identity', 'mount_identity', 'namespaces', 'limits', 'pid'):
        assert before[key] == after[key], key
    for observation in (before, after):
        assert observation['limits']['cpu.max'] == [100000, 100000]
        assert observation['limits']['memory.max'] == memory_max
        assert observation['limits']['memory.swap.max'] == 'max'
        assert observation['memory_swap_current'] == observation['memory_swap_peak'] == 0
        assert observation['memory_peak'] < memory_max
    return {'memory_peak': after['memory_peak'], 'memory_max': memory_max,
            'observed_swap_current_and_peak_zero': True, 'memory_swap_max': 'max',
            'pids_max': after['limits']['pids.max'], 'all_memory_event_deltas_zero': True,
            'whole_invocation_resource_qualified': False}


def fixed_guard(sources, name, message):
    tree = ast.parse(sources[name]['content'])
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and node.func.attr == 'need'
               and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
               and node.args[1].value == message]
    assert len(matches) == 1
    return compile(ast.fix_missing_locations(ast.Expression(matches[0].args[0])), '<fixed-source-guard>', 'eval')


def bind_ordinary(raw, ordinary, host, expected_inputs):
    assert ordinary['success'] is True and ordinary.get('error') is None
    assert ordinary['revision'] == REVISION and ordinary['ordinary_controls_only'] is True
    assert ordinary['external_compile_sha256'] == HOST_SHA and ordinary['cargo_invoked'] is False
    assert ordinary['inputs_before'] == ordinary['inputs_after'] == expected_inputs
    assert ordinary['all_source_inventory_before_sha256'] == ordinary['all_source_inventory_after_sha256'] == host['all_source_inventory_before_sha256']
    assert ordinary['rust_tests_passed'] == {'droidloom-pressure-relay': 39, 'droidloom-supervisor': 136}
    assert ordinary['rust_test_binary_counts'] == {'droidloom_pressure_relay:lib': 39, 'droidloom_supervisor:lib': 136}
    assert ordinary['ordinary_ipc_passed'] == 7 and ordinary['worker_context_passed'] is True
    assert ordinary['actual_compiled_entry_abi_passed'] is True
    for name in ('full_owner_runtime_qualified', 'real_broker_generation_qualified', 'android_runtime_started',
                 'barrier_constructor_executed', 'pressure_or_namespace_effects_requested', 'installed_files_changed', 'main_fence_claimed'):
        assert ordinary[name] is False, name
    constants = literals(HOST / 'run.py')
    targets = ordinary['targeted_public_retirement_controls']
    assert len(targets) == 2 and [row['name'] for row in targets] == constants['TARGETED_TESTS']
    for row in targets:
        assert row['passed'] == 1 and row['filtered_out'] == 38
        assert row['failed'] == row['ignored'] == row['measured'] == 0
    tests = {row['target_name']: row for row in host['compiled_test_artifacts']}
    expected_artifacts = [tests['droidloom_pressure_relay']] * 3 + [tests['droidloom_supervisor']]
    expected_artifacts += [host['artifacts']['owned-ipc-controls']] * 2 + [host['artifacts']['droidloom-supervisor']]
    arguments = [['--exact', name, '--test-threads=1', '--nocapture'] for name in constants['TARGETED_TESTS']]
    arguments += [['--test-threads=1'], ['--test-threads=1'], [], ['--worker-context-control'], ['relay-entry-abi']]
    assert len(ordinary['commands']) == len(expected_artifacts) == len(arguments) == 7
    for command, artifact, argv in zip(ordinary['commands'], expected_artifacts, arguments):
        assert command['returncode'] == 0 and command['timed_out'] is False and command['exact_child_pid'] > 0
        assert command['actual_held_elf'] == {key: artifact[key] for key in ('path', 'bytes', 'sha256', 'device', 'inode', 'mode')}
        assert re.fullmatch('/proc/self/fd/[0-9]+', command['argv'][0]) and command['argv'][1:] == argv
    return {'receipt_sha256': sha(raw), 'commands': 7, 'compiled_source_inputs': len(expected_inputs),
            'tests': ordinary['rust_tests_passed'], 'IPC': 7, 'targeted_retirement': targets,
            'resources': resource_gate(ordinary, 536870912), 'Owner_or_Android_runtime_qualified': False}


def sources16():
    replacements = [(OLD_KIND, KIND), (OLD_PREFIX, PREFIX),
                    ('owner15-normal-preparation01', 'owner16-normal-preparation01'),
                    ('owner15-real-normal01', 'owner16-real-normal01'),
                    ('actual producer15 cell', 'actual producer16 cell')]
    sources, rows, difference = {}, [], ''
    for name in SOURCE_NAMES:
        old = (OLD / 'source' / name).read_text()
        candidate = CONSUMER / 'candidate' / name
        base = candidate.read_text() if candidate.exists() else old
        new = base
        for before, after in replacements:
            new = new.replace(before, after)
        reverse = new
        for before, after in reversed(replacements):
            reverse = reverse.replace(after, before)
        assert reverse == base, name
        if name in ('pinned_support.py', 'qualify.py'):
            assert new == old
        ast.parse(new); compile(new, name, 'exec')
        raw = new.encode()
        sources[name] = {'bytes': len(raw), 'sha256': sha(raw), 'content': new}
        rows.append({'path': name, 'owner15_sha256': sha(old.encode()), 'consumer_candidate_sha256': sha(base.encode()),
                     'new_sha256': sha(raw), 'new_bytes': len(raw), 'reverse_profile_literals_exact': True,
                     'behavioral_delta_is_frozen_consumer_only': True, 'unchanged': new == old})
        difference += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                            fromfile='owner15/source/' + name, tofile='owner16/source/' + name))
    assert sources['coordinator.py']['bytes'] == 14404
    return sources, rows, difference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ordinary', type=Path, required=True)
    parser.add_argument('--ordinary-bytes', type=int, required=True)
    parser.add_argument('--ordinary-sha256', required=True)
    args = parser.parse_args()
    assert 1 <= args.ordinary_bytes <= 256 * 1024 and re.fullmatch('[0-9a-f]{64}', args.ordinary_sha256)
    assert not OUT.exists(), 'create-only freeze already exists'
    old_manifest = manifest(OLD, 'manifest.json', 'c2bbf0f68b954956f229bb4c2490ed8979fc4951f1a8c397cb0228e6513ac164', 30)
    core_manifest = manifest(CORE, 'SOURCE_PINS.json', 'c5afbb0a61653f5fa554ef42cd68f77e71a38893b229151d2b685b5e2d032050', 31)
    host_manifest = manifest(HOST, 'manifest.json', '7e87f1412f11295609bfa39cba002c5feaf4a4d75faaa6101f5f33470ef2d547', 14)
    android_manifest = manifest(ANDROID, 'SOURCE_PINS.json', '1025ea56ef9aec6fe632f07c171575a4b1920da9dd87177da7bf5e9d5ffce064', 13)
    consumer_manifest = manifest(CONSUMER, 'SOURCE_PINS.json', '1a72b0e2d06584344f64c08a94d21d8be27f90e56efadeab370ff51f00d87484', 23)
    review_manifest = manifest(REVIEW, 'SOURCE_PINS.json', '0159f86f0f7a8968aa27566b6be559705a509dd2306ae5dda0b3a3f83aa77b15', 2)
    review_raw, review = pinned(REVIEW / 'review.json', 6662, '28dc031f9c7c8918ecf575c8338eece226946078ebf9fef7e4803637fb5f18f9')
    old_plan_raw, old_plan = pinned(OLD / 'plan.json', 75683, 'cf1d859b47518e356ca63663de1933f06aefe30aea1f130435aef4305aaa1c79')
    host_path = EVIDENCE / 'owner16-host-log-compile02/compile-result.json'
    android_path = EVIDENCE / 'owner16-android-log-build01/build-result.json'
    host_raw, host = pinned(host_path, 49729, HOST_SHA)
    android_raw, android = pinned(android_path, 661519, ANDROID_SHA)
    ordinary_raw, ordinary = pinned(args.ordinary, args.ordinary_bytes, args.ordinary_sha256)
    assert review['source_tool_artifact_binding_passed'] is True
    assert review['host']['receipt'] == {'bytes': len(host_raw), 'sha256': sha(host_raw)}
    assert review['android_c']['receipt'] == {'bytes': len(android_raw), 'sha256': sha(android_raw)}
    assert host['success'] is True and android['success'] is True
    assert host['artifacts'] == review['host']['artifacts'] and host['compiled_test_artifacts'] == review['host']['compiled_test_artifacts']
    assert android['Android_artifact'] == review['android_c']['artifact']
    assert host['candidate'] == BUILD_ROOT + '/candidate' and host['target'] == BUILD_ROOT + '/target'
    payload_raw = (HOST / 'payload.json').read_bytes(); payload = json.loads(payload_raw)
    assert host['payload_sha256'] == sha(payload_raw) and payload['source_manifest_sha256'] == sha(core_manifest)
    assert host['original_source_diff_sha256'] == sha((CORE / 'production.diff').read_bytes())
    expected_inputs = copy.deepcopy(payload['preimage'])
    for relative, row in payload['overlays'].items():
        body = (CORE / 'candidate' / relative).read_bytes()
        assert row['text'].encode() == body and row['bytes'] == len(body) and row['sha256'] == sha(body)
        expected_inputs[relative] = {key: row[key] for key in ('bytes', 'sha256')}
    assert len(expected_inputs) == 33 and host['inputs_before'] == host['inputs_after'] == expected_inputs
    assert host['all_source_inventory_before_sha256'] == host['all_source_inventory_after_sha256'] == review['host']['source_inventory_sha256']
    ordinary_binding = bind_ordinary(ordinary_raw, ordinary, host, expected_inputs)

    prior_path = EVIDENCE / 'owner15-normal01-runtime-read01/runtime-result.json'
    prior_raw, prior = pinned(prior_path, 59461, '6d35b126c24604d373175479c9bc69e0246a45c05f2061bb8f8077399f0926d5')
    prior_review_path = ROOT / 'android-owner15-runtime-failure-actual-review-01/review.json'
    prior_review_raw, prior_review = pinned(prior_review_path, 6273, 'df2d3e37b94c47986f28fd457b96064bef780b8197eed341f432dea90fc6d5b7')
    assert prior['success'] is False and prior['attempt_nonce'] == old_plan['attempt_nonce']
    assert prior['main_before'] == prior['main_before_gate'] == prior['main_after']
    assert all(prior['exact_unit_cleanup'][key] is True for key in ('cgroup_absent', 'original_actor_dead', 'unit_not_found'))
    assert prior_review['runtime_result'] == 'FAIL_PRESERVED_BEFORE_ACTIVE'
    assert prior_review['checks']['ACTIVE_event_present'] is False
    assert prior_review['broker_receipt_boundaries']['incomplete'] is True
    assert prior_review['broker_receipt_boundaries']['faulted'] is True

    def remap(value):
        if isinstance(value, str):
            return value.replace(OLD_PREFIX, PREFIX)
        if isinstance(value, list):
            return [remap(item) for item in value]
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        return value

    plan = remap(old_plan)
    attempt = os.urandom(32).hex()
    assert attempt != old_plan['attempt_nonce'] and attempt != '0' * 64
    plan.update(kind=KIND, scope=SCOPE, attempt_nonce=attempt, description='Pocket4 Owner16 bounded init log NORMAL01 ' + attempt)
    plan['spec']['host_uid'] = 61288
    plan['spec']['subordinate_uids']['start'] = 22000000
    plan['spec']['subordinate_gids']['start'] = 22000000
    plan['spec']['runtime_dir'] = '/run/droidloom/cells/u61288'
    for role in ('droidloomd', 'droidloom-supervisor', 'droidloom-psi-owner'):
        row = copy.deepcopy(host['artifacts'][role])
        assert row['path'] == BUILD_ROOT + '/target/debug/' + role
        assert row['bytes'] > 0 and row['inode'] > 0 and row['mode'] == 0o700
        row['destination'] = old_plan['artifacts'][role]['destination']
        plan['artifacts'][role] = row
    barrier = {key: android['Android_artifact'][key] for key in ('path', 'bytes', 'sha256', 'device', 'inode')}
    barrier.update(mode=stat.S_IMODE(android['Android_artifact']['mode']), destination='lib/libdroidloom_init_relay.so')
    assert barrier['mode'] == 0o700
    plan['artifacts']['init-barrier'] = barrier
    relay = plan['spec']['pressure_relay']
    for name, role in (('broker', 'droidloom-psi-owner'), ('entry_supervisor', 'droidloom-supervisor'), ('init_barrier', 'init-barrier')):
        relay[name]['sha256'] = plan['artifacts'][role]['sha256']
    plan['actual_compile_receipt'] = file_record(host_path, host_raw)
    plan['actual_ordinary_receipt_sha256'] = sha(ordinary_raw)
    plan['projection_build_receipt_sha256'] = sha(android_raw)
    plan['paired_projection_source_manifest_sha256'] = sha(core_manifest)
    plan['earlier_failure_chain'] = {'earlier': copy.deepcopy(old_plan['earlier_failure_chain']), 'previous': copy.deepcopy(old_plan['predecessor_failure'])}
    plan['predecessor_failure'] = {
        'runtime_sha256': sha(prior_raw), 'attempt_nonce': old_plan['attempt_nonce'], 'replayed': False,
        'observed_boundary': 'ABI3 HELLO/PROJECTED/COMMIT/DONE reached, namespace-owner wait SIGHUP before ACTIVE, failed broker receipt retained',
        'outer_exact_cleanup_passed': True, 'old_broker_receipt_faulted_and_incomplete': True,
        'normal_owner_runtime_qualified': False, 'cause_review_sha256': sha(prior_review_raw),
        'specific_relative_name_observed': 'ns/pid_for_children',
        'namespace_open_failure_implies_init_death': False, 'post_error_poll_zero_proves_healthy_init': False,
        'guest_boot_first_cause_proved': False, 'sighup_sender_proved': False,
        'old_failure_not_reclassified': True}
    plan['bounded_init_log_source_manifest_sha256'] = sha(core_manifest)
    plan['bounded_init_log_consumer_manifest_sha256'] = sha(consumer_manifest)
    plan['bounded_init_log_contract'] = {
        'scope': 'one generation-private bounded prefix; diagnostic evidence only',
        'paired_entry_abi': 'droidloom-relay-entry-v3', 'protocol_abi': 3, 'private_fd': 202,
        'capture_capacity_bytes': 262144, 'hex_max_bytes': 524288,
        'generic_response_non_log_bytes_max': 262144, 'lifecycle_response_wire_bytes_max': 1048576,
        'actor_non_log_bytes_max': 1048576, 'actor_result_bytes_max': 4194304,
        'actor_fixed_log_occurrences_max': 6, 'full_runtime_readback_bytes_max': 5242880,
        'both_actual_generation_markers_required_before_broker_start': True,
        'marker_or_capture_failure_is_not_retried': True,
        'failed_capture_fields_preserved_as_diagnostic_data_not_success': True,
        'library_definition_and_runtime_cache_behavior_qualified_before_this_attempt': False,
        'stream_complete_claimed': False, 'exact_writer_attribution_for_every_line_claimed': False,
        'global_kernel_log_fallback': False, 'identity_handshake_retirement_gates_relaxed': False}
    plan['status'] = 'SOURCE_FROZEN_PREPARE_AND_RUNTIME_NOT_SUBMITTED'
    for key in ('main', 'base', 'presenter', 'tools_fixed_paths', 'tools_sha256', 'outer_limits',
                'runtime_max_seconds', 'controller_timeout_seconds', 'helper_uid', 'helper_gid',
                'mem_available_min_bytes', 'host_memory_full_avg10_max', 'disk_available_min_bytes',
                'data_images', 'control_socket', 'scope', 'init_protocol_abi', 'entry_abi',
                'mechanism_evidence', 'cgroup_mount_mechanism_evidence', 'main_budget_restoration_evidence'):
        assert plan[key] == old_plan[key], key
    assert plan['artifacts']['lmkd'] == old_plan['artifacts']['lmkd']
    assert plan['spec']['denial_socket'] == old_plan['spec']['denial_socket']
    assert all(plan[key] is False for key in ('production_ready', 'installed_owner_qualified', 'rc_property_reload_qualified', 'pressure_effect_qualified', 'app_qualified'))
    for key in ('memory_max_bytes', 'memory_high_bytes', 'memory_swap_max_bytes', 'cpu_quota_us',
                'cpu_period_us', 'tasks_max', 'entry_timeout_ms', 'bootstrap_timeout_ms', 'lmkd_uid', 'lmkd_gid',
                'init_sha256', 'init_linker_sha256', 'lmkd_rc_sha256', 'compat_preload_sha256'):
        assert relay[key] == old_plan['spec']['pressure_relay'][key], key
    rust = ROOT / 'lmkd-recovery-20261105-01/producer07-audit-freeze-02/source/runtime/droidloom-supervisor/src'

    def fields(path, name, relative):
        raw = path.read_bytes()
        assert expected_inputs[relative] == {'bytes': len(raw), 'sha256': sha(raw)}
        body = re.search(r'pub struct ' + name + r'\s*\{(.*?)^\}', raw.decode(), re.S | re.M)[1]
        return re.findall(r'^\s*pub\s+(\w+)\s*:', body, re.M)

    spec_fields = fields(rust / 'lib.rs', 'CellSpec', 'runtime/droidloom-supervisor/src/lib.rs')
    assert list(plan['spec']) == [key for key in spec_fields if key in plan['spec']]
    policy = rust / 'relay_lifecycle/policy.rs'
    relative = 'runtime/droidloom-supervisor/src/relay_lifecycle/policy.rs'
    assert list(relay) == fields(policy, 'PressureRelaySpec', relative)
    for name in ('broker', 'entry_supervisor', 'lmkd', 'init_barrier'):
        assert list(relay[name]) == fields(policy, 'RelayArtifact', relative)
    canonical = json.dumps(plan['spec'], ensure_ascii=False, separators=(',', ':')).encode()
    plan['canonical_spec_sha256'] = sha(canonical)
    sources, source_rows, source_diff = sources16()
    profile_guard = fixed_guard(sources, 'prepare.py', 'wrong fixed profile')
    path_guard = fixed_guard(sources, 'coordinator.py', 'this controller accepts only its fixed fresh unit/package/state')
    cases = [('new_profile', profile_guard, plan, True), ('new_paths', path_guard, plan, True),
             ('old_kind_rejected', profile_guard, {**plan, 'kind': OLD_KIND}, False),
             ('short_nonce_rejected', profile_guard, {**plan, 'attempt_nonce': '12' * 31}, False)]
    cases += [('old_' + key + '_rejected', path_guard, {**plan, key: old_plan[key]}, False) for key in ('unit', 'package', 'state')]
    checks = []
    for name, code, candidate, expected in cases:
        accepted = eval(code, {'__builtins__': {}, 'len': len}, {'plan': candidate})
        assert accepted is expected, name
        checks.append({'case': name, 'accepted': accepted})
    plan_raw = pretty(plan)
    packet = json.dumps({'plan_utf8': plan_raw.decode(), 'sources': sources}, ensure_ascii=False, separators=(',', ':')).encode()
    prepare_template = (OLD / 'requests/prepare-template.py').read_text()
    prepare_stdin = prepare_template.replace('__PACKET_SHA256__', repr(sha(packet))).replace('__PACKET_BASE64__', repr(base64.b64encode(packet).decode()))
    ast.parse(prepare_stdin)
    request = json.loads((OLD / 'requests/prepare-request.json').read_bytes())
    request.update(stdin=prepare_stdin, idempotency_key='p4-owner16-normal01-prepare01-' + sha(prepare_stdin.encode())[:16])
    old_coordinator = (OLD / 'source/coordinator.py').read_bytes()
    runtime = (OLD / 'requests/runtime-stdin-template.py').read_text().replace(OLD_PREFIX, PREFIX)
    runtime = runtime.replace(sha(old_coordinator), sources['coordinator.py']['sha256'])
    runtime = runtime.replace('SOURCE_BYTES = ' + str(len(old_coordinator)), 'SOURCE_BYTES = ' + str(sources['coordinator.py']['bytes']))
    ast.parse(runtime)
    assert runtime.count('__ACTUAL_PREPARED_SHA256__') == 1
    runtime_request = json.loads((OLD / 'requests/runtime-request-template.json').read_bytes())
    runtime_request.update(stdin=runtime, idempotency_key='p4-owner16-normal01-runtime01-__ACTUAL_PREPARED_SHA256_PREFIX16__')
    for name, new in [('prepare-request.json', request), ('runtime-request-template.json', runtime_request)]:
        old = json.loads((OLD / 'requests' / name).read_bytes())
        assert {k: v for k, v in new.items() if k not in ('stdin', 'idempotency_key')} == {k: v for k, v in old.items() if k not in ('stdin', 'idempotency_key')}
    wrapper_constants = {}
    for node in ast.parse(prepare_stdin).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('PACKET_SHA256', 'PACKET_BASE64'):
            wrapper_constants[node.targets[0].id] = ast.literal_eval(node.value)
    decoded = base64.b64decode(wrapper_constants['PACKET_BASE64'], validate=True)
    assert decoded == packet and wrapper_constants['PACKET_SHA256'] == sha(packet)
    assert json.loads(decoded) == {'plan_utf8': plan_raw.decode(), 'sources': sources}

    files = {}
    def put(name, raw):
        raw = raw.encode() if isinstance(raw, str) else raw
        raw.decode('utf-8')
        assert name not in files and not Path(name).is_absolute() and '..' not in Path(name).parts
        files[name] = raw

    put('plan.json', plan_raw); put('cell.json', canonical)
    for name, row in sources.items():
        put('source/' + name, row['content'])
    put('source.diff', source_diff)
    put('plan.diff', ''.join(difflib.unified_diff(old_plan_raw.decode().splitlines(True), plan_raw.decode().splitlines(True), fromfile='owner15/plan.json', tofile='owner16/plan.json')))
    put('requests/prepare-template.py', prepare_template); put('requests/prepare-stdin.py', prepare_stdin)
    put('requests/prepare-request.json', pretty(request)); put('requests/runtime-stdin-template.py', runtime)
    put('requests/runtime-request-template.json', pretty(runtime_request))
    for name, raw in [('owner15-normal-manifest.json', old_manifest), ('owner16-core-manifest.json', core_manifest),
                      ('owner16-host-manifest.json', host_manifest), ('owner16-android-build-manifest.json', android_manifest),
                      ('owner16-consumer-manifest.json', consumer_manifest), ('actual-build-review-manifest.json', review_manifest)]:
        put('lineage/' + name, raw)
    put('evidence/actual-builds-review.json', review_raw)
    put('evidence/actual-ordinary.json', ordinary_raw)
    put('evidence/owner15-failure-review.json', prior_review_raw)
    put('freeze_normal16.py', Path(__file__).read_bytes())
    put('source-profile-review.json', pretty({'schema': 1, 'sources': source_rows,
        'fixed_guard_expression_checks': checks, 'unchanged_sources': ['pinned_support.py', 'qualify.py'],
        'consumer_diff_sha256': sha((CONSUMER / 'consumer.diff').read_bytes()),
        'no_runtime_module_imported_or_executed': True}))
    admission = {'schema': 1, 'kind': 'owner16_normal01_actual_source_binding', 'prepare_submitted': False, 'runtime_submitted': False,
        'host_compile': file_record(host_path, host_raw), 'android_compile': file_record(android_path, android_raw),
        'ordinary': file_record(args.ordinary, ordinary_raw), 'ordinary_binding': ordinary_binding,
        'source_manifest_sha256': sha(core_manifest), 'consumer_manifest_sha256': sha(consumer_manifest),
        'prior_owner15_failure': file_record(prior_path, prior_raw), 'prior_failure_not_reclassified': True,
        'artifacts_bound_to_actual_builds': 5, 'LMKD_artifact_unchanged': True, 'base86_unchanged': True,
        'old_mount_mechanism_observation_not_new_paired_runtime_qualification': True,
        'Main_object_equals_original15': True, 'Main_guard_and_original12288_limits_unchanged': True,
        'fresh_live_Main_ID_resource_and_file_absence_checks_still_required': True,
        'new_attempt_nonce': attempt, 'synthetic_uid': 61288, 'subordinate_start': 22000000, 'subordinate_count': 100000,
        'live_UID_subid_absence_not_observed_by_this_binder': True,
        'Rust_field_order_verified_against_actual_unchanged_inputs': True,
        'canonical_spec_sha256': sha(canonical), 'published_plan_sha256': sha(plan_raw),
        'expected_prepared_serialized_plan_sha256': sha((json.dumps(plan, sort_keys=True, indent=2) + '\n').encode()),
        'prepare_packet_bytes': len(packet), 'prepare_packet_sha256': sha(packet),
        'prepare_stdin_bytes': len(prepare_stdin.encode()), 'prepare_stdin_sha256': sha(prepare_stdin.encode()),
        'prepare_request_bytes': len(files['requests/prepare-request.json']), 'prepare_request_sha256': sha(files['requests/prepare-request.json']),
        'idempotency_key': request['idempotency_key'], 'prepare_wrapper_unchanged': True,
        'only_request_stdin_and_key_changed': True, 'runtime_template_requires_external_actual_prepared_digest': True,
        'runtime_resource_window_dispatch_is_Root_only': True, 'init_logger_actual_runtime_qualified': False,
        'production_ready': False, 'app_qualified': False, 'no_remote_action_by_this_binder': True}
    put('ACTUAL-ADMISSION-REVIEW.json', pretty(admission))
    put('README.md', '''# Owner16 NORMAL01 bounded init log candidate

This fresh create-only package consumes exact actual Host16 compile, 39 relay /
136 supervisor library tests, two public retirement tests, seven IPC controls,
worker context, ABI3 and paired C16 build receipts. The five copied artifacts are
three Host16 binaries, unchanged LMKD r6, and the actual C16 barrier DSO. The
compiled IPC/test binaries are admission evidence, not extra copied artifacts.

The new private memfd prefix has a 256 KiB fixed capacity. The paired constructor
must write both real generation-bound KernelLogger markers through that channel
and the held host reader must observe them before broker start. Static ELF
symbols and host C fixtures do not establish the actual libbase definition,
signature/cache behavior or Android runtime success. Failure is retained without
fallback, identity relaxation or action replay. Full-stream completeness and
per-line writer attribution remain false. ABI3 frames and original retirement
authority remain unchanged.

Only the frozen consumer delta plus fixed Owner16 profile literals change the
six Python sources. Ordinary responses retain the original 256 KiB non-log
bound. Only exact bounded log schema fields receive a byte allowance: lifecycle
wire at most 1 MiB, actor at most 4 MiB with six fixed log occurrences, and later
fixed runtime collection at most 5 MiB. Failed capture evidence is preserved as
data and cannot become success. qualify.py and pinned_support.py are original
bytes. First errors, whole-domain retirement and outer exact cleanup remain.

Main, its original seven identities, 12288 task limit, all base86 inputs,
original RC, presenter and mount-mechanism evidence remain unchanged. The latter
is historical mechanism evidence, not a new paired Owner16 result. Fresh live
Main/resources/path/UID gates still execute. Proposed UID 61288 and subordinate
range 22000000+100000 are not reservations or current availability claims.

Owner15 remains failed before ACTIVE with an incomplete/faulted broker receipt.
Its namespace-owner SIGHUP wait status and pid_for_children ENOENT do not identify
the sender, reboot trigger or healthy process state. Its four direct children
and exact outer unit did retire. This new attempt does not retry or reclassify it.

Only local binding and source validation occur here. Root owns all dispatch.
The runtime template is not executable until actual unique preparation succeeds
and supplies its externally verified full digest. The existing 5 GiB Owner
runtime must also wait for Root's resource window; it must not overlap the heavy
framework build. No Main deployment, restart, reload or guard change is proposed.
''')
    rows = [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())]
    put('manifest.json', pretty({'schema': 1, 'kind': 'owner16_normal01_frozen', 'prepare_submitted': False,
                                'runtime_executed': False, 'files': rows}))
    OUT.mkdir()
    for name, raw in files.items():
        path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
    print(json.dumps({'root': str(OUT), 'payload_files': len(rows), 'manifest_sha256': sha(files['manifest.json']),
        'request_bytes': len(files['requests/prepare-request.json']), 'request_sha256': sha(files['requests/prepare-request.json']),
        'stdin_bytes': len(prepare_stdin.encode()), 'stdin_sha256': sha(prepare_stdin.encode()),
        'key': request['idempotency_key'], 'runtime_executed': False}))


if __name__ == '__main__':
    main()
