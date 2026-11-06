#!/usr/bin/python3 -I
"""Disposable PID-namespace init/child for the wrapper's host-only controls."""
import json
import os
from pathlib import Path
import signal
import time


def emit(kind):
    raw = Path('/proc/self/stat').read_text()
    tail = raw[raw.rindex(')') + 2:].split()
    row = {'kind': kind, 'namespace_pid': os.getpid(),
           'host_pid': int(raw.split('(', 1)[0]), 'host_parent': int(tail[1]),
           'start_ticks': int(tail[19]), 'pid_namespace': os.readlink('/proc/self/ns/pid')}
    os.write(1, (json.dumps(row, sort_keys=True) + '\n').encode())


if os.getpid() != 1:
    raise SystemExit('FIXTURE_REQUIRES_A_NEW_PID_NAMESPACE')
signal.signal(signal.SIGTERM, lambda *_: emit('init_received_TERM'))
signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
signal.alarm(25)
child = os.fork()
if child == 0:
    signal.signal(signal.SIGTERM, lambda *_: emit('leaf_received_TERM'))
    signal.alarm(25)
    emit('leaf_ready')
else:
    emit('init_ready')
while True:
    time.sleep(.1)
