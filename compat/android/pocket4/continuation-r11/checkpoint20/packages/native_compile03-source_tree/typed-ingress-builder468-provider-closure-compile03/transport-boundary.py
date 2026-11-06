import hashlib,json,sys
EXPECTED={"bytes":886361,"sha256":"9870cbec3436c245726dd193ffdc84d7850cdad80e083c9d03033ffb80c3598a"}
STAGE={"bytes":19294,"sha256":"a180e9d01fc2e026b1a30c18529a6ce2141ff398526fa8cbe63e7f6dc231ed02"}
wire=sys.stdin.buffer.read(EXPECTED['bytes']+1)
if len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:
    raise RuntimeError('fixed provider compiler transport length/hash mismatch')
value=json.loads(wire)
if type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:
    raise RuntimeError('fixed provider compiler envelope differs')
stage=value['stage'].encode('utf-8')
if len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:
    raise RuntimeError('fixed provider compiler stage pin differs')
scope={'__name__':'__stage__','__file__':'<fixed-provider-stage>'}
exec(compile(stage,'<fixed-provider-stage>','exec'),scope,scope)
scope['main'](value['packet'])
