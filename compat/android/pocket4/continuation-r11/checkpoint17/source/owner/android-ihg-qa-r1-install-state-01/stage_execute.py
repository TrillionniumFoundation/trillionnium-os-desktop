#!/usr/bin/env python3
"""Exact root-owned staging for one install/state request; no retry path."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import types

ROOT = Path('/home/alex/work/pocket4-owned-ihg-qa-r1-install-state-01')
SOURCE = ROOT/'source'
NONCE = 'b637e01d62293f5e7c909e75d2b36d50'
REFERENCE_SHA = 'e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd'
FILES = {'install_state.py','ihg_context.py','ihg_transport.py','stage_execute.py',
    'make_request.py','INPUTS.json','README.md','references/readonly_r3_coordinator.py',
    'references/read_ihg.py','target-artifact-reference.json'}



def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_text(source, path, name):
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(source,str(path),'exec'),module.__dict__)
    return module


def checked_packet(raw):
    require(isinstance(raw,bytes) and 0 < len(raw) <= 262144,'BOUNDED_PACKET_REQUIRED')
    packet = json.loads(raw)
    require(set(packet) == {'schema','source_manifest_sha256','nonce','files'} and
            packet['schema'] == 1 and packet['nonce'] == NONCE,'EXACT_PACKET_REQUIRED')
    files = packet['files']
    require(isinstance(files,dict) and set(files) == FILES | {'SOURCE_PINS.json'},
            'EXACT_SOURCE_FILE_SET_REQUIRED')
    encoded = {}
    for name,text in files.items():
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == name and isinstance(text,str),
                'SOURCE_NAME_OR_UTF8_CHANGED')
        encoded[name] = text.encode('utf-8')
        require(0 < len(encoded[name]) <= 65536,'SOURCE_SIZE_BOUND')
    manifest_raw = encoded['SOURCE_PINS.json']
    require(digest(manifest_raw) == packet['source_manifest_sha256'],'EXTERNAL_SOURCE_MANIFEST_MISMATCH')
    manifest = json.loads(manifest_raw)
    require(set(manifest['files']) == FILES,'EXACT_MANIFEST_FILE_SET_REQUIRED')
    for name,row in manifest['files'].items():
        require(row == {'bytes':len(encoded[name]),'sha256':digest(encoded[name])},'SOURCE_PAYLOAD_CHANGED:'+name)
    require(digest(encoded['references/readonly_r3_coordinator.py']) == REFERENCE_SHA,'ORIGINAL_COORDINATOR_CHANGED')
    return packet,encoded


def main(raw=None):
    if raw is None:
        raw = sys.stdin.buffer.read(262145)
    packet,files = checked_packet(raw)
    require(os.getuid() == os.geteuid() == 0,'ROOT_STAGE_REQUIRED')
    require(ROOT.parent.resolve() == ROOT.parent and not os.path.lexists(ROOT),'FRESH_CANONICAL_ROOT_REQUIRED')
    ref = load_text(files['references/readonly_r3_coordinator.py'],SOURCE/'references/readonly_r3_coordinator.py',
                    'qa_install_stage_reference')
    activation = json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
    epoch = ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'qa_install_stage_epoch')
    before = ref.main_guard(activation,epoch)
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    result = {'schema':1,'ok':False,'source_manifest_sha256':packet['source_manifest_sha256'],
        'packet_sha256':digest(raw),'nonce':NONCE,'Main_before':before,
        'error':None,'secondary_errors':[],'automatic_retry':False,'UI_actions':0,'audio_actions':0,
        'whole_app_production_ready':False}
    def remember(phase,error):
        value={'phase':phase,'type':type(error).__name__,'message':str(error)}
        if result['error'] is None:
            result['error']=value
        else:
            result['secondary_errors'].append(value)
        result['ok']=False
    try:
        ref.write_new(ROOT/'once.claim.json',{'nonce':NONCE,'source_manifest_sha256':packet['source_manifest_sha256'],
                                            'packet_sha256':digest(raw),'automatic_retry':False})
        SOURCE.mkdir(mode=0o700)
        for name,value in files.items():
            path=SOURCE/name
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            ref.write_new(path,value,mode=0o444)
        entry=load_text(files['install_state.py'],SOURCE/'install_state.py','qa_install_actual_entry')
        code=entry.execute(packet['source_manifest_sha256'])
        result['coordinator_returncode']=code
        durable_raw=ref.read(ROOT/'result.json')
        result['coordinator_result']={'path':str(ROOT/'result.json'),'bytes':len(durable_raw),'sha256':digest(durable_raw)}
        durable=json.loads(durable_raw)
        require(code == 0 and durable.get('ok') is True,'ACTUAL_AMAZON_INSTALL_STATE_NOT_QUALIFIED')
        result['ok']=True
    except BaseException as error:
        remember('stage_or_coordinator',error)
    finally:
        try:
            result['Main_after']=ref.main_guard(activation,epoch)
        except BaseException as error:
            remember('stage_final_Main',error)
        try:
            for name,value in files.items():
                ref.read(SOURCE/name,expected=digest(value))
            result['source_unchanged']=True
        except BaseException as error:
            remember('stage_final_source',error)
        try:
            pin=ref.write_new(ROOT/'stage-result.json',result)
        except BaseException as error:
            remember('stage_result_write',error)
            pin=None
        print(json.dumps({'ok':result['ok'],'stage_result':pin,'error':result['error'],
            'secondary_errors':result['secondary_errors'],'UI_actions':0,'audio_actions':0,
            'whole_app_production_ready':False}),flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
