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
        digest,name=line.split('  ',1);rel(name);need(re.fullmatch('[0-9a-f]{64}',digest) is not None and name not in expected,'bad checksum record');expected[name]=digest
    need({str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p!=BASE/'SHA256SUMS'}==set(expected),'checksum inventory mismatch')
    for name,digest in expected.items():need(sha(read(name))==digest,'checksum mismatch: '+name)
    raw=archive(load('raw.manifest.json'),'raw');originals=dict(raw);art=load('artifacts/manifest.json');payloads={}
    for row in art['artifacts']:
        data=gzip.decompress(container(row,row['kind']));need(len(data)==row['original_bytes'] and sha(data)==row['original_sha256'],'input payload mismatch');payloads[row['original_sha256']]=data
    need(len(payloads)==3 and len(art['original_paths'])==6,'binary input scope mismatch')
    for name,row in art['original_paths'].items():
        data=payloads[row['artifact']];check(data,row,name);need(name not in originals,'duplicate input path');originals[name]=data
    capture=load('capture.json');report=load('report.json');need(set(originals)=={r['path'] for r in capture['files']} and len(originals)==len(capture['files'])==41,'original scope mismatch')
    for row in capture['files']:check(originals[row['path']],row,row['path']);need(row['read_stable'] is True,'unstable input read')
    for row in load('readable/manifest.json')['copies']:
        data=read(row['path']);check(data,row,row['path']);need(data==originals[row['original_path']],'readable copy changed')
    sm=load('source/members.json');sources=archive(sm,'source/controls.tar.gz',source=True)
    need(len(sources)==80,'source-control scope mismatch')
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
    need(binding['producer_commit']=='d879a9d2ffae8d0eb0df441370da54f9e3a38431' and binding['producer_complete_tree']=='a2baa0d707b8af80ae0e7d9f09b6e08379667bc2','wrong producer')

    need(not any(path.startswith('source/support/build/repro/') for path in sources),'unused repro controls included')
    lock=json.loads(sources['source/support/upstream-lock.json'])['kernel'];need(lock['commit']=='c4b7ed575b7b32773475b194d2ad41fb6d03765b' and lock['tree']=='96605cf64aeae2d34f29b97e85eff9315fe10a8e' and lock['toolchain']=='nightly-2026-07-21' and lock['reuse']=='full_kernel_derived','fixed source pins changed');need(sources['source/README.md']==b'','root README not empty in producer')
    root='normal-cloud-final/';a=lambda name:originals[root+name];names=['worktree','source-verification','target-absence','fresh-make-kernel','freeze-first-produced-kernel','make-run-kernel','boot-live-recheck','post-source-verification','worktree-status','installed-components','installed-targets'];commands=json.loads(a('controller-N1/commands.json'))
    need([(r['name'],r['returncode']) for r in commands]==[(n,0) for n in names],'eleven commands did not all pass in order');need(commands[0]['argv'][-1]==binding['producer_commit'],'initial producer mismatch')
    for command in commands:
        name='normal-cloud-final/'+command['log'].split('/normal-cloud-final/',1)[1];need(len(originals[name])==command['log_size'] and sha(originals[name])==command['log_sha256'],'command log mismatch');need(command['selected_environment']['RUSTUP_TOOLCHAIN']=='nightly-2026-07-21' and command['selected_environment']['CARGO_BUILD_JOBS']=='2','unexpected selected ordinary environment')
    need(commands[3]['argv']==['bash','support/build/kernel.sh','kernel'] and commands[5]['argv']==['bash','support/build/kernel.sh','run_kernel'],'not ordinary kernel target entrypoints')
    source_before=a('controller-N1/source-verification.log');source_after=a('controller-N1/post-source-verification.log');need(source_before==source_after==a('kernel-build/source-inputs.json')==a('kernel-boot/source-inputs.json'),'actual source pre/post receipts differ');source_result=json.loads(source_before);need(source_result['passed'] is True and source_result['checked_files']==118 and source_result['errors']==[],'actual source verifier did not pass');need(a('controller-N1/worktree-status.log')==b'','postrun source worktree dirty')
    absence=json.loads(a('controller-N1/target-absence.log'));target='/tmp/trillionnium-a01-final-normal/kernel/asterinas/target';need(absence=={'target':target,'absent_before_first_build':True},'cold target precondition missing');need(commands[2]['selected_environment']['CARGO_TARGET_DIR']==target,'cold target environment mismatch')
    controller=originals['run-normal-cloud-final.py'];need(sha(controller)==report['controller_sha256']=='3c4e1f2d6e70ec4211cebc80e456b0048aad16a7893db09a7a10c992ada5254b','actual controller identity changed')
    import ast
    tree=ast.parse(controller);cleared=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='key':
            try:keys=ast.literal_eval(node.iter)
            except (ValueError,TypeError):continue
            if all(isinstance(k,str) for k in keys):
                calls=[n for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='env' and n.func.attr=='pop']
                if calls:cleared.update(keys)
    required_clear={'CARGO_INCREMENTAL','ASTER_BUILD_TIMESTAMP','SOURCE_DATE_EPOCH','OSDK_BUILD_USERNAME','OSDK_BUILD_HOSTNAME','CARGO_ENCODED_RUSTFLAGS','CARGO_TARGET_DIR','RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','A01_KERNEL_WORKER','A01_REPRO_POLICY'};need(required_clear<=cleared,'ordinary controller did not explicitly clear profile/wrapper/timestamp keys')
    import shlex
    compile_counts={}
    for stage,action,logname,countkey in [('kernel-build','kernel','kernel.log','cold_kernel'),('kernel-boot','run_kernel','run_kernel.log','warm_boot')]:
        env=a(stage+'/environment.log').decode().splitlines();required_env=['CARGO_BUILD_JOBS=2','RUSTFLAGS=<unset>','CARGO_ENCODED_RUSTFLAGS=<unset>','ASTER_BUILD_TIMESTAMP=<unset>','CARGO_TARGET_DIR='+target,binding['producer_commit'],'commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48'];need(all(env.count(line)==1 for line in required_env),'actual ordinary child environment differs')
        argv=shlex.split(a(stage+'/command.sh').decode());need(argv[:8]==['make','-C','/tmp/trillionnium-a01-final-normal/kernel/asterinas','-f','Makefile','-f','/tmp/trillionnium-a01-final-normal/support/build/minimal.mk',action],'recorded actual make target differs');need(all(x in argv for x in ['TARGET_ARCH=x86_64','SMP=1','MEM=512M','ENABLE_KVM=0','BOOT_PROTOCOL=multiboot','INITRAMFS=on','AUTO_TEST=none']),'actual make boot profile differs')
        for name in ['make-exit-code.txt','run-exit-code.txt','manifest-cleanup-exit-code.txt','log-exit-code.txt']:need(int(a(stage+'/'+name))==0,'nonzero original make/cleanup/log receipt')
        cleanup=json.loads(a(stage+'/manifest-cleanup.json'));need(cleanup['passed'] is True and cleanup['outcome']=='owned_removed' and cleanup['helper_sha256']==sha(sources['source/support/build/cleanup-manifest.py']),'owned manifest cleanup mismatch')
        compile_counts[countkey]=len(re.findall(rb'^\s*Compiling\s',a(stage+'/'+logname),re.M))
    need(compile_counts==report['compile_lines']=={'cold_kernel':279,'warm_boot':0},'cold/warm compile accounting differs')
    first=json.loads(a('controller-N1/freeze-first-produced-kernel.log'));firstbytes=a('first-build-kernel.elf');need(first['source']==target+'/osdk/asterinas/asterinas-osdk-bin.elf' and first['copy']=='/workspace/scratch/ae1a8cf05419/normal-cloud-final/first-build-kernel.elf' and first['size']==len(firstbytes)==8258112 and first['sha256']==sha(firstbytes)=='c49ad7da1c76c1f559d065ac3f8cbcbad407242dda54f1ed00028f02d5c2413d','first cold build ELF freeze mismatch');need(first['source_stat']['st_size']==len(firstbytes),'first kernel stat size differs');need(first==report['first_kernel_elf'],'report first-kernel receipt differs')
    q=json.loads(a('kernel-boot/qemu.json'));need(q['raw_exit_code']==q['recorder_exit_code']==33 and q['timed_out'] is False and q['stage']=='complete','actual QEMU did not pass');loaded={}
    for option,row in q['artifacts'].items():
        name='normal-cloud-final/'+row['path'].split('/normal-cloud-final/',1)[1];data=originals[name];need(len(data)==row['size'] and sha(data)==row['sha256'],'boot snapshot changed');need(q['argv'][q['argv'].index(option)+1]==row['path'],'QEMU did not execute preserved snapshot path');loaded[option]=data
    need(firstbytes==loaded['-kernel'],'first cold-built kernel bytes differ from subsequently booted kernel')
    need(a('kernel-build/initramfs.cpio.gz')==a('kernel-boot/initramfs.cpio.gz')==loaded['-initrd'],'initramfs byte identities differ')
    for option,value in [('-machine','q35'),('-accel','tcg'),('-cpu','max'),('-smp','1'),('-m','512M')]:need(q['argv'][q['argv'].index(option)+1]==value,'QEMU profile differs: '+option)
    import struct
    kernel=loaded['-kernel'];need(kernel[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<HH',kernel,16)==(2,3),'not OSDK ELF64/EM_386 compatible boot ELF');need(kernel[:8192].find(struct.pack('<I',0x1badb002))>=0,'missing Multiboot header')
    serial=a('kernel-boot/serial.log');need(len(serial)==q['serial_size'] and sha(serial)==q['serial_sha256'],'serial identity mismatch');clean=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)','',serial.decode(errors='replace'));markers=['OSTD initialized. Preparing components.','TRILLIONNIUM_A01_INIT_BEGIN','TRILLIONNIUM_A01_CPU_COUNT=1','Successfully booted.','TRILLIONNIUM_A01_BOOT_OK'];need(all(m in clean for m in markers),'actual guest acceptance marker missing');fatal=['panicked at','An uncaught panic occurred:','Uncaught panic:','unknown panic payload! (fatal panic handling error','Non-resettable panic!','The panic handler panicked','Panicked in `PanicGuard`, aborting the system'];need(not any(m in clean for m in fatal),'actual serial panic')
    need(a('controller-N1/boot-live-recheck.log')==b'PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)\n','actual live artifacts check missing')
    need(report['cold_make_kernel_passed'] is True and report['subsequent_make_run_kernel_passed'] is True and report['cold_target_absent_before_first_build'] is True and report['kernel_boot_passed'] is True and report['first_and_boot_kernel_complete_bytes_equal'] is True,'ordinary success report differs')
    need(all(report[key] is False for key in ['profile_opt_in','path_projection_claimed','cross_path_comparison_claimed','cross_host_claimed','immutable_host_claimed','all_project_blockers_closed']),'ordinary scope widened');need(not any('/target/' in name for name in originals),'original target files must not be packaged')
    restored=None
    if restore is not None:
        destination=Path(restore).absolute();need(destination!=BASE and BASE not in destination.parents,'restore must be outside phase');destination.mkdir(parents=False,exist_ok=False)
        for name,data in dict(originals,**sources).items():
            path=destination.joinpath(*rel(name).parts);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(data)
            need(path.read_bytes()==data,'restored byte mismatch')
        restored=str(destination)
    return {'passed':True,'sha256sum_entries':len(expected),'original_files':len(originals),'raw_members':len(raw),'source_controls':len(sources),'source_git_tree_objects':len(trees['objects']),'unique_binary_inputs':len(payloads),'logical_binary_paths':len(art['original_paths']),'original_controller_commands':11,'cold_make_kernel_exit':0,'warm_make_run_kernel_exit':0,'compile_lines':compile_counts,'first_and_boot_kernel_complete_bytes_equal':True,'kernel_sha256':sha(kernel),'kernel_bytes':len(kernel),'raw_qemu_exit':33,'profile_opt_in':False,'cross_host_claimed':False,'immutable_host_claimed':False,'restored_directory':restored,'scope':'Offline retained ordinary pipeline evidence only; no original source/target access, compiler, live check or guest execution.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--restore',metavar='NEW_DIRECTORY');args=parser.parse_args()
    try:print(json.dumps(verify(args.restore),indent=2))
    except (ValueError,KeyError,OSError,tarfile.TarError,EOFError) as error:print('verification failed: '+str(error),file=sys.stderr);sys.exit(1)
