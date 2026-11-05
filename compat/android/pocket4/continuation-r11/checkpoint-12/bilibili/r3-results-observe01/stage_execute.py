#!/usr/bin/env python3
"""Create one new private source/evidence root and run the fixed inspect plan."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import types

ROOT = Path('/home/alex/work/pocket4-bilibili-r3-results-observe-01')
SOURCE = ROOT/'source'
NONCE = '6af0a9c20e8c06d7237d8635c46a166a'
FILES = {'owned_navigation.py','stage_execute.py','make_request.py','INPUTS.json','README.md'}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_packet(raw):
    require(isinstance(raw,bytes) and 0 < len(raw) <= 131072,'EXACT_BOUNDED_PACKET_REQUIRED')
    packet = json.loads(raw)
    require(set(packet) == {'schema','source_manifest_sha256','nonce','files'} and
            packet['schema'] == 1 and packet['nonce'] == NONCE,'FIXED_PACKET_REQUIRED')
    require(isinstance(packet['files'],dict) and set(packet['files']) == FILES|{'SOURCE_PINS.json'},
            'EXACT_SOURCE_SET_REQUIRED')
    encoded = {}
    for name,value in packet['files'].items():
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == name and
                isinstance(value,str),'FIXED_UTF8_SOURCE_REQUIRED')
        encoded[name] = value.encode('utf-8')
        require(0 < len(encoded[name]) <= 65536,'SOURCE_BOUND')
    manifest_raw = encoded['SOURCE_PINS.json']
    require(sha(manifest_raw) == packet['source_manifest_sha256'],'EXTERNAL_MANIFEST_PIN_REQUIRED')
    manifest = json.loads(manifest_raw)
    require(set(manifest['files']) == FILES,'EXACT_MANIFEST_CLOSURE_REQUIRED')
    for name,row in manifest['files'].items():
        require(row == {'bytes':len(encoded[name]),'sha256':sha(encoded[name])},'SOURCE_CHANGED:'+name)
    return packet,encoded


def main(raw=None):
    if raw is None:
        raw = sys.stdin.buffer.read(131073)
    packet,files = checked_packet(raw)
    require(os.getuid() == os.geteuid() == 0,'ROOT_STAGE_REQUIRED')
    require(ROOT.parent.resolve() == ROOT.parent and not os.path.lexists(ROOT),'FRESH_CANONICAL_ROOT_REQUIRED')
    entry = types.ModuleType('owned_bili_inspect_entry'); entry.__file__ = str(SOURCE/'owned_navigation.py')
    exec(compile(files['owned_navigation.py'],entry.__file__,'exec'),entry.__dict__)
    require(entry.ROOT == ROOT and entry.SOURCE == SOURCE and entry.NONCE == NONCE and entry.FILES == FILES,
            'FIXED_ENTRY_SCOPE_REQUIRED')
    entry.fixed_plan()
    require(not os.path.lexists(entry.FLOW),'FRESH_FLOW_REQUIRED')
    prior = entry.load_prior(); ref = prior.references()
    activation = json.loads(ref.read(ref.ACTIVATION,expected=ref.ACTIVATION_SHA))
    epoch = ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'bili_inspect_stage_epoch')
    before = ref.main_guard(activation,epoch)
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    result = {'schema':1,'ok':False,'error':None,'secondary_errors':[],
        'source_manifest_sha256':packet['source_manifest_sha256'],'packet_sha256':sha(raw),
        'nonce':NONCE,'Main_before':before,'automatic_retry':False,
        'raw_ui_tree_private_only':True,'business_success_verified':False,'whole_app_production_ready':False}
    try:
        ref.write_new(ROOT/'once.claim.json',{'nonce':NONCE,
            'source_manifest_sha256':packet['source_manifest_sha256'],
            'packet_sha256':sha(raw),'automatic_retry':False})
        SOURCE.mkdir(mode=0o700)
        for name,value in files.items():
            ref.write_new(SOURCE/name,value,mode=0o444)
        code = entry.execute(packet['source_manifest_sha256'])
        result['coordinator_returncode'] = code
        durable_raw = entry.read(ROOT/'result.json')
        result['coordinator_result'] = {'path':str(ROOT/'result.json'),'bytes':len(durable_raw),'sha256':sha(durable_raw)}
        durable = json.loads(durable_raw)
        require(code == 0 and durable.get('ok') is True and
                durable.get('owned_task_absent_after_cleanup') is True and
                durable.get('scoped_click_and_post_observation_completed') is True and
                durable.get('query_submission_controls_completed') is True and
                durable.get('results_container_content_observed') is True and
                durable.get('business_success_verified') is False,'OWNED_RESULTS_OBSERVE_CLEANUP_NOT_QUALIFIED')
        result['ok'] = True
    except BaseException as error:
        prior.remember(result,'stage_or_coordinator',error)
    finally:
        try:
            result['Main_after'] = ref.main_guard(activation,epoch)
        except BaseException as error:
            prior.remember(result,'stage_final_Main',error)
        try:
            for name,value in files.items():
                entry.read(SOURCE/name,65536,sha(value),len(value))
            result['source_unchanged'] = True
        except BaseException as error:
            prior.remember(result,'stage_final_source',error)
        try:
            pin = ref.write_new(ROOT/'stage-result.json',result)
        except BaseException as error:
            prior.remember(result,'stage_result_write',error); pin = None
        print(json.dumps({'ok':result['ok'],'stage_result':pin,'error':result['error'],
            'secondary_errors':result['secondary_errors'],'raw_UI_tree_exported':False,
            'business_success_verified':False,'whole_app_production_ready':False}),flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
