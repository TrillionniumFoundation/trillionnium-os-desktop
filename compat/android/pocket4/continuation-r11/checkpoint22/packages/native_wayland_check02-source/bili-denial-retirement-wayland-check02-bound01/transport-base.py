import hashlib,json,sys
EXPECTED={"bytes":691045,"sha256":"aff5245a9060ca5e2556da77460820d227699ad4baa35791df60c0e5d0d13cd8"}
STAGE={"bytes":9566,"sha256":"51655acc8aca54f0059f0d6de39687dae978675467b3c3d6e91058e942d01713"}
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
