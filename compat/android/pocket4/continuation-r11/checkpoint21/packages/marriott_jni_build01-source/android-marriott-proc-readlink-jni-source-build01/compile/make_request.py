"""Reproduce only the frozen static compile request; never dispatch it."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
template=(ROOT/'build-template.py').read_text()
raw=(ROOT/'config.json').read_text()
assert len(raw.encode())==68111 and hashlib.sha256(raw.encode()).hexdigest()=="811b2e508baa25f58e04fed3405457e9f6bf4612d157614bb6e080477a2ea0f9"
assert len(template.encode())==37059 and hashlib.sha256(template.encode()).hexdigest()=="57675940eadbfab28e848fafbc78d694ca4516c20948a09ced9c4e3b6c0e85e6"
slot='CFG = None  # The immutable packet generator fills this exactly once.'
assert template.count(slot)==1
source=template.replace(slot,'CFG = json.loads('+json.dumps(raw,ensure_ascii=True)+')')
assert len(source.encode())==105540 and hashlib.sha256(source.encode()).hexdigest()=="48ff39eed3976acdaec2392000462043b7f398bf96f2f5d4d8630a8315fb48fb"
request={'executable':'/usr/bin/python3','args':['-I','-B','-'],'host':'pocket4','cwd':'/home/alex/work','stdin':source,'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':10,'timeout_seconds':210,'idempotency_key':'p4-marriott-proc-readlink-outer-tu-build01-'+hashlib.sha256(source.encode()).hexdigest()[:16]}
print(json.dumps(request,ensure_ascii=True,sort_keys=True,indent=2))
