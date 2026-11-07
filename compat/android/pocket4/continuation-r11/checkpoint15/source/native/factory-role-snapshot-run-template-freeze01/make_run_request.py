#!/usr/bin/env python3
"""Bind a fresh root-only owned snapshot run to a successful actual build. No dispatch."""
from pathlib import Path
import argparse
import ast
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT='/run/pocket4-role-authorized-snapshot-host-run-01-20261105'
KEY='pocket4-role-authorized-snapshot-host-runtime-01-20261105'
SOURCE_MANIFEST='53e90ef34ab51ae8b9700f93419c3c050665fb0ea5a50482417b48aa860497e1'
TEMPLATE_SHA='140f94169b2514d586bde30276c2ca63fced58141330a8ac084e916ddc9c1e5d'
PLAN_SHA='d79fb33dbf54d7082c6bd70a1f1db12b604853482dd1a1c7ee050e65f5143494'
BUILD_ROOT='/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/role-authorized-snapshot-host-build-01-20261105'


def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def write(path,raw):
    if isinstance(raw,str):raw=raw.encode()
    with path.open('xb')as stream:stream.write(raw)
    return pin(raw)


def freeze(build_path,output):
    raw=build_path.read_bytes()
    if len(raw)>262144:raise RuntimeError('actual build receipt exceeds the fixed bound')
    build=json.loads(raw)
    source=(HERE/'run_snapshot.template.py').read_text()
    plan=(HERE/'CASE_PLAN.json').read_bytes()
    if pin(source.encode())['sha256']!=TEMPLATE_SHA or pin(plan)['sha256']!=PLAN_SHA:
        raise RuntimeError('reviewed run template or case plan changed')
    # Reuse the exact pure predicate from the reviewed runner; no staged source,
    # process, root call, or environment operation is invoked by this generator.
    tree=ast.parse(source)
    selected=[node for node in tree.body if isinstance(node,ast.FunctionDef)and
              node.name in ['require','qualified_build']]
    if len(selected)!=2:raise RuntimeError('matching receipt predicate missing')
    scope={'SOURCE_MANIFEST_SHA':SOURCE_MANIFEST}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'frozen_build_predicate','exec'),scope)
    scope['qualified_build'](build)
    elf=build['artifacts']['control']['elf']
    if elf['path']!=BUILD_ROOT+'/build01/snapshot_controls' or not 0<elf['bytes']<=8*1024*1024:
        raise RuntimeError('actual matching control ELF path or size differs')
    if source.count('PENDING_ACTUAL_BUILD_RESULT_SHA256')!=1:
        raise RuntimeError('single actual build binding placeholder required')
    source=source.replace('PENDING_ACTUAL_BUILD_RESULT_SHA256',pin(raw)['sha256']);ast.parse(source)
    files={'run_snapshot.py':source,'actual-build-result.json':raw.decode(),'CASE_PLAN.json':plan.decode()}
    pins={name:pin(text.encode())for name,text in files.items()}
    stage='''import hashlib,json,os,stat
from pathlib import Path
ROOT=Path(%r)
EXPECTED=%r
def main(packet):
    if (os.getuid(),os.geteuid(),os.getgid(),os.getegid())!=(0,0,0,0):
        raise RuntimeError('exact root staging identity required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('runtime packet members differ')
    for name,text in packet.items():
        raw=text.encode()
        if len(raw)!=EXPECTED[name]['bytes']or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('runtime packet pin differs: '+name)
    if ROOT.parent!=Path('/run'):raise RuntimeError('root runtime parent escaped')
    for path in [ROOT.parent,*ROOT.parent.parents]:
        st=path.lstat()
        if not stat.S_ISDIR(st.st_mode)or st.st_uid!=0 or st.st_gid!=0 or stat.S_IMODE(st.st_mode)&0o022:
            raise RuntimeError('root runtime ancestor is not private against nonroot writers')
    parent=os.open(ROOT.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(parent);named=ROOT.parent.lstat()
        if (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino):raise RuntimeError('root parent alias changed')
        os.umask(0o077);os.mkdir(ROOT.name,mode=0o700,dir_fd=parent)
        source=ROOT/'control-source';source.mkdir(mode=0o700)
        for name,text in packet.items():
            if '/'in name or name in ['.','..']:raise RuntimeError('flat runtime packet required')
            fd=os.open(source/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            with os.fdopen(fd,'wb')as stream:
                stream.write(text.encode());stream.flush();os.fsync(stream.fileno())
        after=os.fstat(parent);named=ROOT.parent.lstat()
        if (before.st_dev,before.st_ino,before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode))!=\
           (after.st_dev,after.st_ino,after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode))or\
           (after.st_dev,after.st_ino)!=(named.st_dev,named.st_ino):
            raise RuntimeError('root parent changed during create-only staging')
    finally:os.close(parent)
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'run_snapshot.py'),'--execute-once'],
              {'PATH':'/usr/bin:/bin','HOME':'/root','LANG':'C','LC_ALL':'C'})
'''%(ROOT,pins)
    entry=stage+'\nPACKET=json.loads('+repr(json.dumps(files,sort_keys=True))+')\nmain(PACKET)\n'
    ast.parse(entry)
    if len(entry.encode())>1024*1024:raise RuntimeError('runtime stdin exceeds process_start bound')
    request={'host':'pocket4','executable':'/usr/bin/sudo','args':['-n','/usr/bin/python3','-I','-B','-'],
             'stdin':entry,'cwd':'/','cpu_quota_percent':50,'memory_max_bytes':268435456,'nice':15,
             'timeout_seconds':120,'idempotency_key':KEY}
    output.mkdir();rows={}
    for name,text in files.items():rows[name]=write(output/name,text)
    rows['stage.py']=write(output/'stage.py',stage)
    rows['exact-request.json']=write(output/'exact-request.json',json.dumps(request,indent=2)+'\n')
    write(output/'SOURCE_PINS.json',json.dumps({'schema':1,'files':rows,'packet_files':pins,
          'state':'FROZEN_REQUIRES_ROOT_ACTUAL_ELF_ADMISSION','actual_build_sha256':pin(raw)['sha256'],
          'actual_elf':elf,'factory_service_started':False,'platform_policy_qualified':False,
          'Main_actions':0},indent=2)+'\n')
    print(json.dumps({'request':rows['exact-request.json'],'stable_key':KEY,
                      'actual_build_sha256':pin(raw)['sha256'],'stdin_bytes':len(entry.encode())},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--actual-build-result',type=Path)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.actual_build_result is None and args.output is None:
        print(json.dumps({'state':'PLAN_ONLY','requires_qualified_actual_build':True,
                          'requires_actual_ELF_root_review':True,'remote_actions':0}))
    elif args.actual_build_result is None or args.output is None:
        parser.error('both actual build receipt and fresh output are required')
    else:freeze(args.actual_build_result,args.output)
