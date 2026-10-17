#!/usr/bin/env python3
"""Create an A08-only ABI initramfs using A01's exact newc/gzip packer.

No files in A01's kernel or build tree are changed. This only stages probes;
it is NOT a QEMU boot, Binder success, or Android runtime result.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / 'support/build/minimal/prepare-initramfs.py'
INIT = ROOT / 'support/build/minimal/init'
SMOKE = ROOT / 'kernel/asterinas/test/initramfs/src/boot_hello.sh'
MARKER = b'echo "TRILLIONNIUM_A01_BOOT_OK"\n'
INJECT = b'''echo "A08_GUEST_ABI_BEGIN"
if /test/a08-kernel-abi; then
 echo "A08_GUEST_ABI_PASS"
else
 rc=$?
 echo "A08_GUEST_ABI_FAIL:$rc"
 exec /bin/busybox poweroff -f
fi
if /test/a08-binder-abi; then
 echo "A08_GUEST_BINDER_PRIMITIVES_PASS"
else
 rc=$?
 echo "A08_GUEST_BINDER_EXIT:$rc"
fi
echo "A08_GUEST_SECCOMP_BEGIN"
if /test/a08-seccomp-abi; then
 echo "A08_GUEST_SECCOMP_FILTER_PASS"
else
 rc=$?
 echo "A08_GUEST_SECCOMP_EXIT:$rc"
fi
echo "A08_GUEST_SECCOMP_END"
echo "A08_GUEST_ABI_END"
'''


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_a01(path: Path):
    spec = importlib.util.spec_from_file_location('a01_cpio_packer', path)
    if spec is None or spec.loader is None:
        raise ValueError('A01 packer is missing')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for api in ('cpio_entry','check_static_x86_64_elf','APPLETS'):
        if not hasattr(module, api):
            raise ValueError('A01 packer changed API: '+api)
    return module


def compose_init(init: bytes) -> bytes:
    if init.count(MARKER) != 1 or b'TRILLIONNIUM_A01_INIT_BEGIN' not in init:
        raise ValueError('A01 init profile changed: ABI probe injection blocked')
    return init.replace(MARKER, INJECT + MARKER)


def prepare(*, busybox: Path, kernel_probe: Path, binder_probe: Path,
            seccomp_probe: Path,
            dest: Path, manifest: Path, builder: Path = BUILDER,
            a01_init: Path = INIT, smoke: Path = SMOKE) -> dict:
    if dest.resolve() == manifest.resolve() or dest.exists() or manifest.exists():
        raise ValueError('output/manifest collide or already exist')
    a01=load_a01(builder)
    files={'bin/busybox':busybox,'test/a08-kernel-abi':kernel_probe,
           'test/a08-binder-abi':binder_probe,
           'test/a08-seccomp-abi':seccomp_probe}
    for name,path in files.items():
        if not path.is_file():
            raise ValueError('missing static executable: '+name)
        a01.check_static_x86_64_elf(path.read_bytes())
    boot=smoke.read_bytes()
    init=compose_init(a01_init.read_bytes())
    items=[]
    for name in ('bin','dev','etc','proc','root','sbin','sys','test','tmp'):
        items.append((name,stat.S_IFDIR|(0o1777 if name=='tmp' else 0o755),b'',None))
    for name,path in files.items():
        items.append((name,stat.S_IFREG|0o755,path.read_bytes(),None))
    items.extend((('init',stat.S_IFREG|0o755,init,None),
                  ('test/boot_hello.sh',stat.S_IFREG|0o755,boot,None)))
    for name in a01.APPLETS:
        items.append(('bin/'+name,stat.S_IFLNK|0o777,b'busybox','busybox'))
    archive=bytearray()
    entries=[]
    for n,(name,mode,data,link) in enumerate(items,1):
        archive.extend(a01.cpio_entry(name,mode,data,n))
        entries.append({'path':name,'sha256':digest(data),'bytes':len(data),
                        'mode':f'{mode:06o}','link':link})
    archive.extend(a01.cpio_entry('TRAILER!!!',0,b'',len(items)+1))
    archive.extend(b'\0'*(-len(archive)%512))
    out=io.BytesIO()
    with gzip.GzipFile(fileobj=out,filename='',mode='wb',mtime=0) as z:
        z.write(archive)
    content=out.getvalue()
    record={'schema':1,'kind':'a08_asterinas_abi_initramfs',
            'architecture':'x86_64','source':'A01 deterministic newc/gzip packer',
            'packer_sha256':digest(builder.read_bytes()),
            'init_sha256':digest(a01_init.read_bytes()),
            'boot_smoke_sha256':digest(boot),
            'image_sha256':digest(content),'image_size':len(content),
            'entries':entries,'guest_executed':False,'android_qualified':False}
    dest.parent.mkdir(parents=True,exist_ok=True)
    manifest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(content)
    manifest.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
    return record


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--busybox',type=Path,required=True)
    p.add_argument('--kernel-probe',type=Path,required=True)
    p.add_argument('--binder-probe',type=Path,required=True)
    p.add_argument('--seccomp-probe',type=Path,required=True)
    p.add_argument('--dest',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=prepare(busybox=args.busybox,kernel_probe=args.kernel_probe,
                       binder_probe=args.binder_probe,seccomp_probe=args.seccomp_probe,
                       dest=args.dest,
                       manifest=args.manifest)
        print(json.dumps({'status':'prepared_not_booted','sha256':result['image_sha256']}))
        return 0
    except (OSError,ValueError) as e:
        print('A08 guest preparation blocked: '+str(e),file=sys.stderr)
        return 3

if __name__=='__main__':
    sys.exit(main())
