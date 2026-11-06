#!/usr/bin/env python3
"""Prepare build07 after the settled build06 nested snapshot-pin failure.

Local source/packet generation only. No stage, Main, compiler or remote job.
"""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path
import pprint
import zlib

BASE = Path(__file__).resolve().parents[1]
PREVIOUS = BASE / 'source-r3'
OUTPUT = BASE / 'source-r4'
ACTUAL = BASE / 'actual-build06-fence-failure'
OLD_ROOT = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-06-20261106'
NEW_ROOT = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-07-20261106'
NEW_KEY = 'pocket4-native-typed-ingress-framework-strict-systemui-provider-two-target-build-07-20261106'
FAILED = [
    ('terminal.original.json', 'settled-normal06-fence-terminal.json', 'terminal.json', 8115,
     '867855adf975072432aada65f4decded4b88c725a6a5d2e9a17909ae1f94b841'),
    ('control-root-timeout.root-supervisor.stdout.original.json', 'settled-normal06-control-root-stdout.json',
     'control-root-timeout.root-supervisor.stdout.json', 904,
     'e78dc93dcb57b4bcd5390d5ff41f82dce63e25be88c311a564969a5396273b5a'),
    ('after.root-supervisor.stdout.original.json', 'settled-normal06-after-root-stdout.json',
     'after.root-supervisor.stdout.json', 896,
     '0df37043724399fd0b3b6597c4e77c6a72e14346271236b65d98a94d1554a58d'),
]


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def fixed(path, size, digest):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, 'original input changed: ' + str(path))
    return raw


def put(path, raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    if path.exists():
        need(path.read_bytes() == raw, 'frozen build07 output differs: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def assignments(source):
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            result[node.targets[0].id] = value
    return result


def replace_nodes(source, replacements):
    rows = source.splitlines(keepends=True)
    changes, found = [], set()
    for node in ast.parse(source).body:
        for target in getattr(node, 'targets', []):
            if isinstance(target, ast.Name) and target.id in replacements:
                need(target.id not in found, 'duplicate assignment target')
                found.add(target.id)
                changes.append((node.lineno - 1, node.end_lineno, replacements[target.id].rstrip() + '\n'))
    need(found == set(replacements), 'missing constant assignment')
    for start, end, replacement in sorted(changes, reverse=True):
        rows[start:end] = [replacement]
    return ''.join(rows)


def replace_once(source, old, new):
    need(source.count(old) == 1, 'non-unique source edit: ' + old[:100])
    return source.replace(old, new)


def check_chain(files, stage, transport, wire, encoded):
    # Inner pin first: catches the actual failure even if every outer hash was
    # honestly recomputed around a stale supervisor snapshot constant.
    root = assignments(files['root_snapshot_supervisor.py'])
    fence = assignments(files['fenced_build.py'])
    child_sha = sha(files['main_snapshot.py'].encode())
    lifecycle_sha = sha(files['capture_lifecycle.py'].encode())
    need(root['SNAPSHOT_SHA'] == child_sha, 'INNER_ROOT_SNAPSHOT_PIN_DIFFERS')
    need(root['LIFECYCLE_SHA'] == lifecycle_sha, 'INNER_ROOT_LIFECYCLE_PIN_DIFFERS')
    need(fence['SNAPSHOT_SHA'] == child_sha and fence['LIFECYCLE_SHA'] == lifecycle_sha and
         fence['ROOT_SUPERVISOR_SHA'] == sha(files['root_snapshot_supervisor.py'].encode()) and
         fence['CONTROLLER_SHA'] == sha(files['framework_build.py'].encode()), 'FENCE_PIN_CHAIN_DIFFERS')
    pins = {name: {'bytes': len(text.encode()), 'sha256': sha(text.encode())} for name, text in files.items()}
    need(assignments(stage)['EXPECTED'] == pins, 'STAGE_MEMBER_PIN_CHAIN_DIFFERS')
    payload = json.loads(wire)
    need(payload == {'schema': 1, 'stage': stage, 'files': files}, 'DECODED_PACKET_MEMBERS_DIFFER')
    constants = assignments(transport)
    need(constants['STAGE_BYTES'] == len(stage.encode()) and constants['STAGE_SHA256'] == sha(stage.encode()) and
         constants['WIRE_BYTES'] == len(wire) and constants['WIRE_SHA256'] == sha(wire), 'TRANSPORT_RAW_PIN_CHAIN_DIFFERS')
    nodes = [node for node in ast.parse(transport).body if isinstance(node, (ast.Import, ast.FunctionDef)) or
             (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant))]
    scope = {'__name__': 'pure_build07_transport_chain'}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<pure-build07-chain>', 'exec'), scope, scope)
    need(scope['decode_exact_wire'](encoded) == wire, 'TRANSPORT_ROUNDTRIP_DIFFERS')
    return {'snapshot_sha256': child_sha, 'lifecycle_sha256': lifecycle_sha,
        'root_supervisor_sha256': fence['ROOT_SUPERVISOR_SHA'], 'controller_sha256': fence['CONTROLLER_SHA'],
        'stage_sha256': sha(stage.encode()), 'decoded_packet_sha256': sha(wire), 'encoded_sha256': sha(encoded)}


def main():
    previous_manifest_raw = fixed(PREVIOUS / 'SOURCE_PINS.json', 9480,
        'd1b551b6ce44dd3084f6bbeba47c4503184e55f1b3e057392f8d6fc3ff33e665')
    previous = json.loads(previous_manifest_raw)
    originals = {name: fixed(PREVIOUS / name, pin['bytes'], pin['sha256']).decode('utf-8')
                 for name, pin in previous['files'].items()}
    files = {name: originals[name] for name in previous['staged_members']}
    for local_name, staged_name, remote_name, size, digest in FAILED:
        files[staged_name] = fixed(ACTUAL / local_name, size, digest).decode('utf-8')
    controller = replace_nodes(files['framework_build.py'], {
        'ROOT': "ROOT = OWNER / 'typed-ingress-framework-systemui-provider-build-07-20261106'",
        'PREVIOUS_ROOT': "PREVIOUS_ROOT = OWNER / 'typed-ingress-framework-native-provider-build-05-20261106'\n" +
            'SETTLED_FENCE_ROOT = P(' + repr(OLD_ROOT + '/build-fences-01') + ')',
    })
    settled = (BASE / 'analysis_sources/settled_normal06_fence_contract.py.inc').read_text()
    controller = replace_once(controller, 'def prior_failure_contract():', settled + '\n\ndef prior_failure_contract():')
    controller = replace_once(controller, '    pins.append(bp_row)\n    return published, pins',
        '    pins.append(bp_row)\n    pins.extend(settled_normal06_fence_contract())\n    return published, pins')
    files['framework_build.py'] = controller
    snapshot_sha = sha(files['main_snapshot.py'].encode())
    files['root_snapshot_supervisor.py'] = replace_nodes(files['root_snapshot_supervisor.py'], {
        'SNAPSHOT_SHA': 'SNAPSHOT_SHA = ' + repr(snapshot_sha),
    })
    fence = replace_nodes(files['fenced_build.py'], {
        'ROOT': 'ROOT = Path(' + repr(NEW_ROOT) + ')',
        'CONTROLLER_SHA': 'CONTROLLER_SHA = ' + repr(sha(controller.encode())),
        'ROOT_SUPERVISOR_SHA': 'ROOT_SUPERVISOR_SHA = ' + repr(sha(files['root_snapshot_supervisor.py'].encode())),
    })
    fence = replace_once(fence, "    exec(compile(source, 'frozen_combined_build.py', 'exec'), scope, scope)\n",
        "    exec(compile(source, 'frozen_combined_build.py', 'exec'), scope, scope)\n" +
        "    settled_previous_fence = scope['settled_normal06_fence_contract']()\n")
    fence = replace_once(fence, "                       'automatic_retry': False, 'Main_actions': 0})",
        "                       'automatic_retry': False, 'Main_actions': 0,\n" +
        "                       'settled_previous_pre_builder_failure_authorities': settled_previous_fence})")
    files['fenced_build.py'] = fence
    pins = {name: {'bytes': len(text.encode()), 'sha256': sha(text.encode())}
            for name, text in sorted(files.items())}
    stage = replace_nodes(originals['stage.py'], {
        'ROOT': 'ROOT = Path(' + repr(NEW_ROOT) + ')',
        'EXPECTED': 'EXPECTED = ' + pprint.pformat(pins, sort_dicts=True, width=110),
    })
    wire = dump({'schema': 1, 'stage': stage, 'files': files}).encode()
    packed = zlib.compress(wire, level=9)
    encoded = base64.b64encode(packed)
    need(len(encoded) <= 1048576 and len(wire) <= 2097152, 'existing transport limits exceeded')
    transport = replace_nodes(originals['transport.py'], {
        'WIRE_BYTES': 'WIRE_BYTES = ' + str(len(wire)), 'WIRE_SHA256': 'WIRE_SHA256 = ' + repr(sha(wire)),
        'STAGE_BYTES': 'STAGE_BYTES = ' + str(len(stage.encode())), 'STAGE_SHA256': 'STAGE_SHA256 = ' + repr(sha(stage.encode())),
        'ENCODED_BYTES': 'ENCODED_BYTES = ' + str(len(encoded)), 'ENCODED_SHA256': 'ENCODED_SHA256 = ' + repr(sha(encoded)),
        'COMPRESSED_BYTES': 'COMPRESSED_BYTES = ' + str(len(packed)), 'COMPRESSED_SHA256': 'COMPRESSED_SHA256 = ' + repr(sha(packed)),
    })
    materials = {**files, 'stage.py': stage, 'transport.py': transport}
    for name, text in materials.items():
        if name.endswith('.py'):
            compile(text, name, 'exec')
    chain = check_chain(files, stage, transport, wire, encoded)
    # This positive-control component uses actual original JSON in memory to
    # catch schema errors. It does not fake host identities or execute a guard.
    framework_scope = {'__name__': 'local_build07_receipt_schema', '__file__': '<local-build07-schema>'}
    exec(compile(controller, 'framework_build.py', 'exec'), framework_scope, framework_scope)
    documents = {}
    for local_name, staged_name, remote_name, size, digest in FAILED:
        raw = files[staged_name].encode()
        for path in [OLD_ROOT + '/build-fences-01/' + remote_name, NEW_ROOT + '/control-source/' + staged_name]:
            documents[path] = (raw, size, digest)
    def json_memory_pin(path, digest, size, **unused):
        raw, wanted_size, wanted_digest = documents[str(path)]
        need(size == wanted_size and digest == wanted_digest and len(raw) == size and sha(raw) == digest,
             'actual failure JSON schema control pin differs')
        return json.loads(raw), None  # No manufactured host stat/identity record.
    framework_scope['json_pin'] = json_memory_pin
    need(framework_scope['settled_normal06_fence_contract']() == [None] * 6, 'settled authority schema component failed')
    bad_files = dict(files)
    old_nested_sha = assignments(originals['root_snapshot_supervisor.py'])['SNAPSHOT_SHA']
    bad_files['root_snapshot_supervisor.py'] = replace_nodes(bad_files['root_snapshot_supervisor.py'], {
        'SNAPSHOT_SHA': 'SNAPSHOT_SHA = ' + repr(old_nested_sha),
    })
    try:
        check_chain(bad_files, stage, transport, wire, encoded)
    except RuntimeError as error:
        need(str(error) == 'INNER_ROOT_SNAPSHOT_PIN_DIFFERS', 'stale inner-pin negative failed elsewhere')
    else:
        raise RuntimeError('stale inner snapshot pin accepted')
    old_request_raw = fixed(PREVIOUS / 'exact-request.json', 316672,
        'ce23b57113c1784580f5a63e814190715d8606022155968e34a89f928190b348')
    old_request = json.loads(old_request_raw)
    request = copy.deepcopy(old_request)
    request['args'][3] = transport
    request['stdin'] = encoded.decode('ascii')
    request['idempotency_key'] = NEW_KEY
    need({k: v for k, v in request.items() if k not in ['args', 'stdin', 'idempotency_key']} ==
         {k: v for k, v in old_request.items() if k not in ['args', 'stdin', 'idempotency_key']} and
         request['args'][:3] == old_request['args'][:3] and request['args'][4:] == old_request['args'][4:],
         'original resource/process envelope changed')
    # All established process, resource, lifecycle and runtime guard logic is
    # compared as AST; only the listed new precondition/constant bindings differ.
    defs = lambda text: {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(text).body
                         if isinstance(n, ast.FunctionDef)}
    inherited = {}
    for name, allowed_changed in [('framework_build.py', {'prior_failure_contract', 'settled_normal06_fence_contract'}),
                                 ('fenced_build.py', {'run'}),
                                 ('root_snapshot_supervisor.py', set()),
                                 ('capture_lifecycle.py', set()), ('main_snapshot.py', set()),
                                 ('pure_controls.py', set()), ('transport.py', set())]:
        before, after = defs(originals[name]), defs(materials[name])
        for function in before:
            need(function in allowed_changed or before[function] == after.get(function),
                 'unintended function change: ' + name + ':' + function)
        inherited[name] = sorted(set(before) - allowed_changed)
    for name, text in materials.items():
        put(OUTPUT / name, text)
    put(OUTPUT / 'decoded-source-packet.original.json', wire)
    put(OUTPUT / 'exact-stdin.base64', encoded)
    request_raw = dump(request)
    put(OUTPUT / 'exact-request.json', request_raw)
    for name in ['pure-controls.actual.json', 'builder470-receipt-controls.actual.json', 'scope-binding.actual.json']:
        put(OUTPUT / name, (PREVIOUS / name).read_bytes())
    controls = {'schema': 1, 'state': 'NESTED_SOURCE_CHAIN_POSITIVE_AND_STALE_INNER_NEGATIVE_PASS',
        'positive': {'complete_inner_to_outer_pin_chain': chain, 'actual_failed_receipt_schema_checked_in_memory': True,
                     'no_host_stat_identity_synthesized': True},
        'negative': {'mutation': 'Restore original build06 root supervisor SNAPSHOT_SHA',
                     'stale_sha256': old_nested_sha, 'rejected': True, 'error': 'INNER_ROOT_SNAPSHOT_PIN_DIFFERS'},
        'controls_run': 2, 'prior_59_pure_controls_rerun': False, 'prior_19_Rust_controls_rerun': False,
        'unchanged_function_bodies': inherited, 'current_guard_and_snapshot_source_bytes_unchanged': True,
        'stage_invoked': False, 'remote_actions': 0, 'Main_actions': 0, 'production_ready': False}
    put(OUTPUT / 'nested-pin-controls.actual.json', dump(controls))
    plan = json.loads((PREVIOUS / 'execution-plan.json').read_bytes())
    plan.update({'state': 'SEALED_BUILD07_NESTED_PIN_REPAIR_REVIEW_REQUIRED',
        'root': NEW_ROOT, 'out': NEW_ROOT + '/android-out',
        'resource_admission_receipt': NEW_ROOT + '/resource-admission.json',
        'last_executed_builder_root': '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-native-provider-build-05-20261106',
        'last_executed_builder_published_projects': 225,
        'settled_build06': {'job_id': '1a1b1f6d728-fc05-7bc6', 'state': 'FAILED',
            'inner_build_called': False, 'Main_snapshot_executed': False, 'Soong_invocations': 0,
            'both_outer_root_children_reaped_and_FDs_closed': True,
            'authority': {'path': OLD_ROOT + '/build-fences-01/terminal.json', 'bytes': FAILED[0][3], 'sha256': FAILED[0][4]}},
        'snapshot_pin_fix_only_in_root_supervisor': {'before': old_nested_sha, 'after': snapshot_sha},
        'settled_predecessor_required_before_any_new_root_child': True,
        'historical_59_and_19_controls_not_rerun_by_local_revision': True,
        'four_actual_capture_controls_still_required_in_new_attempt': True,
        'framework_build_submitted': False, 'host_window_authorized': False,
        'transport': {'encoded': {'bytes': len(encoded), 'sha256': sha(encoded)},
                      'compressed': {'bytes': len(packed), 'sha256': sha(packed)},
                      'decoded': {'bytes': len(wire), 'sha256': sha(wire)},
                      'limits_and_decoder_algorithm_unchanged': True}})
    put(OUTPUT / 'execution-plan.json', dump(plan))
    parts = []
    for name in ['framework_build.py', 'root_snapshot_supervisor.py', 'fenced_build.py', 'stage.py', 'transport.py']:
        parts.extend(difflib.unified_diff(originals[name].splitlines(True), materials[name].splitlines(True),
            fromfile='executed-build06-source-r3/' + name, tofile='proposed-build07-source-r4/' + name))
    diff = ''.join(parts)
    put(OUTPUT / 'r3-to-r4-minimal-code.diff', diff)
    manifest = copy.deepcopy(previous)
    manifest.update({'schema': 'pocket4-normal07-sealed-source-v4',
        'state': 'SEALED_BUILD07_REVIEW_REQUIRED_NOT_SUBMITTED', 'root': NEW_ROOT, 'key': NEW_KEY,
        'files': {name: {'bytes': len(text.encode()), 'sha256': sha(text.encode())} for name, text in sorted(materials.items())},
        'staged_members': sorted(files),
        'exact_stdin': {'bytes': len(encoded), 'sha256': sha(encoded), 'encoding': 'base64(zlib(exact_source_packet))'},
        'decoded_original_stdin': {'bytes': len(wire), 'sha256': sha(wire)},
        'exact_request': {'bytes': len(request_raw.encode()), 'sha256': sha(request_raw.encode())},
        'previous_executed_source_r3': {'bytes': len(previous_manifest_raw), 'sha256': sha(previous_manifest_raw)},
        'previous_build06_preserved_as_failed_without_inner': True,
        'last_published_source_remains_normal05_225': True,
        'transport_revision_only': False,
        'all_prior_runner_stage_input_bytes_preserved': False,
        'only_root_pin_and_new_settled_failure_precondition_changed': True,
        'current_guard_bytes_unchanged': True, 'current_app_scope_pin_unchanged': True,
        'normal06_failed_receipts': [{'staged_name': staged, 'remote_path': OLD_ROOT + '/build-fences-01/' + remote,
                                    'bytes': size, 'sha256': digest}
                                    for _, staged, remote, size, digest in FAILED]})
    put(OUTPUT / 'SOURCE_PINS.json', dump(manifest))
    print(json.dumps({'root': str(OUTPUT), 'stage_members': len(files), 'source_members': len(materials),
        'exact_request': manifest['exact_request'], 'exact_stdin': manifest['exact_stdin'],
        'source_manifest': {'bytes': len(dump(manifest).encode()), 'sha256': sha(dump(manifest).encode())},
        'diff': {'bytes': len(diff.encode()), 'sha256': sha(diff.encode())}, 'local_controls': 2, 'submitted': False}))


if __name__ == '__main__':
    main()
