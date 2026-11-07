import hashlib,json,sys
EXPECTED={"bytes":745153,"sha256":"0c61cdd438010f18f3a0f882343e5d56583d48d02df9f772bfdffe1188a547d3"}
STAGE={"bytes":10834,"sha256":"88e48c88903330228eb6639b3770301c720ba56e00f7eb4457bfbe37d463b635"}
wire=sys.stdin.buffer.read(EXPECTED['bytes']+1)
if len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:
    raise RuntimeError('fixed retirement host compiler transport length/hash mismatch')
value=json.loads(wire)
if type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:
    raise RuntimeError('fixed retirement host compiler envelope differs')
stage=value['stage'].encode('utf-8')
if len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:
    raise RuntimeError('fixed retirement host compiler stage pin differs')
scope={'__name__':'__stage__','__file__':'<fixed-retirement-host-stage>'}
exec(compile(stage,'<fixed-retirement-host-stage>','exec'),scope,scope)
scope['main'](value['packet'])
