#!/usr/bin/env python3
"""Create one fixed private metadata source root; no retry or UI entry."""
import hashlib
import json
import os
from pathlib import Path
import types

ROOT=Path('/home/alex/work/pocket4-12306-artifact-launcher-readonly-01')
SOURCE=ROOT/'source/read_12306.py'
NONCE='a08bcaaa2480f0aafcdaa0d5ac6c315a'
REFERENCE=Path('/home/alex/work/pocket4-owned-bili-qa-r5-install-state-03/source/references/readonly_r3_coordinator.py')
REFERENCE_SHA='e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd'


def main(packet,source_sha256):
    # The exact request independently pins both this stage and all stdin bytes.
    assert type(packet) is dict and set(packet)=={'schema','nonce','source'}
    assert packet['schema']==1 and packet['nonce']==NONCE and type(packet['source']) is str
    raw=packet['source'].encode('utf-8')
    assert 0<len(raw)<=32768 and hashlib.sha256(raw).hexdigest()==source_sha256
    assert os.getuid()==os.geteuid()==0
    assert ROOT.parent.resolve()==ROOT.parent and not os.path.lexists(ROOT)
    entry=types.ModuleType('ticket12306_metadata_fixed_entry');entry.__file__=str(SOURCE)
    exec(compile(raw,str(SOURCE),'exec'),entry.__dict__)
    assert entry.ROOT==ROOT and entry.SOURCE_PATH==SOURCE and entry.NONCE==NONCE
    ref=entry.load(REFERENCE,REFERENCE_SHA,'ticket12306_stage_main_reference')
    activation=json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
    epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),
                     ref.EPOCH_SOURCE,'ticket12306_stage_epoch')
    before=ref.main_guard(activation,epoch)
    os.umask(0o077);ROOT.mkdir(mode=0o700)
    result={'schema':1,'ok':False,'nonce':NONCE,'package':entry.PACKAGE,
            'source_sha256':source_sha256,'Main_before':before,'error':None,
            'secondary_errors':[],'automatic_retry':False,'Android_UI_actions':0,
            'App_launches':0,'instrumentation_calls':0,'whole_app_production_ready':False}
    def remember(phase,error):
        row={'phase':phase,'type':type(error).__name__,'message':str(error)}
        if result['error'] is None:result['error']=row
        else:result['secondary_errors'].append(row)
        result['ok']=False
    try:
        ref.write_new(ROOT/'stage-claim.json',{'nonce':NONCE,'source_sha256':source_sha256,
                      'automatic_retry':False})
        SOURCE.parent.mkdir(mode=0o700)
        ref.write_new(SOURCE,raw,mode=0o444)
        rc=entry.execute(source_sha256)
        result['worker_returncode']=rc
        durable=ref.read(ROOT/'result.json',98304)
        result['worker_result']={'path':str(ROOT/'result.json'),'bytes':len(durable),
                                'sha256':hashlib.sha256(durable).hexdigest()}
        observed=json.loads(durable)
        assert observed['nonce']==NONCE and observed['package']==entry.PACKAGE
        assert observed['source_sha256']==source_sha256
        assert rc==0 and observed.get('ok') is True,'TICKET12306_METADATA_READ_NOT_QUALIFIED'
        result['ok']=True
    except BaseException as error:remember('stage_or_metadata_read',error)
    finally:
        try:
            result['Main_after']=ref.main_guard(activation,epoch)
            assert result['Main_after']==before,'STAGE_MAIN_CHANGED'
        except BaseException as error:remember('stage_final_Main',error)
        try:
            ref.read(SOURCE,32768,source_sha256)
            result['source_unchanged']=True
        except BaseException as error:remember('stage_final_source',error)
        try:pin=ref.write_new(ROOT/'stage-result.json',result)
        except BaseException as error:remember('stage_result_write',error);pin=None
        print(json.dumps({'stage_result':pin,'stage':result},ensure_ascii=False,
                         sort_keys=True,separators=(',',':')),flush=True)
    return 0 if result['ok'] else 1
