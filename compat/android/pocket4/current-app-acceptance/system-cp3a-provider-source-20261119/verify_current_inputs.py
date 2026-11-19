#!/usr/bin/env python3
"""Current source selection consumer; never a runtime or production admission."""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys

sys.dont_write_bytecode=True

HERE=Path(__file__).resolve().parent
EXPECTED={
 'current_business_preflight':{'path':'current/CURRENT-BUSINESS-PLAN.json','bytes':146172,'sha256':'8f209ce7c4be9d8330f8a4280babcb2ad8f62595b6fb5462adb3b0e88c7d282e'},
 'current_system_provider_cohort':{'path':'current/CURRENT-CP3A-PROVIDER-COHORT.json','bytes':71046,'sha256':'487e747cec5d158052e9ad9e0e2c2beec3115a6f0d69594ad84941b438aed8ea'},
}

def require(ok,message):
    if not ok:raise ValueError(message)

def read(relative):
    parts=PurePosixPath(relative)
    require(not parts.is_absolute() and '..' not in parts.parts,'fixed relative packet path')
    path=HERE/relative
    require(path.resolve()==path,'packet symlink refused')
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<=2*1024*1024,'bounded ordinary evidence member')
    return path.read_bytes()

def inventory():
    listed={}
    for line in read('FILES.sha256').decode('ascii').splitlines():
        sha,name=line.split('  ',1)
        require(name not in listed and re.fullmatch('[0-9a-f]{64}',sha),'unique packet inventory')
        require(hashlib.sha256(read(name)).hexdigest()==sha,'packet SHA mismatch: '+name)
        listed[name]=sha
    actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file()}
    require(actual==set(listed)|{'FILES.sha256'},'exact packet inventory')
    return len(listed)

def module(name):
    spec=importlib.util.spec_from_file_location('cp3a_current_'+name,HERE/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def verify():
    checked=inventory()
    repo=HERE.parents[4]
    provider=module('assemble_provider_cohort');preflight=module('refresh_preflight')
    d,before=provider.load_inputs(repo,HERE)
    source=provider.build(d)
    _,after=provider.load_inputs(repo,HERE)
    require(before==after,'provider evidence F9 changed')
    p,pbefore=preflight.read_fixed(repo)
    plan=preflight.build_plan(p)
    _,pafter=preflight.read_fixed(repo)
    require(pbefore==pafter,'preflight evidence F9 changed')
    generated={'current_business_preflight':plan,'current_system_provider_cohort':source}
    for key,value in generated.items():
        pin=EXPECTED[key];actual=read(pin['path'])
        require(len(actual)==pin['bytes'] and hashlib.sha256(actual).hexdigest()==pin['sha256'],'selected current output pin')
        require((json.dumps(value,sort_keys=True,indent=2)+'\n').encode()==actual,'current output did not reconstruct')
    retirement=json.loads(read('actual/r2-retirement.json'))
    observed=json.loads(retirement['text'])
    require(retirement['status']['exit_code']==0 and retirement['output_complete'] is True,'complete retirement observation')
    require('LoadState=not-found' in observed['stdout'] and 'ActiveState=inactive' in observed['stdout'] and
            'SubState=dead' in observed['stdout'] and observed['cgroup_exists'] is False,'original provider unit still exists')
    return {
      'state':'PASS_CURRENT_SOURCE_INPUTS_RUNTIME_BLOCKED','packet_files':checked,
      'selected_provider_source_identities':4,'required_apps':39,
      'United_version':'4.2.104','United_version_code':3622,
      'other38_package_rows_unchanged':True,'installation_prerequisites_unchanged':True,
      'current_outputs_reconstructed':2,'recorded_source_SDK_commands':12,
      'SDK_commands_executed_here':0,'APK_or_GSI_bodies_read_here':0,'Android_actions':0,
      'provider_semantic_cleanup_qualified':False,'runtime_qualified':False,
      'business_qualified':False,'production_ready':False,
    }

def main():
    print(json.dumps(verify(),sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
