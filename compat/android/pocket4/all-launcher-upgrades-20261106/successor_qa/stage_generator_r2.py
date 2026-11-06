#!/usr/bin/env python3
"""Root-private source publication and root Stage host-file controls only.

Reads a pinned stdin payload. Never calls source generation, namespace entry,
Android commands, package installation, App/UI operations or lifecycle APIs.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import types

ROOT = Path('/home/alex/work/pocket4-successor-qa-generator-source-r2-20261106-01')
GUARD = Path('/home/alex/work/pocket4-main-current-baseline-01/current_baseline_guard.py')
GUARD_SHA = '0ee54ef97c073857609aedb4670395db084ceacc7d28558315647ab2ffbef679'
EPOCH = '734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2'
GENERATOR_MANIFEST_SHA = 'ad32c98479cbb763c6c7728336f65a3e10dd1826de17ea43d0662599f7ce7436'
CONTROL_SHA = '62740d2846c37987a927c7c7df45c46e35b097549c4c2dc9774cf62eaa7ca55b'
TEMPLATE_SHA = '362c6cf681d7ef328c5e6a4d04d371e5824cbd2808fc16af5cb2075636cfda18'


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=1048576):
    p = Path(path)
    need(p.is_absolute() and p.resolve() == p,'CANONICAL_READ_PATH')
    fd = os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and 0 <= first.st_size <= maximum,'BOUNDED_SINGLE_READ')
        def meta(s):
            return tuple(getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
        raw, deadline = bytearray(),time.monotonic()+10
        while len(raw) <= maximum:
            need(time.monotonic()<deadline,'READ_DEADLINE')
            b = os.read(fd,min(65536,maximum+1-len(raw)))
            if not b:
                break
            raw.extend(b)
        need(len(raw)==first.st_size and meta(os.fstat(fd))==meta(first)==meta(p.lstat()),'READ_IDENTITY_CHANGED')
        return bytes(raw)
    finally:
        os.close(fd)


def write_new(path, raw):
    fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    try:
        data = memoryview(raw)
        while data:
            n = os.write(fd,data)
            need(n>0,'WRITE_PROGRESS')
            data=data[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'path':str(path),'bytes':len(raw),'sha256':sha(raw)}


def module(raw,path,name):
    m=types.ModuleType(name)
    m.__file__=str(path)
    exec(compile(raw,str(path),'exec'),m.__dict__)
    return m


def guard_module():
    raw=read(GUARD,65536)
    need(sha(raw)==GUARD_SHA,'EXACT_CURRENT_GUARD_SOURCE')
    return module(raw,GUARD,'actual_current_source_stage_guard')


def run_controls():
    for name,pin in (('check_owned_stage.py',CONTROL_SHA),('templates/install_owned_helper.py.in',TEMPLATE_SHA)):
        need(sha(read(ROOT/name))==pin,'EXACT_ROOT_HOST_CONTROL_SOURCE')
    argv=['/usr/bin/python3','-I',str(ROOT/'check_owned_stage.py'),'--template',str(ROOT/'templates/install_owned_helper.py.in'),
          '--template-sha256',TEMPLATE_SHA,'--temporary-parent',str(ROOT),'--require-root-positive']
    logs=[]
    child=pidfd=None
    observed={'argv':argv,'spawned':False,'joined':False,'timed_out':False,'returncode':None}
    try:
        logs=[open(ROOT/'stage-controls.stdout','xb'),open(ROOT/'stage-controls.stderr','xb')]
        child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=logs[0],stderr=logs[1],
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},close_fds=True)
        observed['spawned']=True
        pidfd=os.pidfd_open(child.pid,0)
        try:
            observed['returncode']=child.wait(timeout=45)
            observed['joined']=True
        except subprocess.TimeoutExpired:
            observed['timed_out']=True
            raise
    finally:
        if child is not None and not observed['joined']:
            if child.poll() is None:
                if pidfd is not None:
                    signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                else:
                    child.kill()  # This exact unjoined Popen child; no ambient PID selection.
            observed['returncode']=child.wait(timeout=6)
            observed['joined']=True
        if pidfd is not None:
            os.close(pidfd)
        for stream in logs:
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        write_new(ROOT/'stage-controls-command.json',(json.dumps(observed,sort_keys=True)+'\n').encode())
    out,err=read(ROOT/'stage-controls.stdout',65536),read(ROOT/'stage-controls.stderr',65536)
    need(observed['returncode']==0 and observed['joined'] and not observed['timed_out'] and not err,'ACTUAL_ROOT_CONTROL_COMMAND_FAILED')
    value=json.loads(out)
    need(value['schema']=='pocket4-production-Stage-host-file-controls-v1' and value['caller_uid']==0 and
         value['root_positive_completed'] is True and value['all_required_passed'] is True and
         value['total_fd_count_unchanged'] is True and value['production_template_sha256']==TEMPLATE_SHA,
         'REAL_ROOT_POSITIVE_CONTROL_REQUIRED')
    need([x['name'] for x in value['cases']]==['root_positive_real_write_readback','complete_or_owner_rejected_stage_all_three_fds_closed',
        'partial_write_real_files_all_three_fds_closed','readback_real_files_all_three_fds_closed'] and
         all(x['passed'] is True and x['skipped'] is False for x in value['cases']), 'FOUR_REAL_HOST_FILE_CONTROLS_REQUIRED')
    need(all(value[x]==0 for x in ('actual_android_paths_opened','Android_commands','namespace_entries','helper_installs','generated_successor_bindings')),
         'HOST_ONLY_CONTROL_SCOPE_REQUIRED')
    return {'command':observed,'report':value,'stdout_sha256':sha(out),'stderr_sha256':sha(err)}


def perform(raw,payload_sha):
    need(os.getuid()==os.geteuid()==0,'ACTUAL_ROOT_PUBLICATION_REQUIRED')
    need(0<len(raw)<=2*1024*1024 and sha(raw)==payload_sha,'EXACT_SOURCE_PAYLOAD')
    payload=json.loads(raw)
    need(set(payload)=={'schema','files'} and payload['schema']=='pocket4-successor-generator-source-payload-v1', 'CLOSED_SOURCE_PAYLOAD')
    files={}
    for name,row in payload['files'].items():
        p=Path(name)
        need(not p.is_absolute() and '..' not in p.parts and str(p)==name and set(row)=={'bytes','sha256','base64'},'SOURCE_PAYLOAD_PATH')
        value=base64.b64decode(row['base64'],validate=True)
        need(base64.b64encode(value).decode()==row['base64'] and len(value)==row['bytes'] and sha(value)==row['sha256'],'SOURCE_PAYLOAD_PIN')
        files[name]=value
    manifest=files['GENERATOR_PINS.json']
    need(sha(manifest)==GENERATOR_MANIFEST_SHA,'R2_GENERATOR_MANIFEST_REQUIRED')
    contract=json.loads(manifest)
    need(len(contract['files'])==31 and set(files)==set(contract['files'])|{'GENERATOR_PINS.json','check_owned_stage.py','README.md','source-origins.json'},
         'EXACT_31_INPUTS_AND_FOUR_ADMISSION_FILES')
    for name,row in contract['files'].items():
        need({'bytes':len(files[name]),'sha256':sha(files[name])}==row,'GENERATOR_FILE_CHANGED')
    need(sha(files['check_owned_stage.py'])==CONTROL_SHA and sha(files['templates/install_owned_helper.py.in'])==TEMPLATE_SHA,
         'ROOT_STAGE_CONTROL_CLOSURE_CHANGED')
    guard=guard_module()
    before=guard.current_guard()
    need(before['Main_epoch_sha256']==EPOCH,'SOURCE_STAGE_PREDECESSOR_EPOCH_CHANGED')
    need(ROOT.parent.resolve()==ROOT.parent and not ROOT.exists(),'NEW_PRIVATE_SOURCE_DESTINATION')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    result={'schema':'pocket4-successor-generator-source-stage-r2-v1','ok':False,'root':str(ROOT),'payload_sha256':payload_sha,
        'generator_manifest_sha256':GENERATOR_MANIFEST_SHA,'guard_before':before,'errors':[],
        'source_generation_executed':False,'Android_commands':0,'namespace_entries':0,'installs':0,'UI_actions':0,
        'cell_lifecycle_commands':0,'existing_permissions_changed':False,'automatic_retry':False,'production_ready':False}
    try:
        directories={ROOT}
        for name,data in sorted(files.items()):
            destination=ROOT/name
            missing=[]
            parent=destination.parent
            while parent!=ROOT:
                missing.append(parent)
                parent=parent.parent
            for directory in reversed(missing):
                if directory not in directories:
                    directory.mkdir(mode=0o700)
                    directories.add(directory)
            write_new(destination,data)
            need(read(destination)==data,'STAGED_SOURCE_READBACK')
        for directory in directories:
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        generator=module(files['generate_successor_sources.py'],ROOT/'generate_successor_sources.py','host_source_closure_check_only')
        need(len(generator.reference_closure(GENERATOR_MANIFEST_SHA))==31,'ACTUAL_PUBLISHED_GENERATOR_CLOSURE')
        result['source_closure_readback_passed']=True
        result['root_stage_controls']=run_controls()
        result['ok']=True
    except BaseException as error:
        result['errors'].append({'type':type(error).__name__,'code':str(error)[:256]})
    finally:
        try:
            result['guard_after']=guard.current_guard()
            need(result['guard_after']==before,'SOURCE_STAGE_RUNTIME_CHANGED')
        except BaseException as error:
            result['errors'].append({'phase':'guard_after','type':type(error).__name__,'code':str(error)[:256]})
        if result['errors']:
            result['ok']=False
        receipt=write_new(ROOT/'result.json',(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode())
        result['receipt']=receipt
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--payload-sha256',required=True)
    a=p.parse_args()
    result=perform(sys.stdin.buffer.read(2*1024*1024+1),a.payload_sha256)
    text=json.dumps(result,sort_keys=True,separators=(',',':'))
    need(len(text.encode())<=65536,'STDOUT_BOUND')
    print(text,flush=True)
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
