#!/usr/bin/env python3
"""Verify preserved ordinary private-SDK N2 proof without source targets or execution."""
import base64,gzip,hashlib,io,json,os,re,shlex,stat,struct,tarfile
from pathlib import Path,PurePosixPath
BASE=Path(__file__).resolve().parent;MAX=2097152;ROOT='private-sdk-native-N2/';WORK='/tmp/trillionnium-a01-private-sdk-N2';TARGET=WORK+'/kernel/asterinas/target'
def need(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def rel(n):
 p=PurePosixPath(n);need(bool(n) and not p.is_absolute() and str(p)==n and '..' not in p.parts and '.' not in p.parts and '\\' not in n,'unsafe path '+n);return p
def read(n):
 p=BASE.joinpath(*rel(n).parts);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  a=os.fstat(fd);need(stat.S_ISREG(a.st_mode),'nonregular package input')
  with os.fdopen(fd,'rb',closefd=False) as f:b=f.read()
  z=os.fstat(fd);need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns),'package input changed');return b
 finally:os.close(fd)
def load(n):return json.loads(read(n))
def check(b,r,n):need(len(b)==r['bytes'] and sha(b)==r['sha256'],'bytes/SHA differ '+n)
def container(r,n):
 parts=[]
 for row in r['chunks']:
  b=read(row['path']);check(b,row,row['path']);need(0<len(b)<=MAX,'oversize/empty chunk');parts.append(b)
 b=b''.join(parts);check(b,r,n);return b
def archive(r,n,source=False):
 b=container(r,n);wanted={x['member']:x for x in r['members']};need(len(wanted)==len(r['members']),'duplicate member descriptor');got={}
 with tarfile.open(fileobj=io.BytesIO(b),mode='r:gz') as t:
  for i in t:
   rel(i.name);need(i.isfile() and i.name in wanted and i.name not in got,'unsafe/duplicate archive entry');row=wanted[i.name];need(i.mode==row['mode'] and i.uid==i.gid==i.mtime==0 and i.uname==i.gname=='','tar metadata differs');raw=t.extractfile(i).read();check(raw,row,i.name)
   if source:need(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==row['git_blob'],'Git blob differs')
   got[i.name]=raw
 need(set(got)==set(wanted),'missing archive members');return got
def sdk_global(doc):
 # Root's observational before/after schema is deliberately explicit. Do not
 # infer an SDK identity from arbitrary same-shaped descendant dictionaries.
 if 'global_sdk' in doc:doc=doc['global_sdk']
 need(isinstance(doc,dict) and isinstance(doc.get('path'),str) and isinstance(doc.get('sha256'),str),'global SDK observation schema missing')
 return doc
def main():
 checks={}
 for l in read('SHA256SUMS').decode().splitlines():
  h,n=l.split('  ',1);rel(n);need(re.fullmatch('[0-9a-f]{64}',h) and n not in checks,'bad outer checksum row');checks[n]=h
 need({p.relative_to(BASE).as_posix() for p in BASE.rglob('*') if p.is_file() and p!=BASE/'SHA256SUMS'}==set(checks),'outer checksum inventory differs')
 for n,h in checks.items():need(sha(read(n))==h,'outer checksum differs '+n)
 original=archive(load('raw.manifest.json'),'raw');artifacts=load('artifacts/manifest.json');binary={}
 for row in artifacts['artifacts']:
  b=gzip.decompress(container(row,row['original_sha256']));need(len(b)==row['original_bytes'] and sha(b)==row['original_sha256'],'binary payload differs');binary[row['original_sha256']]=b
 for n,row in artifacts['original_paths'].items():
  need(n not in original,'duplicate logical original');b=binary[row['artifact']];check(b,row,n);original[n]=b
 capture=load('capture.json');need(set(original)=={r['path'] for r in capture['files']} and len(original)==len(capture['files']),'capture inventory differs')
 for row in capture['files']:check(original[row['path']],row,row['path']);need(row['read_stable'],'unstable original capture')
 for n in original:need('/target/' not in n,'original target packaged')
 sm=load('source/members.json');sources=archive(sm,'source',True);binding=load('source-binding.json');commit=binding['commit_object'].encode();need(hashlib.sha1(b'commit '+str(len(commit)).encode()+b'\0'+commit).hexdigest()==binding['producer_commit'],'producer commit differs');need(commit.splitlines()[0].decode()=='tree '+binding['producer_complete_tree'],'producer complete tree differs')
 trees=load('source/tree-objects.json');entries={}
 for digest,row in trees['objects'].items():
  b=base64.b64decode(row['raw_base64'],validate=True);need(len(b)==row['raw_bytes'] and sha(b)==row['raw_sha256'] and hashlib.sha1(b'tree '+str(len(b)).encode()+b'\0'+b).hexdigest()==digest,'tree object differs');children={};o=0
  while o<len(b):
   end=b.index(b'\0',o);mode,n=b[o:end].split(b' ',1);oid=b[end+1:end+21];need(len(oid)==20,'short tree entry');children[n.decode()]=(mode.decode(),oid.hex());o=end+21
  entries[digest]=children
 need(trees['root_tree']==binding['producer_complete_tree'],'tree root differs')
 def lookup(n):
  digest=trees['root_tree'];mode=None
  for part in PurePosixPath(n).parts:mode,digest=entries[digest][part]
  return mode,digest
 for row in sm['members']:need(row['ref']==binding['producer_commit'] and lookup(row['path'])==(row['git_mode'],row['git_blob']),'source membership differs')
 need(lookup('kernel/asterinas')[1]==binding['derived_kernel_tree'],'kernel tree membership differs');need(sources['source/README.md']==b'','root README changed')
 pin=json.loads(sources['source/support/upstream-lock.json'])['kernel'];need(pin['commit']=='c4b7ed575b7b32773475b194d2ad41fb6d03765b' and pin['tree']=='96605cf64aeae2d34f29b97e85eff9315fe10a8e' and pin['toolchain']=='nightly-2026-07-21' and pin['reuse']=='full_kernel_derived','fixed upstream pins differ')
 a=lambda n:original[ROOT+n];commands=json.loads(a('controller-N2/commands.json'));names=['worktree','source-verification','target-absence','fresh-make-kernel','freeze-first-produced-kernel','make-run-kernel','boot-live-recheck','post-source-verification','worktree-status','installed-components','installed-targets']
 need([(r['name'],r['returncode']) for r in commands]==[(n,0) for n in names],'eleven original commands did not all pass');need(commands[0]['argv'][-1]==binding['producer_commit'],'worktree producer differs')
 for row in commands:
  name=ROOT+row['log'].split('/'+ROOT,1)[1];b=original[name];need(len(b)==row['log_size'] and sha(b)==row['log_sha256'],'original command log differs');env=row['selected_environment'];need(env['RUSTUP_TOOLCHAIN']=='nightly-2026-07-21' and env['CARGO_BUILD_JOBS']=='1','actual ordinary toolchain/jobs differ');need(not row.get('controller_timed_out',False),'controller timed out')
 need(commands[3]['argv']==['bash','support/build/kernel.sh','kernel'] and commands[5]['argv']==['bash','support/build/kernel.sh','run_kernel'],'ordinary public entry differs')
 done=json.loads(original['controller/outer-completed-tool.json']);need(any(type(done.get(k)) is int and done.get(k)==0 for k in ('exit_code','returncode','outer_exit_code','observed_exit_code')),'completed outer tool observation missing')
 old=original['controller/published-N1.py'];controller=original['controller/run-private-sdk-native-n2.py'];need(sha(old)=='3c4e1f2d6e70ec4211cebc80e456b0048aad16a7893db09a7a10c992ada5254b' and sha(controller)=='2977c8c0b997e16b1c29a7b6babe7ffd00d0b2126505e04f40cb0ce5c4851950','controller source identity differs')
 expected=old.decode().replace('N1','N2').replace('/tmp/trillionnium-a01-final-normal',WORK).replace("'normal-cloud-final'","'private-sdk-native-N2'").replace("'CARGO_BUILD_JOBS': '2'","'CARGO_BUILD_JOBS': '1'");need(expected.encode()==controller,'undeclared controller change')
 origin=json.loads(original['controller/origin.json']);need(origin['old_sha256']==sha(old) and origin['new_sha256']==sha(controller) and not origin['new_profile_projection'],'controller origin differs')
 before=a('controller-N2/source-verification.log');need(before==a('controller-N2/post-source-verification.log')==a('kernel-build/source-inputs.json')==a('kernel-boot/source-inputs.json'),'source before/after receipts differ');sr=json.loads(before);need(sr['passed'] and sr['errors']==[] and sr['checked_files']==118,'source verifier failed');need(a('controller-N2/worktree-status.log')==b'','worktree dirty')
 need(json.loads(a('controller-N2/target-absence.log'))=={'target':TARGET,'absent_before_first_build':True},'cold target precondition missing')
 need(a('controller-N2/boot-live-recheck.log')==b'PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)\n','actual live artifact checker missing')
 sdk_binding=load('sdk-bindings.json');sdk=sdk_binding['private_sdks'];need(len(sdk)==2 and [s['stage'] for s in sdk]==['kernel-build','kernel-boot'],'private SDK stage scope differs')
 counts={}
 for stage,action,log in [('kernel-build','kernel','kernel.log'),('kernel-boot','run_kernel','run_kernel.log')]:
  env=a(stage+'/environment.log').decode().splitlines();run='/workspace/scratch/ae1a8cf05419/private-sdk-native-N2/'+stage;prefix=run+'/osdk';cargo='/workspace/scratch/ae1a8cf05419/toolchains/cargo';sdkpath=prefix+'/bin/cargo-osdk'
  for wanted in ['CARGO_BUILD_JOBS=1','RUSTFLAGS=<unset>','CARGO_ENCODED_RUSTFLAGS=<unset>','ASTER_BUILD_TIMESTAMP=<unset>','CARGO_TARGET_DIR='+TARGET,'A01_OSDK_INSTALL_ROOT='+prefix,'CARGO_OSDK='+sdkpath,binding['producer_commit'],'commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48']:need(env.count(wanted)==1,'actual child environment differs '+wanted)
  path=next(l[5:] for l in env if l.startswith('PATH=')).split(':');need(path[0]==prefix+'/bin' and cargo+'/bin' in path and path.index(cargo+'/bin')>0,'private SDK lookup prefix differs')
  argv=shlex.split(a(stage+'/command.sh').decode());need(argv[:8]==['make','-C',WORK+'/kernel/asterinas','-f','Makefile','-f',WORK+'/support/build/minimal.mk',action],'recorded make target differs');need('CARGO_OSDK='+sdkpath in argv and 'A01_OSDK_INSTALL_ROOT='+prefix in argv,'private SDK make overrides missing');need(all(v in argv for v in ['TARGET_ARCH=x86_64','SMP=1','MEM=512M','ENABLE_KVM=0','BOOT_PROTOCOL=multiboot','INITRAMFS=on','AUTO_TEST=none']),'actual guest config differs')
  for status in ['make-exit-code.txt','run-exit-code.txt','manifest-cleanup-exit-code.txt','log-exit-code.txt']:need(int(a(stage+'/'+status))==0,'nonzero stage exit '+stage+'/'+status)
  cleanup=json.loads(a(stage+'/manifest-cleanup.json'));need(cleanup['passed'] and cleanup['outcome']=='owned_removed' and cleanup['helper_sha256']==sha(sources['source/support/build/cleanup-manifest.py']),'manifest cleanup differs')
  counts[stage]=len(re.findall(rb'^\s*Compiling\s',a(stage+'/'+log),re.M))
  item=next(s for s in sdk if s['stage']==stage);b=original[item['logical_path']];need(item['original_path']==sdkpath and item['logical_path']==ROOT+stage+'/osdk/bin/cargo-osdk' and len(b)==item['bytes'] and sha(b)==item['sha256'] and b.startswith(b'\x7fELF'),'private SDK binary identity differs')
  expectedroot=WORK+'/kernel/asterinas/osdk';need(item['expected_compiletime_osdk_root']==expectedroot and b.count(expectedroot.encode())==item['expected_root_occurrences']>0,'SDK compile-time source binding differs')
  recorded=a(stage+'/osdk/cargo-osdk.sha256').decode().strip().split();need(recorded==[sha(b),sdkpath],'installed SDK SHA receipt differs')
  for manifest in ('.crates.toml','.crates2.json'):need(expectedroot in a(stage+'/osdk/'+manifest).decode(),'installed SDK metadata source differs')
 need(sdk[0]['original_path']!=sdk[1]['original_path'],'SDK prefixes not distinct')
 capture_by_path={row['path']:row for row in capture['files']};private_stats=[capture_by_path[s['logical_path']]['source_stat'] for s in sdk];need((private_stats[0]['st_dev'],private_stats[0]['st_ino'])!=(private_stats[1]['st_dev'],private_stats[1]['st_ino']),'private SDK captured inodes are not distinct')
 need(sdk_binding['same_private_sdk_hashes']==(sdk[0]['sha256']==sdk[1]['sha256']) and sdk_binding['same_private_sdk_complete_bytes']==(original[sdk[0]['logical_path']]==original[sdk[1]['logical_path']]),'two retained private SDK complete-byte comparison differs')
 need(sdk_binding['global_prelaunch_binary_payload_retained'] is False and sdk_binding['global_complete_before_after_bytes_compared'] is False,'global SDK scope widened beyond hash/stat observations')
 overlay=sources['source/support/build/minimal.mk'].decode();need('OSDK_LOCAL_DEV=1 cargo install --locked --root "$(A01_OSDK_INSTALL_ROOT)" cargo-osdk --path osdk' in overlay,'actual source private locked install recipe missing')
 ostd=sources['source/kernel/asterinas/osdk/src/util.rs'].decode();need('option_env!("OSDK_LOCAL_DEV")' in ostd and 'env!("CARGO_MANIFEST_DIR")' in ostd and '.join("ostd")' in ostd,'pinned compile-time source binding implementation missing')
 global_before=sdk_global(json.loads(original['global-sdk/before.json']));global_after=sdk_global(json.loads(original['global-sdk/after.json']));need(global_before['path']==global_after['path']=='/workspace/scratch/ae1a8cf05419/toolchains/cargo/bin/cargo-osdk' and global_before['sha256']==global_after['sha256'],'global SDK before/after bytes changed')
 need(global_before['sha256']=='b5b92798bfcfb9416539fcaca3271cdc7017444affba26b34b7881d861171f2e','observed global SDK SHA differs from this run')
 for key in ('size','bytes'):
  if key in global_before and key in global_after:need(global_before[key]==global_after[key],'global SDK size changed')
 need(isinstance(global_before.get('stat'),dict) and isinstance(global_after.get('stat'),dict) and global_before['stat']==global_after['stat'],'global SDK observed stat missing/changed')
 prelaunch=json.loads(original['global-sdk/before.json']);postcheck=json.loads(original['global-sdk/after.json']);need(prelaunch['source_commit']==binding['producer_commit'] and prelaunch['worktree_absent'] is True and prelaunch['output_absent'] is True and prelaunch['controller_sha256']==sha(controller),'prelaunch source/absence observation differs');need(postcheck['passed'] is True and postcheck['global_hash_and_fd_stat_unchanged'] is True and postcheck['global_prelaunch_complete_bytes_retained'] is False,'postcheck global comparison scope differs')
 for s in sdk:
  observed=postcheck['private_sdks'][s['stage']];need(observed['path']==s['original_path'] and observed['sha256']==s['sha256'] and observed['bytes']==s['bytes'],'root postcheck private SDK binding differs')
 first=json.loads(a('controller-N2/freeze-first-produced-kernel.log'));firstbytes=a('first-build-kernel.elf');need(first['source']==TARGET+'/osdk/asterinas/asterinas-osdk-bin.elf' and first['copy']=='/workspace/scratch/ae1a8cf05419/private-sdk-native-N2/first-build-kernel.elf' and first['size']==len(firstbytes) and first['sha256']==sha(firstbytes) and first['source_stat']['st_size']==len(firstbytes),'cold first-produced kernel capture differs')
 q=json.loads(a('kernel-boot/qemu.json'));need(q['raw_exit_code']==q['recorder_exit_code']==33 and not q['timed_out'] and q['stage']=='complete','actual QEMU did not pass');loaded={}
 for option,row in q['artifacts'].items():
  n=ROOT+row['path'].split('/'+ROOT,1)[1];b=original[n];need(len(b)==row['size'] and sha(b)==row['sha256'] and q['argv'][q['argv'].index(option)+1]==row['path'],'guest input binding differs');loaded[option]=b
 need(set(loaded)=={'-kernel','-initrd','-bios'},'guest input scope differs')
 for k,v in [('-machine','q35'),('-accel','tcg'),('-cpu','max'),('-smp','1'),('-m','512M')]:need(q['argv'][q['argv'].index(k)+1]==v,'QEMU profile differs '+k)
 kernel=loaded['-kernel'];need(kernel[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<HH',kernel,16)==(2,3) and kernel[:8192].find(struct.pack('<I',0x1badb002))>=0,'not full OSDK ELF64/Multiboot-compatible kernel')
 need(a('kernel-build/initramfs.cpio.gz')==a('kernel-boot/initramfs.cpio.gz')==loaded['-initrd'],'initrd identities differ')
 serial=a('kernel-boot/serial.log');need(len(serial)==q['serial_size'] and sha(serial)==q['serial_sha256'],'serial identity differs');clean=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)','',serial.decode(errors='replace'))
 for text in ['OSTD initialized. Preparing components.','TRILLIONNIUM_A01_INIT_BEGIN','TRILLIONNIUM_A01_CPU_COUNT=1','Successfully booted.','TRILLIONNIUM_A01_BOOT_OK']:need(text in clean,'actual guest marker missing')
 need(not any(t in clean for t in ['panicked at','An uncaught panic occurred:','Uncaught panic:','unknown panic payload! (fatal panic handling error','Non-resettable panic!','The panic handler panicked','Panicked in `PanicGuard`, aborting the system']),'serial panic')
 report=load('report.json');need(report['producer_commit']==binding['producer_commit'] and report['producer_complete_tree']==binding['producer_complete_tree'] and report['derived_kernel_tree']==binding['derived_kernel_tree'],'report source differs');need(report['actual_host']==prelaunch['host_identity']['hostname']=='24f0ea2620fe','actual host observation differs');need(report['compile_lines']==counts and counts['kernel-build']>200,'full cold compile evidence differs');need(report['first_kernel_elf']==first and report['first_and_boot_kernel_complete_bytes_equal']==(firstbytes==kernel),'first/boot byte comparison differs')
 need(report['cold_target_absent_before_first_build'] and report['cold_make_kernel_passed'] and report['subsequent_make_run_kernel_passed'] and report['raw_qemu_exit']==33 and not any(report[k] for k in ['profile_opt_in','cross_instance_elf_equality_claimed','immutable_host_claimed','all_project_blockers_closed']),'ordinary acceptance scope differs')
 for n in ['kernel-boot/serial.log','kernel-boot/qemu.json','kernel-build/environment.log','kernel-boot/environment.log','kernel-build/command.sh','kernel-boot/command.sh','controller-N2/commands.json']:need(read('readable/'+n)==a(n),'readable copy differs')
 print(json.dumps({'passed':True,'source_commit':binding['producer_commit'],'original_files':len(original),'source_controls':len(sources),'private_sdk_paths':[s['original_path'] for s in sdk],'private_sdk_sha256':[s['sha256'] for s in sdk],'global_sdk_observed_unchanged':True,'controller_commands':11,'compile_lines':counts,'raw_qemu_exit':33,'kernel_sha256':sha(kernel),'first_and_boot_complete_bytes_equal':firstbytes==kernel,'scope':'Offline preserved ordinary N2 source/input/controller/guest evidence only; no build, SDK invocation, target access, live guest check or VM.'},sort_keys=True))
if __name__=='__main__':main()
