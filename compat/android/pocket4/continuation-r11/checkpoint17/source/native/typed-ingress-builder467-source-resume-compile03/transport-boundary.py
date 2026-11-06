import base64,hashlib,json,sys,zlib
ENVELOPE = {'bytes': 306030, 'sha256': '414c234a828319d692a06dcab08801c86c63e6a9c011c8e227a992bc5814b003'}
COMPRESSED = {'bytes': 229323, 'sha256': 'f5b4cb428a8eae43272a447916243ff7617b4dd405b4ebc081bf19485b563bb7'}
UNCOMPRESSED = {'bytes': 1300762, 'sha256': 'f3d14e34ea00a9d5d3193eac5f5e00ac75b873073af60e5f660bf734fb7de0dc'}
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
