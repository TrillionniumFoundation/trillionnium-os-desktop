"""Prepare the explicit current470 contract locally, without a process packet."""
import ast
import copy
import difflib
import hashlib
import json
import pprint
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OLD = BASE / 'source-r4'
QUAL = BASE / 'builder470-current-qualification-r1'
DEST = BASE / 'current470-authorization-r1/candidate-r1'
KIND = 'explicit-current470-34commands-28tests-v1'


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixed(path, size, checksum):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == checksum, 'fixed source changed: ' + str(path))
    return raw


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(BASE)), 'bytes': len(raw), 'sha256': sha(raw)}


def put(name, raw):
    with (DEST / name).open('xb') as stream:
        stream.write(raw)


def document(name, value):
    put(name, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode())


def function(source, name):
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(source, node)


def replace_function(source, name, replacement):
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)
    rows = source.splitlines(keepends=True)
    return ''.join(rows[:node.lineno - 1]) + replacement.rstrip() + '\n' + ''.join(rows[node.end_lineno:])


def replace_one(source, old, new):
    need(source.count(old) == 1, 'nonunique source edit: ' + old[:100])
    return source.replace(old, new, 1)


def literal(source, name):
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
    return ast.literal_eval(node.value)


def main():
    need(not DEST.exists(), 'new local candidate must be fresh')
    old = fixed(OLD / 'framework_build.py', 68088,
        'c446be88a61f7d07c05aff1e3f3bb967bcf969b7fa3de568eb3de4915e59e7da').decode()
    qualifier = fixed(QUAL / 'source-r1/qualify_current470.py', 72093,
        'f8a4fed5618f05be2db375ddc63d3b2bff2e884d6ed0d9468e46bb138e86f03e').decode()
    result_raw = fixed(QUAL / 'actual-qualification/result.original.json', 121931,
        '3673f75b77a2133b5fbeecd26b13441d6c4625312c304f7dab8604e2efbfbd69')
    terminal_raw = fixed(QUAL / 'actual-qualification/status-1.original.txt', 731,
        '7042c5d094d24aae3eea354d03d9c3d6b94cb647fa0ca23a872814c3753e8e6a')
    stdout = fixed(QUAL / 'actual-qualification/stdout.original.jsonl', 4024,
        '2854236b0227f6f89e9c6875708fa4863ead70306d02ee4b510d3fe7ddb790ac')
    result, terminal = json.loads(result_raw), json.loads(terminal_raw)
    result_pin = json.loads(stdout.splitlines()[-1])['result']
    build07_files = [
        ('settled-build07-fence-terminal.original.json', BASE / 'actual-build07/fence-terminal.original.json',
            24701, '22c315979504854e249d059762a2ef008fc278c93b26c4a2bd65e0ba0a68bc34'),
        ('settled-build07-durable-terminal.original.json', BASE / 'actual-build07/terminal.process-status.original.json',
            726, '629a7963a7c7f2401c4d0f8a554352c262342d0bca246be39d644bcaa1118d82'),
        ('settled-build07-diagnosis-stdout.original.jsonl', BASE / 'preparation-diagnostic-r1/actual/stdout.original.jsonl',
            4320, '2a8c2c6c141a76bbc604c039d4dfcc22ab2daac80b6d51286b06718f19e6207b'),
        ('settled-build07-diagnosis-terminal.original.json', BASE / 'preparation-diagnostic-r1/actual/status-01.payload.original.json',
            728, '5adba93adeff2d4d540ac0f7ccb41a4d349b66bf2f9bb4769003365a36570d6f'),
    ]
    originals = {name: fixed(path, size, checksum) for name, path, size, checksum in build07_files}
    constants = {
        'CURRENT_BUILDER_CONTRACT': KIND,
        'QUALIFICATION_BYTES': len(result_raw),
        'CURRENT_QUALIFICATION_PIN': result_pin,
        'CURRENT_QUALIFIER_PIN': result['qualifier_source'],
        'CURRENT_QUALIFICATION_STAGE_PIN': result['stage_receipt'],
        'CURRENT_QUALIFICATION_LABELS': literal(qualifier, 'EXPECTED_FRESH_LABELS'),
        'CURRENT_QUALIFICATION_GATES': literal(qualifier, 'EXPECTED_GATES'),
        'CURRENT_QUALIFICATION_ENVIRONMENT': result['command_environment'],
        'CURRENT_AUTHORITY_NAMES': sorted(result['authority_observations']),
        'SETTLED_BUILD07_FILES': [(name, size, checksum) for name, unused, size, checksum in build07_files],
    }
    source = replace_one(old, "ROOT = OWNER / 'typed-ingress-framework-systemui-provider-build-07-20261106'",
        "ROOT = OWNER / 'typed-ingress-framework-systemui-provider-build-08-20261106'")
    source = replace_one(source, 'QUALIFICATION_RESULT = BUILD_RESULT',
        'QUALIFICATION_RESULT = P(' + repr(result_pin['path']) + ')')
    source = replace_one(source, "QUALIFICATION_SHA = '6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8'",
        'QUALIFICATION_SHA = ' + repr(sha(result_raw)))
    code = '\n\n# This distinct contract requires explicit selection; the old chain is not retried or repaired.\n'
    code += '\n'.join(name + ' = ' + pprint.pformat(value, width=110, sort_dicts=True)
                      for name, value in constants.items()) + '\n\n'
    source = replace_one(source, '\n\ndef identity(info):', code + '\ndef identity(info):')
    extra = (BASE / 'analysis_sources/current470_authorization_extra.py.inc').read_text()
    ancestry = function(qualifier, 'verify_source_ancestry')
    source = replace_one(source, '\n\ndef builder_contract():', '\n\n' + ancestry + '\n\n' + extra + '\n\ndef builder_contract():')
    body = function(source, 'builder_contract')
    first = body.index('    # Preserve the genuine normal05 predecessor contract')
    last = body.index('\n    result, pin = json_pin(BUILD_RESULT')
    replacement = '''    # A newly selected current-builder contract, never an exception fallback.
    # Original old03/05 controllers remain byte-bound provenance, not executable authority.
    qualification, historical, observations = current470_qualification_contract()
    for name, size, checksum in [
            ('parent-normal03-framework_build.py', 59292,
             '03f0b4aecba20149ad7f1301ea823eb5e7e5ba1efa00d08c92c4fa7ecf482132'),
            ('parent-normal05-framework_build.py', 60970,
             'f4ab5e09fc22b759811bfa9480c2de555dbc5096bc1258a984dbd33809db734b')]:
        authorization_staged(name, size, checksum, observations)
    authority = qualification['authority_observations']
    parent_compiled, parent_compiled_pin = historical['legacy469-result'], authority['legacy469-result']['pin']
    parent_qualification = historical['legacy469-qualification']
    parent_qualification_pin = authority['legacy469-qualification']['pin']
    parent_map, parent_map_pin = historical['legacy493-manifest'], authority['legacy493-manifest']['pin']
    for name, key in [('actual-builder469-result.json', 'legacy469-result'),
                      ('actual-builder469-qualification.json', 'legacy469-qualification'),
                      ('expected-builder469-manifest.json', 'legacy493-manifest')]:
        wanted = authority[key]['pin']
        staged = json.loads(authorization_staged(name, wanted['bytes'], wanted['sha256'], observations))
        require(staged == historical[key], 'immutable legacy receipt or source map differs')
'''
    body = body[:first] + replacement + body[last:]
    body = replace_one(body, "expected_packages = sorted(value.replace(str(parent_scope['BUILD_SOURCE']), str(BUILD_SOURCE))",
        "expected_packages = sorted(value.replace(str(P(parent_map_pin['path']).parent / 'builder-source'), str(BUILD_SOURCE))")
    body = replace_one(body, '    return result, pin, source_map, source_pin, builder',
        '''    observations.extend(settled_build07_contract())
    authorization = {'contract': CURRENT_BUILDER_CONTRACT,
        'qualification': CURRENT_QUALIFICATION_PIN, 'qualification_job_id': '1a1b26092d9-fc05-7dc7',
        'legacy_ELFs_opened': False, 'legacy_contracts_or_failures_rewritten': False,
        'runtime_authorization_enabled': False, 'observations': observations}
    return result, pin, source_map, source_pin, builder, authorization''')
    source = replace_function(source, 'builder_contract', body)
    source = replace_one(source,
        '    compiled, compiled_pin, builder_map, builder_map_pin, builder_pin = builder_contract()',
        '    compiled, compiled_pin, builder_map, builder_map_pin, builder_pin, authorization = builder_contract()')
    source = replace_one(source, "        'inventory_scope': scope, 'inventory_pin': inventory_pin}",
        "        'inventory_scope': scope, 'inventory_pin': inventory_pin,\n        'current_builder_authorization': authorization}")
    source = replace_one(source,
        "context['qualification_pin'] = json_pin(QUALIFICATION_RESULT, QUALIFICATION_SHA, BUILD_RESULT_BYTES)[1]",
        "context['qualification_pin'] = json_pin(QUALIFICATION_RESULT, QUALIFICATION_SHA, QUALIFICATION_BYTES)[1]")
    source = replace_one(source, "        'builder_source_files': 498, 'actual_host_compile_commands': 23, 'actual_current_exact_controls': 19,\n        'qualification_commands': 19, 'qualification_commands_included_in_host_compile': True,\n        'separate_qualification_commands': 0, 'unchanged_source_resume_controls_inherited': 9,\n        'source_resume_controls_rerun_in_successor': False, 'qualification_result_sha256': QUALIFICATION_SHA,",
        "        'builder_source_files': 498, 'actual_host_compile_commands': 23, 'actual_current_exact_controls': 28,\n        'original_host_compile_exact_controls': 19, 'qualification_commands': 34,\n        'qualification_commands_included_in_host_compile': False, 'separate_qualification_commands': 34,\n        'unchanged_source_resume_controls_inherited': 0, 'source_resume_controls_rerun_in_successor': True,\n        'qualification_result_sha256': QUALIFICATION_SHA, 'builder_contract': CURRENT_BUILDER_CONTRACT,\n        'actual_current_qualification_job_id': '1a1b26092d9-fc05-7dc7',\n        'legacy_468_missing_and_build07_failed_preserved': True,")
    source = replace_one(source,
        "        'actual_static_compile_peak_bytes': 1073741824, 'actual_static_compile_memory_max_events': 657,",
        "        'actual_static_compile_peak_bytes': 1073741824, 'actual_static_compile_memory_max_events': 657,\n        'actual_separate_qualification_peak_bytes': 904175616, 'actual_separate_qualification_memory_max_events': 0,")
    body = function(source, 'verify_inputs_after')
    body = replace_one(body, '    return observations', '    verify_current_authorization_after(context)\n    return observations')
    source = replace_function(source, 'verify_inputs_after', body)
    source = replace_one(source, '        "prior_failure_authorities": context["prior_failure_authority_pins"]})',
        '        "prior_failure_authorities": context["prior_failure_authority_pins"],\n        "current_builder_authorization": context["current_builder_authorization"]})')
    source = replace_one(source, '                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,',
        '                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,\n                    "current_builder_contract": CURRENT_BUILDER_CONTRACT,\n                    "actual_current_qualification_sha256": QUALIFICATION_SHA,')
    source = replace_one(source, "    parser.add_argument('--preparation-sha256')",
        "    parser.add_argument('--preparation-sha256')\n    parser.add_argument('--builder-contract')")
    source = replace_one(source, "        require(args.preparation_sha256 is None, 'SHA provided without build mode')",
        "        require(args.preparation_sha256 is None and args.builder_contract is None,\n                'SHA or builder contract provided without build mode')")
    source = replace_one(source, "    require(args.preparation_sha256 is not None, 'build requires its actual work receipt')",
        "    require(args.preparation_sha256 is not None, 'build requires its actual work receipt')\n    require(args.builder_contract == CURRENT_BUILDER_CONTRACT,\n            'explicit current470 contract selection is required; no legacy fallback')")
    ast.parse(source)
    fence_old = (OLD / 'fenced_build.py').read_text()
    fence = replace_one(fence_old, 'CONTROLLER_SHA = ' + repr(sha(old.encode())),
                        'CONTROLLER_SHA = ' + repr(sha(source.encode())))
    fence = replace_one(fence, "ROOT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-07-20261106')",
        "ROOT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-08-20261106')")
    fence = replace_one(fence,
        "        inner_code = scope['main'](['--build', '--preparation-sha256', PREPARATION_SHA])",
        "        inner_code = scope['main'](['--build', '--preparation-sha256', PREPARATION_SHA,\n                                    '--builder-contract', " + repr(KIND) + "])")
    fence = replace_one(fence,
        "    settled_previous_fence = scope['settled_normal06_fence_contract']()",
        "    settled_previous_fence = scope['settled_normal06_fence_contract']()\n    settled_previous_fence.extend(row['pin'] for row in scope['settled_build07_contract']())")
    ast.parse(fence)

    # Pure checks operate on the actual readback, never hypothetical success data.
    scope = {'require': need, 'hashlib': hashlib, 'json': json, 'P': Path, **constants,
        'QUALIFICATION_RESULT': Path(result_pin['path']),
        'BUILD_SOURCE': Path(result['commands'][0]['cwd']),
        'EXPECTED_TESTS': literal(old, 'EXPECTED_TESTS'),
        'EXPECTED_SOURCE_TESTS': literal(old, 'EXPECTED_SOURCE_TESTS'),
        'EXPECTED_SOURCE_DELTA': literal(old, 'EXPECTED_SOURCE_DELTA')}
    pure_names = ['authorization_pin', 'qualify_authorization_observation', 'durable_current470_terminal',
                  'qualify_current470_authorization', 'qualify_settled_build07', 'verify_source_ancestry']
    nodes = {node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
    for name in pure_names:
        exec(compile(ast.Module(body=[nodes[name]], type_ignores=[]), '<candidate-pure-control>', 'exec'), scope)
    validate = scope['qualify_current470_authorization']
    validate(result, terminal, stdout)
    settled = [json.loads(originals[name]) for name, unused, unused2, unused3 in build07_files]
    scope['qualify_settled_build07'](*settled)
    controls = [{'name': 'complete_actual_current470_evidence_accepted', 'passed': True},
                {'name': 'actual_failed07_and_failed_diagnostic_remain_failed_and_settled', 'passed': True}]
    def reject(name, operation):
        try:
            operation()
        except (RuntimeError, ValueError, KeyError, TypeError):
            controls.append({'name': name, 'passed': True, 'synthetic_negative_mutation': True})
        else:
            raise RuntimeError('negative fixture accepted: ' + name)
    bad = copy.deepcopy(result);bad['fresh_source_resume_independent_result_gates'].pop()
    reject('missing_one_source_resume_independent_gate_rejected', lambda: validate(bad, terminal, stdout))
    bad_terminal = copy.deepcopy(terminal);bad_terminal['output_durable'] = False
    reject('non_durable_qualification_rejected', lambda: validate(result, bad_terminal, stdout))
    bad_child = copy.deepcopy(result);bad_child['cleanup']['children'].append({'pid': 1, 'reaped': True})
    reject('residual_or_reaped_child_cannot_be_success', lambda: validate(bad_child, terminal, stdout))
    binary = result['current_artifacts']['builder']
    wanted = scope['authorization_pin'](binary['pin'])
    scope['qualify_authorization_observation'](wanted, binary['owner'], wanted, binary['owner'])
    bad_identity = copy.deepcopy(wanted);bad_identity['identity'][1] += 1
    reject('same_hash_different_inode_rejected', lambda: scope['qualify_authorization_observation'](
        bad_identity, binary['owner'], wanted, binary['owner']))
    bad_owner = copy.deepcopy(binary['owner']);bad_owner['uid'] = 0
    reject('same_bytes_wrong_owner_rejected', lambda: scope['qualify_authorization_observation'](
        wanted, bad_owner, wanted, binary['owner']))
    bad_settled = copy.deepcopy(settled);bad_settled[2]['state'] = 'PASS'
    reject('historical_diagnostic_failure_relabeling_rejected', lambda: scope['qualify_settled_build07'](*bad_settled))

    old_nodes = {node.name: node for node in ast.parse(old).body if isinstance(node, ast.FunctionDef)}
    changed = ['builder_contract', 'verify_prepared', 'plan', 'verify_inputs_after', 'build', 'main']
    equal = [name for name in old_nodes if name not in changed]
    need(all(function(old, name) == function(source, name) for name in equal), 'unrelated inherited function changed')
    need(function(qualifier, 'verify_source_ancestry') == function(source, 'verify_source_ancestry'),
         'qualified ancestry predicate changed')
    need('parent_scope' not in function(source, 'builder_contract') and
         'FileNotFoundError' not in function(source, 'builder_contract'), 'legacy fallback unexpectedly present')
    # Only result fields are added to the actual build body. Its entire resource,
    # launch, wait, cleanup and completion logic must otherwise be identical.
    restored_build = function(source, 'build').replace(
        '        "prior_failure_authorities": context["prior_failure_authority_pins"],\n        "current_builder_authorization": context["current_builder_authorization"]})',
        '        "prior_failure_authorities": context["prior_failure_authority_pins"]})').replace(
        '                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,\n                    "current_builder_contract": CURRENT_BUILDER_CONTRACT,\n                    "actual_current_qualification_sha256": QUALIFICATION_SHA,',
        '                    "builder_sha256": BUILDER_SHA, "strict_targets": TARGETS,')
    need(restored_build == function(old, 'build'), 'build resource/child semantics changed')

    DEST.mkdir(parents=True, mode=0o700)
    packet = json.loads((OLD / 'decoded-source-packet.original.json').read_bytes())
    payload = {}
    for name, original in packet['files'].items():
        raw = original.encode()
        need((OLD / name).read_bytes() == raw, 'inherited packet byte mismatch: ' + name)
        if name == 'framework_build.py':raw = source.encode()
        if name == 'fenced_build.py':raw = fence.encode()
        put(name, raw);payload[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    additions = {
        'actual-current470-qualification-result.json': result_raw,
        'actual-current470-qualification-terminal.original.json': terminal_raw,
        'actual-current470-qualification-stdout.original.jsonl': stdout, **originals}
    for name, raw in additions.items():
        put(name, raw);payload[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    put('current470-contract-minimal.diff', ''.join(
        list(difflib.unified_diff(old.splitlines(True), source.splitlines(True),
            fromfile='source-r4/framework_build.py', tofile='candidate-r1/framework_build.py')) +
        list(difflib.unified_diff(fence_old.splitlines(True), fence.splitlines(True),
            fromfile='source-r4/fenced_build.py', tofile='candidate-r1/fenced_build.py'))).encode())
    document('local-controls.json', {'schema': 1, 'state': 'PURE_LOCAL_CONTROL_PASS',
        'passed': len(controls), 'controls': controls, 'runtime_or_host_commands': 0,
        'Rust_tests_rerun': 0, 'Soong_invoked': False, 'production_ready': False})
    document('inheritance.json', {'schema': 1, 'base_controller': pin(OLD / 'framework_build.py'),
        'byte_identical_inherited_functions': equal, 'changed_functions': changed,
        'original_build_body_identical_except_authorization_receipt_fields': True,
        'new_source_ancestry_predicate_byte_identical_to_actual_qualified_source': True,
        'inherited_payload_files_identical_except': ['framework_build.py', 'fenced_build.py'],
        'Main_snapshot_guard_scope47_lifecycle_sources_unchanged': True,
        'new07_failure_retirement_required_before_any_new_capture': True,
        'parent_normal03_normal05_sources_read_as_immutable_history_only': True,
        'legacy_missing_ELF_never_recreated_opened_or_substituted': True,
        'historical_actual_files_modified': False})
    mapping = json.loads((QUAL / 'source-r1/capability-contract-map.json').read_bytes())
    mapping['schema'] = 'pocket4-current470-explicit-authorization-capability-map-v1'
    mapping['state'] = 'LOCAL_AUTHORIZATION_CANDIDATE_PENDING_REVIEW'
    mapping['new_authorization_contract_connected'] = False
    mapping['current_actual_qualification'] = {'result': pin(QUAL / 'actual-qualification/result.original.json'),
        'terminal': pin(QUAL / 'actual-qualification/status-1.original.txt'),
        'stdout': pin(QUAL / 'actual-qualification/stdout.original.jsonl'), 'job_id': terminal['job_id'],
        'commands': 34, 'independent_tests': 28, 'gates': result['gates'],
        'memory_peak': result['memory_peak'], 'memory_events': result['owned_resource_gate']['events'],
        'swap_peak': result['swap_peak'], 'strict_cleanup': result['cleanup']}
    for row in mapping['contract_mapping']:
        row['historical_candidate_status'] = row.pop('status')
        row['status'] = ('NEW_EXPLICIT_CURRENT_IDENTITY_CONTRACT_PROPOSED; OLD_CONTRACT_STILL_BROKEN'
            if row['id'] == 'legacy-live-elf' else 'SATISFIED_IN_ACTUAL_CURRENT470_QUALIFICATION')
        row['actual_qualification_sha256'] = sha(result_raw)
        row['new_contract_revalidation'] = ('Full current ELF identity/owner/hash; exact actual receipts, logs and 28 libtest files; '
            'existing live complete498/asset checks and original full-build gates remain.')
    by_label = {row['label']: row for row in result['commands']}
    for row in mapping['test_mapping']:
        row['historical_candidate_status'] = row.pop('new_status')
        row['new_status'] = 'ACTUAL_CURRENT470_INDEPENDENT_TEST_PASS'
        actual = by_label[row['new_label']]
        row['actual_command'] = {key: actual[key] for key in ['label', 'argv', 'cwd', 'returncode', 'timed_out',
            'stdout', 'stderr', 'independent_libtest_result', 'focused_result_gate']}
    mapping['old_contract_status_unmodified'] = 'Old468 live ELF is absent; original old03/05/07 route remains failed and is never used as a fallback.'
    document('capability-contract-map.actual.json', mapping)
    document('integration-plan.json', {'schema': 1, 'state': 'LOCAL_CANDIDATE_NOT_SUBMITTED',
        'contract': KIND, 'proposed_build_root': '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-08-20261106',
        'exact_request_created': False, 'remote_actions': 0,
        'selected_entry': 'fenced_build -> main --build --preparation-sha256 <original> --builder-contract ' + KIND,
        'fixed_current_qualification': result_pin,
        'explicit_change': 'Replace live legacy-ELF authorization with the separately executed and fully bound current470 qualification. Original receipts and failed legacy path remain unchanged.',
        'unchanged': {'targets': ['framework-minus-apex', 'libandroid_runtime'], 'dependency_mode': 'Strict',
            'ALLOW_MISSING_DEPENDENCIES': False, 'fresh_MemAvailable_min_bytes': 15*1024**3,
            'memory_max_bytes': 10*1024**3, 'swap_max_bytes': 0, 'cpu_quota_percent': 200,
            'jobs': 1, 'builder_wait_seconds': 6100, 'two_logical_CPUs_remain_free': True,
            'normal_package_source_locks': True, 'complete_source_498': True,
            'explicit_App_scope': 47, 'all_launcher_resolver_completeness_claimed': False,
            'typed_Main_guard_and_pre_post_snapshot': True, 'original_snapshot_budget_seconds': 15,
            'lifecycle_control_count': 4, 'normal05_last_published_projects': 225, 'proposed_projects': 242},
        'future_before_execution': ['root source review and explicit new contract selection',
            'seal exact stage/transport and complete transitive pins for new08 root',
            'fresh host resource, unchanged scope47/Main identities and all original live preflight checks'],
        'actual_Soong_status': 'Not reached by normal06 or normal07; normal05 remains the actual last full-builder failure.',
        'runtime_authorization_enabled': False, 'production_ready': False, 'cleanup_eligible': False})
    document('PAYLOAD_PINS.json', {'schema': 1, 'files': payload, 'stage_or_transport_sealed': False})
    document('SOURCE_PINS.json', {'schema': 1,
        'files': [pin(path) for path in sorted(DEST.iterdir()) if path.is_file()],
        'generator': pin(Path(__file__)),
        'template': pin(BASE / 'analysis_sources/current470_authorization_extra.py.inc'),
        'remote_execution': False, 'host_process_packet': None})
    print(json.dumps({'state': 'LOCAL_CANDIDATE_PREPARED', 'directory': str(DEST),
        'controller': pin(DEST / 'framework_build.py'), 'fence': pin(DEST / 'fenced_build.py'),
        'diff': pin(DEST / 'current470-contract-minimal.diff'), 'pure_controls': len(controls),
        'payload_files': len(payload), 'remote_actions': 0}))


if __name__ == '__main__':
    main()
