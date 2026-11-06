import hashlib,json,sys
EXPECTED={"bytes":541674,"sha256":"138fbd5a1f9b41c4f0825a229c2e8328ccff9f6deee26f17616fcf2a277040c3"}
STAGE={"bytes":10752,"sha256":"b636adcaf13c3d54cb75ddb6cc099986fde1c63fc138d3283f45eba8caadcf97"}
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
