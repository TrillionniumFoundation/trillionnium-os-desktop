#!/usr/bin/env python3
"""New exact metadata-only source/input stage; no native or Android commands."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = '/home/alex/work/pocket4-retention-metadata-source-20261106-r1'
FILES = [{'name': 'owned_readonly_lifetime.py', 'bytes': 16153, 'sha256': '64c15bcb4a7fe6f1d761c05f63c67a4d52d9dcedcb34a39e48865eccdad3bdfe'}, {'name': 'observe_retention.py', 'bytes': 37600, 'sha256': '1673b0d312de29889a931c9120e8c46e77f5010d76ba46510089f9dd397bf6bc'}, {'name': 'request.review-only.json', 'bytes': 738, 'sha256': '9fef67d494ac6e89f64b2c1c42b8f1d6f39a0194534ecc8dff00cab3aa253dce'}, {'name': 'scope.review-only.json', 'bytes': 125632, 'sha256': '779a0319e956c940c720cdeefa0b0c0456bdbc3fada32de9c9441032f9fec70d'}]
STAT_KEYS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def need(value,code):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def read_file(parent,name,size,digest,owned_mode=None):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1 and
             before.st_size==size and (owned_mode is None or stat.S_IMODE(before.st_mode)==owned_mode),'PINNED_ROOT_FILE')
        body=bytearray()
        while len(body)<=size:
            part=os.read(fd,min(65536,size+1-len(body)))
            if not part:break
            body.extend(part)
        again=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        try:
            need(len(body)==size and sha(body)==digest and
                 all(getattr(before,k)==getattr(os.fstat(fd),k)==getattr(os.fstat(again),k) for k in STAT_KEYS),'FILE_OR_PATH_CHANGED')
        finally:os.close(again)
        return bytes(body)
    finally:os.close(fd)

def read_host_pin(pin):
    path=pin['path'];parts=path[1:].split('/')
    need(path.startswith('/') and all(x not in ('','.','..') for x in parts),'CANONICAL_PIN_PATH')
    fds=[]
    try:
        parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(parent)
        for name in parts[:-1]:
            parent=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(parent)
        return read_file(parent,parts[-1],pin['bytes'],pin['sha256'])
    finally:
        errors=[]
        for fd in reversed(fds):
            try:os.close(fd)
            except OSError:errors.append(fd)
        need(not errors,'PIN_READER_FDS_NOT_CLOSED')

def write_new(directory,name,data):
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600,dir_fd=directory)
    try:
        view=memoryview(data)
        while view:
            count=os.write(fd,view);need(count>0,'WRITE_PROGRESS');view=view[count:]
        os.fchmod(fd,0o400);os.fsync(fd)
    finally:os.close(fd)
    os.fsync(directory)

def main():
    need(os.getuid()==os.geteuid()==0,'ACTUAL_EXISTING_HOST_ROOT_REQUIRED')
    os.umask(0o077);before_fds=len(os.listdir('/proc/self/fd'))
    raw=sys.stdin.buffer.read(193301);need(len(raw)==193300,'BOUNDED_EXACT_INPUT')
    payload=json.loads(raw)
    need(set(payload)=={'schema','files'} and payload['schema']=='pocket4-retention-metadata-source-stage-v1','CLOSED_STAGE_PAYLOAD')
    need(type(payload['files']) is list and len(payload['files'])==len(FILES),'EXACT_FILE_COUNT')
    inputs=[]
    for expected,item in zip(FILES,payload['files']):
        need(set(item)=={'name','text'} and item['name']==expected['name'],'EXACT_INPUT_NAME')
        body=item['text'].encode('utf-8')
        need(len(body)==expected['bytes'] and sha(body)==expected['sha256'],'EXACT_INPUT_BYTES')
        inputs.append((expected,body))
    fds=[]
    try:
        parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(parent)
        for name in ('home','alex','work'):
            parent=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(parent)
        leaf=Path(ROOT).name
        os.mkdir(leaf,0o700,dir_fd=parent);os.fsync(parent)
        directory=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(directory)
        identity=os.fstat(directory)
        need(identity.st_uid==0 and stat.S_IMODE(identity.st_mode)==0o700,'NEW_ROOT_PRIVATE_STAGE')
        os.mkdir('inputs',0o700,dir_fd=directory);os.fsync(directory)
        child=os.open('inputs',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory);fds.append(child)
        need(os.fstat(child).st_uid==0 and stat.S_IMODE(os.fstat(child).st_mode)==0o700,'NEW_ROOT_PRIVATE_INPUTS')
        for item,body in inputs:
            pieces=item['name'].split('/')
            target=directory if len(pieces)==1 else child
            need(len(pieces)==1 or len(pieces)==2 and pieces[0]=='inputs','FIXED_NEW_SUBDIRECTORY')
            write_new(target,pieces[-1],body)
            need(read_file(target,pieces[-1],item['bytes'],item['sha256'],0o400)==body,'EXACT_NEW_FILE_READBACK')
        current=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(current)
        need(all(getattr(identity,k)==getattr(os.fstat(current),k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid')),'STAGE_DIRECTORY_CHANGED')
        for item,body in inputs:
            need(read_host_pin({'path':ROOT+'/'+item['name'],'bytes':item['bytes'],'sha256':item['sha256']})==body,'FULL_NEW_PATH_READBACK')
    finally:
        errors=[]
        for fd in reversed(fds):
            try:os.close(fd)
            except OSError:errors.append(fd)
        need(not errors,'STAGE_FDS_NOT_CLOSED')
    after_fds=len(os.listdir('/proc/self/fd'));need(after_fds==before_fds,'STAGE_DESCRIPTOR_DIFFERENCE')
    print(canonical({'schema':'pocket4-retention-metadata-source-stage-result-v1','source_stage_ok':True,'source_root':ROOT,'files':FILES,
         'bootstrap_FDs_before':before_fds,'bootstrap_FDs_after':after_fds,'worker_about_to_exec_once':True,
         'stage_Main_reads':0,'stage_namespace_entries':0,'stage_installs':0,'stage_UI_actions':0,'automatic_retry':False}).decode(),flush=True)
    wrapper=FILES[0]
    os.execv('/usr/bin/python3',['/usr/bin/python3','-I','-B',ROOT+'/owned_readonly_lifetime.py',
                              '--execute-observation','--source-sha256',wrapper['sha256'],'--source-bytes',str(wrapper['bytes'])])

if __name__=='__main__':main()
