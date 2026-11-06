"""Regenerate the fixed ordinary readonly request; does not execute it."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent
body = (root/'read_inputs.py').read_text()
request = {
    'host':'pocket4', 'executable':'/usr/bin/python3', 'args':['-I','-B','-'],
    'cwd':'/home/alex/work', 'stdin':body, 'timeout_seconds':60,
    'cpu_quota_percent':100, 'memory_max_bytes':268435456, 'nice':15,
    'idempotency_key':'p4-marriott-arm64-apk-input-read01-'+hashlib.sha256(body.encode()).hexdigest()[:16],
}
print(json.dumps(request,indent=2,sort_keys=True))
