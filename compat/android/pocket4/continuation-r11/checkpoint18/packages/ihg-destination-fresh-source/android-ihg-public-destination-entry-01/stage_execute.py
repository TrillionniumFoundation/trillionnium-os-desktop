#!/usr/bin/env python3
"""Stage exactly one new IHG task source and execute its reviewed coordinator."""
import hashlib
import json
import os
from pathlib import Path
import types

ROOT=Path('/home/alex/work/pocket4-ihg-public-destination-entry-01')
SOURCE=ROOT/'source'
NONCE='13096774da42081a4029b0015113be8c'
FILES={'owned_inspect.py','ihg_task_context.py','public_destination.py','INPUTS.json'}
REFERENCE=Path('/home/alex/work/pocket4-owned-ihg-qa-r1-install-state-01/source/references/readonly_r3_coordinator.py')
REFERENCE_SHA='e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd'


def main(packet,manifest_sha256):
    assert type(packet) is dict and set(packet)=={'schema','nonce','files'}
    assert packet['schema']==1 and packet['nonce']==NONCE and type(packet['files']) is dict
    assert set(packet['files'])==FILES|{'SOURCE_PINS.json'}
    data={name:content.encode('utf-8') for name,content in packet['files'].items() if type(content) is str}
    assert set(data)==set(packet['files']) and all(0<len(raw)<=65536 for raw in data.values())
    assert sum(map(len,data.values()))<=131072
    assert hashlib.sha256(data['SOURCE_PINS.json']).hexdigest()==manifest_sha256
    manifest=json.loads(data['SOURCE_PINS.json'])
    assert manifest['schema']==1 and set(manifest['files'])==FILES
    for name,pin in manifest['files'].items():
        assert pin=={'bytes':len(data[name]),'sha256':hashlib.sha256(data[name]).hexdigest()}
    assert os.getuid()==os.geteuid()==0
    assert ROOT.parent.resolve()==ROOT.parent and not os.path.lexists(ROOT)
    entry=types.ModuleType('amazon_owned_inspect_entry');entry.__file__=str(SOURCE/'owned_inspect.py')
    exec(compile(data['owned_inspect.py'],entry.__file__,'exec'),entry.__dict__)
    assert entry.ROOT==ROOT and entry.SOURCE==SOURCE and entry.HERE==SOURCE and entry.NONCE==NONCE
    ref=entry.load(REFERENCE,REFERENCE_SHA,'amazon_task_stage_reference')
    activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
    epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'amazon_task_stage_epoch')
    before=ref.main_guard(activation,epoch)
    os.umask(0o077);ROOT.mkdir(mode=0o700)
    result={'schema':1,'ok':False,'nonce':NONCE,'package':entry.PACKAGE,'source_manifest_sha256':manifest_sha256,
        'Main_before':before,'error':None,'secondary_errors':[],'automatic_retry':False,
        'maximum_native_launches':1,'maximum_click_actions':1,'text_actions':0,'screenshots':0,'audio_actions':0,
        'raw_UI_tree_private_only':True,'business_success_verified':False,'whole_app_production_ready':False}
    def remember(phase,error):
        row={'phase':phase,'type':type(error).__name__,'message':str(error)}
        if result['error'] is None:result['error']=row
        else:result['secondary_errors'].append(row)
        result['ok']=False
    try:
        ref.write_new(ROOT/'once.claim.json',{'nonce':NONCE,'source_manifest_sha256':manifest_sha256,'automatic_retry':False})
        SOURCE.mkdir(mode=0o700)
        for name,raw in sorted(data.items()):ref.write_new(SOURCE/name,raw,mode=0o444)
        rc=entry.execute(manifest_sha256);result['coordinator_returncode']=rc
        durable=entry.read(ROOT/'result.json');observed=json.loads(durable)
        result['coordinator_result']={'path':str(ROOT/'result.json'),'bytes':len(durable),'sha256':hashlib.sha256(durable).hexdigest()}
        assert observed['nonce']==NONCE and observed['source_manifest_sha256']==manifest_sha256
        assert observed['package']==entry.PACKAGE and observed['helper_uid']==10196
        assert rc==0 and observed['ok'] is True and observed['error'] is None and observed['secondary_errors']==[]
        assert observed['destination_click_and_observation_completed'] is True and observed['owned_task_absent_after_cleanup'] is True
        assert observed['business_success_verified'] is False and observed['whole_app_production_ready'] is False
        result['ok']=True
    except BaseException as error:remember('stage_or_owned_launch_inspect',error)
    finally:
        try:
            result['Main_after']=ref.main_guard(activation,epoch)
            assert result['Main_after']==before,'STAGE_MAIN_CHANGED'
        except BaseException as error:remember('stage_final_Main',error)
        try:
            for name,raw in data.items():entry.read(SOURCE/name,65536,hashlib.sha256(raw).hexdigest(),len(raw))
            result['source_unchanged']=True
        except BaseException as error:remember('stage_final_source',error)
        try:pin=ref.write_new(ROOT/'stage-result.json',result)
        except BaseException as error:remember('stage_result_write',error);pin=None
        print(json.dumps({'ok':result['ok'],'stage_result':pin,'error':result['error'],
            'secondary_errors':result['secondary_errors'],'whole_app_production_ready':False},sort_keys=True),flush=True)
    return 0 if result['ok'] else 1
