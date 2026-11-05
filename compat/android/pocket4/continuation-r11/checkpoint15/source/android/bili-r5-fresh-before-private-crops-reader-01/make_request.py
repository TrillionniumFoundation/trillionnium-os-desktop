#!/usr/bin/env python3
"""Freeze one bounded private-copy request; never dispatch."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE_SHA='d3475cc4afd7fbbaeb60e27002fedcbf8fe9ba994be5ee9a8575da7032304b9f'
KEY='pocket4-bilibili-r5-player-fresh-before-private-crops-export-01-20261105'
def main():
    raw=(HERE/'read_private_crops.py').read_bytes()
    assert len(raw)==13952 and hashlib.sha256(raw).hexdigest()==SOURCE_SHA
    wrapper=("import sys,hashlib;raw=sys.stdin.buffer.read(16385);assert 0<len(raw)<=16384 and hashlib.sha256(raw).hexdigest()=="+repr(SOURCE_SHA)+";scope={'__name__':'fixed_private_crop_reader','__file__':'<verified-private-crop-reader>'};exec(compile(raw,'read_private_crops.py','exec'),scope);raise SystemExit(scope['main'](['--collect-once']))")
    request={'host':'pocket4','executable':'/usr/bin/sudo','args':['-n','/usr/bin/python3','-I','-c',wrapper],
        'cwd':'/home/alex/work','env':{'PYTHONDONTWRITEBYTECODE':'1'},'stdin':raw.decode(),
        'idempotency_key':KEY,'timeout_seconds':30,'cpu_quota_percent':100,'memory_max_bytes':134217728,'nice':10}
    data=(json.dumps(request,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    with (HERE/'exact-request.json').open('xb') as f:f.write(data)
    print(json.dumps({'state':'EXACT_PRIVATE_COPY_REQUEST_NOT_SUBMITTED','source_bytes':len(raw),'source_sha256':SOURCE_SHA,'request_bytes':len(data),'request_sha256':hashlib.sha256(data).hexdigest(),'stable_key':KEY,'Android_or_process_actions':0}))
if __name__=='__main__':main()
