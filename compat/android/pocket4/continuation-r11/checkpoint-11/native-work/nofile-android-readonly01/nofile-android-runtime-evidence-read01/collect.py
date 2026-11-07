#!/usr/bin/env python3
"""Read only the fixed owned Android NOFILE cycle's result and proof files."""
import datetime
import hashlib
import json
import os
from pathlib import PurePosixPath
import signal
import stat
import sys

COORDINATOR = '/home/alex/work/pocket4-owned-nofile-recovery03-android-cycle-01-20261105'
ARMS = {name: '/home/alex/work/pocket4-owned-nofile-recovery03-' + name + '-android-01-20261105'
        for name in ('preimage', 'candidate')}
BUILD_SHA = 'f3617407f8c624357f4bf9a9cc53e1e78a217b3c0b8bc9a51448c09569e2ea06'
RUNNER_SHA = 'c16015f7a51f857d114d92691dbf4ac4d0ccf758c2f99c7c541653ce1957ea62'
REVIEW_SHA = '2dbe0c31ec31733fab9bbfb851ab3642dc0c2d7aef3937165084d1fb11b9548c'
ENTRY_SHA = '3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3'
ALLOWLIST = [(COORDINATOR, 'coordinator-result.json', 524288),
             (COORDINATOR, 'coordinator-claim.json', 16384),
             (COORDINATOR, 'resources-before.json', 32768),
             (COORDINATOR, 'resources-after.json', 32768),
             (COORDINATOR, 'preimage-result.json', 262144),
             (COORDINATOR, 'candidate-result.json', 262144)]
for root in ARMS.values():
    ALLOWLIST += [(root, 'install-verified.json', 32768),
                  (root, '01-install/result.json', 32768),
                  (root, '02-run/result.json', 262144),
                  (root, '03-remove/result.json', 32768),
                  (root, '02-run/instrument.stdout', 262144),
                  (root, '02-run/instrument.stderr', 8192)]


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def identity(info):
    return {key: getattr(info, 'st_' + key) for key in
            ('dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns')}


def read_one(root, relative, limit):
    path = PurePosixPath(root) / relative
    need(path.is_absolute() and '..' not in path.parts, 'invalid fixed path')
    descriptors = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        descriptors.append(parent)
        for component in path.parts[1:-1]:
            parent = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=parent)
            descriptors.append(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        descriptors.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1,
             'fixed evidence is not a root-owned single-link regular file')
        need(0 <= before.st_size <= limit, 'fixed evidence exceeds its per-file bound')
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(32768, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            need(total <= limit, 'fixed evidence grew beyond its bound')
        raw = b''.join(chunks)
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        need(identity(before) == identity(after) == identity(named) and len(raw) == before.st_size,
             'held evidence changed while reading')
        return {'path': str(path), 'limit': limit, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'before': identity(before),
                'after': identity(after), 'named_after': identity(named),
                'held_regular_file': True, 'content': raw.decode('utf-8', 'strict')}
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def collect():
    need(os.geteuid() == 0, 'fixed owned result paths require read-only root access')
    signal.alarm(25)
    output = {'schema': 1, 'state': 'READONLY_CAPTURE_RUNNING',
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'runtime_job_id': '1a1a9a2e461-fc05-3670', 'files': [], 'errors': [],
              'source_path_mutations': 0, 'chmod_operations': 0, 'Android_actions': 0,
              'Main_actions': 0, 'services_started': 0, 'production_ready': False}
    total = 0
    for root, name, limit in ALLOWLIST:
        try:
            row = read_one(root, name, limit)
            total += row['bytes']
            need(total <= 3145728, 'fixed evidence aggregate exceeds three MiB')
            output['files'].append(row)
        except Exception as error:
            output['errors'].append({'path': root + '/' + name, 'error': repr(error),
                                     'errno': getattr(error, 'errno', None),
                                     'filename': getattr(error, 'filename', None)})
    try:
        row = next(r for r in output['files'] if r['path'] == COORDINATOR + '/coordinator-result.json')
        result = json.loads(row['content'])
        need(result['build_sha256'] == BUILD_SHA and result['runner_sha256'] == RUNNER_SHA and
             result['entry_review_sha256'] == REVIEW_SHA and result['entry_qualification_sha256'] == ENTRY_SHA,
             'actual coordinator receipt source authority differs')
        output['coordinator_source_binding_match'] = True
        output['observed_coordinator_state'] = result['state']
    except Exception as error:
        output['errors'].append({'operation': 'fixed coordinator source binding', 'error': repr(error)})
    output['files_observed'] = len(output['files'])
    output['bytes_observed'] = total
    output['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    complete = len(output['files']) == 18 and not output['errors']
    output['state'] = 'READONLY_CAPTURE_COMPLETE' if complete else 'READONLY_CAPTURE_INCOMPLETE'
    signal.alarm(0)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if complete else 1


if __name__ == '__main__':
    if sys.argv[1:] != ['--collect-once']:
        print(json.dumps({'state': 'PLAN_ONLY', 'fixed_paths': [a + '/' + b for a, b, c in ALLOWLIST],
                          'file_count': 18, 'aggregate_max_bytes': 3145728, 'remote_actions': 0}))
    else:
        raise SystemExit(collect())
