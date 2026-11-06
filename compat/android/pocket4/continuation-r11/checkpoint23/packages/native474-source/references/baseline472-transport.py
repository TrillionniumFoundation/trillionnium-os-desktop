import hashlib,json,sys
EXPECTED={"bytes":598552,"sha256":"2ff3b81084eff5835d0948091c226f557fc01e0a77e6acd2137a866843dd894a"}
STAGE={"bytes":14834,"sha256":"51559fe3bc57d75e0668d9bdec451cf9bf551ccdb6ac9a4eef9839bd38033643"}
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
