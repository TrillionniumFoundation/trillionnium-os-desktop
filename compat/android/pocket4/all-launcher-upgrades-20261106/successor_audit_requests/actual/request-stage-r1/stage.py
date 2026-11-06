#!/usr/bin/env python3
"""Stage 13 exact audit requests only; never call audit or a runtime guard."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types

ROOT='/home/alex/work/pocket4-successor-apk-audit-requests-20261106-final-upgrades-r1'
COLLECTOR={'path':'/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/audit_successor_apks.py',
           'bytes':29242,'sha256':'faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a'}
MANIFEST_BYTES=17548
MANIFEST_SHA='d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139'
SCOPE={'path':'/home/alex/work/pocket4-successor-native-install-20261106-douyin-01/app-scope-after.private.json',
       'bytes':57340,'sha256':'489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4'}
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
    body=sys.stdin.buffer.read(262145);need(0<len(body)<=262144,'BOUNDED_SOURCE_ONLY_PAYLOAD')
    payload=json.loads(body)
    need(set(payload)=={'schema','manifest_text','requests'} and
         payload['schema']=='pocket4-final-audit-request-stage-input-v1','CLOSED_STAGE_PAYLOAD')
    manifest_raw=payload['manifest_text'].encode('utf-8')
    need(len(manifest_raw)==MANIFEST_BYTES and sha(manifest_raw)==MANIFEST_SHA,'EXACT_REVIEWED_MANIFEST_BYTES')
    plan=json.loads(manifest_raw)
    need(plan['schema']=='pocket4-successor-apk-audit-prepared-requests-v1' and plan['phase']=='post-upgrades' and
         plan['collector']==COLLECTOR and plan['app_scope']==SCOPE and len(plan['batches'])==13,'EXACT_FINAL_PLAN')
    source=read_host_pin(COLLECTOR)
    collector=types.ModuleType('audit_request_schema_validation_only');collector.__file__=COLLECTOR['path']
    exec(compile(source,COLLECTOR['path'],'exec'),collector.__dict__)  # No main/audit invocation.
    need(type(payload['requests']) is list and len(payload['requests'])==13,'THIRTEEN_REQUESTS_REQUIRED')
    files=[];packages=[]
    for number,(item,row) in enumerate(zip(payload['requests'],plan['batches']),1):
        name='batch-%02d.request.json'%number
        need(set(item)=={'name','text'} and item['name']==name and row['batch']==number and
             row['local_request_file']==name and row['request']['path']==ROOT+'/'+name,'CLOSED_REQUEST_DESTINATION')
        raw=item['text'].encode('utf-8')
        need(len(raw)==row['request']['bytes'] and sha(raw)==row['request']['sha256'],'EXACT_REQUEST_PIN')
        request=json.loads(raw);collector.validate_request(request)
        need(request['guard']==plan['guard'] and request['app_scope']==SCOPE and request['packages']==row['packages'] and
             request['output_root']==row['output_root'],'FINAL_SCOPE_AND_OUTPUT_BINDING')
        files.append((name,raw,row['request']));packages.extend(request['packages'])
    need(len(packages)==len(set(packages))==45 and set(packages)==set(collector.PACKAGES),'EXACT_45_LAUNCHER_PARTITION')
    need(sum(row['APK_count'] for row in plan['batches'])==85 and
         sum(row['logical_APK_bytes'] for row in plan['batches'])==4977440266 and
         all(0<row['logical_APK_bytes']<=collector.MAX_BATCH_BYTES for row in plan['batches']),'PINNED_PREPARED_CAPACITY_TOTALS')
    fds=[];pins=[]
    try:
        parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(parent)
        for name in ('home','alex','work'):
            parent=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(parent)
        leaf=Path(ROOT).name
        os.mkdir(leaf,0o700,dir_fd=parent);os.fsync(parent)
        directory=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(directory)
        identity=os.fstat(directory)
        need(identity.st_uid==0 and stat.S_IMODE(identity.st_mode)==0o700,'NEW_ROOT_PRIVATE_REQUEST_STAGE')
        for name,raw,pin in files:
            write_new(directory,name,raw)
            need(read_file(directory,name,pin['bytes'],pin['sha256'],0o400)==raw,'STAGED_REQUEST_READBACK')
            pins.append(pin)
        write_new(directory,'REQUEST_MANIFEST.json',manifest_raw)
        need(read_file(directory,'REQUEST_MANIFEST.json',MANIFEST_BYTES,MANIFEST_SHA,0o400)==manifest_raw,'STAGED_MANIFEST_READBACK')
        current=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(current)
        need(all(getattr(identity,k)==getattr(os.fstat(current),k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid')),'STAGE_DIRECTORY_CHANGED')
        need(read_host_pin(COLLECTOR)==source,'ACTUAL_COLLECTOR_SOURCE_CHANGED_DURING_STAGE')
    finally:
        errors=[]
        for fd in reversed(fds):
            try:os.close(fd)
            except OSError:errors.append(fd)
        need(not errors,'STAGE_FDS_NOT_CLOSED')
    after_fds=len(os.listdir('/proc/self/fd'));need(after_fds==before_fds,'HOST_DESCRIPTOR_DIFFERENCE')
    result={'schema':'pocket4-final-audit-request-stage-result-v1','ok':True,'output_root':ROOT,
            'collector':COLLECTOR,'manifest':{'path':ROOT+'/REQUEST_MANIFEST.json','bytes':MANIFEST_BYTES,'sha256':MANIFEST_SHA},
            'request_pins':pins,'validated_requests':13,'launcher_packages':45,
            'prepared_APK_count':85,'prepared_logical_APK_bytes':4977440266,
            'capacity_basis':'Pinned final-scope plan; no new Android observation by this source-only stage.',
            'bootstrap_FDs_before':before_fds,'bootstrap_FDs_after':after_fds,'audit_invoked':False,
            'Main_reads':0,'native_commands':0,'Android_commands':0,'installs':0,'UI_actions':0,
            'automatic_retry':False,'production_ready':False}
    print(canonical(result).decode('ascii'),flush=True)

if __name__=='__main__':main()

