#!/usr/bin/env python3
"""Read two exact existing b13 fixture manifest logs; no Main or tool execution."""
import hashlib
import json
import os
import stat
import sys
STAT_KEYS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
PINS = ({'bytes': 686, 'path': '/home/alex/work/pocket4-successor-apk-audit-20261106-linked-official-r2-b13/p00-a00-badging.stdout', 'sha256': '28b2cf92369048b078c8fbf337bf8ae08173f49768e946baee8421bb0d0860b5'}, {'bytes': 1244, 'path': '/home/alex/work/pocket4-successor-apk-audit-20261106-linked-official-r2-b13/p00-a00-manifest.stdout', 'sha256': '2deafdbfa41af5daf85f7980a82491408b1472bcb5aafb0904fa1ea72e9b351f'})

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


def main():
    need(os.getuid()==os.geteuid()==0,'EXISTING_AUTHORIZED_ROOT_READER_REQUIRED')
    before=len(os.listdir('/proc/self/fd'))
    rows=[]
    for pin in PINS:
        raw=read_host_pin(pin)
        rows.append({**pin,'encoding':'hex','bytes_hex':raw.hex(),'held_file_and_path_rechecked':True})
    after=len(os.listdir('/proc/self/fd'))
    need(after==before,'HOST_READER_DESCRIPTOR_DIFFERENCE')
    result={'schema':'pocket4-two-exact-b13-fixture-manifest-logs-v1','ok':True,
            'original_failed_audit_job':'1a1b2ab7980-fc05-7f3a','files':rows,
            'process_FDs_before':before,'process_FDs_after':after,
            'existing_files_modified':False,'Main_reads':0,'native_commands':0,
            'Android_commands':0,'aapt_commands':0,'UI_actions':0,'installs':0,
            'namespace_entries':0,'permission_changes':0,'action_lock_acquired':False,
            'automatic_retry':False,'original_failed_audit_reclassified':False}
    print(canonical(result).decode('ascii'),flush=True)

if __name__=='__main__':main()

