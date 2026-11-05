#!/usr/bin/env python3
"""Fixed PRIVATE failed-search diagnostics; no commands or directory scan.

Runtime output may contain commercial UI. Never publish or commit its body.
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import time

ROOT=Path('/home/alex/work/pocket4-bilibili-r3-search-entry-01')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r3-flow-a53815018fc65e6cbcac07538bdd7c7d')
STEP=FLOW/'steps/search-entry-01'
FLOW_NONCE='a53815018fc65e6cbcac07538bdd7c7d'
SOURCE_SHA='383b699100f3f7529b8e8ffc95554e955ee6a50b8f89a1647f2c2c1602abe131'
TERMINAL={
 'coordinator.json':(ROOT/'result.json',6327,'324a5d5e181be451748d3c2079ba86f306ee55658c6bc122fe400d72a84462e8'),
 'stage.json':(ROOT/'stage-result.json',1768,'90909e2429c7e1ec34e5eff1b3d4c6591f6e0a3e6f1e79ce10bdd9636a1aff62')}
NONCES={
 'before':'dc23f1f57cd8a8ee80c2716bca79f3ab',
 'inspect':'12f173af30cad43d067140ee40f0a4b4',
 'action':'246e02a25a3b85775a3c4f0cd691e719',
 'after':'6f7c8b80f94b51a01792bc22b4ca9ca8',
 'post_before':'89b5b4ed5dbdcc409554079f4b0ce86b',
 'post_inspect':'313bcbf4c643b9a1a1f844c181caa78e',
 'post_after':'57e6e78c397b74f943a487821002d8cd'}
FILES={name:row[0] for name,row in TERMINAL.items()}
FILES.update({'navigation.json':STEP/'result.json',
 'worker-command-result.json':ROOT/'evidence/03-navigate.result.json',
 'worker.stdout':ROOT/'evidence/03-navigate.stdout',
 'worker.stderr':ROOT/'evidence/03-navigate.stderr'})
for name,nonce in NONCES.items():
 for suffix in ('request.json','assessment.json','failed-assessment.json'):
  FILES[name+'.'+suffix]=STEP/(nonce+'.'+suffix)


def need(value,reason):
 if not value:raise RuntimeError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()


class Reader:
 def __init__(self):self.started=time.monotonic();self.bytes=0
 def read(self,path,optional):
  need(path in FILES.values(),'FIXED_PRIVATE_ALLOWLIST_REQUIRED')
  current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
  try:
   try:
    for name in path.parts[1:-1]:
     nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
     os.close(current);current=nxt
    fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
   except FileNotFoundError:
    if optional:return None
    raise
   first=os.fstat(fd)
   need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
        0<=first.st_size<=1048576,'ROOT_PRIVATE_SINGLE_REGULAR_BOUND')
   chunks=[];count=0
   while True:
    need(time.monotonic()-self.started<8,'PRIVATE_READ_DEADLINE')
    part=os.read(fd,min(16384,1048577-count))
    if not part:break
    chunks.append(part);count+=len(part);self.bytes+=len(part)
    need(count<=1048576 and self.bytes<=3145728,'PRIVATE_TOTAL_READ_BOUND')
   last=os.fstat(fd)
   keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
   need(count==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),'PRIVATE_FILE_CHANGED')
   return b''.join(chunks)
  finally:
   if fd is not None:os.close(fd)
   os.close(current)


def collect():
 need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
 reader=Reader();files={};missing=[]
 for name,path in FILES.items():
  raw=reader.read(path,name not in TERMINAL)
  if raw is None:
   missing.append({'name':name,'path':str(path)});continue
  if name in TERMINAL:
   _,size,pin=TERMINAL[name]
   need(len(raw)==size and sha(raw)==pin,'EXTERNAL_ORIGINAL_FAILED_TERMINAL_CHANGED')
   value=json.loads(raw)
   need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==FLOW_NONCE and
        value.get('ok') is False,'EXACT_ORIGINAL_FAILED_FLOW_REQUIRED')
  files[name]={'path':str(path),'bytes':len(raw),'sha256':sha(raw),'text':raw.decode('utf-8','strict')}
 payload={'schema':1,'privacy':'PRIVATE_COMMERCIAL_UI_DO_NOT_PUBLISH_OR_COMMIT',
  'files':files,'missing':missing,'bytes_read':reader.bytes,'scope':'original failed search-entry diagnostics only',
  'original_failure_preserved':True,'runtime_qualification_asserted':False,
  'Android_or_process_actions':0,'writes':0,'directory_scans':0,'whole_app_ready':False}
 raw=(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
 need(len(raw)<=4194304,'PRIVATE_DIAGNOSTIC_BUNDLE_BOUND')
 zipped=gzip.compress(raw,mtime=0)
 print(json.dumps({'schema':1,'encoding':'gzip-base64','private_UI_data':True,'must_not_enter_Git':True,
  'uncompressed_bytes':len(raw),'uncompressed_sha256':sha(raw),'compressed_bytes':len(zipped),
  'compressed_sha256':sha(zipped),'data':base64.b64encode(zipped).decode('ascii')},sort_keys=True),flush=True)
 return 0


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collect-once',action='store_true');a=p.parse_args(argv)
 if not a.collect_once:
  print(json.dumps({'state':'PLAN_ONLY','files':{k:str(v) for k,v in FILES.items()},'private_runtime_output_forbidden_in_Git':True,'remote_actions':0}))
  return 0
 return collect()

if __name__=='__main__':raise SystemExit(main())
