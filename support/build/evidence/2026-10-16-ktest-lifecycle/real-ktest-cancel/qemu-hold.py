#!/usr/bin/env python3
import hashlib,json,os,sys,time
from pathlib import Path
root=Path('/workspace/scratch/ae1a8cf05419/next7-real-ktest-cancel-controller-01')
real=Path('/usr/bin/qemu-system-x86_64')
args=sys.argv[1:]
if args==['--version']:
 os.execv(str(real),[str(real),*args])
if args.count('-kernel')!=1 or '-S' in args:
 raise SystemExit('expected one real ktest kernel and no preexisting -S')
index=args.index('-kernel')+1
kernel=Path(args[index]).resolve()
actual=[str(real),*args,'-S']
receipt={'kind':'test_only_native_qemu_minus_S_hold','pid':os.getpid(),'group':os.getpgrp(),'requested_argv':sys.argv,'actual_argv':actual,'real_qemu':str(real),'real_qemu_sha256':hashlib.sha256(real.read_bytes()).hexdigest(),'kernel':{'path':str(kernel),'size':kernel.stat().st_size,'sha256':hashlib.sha256(kernel.read_bytes()).hexdigest()},'adaptation':'only append -S; no source, ELF, serial, device or machine change','rust_entry_or_boot_pass':False,'time_ns':time.time_ns()}
for number in range(1,100):
 destination=root/('qemu-launch-%03d.json'%number)
 try:
  with destination.open('x') as output:json.dump(receipt,output,indent=2)
  break
 except FileExistsError:continue
else:raise SystemExit('launch receipt allocation exhausted')
os.execv(str(real),actual)
