import hashlib,sys
raw=sys.stdin.buffer.read(29299)
if len(raw)!=29298 or hashlib.sha256(raw).hexdigest()!="3f214b5bdd304ba2839369b8053f0cd48ab9dac271aa19c1f4e1bdb5a5ff52da":
    raise RuntimeError('EXACT_FIXED_DIAGNOSTIC_SOURCE_REQUIRED')
scope={'__name__':'__main__','__file__':"<pocket4-wechat-one-apk-fstat-diagnostic-01>"}
exec(compile(raw,"<pocket4-wechat-one-apk-fstat-diagnostic-01>",'exec'),scope)
