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
        digest,name=line.split('  ',1);rel(name)
        need(re.fullmatch('[0-9a-f]{64}',digest) is not None and name not in expected_checksums,'invalid SHA record')
        expected_checksums[name]=digest
    actual={str(x.relative_to(BASE)) for x in BASE.rglob('*') if x.is_file() and x.name!='SHA256SUMS'}
    need(actual==set(expected_checksums),'SHA coverage mismatch')
    for name,digest in expected_checksums.items():need(sha(read(name))==digest,'package SHA mismatch')
    raw=archive(load('raw.manifest.json'),'raw.tar.gz');need(len(raw)==108,'raw member scope changed')
    art=load('artifacts/manifest.json');payloads={}
    for a in art['artifacts']:
        data=gzip.decompress(container(a,a['kind']))
        need(len(data)==a['original_bytes'] and sha(data)==a['original_sha256'],'original artifact mismatch')
        payloads[a['original_sha256']]=data
    need(len(payloads)==4 and len(art['original_paths'])==8,'binary scope mismatch')
    original=dict(raw)
    for name,record in art['original_paths'].items():
        data=payloads[record['artifact']];check(data,record,name);need(name not in original,'duplicate logical input');original[name]=data
    need(len(original)==116,'original file scope mismatch')
    expected_paths=set();captures={}
    package_bindings=load('inputs/frozen-package-bindings.json')['cases']
    for case in ('A2','B2'):
        captures[case]=load('inputs/'+case+'-capture.json')
        binding_record=next(r for r in package_bindings if r['case']==case)
        need(sha(read('inputs/'+case+'-capture.json'))==binding_record['original_capture_sha256'],'frozen case capture binding mismatch')
        need(len(captures[case]['files'])==60,'case capture scope mismatch')
        for record in captures[case]['files']:
            check(original[record['path']],record,record['path']);need(record['read_stable'] is True,'unstable original case capture');expected_paths.add(record['path'])
    capture=load('capture.json')
    for record in capture['new_comparison_originals']:
        check(original[record['path']],record,record['path']);need(record['read_stable'] is True,'unstable original comparison read');expected_paths.add(record['path'])
    need(expected_paths==set(original),'consolidated capture coverage mismatch')
    for copy in load('readable/manifest.json')['copies']:
        data=read(copy['path']);check(data,copy,copy['path']);need(data==original[copy['original_path']],'readable/original mismatch')
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
    cases={};loaded={}
    for case in ('A2','B2'):
        root='normalized-cloud/'+case+'/';policy=json.loads(original[root+'policy.json']);result=json.loads(original[root+'result.json']);qemu=json.loads(original[root+'kernel-run/qemu.json']);commands=json.loads(original['normalized-cloud/controller-'+case+'/commands.json'])
        names=['worktree','source-verification','clean-build-and-boot','boot-live-recheck','post-source-verification','worktree-status','installed-components','installed-targets']
        need([(r['name'],r['returncode']) for r in commands]==[(n,0) for n in names],'actual case command outcomes changed')
        for command in commands:
            name='normalized-cloud/'+command['log'].split('/normalized-cloud/',1)[1]
            need(sha(original[name])==command['log_sha256'] and len(original[name])==command['log_size'],'case command/log binding mismatch')
        need(policy['target_absent_at_prelaunch'] is True and result['returncode']==0,'actual cold-run receipt changed')
        need(all(result[f] is True for f in ('profile_custody_unchanged','source_components_unchanged','profile_code_unchanged')),'actual custody result changed')
        need(qemu['raw_exit_code']==33 and qemu['recorder_exit_code']==33 and qemu['timed_out'] is False,'actual successful boot record changed')
        need(original['normalized-cloud/controller-'+case+'/worktree-status.log']==b'','case status was not empty')
        serial=original[root+'kernel-run/serial.log'];need(len(serial)==qemu['serial_size'] and sha(serial)==qemu['serial_sha256'],'case serial mismatch')
        text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)','',serial.decode(errors='replace'))
        for marker in ('OSTD initialized. Preparing components.','TRILLIONNIUM_A01_INIT_BEGIN','TRILLIONNIUM_A01_CPU_COUNT=1','Successfully booted.','TRILLIONNIUM_A01_BOOT_OK'):need(marker in text,'actual boot marker missing')
        for fatal in ('panicked at','An uncaught panic occurred:','Uncaught panic:'):need(fatal not in text,'actual guest panic')
        loaded[case]={}
        for option,record in qemu['artifacts'].items():
            name='normalized-cloud/'+record['path'].split('/normalized-cloud/',1)[1];data=original[name]
            need(len(data)==record['size'] and sha(data)==record['sha256'],'actual loaded snapshot mismatch');loaded[case][option]=data
        flag='--remap-path-prefix='+policy['real_root']+'='+policy['virtual_root'];rows=[json.loads(x) for x in original[root+'rustc.jsonl'].splitlines()];need(len(rows)==369,'compiler log scope changed')
        for row in rows:
            expected=list(row['incoming_argv']);index=expected.index('--') if '--' in expected else len(expected)
            if flag not in expected[:index]:expected.insert(index,flag)
            need(expected==row['effective_argv']==row['argv'],'actual compiler argv preservation changed')
        count=0
        def project(value):
            if isinstance(value,str):
                real,virtual=policy['real_root'],policy['virtual_root']
                if value==real or value.startswith(real+'/'):return virtual+value[len(real):]
                prefix='path+file://'+real
                if value==prefix or any(value.startswith(prefix+b) for b in ('/','#','@')):return 'path+file://'+virtual+value[len(prefix):]
                return value
            if isinstance(value,list):return [project(v) for v in value]
            if isinstance(value,dict):return {k:project(v) for k,v in value.items()}
            return value
        for name,data in raw.items():
            if name.startswith(root+'metadata/') and name.endswith('.binding.json'):
                count+=1;prefix=name[:-len('.binding.json')];record=json.loads(data);before=original[prefix+'.original.json'];mapped=original[prefix+'.mapped.json']
                need(sha(before)==record['original_sha256'] and sha(mapped)==record['mapped_sha256'] and project(json.loads(before))==json.loads(mapped),'actual metadata projection changed')
        need(count==6,'metadata pair scope changed')
        need(b'PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)' in original['normalized-cloud/comparison/'+case+'-live-recheck.log'],'original comparison live-check log missing')
        cases[case]=policy
    need(cases['A2']['real_root']!=cases['B2']['real_root'] and cases['A2']['virtual_root']==cases['B2']['virtual_root'],'source/virtual root premise changed')
    need(cases['A2']['code_sha256']==cases['B2']['code_sha256'] and cases['A2']['components_sha256']==cases['B2']['components_sha256'],'shared profile input premise changed')
    equality={k:loaded['A2'][k]==loaded['B2'][k] for k in ('-kernel','-initrd','-bios')}
    need(equality=={'-kernel':False,'-initrd':True,'-bios':True},'expected actual input mismatch changed')
    diagnosis=load('diagnosis/inputs.json');need(diagnosis['actual_complete_input_bytes_equal']==equality and diagnosis['comparison_passed'] is False,'diagnosis overstates equality')
    for option in equality:
        for case in ('A2','B2'):
            record=diagnosis['inputs'][option][case];check(loaded[case][option],record,'diagnosed '+case+option)
    need(len(loaded['A2']['-kernel'])-len(loaded['B2']['-kernel'])==1416==diagnosis['A2_kernel_minus_B2_bytes'],'kernel size difference changed')
    first=next((i for i,(a,b) in enumerate(zip(loaded['A2']['-kernel'],loaded['B2']['-kernel'])) if a!=b),None)
    need(first==load('diagnosis/elf.json')['first_differing_byte_offset']==40,'first ELF difference changed')
    observation=load('root-observation.json')
    need(observation['command']['argv']==['python3','compare-normalized-cloud.py'] and observation['command']['exit_code']==1,'original tool observation changed')
    need(observation['raw_traceback_available'] is False and observation['independent_failure_log_available'] is False and observation['comparison_script_reexecuted_by_packager'] is False,'exception provenance overstated')
    need(observation['exception_final_line']=='ValueError: actual boot input bytes differ','original reported final line changed')
    need(sha(original['compare-normalized-cloud.py'])=='5566d3648f6ffff15cb84cb2e1be280899983109b38eb1024873d1f1aae594e6','original comparator changed')
    need(b"require(all(equality.values()), 'actual boot input bytes differ')" in original['compare-normalized-cloud.py'],'original failure guard absent')
    need(observation['existing_regular_members']==['A2-live-recheck.log','B2-live-recheck.log'] and observation['result_json_present'] is False and 'normalized-cloud/comparison/result.json' not in original,'original comparison output scope changed')
    report=load('report.json');need(report['comparison_passed'] is False and report['cross_path_byte_reproduction_accepted'] is False and report['case_boot_results']=={'A2':True,'B2':True},'report conflates boot and equality')
    restored=None
    if restore is not None:
        destination=Path(restore).absolute();need(destination!=BASE and BASE not in destination.parents,'restore must be outside phase');destination.mkdir(parents=False,exist_ok=False)
        for name,data in dict(original,**sources).items():
            path=destination.joinpath(*rel(name).parts);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(data)
            need(path.read_bytes()==data,'restore mismatch')
        restored=str(destination)
    return {'passed':True,'scope':'Offline verification of preserved failed-comparison evidence; comparison itself remains failed. No new build, guest, live check or original comparator execution.','sha256sum_entries':len(expected_checksums),'original_unique_files':116,'raw_regular_members':108,'binary_unique_inputs':4,'binary_original_paths':8,'source_controls':86,'source_tree_objects':30,'actual_boots_passed':{'A2':True,'B2':True},'comparison_passed':False,'actual_complete_input_bytes_equal':equality,'original_comparator_exit_code':1,'raw_traceback_available':False,'restored_directory':restored}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore',metavar='NEW_DIRECTORY',help='reconstruct consolidated originals and exact selected source controls outside this phase; never execute them')
    args=parser.parse_args()
    try:
        print(json.dumps(verify(args.restore),indent=2))
    except (ValueError,KeyError,OSError,tarfile.TarError,EOFError) as error:
        print('verification failed: '+str(error),file=sys.stderr);sys.exit(1)
