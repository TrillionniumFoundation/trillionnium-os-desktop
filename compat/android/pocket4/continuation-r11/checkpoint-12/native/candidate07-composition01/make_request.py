#!/usr/bin/env python3
"""Create the source-composition request locally. No remote calls."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMOTE = '/home/alex/work/pocket4-candidate07-host-uapi-composition-source-01-20261105'
KEY = 'pocket4-native-candidate07-host-uapi-source-composition-01-20261105'
NAMES = [
    'compose.py', 'references/base-source-contract.py',
    'delta/kernel_api/include/berberis/kernel_api/proc_maps_linux_compat.h',
    'delta/kernel_api/proc_maps_fd_owner.cc', 'delta/kernel_api/proc_maps_path.cc',
    'delta/kernel_api/proc_maps_provenance.cc', 'delta/kernel_api/proc_maps_raw_metadata_owner.cc',
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if not args.write:
        print(json.dumps({'state': 'PLAN_ONLY', 'remote_root': REMOTE, 'idempotency_key': KEY,
                          'payload_files': len(NAMES), 'remote_actions': 0}))
        return
    files = []
    for name in NAMES:
        raw = (HERE / name).read_bytes()
        files.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw), 'content': raw.decode('utf-8')})
    assert files[0]['sha256'] == '8466ad04f84e84b6297687402350b0d1e35e9f2b1ece2ce113748b5df8e7b157'
    packet = encoded({'schema': 1, 'files': files})
    assert len(packet) <= 1048576
    stage = '''import hashlib,json,os,stat,sys
from pathlib import Path,PurePosixPath
raw=sys.stdin.buffer.read(1048577)
assert len(raw)<=1048576 and hashlib.sha256(raw).hexdigest()==PACKET_SHA
packet=json.loads(raw);assert packet['schema']==1
assert os.getuid()==os.geteuid()==1000
root=Path(REMOTE_ROOT)
for path in [root,*root.parents]:
 if path.exists() or path.is_symlink():assert stat.S_ISDIR(path.lstat().st_mode)
assert not root.exists() and [row['path'] for row in packet['files']]==EXPECTED_NAMES
for row in packet['files']:
 relative=PurePosixPath(row['path']);assert relative.parts and not relative.is_absolute() and all(x not in ('','.','..') for x in relative.parts)
 value=row['content'].encode();assert len(value)==row['bytes'] and hashlib.sha256(value).hexdigest()==row['sha256']
assert packet['files'][0]['sha256']==COMPOSER_SHA
os.umask(0o077);root.mkdir(mode=0o700)
for row in packet['files']:
 path=root/row['path'];path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
 with os.fdopen(fd,'wb') as stream:
  value=row['content'].encode();assert stream.write(value)==len(value);stream.flush();os.fsync(stream.fileno())
 assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
os.execv('/usr/bin/python3',['/usr/bin/python3','-I',str(root/'compose.py'),'--execute-once'])
'''
    prefix = ('PACKET_SHA=' + repr(sha(packet)) + '\nREMOTE_ROOT=' + repr(REMOTE) +
              '\nEXPECTED_NAMES=' + repr(NAMES) + '\nCOMPOSER_SHA=' + repr(files[0]['sha256']) + '\n')
    stage = (prefix + stage).encode()
    ast.parse(stage)
    request = {'host': 'pocket4', 'executable': '/usr/bin/python3', 'args': ['-I', '-c', stage.decode()],
               'cwd': '/home/alex/work', 'env': {'PYTHONDONTWRITEBYTECODE': '1'}, 'stdin': packet.decode(),
               'idempotency_key': KEY, 'timeout_seconds': 300, 'cpu_quota_percent': 100,
               'memory_max_bytes': 1073741824, 'nice': 10}
    directory = HERE / 'final-request-01'
    directory.mkdir(mode=0o700)
    output = {'packet.json': packet, 'stage.py': stage, 'exact-request.json': encoded(request)}
    pins = {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in output.items()}
    for name, raw in output.items():
        with (directory / name).open('xb') as stream:
            stream.write(raw)
    with (directory / 'REQUEST_PINS.json').open('xb') as stream:
        stream.write(encoded({'schema': 1, 'files': pins,
                              'payload_files': [{k: row[k] for k in ('path','bytes','sha256')} for row in files],
                              'source_only': True, 'remote_actions': 0, 'Main_actions': 0, 'full_build_started': False}))
    print(json.dumps({'request': pins['exact-request.json'], 'packet': pins['packet.json'], 'payload_files': len(files)}))

if __name__ == '__main__':
    main()
