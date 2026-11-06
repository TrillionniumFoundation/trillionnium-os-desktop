#!/usr/bin/env python3
"""Fixed summary-only reader for the parent-bound Ticket01 launch phase and two exact terminal parents."""
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

ROOT=Path('/home/alex/work/pocket4-ticket-owned-launch-inspect-01')
FLOW=Path('/home/alex/work/pocket4-ticket-owned-qa-r1-flow-c398efeb8c07781670825f5ad68e13af')
NONCE='c398efeb8c07781670825f5ad68e13af'
SOURCE_SHA='16f371bda457b830b11536f977a11f8dcce3347eded286605400a9162ba079a8'
HELPER_UID=10190
FILES={
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'launch.json':FLOW/'steps/launch-01/result.json',
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
        maximum=262144
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
    sizes={'coordinator.json':5828,'stage.json':1804}
    reader=Reader();files={};missing=[];values={}
    for name in ('coordinator.json','stage.json'):
        path=FILES[name];raw=reader.read(path)
        need(sha(raw)==expected[name] and len(raw)==sizes[name],
             'EXTERNAL_TERMINAL_BYTES_CHANGED:'+name)
        value=json.loads(raw);no_raw_ui(value)
        need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE and
             value.get('package')=='com.MobileTicket','EXACT_FRESH_FLOW_SOURCE_BINDING_REQUIRED:'+name)
        values[name]=value
        files[name]={'path':str(path),'bytes':len(raw),'sha256':sha(raw),'text':raw.decode('utf-8','strict')}
    coordinator=values['coordinator.json'];stage=values['stage.json']
    if 'coordinator_result' in stage:
        observed=files['coordinator.json']
        need(stage['coordinator_result']=={k:observed[k] for k in ('path','bytes','sha256')},
             'STAGE_COORDINATOR_LINK_REQUIRED')
    retained=coordinator.get('retained_phase_results')
    need(type(retained) is dict,'RETAINED_PHASE_RESULT_MAP_REQUIRED')
    if 'launch' not in retained:
        need('launch_result' not in coordinator,'UNBOUND_SUCCESSFUL_LAUNCH_RESULT')
        missing.append({'name':'launch.json','path':str(FILES['launch.json']),
                        'reason':'exact pinned coordinator did not bind a retained launch result',
                        'file_open_attempted':False})
    else:
        pin=retained['launch'];path=FILES['launch.json']
        need(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==str(path) and
             type(pin['bytes']) is int and 0<pin['bytes']<=262144 and
             isinstance(pin['sha256'],str) and re.fullmatch('[0-9a-f]{64}',pin['sha256']),
             'ONLY_EXACT_PARENT_BOUND_LAUNCH_PATH_AND_BOUNDED_PIN')
        if 'launch_result' in coordinator:
            need(coordinator['launch_result']==pin,'TWO_PARENT_LAUNCH_PINS_DIFFER')
        raw=reader.read(path)
        need(len(raw)==pin['bytes'] and sha(raw)==pin['sha256'],'PARENT_BOUND_LAUNCH_BYTES_CHANGED')
        value=json.loads(raw);no_raw_ui(value)
        need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE and
             value.get('phase')=='launch' and value.get('helper_package')=='org.droidloom.qa.ticket.r1' and
             value.get('helper_uid')==HELPER_UID and value.get('package')=='com.MobileTicket' and
             value.get('uid')==10121,'EXACT_TICKET_LAUNCH_SCOPE_REQUIRED')
        files['launch.json']={'path':str(path),'bytes':len(raw),'sha256':sha(raw),'text':raw.decode('utf-8','strict')}
    bundle={'schema':1,'scope':'fixed-Ticket01-terminal-parents-and-only-parent-bound-launch-result','files':files,'missing':missing,
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
