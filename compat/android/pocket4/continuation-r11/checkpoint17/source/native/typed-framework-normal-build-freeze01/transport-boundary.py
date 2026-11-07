import base64,hashlib,json,sys,zlib
ENVELOPE = {'bytes': 95820, 'sha256': 'c2d49572aaf21918fc175fe578e537af82a4570f3a0fd5db24956750db04458f'}
COMPRESSED = {'bytes': 71666, 'sha256': '34f771de08460145d74f114da2394afec6781cd29c7034d1551f1749cbe9440a'}
UNCOMPRESSED = {'bytes': 349808, 'sha256': '5bef27213463d6a1d0dbaaa426468894583e5c57a6fc4c985ff18e8aba41b938'}
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
