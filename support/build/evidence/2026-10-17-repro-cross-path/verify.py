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
        digest,name=line.split('  ',1);rel(name);need(re.fullmatch('[0-9a-f]{64}',digest) is not None and name not in expected,'invalid checksum record');expected[name]=digest
    need({str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p!=BASE/'SHA256SUMS'}==set(expected),'checksum coverage mismatch')
    for name,digest in expected.items():need(sha(read(name))==digest,'package checksum mismatch: '+name)
    raw=archive(load('raw.manifest.json'),'raw');originals=dict(raw);art=load('artifacts/manifest.json');payloads={}
    for row in art['artifacts']:
        data=gzip.decompress(container(row,row['kind']));need(len(data)==row['original_bytes'] and sha(data)==row['original_sha256'],'input reconstruction mismatch');payloads[row['original_sha256']]=data
    need(len(payloads)==3 and len(art['original_paths'])==8,'binary input scope mismatch')
    for name,row in art['original_paths'].items():
        data=payloads[row['artifact']];check(data,row,name);need(name not in originals,'binary path overlap');originals[name]=data
    capture=load('capture.json');report=load('report.json')
    need(len(originals)==capture['original_file_count']==report['preservation']['original_files'],'original inventory count mismatch')
    need(len(raw)==capture['raw_member_count']==report['preservation']['raw_regular_members'],'raw inventory count mismatch')
    for copy in load('readable/manifest.json')['copies']:
        data=read(copy['path']);check(data,copy,copy['path']);need(data==originals[copy['original_path']],'readable copy differs')
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

    import importlib.util
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('schema4_checks',BASE/'schema4_checks.py');checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
    need(sha(originals['run-normalized-cloud-v4.py'])=='b79ece02e233b9563a4418310d41fb64c4374740f5bb30c4a6e598fe11158805','case controller identity changed')
    actual=json.loads(originals['normalized-cloud/comparison-v4/result.json']);observed=[];inputs=[];case_scopes=[];expected_inventory=set();modes={}
    need([c['case'] for c in actual['cases']]==['A4','B4'],'comparison case ordering changed')
    for case,comparison_case in zip(('A4','B4'),actual['cases']):
        receipt=load('case-receipts/'+case+'.json');case_capture=receipt['capture'];case_report=receipt['report'];root='normalized-cloud/'+case+'/';a=lambda name:originals[root+name]
        own={r['path'] for r in case_capture['files']};need(len(own)==len(case_capture['files'])==61,'case input count mismatch');expected_inventory.update(own)
        for row in case_capture['files']:
            check(originals[row['path']],row,row['path']);need(row['read_stable'] is True,'unstable case capture');modes[row['path']]=row['stat']['st_mode'] & 0o7777
        need(case_report['case']==case and case_report['source_commit']==binding['producer_commit'],'case producer/report mismatch')
        commands=json.loads(originals['normalized-cloud/controller-'+case+'/commands.json']);names=['worktree','source-verification','clean-build-and-boot','boot-live-recheck','post-source-verification','worktree-status','installed-components','installed-targets']
        need([(r['name'],r['returncode']) for r in commands]==[(n,0) for n in names],'not eight successful case commands')
        need(commands[0]['argv'][-1]==binding['producer_commit'],'initial worktree producer mismatch')
        for command in commands:
            path='normalized-cloud/'+command['log'].split('/normalized-cloud/',1)[1];need(len(originals[path])==command['log_size'] and sha(originals[path])==command['log_sha256'],'case command/log binding mismatch')
        before=originals['normalized-cloud/controller-'+case+'/source-verification.log'];after=originals['normalized-cloud/controller-'+case+'/post-source-verification.log'];need(before==after and json.loads(before)['passed'] is True,'pre/post source verification mismatch');need(originals['normalized-cloud/controller-'+case+'/worktree-status.log']==b'','dirty actual source status')
        policy=json.loads(a('policy.json'));result=json.loads(a('result.json'));qemu=json.loads(a('kernel-run/qemu.json'));owner=json.loads(originals['full-kernel-profile-v4/owner.json'])
        need(policy['target_absent_at_prelaunch'] is True and result['returncode']==result['child_returncode']==0,'case was not cold/successful');need(all(result[k] is True for k in ['profile_custody_unchanged','source_components_unchanged','profile_code_unchanged']),'case postrun custody mismatch')
        need(binding['producer_commit'].encode() in a('kernel-run/environment.log').splitlines(),'actual environment producer mismatch')
        for name in ('profile.py','rustc-wrapper.py','cargo-metadata-wrapper.py'):
            data=originals['full-kernel-profile-v4/helpers/'+name];need(data==sources['source/support/build/repro/'+name] and sha(data)==policy['code_sha256'][name]==owner['code_sha256'][name],'private helper/source/policy mismatch')
        need(sha(sources['source/support/build/repro/run.py'])==policy['code_sha256']['run.py']==owner['code_sha256']['run.py'],'projection launcher binding mismatch');need(originals['full-kernel-profile-v4/virtual-asterinas/Components.toml']==sources['source/kernel/asterinas/Components.toml'],'Components binding mismatch')
        files={r['path']:r for r in case_capture['files']};directories={r['path']:r for r in case_capture['directories']}
        for path,row in policy['profile_snapshot'].items():
            name='full-kernel-profile-v4' if path=='.' else 'full-kernel-profile-v4/'+path
            if 'identity' in row:need(sha(originals[name])==row['sha256'] and files[name]['stat']==row['identity'],'profile snapshot identity/bytes mismatch')
            else:need(directories[name]['stat']==row,'profile directory identity mismatch')
        execution=checks.execution_records(policy,a('kernel-run/environment.log'));compiler=checks.compiler_records(checks.jsonl(a('rustc.jsonl')),checks.jsonl(a('compiler-units.jsonl')),policy);guest=checks.boot(qemu,a('kernel-run/serial.log'),originals)
        need(json.loads(json.dumps({k:v for k,v in compiler.items() if k!='canonical_local_units'}))==case_report['compiler_summary'],'case compiler summary changed')
        need(compiler['compiler_calls']==369 and compiler['producer_ledger_rows']==738,'expected actual compiler scope changed')
        core=[row for row in checks.jsonl(a('rustc.jsonl')) if '--crate-name' in row['incoming_argv'] and row['incoming_argv'][row['incoming_argv'].index('--crate-name')+1]=='aster_core'];actual_source=policy['real_root']+'/kernel/core/src/lib.rs';need(len(core)==1 and actual_source in core[0]['incoming_argv'],'actual distinct source input missing')
        loaded={}
        for option,row in qemu['artifacts'].items():
            data=payloads[row['sha256']];need(len(data)==row['size'],'boot input size differs');loaded[option]=data
            need(comparison_case['inputs'][option]=={'path':row['path'],'size':row['size'],'sha256':row['sha256']},'comparison input does not match actual boot input')
        import struct
        kernel=loaded['-kernel'];need(kernel[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<HH',kernel,16)==(2,3),'not pinned OSDK ELF64/EM_386 image');need(kernel[:8192].find(struct.pack('<I',0x1badb002))>=0,'missing Multiboot header')
        for name in ('make-exit-code.txt','run-exit-code.txt','manifest-cleanup-exit-code.txt','log-exit-code.txt'):need(int(a('kernel-run/'+name))==0,'nonzero case action receipt')
        cleanup=json.loads(a('kernel-run/manifest-cleanup.json'));need(cleanup['outcome']=='owned_removed' and cleanup['passed'] is True,'case manifest cleanup mismatch')
        need(b'PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)' in originals['normalized-cloud/controller-'+case+'/boot-live-recheck.log'],'case live check missing')
        fresh=originals['normalized-cloud/comparison-v4/'+case+'-live-recheck.log'];need(fresh==b'PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)\n','fresh comparison live check missing')
        for key,value in {'source_commit':binding['producer_commit'],'real_root':policy['real_root'],'virtual_root':policy['virtual_root'],'actual_core_source_argument':actual_source,'actual_host':policy['actual_host'],'embedded_builder':policy['embedded_builder'],'profile_code_sha256':policy['code_sha256'],'components_sha256':policy['components_sha256'],'target_absent_at_prelaunch':True,'compiler_calls':compiler['compiler_calls'],'canonical_local_units':compiler['canonical_local_units'],'compiler_producer_ledger_sha256':sha(a('compiler-units.jsonl')),'raw_qemu_exit':33,'serial_size':len(a('kernel-run/serial.log')),'serial_sha256':sha(a('kernel-run/serial.log'))}.items():need(comparison_case[key]==value,'comparison case field mismatch: '+case+':'+key)
        need(comparison_case['all_arguments_except_recorded_metadata_and_remap_preserved'] is True and comparison_case['target_calls']==compiler['freestanding_calls'],'compiler scope mismatch')
        need(comparison_case['live_recheck']['returncode']==0 and comparison_case['live_recheck']['argv']==['python3','-I',str(Path(policy['real_root']).parents[1]/'support/build/check-boot.py'),str(Path('/workspace/scratch/ae1a8cf05419/normalized-cloud')/case/'kernel-run'),'--live-artifacts'],'comparison live command changed')
        observed.append(comparison_case);inputs.append(loaded);case_scopes.append({'case':case,'compiler_calls':369,'ledger_events':738,'raw_qemu_exit':33,'policy_jobs':execution['policy_jobs']})
    comparison=checks.compare_cases(observed[0],observed[1],inputs[0],inputs[1]);need(comparison['passed'] is True and actual['passed'] is True and actual['complete_input_bytes_equal']==comparison['complete_input_bytes_equal'],'complete input comparison did not pass')
    need(actual['cross_host_claimed'] is False and actual['immutable_host_claimed'] is False,'actual comparison scope widened')
    need(observed[0]['embedded_builder']==observed[1]['embedded_builder'],'embedded builder differs')
    command=json.loads(originals['normalized-cloud/controller-comparison-v4/command.json']);output=originals['normalized-cloud/controller-comparison-v4/output.log'];script=originals['normalized-cloud/controller-comparison-v4/compare-normalized-cloud-v4.py'];launcher=originals['run-normalized-comparison-v4.py']
    need(script==originals['compare-normalized-cloud-v4.py']==originals['source-bridge-review-final/compare-normalized-cloud-v4.py'],'actual script copy differs from reviewed script')
    need(sha(script)==command['script_sha256']==report['comparator_sha256']=='7c1da58aa5b1e3ee2484404349cee31f09e7bf3e5df39e563e72865dcc933a61','actual comparator hash mismatch')
    need(command['actual_returncode']==0 and command['script_unchanged'] is True and len(output)==command['output_size'] and sha(output)==command['output_sha256'],'actual comparator controller receipt mismatch')
    need(command['argv']==['python3','-I','/workspace/scratch/ae1a8cf05419/compare-normalized-cloud-v4.py',binding['producer_commit']] and command['cwd']=='/workspace/scratch/ae1a8cf05419','actual comparator command changed')
    need(sha(launcher)==report['launcher_sha256'],'actual launcher bytes mismatch')
    shown=json.loads(output);need(shown['passed'] is True and shown['actual_inputs_equal']==comparison['complete_input_bytes_equal'] and shown['raw_qemu_exits']==[33,33] and shown['kernel_sha256']==sha(inputs[0]['-kernel']) and shown['kernel_size']==len(inputs[0]['-kernel']) and shown['scope']==actual['scope'],'complete actual comparator output differs')
    reviewsums=originals['source-bridge-review-final/SHA256SUMS'];need(sha(reviewsums)==report['static_review_sha256sums']=='bd407076082f9b7abf6d1c6400759b52823ab7682aa9e1eb6faa363977b630bf','static review receipt mismatch')
    for line in reviewsums.decode().splitlines():
        digest,name=line.split('  ',1);rel(name);need(sha(originals['source-bridge-review-final/'+name])==digest,'static review checksum mismatch')
    for row in capture['new_stable_reads']:
        need(row['read_stable'] is True,'unstable comparison capture');check(originals[row['path']],row,row['path']);expected_inventory.add(row['path']);modes[row['path']]=row['stat']['st_mode'] & 0o7777
    need(expected_inventory==set(originals),'unaccounted original file')
    need(not any('/target/' in name or 'normal-N1' in name for name in originals),'active target/N1 input packaged')
    for row in load('raw.manifest.json')['members']:need(modes[row['member']]==row['mode'],'raw mode binding mismatch')
    need(report['passed'] is True and report['complete_input_bytes_equal']==comparison['complete_input_bytes_equal'] and report['raw_qemu_exits']==[33,33] and report['cross_host_claimed'] is False and report['immutable_host_claimed'] is False and report['ordinary_default_build_claimed'] is False,'report scope widened')
    restored=None
    if restore is not None:
        destination=Path(restore).absolute();need(destination!=BASE and BASE not in destination.parents,'restore must be outside package');destination.mkdir(parents=False,exist_ok=False)
        for name,data in dict(originals,**sources).items():
            path=destination.joinpath(*rel(name).parts);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(data)
            need(path.read_bytes()==data,'restored bytes mismatch')
        restored=str(destination)
    return {'passed':True,'sha256sum_entries':len(expected),'original_files':len(originals),'raw_members':len(raw),'source_controls':len(sources),'source_git_tree_objects':len(trees['objects']),'unique_binary_inputs':len(payloads),'cases':case_scopes,'complete_input_bytes_equal':comparison['complete_input_bytes_equal'],'kernel_sha256':sha(inputs[0]['-kernel']),'kernel_bytes':len(inputs[0]['-kernel']),'cross_host_claimed':False,'immutable_host_claimed':False,'restored_directory':restored,'scope':'Offline complete retained byte/source/compiler/guest/comparison checks only; no comparator, live check, Cargo, target access or VM.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--restore',metavar='NEW_DIRECTORY');args=parser.parse_args()
    try:print(json.dumps(verify(args.restore),indent=2))
    except (ValueError,KeyError,OSError,tarfile.TarError,EOFError) as error:print('verification failed: '+str(error),file=sys.stderr);sys.exit(1)
