import hashlib,json,sys
WIRE_BYTES = 824918
WIRE_SHA256 = '20e061e7a28c9aca81ef5ae33fa8578caf9ee35b7eef6660e8d7675c2db2762d'
STAGE_BYTES = 7137
STAGE_SHA256 = '5723e4064379832141e068fb87b7a4460e594545ffc3d9a94f779df847b9ad83'
if sys.argv[1:] != ['--execute-once']:
    print(json.dumps({'state':'PLAN_ONLY','source_only':True,'submitted':False,'Main_actions':0,'Android_actions':0,'old_QA_epoch_invalid':True,'new_QA_epoch_qualified':False}))
    raise SystemExit(0)
if WIRE_BYTES is None or WIRE_SHA256 is None:
    raise RuntimeError('NORMAL05_EXACT_REQUEST_NOT_SEALED')
raw=sys.stdin.buffer.read(WIRE_BYTES+1)
if len(raw)!=WIRE_BYTES or hashlib.sha256(raw).hexdigest()!=WIRE_SHA256:
    raise RuntimeError('normal framework exact source packet changed')
packet=json.loads(raw.decode('utf-8','strict'))
if set(packet)!={'schema','stage','files'} or type(packet['schema']) is not int or packet['schema']!=1:
    raise RuntimeError('normal framework source packet shape changed')
stage=packet['stage'].encode('utf-8')
if len(stage)!=STAGE_BYTES or hashlib.sha256(stage).hexdigest()!=STAGE_SHA256:
    raise RuntimeError('normal framework stage source changed')
scope={'__name__':'frozen_normal_framework_stage','__file__':'<frozen-normal-framework-stage>'}
exec(compile(stage,'stage.py','exec'),scope,scope)
scope['main'](packet['files'])
