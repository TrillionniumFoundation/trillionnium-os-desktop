#!/usr/bin/env python3
"""Create a matching host compile packet from the already frozen recovery03 sources."""
from pathlib import Path
import argparse
import ast
import hashlib
import json

HERE=Path(__file__).resolve().parent
CORE=HERE.parent/'nofile-owner-host-recovery-03'
ROOT='/home/alex/work/pocket4-nofile-owner-recovery03-host-build-01-20261105'
KEY='pocket4-nofile-owner-recovery03-host-build-01-20261105'
CORE_MANIFEST='baa504625fc51619824ef3023738b8b589008b9ef024fffdf6707ff726628aa3'
CONTROLLER='b0f8e1ae55dea80ae4091769ba1216161dc8250dbace784502a98dcd22974eff'

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def write(path,raw):
    if isinstance(raw,str):raw=raw.encode()
    with path.open('xb') as stream:stream.write(raw)
    return pin(raw)

def freeze(output):
    raw=(CORE/'SOURCE_PINS.json').read_bytes()
    if pin(raw)['sha256']!=CORE_MANIFEST:raise RuntimeError('reviewed source manifest changed')
    frozen={x['path']:x for x in json.loads(raw)['files']}
    expected=json.loads((HERE/'source-inputs.json').read_text())
    files={'recovery03-source-pins.json':raw.decode()}
    if len(expected)!=16:raise RuntimeError('exact source subset required')
    for name,row in expected.items():
        raw=(CORE/name).read_bytes()
        if pin(raw)!=row or any(frozen[name][k]!=row[k] for k in ['bytes','sha256']):
            raise RuntimeError('frozen source differs: '+name)
        files[name]=raw.decode()
    controller=(HERE/'build_nofile.py').read_bytes()
    if pin(controller)['sha256']!=CONTROLLER:raise RuntimeError('reviewed build controller changed')
    files['build_nofile.py']=controller.decode()
    pins={name:pin(text.encode()) for name,text in files.items()}
    stage='''import hashlib,json,os,stat
from pathlib import Path
ROOT=Path(%r)
EXPECTED=%r
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('source packet member set differs')
    for name,text in packet.items():
        raw=text.encode()
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('frozen packet pin mismatch: '+name)
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned root parent aliases directory')
    os.umask(0o077);ROOT.mkdir(mode=0o700);source=ROOT/'source';source.mkdir(mode=0o700)
    for name,text in packet.items():
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True)
        for parent in [path.parent,*path.parent.parents]:
            if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('source parent aliases directory')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode());stream.flush();os.fsync(stream.fileno())
    receipt=(json.dumps({'schema':1,'files':EXPECTED,'Main_actions':0,'positive_26_execution':False},indent=2)+'\\n').encode()
    fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:
        stream.write(receipt);stream.flush();os.fsync(stream.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'build_nofile.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
'''%(ROOT,pins)
    entry=stage+'\nPACKET=json.loads('+repr(json.dumps(files,sort_keys=True))+')\nmain(PACKET)\n'
    ast.parse(entry)
    if len(entry.encode())>1024*1024:raise RuntimeError('source packet exceeds runtime limit')
    request={'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-B','-'],'stdin':entry,'cwd':'/',
             'cpu_quota_percent':100,'memory_max_bytes':536870912,'nice':15,'timeout_seconds':300,'idempotency_key':KEY}
    output.mkdir()
    recorded={}
    for name,text in files.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);recorded[name]=write(path,text)
    recorded['stage.py']=write(output/'stage.py',stage)
    recorded['exact-request.json']=write(output/'exact-request.json',json.dumps(request,indent=2)+'\n')
    write(output/'SOURCE_PINS.json',json.dumps({'schema':1,'packet_files':pins,'files':recorded,'state':'FROZEN_NOT_DISPATCHED'},indent=2)+'\n')
    print(json.dumps({'request':recorded['exact-request.json'],'packet_count':len(files),'stable_key':KEY},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',type=Path)
    args=parser.parse_args()
    if args.freeze:freeze(args.freeze)
    else:print(json.dumps({'mode':'PLAN','positive_26_execution':False,'remote_actions':0,'requires_actual_build_before_runtime':True}))
