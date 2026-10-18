#!/usr/bin/python3
"""Package the completed independent native-debug snapshot; no original target reads."""
import datetime,gzip,hashlib,io,json,re,stat,sys,tarfile
from pathlib import Path
sys.dont_write_bytecode=True
BASE=Path('/workspace/scratch/ae1a8cf05419');SNAP=BASE/'debug-native-review/snapshot';PHASE=BASE/'trillionnium-os-desktop/support/build/evidence/2026-10-17-debug-private-sdk-native';MAX=2097152
ROOT='native-followup/debug-retry1/';FAILED='native-followup/debug/'
def need(ok,message):
 if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 need(json.loads((BASE/'debug-native-review/capture-done.json').read_text())['capture_done'] is True,'snapshot not complete')
 need(not PHASE.exists(),'phase exists; refuse overwrite');capture=json.loads((SNAP/'capture.json').read_text());original={}
 for row in capture['files']:
  raw=(SNAP/'files'/row['path']).read_bytes();need(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'snapshot changed');original[row['path']]=raw
 PHASE.mkdir(exist_ok=False)
 def write(name,b):
  p=PHASE/name;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as stream:stream.write(b)
 def save(name,v):write(name,(json.dumps(v,indent=2)+'\n').encode())
 def chunks(name,data):
  rows=[]
  for i,offset in enumerate(range(0,len(data),MAX)):
   chunk=data[offset:offset+MAX];path=name+'.part-'+str(i+1).zfill(3);write(path,chunk);rows.append({'path':path,'bytes':len(chunk),'sha256':sha(chunk)})
  return {'bytes':len(data),'sha256':sha(data),'chunks':rows}
 def archive(files):
  stream=io.BytesIO()
  with gzip.GzipFile(fileobj=stream,filename='',mode='wb',mtime=0) as zipped:
   with tarfile.open(fileobj=zipped,mode='w|',format=tarfile.GNU_FORMAT) as tar:
    for name,raw,mode in sorted(files):
     item=tarfile.TarInfo(name);item.size=len(raw);item.mode=mode;item.uid=item.gid=item.mtime=0;item.uname=item.gname='';tar.addfile(item,io.BytesIO(raw))
  return stream.getvalue()
 binary={};rawfiles=[]
 for name,data in sorted(original.items()):
  if data.startswith(b'\x7fELF') or name.endswith(('.cpio.gz','/bios.bin')):binary.setdefault(sha(data),{'data':data,'paths':[]})['paths'].append(name)
  else:rawfiles.append((name,data,0o644))
 rows=[];paths={}
 for digest,item in sorted(binary.items()):
  data=item['data'];print(json.dumps({'stage':'compress_binary','sha256':digest,'bytes':len(data)}),flush=True)
  row=chunks('artifacts/'+digest+'.gz',gzip.compress(data,compresslevel=9,mtime=0));row.update(original_bytes=len(data),original_sha256=digest,original_paths=item['paths']);rows.append(row)
  for name in item['paths']:paths[name]={'artifact':digest,'bytes':len(data),'sha256':digest}
 save('artifacts/manifest.json',{'artifacts':rows,'original_paths':paths})
 rawdesc=chunks('raw/originals.tar.gz',archive(rawfiles));rawdesc['members']=[{'member':name,'bytes':len(data),'sha256':sha(data),'mode':mode} for name,data,mode in rawfiles];save('raw.manifest.json',rawdesc);save('capture.json',capture)
 source_rows=json.loads((SNAP/'source-members.json').read_text())['members'];sourcefiles=[]
 for row in source_rows:
  raw=(SNAP/'source'/row['path']).read_bytes();need(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'source snapshot changed');sourcefiles.append((row['member'],raw,row['mode']))
 desc=chunks('source/controls.tar.gz',archive(sourcefiles));desc['members']=source_rows;save('source/members.json',desc)
 for name,source in [('source/tree-objects.json','tree-objects.json'),('source-binding.json','source-binding.json')]:write(name,(SNAP/source).read_bytes())
 copies={}
 for name in ['controller/commands.json','controller/source-head-clean.log','controller/source-inputs.log','controller/post-source-inputs.log','controller/post-source-head-clean.log','controller/fixed-rustc.log','controller/actual-debug.log','run/environment.json','run/commands.json','run/result.json','run/qemu-ready.json','run/entry-artifact-binding.json','run/symbol-artifact.json','run/installed-osdk.json','run/rust-entry.gdb','run/gdb.log','run/gdb-version.log','run/nm-version.log','run/driver-exit-code.txt','run/gdb-exit-code.txt','run/exit-code.txt','run/boot/qemu.json','run/boot/serial.log','run/boot/command.sh','run/boot/environment.log','run/boot/osdk/cargo-osdk.sha256','run/boot/manifest-cleanup.json']:
  logical=ROOT+name;path='readable/retry/'+name;write(path,original[logical]);copies[path]=logical
 for name,data in original.items():
  if name.startswith(FAILED):path='readable/failed/'+name[len(FAILED):];write(path,data);copies[path]=name
 for name in ('controller/run-native-followup-v1.py','controller/run-native-followup-v2.py','controller/environment-correction.json','controller/root-completed-tool.json','controller/actual-host.json'):
  path='readable/'+name;write(path,original[name]);copies[path]=name
 save('readable/manifest.json',{'copies':copies})
 entry=json.loads(original[ROOT+'run/entry-artifact-binding.json']);sdk=json.loads(original[ROOT+'run/installed-osdk.json']);qemu=json.loads(original[ROOT+'run/boot/qemu.json']);binding=json.loads((SNAP/'source-binding.json').read_text());commands=json.loads(original[ROOT+'controller/commands.json']);compile_lines=len(re.findall(rb'^\s*Compiling\s',original[ROOT+'run/boot/gdb_server.log'],re.M))
 report={'schema':'a01-private-sdk-debug-native/1','producer_commit':binding['producer_commit'],'producer_complete_tree':binding['producer_complete_tree'],'derived_kernel_tree':binding['derived_kernel_tree'],'successful_debug_runs':1,'failed_prepare_attempts':1,'failed_prepare_scope':'Initial controller requested a nonexistent nm path; prepare failed before build or VM. Complete failed bytes retained separately.','controller_commands_successful_retry':6,'controller_commands_failed_prepare':4,'cold_build_claimed':False,'target_context':'Existing N2 worktree/target reused and the kernel recompiled for debug; no target-absence precondition or cold-build claim.','compile_lines':compile_lines,'raw_qemu_exit':33,'gdb_exit':0,'gdb_detached':True,'entry_address':entry['entry_address'],'runtime_entry_bytes':entry['expected_bytes'],'kernel_sha256':entry['boot_artifact']['sha256'],'kernel_bytes':entry['boot_artifact']['size'],'symbol_sha256':entry['symbol_artifact']['sha256'],'symbol_bytes':entry['symbol_artifact']['size'],'private_sdk_sha256':sdk['sha256'],'private_sdk_bytes':sdk['size'],'serial_sha256':qemu['serial_sha256'],'serial_bytes':qemu['serial_size'],'captured_original_files':len(original),'unique_binary_payloads':len(binary),'source_controls':len(source_rows),'actual_host':json.loads(original['controller/actual-host.json']),'packaged_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':['Exactly one real successful debug run; initial nm prepare failure is not a second pass.','Target was reused, with actual recompilation retained; this phase does not claim a cold build.','Private SDK path/hash/source/install receipt is a post-build observation, not immutable custody of the executed bytes.','Source closure contains selected exact controls and Git membership, not a second complete kernel import.','Only the exact original symbol ELF was read from target after root DONE; it matched the original debug binding before root could reuse the target.','No hardware KVM/VMX or all-project-blocker closure acceptance is claimed.']}
 save('report.json',report);write('verify.py',(BASE/'debug-native-review/verify-debug.py').read_bytes());write('package.py',Path(__file__).read_bytes());write('snapshot-completed.json',(BASE/'debug-native-review/capture-done.json').read_bytes())
 readme=f'''# Real Rust-entry debug with a private SDK: passed\n\nSuccessful producer `{binding['producer_commit']}` (complete tree `{binding['producer_complete_tree']}`), fixed Asterinas v0.19.0 / `nightly-2026-07-21`, derived kernel tree `{binding['derived_kernel_tree']}`. This phase records one actual SDK build + Rust kernel rebuild + GDB session + QEMU boot. Six source-bound retry controller commands exited 0. The existing N2 target was reused; {compile_lines} actual `Compiling` lines are preserved. **This is not a cold-build claim.**\n\nGDB stopped at Rust `__ostd_main` address `{entry['entry_address']}`, read 32 runtime instruction bytes, matched the exact original symbol ELF and the actual loaded boot ELF, and detached with exit 0. QEMU then completed the small initramfs on one CPU with raw/recorder exit 33, no timeout and every boot marker. The complete {qemu['serial_size']:,}-byte serial is retained at `readable/retry/run/boot/serial.log` (SHA256 `{qemu['serial_sha256']}`). All five owned helper leaders were reaped.\n\n| Preserved exact input | Bytes | SHA256 |\n| --- | ---: | --- |\n| Original symbol ELF | {entry['symbol_artifact']['size']:,} | `{entry['symbol_artifact']['sha256']}` |\n| Loaded boot ELF | {entry['boot_artifact']['size']:,} | `{entry['boot_artifact']['sha256']}` |\n| This run's private SDK | {sdk['size']:,} | `{sdk['sha256']}` |\n\nThe full symbol ELF, loaded ELF/initramfs/BIOS and actual private SDK binary are independently retained as compressed chunks of at most 2 MiB. The original target symbol ELF was captured with stable descriptor/path stats only after root confirmed the successful run ended; complete size/hash matched the original GDB artifact binding. Root was then released to run the next kernel tests; packaging thereafter reads only the private snapshot.\n\n`installed-osdk.json` binds the actual `boot/osdk/bin/cargo-osdk` to this installation's SHA receipt and source Cargo inputs. Its bytes embed the real N2 OSDK source root and install metadata identifies that source. This is a post-build observation, **not immutable custody of previously executed SDK bytes**. Original commands, environment, source hashes and source Git commit/tree/path/blob proof for {len(source_rows)} selected controls are retained, including debug runner and OSDK source. Project root README remains empty.\n\nThe first controller attempt failed at prepare because it requested a nonexistent private-prefix `nm`; no SDK/kernel build or VM ran in that attempt. Its four completed commands, failed result and full logs remain under `readable/failed/`, with both controller bytes and the exact correction. The retry selects the actual `nm` through the explicit restored PATH and uses a fresh output. This is one failure followed by one real pass.\n\n```sh\npython3 -I support/build/evidence/2026-10-17-debug-private-sdk-native/verify.py\npython3 -I -O support/build/evidence/2026-10-17-debug-private-sdk-native/verify.py\npython3 -I support/build/evidence/2026-10-17-debug-private-sdk-native/verify.py --restore /absolute/new-directory\n```\n\nThe verifier checks retained inputs, exact GDB PC/runtime-byte/symbol/boot binding, complete serial, private SDK receipt/source, both attempts, source Git membership and full package coverage. Verification and optional reconstruction execute no original controller, SDK, compiler, debugger or VM. Original file identities and target outputs are not recreated.\n'''
 write('README.md',readme.encode());write('SHA256SUMS',''.join(sha(p.read_bytes())+'  '+p.relative_to(PHASE).as_posix()+'\n' for p in sorted(PHASE.rglob('*')) if p.is_file()).encode());print(json.dumps({'phase':str(PHASE),'originals':len(original),'source_controls':len(source_rows),'unique_binary_payloads':len(binary),'compile_lines':compile_lines,'kernel_sha256':report['kernel_sha256'],'symbol_sha256':report['symbol_sha256']},indent=2),flush=True)
if __name__=='__main__':main()
