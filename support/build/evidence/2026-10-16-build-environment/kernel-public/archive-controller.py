#!/usr/bin/env python3
"""Package frozen next9 records. Reads saved scratch and immutable Git only."""
import gzip,hashlib,io,json,pathlib,re,shutil,struct,subprocess,tarfile
BASE=pathlib.Path('/workspace/scratch/ae1a8cf05419');REPO=BASE/'trillionnium-os-desktop'
ROOT=REPO/'support/build/evidence/2026-10-16-build-environment'
SRC=BASE/'next9-native';HOST=BASE/'next9-root-host-recheck'
OUT=ROOT/'kernel-public';HOUT=ROOT/'host-recheck'
COMMIT='ff040c6d5afbc4e26a249022093b8090181f6176'
TREE='eb16c5ef5fe8adf3a9249e19a7674cec7b2e359f'
def sha(data):return hashlib.sha256(data).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=REPO)
def write(root,name,obj):
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,indent=2)+'\n')
def copy(source,root,name):
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source.read_bytes())
def checksum(root):
 files=[p for p in sorted(root.rglob('*')) if p.is_file() and p.name!='SHA256SUMS']
 (root/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(root).as_posix()+'\n' for p in files))
 for line in (root/'SHA256SUMS').read_text().splitlines():
  h,name=line.split('  ',1);assert sha((root/name).read_bytes())==h
 return dict(path=str(root),files=len(files)+1,bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),sha256sums_sha256=sha((root/'SHA256SUMS').read_bytes()))

assert git('rev-parse',COMMIT+'^{tree}').decode().strip()==TREE
OUT.mkdir(parents=True,exist_ok=True);HOUT.mkdir(parents=True,exist_ok=True)
copy(pathlib.Path(__file__),OUT,'archive-controller.py')
result=json.loads((SRC/'result.json').read_text());assert result['source_commit']==COMMIT and result['source_tree']==TREE and result['passed']
assert result['controller_sha256']==sha((SRC/'controller.py').read_bytes())
sourcepaths=['support/build/kernel.sh','support/build/kernel-supervisor.py','support/build/minimal.mk','support/build/minimal/Cargo.lock','support/build/minimal/OSDK.toml','support/build/record-qemu.py','support/build/verify-source.py','support/build/cleanup-manifest.py','support/build/minimal/prepare-initramfs.py','support/build/minimal/init','kernel/asterinas/osdk/src/commands/build/bin.rs']
rows=[]
for p in sourcepaths:
 try:data=git('show',COMMIT+':'+p)
 except subprocess.CalledProcessError:continue
 blob=git('rev-parse',COMMIT+':'+p).decode().strip();mode=git('ls-tree',COMMIT,p).decode().split()[0]
 rows.append(dict(path=p,git_blob=blob,git_mode=mode,bytes=len(data),sha256=sha(data)))
fixed=[]
supervisors=[];bindings=[];elfs=[];initrds=[]
for run in result['runs']:
 target=run['target'];base=SRC/target;inv=json.loads((base/'invocation.json').read_text());assert inv==run
 console=(base/'console.log').read_bytes();assert sha(console)==run['console_sha256'] and len(console)==run['console_bytes']
 parsed=[json.loads(line.split(' ',1)[1]) for line in console.decode().splitlines() if line.startswith('A01_KERNEL_SUPERVISOR ')]
 assert len(parsed)==1 and parsed[0]['raw_worker_exit']==0 and parsed[0]['exit_code']==0 and parsed[0]['worker_reaped']
 supervisors.append(dict(target=target,record=parsed[0]))
 assert len(re.findall(rb'^\s*Compiling ',console,re.M))==run['compiling_lines']
 gz=(base/'kernel.elf.gz').read_bytes();raw=gzip.decompress(gz);assert len(raw)==run['kernel_bytes'] and sha(raw)==run['kernel_sha256'] and sha(gz)==run['kernel_gzip_sha256'];assert raw[:5]==b'\x7fELF\x02';elf_machine=struct.unpack_from('<H',raw,18)[0]
 name='artifacts/'+target+'.kernel.elf.gz';copy(base/'kernel.elf.gz',OUT,name);elfs.append(raw)
 bindings.append(dict(saved_input=target+'/kernel.elf.gz',archived=name,gzip_sha256=sha(gz),gzip_bytes=len(gz),raw_sha256=sha(raw),raw_bytes=len(raw),elf_class=2,outer_elf_e_machine=elf_machine,actual_build_and_qemu_target='x86_64',captured_identity=run['kernel_read_identity']))
 init=(base/'run/initramfs.cpio.gz').read_bytes();initrds.append(init)
 im=json.loads((base/'run/initramfs-manifest.json').read_text());assert len(init)==im['image_size'] and sha(init)==im['image_sha256'] and sha(gzip.decompress(init))==im['uncompressed_sha256']
 clean=json.loads((base/'run/manifest-cleanup.json').read_text());assert clean['passed'] and clean['outcome']=='owned_removed' and clean['custody_removed']
 for fname in ['run-exit-code.txt','make-exit-code.txt','log-exit-code.txt','manifest-cleanup-exit-code.txt']:assert (base/'run'/fname).read_text().strip()=='0'
 env=(base/'run/environment.log').read_text();assert COMMIT in env
 for key,value in result['environment'].items():
  if key in ['MAKEFLAGS','MFLAGS','GNUMAKEFLAGS','MAKEFILES','MAKEOVERRIDES','MAKELEVEL']:
   assert key+'_INHERITED='+value+'\n' in env and key+'_EFFECTIVE=<unset>\n' in env
 inputs=json.loads((base/'run/source-inputs.json').read_text());assert inputs['passed'] and inputs['errors']==[] and inputs['checked_files']==118
 for path,expected in inputs['input_sha256'].items():assert sha(git('show',COMMIT+':kernel/asterinas/'+path))==expected
 fixed.append(dict(target=target,checked_files=118,saved_passed=True,six_saved_input_sha256_checked_against_exact_git=True))
 for fname in ['command.sh','environment.log','initramfs-manifest.json','source-inputs.json','manifest-cleanup.json','run-exit-code.txt','make-exit-code.txt','log-exit-code.txt','manifest-cleanup-exit-code.txt']:
  copy(base/'run'/fname,OUT,target+'/'+fname)
 copy(base/'invocation.json',OUT,target+'/invocation.json')
assert elfs[0]==elfs[1];assert initrds[0]==initrds[1]
copy(SRC/'kernel/run/initramfs.cpio.gz',OUT,'artifacts/initramfs.cpio.gz')
cpio=gzip.decompress(initrds[0]);pos=0;cpio_entries={}
while pos<len(cpio):
 assert cpio[pos:pos+6]==b'070701'
 fields=[int(cpio[pos+6+i*8:pos+14+i*8],16) for i in range(13)];mode,uid,gid,mtime,size,namesize=fields[1],fields[2],fields[3],fields[5],fields[6],fields[11]
 name=cpio[pos+110:pos+110+namesize-1].decode();start=(pos+110+namesize+3)&~3;data=cpio[start:start+size];pos=(start+size+3)&~3
 if name=='TRAILER!!!':break
 cpio_entries[name]=dict(mode=format(mode,'06o'),uid=uid,gid=gid,mtime=mtime,size=size,sha256=sha(data))
im=json.loads((SRC/'kernel/run/initramfs-manifest.json').read_text())
assert set(cpio_entries)==set(r['path'] for r in im['entries'])
for row in im['entries']:assert {k:row[k] for k in cpio_entries[row['path']]}==cpio_entries[row['path']]
assert cpio_entries['init']['sha256']==sha(git('show',COMMIT+':support/build/minimal/init'))
assert cpio_entries['test/boot_hello.sh']['sha256']==sha(git('show',COMMIT+':kernel/asterinas/test/initramfs/src/boot_hello.sh'))
write(OUT,'initramfs-independent-check.json',dict(passed=True,newc_entries=len(cpio_entries),entries=cpio_entries,all_saved_manifest_fields_match_newc=True,init_matches_exact_git=True,upstream_smoke_matches_exact_git=True))
bindings.append(dict(saved_inputs=['kernel/run/initramfs.cpio.gz','run_kernel/run/initramfs.cpio.gz'],archived='artifacts/initramfs.cpio.gz',sha256=sha(initrds[0]),bytes=len(initrds[0]),byte_identical=True))
q=json.loads((SRC/'run_kernel/run/qemu.json').read_text());serial=(SRC/'run_kernel/run/serial.log').read_bytes()
assert q['raw_exit_code']==33 and not q['timed_out'] and sha(serial)==q['serial_sha256']==result['runs'][1]['serial_sha256'] and len(serial)==q['serial_size']
assert q['artifacts']['-kernel']['sha256']==sha(elfs[1]) and q['artifacts']['-initrd']['sha256']==sha(initrds[1])
for option,value in [('-machine','q35'),('-accel','tcg'),('-cpu','max'),('-m','512M'),('-smp','1')]:assert q['argv'][q['argv'].index(option)+1]==value
assert b'TRILLIONNIUM_A01_BOOT_OK' in serial and b'TRILLIONNIUM_A01_CPU_COUNT=1' in serial and b'TRILLIONNIUM_A01_INIT_BEGIN' in serial
assert not any(arg in q['argv'] for arg in ['-drive','-hda','-hdb','-netdev','-nic'])
copy(SRC/'run_kernel/run/qemu.json',OUT,'run_kernel/qemu.json')
(OUT/'run_kernel/serial.log.gz').write_bytes(gzip.compress(serial,mtime=0))
for call in result['guard_calls']:
 assert call['exit']==2 and call['output_absent_after'] and call['workspace_lock_absent_after'] and call['target_absent_after'] and sha((SRC/call['log']).read_bytes())==call['log_sha256']
lock=(SRC/'generated-normal.Cargo.lock').read_bytes();lr=json.loads((SRC/'generated-normal-lock.json').read_text())
assert lock==git('show',COMMIT+':support/build/minimal/Cargo.lock') and sha(lock)==lr['sha256'] and len(lock)==lr['bytes'] and lr['exact_committed_minimal_lock']
assert lr['before']==lr['after']==lr['public_after']
copy(SRC/'generated-normal.Cargo.lock',OUT,'provenance/generated-normal.Cargo.lock');copy(SRC/'generated-normal-lock.json',OUT,'provenance/generated-normal-lock.json')
publication=json.loads((BASE/'next9-publication-receipt.json').read_text());assert len(publication['publications'])==2 and publication['publications'][-1]['remote_commit']==COMMIT and publication['publications'][-1]['tree']==TREE
copy(BASE/'next9-publication-receipt.json',OUT,'source-publication-receipt.json')
write(OUT,'source-bindings.json',dict(source_commit=COMMIT,source_tree=TREE,ordered_parents=git('show','-s','--format=%P',COMMIT).decode().strip().split(),files=rows,kernel_subtree=git('rev-parse',COMMIT+':kernel/asterinas').decode().strip(),core_subtree=git('rev-parse',COMMIT+':kernel/asterinas/kernel/core').decode().strip(),ostd_subtree=git('rev-parse',COMMIT+':kernel/asterinas/ostd').decode().strip(),fixed_source=fixed,live_target_or_manifest_read=False))
osdk=git('show',COMMIT+':kernel/asterinas/osdk/src/commands/build/bin.rs').decode();assert 'Set EM_386 (0x0003) to em_machine.' in osdk
write(OUT,'artifact-bindings.json',dict(artifacts=bindings,outer_elf_machine_note='OSDK deliberately sets EM_386 for QEMU multiboot loading; exact source kernel/asterinas/osdk/src/commands/build/bin.rs contains the assignment',normal_build_and_boot_elf_byte_equal=True,comparison_scope='one fresh-target build then cached run_kernel, not two clean builds or cross-path/cross-host repeatability',serial=dict(archive='run_kernel/serial.log.gz',raw_sha256=sha(serial),raw_bytes=len(serial),gzip_sha256=sha((OUT/'run_kernel/serial.log.gz').read_bytes()))))
write(OUT,'supervisor-receipts.json',supervisors)
write(OUT,'outer-completion.posthoc.json',dict(kind='coordinator-observed actual tool completion, transcribed during packaging',actual_tool_session_id=47989,actual_outer_exit=0,provenance='root assignment explicitly reports completed tool47989 exit0',not_inferred_from_result_json=True))
binary={'kernel/kernel.elf.gz','run_kernel/kernel.elf.gz','kernel/run/initramfs.cpio.gz','run_kernel/run/initramfs.cpio.gz'}
rawfiles=[p for p in sorted(SRC.rglob('*')) if p.is_file() and p.relative_to(SRC).as_posix() not in binary]
buf=io.BytesIO();members=[]
with tarfile.open(fileobj=buf,mode='w') as tar:
 for p in rawfiles:
  name=p.relative_to(SRC).as_posix();data=p.read_bytes();ti=tarfile.TarInfo(name);ti.size=len(data);ti.mode=0o644;ti.mtime=0;tar.addfile(ti,io.BytesIO(data));members.append(dict(path=name,bytes=len(data),sha256=sha(data)))
(OUT/'raw.tar.gz').write_bytes(gzip.compress(buf.getvalue(),mtime=0));write(OUT,'members.json',dict(archive='raw.tar.gz',members=members))
with tarfile.open(OUT/'raw.tar.gz','r:gz') as tar:
 assert [m.name for m in tar.getmembers()]==[r['path'] for r in members]
 for row in members:assert sha(tar.extractfile(row['path']).read())==row['sha256']
write(OUT,'report.json',dict(result,scope='Real full Asterinas kernel fresh-target source build followed by one cached real boot under isolated inherited Make controls',actual_tool_session_id=47989,actual_tool_outer_exit=0,independent_saved_copy_checks=True,live_target_or_manifest_read=False,supervised_workers_reaped=[r['record']['worker_reaped'] for r in supervisors],raw_text_archive_members=len(members),compressed_binary_artifacts_not_nested_in_raw=True,generated_normal_lock_verified=True))
write(OUT,'archive-validation.json',dict(passed=True,raw_members=len(members),raw_sha256=sha((OUT/'raw.tar.gz').read_bytes()),elf_copies_decompressed_and_byte_compared=True,initramfs_copies_byte_compared=True,serial_hash_and_boot_markers_verified=True,qemu_kernel_initrd_hash_bound=True,source_git_bindings_checked=True,generated_lock_matches_exact_committed_minimal=True,all_exit_and_cleanup_receipts_zero=True,live_target_or_manifest_read=False))
(OUT/'README.md').write_text('''# Actual public kernel build and boot with inherited Make controls

Tested source: `ff040c6d5afbc4e26a249022093b8090181f6176`, tree `eb16c5ef5fe8adf3a9249e19a7674cec7b2e359f`. Fixed Asterinas v0.19.0, nightly-2026-07-21. Actual coordinator tool session **47989 exited 0**.

The public `support/build/kernel.sh kernel` compiled the complete kernel from an absent target (279 actual compilation lines, including core, alloc, aster-core and asterinas). The subsequent `support/build/kernel.sh run_kernel` reused that target and booted **one actual QEMU guest**, raw exit **33**. Both commands exited 0; both worker leaders were reaped; manifest custody cleanup exited 0 with `owned_removed`. The build and run snapshots contain the same 8,266,576-byte ELF, SHA256 **d90ebc3210e74271252a6d1f75ca22a16a569a8b48a99805d30d3d99124b9306**. This is one clean build followed by a cached boot, not two clean builds or cross-path/host reproducibility.

Both invocations deliberately inherited `MAKEFLAGS=nt`, `MFLAGS=-n`, `GNUMAKEFLAGS=--ignore-errors`, an error-producing `MAKEFILES`, `MAKEOVERRIDES=TARGET_ARCH=riscv64` and `MAKELEVEL=73`. Production metadata preserves the inherited values and records every effective key as unset; actual compilation and boot still occurred. Two preceding real public entry calls with empty and nonempty `CARGO_ENCODED_RUSTFLAGS` each exited 2 before creating output, workspace lock or target. Removing that variable allowed the same public kernel argv to succeed. Exact fixture, controller, calls and logs are retained.

QEMU 8.2.2 used x86_64 q35, TCG CPU max, 1 vCPU, fixed 512MiB, SeaBIOS and serial, with no data disk or network backend. The 1,107,990-byte BusyBox initramfs is SHA256 `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`. The retained serial bytes contain init, CPU-count=1 and BOOT_OK markers. This is the derived Rust kernel executing its initramfs, not host Linux or an ISO installer.

`raw.tar.gz` retains every saved text/metadata output, complete console, complete serial, original controller, guards and generated normal lock. Its member hashes are in `members.json`. Compressed ELF copies remain separately bound to each invocation, with one shared verified initramfs. Readable commands/environment/QEMU/cleanup/source receipts are copied out. `source-bindings.json` links the tested commit/tree and wrapper inputs to immutable Git objects. The post-run generated normal lock was captured by root with stable fd/public identities, is retained under `provenance/`, and independently matches the exact committed minimal lock (SHA256 b42d8fff136d80a5f8159356882096996991e05975d8da9c81ad9db9bdb06e10).

Packaging consumed only frozen saved copies and immutable Git objects. It never read the live target or manifest. Saved source checks report 118 verified inputs, with the six recorded digest values independently checked against the tested Git commit. Original absolute paths are actual run provenance; use the repository's normal preparation/build commands for a new machine. No HOS2 driver, scheduler limits, SMP/VMX or persistence acceptance is claimed.
''')

# Separate root host repetition: keep exact originals and validate all six receipts.
for p in sorted(HOST.rglob('*')):
 if p.is_file():copy(p,HOUT,p.relative_to(HOST))
host=json.loads((HOST/'report.json').read_text());assert host['source_commit']==COMMIT and host['source_tree']==TREE and host['all_passed'] and host['host_executions']==112 and host['distinct_tests']==56
counts=[]
for receipt in host['receipts']:
 log=(HOST/receipt['log']).read_bytes();assert receipt['actual_exit']==0 and len(log)==receipt['log_bytes'] and sha(log)==receipt['log_sha256']
 matches=re.findall(rb'Ran (\d+) tests in ',log);assert matches==[str(receipt['expected_tests']).encode()] and b'\nOK\n' in log
 inv=json.loads((HOST/(receipt['log'].removesuffix('.log')+'.invocation.json')).read_text());assert inv==receipt
 counts.append(dict(log=receipt['log'],actual_tests=int(matches[0]),actual_exit=0,argv=receipt['argv'],sha256=sha(log)))
assert sum(r['actual_tests'] for r in counts)==112
blobs=[]
for path,h in host['source_inputs_sha256'].items():
 data=git('show',COMMIT+':'+path);assert sha(data)==h;blobs.append(dict(path=path,git_blob=git('rev-parse',COMMIT+':'+path).decode().strip(),bytes=len(data),sha256=h))
write(HOUT,'archive-verification.json',dict(passed=True,source_commit=COMMIT,source_tree=TREE,source_inputs_verified_against_git=blobs,all_6_actual_invocations_and_log_hashes_checked=counts,host_executions=112,distinct_tests=56,modes=['-I','-I -O'],actual_tool_session_id=56957,actual_outer_exit=0,actual_outer_exit_provenance='root assignment reports completed tool session56957 exit0',prior_agent_runs_overlap=True,total_distinct_is_not_224=True,live_target_or_manifest_read=False))
(HOUT/'README.md').write_text('''# Additional root host recheck

Actual root tool session **56957 exited 0** on tested source `ff040c6d5afbc4e26a249022093b8090181f6176`, tree `eb16c5ef5fe8adf3a9249e19a7674cec7b2e359f`. Six exact invocation receipts and all raw logs are retained: kernel runner 30, supervisor 9 and kernel-test lifecycle 17, each under `-I` and `-I -O`, totaling **112 executions of 56 distinct tests**, all passing.

This repeats the separate implementation agent's 112 executions. If totaling actual host executions, those are 224 repeated executions; they are **not 224 distinct tests**. The root recheck removed the listed runner/Cargo/Rustup/Make environment keys before launching child tests, recorded exact argv/cwd/times/exit/log hash and compared six source input hashes before/after. Packaging independently checked every retained receipt, actual unittest count, zero exit, log bytes/hash and source digest against immutable Git. The original controller/report remain unchanged. No Cargo, VM, target or live manifest access occurred during packaging.
''')
print(json.dumps(dict(kernel_public=checksum(OUT),host_recheck=checksum(HOUT)),indent=2))
