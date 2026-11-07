import base64,hashlib,json,sys,zlib
ENVELOPE = {'bytes': 315342, 'sha256': '4c1929177171b438a3e9f3afab7be65b362efd06042560fd831fab697edcd1e0'}
COMPRESSED = {'bytes': 236306, 'sha256': '50a8b56b4f389836dc6cf88f36fa4c1f59a082bb04e093eb2550183608b728e6'}
UNCOMPRESSED = {'bytes': 1344731, 'sha256': '507259d04f5846f17dd49b6066d0f2da1cebc3a366086c308393ee7586bba1c2'}
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
