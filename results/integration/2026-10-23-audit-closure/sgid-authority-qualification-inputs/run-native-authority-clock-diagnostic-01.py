"""Run the byte-identical Linux-qualified SGID probe on a real product ELF."""
from pathlib import Path
import argparse, gzip, hashlib, json, re, shutil, subprocess, sys, time

p=argparse.ArgumentParser()
p.add_argument('--ordinary',type=Path,required=True)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
sys.dont_write_bytecode=True
sys.path.insert(0,str(a.source/'tests/kernel/control'))
from run_proc_boot_identity import pack, unpack
from run_g1c_guest import inspect_probe_elf
DATA=Path('/data/asterinas-audit-build.8tdrjboi')
BASE=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
a.out.mkdir(mode=0o700,exist_ok=False)
receipt=json.loads((a.ordinary/'result.json').read_text())
assert receipt['passed'] and receipt['source_inputs_unchanged']
kernel=a.ordinary/'product-kernel.elf'
assert sha(kernel)==receipt['kernel_elf_sha256']
probe=DATA/'native-authority-clock-diagnostic-01'
assert sha(probe)=='dd46b4b98dc7685583c239a49f7aa94c9ca35ff896e706c94fdaee00dd1021bf'
assert sha(BASE/'work/native_authority_clock_diagnostic.c')=='b9ff4dc1d11062aa29f31ba0dca53ec6bd0fc19bf106082bf9be2c8b1682b899'
inspect_probe_elf(probe.read_bytes())
initramfs=a.source/'support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz'
entries=unpack(gzip.decompress(initramfs.read_bytes()))
invocation=b'''/bin/busybox mkdir -p /run /mnt/sgid-disk
echo CLOCK_DIAGNOSTIC_RAMFS_BEGIN
if /bin/clock-diagnostic /run/clock-check; then echo CLOCK_RAMFS_EXIT=0; else echo CLOCK_RAMFS_EXIT=$?; fi
if /bin/busybox mount -t ext2 /dev/vda /mnt/sgid-disk; then
  echo CLOCK_DIAGNOSTIC_EXT2_BEGIN
  if /bin/clock-diagnostic /mnt/sgid-disk/check; then echo CLOCK_EXT2_EXIT=0; else echo CLOCK_EXT2_EXIT=$?; fi
else echo CLOCK_EXT2_MOUNT_FAILED; fi
'''
marker=b'echo "TRILLIONNIUM_A01_BOOT_OK"'
patched=[]; found=0
for name,fields,data in entries:
    assert name.lstrip('./')!='bin/clock-diagnostic'
    if name.lstrip('./')=='init':
        assert data.count(marker)==1
        data=data.replace(marker,invocation+marker); found+=1
    patched.append((name,fields,data))
assert found==1
patched.append(('bin/clock-diagnostic',[max(f[0] for _,f,_ in entries)+1,0o100755,0,0,1,0,0,0,0,0,0,0,0],probe.read_bytes()))
archive=pack(patched)
assert len(unpack(archive))==len(entries)+1
injected=a.out/'initramfs.cpio.gz'
injected.write_bytes(gzip.compress(archive,mtime=0))
assert injected.stat().st_size<=8*1024*1024
disk=a.out/'clock.ext2'
with disk.open('xb') as f:f.truncate(32*1024*1024)
disk.chmod(0o600)
format_argv=['/usr/sbin/mkfs.ext2','-F','-q','-b','4096','-I','256','-O','none,filetype',str(disk)]
with (a.out/'format.log').open('xb') as log:subprocess.run(format_argv,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
shutil.copyfile('/usr/share/seabios/bios-256k.bin',a.out/'bios.bin')
argv=['/usr/bin/qemu-system-x86_64','-kernel',str(kernel),'-initrd',str(injected),'-bios',str(a.out/'bios.bin'),'-append','earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --','-machine','q35','-accel','kvm','-cpu','host','-m','512M','-smp','1','-nodefaults','-no-user-config','-no-reboot','-nographic','-display','none','-monitor','none','-serial','stdio','-nic','none','-drive','file='+str(disk)+',format=raw,id=sgid,if=none','-device','virtio-blk-pci,bus=pcie.0,addr=0x7,drive=sgid,disable-legacy=on,disable-modern=off','-device','isa-debug-exit,iobase=0xf4,iosize=0x04']
report={'schema':'trillionnium.native-authority-clock-diagnostic.v1','source_head':receipt['source_head'],'source_tree':receipt['source_tree'],'kernel_sha256':sha(kernel),'ordinary_receipt_sha256':sha(a.ordinary/'result.json'),'probe_sha256':sha(probe),'probe_source_sha256':sha(BASE/'work/native_authority_clock_diagnostic.c'),'original_initramfs_sha256':sha(initramfs),'injected_initramfs_sha256':sha(injected),'format_argv':format_argv,'qemu_argv':argv,'guest_deadline_seconds':120,'passed':False,'status':'running','production_authority':False,'g2_complete':False}
def save():(a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
save(); start=time.monotonic(); timed_out=False
with (a.out/'serial.log').open('xb') as log:
    try:code=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=120).returncode
    except subprocess.TimeoutExpired:code=None; timed_out=True
text=re.sub(r'\x1b\[[0-9;]*m','',(a.out/'serial.log').read_text(errors='replace')).replace('\r','')
lines=[line for line in text.splitlines() if line.startswith('CLOCK_DIAGNOSTIC')]
execution_ok=code==33 and not timed_out and text.count('CLOCK_DIAGNOSTIC_COMPLETE cases=16 qualification=0')==2 and text.count('CLOCK_RAMFS_EXIT=0')==1 and text.count('CLOCK_EXT2_EXIT=0')==1 and text.count('TRILLIONNIUM_A01_BOOT_OK')==1
report.update(raw_qemu_exit=code,timed_out=timed_out,diagnostic_lines=lines,execution_passed=execution_ok,authority_qualified=False,passed=False,serial_sha256=sha(a.out/'serial.log'),elapsed_seconds=round(time.monotonic()-start,3),status='complete')
save()
raise SystemExit(0 if execution_ok else 1)
