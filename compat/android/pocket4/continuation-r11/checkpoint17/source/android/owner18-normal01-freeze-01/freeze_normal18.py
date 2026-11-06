#!/usr/bin/env python3
"""Create-only local Owner18 actual-artifact binder; no runtime module or device execution.

Pure validators retain the frozen Owner17 binder bytes and the actual
39/139 ordinary counts. Host17/C16 binaries remain unchanged. Only this local program emits the new immutable package.
"""
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
OLD = ROOT / 'android-owner17-normal01-freeze-01'
CAPTURE = ROOT / 'android-owner18-crash-log-source-freeze01'
CORE = ROOT / 'android-owner17-bootstrap-mode-source-freeze01'
HOST = ROOT / 'android-owner17-host-build-freeze01'
EVIDENCE = ROOT / 'root-recovery-20261104-02/evidence'
OUT = ROOT / 'android-owner18-normal01-freeze-01'
OLD_PREFIX = 'p4-owner17-normal-20261105-01'
PREFIX = 'p4-owner18-normal-20261105-01'
OLD_KIND = 'owned-real-producer17-normal01-owned-bootstrap-modes01'
KIND = 'owned-real-producer18-normal01-private-crash-buffer01'
SCOPE = 'REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT'
REVISION = 'producer17-owned-bootstrap-modes01'
BUILD_ROOT = '/home/alex/work/pocket4-supervisor-lmkd-bootstrap-mode-r11-build-17-01'
SOURCE_NAMES = ('actor.py', 'coordinator.py', 'prepare.py', 'owned.py', 'pinned_support.py', 'qualify.py', 'crash_log.py')
HOST_SHA = '86c8078472a4e6ecc271ccb39e86cf8aba24bc7a4828dcabfdf3d3f38bbd5466'
ORDINARY_SHA = 'b6a1349a8b0d147d6dfe5b0defcef51ce4b3d478325d6bb104e02229c0a2c14a'
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
    assert ordinary['rust_tests_passed'] == {'droidloom-pressure-relay': 39, 'droidloom-supervisor': 139}
    assert ordinary['rust_test_binary_counts'] == {'droidloom_pressure_relay:lib': 39, 'droidloom_supervisor:lib': 139}
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


def source18():
    replacements = [(OLD_KIND, KIND), (OLD_PREFIX, PREFIX),
                    ('owner17-normal-preparation01', 'owner18-normal-preparation01'),
                    ('owner17-real-normal01', 'owner18-real-normal01')]
    assert (CAPTURE / 'baseline/source/actor.py').read_bytes() == (OLD / 'source/actor.py').read_bytes()
    sources, rows, difference = {}, [], ''
    for name in SOURCE_NAMES:
        old = (OLD / 'source' / name).read_text() if name != 'crash_log.py' else ''
        overlay = ((CAPTURE / 'candidate/source' / name).read_text()
                   if name in ('actor.py', 'crash_log.py') else old)
        new = overlay
        for before, after in replacements:
            if name not in ('actor.py', 'crash_log.py'):
                new = new.replace(before, after)
        reverse = new
        for before, after in reversed(replacements):
            if name not in ('actor.py', 'crash_log.py'):
                reverse = reverse.replace(after, before)
        assert reverse == overlay, name
        assert ast.dump(ast.parse(reverse), include_attributes=False) == ast.dump(ast.parse(overlay), include_attributes=False)
        if name in ('owned.py', 'pinned_support.py', 'qualify.py', 'actor.py', 'crash_log.py'):
            assert new == overlay
        ast.parse(new); compile(new, name, 'exec')
        raw = new.encode()
        sources[name] = {'bytes': len(raw), 'sha256': sha(raw), 'content': new}
        rows.append({'path': name, 'old_sha256': sha(old.encode()) if old else None,
                     'overlay_sha256': sha(overlay.encode()), 'new_sha256': sha(raw),
                     'new_bytes': len(raw), 'inverse_profile_bytes_and_AST_equal_to_overlay': True,
                     'unchanged_from_owner17': new == old})
        difference += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                             fromfile='owner17/source/' + name if old else '/dev/null',
                             tofile='owner18/source/' + name))
    return sources, rows, difference


def main():
    assert not OUT.exists(), 'create-only freeze already exists'
    old_manifest = manifest(OLD, 'manifest.json', '0b69c268625123af4626964cb59a3cf36278a9345ca6f011af7033569426a262', 26)
    capture_manifest = manifest(CAPTURE, 'SOURCE_PINS.json', 'c4c34d194586e98289c766bb8518230a81555068ebf7fb51c42698dec70a8810', 12)
    core_manifest = manifest(CORE, 'SOURCE_PINS.json', 'dca55eadb80fe20905f4aadc2420ac89406fb9c019bea97a73e67526b408a845', 11)
    host_manifest = manifest(HOST, 'manifest.json', 'ac44aa4b454a271fb3468bb5437a64ed77de77dffe60e296b80e643dcf398626', 15)
    compile_review_raw, compile_review = pinned(ROOT / 'android-owner17-host-compile-actual-review01/report.json', 11328,
        '02b0bb0d13f719ee8ac6707419684c86f3f025dc0e614aca4295537ec46ec4b3')
    ordinary_review_raw, ordinary_review = pinned(ROOT / 'android-owner17-host-ordinary-actual-review01/report.json', 4741,
        '61e0603ae6971e2a45e24dcb1a7320ff8a2dac94ac7c8e4a879e10f7ce174dc5')
    old_plan_raw, old_plan = pinned(OLD / 'plan.json', 80010,
        'a8c1a5364a618e6f3d6556fc824ea493bff8b8255abcaccf37caa6a79f795427')
    host_path = EVIDENCE / 'owner17-host-mode-compile01/compile-result.json'
    ordinary_path = EVIDENCE / 'owner17-host-ordinary01/run-result.json'
    android_path = EVIDENCE / 'owner16-android-log-build01/build-result.json'
    host_raw, host = pinned(host_path, 50235, HOST_SHA)
    ordinary_raw, ordinary = pinned(ordinary_path, 37889, ORDINARY_SHA)
    android_raw, android = pinned(android_path, 661519, ANDROID_SHA)
    assert host['success'] is True and android['success'] is True
    assert compile_review['actual_receipt']['sha256'] == HOST_SHA
    assert compile_review['artifacts'] == host['artifacts']
    assert compile_review['compiled_test_artifacts'] == host['compiled_test_artifacts']
    assert ordinary_review['ordinary_receipt']['sha256'] == ORDINARY_SHA
    assert ordinary_review['result'] == 'ACTUAL_ORDINARY_CONTROLS_PASS_OWNER17_RUNTIME_PENDING'
    assert ordinary_review['actual_tests'] == {'droidloom-pressure-relay': 39, 'droidloom-supervisor': 139}
    assert len(ordinary_review['new_mode_tests_actual_named_pass']) == 3
    assert ordinary_review['full_owner_runtime_qualified'] is False
    assert host['candidate'] == BUILD_ROOT + '/candidate' and host['target'] == BUILD_ROOT + '/target'
    payload_raw = (HOST / 'payload.json').read_bytes(); payload = json.loads(payload_raw)
    assert host['payload_sha256'] == sha(payload_raw) and payload['source_manifest_sha256'] == sha(core_manifest)
    assert host['original_source_diff_sha256'] == sha((CORE / 'production.diff').read_bytes())
    expected_inputs = copy.deepcopy(payload['preimage'])
    assert list(payload['overlays']) == ['runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs']
    for relative, row in payload['overlays'].items():
        body = (CORE / 'candidate' / relative).read_bytes()
        assert row['text'].encode() == body and row['bytes'] == len(body) and row['sha256'] == sha(body)
        expected_inputs[relative] = {key: row[key] for key in ('bytes', 'sha256')}
    assert len(expected_inputs) == 33 and host['inputs_before'] == host['inputs_after'] == expected_inputs
    assert host['all_source_inventory_before_sha256'] == host['all_source_inventory_after_sha256'] == compile_review['actual_complete_source_inventory_sha256']
    assert len(host['commands']) == 6 and all(c['returncode'] == 0 and not c['timed_out'] and c['exact_child_pid'] > 0 for c in host['commands'])
    resource_gate(host, 1073741824)
    ordinary_binding = bind_ordinary(ordinary_raw, ordinary, host, expected_inputs)
    prior_path = EVIDENCE / 'owner17-runtime-read01/runtime-result.json'
    prior_raw, prior = pinned(prior_path, 752649, '701522531cd0166e02f90fe5f49da3d6f828cd65ea8c0bd8fb5df94617e91530')
    prior_review_path = ROOT / 'android-owner17-runtime-actual-review01/report.json'
    prior_review_raw, prior_review = pinned(prior_review_path, 7571, 'ea32c73db88a1b07ef9ff3052d0d4890b839e44e2fe8f8f54e7c9542ca65799b')
    assert prior['success'] is False and prior['attempt_nonce'] == old_plan['attempt_nonce']
    assert prior['main_before'] == prior['main_before_gate'] == prior['main_after']
    assert all(prior['exact_unit_cleanup'][key] is True for key in ('cgroup_absent', 'original_actor_dead', 'unit_not_found'))
    assert prior_review['runtime_failed_preserved'] is True and prior_review['broker_active_observed'] is False
    assert prior_review['six_post_retiring_events_complete'] is True
    assert prior_review['actual_kernel_logger_two_markers_passed'] is True
    assert prior_review['LMKD_exec_permission_cause_complete'] is False
    assert prior_review['hwservicemanager_abort_message_observed'] is False
    assert prior_review['LMKD_exec_EACCES_lines'] == [] and len(prior_review['LMKD_SIGABRT_lines_and_guest_pids']) == 5
    capture_controls = json.loads((CAPTURE / 'controls/result-03.json').read_bytes())
    assert capture_controls['passed'] == 12 and capture_controls['failed'] == 0
    assert capture_controls['source_sha256'] == sha((CAPTURE / 'candidate/source/crash_log.py').read_bytes())
    assert capture_controls['real_peer_or_init_admission_qualified'] is False

    def remap(value):
        if isinstance(value, str): return value.replace(OLD_PREFIX, PREFIX)
        if isinstance(value, list): return [remap(item) for item in value]
        if isinstance(value, dict): return {key: remap(item) for key, item in value.items()}
        return value

    plan = remap(old_plan)
    attempt = os.urandom(32).hex()
    assert attempt != '0' * 64 and attempt not in old_plan_raw.decode()
    plan.update(kind=KIND, scope=SCOPE, attempt_nonce=attempt,
                description='Pocket4 Owner18 bounded private crash buffer NORMAL01 ' + attempt)
    for role in ('droidloomd', 'droidloom-supervisor', 'droidloom-psi-owner'):
        row = copy.deepcopy(host['artifacts'][role])
        assert row['path'] == BUILD_ROOT + '/target/debug/' + role
        assert row['bytes'] > 0 and row['inode'] > 0 and row['mode'] == 0o700
        row['destination'] = old_plan['artifacts'][role]['destination']
        plan['artifacts'][role] = row
    barrier = {key: android['Android_artifact'][key] for key in ('path', 'bytes', 'sha256', 'device', 'inode')}
    barrier.update(mode=stat.S_IMODE(android['Android_artifact']['mode']), destination='lib/libdroidloom_init_relay.so')
    assert plan['artifacts']['init-barrier'] == old_plan['artifacts']['init-barrier'] == barrier
    assert len(plan['artifacts']) == 5 and plan['artifacts'] == old_plan['artifacts']
    relay = plan['spec']['pressure_relay']
    for name, role in (('broker', 'droidloom-psi-owner'), ('entry_supervisor', 'droidloom-supervisor')):
        relay[name]['sha256'] = plan['artifacts'][role]['sha256']
    plan['actual_compile_receipt'] = file_record(host_path, host_raw)
    plan['actual_ordinary_receipt_sha256'] = sha(ordinary_raw)
    assert plan['projection_build_receipt_sha256'] == sha(android_raw)
    plan['earlier_failure_chain'] = {'earlier': copy.deepcopy(old_plan['earlier_failure_chain']),
                                    'previous': copy.deepcopy(old_plan['predecessor_failure'])}
    plan['predecessor_failure'] = {
        'runtime_sha256': sha(prior_raw), 'attempt_nonce': old_plan['attempt_nonce'], 'replayed': False,
        'cause_review_sha256': sha(prior_review_raw), 'old_failure_not_reclassified': True,
        'observed_boundary': 'Actual generation markers and broker READY, ABI3 DONE; no original LMKD exec EACCES in retained prefix, five LMKD SIGABRT and five HWS SIGABRT observations, HWS critical init reboot before ACTIVE',
        'both_actual_init_logger_markers_passed': True, 'six_post_retiring_events_complete': True,
        'outer_exact_cleanup_passed': True, 'old_broker_receipt_faulted_and_incomplete': True,
        'normal_owner_runtime_qualified': False, 'LMKD_exec_permission_cause_complete': False,
        'HWS_abort_message_observed': False, 'HWS_fixed_by_directory_mode_change_claimed': False}
    # Host17's build contract is historical and byte-exact: no new ELF or ABI.
    assert plan['bootstrap_mode_source_manifest_sha256'] == sha(core_manifest)
    plan['private_crash_buffer_contract'] = {
        'source_manifest_sha256': sha(capture_manifest),
        'module_sha256': sha((CAPTURE / 'candidate/source/crash_log.py').read_bytes()),
        'local_control_result_sha256': sha((CAPTURE / 'controls/result-03.json').read_bytes()),
        'local_controls_passed': 12, 'real_peer_init_protocol_qualification': False,
        'fresh_HELLO_root_userns_UID0_and_peer_pidfd_required': True,
        'one_connection_one_stream_lids4_no_reconnect': True,
        'existing_65s_startup_deadline_and_immediate_Stop_unchanged': True,
        'maximum_packet_bytes': 5120, 'maximum_private_prefix_bytes': 262144,
        'maximum_records': 2048, 'maximum_packets_per_poll': 32,
        'final_nonblocking_drain_after_original_Stop_and_children_retired': True,
        'private_packet_file_relative': 'evidence/generation-crash-buffer4.bin',
        'raw_packets_in_general_actor_JSON_or_Git': False,
        'empty_capture_proves_HWS_health': False, 'native_LMKD_enrollment_qualified': False}
    plan['status'] = 'SOURCE_FROZEN_PREPARE_AND_RUNTIME_NOT_SUBMITTED'
    changed_top = {'kind', 'attempt_nonce', 'description', 'artifacts', 'spec', 'actual_compile_receipt',
                   'actual_ordinary_receipt_sha256', 'earlier_failure_chain', 'predecessor_failure',
                   'private_crash_buffer_contract', 'canonical_spec_sha256'}
    remapped_old = remap(old_plan)
    for key in plan:
        if key not in changed_top:
            assert plan[key] == remapped_old[key], key
    old_spec = copy.deepcopy(remapped_old['spec'])
    old_spec['pressure_relay']['broker']['sha256'] = relay['broker']['sha256']
    old_spec['pressure_relay']['entry_supervisor']['sha256'] = relay['entry_supervisor']['sha256']
    assert plan['spec'] == old_spec
    assert len(plan['base']['records']) == 86 and len(plan['data_images']) == 2
    assert all(plan[key] is False for key in ('production_ready', 'installed_owner_qualified',
        'rc_property_reload_qualified', 'pressure_effect_qualified', 'app_qualified'))
    rust = ROOT / 'lmkd-recovery-20261105-01/producer07-audit-freeze-02/source/runtime/droidloom-supervisor/src'
    def fields(path, name, relative):
        raw = path.read_bytes()
        assert expected_inputs[relative] == {'bytes': len(raw), 'sha256': sha(raw)}
        body = re.search(r'pub struct ' + name + r'\s*\{(.*?)^\}', raw.decode(), re.S | re.M)[1]
        return re.findall(r'^\s*pub\s+(\w+)\s*:', body, re.M)
    spec_fields = fields(rust / 'lib.rs', 'CellSpec', 'runtime/droidloom-supervisor/src/lib.rs')
    assert list(plan['spec']) == [key for key in spec_fields if key in plan['spec']]
    policy = rust / 'relay_lifecycle/policy.rs'; relative = 'runtime/droidloom-supervisor/src/relay_lifecycle/policy.rs'
    assert list(relay) == fields(policy, 'PressureRelaySpec', relative)
    for name in ('broker', 'entry_supervisor', 'lmkd', 'init_barrier'):
        assert list(relay[name]) == fields(policy, 'RelayArtifact', relative)
    canonical = json.dumps(plan['spec'], ensure_ascii=False, separators=(',', ':')).encode()
    plan['canonical_spec_sha256'] = sha(canonical)
    sources, source_rows, source_diff = source18()
    profile_guard = fixed_guard(sources, 'prepare.py', 'wrong fixed profile')
    path_guard = fixed_guard(sources, 'coordinator.py', 'this controller accepts only its fixed fresh unit/package/state')
    cases = [('new_profile', profile_guard, plan, True), ('new_paths', path_guard, plan, True),
             ('old_kind_rejected', profile_guard, {**plan, 'kind': OLD_KIND}, False),
             ('short_nonce_rejected', profile_guard, {**plan, 'attempt_nonce': '12' * 31}, False)]
    cases += [('old_' + key + '_rejected', path_guard, {**plan, key: old_plan[key]}, False)
              for key in ('unit', 'package', 'state')]
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
    request.update(stdin=prepare_stdin, idempotency_key='p4-owner18-normal01-prepare01-' + sha(prepare_stdin.encode())[:16])
    old_coordinator = (OLD / 'source/coordinator.py').read_bytes()
    runtime = (OLD / 'requests/runtime-stdin-template.py').read_text().replace(OLD_PREFIX, PREFIX)
    runtime = runtime.replace(sha(old_coordinator), sources['coordinator.py']['sha256'])
    runtime = runtime.replace('SOURCE_BYTES = ' + str(len(old_coordinator)), 'SOURCE_BYTES = ' + str(sources['coordinator.py']['bytes']))
    ast.parse(runtime); assert runtime.count('__ACTUAL_PREPARED_SHA256__') == 1
    runtime_request = json.loads((OLD / 'requests/runtime-request-template.json').read_bytes())
    runtime_request.update(stdin=runtime, idempotency_key='p4-owner18-normal01-runtime01-__ACTUAL_PREPARED_SHA256_PREFIX16__')
    for name, new in [('prepare-request.json', request), ('runtime-request-template.json', runtime_request)]:
        old = json.loads((OLD / 'requests' / name).read_bytes())
        assert {k: v for k, v in new.items() if k not in ('stdin', 'idempotency_key')} == {k: v for k, v in old.items() if k not in ('stdin', 'idempotency_key')}
    wrapper_constants = literals_from_text(prepare_stdin)
    decoded = base64.b64decode(wrapper_constants['PACKET_BASE64'], validate=True)
    assert decoded == packet and wrapper_constants['PACKET_SHA256'] == sha(packet)
    assert json.loads(decoded) == {'plan_utf8': plan_raw.decode(), 'sources': sources}
    files = {}
    def put(name, raw):
        raw = raw.encode() if isinstance(raw, str) else raw; raw.decode('utf-8')
        assert name not in files and not Path(name).is_absolute() and '..' not in Path(name).parts
        files[name] = raw
    put('plan.json', plan_raw); put('cell.json', canonical)
    for name, row in sources.items(): put('source/' + name, row['content'])
    put('source.diff', source_diff)
    put('plan.diff', ''.join(difflib.unified_diff(old_plan_raw.decode().splitlines(True), plan_raw.decode().splitlines(True), fromfile='owner17/plan.json', tofile='owner18/plan.json')))
    put('requests/prepare-template.py', prepare_template); put('requests/prepare-stdin.py', prepare_stdin)
    put('requests/prepare-request.json', pretty(request)); put('requests/runtime-stdin-template.py', runtime)
    put('requests/runtime-request-template.json', pretty(runtime_request))
    for name, raw in [('owner17-normal-manifest.json', old_manifest), ('owner18-crash-source-manifest.json', capture_manifest), ('owner17-core-manifest.json', core_manifest), ('owner17-host-manifest.json', host_manifest)]:
        put('lineage/' + name, raw)
    put('evidence/actual-compile-review.json', compile_review_raw)
    put('evidence/actual-ordinary-review.json', ordinary_review_raw)
    put('evidence/actual-ordinary.json', ordinary_raw)
    put('evidence/owner17-failure-review.json', prior_review_raw)
    put('evidence/crash-source-review.json', (CAPTURE / 'SOURCE_REVIEW.json').read_bytes())
    put('evidence/crash-local-controls.json', (CAPTURE / 'controls/result-03.json').read_bytes())
    put('freeze_normal18.py', Path(__file__).read_bytes())
    put('source-profile-review.json', pretty({'schema': 1, 'sources': source_rows,
        'fixed_guard_expression_checks': checks, 'unchanged_sources': ['owned.py', 'pinned_support.py', 'qualify.py'],
        'seven_sources_with_one_frozen_actor_observation_overlay': True, 'NORMAL_Stop_and_retirement_semantics_unchanged': True,
        'private_logdr_frozen_candidate_included': True, 'no_runtime_module_imported_or_executed': True}))
    admission = {'schema': 1, 'kind': 'owner18_normal01_actual_source_binding', 'prepare_submitted': False, 'runtime_submitted': False,
        'host_compile': file_record(host_path, host_raw), 'android_compile': file_record(android_path, android_raw),
        'ordinary': file_record(ordinary_path, ordinary_raw), 'ordinary_binding': ordinary_binding,
        'source_manifest_sha256': sha(core_manifest), 'capture_source_manifest_sha256': sha(capture_manifest), 'prior_owner17_failure': file_record(prior_path, prior_raw),
        'prior_failure_not_reclassified': True, 'artifacts_bound_to_actual_builds': 5,
        'all_five_Host17_LMKD_C16_artifacts_exact_original': True, 'base86_unchanged': True,
        'actor_and_collector_exact_frozen_overlay_bytes': True,
        'retained_actor_kind_is_implementation_label_not_attempt_identity': 'owner17-real-normal01',
        'seven_runtime_sources_one_frozen_observation_overlay': True, 'private_logdr_frozen_candidate_included': True,
        'NORMAL_Stop_and_original_retirement_unchanged': True,
        'Main_guard_and_original12288_limits_unchanged': True,
        'fresh_live_Main_ID_resource_and_file_absence_checks_still_required': True,
        'new_attempt_nonce': attempt, 'synthetic_uid': 61288, 'subordinate_start': 22000000, 'subordinate_count': 100000,
        'live_UID_subid_absence_not_observed_by_this_binder': True,
        'CellSpec_host_uid_not_asserted_as_actual_init_credentials': True,
        'Rust_field_order_verified_against_actual_unchanged_inputs': True,
        'canonical_spec_sha256': sha(canonical), 'published_plan_sha256': sha(plan_raw),
        'expected_prepared_serialized_plan_sha256': sha((json.dumps(plan, sort_keys=True, indent=2) + '\n').encode()),
        'prepare_packet_bytes': len(packet), 'prepare_packet_sha256': sha(packet),
        'prepare_stdin_bytes': len(prepare_stdin.encode()), 'prepare_stdin_sha256': sha(prepare_stdin.encode()),
        'prepare_request_bytes': len(files['requests/prepare-request.json']), 'prepare_request_sha256': sha(files['requests/prepare-request.json']),
        'idempotency_key': request['idempotency_key'], 'prepare_wrapper_unchanged': True,
        'only_request_stdin_and_key_changed': True, 'runtime_template_requires_external_actual_prepared_digest': True,
        'runtime_resource_window_dispatch_is_Root_only': True,
        'prior_generation_logger_success_not_new_generation_qualification': True,
        'production_ready': False, 'app_qualified': False, 'no_remote_action_by_this_binder': True}
    put('ACTUAL-ADMISSION-REVIEW.json', pretty(admission))
    put('README.md', """# Owner18 NORMAL01 with bounded generation-private crash observation

This new attempt reuses all five actual Host17/LMKD/C16 artifacts unchanged.
Actual ordinary qualification remains 39 relay, 139 supervisor, seven IPC,
worker-context and ABI3 with original retirement controls. No Rust or Android
DSO build is performed or implied by this package.

The new frozen crash_log module and its actor observation wiring are included
byte-for-byte. The actor retains its legacy owner17-real-normal01 implementation
label; the fresh plan, actual prepared digest, nonce, root, unit and invocation
identify this Owner18 attempt. prepare.py and coordinator.py receive only their
fresh fixed profile/root literals. owned.py,
pinned_support.py and qualify.py are unchanged bytes. Original NORMAL Stop,
ACTIVE and failure gates, whole-domain retirement and exact cleanup remain.

Observation is confined to the new generation's held init root and logdr peer;
only one stream lids=4 request is permitted after strict peer/init/root/ELF/domain
qualification. Raw crash packets remain in the private bounded file, not general
result JSON or this package. Actual peer/kernel/API/protocol admission remains
unqualified. Empty capture does not establish service health.

Owner17 stays failed: the retained prefix has no former LMKD exec denial, but
five LMKD and five HWS SIGABRT observations; HWS critical failure triggered init
reboot before ACTIVE. No specific service abort message was observed. New logs
must supply the missing facts; no lifecycle or identity gate is relaxed.

Main original seven identities/pids12288, base86, presenter/tools/resources,
two new images, original cell budget and Stop timing are unchanged. UID61288 is
only the CellSpec value; actual init must remain UID/GID0 in the actor initial
user namespace. This package is local and unsubmitted. Root alone dispatches,
and the runtime template requires unique actual prepared SHA before use.
""")
    rows = [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())]
    put('manifest.json', pretty({'schema': 1, 'kind': 'owner18_normal01_frozen', 'prepare_submitted': False,
        'runtime_executed': False, 'files': rows}))
    OUT.mkdir()
    for name, raw in files.items():
        path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream: stream.write(raw)
    print(json.dumps({'root': str(OUT), 'payload_files': len(rows), 'manifest_sha256': sha(files['manifest.json']),
        'request_bytes': len(files['requests/prepare-request.json']), 'request_sha256': sha(files['requests/prepare-request.json']),
        'stdin_bytes': len(prepare_stdin.encode()), 'stdin_sha256': sha(prepare_stdin.encode()),
        'key': request['idempotency_key'], 'runtime_executed': False}))


def literals_from_text(source):
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try: result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError): pass
    return result


if __name__ == '__main__':
    main()
