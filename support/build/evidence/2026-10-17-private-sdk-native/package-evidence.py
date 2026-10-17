#!/usr/bin/env python3
"""Package only a completed ordinary N2 run; never build, invoke SDK or read targets."""
import argparse,base64,datetime,gzip,hashlib,io,json,os,pathlib,stat,subprocess,tarfile
ROOT=pathlib.Path('/workspace/scratch/ae1a8cf05419');REPO=ROOT/'trillionnium-os-desktop';RUN=ROOT/'private-sdk-native-N2';MAX=2097152
def need(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def captured(path):
 before=path.lstat();fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  opened=os.fstat(fd);keys=('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns');ident=lambda s:{k:getattr(s,k) for k in keys}
  need(stat.S_ISREG(opened.st_mode) and ident(before)==ident(opened),'capture not stable regular '+str(path))
  with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read()
  need(ident(opened)==ident(os.fstat(fd))==ident(path.lstat()),'capture changed '+str(path))
  return raw,{'source':str(path),'bytes':len(raw),'sha256':sha(raw),'source_stat':ident(opened),'read_stable':True}
 finally:os.close(fd)
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*args])
def tar(files):
 out=io.BytesIO()
 with gzip.GzipFile(fileobj=out,filename='',mode='wb',mtime=0) as gz:
  with tarfile.open(fileobj=gz,mode='w|',format=tarfile.GNU_FORMAT) as t:
   for name,raw,mode in files:
    i=tarfile.TarInfo(name);i.size=len(raw);i.mode=mode;i.uid=i.gid=i.mtime=0;i.uname=i.gname='';t.addfile(i,io.BytesIO(raw))
 return out.getvalue()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer',required=True);p.add_argument('--done-receipt',type=pathlib.Path,required=True);p.add_argument('--global-before',type=pathlib.Path,required=True);p.add_argument('--global-after',type=pathlib.Path,required=True);p.add_argument('--phase',type=pathlib.Path,default=REPO/'support/build/evidence/2026-10-17-private-sdk-native');a=p.parse_args()
 need(a.phase.absolute()==REPO/'support/build/evidence/2026-10-17-private-sdk-native','phase outside owner scope')
 commands=json.loads((RUN/'controller-N2/commands.json').read_text());names=['worktree','source-verification','target-absence','fresh-make-kernel','freeze-first-produced-kernel','make-run-kernel','boot-live-recheck','post-source-verification','worktree-status','installed-components','installed-targets']
 need([(r['name'],r.get('returncode')) for r in commands]==[(n,0) for n in names],'N2 is not complete successful eleven-command run')
 need(commands[0]['argv'][-1]==a.producer,'producer mismatch')
 done_raw,done_capture=captured(a.done_receipt);done=json.loads(done_raw);need(any(type(done.get(k)) is int and done.get(k)==0 for k in ('exit_code','returncode','outer_exit_code','observed_exit_code')),'explicit root completed-tool exit0 receipt missing')
 q=json.loads((RUN/'kernel-boot/qemu.json').read_text());need(q['raw_exit_code']==q['recorder_exit_code']==33 and q['timed_out'] is False and q['stage']=='complete','guest not accepted')
 a.phase.mkdir(exist_ok=False)
 def write(name,raw):
  dest=a.phase/name;dest.parent.mkdir(parents=True,exist_ok=True)
  with dest.open('xb') as f:f.write(raw)
 def save(name,v):write(name,(json.dumps(v,indent=2)+'\n').encode())
 def chunks(name,raw):
  rows=[]
  for n,o in enumerate(range(0,len(raw),MAX)):
   part=f'{name}.part{n:03}';b=raw[o:o+MAX];write(part,b);rows.append({'path':part,'bytes':len(b),'sha256':sha(b)})
  return {'bytes':len(raw),'sha256':sha(raw),'chunks':rows}
 originals={};capture=[]
 listed=sorted(x for x in RUN.rglob('*') if x.is_file() or x.is_symlink())
 for path in listed:
  name=RUN.name+'/'+path.relative_to(RUN).as_posix();need('/target/' not in name,'refuse target tree')
  raw,row=captured(path);originals[name]=raw;capture.append({'path':name,**row})
 extras={'controller/run-private-sdk-native-n2.py':ROOT/'round-next/run-private-sdk-native-n2.py','controller/published-N1.py':REPO/'support/build/evidence/2026-10-17-native-cloud-normal/readable/run-normal-cloud-final.py','controller/origin.json':ROOT/'round-next/n2-controller-origin.json','controller/independent-review.json':ROOT/'round-next/n2-controller-review/review.json','controller/independent-diff.patch':ROOT/'round-next/n2-controller-review/diff.patch','controller/root-postcheck.py':ROOT/'round-next/n2-postcheck.py','global-sdk/before.json':a.global_before,'global-sdk/after.json':a.global_after,'controller/outer-completed-tool.json':a.done_receipt}
 for name,path in extras.items():
  raw,row=captured(path);originals[name]=raw;capture.append({'path':name,**row})
 need(listed==sorted(x for x in RUN.rglob('*') if x.is_file() or x.is_symlink()),'completed run inventory changed')
 for row in capture:
  raw,again=captured(pathlib.Path(row['source']));need(raw==originals[row['path']] and again['source_stat']==row['source_stat'],'original changed after capture')
 binary={};rawfiles=[]
 for name,b in sorted(originals.items()):
  if b.startswith(b'\x7fELF') or name.endswith(('.cpio.gz','/bios.bin')):
   key=sha(b);binary.setdefault(key,{'data':b,'paths':[]})['paths'].append(name)
  else:rawfiles.append((name,b,0o644))
 rawarchive=tar(rawfiles);rawdesc=chunks('raw/originals.tar.gz',rawarchive);rawdesc['members']=[{'member':n,'bytes':len(b),'sha256':sha(b),'mode':m} for n,b,m in rawfiles];save('raw.manifest.json',rawdesc)
 artifactrows=[];logical={}
 for key,record in sorted(binary.items()):
  b=record['data'];d=chunks('artifacts/'+key+'.gz',gzip.compress(b,mtime=0));d.update(original_bytes=len(b),original_sha256=key,original_paths=record['paths']);artifactrows.append(d)
  for name in record['paths']:logical[name]={'artifact':key,'bytes':len(b),'sha256':key}
 save('artifacts/manifest.json',{'artifacts':artifactrows,'original_paths':logical});save('capture.json',{'files':capture,'capture_scope':'Completed N2 output, external controller/origin/review and global SDK before/after receipts only; no original target access.'})
 # The historic normal phase's complete runtime-control selection is reused
 # by path, but every byte and tree membership comes from the new producer.
 prior=json.loads((REPO/'support/build/evidence/2026-10-17-native-cloud-normal/source/members.json').read_text())
 sourcefiles=[];members=[];path_trees={'':git('rev-parse',a.producer+'^{tree}').decode().strip()}
 for row in prior['members']:
  path=row['path'];entry=git('ls-tree',a.producer,'--',path).decode().strip();mode,typ,digest=entry.split('\t',1)[0].split();need(typ=='blob' and mode in ('100644','100755'),'source path not regular Git blob')
  b=git('cat-file','blob',digest);member='source/'+path;sourcefiles.append((member,b,int(mode,8)&0o777));members.append({'member':member,'path':path,'mode':int(mode,8)&0o777,'git_mode':mode,'git_blob':digest,'ref':a.producer,'bytes':len(b),'sha256':sha(b)})
  parent=pathlib.PurePosixPath(path).parent
  for tree in [*reversed(parent.parents),parent]:
   name='' if str(tree)=='.' else str(tree)
   if name and name not in path_trees:path_trees[name]=git('rev-parse',a.producer+':'+name).decode().strip()
 sourcearchive=tar(sourcefiles);sdesc=chunks('source/controls.tar.gz',sourcearchive);sdesc['members']=members;save('source/members.json',sdesc)
 trees={}
 for digest in set(path_trees.values()):
  b=git('cat-file','tree',digest);trees[digest]={'raw_base64':base64.b64encode(b).decode(),'raw_bytes':len(b),'raw_sha256':sha(b)}
 save('source/tree-objects.json',{'root_tree':path_trees[''],'path_trees':path_trees,'objects':trees})
 commit=git('cat-file','commit',a.producer).decode();kernel_tree=git('rev-parse',a.producer+':kernel/asterinas').decode().strip()
 save('source-binding.json',{'producer_commit':a.producer,'producer_complete_tree':path_trees[''],'derived_kernel_tree':kernel_tree,'commit_object':commit,'scope':'Exact producer commit/tree and selected runtime-control Git paths, not a second full kernel source import.'})
 first=json.loads(originals[RUN.name+'/controller-N2/freeze-first-produced-kernel.log']);boot=originals[RUN.name+'/'+q['artifacts']['-kernel']['path'].split('/'+RUN.name+'/',1)[1]]
 compile_counts={stage:sum(1 for line in originals[RUN.name+'/'+stage+'/'+log].splitlines() if line.lstrip().startswith(b'Compiling ')) for stage,log in [('kernel-build','kernel.log'),('kernel-boot','run_kernel.log')]}
 sdk=[]
 for stage in ('kernel-build','kernel-boot'):
  path=f'{RUN.name}/{stage}/osdk/bin/cargo-osdk';b=originals[path];root='/tmp/trillionnium-a01-private-sdk-N2/kernel/asterinas/osdk';record={'stage':stage,'original_path':str(RUN/stage/'osdk/bin/cargo-osdk'),'logical_path':path,'bytes':len(b),'sha256':sha(b),'expected_compiletime_osdk_root':root,'expected_root_occurrences':b.count(root.encode()),'source_binding_scope':'Observed exact embedded compile-time source path together with pinned OSDK source option_env!/env! implementation and actual locked install command/log; not a compiler attestation.'};need(record['expected_root_occurrences']>0,'private SDK binary does not embed N2 source');sdk.append(record)
 save('sdk-bindings.json',{'private_sdks':sdk,'same_private_sdk_hashes':sdk[0]['sha256']==sdk[1]['sha256'],'same_private_sdk_complete_bytes':originals[sdk[0]['logical_path']]==originals[sdk[1]['logical_path']],'global_before_receipt':'global-sdk/before.json','global_after_receipt':'global-sdk/after.json','global_comparison':'Observed before/after SHA256 and stable-FD path/stat only; no prelaunch global binary payload was retained, so no full global before/after byte comparison is claimed.','global_prelaunch_binary_payload_retained':False,'global_complete_before_after_bytes_compared':False})
 save('report.json',{'schema':'a01-private-sdk-native/1','case':'N2','producer_commit':a.producer,'producer_complete_tree':path_trees[''],'derived_kernel_tree':kernel_tree,'actual_controller_sha256':sha(originals['controller/run-private-sdk-native-n2.py']),'controller_commands':11,'cold_target_absent_before_first_build':True,'cold_make_kernel_passed':True,'subsequent_make_run_kernel_passed':True,'raw_qemu_exit':33,'profile_opt_in':False,'first_kernel_elf':first,'first_and_boot_kernel_complete_bytes_equal':originals[RUN.name+'/first-build-kernel.elf']==boot,'compile_lines':compile_counts,'actual_host':os.uname().nodename,'cross_instance_elf_equality_claimed':False,'immutable_host_claimed':False,'all_project_blockers_closed':False,'captured_original_files':len(originals),'unique_binary_payloads':len(binary),'source_controls':len(sourcefiles),'packaged_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':['Only an ordinary cold build and its subsequent warm boot are accepted here.','Private SDK paths are exclusive per action; byte equality between them is observed separately.','Global SDK identity stability is based on captured before/after observations, not prevention of arbitrary concurrent external writers.','No source target tree was captured or read by this packager.']})
 for name in ('kernel-boot/serial.log','kernel-boot/qemu.json','kernel-build/environment.log','kernel-boot/environment.log','kernel-build/command.sh','kernel-boot/command.sh','controller-N2/commands.json'):
  write('readable/'+name,originals[RUN.name+'/'+name])
 print(json.dumps({'phase':str(a.phase),'originals':len(originals),'binary_payloads':len(binary),'source_controls':len(sourcefiles),'producer':a.producer},indent=2))
if __name__=='__main__':main()
