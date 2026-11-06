"""Read retained Host17 actual evidence and bind the already frozen ordinary runner.

Local only: no production module imports, commands, network or runtime execution.
Both output directories are create-only. The runner bytes remain unchanged.
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'android-owner17-host-build-freeze01'
SOURCE = ROOT / 'android-owner17-bootstrap-mode-source-freeze01'
ACTUAL = ROOT / 'root-recovery-20261104-02/evidence/owner17-host-mode-compile01/compile-result.json'
STDOUT = ACTUAL.with_name('stdout.log')
REVIEW = ROOT / 'android-owner17-host-compile-actual-review01'
ORDINARY = ROOT / 'android-owner17-host-ordinary-freeze01'
ACTUAL_SHA = '86c8078472a4e6ecc271ccb39e86cf8aba24bc7a4828dcabfdf3d3f38bbd5466'
REL = 'runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs'
REMOTE = '/home/alex/work/pocket4-supervisor-lmkd-bootstrap-mode-r11-build-17-01'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def pretty(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def pin(body):
    return {'bytes': len(body), 'sha256': sha(body)}


def write_group(directory, files):
    assert not directory.exists()
    files = dict(files)
    files['SOURCE_PINS.json'] = pretty({name: pin(body) for name, body in sorted(files.items())})
    directory.mkdir()
    for name, body in files.items():
        body.decode('utf-8')
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as out:
            assert out.write(body) == len(body)
    return {name: pin(body) for name, body in sorted(files.items())}


def main():
    assert not REVIEW.exists() and not ORDINARY.exists()
    checks = []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    build_manifest_raw = (BUILD / 'manifest.json').read_bytes()
    check('frozen build manifest', sha(build_manifest_raw) == 'ac44aa4b454a271fb3468bb5437a64ed77de77dffe60e296b80e643dcf398626')
    for row in json.loads(build_manifest_raw)['files']:
        check('build leaf ' + row['path'], pin((BUILD / row['path']).read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')})
    source_manifest_raw = (SOURCE / 'SOURCE_PINS.json').read_bytes()
    check('frozen production manifest', sha(source_manifest_raw) == 'dca55eadb80fe20905f4aadc2420ac89406fb9c019bea97a73e67526b408a845')
    source_manifest = json.loads(source_manifest_raw)
    for name, row in source_manifest['files'].items():
        check('source leaf ' + name, pin((SOURCE / name).read_bytes()) == row)
    raw = ACTUAL.read_bytes()
    check('actual receipt full bytes', len(raw) == 50235 and sha(raw) == ACTUAL_SHA)
    actual = json.loads(raw)
    stdout = STDOUT.read_bytes()
    check('actual stdout full bytes', len(stdout) == 368 and sha(stdout) == 'd9ac8892af7d50f65e48238ad4650811736c7e8aa350d52254c917c7187da9ae')
    terminal_summary = json.loads(stdout)
    check('actual stdout binds receipt', terminal_summary['success'] is True and terminal_summary['report'] == REMOTE + '/compile-result.json' and terminal_summary['bytes'] == len(raw) and terminal_summary['sha256'] == ACTUAL_SHA and terminal_summary['error'] is None)
    check('compile-only success', actual['success'] is True and actual['compile_only'] is True and actual['revision'] == 'producer17-owned-bootstrap-modes01' and not actual.get('error') and not actual.get('traceback') and not actual.get('failure_collection_errors'))
    check('no tests Android or owner claimed', all(actual[k] is False for k in ('test_binaries_executed', 'ordinary_controls_executed', 'full_owner_runtime_qualified', 'android_runtime_started', 'barrier_constructor_executed', 'installed_files_changed', 'namespace_or_network_effects_requested')))
    payload_raw = (BUILD / 'payload.json').read_bytes()
    payload = json.loads(payload_raw)
    prior_raw = (BUILD / 'lineage/actual-host16-compile-result.json').read_bytes()
    prior = json.loads(prior_raw)
    check('prior actual chain', sha(prior_raw) == actual['prior_build_receipt_sha256'] == 'dad36fe9fd79aa782bcc255e74b8cc1b1ee241a341318e179ccaa9e7f1c785ea')
    check('all 33 original inputs', actual['preimage_inputs'] == payload['preimage'] == prior['inputs_before'] == prior['inputs_after'] and len(actual['preimage_inputs']) == 33)
    check('exact one overlay', set(payload['overlays']) == {REL})
    overlay = payload['overlays'][REL]
    check('overlay exact production bytes', overlay['text'].encode() == (SOURCE / 'candidate' / REL).read_bytes() and pin(overlay['text'].encode()) == {k: overlay[k] for k in ('bytes', 'sha256')})
    expected_inputs = {**payload['preimage'], REL: {k: overlay[k] for k in ('bytes', 'sha256')}}
    check('actual 33 inputs unchanged', actual['inputs_before'] == actual['inputs_after'] == expected_inputs and len(expected_inputs) == 33)
    check('payload and production diff pins', actual['payload_sha256'] == sha(payload_raw) and actual['original_source_diff_sha256'] == sha((SOURCE / 'production.diff').read_bytes()))
    check('full isolated inventory stable', actual['all_source_inventory_before_sha256'] == actual['all_source_inventory_after_sha256'] == '5874d617a76f5c09189d10982f9292323f71a048b857753a912dd7ab7c412336')
    check('original complete tree unchanged', actual['original_source_inventory_after_sha256'] == prior['all_source_inventory_before_sha256'] == prior['all_source_inventory_after_sha256'])
    check('paths isolated', actual['candidate'] == REMOTE + '/candidate' and actual['target'] == REMOTE + '/target' and actual['source_origin'] == prior['candidate'])
    check('direct actual Rust tools and versions unchanged', actual['direct_toolchain_before'] == actual['direct_toolchain_after'] == prior['direct_toolchain_after'] and actual['direct_versions_before'] == actual['direct_versions_after'] == prior['direct_versions_after'] and actual['direct_tool_authority'] == prior['direct_tool_authority'])
    expected_environment = dict(prior['build_environment_overrides'], CARGO_TARGET_DIR=REMOTE + '/target')
    check('fixed environment retained', actual['build_environment_overrides'] == expected_environment and not any(k.startswith('RUSTUP') for k in actual['build_environment_overrides']))
    commands = actual['commands']
    check('exact six original argv no-run', len(commands) == 6 and [c['argv'] for c in commands] == [c['argv'] for c in prior['commands']])
    check('six direct children waited successfully', all(c['returncode'] == 0 and c['timed_out'] is False and c['exact_child_pid'] > 0 and c['cwd'] == actual['candidate'] and c['finished_at'] >= c['started_at'] for c in commands) and len({c['exact_child_pid'] for c in commands}) == 6)
    for i, command in enumerate(commands):
        for stream in ('stdout', 'stderr'):
            p = command[stream + '_pin']
            check('command %d %s exact path and finite retained bytes' % (i, stream), p['path'] == command[stream + '_path'] == REMOTE + '/command-%02d.%s' % (i, stream) and 0 <= p['bytes'] <= 8 * 1024 * 1024 and p['device'] == 66306 and p['inode'] > 0 and p['mode'] == 0o600 and len(p['sha256']) == 64)
    check('version outputs fully pinned', all(pin(commands[i]['stdout_excerpt'].encode()) == {k: commands[i]['stdout_pin'][k] for k in ('bytes', 'sha256')} and commands[i]['stderr_pin']['bytes'] == 0 for i in (0, 1, 4, 5)))
    artifacts = actual['artifacts']
    check('four compiled binaries retained', set(artifacts) == {'droidloomd', 'droidloom-supervisor', 'droidloom-psi-owner', 'owned-ipc-controls'})
    expected_artifacts = {
        'droidloomd': (6600824, 'b625080e77d9ae0c2ed375c5a4fcfe27eb918766dd2b59e3df19e9a10606c9b3'),
        'droidloom-supervisor': (6623376, '69976328ee7f4850f7308067a8b5437f23cb0739943f5648eb8adbfde87db068'),
        'droidloom-psi-owner': (1327696, '044c851a88d544aa3ed47a30fbe8beac568b0240b660290541d2c18ac72af167'),
        'owned-ipc-controls': (1616112, '44474d8fb4cbbdce595e993628bbb64b9dbf6515bd24f60f686aea20656900c2'),
    }
    for name, row in artifacts.items():
        check('actual ELF ' + name, (row['bytes'], row['sha256']) == expected_artifacts[name] and row['path'] == REMOTE + '/target/debug/' + name and row['mode'] == 0o700 and row['device'] == 66306 and row['inode'] > 0 and row['cargo_target_source'].startswith(actual['candidate'] + '/runtime/'))
    tests = actual['compiled_test_artifacts']
    check('two selected library test artifacts', [(r['target_name'], r['target_kind']) for r in tests] == [('droidloom_pressure_relay', 'lib'), ('droidloom_supervisor', 'lib')] and all(r['path'].startswith(REMOTE + '/target/debug/deps/') and r['mode'] == 0o700 and r['device'] == 66306 for r in tests))
    resource = actual['resource_health']
    check('own resource gate complete', resource['held_own_cgroup_gate_passed'] is True and resource['cgroup_files_written'] is False and actual['uid'] == 1000 and actual['cpu_quota_percent'] == 100 and actual['memory_budget_bytes'] == 1073741824)
    check('own cgroup identity limits stable', resource['before']['cgroup_identity'] == resource['after']['cgroup_identity'] and resource['before']['limits'] == resource['after']['limits'] and resource['after']['limits']['cpu.max'] == [100000, 100000] and resource['after']['limits']['memory.max'] == 1073741824)
    check('actual memory events zero', all(v == 0 for v in resource['memory_event_delta'].values()) and resource['after']['memory_peak'] == 805916672 and resource['after']['memory_swap_current'] == resource['after']['memory_swap_peak'] == 0)
    template_raw = (BUILD / 'ordinary-run-request-template.json').read_bytes()
    template = json.loads(template_raw)
    request = copy.deepcopy(template['request_template'])
    check('original not-ready template', template['execution_ready'] is False and request['args'][-1] == 'REQUIRES_ACTUAL_SUCCESSFUL_COMPILE_SHA256' and request['idempotency_key'].endswith('REQUIRES_ACTUAL_SHA16'))
    request['args'][-1] = ACTUAL_SHA
    request['idempotency_key'] = request['idempotency_key'].replace('REQUIRES_ACTUAL_SHA16', ACTUAL_SHA[:16])
    check('runner byte-exact unchanged', request['stdin'].encode() == (BUILD / 'run.py').read_bytes())
    check('ordinary unchanged resources scope', request['cpu_quota_percent'] == 100 and request['memory_max_bytes'] == 536870912 and request['timeout_seconds'] == 180 and request['args'] == ['-I', '-B', '-', '--compile-sha256', ACTUAL_SHA])
    report = {
        'schema': 1, 'result': 'ACTUAL_COMPILE_PASS_ORDINARY_AND_OWNER_NOT_RUN',
        'actual_receipt': {'local_path': str(ACTUAL), **pin(raw)}, 'actual_stdout': pin(stdout),
        'frozen_build_manifest': pin(build_manifest_raw), 'frozen_production_manifest': pin(source_manifest_raw),
        'checks': checks, 'check_count': len(checks), 'source_inputs': 33, 'overlaid_source_inputs': [REL],
        'six_commands': [{'argv': r['argv'], 'returncode': r['returncode'], 'timed_out': r['timed_out'], 'exact_child_pid': r['exact_child_pid']} for r in commands],
        'artifacts': artifacts, 'compiled_test_artifacts': tests,
        'actual_complete_source_inventory_sha256': actual['all_source_inventory_after_sha256'],
        'resource': {'cpu_quota_percent': 100, 'memory_max_bytes': 1073741824, 'memory_peak_bytes': 805916672, 'memory_events_delta': resource['memory_event_delta'], 'swap_current_bytes': 0, 'swap_peak_bytes': 0, 'swap_limit_is_max_not_zero': True},
        'limits': ['Local review consumes exact retained actual report and stdout; no second remote ELF or source read.', 'Six return codes come from the frozen direct-child wait path; no independent process scan.', 'Complete build/source inventories were measured by the actual frozen builder, not re-created locally.', 'Rustup proxy was not executed; compiler runtime libraries are not covered by the narrow direct-tool rehash.', 'No Rust tests or Android/Owner runtime were executed by this compile.', 'This review does not establish the causal sufficiency of the LMKD mode repair or resolve HWS aborts.'],
        'ordinary_pending': {'relay_library_tests': 39, 'supervisor_library_tests': 139, 'new_fd_mode_tests': 3, 'exact_retirement_tests': 2, 'IPC_controls': 7, 'worker_context': True, 'entry_ABI': 3},
        'owner_runtime_qualified': False, 'android_business_qualified': False,
    }
    report_raw = pretty(report)
    review_files = write_group(REVIEW, {'check_and_bind.py': Path(__file__).read_bytes(), 'report.json': report_raw})
    binding = {'schema': 1, 'exact_compile_receipt': pin(raw), 'compile_receipt_path': REMOTE + '/compile-result.json', 'actual_review': pin(report_raw), 'request_source_template': pin(template_raw), 'only_request_fields_changed': ['args[-1]', 'idempotency_key'], 'executed': False, 'root_dispatch_required': True, 'owner_runtime_allowed': False, 'scope': template['scope']}
    ordinary_files = write_group(ORDINARY, {'request.json': pretty(request), 'stdin.py': request['stdin'].encode(), 'binding.json': pretty(binding)})
    print(json.dumps({'review_root': str(REVIEW), 'ordinary_root': str(ORDINARY), 'review_files': review_files, 'ordinary_files': ordinary_files, 'key': request['idempotency_key'], 'checks': len(checks)}, sort_keys=True))


if __name__ == '__main__':
    main()
