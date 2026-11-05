#!/usr/bin/env python3
"""Freeze a small normal-builder compile only after two actual input receipts exist."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import subprocess

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT='/home/alex/work/pocket4-blueprint-streaming-builder-450-compile-02-20261105'
KEY='pocket4-blueprint-streaming-builder-450-matching-compile-02-20261105'
GO_PATCH_SHA='9df4688903dc7ba07dad4fae54abc21faa2a0abe9f37f72178668d5e6e9ff307'
FIXTURE_SHA='5a928d10fbaabab5a1198c9c4a5abe9281da091abdde923a2e0a500071e8fbc5'
EXPECTED_INPUTS={
    'original-builder-449-manifest.json':('blueprint-streaming-r1/references/original-builder-449-manifest.json','e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017'),
    'expected-builder-450-manifest.json':('blueprint-streaming-r1/builder-delta/expected-builder-450-manifest.json','6834ea57e4d0402bd5c6e6c405728a111af77fb54ea0e0bea407ba9647fa41b4'),
    'normal-projection.patch':('blueprint-streaming-r1/builder-delta/normal-projection.patch','425f3a5bdeafec1f5f7e821cc575597c1075677715341d08a8588c8bd25a4a28'),
    '0009-blueprint-stream-uncached-module-actions.patch':('blueprint-streaming-r1/0009-blueprint-stream-uncached-module-actions.patch',GO_PATCH_SHA),
    'selection-result.json':('builder-streaming-compile-02/references/selection-result.json','185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf'),
    'selected-build.stdout':('builder-streaming-compile-02/references/selected-build.stdout','82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d'),
}

def sha(raw):return hashlib.sha256(raw).hexdigest()

def read(path,maximum=4*1024*1024):
    data=path.read_bytes()
    if not path.is_file() or path.is_symlink() or len(data)>maximum:raise RuntimeError('bounded regular authority input required')
    return data

def write(path,data):
    if isinstance(data,str):data=data.encode()
    with path.open('xb') as stream:stream.write(data)
    return {'bytes':len(data),'sha256':sha(data)}

def freeze(go_path,tool_path,output):
    go_raw=read(go_path);go=json.loads(go_raw)
    tool_raw=read(tool_path);tool=json.loads(tool_raw)
    if not(go['state']=='PASS' and go['patch']['sha256']==GO_PATCH_SHA and go['fixture']['sha256']==FIXTURE_SHA and
           go['whole_output_files_equal']>0 and go['whole_path_total_alloc_saved']>=go['arms']['preimage']['metrics']['output_bytes'] and
           go['owned_resource_gate']['pass'] is True and all(go[k] is True for k in ['source_unchanged_after','tools_unchanged_after','authority_unchanged_after']) and
           not go['cleanup']['forced_cleanup'] and not go['cleanup']['remaining'] and not go['cleanup']['errors']):
        raise RuntimeError('actual complete-package writer gate must pass first')
    if not(tool['complete'] is True and tool['repository_channel']=='1.93.0' and len(tool['tools'])==12 and
           tool['repository_toolchain']['sha256']=='8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46' and
           all(q['returncode']==0 for q in tool['queries'])):
        raise RuntimeError('complete actual repository-toolchain authority required')
    source=(HERE/'compile_builder.py').read_text()
    if sha(source.encode())!='dfe71cc77b5acf87ac28a27d618de288978e270515d1e76c579796622ec159b1':
        raise RuntimeError('reviewed compile02 source differs')
    for digest in [sha(tool_raw),sha(go_raw)]:
        if source.count(digest)!=1:raise RuntimeError('actual receipt differs from fixed controller binding')
    ast.parse(source)
    files={'compile_builder.py':source,'go-control-result.json':go_raw.decode(),'rust193-tools-read02-result.json':tool_raw.decode()}
    for name,(relative,digest) in EXPECTED_INPUTS.items():
        data=read(BASE/relative)
        if sha(data)!=digest:raise RuntimeError('frozen source input differs: '+name)
        files[name]=data.decode()
    pins={name:{'bytes':len(text.encode()),'sha256':sha(text.encode())} for name,text in files.items()}
    stage='''import hashlib,json,os,stat
from pathlib import Path
ROOT=Path(%r)
EXPECTED=%r
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('staged source member set differs')
    for name,text in packet.items():
        raw=text.encode('utf-8')
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('staged source pin mismatch: '+name)
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned root parent aliases non-directory')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    source=ROOT/'control-source';source.mkdir(mode=0o700)
    for name,text in packet.items():
        fd=os.open(source/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode('utf-8'));stream.flush();os.fsync(stream.fileno())
    raw=(json.dumps({'schema':1,'files':EXPECTED,'Main_actions':0,'only_owned_root_written':True},indent=2)+'\\n').encode()
    fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(source/'compile_builder.py'),'--execute-once'],{'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
'''%(ROOT,pins)
    ast.parse(stage)
    entry=stage+'\nPACKET=json.loads('+repr(json.dumps(files,sort_keys=True))+')\nmain(PACKET)\n'
    ast.parse(entry)
    if len(entry.encode())>1024*1024:raise RuntimeError('source packet exceeds runtime stdin limit')
    request={'host':'pocket4','executable':'/usr/bin/python3','args':['-I','-B','-'],'stdin':entry,'cwd':'/',
             'cpu_quota_percent':100,'memory_max_bytes':1073741824,'nice':15,'timeout_seconds':600,'idempotency_key':KEY}
    output.mkdir()
    recorded={}
    for name,text in files.items():recorded[name]=write(output/name,text)
    recorded['stage.py']=write(output/'stage.py',stage)
    recorded['exact-request.json']=write(output/'exact-request.json',json.dumps(request,indent=2)+'\n')
    plan={'schema':1,'state':'FROZEN_NOT_DISPATCHED','source_root':ROOT+'/builder-source','out':ROOT+'/attempt01',
          'original449_manifest_sha256':EXPECTED_INPUTS['original-builder-449-manifest.json'][1],
          'new450_manifest_sha256':EXPECTED_INPUTS['expected-builder-450-manifest.json'][1],
          'source_delta':'one existing Rust file changed, one Blueprint patch added, 448 original files identical',
          'normal_source_projection_journal_used_by_resulting_builder':True,'live_AOSP_modified_by_this_compile':False,
          'Go6_memory_patch_unchanged':True,'candidate05_925_engine_files_unchanged_by_this_job':True,
          'toolchain':'installed repository-selected 1.93.0; actual executable/library/system tool pins before and after',
          'resources':{'CPU_percent':100,'MemoryMax':1073741824,'nice':15,'timeout_seconds':600,'affinity_cpus':1,'reserved_other_logical_cpus_at_least':2},
          'owned_resource_gate':'held invocation cgroup identity, limits, peaks/swap and zero OOM/oom_kill/oom_group_kill deltas',
          'cargo':'offline, locked, jobs1, fresh owned target directory, fixed package/binary',
          'validation':'actual normal ELF --help plus seven existing exact Projection/recovery/CLI tests; source/dependency/tool/ELF before-after',
          'Main_actions':0,'Main_identity_observed':False,'full_engine_build':False,'Android_execution':False,
          'upstream_Blueprint_vet_pass_claimed':False,'whole_app_qualification':False,
          'actual_Go_gate_sha256':sha(go_raw),'actual_tool_authority_sha256':sha(tool_raw),
          'actual_selection_authority_sha256':'185fce9a8eba4c8edb9879da1eef282404e890ec013a8c4c41c61ccbea7023bf',
          'registry_qualification':'45 selected original locked crates; unique existing cache source; full held/checksum pre-post; every actual compiler input bound',
          'full_workspace_metadata_failure_preserved':True,
          'upstream_inputs_local_paths':{'Go':str(go_path),'Rust':str(tool_path)}}
    recorded['PLAN.json']=write(output/'PLAN.json',json.dumps(plan,indent=2)+'\n')
    result=subprocess.run(['/usr/bin/python3','-I','-B',str(output/'compile_builder.py')],capture_output=True,text=True)
    if result.returncode!=0 or json.loads(result.stdout)['mode']!='PLAN' or result.stderr:
        raise RuntimeError('default controller PLAN validation failed')
    recorded['LOCAL_VALIDATION.json']=write(output/'LOCAL_VALIDATION.json',json.dumps({'AST_valid':True,'default_PLAN':json.loads(result.stdout),
                 'remote_dispatch_performed':False,'Rust_compilation_performed':False},indent=2)+'\n')
    manifest=write(output/'SOURCE_PINS.json',json.dumps({'schema':1,'files':recorded,'packet_files':pins,'submitted':False},indent=2)+'\n')
    print(json.dumps({'manifest':manifest,'request':recorded['exact-request.json'],'root':str(output),'stable_key':KEY},indent=2))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--go-result',type=Path)
    parser.add_argument('--tools-result',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.freeze:
        print(json.dumps({'mode':'PLAN','requires_actual_Go_PASS':True,'requires_complete_Rust193_tool_read':True,
                          'remote_actions':0,'normal_builder_450_compile_only':True}))
        return
    if args.go_result is None or args.tools_result is None or args.output is None:
        parser.error('--freeze requires both actual receipt files and a new output directory')
    freeze(args.go_result,args.tools_result,args.output)

if __name__=='__main__':main()
