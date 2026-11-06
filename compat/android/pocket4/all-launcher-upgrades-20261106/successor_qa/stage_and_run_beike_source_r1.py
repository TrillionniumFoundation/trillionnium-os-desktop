#!/usr/bin/env python3
"""Use the existing sudo/Python host channel to stage two pinned files once.

No subprocess or namespace path is added. After bootstrap FDs are closed, the
reviewed worker is invoked once in this process with its real staged __file__.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SOURCE_BYTES = 22148
SOURCE_SHA = '9db3af14e7f2903e3b94bc45ed43f202f2ceb243e95f904dcab3c363aa55cbde'
REQUEST_BYTES = 1250
REQUEST_SHA = '362a42693e7c0a7ed815eb356b6ef2f71a9bf461e60aebb45158830682ce2de6'
NONCE = '77fe9d36efe51cf69813f3411099f049'
ROOT = '/home/alex/work/pocket4-beike-qa-source-preparation-worker-20261106-'+NONCE
STAT_KEYS = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(directory, name, data):
    # Same O_EXCL/root0400/fsync publication used by the reviewed upgrade stagers.
    fd = os.open(name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC|os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        view = memoryview(data)
        while view:
            count = os.write(fd, view); need(count > 0, 'WRITE_PROGRESS'); view = view[count:]
        os.fchmod(fd, 0o400); os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory)


def readback(directory, name, size, digest):
    fd = os.open(name, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
             stat.S_IMODE(before.st_mode) == 0o400 and before.st_size == size, 'STAGED_ROOT_FILE_IDENTITY')
        raw = bytearray()
        while len(raw) <= size:
            block = os.read(fd, min(65536, size+1-len(raw)))
            if not block:
                break
            raw.extend(block)
        again = os.open(name, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC, dir_fd=directory)
        try:
            need(len(raw) == size and sha(raw) == digest and
                 all(getattr(before, key) == getattr(os.fstat(fd), key) == getattr(os.fstat(again), key) for key in STAT_KEYS),
                 'STAGED_SOURCE_OR_PATH_CHANGED')
        finally:
            os.close(again)
        return bytes(raw)
    finally:
        os.close(fd)


def main():
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_EXISTING_HOST_ROOT_REQUIRED')
    os.umask(0o077)
    start_fds = len(os.listdir('/proc/self/fd'))
    payload_raw = sys.stdin.buffer.read(262145)
    need(0 < len(payload_raw) <= 262144, 'BOUNDED_SOURCE_PAYLOAD')
    payload = json.loads(payload_raw)
    need(set(payload) == {'schema', 'source_text', 'request_text'} and
         payload['schema'] == 'pocket4-beike-source-preparation-stage-input-v1', 'CLOSED_STAGE_PAYLOAD')
    source, request = payload['source_text'].encode('utf-8'), payload['request_text'].encode('utf-8')
    need(len(source) == SOURCE_BYTES and sha(source) == SOURCE_SHA and
         len(request) == REQUEST_BYTES and sha(request) == REQUEST_SHA, 'EXACT_REVIEWED_SOURCE_AND_REQUEST')
    compile(source, ROOT+'/prepare_beike_bound_source.py', 'exec')
    descriptors = []
    try:
        parent = os.open('/', os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC); descriptors.append(parent)
        for name in ('home', 'alex', 'work'):
            parent = os.open(name, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC, dir_fd=parent)
            descriptors.append(parent)
        leaf = Path(ROOT).name
        os.mkdir(leaf, 0o700, dir_fd=parent)  # Existing stage is never resumed or overwritten.
        os.fsync(parent)
        directory = os.open(leaf, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC, dir_fd=parent)
        descriptors.append(directory)
        meta = os.fstat(directory)
        need(meta.st_uid == 0 and stat.S_IMODE(meta.st_mode) == 0o700, 'NEW_ROOT_PRIVATE_STAGE_REQUIRED')
        write_new(directory, 'prepare_beike_bound_source.py', source)
        write_new(directory, 'request.json', request)
        source = readback(directory, 'prepare_beike_bound_source.py', SOURCE_BYTES, SOURCE_SHA)
        readback(directory, 'request.json', REQUEST_BYTES, REQUEST_SHA)
        current = os.open(leaf, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC, dir_fd=parent)
        descriptors.append(current)
        need(all(getattr(meta, key) == getattr(os.fstat(current), key) for key in
                 ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')), 'STAGE_PATH_IDENTITY_CHANGED')
    finally:
        errors = []
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        need(not errors, 'BOOTSTRAP_FD_CLOSE_FAILED')
    need(len(os.listdir('/proc/self/fd')) == start_fds, 'BOOTSTRAP_DESCRIPTOR_DIFFERENCE')
    print(json.dumps({'schema': 'pocket4-beike-source-preparation-bootstrap-v1',
        'source': {'path': ROOT+'/prepare_beike_bound_source.py', 'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA},
        'request': {'path': ROOT+'/request.json', 'bytes': REQUEST_BYTES, 'sha256': REQUEST_SHA},
        'bootstrap_FDs_before': start_fds, 'bootstrap_FDs_after': start_fds,
        'bootstrap_Main_actions': 0, 'worker_not_yet_invoked': True, 'automatic_retry': False}, sort_keys=True), flush=True)
    path = ROOT+'/prepare_beike_bound_source.py'
    sys.argv = [path, '--request', ROOT+'/request.json', '--request-sha256', REQUEST_SHA, '--request-bytes', str(REQUEST_BYTES)]
    exec(compile(source, path, 'exec'), {'__name__': '__main__', '__file__': path})


if __name__ == '__main__':
    main()
