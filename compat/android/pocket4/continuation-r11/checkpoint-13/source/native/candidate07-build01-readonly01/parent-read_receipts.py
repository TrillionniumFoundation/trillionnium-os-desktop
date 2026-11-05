#!/usr/bin/env python3
"""Read only this failed build's fixed receipts and logs; no retry or source mutation."""
import base64
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat

BASE = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined06-go5-streaming-01')
SOURCES = (
    ('preparation.json', 262144),
    ('attempt-01/terminal.json', 131072),
    ('attempt-01/claim.json', 131072),
    ('attempt-01/build.stdout', 8388608),
    ('attempt-01/build.stderr', 8388608),
    ('build-fences-02/terminal.json', 131072),
    ('build-fences-02/readmission.json', 131072),
    ('build-fences-02/claim.json', 131072),
    ('build-fences-02/before.json', 262144),
    ('build-fences-02/after.json', 262144),
    ('build-fences-01/terminal.json', 131072),
    ('android-out/target/product/droidloom_x86_64/droidloom-native-engine-inputs.json', 2097152),
    ('android-out/target/product/droidloom_x86_64/droidloom-native-engine-source.json', 2097152),
)
EXPECTED = {
    'preparation.json': 'ea14a9f968f84c5ab02c6f0c03d61ab4cad30f4374cb6662c825621644d71c2a',
    'attempt-01/terminal.json': '51b2d236f90ebb709eb907e7fa6ad64a7b017822faec1655c5c23b12f0c0b19a',
    'build-fences-02/terminal.json': '1abb05239ee80d9afbd208f760541956606746f6249986b4f5078a7e0233bc72',
    'build-fences-01/terminal.json': '8b74d6b0351db5823c4e183c222783b94ada34369f1eede78289ac3b6d20146a',
}
OPTIONAL_ABSENT = {
    'android-out/target/product/droidloom_x86_64/droidloom-native-engine-inputs.json',
    'android-out/target/product/droidloom_x86_64/droidloom-native-engine-source.json',
}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'bytes': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def observe(relative, limit):
    path = BASE / relative
    row = {'path': str(path), 'relative': relative, 'maximum_bytes': limit,
           'started_utc': utc(), 'complete': False}
    try:
        parents = {}
        for parent in path.parents:
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise RuntimeError('source ancestor is not a real directory: ' + str(parent))
            parents[str(parent)] = (info.st_dev, info.st_ino, info.st_mode)
        named_before = path.lstat()
        row['named_before'] = identity(named_before)
        if not stat.S_ISREG(named_before.st_mode) or named_before.st_size > limit:
            raise RuntimeError('source is not regular or exceeds its fixed bound')
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            row['held_before'] = identity(os.fstat(stream.fileno()))
            if row['held_before'] != row['named_before']:
                raise RuntimeError('named/held source identity differs before read')
            raw = stream.read(limit + 1)
            row['held_after'] = identity(os.fstat(stream.fileno()))
            row['named_after'] = identity(path.lstat())
            if not (row['held_before'] == row['held_after'] == row['named_after']):
                raise RuntimeError('source changed while held')
            if len(raw) != row['held_before']['bytes'] or len(raw) > limit:
                raise RuntimeError('source read is incomplete or exceeds its fixed bound')
            for name, expected in parents.items():
                info = Path(name).lstat()
                if (info.st_dev, info.st_ino, info.st_mode) != expected:
                    raise RuntimeError('source ancestor identity changed: ' + name)
            row['bytes'] = len(raw)
            row['sha256'] = digest(raw)
            row['text'] = raw.decode('utf-8', errors='strict')
            row['complete'] = True
    except Exception as error:
        row['error'] = {'type': type(error).__name__, 'message': str(error),
                        'errno': getattr(error, 'errno', None),
                        'filename': getattr(error, 'filename', None)}
    row['finished_utc'] = utc()
    return row


def main():
    started = utc()
    rows = [observe(relative, limit) for relative, limit in SOURCES]
    errors = []
    byname = {row['relative']:row for row in rows}
    for row in rows:
        if not row['complete']:
            missing_artifact = row['relative'] in OPTIONAL_ABSENT and row.get('error',{}).get('errno') == 2
            row['expected_failure_artifact_absence'] = missing_artifact
            if not missing_artifact:
                errors.append({'path':row['relative'],'error':row.get('error')})
        elif row['relative'] in EXPECTED and row['sha256'] != EXPECTED[row['relative']]:
            errors.append({'path':row['relative'],'error':'known receipt digest mismatch'})
    inner = byname['attempt-01/terminal.json']
    if inner['complete']:
        try:
            terminal = json.loads(inner['text'])
            for label in ('stdout','stderr'):
                row = byname['attempt-01/build.'+label]
                if not row['complete'] or row.get('sha256') != terminal[label+'_sha256']:
                    errors.append({'path':row['relative'],'error':'builder terminal/log digest mismatch'})
        except Exception as error:
            errors.append({'path':inner['relative'],'error':repr(error)})
    result = {'schema':1,'scope':'failed candidate06 Go5 full build02 fixed evidence collection',
              'source_sha256':SOURCE_SHA256,'started_utc':started,'finished_utc':utc(),
              'collection_complete':not errors,'all_requested_files_present':all(r['complete'] for r in rows),
              'errors':errors,'files':rows,'recursive_scan':False,'source_execution':False,
              'Main_actions':0,'files_written':0,'retry_or_build_started':False,
              'policy_or_resource_changes':0,'failed_build_preserved':True}
    raw = (json.dumps(result,ensure_ascii=True,sort_keys=True)+'\n').encode()
    if len(raw)>64000000:
        raise RuntimeError('bounded receipt/log result exceeds transport encoding bound')
    packed = gzip.compress(raw,compresslevel=6,mtime=0)
    envelope = {'schema':1,'encoding':'gzip+base64','uncompressed_bytes':len(raw),
                'sha256':digest(raw),'gzip_bytes':len(packed),'gzip_sha256':digest(packed),
                'collection_complete':not errors,'payload':base64.b64encode(packed).decode('ascii')}
    print(json.dumps(envelope,sort_keys=True),flush=True)
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
