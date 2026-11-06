#!/usr/bin/env python3
"""Bounded transport-only revision; never submit or invoke the decoded stage."""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path
import zlib

BASE = Path(__file__).resolve().parents[1]
PREVIOUS = BASE / 'source-r2'
OUTPUT = BASE / 'source-r3'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def put(path, raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    if path.exists():
        need(path.read_bytes() == raw, 'frozen output differs: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


DECODER = '''def decode_exact_wire(encoded):
    if not (0 < ENCODED_BYTES <= INPUT_MAX_BYTES == 1048576 and
            0 < COMPRESSED_BYTES <= INPUT_MAX_BYTES and
            0 < WIRE_BYTES <= DECODED_MAX_BYTES == 2097152):
        raise RuntimeError('normal06 transport bounds invalid')
    if len(encoded) != ENCODED_BYTES or hashlib.sha256(encoded).hexdigest() != ENCODED_SHA256:
        raise RuntimeError('normal06 encoded input length or SHA changed')
    try:
        packed = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise RuntimeError('normal06 input is not strict base64') from error
    if base64.b64encode(packed) != encoded:
        raise RuntimeError('normal06 base64 is not canonical')
    if len(packed) != COMPRESSED_BYTES or hashlib.sha256(packed).hexdigest() != COMPRESSED_SHA256:
        raise RuntimeError('normal06 compressed stream length or SHA changed')
    decoder = zlib.decompressobj(wbits=zlib.MAX_WBITS)
    try:
        # Exactly one extra byte detects an expansion beyond the original size.
        # No unbounded flush is used; EOF and both tails must agree afterwards.
        raw = decoder.decompress(packed, WIRE_BYTES + 1)
    except zlib.error as error:
        raise RuntimeError('normal06 zlib stream invalid') from error
    if len(raw) != WIRE_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise RuntimeError('normal06 decoded length EOF or tail differs')
    if hashlib.sha256(raw).hexdigest() != WIRE_SHA256:
        raise RuntimeError('normal06 decoded original SHA changed')
    return raw
'''


def main():
    manifest_raw = (PREVIOUS / 'SOURCE_PINS.json').read_bytes()
    need(len(manifest_raw) == 9031 and sha(manifest_raw) ==
         '0ae88d945efdd1ce87ffd5b5767b9b922df48f92adf4e6b20be58a80b83e30f8', 'exact r2 manifest changed')
    manifest = json.loads(manifest_raw)
    files = {}
    for name, pin in manifest['files'].items():
        raw = (PREVIOUS / name).read_bytes()
        need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'r2 member changed: ' + name)
        files[name] = raw
    old_request_raw = (PREVIOUS / 'exact-request.json').read_bytes()
    need(len(old_request_raw) == 1197269 and sha(old_request_raw) ==
         '15eca25ca1ee3dcea89ba6037a9f879fdf676eed5cb87c8ed20de0e66a797972', 'r2 exact request changed')
    old_request = json.loads(old_request_raw)
    wire = (PREVIOUS / 'exact-stdin.json').read_bytes()
    need(wire == old_request['stdin'].encode('utf-8') and len(wire) == 1088084 and sha(wire) ==
         '10ceb1923c73dd7d72c04bc24dc2798fbd2b49f53f7ca1e819c67d761726f269', 'r2 original wire changed')
    packed = zlib.compress(wire, level=9)
    encoded = base64.b64encode(packed)
    need(len(encoded) <= 1048576, 'encoded request still exceeds transport limit')
    old_transport = files['transport.py'].decode('utf-8')
    tree = ast.parse(old_transport)
    assignments = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                   and isinstance(node.value, ast.Constant)}
    need(assignments['WIRE_BYTES'] == len(wire) and assignments['WIRE_SHA256'] == sha(wire) and
         assignments['STAGE_BYTES'] == len(files['stage.py']) and
         assignments['STAGE_SHA256'] == sha(files['stage.py']), 'original transport source pins differ')
    header = ('import base64,binascii,hashlib,json,sys,zlib\n'
        + ''.join(name + ' = ' + repr(value) + '\n' for name, value in {
            **assignments, 'INPUT_MAX_BYTES': 1048576, 'DECODED_MAX_BYTES': 2097152,
            'ENCODED_BYTES': len(encoded), 'ENCODED_SHA256': sha(encoded),
            'COMPRESSED_BYTES': len(packed), 'COMPRESSED_SHA256': sha(packed),
        }.items()) + '\n' + DECODER + '\n')
    start = old_transport.index("if sys.argv[1:] != ['--execute-once']:")
    end = old_transport.index("packet=json.loads(raw.decode('utf-8','strict'))")
    middle = old_transport[start:end]
    old_read = "raw=sys.stdin.buffer.read(WIRE_BYTES+1)\nif len(raw)!=WIRE_BYTES or hashlib.sha256(raw).hexdigest()!=WIRE_SHA256:\n    raise RuntimeError('normal framework exact source packet changed')\n"
    need(middle.count(old_read) == 1, 'original bounded wire read not unique')
    middle = middle.replace(old_read, "encoded=sys.stdin.buffer.read(ENCODED_BYTES+1)\nraw=decode_exact_wire(encoded)\n")
    transport = header + middle + old_transport[end:]
    compile(transport, 'transport.py', 'exec')
    # Execute only declarations and the decoder function. The exact old stage
    # and all runtime/build functions remain inert in these local controls.
    decls = [node for node in ast.parse(transport).body if isinstance(node, (ast.Import, ast.FunctionDef))
             or (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant))]
    scope = {'__name__': 'local_transport_decoder_controls'}
    exec(compile(ast.Module(body=decls, type_ignores=[]), '<decoder-only>', 'exec'), scope, scope)
    need(scope['decode_exact_wire'](encoded) == wire, 'exact old wire roundtrip failed')
    tests = []
    def bad(name, candidate, compressed=None, decoded_limit=None):
        local = dict(scope)
        if compressed is not None:
            local.update(ENCODED_BYTES=len(candidate), ENCODED_SHA256=sha(candidate),
                         COMPRESSED_BYTES=len(compressed), COMPRESSED_SHA256=sha(compressed))
        if decoded_limit is not None:
            local['WIRE_BYTES'] = decoded_limit
        exec(compile(DECODER, '<negative-decoder>', 'exec'), local, local)
        try:
            local['decode_exact_wire'](candidate)
        except RuntimeError as error:
            tests.append({'name': name, 'rejected': True, 'error': str(error),
                          'new_test_only_input_pins': compressed is not None})
        else:
            raise RuntimeError('transport negative accepted: ' + name)
    bad('extra_encoded_byte', encoded + b'\n')
    bad('wrong_encoded_sha', (b'A' if encoded[:1] != b'A' else b'B') + encoded[1:])
    truncated = packed[:-4]
    bad('truncated_zlib_rejected_without_EOF', base64.b64encode(truncated), truncated)
    trailing = packed + b'extra'
    bad('trailing_compressed_data_rejected', base64.b64encode(trailing), trailing)
    bad('decoded_output_exceeds_exact_bound', encoded, packed, len(wire) - 1)
    members = dict(files)
    members['transport.py'] = transport.encode()
    for name, raw in members.items():
        put(OUTPUT / name, raw)
    put(OUTPUT / 'decoded-source-packet.original.json', wire)
    put(OUTPUT / 'exact-stdin.base64', encoded)
    request = copy.deepcopy(old_request)
    request['args'][3] = transport
    request['stdin'] = encoded.decode('ascii')
    need({key: value for key, value in request.items() if key not in ['args', 'stdin']} ==
         {key: value for key, value in old_request.items() if key not in ['args', 'stdin']} and
         request['args'][:3] == old_request['args'][:3] and request['args'][4:] == old_request['args'][4:],
         'non-transport process request changed')
    request_raw = dump(request)
    put(OUTPUT / 'exact-request.json', request_raw)
    for name in ['pure-controls.actual.json', 'builder470-receipt-controls.actual.json',
                 'local-inheritance-check.json', 'scope-binding.actual.json',
                 'normal05-to-normal06-code.diff', 'unsealed-to-sealed.diff']:
        put(OUTPUT / name, (PREVIOUS / name).read_bytes())
    diff = ''.join(difflib.unified_diff(old_transport.splitlines(True), transport.splitlines(True),
        fromfile='source-r2/transport.py', tofile='source-r3/transport.py'))
    put(OUTPUT / 'r2-to-r3-transport-only.diff', diff)
    evidence = {'schema': 1, 'state': 'TRANSPORT_ONLY_ROUNDTRIP_AND_BOUNDS_PASS',
        'r2_was_not_submitted': True, 'previous_stdin_exceeded_one_MiB': True,
        'encoded': {'bytes': len(encoded), 'sha256': sha(encoded), 'format': 'canonical strict base64'},
        'compressed': {'bytes': len(packed), 'sha256': sha(packed), 'format': 'single zlib stream'},
        'decoded_original': {'bytes': len(wire), 'sha256': sha(wire)},
        'input_tool_max_bytes': 1048576, 'decode_call_max_output_bytes': len(wire) + 1,
        'unbounded_flush_used': False, 'EOF_required': True,
        'unused_data_and_unconsumed_tail_must_be_empty': True,
        'all_25_decoded_members_and_original_stage_byte_equal_r2': True,
        'runtime_and_build_source_bytes_changed': False,
        'roundtrip_exact': True, 'negative_fixtures': tests,
        'runtime_controls_rerun_for_transport_change': False,
        'actual_stage_invoked': False, 'remote_or_Main_operations': 0,
        'framework_build_submitted': False, 'production_ready': False}
    put(OUTPUT / 'transport-controls.actual.json', dump(evidence))
    plan = json.loads((PREVIOUS / 'execution-plan.json').read_bytes())
    plan['transport'] = {key: evidence[key] for key in ['encoded', 'compressed', 'decoded_original',
        'input_tool_max_bytes', 'decode_call_max_output_bytes', 'unbounded_flush_used', 'EOF_required',
        'unused_data_and_unconsumed_tail_must_be_empty']}
    plan['prior_sealed_r2_unsubmitted_due_to_stdin_limit'] = True
    put(OUTPUT / 'execution-plan.json', dump(plan))
    metadata = copy.deepcopy(manifest)
    metadata.update({'schema': 'pocket4-normal06-sealed-source-v3',
        'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(members.items())},
        'exact_stdin': {'bytes': len(encoded), 'sha256': sha(encoded), 'encoding': 'base64(zlib(exact_r2_source_packet))'},
        'decoded_original_stdin': {'bytes': len(wire), 'sha256': sha(wire)},
        'exact_request': {'bytes': len(request_raw.encode()), 'sha256': sha(request_raw.encode())},
        'transport_revision_only': True,
        'source_r2_manifest': {'bytes': len(manifest_raw), 'sha256': sha(manifest_raw)},
        'all_prior_runner_stage_input_bytes_preserved': True,
        'max_stdin_tool_bytes': 1048576})
    put(OUTPUT / 'SOURCE_PINS.json', dump(metadata))
    put(PREVIOUS / 'transport-limit.unsubmitted.json', dump({
        'schema': 1, 'state': 'UNSUBMITTED_EXCEEDS_TOOL_STDIN_LIMIT', 'actual_stdin_bytes': len(wire),
        'tool_max_stdin_bytes': 1048576, 'remote_submissions': 0,
        'successor': 'source-r3 transport-only bounded zlib+base64 with identical decoded original',
        'original_r2_request_preserved': True, 'production_ready': False}))
    print(json.dumps({'root': str(OUTPUT), 'encoded_stdin': metadata['exact_stdin'],
        'compressed': evidence['compressed'], 'original_decoded': metadata['decoded_original_stdin'],
        'exact_request': metadata['exact_request'],
        'source_manifest': {'bytes': len(dump(metadata).encode()), 'sha256': sha(dump(metadata).encode())},
        'transport_diff': {'bytes': len(diff.encode()), 'sha256': sha(diff.encode())},
        'controls': len(tests) + 1, 'submitted': False}))


if __name__ == '__main__':
    main()
