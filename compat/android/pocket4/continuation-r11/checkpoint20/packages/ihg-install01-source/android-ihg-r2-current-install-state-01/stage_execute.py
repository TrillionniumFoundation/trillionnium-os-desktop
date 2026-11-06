#!/usr/bin/env python3
"""Exact ihg current-baseline install/state staging with its own target context."""
import hashlib,json,os,stat,sys,types
from pathlib import Path,PurePosixPath
ROOT=Path('/home/alex/work/pocket4-owned-ihg-qa-r2-install-state-01')
SOURCE=ROOT/'source'
NONCE='92b900dd770f1834f96b7dd1a6bfdf6c'
REFERENCE_SHA='fa153c308cc629c16ce2a6b649ebdbb6c38c083cc9b00644df679211ede862f2'
FILES={'install_state.py','ihg_context.py','ihg_transport.py','stage_execute.py',
       'make_request.py','INPUTS.json','README.md','host/source-manifest.json','host-stage-actual.json',
       'check_install_binding.py','references/read_ihg.py','target-artifact-reference.json'}
BASE_ROOT=Path('/home/alex/work/pocket4-current-host-r5-source-01')
R5_MANIFEST='6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e'
def require(value,reason):
    if not value:raise RuntimeError(reason)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def read(path, maximum=1048576, expected=None, size=None):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                0 <= before.st_size <= maximum, 'INPUT_SHAPE_OR_BOUND: ' + str(path))
        chunks = []; count = 0
        while True:
            part = os.read(fd, min(65536, maximum + 1 - count))
            if not part:
                break
            chunks.append(part); count += len(part)
            require(count <= maximum, 'INPUT_GREW: ' + str(path))
        after = os.fstat(fd)
        fields = ('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        require(all(getattr(before, k) == getattr(after, k) for k in fields) and count == before.st_size,
                'INPUT_CHANGED: ' + str(path))
        raw = b''.join(chunks)
        require(expected is None or digest(raw) == expected, 'INPUT_SHA_CHANGED: ' + str(path))
        require(size is None or len(raw) == size, 'INPUT_SIZE_CHANGED: ' + str(path))
        return raw
    finally:
        os.close(fd)

def load_text(source,path,name):
    value=types.ModuleType(name);value.__file__=str(path)
    exec(compile(source,str(path),'exec'),value.__dict__)
    return value
def checked_packet(raw):
    require(isinstance(raw,bytes) and 0<len(raw)<=262144,'BOUNDED_PACKET_REQUIRED')
    packet=json.loads(raw)
    require(set(packet)=={'schema','source_manifest_sha256','nonce','files'} and
            packet['schema']==2 and packet['nonce']==NONCE and
            isinstance(NONCE,str) and len(NONCE)==32 and all(c in '0123456789abcdef' for c in NONCE),
            'EXACT_CURRENT_HOST_INSTALL_PACKET_REQUIRED')
    files=packet['files']
    require(isinstance(files,dict) and set(files)==FILES|{'SOURCE_PINS.json'},'EXACT_SOURCE_FILE_SET_REQUIRED')
    encoded={}
    for name,text in files.items():
        rel=PurePosixPath(name)
        require(not rel.is_absolute() and '..' not in rel.parts and str(rel)==name and isinstance(text,str),
                'SOURCE_NAME_OR_UTF8_CHANGED')
        encoded[name]=text.encode('utf-8')
        require(0<len(encoded[name])<=65536,'SOURCE_SIZE_BOUND')
    manifest_raw=encoded['SOURCE_PINS.json'];manifest=json.loads(manifest_raw)
    require(digest(manifest_raw)==packet['source_manifest_sha256'] and manifest.get('schema')==2 and
            manifest.get('host_recorder_manifest_sha256')==R5_MANIFEST and
            set(manifest['files'])==FILES,'EXTERNAL_CURRENT_SOURCE_MANIFEST_REQUIRED')
    for name,row in manifest['files'].items():
        require(row=={'bytes':len(encoded[name]),'sha256':digest(encoded[name])},'SOURCE_PAYLOAD_CHANGED:'+name)
    require(digest(encoded['host/source-manifest.json'])==R5_MANIFEST,'CURRENT_HOST_MANIFEST_CHANGED')
    return packet,encoded
def load_original_host(files):
    raw=read(BASE_ROOT/'source-manifest.json',131072,R5_MANIFEST)
    require(raw==files['host/source-manifest.json'],'EXACT_PUBLISHED_HOST_MANIFEST_REQUIRED')
    manifest=json.loads(raw)
    require(manifest.get('schema')==2 and manifest.get('revision')==5 and
            manifest.get('artifact')=='pocket4-bilibili-current-recorder-held-r5' and len(manifest['files'])==14,
            'EXACT_CURRENT_HOST_SOURCE_SCHEMA_REQUIRED')
    row=manifest['files']['source_contract.py']
    mod=load_text(read(BASE_ROOT/'source_contract.py',131072,row['sha256'],row['bytes']),
                  BASE_ROOT/'source_contract.py','original_current_host_contract')
    original=mod.SourceContract(BASE_ROOT/'source-manifest.json',R5_MANIFEST)
    original.verify()
    row=manifest['files']['current_coordinator.py']
    require(row['sha256']==REFERENCE_SHA,'CURRENT_COORDINATOR_PIN_CHANGED')
    ref=load_text(read(BASE_ROOT/'current_coordinator.py',131072,REFERENCE_SHA,row['bytes']),
                  BASE_ROOT/'current_coordinator.py','current_install_stage_reference')
    return ref,original,manifest
def main(raw=None):
    if raw is None:raw=sys.stdin.buffer.read(262145)
    packet,files=checked_packet(raw)
    require(os.getuid()==os.geteuid()==0,'ROOT_STAGE_REQUIRED')
    require(ROOT.parent.resolve()==ROOT.parent and not os.path.lexists(ROOT),'FRESH_CANONICAL_ROOT_REQUIRED')
    entry=load_text(files['install_state.py'],SOURCE/'install_state.py','current_install_entry_before_stage')
    actual_host=json.loads(files['host-stage-actual.json'])
    require(digest(files['host-stage-actual.json'])==entry.HOST_STAGE_SHA and
            len(files['host-stage-actual.json'])==entry.HOST_STAGE_BYTES,'ACTUAL_HOST_STAGE_RECEIPT_PIN')
    host_manifest=json.loads(files['host/source-manifest.json'])
    ref,original,manifest=load_original_host(files)
    baseline=ref.current_baseline()
    context=load_text(files['ihg_context.py'],SOURCE/'ihg_context.py','current_target_context_controls')
    transport=load_text(files['ihg_transport.py'],SOURCE/'ihg_transport.py','current_target_transport_controls')
    controls_module=load_text(files['check_install_binding.py'],SOURCE/'check_install_binding.py','current_install_pure_controls')
    controls=controls_module.run_controls(entry,actual_host,host_manifest,context,transport,baseline,ref)
    require(controls['all_passed'] is True and controls['count']==33 and
            len(controls['cases'])==33 and all(x['passed'] is True for x in controls['cases']),
            'ACTUAL_CURRENT_APP_CONTEXT_CONTROLS_REQUIRED')
    epoch=ref.module(ref.read(ref.EPOCH_SOURCE,expected=ref.EPOCH_SOURCE_SHA),ref.EPOCH_SOURCE,'current_install_stage_epoch')
    before=ref.main_guard(baseline,epoch)
    os.umask(0o077);ROOT.mkdir(mode=0o700)
    result={'schema':2,'ok':False,'source_manifest_sha256':packet['source_manifest_sha256'],
        'packet_sha256':digest(raw),'nonce':NONCE,'Main_before':before,'controls':controls,
        'error':None,'secondary_errors':[],'automatic_retry':False,'UI_actions':0,'audio_actions':0,
        'current_host_manifest_sha256':R5_MANIFEST,'whole_app_production_ready':False}
    def remember(phase,error):
        value={'phase':phase,'type':type(error).__name__,'message':str(error)}
        if result['error'] is None:result['error']=value
        else:result['secondary_errors'].append(value)
        result['ok']=False
    try:
        ref.write_new(ROOT/'once.claim.json',{'nonce':NONCE,'source_manifest_sha256':packet['source_manifest_sha256'],
                                            'packet_sha256':digest(raw),'automatic_retry':False})
        SOURCE.mkdir(mode=0o700)
        for name,value in files.items():
            path=SOURCE/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            ref.write_new(path,value,mode=0o444)
        result['shared_current_host_source_verified']=True
        result['Bili_Flow_or_MainBinding_instantiated']=False
        entry=load_text(files['install_state.py'],SOURCE/'install_state.py','qa_install_current_actual_entry')
        code=entry.execute(packet['source_manifest_sha256'])
        result['coordinator_returncode']=code
        durable_raw=ref.read(ROOT/'result.json')
        result['coordinator_result']={'path':str(ROOT/'result.json'),'bytes':len(durable_raw),'sha256':digest(durable_raw)}
        require(code==0 and json.loads(durable_raw).get('ok') is True,'ACTUAL_INSTALL_STATE_NOT_QUALIFIED')
        result['ok']=True
    except BaseException as error:remember('stage_or_coordinator',error)
    finally:
        try:result['Main_after']=ref.main_guard(baseline,epoch)
        except BaseException as error:remember('stage_final_Main',error)
        try:
            for name,value in files.items():ref.read(SOURCE/name,expected=digest(value))
            original.verify();result['source_unchanged']=True
        except BaseException as error:remember('stage_final_source',error)
        try:pin=ref.write_new(ROOT/'stage-result.json',result)
        except BaseException as error:remember('stage_result_write',error);pin=None
        print(json.dumps({'ok':result['ok'],'stage_result':pin,'error':result['error'],
            'secondary_errors':result['secondary_errors'],'UI_actions':0,'audio_actions':0,
            'whole_app_production_ready':False}),flush=True)
    return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
