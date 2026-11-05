#!/usr/bin/env python3
"""Read only six fixed owned install/state02 receipts; never infer success."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT = Path('/home/alex/work/pocket4-owned-bili-qa-r5-install-state-02')
STEP = Path('/home/alex/work/pocket4-bilibili-owned-qa-r5-flow-2b677053c75cb4e91aada7fd108071bf/steps/install-state-r5-02')
PACKAGE = 'org.droidloom.qa.bili.r5'
NONCE = '2b677053c75cb4e91aada7fd108071bf'
STATE_NONCE = '0cd510d1c7647441f250b0cad35599d8'
SOURCE_SHA = '7317d344da48a2819618968c9589ae839b08bcd1405ea8f3cc80b4bf8b68310b'
FILES = {
    'coordinator.json': ROOT/'result.json',
    'stage.json': ROOT/'stage-result.json',
    'worker.json': STEP/'result.json',
    'worker-command-result.json': ROOT/'evidence/02-install-state.result.json',
    'worker.stdout': ROOT/'evidence/02-install-state.stdout',
    'worker.stderr': ROOT/'evidence/02-install-state.stderr',
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Reader:
    def __init__(self):
        self.started = time.monotonic()
        self.total = 0

    def read(self, path, optional):
        require(path in FILES.values(), 'EXACT_SIX_FILE_ALLOWLIST_REQUIRED')
        directory = os.open('/', os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        fd = None
        try:
            try:
                for name in path.parts[1:-1]:
                    next_fd = os.open(name, os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,
                                      dir_fd=directory)
                    os.close(directory)
                    directory = next_fd
                fd = os.open(path.name, os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW, dir_fd=directory)
            except FileNotFoundError:
                if optional:
                    return None
                raise
            first = os.fstat(fd)
            require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_uid == 0 and
                    0 <= first.st_size <= 65536, 'ROOT_SINGLE_REGULAR_BOUNDED_RECEIPT_REQUIRED')
            parts = []
            count = 0
            while True:
                require(time.monotonic()-self.started < 8, 'READ_DEADLINE')
                part = os.read(fd, min(16384, 65537-count))
                if not part:
                    break
                parts.append(part)
                count += len(part)
                self.total += len(part)
                require(count <= 65536 and self.total <= 524288, 'TOTAL_OR_FILE_BOUND')
            last = os.fstat(fd)
            keys = ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
            require(count == first.st_size and all(getattr(first,k) == getattr(last,k) for k in keys),
                    'RECEIPT_CHANGED')
            return b''.join(parts)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(directory)


def collect(coordinator_sha, stage_sha):
    require(os.getuid() == os.geteuid() == 0, 'ROOT_READ_ONLY_REQUIRED')
    require(all(isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x)
                for x in (coordinator_sha, stage_sha)), 'EXTERNAL_TERMINAL_PINS_REQUIRED')
    pins = {'coordinator.json':coordinator_sha, 'stage.json':stage_sha}
    reader = Reader()
    records = {}
    missing = []
    for name, path in FILES.items():
        raw = reader.read(path, optional=name not in pins)
        if raw is None:
            missing.append({'name':name, 'path':str(path)})
            continue
        if name in pins:
            require(sha(raw) == pins[name], 'EXTERNAL_TERMINAL_RECEIPT_CHANGED:'+name)
        records[name] = {'path':str(path), 'bytes':len(raw), 'sha256':sha(raw),
                         'text':raw.decode('utf-8','strict')}
    coordinator = json.loads(records['coordinator.json']['text'])
    stage = json.loads(records['stage.json']['text'])
    require(coordinator.get('package') == PACKAGE and coordinator.get('nonce') == NONCE and
            coordinator.get('source_manifest_sha256') == stage.get('source_manifest_sha256') == SOURCE_SHA,
            'EXACT_FROZEN_INSTALL02_SCOPE_REQUIRED')
    require(coordinator.get('UI_actions') == coordinator.get('audio_actions') == 0,
            'ONLY_OWNED_NO_UI_INSTALL_RECEIPTS_ALLOWED')
    if 'worker.json' in records:
        row = records['worker.json']
        worker = json.loads(row['text'])
        require(worker.get('package') == PACKAGE and worker.get('nonce') == NONCE and
                worker.get('state_nonce') == STATE_NONCE and
                worker.get('UI_actions') == worker.get('audio_actions') == 0 and
                worker.get('UiAutomation_connection_requested') is False,
                'EXACT_OWNED_NO_UI_WORKER_REQUIRED')
        pinned = coordinator.get('failed_worker_result', coordinator.get('worker_result'))
        require(pinned == {k:row[k] for k in ('path','bytes','sha256')},
                'COORDINATOR_WORKER_RECEIPT_BINDING_REQUIRED')
    output = {'schema':1, 'scope':'fixed-owned-r5-install-state02-first-failure-six-files',
        'files':records, 'missing':missing, 'state_consumption_performed':False,
        'installation_or_runtime_qualification_asserted':False,
        'Android_commands':0, 'service_or_process_actions':0, 'permission_or_original_file_changes':0,
        'raw_commercial_UI_or_journal_exported':False, 'total_read_bytes':reader.total,
        'elapsed_seconds':time.monotonic()-reader.started}
    encoded = (json.dumps(output,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    require(len(encoded) <= 524288, 'EXPORT_BOUND')
    print(encoded.decode(), end='', flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once',action='store_true')
    parser.add_argument('--coordinator-sha256')
    parser.add_argument('--stage-sha256')
    args = parser.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','files':{k:str(v) for k,v in FILES.items()},
                          'remote_actions':0,'qualification_asserted':False}))
        return 0
    return collect(args.coordinator_sha256,args.stage_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
