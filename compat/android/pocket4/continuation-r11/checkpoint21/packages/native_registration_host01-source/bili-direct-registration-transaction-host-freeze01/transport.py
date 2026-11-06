import hashlib,json,sys
EXPECTED={"bytes":276398,"sha256":"908f844d212217d87495cd53469a1799ca2080813a59e5d6e485c35bfd5f187a"}
STAGE={"bytes":8352,"sha256":"5211bd8509560bb5e76842cfc963ad123b6970ca043e7dc86174c6cc03a84c7e"}
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
