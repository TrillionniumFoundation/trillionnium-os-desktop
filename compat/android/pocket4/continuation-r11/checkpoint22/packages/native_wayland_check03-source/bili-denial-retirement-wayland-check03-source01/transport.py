import hashlib,json,sys
EXPECTED={"bytes":709500,"sha256":"5f08266f550b6ea8d980719181e16f8a4a5d8b051bd799d1b91ec6af5c9f948a"}
STAGE={"bytes":10737,"sha256":"6e84b27c9ba00cd0e4a8733729f09fa555a125e479d851ea57044071e59b341e"}
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
