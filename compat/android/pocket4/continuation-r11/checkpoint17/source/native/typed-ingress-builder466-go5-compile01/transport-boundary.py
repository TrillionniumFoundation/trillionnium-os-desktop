import base64,hashlib,json,sys,zlib
ENVELOPE = {'bytes': 196193, 'sha256': '700cc3cbef8a05bb8eb3f70a905944f60866d92dc67cbe97ba1e50af75254451'}
COMPRESSED = {'bytes': 146946, 'sha256': 'd1732f8b35a9ace0402abe36ab1bf1d015f448a995e49a3240e2d3a9b1d42cfc'}
UNCOMPRESSED = {'bytes': 897961, 'sha256': '4095e73c1a4c52db719e17e100c399a1429fcb6abaf6938d0248b5e2f1b26150'}
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
