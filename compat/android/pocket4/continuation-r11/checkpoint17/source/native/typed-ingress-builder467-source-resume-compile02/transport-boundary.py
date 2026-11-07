import base64,hashlib,json,sys,zlib
ENVELOPE = {'bytes': 305990, 'sha256': '9d231ddc02b1006902bbc88133afe48974abb716ee5d77d153456d652ab7bdf8'}
COMPRESSED = {'bytes': 229292, 'sha256': '1a9dda39e8ea5805529876a79325f6cd1bba41e0bf2a04ca367e74f50bbd1508'}
UNCOMPRESSED = {'bytes': 1300599, 'sha256': '9854c513380d23a19f424d9db66e061f2d295cdd8a292a41d0e9bb4c28f0a479'}
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
