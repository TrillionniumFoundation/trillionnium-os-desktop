import hashlib,json,sys
WIRE_BYTES = None
WIRE_SHA256 = None
STAGE_BYTES = 7841
STAGE_SHA256 = 'da1627de74f7c5daddb61708ea2cbe2bbefcf4ea204a855bff346ded5b38d9a0'
if sys.argv[1:] != ['--execute-once']:
    print(json.dumps({'state':'PLAN_ONLY','source_only':True,'submitted':False,'Main_actions':0,'Android_actions':0,'old_QA_epoch_invalid':True,'new_QA_epoch_qualified':False}))
    raise SystemExit(0)
if WIRE_BYTES is None or WIRE_SHA256 is None:
    raise RuntimeError('NORMAL06_EXACT_REQUEST_NOT_SEALED')
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
