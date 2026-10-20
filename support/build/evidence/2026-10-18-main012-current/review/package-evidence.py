#!/usr/bin/env python3
"""Package actual A01 execution bytes without rewriting source receipts."""
import datetime, hashlib, io, json, os, pathlib, shutil, stat, tarfile
REPO=pathlib.Path('/workspace/scratch/d7da9e7650f0/a01-current')
ROOT=REPO/'support/build/out/2026-10-18-main012'
DEST=REPO/'support/build/evidence/2026-10-18-main012-current'
RUNTIME=pathlib.Path('/workspace/scratch/d7da9e7650f0/a01-current-runtime')
SOURCE='b39e154ae5a1e9853f57e23f9bee84712ee8ef7e'
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(raw): return hashlib.sha256(raw).hexdigest()
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def copy(src,name):
    target=DEST/name
    target.parent.mkdir(parents=True,exist_ok=True)
    assert not target.exists()
    shutil.copyfile(src,target)
    assert target.read_bytes()==pathlib.Path(src).read_bytes()
    return target
def stable(path,expected_sha=None,expected_size=None):
    path=pathlib.Path(path)
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        assert stat.S_ISREG(before.st_mode)
        with os.fdopen(os.dup(fd),'rb') as stream: raw=stream.read()
        after=os.fstat(fd); live=path.lstat()
        keys=('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')
        assert all(getattr(before,k)==getattr(after,k)==getattr(live,k) for k in keys)
        assert len(raw)==before.st_size
        if expected_sha is not None: assert digest(raw)==expected_sha
        if expected_size is not None: assert len(raw)==expected_size
        return raw,{'source_path':str(path),'observed_at_utc':now(),
            'size':len(raw),'sha256':digest(raw),'mode':stat.S_IMODE(before.st_mode),
            'stat':{k:getattr(before,k) for k in keys},'stable_fd_and_path':True}
    finally: os.close(fd)
archives=[]
def archive(name,entries):
    path=DEST/name
    members=[]
    with tarfile.open(path,'w:xz',preset=6) as output:
        for arcname,source in sorted(entries.items()):
            assert not pathlib.PurePosixPath(arcname).is_absolute() and '..' not in pathlib.PurePosixPath(arcname).parts
            raw,receipt = source if isinstance(source,tuple) else stable(source)
            info=tarfile.TarInfo(arcname)
            info.size=len(raw);info.mode=receipt['mode'];info.mtime=0;info.uid=info.gid=0
            output.addfile(info,io.BytesIO(raw))
            members.append({'path':arcname,**receipt})
        manifest=(json.dumps({'schema':'trillionnium.a01.archive.v1','source_commit':SOURCE,
            'normalization':'tar timestamps and uid/gid zeroed; original bytes and file modes retained',
            'members':members},indent=2)+'\n').encode()
        info=tarfile.TarInfo('ARCHIVE-MANIFEST.json');info.size=len(manifest);info.mode=0o644
        output.addfile(info,io.BytesIO(manifest))
    expected={m['path']:m for m in members}
    with tarfile.open(path,'r:xz') as check:
        actual=check.getmembers()
        assert len(actual)==len(members)+1
        for item in actual:
            assert item.isfile()
            raw=check.extractfile(item).read()
            if item.name=='ARCHIVE-MANIFEST.json': assert raw==manifest
            else:
                entry=expected[item.name]
                assert len(raw)==entry['size'] and digest(raw)==entry['sha256'] and item.mode==entry['mode']
    archives.append({'path':name,'size':path.stat().st_size,'sha256':digest(path.read_bytes()),
        'member_count':len(members)+1,'all_members_verified':True})
    print(json.dumps(archives[-1]),flush=True)
DEST.mkdir(exist_ok=False)

# Complete raw native logs/config/receipts, with binaries and per-stage source
# manifests stored once in their dedicated archives below.
native={}
for path in sorted(ROOT.rglob('*')):
    if not path.is_file(): continue
    rel=path.relative_to(ROOT)
    if rel.parts[0]=='source':continue
    if path.name in ('cargo-osdk','kernel.elf','initramfs.cpio.gz','bios.bin'):continue
    native['native/'+str(rel)]=path
for name in ['a01-current-run-stage.py','a01-current-freeze-kernel.py','a01-current-retry-and-ktest.py','a01-current-close-native.py']:
    native['scripts/'+name]=pathlib.Path('/tmp')/name
archive('native-records.tar.xz',native)

sources={'source/'+str(f.relative_to(ROOT/'source')):f for f in (ROOT/'source').rglob('*') if f.is_file()}
sources['source/capture-source.py']=REPO/'support/build/evidence/2026-10-18-current-main/source/capture-source.py'
audit=pathlib.Path('/tmp/a01-current-audit')
for name in ['audit_source.py','pre-build-paths.json','source-before.json','source-after-native.json']:
    sources['independent-audit/'+name]=audit/name
for path in pathlib.Path('/tmp/a01-current-acquisition').rglob('*'):
    if path.is_file():sources['acquisition/'+path.name]=path
archive('source-records.tar.xz',sources)

boot=json.loads((ROOT/'run_kernel_retry01/qemu.json').read_text())
artifacts={};bindings=[]
for key,name in [('-kernel','boot/kernel.elf'),('-initrd','boot/initramfs.cpio.gz'),('-bios','firmware/bios.bin')]:
    entry=boot['artifacts'][key]
    artifacts[name]=stable(entry['path'],entry['sha256'],entry['size'])
    bindings.append({'member':name,'record':'boot/qemu.json','selector':key,'source_receipt':artifacts[name][1]})
first=json.loads((ROOT/'artifacts-first-build/capture.json').read_text())
frozen,_=stable(first['frozen_path'],first['sha256'],first['bytes'])
assert frozen==artifacts['boot/kernel.elf'][0]
for crate in ['ostd','aster-core']:
    q=json.loads((ROOT/'ktest'/crate/'guests/guest-001/qemu.json').read_text())
    entry=q['artifacts']['-kernel'];name='ktest/'+crate+'.elf'
    artifacts[name]=stable(entry['path'],entry['sha256'],entry['size'])
    bindings.append({'member':name,'record':'ktest/'+crate+'/guests/guest-001/qemu.json',
        'selector':'-kernel','source_receipt':artifacts[name][1],
        'capture_scope':'Post-test stable-FD bytes equal the recorder hash; the ktest recorder itself used these source paths, not a private snapshot.'})
archive('guest-artifacts.tar.xz',artifacts)
write_json(DEST/'artifact-bindings.json',{'source_commit':SOURCE,'first_build_equals_actual_loaded':True,
    'first_build_capture':first,'bindings':bindings,'bios_shared_by_three_guests':True})

# Raw high-value records are also kept as ordinary reviewable files.
for name in ['qemu.json','serial.log','command.sh','manifest-cleanup.json','source-inputs.json']:
    copy(ROOT/'run_kernel_retry01'/name,'boot/'+name)
copy(ROOT/'kernel/command.sh','kernel/command.sh')
copy(ROOT/'kernel/manifest-cleanup.json','kernel/manifest-cleanup.json')
copy(ROOT/'artifacts-first-build/capture.json','kernel/first-artifact.json')
for name in ['kernel-execution.json','run_kernel-execution.json','run_kernel_retry01-execution.json','ktest-execution.json','boot-summary.json']:
    copy(ROOT/name,'executions/'+name)
for name in ['result.json','environment.json','commands.json']:
    copy(ROOT/'ktest'/name,'ktest/'+name)
for crate in ['ostd','aster-core']:
    for name in ['qemu.json','serial.log']:
        copy(ROOT/'ktest'/crate/'guests/guest-001'/name,'ktest/'+crate+'/guests/guest-001/'+name)
    copy(ROOT/'ktest'/crate/'result.json','ktest/'+crate+'/result.json')
for kind in ['prelaunch-failure','post-ktest-manifest']:
    for name in ['observation.json','quarantine.json','OSDK.toml.observed']:
        copy(ROOT/kind/name,'failures/'+kind+'/'+name)
    if (ROOT/kind/'closure.json').exists():copy(ROOT/kind/'closure.json','failures/'+kind+'/closure.json')
copy(ROOT/'run_kernel-driver.log','failures/prelaunch-failure/run_kernel-driver.log')
copy(RUNTIME/'runtime-current.tar.gz','runtime-current.tar.gz')
copy(RUNTIME/'summary.json','runtime-summary.json')
copy(RUNTIME/'archive-verification.json','runtime-archive-verification.json')
copy('/tmp/a01-current-build-review/host-gate.tar.gz','host-gate.tar.gz')
copy('/tmp/a01-current-build-review/host-gate-summary.json','host-gate-summary.json')
copy('/tmp/a01-current-build-review/late-manifest-self-review.json','review/late-manifest-self-review.json')
for path,expected in [('runtime-current.tar.gz','61615a214530b7af47d0206db533c4ebef3298df07bc8d9522b231c2a9f51ca0'),
                      ('host-gate.tar.gz','42d89e0b97c962d65abecbc5f943689264fb4f25057dea2a67aea7fe5e03eee5')]:
    raw=(DEST/path).read_bytes();assert digest(raw)==expected
    archives.append({'path':path,'size':len(raw),'sha256':digest(raw),'previously_independently_verified':True})
copy(pathlib.Path(__file__),'review/package-evidence.py')
write_json(DEST/'archive-index.json',{'source_commit':SOURCE,'created_at_utc':now(),'archives':archives,
    'native_archive_scope':'All actual native output regular files except SDK executable binaries, boot input binaries and per-stage source manifests. Repeated boot binaries are represented once in guest-artifacts; every source receipt is in source-records. SDK hashes, installation receipts and commands are retained.',
    'artifact_archive_scope':'The complete actual loaded boot ELF/initramfs/BIOS, plus both complete test ELFs with hashes matched after testing; no stripped or reconstructed kernel substitution.'})
print(json.dumps({'evidence_directory':str(DEST),'archives':archives,'ready_for_report':True}),flush=True)
