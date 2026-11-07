import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT=Path('/home/alex/work/pocket4-native-generation-builder462-compile-01-20261105')
EXPECTED={'go-control-result.json': {'bytes': 44083, 'sha256': '391ed7920bdc8a0a7ff3797237a8425d51aaa88cd37f29214baca6a7061d8674'}, 'image-tools-result.json': {'bytes': 34633, 'sha256': 'b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292'}, 'registry-result.json': {'bytes': 211021, 'sha256': 'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993'}, 'rust193-tools-read02-result.json': {'bytes': 9419, 'sha256': '45d3a3307cf40c57c1835f1a275be7cb2e920f0d2b703880756ce0bd89386cfd'}, 'selected-build.stdout': {'bytes': 2121, 'sha256': '82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d'}, 'selection-result.json': {'bytes': 14132, 'sha256': '185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf'}, 'compile_builder.py': {'bytes': 64192, 'sha256': '997a1024b3ede93afa4fad33858b00432b95cf73abb6819612b4c096e76e52fc'}, 'compiled-parent451-manifest.json': {'bytes': 88664, 'sha256': 'a5052accd9bb36231a3c59271f8bc35e464e5cf14d702787735feed0d86b7a13'}, 'compiled-parent451-result.json': {'bytes': 129787, 'sha256': '8c72e771c9ed5bd440b36aa8c7c3379b31ce8acccdc2b222fadad9e64cb28096'}, 'expected-builder462-manifest.json': {'bytes': 91148, 'sha256': '7eaf421cc911a8fec13945099f8d3758bada44b2331e4698dbefd472f535c8da'}, 'delta/android/native-generation-art/source/art/libnativebridge/Android.bp': {'bytes': 2840, 'sha256': '33ea5fb3bdcfe55c038ef5599b08fb643276aa50fe05a8757e351bf7478f7e74'}, 'delta/android/native-generation-art/source/art/libnativebridge/droidloom_generation.cc': {'bytes': 2462, 'sha256': '1e43381bdb0eba44777317bb1372346eca99322139c5b2662932724fdc82aa68'}, 'delta/android/native-generation-art/source/art/libnativebridge/droidloom_generation.h': {'bytes': 410, 'sha256': '28facfdf31818b2dd7e4f08b3ca0359dae0e5fdb2f5b243dc7455ac3edd966fe'}, 'delta/android/native-generation-art/source/art/libnativebridge/include/nativebridge/droidloom_generation_protocol.h': {'bytes': 1110, 'sha256': '913d7a0dd717ff9d697bc926906958029b1be7ba9fb612b57218bc40fe6e27dd'}, 'delta/android/native-generation-art/source/art/libnativebridge/include/nativebridge/native_bridge.h': {'bytes': 20874, 'sha256': '664dd6ed2a71d90f4bc3f84ab621d7ebbdedc148284c452d6ca2f8e8d9888760'}, 'delta/android/native-generation-art/source/art/libnativebridge/libnativebridge.map.txt': {'bytes': 1062, 'sha256': '5b64217bcc16eba7083942783b920da59de9e16255ba5a3adb92e8ce7428de31'}, 'delta/android/native-generation-art/source/art/libnativebridge/native_bridge.cc': {'bytes': 24851, 'sha256': '4fc33d917915886fccabaf76dbf7a6bee949cf08cd6b8ac9be429dc8614706a4'}, 'delta/android/native-generation-art/source/art/runtime/Android.bp': {'bytes': 47356, 'sha256': 'deac350bd467f39dddb657c8a137ef7800998d4039381045875cf41fd8af8cf9'}, 'delta/android/native-generation-art/source/art/runtime/native_bridge_art_interface.cc': {'bytes': 5919, 'sha256': 'd71e569e0f782ed461bdc167c6228e35414a02b209072b8cba9b7534bc8b3a5a'}, 'delta/android/native-generation-art/source/art/runtime/runtime.cc': {'bytes': 148153, 'sha256': 'ec7105503380ec505dbe58b822a4ac46edb48311e6093eb3e396d0768e111bc3'}, 'delta/tools/droidloom-update/src/android.rs': {'bytes': 265951, 'sha256': 'f61ab5f52f1eba7258c06dc0f42ae823d1dd66ac397d63e222b02e1ed4969d28'}, 'delta/tools/droidloom-update/src/main.rs': {'bytes': 20107, 'sha256': 'aa6481c47b5adc3c7fc56af5a598b05cf945d5178d108c8050d2e2e01d7ada9c'}, 'delta/tools/droidloom-update/src/native_generation_art.rs': {'bytes': 11106, 'sha256': '2f6f6a799b90c3f534e89ce8015cae5e889bb59966e8894f9fbbfc58214b6905'}}
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
