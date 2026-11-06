#!/usr/bin/env python3
"""Persist the reviewed r2 source and original evidence, then invoke one mode.

This bootstrap introduces no Android transport. The immutable reviewed worker
does the actual default preflight or the separately explicit execution. Every
request file is exclusive; source/evidence files are unchanged across modes.
"""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import os
import stat
import types

ROOT = '/home/alex/work/pocket4-lifecycle-r2-reviewed-source-20261106-r1'
SOURCE_NAME = 'independent_repair_r2.py'
SOURCE_SHA = 'd45486fbc5b467a6c98ebf7fe8a0dfa6588fde9de5b6bfae466de42fd084b6c9'
SOURCE_BYTES = 68350
OBS_SHA = '8939bf273b3feb6d5fb4360d2739e087ad42c1bb07ec692913eafee433a3d189'
OBS_BYTES = 49955
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def opened_directory(path):
    fds = []
    try:
        d = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        fds.append(d)
        for name in path[1:].split('/'):
            need(name not in ('', '.', '..'), 'CANONICAL_DIRECTORY_REQUIRED')
            d = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=d)
            fds.append(d)
        for f in fds[:-1]:
            os.close(f)
        return d
    except BaseException:
        for f in reversed(fds):
            try:
                os.close(f)
            except OSError:
                pass
        raise


def pinned_read(directory, name, raw):
    f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    try:
        a = os.fstat(f)
        before = tuple(getattr(a, key) for key in FIELDS)
        need(stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1 and
             stat.S_IMODE(a.st_mode) == 0o400 and a.st_size == len(raw), 'ROOT_PINNED_SOURCE_METADATA')
        data = bytearray()
        while len(data) <= len(raw):
            part = os.read(f, min(65536, len(raw) + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        need(data == raw and tuple(getattr(os.fstat(f), key) for key in FIELDS) == before,
             'SOURCE_BYTES_CHANGED')
        b = os.stat(name, dir_fd=directory, follow_symlinks=False)
        need(tuple(getattr(b, key) for key in FIELDS) == before, 'SOURCE_PATH_CHANGED')
    finally:
        os.close(f)
    return {'path': ROOT + '/' + name, 'bytes': len(raw), 'sha256': digest(raw)}


def write_new(directory, name, raw):
    need('/' not in name and name not in ('.', '..'), 'CLOSED_ARTIFACT_NAME')
    f = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o400, dir_fd=directory)
    try:
        view = memoryview(raw)
        while view:
            n = os.write(f, view)
            need(n > 0, 'WRITE_PROGRESS')
            view = view[n:]
        os.fchmod(f, 0o400)
        os.fsync(f)
    finally:
        os.close(f)
    os.fsync(directory)
    return pinned_read(directory, name, raw)


def main():
    need(os.getuid() == os.geteuid() == 0 and sys.argv[1:] in (['preflight'], ['execute']),
         'EXPLICIT_ROOT_MODE_REQUIRED')
    mode = sys.argv[1]
    os.umask(0o077)
    before = len(os.listdir('/proc/self/fd'))
    raw = sys.stdin.buffer.read(1048577)
    need(0 < len(raw) <= 1048576, 'BOOTSTRAP_PAYLOAD_BOUND')
    packet = json.loads(raw)
    need(set(packet) == {'source_text', 'observation_text', 'request_text', 'bootstrap_source'},
         'CLOSED_BOOTSTRAP_PACKET')
    source = packet['source_text'].encode()
    observation = packet['observation_text'].encode()
    request = packet['request_text'].encode()
    need(len(source) == SOURCE_BYTES and digest(source) == SOURCE_SHA, 'REVIEWED_SOURCE_PIN')
    need(len(observation) == OBS_BYTES and digest(observation) == OBS_SHA, 'ORIGINAL_OBSERVATION_PIN')
    need(0 < len(request) <= 262144, 'REQUEST_BYTE_BOUND')
    compile(source, ROOT + '/' + SOURCE_NAME, 'exec')
    plan = json.loads(request)
    need(plan['source'] == {'path': ROOT + '/' + SOURCE_NAME, 'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA},
         'REQUEST_EXACT_SOURCE_PIN')
    need(plan['current_observation'] == {'path': ROOT + '/original-current-observation.raw.json',
         'bytes': OBS_BYTES, 'sha256': OBS_SHA}, 'REQUEST_EXACT_OBSERVATION_PIN')
    need(plan['output_root'] == '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-' + mode + '-01',
         'EXPLICIT_MODE_OUTPUT_ROOT')
    if mode == 'preflight':
        p = opened_directory('/home/alex/work')
        try:
            os.mkdir(ROOT.rsplit('/', 1)[1], 0o700, dir_fd=p)
            os.fsync(p)
        finally:
            os.close(p)
    d = opened_directory(ROOT)
    try:
        if mode == 'preflight':
            source_pin = write_new(d, SOURCE_NAME, source)
            observation_pin = write_new(d, 'original-current-observation.raw.json', observation)
            write_new(d, 'stage_and_invoke_reviewed.py', packet['bootstrap_source'].encode())
        else:
            source_pin = pinned_read(d, SOURCE_NAME, source)
            observation_pin = pinned_read(d, 'original-current-observation.raw.json', observation)
        request_pin = write_new(d, 'request-' + mode + '.private.json', request)
    finally:
        os.close(d)
    need(len(os.listdir('/proc/self/fd')) == before, 'BOOTSTRAP_ALL_FDS_CLOSED')
    print(json.dumps({'schema': 'pocket4-reviewed-r2-input-stage-v1', 'mode': mode,
        'source': source_pin, 'observation': observation_pin, 'request': request_pin,
        'bootstrap_FDs_before': before, 'bootstrap_FDs_after': before,
        'bootstrap_Main_actions': 0}, sort_keys=True, separators=(',', ':')), flush=True)
    worker = types.ModuleType('reviewed_independent_repair_r2')
    worker.__file__ = source_pin['path']
    exec(compile(source, worker.__file__, 'exec'), worker.__dict__)
    argv = ['--packet', request_pin['path'], '--packet-sha256', request_pin['sha256']]
    if mode == 'execute':
        argv.append('--execute')
    return worker.main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
