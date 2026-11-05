import sys,hashlib,io,contextlib,gzip,base64,json
raw=sys.stdin.buffer.read(16385)
assert 0<len(raw)<=16384 and hashlib.sha256(raw).hexdigest()=='8eb9dea5a0c7ba76c9332183f6f4d28ef21bf20d98cf990046be4c8195103786'
scope={'__name__':'fixed_owned_nofile_readonly','__file__':'<verified-fixed-owned-nofile-runtime-readonly-01>'}
exec(compile(raw,'collect.py','exec'),scope,scope)
output=io.StringIO()
with contextlib.redirect_stdout(output):
 code=scope['collect']()
body=output.getvalue().encode('utf-8')
assert 0<len(body)<=4194304
packed=gzip.compress(body,mtime=0)
assert len(packed)<=524288
print(json.dumps({'schema':1,'encoding':'gzip-base64','uncompressed_bytes':len(body),'uncompressed_sha256':hashlib.sha256(body).hexdigest(),'compressed_bytes':len(packed),'compressed_sha256':hashlib.sha256(packed).hexdigest(),'data':base64.b64encode(packed).decode('ascii')},sort_keys=True),flush=True)
raise SystemExit(code)
