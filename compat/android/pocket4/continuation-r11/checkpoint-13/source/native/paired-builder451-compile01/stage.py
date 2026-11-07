import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path('/home/alex/work/pocket4-native-generation-builder451-compile-01-20261105')
EXPECTED={'compile_builder.py': {'bytes': 58653, 'sha256': 'e626724aa36d49412aaacd6249687044501438c05492f2176c59ad9c3aadcd5a'}, 'compiled-parent450-manifest.json': {'bytes': 88466, 'sha256': '6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4'}, 'expected-builder451-manifest.json': {'bytes': 88664, 'sha256': 'a5052accd9bb36231a3c59271f8bc35e464e5cf14d702787735feed0d86b7a13'}, 'compiled-parent450-result.json': {'bytes': 57408, 'sha256': 'a1d8fe1e891c876baeff555b18fce9bafe6a895d379d9e55261c6df1981785de'}, 'image-tools-result.json': {'bytes': 34633, 'sha256': 'b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292'}, 'go-control-result.json': {'bytes': 44083, 'sha256': '391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674'}, 'rust193-tools-read02-result.json': {'bytes': 9419, 'sha256': '45d3a3307cf40c57c1835f1a275be7cb2e920f0d2b703880756ce0bd89386cfd'}, 'selection-result.json': {'bytes': 14132, 'sha256': '185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf'}, 'selected-build.stdout': {'bytes': 2121, 'sha256': '82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d'}, 'registry-result.json': {'bytes': 211021, 'sha256': 'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993'}, 'delta/tools/droidloom-update/src/native_bridge.rs': {'bytes': 37984, 'sha256': 'dbdc2047120c3ce607a3127ac261c4ffd9218c09acd5f490f835fae3b79827e0'}, 'delta/tools/droidloom-update/src/main.rs': {'bytes': 18977, 'sha256': '2194bcd16cc7866e925687b9e03c7ebb8ee96ad7a5311cfeb9ac38936800d0ec'}, 'delta/tools/droidloom-update/src/native_generation.rs': {'bytes': 23569, 'sha256': 'bfe0f4046358fa6599b0dc5596f50e593de8dc766b2164e796f80b91c4821c58'}, 'delta/tools/droidloom-update/src/bundle.rs': {'bytes': 14523, 'sha256': '3ee0ec4c91a4b24e0886577760b441e3dd0f8ddd0d8811f90044cf7f8d07e868'}}
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
