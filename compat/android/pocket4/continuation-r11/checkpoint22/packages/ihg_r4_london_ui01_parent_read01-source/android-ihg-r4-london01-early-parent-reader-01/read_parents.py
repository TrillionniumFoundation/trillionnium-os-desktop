#!/usr/bin/env python3
"""Fixed two-parent IHG London failure reader; no Main or Android operation."""
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
FILES={
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
}


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
        maximum=6175 if path==FILES['coordinator.json'] else 2187
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


def collect(coordinator_sha,stage_sha):
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    need(all(isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x) for x in (coordinator_sha,stage_sha)),
         'EXTERNAL_EXACT_TERMINAL_PINS_REQUIRED')
    expected={'coordinator.json':coordinator_sha,'stage.json':stage_sha}
    sizes={'coordinator.json':6175,'stage.json':2187}
    reader=Reader();files={};values={}
    for name in ('coordinator.json','stage.json'):
        path=FILES[name];raw=reader.read(path)
        need(sha(raw)==expected[name] and len(raw)==sizes[name],
             'EXTERNAL_TERMINAL_BYTES_CHANGED:'+name)
        value=json.loads(raw);no_raw_ui(value)
        need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE and
             value.get('package')=='com.ihg.apps.android','EXACT_FRESH_FLOW_SOURCE_BINDING_REQUIRED:'+name)
        values[name]=value
        files[name]={'path':str(path),'bytes':len(raw),'sha256':sha(raw),'text':raw.decode('utf-8','strict')}
    coordinator=values['coordinator.json'];stage=values['stage.json']
    observed=files['coordinator.json']
    need(stage.get('coordinator_result')=={k:observed[k] for k in ('path','bytes','sha256')},
         'STAGE_COORDINATOR_LINK_REQUIRED')
    need(coordinator.get('helper_package')=='org.droidloom.qa.ihg.r4' and
         coordinator.get('helper_uid')==HELPER_UID and coordinator.get('uid')==10137 and
         coordinator.get('flow')==str(FLOW),'EXACT_IHG_COORDINATOR_SCOPE_REQUIRED')
    # Export only the exact two original parents. Retained phase pins, if any,
    # remain original metadata; no child or successful Main guard is assumed.
    bundle={'schema':1,'scope':'fixed-current-IHG-R4-London01-early-failure-two-terminal-parents-only','files':files,
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
    p.add_argument('--coordinator-sha256');p.add_argument('--stage-sha256')
    args=p.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','files':{k:str(v) for k,v in FILES.items()},'remote_actions':0}))
        return 0
    return collect(args.coordinator_sha256,args.stage_sha256)


if __name__=='__main__':
    raise SystemExit(main())
