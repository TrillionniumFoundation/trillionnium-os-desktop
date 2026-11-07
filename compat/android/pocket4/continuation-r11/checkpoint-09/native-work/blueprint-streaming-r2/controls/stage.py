import hashlib, json, os, stat, sys
from pathlib import Path
ROOT = Path('/home/alex/work/pocket4-blueprint-streaming-controls-02-20261105')
EXPECTED = {'run_control.py': {'bytes': 24689, 'sha256': '280a2b0e25782af40e6220a0e29cbe2aa1c35dc584b27df9b489262c4c3e57da'}, 'owned_streaming_test.go': {'bytes': 13896, 'sha256': '6e07b46d2fec835897fdc2bb444571d09ef41d01148d8c3940398e716d8594ef'}, '0009-blueprint-stream-uncached-module-actions.patch': {'bytes': 470, 'sha256': '9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307'}}
def main(packet):
    if os.getuid() != 1000 or os.geteuid() != 1000:
        raise RuntimeError('ordinary operator UID 1000 required')
    if set(packet) != set(EXPECTED):
        raise RuntimeError('unexpected source packet members')
    for name, text in packet.items():
        raw = text.encode('utf-8')
        if len(raw) != EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest() != EXPECTED[name]['sha256']:
            raise RuntimeError('source packet pin mismatch')
    for directory in (ROOT.parent, *ROOT.parent.parents):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise RuntimeError('owned source parent aliases a non-directory')
    if ROOT.exists() or ROOT.is_symlink():
        raise RuntimeError('create-only source root already exists')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    source = ROOT/'source'
    source.mkdir(mode=0o700)
    for name, text in packet.items():
        fd = os.open(source/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(text.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
    with (ROOT/'stage-receipt.json').open('x') as out:
        json.dump({'schema':1, 'files':EXPECTED, 'Main_actions':0, 'only_owned_root_written':True}, out, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    os.execve('/usr/bin/python3', ['/usr/bin/python3','-I','-B',str(source/'run_control.py'),'--execute-once'], {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
