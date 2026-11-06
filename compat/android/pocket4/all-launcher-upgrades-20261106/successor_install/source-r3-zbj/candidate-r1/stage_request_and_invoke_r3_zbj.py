#!/usr/bin/env python3
"""Stage one exact explicit install request, then invoke the reviewed worker once."""
import hashlib
import json
import os
import re
import stat
import sys
import types

SOURCE = {'path': '/home/alex/work/pocket4-successor-install-source-20261106-r3-zbj/install_successor_native.py', 'bytes': 61890, 'sha256': '9b68ed2b7be47961746ea3a1a5485f907c77c8eff04f6da834cbf531527712d3'}
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, code):
    if not value:
        raise RuntimeError(code)


def meta(fd):
    s = os.fstat(fd)
    return {k: getattr(s, k) for k in FIELDS}


def opened(path, directory=False):
    parts = path.split('/')[1:]
    need(path.startswith('/home/alex/work/pocket4-') and all(p not in ('', '.', '..') for p in parts), 'CLOSED_WORK_PATH')
    owned = []
    try:
        d = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        owned.append(d)
        for item in parts[:-1]:
            d = os.open(item, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=d)
            owned.append(d)
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        if directory:
            flags |= os.O_DIRECTORY
        fd = os.open(parts[-1], flags, dir_fd=d)
        owned.append(fd)
        return owned, fd
    except BaseException:
        for fd in reversed(owned):
            os.close(fd)
        raise


def read_pinned(pin):
    owned, fd = opened(pin['path'])
    try:
        before = meta(fd)
        need(stat.S_ISREG(before['st_mode']) and before['st_uid'] == 0 and before['st_nlink'] == 1 and before['st_size'] == pin['bytes'], 'ROOT_REGULAR_SOURCE')
        raw = b''
        while len(raw) <= pin['bytes']:
            chunk = os.read(fd, min(65536, pin['bytes'] + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        need(meta(fd) == before and len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'EXACT_SOURCE_BYTES')
        others, check = opened(pin['path'])
        try:
            need(meta(check) == before, 'SOURCE_PATH_REPLACED')
        finally:
            for f in reversed(others):
                os.close(f)
        return raw
    finally:
        for f in reversed(owned):
            os.close(f)


def main():
    need(os.getuid() == os.geteuid() == 0, 'ROOT_REQUIRED')
    os.umask(0o077)
    packet_raw = sys.stdin.buffer.read(131073)
    need(len(packet_raw) <= 131072, 'INPUT_LIMIT')
    packet = json.loads(packet_raw)
    need(set(packet) == {'input_root', 'request_text', 'terminal_text'}, 'CLOSED_STAGE_INPUT')
    root = packet['input_root']
    need(re.fullmatch('/home/alex/work/pocket4-successor-install-input-20261106-[a-z0-9-]{1,40}', root), 'NEW_INPUT_ROOT')
    source = read_pinned(SOURCE)
    worker = types.ModuleType('reviewed_successor_single_install')
    worker.__file__ = SOURCE['path']
    exec(compile(source, worker.__file__, 'exec'), worker.__dict__)
    request_bytes = packet['request_text'].encode('utf-8')
    terminal_bytes = packet['terminal_text'].encode('utf-8')
    request = json.loads(request_bytes)
    worker.validate_request(request)
    terminal = json.loads(terminal_bytes)
    need(terminal.get('state') == 'succeeded' and terminal.get('exit_code') == 0 and all(terminal.get(k) is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed')), 'ACTUAL_VERIFIER_COMPLETION')
    tp = {'path': root + '/verifier-terminal.raw.json', 'bytes': len(terminal_bytes), 'sha256': hashlib.sha256(terminal_bytes).hexdigest()}
    need(request['verifier_terminal'] == tp, 'REQUEST_TERMINAL_BINDING')
    before = len(os.listdir('/proc/self/fd'))
    os.mkdir(root, 0o700)
    owned, directory = opened(root, directory=True)
    try:
        original = meta(directory)
        need(original['st_uid'] == 0 and stat.S_IMODE(original['st_mode']) == 0o700, 'PRIVATE_ROOT_DIRECTORY')
        for name, raw in [('verifier-terminal.raw.json', terminal_bytes), ('request.private.json', request_bytes)]:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=directory)
            try:
                with os.fdopen(os.dup(fd), 'wb') as f:
                    f.write(raw)
                    f.flush()
                    os.fsync(f.fileno())
            finally:
                os.close(fd)
            pin = {'path': root + '/' + name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            need(read_pinned(pin) == raw, 'STAGED_BYTES_READBACK')
        os.fsync(directory)
        others, check = opened(root, directory=True)
        try:
            need(all(meta(check)[k] == original[k] for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')), 'STAGE_ROOT_REPLACED')
        finally:
            for f in reversed(others):
                os.close(f)
    finally:
        for f in reversed(owned):
            os.close(f)
    need(len(os.listdir('/proc/self/fd')) == before, 'BOOTSTRAP_FD_LEAK')
    rp = {'path': root + '/request.private.json', 'bytes': len(request_bytes), 'sha256': hashlib.sha256(request_bytes).hexdigest()}
    print(json.dumps({'schema': 'pocket4-explicit-install-request-stage-v1', 'source': SOURCE, 'request': rp, 'verifier_terminal': tp, 'bootstrap_Main_actions': 0, 'bootstrap_FDs_before': before, 'bootstrap_FDs_after': before}, sort_keys=True, separators=(',', ':')), flush=True)
    sys.argv = [SOURCE['path'], '--request', rp['path'], '--request-sha256', rp['sha256']]
    return worker.main()


if __name__ == '__main__':
    raise SystemExit(main())
