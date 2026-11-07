"""Local-only fresh NORMAL03 freezer. Requires the external actual build hash.

This never executes preparation or a runtime and cannot reuse NORMAL01 paths.
"""
import argparse
import ast
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat

BASE = Path('/workspace/scratch/94990735b266/lmkd-recovery-20261105-01')
OLD = BASE / 'owner07-normal02-diagnostic-freeze-01'
FROZEN_SOURCE = BASE / 'init-project-diagnostic-freeze-01'
OUT = BASE / 'owner07-normal03-diagnostic-freeze-01'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--build-sha256', required=True)
    args = parser.parse_args()
    assert re.fullmatch('[0-9a-f]{64}', args.build_sha256)
    actual_raw = args.build_receipt.read_bytes()
    assert sha(actual_raw) == args.build_sha256
    actual = json.loads(actual_raw)
    assert actual['kind'] == 'p4-init-project-diagnostic-build03'
    assert actual['success'] is True and actual['errors'] == [] and actual['all_inputs_unchanged'] is True
    assert actual['source_manifest_sha256'] == '7ae7bc262f09ede128f1ee6b2fd7f3e8710c47b69c4df68370f2ca9ae2918c9f'
    assert actual['Android_actual_MD_equals_preflight'] is True and actual['Android_input_count'] == 140
    assert actual['Android_needed'] == ['libc.so']
    assert [(r['name'], r['passed']) for r in actual['host_control_results']] == [
        ('protocol', 20), ('protocol-close-errno', 20), ('diagnostic', 7)]
    assert len(actual['commands']) == 13 and all(c['returncode'] == 0 and not c['timed_out'] and c['child_reaped'] for c in actual['commands'])
    assert actual['resource_health']['held_own_cgroup_gate_passed'] is True
    assert not actual['Android_constructor_executed'] and not actual['namespace_mount_or_pressure_executed'] and not actual['installed_files_changed']
    frozen = json.loads((FROZEN_SOURCE / 'manifest.json').read_bytes())
    sources = {Path(r['path']).name: r for r in frozen['files'] if r['path'].startswith('source/')}
    assert set(actual['source_before']) == set(sources)
    for name, row in sources.items():
        assert actual['source_before'][name]['sha256'] == row['sha256'] and actual['source_before'][name]['bytes'] == row['bytes']
    artifact = actual['Android_artifact']
    assert artifact['path'] == '/opt/p4-init-project-diagnostic-20261105-build-03/libdroidloom_init_relay.so'
    assert artifact['uid'] == artifact['gid'] == 0 and not artifact['mode'] & 0o6022
    assert artifact['bytes'] > 0 and artifact['inode'] > 0
    old_manifest_raw = (OLD / 'manifest.json').read_bytes()
    assert sha(old_manifest_raw) == '838b1b0acd2b7d8cbf12d4809759aab077f25857276d36095d5a3862527fde4e'
    for row in json.loads(old_manifest_raw)['files']:
        raw = (OLD / row['path']).read_bytes()
        assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
    plan = json.loads((OLD / 'plan.json').read_bytes())
    old_attempt = plan['attempt_nonce']
    attempt = os.urandom(32).hex()
    assert attempt != old_attempt and int(attempt, 16) != 0
    previous_prefix = 'p4-owner07-normal-20261105-02'
    new_prefix = 'p4-owner07-normal-20261105-03'
    def remap(value):
        if isinstance(value, str):
            return value.replace(previous_prefix, new_prefix)
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        if isinstance(value, list):
            return [remap(item) for item in value]
        return value
    plan = remap(plan)
    plan['kind'] = 'owned-real-producer07-normal03-diagnostic01'
    plan['scope'] = 'REAL_OWNER_INIT_PROJECT_DIAGNOSTIC_AND_ORIGINAL_ACTIVE_RETIREMENT_GATES'
    plan['attempt_nonce'] = attempt
    plan['description'] = 'Pocket4 Owner07 NORMAL diagnostic03 ' + attempt
    plan['spec']['host_uid'] = 61279
    plan['spec']['subordinate_uids']['start'] = 20200000
    plan['spec']['subordinate_gids']['start'] = 20200000
    plan['spec']['runtime_dir'] = '/run/droidloom/cells/u61279'
    plan['spec']['pressure_relay']['init_barrier']['sha256'] = artifact['sha256']
    plan['artifacts']['init-barrier'] = {
        'path': artifact['path'], 'bytes': artifact['bytes'], 'sha256': artifact['sha256'],
        'device': artifact['device'], 'inode': artifact['inode'], 'mode': stat.S_IMODE(artifact['mode']),
        'destination': 'lib/libdroidloom_init_relay.so'}
    canonical = json.dumps(plan['spec'], ensure_ascii=False, separators=(',', ':')).encode()
    plan['canonical_spec_sha256'] = sha(canonical)
    plan['diagnostic_build_receipt_sha256'] = args.build_sha256
    failure_root = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/owner07-normal02-prepare01')
    failure_raw = (failure_root / 'stdout.txt').read_bytes()
    assert sha(failure_raw) == '8921a665badde77731239e59c1a823ce27318d7ef42e6d8d204a6088dbad707e'
    prior = json.loads(failure_raw)
    before_owned = (failure_root / 'result-before-owned-root.json').read_bytes()
    assert sha(before_owned) == 'd3876c6061cfaa3c9d55b1e302dd432768f8e1268e609f79c06b63a7518107bc'
    assert json.loads(before_owned) == prior['result_before_owned_root']
    assert prior['success'] is False and prior['runtime_executed'] is False
    assert prior['result_before_owned_root']['attempt_nonce'] == old_attempt
    assert prior['first_error']['error'] == "RuntimeError('wrong fixed profile')"
    plan['earlier_runtime_failure'] = plan['predecessor_failure']
    plan['predecessor_failure'] = {'stdout_sha256': sha(failure_raw), 'reconstructed_report_sha256': sha(before_owned),
        'attempt_nonce': old_attempt, 'replayed': False, 'runtime_executed': False,
        'remote_prepared_file_written': False,
        'observed_boundary': 'prepare fixed scope guard rejected before owned root creation'}
    plan['status'] = 'SOURCE_FROZEN_PREPARE_AND_RUNTIME_NOT_SUBMITTED'
    payload = {}
    source_diff = ''
    for path in sorted((OLD / 'source').glob('*.py')):
        old = path.read_text()
        new = old
        if path.name == 'coordinator.py':
            assert old.count(previous_prefix) == 3
            new = old.replace(previous_prefix, new_prefix)
            assert new.replace(new_prefix, previous_prefix) == old
        if path.name == 'prepare.py':
            needle = "len(plan['attempt_nonce']) == 64 and plan['scope'] == 'FIRST_REAL_OWNER_INIT_LMKD_ENROLLMENT_AND_NORMAL_RETIREMENT_ONLY'"
            replacement = "len(plan['attempt_nonce']) == 64 and\n                   plan['scope'] == 'REAL_OWNER_INIT_PROJECT_DIAGNOSTIC_AND_ORIGINAL_ACTIVE_RETIREMENT_GATES' and\n                   plan['kind'] == 'owned-real-producer07-normal03-diagnostic01'"
            assert old.count(needle) == 1
            new = old.replace(needle, replacement)
        assert path.name in ('coordinator.py', 'prepare.py') or new == old
        ast.parse(new)
        compile(new, path.name, 'exec')
        data = new.encode()
        payload[path.name] = {'bytes': len(data), 'sha256': sha(data), 'content': new}
        source_diff += ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                            fromfile='normal02/source/' + path.name, tofile='normal03/source/' + path.name))
    assert len(payload) == 6
    rust = BASE / 'producer07-audit-freeze-02/source/runtime/droidloom-supervisor/src'
    fields = lambda text, name: re.findall(r'^\s*pub\s+(\w+)\s*:', re.search(r'pub struct ' + name + r'\s*\{(.*?)^\}', text, re.S | re.M)[1], re.M)
    lib = (rust / 'lib.rs').read_text()
    policy = (rust / 'relay_lifecycle/policy.rs').read_text()
    assert list(plan['spec']) == [name for name in fields(lib, 'CellSpec') if name in plan['spec']]
    assert list(plan['spec']['pressure_relay']) == fields(policy, 'PressureRelaySpec')
    for name in ('broker', 'entry_supervisor', 'lmkd', 'init_barrier'):
        assert list(plan['spec']['pressure_relay'][name]) == fields(policy, 'RelayArtifact')
    plan_raw = pretty(plan)
    packet_raw = json.dumps({'plan_utf8': plan_raw.decode(), 'sources': payload}, ensure_ascii=False, separators=(',', ':')).encode()
    prepare_template = (OLD / 'requests/prepare-template.py').read_text()
    prepare_stdin = prepare_template.replace('__PACKET_SHA256__', repr(sha(packet_raw))).replace('__PACKET_BASE64__', repr(base64.b64encode(packet_raw).decode()))
    compile(prepare_stdin, '<NORMAL03 prepare>', 'exec')
    request = json.loads((OLD / 'requests/prepare-request.json').read_bytes())
    request['stdin'] = prepare_stdin
    request['idempotency_key'] = 'p4-owner07-normal03-prepare01-' + sha(prepare_stdin.encode())[:16]
    runtime = (OLD / 'requests/runtime-stdin-template.py').read_text()
    old_coordinator = sha((OLD / 'source/coordinator.py').read_bytes())
    runtime = runtime.replace(previous_prefix, new_prefix).replace(old_coordinator, payload['coordinator.py']['sha256'])
    assert payload['coordinator.py']['bytes'] == len((OLD / 'source/coordinator.py').read_bytes())
    runtime_request = json.loads((OLD / 'requests/runtime-request-template.json').read_bytes())
    runtime_request['stdin'] = runtime
    runtime_request['idempotency_key'] = 'p4-owner07-normal03-runtime01-__ACTUAL_PREPARED_SHA256_PREFIX16__'
    compile(runtime, '<NORMAL03 runtime template>', 'exec')
    # Execute only the actual source admission expressions, not a rewritten
    # fixture or any main/helper body. No I/O or runtime code is evaluated.
    def expression(source, message):
        calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and
            isinstance(n.func, ast.Attribute) and n.func.attr == 'need' and len(n.args) >= 2 and
            isinstance(n.args[1], ast.Constant) and n.args[1].value == message]
        assert len(calls) == 1
        value = ast.Expression(calls[0].args[0])
        return compile(ast.fix_missing_locations(value), '<actual-source-admission-expression>', 'eval')
    original_guard = expression((OLD / 'source/prepare.py').read_text(), 'wrong fixed profile')
    candidate_guard = expression(payload['prepare.py']['content'], 'wrong fixed profile')
    path_guard = expression(payload['coordinator.py']['content'], 'this controller accepts only its fixed fresh unit/package/state')
    controls = []
    def check(name, code, candidate, expected):
        actual_value = eval(code, {'__builtins__': {}, 'len': len}, {'plan': candidate})
        assert actual_value is expected, name
        controls.append({'case': name, 'accepted': actual_value, 'expected_acceptance': expected})
    old_plan = json.loads((OLD / 'plan.json').read_bytes())
    check('actual_old_scope_guard_reproduces_NORMAL02_rejection', original_guard, old_plan, False)
    check('dedicated_NORMAL03_profile_is_accepted', candidate_guard, plan, True)
    check('old_NORMAL02_kind_remains_rejected', candidate_guard, old_plan, False)
    for name, key, value in [('wrong_scope', 'scope', 'FIRST_REAL_OWNER_INIT_LMKD_ENROLLMENT_AND_NORMAL_RETIREMENT_ONLY'),
                             ('wrong_kind', 'kind', 'owned-real-producer07-normal99-diagnostic01'),
                             ('short_nonce', 'attempt_nonce', plan['attempt_nonce'][:-1])]:
        changed = dict(plan); changed[key] = value
        check(name + '_rejected', candidate_guard, changed, False)
    check('fresh03_exact_unit_package_state_accepted', path_guard, plan, True)
    for key in ('unit', 'package', 'state'):
        changed = dict(plan); changed[key] = old_plan[key]
        check('old_' + key + '_rejected', path_guard, changed, False)
    inventory = {}
    for name, row in payload.items():
        source = row['content']; tree = ast.parse(source)
        inventory[name] = [{'line': n.lineno, 'expression': ast.get_source_segment(source, n)}
            for n in ast.walk(tree) if isinstance(n, ast.Compare) and
            any(word in ast.get_source_segment(source, n) for word in ('scope', 'kind', "plan['unit']", "plan['package']", "plan['state']"))]
    assert len(controls) == 10
    OUT.mkdir(exist_ok=False)
    for name in ('source', 'requests', 'evidence'):
        (OUT / name).mkdir()
    files = {'plan.json': plan_raw, 'cell.json': canonical, 'source.diff': source_diff.encode(),
             'plan.diff': ''.join(difflib.unified_diff((OLD / 'plan.json').read_text().splitlines(True), plan_raw.decode().splitlines(True), fromfile='normal02/plan.json', tofile='normal03/plan.json')).encode(),
             'requests/prepare-template.py': prepare_template.encode(), 'requests/prepare-stdin.py': prepare_stdin.encode(),
             'requests/prepare-request.json': pretty(request), 'requests/runtime-stdin-template.py': runtime.encode(),
             'requests/runtime-request-template.json': pretty(runtime_request), 'evidence/actual-diagnostic-build.json': actual_raw,
             'make_normal03.py': Path(__file__).read_bytes()}
    for name in ('stdout.txt', 'result-before-owned-root.json', 'remote-receipt.json'):
        files['evidence/normal02-prepare-failure-' + name] = (failure_root / name).read_bytes()
    for name, row in payload.items():
        files['source/' + name] = row['content'].encode()
    files['profile-gate-controls.json'] = pretty({'schema': 1, 'source_expression_controls_passed': 10,
        'records': controls, 'six_source_fixed_gate_inventory': inventory,
        'old_actor_result_kind_retained_as_non_authorizing_schema_label': 'owner07-real-normal01',
        'runtime_or_namespace_executed': False})
    proof = {'schema': 1, 'Python_AST_and_compile': True, 'actual_prior_build_sha256': args.build_sha256,
             'old_source_manifest_sha256': sha(old_manifest_raw), 'four_sources_unchanged_other_deltas_exact_profile_and_three_coordinator_paths_only': True,
             'canonical_spec_sha256': sha(canonical), 'actual_Rust_field_order_matches': True,
             'same_cell_replay': False, 'Android_executed': False, 'prepare_submitted': False,
             'runtime_submitted': False, 'uid_and_subid_proposed_only_live_admission_required': True,
             'packet_sha256': sha(packet_raw), 'request_sha256': sha(files['requests/prepare-request.json']),
             'stdin_sha256': sha(prepare_stdin.encode()), 'idempotency_key': request['idempotency_key']}
    files['source-binding-result.json'] = pretty(proof)
    files['README.md'] = ("# Fresh Owner NORMAL03 with exact preparation profile repair\n\n"
        "This fresh attempt replaces only the paired init barrier with the actual matching diagnostic DSO. "
        "The same audit02 Rust Owner and native r6 LMKD remain pinned. The original NORMAL01 failed after "
        "PROJECT send and remains failed. Its package, state, nonce and results are not reused or modified.\n\n"
        "Four Python sources are unchanged; coordinator changes only its three exact package/state/unit "
        "literals. Preparation now exactly compares this diagnostic scope and dedicated NORMAL03 kind. "
        "NORMAL02 failed its scope guard before creating owned roots or a prepared file. Its raw stdout "
        "and reconstructed report remain unchanged. UID 61279 and subordinate range 20200000+100000 are proposed, subject to the original "
        "live absence gates; no account/subid tables are written. All outer 5 GiB/inner 4 GiB, swap zero, "
        "Main fence, one-shot claim, real private helpers, ACTIVE/retirement and exact cleanup gates remain. "
        "The original actor record kind is retained for schema compatibility; the attempt nonce, unit, "
        "package, state, plan and canonical CellSpec distinguish this new invocation.\n\n"
        "Preparation has not been submitted. The runtime template is not executable until a new actual "
        "prepared receipt is externally SHA-pinned and reviewed. Diagnostic output or a failed invocation "
        "cannot qualify ACTIVE, reload, pressure, production or commercial Apps.\n").encode()
    rows = []
    for name, data in files.items():
        (OUT / name).write_bytes(data)
        rows.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
    manifest = pretty({'schema': 1, 'kind': 'owner07-normal03-diagnostic-frozen-text', 'runtime_executed': False,
                       'files': sorted(rows, key=lambda row: row['path'])})
    (OUT / 'manifest.json').write_bytes(manifest)
    print(json.dumps({'freeze': str(OUT), 'manifest_sha256': sha(manifest), 'request_bytes': len(files['requests/prepare-request.json']), **proof}, indent=2))


if __name__ == '__main__':
    main()
