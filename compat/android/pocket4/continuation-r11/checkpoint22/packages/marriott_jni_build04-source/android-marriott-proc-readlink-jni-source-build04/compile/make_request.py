"""Reproduce only the frozen static compile request; never dispatch it."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
template=(ROOT/'build-template.py').read_text()
raw=(ROOT/'config.json').read_text()
assert len(raw.encode())==72806 and hashlib.sha256(raw.encode()).hexdigest()=="caea1c9df7adf148dbb52ba8bdac03087fb9d76d627746bb1a8af68ba8eeea1e"
assert len(template.encode())==39333 and hashlib.sha256(template.encode()).hexdigest()=="fefae8d458c2b8d46268162b8d42b5b90ba7413809209d727dba71e3710536a7"
slot='CFG = None  # The immutable packet generator fills this exactly once.'
assert template.count(slot)==1
source=template.replace(slot,'CFG = json.loads('+json.dumps(raw,ensure_ascii=True)+')')
assert len(source.encode())==112862 and hashlib.sha256(source.encode()).hexdigest()=="43f4d22a748006350e44ae16166c3d10fe67fd2b750a36e0baa29fb3120155ff"
request={'executable':'/usr/bin/python3','args':['-I','-B','-'],'host':'pocket4','cwd':'/home/alex/work','stdin':source,'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':10,'timeout_seconds':210,'idempotency_key':'p4-marriott-proc-readlink-outer-tu-build04-'+hashlib.sha256(source.encode()).hexdigest()[:16]}
print(json.dumps(request,ensure_ascii=True,sort_keys=True,indent=2))
