"""Reproduce only the frozen static compile request; never dispatch it."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
template=(ROOT/'build-template.py').read_text()
raw=(ROOT/'config.json').read_text()
assert len(raw.encode())==69109 and hashlib.sha256(raw.encode()).hexdigest()=="c82bc679b3b1223909f34bf9d1dfedc8fa5ec33f2d7706db7170277a094554e2"
assert len(template.encode())==37312 and hashlib.sha256(template.encode()).hexdigest()=="64ff08b97884e5975d8ee2cb302c7f7c9b4b6f6fb4f5e438dd64f115ce06bbc6"
slot='CFG = None  # The immutable packet generator fills this exactly once.'
assert template.count(slot)==1
source=template.replace(slot,'CFG = json.loads('+json.dumps(raw,ensure_ascii=True)+')')
assert len(source.encode())==106865 and hashlib.sha256(source.encode()).hexdigest()=="9d3abe9eaede9b4f6def892b683ff1f0ae78648c83522e876a2a8d1b9a9423fa"
request={'executable':'/usr/bin/python3','args':['-I','-B','-'],'host':'pocket4','cwd':'/home/alex/work','stdin':source,'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':10,'timeout_seconds':210,'idempotency_key':'p4-marriott-proc-readlink-outer-tu-build02-'+hashlib.sha256(source.encode()).hexdigest()[:16]}
print(json.dumps(request,ensure_ascii=True,sort_keys=True,indent=2))
