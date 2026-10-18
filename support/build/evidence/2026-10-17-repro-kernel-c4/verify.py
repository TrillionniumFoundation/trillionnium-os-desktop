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
    expected_checksums={}
    for line in read('SHA256SUMS').decode().splitlines():
        digest,name=line.split('  ',1);rel(name);need(re.fullmatch('[0-9a-f]{64}',digest) is not None and name not in expected_checksums,'invalid SHA record');expected_checksums[name]=digest
    actual={str(x.relative_to(BASE)) for x in BASE.rglob('*') if x.is_file() and x.name!='SHA256SUMS'}
    need(actual==set(expected_checksums),'checksum coverage mismatch')
    for name,digest in expected_checksums.items():need(sha(read(name))==digest,'package checksum mismatch')
    report=load('report.json');case=report['case'];need(case == 'C4','unexpected case')
    raw=archive(load('raw.manifest.json'),'raw.tar.gz');originals=dict(raw);art=load('artifacts/manifest.json');payloads={}
    for record in art['artifacts']:
        data=gzip.decompress(container(record,record['kind']));need(len(data)==record['original_bytes'] and sha(data)==record['original_sha256'],'original input mismatch');payloads[record['original_sha256']]=data
    need(len(payloads)==3 and len(art['original_paths'])==4,'binary input scope mismatch')
    for name,record in art['original_paths'].items():
        data=payloads[record['artifact']];check(data,record,name);need(name not in originals,'duplicate logical binary path');originals[name]=data
    capture=load('capture.json');need(len(originals)==len(capture['files'])==report['original_file_count'],'original file scope mismatch')
    need(set(originals)=={r['path'] for r in capture['files']},'capture inventory mismatch')
    for record in capture['files']:check(originals[record['path']],record,record['path']);need(record['read_stable'] is True,'unstable original capture')
    for copy in load('readable/manifest.json')['copies']:
        data=read(copy['path']);check(data,copy,copy['path']);need(data==originals[copy['original_path']],'readable copy mismatch')
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
    need(binding['producer_commit']=='4e8c7083575cec69efabe8d2250dfdd040c8dee8' and binding['producer_complete_tree']=='d50cc2fd3fac4e8060ff26c324267b267767bca2','wrong producer')
    root='normalized-cloud/'+case+'/';a=lambda name:originals[root+name]
    need(not any('/target/' in n for n in originals),'target must not be packaged')
    need(all(not n.startswith('normalized-cloud/') or n.startswith(root) or n.startswith('normalized-cloud/controller-'+case+'/') for n in originals),'other case output was packaged')
    commands=json.loads(originals['normalized-cloud/controller-'+case+'/commands.json']);names=['worktree','source-verification','clean-build-and-boot','boot-live-recheck','post-source-verification','worktree-status','installed-components','installed-targets']
    need([(r['name'],r['returncode']) for r in commands]==[(name,0) for name in names],'expected eight actual commands did not pass')
    need(commands[0]['argv'][-1]==binding['producer_commit'],'actual initial producer differs')
    for command in commands:
        name='normalized-cloud/'+command['log'].split('/normalized-cloud/',1)[1]
        need(sha(originals[name])==command['log_sha256'] and len(originals[name])==command['log_size'],'command/log binding mismatch')
    before=originals['normalized-cloud/controller-'+case+'/source-verification.log'];after=originals['normalized-cloud/controller-'+case+'/post-source-verification.log']
    need(before==after and json.loads(before)['passed'] is True,'actual pre/post source checks mismatch')
    need(originals['normalized-cloud/controller-'+case+'/worktree-status.log']==b'','actual source worktree status was not empty')
    need(sha(originals['run-normalized-cloud-v4.py'])=='b79ece02e233b9563a4418310d41fb64c4374740f5bb30c4a6e598fe11158805','actual controller identity differs')
    original=originals['run-normalized-cloud-v4.py'];new=originals['round-next/run-normalized-cloud-c4.py']
    need(new==original.replace(b"if case not in ('A4', 'B4'):\n    raise SystemExit('case must be A4 or B4')",b"if case != 'C4':\n    raise SystemExit('case must be C4')"),'C4 controller has changes beyond the accepted case guard')
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
    policy=json.loads(a('policy.json'));result=json.loads(a('result.json'));qemu=json.loads(a('kernel-run/qemu.json'));owner=json.loads(originals['full-kernel-profile-v4/owner.json'])
    need(policy['actual_host']['hostname']==host['hostname'] and policy['actual_host']['uname'][2] in host['kernel'],'actual policy and fresh host mismatch')
    need(policy['target_absent_at_prelaunch'] is True and result['returncode']==result['child_returncode']==0,'actual cold build/action did not pass')
    need(all(result[k] is True for k in ('profile_custody_unchanged','source_components_unchanged','profile_code_unchanged')),'actual postrun custody mismatch')
    for name in ('profile.py','rustc-wrapper.py','cargo-metadata-wrapper.py'):
        data=originals['full-kernel-profile-v4/helpers/'+name]
        need(data==sources['source/support/build/repro/'+name] and sha(data)==policy['code_sha256'][name]==owner['code_sha256'][name],'helper/Git source/policy mismatch')
    need(sha(sources['source/support/build/repro/run.py'])==policy['code_sha256']['run.py']==owner['code_sha256']['run.py'],'launcher source binding mismatch')
    need(originals['full-kernel-profile-v4/virtual-asterinas/Components.toml']==sources['source/kernel/asterinas/Components.toml'],'Components source mismatch')
    files={r['path']:r for r in capture['files']};directories={r['path']:r for r in capture['directories']}
    for path,record in policy['profile_snapshot'].items():
        name='full-kernel-profile-v4' if path=='.' else 'full-kernel-profile-v4/'+path
        if 'identity' in record:need(sha(originals[name])==record['sha256'] and files[name]['stat']==record['identity'],'captured profile bytes/identity mismatch')
        else:need(directories[name]['stat']==record,'captured profile directory mismatch')
    import importlib.util
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('schema4_checks',BASE/'schema4_checks.py');checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
    execution=checks.execution_records(policy,a('kernel-run/environment.log'))
    compiler=checks.compiler_records(checks.jsonl(a('rustc.jsonl')),checks.jsonl(a('compiler-units.jsonl')),policy)
    need(json.loads(json.dumps(compiler))==load('analysis/compiler-and-custody.json'),'compiler proof does not match actual records')
    need(report['compiler_summary']==json.loads(json.dumps({k:v for k,v in compiler.items() if k!='canonical_local_units'})),'report compiler facts do not match recorded invocations')
    if (BASE/'DRAFT.json').exists():
        draft=load('DRAFT.json')
        need(draft['case']==case and draft['source_commit']==binding['producer_commit'] and draft['compiler_summary']==report['compiler_summary'],'retained draft capture facts differ from final report')
    guest=checks.boot(qemu,a('kernel-run/serial.log'),originals)
    import struct
    kernel=payloads[qemu['artifacts']['-kernel']['sha256']]
    need(kernel[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<HH',kernel,16)==(2,3),'not pinned OSDK ELF64/EM_386 compatible image')
    need(kernel[:8192].find(struct.pack('<I',0x1badb002))>=0,'missing Multiboot v1 header')
    core=[r for r in checks.jsonl(a('rustc.jsonl')) if '--crate-name' in r['incoming_argv'] and r['incoming_argv'][r['incoming_argv'].index('--crate-name')+1]=='aster_core']
    need(len(core)==1 and policy['real_root']+'/kernel/core/src/lib.rs' in core[0]['incoming_argv'],'core was not compiled from actual source root')
    need(b'PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)' in originals['normalized-cloud/controller-'+case+'/boot-live-recheck.log'],'actual postrun live-artifact check missing')
    for name in ('make-exit-code.txt','run-exit-code.txt','manifest-cleanup-exit-code.txt','log-exit-code.txt'):need(int(a('kernel-run/'+name))==0,'nonzero action receipt')
    cleanup=json.loads(a('kernel-run/manifest-cleanup.json'));need(cleanup['outcome']=='owned_removed' and cleanup['passed'] is True,'actual cleanup receipt mismatch')
    need(report['kernel_boot_passed'] is True and report['cross_path_accepted_by_this_case_capture'] is False and report['cross_host_accepted'] is False,'single-case acceptance scope changed')
    restored=None
    if restore is not None:
        destination=Path(restore).absolute();need(destination!=BASE and BASE not in destination.parents,'restore must be outside phase');destination.mkdir(parents=False,exist_ok=False)
        for name,data in dict(originals,**sources).items():
            target=destination.joinpath(*rel(name).parts);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(data)
            need(target.read_bytes()==data,'restore mismatch')
        restored=str(destination)
    return {'passed':True,'case':case,'sha256sum_entries':len(expected_checksums),'original_files':len(originals),'raw_members':len(raw),'source_controls':len(sources),'source_git_tree_objects':len(trees['objects']),'binary_unique_inputs':len(payloads),'compiler_calls':compiler['compiler_calls'],'ledger_events':compiler['producer_ledger_rows'],'local_metadata_replacements':compiler['local_metadata_replacements'],'actual_job1':True,'kernel_boot_passed':True,'raw_qemu_exit_code':33,'cross_path_accepted':False,'cross_host_accepted':False,'restored_directory':restored,'scope':'Offline retained evidence only; no new Cargo/Rust build, original controller, target read, live check or VM.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--restore',metavar='NEW_DIRECTORY',help='reconstruct verified original bytes/source controls into a fresh directory; never execute them');args=parser.parse_args()
    try:print(json.dumps(verify(args.restore),indent=2))
    except (ValueError,KeyError,OSError,tarfile.TarError,EOFError) as error:print('verification failed: '+str(error),file=sys.stderr);sys.exit(1)
