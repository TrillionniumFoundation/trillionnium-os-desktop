#!/usr/bin/env python3
"""One owned sleeper for the separately admitted R5 systemd control."""
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import time

NAME="p4-signal-r5-unit-control-20261104-01"
NONCE="969694d682504cb2ae81bf178474c96e8"
UNIT=NAME+"-bus.service"
GROUP="/system.slice/"+UNIT
EVIDENCE=Path("/home/alex/work/pocket4-signal-runtime-r5-work-01/owned-unit-control-01")
assert len(sys.argv)==1 and os.geteuid()==0
assert Path("/proc/self/cgroup").read_text().strip()=="0::"+GROUP
read_fd,write_fd=os.pipe()
child=os.fork()
if child==0:
    os.close(read_fd)
    unit_fd=group_fd=-1
    try:
        unit_fd=os.open("/sys/fs/cgroup"+GROUP,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        os.mkdir("owned-sleeper",mode=0o700,dir_fd=unit_fd)
        group_fd=os.open("owned-sleeper",os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=unit_fd)
        procs=os.open("cgroup.procs",os.O_WRONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=group_fd)
        try:
            raw=(str(os.getpid())+"\n").encode()
            assert os.write(procs,raw)==len(raw)
        finally:os.close(procs)
        actual=Path("/proc/self/cgroup").read_text().strip()
        assert actual=="0::"+GROUP+"/owned-sleeper"
        status=dict(line.split(":",1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
        record={"pid":os.getpid(),"parent_pid":os.getppid(),
            "start_ticks":int(Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]),
            "boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "uids":[int(x) for x in status["Uid"].split()],"cgroup":actual,
            "unit":UNIT,"nonce":NONCE,"sleep_seconds_max":45}
        assert record["uids"]==[0,0,0,0]
        fd=os.open(EVIDENCE/"child-identity.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
        with os.fdopen(fd,"wb") as stream:
            stream.write((json.dumps(record,sort_keys=True,indent=2)+"\n").encode())
            stream.flush();os.fsync(stream.fileno())
        os.write(write_fd,b"R");os.close(write_fd)
        os.close(group_fd);group_fd=-1
        os.close(unit_fd);unit_fd=-1
        time.sleep(45)
        os._exit(0)
    except BaseException:
        os._exit(91)
os.close(write_fd)
child_fd=-1
ready_confirmed=False
try:
    child_fd=os.pidfd_open(child,0)
    ready=select.select([read_fd],[],[],10)[0]
    assert ready and os.read(read_fd,1)==b"R","owned child setup failed"
    ready_confirmed=True
    # Deliberately leave the bounded sleeper in its owned unit after this
    # oneshot main process exits. No other child is created.
finally:
    os.close(read_fd)
    if not ready_confirmed and child_fd>=0:
        try:signal.pidfd_send_signal(child_fd,signal.SIGKILL)
        except ProcessLookupError:pass
        deadline=time.monotonic()+3
        while True:
            done,_=os.waitpid(child,os.WNOHANG)
            if done==child:break
            assert time.monotonic()<deadline,"failed setup child reap deadline"
            time.sleep(.02)
    if child_fd>=0:os.close(child_fd)

