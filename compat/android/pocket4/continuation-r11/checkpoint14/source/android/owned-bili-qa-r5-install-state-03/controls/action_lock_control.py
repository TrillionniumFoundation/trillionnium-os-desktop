#!/usr/bin/env python3
"""Actual owned two-process flock controls; no device or Android commands."""
import ast
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent/'install_state.py'
ORIGINAL = Path('/workspace/scratch/94990735b266/android-qa-install-state-01/review-inputs/recorder.py')
ORIGINAL_SHA = '5f25f22db55ba94e6ac895c2ce274b6959a274b64c9aa82bbc30d8c3c860f511'
HOLDER = '''import os,sys,fcntl,select
p,ready,command=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
fd=os.open(p,os.O_RDWR|os.O_CREAT|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
try:
 fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 os.write(ready,b'R');os.close(ready)
 assert select.select([command],[],[],10)[0]
 assert os.read(command,1)==b'Q'
finally:
 os.close(command);os.close(fd)
'''
PROBE = '''import os,sys,fcntl,errno
fd=os.open(sys.argv[1],os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW)
try:
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except OSError as e:
  assert e.errno==errno.EAGAIN;sys.exit(17)
finally:os.close(fd)
'''


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def descriptors():
    result = {}
    for text in os.listdir('/proc/self/fd'):
        fd = int(text)
        try:
            row = os.fstat(fd)
        except OSError as error:
            if error.errno == errno.EBADF:
                continue
            raise
        result[fd] = (row.st_dev,row.st_ino,row.st_mode)
    return result


class Holder:
    def __init__(self,path):
        self.child = None
        self.ready = self.command = None
        read_ready,write_ready = os.pipe()
        read_command,write_command = os.pipe()
        opened = {read_ready,write_ready,read_command,write_command}
        try:
            self.child = subprocess.Popen([sys.executable,'-I','-c',HOLDER,str(path),
                str(write_ready),str(read_command)],pass_fds=(write_ready,read_command),
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.ready,self.command = read_ready,write_command
            for fd in (write_ready,read_command):
                os.close(fd);opened.remove(fd)
            require(select.select([self.ready],[],[],3)[0] and os.read(self.ready,1)==b'R',
                    'OWNED_HOLDER_READY_REQUIRED')
            os.close(self.ready);opened.remove(self.ready);self.ready=None
        except BaseException as original:
            for fd in opened:
                try:os.close(fd)
                except OSError as secondary:original.add_note('fixture FD cleanup: '+repr(secondary))
            if self.child is not None:
                try:
                    if self.child.poll() is None:self.child.kill()
                    self.child.communicate(timeout=3)
                except BaseException as secondary:original.add_note('fixture child cleanup: '+repr(secondary))
            raise

    def release(self):
        if self.command is not None:
            os.write(self.command,b'Q');os.close(self.command);self.command=None

    def close(self):
        self.release()
        try:
            out,err=self.child.communicate(timeout=3)
        except BaseException:
            if self.child.poll() is None:
                self.child.kill()
            self.child.communicate(timeout=3)
            raise
        require(self.child.returncode==0 and out==err==b'','OWNED_HOLDER_EXACT_NORMAL_EXIT_REQUIRED')
        if self.ready is not None:
            os.close(self.ready);self.ready=None


def after_busy(observation, action, errors):
    try:
        end=time.monotonic()+3
        while observation.get('busy_attempts',0)==0:
            require(time.monotonic()<end,'OBSERVED_BUSY_DEADLINE')
            time.sleep(0.005)
        action()
    except BaseException as error:
        errors.append(repr(error))


def main():
    require(os.getuid()==os.geteuid()==0,'LOCAL_ROOT_OWNED_FIXTURES_REQUIRED')
    source=SOURCE.read_bytes()
    module=types.ModuleType('actual_install03');module.__file__=str(SOURCE)
    exec(compile(source,str(SOURCE),'exec'),module.__dict__)
    original=ORIGINAL.read_bytes()
    require(hashlib.sha256(original).hexdigest()==ORIGINAL_SHA,'ORIGINAL_FROZEN_SOURCE_REQUIRED')
    tree=ast.parse(original)
    body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='lock_file']
    require(len(body)==1,'ONE_ACTUAL_OLD_LOCK_FUNCTION')
    old={'os':os,'stat':stat,'fcntl':fcntl,'require':require}
    exec(compile(ast.Module(body=body,type_ignores=[]),str(ORIGINAL),'exec'),old)
    results=[]
    before_all=descriptors()
    with tempfile.TemporaryDirectory(prefix='owned-lock03-',dir=HERE) as temp:
        directory=Path(temp)
        path=directory/'action.lock'
        holder=Holder(path)
        try:
            before=descriptors()
            try:
                old['lock_file'](path)
                raise AssertionError('ORIGINAL_BUSY_MUST_REJECT')
            except BlockingIOError as error:
                require(error.errno==errno.EAGAIN,'ORIGINAL_ERRNO')
            leaked=set(descriptors())-set(before)
            require(len(leaked)==1,'ORIGINAL_ONE_OPEN_DESCRIPTOR_LEAK_REQUIRED')
            for fd in leaked:
                row=os.fstat(fd);named=path.stat()
                require((row.st_dev,row.st_ino)==(named.st_dev,named.st_ino),'ONLY_OWNED_ORIGINAL_LEAK')
                os.close(fd)
            require(descriptors()==before,'ORIGINAL_CONTROL_CLEANUP')
            results.append({'case':'original_busy_actual_EAGAIN_and_one_fd_leak','expected_red':True,
                            'leaked_descriptors':1,'controller_closed_its_own_fd':True,'pass':True})
            observation={};before=descriptors();followup=0
            try:
                fd=module.acquire_action_lock(path,observation)
                followup+=1;os.close(fd)
                raise AssertionError('BUSY_MUST_NOT_ADMIT')
            except BlockingIOError as error:
                require(error.errno==errno.EAGAIN,'NEW_ORIGINAL_ERRNO_RETAINED')
            require(followup==0 and observation['phase']=='lock_deadline' and
                observation['fd_closed_on_error'] is True and observation['acquired'] is False and
                observation['busy_attempts']>=1 and observation['elapsed_seconds']>=5 and
                descriptors()==before,'NEW_BUSY_DEADLINE_OR_FD_RECLAIM_FAILED')
            results.append({'case':'actual_busy_deadline_preserves_EAGAIN_no_followup_no_fd_leak',
                            'observation':observation,'pass':True})
        finally:
            holder.close()

        holder=Holder(path);observation={};errors=[]
        releaser=threading.Thread(target=after_busy,args=(observation,holder.release,errors))
        releaser.start();fd=None
        try:
            fd=module.acquire_action_lock(path,observation)
            releaser.join(timeout=4)
            require(not releaser.is_alive() and not errors and observation['busy_attempts']>=1 and
                    observation['same_inode_confirmed'] is True,'REAL_RELEASE_NOT_OBSERVED')
            probe=subprocess.run([sys.executable,'-I','-c',PROBE,str(path)],capture_output=True,timeout=3)
            require(probe.returncode==17 and probe.stdout==probe.stderr==b'',
                    'SECOND_PROCESS_MUST_BE_EXCLUDED_WHILE_NEW_LOCK_HELD')
            require(fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC,'RETURNED_FD_CLOEXEC_REQUIRED')
            results.append({'case':'actual_holder_release_then_exclusive_same_inode_admission',
                            'observation':observation,'second_process_rejected':True,'pass':True})
        finally:
            if fd is not None:os.close(fd)
            releaser.join(timeout=4);holder.close()
        probe=subprocess.run([sys.executable,'-I','-c',PROBE,str(path)],capture_output=True,timeout=3)
        require(probe.returncode==0 and probe.stdout==probe.stderr==b'','OWNED_RELEASE_MUST_UNLOCK')
        results.append({'case':'actual_second_process_acquires_after_own_fd_close','pass':True})

        holder=Holder(path);observation={};errors=[];before=descriptors()
        def replace_owned_path():
            path.rename(directory/'original-held.lock')
            fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC,0o600);os.close(fd)
            holder.release()
        replacer=threading.Thread(target=after_busy,args=(observation,replace_owned_path,errors))
        replacer.start()
        try:
            try:
                fd=module.acquire_action_lock(path,observation);os.close(fd)
                raise AssertionError('REPLACED_NAME_MUST_NOT_ADMIT')
            except RuntimeError as error:
                require(str(error)=='ACTION_LOCK_NAME_OR_HELD_INODE_CHANGED','EXACT_IDENTITY_ERROR')
            replacer.join(timeout=4)
            require(not replacer.is_alive() and not errors and observation['fd_closed_on_error'] is True
                    and observation['acquired'] is False,'REPLACEMENT_MUST_CLOSE_HELD_FD')
            results.append({'case':'actual_owned_path_replacement_rejected_without_reopening',
                            'observation':observation,'pass':True})
        finally:
            replacer.join(timeout=4);holder.close()

        os.link(path,directory/'second-name.lock')
        observation={};before=descriptors()
        try:
            fd=module.acquire_action_lock(path,observation);os.close(fd)
            raise AssertionError('MULTILINK_MUST_REJECT')
        except RuntimeError as error:
            require(str(error)=='UNSAFE_ACTION_LOCK','EXACT_METADATA_ERROR')
        require(observation['fd_closed_on_error'] is True and observation['attempts']==0 and
                descriptors()==before,'METADATA_EXCEPTION_MUST_CLOSE_OWN_FD')
        results.append({'case':'actual_metadata_rejection_closes_opened_fd_without_flock','pass':True})
    require(descriptors()==before_all,'ALL_CONTROL_FDS_MUST_BE_RECLAIMED')
    report={'schema':1,'production_source_sha256':hashlib.sha256(source).hexdigest(),
        'original_recorder_sha256':ORIGINAL_SHA,'cases':results,'pass':True,
        'actual_two_process_flock':True,'flock_or_clock_seams':False,
        'fixture_release_thread_only':True,'all_own_children_reaped':True,'all_fds_reclaimed':True,
        'temporary_own_lock_files_only':True,'Hepta_or_Android_actions':0,
        'no_external_lock_holder_identified':True,'actual_device_install_qualification':False}
    print(json.dumps(report,sort_keys=True,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
