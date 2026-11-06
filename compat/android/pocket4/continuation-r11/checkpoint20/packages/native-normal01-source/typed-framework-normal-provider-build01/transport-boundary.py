import hashlib,json,sys
WIRE_BYTES = 653752
WIRE_SHA256 = "b05def30391b38aa68e71c2283a779b651255c1ea09a4888a8eb07e47a5d3b75"
STAGE_BYTES = 4733
STAGE_SHA256 = "d9e054b910fa8f6ad7b80ef9504e978dc490198b3129389747f427e7fc6c3319"
if sys.argv[1:] != ['--execute-once']:
    print(json.dumps({'state':'PLAN_ONLY','source_only':True,'submitted':False,'Main_actions':0,'Android_actions':0,'old_QA_epoch_invalid':True,'new_QA_epoch_qualified':False}))
    raise SystemExit(0)
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
