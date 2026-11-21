#!/usr/bin/env python3
"""Replay Car653, ext4, init thread placement and Settings source over the complete2381 tree.

This is an adapter to the existing authenticated Python capsule verifier, not
an Android execution, deployment or qualification tool.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent/'current-owned-persistent-data-successor-20261120'
PARENT_VERIFIER_SHA='00acaafb64a94cb0ce240428e0dab95cf7a1551d9ac1cf2d478e6afa44cc78d4'
PARENT_INVENTORY='715557d89c6fdfecbaae5fb617f26537769a95e77d01b2538ce0b62606831799'
PARENT_TREE='00c99f0f89fef255d6e8e818769f687f80c1af86'


def checked_verifier(path,expected):
    need_path=path.resolve()==path
    if not need_path: raise RuntimeError('canonical original verifier required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    identity=lambda m:(m.st_dev,m.st_ino,m.st_mode,m.st_uid,m.st_gid,m.st_nlink,m.st_size,m.st_mtime_ns,m.st_ctime_ns)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=65536:
            raise RuntimeError('bounded original verifier required')
        with os.fdopen(os.dup(fd),'rb') as stream: raw=stream.read(before.st_size+1)
        if identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(path.lstat()) or len(raw)!=before.st_size:
            raise RuntimeError('original verifier changed during read')
        if expected is not None and hashlib.sha256(raw).hexdigest()!=expected:
            raise RuntimeError('original verifier hash differs')
        return raw
    finally: os.close(fd)


def bootstrap():
    path=PARENT/'source_verify.py';raw=checked_verifier(path,PARENT_VERIFIER_SHA)
    spec=importlib.util.spec_from_file_location('native_predecessor_verifier',path)
    value=importlib.util.module_from_spec(spec)
    exec(compile(raw,str(path),'exec'),value.__dict__)
    if checked_verifier(path,PARENT_VERIFIER_SHA)!=raw:
        raise RuntimeError('original verifier changed during import')
    return value


PARENT_SOURCE=bootstrap()
BASE=PARENT_SOURCE.BASE
need=BASE.need
decode=BASE.decode
regular=BASE.regular
digest=BASE.digest
f9=BASE.f9
safe=BASE.safe
source_snapshot=BASE.source_snapshot


def verify_packet(expected_inventory):
    need(re.fullmatch('[0-9a-f]{64}',expected_inventory),'external complete successor inventory required')
    names,dirs=BASE.member_names(HERE)
    identities={name:f9((HERE/name).lstat()) for name in names}
    raw=regular(HERE/'FILES.sha256',65536)
    need(hashlib.sha256(raw).hexdigest()==expected_inventory,'external complete successor pin differs')
    inventory={}
    for line in raw.decode('utf-8','strict').splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  ([^\r\n]+)',line)
        need(match is not None,'exact source inventory row')
        safe(match[2]);need(match[2] not in inventory and match[2]!='FILES.sha256','unique source inventory member')
        inventory[match[2]]=match[1]
    need(names==set(inventory)|{'FILES.sha256'},'complete successor packet membership differs')
    for name,sha in inventory.items():
        need(hashlib.sha256(regular(HERE/name)).hexdigest()==sha,'successor member differs: '+name)
    manifest=decode(regular(HERE/'MANIFEST.json'))
    need(set(manifest)=={'schema','parent','source','changes','additions','required','scope'},'exact successor manifest fields')
    need(manifest['schema']=='p4-car-ext4-and-ignored-syscall-source-successor-v1'
         and manifest['parent']=={'tree':PARENT_TREE,'files':2381,'bytes':45436614,'inventory_sha256':PARENT_INVENTORY}
         and manifest['required']=={'packages':28,'targets':49,'ordinary':1628,'ignored_not_run':31,
            'catalog':1659,'release_binaries':19,'example_binaries':3,'recipe_tests':9,'doc_targets':20}
         and manifest['scope']=={'source_only':True,'runtime_qualified':False,'production_ready':False,
            'Android_actions':0,'old_budget_and_peer_authorization_preserved':True,
            'fresh_current_rust_run_in_this_packet':False,
            'new_cases_source_declared_until_actual_compiled_catalog':True,
            'persistent_data_provider_included':True,'persistent_data_mounted':False,'actual_Main_qualified':False,
            'canonical_sources_adopted':False,'Settings_whole_app_accepted':False,
            'syscall_fixture_declared_ignored':True,'syscall_fixture_execution_authorized':False},'source or full-cohort scope differs')
    need(manifest['scope']['source_only'] is True
         and manifest['scope']['runtime_qualified'] is False and manifest['scope']['production_ready'] is False
         and manifest['scope']['old_budget_and_peer_authorization_preserved'] is True
         and manifest['scope']['fresh_current_rust_run_in_this_packet'] is False
         and manifest['scope']['new_cases_source_declared_until_actual_compiled_catalog'] is True
         and type(manifest['scope']['Android_actions']) is int
         and manifest['scope']['persistent_data_provider_included'] is True
         and manifest['scope']['syscall_fixture_declared_ignored'] is True
         and manifest['scope']['syscall_fixture_execution_authorized'] is False
         and all(manifest['scope'][name] is False for name in ('persistent_data_mounted',
             'actual_Main_qualified','canonical_sources_adopted','Settings_whole_app_accepted')),
         'exact typed source-only scope flags required')
    before=decode(regular(HERE/'PREDECESSOR-SOURCE-ROWS.json'))
    old=BASE.validate_rows(before,2381)
    need(BASE.tree_id(before)==PARENT_TREE and sum(x['bytes'] for x in before)==45436614,'complete actual2381 source parent required')
    changes=manifest['changes']; additions=manifest['additions']
    need(type(changes) is list and type(additions) is list and changes and additions,'explicit nonempty source changes required')
    result=dict(old); patches={}; added={}
    for change in changes:
        need(set(change)=={'path','component','before','after','patch'},'exact changed source fields')
        name=change['path'];safe(name)
        need(name in old and name not in patches and change['before']==old[name]
             and change['after']['path']==name and change['after']['mode']==old[name]['mode'],
             'precise source preimage/mode required')
        BASE.validate_rows([change['after']],1)
        need(change['patch']['path']=='patches/'+name+'.patch','precise single-file source patch path')
        patches[name]=BASE.check(HERE/change['patch']['path'],change['patch'])
        result[name]=change['after']
    for item in additions:
        need(set(item)=={'path','component','after','payload'},'exact added source fields')
        name=item['path'];safe(name)
        need(name not in result and item['after']['path']==name and item['payload']['path']=='additions/'+name,
             'only explicit fresh source additions allowed')
        BASE.validate_rows([item['after']],1)
        data=BASE.check(HERE/item['payload']['path'],item['payload'])
        need(digest(data)=={k:item['after'][k] for k in ('bytes','sha256')}
             and BASE.object_id('blob',data)==item['after']['git_blob'],'exact added source body required')
        added[name]=data;result[name]=item['after']
    need([x['path'] for x in changes]==sorted(patches) and [x['path'] for x in additions]==sorted(added),
         'ordered unique complete source changes')
    after=sorted(result.values(),key=lambda row:row['path'])
    need(after==decode(regular(HERE/'SOURCE-ROWS.json')) and manifest['source']=={
        'tree':BASE.tree_id(after),'files':len(after),'bytes':sum(x['bytes'] for x in after)},'complete successor source rows differ')
    need(BASE.member_names(HERE)==(names,dirs)
         and all(f9((HERE/name).lstat())==identity for name,identity in identities.items()),'successor packet changed during full read')
    return {'manifest':manifest,'before':before,'after':after,'patches':patches,'added':added,
            'packet_snapshot':{'files':identities,'directories':dirs},'inventory_sha256':expected_inventory}


def verify_parent(packet):
    parent=PARENT_SOURCE.verify_packet(PARENT_INVENTORY)
    PARENT_SOURCE.verify_parent(parent)
    need(parent['after']==packet['before'],'authenticated full predecessor source differs')
    return parent


def replay(packet,parent_source,output):
    parent_source=Path(parent_source).absolute()
    before=source_snapshot(parent_source,packet['before'],PARENT_TREE)
    output=BASE.fresh_destination(output,[HERE,PARENT,parent_source])
    changed={}
    for row in packet['manifest']['changes']:
        name=row['path'];old=BASE.check(parent_source/name,row['before'])
        new=BASE.strict_patch(old,packet['patches'][name],name)
        need(digest(new)=={k:row['after'][k] for k in ('bytes','sha256')}
             and BASE.object_id('blob',new)==row['after']['git_blob'],'strict successor patch postimage differs: '+name)
        changed[name]=new
    output.mkdir(mode=0o700)
    for row in packet['after']:
        name=row['path'];data=packet['added'][name] if name in packet['added'] else changed[name] if name in changed else BASE.check(parent_source/name,row)
        destination=output/safe(name);destination.parent.mkdir(parents=True,exist_ok=True)
        need(destination.parent.resolve()==destination.parent,'new complete output parent alias rejected')
        fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            with os.fdopen(os.dup(fd),'wb') as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.fchmod(fd,int(row['mode'],8)&0o777)
        finally: os.close(fd)
    need(source_snapshot(parent_source,packet['before'],PARENT_TREE)==before,'actual predecessor changed during replay')
    return {'parent_snapshot':before,'source_snapshot':source_snapshot(output,packet['after'],packet['manifest']['source']['tree'])}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256',required=True)
    parser.add_argument('--parent-source',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--producer',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    packet=verify_packet(args.inventory_sha256);verify_parent(packet)
    need(bool(args.producer)!=bool(args.parent_source) and bool(args.parent_source)==bool(args.output),
         'one complete verify or fresh replay mode required')
    report={'schema':'p4-native-complete-source-replay-v1','source':packet['manifest']['source'],
            'runtime_qualified':False,'production_ready':False,'Android_actions':0}
    if args.producer:
        report['source_snapshot']=source_snapshot(args.producer,packet['after'],packet['manifest']['source']['tree'])
    else: report.update(replay(packet,args.parent_source,args.output))
    need(verify_packet(args.inventory_sha256)['packet_snapshot']==packet['packet_snapshot'],'source packet changed during complete verification')
    report['state']='COMPLETE_SOURCE_VERIFIED_RUNTIME_PENDING'
    BASE.write_report(args.report,report,[HERE,PARENT,*[p for p in (args.producer,args.parent_source,args.output) if p]])
    print(json.dumps({'state':report['state'],'source':report['source'],'report':str(args.report)},sort_keys=True))


if __name__=='__main__': main()
