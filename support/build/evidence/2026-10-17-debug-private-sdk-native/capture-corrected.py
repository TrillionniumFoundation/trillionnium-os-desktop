#!/usr/bin/python3
"""Read root-confirmed completed native debug evidence into a private snapshot."""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import stat
import subprocess
import sys

sys.dont_write_bytecode=True
BASE=Path('/workspace/scratch/ae1a8cf05419');REPO=BASE/'trillionnium-os-desktop'
SOURCE='a5af45537dea32039ea172ad0d7e381400c07d95'
def need(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def ident(value):return {key:getattr(value,key) for key in ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns','st_nlink')}
def stable(path):
    before=path.lstat();fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        first=os.fstat(fd);need(stat.S_ISREG(first.st_mode) and ident(before)==ident(first),'capture is not stable regular: '+str(path))
        with os.fdopen(os.dup(fd),'rb') as stream:data=stream.read()
        need(ident(first)==ident(os.fstat(fd))==ident(path.lstat()) and len(data)==first.st_size,'capture changed: '+str(path))
    finally:os.close(fd)
    return data,ident(first)
def dump(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2)+'\n')
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*args])
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root-done-receipt',required=True,type=Path);args=parser.parse_args()
    done_bytes,done_stat=stable(args.root_done_receipt);done=json.loads(done_bytes)
    need(any(type(done.get(key)) is int and done[key]==0 for key in ('observed_exit_code','exit_code','outer_exit_code','returncode')),'root did not confirm actual outer exit0')
    retry=BASE/'native-followup/debug-retry1';failed=BASE/'native-followup/debug'
    commands=json.loads(stable(retry/'controller/commands.json')[0]);names=['source-head-clean','source-inputs','fixed-rustc','actual-debug','post-source-inputs','post-source-head-clean']
    need([(r['name'],r.get('returncode')) for r in commands]==[(name,0) for name in names],'retry six commands did not complete')
    need(commands[0]['argv'][-1]==SOURCE,'retry producer differs')
    result=json.loads(stable(retry/'run/result.json')[0]);need(result['passed'] is True and result['stage']=='complete','actual debug did not pass')
    failure=json.loads(stable(failed/'run/result.json')[0]);need(failure['passed'] is False and failure['stage']=='prepare' and failure['error']=='GDB and nm must be available','first failure scope differs')
    qemu=json.loads(stable(retry/'run/boot/qemu.json')[0]);need(qemu['raw_exit_code']==qemu['recorder_exit_code']==33 and not qemu['timed_out'] and qemu['stage']=='complete','actual detached guest failed')
    snapshot=BASE/'debug-native-review/snapshot';snapshot.mkdir(mode=0o700,exist_ok=False)
    capture=[];names_before={}
    def copy(path,name):
        data,s=stable(path);target=snapshot/'files'/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(data)
        row={'path':name,'source':str(path),'bytes':len(data),'sha256':sha(data),'source_stat':s,'read_stable':True};capture.append(row)
        return data,row
    for directory in (failed,retry):
        paths=sorted(p for p in directory.rglob('*') if p.is_file() or p.is_symlink());names_before[str(directory)]=paths
        for p in paths:copy(p,str(p.relative_to(BASE)))
    extras={'controller/run-native-followup-v1.py':BASE/'round-next/run-native-followup.py','controller/run-native-followup-v2.py':BASE/'round-next/run-native-followup-v2.py','controller/environment-correction.json':BASE/'round-next/debug-environment-correction.json','controller/root-completed-tool.json':args.root_done_receipt,'controller/actual-host.json':BASE/'round-next/host-identity.json','controller/capture.py':Path(__file__).resolve()}
    for name,path in extras.items():copy(path,name)
    # This is the only original compiler target file explicitly allowed here.
    # Preserve it before the root checks out the next regression source.
    entry=json.loads(stable(retry/'run/entry-artifact-binding.json')[0]);symbol=Path(entry['symbol_artifact']['path'])
    expected=Path('/tmp/trillionnium-a01-private-sdk-N2/kernel/asterinas/target/x86_64-unknown-none/release/asterinas-osdk-bin')
    need(symbol==expected,'unexpected original symbol target path')
    data,row=copy(symbol,'observed-symbol/asterinas-osdk-bin')
    need(len(data)==entry['symbol_artifact']['size'] and sha(data)==entry['symbol_artifact']['sha256'],'actual symbol ELF no longer matches debug binding')
    for directory,paths in names_before.items():need(paths==sorted(p for p in Path(directory).rglob('*') if p.is_file() or p.is_symlink()),'completed evidence inventory changed')
    dump(snapshot/'capture.json',{'schema':1,'producer_commit':SOURCE,'files':capture,'original_target_file_scope':'Only the exact successful-debug symbol ELF was opened after root confirmed DONE, and its complete size/hash matched the original binding. No other target files opened.','captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    # Exact producer Git objects are read without consulting the current worktree.
    selected={r['path'] for r in json.loads((REPO/'support/build/evidence/2026-10-17-native-cloud-normal/source/members.json').read_text())['members']}
    selected.update(json.loads((snapshot/'files/native-followup/debug-retry1/run/environment.json').read_text())['source_sha256'])
    for line in git('ls-tree','-r',SOURCE,'--','support/build/debug').decode().splitlines():
        header,path=line.split('\t',1);mode,kind,digest=header.split();need(kind=='blob' and mode in ('100644','100755'),'nonregular debug source');selected.add(path)
    selected.add('kernel/asterinas/osdk/Cargo.toml')
    source_rows=[];path_trees={'':git('rev-parse',SOURCE+'^{tree}').decode().strip()}
    for path in sorted(selected):
        line=git('ls-tree',SOURCE,'--',path).decode().strip();header,actual=line.split('\t',1);mode,kind,digest=header.split();need(actual==path and kind=='blob' and mode in ('100644','100755'),'source path differs')
        raw=git('cat-file','blob',digest);target=snapshot/'source'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        source_rows.append({'path':path,'member':'source/'+path,'mode':int(mode,8)&0o777,'git_mode':mode,'git_blob':digest,'ref':SOURCE,'bytes':len(raw),'sha256':sha(raw)})
        parent=PurePosixPath(path).parent
        for directory in [*reversed(parent.parents),parent]:
            name='' if str(directory)=='.' else str(directory)
            if name and name not in path_trees:path_trees[name]=git('rev-parse',SOURCE+':'+name).decode().strip()
    trees={}
    for digest in set(path_trees.values()):
        raw=git('cat-file','tree',digest);trees[digest]={'raw_base64':base64.b64encode(raw).decode(),'raw_bytes':len(raw),'raw_sha256':sha(raw)}
    dump(snapshot/'source-members.json',{'members':source_rows});dump(snapshot/'tree-objects.json',{'root_tree':path_trees[''],'path_trees':path_trees,'objects':trees})
    dump(snapshot/'source-binding.json',{'producer_commit':SOURCE,'producer_complete_tree':path_trees[''],'derived_kernel_tree':git('rev-parse',SOURCE+':kernel/asterinas').decode().strip(),'commit_object':git('cat-file','commit',SOURCE).decode(),'scope':'Exact selected runtime/debug controls at successful debug producer D, with commit/tree/path/blob membership; not a second kernel import.'})
    for row in capture:
        retained=snapshot/'files'/row['path'];need(retained.stat().st_size==row['bytes'] and sha(retained.read_bytes())==row['sha256'],'retained snapshot changed')
    result={'capture_done':True,'snapshot':str(snapshot),'producer_commit':SOURCE,'original_files':len(capture),'source_controls':len(source_rows),'symbol_bytes':len(data),'symbol_sha256':sha(data),'raw_qemu_exit':33,'passed':True,'only_one_original_target_symbol_captured':True,'root_may_reuse_original_target':True}
    dump(BASE/'debug-native-review/capture-done.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
