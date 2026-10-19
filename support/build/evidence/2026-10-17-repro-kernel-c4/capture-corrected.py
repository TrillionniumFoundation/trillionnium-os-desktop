#!/usr/bin/python3
"""Freeze root-confirmed completed C4; never build, run VM or read target paths."""
import argparse
import datetime
import difflib
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile

sys.dont_write_bytecode=True

BASE=Path('/workspace/scratch/ae1a8cf05419')
REPO=BASE/'trillionnium-os-desktop'
OLD=REPO/'support/build/evidence/2026-10-17-repro-kernel-a4'
PHASE=REPO/'support/build/evidence/2026-10-17-repro-kernel-c4'
MAX=2*1024*1024
SOURCE='4e8c7083575cec69efabe8d2250dfdd040c8dee8'

def need(ok,message):
    if not ok: raise ValueError(message)

def sha(data): return hashlib.sha256(data).hexdigest()
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')
def identity(s):
    return {k:getattr(s,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_nlink')}
def stable(path):
    before=path.lstat();need(stat.S_ISREG(before.st_mode),'not regular: '+str(path))
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        opened=os.fstat(fd);need(identity(before)==identity(opened),'opened identity mismatch: '+str(path))
        with os.fdopen(os.dup(fd),'rb') as stream:data=stream.read()
        after=os.fstat(fd);end=path.lstat()
        need(identity(before)==identity(after)==identity(end) and len(data)==before.st_size,'unstable read: '+str(path))
    finally:os.close(fd)
    return data,identity(before)
def record(data,**extra):return dict(bytes=len(data),sha256=sha(data),**extra)
def chunks(data,path):
    names=[path] if len(data)<=MAX else [path+'.part-'+str(i//MAX+1).zfill(3) for i in range(0,len(data),MAX)]
    rows=[]
    for i,name in enumerate(names):
        part=data[i*MAX:(i+1)*MAX];p=PHASE/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(part)
        rows.append(record(part,path=name))
    return record(data,chunks=rows)
def tar_bytes(members,capture):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as stream:
        for name,data in sorted(members.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=stat.S_IMODE(capture[name]['stat']['st_mode']);info.mtime=0
            info.uid=info.gid=0;info.uname=info.gname='';stream.addfile(info,io.BytesIO(data))
    return gzip.compress(out.getvalue(),compresslevel=9,mtime=0)
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root-confirmed-outer-exit',required=True,type=int);args=parser.parse_args()
    need(args.root_confirmed_outer_exit==0,'root did not confirm outer success')
    # Do not invoke this before the root has explicitly confirmed the process ended.
    output=BASE/'normalized-cloud/C4';controller=BASE/'normalized-cloud/controller-C4'
    commands=json.loads(stable(controller/'commands.json')[0]);need(len(commands)==8 and all(x.get('returncode')==0 for x in commands),'C4 controller incomplete')
    need(commands[0]['argv'][-1]==SOURCE,'wrong producer')
    need(not PHASE.exists(),'phase exists; no overwrite')
    paths=[]
    for directory in (output,controller,BASE/'full-kernel-profile-v4'):
        for p in sorted(directory.rglob('*')):
            need(not p.is_symlink(),'symlink in capture: '+str(p))
            if p.is_file():paths.append(p)
    paths += [BASE/'old-a4-restore/run-normalized-cloud-v4.py',BASE/'round-next/run-normalized-cloud-c4.py',BASE/'round-next/c4-prelaunch.json',BASE/'round-next/c4-outer-tool.json',BASE/'round-next/host-identity.json',BASE/'cross-host-review/pack-c4.py',BASE/'cross-host-review/prelaunch-review.json',BASE/'cross-host-review/old-a4-offline-independent.json']
    paths += sorted(p for p in (BASE/'round-next/prefetch').rglob('*') if p.is_file())
    originals={};inventory=[]
    for p in paths:
        name=str(p.relative_to(BASE));name='run-normalized-cloud-v4.py' if name=='old-a4-restore/run-normalized-cloud-v4.py' else name
        data,s=stable(p);need(name not in originals,'duplicate capture path');originals[name]=data
        inventory.append(record(data,path=name,stat=s,read_stable=True))
    original=originals['run-normalized-cloud-v4.py'];new=originals['round-next/run-normalized-cloud-c4.py']
    expected=original.replace(b"if case not in ('A4', 'B4'):\n    raise SystemExit('case must be A4 or B4')",b"if case != 'C4':\n    raise SystemExit('case must be C4')")
    need(new==expected and sha(original)=='b79ece02e233b9563a4418310d41fb64c4374740f5bb30c4a6e598fe11158805','unexpected controller mutation')
    policy=json.loads(originals['normalized-cloud/C4/policy.json']);result=json.loads(originals['normalized-cloud/C4/result.json']);qemu=json.loads(originals['normalized-cloud/C4/kernel-run/qemu.json'])
    need(result['returncode']==result['child_returncode']==0,'run did not pass')
    need(all(result[x] is True for x in ('profile_custody_unchanged','source_components_unchanged','profile_code_unchanged')),'custody failed')
    need(qemu['raw_exit_code']==qemu['recorder_exit_code']==33 and not qemu['timed_out'],'QEMU did not pass')
    need(policy['target_absent_at_prelaunch'] is True,'not a cold target')
    directory_rows=[]
    for p in [BASE/'full-kernel-profile-v4',BASE/'full-kernel-profile-v4/helpers',BASE/'full-kernel-profile-v4/virtual-asterinas']:
        s=p.lstat();need(stat.S_ISDIR(s.st_mode),'profile directory missing');directory_rows.append({'path':str(p.relative_to(BASE)),'stat':identity(s)})
    PHASE.mkdir(parents=True,exist_ok=False)
    for name in ('source/controls.tar.gz','source/members.json','source/tree-objects.json','source-binding.json','schema4_checks.py'):
        data,_=stable(OLD/name);target=PHASE/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    inv={r['path']:r for r in inventory};binary={};payloads={}
    for option,info in qemu['artifacts'].items():
        name='normalized-cloud/'+info['path'].split('/normalized-cloud/',1)[1];data=originals[name]
        need(len(data)==info['size'] and sha(data)==info['sha256'],'loaded input mismatch')
        payloads[sha(data)]=(option,data)
    for name,data in originals.items():
        if sha(data) in payloads and name.startswith('normalized-cloud/C4/') and (name.endswith('/kernel.elf') or name.endswith('/bios.bin') or name.endswith('/initramfs.cpio.gz')):
            binary[name]=record(data,artifact=sha(data),mode=stat.S_IMODE(inv[name]['stat']['st_mode']))
    need(len(binary)==4 and len(payloads)==3,'unexpected exact input scope')
    artifacts=[]
    for digest,(option,data) in sorted(payloads.items()):
        kind={'-kernel':'kernel','-initrd':'initramfs','-bios':'bios'}[option]
        artifacts.append(dict(kind=kind,original_bytes=len(data),original_sha256=digest,encoding='gzip wraps exact original input bytes; initramfs original remains cpio.gz',**chunks(gzip.compress(data,compresslevel=9,mtime=0),'artifacts/'+kind+'.input.gz')))
    dump(PHASE/'artifacts/manifest.json',{'schema':1,'maximum_stored_chunk_bytes':MAX,'artifacts':artifacts,'original_paths':binary})
    raw={n:d for n,d in originals.items() if n not in binary};manifest=chunks(tar_bytes(raw,inv),'raw.tar.gz')
    manifest['members']=[record(data,member=name,mode=stat.S_IMODE(inv[name]['stat']['st_mode'])) for name,data in sorted(raw.items())]
    dump(PHASE/'raw.manifest.json',manifest)
    dump(PHASE/'capture.json',{'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Root-confirmed completed C4 only, its controller, immutable prelaunch and fresh prefetch receipts, original controller and read-only profile. No target reads, builds, VM, lock mutation or cleanup.','files':inventory,'directories':directory_rows})
    copies=[]
    mapping={
      'readable/serial.log':'normalized-cloud/C4/kernel-run/serial.log','readable/qemu.json':'normalized-cloud/C4/kernel-run/qemu.json','readable/run_kernel.log':'normalized-cloud/C4/kernel-run/run_kernel.log','readable/environment.log':'normalized-cloud/C4/kernel-run/environment.log','readable/command.sh':'normalized-cloud/C4/kernel-run/command.sh','readable/policy.json':'normalized-cloud/C4/policy.json','readable/result.json':'normalized-cloud/C4/result.json','readable/console.log':'normalized-cloud/C4/console.log','readable/manifest-cleanup.json':'normalized-cloud/C4/kernel-run/manifest-cleanup.json','readable/controller-commands.json':'normalized-cloud/controller-C4/commands.json','readable/c4-prelaunch.json':'round-next/c4-prelaunch.json','readable/host-identity.json':'round-next/host-identity.json','readable/controller-original.py':'run-normalized-cloud-v4.py','readable/controller-c4.py':'round-next/run-normalized-cloud-c4.py','readable/prefetch-commands.json':'round-next/prefetch/commands.json'}
    mapping.update({'readable/controller-'+p.name:'normalized-cloud/controller-C4/'+p.name for p in controller.glob('*.log')})
    for name,source in mapping.items():
        data=originals[source];target=PHASE/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);copies.append(record(data,path=name,original_path=source))
    dump(PHASE/'readable/manifest.json',{'copies':copies})
    (PHASE/'readable/controller-change.diff').write_text(''.join(difflib.unified_diff(original.decode().splitlines(True),new.decode().splitlines(True),fromfile='original-v4',tofile='c4')))
    spec=importlib.util.spec_from_file_location('schema4_checks',OLD/'schema4_checks.py');checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
    compiler=checks.compiler_records(checks.jsonl(originals['normalized-cloud/C4/rustc.jsonl']),checks.jsonl(originals['normalized-cloud/C4/compiler-units.jsonl']),policy)
    execution=checks.execution_records(policy,originals['normalized-cloud/C4/kernel-run/environment.log']);guest=checks.boot(qemu,originals['normalized-cloud/C4/kernel-run/serial.log'],originals)
    dump(PHASE/'analysis/compiler-and-custody.json',compiler);dump(PHASE/'analysis/runtime-proof.json',guest)
    report={'state':'frozen actual completed C4; independent offline verification required','case':'C4','source_commit':SOURCE,'source_binding':json.loads((PHASE/'source-binding.json').read_text()),'outer_tool_observation':{'session_id':90518,'exit_code':0,'source':'Delegating root actual completed tool result; eight raw subprocess receipts independently retained.'},'commands':commands,'compiler_summary':{k:v for k,v in compiler.items() if k!='canonical_local_units'},'compiler_execution':execution,'guest':guest,'loaded_artifacts':qemu['artifacts'],'original_file_count':len(originals),'raw_member_count':len(raw),'binary_unique_inputs':3,'binary_original_paths':4,'source_before_after_equal':True,'kernel_boot_passed':True,'cross_path_accepted_by_this_case_capture':False,'cross_host_accepted':False,'actual_host':policy['actual_host'],'profile_opt_in':True,'synthetic_embedded_builder':policy['embedded_builder'],'compile_lines':sum('Compiling ' in line for line in originals['normalized-cloud/C4/console.log'].decode().splitlines()),'scope':'This completed single case only. Cross-instance complete-byte comparison is a separate phase. Frozen original run.py scope string is preserved verbatim.','limits':['Preserved fixed absolute CARGO_HOME/RUSTUP_HOME/native-tool/profile virtual paths, fixed tool bytes and selected producer source.','Schema4 opt-in job1/canonical local metadata and synthetic embedded builder; not arbitrary-host or immutable-environment reproducibility.','Producer artifact provenance binds successful completion and stat identities, not immutable content.','Source closure is 86 selected exact Git blobs, not the entire repository.']}
    dump(PHASE/'report.json',report)
    text=(OLD/'verify.py').read_text().replace("case in ('A4','B4')","case == 'C4'")
    needle="    policy=json.loads(a('policy.json'));result=json.loads(a('result.json'));qemu=json.loads(a('kernel-run/qemu.json'));owner=json.loads(originals['full-kernel-profile-v4/owner.json'])"
    extra="""    original=originals['run-normalized-cloud-v4.py'];new=originals['round-next/run-normalized-cloud-c4.py']
    need(new==original.replace(b\"if case not in ('A4', 'B4'):\\n    raise SystemExit('case must be A4 or B4')\",b\"if case != 'C4':\\n    raise SystemExit('case must be C4')\"),'C4 controller has changes beyond the accepted case guard')
    pre=json.loads(originals['round-next/c4-prelaunch.json']);host=json.loads(originals['round-next/host-identity.json'])
    need(pre['source']==binding['producer_commit'] and all(pre[k] is False for k in ('fresh_worktree_exists_before','profile_exists_before','output_exists_before')),'fresh prelaunch mismatch')
    need(pre['original_controller_sha256']==sha(original) and pre['new_controller_sha256']==sha(new),'prelaunch controller identity mismatch')
    need(pre['actual_new_host']==host,'new host identity mismatch')
    outer=json.loads(originals['round-next/c4-outer-tool.json'])
    need(outer['session_id']==90518 and outer['observed_exit_code']==0 and outer['completed'] is True and outer['command']==['python3','-I','round-next/run-normalized-cloud-c4.py',binding['producer_commit'],'C4'],'root-observed outer completion mismatch')
    prefetch=json.loads(originals['round-next/prefetch/commands.json'])
    need(len(prefetch)==2 and {x['name'] for x in prefetch}=={'kernel','osdk'},'prefetch scope mismatch')
    for row in prefetch:
        need(row['returncode']==0 and row['lock_sha256_before']==row['lock_sha256_after'],'locked fresh fetch failed or changed lock')
        need('--locked' in row['argv'] and sha(originals['round-next/prefetch/'+row['name']+'.log'])==row['log_sha256'],'prefetch command/log mismatch')
        source_lock='source/kernel/asterinas/'+('osdk/' if row['name']=='osdk' else '')+'Cargo.lock'
        need(row['lock_sha256_before']==sha(sources[source_lock]),'fresh fetch lock does not match exact producer Git blob')
    for row in commands:
        env=row['selected_environment']
        need(env['CARGO_HOME']=='/workspace/scratch/ae1a8cf05419/toolchains/cargo' and env['RUSTUP_HOME']=='/workspace/scratch/ae1a8cf05419/toolchains/rustup' and env['RUSTUP_TOOLCHAIN']=='nightly-2026-07-21','fixed absolute toolchain roots differ')
"""
    need(needle in text,'verifier insertion anchor missing');text=text.replace(needle,extra+needle)
    text=text.replace("    need(policy['target_absent_at_prelaunch']", "    need(policy['actual_host']['hostname']==host['hostname'] and policy['actual_host']['uname'][2] in host['kernel'],'actual policy and fresh host mismatch')\n    need(policy['target_absent_at_prelaunch']",1)
    (PHASE/'verify.py').write_text(text)
    readme=f'''# C4: fresh cloud instance, cold Rust kernel build and actual boot\n\nProducer `{SOURCE}`; fixed Asterinas v0.19.0 and `nightly-2026-07-21`. Actual source checkout `/tmp/trillionnium-a01-normalized-C4` had no target at prelaunch. Eight controller commands completed successfully, including cold `run_kernel` (upstream `make run_kernel`), source checks and `check-boot.py --live-artifacts`. Actual QEMU raw/recorder exit: 33.\n\nThe actual cloud instance was `{policy['actual_host']['hostname']}`, Linux `{policy['actual_host']['uname'][2]}`. The schema4 embedded builder `a01-repro@a01-fixed-profile` is synthetic and separately recorded. This phase accepts C4 alone. Cross-instance equality is accepted only by the independent comparison phase. Frozen producer `run.py` still contains its historical same-host scope text; its bytes remain unchanged.\n\n`readable/serial.log` preserves the complete {guest['serial_bytes']:,}-byte serial (SHA256 `{guest['serial_sha256']}`). Exact QEMU argv, executable hash/version, loaded ELF/initramfs/BIOS, source pre/post receipts, empty postrun worktree status, compiler arguments and all ledger events are retained. {compiler['compiler_calls']} compiler calls, {compiler['producer_ledger_rows']} ledger events, {len(compiler['canonical_local_units'])} canonical local descriptors. Cargo units all completed zero; query probes have retained status counts `{compiler['query_probe_statuses']}`.\n\nInputs are standalone compressed exact bytes, at most 2 MiB per chunk. `capture.json` records stable original file stats; no original target paths were opened by packaging. The 86 selected source controls and 30 Git tree objects are copied unchanged from the independently verified A4 closure because the producer commit is identical. New prelaunch, fresh locked fetch, actual host, original controller and C4 controller are included; the only controller change is the accepted case guard. This is an opt-in fixed-path/toolchain/profile result, not arbitrary environment or immutable-host acceptance.\n\n```sh\npython3 -I support/build/evidence/2026-10-17-repro-kernel-c4/verify.py\npython3 -I -O support/build/evidence/2026-10-17-repro-kernel-c4/verify.py\npython3 -I support/build/evidence/2026-10-17-repro-kernel-c4/verify.py --restore /absolute/new-directory\n```\n\nThe offline verifier checks complete package coverage, source Git membership, full compiler/custody/guest records and exact retained inputs. Optional restore only creates verified bytes in a fresh directory; neither command executes a build, captured controller or VM. Reproduction uses the preserved controller and producer checkout after restoring the locked private dependencies; the exact literal toolchain and profile paths are prerequisites.\n'''
    (PHASE/'README.md').write_text(readme)
    checksum=''.join(sha(p.read_bytes())+'  '+str(p.relative_to(PHASE))+'\n' for p in sorted(PHASE.rglob('*')) if p.is_file() and p.name!='SHA256SUMS')
    (PHASE/'SHA256SUMS').write_text(checksum)
    print(json.dumps({'phase':str(PHASE),'original_files':len(originals),'raw_members':len(raw),'compiler_calls':compiler['compiler_calls'],'canonical_descriptors':len(compiler['canonical_local_units']),'sha256sums':sha(checksum.encode())},indent=2))

if __name__=='__main__':main()
