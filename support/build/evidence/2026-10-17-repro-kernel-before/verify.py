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
    raw=archive(load('raw.manifest.json'),'raw.tar.gz')
    need(len(raw)==51,'raw nonbinary scope count mismatch')
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
    need(len(capture['files'])==55 and len(original)==55,'original capture scope count mismatch')
    need({r['path'] for r in capture['files']}==set(original),'capture coverage mismatch')
    for record in capture['files']:
        need(record['read_stable'] is True,'unstable read receipt');check(original[record['path']],record,record['path'])
    need(sum(n.startswith('normalized-cloud/A/') for n in original)==44,'A file inventory mismatch')
    need(sum(n.startswith('normalized-cloud/controller-A/') for n in original)==4,'controller inventory mismatch')
    need(sum(n.startswith('full-kernel-profile/') for n in original)==6,'profile v1 inventory mismatch')
    need(not any('v2' in n or '/target/' in n or '/A2/' in n or '/B2/' in n for n in original),'out-of-scope input')
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
    need(binding['producer_commit']=='542e09ebf0471124a01e3d721b531a29e141e54b' and binding['producer_complete_tree']=='8e7a594456108c9a9e796bdee2d22a26f9ebfbda','wrong producer')
    def a(name):return original['normalized-cloud/A/'+name]
    commands=json.loads(original['normalized-cloud/controller-A/commands.json'])
    need([(r['name'],r['returncode']) for r in commands]==[('worktree',0),('source-verification',0),('clean-build-and-boot',2)],'completed controller command outcomes mismatch')
    for command in commands:
        name='normalized-cloud/'+command['log'].split('/normalized-cloud/',1)[1]
        need(len(original[name])==command['log_size'] and sha(original[name])==command['log_sha256'],'controller/log binding mismatch')
    need(sha(original['normalized-cloud/run-normalized-cloud-v1.py'])=='726dab78bb9d9ff2ac83f3c9a0d8c495d4c7dfe3bf7c36774fe360dc0b433559','wrong v1 controller')
    policy=json.loads(a('policy.json'));result=json.loads(a('result.json'));owner=json.loads(original['full-kernel-profile/owner.json']);qemu=json.loads(a('kernel-run/qemu.json'))
    need(policy['target_absent_at_prelaunch'] is True,'prelaunch target absence receipt changed')
    for name in ('profile_custody_unchanged','source_components_unchanged','profile_code_unchanged'):need(result[name] is True,'profile result changed: '+name)
    need(result['child_returncode']==2 and result['returncode']==2,'recorded case result changed')
    for name in ('profile.py','rustc-wrapper.py','cargo-metadata-wrapper.py'):
        data=original['full-kernel-profile/helpers/'+name]
        need(sha(data)==policy['code_sha256'][name]==owner['code_sha256'][name] and data==sources['source/support/build/repro/'+name],'captured helper/source/policy binding mismatch')
    need(sha(sources['source/support/build/repro/run.py'])==policy['code_sha256']['run.py']==owner['code_sha256']['run.py'],'run.py policy binding mismatch')
    components=original['full-kernel-profile/virtual-asterinas/Components.toml']
    need(sha(components)==policy['components_sha256']==owner['components_sha256'] and components==sources['source/kernel/asterinas/Components.toml'],'Components binding mismatch')
    for path,record in policy['profile_snapshot'].items():
        if 'sha256' in record:need(sha(original['full-kernel-profile/'+path])==record['sha256'],'profile snapshot bytes mismatch')
    log=a('kernel-run/run_kernel.log')
    need(len(re.findall(rb'^\s*Compiling\s',log,re.M))==279 and len([x for x in log.splitlines() if b'Finished `release`' in x])==2,'cold compile log scope changed')
    need(qemu['raw_exit_code']==65 and qemu['recorder_exit_code']==65 and qemu['timed_out'] is False,'QEMU failure status changed')
    need(int(a('kernel-run/make-exit-code.txt'))==2,'make status changed')
    serial=a('kernel-run/serial.log')
    need(len(serial)==4627==qemu['serial_size'] and sha(serial)==qemu['serial_sha256'],'serial identity mismatch')
    need(b'OSTD initialized. Preparing components.' in serial and b'NotIncludeAllComponent("/tmp/trillionnium-a01-normalized-A/kernel/asterinas/kernel/core/comps/virtio")' in serial,'observed OSTD panic missing')
    for key,snapshot in qemu['artifacts'].items():
        path='normalized-cloud/'+snapshot['path'].split('/normalized-cloud/',1)[1]
        need(len(original[path])==snapshot['size'] and sha(original[path])==snapshot['sha256'],'loaded input snapshot mismatch: '+key)
    rows=[json.loads(line) for line in a('rustc.jsonl').splitlines()];need(len(rows)==369,'rustc call count changed')
    analysis=load('analysis/path-mismatch.json')
    for name in ('aster_core','ostd','component_macro','aster_virtio'):
        selected=[(i+1,r) for i,r in enumerate(rows) if '--crate-name' in r['argv'] and r['argv'][r['argv'].index('--crate-name')+1]==name]
        need(len(selected)==1 and not any('remap-path-prefix' in arg for arg in selected[0][1]['argv']),'selected actual argv mismatch')
        saved=analysis['selected_crate_calls'][name][0]
        need(saved['jsonl_line']==selected[0][0] and saved['argv']==selected[0][1]['argv'],'analysis/actual rustc argv binding mismatch')
    pair_count=0
    for name,data in raw.items():
        if name.startswith('normalized-cloud/A/metadata/') and name.endswith('.binding.json'):
            pair_count+=1;prefix=name[:-len('.binding.json')];record=json.loads(data)
            need(sha(raw[prefix+'.original.json'])==record['original_sha256'] and sha(raw[prefix+'.mapped.json'])==record['mapped_sha256'],'metadata pair hash mismatch')
            old=json.loads(raw[prefix+'.original.json']);mapped=json.loads(raw[prefix+'.mapped.json'])
            for package in ('aster-core','ostd','component-macro','aster-virtio'):
                before=[x for x in old['packages'] if x['name']==package];after=[x for x in mapped['packages'] if x['name']==package]
                need(len(before)==len(after)==1,'metadata selected package ambiguity')
                for field in ('manifest_path','id'):
                    need(before[0][field].replace(policy['real_root'],policy['virtual_root'])==after[0][field],'metadata projection mismatch')
    need(pair_count==6,'metadata pair scope mismatch')
    report=load('report.json')
    need(report['boot']['kernel_boot_passed'] is False and report['boot']['rust_ostd_reached'] is True and report['diagnosis']['new_fix_verified_by_this_phase'] is False,'report overstates old A result')
    restored=None
    if restore is not None:
        destination=Path(restore).absolute();need(destination!=BASE and BASE not in destination.parents,'restore must be outside evidence phase')
        destination.mkdir(parents=False,exist_ok=False)
        for name,data in dict(original,**sources).items():
            target=destination.joinpath(*rel(name).parts);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(data)
            need(target.read_bytes()==data,'restored bytes mismatch')
        restored=str(destination)
    return {'passed':True,'sha256sum_entries':len(expected),'original_files':55,'raw_regular_members':51,'source_controls':86,'source_git_tree_objects':len(trees['objects']),'deduplicated_binary_inputs':3,'binary_original_paths':4,'rustc_calls':369,'metadata_pairs':6,'rust_ostd_reached':True,'kernel_boot_passed':False,'qemu_raw_exit_code':65,'restored_directory':restored,'scope':'Offline evidence and recorded-failure checks only; no Cargo, make, captured controller, host suite or VM executed.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore',metavar='NEW_DIRECTORY',help='reassemble original evidence/profile files and selected Git source controls outside this phase; never execute them')
    args=parser.parse_args()
    try:
        print(json.dumps(verify(args.restore),indent=2))
    except (ValueError,KeyError,OSError,tarfile.TarError,EOFError) as error:
        print('verification failed: '+str(error),file=sys.stderr);sys.exit(1)
