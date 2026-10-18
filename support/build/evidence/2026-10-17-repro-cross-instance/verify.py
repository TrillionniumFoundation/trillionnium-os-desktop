#!/usr/bin/python3
"""Offline cross-instance comparison of two complete, independently verified cases."""
import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

BASE=Path(__file__).resolve().parent
SOURCE='4e8c7083575cec69efabe8d2250dfdd040c8dee8'
CASE_PHASES={'A4':'2026-10-17-repro-kernel-a4','C4':'2026-10-17-repro-kernel-c4'}

def need(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':')).encode()
def identity(s):return {k:getattr(s,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_nlink')}
def stable(path):
    before=path.lstat();need(stat.S_ISREG(before.st_mode),'not regular capture input')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        need(identity(os.fstat(fd))==identity(before),'capture open identity mismatch')
        with os.fdopen(os.dup(fd),'rb') as stream:data=stream.read()
        need(identity(os.fstat(fd))==identity(path.lstat())==identity(before) and len(data)==before.st_size,'capture input changed')
    finally:os.close(fd)
    return data,identity(before)
def module(path,name):
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location(name,path);loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
    return loaded
def case(evidence,name):
    phase=evidence/CASE_PHASES[name];v=module(phase/'verify.py','case_'+name)
    verified=v.verify()
    raw=v.archive(v.load('raw.manifest.json'),'raw.tar.gz');originals=dict(raw);art=v.load('artifacts/manifest.json');payloads={}
    for record in art['artifacts']:
        data=gzip.decompress(v.container(record,record['kind']));payloads[sha(data)]=data
    for path,record in art['original_paths'].items():originals[path]=payloads[record['artifact']]
    root='normalized-cloud/'+name+'/'
    policy=json.loads(originals[root+'policy.json']);qemu=json.loads(originals[root+'kernel-run/qemu.json'])
    commands=json.loads(originals['normalized-cloud/controller-'+name+'/commands.json'])
    rows=[json.loads(line) for line in originals[root+'rustc.jsonl'].splitlines()]
    ledger=[json.loads(line) for line in originals[root+'compiler-units.jsonl'].splitlines()]
    checks=module(phase/'schema4_checks.py','schema_'+name)
    compiler=checks.compiler_records(rows,ledger,policy)
    inputs={option:payloads[record['sha256']] for option,record in qemu['artifacts'].items()}
    binding=v.load('source-binding.json')
    need(binding['producer_commit']==SOURCE,'different producer commit')
    cargo_units=[row['compiler_unit'] for row in rows if row['compiler_unit'] is not None]
    unit_ids=Counter(row['canonical_id'] for row in cargo_units)
    envs=[row['selected_environment'] for row in commands]
    fixed_env={key:envs[0][key] for key in ('CARGO_HOME','RUSTUP_HOME','RUSTUP_TOOLCHAIN','VDSO_LIBRARY_DIR','PKG_CONFIG_SYSROOT_DIR')}
    need(all(all(env.get(key)==value for key,value in fixed_env.items()) for env in envs),'environment changes within one case')
    qemu_argv=list(qemu['argv'])
    for option in ('-kernel','-initrd','-bios'):
        need(qemu_argv.count(option)==1,'ambiguous QEMU input option')
        qemu_argv[qemu_argv.index(option)+1]='<exact-retained-'+option[1:]+'>'
    info={'case':name,'source_commit':binding['producer_commit'],'source_tree':binding['producer_complete_tree'],'derived_kernel_tree':binding['derived_kernel_tree'],'phase':CASE_PHASES[name],'phase_sha256sums_sha256':sha((phase/'SHA256SUMS').read_bytes()),'actual_host':policy['actual_host'],'real_source_root':policy['real_root'],'virtual_root':policy['virtual_root'],'fixed_environment':fixed_env,'rustc_identity':policy['rustc_identity'],'profile_code_sha256':policy['code_sha256'],'components_sha256':policy['components_sha256'],'compiler_calls':len(rows),'ledger_events':len(ledger),'cargo_units':len(cargo_units),'compiler_scopes':compiler['compiler_unit_scopes'],'query_probe_statuses':compiler['query_probe_statuses'],'canonical_local_descriptors':len(compiler['canonical_local_units']),'canonical_local_descriptors_sha256':sha(canonical(compiler['canonical_local_units'])),'cargo_producer_identity_counts':dict(sorted(unit_ids.items())),'all_cargo_units_completed_zero':compiler['all_cargo_unit_completions_zero'],'raw_qemu_exit':qemu['raw_exit_code'],'serial_size':qemu['serial_size'],'serial_sha256':qemu['serial_sha256'],'inputs':{option:{'bytes':len(data),'sha256':sha(data),'original_snapshot_path':qemu['artifacts'][option]['path']} for option,data in inputs.items()},'verification':verified}
    info['qemu_identity']={'sha256':qemu['qemu_sha256'],'version':qemu['qemu_version']}
    info['qemu_argv_except_three_input_paths']=qemu_argv
    return info,inputs,compiler['canonical_local_units'],v.load('capture.json'),qemu

def comparison(evidence):
    left,lp,ld,lc,lq=case(evidence,'A4');right,rp,rd,rc,rq=case(evidence,'C4')
    for key in ('source_commit','source_tree','derived_kernel_tree','virtual_root','fixed_environment','rustc_identity','profile_code_sha256','components_sha256','qemu_identity','qemu_argv_except_three_input_paths'):
        need(left[key]==right[key],'held-fixed identity differs: '+key)
    need(left['real_source_root']!=right['real_source_root'],'actual source roots are the same')
    need(left['actual_host']['hostname']!=right['actual_host']['hostname'],'cloud hostname is unchanged')
    need(left['actual_host']['uname'][2]!=right['actual_host']['uname'][2],'host kernel identity is unchanged')
    equality={option:lp[option]==rp[option] for option in ('-kernel','-initrd','-bios')}
    descriptor_equal=ld==rd
    producer_counts_equal=left['cargo_producer_identity_counts']==right['cargo_producer_identity_counts']
    result={'schema':1,'passed':all(equality.values()) and descriptor_equal,'source_commit':SOURCE,'cases':[left,right],'complete_input_bytes_equal':equality,'canonical_local_descriptors_equal':descriptor_equal,'cargo_producer_identity_counts_equal':producer_counts_equal,'different_actual_cloud_hostnames':True,'different_actual_host_kernels':True,'source_paths_distinct':True,'cross_instance_accepted':all(equality.values()) and descriptor_equal,'immutable_environment_accepted':False,'scope':'Two observed cloud instances, same fixed producer and literal private-toolchain/registry/profile prefixes, independently cold-built and booted, complete ELF/initramfs/BIOS byte equality. Schema4 opt-in only.','limits':['Actual host identities come from the original recorded socket hostname and os.uname; no cloud-provider instance attestation is claimed.','Literal absolute CARGO_HOME/RUSTUP_HOME/native toolchain/profile virtual paths were preserved, not varied.','Fixed selected dependency bytes were restored into a new runtime; the entire host or dependency closure is not immutable.','Canonical metadata and explicit epoch/synthetic embedded builder are part of this opt-in profile.','The frozen producer result.scope historical same-host string remains unchanged; this separate comparison supplies the new cross-instance result.','Successful producer provenance plus stat identities is not immutable compiler artifact content; exact final boot inputs are retained separately.','Query/probe nonzero statuses are preserved and are not failed Cargo compilation units.']}
    # Counter keys are ints in memory and JSON object keys are strings on disk.
    # Compare the canonical stored representation rather than Python-only types.
    return json.loads(json.dumps(result)),{'A4':(lc,lq,lp),'C4':(rc,rq,rp)}

def verify():
    checks={}
    for line in (BASE/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);need(name and '/' not in name and name not in checks and len(digest)==64,'invalid phase checksum row');checks[name]=digest
    entries=list(BASE.iterdir())
    actual={p.name for p in entries if p.is_file() and p.name!='SHA256SUMS'}
    need(actual==set(checks) and all(p.is_file() and not p.is_symlink() for p in entries),'checksum coverage mismatch')
    for name,digest in checks.items():need(sha((BASE/name).read_bytes())==digest,'phase file changed: '+name)
    expected=json.loads((BASE/'comparison.json').read_text());recomputed,details=comparison(BASE.parent)
    need(recomputed==expected and expected['passed'] is True,'comparison facts no longer match retained cases')
    receipt=json.loads((BASE/'live-comparison.json').read_text())
    need(receipt['source_commit']==SOURCE and receipt['complete_input_bytes_equal']==expected['complete_input_bytes_equal'],'live comparison result mismatch')
    need(receipt['all_complete_bytes_compared'] is True and receipt['no_target_paths_opened'] is True,'live comparison scope mismatch')
    for name in ('A4','C4'):
        capture,qemu,payloads=details[name];original_stats={row['path']:row for row in capture['files']}
        for option,info in qemu['artifacts'].items():
            row=receipt['inputs'][option][name];path='normalized-cloud/'+info['path'].split('/normalized-cloud/',1)[1]
            need(row['snapshot_path']==info['path'] and row['bytes']==len(payloads[option]) and row['sha256']==sha(payloads[option]) and row['read_stable'] is True,'live/retained input mismatch')
            need(row['original_capture_stat']==original_stats[path]['stat'],'original capture stats mismatch')
            if name=='C4':need(row['fd_read_stat']==row['original_capture_stat'],'C4 live comparison did not read same captured identity')
    return {'passed':True,'cross_instance_accepted':True,'immutable_environment_accepted':False,'complete_input_bytes_equal':expected['complete_input_bytes_equal'],'canonical_local_descriptors_equal':expected['canonical_local_descriptors_equal'],'cargo_producer_identity_counts_equal':expected['cargo_producer_identity_counts_equal'],'compiler_calls':[x['compiler_calls'] for x in expected['cases']],'cargo_units':[x['cargo_units'] for x in expected['cases']],'raw_qemu_exits':[x['raw_qemu_exit'] for x in expected['cases']],'scope':'Offline complete retained byte/source/controller/ledger/host comparison only; no original target, build, live check or VM.'}

def capture():
    workspace=Path('/workspace/scratch/ae1a8cf05419');evidence=workspace/'trillionnium-os-desktop/support/build/evidence';destination=evidence/'2026-10-17-repro-cross-instance'
    need(not destination.exists(),'comparison phase exists; refuse overwrite')
    report,details=comparison(evidence)
    receipt={'schema':1,'source_commit':SOURCE,'all_complete_bytes_compared':True,'no_target_paths_opened':True,'inputs':{},'complete_input_bytes_equal':{}}
    for option in ('-kernel','-initrd','-bios'):
        data={};rows={}
        for name in ('A4','C4'):
            inventory,qemu,payloads=details[name];path=qemu['artifacts'][option]['path'];logical='normalized-cloud/'+path.split('/normalized-cloud/',1)[1]
            actual=workspace/'old-a4-restore'/logical if name=='A4' else Path(path)
            data[name],fdstat=stable(actual);need(data[name]==payloads[option],'live original differs from packaged input')
            captured=next(row for row in inventory['files'] if row['path']==logical)
            rows[name]={'snapshot_path':path,'actual_comparison_read_path':str(actual),'bytes':len(data[name]),'sha256':sha(data[name]),'fd_read_stat':fdstat,'original_capture_stat':captured['stat'],'read_stable':True,'scope':'Restored verified original A4 bytes; historical original identity is separate.' if name=='A4' else 'Actual completed C4 loaded snapshot bytes and current stable descriptor identity.'}
        receipt['inputs'][option]=rows;receipt['complete_input_bytes_equal'][option]=data['A4']==data['C4']
    need(report['passed'] and all(receipt['complete_input_bytes_equal'].values()),'cross-instance comparison failed')
    destination.mkdir()
    for name,value in [('comparison.json',report),('live-comparison.json',receipt)]: (destination/name).write_text(json.dumps(value,indent=2)+'\n')
    (destination/'verify.py').write_bytes(Path(__file__).read_bytes())
    kernel=report['cases'][0]['inputs']['-kernel']
    (destination/'README.md').write_text(f'''# A4 / C4: complete Rust kernel inputs reproduced across two cloud instances\n\nBoth real cold builds used producer `{SOURCE}` and fixed Asterinas v0.19.0 / `nightly-2026-07-21`. Their actual cloud hostnames were `{report['cases'][0]['actual_host']['hostname']}` and `{report['cases'][1]['actual_host']['hostname']}`, with Linux `{report['cases'][0]['actual_host']['uname'][2]}` and `{report['cases'][1]['actual_host']['uname'][2]}`. Both actual kernels booted in QEMU with raw exit 33 and retained full serial logs in their single-case phases.\n\nComplete loaded ELF bytes compare equal ({kernel['bytes']:,} bytes, SHA256 `{kernel['sha256']}`). Complete initramfs and BIOS bytes also compare equal. The comparison opened stable descriptors for the verified restored A4 original bytes and actual completed C4 snapshots; their exact stats, sizes and hashes are retained in `live-comparison.json`. No original compiler target was opened. Offline verification independently recomputes full byte equality from both packaged cases.\n\nEach case records 369 compiler calls, 738 ledger events, 332 successful Cargo units and 61 canonical local descriptors; the complete descriptor mappings compare equal. Cargo producer identity counts are recorded and compared separately. Probe results are retained without relabelling their three legitimate exit-1 queries as compiler failures. Exact source controls, compiler arguments, profile custody, original controllers, successful source checks and QEMU evidence are independently verified by each case verifier.\n\nThis result holds the literal absolute Cargo/Rustup registry/toolchain roots, native tool prefix and profile virtual prefix fixed, with the explicit schema4 job1/canonical-metadata/epoch/synthetic-builder profile. It establishes the observed two-instance reproduction; it does not establish an immutable environment, arbitrary-path/host reproduction, provider instance attestation or an unprofiled default-build result. The frozen producer's original `result.scope` same-host wording remains verbatim; this independent comparison carries the new result.\n\n```sh\npython3 -I support/build/evidence/2026-10-17-repro-cross-instance/verify.py\npython3 -I -O support/build/evidence/2026-10-17-repro-cross-instance/verify.py\n```\n\nBoth sibling phases `2026-10-17-repro-kernel-a4` and `2026-10-17-repro-kernel-c4` are required. Their complete checksum inventories are bound in `comparison.json`; neither historical phase is modified. The verifier performs offline checks only, without a compiler, Cargo, network, captured controller or VM.\n''')
    (destination/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(destination.iterdir()) if p.is_file()))
    print(json.dumps({'phase':str(destination),'passed':True,'complete_input_bytes_equal':report['complete_input_bytes_equal'],'compiler_calls':[x['compiler_calls'] for x in report['cases']],'canonical_local_descriptors_equal':report['canonical_local_descriptors_equal']},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--capture-completed-c4',action='store_true');args=parser.parse_args()
    try:
        if args.capture_completed_c4:
            need(BASE.name=='cross-host-review','capture is only permitted from the scratch review script');capture()
        else:print(json.dumps(verify(),indent=2))
    except (OSError,ValueError,KeyError) as error:print('comparison failed: '+str(error),file=sys.stderr);raise SystemExit(1)
