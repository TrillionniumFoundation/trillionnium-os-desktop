import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path('/home/alex/work/pocket4-native-typed-ingress-builder465-compile-01-20261105')
EXPECTED = {'go-control-result.json': {'bytes': 44083, 'sha256': '391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674'}, 'image-tools-result.json': {'bytes': 34633, 'sha256': 'b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292'}, 'registry-result.json': {'bytes': 211021, 'sha256': 'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993'}, 'rust193-tools-read02-result.json': {'bytes': 9419, 'sha256': '45d3a3307cf40c57c1835f1a275be7cb2e920f0d2b703880756ce0bd89386cfd'}, 'selected-build.stdout': {'bytes': 2121, 'sha256': '82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d'}, 'selection-result.json': {'bytes': 14132, 'sha256': '185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf'}, 'compile_builder.py': {'bytes': 66298, 'sha256': '2742d19a6de247655a8f3ae067e970b6e753f1cdae0c053de1f0587b088f84e5'}, 'compiled-parent462-manifest.json': {'bytes': 91148, 'sha256': '7eaf421cc911a8fec13945099f8d3758bada44b2331e4698dbefd472f535c8da'}, 'compiled-parent462-result.json': {'bytes': 136350, 'sha256': 'f9a3dd01d9ebdb60a0e6a34ee99e3b1a2f646a30191eda3643cee5ca36ff544f'}, 'expected-builder465-manifest.json': {'bytes': 91758, 'sha256': '6b15e35c79575f2da99fcaf383a29e1d0ddcfaa34f9bc9bb5ae070fb3367ee10'}, 'typed-root-trees-result.json': {'bytes': 51842, 'sha256': '0088aaea045f1c0e048db1a65184e536495f3d0d8a9721cd668bdfa0016b43e8'}, 'typed-lock-derivation.json': {'bytes': 6051, 'sha256': 'c5cd3f0efd5519b8e724a42b7fc27850e20dc5a5ea55fff868366e902b56c3e0'}, 'delta/android/manifest/m2-role-ingress-source-lock.json': {'bytes': 86293, 'sha256': 'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54'}, 'delta/android/native-role-ingress/typed-ingress02-framework.patch': {'bytes': 17019, 'sha256': '5a6258c4e60446956cb164ef6796a302e2fb9d48e7f41263572ed51f44015493'}, 'delta/tools/droidloom-update/src/android.rs': {'bytes': 268218, 'sha256': '32d465c001be935f2d460995257da40fed15026b7c805367c18bbc6cd81dac6b'}, 'delta/tools/droidloom-update/src/main.rs': {'bytes': 21002, 'sha256': '0a457dc7952eb531bdf7153ccce73f59ad1f2c39132045a6ea755b4ac10eeaa0'}, 'delta/tools/droidloom-update/src/native_role_ingress.rs': {'bytes': 17957, 'sha256': '760b1eae408e4bc68d84b1883152a0ef5eb5e7bb8f2de7e0a1ee8b39503c4a68'}}
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
