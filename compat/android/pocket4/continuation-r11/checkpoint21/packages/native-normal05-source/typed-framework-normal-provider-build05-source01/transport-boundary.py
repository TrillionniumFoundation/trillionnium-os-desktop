import hashlib,json,sys
WIRE_BYTES = 797035
WIRE_SHA256 = "7f27c692b0e27282fd88ad1ba0ba8463049828550340e24eab065d50428c7b6c"
STAGE_BYTES = 5448
STAGE_SHA256 = "c87881163e40295dce79902a17d933e1f14182ce1a646d6a0b1c19d513f7ef91"
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
