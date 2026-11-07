#!/usr/bin/env python3
"""Fixed eight-role pre/post host protection; never qualifies an Android QA epoch."""
import hashlib
import json
import os
from pathlib import Path
import resource
import select
import signal
import stat
import time

BOOT_ID = '981ff371-cd72-4f81-9be3-a862111afdb1'
IDENTITY_SOURCE_SHA = 'a949d51bad870db6e95941849faac1c91e95c6fe574bf270702c6c039fa4313e'
ACTUAL_BASELINE02_STDOUT_SHA = '107bf1487ace30a38c113057812a0a18415e3430640f11db0b5131e462d05269'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
OLD_INVALID_EPOCH_SHA = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
CG = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
CELL = Path('/etc/droidloom/cell.json')
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
ENGINE_SHA = 'c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d'
PRESENTER_SHA = '47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24'
DEADLINE = None
EXPECTED=json.loads("{\"android_init\":{\"pid\":3268779,\"start_ticks\":99615082,\"ppid\":3268775,\"uids\":[0,0,0,0],\"namespace_pids\":[3268779,1],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533280]\",\"pid\":\"pid:[4026533285]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"daemon\":{\"pid\":3588022,\"start_ticks\":80796995,\"ppid\":1,\"uids\":[0,0,0,0],\"namespace_pids\":[3588022],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026531832]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"launcher\":{\"pid\":3268774,\"start_ticks\":99615080,\"ppid\":3588022,\"uids\":[0,0,0,0],\"namespace_pids\":[3268774],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533279]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"owner_intermediary\":{\"pid\":3268775,\"start_ticks\":99615082,\"ppid\":3268774,\"uids\":[0,0,0,0],\"namespace_pids\":[3268775],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533280]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"presenter\":{\"pid\":3588024,\"start_ticks\":80796995,\"ppid\":2472,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3588024],\"cgroup\":\"0::/user.slice/user-1000.slice/user@1000.service/app.slice/droidloom.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026531832]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"surfaceflinger\":{\"pid\":3270350,\"start_ticks\":99615245,\"ppid\":3268779,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3270350,661],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_1000/pid_661\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533280]\",\"pid\":\"pid:[4026533285]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"system_server\":{\"pid\":3270611,\"start_ticks\":99615342,\"ppid\":3270325,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3270611,808],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_1000/pid_808\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533719]\",\"pid\":\"pid:[4026533285]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"zygote64\":{\"pid\":3270325,\"start_ticks\":99615242,\"ppid\":3268779,\"uids\":[0,0,0,0],\"namespace_pids\":[3270325,638],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_0/pid_638\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533718]\",\"pid\":\"pid:[4026533285]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}}}")
LIMITS={"cpu.max":"200000 100000","memory.high":"5368709120","memory.max":"6442450944","memory.swap.max":"max","pids.max":"12288"}
STATUS_KEYS={'Uid','Gid','Groups','NSpid','CapInh','CapPrm','CapEff','CapBnd','CapAmb','Threads','State','PPid'}

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe fixed input')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'fixed input too large')
        return raw
    finally:
        os.close(fd)

def parse_counters(text):
    rows = {}
    for line in text.splitlines():
        key, value = line.split()
        require(key not in rows and value.isdecimal(), 'counter format changed')
        rows[key] = int(value)
    return rows

def need(value, reason):
    require(value, reason)


def check():
    need(DEADLINE is not None and time.monotonic() < DEADLINE, 'SNAPSHOT_DEADLINE')


def read(path,limit):
    check();fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        chunks=[];n=0
        while True:
            check();b=os.read(fd,min(8192,limit+1-n))
            if not b:break
            chunks.append(b);n+=len(b);need(n<=limit,'FIXED_READ_BOUND')
        return b''.join(chunks)
    finally:os.close(fd)

def statrow(pid):
    b=read('/proc/%d/stat'%pid,8192);at=b.rfind(b') ')
    need(at>0 and b[:at].startswith(str(pid).encode()+b' ('),'PROC_STAT_SCHEMA')
    f=b[at+2:].split();need(len(f)>=20,'PROC_STAT_FIELDS')
    return {'pid':pid,'start_ticks':int(f[19]),'state':f[0].decode('ascii'),'ppid':int(f[1])}

def process(pid,birth):
    row={'pid':pid,'expected_start_ticks':birth};held=None
    try:
        first=statrow(pid);row['before']=first
        if birth is not None:need(first['start_ticks']==birth,'ORIGINAL_PID_REUSED')
        held=os.pidfd_open(pid,0)
        poll=select.poll();poll.register(held,select.POLLIN)
        need(not poll.poll(0),'PROCESS_ALREADY_DEAD')
        status=read('/proc/%d/status'%pid,65536).decode('ascii','strict')
        row['status']={k:v.strip() for k,v in (line.split(':',1) for line in status.splitlines() if ':' in line) if k in STATUS_KEYS}
        row['cgroup']=read('/proc/%d/cgroup'%pid,8192).decode('ascii','strict')
        row['namespaces']={k:os.readlink('/proc/%d/ns/%s'%(pid,k)) for k in ('mnt','pid','user')}
        st=os.stat('/proc/%d/root'%pid);row['root_identity']={'device':st.st_dev,'inode':st.st_ino}
        last=statrow(pid);row['after']=last
        need(first['start_ticks']==last['start_ticks'] and not poll.poll(0),'PROCESS_CHANGED_DURING_READ')
        row['alive_identity_verified']=True
    except OSError as e:row['error']={'type':type(e).__name__,'errno':e.errno}
    except RuntimeError as e:row['error']={'type':type(e).__name__,'code':str(e)}
    finally:
        if held is not None:os.close(held)
    return row

def identity(row):
    need(row.get("alive_identity_verified") is True and "error" not in row,"FIXED_PROCESS_UNAVAILABLE")
    need(row["before"]["state"] not in ("Z","X") and row["after"]["state"] not in ("Z","X"),"FIXED_PROCESS_DEAD")
    need(row["before"]["ppid"]==row["after"]["ppid"] and
         row["before"]["start_ticks"]==row["after"]["start_ticks"],"FIXED_PROCESS_CHANGED")
    return {"pid":row["pid"],"start_ticks":row["before"]["start_ticks"],
            "ppid":row["before"]["ppid"],"uids":[int(x) for x in row["status"]["Uid"].split()],
            "namespace_pids":[int(x) for x in row["status"]["NSpid"].split()],
            "cgroup":row["cgroup"],"namespaces":row["namespaces"],"root_identity":row["root_identity"]}

def qualify_process(role, row):
    actual = identity(row)
    need(role in EXPECTED and actual == EXPECTED[role], 'FIXED_IDENTITY_DIFFERS_FROM_ACTUAL_BASELINE02')
    return actual


def snapshot_processes():
    rows = {}
    for role, expected in EXPECTED.items():
        check()
        rows[role] = qualify_process(role, process(expected['pid'], expected['start_ticks']))
    need(set(rows) == set(EXPECTED) and len(rows) == 8, 'FIXED_EIGHT_ROLES_INCOMPLETE')
    return rows


def qualify_finish(primary_error, cleanup_errors, within_deadline):
    if primary_error is not None:
        raise primary_error
    need(not cleanup_errors, 'SNAPSHOT_FD_CLEANUP_FAILED')
    need(within_deadline, 'SNAPSHOT_DEADLINE')


def capture():
    global DEADLINE
    need(os.getuid() == 0 and os.geteuid() == 0, 'ROOT_SNAPSHOT_REQUIRED')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic_ns()
    DEADLINE = time.monotonic() + 15
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.alarm(15)  # Self-only watchdog. This helper starts no child processes.
    cg_fd = None
    failure = None
    cleanup_errors = []
    result = None
    try:
        need(read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip() == BOOT_ID, 'BOOT_CHANGED')
        raw = read_regular(ACTIVATION)
        need(sha(raw) == ACTIVATION_SHA, 'HISTORICAL_ACTIVATION_CHANGED')
        activation = json.loads(raw)
        need(activation['main_deployed'] is True and activation['engine_sha256'] == ENGINE_SHA and
             activation['presenter_sha256'] == PRESENTER_SHA and
             activation['framework_epoch']['sha256'] == OLD_INVALID_EPOCH_SHA,
             'HISTORICAL_ACTIVATION_SHAPE_CHANGED')
        need(sha(read_regular(CELL)) == CELL_SHA, 'MAIN_CONFIG_CHANGED')
        before_processes = snapshot_processes()
        cg_fd = os.open(CG, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        cg_info = os.fstat(cg_fd)
        def cg_id(info):
            return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid]
        need(stat.S_ISDIR(cg_info.st_mode) and cg_id(cg_info) == cg_id(CG.lstat()), 'MAIN_CGROUP_NAMING_CHANGED')
        def cg_read(name):
            check()
            need(name and '/' not in name and name not in ('.', '..'), 'CGROUP_FILENAME')
            fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=cg_fd)
            try:
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    value = stream.read(65537)
                need(len(value) <= 65536, 'CGROUP_FIELD_BOUND')
                return value.decode('ascii').strip()
            finally:
                os.close(fd)
        limits = {name: cg_read(name) for name in LIMITS}
        need(limits == LIMITS, 'MAIN_FIVE_LIMITS_CHANGED')
        events = parse_counters(cg_read('memory.events'))
        need({'oom', 'oom_kill', 'oom_group_kill'} <= events.keys(), 'MAIN_OOM_COUNTERS_INCOMPLETE')
        current = {name: int(cg_read(name)) for name in ('memory.current', 'memory.swap.current', 'pids.current')}
        need(all(value >= 0 for value in current.values()), 'MAIN_RESOURCE_COUNTER_INVALID')
        cpu = parse_counters(cg_read('cpu.stat'))
        pressure = cg_read('memory.pressure')
        need({name: cg_read(name) for name in LIMITS} == limits, 'MAIN_LIMITS_CHANGED_DURING_SNAPSHOT')
        need(cg_id(os.fstat(cg_fd)) == cg_id(cg_info) == cg_id(CG.lstat()), 'MAIN_CGROUP_CHANGED_DURING_SNAPSHOT')
        after_processes = snapshot_processes()
        need(before_processes == after_processes == EXPECTED, 'PROTECTED_PROCESSES_CHANGED_DURING_SNAPSHOT')
        need(read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip() == BOOT_ID, 'BOOT_CHANGED')
        need(sha(read_regular(ACTIVATION)) == ACTIVATION_SHA and sha(read_regular(CELL)) == CELL_SHA,
             'SNAPSHOT_AUTHORITIES_CHANGED')
        result = {'schema': 2, 'ok': True,
                  'historical_activation_sha256': ACTIVATION_SHA,
                  'old_invalid_QA_epoch_sha256': OLD_INVALID_EPOCH_SHA,
                  'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
                  'protected_boot_id': BOOT_ID,
                  'protected_identity_source_sha256': IDENTITY_SOURCE_SHA,
                  'actual_baseline02_stdout_sha256': ACTUAL_BASELINE02_STDOUT_SHA,
                  'protected_processes': after_processes,
                  'cell_sha256': CELL_SHA, 'limits': limits,
                  'main_cgroup': str(CG),
                  'main_cgroup_identity': {'device': cg_info.st_dev, 'inode': cg_info.st_ino},
                  'memory_events': events, 'current_resources': current, 'cpu_stat': cpu,
                  'memory_pressure': pressure, 'started_monotonic_ns': started,
                  'Main_actions': 0, 'Android_actions': 0, 'subprocesses_started': 0,
                  'runtime_authorization_enabled': False,
                  'installed_engine_hash_observed': False,
                  'scope': 'Only the fixed current eight process identities, boot, historical activation pin, config, original Main limits and counters. No new QA epoch or full-interval noninterference qualification.'}
    except BaseException as error:
        failure = error
    finally:
        if cg_fd is not None:
            try:
                os.close(cg_fd)
            except BaseException as error:
                cleanup_errors.append({'phase': 'main-cgroup-close', 'type': type(error).__name__,
                                       'errno': getattr(error, 'errno', None)})
        # If the watchdog fired, no successful JSON can have been emitted.
        # Clear it only after local FD retirement; explicit time qualification remains.
        within_deadline = time.monotonic() < DEADLINE
        signal.alarm(0)
    qualify_finish(failure, cleanup_errors, within_deadline)
    result['finished_monotonic_ns'] = time.monotonic_ns()
    result['cleanup_errors'] = cleanup_errors
    return result


if __name__ == '__main__':
    try:
        print(json.dumps(capture(), separators=(',', ':')), flush=True)
    except Exception as error:
        safe = {'type': type(error).__name__, 'errno': getattr(error, 'errno', None)}
        if isinstance(error, RuntimeError) and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in str(error)):
            safe['code'] = str(error)
        print(json.dumps({'schema': 2, 'ok': False, 'error': safe,
                          'Main_actions': 0, 'Android_actions': 0,
                          'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
                          'runtime_authorization_enabled': False}), flush=True)
        raise SystemExit(1)
