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

ROOT=Path('/home/alex/work/pocket4-bilibili-r2-search-entry-01')
FLOW=Path('/home/alex/work/pocket4-bilibili-owned-qa-r2-flow-69b2d59b9d416e3d6c082a3610b45b63')
STEP=FLOW/'steps/search-entry-01'
FLOW_NONCE='69b2d59b9d416e3d6c082a3610b45b63'
SOURCE_SHA='79498046a8ea1e38ebfdaa99a94eb4523f1101b2cb08218f8c9eb7e090deeb86'
TERMINAL={
 'coordinator.json':(ROOT/'result.json',6327,'a681a0dd988e97fe8b8923985f5ebcb364e2ff23a6e536269b0d6c1fbce185d2'),
 'stage.json':(ROOT/'stage-result.json',1768,'c573c78dc96e8c4978678a608034f329c1b8783fd5798e494cf3733a71030e7b')}
NONCES={
 'before':'7f379363fab11375e075a03c842960ec',
 'inspect':'d09eae3f89850fa2ae08d7ff7397ba43',
 'action':'32275761f7cd00ae05a885f2732cc184',
 'after':'c9f88106b407b46ccb93ea594eb148b7',
 'post_before':'a84bcca86eceb025d3f1ac6a7b966997',
 'post_inspect':'24dae2a7972bcaacd44990d9b3a9112d',
 'post_after':'ce95537f902655940e154edf325623c6'}
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
        0<=first.st_size<=524288,'ROOT_PRIVATE_SINGLE_REGULAR_BOUND')
   chunks=[];count=0
   while True:
    need(time.monotonic()-self.started<8,'PRIVATE_READ_DEADLINE')
    part=os.read(fd,min(16384,524289-count))
    if not part:break
    chunks.append(part);count+=len(part);self.bytes+=len(part)
    need(count<=524288 and self.bytes<=3145728,'PRIVATE_TOTAL_READ_BOUND')
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
