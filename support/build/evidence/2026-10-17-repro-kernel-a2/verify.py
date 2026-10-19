#!/usr/bin/env python3
"""Offline evidence verification; never invoke a captured command, build or VM."""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

BASE=Path(__file__).resolve().parent
MAX=2*1024*1024

def need(condition,message):
    if not condition:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def rel(name):
    p=PurePosixPath(name)
    need(bool(name) and not p.is_absolute() and '..' not in p.parts and '.' not in p.parts and str(p)==name and '\\' not in name,'unsafe relative path: '+name)
    return p

def read(name):
    p=BASE.joinpath(*rel(name).parts)
    need(p.is_file() and not p.is_symlink(),'missing regular package file: '+name)
    return p.read_bytes()

def load(name):
    return json.loads(read(name))

def check(data,record,label):
    need(len(data)==record['bytes'] and sha(data)==record['sha256'],'size/SHA mismatch: '+label)

def container(record,label):
    parts=[]
    for chunk in record['chunks']:
        data=read(chunk['path']);check(data,chunk,chunk['path'])
        need(len(data)<=MAX,'oversize chunk: '+chunk['path']);parts.append(data)
    data=b''.join(parts);check(data,record,label)
    return data

def archive(record,label,source=False):
    data=container(record,label);wanted={r['member']:r for r in record['members']}
    need(len(wanted)==len(record['members']),'duplicate manifest entry: '+label)
    members={}
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as stream:
        for member in stream.getmembers():
            rel(member.name)
            need(member.isfile() and member.name in wanted and member.name not in members,'unsafe/unexpected/duplicate archive member: '+member.name)
            record=wanted[member.name]
            need(member.mode==record['mode'],'tar mode mismatch: '+member.name)
            payload=stream.extractfile(member).read();check(payload,record,member.name)
            if source:
                digest=hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
                need(digest==record['git_blob'],'Git blob mismatch: '+member.name)
            members[member.name]=payload
    need(set(members)==set(wanted),'missing archive member: '+label)
    return members

def verify(restore=None):
    expected={}
    for line in read('SHA256SUMS').decode().splitlines():
        digest,name=line.split('  ',1);rel(name)
        need(re.fullmatch('[0-9a-f]{64}',digest) is not None and name not in expected,'invalid SHA record')
        expected[name]=digest
    actual={str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
    need(actual==set(expected),'SHA256SUMS coverage mismatch')
    for name,digest in expected.items():need(sha(read(name))==digest,'package SHA mismatch: '+name)
    expected_checksums=dict(expected)
    raw=archive(load('raw.manifest.json'),'raw.tar.gz')
    need(len(raw)==56,'raw nonbinary scope count mismatch')
    art=load('artifacts/manifest.json');originals={}
    for artifact in art['artifacts']:
        data=gzip.decompress(container(artifact,artifact['kind']))
        need(len(data)==artifact['original_bytes'] and sha(data)==artifact['original_sha256'],'reconstructed original artifact mismatch')
        originals[artifact['original_sha256']]=data
    need(len(originals)==3 and len(art['original_paths'])==4,'binary input scope count mismatch')
    logical={}
    for path,record in art['original_paths'].items():
        rel(path);data=originals[record['artifact']];check(data,record,path);logical[path]=data
    need(not set(raw)&set(logical),'duplicate original logical path')
    original=dict(raw,**logical);capture=load('capture.json')
    need(len(capture['files'])==60 and len(original)==60,'original capture scope count mismatch')
    need({r['path'] for r in capture['files']}==set(original),'capture coverage mismatch')
    for record in capture['files']:
        need(record['read_stable'] is True,'unstable read receipt');check(original[record['path']],record,record['path'])
    need(sum(n.startswith('normalized-cloud/A2/') for n in original)==44,'A file inventory mismatch')
    need(sum(n.startswith('normalized-cloud/controller-A2/') for n in original)==9,'controller inventory mismatch')
    need(sum(n.startswith('full-kernel-profile-v2/') for n in original)==6,'profile v1 inventory mismatch')
    need(not any('/target/' in n or '/B2/' in n or '/controller-B2/' in n for n in original),'out-of-scope B2/target input')
    for copy in load('readable/manifest.json')['copies']:
        data=read(copy['path']);check(data,copy,copy['path']);need(data==original[copy['original_path']],'readable/raw mismatch')
    sm=load('source/members.json');sources=archive(sm,'source/controls.tar.gz',source=True)
    need(len(sources)==86,'source-control scope mismatch')
    binding=load('source-binding.json');commit=binding['commit_object'].encode()
    need(hashlib.sha1(b'commit '+str(len(commit)).encode()+b'\0'+commit).hexdigest()==binding['producer_commit'],'Git producer commit identity mismatch')
    need(commit.splitlines()[0].decode()=='tree '+binding['producer_complete_tree'],'Git commit-tree mismatch')
    trees=load('source/tree-objects.json');tree_entries={}
    for digest,record in trees['objects'].items():
        data=base64.b64decode(record['raw_base64'],validate=True)
        need(len(data)==record['raw_bytes'] and sha(data)==record['raw_sha256'],'Git raw tree payload mismatch')
        need(hashlib.sha1(b'tree '+str(len(data)).encode()+b'\0'+data).hexdigest()==digest,'Git tree identity mismatch')
        entries={};offset=0
        while offset<len(data):
            end=data.index(b'\0',offset);header=data[offset:end];mode,name=header.split(b' ',1);entry_hash=data[end+1:end+21]
            need(len(entry_hash)==20,'truncated Git tree');entries[name.decode()]=(mode.decode(),entry_hash.hex());offset=end+21
        tree_entries[digest]=entries
    need(trees['root_tree']==binding['producer_complete_tree']==trees['path_trees'][''],'tree root binding mismatch')
    def lookup(path):
        parts=PurePosixPath(path).parts;digest=trees['root_tree'];mode=None
        for part in parts:
            mode,digest=tree_entries[digest][part]
        return mode,digest
    for record in sm['members']:
        mode,digest=lookup(record['path'])
        need(record['ref']==binding['producer_commit'] and mode in ('100644','100755') and digest==record['git_blob'],'producer-tree/path/blob membership mismatch')
    need(lookup('kernel/asterinas')[1]==binding['derived_kernel_tree']=='6b3cab110aa6d30d5b89f99c4389c9c3e01022da','derived kernel tree mismatch')
    need(binding['producer_commit']=='bdf7a08dcc0980fa85c0ba5abdf365b7d2c42e80' and binding['producer_complete_tree']=='eff51eb940d1f415aedb84555752ecbc97d58faa','wrong producer')
    def a(name):return original['normalized-cloud/A2/'+name]
    commands=json.loads(original['normalized-cloud/controller-A2/commands.json'])
    names=['worktree','source-verification','clean-build-and-boot','boot-live-recheck','post-source-verification','worktree-status','installed-components','installed-targets']
    need([(r['name'],r['returncode']) for r in commands]==[(n,0) for n in names],'eight completed command outcomes mismatch')
    for command in commands:
        name='normalized-cloud/'+command['log'].split('/normalized-cloud/',1)[1]
        need(len(original[name])==command['log_size'] and sha(original[name])==command['log_sha256'],'controller/log binding mismatch')
    need(sha(original['run-normalized-cloud-v2.py'])=='fe9b1180aaa1316075701553f82b5b129c1f541bf3a0f4513ae1ff2e234043e8','wrong v2 controller')
    policy=json.loads(a('policy.json'));result=json.loads(a('result.json'));owner=json.loads(original['full-kernel-profile-v2/owner.json']);qemu=json.loads(a('kernel-run/qemu.json'))
    need(policy['schema']=='a01-component-path-projection/2' and policy['target_absent_at_prelaunch'] is True,'v2/prelaunch receipt changed')
    for name in ('profile_custody_unchanged','source_components_unchanged','profile_code_unchanged'):need(result[name] is True,'profile postrun result changed: '+name)
    need(result['child_returncode']==0 and result['returncode']==0,'recorded A2 result changed')
    for name in ('profile.py','rustc-wrapper.py','cargo-metadata-wrapper.py'):
        data=original['full-kernel-profile-v2/helpers/'+name]
        need(sha(data)==policy['code_sha256'][name]==owner['code_sha256'][name] and data==sources['source/support/build/repro/'+name],'captured helper/source/policy binding mismatch')
    need(sha(sources['source/support/build/repro/run.py'])==policy['code_sha256']['run.py']==owner['code_sha256']['run.py'],'runner policy binding mismatch')
    components=original['full-kernel-profile-v2/virtual-asterinas/Components.toml']
    need(sha(components)==policy['components_sha256']==owner['components_sha256'] and components==sources['source/kernel/asterinas/Components.toml'],'Components binding mismatch')
    files={r['path']:r for r in capture['files']};directories={r['path']:r for r in capture['directories']}
    for path,record in policy['profile_snapshot'].items():
        logical='full-kernel-profile-v2' if path=='.' else 'full-kernel-profile-v2/'+path
        if 'identity' in record:
            need(sha(original[logical])==record['sha256'] and files[logical]['stat']==record['identity'],'profile prelaunch/capture binding mismatch')
        else:need(directories[logical]['stat']==record,'profile directory snapshot mismatch')
    pre=original['normalized-cloud/controller-A2/source-verification.log'];post=original['normalized-cloud/controller-A2/post-source-verification.log']
    need(pre==post and json.loads(pre)['passed'] is True and json.loads(post)['passed'] is True,'source pre/post mismatch')
    need(original['normalized-cloud/controller-A2/worktree-status.log']==b'','worktree status was not empty')
    need(b'PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)' in original['normalized-cloud/controller-A2/boot-live-recheck.log'],'actual postrun live-artifact acceptance receipt missing')
    log=a('kernel-run/run_kernel.log')
    need(len(re.findall(rb'^\s*Compiling\s',log,re.M))==279 and len([x for x in log.splitlines() if b'Finished `release`' in x])==2,'cold compile log scope changed')
    need(qemu['raw_exit_code']==33 and qemu['recorder_exit_code']==33 and qemu['timed_out'] is False and qemu['stage']=='complete','successful QEMU record changed')
    for name in ('make-exit-code.txt','run-exit-code.txt','manifest-cleanup-exit-code.txt','log-exit-code.txt'):need(int(a('kernel-run/'+name))==0,'nonzero action receipt: '+name)
    serial=a('kernel-run/serial.log')
    need(len(serial)==72341==qemu['serial_size'] and sha(serial)==qemu['serial_sha256']=='e0845a2d34a0f3d16d7a753c50c94f30b1d3eacc1d7b1649811cfdc4f574cccd','serial identity mismatch')
    clean=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)','',serial.decode(errors='replace'))
    for marker in ('OSTD initialized. Preparing components.','TRILLIONNIUM_A01_INIT_BEGIN','TRILLIONNIUM_A01_CPU_COUNT=1','Successfully booted.','TRILLIONNIUM_A01_BOOT_OK'):need(marker in clean,'missing actual guest marker: '+marker)
    for fatal in ('panicked at','An uncaught panic occurred:','Uncaught panic:','unknown panic payload! (fatal panic handling error','Non-resettable panic!','The panic handler panicked','Panicked in `PanicGuard`, aborting the system'):need(fatal not in clean,'fatal guest panic')
    need('(a01-repro@a01-fixed-profile)' in clean and policy['actual_host']['hostname']=='343e40cfefc1','synthetic builder/actual host provenance changed')
    for key,snapshot in qemu['artifacts'].items():
        path='normalized-cloud/'+snapshot['path'].split('/normalized-cloud/',1)[1]
        need(len(original[path])==snapshot['size'] and sha(original[path])==snapshot['sha256'],'loaded input snapshot mismatch: '+key)
    need(qemu['artifacts']['-kernel']['sha256']=='e89063b19e5895aa64695ba27c04d7d53fd5d65e23adeb0aab06983a1a33794d','wrong A2 kernel ELF')
    cleanup=json.loads(a('kernel-run/manifest-cleanup.json'))
    need(cleanup['outcome']=='owned_removed' and cleanup['passed'] is True and cleanup['anchor']==cleanup['captured'],'actual cleanup outcome changed')
    rows=[json.loads(line) for line in a('rustc.jsonl').splitlines()];need(len(rows)==369,'rustc call count changed')
    flag='--remap-path-prefix='+policy['real_root']+'='+policy['virtual_root'];already_count=0
    analysis=load('analysis/compiler-and-custody.json')
    need(len(analysis['all_rustc_row_checks'])==369,'all-row analysis scope mismatch')
    for i,row in enumerate(rows):
        incoming=row['incoming_argv'];expected=list(incoming);delimiter=expected.index('--') if '--' in expected else len(expected);already=flag in expected[:delimiter]
        if not already:expected.insert(delimiter,flag)
        already_count+=int(already)
        need(row['effective_argv']==expected==row['argv'],'Cargo/OSDK argument order changed beyond canonical insertion')
        need(flag in expected[:expected.index('--') if '--' in expected else len(expected)],'effective remap missing before delimiter')
        need(row['effective']['OSDK_BUILD_USERNAME']==policy['embedded_builder']['username'] and row['effective']['OSDK_BUILD_HOSTNAME']==policy['embedded_builder']['hostname'],'embedded builder override mismatch')
        record=analysis['all_rustc_row_checks'][i]
        need(record['jsonl_line']==i+1 and record['incoming_sha256']==sha(json.dumps(incoming,separators=(',',':')).encode()) and record['effective_sha256']==sha(json.dumps(expected,separators=(',',':')).encode()),'analysis/actual argv binding mismatch')
    need(already_count==130,'existing canonical mapping count changed')
    for name in ('aster_core','ostd','component_macro','aster_virtio'):
        selected=[(i+1,r) for i,r in enumerate(rows) if '--crate-name' in r['incoming_argv'] and r['incoming_argv'][r['incoming_argv'].index('--crate-name')+1]==name]
        need(len(selected)==1,'selected crate actual call ambiguity')
        saved=analysis['selected_crate_calls'][name][0]
        need(saved['jsonl_line']==selected[0][0] and saved['incoming_argv']==selected[0][1]['incoming_argv'] and saved['effective_argv']==selected[0][1]['effective_argv'],'selected incoming/effective actual argv mismatch')
    pair_count=0
    def project(value):
        if isinstance(value,str):
            real,virtual=policy['real_root'],policy['virtual_root']
            if value==real or value.startswith(real+'/'):return virtual+value[len(real):]
            prefix='path+file://'+real
            if value==prefix or any(value.startswith(prefix+boundary) for boundary in ('/','#','@')):return 'path+file://'+virtual+value[len(prefix):]
            return value
        if isinstance(value,list):return [project(v) for v in value]
        if isinstance(value,dict):return {k:project(v) for k,v in value.items()}
        return value
    for name,data in raw.items():
        if name.startswith('normalized-cloud/A2/metadata/') and name.endswith('.binding.json'):
            pair_count+=1;prefix=name[:-len('.binding.json')];record=json.loads(data)
            need(sha(raw[prefix+'.original.json'])==record['original_sha256'] and sha(raw[prefix+'.mapped.json'])==record['mapped_sha256'],'metadata pair hash mismatch')
            before=json.loads(raw[prefix+'.original.json']);mapped=json.loads(raw[prefix+'.mapped.json'])
            need(project(before)==mapped,'full metadata projection mismatch')
            need(all(r['in_workspace_before']==r['in_workspace_after'] and r['listed'] for r in record['component_membership']),'component membership changed')
    need(pair_count==6,'metadata pair scope mismatch')
    report=load('report.json')
    need(report['kernel_boot_passed'] is True and report['boot']['project_kernel_passed'] is True and report['b2_accepted_in_this_phase'] is False and report['cross_path_reproduction_accepted'] is False and report['cross_host_reproduction_accepted'] is False,'report A2-only acceptance scope changed')
    restored=None
    if restore is not None:
        destination=Path(restore).absolute();need(destination!=BASE and BASE not in destination.parents,'restore must be outside evidence phase')
        destination.mkdir(parents=False,exist_ok=False)
        for name,data in dict(original,**sources).items():
            target=destination.joinpath(*rel(name).parts);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(data)
            need(target.read_bytes()==data,'restored bytes mismatch')
        restored=str(destination)
    return {'passed':True,'sha256sum_entries':len(expected_checksums),'original_files':60,'raw_regular_members':56,'source_controls':86,'source_git_tree_objects':len(trees['objects']),'deduplicated_binary_inputs':3,'binary_original_paths':4,'rustc_calls':369,'all_compiler_flags_preserved':True,'metadata_pairs':6,'kernel_boot_passed':True,'qemu_raw_exit_code':33,'b2_accepted_in_this_phase':False,'cross_path_reproduction_accepted':False,'cross_host_reproduction_accepted':False,'restored_directory':restored,'scope':'Offline A2 evidence checks only; no new Cargo, make, captured controller, host suite or VM executed.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore',metavar='NEW_DIRECTORY',help='reassemble original A2 evidence/profile inputs and selected source controls outside this phase; never execute them')
    args=parser.parse_args()
    try:
        print(json.dumps(verify(args.restore),indent=2))
    except (ValueError,KeyError,OSError,tarfile.TarError,EOFError) as error:
        print('verification failed: '+str(error),file=sys.stderr);sys.exit(1)
