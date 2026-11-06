#!/usr/bin/env python3
"""New identity/bounded-enumeration controls only; no live /proc collection."""
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import types
from unittest import mock

HERE = Path(__file__).resolve().parent
RAW = (HERE/'read_visible_lock_fds.py').read_bytes()
reader = types.ModuleType('local_visible_fd_source_controls')
exec(compile(RAW,str(HERE/'read_visible_lock_fds.py'),'exec'),reader.__dict__)
results = []


def need(value, message):
    if not value:
        raise AssertionError(message)


def case(name):
    def run(fn):
        fn()
        results.append(dict(name=name,passed=True))
        return fn
    return run


def support():
    def check_time(deadline):
        need(time.monotonic() < deadline, 'local deadline')
    def no_read(*args, **kwargs):
        raise AssertionError('UNMATCHED_CONTENT_READ_FORBIDDEN')
    return types.SimpleNamespace(check_time=check_time,
        metadata=lambda fd:reader.metadata_from_stat(os.fstat(fd)),read_bounded=no_read)


def counters():
    return dict(enumerated=0,matches=0),dict(gaps=[],fd_stat_attempts=0,
        pid_fd_enumerations_completed=0,matched_fdinfo_bytes=0)


@case('retained_actual_nsfs_timestamp_diff_is_not_identity')
def actual_timestamp_replay():
    p=Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/action-lock-main-fds-readonly01/stdout.log')
    raw=p.read_bytes()
    need((len(raw),hashlib.sha256(raw).hexdigest()) ==
         (28778,'44e2f3f48c5da236c3c9c292a306a6a38c7d926740165e1e753dacdd26f8681c'),'retained actual pin')
    value=json.loads(raw)
    need(value['collection_complete'] is False,'old FAIL retained')
    for row in value['processes'].values():
        need(reader.stable_process_part(row['before'])==reader.stable_process_part(row['after']),
             'new identity tuple compares actual samples')
    before=value['self_before'];after=value['self_after']
    need(reader.namespace_identity(before['namespaces'])==reader.namespace_identity(after['namespaces']),
         'actual self identity')
    original=copy.deepcopy(value['processes']['launcher_process']['before'])
    for key in ('device','inode','mode','uid','gid'):
        changed=copy.deepcopy(original)
        changed['namespaces']['mnt']['metadata'][key]+=1
        need(reader.stable_process_part(changed)!=reader.stable_process_part(original),'reject namespace '+key)
    changed=copy.deepcopy(original);changed['namespaces']['mnt']['label']='mnt:[999]'
    need(reader.stable_process_part(changed)!=reader.stable_process_part(original),'reject namespace label')


@case('proc_root_nlink_not_identity_but_device_inode_owner_are')
def proc_directory_identity():
    row=dict(device=26,inode=1,mode=16749,uid=0,gid=0,nlink=894,size=0,mtime_ns=1,ctime_ns=1)
    changed=dict(row,nlink=895,mtime_ns=2,ctime_ns=2)
    need(reader.inode_identity(row)==reader.inode_identity(changed),'link/time observations')
    for key in ('device','inode','mode','uid','gid'):
        changed=dict(row);changed[key]+=1
        need(reader.inode_identity(row)!=reader.inode_identity(changed),'identity key '+key)


@case('actual_owned_numeric_PID_directory_filter_and_bound')
def numeric_directories():
    with tempfile.TemporaryDirectory(prefix='owned-visible-pid-control-',dir=HERE) as name:
        root=Path(name)
        for part in ('1','25','2147483647','self','unrelated-content'):
            (root/part).mkdir()
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        try:
            values,count=reader.numeric_pid_names(fd,support(),time.monotonic()+5)
            need(values==[1,25,2147483647] and count==5,'only numeric PID names')
        finally:
            os.close(fd)
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        try:
            with mock.patch.object(reader,'VISIBLE_PID_MAX',1):
                try:
                    reader.numeric_pid_names(fd,support(),time.monotonic()+5)
                except RuntimeError as error:
                    need(str(error)=='VISIBLE_NUMERIC_PID_BOUND','bounded numeric enumeration')
                else:
                    raise AssertionError('PID bound not enforced')
        finally:
            os.close(fd)


@case('actual_owned_nonmatches_never_read_process_or_fdinfo_and_gap_is_sanitized')
def nonmatch_access():
    with tempfile.TemporaryDirectory(prefix='owned-nonmatch-fd-control-',dir=HERE) as name:
        root=Path(name);directory=root/'17'/'fd';directory.mkdir(parents=True)
        for part in ('0','3'):
            (directory/part).write_bytes(b'not to be read')
            st=(directory/part).stat()
            need((st.st_dev,st.st_ino)!=(reader.LOCK_DEV,reader.LOCK_INO),'real local nonmatch')
        for inject_gap in (False,True):
            fds=reader.OwnedFDs();procroot=fds.take(os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC))
            budget,coverage=counters();real_stat=os.stat
            def sample_stat(path,*args,**kwargs):
                if inject_gap and path=='3' and kwargs.get('dir_fd') is not None:
                    raise OSError(errno.ENOENT,'private unmatched FD must not be exported')
                return real_stat(path,*args,**kwargs)
            try:
                with mock.patch.object(reader,'process_sample',side_effect=AssertionError('process content forbidden')), \
                     mock.patch.object(reader.os,'pidfd_open',side_effect=AssertionError('unmatched pidfd forbidden')), \
                     mock.patch.object(reader.os,'readlink',side_effect=AssertionError('unmatched readlink forbidden')), \
                     mock.patch.object(reader.os,'stat',sample_stat):
                    row=reader.scan_process(fds,support(),procroot,17,{},budget,coverage,time.monotonic()+5)
                need(row is None and budget==dict(enumerated=2,matches=0),'no unmatched PID export')
                need(coverage['fd_stat_attempts']==2 and coverage['matched_fdinfo_bytes']==0,'metadata only')
                if inject_gap:
                    need(coverage['gaps']==[dict(phase='fd_target_stat',type='FileNotFoundError',errno=errno.ENOENT,count=1)],'sanitized gap')
                    need('private unmatched' not in json.dumps(coverage),'exception message not exported')
                else:
                    need(coverage['gaps']==[],'complete local metadata observations')
            finally:
                fds.finish()
            need(not fds.values and not fds.close_errors,'all owned FDs closed')


@case('matched_initial_identity_failure_stays_sticky_and_never_opens_fdinfo')
def failed_match_identity():
    # A deliberate local I/O seam: adapt only the lock inode constants to an
    # owned temporary file, and replace pidfd/identity observation. No /proc,
    # real PID lookup, flock or collect occurs; this is not kernel qualification.
    with tempfile.TemporaryDirectory(prefix='owned-matched-fd-control-',dir=HERE) as name:
        root=Path(name);directory=root/'17'/'fd';directory.mkdir(parents=True)
        target=root/'owned-lock';target.write_bytes(b'')
        for part in ('0','1'):
            (directory/part).symlink_to(target)
        st=target.stat();metadata=reader.metadata_from_stat(st)
        fds=reader.OwnedFDs();procroot=fds.take(os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC))
        pipe_r,pipe_w=os.pipe2(os.O_CLOEXEC)
        budget,coverage=counters();opened=[];real_open=os.open
        def tracked_open(path,*args,**kwargs):
            opened.append(path)
            return real_open(path,*args,**kwargs)
        try:
            with mock.patch.object(reader,'LOCK_DEV',st.st_dev),mock.patch.object(reader,'LOCK_INO',st.st_ino), \
                 mock.patch.object(reader.os,'open',tracked_open), \
                 mock.patch.object(reader.os,'pidfd_open',side_effect=lambda *args:os.dup(pipe_r)), \
                 mock.patch.object(reader,'pidfd_alive',return_value=[]), \
                 mock.patch.object(reader,'process_sample',side_effect=RuntimeError('INITIAL_IDENTITY_SENTINEL')):
                row=reader.scan_process(fds,support(),procroot,17,metadata,budget,coverage,time.monotonic()+5)
            need(row is not None and row['complete'] is False and len(row['matched_fds'])==2,'retain partial exact matches')
            need(row['first_error']['message']=='INITIAL_IDENTITY_SENTINEL','first cause sticky')
            need(row['matched_fds'][1]['error']['message']=='MATCHED_PROCESS_INITIAL_IDENTITY_REQUIRED','no implicit identity retry')
            need('fdinfo' not in opened and coverage['matched_fdinfo_bytes']==0,'failed identity does not allow FDinfo read')
        finally:
            fds.finish();os.close(pipe_r);os.close(pipe_w)
        need(not fds.values and not fds.close_errors,'owned fixture FDs closed')


print(json.dumps(dict(schema=1,source_bytes=len(RAW),source_sha256=hashlib.sha256(RAW).hexdigest(),
                      scope='five new local controls; retained actual timestamp replay and owned directory/FD seams',
                      count=len(results),results=results,collect_executed=False,live_proc_reads=False,
                      device_qualification=False,old_Main7_FAIL_preserved=True),sort_keys=True,indent=2))
