import hashlib,sys
raw=sys.stdin.buffer.read(29331)
if len(raw)!=29330 or hashlib.sha256(raw).hexdigest()!="0878c762de8ee0b6b19b3b8836a236120e6294ed4cfffc7a40ea621c2b73c076":
    raise RuntimeError('EXACT_FIXED_DIAGNOSTIC_SOURCE_REQUIRED')
scope={'__name__':'__main__','__file__':"<pocket4-douyin-one-apk-fstat-diagnostic-01>"}
exec(compile(raw,"<pocket4-douyin-one-apk-fstat-diagnostic-01>",'exec'),scope)
