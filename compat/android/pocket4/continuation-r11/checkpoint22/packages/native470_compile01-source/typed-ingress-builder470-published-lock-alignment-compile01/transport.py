import hashlib,json,sys
EXPECTED={"bytes":481879,"sha256":"b6856cb45e7738441b6d83ab80496b18de7f3b36074857da0e2242296e0606e7"}
STAGE={"bytes":10959,"sha256":"8510804bba86aa6b6b4730ef2fedb2037af6ab596fa5e0e3f6e9303e1299a522"}
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
