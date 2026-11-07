import hashlib,json,sys
EXPECTED={"bytes":279647,"sha256":"b1068b8058bd96f2c5f7d03e1feeaca4c2fd5c58bf4df44804c44dd98fac6fbb"}
STAGE={"bytes":8352,"sha256":"f747856c51daf57a26db97938d20018d20cb5f600b64ae2173dc069a9d51d2c4"}
wire=sys.stdin.buffer.read(EXPECTED['bytes']+1)
if len(wire)!=EXPECTED['bytes'] or hashlib.sha256(wire).hexdigest()!=EXPECTED['sha256']:
    raise RuntimeError('fixed composer transaction host transport length/hash mismatch')
value=json.loads(wire)
if type(value) is not dict or set(value)!={'schema','stage','packet'} or value['schema']!=1 or type(value['stage']) is not str:
    raise RuntimeError('fixed composer transaction host envelope differs')
stage=value['stage'].encode('utf-8')
if len(stage)!=STAGE['bytes'] or hashlib.sha256(stage).hexdigest()!=STAGE['sha256']:
    raise RuntimeError('fixed composer transaction host stage pin differs')
scope={'__name__':'__stage__','__file__':'<fixed-composer-transaction-stage>'}
exec(compile(stage,'<fixed-composer-transaction-stage>','exec'),scope,scope)
scope['main'](value['packet'])
