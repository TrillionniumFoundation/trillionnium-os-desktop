#!/usr/bin/env python3
"""Local owned target/O_TMPFILE and explicit failure seams; never collect/Main."""
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE_SHA = 'caad07035d43dd0e76d8cb0af33b455b2e77eff2aceb90d90c80f0162ee9a49d'
raw = (HERE/'probe_lock.py').read_bytes()
assert len(raw)==35329 and hashlib.sha256(raw).hexdigest()==SOURCE_SHA
spec=importlib.util.spec_from_file_location('local_differential_controls',HERE/'probe_lock.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert os.getuid()==os.geteuid()==os.getgid()==0
real_flock,real_open=fcntl.flock,os.open
real_read_proc=m.read_proc_record
local_getpid=os.getpid()
local_proc_self_pid=int(os.readlink('/proc/self'))


support_raw=(HERE/'read_main_identity.py').read_bytes()
assert len(support_raw)==18537 and hashlib.sha256(support_raw).hexdigest()=='4b955afce019418e98282aa4af549ab1089afc040a5c8990b7713be5f8b4585e'
support_spec=importlib.util.spec_from_file_location('local_original_identity_support',HERE/'read_main_identity.py')
Support=importlib.util.module_from_spec(support_spec)
support_spec.loader.exec_module(Support)


def operation():
    return dict(opened_existing=False,exclusive_calls=0,exclusive_errno=None,acquired=False,
                unlock_calls=0,unlock_errno=None,unlocked=False,close_attempted=False,close_confirmed=False)


results=[]
with tempfile.TemporaryDirectory(prefix='lock-differential-local-') as directory:
    path=Path(directory)/'owned.lock'
    path.write_bytes(b'')
    path.chmod(0o600)
    st=path.stat()
    m.LOCK,m.LOCK_PARENT=str(path),directory
    m.LOCK_DEV,m.LOCK_INO,m.PROC_DEV=st.st_dev,st.st_ino,os.stat('/proc').st_dev

    def run(label,*,busy=True,control_busy=False,unsupported=False,sample_failure=False):
        holder=None
        if busy:
            holder=real_open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
            real_flock(holder,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fds=m.OwnedFDs()
        anchor=fds.take(real_open(path,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC))
        parent=fds.take(real_open(directory,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC))
        before=Support.metadata(anchor)
        parent_before=Support.metadata(parent)
        target,control=operation(),operation()
        control.update(open_attempted=False,opened=False)
        target_error=control_error=None
        calls=[]
        anonymous_opens=0
        old_names=sorted(os.listdir(directory))

        def flock(fd,flags):
            anonymous=os.fstat(fd).st_nlink==0
            calls.append(('anonymous' if anonymous else 'target',flags))
            if control_busy and anonymous and flags==(fcntl.LOCK_EX|fcntl.LOCK_NB):
                raise BlockingIOError(errno.EAGAIN,'local injected anonymous refusal')
            return real_flock(fd,flags)

        def opening(path_arg,flags,mode=0o777,*,dir_fd=None):
            nonlocal anonymous_opens
            if flags & os.O_TMPFILE == os.O_TMPFILE:
                anonymous_opens+=1
                assert path_arg=='.' and dir_fd==parent and flags==os.O_TMPFILE|os.O_RDWR|os.O_CLOEXEC
                if unsupported:
                    raise OSError(errno.EOPNOTSUPP,'local injected anonymous-file unsupported')
            return real_open(path_arg,flags,mode,dir_fd=dir_fd)

        def reading(fds_arg,support,path_arg,maximum,deadline):
            if sample_failure:
                raise OSError(errno.EIO,'local injected adjacent sample failure')
            return real_read_proc(fds_arg,support,path_arg,maximum,deadline)

        try:
            # Local executor mounts an ancestor /proc view. This explicit fixture
            # mapping affects only this test, not the frozen production identity gate.
            with mock.patch.object(m.os,'getpid',lambda:local_proc_self_pid), mock.patch.object(m.fcntl,'flock',flock),mock.patch.object(m.os,'open',opening),mock.patch.object(m,'read_proc_record',reading):
                try:
                    m.admit_once(fds,Support,anchor,before,target,time.monotonic()+3.0)
                except Exception as error:
                    target_error=error
                assert target['exclusive_calls']==1 and target['close_confirmed']
                if busy:
                    assert isinstance(target_error,BlockingIOError) and target_error.errno==errno.EAGAIN
                    assert target['exclusive_errno']==errno.EAGAIN and target['unlock_calls']==0
                else:
                    assert target_error is None and target['acquired'] and target['unlocked']
                if sample_failure:
                    assert not target['adjacent_observation']['complete']
                    assert target['adjacent_observation_error']['errno']==errno.EIO
                    assert target_error.errno==errno.EAGAIN
                else:
                    sample=target['adjacent_observation']
                    assert sample['complete'] and sample['held_after']==before
                    assert sample['own_fdinfo']['parsed']['fields']['ino']==st.st_ino
                    assert sample['mountinfo']['selected']['device']==str(os.major(st.st_dev))+':'+str(os.minor(st.st_dev))
                    rows=sample['table']['parsed']['matched_records']
                    assert len(rows)==(1 if busy else 0)
                    if busy:
                        assert rows[0]['kernel_reported_pid']==os.getpid() and rows[0]['kind']=='FLOCK'
                    m.same_parent(fds,Support,parent,parent_before,time.monotonic()+3.0)
                    try:
                        m.anonymous_once(fds,Support,parent,control,time.monotonic()+3.0)
                    except Exception as error:
                        control_error=error

            assert fds.values==[anchor,parent] and not fds.close_errors
            assert sorted(os.listdir(directory))==old_names
            if sample_failure:
                assert anonymous_opens==0 and control['exclusive_calls']==0
            elif unsupported:
                assert anonymous_opens==1 and control_error.errno==errno.EOPNOTSUPP
                assert control['open_attempted'] and not control['opened'] and control['exclusive_calls']==0
            else:
                assert anonymous_opens==1 and control['close_confirmed'] and control['held_identity_unchanged']
                assert control['held_before']['nlink']==0 and control['held_before']['device']==st.st_dev
                assert control['held_before']['inode']!=st.st_ino and control['exclusive_calls']==1
                if control_busy:
                    assert control_error.errno==errno.EAGAIN and not control['acquired'] and control['unlock_calls']==0
                else:
                    assert control_error is None and control['acquired'] and control['unlocked'] and control['unlock_calls']==1
            assert calls.count(('target',fcntl.LOCK_EX|fcntl.LOCK_NB))==1
            assert calls.count(('anonymous',fcntl.LOCK_EX|fcntl.LOCK_NB))==control['exclusive_calls']
            if busy:
                check=real_open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
                try:
                    try:
                        real_flock(check,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError as error:
                        assert error.errno==errno.EAGAIN
                    else:
                        raise AssertionError('existing fixture holder changed')
                finally:
                    os.close(check)
            results.append(dict(name=label,passed=True,calls=calls,anonymous_open_attempts=anonymous_opens,
                target_errno=getattr(target_error,'errno',None),control_errno=getattr(control_error,'errno',None),
                adjacent_sample_complete=target.get('adjacent_observation',{}).get('complete',False)))
        finally:
            fds.finish()
            assert not fds.values and not fds.close_errors
            if holder is not None:
                real_flock(holder,fcntl.LOCK_UN)
                os.close(holder)

    run('busy_target_actual_adjacent_FLOCK_and_anonymous_PASS')
    run('free_target_and_anonymous_actual_release',busy=False)
    run('both_EAGAIN_preserved_with_no_failed_arm_unlock',control_busy=True)
    run('O_TMPFILE_unsupported_preserved_no_named_fallback',unsupported=True)
    run('target_EAGAIN_survives_adjacent_read_failure',sample_failure=True)

    selected=(b'1 0 0:0 / /unrelated-\xff rw - tmpfs tmpfs rw\n' +
        ('29 1 '+str(os.major(st.st_dev))+':'+str(os.minor(st.st_dev))+' / /owned rw - tmpfs tmpfs rw\n').encode())
    assert m.parse_selected_mount(selected,29)['mountpoint']=='/owned'
    try:
        m.parse_own_fdinfo(('pos:\t0\nflags:\t02000002\nmnt_id:\t29\nino:\t'+str(st.st_ino+1)+'\n').encode())
    except RuntimeError as error:
        assert str(error)=='OWN_TARGET_FDINFO_IDENTITY'
    else:
        raise AssertionError('wrong fdinfo inode accepted')
    results.append(dict(name='only_selected_mount_decoded_and_wrong_fdinfo_inode_rejected',passed=True))

print(json.dumps(dict(schema=1,scope='local owned files/O_TMPFILE and explicit failure seams',
    source_sha256=SOURCE_SHA,passed=len(results),controls=results,collect_called=False,
    local_PID_view_fixture=dict(getpid=local_getpid,proc_self_pid=local_proc_self_pid,
        mapping_only_in_control=True,production_gate_executed=False),
    Main_paths_read=False,Hepta_calls=0,device_holder_or_security_cause_qualified=False),sort_keys=True,indent=2))
