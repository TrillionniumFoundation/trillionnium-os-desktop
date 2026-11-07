#!/usr/bin/env python3
"""Freeze only a matching compile request; never dispatch or run a role grant."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
CORE=HERE.parent/'factory-role-auth-positive-source-freeze02'
ROOT='/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/role-authorization-positive-host-build-02-20261105'
KEY='pocket4-role-authorization-positive-host-build-02-20261105'
MANIFEST_SHA='fda076982c0a26682eb3b6a596a6964e6645cf1eddc7b175e56d9b499c06fda2'
CONTROLLER_SHA='0dfeafc0dea6037ec189fb73ab9d6d268f55dc84691390f9dd8121c6ef17ebee'

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def write(path,data):
    if isinstance(data,str):data=data.encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb')as stream:stream.write(data)
    return pin(data)

def freeze(output):
    raw=(CORE/'SOURCE_PINS.json').read_bytes()
    if pin(raw)['sha256']!=MANIFEST_SHA:raise RuntimeError('immutable source authority differs')
    authority={row['path']:row for row in json.loads(raw)['files']}
    expected=json.loads((HERE/'source-inputs.json').read_text())
    if len(expected)!=5:raise RuntimeError('exact five source inputs required')
    files={'role-source-pins.json':raw.decode()}
    for name,row in expected.items():
        data=(CORE/name).read_bytes()
        if pin(data)!=row or any(authority[name][key]!=row[key]for key in ['bytes','sha256']):
            raise RuntimeError('frozen input differs: '+name)
        files[name]=data.decode()
    controller=(HERE/'build_registry.py').read_bytes()
    if pin(controller)['sha256']!=CONTROLLER_SHA:raise RuntimeError('matching controller differs')
    files['build_registry.py']=controller.decode()
    pins={name:pin(text.encode())for name,text in files.items()}
    stage='''import hashlib,json,os,stat
from pathlib import Path
ROOT=Path(%r)
EXPECTED=%r
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('packet members differ')
    for name,text in packet.items():
        raw=text.encode()
        if len(raw)!=EXPECTED[name]['bytes']or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('frozen packet differs: '+name)
    for path in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(path.lstat().st_mode):raise RuntimeError('parent directory alias')
    parent=os.open(ROOT.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(parent);named=ROOT.parent.lstat()
        if (before.st_dev,before.st_ino,before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode))!=(66306,34351895,1000,1000,0o700):
            raise RuntimeError('known private source parent identity differs')
        if (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino):raise RuntimeError('parent alias changed')
        os.umask(0o077);os.mkdir(ROOT.name,mode=0o700,dir_fd=parent)
        source=ROOT/'source';source.mkdir(mode=0o700)
        for name,text in packet.items():
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True)
            for directory in [path.parent,*path.parent.parents]:
                if not stat.S_ISDIR(directory.lstat().st_mode):raise RuntimeError('source parent alias')
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            with os.fdopen(fd,'wb')as stream:
                stream.write(text.encode());stream.flush();os.fsync(stream.fileno())
        receipt=(json.dumps({'schema':1,'files':EXPECTED,'registry_positive_executed':False,'Main_actions':0},indent=2)+'\\n').encode()
        fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb')as stream:
            stream.write(receipt);stream.flush();os.fsync(stream.fileno())
        after=os.fstat(parent);named=ROOT.parent.lstat()
        if (after.st_dev,after.st_ino,after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode))!=(66306,34351895,1000,1000,0o700)or (after.st_dev,after.st_ino)!=(named.st_dev,named.st_ino):
            raise RuntimeError('private parent changed during create-only staging')
    finally:os.close(parent)
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'build_registry.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
'''%(ROOT,pins)
    entry=stage+'\nPACKET=json.loads('+repr(json.dumps(files,sort_keys=True))+')\nmain(PACKET)\n'
    ast.parse(entry)
    if len(entry.encode())>1024*1024:raise RuntimeError('stdin exceeds process_start bound')
    request={'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-B','-'],'stdin':entry,'cwd':'/',
             'cpu_quota_percent':100,'memory_max_bytes':536870912,'nice':15,'timeout_seconds':240,
             'idempotency_key':KEY}
    output.mkdir()
    recorded={}
    for name,text in files.items():recorded[name]=write(output/name,text)
    recorded['stage.py']=write(output/'stage.py',stage)
    recorded['exact-request.json']=write(output/'exact-request.json',json.dumps(request,indent=2)+'\n')
    write(output/'SOURCE_PINS.json',json.dumps({'schema':1,'packet_files':pins,'files':recorded,
                                             'state':'FROZEN_NOT_DISPATCHED'},indent=2)+'\n')
    print(json.dumps({'request':recorded['exact-request.json'],'packet_count':len(files),
                      'stdin_bytes':len(entry.encode()),'stable_key':KEY}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',type=Path)
    args=parser.parse_args()
    if args.freeze:freeze(args.freeze)
    else:print(json.dumps({'state':'PLAN_ONLY','registry_positive_executed':False,'remote_actions':0}))
