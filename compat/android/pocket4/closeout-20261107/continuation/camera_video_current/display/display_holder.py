#!/usr/bin/env python3
"""Normal alex side of the bounded camera display lease; no Android actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import stat
import struct
import time
import types

MODULE_SHA = '81f34cdbc75a2cf4e092a961fe4dce5d23522842c0ec54cdcff4fc9c99e4dbfd'
MAX_PACKET = 65536


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read_fd(fd, bound):
    st = os.fstat(fd)
    require(stat.S_ISREG(st.st_mode) and st.st_size <= bound, 'bounded regular input required')
    raw = os.pread(fd, bound + 1, 0)
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
                value.st_ctime_ns, value.st_mode, value.st_uid, value.st_gid, value.st_nlink)
    require(len(raw) == st.st_size and identity(os.fstat(fd)) == identity(st), 'held input changed')
    return raw


def load_module(fd):
    raw = read_fd(fd, 32768)
    require(hashlib.sha256(raw).hexdigest() == MODULE_SHA, 'display lease module differs')
    module = types.ModuleType('frozen_camera_display_lease')
    exec(compile(raw, 'frozen_display_lease.py', 'exec'), module.__dict__)
    return module


def observe(module, raw):
    prior = json.loads(raw)
    bus = module.DesktopBus()
    try:
        deadline = time.monotonic() + 5
        while True:
            current = bus.snapshot()
            removed = prior.get('inhibitor', {}).get('path') not in bus.inhibitors()
            if removed or time.monotonic() >= deadline:
                return {'owners': bus.owners, 'owners_unchanged': bus.owners == prior['owners'],
                        'inhibitor_removed': removed, 'current': current,
                        'entry_mode_matches': current['power_save_mode'] == prior['before']['power_save_mode'],
                        'DPMS_writes': 0, 'restoration_authority_claimed': False}
            time.sleep(0.05)
    finally:
        bus.close()


def hold(module, control_fd, parent_pid, transaction, max_seconds):
    require(os.getppid() == parent_pid and 1 < parent_pid < 2**31, 'root wrapper parent differs')
    channel = socket.socket(fileno=control_fd)
    channel.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    channel.settimeout(2)
    record = {'state': 'PREPARING', 'signals': [], 'errors': [], 'lease': {},
              'uid': os.geteuid(), 'pid': os.getpid(), 'parent_pid': parent_pid,
              'Main_actions': 0, 'Android_actions': 0, 'USB_actions': 0,
              'video_node_opens': 0, 'started_monotonic_ns': time.monotonic_ns()}
    lease = None
    sequence = 0
    retiring = False

    def send(kind, value):
        nonlocal sequence
        sequence += 1
        data = json.dumps({'kind': kind, 'sequence': sequence, 'value': value},
                          sort_keys=True, separators=(',', ':')).encode()
        require(len(data) <= MAX_PACKET, 'display holder packet exceeded bound')
        require(channel.send(data) == len(data), 'partial display packet')

    def cancelled(number, frame):
        record['signals'].append({'signal': number, 'retiring': retiring,
                                  'monotonic_ns': time.monotonic_ns()})
        if not retiring:
            raise InterruptedError('display holder cancellation')

    previous = {s: signal.signal(s, cancelled) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)}
    signal.setitimer(signal.ITIMER_REAL, max_seconds)
    try:
        lease = module.DisplayLease(transaction, record['lease'])
        lease.acquire()
        record['state'] = 'READY'
        send('READY', record['lease'])
        deadline = time.monotonic() + max_seconds - 20
        while True:
            require(time.monotonic() < deadline, 'display lease absolute budget exhausted')
            current = lease.check()
            send('HEARTBEAT', current)
            readable, _, _ = select.select([channel], [], [], 0.5)
            if not readable:
                continue
            data, anc, flags, address = channel.recvmsg(MAX_PACKET + 1, socket.CMSG_SPACE(12))
            require(data and len(data) <= MAX_PACKET and flags == 0, 'root control link lost or truncated')
            creds = [struct.unpack('3i', value) for level, kind, value in anc
                     if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS]
            require(creds == [(parent_pid, 0, 0)], 'release request lacks root parent credentials')
            request = json.loads(data)
            require(request == {'operation': 'release'}, 'unexpected display holder request')
            record['final_device_check'] = lease.check()
            record['state'] = 'RELEASING'
            break
    except BaseException as error:
        record['state'] = 'FAILED'
        record['errors'].append({'type': type(error).__name__, 'message': str(error)})
        try:
            send('ERROR', record['errors'][-1])
        except BaseException as send_error:
            record['errors'].append({'stage': 'error_send', 'message': str(send_error)})
    finally:
        retiring = True
        signal.setitimer(signal.ITIMER_REAL, 0)
        started = time.monotonic()
        if lease is not None:
            try:
                record['release'] = lease.finish()
            except BaseException as error:
                record['errors'].append({'stage': 'release', 'type': type(error).__name__, 'message': str(error)})
        release = record.get('release', {})
        record['cleanup_seconds'] = time.monotonic() - started
        record['owned_children_after'] = Path('/proc/self/task/%d/children' % os.getpid()).read_text().split()
        record['success'] = (not record['errors'] and not record['signals'] and
            release.get('connection_closed') is True and release.get('inhibitor_removed') is True and
            release.get('entry_mode_restored') is True and not release.get('errors') and
            not record['owned_children_after'] and record['cleanup_seconds'] < 15)
        record['state'] = 'RELEASED' if record['success'] else 'FAILED'
        record['finished_monotonic_ns'] = time.monotonic_ns()
        try:
            send('RELEASE', record)
        except BaseException:
            record['success'] = False
        channel.close()
        for number, old in previous.items():
            signal.signal(number, old)
    return 0 if record['success'] else 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-fd', required=True, type=int)
    parser.add_argument('--control-fd', type=int)
    parser.add_argument('--parent-pid', type=int)
    parser.add_argument('--transaction')
    parser.add_argument('--max-seconds', type=int, default=665)
    parser.add_argument('--observe-fd', type=int)
    args = parser.parse_args()
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000,
            'display helper requires normal alex credentials')
    module = load_module(args.module_fd)
    os.close(args.module_fd)
    if args.observe_fd is not None:
        require(args.control_fd is None and args.parent_pid is None and args.transaction is None,
                'observer cannot acquire a lease')
        print(json.dumps(observe(module, read_fd(args.observe_fd, MAX_PACKET))), flush=True)
        return 0
    require(args.control_fd is not None and args.parent_pid is not None and args.transaction is not None
            and args.max_seconds == 665, 'fixed holder arguments required')
    return hold(module, args.control_fd, args.parent_pid, args.transaction, args.max_seconds)


if __name__ == '__main__':
    raise SystemExit(main())
