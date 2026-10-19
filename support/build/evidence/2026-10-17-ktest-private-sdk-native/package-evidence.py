#!/usr/bin/env python3
"""Freeze completed private-SDK ktests and only explicitly loaded target inputs."""
import argparse,base64,datetime,gzip,hashlib,io,json,os,stat,subprocess,tarfile
from pathlib import Path,PurePosixPath
ROOT=Path('/workspace/scratch/ae1a8cf05419');REPO=ROOT/'trillionnium-os-desktop';RUN=ROOT/'native-followup/ktest';WORK=Path('/tmp/trillionnium-a01-private-sdk-N2');MAX=2097152
def need(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def captured(p):
 before=p.lstat();fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  s=os.fstat(fd);keys=('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns');ident=lambda z:{k:getattr(z,k) for k in keys};need(stat.S_ISREG(s.st_mode) and ident(before)==ident(s),'unstable/nonregular capture '+str(p))
  with os.fdopen(fd,'rb',closefd=False) as f:b=f.read()
  need(ident(s)==ident(os.fstat(fd))==ident(p.lstat()),'source changed '+str(p));return b,{'source':str(p),'bytes':len(b),'sha256':sha(b),'source_stat':ident(s),'read_stable':True}
 finally:os.close(fd)
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*args])
def tar(files):
 out=io.BytesIO()
 with gzip.GzipFile(fileobj=out,filename='',mode='wb',mtime=0) as gz:
  with tarfile.open(fileobj=gz,mode='w|',format=tarfile.GNU_FORMAT) as stream:
   for n,b,m in files:
    i=tarfile.TarInfo(n);i.size=len(b);i.mode=m;i.uid=i.gid=i.mtime=0;i.uname=i.gname='';stream.addfile(i,io.BytesIO(b))
 return out.getvalue()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer',required=True);p.add_argument('--done-receipt',type=Path,required=True);a=p.parse_args();phase=REPO/'support/build/evidence/2026-10-17-ktest-private-sdk-native'
 need(a.producer=='ff0d09a2c2e0cba1d528d11a06083f588989a9f3','wrong planned ktest producer')
 cmds=json.loads((RUN/'controller/commands.json').read_text());names=['source-head-clean','source-inputs','fixed-rustc','actual-ktest','post-source-inputs','post-source-head-clean'];need([(r['name'],r.get('returncode')) for r in cmds]==[(n,0) for n in names],'six controller commands incomplete/not all0');need(cmds[0]['argv'][-1]==a.producer,'source mismatch')
 done=json.loads(a.done_receipt.read_text());need(any(type(done.get(k)) is int and done.get(k)==0 for k in ('exit_code','returncode','observed_exit_code','outer_exit_code')),'root actual completed-tool exit0 missing')
 result=json.loads((RUN/'run/result.json').read_text());need(result['passed'] and len(result['crates'])==2,'both crate results not complete')
 phase.mkdir(exist_ok=False)
 def write(n,b):
  dest=phase/n;dest.parent.mkdir(parents=True,exist_ok=True)
  with dest.open('xb') as f:f.write(b)
 def save(n,v):write(n,(json.dumps(v,indent=2)+'\n').encode())
 def chunks(n,b):
  parts=[]
  for i,o in enumerate(range(0,len(b),MAX)):
   name=f'{n}.part{i:03}';piece=b[o:o+MAX];write(name,piece);parts.append({'path':name,'bytes':len(piece),'sha256':sha(piece)})
  return {'bytes':len(b),'sha256':sha(b),'chunks':parts}
 originals={};capture=[];listed=sorted(p for p in RUN.rglob('*') if p.is_file() or p.is_symlink())
 for path in listed:
  n='native-followup/ktest/'+path.relative_to(RUN).as_posix();b,row=captured(path);originals[n]=b;capture.append({'path':n,**row})
 reviewed=ROOT/'round-next/ktest-evidence-prep/controller-reviewed.py';review=json.loads((ROOT/'round-next/ktest-evidence-prep/controller-review.json').read_text());need(sha(reviewed.read_bytes())==review['sha256'] and (ROOT/'round-next/run-native-followup-v2.py').read_bytes()==reviewed.read_bytes(),'followup controller changed from reviewed bytes')
 extras={'controller/run-native-followup-v2.py':reviewed,'controller/controller-review.json':ROOT/'round-next/ktest-evidence-prep/controller-review.json','controller/outer-completed-tool.json':a.done_receipt}
 for n,path in extras.items():
  b,row=captured(path);originals[n]=b;capture.append({'path':n,**row})
 loaded=[]
 for crate in ('ostd','aster-core'):
  guests=sorted((RUN/'run'/crate/'guests').glob('guest-*/qemu.json'));need(guests,'no guest records')
  for record in guests:
   q=json.loads(record.read_text());need(q['raw_exit_code']==33 and not q['timed_out'] and q['stage']=='complete' and q['crate']==crate,'guest not accepted')
   for option,artifact in q['artifacts'].items():
    need(option in ('-kernel','-bios','-initrd'),'unexpected loaded option');path=Path(artifact['path']);need(path.is_absolute(),'nonabsolute loaded path')
    if option=='-kernel':need(path.is_relative_to(WORK/'kernel/asterinas/target'),'kernel input is outside held source target')
    elif option=='-bios':need(path.is_relative_to(ROOT/'native-tools/root'),'guest BIOS is outside private tools')
    else:need(path.is_relative_to(WORK/'kernel/asterinas/target') or path.is_relative_to(RUN),'initrd input outside known roots')
    b,row=captured(path);need(len(b)==artifact['size'] and sha(b)==artifact['sha256'],'loaded input no longer matches guest record')
    n=f'loaded-inputs/{crate}/{record.parent.name}/{option[1:]}';originals[n]=b;capture.append({'path':n,**row});loaded.append({'crate':crate,'guest':record.parent.name,'option':option,'qemu_record':'native-followup/ktest/'+record.relative_to(RUN).as_posix(),'actual_loaded_path':str(path),'captured_path':n,'bytes':len(b),'sha256':sha(b),'capture_timing':'After root RUN DONE, before held worktree/target release; actual QEMU used original path, not this later evidence copy.'})
 need(listed==sorted(p for p in RUN.rglob('*') if p.is_file() or p.is_symlink()),'completed outer inventory changed')
 for row in capture:
  b,again=captured(Path(row['source']));need(b==originals[row['path']] and again['source_stat']==row['source_stat'],'source changed on second capture')
 print('CAPTUREDONE: completed output and only recorded loaded inputs captured and rechecked',flush=True)
 raw=[];binary={}
 for n,b in sorted(originals.items()):
  if b.startswith(b'\x7fELF') or n.startswith('loaded-inputs/') or n.endswith('.cpio.gz'):binary.setdefault(sha(b),{'data':b,'paths':[]})['paths'].append(n)
  else:raw.append((n,b,0o644))
 desc=chunks('raw/originals.tar.gz',tar(raw));desc['members']=[{'member':n,'bytes':len(b),'sha256':sha(b),'mode':m} for n,b,m in raw];save('raw.manifest.json',desc)
 arts=[];logical={}
 for digest,r in sorted(binary.items()):
  b=r['data'];d=chunks('artifacts/'+digest+'.gz',gzip.compress(b,mtime=0));d.update(original_bytes=len(b),original_sha256=digest,original_paths=r['paths']);arts.append(d)
  for n in r['paths']:logical[n]={'artifact':digest,'bytes':len(b),'sha256':digest}
 save('artifacts/manifest.json',{'artifacts':arts,'original_paths':logical});save('capture.json',{'files':capture,'scope':'Completed outer, controller and explicitly qemu.json-listed actual loaded inputs only. No target directory dump; kernel inputs were read from their actual target paths after RUN DONE.'});save('loaded-inputs.json',{'inputs':loaded,'immutable_or_snapshot_execution_claimed':False})
 old=json.loads((REPO/'support/build/evidence/2026-10-17-native-cloud-normal/source/members.json').read_text());paths={r['path'] for r in old['members']};paths.update(git('ls-tree','-r','--name-only',a.producer,'--','support/build/ktest').decode().splitlines());source=[];members=[];trees_by_path={'':git('rev-parse',a.producer+'^{tree}').decode().strip()}
 for path in sorted(paths):
  entry=git('ls-tree',a.producer,'--',path).decode().strip();m,t,d=entry.split('\t',1)[0].split();need(t=='blob' and m in ('100644','100755'),'source path not blob');b=git('cat-file','blob',d);n='source/'+path;mode=int(m,8)&0o777;source.append((n,b,mode));members.append({'member':n,'path':path,'mode':mode,'git_mode':m,'git_blob':d,'ref':a.producer,'bytes':len(b),'sha256':sha(b)})
  parent=PurePosixPath(path).parent
  for tree in [*reversed(parent.parents),parent]:
   n='' if str(tree)=='.' else str(tree)
   if n and n not in trees_by_path:trees_by_path[n]=git('rev-parse',a.producer+':'+n).decode().strip()
 desc=chunks('source/controls.tar.gz',tar(source));desc['members']=members;save('source/members.json',desc)
 objects={}
 for d in set(trees_by_path.values()):
  b=git('cat-file','tree',d);objects[d]={'raw_base64':base64.b64encode(b).decode(),'raw_bytes':len(b),'raw_sha256':sha(b)}
 save('source/tree-objects.json',{'root_tree':trees_by_path[''],'path_trees':trees_by_path,'objects':objects});save('source-binding.json',{'producer_commit':a.producer,'producer_complete_tree':trees_by_path[''],'derived_kernel_tree':git('rev-parse',a.producer+':kernel/asterinas').decode().strip(),'commit_object':git('cat-file','commit',a.producer).decode()})
 env=json.loads(originals['native-followup/ktest/run/environment.json']);sdkname='native-followup/ktest/run/osdk/bin/cargo-osdk';sdk=originals[sdkname];sdkroot=str(WORK/'kernel/asterinas/osdk');need(sdk.count(sdkroot.encode())>0 and sha(sdk)==env['osdk_sha256'],'private SDK source/SHA differs')
 save('sdk-binding.json',{'logical_path':sdkname,'actual_path':str(RUN/'run/osdk/bin/cargo-osdk'),'bytes':len(sdk),'sha256':sha(sdk),'expected_compiletime_source_root':sdkroot,'root_literal_occurrences':sdk.count(sdkroot.encode()),'actual_source_bound_install_skipped':False,'scope':'Actual private SDK full bytes, installation metadata, original direct absolute SDK commands and embedded compile-time source literal; not compiler attestation.'})
 guests=[g for r in result['crates'] for g in r['guests']];totals={k:sum(g[k] for g in guests) for k in ('declared','passed','failed','filtered','soft_skipped','exercised_passed_lower_bound','observed_test_starts')};compilelines={crate:sum(1 for l in originals[f'native-followup/ktest/run/{crate}/osdk-test.log'].splitlines() if l.lstrip().startswith(b'Compiling ')) for crate in ('ostd','aster-core')}
 save('report.json',{'schema':'a01-ktest-private-sdk-native/1','producer_commit':a.producer,'controller_commands':6,'actual_host':os.uname().nodename,'target_reused':True,'cold_build_claimed':False,'runner_result':result,'totals':totals,'compile_lines_by_crate':compilelines,'raw_guest_exits':[33 for _ in guests],'preserved_original_files':len(originals),'unique_binary_payloads':len(binary),'selected_source_controls':len(source),'private_sdk_sha256':sha(sdk),'snapshot_loaded_execution_claimed':False,'immutable_execution_claimed':False,'all_project_blockers_closed':False,'packaged_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
 for crate in ('ostd','aster-core'):
  for record in sorted((RUN/'run'/crate/'guests').glob('guest-*/qemu.json')):
   for leaf in ('qemu.json','serial.log'):
    relative=(record.parent/leaf).relative_to(RUN).as_posix();write('readable/'+relative,originals['native-followup/ktest/'+relative])
 write('readable/environment.json',originals['native-followup/ktest/run/environment.json']);write('readable/controller-commands.json',originals['native-followup/ktest/controller/commands.json']);write('readable/runner-result.json',originals['native-followup/ktest/run/result.json'])
 print(json.dumps({'originals':len(originals),'unique_binaries':len(binary),'source_controls':len(source),'totals':totals,'compile_lines':compilelines},sort_keys=True))
if __name__=='__main__':main()
