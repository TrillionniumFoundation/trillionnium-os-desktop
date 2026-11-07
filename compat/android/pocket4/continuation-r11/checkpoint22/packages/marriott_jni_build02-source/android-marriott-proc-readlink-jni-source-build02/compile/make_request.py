"""Reproduce only the frozen static compile request; never dispatch it."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
template=(ROOT/'build-template.py').read_text()
raw=(ROOT/'config.json').read_text()
assert len(raw.encode())==69109 and hashlib.sha256(raw.encode()).hexdigest()=="c82bc679b3b1223909f34bf9d1dfedc8fa5ec33f2d7706db7170277a094554e2"
assert len(template.encode())==37312 and hashlib.sha256(template.encode()).hexdigest()=="0c372a0fee860d4b23845b7e27006704f9a917246246bccaa470b3071920f288"
slot='CFG = None  # The immutable packet generator fills this exactly once.'
assert template.count(slot)==1
source=template.replace(slot,'CFG = json.loads('+json.dumps(raw,ensure_ascii=True)+')')
assert len(source.encode())==106865 and hashlib.sha256(source.encode()).hexdigest()=="6924ef6031399036d9c44a26042289d4774cfdcb1026151a44263270adfe0801"
request={'executable':'/usr/bin/python3','args':['-I','-B','-'],'host':'pocket4','cwd':'/home/alex/work','stdin':source,'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':10,'timeout_seconds':210,'idempotency_key':'p4-marriott-proc-readlink-outer-tu-build02-'+hashlib.sha256(source.encode()).hexdigest()[:16]}
print(json.dumps(request,ensure_ascii=True,sort_keys=True,indent=2))
