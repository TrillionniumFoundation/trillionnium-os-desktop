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
        need(re.fullmatch('[0-9a-f]{64}',digest) is not None and name not in expected_checksums,'invalid SHA record');expected_checksums[name]=digest
    actual={str(x.relative_to(BASE)) for x in BASE.rglob('*') if x.is_file() and x.name!='SHA256SUMS'}
    need(set(expected_checksums)==actual,'checksum coverage mismatch')
    for name,digest in expected_checksums.items():need(sha(read(name))==digest,'package checksum mismatch: '+name)
    raw=archive(load('raw.manifest.json'),'raw.tar.gz');need(len(raw)==32,'original nonbinary scope mismatch')
    artifact_manifest=load('artifacts/manifest.json');need(len(artifact_manifest['artifacts'])==1,'only prepared initramfs should exist')
    originals=dict(raw)
    for artifact in artifact_manifest['artifacts']:
        payload=gzip.decompress(container(artifact,artifact['kind']));need(len(payload)==artifact['original_bytes'] and sha(payload)==artifact['original_sha256'],'prepared initramfs mismatch')
        for name,record in artifact_manifest['original_paths'].items():
            check(payload,record,name);need(name not in originals,'duplicate original path');originals[name]=payload
    capture=load('capture.json');need(len(capture['files'])==33==len(originals),'capture scope mismatch')
    need({r['path'] for r in capture['files']}==set(originals),'capture inventory mismatch')
    for record in capture['files']:check(originals[record['path']],record,record['path']);need(record['read_stable'] is True,'unstable captured input')
    need(capture['original_empty_directories']==['normalized-cloud/A3/metadata'],'empty metadata inventory changed')
    need(not any('/qemu.json' in n or n.endswith('/serial.log') or '/artifacts-' in n for n in originals if n.startswith('normalized-cloud/A3/')),'unexpected guest artifact')
    for copy in load('readable/manifest.json')['copies']:
        data=read(copy['path']);check(data,copy,copy['path']);need(data==originals[copy['original_path']],'readable original mismatch')
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
    need(binding['producer_commit']=='4cf864b62859f0fdb39609589ddd9ef90c6dbc9d' and binding['producer_complete_tree']=='d6fc172e0581609e27656a6bef597f377487f0bc','wrong producer')
    def a(name):return originals['normalized-cloud/A3/'+name]
    original_commands=json.loads(originals['normalized-cloud/controller-A3/commands.json'])
    need([(r['name'],r['returncode']) for r in original_commands]==[('worktree',0),('source-verification',0),('clean-build-and-boot',2)],'original controller outcomes changed')
    post=json.loads(originals['normalized-cloud/controller-A3-postfailure/commands.json'])
    need([(r['name'],r['returncode']) for r in post]==[(n,0) for n in ['source-verification','worktree-status','source-head','source-tree','derived-kernel-tree']],'separate actual postfailure outcomes changed')
    for command in original_commands+post:
        name='normalized-cloud/'+command['log'].split('/normalized-cloud/',1)[1]
        need(sha(originals[name])==command['log_sha256'] and len(originals[name])==command.get('log_size',command.get('log_bytes')),'actual command/log binding mismatch')
    need(originals['normalized-cloud/controller-A3-postfailure/worktree-status.log']==b'','postfailure worktree was dirty')
    need(originals['normalized-cloud/controller-A3-postfailure/source-head.log'].decode().strip()==binding['producer_commit'],'postfailure producer changed')
    need(originals['normalized-cloud/controller-A3-postfailure/source-tree.log'].decode().strip()==binding['producer_complete_tree'],'postfailure complete tree changed')
    need(originals['normalized-cloud/controller-A3-postfailure/derived-kernel-tree.log'].decode().strip()==binding['derived_kernel_tree'],'postfailure kernel tree changed')
    before=originals['normalized-cloud/controller-A3/source-verification.log'];after=originals['normalized-cloud/controller-A3-postfailure/source-verification.log']
    need(before==after and json.loads(after)['passed'] is True,'separate postfailure source verification mismatch')
    policy=json.loads(a('policy.json'));result=json.loads(a('result.json'));owner=json.loads(originals['full-kernel-profile-v3/owner.json'])
    need(policy['target_absent_at_prelaunch'] is True and result['returncode']==result['child_returncode']==2,'actual failed action receipt changed')
    need(all(result[f] is True for f in ('profile_custody_unchanged','source_components_unchanged','profile_code_unchanged')),'actual postrun custody changed')
    for name in ('profile.py','rustc-wrapper.py','cargo-metadata-wrapper.py'):
        data=originals['full-kernel-profile-v3/helpers/'+name]
        need(data==sources['source/support/build/repro/'+name] and sha(data)==policy['code_sha256'][name]==owner['code_sha256'][name],'actual helper/source/policy binding mismatch')
    need(sha(sources['source/support/build/repro/run.py'])==policy['code_sha256']['run.py']==owner['code_sha256']['run.py'],'launcher source binding mismatch')
    need(originals['full-kernel-profile-v3/virtual-asterinas/Components.toml']==sources['source/kernel/asterinas/Components.toml'],'Components source binding mismatch')
    captured={r['path']:r for r in capture['files']};directories={r['path']:r for r in capture['directories']}
    for path,record in policy['profile_snapshot'].items():
        name='full-kernel-profile-v3' if path=='.' else 'full-kernel-profile-v3/'+path
        if 'identity' in record:need(sha(originals[name])==record['sha256'] and captured[name]['stat']==record['identity'],'profile captured bytes/identity mismatch')
        else:need(directories[name]['stat']==record,'profile directory identity mismatch')
    import importlib.util
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('a3_schema3_checks',BASE/'schema3_checks.py');checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
    rows=checks.jsonl(a('rustc.jsonl'));ledger=checks.jsonl(a('compiler-units.jsonl'));partial=checks.compiler_records(rows,ledger,policy)
    need(len(rows)==304 and len(ledger)==608 and partial['local_metadata_replacements']==32,'recorded partial compiler scope changed')
    need(not any('--crate-name' in r['incoming_argv'] and r['incoming_argv'][r['incoming_argv'].index('--crate-name')+1]=='aster_bigtcp' for r in rows),'failed prelogging consumer unexpectedly has a recorded compiler invocation')
    analysis=load('analysis/partial-compiler-proof.json')
    need(analysis['canonical_local_units']==partial['canonical_local_units'] and analysis['failed_aster_bigtcp_invocation_recorded'] is False,'partial proof mismatches actual rows')
    need(b'ValueError: extern lacks one unchanged successful producer: smoltcp' in a('kernel-run/run_kernel.log'),'original failure diagnostic absent')
    need(b'warning: build failed, waiting for other jobs to finish...' in a('console.log'),'original waiting-for-jobs diagnostic absent')
    need(len(re.findall(rb'^\s*Compiling\s',a('kernel-run/run_kernel.log'),re.M))==225,'partial compile-line count changed')
    need(int(a('kernel-run/make-exit-code.txt'))==int(a('kernel-run/run-exit-code.txt'))==2,'failed make/worker status changed')
    cleanup=json.loads(a('kernel-run/manifest-cleanup.json'))
    need(cleanup['outcome']=='owned_removed' and cleanup['passed'] is True and cleanup['anchor']==cleanup['captured'],'actual cleanup receipt changed')
    observation=load('observations/A3-smoltcp-observation.json');origin=load('observations/source.json');check(read('observations/A3-smoltcp-observation.json'),origin,'retained independent observation')
    need(observation['ledger_events']==608 and observation['ledger_sha256']==sha(a('compiler-units.jsonl')) and observation['console_sha256']==sha(a('console.log')),'observation raw-data binding mismatch')
    for event in observation['smoltcp_events']:
        need(event['record']==ledger[event['event_index_zero_based']],'observed smoltcp ledger event changed')
    need(observation['smoltcp_events'][0]['event_index_zero_based']==585 and observation['smoltcp_events'][-1]['event_index_zero_based']==len(ledger)-1==607,'actual smoltcp ledger order changed')
    for name,value in observation['smoltcp_events'][-1]['current_artifacts'].items():
        need(value['matches_completed_stat'] is True and value['actual']==ledger[607]['artifacts'][name],'retained postfailure stat observation mismatch')
    console=a('console.log').decode().splitlines()
    for line in observation['failure_lines']:need(console[line['line_one_based']-1]==line['text'],'retained failure-line observation mismatch')
    report=load('report.json')
    need(report['full_kernel_build_passed'] is False and report['kernel_boot_passed'] is False and report['qemu']['launched'] is False and report['qemu']['raw_exit_code'] is None,'report overstates A3 build/guest result')
    need(report['original_controller']['completed_command_count']==3 and report['postfailure_controller']['completed_command_count']==5,'report conflates original versus new postfailure commands')
    restored=None
    if restore is not None:
        destination=Path(restore).absolute();need(destination!=BASE and BASE not in destination.parents,'restore must be outside phase');destination.mkdir(parents=False,exist_ok=False)
        for directory in capture['original_empty_directories']:destination.joinpath(*rel(directory).parts).mkdir(parents=True,exist_ok=True)
        for name,data in dict(originals,**sources).items():
            target=destination.joinpath(*rel(name).parts);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(data)
            need(target.read_bytes()==data,'restore mismatch')
        restored=str(destination)
    return {'passed':True,'scope':'Offline integrity and truthful failure checks only; actual A3 kernel build failed and no QEMU launched. No new build, guest or original command execution.','sha256sum_entries':len(expected_checksums),'original_files':33,'raw_members':32,'prepared_binary_inputs':1,'source_controls':86,'source_git_tree_objects':30,'recorded_compiler_calls':304,'ledger_events':608,'recorded_local_metadata_replacements':32,'failed_consumer_has_compiler_record':False,'original_controller_exit_codes':[0,0,2],'new_postfailure_checks_exit_zero':True,'kernel_build_passed':False,'kernel_boot_passed':False,'qemu_raw_exit_code':None,'restored_directory':restored}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore',metavar='NEW_DIRECTORY',help='restore original failed-run evidence/profile bytes and selected source controls only; never execute them')
    args=parser.parse_args()
    try:
        print(json.dumps(verify(args.restore),indent=2))
    except (ValueError,KeyError,OSError,tarfile.TarError,EOFError) as error:
        print('verification failed: '+str(error),file=sys.stderr);sys.exit(1)
