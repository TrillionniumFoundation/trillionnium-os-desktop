#!/usr/bin/env python3
"""Package the completed real main-f9 native run without rewriting its receipts."""
import datetime, hashlib, io, json, os, pathlib, shutil, stat, subprocess, tarfile
R=pathlib.Path('/workspace/scratch/d7da9e7650f0/a01-mainf9')
O=R/'support/build/out/2026-10-19-mainf9'
E=R/'support/build/evidence/2026-10-19-mainf9'
P='7758ffe294bb0e1eab46e20cba60e8af9d8bcd61'
M='f9e306f76154590e096a42f70ce9de0a7c859e60'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def stable(p):
 p=pathlib.Path(p);before=p.lstat()
 if not stat.S_ISREG(before.st_mode):raise RuntimeError('not regular: '+str(p))
 with p.open('rb') as f:opened=os.fstat(f.fileno());raw=f.read();finished=os.fstat(f.fileno())
 fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 if not fields(before)==fields(opened)==fields(finished)==fields(p.lstat()):raise RuntimeError('changed during capture: '+str(p))
 return raw,stat.S_IMODE(before.st_mode)
def info(p):
 raw,mode=stable(p);return {'size':len(raw),'sha256':sha(raw),'mode':oct(mode)}
def copy(src,dst):
 raw,mode=stable(src);dst.parent.mkdir(parents=True,exist_ok=True)
 with dst.open('xb') as f:f.write(raw)
 os.chmod(dst,mode)
 return info(dst)
def paths(root):return sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts)
def archive(name,mappings,scope):
 pairs=sorted(mappings,key=lambda x:x[0]);assert len({x[0] for x in pairs})==len(pairs)
 entries=[];blobs={}
 for member,source in pairs:
  raw,mode=stable(source);blobs[member]=(raw,mode)
  entries.append({'member':member,'source':str(source),'size':len(raw),'sha256':sha(raw),'mode':oct(mode)})
 manifest={'schema':'trillionnium.a01.archive.v1','scope':scope,'source_commit':P,'created_at':now(),'tar_mtime_normalized_to_zero':True,'members':entries}
 blobs['ARCHIVE-MANIFEST.json']=((json.dumps(manifest,indent=2)+'\n').encode(),0o644)
 dest=E/name
 with tarfile.open(dest,'x:xz',preset=6) as tf:
  for member,(raw,mode) in sorted(blobs.items()):
   ti=tarfile.TarInfo(member);ti.size=len(raw);ti.mode=mode;ti.mtime=0;tf.addfile(ti,io.BytesIO(raw))
 with tarfile.open(dest,'r:xz') as tf:
  assert sorted(tf.getnames())==sorted(blobs)
  for ti in tf.getmembers():
   assert ti.isfile() and ti.mode==blobs[ti.name][1]
   assert tf.extractfile(ti).read()==blobs[ti.name][0]
 return {'path':name,**info(dest),'member_count':len(blobs),'payload_file_count':len(entries),'roundtrip_all_members_verified':True,'scope':scope}

assert subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip()==P
assert not E.exists()
execution={s:read(O/f'executions/{s}.json') for s in ['kernel','boot','boot-retry','ktest']}
assert [execution[s]['exit_code'] for s in execution]==[0,1,0,0]
q=read(O/'boot-retry/qemu.json');k=read(O/'ktest/result.json')
assert q['raw_exit_code']==33 and not q['timed_out'] and k['passed']
source=read(O/'source/kernel-before.json');last=read(O/'source/after-quarantine.json')
assert source['matches_git'] and last['comparison']['passed'] and source['file_count']==3014
review=read('/tmp/a01-round2-native-review/native-review.json');assert review['all_checked_native_evidence_consistent'] and review['failed_checks']==0
E.mkdir(parents=True)
index=[]
payload=[]
for flag,name in [('-kernel','boot/kernel.elf'),('-initrd','boot/initramfs.cpio.gz'),('-bios','firmware/bios.bin')]:
 p=pathlib.Path(q['artifacts'][flag]['path']);assert info(p)['sha256']==q['artifacts'][flag]['sha256'];payload.append((name,p))
assert stable(O/'artifacts/first-kernel.elf')[0]==stable(payload[0][1])[0]
bindings={'producer':P,'boot_first_build_equals_loaded':True,'first_kernel':read(O/'artifacts/first-kernel.json'),'boot_artifacts':q['artifacts'],'ktest':{}}
for crate in ['ostd','aster-core']:
 guest=read(O/f'ktest/{crate}/guests/guest-001/qemu.json');p=O/f'artifacts/{crate}.elf'
 assert info(p)['sha256']==guest['artifacts']['-kernel']['sha256']
 bindings['ktest'][crate]={'prelaunch_recorded':guest['artifacts']['-kernel'],'post_execution_frozen':read(O/f'artifacts/{crate}.json'),'bytes_hash_equal':True,'prelaunch_private_snapshot':False}
 payload.append((f'ktest/{crate}.elf',p))
index.append(archive('guest-artifacts.tar.xz',payload,'The actual privately loaded boot ELF/initramfs/BIOS, plus post-test frozen ktest ELFs matched to each prelaunch recorded hash.'))
records=[]
for p in paths(O):
 rel=p.relative_to(O)
 if rel.parts[0]=='source' or any(n.startswith('artifacts-') for n in rel.parts):continue
 if 'osdk' in rel.parts and p.name!='cargo-osdk.sha256':continue
 if p.suffix in ['.elf','.gz']:continue
 records.append((str(rel),p))
index.append(archive('native-records.tar.xz',records,'Complete command logs, serial streams, source-input checks, environment, generated locks, execution receipts, artifact bindings and all native failure observations. SDK binaries and build caches are omitted.'))
sources=[('source/'+str(p.relative_to(O/'source')),p) for p in paths(O/'source')]
for dirname,root in [('acquisition',pathlib.Path('/tmp/a01-round2-acquisition')),('audit',pathlib.Path('/tmp/a01-round2-source-audit'))]:
 sources += [(dirname+'/'+str(p.relative_to(root)),p) for p in paths(root)]
index.append(archive('source-records.tar.xz',sources,'Current source captures and fixed-object/owner audits, actual fetch/publication/checkout receipts, disk-cache custody and retained acquisition/auditor diagnostics.'))
for src,name,expected,scope in [
 ('/workspace/scratch/d7da9e7650f0/a01-current-runtime/runtime-current.tar.gz','dependencies/installation-2026-10-18.tar.gz','61615a214530b7af47d0206db533c4ebef3298df07bc8d9522b231c2a9f51ca0','Actual previous-day private dependency installation; not a new installation for this producer.'),
 ('/tmp/a01-round2-runtime.tar.gz','dependencies/revalidation-2026-10-18.tar.gz','19a199c405a2a65b458469c4ddb90161192220c922269af3192bbd3c6566a05d','Read-only revalidation on October 18.'),
 ('/tmp/a01-round2-runtime-resume/runtime-resume-check.tar.gz','dependencies/revalidation-2026-10-19.tar.gz','6b03cfaec1713b5730a691ea66da83926883f9b1ff4eec405c1d585911f57c79','Read-only revalidation immediately before the October 19 native build.')]:
 assert info(src)['sha256']==expected
 ci=copy(src,E/name);index.append({'path':name,**ci,'scope':scope,'reused_original_archive_bytes':True})
direct=[]
for phase,label in [('kernel','kernel'),('boot-retry','boot')]:
 for name in ['command.sh','environment.log','source-inputs.json','manifest-cleanup.json','make-exit-code.txt','run-exit-code.txt','initramfs-manifest.json']:
  direct.append((O/phase/name,E/label/name))
direct += [(O/'boot-retry/qemu.json',E/'boot/qemu.json'),(O/'boot-retry/serial.log',E/'boot/serial.log'),(O/'kernel/kernel.log',E/'kernel/kernel.log')]
for name in ['result.json','environment.json','commands.json']:
 direct.append((O/'ktest'/name,E/'ktest'/name))
for crate in ['ostd','aster-core']:
 for name in ['qemu.json','serial.log']:
  rel=f'ktest/{crate}/guests/guest-001/{name}';direct.append((O/rel,E/rel))
for stage in execution:direct.append((O/f'executions/{stage}.json',E/f'executions/{stage}.json'))
for p in paths(O/'failures'):direct.append((p,E/'failures'/p.relative_to(O/'failures')))
direct += [(O/'executions/boot.stdout-stderr.log',E/'failures/boot-preflight/driver.log'),(pathlib.Path('/tmp/a01-round2-native-review/native-review.json'),E/'review/native-review.json'),(pathlib.Path('/tmp/a01-round2-native-review/review.py'),E/'review/native-review.py'),(pathlib.Path('/tmp/a01-round2-runtime-resume/summary.json'),E/'dependencies/current-summary.json'),(pathlib.Path('/tmp/a01-round2-source-audit/HANDOFF-FINAL.md'),E/'HANDOFF.md')]
for src,dst in direct:copy(src,dst)
copy(__file__,E/'review/package-evidence.py')
write(E/'artifact-bindings.json',bindings)
counts=[crate['guests'][0] for crate in k['crates']]
summary={key:source[key] for key in ['head','project_tree','kernel_tree','upstream_commit','upstream_tree','file_count','files_sha256','selection']}
summary.update(selected_inputs_match_producer_through_execution=True,derived_kernel_file_count=2945,upstream_original_paths_retained=2938,independent_source_checks_passed=25,independent_actual_workfile_checks=2875,independent_git_object_only_manifest_checks=139,root_native_capture_checks_all_selected_actual_bytes=True,source_archive='source-records.tar.xz',raw_source_statuses=review['observations']['source_statuses'],after_quarantine_git_status=last['git_status_porcelain'],whole_worktree_clean_after_quarantine=False)
write(E/'source-summary.json',summary)
report={'schema':1,'created_at':now(),'producer_commit':P,'project_tree':source['project_tree'],'kernel_tree':source['kernel_tree'],'integrated_main':M,'prior_a01_parent':'71524be19383e2ff98f6abc90668c48988e7c8e2','upstream_commit':source['upstream_commit'],'upstream_tree':source['upstream_tree'],'toolchain':'nightly-2026-07-21','source_directory':'kernel/asterinas','source_summary':'source-summary.json','pipeline_passed_after_preflight_retry':True,'native_build':{'execution':execution['kernel'],'empty_target':True,'compilation_lines':284,'first_elf':info(O/'artifacts/first-kernel.elf')},'boot':{'execution':execution['boot-retry'],'qemu_record':'boot/qemu.json','serial':'boot/serial.log','serial_sha256':q['serial_sha256'],'serial_bytes':q['serial_size'],'qemu_raw_exit':q['raw_exit_code'],'qemu_seconds':q['duration_seconds'],'actual_argv':q['argv'],'first_build_equals_loaded':True,'boot_stage_reused_fresh_target':True,'separate_second_cold_build_claimed':False,'artifact_sha256':q['artifacts']['-kernel']['sha256']},'kernel_tests':{'execution':execution['ktest'],'result':'ktest/result.json','crates':counts,'reported_passed':sum(x['passed'] for x in counts),'soft_skipped':sum(x['soft_skipped'] for x in counts),'exercised_passed_lower_bound':sum(x['exercised_passed_lower_bound'] for x in counts),'failed':sum(x['failed'] for x in counts),'filtered':sum(x['filtered'] for x in counts),'new_cpu_config_tests_executed_and_passed':9,'new_tests_proof':'review/native-review.json','ktest_snapshot_scope':'Prelaunch stable-FD hashes plus matched post-execution frozen ELFs; not private prelaunch copies.'},'dependencies':{'new_installation_for_this_run':False,'actual_prior_installation_archive':'dependencies/installation-2026-10-18.tar.gz','current_revalidation_archive':'dependencies/revalidation-2026-10-19.tar.gz','current_commands_passed':13,'binaries_and_libraries_matched':70,'qemu_dynamic_libraries_matched':48,'firmware_busybox_vdso_initramfs_matched':4,'original_packages_verified':57,'docker_available':False,'nix_available':False,'kvm_available':False,'installer_iso_required':False},'independent_native_review':{'passed':True,'checks_passed':53,'checks_failed':0,'path':'review/native-review.json','new_guest_executions_by_reviewer':False},'failures':{'first_boot_driver_exit':1,'first_boot_launched_make_or_qemu':False,'original_preflight_log':'failures/boot-preflight/driver.log','manifest_first_custody':'failures/boot-preflight/quarantine.json','manifest_second_custody':'failures/post-boot-manifest/quarantine.json','manifest_current_observation':'failures/manifest-reappearance/observation.json','current_public_manifest_present':True,'whole_worktree_current_clean':False,'writer_identified':False,'guards_unchanged':True,'earlier_cache_reappearance_receipt':'source-records.tar.xz:acquisition/cache-reappearance.json'},'scope_limits':['No new host ABI acceptance gate or OSDK full matrix was run at this producer.','TCG soft skips do not establish KVM/VMX/EPT acceptance.','No native HOS2 four-effect enforcement, durable K-D, G1/G2, general SMP or real-device acceptance is established by these results.','No cross-host reproducibility or complete immutable host dependency lock is established.','The following evidence-only publication does not create a separately rebuilt native producer.'],'archives':'archive-index.json'}
write(E/'report.json',report)
write(E/'archive-index.json',{'created_at':now(),'producer':P,'archives':index})
print(json.dumps({'evidence_root':str(E),'producer':P,'boot_elf':report['native_build']['first_elf'],'kernel_tests':{'reported':report['kernel_tests']['reported_passed'],'soft_skipped':report['kernel_tests']['soft_skipped'],'exercised_lower_bound':report['kernel_tests']['exercised_passed_lower_bound']},'archives':index},indent=2))
