#!/usr/bin/env python3
"""Bind every old runner gate to the complete owned-unit and canonical source."""
import ast
import hashlib
import importlib.util
import os
import stat
from pathlib import Path

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent/'current-owned-persistent-data-successor-20261120'
PARENT_VERIFIER_SHA='76d11d500655f0ae2f6f58ce82e226ce17f43d280867bde606523236843637d9'
PARENT_RUNNER_SHA='7d7e605c7194adc7383e2e7c4b659240547e0ff1c5c92adaf50ca4a60151855f'
PARENT_INVENTORY='715557d89c6fdfecbaae5fb617f26537769a95e77d01b2538ce0b62606831799'


def load(name,path,sha=None):
    if path.resolve()!=path: raise RuntimeError('canonical original verifier required')
    identity=lambda m:(m.st_dev,m.st_ino,m.st_mode,m.st_uid,m.st_gid,m.st_nlink,m.st_size,m.st_mtime_ns,m.st_ctime_ns)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=65536:
            raise RuntimeError('bounded original verifier required')
        with os.fdopen(os.dup(fd),'rb') as stream: raw=stream.read(before.st_size+1)
        if identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(path.lstat()) or len(raw)!=before.st_size:
            raise RuntimeError('original verifier changed during read')
        if sha is not None and hashlib.sha256(raw).hexdigest()!=sha:
            raise RuntimeError('authenticated original verifier changed')
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec)
        exec(compile(raw,str(path),'exec'),module.__dict__)
        if identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(path.lstat()):
            raise RuntimeError('verifier changed during import')
        return module
    finally: os.close(fd)


PARENT_SOURCE=load('native_parent_cohort',PARENT/'verify.py',PARENT_VERIFIER_SHA)
SOURCE=load('native_complete_source',HERE/'source_verify.py')
BASE=PARENT_SOURCE.BASE
OVERLAY=PARENT_SOURCE.OVERLAY
decode=PARENT_SOURCE.decode
digest=PARENT_SOURCE.digest
f9=PARENT_SOURCE.f9
need=PARENT_SOURCE.need
regular=PARENT_SOURCE.regular
safe=PARENT_SOURCE.safe
source_snapshot=PARENT_SOURCE.source_snapshot
successful_cargo_stream=PARENT_SOURCE.successful_cargo_stream
test_terminal=PARENT_SOURCE.test_terminal
_manifest=decode(regular(HERE/'MANIFEST.json'))
HEAD_TREE=_manifest['source']['tree']
HEAD_COMMIT=None
PARENT_COMMIT=None
SOURCE_FILES=_manifest['source']['files']
SOURCE_BYTES=_manifest['source']['bytes']


def fresh_destination(path,protected):
    return PARENT_SOURCE.fresh_destination(path,[*protected,PARENT,HERE])


def write_report(path,value,protected):
    return PARENT_SOURCE.write_report(path,value,[*protected,PARENT,HERE])


def complete_catalog(parent,additions):
    need(type(parent) is list and len(parent)==49,'all49 original test targets required')
    mapped={}
    for row in parent:
        need(set(row)=={'package','target','all','ignored'},'exact original catalog fields')
        key=(row['package'],row['target'])
        need(key not in mapped and row['all']==sorted(set(row['all']))
             and row['ignored']==sorted(set(row['ignored'])) and set(row['ignored'])<=set(row['all']),
             'complete original unique catalog')
        mapped[key]=dict(row,all=list(row['all']),ignored=list(row['ignored']))
    new=set()
    for row in additions:
        need(set(row)=={'component','package','target','tests'},'exact new source test fields')
        key=(row['package'],row['target'])
        need(key in mapped and row['tests']==sorted(set(row['tests'])),'explicit existing target and new names')
        for name in row['tests']:
            need(name not in mapped[key]['all'] and (key,name) not in new,'new cases cannot replace old or duplicate')
            new.add((key,name));mapped[key]['all'].append(name)
    # This exact new test remains ignored. Its metadata cannot authorize execution.
    ignored=decode(regular(HERE/'NEW-IGNORED.json'))
    case='production_namespace::tree::tests::persistent_syscalls::privileged_private_persistent_data_syscall_controls'
    need(ignored=={'package':'droidloom-supervisor','target':'droidloom_supervisor',
         'case':case,'compiled_and_listed_only':True,'execution_authorized_by_this_packet':False}
         and ignored['compiled_and_listed_only'] is True
         and ignored['execution_authorized_by_this_packet'] is False,'only the exact compile-only fixture may be added')
    key=('droidloom-supervisor','droidloom_supervisor')
    need(case not in mapped[key]['all'] and case not in mapped[key]['ignored'],
         'new ignored fixture cannot replace an original ordinary or ignored test')
    original_ignored={(k,name) for k,row in mapped.items() for name in row['ignored']}
    need(len(original_ignored)==30,'all30 original ignored names must remain')
    mapped[key]['all'].append(case)
    mapped[key]['ignored'].append(case)
    mapped[key]['ignored'].sort()
    need({(k,name) for k,row in mapped.items() for name in row['ignored']}==original_ignored|{(key,case)},
         'only the one declared fixture may extend the unchanged original ignored set')
    result=[]
    for key,row in sorted(mapped.items()):
        row['all'].sort();result.append(row)
    need(len(new)==21 and sum(len(row['all']) for row in result)==1664
         and sum(len(row['ignored']) for row in result)==31,'complete1633 ordinary and31 listed-only ignored tests required')
    return result


def verify_capsule(expected_inventory):
    packet=SOURCE.verify_packet(expected_inventory)
    SOURCE.verify_parent(packet)
    parent=PARENT_SOURCE.verify_capsule(PARENT_INVENTORY)
    need(parent['rows']==packet['before'],'the complete audited2381 parent and test cohort differ')
    for name in ('EXPECTED-TARGETS.json','EXPECTED-BINS.json','EXTRA-TARGETS.json','UPDATER-EXACT64.json','test_runner.py'):
        need(regular(HERE/name)==regular(PARENT/name),'an original target, example or runner control changed: '+name)
    expected=complete_catalog(decode(regular(PARENT/'EXPECTED-CATALOG.json')),decode(regular(HERE/'NEW-TESTS.json')))
    need(decode(regular(HERE/'EXPECTED-CATALOG.json'))==expected,'actual complete declared current test catalog differs')
    parent_runner=regular(PARENT/'run_ci.py')
    need(hashlib.sha256(parent_runner).hexdigest()==PARENT_RUNNER_SHA,'original complete runner body required')
    replay=SOURCE.BASE.strict_patch(parent_runner,regular(HERE/'RUNNER.patch'),'run_ci.py')
    need(replay==regular(HERE/'run_ci.py'),'full runner is not its exact reviewed adapter delta')
    functions=lambda raw:{node.name:ast.dump(node,include_attributes=False) for node in ast.parse(raw).body if isinstance(node,ast.FunctionDef)}
    before=functions(parent_runner);after=functions(replay)
    need(set(before)==set(after) and all(before[name]==after[name] for name in before if name not in ('configuration','main')),
         'an original shared compile, artifact, test, ownership or retirement gate changed')
    module=lambda raw:[ast.dump(node,include_attributes=False) for node in ast.parse(raw).body
                       if not(isinstance(node,ast.FunctionDef) and node.name in ('configuration','main'))]
    need(module(parent_runner)==module(replay),'an original runner import, constant or module entry changed')
    SOURCE.verify_packet(expected_inventory)
    chain={**parent['source_chain'],'parent_ext4_features_source_tree':SOURCE.PARENT_TREE,'ext4_features_source_tree':HEAD_TREE,
           'ext4_features_complete_inventory_sha256':expected_inventory}
    return {'rows':packet['after'],'source_chain':chain,'source_packet_snapshot':packet['packet_snapshot'],
            'inventory_sha256':expected_inventory,'manifest':packet['manifest']}
