import hashlib,json,sys
if sys.argv[1:] != ['--stage-only-once']:
 print(json.dumps({'state':'PLAN_ONLY','Main_actions':0,'Android_actions':0,'compiler_invoked':False,'submitted':False}));raise SystemExit(0)
raw=sys.stdin.buffer.read(645192)
if len(raw)!=645191 or hashlib.sha256(raw).hexdigest()!='2fa99c7e9740ccfe1f03a2318f26ed0ffc47e45f7e313ccfd19afbb2f79e68f2':raise RuntimeError('exact builder470 source request differs')
packet=json.loads(raw.decode('utf-8','strict'))
if set(packet)!={'schema','stage','files'} or type(packet['schema']) is not int or packet['schema']!=1:raise RuntimeError('builder470 source packet shape differs')
stage=packet['stage'].encode()
if len(stage)!=7188 or hashlib.sha256(stage).hexdigest()!='715f3b4c856e95b064073d80be6b67e4fb664aac6d2b759418193e3b7a8071b4':raise RuntimeError('builder470 stage differs')
scope={'__name__':'frozen_builder470_stage','__file__':'<frozen-builder470-stage>'}
exec(compile(stage,'stage_builder470.py','exec'),scope,scope);scope['main'](packet['files'])
