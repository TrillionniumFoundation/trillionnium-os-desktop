#!/usr/bin/env python3
"""Exact eight-file package RC observation; no writes, subprocess or namespaces."""
import hashlib
import json
import os
from pathlib import PurePosixPath
import stat
import sys
import traceback

FILES = [{'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/payload/3/input-bridge-no-adb.rc', 'bytes': 972, 'sha256': 'a5f383dfd19b4e02d6fcc4ed4b01502978b727779930f89507f087394a67ddf3', 'include_text': True}, {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/payload/7/lmkd-first-pixels.rc', 'bytes': 811, 'sha256': 'ae02e6e01d907b6a0a28e56d01ed9120c2072b9c2f313b415bc0ba28f3b3a710', 'include_text': True}, {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/payload/9/netd-mainline-bpf.rc', 'bytes': 1339, 'sha256': 'f0d45cfd1400c15bfde6eea85969ce232ad51e63c9ab956051cfdd83cbcededf', 'include_text': True}, {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/payload/11/init.rc', 'bytes': 58845, 'sha256': '86d9d3a995a5bb70ea89431dca096bf21fa2310221c1cab90a4f23664e1a791b', 'include_text': True}, {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/payload/15/droidloom-composer.rc', 'bytes': 548, 'sha256': 'c2829e7e76266d43ab6bd5def85031d95a067e461e1a20915169c2ec475c5fd2', 'include_text': True}, {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/runtime-trees/0/droidloom-home.rc', 'bytes': 230, 'sha256': '7a1bbd29cdf3266662670eedea52feeb7edcba67ac2c683c8287ebb32b059c85', 'include_text': True}, {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/runtime-trees/0/droidloom-input-bridge.rc', 'bytes': 464, 'sha256': '27ed65badb62444298722e68b209eb3d326e227dd49425ff090e5b8622e480b4', 'include_text': True}, {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/runtime-trees/3/init.rc', 'bytes': 58845, 'sha256': '86d9d3a995a5bb70ea89431dca096bf21fa2310221c1cab90a4f23664e1a791b', 'include_text': False}]
BASE_MANIFEST_SHA256 = '31885dffa33fe30b0249d37acf437c00b348a0ac1020f8c56b427a8dac743183'


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def stamp(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def read_one(row):
    parts = PurePosixPath(row['path']).parts
    need(parts[0] == '/' and all(x not in ('', '.', '..') for x in parts[1:]), 'non-normalized fixed path')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    fd = None
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
            meta = os.fstat(parent)
            need(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and not (meta.st_mode & 0o022), 'unsafe fixed parent')
        fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0 and
             stat.S_IMODE(before.st_mode) == 0o444 and before.st_size == row['bytes'] and
             0 < before.st_size <= 64 * 1024, 'fixed file type/owner/mode/size differs')
        data = bytearray()
        while len(data) <= row['bytes']:
            chunk = os.read(fd, min(16384, row['bytes'] + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        need(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'fixed file length or digest differs')
        need(stamp(os.fstat(fd)) == stamp(before), 'held fixed file changed while reading')
        named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        need(stamp(named) == stamp(before), 'fixed file name was replaced while reading')
        result = dict(row, device=before.st_dev, inode=before.st_ino, mode=stat.S_IMODE(before.st_mode),
                      uid=before.st_uid, gid=before.st_gid, mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns)
        text = data.decode('utf-8', errors='strict')
        if row['include_text']:
            result['text'] = text
        return result
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def main():
    report = {'schema': 1, 'kind': 'producer07-private-owner-package-rc-readonly01',
              'base_manifest_sha256': BASE_MANIFEST_SHA256, 'files': [], 'success': False,
              'qualification': False, 'services_started': False, 'writes_performed': False,
              'process_signals_or_namespaces': False}
    code = 1
    try:
        need(len(FILES) == 8 and len({r['path'] for r in FILES}) == 8, 'fixed file set differs')
        need(sum(r['bytes'] for r in FILES) <= 128 * 1024 and
             sum(r['bytes'] for r in FILES if r['include_text']) <= 64 * 1024, 'fixed aggregate limit exceeded')
        for row in FILES:
            report['files'].append(read_one(row))
        report['success'] = True
        code = 0
    except BaseException as error:
        report.update(error=repr(error), traceback=traceback.format_exc())
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True) + '\n'
    need(len(encoded.encode('utf-8')) <= 192 * 1024, 'bounded output exceeded')
    sys.stdout.write(encoded)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
