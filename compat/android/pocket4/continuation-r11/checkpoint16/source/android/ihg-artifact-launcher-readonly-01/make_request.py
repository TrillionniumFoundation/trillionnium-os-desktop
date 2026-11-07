#!/usr/bin/env python3
"""Generate one exact metadata-only request; never submit it."""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
READER_SHA='51ecf1c0a12d8bfa9ed721265e14c4f06ef3eff72cbf5840de9569eb09797d40'
READER_BYTES=21052
STAGE_SHA='c667f16fddb1ad10f74f321fbb7bf20e661f1c691f77540a96269cd13511a04c'
STAGE_BYTES=3872
NONCE='70e82b2ce30be099f99c9e46431b2406'
KEY='pocket4-ihg-artifact-launcher-readonly-01-20261105'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-once',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if not a.write_once:
        print(json.dumps({'state':'PLAN_ONLY','package':'com.ihg.apps.android',
                          'nonce':NONCE,'stable_key':KEY,'Android_UI_actions':0,'submission':False}))
        return 0
    reader=(HERE/'read_ihg.py').read_bytes();stage=(HERE/'stage_execute.py').read_bytes()
    assert len(NONCE)==32 and int(NONCE,16)>=0
    assert len(reader)==READER_BYTES and hashlib.sha256(reader).hexdigest()==READER_SHA
    assert len(stage)==STAGE_BYTES and hashlib.sha256(stage).hexdigest()==STAGE_SHA
    packet=(json.dumps({'schema':1,'nonce':NONCE,'source':reader.decode('utf-8')},
                      ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    assert 0<len(packet)<=32768 and a.output is not None
    wrapper=('import hashlib,json,sys;raw=sys.stdin.buffer.read(32769);assert len(raw)=='+str(len(packet))+
        ' and hashlib.sha256(raw).hexdigest()=='+repr(hashlib.sha256(packet).hexdigest())+
        ';stage='+repr(stage.decode('utf-8'))+
        ';assert hashlib.sha256(stage.encode()).hexdigest()=='+repr(STAGE_SHA)+
        ';scope={"__name__":"ticket12306_fixed_metadata_stage","__file__":"<verified-ticket12306-stage>"};'+
        'exec(compile(stage,"stage_execute.py","exec"),scope);'+
        'raise SystemExit(scope["main"](json.loads(raw),'+repr(READER_SHA)+'))')
    request={'host':'pocket4','executable':'/usr/bin/sudo',
             'args':['-n','/usr/bin/python3','-I','-c',wrapper],
             'cwd':'/home/alex/work','env':{'PYTHONDONTWRITEBYTECODE':'1'},
             'stdin':packet.decode('utf-8'),'idempotency_key':KEY,
             'timeout_seconds':240,'cpu_quota_percent':100,'memory_max_bytes':536870912,'nice':10}
    raw=(json.dumps(request,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    try:
        offset=0
        while offset<len(raw):
            n=os.write(fd,raw[offset:]);assert n>0;offset+=n
        os.fsync(fd)
    finally:os.close(fd)
    print(json.dumps({'state':'EXACT_REQUEST_NOT_SUBMITTED','path':str(a.output),'bytes':len(raw),
        'sha256':hashlib.sha256(raw).hexdigest(),'stdin_bytes':len(packet),
        'stdin_sha256':hashlib.sha256(packet).hexdigest(),'stable_key':KEY}))
    return 0

if __name__=='__main__':raise SystemExit(main())
