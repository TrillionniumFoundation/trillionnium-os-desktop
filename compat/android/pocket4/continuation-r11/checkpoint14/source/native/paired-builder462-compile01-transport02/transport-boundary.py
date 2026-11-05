import base64,hashlib,json,sys,zlib
ENVELOPE = {'bytes': 332858, 'sha256': 'd1811c949aa0b05a65de7257096a4832d8099661bccc9f9813d9aff0466a75b9'}
COMPRESSED = {'bytes': 249443, 'sha256': '59b4dcb4c225fefbf8671134bb7c8175898875a7c31c236bc308636421ed6ee6'}
UNCOMPRESSED = {'bytes': 1408472, 'sha256': '3365b2d2330c3bcc2927fbf454e781587363415d7255bd361ae6f80c93102e9d'}
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
