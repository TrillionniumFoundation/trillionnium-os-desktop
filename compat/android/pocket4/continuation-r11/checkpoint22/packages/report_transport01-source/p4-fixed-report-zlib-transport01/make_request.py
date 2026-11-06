"""Reproduce the fixed transport request. Never dispatch."""
import hashlib,json
from pathlib import Path
source=Path(__file__).with_name('transport.py').read_text()
assert len(source.encode())==21194 and hashlib.sha256(source.encode()).hexdigest()=="1ac361911bf3b9a0080c80f5db006aeb0f9fe52cb9b48b88d265185eff79d23d"
q={'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-B','-'],'cwd':'/home/alex/work','stdin':source,'cpu_quota_percent':100,'memory_max_bytes':268435456,'nice':15,'timeout_seconds':60,'idempotency_key':'p4-fixed-report-zlib-transport01-'+hashlib.sha256(source.encode()).hexdigest()[:16]}
print(json.dumps(q,sort_keys=True,indent=2))
