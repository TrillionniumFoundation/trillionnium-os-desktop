#!/usr/bin/env python3
"""Read-only source identity gate after A01 report/history updates."""
import datetime, hashlib, json, os, pathlib, shutil, stat, subprocess, sys
REPO=pathlib.Path('/workspace/scratch/d7da9e7650f0/a01-current')
DEST=REPO/'support/build/evidence/2026-10-18-main012-current'
ROOT=REPO/'support/build/out/2026-10-18-main012'
SOURCE='b39e154ae5a1e9853f57e23f9bee84712ee8ef7e'
MAIN='01225ab0a20a9f25dd8313a7fad7652dd9154e30'
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*args],text=True)
def sha(raw):return hashlib.sha256(raw).hexdigest()
before=json.loads((ROOT/'source/before.json').read_text())
assert git('rev-parse','HEAD').strip()==SOURCE
changed=[]
for record in before['files']:
    path=REPO/record['path'];status=path.lstat()
    if stat.S_ISLNK(status.st_mode):raw=os.fsencode(os.readlink(path));mode='120000'
    else:
        assert stat.S_ISREG(status.st_mode)
        raw=path.read_bytes();mode='100755' if status.st_mode&0o111 else '100644'
    blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    current={'path':record['path'],'worktree_mode':mode,'size':len(raw),'sha256':sha(raw),'worktree_git_blob':blob}
    if any(current[k]!=record[k] for k in ['worktree_mode','size','sha256','worktree_git_blob']):
        changed.append({'before':record,'after':current})
assert {x['after']['path'] for x in changed}=={'support/build/README.md','support/upstream-lock.json'}
assert all(x['after']['worktree_mode']==x['before']['worktree_mode'] for x in changed)
old=json.loads(git('show','HEAD:support/upstream-lock.json'))
new=json.loads((REPO/'support/upstream-lock.json').read_text())
root_changes=[k for k in set(old)|set(new) if old.get(k)!=new.get(k)]
assert set(root_changes)=={'kernel','native_build_environment'}
kernel_changes=sorted(k for k in set(old['kernel'])|set(new['kernel']) if old['kernel'].get(k)!=new['kernel'].get(k))
assert set(kernel_changes)<= {'native_boot_history','native_validation_history','latest_native_boot','latest_native_validation','latest_main_source_integration'}
owner_diff=git('diff',MAIN,'--name-only','--','kernel/asterinas/kernel','kernel/asterinas/ostd','libs/os-abi')
assert not owner_diff
assert (REPO/'README.md').stat().st_size==0
tracked_changes=git('diff','--name-only').splitlines()
assert set(tracked_changes)=={'support/build/README.md','support/upstream-lock.json'}
command=[sys.executable,'-B','-I',str(REPO/'support/build/verify-source.py')]
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
process=subprocess.run(command,cwd=REPO,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
(DEST/'review/publication-fixed-inputs.json').write_bytes(process.stdout)
(DEST/'review/publication-fixed-inputs.stderr.log').write_bytes(process.stderr)
pins=json.loads(process.stdout)
assert process.returncode==0 and pins['passed'] and pins['checked_files']==118
assert pins==json.loads((ROOT/'kernel/source-inputs.json').read_text())
summary={'schema':'trillionnium.a01.publication-source-bridge.v1','captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'native_producer':SOURCE,'integrated_main':MAIN,'producer_project_tree':git('rev-parse','HEAD^{tree}').strip(),
    'kernel_tree':git('rev-parse','HEAD:kernel/asterinas').strip(),'selection_from':'source-records.tar.xz:source/before.json',
    'producer_files_sha256':before['files_sha256'],'selected_inputs':len(before['files']),
    'unchanged_inputs':len(before['files'])-len(changed),'metadata_changes':changed,
    'upstream_lock_changed_root_fields':sorted(root_changes),'upstream_lock_changed_kernel_fields':kernel_changes,
    'all_fixed_configuration_and_historical_nonlatest_fields_preserved':True,
    'owner_kernel_ostd_abi_diff_from_main':owner_diff,'root_readme_bytes':0,
    'full_status_at_publication_review':git('status','--porcelain=v1','--untracked-files=all'),
    'full_status_scope':'Expected untracked new A01 evidence plus the two tracked reporting changes; native receipts retain their own earlier status.',
    'public_manifest_entry_present':os.path.lexists(REPO/'kernel/asterinas/kernel/OSDK.toml'),
    'fixed_pin_command':{'argv':command,'started_at_utc':start,'exit_code':process.returncode,
        'checked_files':118,'receipt':'review/publication-fixed-inputs.json','receipt_sha256':sha(process.stdout),
        'receipt_equal_to_native_build':True},
    'no_additional_build_or_qemu_execution':True,'evidence_commit_itself_claimed_as_tested':False,'passed':True,
    'script_sha256':sha(pathlib.Path(__file__).read_bytes())}
(DEST/'publication-source-bridge.json').write_text(json.dumps(summary,indent=2)+'\n')
shutil.copyfile('/tmp/a01-current-build-review/native-review.json',DEST/'review/native-review.json')
shutil.copyfile(pathlib.Path(__file__),DEST/'review/publication-gate.py')
print(json.dumps({'passed':True,'selected_inputs':len(before['files']),'unchanged_inputs':len(before['files'])-len(changed),
    'metadata_paths':[x['after']['path'] for x in changed],'fixed_checks':118,
    'owner_diff_empty':True,'manifest_present':summary['public_manifest_entry_present']}))
