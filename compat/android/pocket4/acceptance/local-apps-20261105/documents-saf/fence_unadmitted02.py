#!/usr/bin/python3 -I
"""Invalidate our late stage02 before its first business mutation; no Android commands."""
import datetime, hashlib, json, os, stat
from pathlib import Path
WORK=Path('/home/alex/work')
NAME='pocket4-documents-flow-20261105-r12-tools-02'
RUN='pocket4-documents-flow-20261105-r12-02'
MARK='NEVER_EXECUTE_OR_REUSE.json'
def need(ok,reason):
    if not ok:raise RuntimeError(reason)
need(os.geteuid()==0 and WORK.resolve()==WORK,'ROOT_AND_CANONICAL_WORK_REQUIRED')
os.umask(0o077)
p=os.open(WORK,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
try:
    try:os.stat(RUN,dir_fd=p,follow_symlinks=False)
    except FileNotFoundError:pass
    else:raise RuntimeError('ORIGINAL_RUN_EXISTS_NO_FENCE')
    os.mkdir(NAME,0o700,dir_fd=p)  # Exclusive: an existing object is never modified.
    os.fsync(p)
    d=os.open(NAME,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=p)
    try:
        s=os.fstat(d);need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,'FENCE_IDENTITY')
        receipt={'state':'OLD_STAGE_ENTRY_FENCED','job_id':'1a1ab190ab3-fc05-4a51','original_key':'pocket4-documents-saf-flow-r12-02','original_stage_sha256':'920a0f887140602d8176ebd96e88601257d61d94310a8ea8a541a04d6a9587d0','original_request_sha256':'41aaa47e172c847e2171a400d8bf531181f89f28531c48795a3fcda6de2b9d11','fence_path':str(WORK/NAME),'fence_identity':{'dev':s.st_dev,'ino':s.st_ino,'uid':s.st_uid,'mode':s.st_mode},'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'android_actions':0,'original_termination_confirmed':False,'must_never_remove_or_reuse':True}
        data=(json.dumps(receipt,sort_keys=True,indent=2)+'\n').encode()
        f=os.open(MARK,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW,0o600,dir_fd=d)
        with os.fdopen(f,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
        os.fsync(d);os.fsync(p)
        f=os.open(MARK,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d)
        try:
            m=os.fstat(f);need(stat.S_ISREG(m.st_mode) and m.st_nlink==1 and m.st_uid==0 and m.st_size==len(data) and os.read(f,len(data)+1)==data,'FENCE_MARKER_READBACK')
        finally:os.close(f)
        live=os.stat(NAME,dir_fd=p,follow_symlinks=False)
        need((live.st_dev,live.st_ino,live.st_mode,live.st_uid)==(s.st_dev,s.st_ino,s.st_mode,s.st_uid) and os.listdir(d)==[MARK],'FENCE_PATH_READBACK')
        print(json.dumps({'receipt':receipt,'marker_sha256':hashlib.sha256(data).hexdigest(),'identity_and_marker_readback_verified':True}))
    finally:os.close(d)
finally:os.close(p)
