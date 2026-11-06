"""Seal the reviewed current470 build08 candidate locally; never submit it."""
import argparse
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
OLD = BASE / 'source-r4'
CANDIDATE = BASE / 'current470-authorization-r1/candidate-r1'
OUTPUT = BASE / 'current470-authorization-r1/sealed-r1'
ROOT = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-08-20261106'
KEY = 'pocket4-native-typed-ingress-framework-strict-systemui-provider-two-target-build-08-20261106'
CONTRACT = 'explicit-current470-34commands-28tests-v1'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def fixed(path, size, checksum):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == checksum, 'frozen input changed: ' + str(path))
    return raw


def put(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    with (OUTPUT / name).open('xb') as stream:
        stream.write(raw)


def pin(raw):
    if isinstance(raw, str):
        raw = raw.encode()
    return {'bytes': len(raw), 'sha256': sha(raw)}


def assignments(source):
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return result


def function(source, name):
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(source, node)


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


def decoder_only(transport):
    nodes = [node for node in ast.parse(transport).body if isinstance(node, (ast.Import, ast.FunctionDef)) or
             (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant))]
    scope = {'__name__': 'pure_build08_decoder_only'}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<pure-build08-decoder>', 'exec'), scope)
    return scope


def check_chain(files, stage, transport, wire, encoded):
    root = assignments(files['root_snapshot_supervisor.py'])
    fence = assignments(files['fenced_build.py'])
    snapshot_sha = sha(files['main_snapshot.py'].encode())
    lifecycle_sha = sha(files['capture_lifecycle.py'].encode())
    need(root['SNAPSHOT_SHA'] == snapshot_sha, 'INNER_ROOT_SNAPSHOT_PIN_DIFFERS')
    need(root['LIFECYCLE_SHA'] == lifecycle_sha, 'INNER_ROOT_LIFECYCLE_PIN_DIFFERS')
    need(fence['SNAPSHOT_SHA'] == snapshot_sha and fence['LIFECYCLE_SHA'] == lifecycle_sha and
         fence['ROOT_SUPERVISOR_SHA'] == sha(files['root_snapshot_supervisor.py'].encode()) and
         fence['CONTROLLER_SHA'] == sha(files['framework_build.py'].encode()), 'FENCE_PIN_CHAIN_DIFFERS')
    pins = {name: pin(text) for name, text in files.items()}
    need(assignments(stage)['EXPECTED'] == pins, 'STAGE_MEMBER_PIN_CHAIN_DIFFERS')
    need(json.loads(wire) == {'schema': 1, 'stage': stage, 'files': files}, 'DECODED_PACKET_MEMBERS_DIFFER')
    constants = assignments(transport)
    need(constants['STAGE_BYTES'] == len(stage.encode()) and constants['STAGE_SHA256'] == sha(stage.encode()) and
         constants['WIRE_BYTES'] == len(wire) and constants['WIRE_SHA256'] == sha(wire), 'TRANSPORT_RAW_PIN_CHAIN_DIFFERS')
    need(decoder_only(transport)['decode_exact_wire'](encoded) == wire, 'TRANSPORT_ROUNDTRIP_DIFFERS')
    return {'snapshot': snapshot_sha, 'lifecycle': lifecycle_sha,
        'root_supervisor': fence['ROOT_SUPERVISOR_SHA'], 'controller': fence['CONTROLLER_SHA'],
        'fence': sha(files['fenced_build.py'].encode()), 'stage': sha(stage.encode()),
        'decoded_packet': sha(wire), 'encoded_stdin': sha(encoded)}


def entry_and_plan(files):
    source = files['framework_build.py']
    # Global inputs consist solely of literals, arithmetic and fixed Path calls.
    # Evaluate only those declarations and plan(), never module imports/main/build.
    scope = {'P': Path, 'require': need}
    tree = ast.parse(source)
    allowed = (ast.Expression, ast.Constant, ast.Dict, ast.List, ast.Tuple, ast.Set,
        ast.Name, ast.Load, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
        ast.UnaryOp, ast.USub, ast.Call)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            need(len(node.targets) == 1 and isinstance(node.targets[0], ast.Name), 'unexpected global assignment')
            if node.targets[0].id == 'P':
                need(ast.dump(node.value, include_attributes=False) ==
                     ast.dump(ast.parse('pathlib.Path', mode='eval').body, include_attributes=False),
                     'fixed Path alias changed')
                continue
            need(all(isinstance(part, allowed) for part in ast.walk(node.value)), 'nonliteral global expression')
            for part in ast.walk(node.value):
                if isinstance(part, ast.Call):
                    need(isinstance(part.func, ast.Name) and part.func.id == 'P' and len(part.args) == 1 and
                         isinstance(part.args[0], ast.Constant) and isinstance(part.args[0].value, str) and
                         not part.keywords, 'non-Path global call')
            scope[node.targets[0].id] = eval(compile(ast.Expression(node.value), '<fixed-declaration>', 'eval'), scope)
    plan_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'plan')
    main_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    exec(compile(ast.Module(body=[plan_node], type_ignores=[]), '<fixed-plan-only>', 'exec'), scope)
    plan = scope['plan']()
    need(str(scope['ROOT']) == ROOT and str(scope['OUT']) == ROOT + '/android-out' and
         plan['root'] == ROOT and plan['out'] == ROOT + '/android-out' and
         plan['argv'][-2:] == ['--out', ROOT + '/android-out'], 'build08 plan points at another output')
    need(scope['CURRENT_BUILDER_CONTRACT'] == CONTRACT, 'explicit authorization constant differs')
    fence_tree = ast.parse(files['fenced_build.py'])
    calls = [node for node in ast.walk(fence_tree) if isinstance(node, ast.Call) and
        isinstance(node.func, ast.Subscript) and isinstance(node.func.value, ast.Name) and
        node.func.value.id == 'scope' and isinstance(node.func.slice, ast.Constant) and node.func.slice.value == 'main']
    need(len(calls) == 1 and len(calls[0].args) == 1 and isinstance(calls[0].args[0], ast.List),
         'single actual framework entry invocation required')
    argument = calls[0].args[0]
    expected_ast = ast.parse("['--build', '--preparation-sha256', PREPARATION_SHA, '--builder-contract', " + repr(CONTRACT) + ']')
    need(ast.dump(argument, include_attributes=False) ==
         ast.dump(expected_ast.body[0].value, include_attributes=False), 'EXPLICIT_BUILDER_CONTRACT_NOT_FORWARDED')
    observed = []
    scope.update(argparse=argparse, build=lambda value: observed.append(value) or 0)
    exec(compile(ast.Module(body=[main_node], type_ignores=[]), '<entry-dispatch-only>', 'exec'), scope)
    arguments = ['--build', '--preparation-sha256', scope['PREPARATION_SHA']]
    cases = []
    for label, argv in [('missing_explicit_contract_rejected', arguments),
                        ('wrong_explicit_contract_rejected', arguments + ['--builder-contract', 'legacy468'])]:
        try:
            scope['main'](argv)
        except RuntimeError as error:
            need(str(error) == 'explicit current470 contract selection is required; no legacy fallback',
                 'wrong entrypoint failure')
            cases.append({'name': label, 'passed': True})
        else:
            raise RuntimeError('entrypoint accepted missing/wrong contract')
    need(observed == [], 'rejected entry dispatched a build')
    need(scope['main'](arguments + ['--builder-contract', CONTRACT]) == 0 and
         observed == [scope['PREPARATION_SHA']], 'correct explicit entry did not forward actual preparation pin')
    cases.append({'name': 'explicit_contract_forwards_preparation_SHA_to_local_sentinel', 'passed': True,
                  'sentinel_only': True, 'real_build_called': False})
    return plan, cases


def main():
    need(not OUTPUT.exists(), 'sealed output must be a fresh independent directory')
    candidate_manifest_raw = fixed(CANDIDATE / 'SOURCE_PINS.json', 9054,
        'b84f1e5ab6f6d65f2156aca6027b7078cfa845cc517f037b31e7afecb627c141')
    manifest = json.loads(candidate_manifest_raw)
    for row in manifest['files'] + [manifest['generator'], manifest['template']]:
        fixed(BASE / row['path'], row['bytes'], row['sha256'])
    payload = json.loads((CANDIDATE / 'PAYLOAD_PINS.json').read_bytes())
    need(payload['stage_or_transport_sealed'] is False and len(payload['files']) == 35, 'frozen candidate payload scope differs')
    files = {name: fixed(CANDIDATE / name, row['bytes'], row['sha256']).decode('utf-8')
             for name, row in sorted(payload['files'].items())}
    old_stage = fixed(OLD / 'stage.py', 8389,
        '5a108bcc09b17074d273d30ebc5a95c379e2bd2846e17ed276a5e283fe42e994').decode()
    old_transport = fixed(OLD / 'transport.py', 3152,
        '4df90d65a8114b8d5ca83a384b6e2e8d63ec8e7623bf1c2444fba926460a2749').decode()
    old_request_raw = fixed(OLD / 'exact-request.json', 320416,
        'bd60060c5a1bd329b3c05bfa5309f192c42168d48397f4bcdcfc674fc889054b')
    stage = replace_nodes(old_stage, {'ROOT': 'ROOT = Path(' + repr(ROOT) + ')',
        'EXPECTED': 'EXPECTED = ' + pprint.pformat({name: pin(text) for name, text in files.items()}, sort_dicts=True, width=110)})
    need(function(stage, 'main') == function(old_stage, 'main'), 'original stage lifecycle changed')
    wire = dump({'schema': 1, 'stage': stage, 'files': files})
    packed = zlib.compress(wire, level=9)
    encoded = base64.b64encode(packed)
    need(len(encoded) <= 1048576 and len(packed) <= 1048576 and len(wire) <= 2097152,
         'unchanged input or decoded bounds exceeded')
    values = {'WIRE_BYTES': len(wire), 'WIRE_SHA256': sha(wire),
        'STAGE_BYTES': len(stage.encode()), 'STAGE_SHA256': sha(stage.encode()),
        'ENCODED_BYTES': len(encoded), 'ENCODED_SHA256': sha(encoded),
        'COMPRESSED_BYTES': len(packed), 'COMPRESSED_SHA256': sha(packed)}
    transport = replace_nodes(old_transport, {name: name + ' = ' + repr(value) for name, value in values.items()})
    need(function(transport, 'decode_exact_wire') == function(old_transport, 'decode_exact_wire'),
         'original bounded decoder changed')
    old_without_pins = replace_nodes(old_transport, {name: name + ' = None' for name in values})
    new_without_pins = replace_nodes(transport, {name: name + ' = None' for name in values})
    need(old_without_pins == new_without_pins, 'non-pin transport behavior changed')
    chain = check_chain(files, stage, transport, wire, encoded)
    plan, entry_controls = entry_and_plan(files)
    bad_files = dict(files)
    bad_files['root_snapshot_supervisor.py'] = replace_nodes(bad_files['root_snapshot_supervisor.py'],
        {'SNAPSHOT_SHA': 'SNAPSHOT_SHA = ' + repr('0'*64)})
    try:
        check_chain(bad_files, stage, transport, wire, encoded)
    except RuntimeError as error:
        need(str(error) == 'INNER_ROOT_SNAPSHOT_PIN_DIFFERS', 'inner pin negative failed elsewhere')
    else:
        raise RuntimeError('stale inner snapshot pin accepted')
    old_request = json.loads(old_request_raw)
    request = copy.deepcopy(old_request)
    request['args'][3] = transport
    request['stdin'] = encoded.decode('ascii')
    request['idempotency_key'] = KEY
    need({key: value for key, value in request.items() if key not in ('args', 'stdin', 'idempotency_key')} ==
         {key: value for key, value in old_request.items() if key not in ('args', 'stdin', 'idempotency_key')} and
         request['args'][:3] == old_request['args'][:3] and request['args'][4:] == old_request['args'][4:] and
         request['host'] == 'pocket4' and request['executable'] == '/usr/bin/python3' and
         request['timeout_seconds'] == 6400 and request['cpu_quota_percent'] == 200 and
         request['memory_max_bytes'] == 10*1024**3 and request['nice'] == 10, 'original process/resource envelope changed')
    request_raw = dump(request)
    materials = {**files, 'stage.py': stage, 'transport.py': transport}
    for name, source in materials.items():
        if name.endswith('.py'):
            compile(source, '<sealed-' + name + '>', 'exec')
    OUTPUT.mkdir(parents=True, mode=0o700)
    for name, raw in materials.items():
        put(name, raw)
    put('decoded-source-packet.original.json', wire)
    put('exact-stdin.base64', encoded)
    put('exact-request.json', request_raw)
    controls = {'schema': 1, 'state': 'SEALED_TRANSPORT_CHAIN_AND_EXPLICIT_ENTRY_CONTROLS_PASS',
        'positive_complete_inner_to_outer_chain': chain,
        'negative_stale_inner_snapshot_pin': {'rejected': True, 'error': 'INNER_ROOT_SNAPSHOT_PIN_DIFFERS'},
        'entry_controls': entry_controls, 'control_count': 5,
        'decoder_body_and_bounds_unchanged': True, 'stage_main_body_unchanged': True,
        'candidate35_payload_members_byte_identical': True,
        'original59_pure_controls_not_rerun_locally': True, 'original59_controls_still_required_by_stage': True,
        'current28_Rust_tests_not_rerun': True, 'stage_called': False, 'real_builder_called': False,
        'remote_commands': 0, 'Main_actions': 0, 'Android_actions': 0, 'production_ready': False}
    put('seal-controls.actual.json', dump(controls))
    plan.update({'state': 'SEALED_BUILD08_CURRENT470_EXPLICIT_CONTRACT_REVIEW_REQUIRED',
        'key': KEY, 'current_builder_contract': CONTRACT, 'framework_build_submitted': False,
        'candidate_source_manifest': pin(candidate_manifest_raw),
        'settled07_failed_before_builder_source_materialization': True,
        'last_published_source_remains_actual_normal05_225': True,
        'scope47_is_explicit_installed_set_not_full_launcher_resolver_claim': True,
        'new_stage_root': ROOT, 'stage_members': len(files),
        'exact_request': pin(request_raw), 'transport': {'encoded': pin(encoded), 'compressed': pin(packed),
            'decoded': pin(wire), 'input_limit': 1048576, 'decoded_limit': 2097152,
            'decoded_call_limit': len(wire)+1, 'EOF_and_empty_tails_required': True,
            'unbounded_flush_used': False, 'algorithm_unchanged': True},
        'old_sources_and_failures_unchanged': True, 'runtime_authorization_enabled': False,
        'production_ready': False, 'cleanup_eligible': False})
    put('execution-plan.json', dump(plan))
    diff = ''.join(difflib.unified_diff(old_stage.splitlines(True), stage.splitlines(True),
        fromfile='executed-build07/stage.py', tofile='proposed-build08/stage.py'))
    diff += ''.join(difflib.unified_diff(old_transport.splitlines(True), transport.splitlines(True),
        fromfile='executed-build07/transport.py', tofile='proposed-build08/transport.py'))
    put('stage-transport-only.diff', diff)
    descriptor = {'schema': 'pocket4-build08-explicit-current470-sealed-source-v1',
        'state': 'SEALED_REVIEW_REQUIRED_NOT_SUBMITTED', 'root': ROOT, 'key': KEY,
        'current_builder_contract': CONTRACT, 'candidate_source_manifest': pin(candidate_manifest_raw),
        'files': {name: pin(text) for name, text in sorted(materials.items())},
        'staged_members': sorted(files), 'candidate_payload_unchanged': True,
        'exact_stdin': {**pin(encoded), 'encoding': 'base64(zlib(exact_source_packet))'},
        'decoded_source_packet': pin(wire), 'exact_request': pin(request_raw),
        'generator': {'path': str(Path(__file__).relative_to(BASE)), **pin(Path(__file__).read_bytes())},
        'old_process_envelope': pin(old_request_raw),
        'stage_main_and_transport_decoder_byte_identical_to_build07': True,
        'new_contract_forwarded_to_only_actual_framework_entry': True,
        'remote_submissions': 0, 'production_ready': False, 'cleanup_eligible': False}
    put('SOURCE_PINS.json', dump(descriptor))
    print(json.dumps({'output': str(OUTPUT), 'exact_request': pin(request_raw), 'stdin': pin(encoded),
        'wire': pin(wire), 'stage': pin(stage), 'transport': pin(transport), 'source_pins': pin(dump(descriptor)),
        'stage_transport_diff': pin(diff), 'controls': 5, 'submitted': False}))


if __name__ == '__main__':
    main()
