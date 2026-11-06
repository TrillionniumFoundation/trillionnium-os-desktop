#!/usr/bin/env python3
"""Verify only the complete s36 APK signature using the existing pinned tools."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

APK = '/home/alex/work/pocket4-szzc-finite-tail-20261106-s36/com.szzc_327.apk'
APK_BYTES = 220579134
APK_SHA = '6c796f5073658d6f541ebbae5723d80645e6fbf6060ca816def6c3ec173e31d6'
SAVED_PM_SIGNER = 'd85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44'
DEPS = '/home/alex/work/pocket4-app-identities-20261105-r12-01/dependencies.json'
DEPS_SHA = 'dfe1182d8e0da4d3d6e842736378539df33e03a87cf0ed9ab4bbe9ae1f26c041'
COLLECTOR = '/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/audit_successor_apks.py'
COLLECTOR_SHA = 'faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a'
ROOT = Path('/home/alex/work/pocket4-szzc-signature-observation-20261106-s37')
FIELDS = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')


def need(value, code):
    if not value:
        raise RuntimeError(code)


def ident(fd):
    s = os.fstat(fd)
    return {k: str(getattr(s,k)) for k in FIELDS}


def digest_fd(fd, limit, deadline):
    size = os.fstat(fd).st_size
    need(0 < size <= limit, 'BOUNDED_FILE_SIZE')
    offset, digest = 0, hashlib.sha256()
    while offset < size:
        need(time.monotonic() < deadline, 'FULL_FILE_HASH_DEADLINE')
        block = os.pread(fd, min(1024*1024,size-offset),offset)
        need(bool(block), 'FULL_FILE_HASH_PROGRESS')
        offset += len(block); digest.update(block)
    return digest.hexdigest()


def hold(path, size, checksum, owner, held, deadline):
    need(Path(path).is_absolute() and Path(path).resolve(strict=True).as_posix() == path, 'EXACT_NONALIAS_INPUT_PATH')
    fd = os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s = os.fstat(fd); before = ident(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == owner and not s.st_mode & 0o022 and
             (size is None or s.st_size == size), 'FIXED_FILE_OWNER_SIZE_MODE')
        need(digest_fd(fd, max(size or 0,262144),deadline) == checksum and ident(fd)==before, 'PINNED_FILE_HASH_IDENTITY')
    except BaseException:
        os.close(fd); raise
    held.append({'fd':fd,'path':path,'bytes':s.st_size,'sha256':checksum,'identity':before})
    return fd


def recheck(held,deadline):
    for row in held:
        need(ident(row['fd'])==row['identity'] and digest_fd(row['fd'],row['bytes'],deadline)==row['sha256'], 'HELD_INPUT_CHANGED')
        fd=os.open(row['path'],os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            need(ident(fd)==row['identity'] and Path(row['path']).resolve(strict=True).as_posix()==row['path'], 'INPUT_PATH_REPLACED')
        finally:
            os.close(fd)


def census():
    result={}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd=int(name);s=os.fstat(fd)
            result[name]=[os.readlink('/proc/self/fd/'+name),s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,
                          fcntl.fcntl(fd,fcntl.F_GETFD),fcntl.fcntl(fd,fcntl.F_GETFL)]
        except OSError as e:
            if e.errno not in (2,9):raise
    return result


def save(name,body):
    need(name in ('apksigner.stdout','apksigner.stderr','result.json'), 'CLOSED_EVIDENCE_NAME')
    with (ROOT/name).open('xb') as stream:
        stream.write(body);stream.flush();os.fsync(stream.fileno())
    return {'path':str(ROOT/name),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}


def main():
    need(os.getuid()==os.geteuid()==0 and sys.argv[1:]==['--observe-signature-once'], 'EXACT_EXISTING_ROOT_VERIFICATION_ENTRY')
    need(ROOT.parent.resolve()==ROOT.parent, 'FIXED_PRIVATE_PARENT')
    os.umask(0o077);before=census();ROOT.mkdir(mode=0o700)
    held=[];deadline=time.monotonic()+170
    result={'schema':'pocket4-szzc-complete-candidate-signature-observation-v1','ok':False,'errors':[],
        'Android_commands':0,'Main_actions':0,'installs':0,'UI_actions':0,'permission_changes':0,
        'automatic_retry':False,'production_ready':False,'package_name_hint_not_manifest_proof':'com.szzc',
        'current_manifest_verified':False,'candidate_manifest_verified':False,'newer_version_claimed':False,
        'installed_signature_reference_kind':'saved PackageManager certificate digest, not current APK cryptographic verification',
        'installed_signer_reference':SAVED_PM_SIGNER,'old_files_modified_or_deleted':False,'commands':[]}
    try:
        df=hold(DEPS,None,DEPS_SHA,0,held,deadline)
        deps=json.loads(os.pread(df,os.fstat(df).st_size,0))['files']
        need(isinstance(deps,dict) and 0<len(deps)<=64 and all(k in deps for k in ('java','apksigner_jar','aapt')), 'EXISTING_TOOL_DEPENDENCY_SCHEMA')
        for name,row in deps.items():
            need(Path(row['declared_path']).resolve(strict=True).as_posix()==row['resolved_path'], 'DECLARED_TOOL_ALIAS_CHANGED')
            hold(row['resolved_path'],row['bytes'],row['sha256'],0,held,deadline)
        cf=hold(COLLECTOR,29242,COLLECTOR_SHA,0,held,deadline)
        raw=os.pread(cf,29242,0);runner=types.ModuleType('unchanged_bounded_host_runner');runner.__file__=COLLECTOR
        exec(compile(raw,COLLECTOR,'exec'),runner.__dict__)
        af=hold(APK,APK_BYTES,APK_SHA,1000,held,deadline)
        result['candidate']={k:v for k,v in held[-1].items() if k!='fd'}
        recheck(held,deadline)
        argv=[deps['java']['resolved_path'],'-Xmx256m','-jar',deps['apksigner_jar']['resolved_path'],
              'verify','--verbose','--print-certs','/proc/self/fd/'+str(af)]
        command={'name':'apksigner-verify','purpose':'cryptographic signature observation only'};result['commands'].append(command)
        outputs=runner.run_tool(argv,(af,),command,deadline)
        for stream,body in outputs.items():
            command[stream]=save('apksigner.'+stream,body)
            if len(body)<=32768:command[stream+'_original_utf8']=body.decode('utf-8','strict')
        need(command.get('returncode')==0 and command.get('joined') is True and command.get('pipes_closed') is True and
             command.get('output_capture_complete') is True and command.get('timed_out') is False and
             command.get('own_group_kill_requested') is False and not command.get('error') and not command.get('retirement_error'),
             'COMPLETE_NORMAL_SIGNATURE_VERIFIER_EXIT_REQUIRED')
        text=outputs['stdout'].decode('utf-8','strict')
        certs=re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$',text,re.M)
        need(certs and len(certs)==len(set(certs)),'EXACT_UNIQUE_SIGNER_DIGESTS')
        recheck(held,deadline)
        for row in deps.values():
            need(Path(row['declared_path']).resolve(strict=True).as_posix()==row['resolved_path'],'FINAL_TOOL_ALIAS_CHANGED')
        result.update(ok=True,signature_verified=True,signer_certificate_sha256=certs,
            signer_matches_saved_PM_reference=certs==[SAVED_PM_SIGNER],all_held_files_unchanged=True,
            dependency_input_sha256=DEPS_SHA,runner_source_sha256=COLLECTOR_SHA,
            update_eligibility='NOT_ASSESSED_PENDING_MANIFEST_CURRENT_SCOPE_AND_VERSION')
    except BaseException as e:
        result['errors'].append({'type':type(e).__name__,'reason':str(e)[:512]})
    finally:
        errors=[]
        for row in reversed(held):
            try:os.close(row['fd'])
            except OSError as e:errors.append(str(e))
        result['held_files']={'acquired':len(held),'closed':len(held)-len(errors),'errors':errors}
        if errors:result['ok']=False
    result['original_descriptor_identities_restored']=census()==before
    result['ok']=result['ok'] and result['original_descriptor_identities_restored']
    result['status']='SIGNATURE_OBSERVED_NOT_INSTALLED' if result['ok'] else 'SIGNATURE_OBSERVATION_FAILED'
    raw=(json.dumps(result,sort_keys=True)+'\n').encode();save('result.json',raw);print(raw.decode(),end='',flush=True)
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
