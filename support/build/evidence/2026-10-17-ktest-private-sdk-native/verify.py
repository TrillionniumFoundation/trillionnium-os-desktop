#!/usr/bin/env python3
"""Offline verification of retained real private-SDK kernel-test evidence."""
import base64,gzip,hashlib,io,json,os,re,stat,struct,tarfile
from pathlib import Path,PurePosixPath
BASE=Path(__file__).resolve().parent;ROOT='native-followup/ktest/';MAX=2097152;WORK='/tmp/trillionnium-a01-private-sdk-N2';PIN='ff0d09a2c2e0cba1d528d11a06083f588989a9f3'
def need(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def rel(n):
 p=PurePosixPath(n);need(bool(n) and not p.is_absolute() and str(p)==n and '..' not in p.parts and '.' not in p.parts and '\\' not in n,'unsafe path '+n);return p
def read(n):
 p=BASE.joinpath(*rel(n).parts);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  a=os.fstat(fd);need(stat.S_ISREG(a.st_mode),'nonregular input')
  with os.fdopen(fd,'rb',closefd=False) as f:b=f.read()
  z=os.fstat(fd);need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns),'input changed');return b
 finally:os.close(fd)
def load(n):return json.loads(read(n))
def check(b,r,n):need(len(b)==r['bytes'] and sha(b)==r['sha256'],'size/SHA differs '+n)
def container(r,n):
 parts=[]
 for item in r['chunks']:
  b=read(item['path']);check(b,item,item['path']);need(0<len(b)<=MAX,'bad chunk size');parts.append(b)
 b=b''.join(parts);check(b,r,n);return b
def archive(r,n,source=False):
 b=container(r,n);wanted={x['member']:x for x in r['members']};need(len(wanted)==len(r['members']),'duplicate descriptor');members={}
 with tarfile.open(fileobj=io.BytesIO(b),mode='r:gz') as t:
  for item in t:
   rel(item.name);need(item.isfile() and item.name in wanted and item.name not in members,'unexpected/nonregular/duplicate tar entry');row=wanted[item.name];need(item.mode==row['mode'] and item.uid==item.gid==item.mtime==0 and item.uname==item.gname=='','tar metadata differs');raw=t.extractfile(item).read();check(raw,row,item.name)
   if source:need(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==row['git_blob'],'Git blob differs')
   members[item.name]=raw
 need(set(members)==set(wanted),'missing tar entry');return members
ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')
HEAD=re.compile(r'^running (\d+) tests in crate "([^"]+)"$',re.M)
SUMMARY=re.compile(r'test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) filtered out\.')
def parse_guest(raw,q,crate,guest):
 need(q['raw_exit_code']==33 and not q['timed_out'] and q['crate']==crate and q['stage']=='complete','guest raw result invalid');need(sha(raw)==q['serial_sha256'],'serial SHA differs');serial=ANSI.sub('',raw.decode(errors='replace')).replace('\r','')
 need(serial.count('[ktest runner] All crates tested.')==1 and len(re.findall(r'\[ktest runner\] running \d+ tests in \d+ crates',serial))==1,'runner start/complete missing or repeated');headers=list(HEAD.finditer(serial));targets=[h for h in headers if h[2]==crate];need(len(targets)==1,'target crate header missing or repeated');header=targets[0];end=next((h.start() for h in headers if h.start()>header.start()),len(serial));section=serial[header.end():end];summaries=list(SUMMARY.finditer(section));need(len(summaries)==1,'target summary missing/repeated');s=summaries[0];status,passed,failed,filtered=s[1],int(s[2]),int(s[3]),int(s[4]);declared=int(header[1]);need(status=='ok' and failed==0 and passed>0 and filtered==0 and passed+failed+filtered==declared,'target result failed/filtered/inconsistent');starts=re.findall(r'^test ([\w:]+) \.\.\.',section,re.M);need(len(starts)==passed+failed and all(n.startswith(crate.replace('-','_')+'::') for n in starts),'per-test starts differ');need(not any(r[1]=='FAILED' or int(r[3]) for r in SUMMARY.finditer(serial)),'another crate failed')
 need(not any(m in serial for m in ('An uncaught panic occurred:','Uncaught panic:','unknown panic payload! (fatal panic handling error','Non-resettable panic!','The panic handler panicked','Panicked in `PanicGuard`, aborting the system')),'fatal/uncaught kernel-test panic');skips=re.findall(r'\[skipped: ([^\]]+)\]',section);need(len(skips)<passed,'all target tests soft-skipped')
 return {'crate':crate,'declared':declared,'passed':passed,'failed':failed,'filtered':filtered,'soft_skipped':len(skips),'soft_skip_reasons':skips,'exercised_passed_lower_bound':passed-len(skips),'observed_test_starts':len(starts),'raw_qemu_exit':33,'guest':guest}
def main():
 checks={}
 for l in read('SHA256SUMS').decode().splitlines():
  h,n=l.split('  ',1);rel(n);need(re.fullmatch('[0-9a-f]{64}',h) and n not in checks,'invalid checksum row');checks[n]=h
 need({p.relative_to(BASE).as_posix() for p in BASE.rglob('*') if p.is_file() and p!=BASE/'SHA256SUMS'}==set(checks),'outer inventory differs')
 for n,h in checks.items():need(sha(read(n))==h,'outer SHA differs '+n)
 originals=archive(load('raw.manifest.json'),'raw');arts=load('artifacts/manifest.json');binary={}
 for row in arts['artifacts']:
  b=gzip.decompress(container(row,row['original_sha256']));need(len(b)==row['original_bytes'] and sha(b)==row['original_sha256'],'binary differs');binary[row['original_sha256']]=b
 for n,row in arts['original_paths'].items():need(n not in originals,'duplicate logical input');b=binary[row['artifact']];check(b,row,n);originals[n]=b
 capture=load('capture.json');need(set(originals)=={r['path'] for r in capture['files']} and len(originals)==len(capture['files']),'capture inventory differs')
 for row in capture['files']:check(originals[row['path']],row,row['path']);need(row['read_stable'],'capture source unstable')
 sm=load('source/members.json');sources=archive(sm,'source',True);binding=load('source-binding.json');commit=binding['commit_object'].encode();need(binding['producer_commit']==PIN and hashlib.sha1(b'commit '+str(len(commit)).encode()+b'\0'+commit).hexdigest()==PIN and commit.splitlines()[0].decode()=='tree '+binding['producer_complete_tree'],'source producer differs');trees=load('source/tree-objects.json');entries={}
 for digest,row in trees['objects'].items():
  b=base64.b64decode(row['raw_base64'],validate=True);need(len(b)==row['raw_bytes'] and sha(b)==row['raw_sha256'] and hashlib.sha1(b'tree '+str(len(b)).encode()+b'\0'+b).hexdigest()==digest,'tree object differs');children={};o=0
  while o<len(b):
   end=b.index(b'\0',o);mode,n=b[o:end].split(b' ',1);oid=b[end+1:end+21];need(len(oid)==20,'truncated tree');children[n.decode()]=(mode.decode(),oid.hex());o=end+21
  entries[digest]=children
 need(trees['root_tree']==binding['producer_complete_tree'],'root tree differs')
 def lookup(n):
  digest=trees['root_tree'];mode=None
  for part in PurePosixPath(n).parts:mode,digest=entries[digest][part]
  return mode,digest
 for row in sm['members']:need(row['ref']==PIN and lookup(row['path'])==(row['git_mode'],row['git_blob']),'source membership differs')
 need(lookup('kernel/asterinas')[1]==binding['derived_kernel_tree'] and sources['source/README.md']==b'','kernel/root README differs');pin=json.loads(sources['source/support/upstream-lock.json'])['kernel'];need(pin['commit']=='c4b7ed575b7b32773475b194d2ad41fb6d03765b' and pin['tree']=='96605cf64aeae2d34f29b97e85eff9315fe10a8e' and pin['toolchain']=='nightly-2026-07-21','upstream pins differ')
 a=lambda n:originals[ROOT+n];cmd=json.loads(a('controller/commands.json'));names=['source-head-clean','source-inputs','fixed-rustc','actual-ktest','post-source-inputs','post-source-head-clean'];need([(r['name'],r['returncode']) for r in cmd]==[(n,0) for n in names],'six actual controller commands not all0')
 for row in cmd:
  log=a('controller/'+row['name']+'.log');need(len(log)==row['log_bytes'] and sha(log)==row['log_sha256'] and not row.get('timed_out',False),'controller log/status differs');need(row['environment']['RUSTUP_TOOLCHAIN']=='nightly-2026-07-21' and row['environment']['CARGO_BUILD_JOBS']=='1','controller actual toolchain/jobs differ')
 need(cmd[0]['argv'][-1]==cmd[-1]['argv'][-1]==PIN and a('controller/source-head-clean.log').decode().strip()==a('controller/post-source-head-clean.log').decode().strip()==PIN,'actual head/clean differs');need(a('controller/source-inputs.log')==a('controller/post-source-inputs.log')==a('run/source-inputs.json'),'source receipts differ');source_result=json.loads(a('controller/source-inputs.log'));need(source_result['passed'] and source_result['errors']==[] and source_result['checked_files']==118,'actual source verification failed');need('87e5904f5eb6398af6b22eac2802c78934260c48' in a('controller/fixed-rustc.log').decode(),'fixed compiler differs')
 actual=cmd[3]['argv'];need(actual[:4]==['python3','-I','support/build/ktest/run.py','--output'] and len(actual)==5 and '--skip-osdk-install' not in actual,'not default two-crate private-SDK entry')
 controller=originals['controller/run-native-followup-v2.py'];review=json.loads(originals['controller/controller-review.json']);need(sha(controller)==review['sha256']=='1e1a2d51978ed0dec79ca105c746e4ad7daa743dbd47c4b9490c0dc9fd9bb25c' and review['planned_action']=='ktest' and review['planned_producer']==PIN,'reviewed followup controller identity differs')
 done=json.loads(originals['controller/outer-completed-tool.json']);need(any(type(done.get(k)) is int and done.get(k)==0 for k in ('exit_code','returncode','observed_exit_code','outer_exit_code')),'root completed-tool observation missing')
 env=json.loads(a('run/environment.json'));sdk=load('sdk-binding.json');sdkbytes=originals[sdk['logical_path']];expected='/workspace/scratch/ae1a8cf05419/native-followup/ktest/run/osdk/bin/cargo-osdk';need(env['osdk_executable']==sdk['actual_path']==expected and env['osdk_install_root']==str(PurePosixPath(expected).parents[1]) and env['osdk_source_root']==WORK+'/kernel/asterinas','private SDK paths/source differ');need(env['toolchain']=='nightly-2026-07-21' and env['osdk_install_skipped'] is False and env['test_name'] is None and env['git_head']==PIN and env['git_status']=='' and env['cargo_build_jobs']=='1','actual runner environment differs');need(len(sdkbytes)==sdk['bytes'] and sha(sdkbytes)==sdk['sha256']==env['osdk_sha256'] and sdkbytes.startswith(b'\x7fELF'),'actual private SDK payload differs');literal=(WORK+'/kernel/asterinas/osdk').encode();need(sdkbytes.count(literal)==sdk['root_literal_occurrences']>0 and sdk['expected_compiletime_source_root']==literal.decode(),'private SDK compile-time source literal differs')
 for n,h in env['build_inputs_sha256'].items():need(sha(sources['source/'+n])==h,'actual runner input source differs '+n)
 for leaf in ('.crates.toml','.crates2.json'):need(literal.decode() in a('run/osdk/'+leaf).decode(),'private SDK install metadata source differs')
 commands=json.loads(a('run/commands.json'));need(len(commands)==3,'default install/test command count differs');install=commands[0];need(install['argv']==['cargo','+nightly-2026-07-21','install','--locked','cargo-osdk','--path','osdk','--root','/workspace/scratch/ae1a8cf05419/native-followup/ktest/run/osdk'] and install['cwd']==WORK+'/kernel/asterinas','source-bound locked private install differs')
 for i,crate in enumerate(('ostd','aster-core'),1):
  args=commands[i]['argv'];need(args[:3]==[expected,'osdk','test'] and '--release' in args and len(args)==10,'direct absolute SDK default test argv differs');need(commands[i]['cwd']==WORK+'/kernel/asterinas/'+('ostd' if crate=='ostd' else 'kernel/core'),'crate cwd differs');lock=sources['source/support/build/ktest/locks/'+crate+'.Cargo.lock'];need(a('run/'+crate+'/generated.Cargo.lock')==lock and commands[i]['lock_sha256']==sha(lock),'actual generated test-base lock differs');need(int(a('run/'+crate+'/osdk-exit-code.txt'))==0,'OSDK test failed')
 result=json.loads(a('run/result.json'));need(result['passed'] and result['runner_sha256']==sha(sources['source/support/build/ktest/run.py']) and result['toolchain']=='nightly-2026-07-21' and len(result['crates'])==2,'runner result/source differs')
 for receipt in result['command_receipts']:
  doc=json.loads(a('run/'+receipt));need(doc['exit_code']==doc['raw_exit_code']==0 and doc['group_cleanup']['leader_reaped'] is True and not doc['group_cleanup']['external_reap_disarmed'],'actual runner subprocess/cleanup receipt failed')
 loaded=load('loaded-inputs.json');need(loaded['immutable_or_snapshot_execution_claimed'] is False,'snapshot/immutable execution scope widened');inputs=loaded['inputs'];rows=[];guest_keys={}
 for crate in ('ostd','aster-core'):
  parsed=[]
  qnames=sorted(n for n in originals if n.startswith(ROOT+'run/'+crate+'/guests/guest-') and n.endswith('/qemu.json'))
  need(qnames,'actual guest records missing')
  for qname in qnames:
   q=json.loads(originals[qname]);guest=PurePosixPath(qname).parent.name;raw=originals[str(PurePosixPath(qname).parent/'serial.log')];parsed.append(parse_guest(raw,q,crate,guest));guest_keys[(crate,guest)]=qname
   profile=q['profile'];need(profile=={'arch':'x86_64','machine':'q35','accel':'tcg','cpu':'max','vcpus':1,'memory_mib':512,'network':False,'data_disks':False},'actual QEMU test profile differs');need(q['input_selector_source']['sha256']==sha(sources['source/support/build/record-qemu.py']),'actual selector helper differs')
   for option,r in q['artifacts'].items():
    matches=[x for x in inputs if x['crate']==crate and x['guest']==guest and x['option']==option];need(len(matches)==1,'loaded input mapping missing/repeated');row=matches[0];b=originals[row['captured_path']];need(row['qemu_record']==qname and row['actual_loaded_path']==r['path'] and len(b)==r['size']==row['bytes'] and sha(b)==r['sha256']==row['sha256'],'actual loaded input bytes differ');need(q['argv'][q['argv'].index(option)+1]==r['path'],'actual argv did not use recorded original loaded path')
    if option=='-kernel':need(b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<HH',b,16)==(2,3) and b[:8192].find(struct.pack('<I',0x1badb002))>=0,'not actual OSDK kernel-test ELF')
  observed=json.loads(a('run/'+crate+'/result.json'));need(observed=={'passed':True,'guests':parsed} and result['crates'][('ostd','aster-core').index(crate)]==observed,'actual checker parsed counts differ');rows.extend(parsed)
 need(set((r['crate'],r['guest']) for r in inputs)==set(guest_keys),'loaded input/guest inventory differs')
 totals={k:sum(r[k] for r in rows) for k in ('declared','passed','failed','filtered','soft_skipped','exercised_passed_lower_bound','observed_test_starts')};report=load('report.json');need(report['producer_commit']==PIN and report['totals']==totals and report['runner_result']==result and report['controller_commands']==6,'report counts/source differ');need(report['target_reused'] and not any(report[k] for k in ('cold_build_claimed','snapshot_loaded_execution_claimed','immutable_execution_claimed','all_project_blockers_closed')),'ktest acceptance scope widened');counts={crate:len(re.findall(rb'^\s*Compiling\s',a('run/'+crate+'/osdk-test.log'),re.M)) for crate in ('ostd','aster-core')};need(counts==report['compile_lines_by_crate'],'actual compilation accounting differs')
 need(read('readable/environment.json')==a('run/environment.json') and read('readable/controller-commands.json')==a('controller/commands.json') and read('readable/runner-result.json')==a('run/result.json'),'readable core copies differ')
 for qname in guest_keys.values():
  relative=qname[len(ROOT):]
  for leaf in ('qemu.json','serial.log'):
   n=str(PurePosixPath(relative).parent/leaf);need(read('readable/'+n)==a(n),'readable guest copy differs')
 print(json.dumps({'passed':True,'source_commit':PIN,'original_files':len(originals),'source_controls':len(sources),'private_sdk_sha256':sha(sdkbytes),'guest_count':len(rows),'raw_guest_exits':[33]*len(rows),'totals':totals,'compile_lines_by_crate':counts,'cold_build_claimed':False,'snapshot_loaded_execution_claimed':False,'scope':'Offline preserved private-SDK full-crate kernel-test evidence; only retained bytes parsed, no compiler, SDK, original target access or guest execution.'},sort_keys=True))
if __name__=='__main__':main()
