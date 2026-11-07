#!/usr/bin/env python3
"""Bind the already reviewed runner to the actual matching build receipt."""
from pathlib import Path
import argparse
import ast
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT='/home/alex/work/pocket4-nofile-owner-recovery03-host-run-01-20261105'
KEY='pocket4-nofile-owner-recovery03-host-positive-26-control-01-20261105'
SOURCE_MANIFEST='baa504625fc51619824ef3023738b8b589008b9ef024fffdf6707ff726628aa3'

def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def write(path,raw):
    if isinstance(raw,str):raw=raw.encode()
    with path.open('xb') as stream:stream.write(raw)
    return pin(raw)

def freeze(build_path,output):
    raw=build_path.read_bytes();build=json.loads(raw)
    if not(build['state']=='PASS' and build['source_manifest_sha256']==SOURCE_MANIFEST and
           build['source_unchanged_after'] is True and build['ELF_unchanged_after'] is True and
           not build['tool_changes'] and not build['dependency_changes'] and build['owned_resource_gate']['pass'] is True and
           not build['cleanup']['forced_cleanup'] and not build['cleanup']['remaining'] and not build['cleanup']['errors'] and
           build['positive_26_execution'] is False and set(build['artifacts'])=={'candidate','preimage'}):
        raise RuntimeError('complete qualified actual matching build receipt required')
    source=(HERE/'run_nofile.template.py').read_text()
    if pin(source.encode())['sha256']!='c638a60e9839d391cd4a0b944c593bf56b86ebcb9e11720c2f2388ac07292cf5':
        raise RuntimeError('reviewed runtime template changed')
    if pin((HERE/'CASE_PLAN.json').read_bytes())['sha256']!='5ad4e7985eee2d1c9a7dd1322a2c933e74d734a5c98a37d4bb0c5b88e101ee09':
        raise RuntimeError('reviewed 26-case plan changed')
    if source.count('PENDING_ACTUAL_BUILD_RESULT_SHA256')!=1:raise RuntimeError('template binding differs')
    source=source.replace('PENDING_ACTUAL_BUILD_RESULT_SHA256',pin(raw)['sha256']);ast.parse(source)
    files={'run_nofile.py':source,'actual-build-result.json':raw.decode(),'CASE_PLAN.json':(HERE/'CASE_PLAN.json').read_text()}
    pins={name:pin(text.encode()) for name,text in files.items()}
    stage='''import hashlib,json,os,stat
from pathlib import Path
ROOT=Path(%r)
EXPECTED=%r
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('ordinary operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('runtime packet member set differs')
    for name,text in packet.items():
        raw=text.encode()
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('runtime packet pin differs: '+name)
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned runtime root parent aliases directory')
    os.umask(0o077);ROOT.mkdir(mode=0o700);source=ROOT/'control-source';source.mkdir(mode=0o700)
    for name,text in packet.items():
        fd=os.open(source/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode());stream.flush();os.fsync(stream.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'run_nofile.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
'''%(ROOT,pins)
    entry=stage+'\nPACKET=json.loads('+repr(json.dumps(files,sort_keys=True))+')\nmain(PACKET)\n';ast.parse(entry)
    if len(entry.encode())>1024*1024:raise RuntimeError('runtime input exceeds bound')
    request={'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-B','-'],'stdin':entry,'cwd':'/',
             'cpu_quota_percent':50,'memory_max_bytes':268435456,'nice':15,'timeout_seconds':300,'idempotency_key':KEY}
    output.mkdir();rows={}
    for name,text in files.items():rows[name]=write(output/name,text)
    rows['stage.py']=write(output/'stage.py',stage)
    rows['exact-request.json']=write(output/'exact-request.json',json.dumps(request,indent=2)+'\n')
    write(output/'SOURCE_PINS.json',json.dumps({'schema':1,'files':rows,'packet_files':pins,
          'state':'FROZEN_REQUIRES_ROOT_ACTUAL_ELF_ADMISSION','actual_build_sha256':pin(raw)['sha256']},indent=2)+'\n')
    print(json.dumps({'request':rows['exact-request.json'],'stable_key':KEY,'actual_build_sha256':pin(raw)['sha256']},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--actual-build-result',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.actual_build_result is None and args.output is None:
        print(json.dumps({'mode':'PLAN','requires_qualified_matching_build':True,'requires_actual_ELF_root_review':True,'remote_actions':0}))
    elif args.actual_build_result is None or args.output is None:parser.error('both receipt and new output are required')
    else:freeze(args.actual_build_result,args.output)
