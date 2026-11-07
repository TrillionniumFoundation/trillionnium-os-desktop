import hashlib,json,sys
EXPECTED={"bytes":436252,"sha256":"141238d219adc73d05a68a4822b2986a6ac94bb5cb7612705c45e67d90ac822d"}
STAGE={"bytes":9165,"sha256":"bee616fe0688e62694ba66a868d037640512a3352a9146a3a2d58394205e75dc"}
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
