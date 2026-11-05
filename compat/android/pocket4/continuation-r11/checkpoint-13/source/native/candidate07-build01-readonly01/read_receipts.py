#!/usr/bin/env python3
"""Read only candidate07 fixed terminal evidence and held artifact hashes; no execution."""
import base64
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat

BASE = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01')
PRODUCT = 'android-out/target/product/droidloom_x86_64/'
HOST_TEST = 'android-out/host/linux-x86/nativetest64/berberis_arm64_host_tests/'
HOST_LIB = 'android-out/host/linux-x86/lib64/'
JOURNAL = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/source-projection.json')
SOURCES = (
    ('preparation.json', 262144),
    ('copied-builder-source-manifest.json', 262144),
    ('attempt-01/terminal.json', 131072),
    ('attempt-01/claim.json', 131072),
    ('attempt-01/build.stdout', 8388608),
    ('attempt-01/build.stderr', 8388608),
    ('build-fences-01/terminal.json', 131072),
    ('build-fences-01/claim.json', 131072),
    ('build-fences-01/before.json', 262144),
    ('build-fences-01/after.json', 262144),
    ('build-fences-01/before.stdout.json', 262144),
    ('build-fences-01/after.stdout.json', 262144),
    ('build-fences-01/before.stderr.txt', 65536),
    ('build-fences-01/after.stderr.txt', 65536),
    (PRODUCT + 'droidloom-native-engine-inputs.json', 2097152),
    (PRODUCT + 'droidloom-native-engine-source.json', 2097152),
)
EXPECTED = {
    'preparation.json': '0db7bdac207cab7bd800f6c9948d41b530da1d6ccb077897a508e641c7abee2c',
    'copied-builder-source-manifest.json': '776435c88ca6ddb983456c639ca051e586731140394756f33abe53dc478357e3',
    'attempt-01/terminal.json': '388ab68cd73a932addc43b6a39b334628a619e2a84bf894609047c5d6f852587',
    'build-fences-01/terminal.json': '8432e470ca0b7e945510a2c516fde7affc423c018d3f1d70474971d81dababf9',
}
ARTIFACTS = (
    (PRODUCT + 'system/lib64/libberberis_arm64.so', 67108864),
    (HOST_TEST + 'berberis_arm64_host_tests', 268435456),
    (HOST_TEST + 'decoder/arm64_test/arm64_decoder_encodings.txt', 8388608),
    (HOST_TEST + 'decoder/arm64_test/arm64_decoder_undefined_baseline.txt', 8388608),
    (HOST_TEST + 'heavy_optimizer/arm64/arm64_tier_coverage.txt', 8388608),
    (HOST_LIB + 'libbase.so', 33554432),
    (HOST_LIB + 'liblog.so', 33554432),
    (HOST_LIB + 'libc++.so', 33554432),
)


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


def hash_artifact(relative, limit):
    path = BASE / relative
    row = {'path':str(path), 'relative':relative, 'maximum_bytes':limit,
           'started_utc':utc(), 'complete':False}
    try:
        parents = {}
        for parent in path.parents:
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise RuntimeError('artifact ancestor is not a real directory: '+str(parent))
            parents[str(parent)] = (info.st_dev,info.st_ino,info.st_mode)
        named = path.lstat()
        row['named_before'] = identity(named)
        if not stat.S_ISREG(named.st_mode) or not 0 < named.st_size <= limit:
            raise RuntimeError('artifact type/size outside its fixed bound')
        fd = os.open(path, os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            row['held_before'] = identity(os.fstat(stream.fileno()))
            if row['held_before'] != row['named_before']:
                raise RuntimeError('artifact named/held identity differs')
            value = hashlib.sha256()
            size = 0
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise RuntimeError('artifact grew beyond bound')
                value.update(chunk)
            row['held_after'] = identity(os.fstat(stream.fileno()))
            row['named_after'] = identity(path.lstat())
            if not (row['held_before'] == row['held_after'] == row['named_after']) or size != named.st_size:
                raise RuntimeError('artifact changed while held')
            for name, expected in parents.items():
                info = Path(name).lstat()
                if (info.st_dev,info.st_ino,info.st_mode) != expected:
                    raise RuntimeError('artifact ancestor identity changed: '+name)
            row.update({'bytes':size,'sha256':value.hexdigest(),'complete':True})
    except Exception as error:
        row['error'] = {'type':type(error).__name__,'message':str(error),
                        'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}
    row['finished_utc'] = utc()
    return row


def main():
    started = utc()
    rows = [observe(relative, limit) for relative, limit in SOURCES]
    artifacts = [hash_artifact(relative, limit) for relative, limit in ARTIFACTS]
    errors = []
    byname = {row['relative']:row for row in rows}
    for row in rows+artifacts:
        if not row['complete']:
            errors.append({'path':row['relative'],'error':row.get('error')})
        elif row['relative'] in EXPECTED and row['sha256'] != EXPECTED[row['relative']]:
            errors.append({'path':row['relative'],'error':'known receipt digest mismatch'})
    journal = {'path':str(JOURNAL),'observed_utc':utc(),'metadata_only':True}
    try:
        journal['named_identity'] = identity(JOURNAL.lstat())
        journal['present'] = True
        errors.append({'path':str(JOURNAL),'error':'normal projection journal still present after successful terminal'})
    except FileNotFoundError as error:
        journal.update({'present':False,'errno':error.errno,'filename':error.filename})
    except Exception as error:
        journal['error'] = repr(error)
        errors.append({'path':str(JOURNAL),'error':repr(error)})
    try:
        terminal = json.loads(byname['attempt-01/terminal.json']['text'])
        outer = json.loads(byname['build-fences-01/terminal.json']['text'])
        if not (terminal['state'] == 'ARTIFACTS_BUILT_QUALIFICATION_PENDING' and
                terminal['builder_returncode'] == 0 and terminal['cleanup']['complete'] is True and
                terminal['source_projection_journal_present'] is False and
                outer['state'] == 'BUILD_AND_OBSERVED_MAIN_FENCES_PASSED' and outer['inner_returncode'] == 0):
            raise RuntimeError('actual successful terminal contract differs')
        for label in ('stdout','stderr'):
            row = byname['attempt-01/build.'+label]
            if not row['complete'] or row.get('sha256') != terminal[label+'_sha256']:
                errors.append({'path':row['relative'],'error':'builder terminal/log digest mismatch'})
        inputs = byname[PRODUCT+'droidloom-native-engine-inputs.json']
        final = byname[PRODUCT+'droidloom-native-engine-source.json']
        gate = terminal['artifact_gate']
        if inputs['sha256'] != gate['input_receipt_sha256'] or final['sha256'] != gate['final_receipt_sha256']:
            raise RuntimeError('terminal/source receipt digest mismatch')
        value = json.loads(final['text'])
        test = value['host_tests']
        if not (value['engine']['path'] == str(BASE/ARTIFACTS[0][0]) and
                test['binary_path'] == str(BASE/ARTIFACTS[1][0]) and
                test['directory'] == str(BASE/HOST_TEST) and
                test['shared_library_directory'] == str(BASE/HOST_LIB)):
            raise RuntimeError('source receipt artifact path outside fixed set')
        wanted = {ARTIFACTS[0][0]:value['engine']['sha256'], ARTIFACTS[1][0]:test['binary']['sha256']}
        wanted.update({HOST_TEST+name:pin for name,pin in test['data'].items()})
        wanted.update({HOST_LIB+name:pin['sha256'] for name,pin in test['shared_libraries'].items()})
        if set(wanted) != {name for name,_ in ARTIFACTS}:
            raise RuntimeError('source receipt artifact closure differs')
        for row in artifacts:
            if not row['complete'] or row.get('sha256') != wanted[row['relative']]:
                errors.append({'path':row['relative'],'error':'actual held artifact digest differs from source receipt'})
    except Exception as error:
        errors.append({'path':'terminal/source/artifact binding','error':repr(error)})
    result = {'schema':1,'scope':'candidate07 full build01 fixed terminal evidence and artifact hash collection',
              'source_sha256':SOURCE_SHA256,'started_utc':started,'finished_utc':utc(),
              'collection_complete':not errors,'all_requested_files_present':all(r['complete'] for r in rows+artifacts),
              'errors':errors,'files':rows,'artifact_metadata':artifacts,'projection_journal':journal,
              'recursive_scan':False,'source_execution':False,'binary_execution':False,
              'Main_actions':0,'files_written':0,'retry_or_build_started':False,
              'policy_or_resource_changes':0,'prior_failed_builds_preserved':True,
              'host_suite_executed':False,'Android_executed':False,'production_ready':False}
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
