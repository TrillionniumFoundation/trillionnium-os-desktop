#!/usr/bin/env python3
"""Freeze one build-bound APK pair request. This generator never dispatches it."""
from pathlib import Path
import argparse
import ast
import hashlib
import json

HERE = Path(__file__).resolve().parent
REMOTE = '/home/alex/work/pocket4-owned-nofile-recovery03-android-cycle-source-01-20261105'
FILES = ('coordinator.py', 'entry-review.json', 'CASE_PLAN.json')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write')
    args = parser.parse_args()
    if not args.write:
        print(json.dumps({'state': 'PLAN_ONLY', 'remote_source': REMOTE, 'packet_files': list(FILES),
                          'Android_actions': 0, 'remote_requests_dispatched': 0}))
        return
    output = Path(args.write)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise RuntimeError('new absolute local request output required')
    packet = {}
    for name in FILES:
        raw = (HERE / name).read_bytes()
        if name.endswith('.py'):
            ast.parse(raw)
        packet[name] = {'bytes': len(raw), 'sha256': sha(raw), 'text': raw.decode('utf-8')}
    raw_packet = (json.dumps(packet, sort_keys=True, separators=(',', ':')) + '\n').encode()
    stage = '''from pathlib import Path
import hashlib,json,os,stat,sys
assert os.geteuid()==0 and os.getegid()==0 and not sys.flags.optimize
raw=PACKET_RAW.encode('utf-8')
assert hashlib.sha256(raw).hexdigest()==PACKET_SHA
files=json.loads(raw)
assert set(files)=={'coordinator.py','entry-review.json','CASE_PLAN.json'}
root=Path(REMOTE_SOURCE)
assert not root.exists() and not root.is_symlink()
for parent in root.parents:
 assert stat.S_ISDIR(parent.lstat().st_mode)
for name,row in files.items():
 value=row['text'].encode('utf-8')
 assert len(value)==row['bytes'] and hashlib.sha256(value).hexdigest()==row['sha256']
compile(files['coordinator.py']['text'],'coordinator.py','exec')
os.umask(0o077);root.mkdir(mode=0o700)
for name,row in files.items():
 fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
 with os.fdopen(fd,'wb') as stream:
  stream.write(row['text'].encode('utf-8'));stream.flush();os.fsync(stream.fileno())
os.execv('/usr/bin/python3',['/usr/bin/python3','-I',str(root/'coordinator.py'),'--execute-once'])
'''
    source = ('PACKET_RAW=' + repr(raw_packet.decode('utf-8')) + '\nPACKET_SHA=' + repr(sha(raw_packet)) +
              '\nREMOTE_SOURCE=' + repr(REMOTE) + '\n' + stage)
    ast.parse(source)
    request = {'host': 'pocket4', 'executable': '/usr/bin/sudo', 'args': ['-n', '/usr/bin/python3', '-I', '-'],
               'stdin': source, 'idempotency_key': 'pocket4-nofile-owner-recovery03-android-26case-pair-01-20261105',
               'cpu_quota_percent': 50, 'memory_max_bytes': 268435456, 'nice': 10, 'timeout_seconds': 660}
    payloads = {name: row['text'].encode() for name, row in packet.items()}
    payloads.update({'packet.json': raw_packet, 'stage.py': stage.encode(),
                     'exact-request.json': (json.dumps(request, indent=2) + '\n').encode()})
    output.mkdir(mode=0o700)
    for name, raw in payloads.items():
        with (output / name).open('xb') as stream:
            stream.write(raw)
    pins = {'schema': 1, 'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in payloads.items()},
            'remote_dispatch_performed': False, 'Android_execution_performed': False,
            'actual_matching_build_sha256': 'f3617407f8c624357f4bf9a9cc53e1e78a217b3c0b8bc9a51448c09569e2ea06'}
    with (output / 'SOURCE_PINS.json').open('xb') as stream:
        stream.write((json.dumps(pins, indent=2) + '\n').encode())
    print(json.dumps(pins))


if __name__ == '__main__':
    main()
