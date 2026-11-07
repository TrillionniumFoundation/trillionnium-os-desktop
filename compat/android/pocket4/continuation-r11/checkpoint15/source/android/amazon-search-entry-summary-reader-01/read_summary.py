#!/usr/bin/env python3
"""Fixed summary-only reader for one Amazon launch / search-entry / cleanup attempt."""
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

ROOT=Path('/home/alex/work/pocket4-amazon-owned-search-entry-01')
FLOW=Path('/home/alex/work/pocket4-amazon-owned-qa-r1-flow-853b099b08f0e7a60c3d7b05fcd07461')
NONCE='853b099b08f0e7a60c3d7b05fcd07461'
SOURCE_SHA='1c6b1f70daaa562236c434bd38c7c95051ff095f8e92571fb09f85123403f567'
HELPER_UID=10175
FILES={
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'launch.json':FLOW/'steps/launch-01/result.json',
    'inspection.json':FLOW/'steps/inspect-01/result.json',
    'cleanup.json':FLOW/'steps/cleanup-01/result.json',
    'launch-command-result.json':ROOT/'evidence/01-launch.result.json',
    'inspection-command-result.json':ROOT/'evidence/02-inspect.result.json',
    'cleanup-command-result.json':ROOT/'evidence/03-cleanup.result.json',
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
        maximum=1048576 if path == FILES['inspection.json'] else 262144
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
    reader=Reader();files={};missing=[]
    for name,path in FILES.items():
        raw=reader.read(path,optional=name not in expected)
        if raw is None:
            missing.append({'name':name,'path':str(path)});continue
        if name in expected:
            need(sha(raw)==expected[name],'EXTERNAL_TERMINAL_SHA_CHANGED:'+name)
        value=json.loads(raw);no_raw_ui(value)
        if name in ('coordinator.json','stage.json','launch.json','inspection.json','cleanup.json'):
            need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE,
                 'EXACT_FRESH_FLOW_SOURCE_BINDING_REQUIRED:'+name)
        if name in ('launch.json','inspection.json','cleanup.json'):
            need(value.get('helper_package')=='org.droidloom.qa.amazon.r1' and type(HELPER_UID) is int and value.get('helper_uid')==HELPER_UID and value.get('package')=='com.amazon.mShop.android.shopping' and value.get('uid')==10129,
                 'EXACT_AMAZON_HELPER_SCOPE_REQUIRED')
        files[name]={'path':str(path),'bytes':len(raw),'sha256':sha(raw),'text':raw.decode('utf-8','strict')}
    coordinator=json.loads(files['coordinator.json']['text']);stage=json.loads(files['stage.json']['text'])
    if 'coordinator_result' in stage:
        expected_pin=stage['coordinator_result'];observed=files['coordinator.json']
        need(expected_pin=={k:observed[k] for k in ('path','bytes','sha256')},'STAGE_COORDINATOR_LINK_REQUIRED')
    for phase,name,key in (('launch','launch.json','launch_result'),('inspect','inspection.json','inspection_result'),
                           ('cleanup','cleanup.json','cleanup_result')):
        pins=[]
        if key in coordinator:pins.append(coordinator[key])
        if phase in coordinator.get('retained_phase_results',{}):pins.append(coordinator['retained_phase_results'][phase])
        for expected_pin in pins:
            need(name in files,'PINNED_ORIGINAL_PHASE_IS_MISSING:'+phase)
            need(expected_pin=={k:files[name][k] for k in ('path','bytes','sha256')},'COORDINATOR_PHASE_LINK_REQUIRED:'+phase)
    bundle={'schema':1,'scope':'fixed-Amazon-first-search-entry-summary-only','files':files,'missing':missing,
        'source_manifest_sha256':SOURCE_SHA,'flow_nonce':NONCE,'bytes_read':reader.bytes,
        'raw_UI_or_commercial_journal_exported':False,'Android_or_process_actions':0,
        'runtime_qualification_asserted':False,'permission_or_original_file_changes':0}
    raw=(json.dumps(bundle,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw)<=3145728,'SUMMARY_BUNDLE_BOUND')
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
