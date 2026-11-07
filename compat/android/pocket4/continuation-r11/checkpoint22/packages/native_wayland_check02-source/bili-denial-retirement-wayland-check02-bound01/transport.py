import hashlib,json,sys
EXPECTED={"bytes":704577,"sha256":"f9455c98f7a93ecb32e8b661f0c8685415d8369e86fce4f3a6bd97c583832035"}
STAGE={"bytes":10737,"sha256":"a55197df7401d0622593880e76e55e11cd45a4ed4ea3a3543ee0ae3b2b764d1d"}
wire=sys.stdin.buffer.read(EXPECTED['bytes']+1)
if len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:
    raise RuntimeError('fixed complete Wayland checker transport length/hash mismatch')
value=json.loads(wire)
if type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:
    raise RuntimeError('fixed complete Wayland checker envelope differs')
stage=value['stage'].encode('utf-8')
if len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:
    raise RuntimeError('fixed complete Wayland checker stage pin differs')
scope={'__name__':'__stage__','__file__':'<fixed-wayland-check-stage>'}
exec(compile(stage,'<fixed-wayland-check-stage>','exec'),scope,scope)
scope['main'](value['packet'])
