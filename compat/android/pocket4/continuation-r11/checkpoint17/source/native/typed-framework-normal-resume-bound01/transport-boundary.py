import base64,hashlib,json,sys,zlib
ENVELOPE = {'bytes': 168245, 'sha256': '9daf13c3eb68d160ce2a75ec6c3bf6bd567e287dc7d244a30420744237773c68'}
COMPRESSED = {'bytes': 125983, 'sha256': 'ba629f59f3fbe5afb87f4176cfa4c52ff4fdbbc9e5d2e3a9820ccbac14d414bc'}
UNCOMPRESSED = {'bytes': 696874, 'sha256': 'd36715e336a50df7290cf3d3c3387b877dbe710e1195d4e2c2e0acef93256af1'}
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
