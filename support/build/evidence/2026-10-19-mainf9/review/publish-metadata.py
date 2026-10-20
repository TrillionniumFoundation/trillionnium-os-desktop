#!/usr/bin/env python3
import copy,datetime,hashlib,json,os,pathlib,shutil,stat,subprocess
R=pathlib.Path('/workspace/scratch/d7da9e7650f0/a01-mainf9');E=R/'support/build/evidence/2026-10-19-mainf9';O=R/'support/build/out/2026-10-19-mainf9'
P='7758ffe294bb0e1eab46e20cba60e8af9d8bcd61';M='f9e306f76154590e096a42f70ce9de0a7c859e60';REL=str(E.relative_to(R))
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(R),*args],text=True).strip()
assert git('rev-parse','HEAD')==P
assert not (E/'REPORT.md').exists()
shutil.copyfile('/tmp/a01-round2-REPORT.md',E/'REPORT.md')
q=read(E/'boot/qemu.json');r=read(E/'report.json');ks=read(E/'ktest/environment.json')
(E/'boot/qemu.command.sh').write_text(q['shell_command']+'\n')
readme=R/'support/build/README.md';prior=readme.read_text()
heading='## Current main-f9 build and native regressions — 2026-10-19\n\n'
intro='''Published source `7758ffe294bb0e1eab46e20cba60e8af9d8bcd61` incorporates actual
main `f9e306f76154590e096a42f70ce9de0a7c859e60` as first parent while preserving
A01 history. The complete fixed Rust kernel passed an absent-target **make kernel**
in 189.633 seconds, then a real **make run_kernel** retry with raw QEMU **33**.
Its 8,382,376-byte ELF has SHA256
`4625a5ddf9e82aee2ce01bdfb23127f88a5200565ce2a0645a09e181073ab6d4`;
the frozen first build and actual private loaded copy are identical.

Current real kernel-mode suites passed **OSTD 221** (three VMX/EPT soft skips)
and **aster-core 169**, with zero failures or filters: **390 reported passes,
387 exercised lower bound**. All nine new CPU configuration regressions completed
in the guest. Dependencies reuse the actual October 18 private installation and
were revalidated immediately before this build; no new installation is claimed.

The first boot invocation was refused before make/QEMU because a public manifest
unexpectedly reappeared. Its error and original bytes are retained. A locked,
reversible move preceded the successful retry. The manifest reappeared again,
including after a second move, and remains present in the final observed local
checkout. Its writer is unknown. All 3,014 selected tracked inputs match the
producer; that does **not** establish a clean whole worktree. Existing build
refusal and cleanup guards remain unchanged.

The [current report](evidence/2026-10-19-mainf9/REPORT.md) contains actual artifacts,
full serial logs, dependency/source receipts and failures, with the
[A00/A05/A06 handoff](evidence/2026-10-19-mainf9/HANDOFF.md). Independent source
and native evidence reviews passed 25 and 53 checks respectively. The reporting
commit is evidence-only, not a separately rebuilt native producer. Earlier
results below retain their own source identities and acceptance boundaries.

'''
needle='## Current main cold build, boot and kernel tests — 2026-10-18'
assert prior.count(needle)==1
readme.write_text(prior.replace(needle,heading+intro+needle,1))
lock_path=R/'support/upstream-lock.json';old=read(lock_path);new=copy.deepcopy(old);k=new['kernel']
assert k['latest_native_boot']['code_commit']=='b39e154ae5a1e9853f57e23f9bee84712ee8ef7e'
k.setdefault('native_boot_history',[]).append(copy.deepcopy(k['latest_native_boot']))
k['latest_native_boot']={'code_commit':P,'source_tree':r['project_tree'],'derived_tree':r['kernel_tree'],'integrated_main':M,'source_directory':'kernel/asterinas','source_build_invoked':True,'target_cache_reused':True,'empty_target_rebuild':False,'preceding_kernel_build':{'source_commit':P,'target_absent_before_launch':True,'osdk_target_absent_before_launch':True,'compilation_lines':284,'public_exit':0,'elapsed_seconds':r['native_build']['execution']['elapsed_seconds'],'kernel_sha256':r['boot']['artifact_sha256'],'kernel_bytes':8382376,'first_produced_bytes_retained':True},'original_absent_target_pipeline_commit':P,'passed':True,'qemu_raw_exit':33,'boot_sha256':r['boot']['artifact_sha256'],'boot_size':8382376,'initramfs_sha256':q['artifacts']['-initrd']['sha256'],'serial_sha256':q['serial_sha256'],'serial_size':q['serial_size'],'evidence':REL+'/REPORT.md','profile':'ordinary x86_64-q35-tcg-max-1cpu-512MiB-SeaBIOS','make_exit':0,'driver_exit':0,'full_tracked_inputs_checked':3014,'first_build_equals_loaded':True,'first_attempt_failed_before_qemu':True,'first_attempt_driver_exit':1,'post_boot_git_status_empty':True,'later_untracked_manifest_observed':True,'late_manifest_quarantined':True,'late_manifest_reappeared_after_quarantine':True,'late_manifest_writer_identified':False,'post_quarantine_git_status_empty':False,'current_public_manifest_present':True,'cross_host_reproducibility_claimed':False,'stage_scope':'One absent-target build; one preflight-refused boot; separate successful cached boot retry. Two manifest custody instants do not establish subsequent absence.'}
k.setdefault('native_validation_history',[]).append(copy.deepcopy(k['latest_native_validation']))
k['latest_native_validation']={'schema':1,'evidence':REL+'/REPORT.md','machine_readable_report':REL+'/report.json','handoff':REL+'/HANDOFF.md','source_commit':P,'project_tree':r['project_tree'],'kernel_tree':r['kernel_tree'],'base_main':M,'owner_kernel_ostd_external_abi_equal_base_main':True,'source_manifest':REL+'/source-summary.json','toolchain':'nightly-2026-07-21','pipeline_passed':True,'build_was_incremental':False,'boot_stage_reused_fresh_target':True,'fresh_dependency_installation':False,'dependency_installation_scope':'Reuse the actual 2026-10-18 installation, with preserved original receipts and current 2026-10-19 revalidation.','current_dependency_commands_passed':13,'actual_dependency_hashes_matched':70,'qemu_dynamic_libraries_matched':48,'original_native_packages_verified':57,'kernel_mode_reported_passed':390,'kernel_mode_soft_skipped':3,'kernel_mode_exercised_passed_lower_bound':387,'kernel_mode_failed':0,'kernel_mode_filtered':0,'ostd_reported_passed':221,'aster_core_passed':169,'new_cpu_configuration_tests_passed':9,'independent_source_checks_passed':25,'independent_native_evidence_checks_passed':53,'host_gate_rerun':False,'current_abi_gate_rerun':False,'current_osdk_full_matrix_rerun':False,'first_boot_attempt_failed_before_qemu':True,'late_manifest_writer_identified':False,'late_manifest_evidence':REL+'/failures/','whole_worktree_current_clean':False,'current_public_manifest_present':True,'full_project_acceptance':False}
k['latest_main_source_integration']={'source_commit':P,'project_tree':r['project_tree'],'integrated_main':M,'prior_a01_parent':'71524be19383e2ff98f6abc90668c48988e7c8e2','method':'ordinary two-parent merge from actual main','native_rebuilt_at_this_producer':True,'owner_kernel_ostd_external_abi_equal_main':True,'source_summary':REL+'/source-summary.json','handoff':REL+'/HANDOFF.md'}
k.setdefault('kernel_mode_regression_history',[]).append(copy.deepcopy(k['kernel_mode_regression']))
fixed_locks=copy.deepcopy(k['kernel_mode_regression']['test_base_locks'])
k['kernel_mode_regression']={'evidence':REL+'/ktest/result.json','code_commit':P,'source_tree':r['project_tree'],'crates':['ostd','aster-core'],'reported_passed':390,'failed':0,'filtered':0,'soft_skipped':3,'exercised_passed_lower_bound':387,'profile':'x86_64-q35-tcg-1cpu-512MiB','test_base_locks':fixed_locks,'osdk_code_commit':P,'osdk_binary_sha256':ks['osdk_sha256'],'latest_phase':'2026-10-19-mainf9','guests':2,'raw_qemu_exits':[33,33],'kernel_mode_runner_exit':0,'target_cache_reused':True,'empty_target_rebuild':False,'osdk_install_skipped':False,'source_root_bound_sdk_reinstalled':True,'new_cpu_configuration_tests_passed':9}
new['native_build_environment']=REL+'/REPORT.md'
allowed_kernel={'native_boot_history','latest_native_boot','native_validation_history','latest_native_validation','latest_main_source_integration','kernel_mode_regression_history','kernel_mode_regression'}
def stable_lock(v):
 v=copy.deepcopy(v);v.pop('native_build_environment',None)
 for n in allowed_kernel:v['kernel'].pop(n,None)
 return v
assert stable_lock(old)==stable_lock(new)
write(lock_path,new)
baseline=read(O/'source/kernel-before.json');changed=[];unchanged=0
for entry in baseline['files']:
 p=R/entry['path'];s=p.lstat()
 raw=os.fsencode(os.readlink(p)) if stat.S_ISLNK(s.st_mode) else p.read_bytes()
 mode='120000' if stat.S_ISLNK(s.st_mode) else ('100755' if s.st_mode&0o111 else '100644')
 after={'sha256':sha(raw),'git_blob':hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest(),'mode':mode,'size':len(raw)}
 if after['sha256']==entry['sha256'] and mode==entry['worktree_mode']:unchanged+=1
 else:changed.append({'path':entry['path'],'before':{n:entry[n] for n in ['sha256','git_blob','size','worktree_mode']},'after':after})
assert {x['path'] for x in changed}=={'support/build/README.md','support/upstream-lock.json'}
assert unchanged==3012 and (R/'README.md').stat().st_size==0
assert git('diff','--name-only','HEAD','--','kernel/asterinas','libs')==''
write(E/'publication-source-bridge.json',{'schema':1,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_producer':P,'native_project_tree':r['project_tree'],'native_kernel_tree':r['kernel_tree'],'selected_inputs':3014,'unchanged_selected_inputs':unchanged,'metadata_exceptions':changed,'kernel_abi_build_program_bytes_unchanged':True,'upstream_lock_nonreporting_fields_unchanged':True,'root_readme_bytes':0,'new_native_executions_for_reporting_commit':0,'git_status_porcelain':git('status','--porcelain=v1','--untracked-files=all'),'scope':'Only the README report and lock reporting/history fields change in the selected native input set; new evidence files are outside that selection. Public foreign manifest remains untracked and is not hidden.','passed':True})
shutil.copyfile(__file__,E/'review/publish-metadata.py')
print(json.dumps({'source_producer':P,'selected_inputs':3014,'unchanged':3012,'metadata_paths':[x['path'] for x in changed],'root_readme_bytes':0,'kernel_abi_build_programs_unchanged':True,'report_path':str(E/'REPORT.md')},indent=2))
