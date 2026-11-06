import hashlib,json,sys
if sys.argv[1:] != ['--stage-only-once']:raise SystemExit('PLAN_ONLY: stage not executed')
raw=sys.stdin.buffer.read(77478)
if len(raw)!=77477 or hashlib.sha256(raw).hexdigest()!='262006a394a102e4be372a6ba31960168f47f49d682ca9e3a297cbf05467066e':raise RuntimeError('closed qualification packet differs')
packet=json.loads(raw.decode('utf-8','strict'))
if set(packet)!={'schema','stage','files'} or type(packet['schema']) is not int or packet['schema']!=1:raise RuntimeError('closed qualification packet shape differs')
stage=packet['stage'].encode('utf-8','strict')
if len(stage)!=3831 or hashlib.sha256(stage).hexdigest()!='b00c9cc75c33b57eadf7c392ccdc423d0e37e47cfc323667ff1e2ff6ea25630c':raise RuntimeError('closed qualifier stager differs')
scope={'__name__':'fixed_current470_qualification_stager','__file__':'<fixed-current470-qualification-stager>'}
exec(compile(stage,'stage_current470_qualification.py','exec'),scope,scope)
scope['main'](packet['files'])
