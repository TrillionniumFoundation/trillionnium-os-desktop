#!/usr/bin/env python3
"""Change only the transport of the never-dispatched 462 compiler request."""
from pathlib import Path
import ast
import base64
import gzip
import hashlib
import json
import zlib

BASE = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
OLD = BASE / 'paired-builder462-compile01'
DEST = BASE / 'paired-builder462-compile01-transport02'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write(name, raw):
    path = DEST / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def main():
    old_raw = (OLD / 'exact-request.json').read_bytes()
    assert pin(old_raw)['sha256'] == '34b421d5661c48112073989779cfa70ffa458c0e4470c22331a7c4f9f24e728f'
    original = json.loads(old_raw)
    stage = original['stdin'].encode()
    assert pin(stage) == {'bytes': 1408472, 'sha256': '3365b2d2330c3bcc2927fbf454e781587363415d7255bd361ae6f80c93102e9d'}
    assert original['args'] == ['-I', '-B', '-']
    packed = gzip.compress(stage, compresslevel=9, mtime=0)
    envelope = (json.dumps({
        'schema': 1, 'encoding': 'gzip+base64',
        'compressed': pin(packed), 'uncompressed': pin(stage),
        'payload': base64.b64encode(packed).decode('ascii'),
    }, sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert len(envelope) < 1024 * 1024
    boundary = '''import base64,hashlib,json,sys,zlib
ENVELOPE = %r
COMPRESSED = %r
UNCOMPRESSED = %r
def exact(raw, expected):
    if len(raw)!=expected['bytes'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']:
        raise RuntimeError('fixed compiler transport length/hash mismatch')
wire=sys.stdin.buffer.read(ENVELOPE['bytes']+1)
exact(wire,ENVELOPE)
value=json.loads(wire)
if set(value)!={'schema','encoding','compressed','uncompressed','payload'} or value['schema']!=1 or value['encoding']!='gzip+base64' or value['compressed']!=COMPRESSED or value['uncompressed']!=UNCOMPRESSED:
    raise RuntimeError('fixed compiler transport envelope differs')
packed=base64.b64decode(value['payload'],validate=True)
exact(packed,COMPRESSED)
decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
raw=decoder.decompress(packed,UNCOMPRESSED['bytes']+1)
if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
    raise RuntimeError('compiler transport has incomplete/trailing/oversized gzip content')
exact(raw,UNCOMPRESSED)
scope={'__name__':'__main__','__file__':'<stdin>'}
exec(compile(raw,'<stdin>','exec'),scope,scope)
''' % (pin(envelope), pin(packed), pin(stage))
    ast.parse(boundary)
    request = dict(original)
    request['args'] = ['-I', '-B', '-c', boundary]
    request['stdin'] = envelope.decode()
    request['idempotency_key'] = 'pocket4-native-generation-builder462-matching-compile-01-transport02-20261105'
    assert {k for k in request if request[k] != original[k]} == {'args', 'stdin', 'idempotency_key'}
    # Validate the precise compressed transport locally without compiling or
    # executing its decoded stage or any source in the 23-member packet.
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    restored = decoder.decompress(packed, len(stage) + 1)
    assert decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
    assert restored == stage and pin(restored) == pin(stage)
    write('transport-boundary.py', boundary.encode())
    write('exact-request.json', (json.dumps(request, indent=2) + '\n').encode())
    write('make_request.py', Path(__file__).read_bytes())
    record = {
        'schema': 1, 'state': 'SOURCE_ONLY_TRANSPORT_REVISION_NOT_DISPATCHED',
        'original_request': {'local_path': str(OLD / 'exact-request.json'), **pin(old_raw)},
        'old_stdin_exceeds_1_MiB': True, 'original_remote_request_submitted': False,
        'compressed_envelope': pin(envelope), 'compressed_bytes': pin(packed),
        'uncompressed_exact_original_stdin': pin(stage),
        'changed_request_fields': ['args', 'stdin', 'idempotency_key'],
        'bounded_round_trip_equal': True, 'stage_source_changed': False,
        'packet_files_changed': 0, 'packet_files': 23, 'production_sources_changed': 0,
        'old_source_root_preserved': True,
        'source_root': '/home/alex/work/pocket4-native-generation-builder462-compile-01-20261105',
        'source_root_was_not_created_by_this_local_operation': True,
        'CPU_RAM_timeout_and_child_cleanup_unchanged': True,
        'decoded_stage_executed_locally': False, 'Rust_compile_performed_locally': False,
        'Hepta_calls': 0, 'Main_actions': 0,
    }
    write('TRANSPORT_BINDING.json', (json.dumps(record, indent=2, sort_keys=True) + '\n').encode())
    write('README.md', b'''# Bounded transport revision for the unsubmitted builder462 request

The original request remains frozen and unsubmitted. Its actual stdin is 1,408,472 bytes, beyond process_start's 1 MiB limit. This revision changes only args, stdin encoding and the idempotency key. The exact original stage plus all 23 packet members are gzip-compressed as one input. The boundary fixes envelope, compressed and uncompressed byte counts and SHA256 values, reads at most the fixed envelope length plus one, validates base64, decompresses to at most the fixed output length plus one and rejects incomplete streams, trailing members/data and unconsumed bytes. Only after every check does it compile and execute the byte-identical original stage. No source, test, resource, ownership or cleanup gate is reduced. The same never-created remote source root is used; no remote call was made by this freeze.

The local check proves only bounded decode round-trip equality. It does not execute the decoded stage or any Rust/ART code. No APK, ELF, gzip archive or raw dependency cache is included as a standalone deliverable; the structured request contains its fixed source envelope.
''')
    pins = {str(p.relative_to(DEST)): pin(p.read_bytes()) for p in sorted(DEST.rglob('*')) if p.is_file()}
    write('SOURCE_PINS.json', (json.dumps({'schema': 1, 'files': pins}, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'root': str(DEST), 'request': pin((DEST / 'exact-request.json').read_bytes()),
                      'stdin_bytes': len(envelope), 'boundary': pin(boundary.encode()),
                      'unchanged_decoded_stdin': pin(stage)}))


if __name__ == '__main__':
    main()
