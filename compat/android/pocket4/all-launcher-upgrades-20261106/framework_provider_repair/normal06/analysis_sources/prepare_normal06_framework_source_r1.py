#!/usr/bin/env python3
"""Prepare an unsealed normal06 successor from actual local pinned originals.

This writes only local review material. No host, Android, compiler, build or
process controller is invoked. The final 47-package scope remains mandatory.
"""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path
import pprint

BASE = Path(__file__).resolve().parents[1]
PARENT = BASE / 'reference/normal05-source-r2'
OUTPUT = BASE / 'source-r1'
NEW_ROOT = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-06-20261106'
NEW_KEY = 'pocket4-native-typed-ingress-framework-strict-systemui-provider-two-target-build-06-20261106'
BUILD_PARENT = '/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixed(path, size, digest):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, 'fixed local input changed: ' + str(path))
    return raw.decode('utf-8')


def put(path, raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    if path.exists():
        need(path.read_bytes() == raw, 'frozen output differs: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def replace_nodes(text, replacements, functions=False):
    rows = text.splitlines(keepends=True)
    found = set()
    spans = []
    for node in ast.parse(text).body:
        names = [node.name] if functions and isinstance(node, ast.FunctionDef) else [
            target.id for target in getattr(node, 'targets', []) if isinstance(target, ast.Name)]
        for name in names:
            if name in replacements:
                need(name not in found, 'duplicate target: ' + name)
                found.add(name)
                spans.append((node.lineno - 1, node.end_lineno, replacements[name].rstrip() + '\n'))
    need(found == set(replacements), 'missing replacement: ' + repr(set(replacements) - found))
    for start, end, replacement in reversed(sorted(spans)):
        rows[start:end] = [replacement]
    return ''.join(rows)


def replace_once(text, old, new):
    need(text.count(old) == 1, 'non-unique exact replacement: ' + old[:120])
    return text.replace(old, new)


def main():
    stage = fixed(PARENT / 'stage.py', 7137, '5723e4064379832141e068fb87b7a4460e594545ffc3d9a94f779df847b9ad83')
    stage_ns = {'__name__': 'local_parent_stage_metadata', '__file__': str(PARENT / 'stage.py')}
    exec(compile(stage, str(PARENT / 'stage.py'), 'exec'), stage_ns, stage_ns)
    files = {name: fixed(PARENT / name, pin['bytes'], pin['sha256']) for name, pin in stage_ns['EXPECTED'].items()}
    actual_result = fixed(BASE / 'builder470-hostprep-r2/root-readback-01/result.original.json',
        76136, '6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8')
    result = json.loads(actual_result)
    result_manifest = fixed(BASE / 'builder470-hostprep-r2/actual/stage/actual-candidate-source-manifest.json',
        99075, 'f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd')
    actual_admission = fixed(BASE / 'builder470-hostprep-r2/root-readback-01/resource-admission.original.json',
        2746, '5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031')
    published = fixed(BASE / 'reference/normal05-actual-graph/droidloom-source-manifest.json',
        109252, '5ae96f8d2bc32986fdbf8fea12f54dbcb02b1ed1601894b2b23998f61aba0d7d')
    inner = fixed(BASE / 'reference/normal05-actual-authority/attempt-01/terminal.json',
        3176, '232a63a6a48c4248346921ee7f9cb86f13d17dcd3abcb32e6a52856cda0dbbde')
    outer = fixed(BASE / 'reference/normal05-actual-authority/build-fences-01/terminal.json',
        24715, '1353fe85e19ae79f4b615e7f38efcbb2f45f8a34529a3be6c59a6ed585e1a1f2')
    lock = fixed(BASE / 'candidate-r3/android/manifest/m2-role-ingress-provider3-source-lock.json',
        103409, 'f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772')
    controller_parent = files['framework_build.py']
    need(sha(controller_parent.encode()) == 'f4ab5e09fc22b759811bfa9480c2de555dbc5096bc1258a984dbd33809db734b',
         'original normal05 controller differs')
    assignments = {
        'ROOT': "ROOT = OWNER / 'typed-ingress-framework-systemui-provider-build-06-20261106'",
        'BUILD_PARENT': 'BUILD_PARENT = P(' + repr(BUILD_PARENT) + ')',
        'BUILDER': "BUILDER = BUILD_PARENT / 'compile01/cargo-target/debug/droidloom-update'",
        'BUILDER_SHA': 'BUILDER_SHA = ' + repr(result['builder']['sha256']),
        'BUILDER_BYTES': 'BUILDER_BYTES = ' + repr(result['builder']['bytes']),
        'BUILD_RESULT': "BUILD_RESULT = BUILD_PARENT / 'compile01/result.json'",
        'QUALIFICATION_RESULT': 'QUALIFICATION_RESULT = BUILD_RESULT',
        'QUALIFICATION_SHA': 'QUALIFICATION_SHA = ' + repr(sha(actual_result.encode())),
        'BUILD_RESULT_SHA': 'BUILD_RESULT_SHA = ' + repr(sha(actual_result.encode())),
        'BUILD_RESULT_BYTES': 'BUILD_RESULT_BYTES = 76136',
        'SOURCE_MANIFEST_SHA': 'SOURCE_MANIFEST_SHA = ' + repr(sha(result_manifest.encode())),
        'EXTENDED_LOCK_SHA': 'EXTENDED_LOCK_SHA = ' + repr(sha(lock.encode())) + '\n' +
            "PREVIOUS_NATIVE_PROVIDER_LOCK_SHA = '72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d'",
        'EXPECTED_TESTS': 'EXPECTED_TESTS = ' + repr(result['test_names']),
        'PREVIOUS_ROOT': "PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-native-provider-build-05-20261106'",
        'PUBLISHED_MANIFEST_SHA': 'PUBLISHED_MANIFEST_SHA = ' + repr(sha(published.encode())),
        'PUBLISHED_MANIFEST_BYTES': 'PUBLISHED_MANIFEST_BYTES = 109252',
        'PRIOR_INNER_SHA': 'PRIOR_INNER_SHA = ' + repr(sha(inner.encode())),
        'PRIOR_OUTER_SHA': 'PRIOR_OUTER_SHA = ' + repr(sha(outer.encode())),
        'EXPECTED_COMPILE_LABELS': 'EXPECTED_COMPILE_LABELS = ' + repr([row['label'] for row in result['commands']]),
        'EXPECTED_SOURCE_DELTA': 'EXPECTED_SOURCE_DELTA = ' + repr(result['source_delta']),
    }
    controller = replace_nodes(controller_parent, assignments)
    contract = (BASE / 'analysis_sources/builder470_contract.py.inc').read_text()
    controller = replace_nodes(controller, {'builder_contract': contract}, functions=True)
    for old, new in [
        ("PRIOR_INNER_SHA, 5239", "PRIOR_INNER_SHA, 3176"),
        ("PRIOR_OUTER_SHA, 24689", "PRIOR_OUTER_SHA, 24715"),
        ("len(inner['cleanup']['children']) == 27", "len(inner['cleanup']['children']) == 4"),
        ("f1458d03292c14c05b14fdfe76091cfd7b2ffe05df2bbb3480be8d2cd20a329b", "5453e358a70d1531218699641b289e58dfbe13202d7ad369f46b5fbf016eb151"),
        ("a517eefb94ef2116400ac329e0fb74cf74eb34379a726fb2b6403f74d8659ad8", "615d8e9d5fdd2e2fb31c605e4eed204e92a5f0ab21621765bb6c27115d0c339e"),
        ('prior normal03 strict failure', 'prior normal05 strict failure'),
        ("published['source_lock_sha256'] == PREVIOUS_PROVIDER_LOCK_SHA", "published['source_lock_sha256'] == PREVIOUS_NATIVE_PROVIDER_LOCK_SHA"),
        ("len(published['plan']['projects']) == 224", "len(published['plan']['projects']) == 225"),
        ('actual current provider1 published source manifest differs', 'actual current provider2 published source manifest differs'),
        ("'previous_locked_projects': 224, 'new_locked_projects': 225", "'previous_locked_projects': 225, 'new_locked_projects': 242"),
        ('actual 493-file builder source changed', 'actual 498-file builder source changed'),
        ("context['qualification_pin'] = json_pin(QUALIFICATION_RESULT, QUALIFICATION_SHA, 65386)[1]", "context['qualification_pin'] = json_pin(QUALIFICATION_RESULT, QUALIFICATION_SHA, BUILD_RESULT_BYTES)[1]"),
        ("'builder_source_files': 493, 'actual_host_compile_commands': 20, 'actual_current_exact_controls': 16", "'builder_source_files': 498, 'actual_host_compile_commands': 23, 'actual_current_exact_controls': 19"),
        ("'qualification_commands': 17, 'unchanged_source_resume_controls_inherited': 9", "'qualification_commands': 19, 'qualification_commands_included_in_host_compile': True,\n        'separate_qualification_commands': 0, 'unchanged_source_resume_controls_inherited': 9"),
        ('published 224-project provider1 lock, then normal monotonic reconciliation to 225 locked projects', 'published 225-project provider2 lock, then normal monotonic reconciliation to 242 locked projects'),
        ("'prior_outer_failure_sha256': PRIOR_OUTER_SHA, 'prior_reaped_children': 27", "'prior_outer_failure_sha256': PRIOR_OUTER_SHA, 'prior_reaped_children': 4,\n        'actual_builder470_job_id': '1a1b1d86cb7-fc05-7b1f',\n        'prior_compile_status_timeout_preserved_then_authoritatively_settled': True"),
        ("'prior_normal_peak_bytes': 8141615104", "'prior_normal_peak_bytes': 3168141312"),
        ("'actual_static_compile_memory_max_events': 314", "'actual_static_compile_memory_max_events': 657"),
        ("len(document['plan']['projects']) == 225", "len(document['plan']['projects']) == 242"),
        ("inputs['native_provider_extension_exact'] is True and", "inputs['native_provider_extension_exact'] is True and\n            inputs['previous_native_provider_source_lock_sha256'] == PREVIOUS_NATIVE_PROVIDER_LOCK_SHA and\n            inputs['systemui_provider_extension_exact'] is True and"),
        ("lock, _ = json_pin(BUILD_SOURCE / 'android/manifest/m2-role-ingress-provider2-source-lock.json',\n                       EXTENDED_LOCK_SHA, 96957)", "lock, _ = json_pin(BUILD_SOURCE / 'android/manifest/m2-role-ingress-provider3-source-lock.json',\n                       EXTENDED_LOCK_SHA, 103409)"),
        ("'published_projects': 225", "'published_projects': 242"),
    ]:
        controller = replace_once(controller, old, new)
    files['parent-normal05-framework_build.py'] = controller_parent
    files['framework_build.py'] = controller
    files['actual-builder470-result.json'] = actual_result
    files['actual-builder470-resource-admission.json'] = actual_admission
    files['expected-builder470-manifest.json'] = result_manifest
    files['actual-provider-source-lock.json'] = lock
    files['actual-published-source-manifest.json'] = published
    files['prior-framework-inner-terminal.json'] = inner
    files['prior-framework-outer-terminal.json'] = outer
    files['main_snapshot.py'] = replace_nodes(files['main_snapshot.py'], {
        'APP_SCOPE_PIN': 'APP_SCOPE_PIN = None  # Required external current 47-package original, not the old 46.',
        'APP_SCOPE_PACKAGES': 'APP_SCOPE_PACKAGES = None  # Set only by the exact final-scope sealer.',
    })
    files['fenced_build.py'] = replace_nodes(files['fenced_build.py'], {
        'ROOT': 'ROOT = Path(' + repr(NEW_ROOT) + ')',
        'CONTROLLER_SHA': 'CONTROLLER_SHA = ' + repr(sha(controller.encode())),
        'SNAPSHOT_SHA': 'SNAPSHOT_SHA = ' + repr(sha(files['main_snapshot.py'].encode())),
    })
    controls = files['pure_controls.py']
    for old, new in [
        ("len(lock['projects']) == 225", "len(lock['projects']) == 242"),
        ('complete_expected_225_project_plan', 'complete_expected_242_project_plan'),
        ('actual_provider1_224_manifest_is_not_current_completion', 'actual_provider2_225_manifest_is_not_current_completion'),
    ]:
        controls = replace_once(controls, old, new)
    files['pure_controls.py'] = controls
    pins = {name: {'bytes': len(text.encode()), 'sha256': sha(text.encode())} for name, text in sorted(files.items())}
    stage = replace_nodes(stage, {
        'ROOT': 'ROOT = Path(' + repr(NEW_ROOT) + ')',
        'EXPECTED': 'EXPECTED = ' + pprint.pformat(pins, sort_dicts=True, width=110),
    })
    stage = stage.replace('normal05_binding_only', 'normal06_binding_only').replace('<normal05-binding-only>', '<normal06-binding-only>')
    transport = (PARENT / 'transport.py').read_text()
    transport = replace_nodes(transport, {
        'WIRE_BYTES': 'WIRE_BYTES = None', 'WIRE_SHA256': 'WIRE_SHA256 = None',
        'STAGE_BYTES': 'STAGE_BYTES = ' + str(len(stage.encode())),
        'STAGE_SHA256': 'STAGE_SHA256 = ' + repr(sha(stage.encode())),
    }).replace('NORMAL05_EXACT_REQUEST_NOT_SEALED', 'NORMAL06_EXACT_REQUEST_NOT_SEALED')
    for name, text in {**files, 'stage.py': stage, 'transport.py': transport}.items():
        if name.endswith('.py'):
            compile(text, name, 'exec')
        put(OUTPUT / name, text)
    controls_ns = {'__name__': 'local_normal06_pure_controls', '__file__': '<local-normal06-pure-controls>'}
    exec(compile(controls, 'pure_controls.py', 'exec'), controls_ns, controls_ns)
    outcome = controls_ns['run'](files)
    need(outcome['state'] == 'PASS' and outcome['passed'] == 59, 'inherited local controls failed')
    put(OUTPUT / 'pure-controls.actual.json', dump(outcome))
    framework_ns = {'__name__': 'local_normal06_plan_only', '__file__': '<local-normal06-plan-only>'}
    exec(compile(controller, 'framework_build.py', 'exec'), framework_ns, framework_ns)
    framework_ns['qualify_builder470_receipt'](copy.deepcopy(result))
    mutations = [
        ('residual_reaped_child_not_pass', lambda r: r['cleanup']['children'].append({'pid': 1, 'reaped': True})),
        ('missing_independent_result_gate_not_pass', lambda r: r['independent_result_gates'].pop()),
        ('changed_source_continuity_not_pass', lambda r: r.__setitem__('candidate_source_unchanged_after', False)),
    ]
    negative = []
    for name, mutate in mutations:
        fixture = copy.deepcopy(result)
        mutate(fixture)
        try:
            framework_ns['qualify_builder470_receipt'](fixture)
        except RuntimeError as error:
            negative.append({'name': name, 'rejected': True, 'error': str(error)})
        else:
            raise RuntimeError('negative fixture accepted: ' + name)
    put(OUTPUT / 'builder470-receipt-controls.actual.json', dump({
        'schema': 1, 'state': 'PASS', 'scope': 'Pure local actual-receipt schema plus three explicit negative mutations.',
        'actual_result_pin': {'bytes': 76136, 'sha256': sha(actual_result.encode())},
        'actual_result_metadata_accepted': True, 'negative_fixtures': negative,
        'host_observations': 0, 'compilers_or_processes_run': 0, 'production_ready': False,
    }))
    plan = framework_ns['plan']()
    plan.update({'state': 'SOURCE_PREPARED_UNSEALED_SCOPE_REQUIRED',
        'external_current_scope_required_packages': 47, 'final_current_scope_pin': None,
        'old_46_scope_is_current_complete': False, 'framework_build_submitted': False,
        'host_window_authorized': False, 'execution_permitted': False, 'production_ready': False,
        'cleanup_eligible': False})
    put(OUTPUT / 'execution-plan.unsealed.json', dump(plan))
    request = json.loads((PARENT / 'parent-request-without-stdin.json').read_text())
    request['idempotency_key'] = NEW_KEY
    request['args'][3] = transport
    put(OUTPUT / 'request-template.unsealed.json', dump(request))
    diffs = []
    for name in sorted(set(stage_ns['EXPECTED']) | {'stage.py', 'transport.py'}):
        before = (PARENT / name).read_text()
        after = (OUTPUT / name).read_text()
        if before != after:
            diffs.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                fromfile='normal05-source-r2/' + name, tofile='normal06-source-r1/' + name))
    put(OUTPUT / 'parent-to-successor.diff', ''.join(diffs))
    material = {name: {'bytes': len(text.encode()), 'sha256': sha(text.encode())}
                for name, text in sorted({**files, 'stage.py': stage, 'transport.py': transport}.items())}
    manifest = {'schema': 'pocket4-normal06-unsealed-source-v1', 'state': 'UNSEALED_WAITING_ACTUAL_47_SCOPE',
        'files': material, 'staged_members': sorted(files), 'root': NEW_ROOT, 'key': NEW_KEY,
        'baseline_normal05_controller': {'bytes': 60970, 'sha256': sha(controller_parent.encode())},
        'builder470_actual_compile_job': '1a1b1d86cb7-fc05-7b1f', 'current_builder': result['builder'],
        'source_lock_sha256': sha(lock.encode()), 'source_projects': 242, 'root_links': 8,
        'prior_published_source_projects': 225, 'pure_controls_passed': 59,
        'resource_process_lifecycle_functions_unchanged': True,
        'current_scope_pin': None, 'required_exact_packages': 47, 'framework_build_submitted': False,
        'no_runtime_or_Java_JNI_qualification_inherited': True, 'production_ready': False, 'cleanup_eligible': False}
    put(OUTPUT / 'SOURCE_PINS.json', dump(manifest))
    print(json.dumps({'root': str(OUTPUT), 'files': len(material),
        'source_manifest_bytes': len(dump(manifest).encode()), 'source_manifest_sha256': sha(dump(manifest).encode()),
        'pure_controls': 59, 'receipt_negative_controls': len(negative), 'scope_sealed': False}))


if __name__ == '__main__':
    main()
