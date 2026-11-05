#!/usr/bin/env python3
"""Fixed summary-only reader for the fresh r3 stable owned search-entry attempt."""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT=Path('/home/alex/work/pocket4-bilibili-r3-stable-search-entry-01')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r3-flow-35c49c9f72a6a8323ad1d8f384cad3c6')
NONCE='35c49c9f72a6a8323ad1d8f384cad3c6'
SOURCE_SHA='7e35e1696979b82993ee2f31e91215c72ba9d95e5c4752783ade750b289d9ecc'
FILES={
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'launch.json':FLOW/'steps/launch-01/result.json',
    'navigation.json':FLOW/'steps/search-entry-01/result.json',
    'cleanup.json':FLOW/'steps/cleanup-01/result.json',
    'launch-command-result.json':ROOT/'evidence/02-launch.result.json',
    'navigation-command-result.json':ROOT/'evidence/03-navigate.result.json',
    'cleanup-command-result.json':ROOT/'evidence/04-cleanup.result.json',
}


def need(value,reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def no_raw_ui(value, path=()):
    if path == ('navigation','selector'):
        need(value == {'resource_id':'tv.danmaku.bili:id/expand_search',
                       'class':'android.widget.LinearLayout','content_desc':'Search bar, button'},
             'ONLY_THE_FIXED_PUBLIC_CONTROL_SELECTOR_MAY_LEAVE')
        return
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
                 0<=first.st_size<=262144,'ROOT_SINGLE_REGULAR_SUMMARY_BOUND')
            chunks=[];size=0
            while True:
                need(time.monotonic()-self.started<8,'READ_DEADLINE')
                part=os.read(fd,min(16384,262145-size))
                if not part:
                    break
                chunks.append(part);size+=len(part);self.bytes+=len(part)
                need(size<=262144 and self.bytes<=1048576,'TOTAL_READ_BOUND')
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
    reader=Reader();files={};missing=[]
    for name,path in FILES.items():
        raw=reader.read(path,optional=name not in expected)
        if raw is None:
            missing.append({'name':name,'path':str(path)});continue
        if name in expected:
            need(sha(raw)==expected[name],'EXTERNAL_TERMINAL_SHA_CHANGED:'+name)
        value=json.loads(raw);no_raw_ui(value)
        if name in ('coordinator.json','stage.json','launch.json','navigation.json'):
            need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE,
                 'EXACT_FRESH_FLOW_SOURCE_BINDING_REQUIRED:'+name)
        if name in ('launch.json','navigation.json'):
            need(value.get('helper_package')=='org.droidloom.qa.bili.r3' and value.get('helper_uid')==10166,
                 'EXACT_R3_HELPER_SCOPE_REQUIRED')
        files[name]={'path':str(path),'bytes':len(raw),'sha256':sha(raw),'text':raw.decode('utf-8','strict')}
    bundle={'schema':1,'scope':'fixed-r3-stable-search-entry-summary-only','files':files,'missing':missing,
        'source_manifest_sha256':SOURCE_SHA,'flow_nonce':NONCE,'bytes_read':reader.bytes,
        'raw_UI_or_commercial_journal_exported':False,'Android_or_process_actions':0,
        'runtime_qualification_asserted':False,'permission_or_original_file_changes':0}
    raw=(json.dumps(bundle,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw)<=1310720,'SUMMARY_BUNDLE_BOUND')
    compressed=gzip.compress(raw,mtime=0)
    print(json.dumps({'schema':1,'encoding':'gzip-base64','private_UI_data':False,
        'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw),
        'compressed_bytes':len(compressed),'compressed_sha256':sha(compressed),
        'data':base64.b64encode(compressed).decode('ascii')},sort_keys=True),flush=True)
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
