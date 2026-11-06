import hashlib,json,sys
if sys.argv[1:] != ['--stage-only-once']:
 print(json.dumps({'state':'PLAN_ONLY','Main_actions':0,'Android_actions':0,'compiler_invoked':False,'submitted':False}));raise SystemExit(0)
raw=sys.stdin.buffer.read(645324)
if len(raw)!=645323 or hashlib.sha256(raw).hexdigest()!='fc85a08d4db8c039c6e859967d8293c907ddd9e4bb61ab6e1191290ed4db61bc':raise RuntimeError('exact builder470 source request differs')
packet=json.loads(raw.decode('utf-8','strict'))
if set(packet)!={'schema','stage','files'} or type(packet['schema']) is not int or packet['schema']!=1:raise RuntimeError('builder470 source packet shape differs')
stage=packet['stage'].encode()
if len(stage)!=7188 or hashlib.sha256(stage).hexdigest()!='1276672085e2cff8821014348c5373e787b56bb9822909cd3512c5bad9541b86':raise RuntimeError('builder470 stage differs')
scope={'__name__':'frozen_builder470_stage','__file__':'<frozen-builder470-stage>'}
exec(compile(stage,'stage_builder470.py','exec'),scope,scope);scope['main'](packet['files'])
