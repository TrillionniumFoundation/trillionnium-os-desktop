#!/usr/bin/env python3
"""Create the one exact retained-file diagnostic request; never dispatch."""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
READER_SHA='8b3b222fa6075d01124f600e4ddf7cf66e40c96f1c9c66cc9781e86eee26cf5e'
READER_BYTES=15988
KEY='pocket4-bilibili-r5-player-structure-readback-01-20261105'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--write-once',action='store_true')
    p.add_argument('--output',type=Path);a=p.parse_args()
    if not a.write_once:
        print(json.dumps({'state':'PLAN_ONLY','source_sha256':READER_SHA,'bytes':READER_BYTES,
                          'stable_key':KEY,'Android_or_process_actions':0}));return 0
    raw=(HERE/'read_structure.py').read_bytes()
    assert len(raw)==READER_BYTES and hashlib.sha256(raw).hexdigest()==READER_SHA and a.output is not None
    wrapper="import sys,hashlib;raw=sys.stdin.buffer.read(16385);assert len(raw)==15988 and hashlib.sha256(raw).hexdigest()=="+repr(READER_SHA)+";scope={'__name__':'fixed_retained_structure_reader','__file__':'<verified-retained-structure-reader>'};exec(compile(raw,'read_structure.py','exec'),scope);raise SystemExit(scope['main'](['--collect-once']))"
    request={'host':'pocket4','executable':'/usr/bin/sudo','args':['-n','/usr/bin/python3','-I','-c',wrapper],
             'cwd':'/home/alex/work','env':{'PYTHONDONTWRITEBYTECODE':'1'},'stdin':raw.decode('utf-8'),
             'idempotency_key':KEY,'timeout_seconds':30,'cpu_quota_percent':100,
             'memory_max_bytes':134217728,'nice':10}
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
