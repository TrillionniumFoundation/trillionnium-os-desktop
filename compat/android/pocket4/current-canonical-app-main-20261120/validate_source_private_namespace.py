"""Inspect the exact canonical source paths inside an owned private mount NS.

This is a host source control, not an Android runtime, release adopter, or
qualification writer. Only the already pinned source-inspection entrypoints
and two wrong-preparation-pin refusals may run. No Main or app action is used.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

CANON=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1')
EXPECTED_CURRENT='091f53bb8ad9623c9825c5e94a91e7226157ba90205fa1bddf06eb362aa0875b'
CURRENT=Path('/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json')

def need(ok,why):
    if not ok:raise RuntimeError(why)

def pin(path,raw):
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def read(path,maximum=2*1024*1024,minimum=1):
    path=Path(path);need(path.is_absolute() and path.resolve()==path,'EXACT_SOURCE_INPUT_PATH')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd);fields=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and minimum<=before.st_size<=maximum,'BOUNDED_SOURCE_FILE')
        raw=bytearray()
        while len(raw)<=maximum:
            block=os.read(fd,min(65536,maximum+1-len(raw)))
            if not block:break
            raw.extend(block)
        need(len(raw)==before.st_size and all(getattr(before,k)==getattr(os.fstat(fd),k)==getattr(path.lstat(),k) for k in fields),
             'SOURCE_INPUT_CHANGED')
        return bytes(raw)
    finally:os.close(fd)

def module(reference,name):
    raw=read(reference['path']);need(pin(reference['path'],raw)==reference,'EXACT_SOURCE_MODULE_PIN')
    value=types.ModuleType(name);value.__file__=reference['path']
    exec(compile(raw,reference['path'],'exec'),value.__dict__);return value

def mount(source,target,kind,flags,data):
    libc=ctypes.CDLL(None,use_errno=True)
    libc.mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_char_p]
    libc.mount.restype=ctypes.c_int
    encoded=lambda value:None if value is None else os.fsencode(value)
    if libc.mount(encoded(source),encoded(target),encoded(kind),flags,encoded(data))!=0:
        raise OSError(ctypes.get_errno(),'private source control mount failed')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',required=True);parser.add_argument('--expect-manifest-sha256',required=True)
    parser.add_argument('--original-mount-inode',required=True,type=int)
    args=parser.parse_args()
    stage=Path(args.stage)
    need(os.getuid()==os.geteuid()==0 and stage.parent==Path('/home/alex/work') and
         re.fullmatch('p4-canonical-source-validation-20261120-3b9d-r[1-9][0-9]*',stage.name),
         'EXACT_CREATE_ONLY_SOURCE_CONTROL_STAGE')
    private_ns=os.stat('/proc/self/ns/mnt').st_ino
    need(private_ns!=args.original_mount_inode and
         os.stat('/proc/'+str(os.getppid())+'/ns/mnt').st_ino==args.original_mount_inode,
         'ACTUAL_OWNED_PRIVATE_MOUNT_NAMESPACE_REQUIRED')
    manifest_raw=read(stage/'BUNDLE-MANIFEST.json',4*1024*1024)
    need(hashlib.sha256(manifest_raw).hexdigest()==args.expect_manifest_sha256,'EXTERNAL_BUNDLE_PIN_CHANGED')
    manifest=json.loads(manifest_raw);need(manifest['runtime_qualified'] is False,'SOURCE_ONLY_MANIFEST')
    original_current=read(CURRENT)
    need(hashlib.sha256(original_current).hexdigest()==EXPECTED_CURRENT,'ORIGINAL_CURRENT_PREIMAGE_CHANGED')
    # unshare already made the namespace private. Reassert recursively before
    # replacing only this actor's /usr/libexec view; no host path is created.
    mount(None,'/',None,(1<<18)|(1<<14),None)
    mount('tmpfs','/usr/libexec','tmpfs',2|4|8,'size=16777216,mode=0755')
    CANON.mkdir(mode=0o755,parents=True)
    mount(str(stage/'bundle'),str(CANON),None,4096,None)
    mount(None,str(CANON),None,4096|32|1|2|4|8,None)
    by_path={row['path']:row for row in manifest['files']}
    need(len(by_path)==len(manifest['files']),'UNIQUE_COMPLETE_SOURCE_GRAPH')
    def source_guard(*,action_attempted=False):
        need(action_attempted is False,'SOURCE_CONTROL_CANNOT_ADMIT_ANDROID_MUTATION')
        need(os.stat('/proc/self/ns/mnt').st_ino==private_ns,'PRIVATE_MOUNT_NAMESPACE_CHANGED')
        need(read(stage/'BUNDLE-MANIFEST.json',4*1024*1024)==manifest_raw,'SOURCE_GRAPH_MANIFEST_CHANGED')
        for ref in manifest['files']:
            need(Path(ref['path']).is_relative_to(CANON),'SOURCE_GRAPH_ESCAPED_CANONICAL_ROOT')
            # Historical byte-pinned empty stdout/stderr receipts are valid
            # graph inputs, although source modules themselves must be nonempty.
            body=read(ref['path'],minimum=0 if ref['bytes']==0 else 1)
            need(pin(ref['path'],body)==ref,'WHOLE_SOURCE_GRAPH_CHANGED')
        return {'bundle_sha256':args.expect_manifest_sha256,'private_mount_inode':private_ns}
    source_guard()
    catalog=json.loads(read(CANON/'selection/leaf_sources.json'))
    need(len(catalog)==14 and [x['index'] for x in catalog]==list(range(14)),'EXACT_FOURTEEN_SOURCE_CATALOG')
    commands=module(by_path[str(CANON/'source/support/business_commands.py')],'actual_original_owned_commands')
    output=stage/'source-controls';output.mkdir(mode=0o700)
    results=[];error=None;started=time.monotonic_ns()
    try:
        for row in catalog:
            index=row['index'];prep=row['preparation'];entry=row['entry']
            if index==3:
                argv=['/usr/bin/python3','-I','-B',entry['path'],'inspect-source']
            elif index==5:
                # This original entry exposes a pure bootstrap function, not
                # an inspect-source CLI command. Exercise that exact function.
                program="""import argparse,json,pathlib,sys,types
p=pathlib.Path(sys.argv[1]);m=types.ModuleType('actual_IHG_source_entry');m.__file__=str(p)
exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__)
c,packet,ref=m.bootstrap(argparse.Namespace(preparation=pathlib.Path(sys.argv[2]),expect_preparation_sha256=sys.argv[3]))
print(json.dumps({'preparation':ref,'source_files':len(packet['files']),'Android_actions':0,'whole_app_business_accepted':False}))
"""
                argv=['/usr/bin/python3','-I','-B','-c',program,entry['path'],prep['path'],prep['sha256']]
            else:
                argv=['/usr/bin/python3','-I','-B',entry['path'],'--preparation',prep['path'],
                      '--expect-preparation-sha256',prep['sha256'],'inspect-source']
            journal=output/('entry-'+str(index));journal.mkdir(mode=0o700)
            result=commands.run_recorded('source-inspection',argv,20,journal,source_guard,
                protected_pids=[os.getpid(),os.getppid()],mutation=False,check=False,output_bound=1024*1024)
            observation=result.command_observation
            need(observation['host_retirement_proved'] and observation['lifecycle']['child_reaped'] and
                 observation['subreaper']['final_children_empty'],'SOURCE_CHILD_NOT_RETIRED')
            result_ref=pin(journal/'source-inspection.result.json',read(journal/'source-inspection.result.json'))
            results.append({'index':index,'entry':entry,'preparation':prep,'exit_code':result.returncode,
                'command_result':result_ref,'stdout':pin(journal/'source-inspection.stdout',result.stdout),
                'stderr':pin(journal/'source-inspection.stderr',result.stderr)})
            need(result.returncode==0,'SOURCE_INSPECTION_FAILED:'+str(index))
            printed=json.loads(result.stdout)
            if 8 <= index <= 12:
                need(all(printed.get(key) is False for key in
                         ('runtime_qualified','business_qualified','production_ready')) and
                     printed.get('Main_actions') == printed.get('Android_actions') ==
                     printed.get('Gallery_install_attempts') == 0,
                     'GALLERY_SOURCE_ONLY_RESULT_CREDIT_BOUNDARY')
            else:
                need(printed.get('whole_app_business_accepted') is False,
                     'SOURCE_ONLY_RESULT_CREDIT_BOUNDARY')
        for index in (0,9):
            row=catalog[index];prep=row['preparation'];journal=output/('wrong-pin-'+str(index));journal.mkdir(mode=0o700)
            argv=['/usr/bin/python3','-I','-B',row['entry']['path'],'--preparation',prep['path'],
                  '--expect-preparation-sha256','0'*64,'inspect-source']
            result=commands.run_recorded('wrong-preparation-pin',argv,10,journal,source_guard,
                protected_pids=[os.getpid(),os.getppid()],mutation=False,check=False,output_bound=1024*1024)
            need(result.returncode!=0 and result.command_observation['host_retirement_proved'] and
                 result.command_observation['subreaper']['final_children_empty'],'WRONG_SOURCE_PIN_WAS_NOT_REFUSED_CLEANLY')
            results.append({'negative_index':index,'exit_code':result.returncode,'expected_refusal':True,
                'command_result':pin(journal/'wrong-preparation-pin.result.json',read(journal/'wrong-preparation-pin.result.json'))})
        source_guard()
        need(read(CURRENT)==original_current,'CURRENT_CHANGED_DURING_SOURCE_CONTROLS')
    except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)}
    children=Path('/proc/self/task')/str(os.getpid())/'children'
    child_text=children.read_text().strip()
    report={'schema':'pocket4-canonical-private-source-bootstrap-controls-v1','results':results,'error':error,
        'expected_positive_count':14,'expected_negative_count':2,'all_passed':error is None and len(results)==16 and not child_text,
        'source_manifest':pin(stage/'BUNDLE-MANIFEST.json',manifest_raw),'private_mount_inode':private_ns,
        'original_mount_inode':args.original_mount_inode,'remaining_owned_children':child_text,
        'elapsed_ns':time.monotonic_ns()-started,'host_canonical_path_writes':0,'Android_actions':0,
        'image_opens':0,'CURRENT_writes':0,'release_adoptions':0,'runtime_qualified':False,'Main_readonly_entry_passed':False}
    raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    path=output/'RESULT.json';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    print(json.dumps(pin(path,raw)),flush=True)
    return 0 if report['all_passed'] else 1

if __name__=='__main__':raise SystemExit(main())
