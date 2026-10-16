import os
import sys
import signal
import subprocess
import time
import json

role, mode, fd_text, nonce, *extra_args = sys.argv[1:]
fd = int(fd_text)

def event(name, **extra):
    row = dict(event=name, role=role, nonce=nonce, pid=os.getpid(), ppid=os.getppid(),
               pgid=os.getpgrp(), monotonic=time.monotonic(), **extra)
    os.write(fd, (json.dumps(row) + "\n").encode())

if role == "leader":
    if mode == "leader_and_descendant_ignore_term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    ack_read, ack_write = os.pipe()
    child = subprocess.Popen([sys.executable, __file__, "descendant", mode, str(fd), nonce, str(ack_write)], pass_fds=(fd, ack_write))
    os.close(ack_write)
    event("leader_spawned", child_pid=child.pid, ignores_term=signal.getsignal(signal.SIGTERM) == signal.SIG_IGN)
    assert os.read(ack_read, 1) == b"R"
    os.close(ack_read)
    if mode == "leader_exits_normally":
        time.sleep(0.2)
        event("leader_exiting_normally")
        sys.exit(0)
    child.wait()
elif role == "descendant":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    event("descendant_ready", ignores_term=True)
    ack_write = int(extra_args[0])
    os.write(ack_write, b"R")
    os.close(ack_write)
    while True:
        event("heartbeat")
        time.sleep(0.1)
else:
    raise RuntimeError("unknown role")
