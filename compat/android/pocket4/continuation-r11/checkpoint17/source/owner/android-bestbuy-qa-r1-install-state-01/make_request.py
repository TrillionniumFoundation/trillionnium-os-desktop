#!/usr/bin/env python3
"""Create one exact request file; never dispatch any tool or install command."""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
KEY='pocket4-owned-bestbuy-qa-r1-install-state-01-20261105'
ROOT='/home/alex/work/pocket4-owned-bestbuy-qa-r1-install-state-01'
NONCE='1a52aa80a32d02e2ed1b8e00f7f76875'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-once',action='store_true')
    p.add_argument('--source-manifest-sha256')
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if not a.write_once:
        print(json.dumps({'state':'PLAN_ONLY','stable_key':KEY,'remote_actions':0}))
        return 0
    manifest_raw=(HERE/'SOURCE_PINS.json').read_bytes()
    assert sha(manifest_raw) == a.source_manifest_sha256
    manifest=json.loads(manifest_raw)
    files={}
    for name,row in manifest['files'].items():
        raw=(HERE/name).read_bytes()
        assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
        files[name]=raw.decode('utf-8')
    files['SOURCE_PINS.json']=manifest_raw.decode('utf-8')
    packet={'schema':1,'source_manifest_sha256':a.source_manifest_sha256,'nonce':NONCE,'files':files}
    payload=(json.dumps(packet,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    assert len(payload)<=262144
    stage_sha=manifest['files']['stage_execute.py']['sha256']
    wrapper="import hashlib,json,sys\nraw=sys.stdin.buffer.read(262145)\n"
    wrapper+="assert hashlib.sha256(raw).hexdigest()=="+repr(sha(payload))+"\n"
    wrapper+="p=json.loads(raw);src=p['files']['stage_execute.py'].encode('utf-8')\n"
    wrapper+="assert hashlib.sha256(src).hexdigest()=="+repr(stage_sha)+"\n"
    wrapper+="scope={'__name__':'owned_qa_stage','__file__':"+repr(ROOT+'/source/stage_execute.py')+"}\n"
    wrapper+="exec(compile(src,scope['__file__'],'exec'),scope)\nraise SystemExit(scope['main'](raw))\n"
    request={'host':'pocket4','executable':'/usr/bin/sudo',
        'args':['-n','/usr/bin/python3','-I','-c',wrapper],
        'cwd':'/home/alex/work','env':{'PYTHONDONTWRITEBYTECODE':'1'},
        'stdin':payload.decode('utf-8'),'idempotency_key':KEY,
        'timeout_seconds':300,'cpu_quota_percent':100,'memory_max_bytes':536870912,'nice':10}
    encoded=(json.dumps(request,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode()
    assert a.output is not None
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(encoded);stream.flush();os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps({'state':'EXACT_REQUEST_NOT_SUBMITTED','path':str(a.output),'bytes':len(encoded),
        'sha256':sha(encoded),'stdin_bytes':len(payload),'stdin_sha256':sha(payload),'stable_key':KEY}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
