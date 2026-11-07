#!/usr/bin/env python3
"""Fixed parent-bound IHG London launch failure receipt; no Main or Android operation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT=Path("/home/alex/work/pocket4-ihg-r4-public-london-input-01")
FLOW=Path("/home/alex/work/pocket4-ihg-owned-qa-r4-flow-ec4f2977574102b1e5869d2494e8416b")
NONCE="ec4f2977574102b1e5869d2494e8416b"
SOURCE_SHA="24a8491dbb44faf1288869d278da96290597b7af1fcdcce12a72fd62bad9435f"
HELPER_UID=10158
FILES={'launch.json':FLOW/'steps/launch-01/result.json'}
PARENT={'path':str(ROOT/'result.json'),'bytes':6175,
        'sha256':'09e528df22c01ffbb293264309c028ce549666602e4a97669c3eac80d62488b1'}
LAUNCH={'path':str(FILES['launch.json']),'bytes':12051,
        'sha256':'3ab8190051ab6c628a7e6b67c0f10567cb18e273db6ecc067b5856098e37034b'}


def need(value,reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def no_raw_ui(value, path=()):
    if isinstance(value,dict):
        need(not ({'nodes','text','content_desc','raw_tree','raw_ui_tree','screenshot'} & set(value)),
             'RAW_UI_FIELD_FORBIDDEN_IN_SUMMARY_EXPORT')
        for key,item in value.items():
            no_raw_ui(item,path+(key,))
    elif isinstance(value,list):
        for index,item in enumerate(value):
            no_raw_ui(item,path+(str(index),))


class Reader:
    def __init__(self):
        self.started=time.monotonic();self.bytes=0

    def read(self,path,optional=False):
        need(path in FILES.values(),'EXACT_FILE_ALLOWLIST_REQUIRED')
        maximum=12051
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
        try:
            try:
                for name in path.parts[1:-1]:
                    nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
                    os.close(current);current=nxt
                fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
            except FileNotFoundError:
                if optional:
                    return None
                raise
            first=os.fstat(fd)
            need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
                 0<=first.st_size<=maximum,'ROOT_SINGLE_REGULAR_SUMMARY_BOUND')
            chunks=[];size=0
            while True:
                need(time.monotonic()-self.started<8,'READ_DEADLINE')
                part=os.read(fd,min(16384,maximum+1-size))
                if not part:
                    break
                chunks.append(part);size+=len(part);self.bytes+=len(part)
                need(size<=maximum and self.bytes<=2097152,'TOTAL_READ_BOUND')
            last=os.fstat(fd)
            keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
            need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),'FILE_CHANGED')
            return b''.join(chunks)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(current)


def collect(launch_sha):
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    need(isinstance(launch_sha,str) and re.fullmatch('[0-9a-f]{64}',launch_sha) and
         launch_sha==LAUNCH['sha256'],'EXTERNAL_EXACT_PARENT_RETAINED_PIN_REQUIRED')
    reader=Reader();path=FILES['launch.json'];raw=reader.read(path)
    need(sha(raw)==launch_sha and len(raw)==LAUNCH['bytes'],'PARENT_RETAINED_LAUNCH_BYTES_CHANGED')
    value=json.loads(raw);no_raw_ui(value)
    need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE and
         value.get('package')=='com.ihg.apps.android' and value.get('phase')=='launch',
         'EXACT_FRESH_FLOW_SOURCE_PHASE_BINDING_REQUIRED')
    need(value.get('helper_package')=='org.droidloom.qa.ihg.r4' and
         value.get('helper_uid')==HELPER_UID and value.get('uid')==10137,
         'EXACT_IHG_LAUNCH_RECEIPT_SCOPE_REQUIRED')
    files={'launch.json':{'path':str(path),'bytes':len(raw),'sha256':sha(raw),
                         'text':raw.decode('utf-8','strict')}}
    # PARENT and LAUNCH are exact pins taken from the fully collected original
    # coordinator. This read exports only its one retained launch receipt.
    # A failed receipt, unknown outcome or absent Main-after remains unchanged.
    bundle={'schema':1,'scope':'fixed-current-IHG-R4-London01-parent-bound-launch-receipt-only',
        'files':files,'actual_parent':PARENT,'actual_parent_retained_launch':LAUNCH,
        'source_manifest_sha256':SOURCE_SHA,'flow_nonce':NONCE,'bytes_read':reader.bytes,
        'raw_UI_or_commercial_journal_exported':False,'Android_or_process_actions':0,
        'runtime_qualification_asserted':False,'permission_or_original_file_changes':0}
    raw=(json.dumps(bundle,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw)<=3145728,'SUMMARY_BUNDLE_BOUND')
    print(json.dumps({'schema':1,'encoding':'plain-utf8','private_UI_data':False,
        'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw),
        'data':raw.decode('utf-8','strict')},sort_keys=True),flush=True)
    return 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collect-once',action='store_true')
    p.add_argument('--launch-sha256')
    args=p.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','files':{k:str(v) for k,v in FILES.items()},'remote_actions':0}))
        return 0
    return collect(args.launch_sha256)


if __name__=='__main__':
    raise SystemExit(main())
