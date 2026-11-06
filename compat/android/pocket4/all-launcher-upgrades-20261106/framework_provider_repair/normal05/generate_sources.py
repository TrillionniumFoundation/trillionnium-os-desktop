#!/usr/bin/env python3
"""Local generation and pure controls only. Never submits or seals a request."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import pprint
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
PARENT = HERE / 'reference/normal04'
ACTUAL = PROJECT / 'recovery/independent_repair_r2/actual-execute-01'
NEW_ROOT = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-native-provider-build-05-20261106'
BASELINE_SHA = '7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8'
QUALIFICATION_SHA = '4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6'
GUARD_SHA = 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'


def need(value, why):
    if not value:
        raise RuntimeError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def assign(source, name, expression):
    rows = source.splitlines(keepends=True)
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    need(len(nodes) == 1, 'EXACT_SOURCE_ASSIGNMENT:' + name)
    node = nodes[0]
    rows[node.lineno - 1:node.end_lineno] = [name + ' = ' + expression + '\n']
    return ''.join(rows)


def replace(source, old, new, count=1):
    need(source.count(old) == count, 'EXACT_PARENT_ANCHOR:' + old[:90])
    return source.replace(old, new)


def literal(source, name):
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    need(len(nodes) == 1, 'EXACT_LITERAL:' + name)
    return ast.literal_eval(nodes[0].value)


def write_new(directory, name, value):
    path = directory / name
    raw = value.encode() if isinstance(value, str) else value
    with path.open('xb') as stream:
        stream.write(raw)
    return pin(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'source-r1')
    parser.add_argument('--app-scope', type=Path)
    parser.add_argument('--app-scope-sha256')
    parser.add_argument('--app-scope-host-path')
    args = parser.parse_args()
    parent_files = json.loads((PARENT / 'actual/normal04-stage-receipt.json').read_bytes())['files']
    old = {}
    for name, expected in parent_files.items():
        raw = (PARENT / name).read_bytes()
        need(pin(raw) == expected, 'PARENT_PACKET_PIN:' + name)
        old[name] = raw.decode('utf-8')
    raw_baseline = (ACTUAL / 'baseline.private.json').read_bytes()
    raw_qualification = (ACTUAL / 'qualification.private.json').read_bytes()
    raw_guard = (ACTUAL / 'current_baseline_guard.py').read_bytes()
    need(sha(raw_baseline) == BASELINE_SHA and sha(raw_qualification) == QUALIFICATION_SHA and sha(raw_guard) == GUARD_SHA,
         'EXACT_ACTUAL_R2_AUTHORITIES_REQUIRED')
    baseline, qualification = json.loads(raw_baseline), json.loads(raw_qualification)
    guard_pins = literal(raw_guard, 'PINS')
    source_manifest = (PROJECT / 'recovery/SOURCE_PINS.json').read_bytes()
    need(sha(source_manifest) == guard_pins['manifest_sha'] == qualification['source_manifest_sha256'], 'CURRENT_GUARD_SOURCE_CLOSURE')
    for name, expected in json.loads(source_manifest)['files'].items():
        need(pin((PROJECT / 'recovery' / name).read_bytes()) == expected, 'CURRENT_GUARD_DEPENDENCY:' + name)
    need(qualification['baseline'] == guard_pins['baseline'] and qualification['identity_qualified'] is True and
         qualification['observation_fds']['acquired'] == qualification['observation_fds']['closed'] and
         qualification['observation_fds']['remaining'] == 0 and qualification['observation_fds']['errors'] == [],
         'ACTUAL_R2_QUALIFICATION_REQUIRED')
    scope_pin = packages = None
    if args.app_scope is not None:
        need(args.app_scope_sha256 and args.app_scope_host_path, 'EXPLICIT_FINAL_SCOPE_PIN_REQUIRED')
        raw = args.app_scope.read_bytes()
        need(sha(raw) == args.app_scope_sha256, 'FINAL_SCOPE_FILE_PIN')
        scope = json.loads(raw)
        need(scope['schema'] == 'pocket4-versioned-app-scope-v1' and
             scope['runtime_epoch_sha256'] == baseline['runtime_epoch_sha256'], 'FINAL_SCOPE_EPOCH')
        initial = json.loads((ACTUAL / 'initial-app-scope.private.json').read_bytes())
        need(set(initial['apps']) <= set(scope['apps']) and sha(raw) != sha((ACTUAL / 'initial-app-scope.private.json').read_bytes()),
             'FINAL_SCOPE_MUST_INCLUDE_PREVIOUS_MEMBERS_AND_POST_UPGRADE_CONTENT')
        scope_pin = {'path': args.app_scope_host_path, **pin(raw)}
        packages = sorted(scope['apps'])

    additions = (HERE / 'snapshot_typedguard_additions.py').read_text()
    derive = {'__name__': 'local_pure_derivation', 'need': need}
    exec(compile(additions, 'snapshot_typedguard_additions.py', 'exec'), derive, derive)
    expected = derive['expected_from_baseline'](baseline)
    need(len(expected) == 8, 'CURRENT_EIGHT_ROLES')
    packet = dict(old)
    packet['framework_build.py'] = replace(old['framework_build.py'],
        "ROOT = OWNER / 'typed-ingress-framework-native-provider-build-04-20261106'",
        "ROOT = OWNER / 'typed-ingress-framework-native-provider-build-05-20261106'")

    snapshot = old['main_snapshot.py']
    snapshot = replace(snapshot, 'Fixed seven-role pre/post host protection; never qualifies an Android QA epoch.',
                       'Fixed eight-role typedguard protection; never qualifies Android app or framework QA.')
    snapshot = assign(snapshot, 'BOOT_ID', repr(baseline['runtime']['held']['process_snapshot']['binding']['boot_id']))
    snapshot = assign(snapshot, 'IDENTITY_SOURCE_SHA', repr(BASELINE_SHA))
    snapshot = snapshot.replace('ACTUAL_READ02_STDOUT_SHA', 'CURRENT_QUALIFICATION_SHA')
    snapshot = assign(snapshot, 'CURRENT_QUALIFICATION_SHA', repr(QUALIFICATION_SHA))
    snapshot = assign(snapshot, 'EXPECTED', pprint.pformat(expected, sort_dicts=True, width=110))
    constants = {
        'RUNTIME_EPOCH_SHA': baseline['runtime_epoch_sha256'], 'FRAMEWORK_EPOCH_SHA': baseline['framework_epoch']['sha256'],
        'CURRENT_GUARD_PIN': {'path': guard_pins['root'] + '/current_baseline_guard.py', **pin(raw_guard)},
        'CURRENT_GUARD_PINS': guard_pins, 'APP_SCOPE_PIN': scope_pin, 'APP_SCOPE_PACKAGES': packages,
    }
    extra = '\n'.join(name + ' = ' + pprint.pformat(value, sort_dicts=True, width=110) for name, value in constants.items())
    snapshot = replace(snapshot, 'def qualify_finish(', extra + '\n\n' + additions + '\n\ndef qualify_finish(')
    snapshot = snapshot.replace('FIXED_IDENTITY_DIFFERS_FROM_ACTUAL_READ02', 'FIXED_IDENTITY_DIFFERS_FROM_TYPED_BASELINE')
    snapshot = replace(snapshot, "len(rows) == 7, 'FIXED_SEVEN_ROLES_INCOMPLETE'", "len(rows) == 8, 'FIXED_EIGHT_ROLES_INCOMPLETE'")
    snapshot = replace(snapshot, "    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))",
                       "    qualify_scope_reference(APP_SCOPE_PIN, APP_SCOPE_PACKAGES)\n    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))")
    snapshot = replace(snapshot, "        need(read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip() == BOOT_ID, 'BOOT_CHANGED')",
                       "        need(read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip() == BOOT_ID, 'BOOT_CHANGED')", count=2)
    anchor = "    try:\n        need(read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip() == BOOT_ID, 'BOOT_CHANGED')"
    snapshot = replace(snapshot, anchor,
        "    try:\n        guard = load_current_guard()\n        current_baseline = guard['current_baseline']()\n        qualify_baseline(current_baseline)\n        typed_guard_receipt = guard['current_guard'](current_baseline, action_attempted=False)\n        qualify_typed_guard(typed_guard_receipt)\n        need(read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip() == BOOT_ID, 'BOOT_CHANGED')")
    snapshot = replace(snapshot, "        after_processes = snapshot_processes()",
        "        app_scope_receipt = guard['check_app_scope'](APP_SCOPE_PIN, APP_SCOPE_PACKAGES)\n        qualify_scope_receipt(app_scope_receipt, APP_SCOPE_PIN, APP_SCOPE_PACKAGES)\n        after_processes = snapshot_processes()")
    snapshot = snapshot.replace("'actual_read02_stdout_sha256': CURRENT_QUALIFICATION_SHA", "'current_qualification_sha256': CURRENT_QUALIFICATION_SHA")
    snapshot = replace(snapshot, "                  'protected_processes': after_processes,",
        "                  'protected_processes': after_processes,\n                  'runtime_epoch_sha256': RUNTIME_EPOCH_SHA, 'framework_epoch_sha256': FRAMEWORK_EPOCH_SHA,\n                  'current_guard_source_sha256': CURRENT_GUARD_PIN['sha256'],\n                  'app_scope_sha256': APP_SCOPE_PIN['sha256'], 'app_scope_packages': APP_SCOPE_PACKAGES,\n                  'typed_guard_receipt': typed_guard_receipt, 'app_scope_guard_receipt': app_scope_receipt,")
    snapshot = snapshot.replace("'subprocesses_started': 0", "'subprocesses_started': None, 'readonly_guard_service_queries_possible': True")
    snapshot = snapshot.replace('Only the fixed current seven process identities, boot, historical activation pin, config, original Main limits and counters.',
        'Only the typedguard-bound eight process identities, current baseline/app scope, boot, historical activation pin, config, original Main limits and counters.')
    snapshot = snapshot.replace('This helper starts no child processes.', 'The existing typedguard may start fixed read-only service queries; its children remain owned by the root supervisor.')
    packet['main_snapshot.py'] = snapshot

    lifecycle = assign(old['capture_lifecycle.py'], 'PROTECTED_PIDS', 'frozenset(' + repr(tuple(sorted(row['pid'] for row in expected.values()))) + ')')
    packet['capture_lifecycle.py'] = lifecycle
    supervisor = old['root_snapshot_supervisor.py'].replace('the seven protected Main PIDs', 'the eight protected Main PIDs')
    supervisor = assign(supervisor, 'LIFECYCLE_SHA', repr(sha(lifecycle.encode())))
    supervisor = assign(supervisor, 'SNAPSHOT_SHA', repr(sha(snapshot.encode())))
    packet['root_snapshot_supervisor.py'] = supervisor

    fence = old['fenced_build.py']
    fence = assign(fence, 'ROOT', 'Path(' + repr(NEW_ROOT) + ')')
    for name, member in [('CONTROLLER_SHA', 'framework_build.py'), ('LIFECYCLE_SHA', 'capture_lifecycle.py'),
                         ('ROOT_SUPERVISOR_SHA', 'root_snapshot_supervisor.py'), ('SNAPSHOT_SHA', 'main_snapshot.py')]:
        fence = assign(fence, name, repr(sha(packet[member].encode())))
    fence = fence.replace("'actual_read02_stdout_sha256'", "'current_qualification_sha256'")
    fence = replace(fence, "{'android_init', 'daemon', 'launcher', 'presenter', 'surfaceflinger', 'zygote64', 'system_server'},",
                          "{'android_init', 'daemon', 'launcher', 'presenter', 'surfaceflinger', 'zygote64', 'system_server', 'composer'},")
    fence = replace(fence, "                  'cell_sha256', 'limits', 'main_cgroup', 'main_cgroup_identity')",
        "                  'cell_sha256', 'limits', 'main_cgroup', 'main_cgroup_identity',\n                  'runtime_epoch_sha256', 'framework_epoch_sha256', 'current_guard_source_sha256',\n                  'app_scope_sha256', 'app_scope_packages')")
    fence = fence.replace('current seven-role identity, historical activation, limits or OOM fence failed',
                          'current typedguard eight-role identity/app scope, historical activation, limits or OOM fence failed')
    packet['fenced_build.py'] = fence

    controls = old['pure_controls.py'].replace('FIXED_IDENTITY_DIFFERS_FROM_ACTUAL_READ02', 'FIXED_IDENTITY_DIFFERS_FROM_TYPED_BASELINE')
    controls = controls.replace("'actual_read02_stdout_sha256': snapshot['ACTUAL_READ02_STDOUT_SHA']",
                                "'current_qualification_sha256': snapshot['CURRENT_QUALIFICATION_SHA']")
    controls = replace(controls, "        'protected_processes': copy.deepcopy(snapshot['EXPECTED']),",
        "        'protected_processes': copy.deepcopy(snapshot['EXPECTED']),\n        'runtime_epoch_sha256': snapshot['RUNTIME_EPOCH_SHA'], 'framework_epoch_sha256': snapshot['FRAMEWORK_EPOCH_SHA'],\n        'current_guard_source_sha256': snapshot['CURRENT_GUARD_PIN']['sha256'],\n        'app_scope_sha256': '1' * 64, 'app_scope_packages': ['synthetic.one', 'synthetic.two'],")
    controls = controls.replace('same_current_seven_roles_pass', 'same_current_eight_roles_pass')
    controls = replace(controls, "    need(len(passed) == len(set(passed)) == 45, 'CONTROL_CASE_COUNT')",
        (HERE / 'pure_control_additions.py.inc').read_text() + "\n    need(len(passed) == len(set(passed)) == 59, 'CONTROL_CASE_COUNT')")
    packet['pure_controls.py'] = controls
    packet['actual-current-runtime-baseline.json'] = raw_baseline.decode()
    packet['actual-current-qualification.json'] = raw_qualification.decode()
    packet['actual-current-baseline-guard.py'] = raw_guard.decode()
    packet['actual-current-guard-source-manifest.json'] = source_manifest.decode()

    for name, text in packet.items():
        if name.endswith('.py'):
            ast.parse(text, filename=name)
    pure = {'__name__': 'normal05_actual_local_pure_controls', '__file__': '<normal05-local-pure-controls>'}
    exec(compile(controls, 'pure_controls.py', 'exec'), pure, pure)
    result = pure['run'](packet)
    need(result['state'] == 'PASS' and result['passed'] == 59, 'NEW_LOCAL_PURE_CONTROLS_INCOMPLETE')
    expected_packet = {name: pin(text.encode()) for name, text in packet.items()}
    stage = (PARENT / 'stage.py').read_text()
    stage = assign(stage, 'ROOT', 'Path(' + repr(NEW_ROOT) + ')')
    stage = assign(stage, 'EXPECTED', pprint.pformat(expected_packet, sort_dicts=True, width=110))
    stage = replace(stage, "    controls_scope={'__name__':'frozen_host_build_pure_controls','__file__':'<frozen-pure-controls>'}",
        "    binding_scope={'__name__':'normal05_binding_only','__file__':'<normal05-binding-only>'}\n    exec(compile(packet['main_snapshot.py'],'main_snapshot.py','exec'),binding_scope,binding_scope)\n    binding_scope['qualify_scope_reference'](binding_scope['APP_SCOPE_PIN'],binding_scope['APP_SCOPE_PACKAGES'])\n    controls_scope={'__name__':'frozen_host_build_pure_controls','__file__':'<frozen-pure-controls>'}")
    stage = stage.replace("controls['passed']!=45", "controls['passed']!=59")
    ast.parse(stage)
    boundary = (PARENT / 'transport-boundary.py').read_text()
    boundary = assign(boundary, 'WIRE_BYTES', 'None')
    boundary = assign(boundary, 'WIRE_SHA256', 'None')
    boundary = assign(boundary, 'STAGE_BYTES', repr(len(stage.encode())))
    boundary = assign(boundary, 'STAGE_SHA256', repr(sha(stage.encode())))
    boundary = replace(boundary, 'raw=sys.stdin.buffer.read(WIRE_BYTES+1)',
        "if WIRE_BYTES is None or WIRE_SHA256 is None:\n    raise RuntimeError('NORMAL05_EXACT_REQUEST_NOT_SEALED')\nraw=sys.stdin.buffer.read(WIRE_BYTES+1)")
    ast.parse(boundary)
    args.output.mkdir(mode=0o700)
    rows = {}
    for name, text in packet.items():
        rows[name] = write_new(args.output, name, text)
    rows['stage.py'] = write_new(args.output, 'stage.py', stage)
    rows['transport-boundary.py'] = write_new(args.output, 'transport-boundary.py', boundary)
    result.update({'new_scope_bound_in_source': scope_pin is not None, 'runtime_or_app_QA_pass_count': 0,
                   'actual_scope_guard_executed': False, 'remote_submitted': False, 'Soong_invoked': False})
    rows['local-pure-controls-result.json'] = write_new(args.output, 'local-pure-controls-result.json', json.dumps(result, indent=2) + '\n')
    diff = ''.join(''.join(difflib.unified_diff(old[name].splitlines(keepends=True), packet[name].splitlines(keepends=True),
                 fromfile='normal04/' + name, tofile='normal05/' + name))
                 for name in ('framework_build.py', 'main_snapshot.py', 'capture_lifecycle.py', 'root_snapshot_supervisor.py', 'fenced_build.py', 'pure_controls.py'))
    rows['source-diff.patch'] = write_new(args.output, 'source-diff.patch', diff)
    manifest = {'schema': 'pocket4-normal05-unsealed-source-v1',
                'state': 'SOURCES_PREPARED_FINAL_SCOPE_REQUIRED' if scope_pin is None else 'SOURCES_PREPARED_SCOPE_BOUND_EXACT_REQUEST_UNSEALED',
                'files': rows, 'final_app_scope_reference': scope_pin, 'final_app_scope_packages': packages,
                'parent_packet_files': parent_files, 'runtime_epoch_sha256': baseline['runtime_epoch_sha256'],
                'local_pure_controls': result['passed'], 'Main_actions': 0, 'Android_actions': 0, 'Main_observation_performed': False,
                'host_build_or_source_stage_executed': False, 'exact_request_sealed': False, 'remote_submitted': False,
                'production_ready': False, 'cleanup_eligible': False,
                'generator_sources': {name: pin((HERE / name).read_bytes()) for name in
                                      ('generate_sources.py', 'snapshot_typedguard_additions.py', 'pure_control_additions.py.inc')}}
    manifest_pin = write_new(args.output, 'SOURCE_PINS.json', json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'state': manifest['state'], 'directory': str(args.output), 'files': len(rows),
                      'local_pure_controls_passed': result['passed'], 'manifest': manifest_pin,
                      'exact_request_sealed': False, 'remote_submitted': False, 'production_ready': False}))


if __name__ == '__main__':
    main()
