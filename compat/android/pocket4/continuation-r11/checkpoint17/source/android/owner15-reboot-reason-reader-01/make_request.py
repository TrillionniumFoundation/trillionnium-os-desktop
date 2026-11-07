"""Exact read-only request; does not submit any remote action."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
source=(p/'read_reason.py').read_bytes()
request={'host':'pocket4','executable':'/usr/bin/sudo','args':['-n','/usr/bin/python3','-I','-B','-'],'cwd':'/','env':{'LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'},'stdin':source.decode('utf-8'),'timeout_seconds':50,'cpu_quota_percent':100,'memory_max_bytes':134217728,'nice':10,'idempotency_key':'p4-owner15-reboot-reason01-'+hashlib.sha256(source).hexdigest()[:16]}
body=(json.dumps(request,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
with (p/'exact-request.json').open('xb') as output: output.write(body)
print(json.dumps({'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'stdin_bytes':len(source),'stdin_sha256':hashlib.sha256(source).hexdigest(),'key':request['idempotency_key']}))
