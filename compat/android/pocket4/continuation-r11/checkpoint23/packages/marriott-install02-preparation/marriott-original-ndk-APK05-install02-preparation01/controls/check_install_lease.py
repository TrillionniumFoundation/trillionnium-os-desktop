"""Eight install admission/FD controls using the real fixed lease methods.
Only fresh, exact host-owned control directories/files are written. The global
action lock, Main, Android, namespace entry, fixture install and child creation
are never called. Four path constants are explicit IO seams; source is unchanged.
"""
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import types

CONTROL_ROOT = Path('/home/alex/work/p4-ndk-fixture-install-lease-controls02-20261106')
ACTION_HOLDER = Path('/home/alex/work/p4-ndk-fixture-install-lease-controls02-20261106-action')
ACTION_PARENT = ACTION_HOLDER/'original'
ACTION_MOVED = ACTION_HOLDER/'moved'


def need(value, code):
    if not value:
        raise AssertionError(code)


def pin(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def load(raw,name):
    value=types.ModuleType(name)
    value.__file__='<exact-control-loaded-'+name+'>'
    exec(compile(raw,value.__file__,'exec'),value.__dict__)
    return value


def run_controls(sources, manifest_raw):
    need(type(sources) is dict and type(manifest_raw) is bytes,'control source shape')
    manifest=json.loads(manifest_raw)
    need(set(manifest['files'])==set(sources) and
         all(pin(raw)==manifest['files'][name] for name,raw in sources.items()),
         'control exact production sources')
    fixture=load(sources['fixture_contract.py'],'fixture')
    phases=load(sources['fixture_phases.py'],'phases')
    module=load(sources['install_lease.py'],'lease')
    worker=load(sources['install_worker.py'],'worker')
    original_paths=(module.ROOT,module.SOURCE,module.STEP,module.ACTION_LOCK)
    original_fcntl=module.fcntl
    original_worker_os=worker.os
    need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==0,
         'only root host-owned fixture controls')
    cases=[]
    lease=None
    sources_view=None
    control_fds=[]
    files=[]
    directories=[]
    cleanup_errors=[]
    moved=False
    replacement=None
    lease_observation=None
    count_before_owned_case=None

    def case(name,callback):
        callback()
        cases.append({'name':name,'passed':True})

    def reject(callback,code):
        try:
            callback()
        except RuntimeError as error:
            need(str(error)==code,('wrong admission rejection',str(error),code))
        else:
            raise AssertionError('unexpected admission success')

    def take(fd,label):
        control_fds.append({'fd':fd,'label':label,'closed':False})
        return fd

    def close_control(fd):
        rows=[x for x in control_fds if x['fd']==fd and x['closed'] is False]
        need(len(rows)==1,'exact control fd')
        try:
            os.close(fd)
            rows[0]['closed']=True
        except BaseException:
            rows[0]['closed']=None
            raise

    def metadata(path):
        row=os.stat(path,follow_symlinks=False)
        return (row.st_dev,row.st_ino,row.st_mode,row.st_uid,row.st_gid,row.st_nlink)

    def remember_file(path):
        row=metadata(path)
        need(stat.S_ISREG(row[2]) and row[3]==row[4]==0 and row[5]==1,'own control file')
        files.append((path,row))

    def remember_directory(path):
        row=metadata(path)
        need(stat.S_ISDIR(row[2]) and row[3]==row[4]==0,'own control directory')
        directories.append((path,row))

    def snapshot_created_paths():
        # Never inspect or clean an old root when our atomic mkdir did not succeed.
        if lease is None or not lease.root_created:
            return
        # All names are fixed consequences of this lease; no listdir/scandir/glob.
        for path in (CONTROL_ROOT,CONTROL_ROOT/'source',CONTROL_ROOT/'steps',
                     CONTROL_ROOT/'steps'/'install-02'):
            if not any(x[0]==path for x in directories):
                try:
                    remember_directory(path)
                except FileNotFoundError:
                    pass
        names=[CONTROL_ROOT/'source'/x for x in sorted(module.SOURCE_NAMES)]
        names += [CONTROL_ROOT/'source'/'SOURCE_PINS.json',CONTROL_ROOT/'flow.lock',
                  CONTROL_ROOT/'failure.lock',CONTROL_ROOT/'steps'/'install-02'/'step.lock',
                  CONTROL_ROOT/'steps'/'install-02'/'once.claim.json']
        for path in names:
            if not any(x[0]==path for x in files):
                try:
                    remember_file(path)
                except FileNotFoundError:
                    pass

    def unbound_worker():
        class NoOS:
            def __getattr__(self,name):
                raise AssertionError('unbound worker attempted OS access:'+name)
        worker.os=NoOS()
        try:
            reject(lambda:worker.run_install(None,None),
                   'SOURCE_ONLY_INSTALL_ACTUAL_BINDING_UNBOUND')
        finally:
            worker.os=original_worker_os

    try:
        case('install_worker_unbound_stops_before_OS_or_Main',unbound_worker)
        module.ROOT=CONTROL_ROOT
        module.SOURCE=CONTROL_ROOT/'source'
        module.STEP=CONTROL_ROOT/'steps'/'install-02'
        module.ACTION_LOCK=str(ACTION_PARENT/'action.lock')
        # Each control directory is new; an old failed run cannot be adopted.
        os.mkdir(ACTION_HOLDER,0o700)
        remember_directory(ACTION_HOLDER)
        os.mkdir(ACTION_PARENT,0o700)
        remember_directory(ACTION_PARENT)
        action_fd=take(os.open(ACTION_PARENT/'action.lock',
            os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600),'own-action')
        os.fsync(action_fd)
        remember_file(ACTION_PARENT/'action.lock')
        scope=fixture.scope('install','1'*32,{'bytes':123,'sha256':'b'*64})
        deadline=time.monotonic()+30
        lease=module.InstallLease(scope,pin(manifest_raw),deadline)

        def positive():
            nonlocal sources_view,count_before_owned_case
            lease.create_and_stage(sources,manifest_raw)
            snapshot_created_paths()
            sources_view=phases.FixedSources(pin(manifest_raw),source_root=str(module.SOURCE))
            lease.acquire_and_claim()
            snapshot_created_paths()
            lease.enter_install_once(sources_view,fixture,scope,module.STEP,deadline)
            need(lease.entered is True and len(lease.locked)==3 and
                 lease.observation['flow_lock_exclusive'] is True and
                 lease.observation['step_lock_exclusive'] is True and
                 lease.observation['global_lock_acquired'] is True and
                 lease.observation['step_claim_create_only'] is True,
                 'real complete three-lock plus O_EXCL claim')
            sources_view.verify()
            count_before_owned_case=len(lease.fds)
        case('real_lease_claims_three_locks_and_exact_seven_sources',positive)

        case('same_lease_cannot_enter_install_twice',lambda:reject(
            lambda:lease.enter_install_once(sources_view,fixture,scope,module.STEP,deadline),
            'INSTALL_PHASE_ALREADY_ENTERED_NO_REPLAY'))

        def reject_retire():
            retired=fixture.scope('retire','2'*32,scope['build_result'],{
                'package':fixture.PACKAGE,'uid':14000,'user':0,
                'owned_install_qualified':True,'Main_epoch':fixture.MAIN_EPOCH,
                'build_result':scope['build_result']})
            reject(lambda:lease.verify_install(sources_view,fixture,retired,module.STEP,deadline),
                   'EXACT_LIVE_INSTALL_ADMISSION_REQUIRED')
        case('install_lease_cannot_authorize_retirement_scope',reject_retire)

        def reject_manifest():
            altered=types.SimpleNamespace(root=sources_view.root,
                pin={'bytes':sources_view.pin['bytes'],'sha256':'0'*64})
            reject(lambda:lease.verify_install(altered,fixture,scope,module.STEP,deadline),
                   'EXACT_LIVE_INSTALL_ADMISSION_REQUIRED')
        case('install_lease_rejects_changed_external_manifest',reject_manifest)

        def replace_ancestor():
            nonlocal moved,replacement
            # Both names are below the new root-owned 0700 action holder.
            # No shared /home directory destination is overwritten by this test.
            try:
                os.stat(ACTION_MOVED,follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise AssertionError('own move destination unexpectedly exists')
            os.rename(ACTION_PARENT,ACTION_MOVED)
            moved=True
            try:
                os.mkdir(ACTION_PARENT,0o700)
                replacement=metadata(ACTION_PARENT)
                reject(lambda:lease.verify_install(sources_view,fixture,scope,module.STEP,deadline),
                       'LEASE_ANCESTOR_HELD_OR_NAMED_IDENTITY_CHANGED')
            finally:
                if replacement is not None:
                    need(metadata(ACTION_PARENT)==replacement,'own replacement directory changed')
                    os.rmdir(ACTION_PARENT)
                    replacement=None
                os.rename(ACTION_MOVED,ACTION_PARENT)
                moved=False
            lease.verify_install(sources_view,fixture,scope,module.STEP,deadline)
        case('real_renamed_shared_ancestor_is_rejected_before_command',replace_ancestor)

        def contention_and_failure():
            fd=take(os.open(ACTION_PARENT/'action.lock',os.O_RDWR|os.O_NOFOLLOW|
                            os.O_CLOEXEC),'contending-owned-open')
            try:
                try:
                    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError as error:
                    need(error.errno==errno.EAGAIN,'wrong real lock contention')
                else:
                    fcntl.flock(fd,fcntl.LOCK_UN)
                    raise AssertionError('real exclusive action lock not held')
            finally:
                close_control(fd)
            def fail_lock(fd,operation):
                if operation==(fcntl.LOCK_EX|fcntl.LOCK_NB):
                    raise BlockingIOError(errno.EAGAIN,'owned fixture injected lock denial')
                return fcntl.flock(fd,operation)
            module.fcntl=types.SimpleNamespace(LOCK_EX=fcntl.LOCK_EX,LOCK_NB=fcntl.LOCK_NB,
                                               LOCK_UN=fcntl.LOCK_UN,flock=fail_lock)
            try:
                try:
                    lease._own_lock(lease.root,'failure.lock','failed-own-lock')
                except BlockingIOError as error:
                    need(error.errno==errno.EAGAIN,'wrong injected failure')
                else:
                    raise AssertionError('failed acquisition accepted')
            finally:
                module.fcntl=original_fcntl
                snapshot_created_paths()
            need(len(lease.fds)==count_before_owned_case+1 and
                 lease.fds[-1]['closed'] is False and len(lease.locked)==3,
                 'failed lock fd must remain owned and tracked until close')
        case('real_lock_contention_and_failed_acquire_FD_remain_accounted',contention_and_failure)

        def failing_unlock():
            nonlocal lease_observation
            def fail_one(fd,operation):
                if fd==lease.step_lock and operation==fcntl.LOCK_UN:
                    raise OSError(errno.EIO,'owned fixture injected unlock failure')
                return fcntl.flock(fd,operation)
            module.fcntl=types.SimpleNamespace(LOCK_EX=fcntl.LOCK_EX,LOCK_NB=fcntl.LOCK_NB,
                                               LOCK_UN=fcntl.LOCK_UN,flock=fail_one)
            try:
                lease_observation=lease.close()
            finally:
                module.fcntl=original_fcntl
            need(lease_observation['all_tracked_lease_FDs_closed'] is True and
                 lease_observation['tracked_FD_count']==lease_observation['closed_FD_count'] and
                 len(lease_observation['lease_errors'])==1 and
                 lease_observation['lease_errors'][0]['stage']=='unlock:step-lock' and
                 lease_observation['lease_errors'][0]['errno']==errno.EIO and
                 lease_observation['global_action_lock_released'] is False and
                 lease_observation['step_lock_released'] is False,
                 'unlock error retained despite actual FD closure')
            for fd in {x['fd'] for x in lease.fds}:
                try:
                    os.fstat(fd)
                except OSError as error:
                    need(error.errno==errno.EBADF,'own fd check error')
                else:
                    raise AssertionError('tracked lease fd still live')
        case('unlock_failure_stays_failed_and_all_owned_FDs_close',failing_unlock)
    finally:
        worker.os=original_worker_os
        module.fcntl=original_fcntl
        if lease is not None and not lease.closed:
            try:
                lease_observation=lease.close()
            except BaseException as error:
                cleanup_errors.append(('lease_close',type(error).__name__))
        for item in reversed(control_fds):
            if item['closed'] is False:
                try:
                    close_control(item['fd'])
                except BaseException as error:
                    cleanup_errors.append(('control_fd_close',type(error).__name__))
        if moved:
            try:
                if replacement is not None:
                    need(metadata(ACTION_PARENT)==replacement,'replacement cleanup identity')
                    os.rmdir(ACTION_PARENT)
                os.rename(ACTION_MOVED,ACTION_PARENT)
                moved=False
            except BaseException as error:
                cleanup_errors.append(('own_ancestor_restore',type(error).__name__))
        try:
            snapshot_created_paths()
        except BaseException as error:
            cleanup_errors.append(('own_literal_paths',type(error).__name__))
        for path,expected in reversed(files):
            try:
                actual=metadata(path)
                need(actual[:5]==expected[:5] and actual[5]==1,'own cleanup file identity')
                os.unlink(path)
            except BaseException as error:
                cleanup_errors.append(('own_file_cleanup',str(path),type(error).__name__))
        # Deepest exact directories first. rmdir refuses every unrecognized child.
        for path,expected in sorted(directories,key=lambda x:len(x[0].parts),reverse=True):
            try:
                actual=metadata(path)
                need(actual[:5]==expected[:5],'own cleanup directory identity')
                os.rmdir(path)
            except BaseException as error:
                cleanup_errors.append(('own_directory_cleanup',str(path),type(error).__name__))
        module.ROOT,module.SOURCE,module.STEP,module.ACTION_LOCK=original_paths
    need(not cleanup_errors,('owned control cleanup failed',cleanup_errors))
    need(len(cases)==8 and all(x['closed'] is True for x in control_fds) and
         lease_observation is not None and lease_observation['all_tracked_lease_FDs_closed'] is True,
         'eight controls and exact host-owned FD closure')
    need((module.ROOT,module.SOURCE,module.STEP,module.ACTION_LOCK)==original_paths and
         module.fcntl is original_fcntl and worker.os is original_worker_os,
         'explicit control seams not restored')
    return {'ok':True,'count':8,'cases':cases,'all_owned_control_FDs_closed':True,
            'all_owned_control_files_removed':True,'runtime_qualified':False,
            'Main_reads':0,'Android_commands':0,'children':0,
            'actual_install_nonce_consumed':False,'synthetic_scope_only':True,
            'real_own_fd_count':lease_observation['tracked_FD_count']+len(control_fds),
            'expected_unlock_failure_preserved':True,'seams_restored':True}
