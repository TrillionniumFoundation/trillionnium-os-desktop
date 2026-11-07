#!/usr/bin/env python3
"""Bind the fixed safe reader to actual terminal hashes; never dispatch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
READER_SHA='abaa3e48e334cefeb153c9d4e8c8a15978b671f717adc9041c0b432fb5c499ec'
KEY='pocket4-bilibili-r3-public-query-summary-readback-01-20261105'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-once',action='store_true')
    p.add_argument('--coordinator-sha256');p.add_argument('--stage-sha256')
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if not a.write_once:
        print(json.dumps({'state':'PLAN_ONLY','source_sha256':READER_SHA,'stable_key':KEY,
                          'actual_terminal_pins_required':True,'remote_actions':0}))
        return 0
    assert a.output is not None and all(isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x)
                                       for x in (a.coordinator_sha256,a.stage_sha256))
    raw=(HERE/'read_summary.py').read_bytes()
    assert len(raw)==6276 and hashlib.sha256(raw).hexdigest()==READER_SHA
    args=['--collect-once','--coordinator-sha256',a.coordinator_sha256,'--stage-sha256',a.stage_sha256]
    wrapper="import sys,hashlib;raw=sys.stdin.buffer.read(16385);assert 0<len(raw)<=16384 and hashlib.sha256(raw).hexdigest()=="+repr(READER_SHA)+";scope={'__name__':'fixed_owned_summary_reader','__file__':'<verified-fixed-summary-reader>'};exec(compile(raw,'read_summary.py','exec'),scope);raise SystemExit(scope['main']("+repr(args)+"))"
    request={'host':'pocket4','executable':'/usr/bin/sudo','args':['-n','/usr/bin/python3','-I','-c',wrapper],
        'cwd':'/home/alex/work','env':{'PYTHONDONTWRITEBYTECODE':'1'},'stdin':raw.decode('utf-8'),
        'idempotency_key':KEY,'timeout_seconds':30,'cpu_quota_percent':100,'memory_max_bytes':134217728,'nice':10}
    data=(json.dumps(request,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    try:
        offset=0
        while offset<len(data):
            count=os.write(fd,data[offset:]);assert count>0;offset+=count
        os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'state':'EXACT_REQUEST_NOT_SUBMITTED','path':str(a.output),'bytes':len(data),
        'sha256':hashlib.sha256(data).hexdigest(),'stdin_sha256':READER_SHA,'stable_key':KEY}))
    return 0

if __name__=='__main__':raise SystemExit(main())
