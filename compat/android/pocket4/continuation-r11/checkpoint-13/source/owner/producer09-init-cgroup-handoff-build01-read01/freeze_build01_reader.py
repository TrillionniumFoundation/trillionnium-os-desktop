#!/usr/bin/env python3
"""Freeze a fixed protected-report reader after actual terminal metadata exists."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE=Path(__file__).resolve().parent.parent
OLD=BASE/'init-socket-projection-build01-read-freeze-01'
OUT=BASE/'init-cgroup-handoff-build01-read-freeze-01'
def sha(body):return hashlib.sha256(body).hexdigest()
def pretty(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def main():
    p=argparse.ArgumentParser();p.add_argument('--bytes',type=int,required=True);p.add_argument('--sha256',required=True);args=p.parse_args()
    assert 0<args.bytes<=1048576 and re.fullmatch('[0-9a-f]{64}',args.sha256)
    old=(OLD/'read.py').read_text()
    changes=[("ROOT_NAME = 'p4-init-socket-projection-20261105-build-01'","ROOT_NAME = 'p4-init-cgroup-handoff-20261105-build-01'"),
             ('EXPECTED_REPORT_BYTES = 445590','EXPECTED_REPORT_BYTES = '+str(args.bytes)),
             ("EXPECTED_REPORT_SHA256 = 'b74dabc8c2cd8abcb4efe7de2cd35a95ec9ee5b29f364d33f055c0cd305972cd'","EXPECTED_REPORT_SHA256 = '"+args.sha256+"'"),
             ("'fixed-init-projection-build01-read'","'fixed-init-cgroup-handoff-build01-read'")]
    source=old
    for before,after in changes:assert source.count(before)==1;source=source.replace(before,after)
    restored=source
    for before,after in reversed(changes):assert restored.count(after)==1;restored=restored.replace(after,before)
    assert restored==old
    ast.parse(source);compile(source,'read.py','exec')
    request=json.loads((OLD/'request.json').read_bytes());request['stdin']=source
    request['idempotency_key']='p4-init-cgroup-handoff-build01-read01-'+sha(source.encode())[:16]
    OUT.mkdir(exist_ok=False)
    payload={'read.py':source.encode(),'request.json':pretty(request),
             'source.diff':''.join(difflib.unified_diff(old.splitlines(True),source.splitlines(True),fromfile='projection01/read.py',tofile='cgroup-handoff01/read.py')).encode(),
             'validation.json':pretty({'inverse_reconstruction_exact':True,'fixed_member_count':1,
                  'expected_report_bytes':args.bytes,'expected_report_sha256':args.sha256,
                  'request_stdin_matches_source':True,'function_bodies_unchanged_except_kind_label':True,
                  'key':request['idempotency_key'],'qualification':False}),
             'freeze_build01_reader.py':Path(__file__).read_bytes()}
    for name,body in payload.items():(OUT/name).open('xb').write(body)
    rows=[{'path':name,'bytes':len(body),'sha256':sha(body)} for name,body in sorted(payload.items())]
    manifest=pretty({'files':rows,'runtime_executed':False});(OUT/'manifest.json').open('xb').write(manifest)
    print(json.dumps({'root':str(OUT),'source_sha256':sha(payload['read.py']),'request_sha256':sha(payload['request.json']),'request_bytes':len(payload['request.json']),'manifest_sha256':sha(manifest),'key':request['idempotency_key']}))
if __name__=='__main__':main()
