import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path('/home/alex/work/pocket4-native-typed-ingress-builder467-source-resume-compile-01-20261105')
EXPECTED = {'go-control-result.json': {'bytes': 44083, 'sha256': '391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674'}, 'image-tools-result.json': {'bytes': 34633, 'sha256': 'b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292'}, 'prior-compile01-failure.json': {'bytes': 7681, 'sha256': '44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3'}, 'registry-result.json': {'bytes': 211021, 'sha256': 'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993'}, 'rust193-tools-recheck-read03-result.json': {'bytes': 31452, 'sha256': '60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb'}, 'selected-build.stdout': {'bytes': 2121, 'sha256': '82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d'}, 'selection-result.json': {'bytes': 14132, 'sha256': '185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf'}, 'typed-lock-derivation.json': {'bytes': 6051, 'sha256': 'c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0'}, 'typed-root-trees-result.json': {'bytes': 51842, 'sha256': '0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8'}, 'compiled-parent466-manifest.json': {'bytes': 91758, 'sha256': 'f09b908745cf294735f897a64d0d956a207d27f78277781f536d5059bb856d0f'}, 'compiled-parent466-result.json': {'bytes': 98764, 'sha256': '2d6c80a29e957b1e97764d8785257eb47c3d0b899f301e64c9a9c418e96ea0ab'}, 'expected-builder467-manifest.json': {'bytes': 91945, 'sha256': '15d8ee7e28d80d90bd0543abd0dbe32fde791890eadc062ec1ecdf52098d6336'}, 'compile_builder.py': {'bytes': 78230, 'sha256': '276d69cc6b5c15575143f071b92aca1744328a18ce3475bcedd90dd018f2ef03'}, 'delta/tools/droidloom-source/src/lib.rs': {'bytes': 44272, 'sha256': '40153ed05004620876fc6ef240b9d89373781baee3111bbbd3c65d446c31e5b3'}, 'delta/tools/droidloom-update/src/android.rs': {'bytes': 269024, 'sha256': 'a48aa5db24d22df56939562a125567aaea9f26fd28a75230270c89f63d4cf8d3'}, 'delta/tools/droidloom-update/src/main.rs': {'bytes': 21215, 'sha256': 'c75a0b03c2f3827a946e360ea8747665e183cf9f495460c24e29d176ae678172'}, 'delta/tools/droidloom-source/src/resume.rs': {'bytes': 38061, 'sha256': '18e525e7fa1cf24a5d5a2ea9ce4673297f31bde6b45655bd121c83850acfc9f7'}}
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('staged source member set differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        if not name or path.is_absolute() or '..' in path.parts or str(path)!=name:raise RuntimeError('noncanonical staged source path')
        raw=text.encode('utf-8')
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('staged source pin mismatch: '+name)
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned root parent aliases non-directory')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    source=ROOT/'control-source';source.mkdir(mode=0o700)
    for name,text in packet.items():
        path=source/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        for parent in [path.parent,*path.parent.parents]:
            if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('staged parent is not a real directory')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode('utf-8'));stream.flush();os.fsync(stream.fileno())
    raw=(json.dumps({'schema':1,'files':EXPECTED,'Main_actions':0,'only_owned_root_written':True},indent=2)+'\n').encode()
    fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'compile_builder.py'),'--execute-once'],{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
