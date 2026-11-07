import base64,hashlib,json,sys,zlib
ENVELOPE = {'bytes': 202169, 'sha256': 'cfd013eb5a3a564619bbd79ade7662184fefcc926716f63693ee934d5df9a54a'}
COMPRESSED = {'bytes': 151426, 'sha256': 'd1bb7d61b64f5d8b315ed25731d74590a5e67c1804565a1f2b001b3e8b55047e'}
UNCOMPRESSED = {'bytes': 937337, 'sha256': '0258db6146d279f90e30ac161251b16c7fb72638a2e9faca49ffffe3dc90f508'}
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
