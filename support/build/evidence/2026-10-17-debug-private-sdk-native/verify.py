#!/usr/bin/python3
"""Verify preserved real private-SDK Rust-entry debug evidence offline."""
import argparse,base64,gzip,hashlib,io,json,os,re,shlex,stat,struct,sys,tarfile
from pathlib import Path,PurePosixPath
BASE=Path(__file__).resolve().parent;MAX=2097152
SOURCE='a5af45537dea32039ea172ad0d7e381400c07d95'
WORK='/tmp/trillionnium-a01-private-sdk-N2';TARGET=WORK+'/kernel/asterinas/target'
ROOT='native-followup/debug-retry1/';FAILED='native-followup/debug/'
def need(ok,message):
 if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def rel(name):
 p=PurePosixPath(name);need(bool(name) and not p.is_absolute() and str(p)==name and '..' not in p.parts and '.' not in p.parts and '\\' not in name,'unsafe path '+name);return p
def read(name):
 p=BASE.joinpath(*rel(name).parts);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  before=os.fstat(fd);need(stat.S_ISREG(before.st_mode),'nonregular package member');identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  with os.fdopen(os.dup(fd),'rb') as f:b=f.read()
  need(identity(before)==identity(os.fstat(fd))==identity(p.lstat()) and len(b)==before.st_size,'package member changed');return b
 finally:os.close(fd)
def load(name):return json.loads(read(name))
def check(b,row,name):need(len(b)==row['bytes'] and sha(b)==row['sha256'],'bytes/SHA mismatch '+name)
def container(row,name):
 parts=[]
 for chunk in row['chunks']:
  b=read(chunk['path']);check(b,chunk,chunk['path']);need(0<len(b)<=MAX,'bad chunk size');parts.append(b)
 b=b''.join(parts);check(b,row,name);return b
def archive(row,name,source=False):
 data=container(row,name);wanted={r['member']:r for r in row['members']};need(len(wanted)==len(row['members']),'duplicate manifest member');members={}
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as stream:
  for info in stream:
   rel(info.name);need(info.isfile() and info.name in wanted and info.name not in members,'unsafe/duplicate archive member');item=wanted[info.name]
   need(info.mode==item['mode'] and info.uid==info.gid==info.mtime==0 and info.uname==info.gname=='','tar metadata differs');raw=stream.extractfile(info).read();check(raw,item,info.name)
   if source:need(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==item['git_blob'],'source blob differs')
   members[info.name]=raw
 need(set(members)==set(wanted),'archive inventory differs');return members
def entry(data,address,machine):
 need(len(data)>=64 and data[:7]==b'\x7fELF\x02\x01\x01','not ELF64 little-endian')
 f=struct.unpack_from('<16sHHIQQQIHHHHHH',data);need(f[1:4]==(2,machine,1),'ELF type/machine/version differs');offset,stride,count=f[5],f[9],f[10]
 need(f[8]==64 and stride==56 and count>0 and offset>=64 and offset+stride*count<=len(data),'bad program-header table');locations=[]
 for i in range(count):
  kind,flags,fileoff,virtual,_,filesz,memsz,_=struct.unpack_from('<IIQQQQQQ',data,offset+i*stride)
  if kind!=1:continue
  need(filesz<=memsz and fileoff+filesz<=len(data),'truncated PT_LOAD')
  if flags&1 and virtual<=address and address+32<=virtual+filesz:locations.append(fileoff+address-virtual)
 need(len(locations)==1,'entry not in exactly one executable PT_LOAD');return locations[0],data[locations[0]:locations[0]+32]
def main(restore=None):
 sums={}
 for line in read('SHA256SUMS').decode().splitlines():
  h,name=line.split('  ',1);rel(name);need(re.fullmatch('[0-9a-f]{64}',h) and name not in sums,'invalid checksum row');sums[name]=h
 actual={p.relative_to(BASE).as_posix() for p in BASE.rglob('*') if p.is_file() and p!=BASE/'SHA256SUMS'};need(actual==set(sums),'checksum inventory differs')
 for name,h in sums.items():need(sha(read(name))==h,'outer checksum differs '+name)
 original=archive(load('raw.manifest.json'),'raw');art=load('artifacts/manifest.json');binaries={}
 for row in art['artifacts']:
  b=gzip.decompress(container(row,row['original_sha256']));need(len(b)==row['original_bytes'] and sha(b)==row['original_sha256'],'binary original differs');binaries[sha(b)]=b
 for name,row in art['original_paths'].items():
  need(name not in original,'duplicate logical binary');b=binaries[row['artifact']];check(b,row,name);original[name]=b
 capture=load('capture.json');need(set(original)=={r['path'] for r in capture['files']} and len(original)==len(capture['files']),'original capture inventory differs')
 for row in capture['files']:check(original[row['path']],row,row['path']);need(row['read_stable'] is True,'unstable original read')
 need(not any('/target/' in name for name in original) and set(n for n in original if n.startswith('observed-symbol/'))=={'observed-symbol/asterinas-osdk-bin'},'unexpected original target payload')
 sources=archive(load('source/members.json'),'source',True);binding=load('source-binding.json');commit=binding['commit_object'].encode()
 need(binding['producer_commit']==SOURCE and hashlib.sha1(b'commit '+str(len(commit)).encode()+b'\0'+commit).hexdigest()==SOURCE,'producer commit differs');need(commit.splitlines()[0].decode()=='tree '+binding['producer_complete_tree'],'producer complete tree differs')
 trees=load('source/tree-objects.json');entries={}
 for digest,row in trees['objects'].items():
  b=base64.b64decode(row['raw_base64'],validate=True);need(len(b)==row['raw_bytes'] and sha(b)==row['raw_sha256'] and hashlib.sha1(b'tree '+str(len(b)).encode()+b'\0'+b).hexdigest()==digest,'Git tree differs');children={};offset=0
  while offset<len(b):
   end=b.index(b'\0',offset);mode,name=b[offset:end].split(b' ',1);oid=b[end+1:end+21];need(len(oid)==20,'truncated tree');children[name.decode()]=(mode.decode(),oid.hex());offset=end+21
  entries[digest]=children
 need(trees['root_tree']==binding['producer_complete_tree'],'root tree binding differs')
 def lookup(path):
  digest=trees['root_tree'];mode=None
  for part in PurePosixPath(path).parts:mode,digest=entries[digest][part]
  return mode,digest
 for row in load('source/members.json')['members']:need(row['ref']==SOURCE and lookup(row['path'])==(row['git_mode'],row['git_blob']),'source Git membership differs')
 need(lookup('kernel/asterinas')[1]==binding['derived_kernel_tree']=='6b3cab110aa6d30d5b89f99c4389c9c3e01022da','derived kernel tree differs');need(sources['source/README.md']==b'','root README not empty')
 pin=json.loads(sources['source/support/upstream-lock.json'])['kernel'];need(pin['commit']=='c4b7ed575b7b32773475b194d2ad41fb6d03765b' and pin['tree']=='96605cf64aeae2d34f29b97e85eff9315fe10a8e' and pin['toolchain']=='nightly-2026-07-21' and pin['reuse']=='full_kernel_derived','upstream pins differ')
 a=lambda n:original[ROOT+n];f=lambda n:original[FAILED+n]
 names=['source-head-clean','source-inputs','fixed-rustc','actual-debug','post-source-inputs','post-source-head-clean'];commands=json.loads(a('controller/commands.json'));failed_commands=json.loads(f('controller/commands.json'))
 need([(r['name'],r['returncode']) for r in commands]==[(name,0) for name in names],'retry six commands did not pass');need([(r['name'],r['returncode']) for r in failed_commands]==[(name,0 if name!='actual-debug' else 1) for name in names[:4]],'failed first command scope differs')
 for rows in (failed_commands,commands):
  need(rows[0]['argv'][-1]==SOURCE and all(row['cwd']==WORK for row in rows),'controller source/cwd differs')
  for row in rows:
   # Controller rows record no log path; the exact name maps to its own controller.
   prefix=FAILED if rows is failed_commands else ROOT;raw=original[prefix+'controller/'+row['name']+'.log'];need(len(raw)==row['log_bytes'] and sha(raw)==row['log_sha256'],'controller log binding differs')
   need(not row.get('timed_out',False) and row['environment']['RUSTUP_TOOLCHAIN']=='nightly-2026-07-21' and row['environment']['CARGO_BUILD_JOBS']=='1','controller timeout/toolchain/jobs differ')
 done=json.loads(original['controller/root-completed-tool.json']);need(any(type(done.get(k)) is int and done[k]==0 for k in ('observed_exit_code','exit_code','outer_exit_code','returncode')),'root outer completion not accepted')
 old=original['controller/run-native-followup-v1.py'];new=original['controller/run-native-followup-v2.py'];correction=json.loads(original['controller/environment-correction.json'])
 need(sha(old)==correction['old_controller_sha256']=='7638d540c2d81ffa442296103fe73db0e65509a03cafbfa5cd143697ce7049ee' and sha(new)==correction['new_controller_sha256']=='1e1a2d51978ed0dec79ca105c746e4ad7daa743dbd47c4b9490c0dc9fd9bb25c','controller identity differs')
 expected=old.decode().replace('import datetime, hashlib, json, os, signal, subprocess, sys','import datetime, hashlib, json, os, signal, subprocess, sys, shutil').replace("outer=base/'native-followup'/action","outer=base/'native-followup'/('debug-retry1' if action=='debug' else action)").replace("'--nm',str(prefix/'usr/bin/nm')","'--nm',str(Path(shutil.which('nm',path=env['PATH'])).resolve())")
 need(new==expected.encode(),'undeclared retry controller difference');need(correction['failed_outer_observed_exit']==correction['failed_actual_debug_exit']==1 and correction['no_kernel_or_qemu_in_failed_prepare'] is True,'first failure correction scope differs')
 failed=json.loads(f('run/result.json'));need(failed['passed'] is False and failed['stage']=='prepare' and failed['error']=='GDB and nm must be available' and failed['owned_session_cleanup']==[] and int(f('run/exit-code.txt'))==1,'first failed attempt differs');need(not any(name.startswith(FAILED+'run/boot/') for name in original),'first failed prepare unexpectedly has boot inputs')
 before=a('controller/source-inputs.log');need(before==a('controller/post-source-inputs.log')==a('run/boot/source-inputs.json')==f('controller/source-inputs.log'),'source pre/post inputs differ');sr=json.loads(before);need(sr['passed'] and sr['errors']==[] and sr['checked_files']==118,'source check not accepted')
 need(a('controller/source-head-clean.log')==a('controller/post-source-head-clean.log')==(SOURCE+'\n\n').encode(),'source head/clean receipt differs');need(b'commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48' in a('controller/fixed-rustc.log'),'wrong compiler')
 environment=json.loads(a('run/environment.json'));need(environment['git_head']==SOURCE and environment['git_tree']==binding['producer_complete_tree'] and environment['git_status']=='' and environment['toolchain']=='nightly-2026-07-21','actual debug source environment differs')
 for path,digest in environment['source_sha256'].items():need(sha(sources['source/'+path])==digest,'actual debug source file not bound to Git '+path)
 q=json.loads(a('run/boot/qemu.json'));ready=json.loads(a('run/qemu-ready.json'));need(q['raw_exit_code']==q['recorder_exit_code']==33 and q['stage']=='complete' and q['timed_out'] is False,'actual detached QEMU did not pass')
 loaded={}
 for option,row in q['artifacts'].items():
  path='native-followup/'+row['path'].split('/native-followup/',1)[1];raw=original[path];need(len(raw)==row['size'] and sha(raw)==row['sha256'] and q['argv'][q['argv'].index(option)+1]==row['path'],'actual loaded input differs');loaded[option]=raw
 need(set(loaded)=={'-kernel','-initrd','-bios'},'loaded input scope differs')
 for key,value in [('-machine','q35'),('-accel','tcg'),('-cpu','max'),('-smp','1'),('-m','512M')]:need(q['argv'][q['argv'].index(key)+1]==value,'fixed QEMU device profile differs')
 need(ready['raw_exit_code'] is None and ready['timed_out'] is False and ready['qemu_pid']==q['qemu_pid'] and ready['gdb_listener']==q['gdb_listener'] and ready['artifacts']==q['artifacts'],'actual ready/final QEMU identity differs')
 updates=environment['explicit_environment_updates'];need(ready['gdb_listener']['fd']==int(updates['A01_GDB_FD']) and ready['gdb_listener']['address']==environment['listener']['address'] and ready['gdb_listener']['address'][1]==int(updates['A01_GDB_PORT']),'inherited owned listener binding differs')
 binding_entry=json.loads(a('run/entry-artifact-binding.json'));symbol=original['observed-symbol/asterinas-osdk-bin'];address=int(binding_entry['entry_address'],16);symbol_info=binding_entry['symbol_artifact'];boot_info=binding_entry['boot_artifact'];expected_bytes=bytes.fromhex(binding_entry['expected_bytes'])
 need(binding_entry['entry_size']==len(expected_bytes)==32 and symbol_info['path']==TARGET+'/x86_64-unknown-none/release/asterinas-osdk-bin' and symbol_info['size']==len(symbol) and symbol_info['sha256']==sha(symbol),'preserved actual symbol ELF binding differs')
 for data,info,machine in [(symbol,symbol_info,62),(loaded['-kernel'],boot_info,3)]:
  offset,observed=entry(data,address,machine);need(observed==expected_bytes and info['entry_file_offset']==offset and info['entry_bytes']==expected_bytes.hex() and info['size']==len(data) and info['sha256']==sha(data),'ELF entry bytes do not match original binding')
 need(boot_info['path']==q['artifacts']['-kernel']['path'] and loaded['-kernel'][:8192].find(struct.pack('<I',0x1badb002))>=0,'boot ELF is not exact recorded Multiboot input')
 symbols=[line.split() for line in a('run/symbols.log').decode().splitlines()];matches=[int(r[2],16) for r in symbols if len(r)>=3 and r[0]=='__ostd_main' and r[1]=='T'];need(matches==[address],'nm exact Rust-entry symbol differs')
 gdb=a('run/gdb.log').decode(errors='replace');hits=re.findall(r'^A01_GDB_RUST_ENTRY_HIT pc=0x([0-9a-fA-F]+) entry=0x([0-9a-fA-F]+)$',gdb,re.M);bytehits=re.findall(r'^A01_GDB_RUST_ENTRY_BYTES pc=0x([0-9a-fA-F]+) size=32 bytes=([0-9a-fA-F]{64})$',gdb,re.M)
 need(len(hits)==len(bytehits)==1 and [int(x,16) for x in hits[0]]==[address,address] and int(bytehits[0][0],16)==address and bytes.fromhex(bytehits[0][1])==expected_bytes and gdb.count('A01_GDB_DETACHED')==1 and 'A01_GDB_WRONG_PC' not in gdb,'GDB runtime PC/bytes/detach differs')
 for name in ('run/gdb-exit-code.txt','run/driver-exit-code.txt','run/exit-code.txt','run/boot/run-exit-code.txt','run/boot/make-exit-code.txt','run/boot/log-exit-code.txt','run/boot/manifest-cleanup-exit-code.txt'):need(int(a(name))==0,'nonzero debug/kernel exit '+name)
 serial=a('run/boot/serial.log');need(len(serial)==q['serial_size'] and sha(serial)==q['serial_sha256'],'full serial differs');clean=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)','',serial.decode(errors='replace'))
 for marker in ('OSTD initialized. Preparing components.','TRILLIONNIUM_A01_INIT_BEGIN','TRILLIONNIUM_A01_CPU_COUNT=1','Successfully booted.','TRILLIONNIUM_A01_BOOT_OK'):need(marker in clean,'actual guest marker missing')
 need(not any(text in clean for text in ('panicked at','An uncaught panic occurred:','Uncaught panic:','unknown panic payload! (fatal panic handling error','Non-resettable panic!','The panic handler panicked','Panicked in `PanicGuard`, aborting the system')),'actual guest panic')
 sdk=json.loads(a('run/installed-osdk.json'));sdkpath='/workspace/scratch/ae1a8cf05419/native-followup/debug-retry1/run/boot/osdk/bin/cargo-osdk';sdklogical=ROOT+'run/boot/osdk/bin/cargo-osdk';sdkbytes=original[sdklogical]
 need(sdk['path']==sdkpath and sdk['installation_root']==str(PurePosixPath(sdkpath).parents[1]) and sdk['size']==len(sdkbytes) and sdk['sha256']==sha(sdkbytes) and sdk['matches_installation_receipt'] is True,'actual private SDK identity differs')
 expectedroot=WORK+'/kernel/asterinas/osdk';need(sdkbytes.startswith(b'\x7fELF') and expectedroot.encode() in sdkbytes and sdk['source_directory']==expectedroot,'private SDK source root binding differs')
 need(set(sdk['source_inputs'])=={'Cargo.toml','Cargo.lock'},'private SDK Cargo input scope differs')
 for name,item in sdk['source_inputs'].items():need(item['path']==expectedroot+'/'+name and item['sha256']==sha(sources['source/kernel/asterinas/osdk/'+name]),'private SDK source Cargo input differs')
 receipt=a('run/boot/osdk/cargo-osdk.sha256');need(receipt==(sha(sdkbytes)+'  '+sdkpath+'\n').encode() and sdk['installation_receipt']['sha256']==sha(receipt) and sdk['installation_receipt']['path']==str(PurePosixPath(sdkpath).parents[1]/'cargo-osdk.sha256'),'private SDK install receipt differs')
 captured_sdk=next(row for row in capture['files'] if row['path']==sdklogical);need(all(captured_sdk['source_stat'][key]==value for key,value in sdk['stat'].items()),'private SDK identity changed since debug observation')
 for name in ('.crates.toml','.crates2.json'):need(expectedroot.encode() in a('run/boot/osdk/'+name),'SDK install metadata root differs')
 overlay=sources['source/support/build/minimal.mk'];need(b'OSDK_LOCAL_DEV=1 cargo install --locked --root "$(A01_OSDK_INSTALL_ROOT)" cargo-osdk --path osdk' in overlay,'source private locked install recipe missing')
 util=sources['source/kernel/asterinas/osdk/src/util.rs'];need(b'option_env!("OSDK_LOCAL_DEV")' in util and b'env!("CARGO_MANIFEST_DIR")' in util,'source compile-time binding implementation differs')
 env=a('run/boot/environment.log').decode().splitlines();prefix=str(PurePosixPath(sdkpath).parents[1]);cargo='/workspace/scratch/ae1a8cf05419/toolchains/cargo'
 for expected in ('A01_OSDK_INSTALL_ROOT='+prefix,'CARGO_OSDK='+sdkpath,'CARGO_HOME='+cargo,'CARGO_TARGET_DIR='+TARGET,'CARGO_BUILD_JOBS=1',SOURCE):need(env.count(expected)==1,'actual debug build environment differs '+expected)
 lookup_path=next(line[5:] for line in env if line.startswith('PATH=')).split(':');need(lookup_path[0]==prefix+'/bin' and cargo+'/bin' in lookup_path and lookup_path.index(cargo+'/bin')>0,'actual SDK lookup order differs')
 make=shlex.split(a('run/boot/command.sh').decode());need(make[:8]==['make','-C',WORK+'/kernel/asterinas','-f','Makefile','-f',WORK+'/support/build/minimal.mk','gdb_server'],'actual upstream debug make entry differs')
 for expected in ('CARGO_OSDK='+sdkpath,'A01_OSDK_INSTALL_ROOT='+prefix,'TARGET_ARCH=x86_64','SMP=1','MEM=512M','ENABLE_KVM=0','BOOT_PROTOCOL=multiboot','INITRAMFS=on','AUTO_TEST=none'):need(expected in make,'actual debug make option missing '+expected)
 result=json.loads(a('run/result.json'));need(result['passed'] and result['stage']=='complete' and result['entry_artifact_binding']==binding_entry and result['gdb']['runtime_entry_bytes']==expected_bytes.hex() and result['boot']['raw_qemu_exit']==33 and result['boot']['serial_sha256']==sha(serial),'final debug result differs')
 need(all(row['status']==0 and row['reaped'] is True and row['external_reap'] is False for row in result['owned_session_cleanup']),'owned session cleanup differs')
 compile_lines=len(re.findall(rb'^\s*Compiling\s',a('run/boot/gdb_server.log'),re.M));report=load('report.json');need(report['producer_commit']==SOURCE and report['successful_debug_runs']==1 and report['failed_prepare_attempts']==1 and report['raw_qemu_exit']==33 and report['cold_build_claimed'] is False and report['compile_lines']==compile_lines and compile_lines>0,'report acceptance/compile scope differs')
 need(report['kernel_sha256']==sha(loaded['-kernel']) and report['symbol_sha256']==sha(symbol) and report['private_sdk_sha256']==sha(sdkbytes),'report binary identities differ')
 for name,row in load('readable/manifest.json')['copies'].items():need(read(name)==original[row],'readable original differs')
 restored=None
 if restore is not None:
  destination=Path(restore).absolute();need(destination!=BASE and BASE not in destination.parents,'restore must be outside phase');destination.mkdir(parents=False,exist_ok=False)
  for name,data in {**original,**sources}.items():
   path=destination.joinpath(*rel(name).parts);path.parent.mkdir(parents=True,exist_ok=True)
   with path.open('xb') as stream:stream.write(data)
  restored=str(destination)
 return {'passed':True,'source_commit':SOURCE,'source_controls':len(sources),'original_files':len(original),'successful_debug_runs':1,'failed_prepare_attempts':1,'raw_qemu_exit':33,'gdb_runtime_entry_bytes_match':True,'kernel_sha256':sha(loaded['-kernel']),'symbol_sha256':sha(symbol),'private_sdk_sha256':sha(sdkbytes),'compile_lines':compile_lines,'cold_build_claimed':False,'restored_directory':restored,'scope':'Offline retained source/input/controller/runtime-entry-byte/serial checks only; no captured code, SDK, debugger, target, build or VM execution.'}
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--restore');args=parser.parse_args()
 try:print(json.dumps(main(args.restore),indent=2))
 except (OSError,ValueError,KeyError,tarfile.TarError,EOFError) as error:print('verification failed: '+str(error),file=sys.stderr);raise SystemExit(1)
