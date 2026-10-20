#!/usr/bin/env python3
import hashlib,json,os,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
real=Path('/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root/usr/bin/gdb')
args=sys.argv[1:]
if args==['--version']:
 os.execv(str(real),[str(real),*args])
if args.count('-x')!=1:
 raise SystemExit('expected exactly one original GDB -x script')
index=args.index('-x')+1
original=Path(args[index]).resolve()
if original!=Path('/workspace/scratch/ae1a8cf05419/a01-next6-build/support/build/out/next6-real-debug-cancel-03/rust-entry.gdb'):
 raise SystemExit('unexpected original GDB script path')
raw=original.read_bytes()
lines=raw.decode().splitlines(keepends=True)
markers=[i for i,line in enumerate(lines) if line.startswith('gdb.write("A01_GDB_RUST_ENTRY_BYTES ')]
if len(markers)!=1 or lines[markers[0]+1].strip()!='end':
 raise SystemExit('expected the original verified live-byte marker immediately before Python end')
hold = """import json, os, time
gdb.flush(gdb.STDOUT)
hold_record = {"kind": "real_native_gdb_hold_after_original_live_entry_validation", "gdb_pid": os.getpid(), "group": os.getpgrp(), "pc": hex(pc), "entry_bytes": observed.hex(), "entry_size": len(observed), "hold_seconds": 60}
with open(READY_VALUE, "x") as hold_output:
    json.dump(hold_record, hold_output, indent=2)
    hold_output.write(chr(10))
gdb.write("A01_REAL_CANCEL_HOLD_READY" + chr(10))
gdb.flush(gdb.STDOUT)
time.sleep(60)
"""
hold=hold.replace('READY_VALUE',repr(str(root/'native-gdb-ready.json')))
adapted=''.join(lines[:markers[0]+1])+hold+''.join(lines[markers[0]+1:])
script=root/'adapted-rust-entry.gdb'
compile(adapted.split('python'+chr(10),1)[1].rsplit(chr(10)+'end'+chr(10),1)[0],str(script),'exec')
with script.open('x') as output: output.write(adapted)
args[index]=str(script)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
receipt={"scope":"GDB script adaptation only; no source/ELF modification; cancellation case, not boot pass", "shim_pid":os.getpid(), "original_script":str(original), "original_sha256":hashlib.sha256(raw).hexdigest(), "adapted_script":str(script), "adapted_sha256":digest(script), "insertion":"after original PC/32-byte live verification and byte marker, before Python end; write readiness then sleep(60)", "real_gdb":str(real), "real_gdb_sha256":digest(real), "requested_argv":sys.argv, "actual_argv":[str(real),*args]}
(root/'adaptation.json').write_text(json.dumps(receipt,indent=2)+'\n')
os.execv(str(real),[str(real),*args])
