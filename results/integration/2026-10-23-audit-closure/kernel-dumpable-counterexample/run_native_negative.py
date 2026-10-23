from pathlib import Path
import gzip,hashlib,json,re,shutil,subprocess,sys,time
out=Path(__file__).resolve().parent/'native-6c26-negative-01';out.mkdir(mode=0o700,exist_ok=False)
audit=out.parent;data=Path('/data/asterinas-audit-build.8tdrjboi');source=data/'inline-signal-rtqueue'
sys.dont_write_bytecode=True;sys.path.insert(0,str(source/'tests/kernel/control'))
from run_proc_boot_identity import pack,unpack
from run_g1c_guest import inspect_probe_elf
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
binary=audit/'dumpable-probe';built=json.loads((audit/'compile-02.json').read_text());linux=json.loads((audit/'linux-reference-01.json').read_text())
assert built['exit']==0 and linux['exit']==0 and sha(binary)==built['binary_sha256']==linux['binary_sha256']
shape=inspect_probe_elf(binary.read_bytes());ordinary=data/'inline-signal-native-6c26-01/ordinary';r=json.loads((ordinary/'result.json').read_text());kernel=ordinary/'product-kernel.elf'
assert r['passed'] and r['source_inputs_unchanged'] and sha(kernel)==r['kernel_elf_sha256']
original=source/'support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz';entries=unpack(gzip.decompress(original.read_bytes()));new=[];found=0
inv=b'if /bin/dumpable-probe; then\n echo DUMPABLE_PROBE_EXIT=0\nelse\n echo DUMPABLE_PROBE_EXIT=$?\nfi\n'
marker=b'echo "TRILLIONNIUM_A01_BOOT_OK"'
for name,fields,content in entries:
 assert name.lstrip('./')!='bin/dumpable-probe'
 if name.lstrip('./')=='init':
  assert content.count(marker)==1;content=content.replace(marker,inv+marker);found+=1
 new.append((name,fields,content))
assert found==1
ino=max(fields[0] for _,fields,_ in entries)+1;new.append(('bin/dumpable-probe',[ino,0o100755,0,0,1,0,0,0,0,0,0,0,0],binary.read_bytes()))
archive=pack(new);assert len(unpack(archive))==len(entries)+1
initrd=out/'initramfs.cpio.gz';initrd.write_bytes(gzip.compress(archive,mtime=0));assert initrd.stat().st_size<=8*1024*1024
bios=out/'bios.bin';shutil.copyfile('/usr/share/seabios/bios-256k.bin',bios)
qemu=Path('/usr/bin/qemu-system-x86_64')
command=[str(qemu),'-kernel',str(kernel),'-initrd',str(initrd),'-bios',str(bios),'-append','earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --','-machine','q35','-accel','kvm','-cpu','host','-m','512M','-smp','1','-nodefaults','-no-user-config','-no-reboot','-nographic','-display','none','-monitor','none','-serial','stdio','-nic','none','-device','isa-debug-exit,iobase=0xf4,iosize=0x04']
report={'command':command,'kernel_source':r['source_head'],'kernel_tree':r['source_tree'],'kernel_sha256':sha(kernel),'kernel_receipt':str(ordinary/'result.json'),'probe_source_sha256':built['source_sha256'],'probe_sha256':sha(binary),'shape':shape,'original_initrd_sha256':sha(original),'injected_initrd_sha256':sha(initrd),'bios_sha256':sha(bios),'qemu_sha256':sha(qemu),'timeout_seconds':120,'memory_mib':512,'smp':1,'only_single_self_created_child':True,'no_injection_or_process_writes':True,'linux_reference_exit':linux['exit'],'status':'running','security_gap_reproduced':False}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');start=time.monotonic();timeout=False
with (out/'serial.log').open('xb') as f:
 try:rc=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=120).returncode
 except subprocess.TimeoutExpired:rc=None;timeout=True
text=re.sub(r'\x1b\[[0-9;]*m','',(out/'serial.log').read_text(errors='replace')).replace('\r','');observations=[]
for line in text.splitlines():
 if line.startswith('{'):
  try:observations.append(json.loads(line))
  except json.JSONDecodeError:pass
sensitive=[v for v in observations if v.get('stage') in ['set0','set0_again'] and ((v.get('operation')=='ptrace_attach_only' and v.get('rc')==0) or (v.get('operation')=='pidfd_getfd_dev_null' and v.get('rc',-1)>=0) or (v.get('operation') in ['maps','mem'] and v.get('rc',-1)>0))]
complete=[v for v in observations if v.get('summary')]
report.update(status='complete',raw_qemu_exit=rc,timed_out=timeout,seconds=time.monotonic()-start,serial_sha256=sha(out/'serial.log'),observations=observations,non_dumpable_successful_sensitive_access=sensitive,security_gap_reproduced=(rc==33 and not timeout and text.count('DUMPABLE_PROBE_EXIT=42')==1 and text.count('TRILLIONNIUM_A01_BOOT_OK')==1 and len(complete)==1 and complete[0].get('all_children_reaped') and bool(sensitive)),production_isolation_qualified=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'raw_qemu_exit':rc,'gap_reproduced':report['security_gap_reproduced'],'successful_sensitive_access':len(sensitive),'out':str(out)}),flush=True)
assert report['security_gap_reproduced'],'expected controlled security negative was not established'
