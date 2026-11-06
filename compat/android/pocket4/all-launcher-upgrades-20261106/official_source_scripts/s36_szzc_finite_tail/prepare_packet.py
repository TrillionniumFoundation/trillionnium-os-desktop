from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 's35_szzc_published_candidate'
raw = (BASE/'fetch_szzc_published_once.py').read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'eb4a8e7ff656e7bfec530d1310b317b95c2172c5ab7a765a78a93c206483f6ae'
tree = ast.parse(raw)
lines = raw.decode().splitlines()
shared_names = {'need','NoRedirect','census','write_all','verify_file'}
shared = '\n\n'.join('\n'.join(lines[n.lineno-1:n.end_lineno]) for n in tree.body
                       if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in shared_names)
assign = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and
          len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and isinstance(n.value,(ast.Constant,ast.Tuple))}
terminal = (BASE/'actual/status-4.original.txt').read_text()
prefix = json.loads((BASE/'actual/partial.file-info.original.txt').read_bytes())
receipt = json.loads((BASE/'actual/result.file-info.original.txt').read_bytes())
def pin(d):
    return {'path':d['path'],'bytes':d['size'],'sha256':d['sha256'],'version':d['version'],'mode':d['mode']}
header = '''#!/usr/bin/env python3
"""One bounded continuation of an actually settled normal HTTPS download."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import stat
import sys
import time
import urllib.error
import urllib.request
'''
for name in ('URL','NAME','EXPECTED_BYTES','BOUND_INSTALLED_SHA256','FIELDS'):
    header += name + ' = ' + repr(assign[name]) + '\n'
header += "ROOT = Path('/home/alex/work/pocket4-szzc-finite-tail-20261106-s36')\n"
for name,value in [('PREFIX',pin(prefix)),('PRIOR_RESULT',pin(receipt)),('PRIOR_TERMINAL_RAW',terminal),
                   ('PRIOR_TERMINAL_SHA256',hashlib.sha256(terminal.encode()).hexdigest()),
                   ('LAST_MODIFIED','Mon, 02 Nov 2026 02:41:02 GMT')]:
    header += name+' = '+repr(value)+'\n'
source = (header+'\n'+shared+'\n\n'+(ROOT/'continuation_body.py').read_text()).encode()
compile(source,str(ROOT/'continue_szzc_once.py'),'exec')
(ROOT/'continue_szzc_once.py').write_bytes(source)
packet = {'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-B','-c',source.decode(),'--continue-one-range'],
    'idempotency_key':'pocket4-szzc-one-fixed-tail-s36-20261106-r1','timeout_seconds':270,
    'memory_max_bytes':536870912,'cpu_quota_percent':100,'nice':10}
body = (json.dumps(packet,sort_keys=True,indent=2)+'\n').encode()
(ROOT/'process-request.json').write_bytes(body)
pins = {'schema':'pocket4-szzc-one-fixed-tail-pins-v1','state':'PREPARED_NOT_SUBMITTED',
    'source':{'bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()},
    'request':{'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()},
    'reused_exact_functions':sorted(shared_names),'original_source_sha256':hashlib.sha256(raw).hexdigest(),
    'prior_actual_full_hash_file_info':pin(prefix),'prior_actual_failed_result':pin(receipt),
    'range_start':prefix['size'],'range_end':assign['EXPECTED_BYTES']-1,'range_bytes':assign['EXPECTED_BYTES']-prefix['size'],
    'network_requests_max':1,'automatic_retries':0,'old_failure_preserved':True,
    'Android_commands':0,'installs':0,'newer_version_claimed':False,'production_ready':False}
(ROOT/'SOURCE_PINS.json').write_text(json.dumps(pins,sort_keys=True,indent=2)+'\n')
print(json.dumps(pins))
