"""Reproduce only the frozen static compile request; never dispatch it."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
template=(ROOT/'build-template.py').read_text()
raw=(ROOT/'config.json').read_text()
assert len(raw.encode())==72806 and hashlib.sha256(raw.encode()).hexdigest()=="9cd0dff7255d9aa681e5511fc5e9e211b6ce1f58f6c38c1477251cb3fb6a5e3d"
assert len(template.encode())==39161 and hashlib.sha256(template.encode()).hexdigest()=="d530e8012845e25a8b4cf1d416b8507e070e28ac704be92837fa41fe72e210a9"
slot='CFG = None  # The immutable packet generator fills this exactly once.'
assert template.count(slot)==1
source=template.replace(slot,'CFG = json.loads('+json.dumps(raw,ensure_ascii=True)+')')
assert len(source.encode())==112690 and hashlib.sha256(source.encode()).hexdigest()=="dd67abeea82413b010f8a6e86d96f77c95386e5a4057e16cf6df9a9fe7f798a0"
request={'executable':'/usr/bin/python3','args':['-I','-B','-'],'host':'pocket4','cwd':'/home/alex/work','stdin':source,'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':10,'timeout_seconds':210,'idempotency_key':'p4-marriott-proc-readlink-outer-tu-build03-'+hashlib.sha256(source.encode()).hexdigest()[:16]}
print(json.dumps(request,ensure_ascii=True,sort_keys=True,indent=2))
