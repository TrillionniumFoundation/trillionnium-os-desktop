#!/usr/bin/env python3
"""Fixed Amazon05 inspection failure and retirement reader; no UI actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT=Path('/home/alex/work/pocket4-amazon-owned-search-entry-05')
FLOW=Path('/home/alex/work/pocket4-amazon-owned-qa-r1-flow-115093066f53500d1c8f52105e3f2948')
NONCE='115093066f53500d1c8f52105e3f2948'
SOURCE_SHA='de55453c6ecc711cdb85928b894a798fe2c2850822c8b6b6174269f3f2e3265a'
HELPER_UID=10175
COORDINATOR_BYTES=7456
STAGE_BYTES=1827
COORDINATOR_SHA='172f4c4ca7a63b1680ef44774fbabdbb892426bea43748acc9ebff8c177ad281'
STAGE_SHA='1f6a62974cdeef554ebc80e2ddcff9eae14e7c9097103e65f08b4d4b6c710cf6'
PARENT_EXPECTED_OK=False
FILES={
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'cleanup.json':FLOW/'steps/cleanup-01/result.json',
    'launch.json':FLOW/'steps/launch-01/result.json',
    'inspection.json':FLOW/'steps/inspect-01/result.json',
}


def need(value,reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def no_raw_ui(value, path=()):
    if isinstance(value,dict):
        need(not ({'nodes','text','content_desc','raw_tree','raw_ui_tree','screenshot'} & set(value)),
             'RAW_UI_FIELD_FORBIDDEN_IN_SUMMARY_EXPORT')
        for key,item in value.items():
            no_raw_ui(item,path+(key,))
    elif isinstance(value,list):
        for index,item in enumerate(value):
            no_raw_ui(item,path+(str(index),))


class Reader:
    def __init__(self):
        self.started=time.monotonic();self.bytes=0

    def read(self,path,optional=False):
        need(path in FILES.values(),'EXACT_FILE_ALLOWLIST_REQUIRED')
        maximum=32768 if path==FILES['launch.json'] else 262144
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
        try:
            try:
                for name in path.parts[1:-1]:
                    nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
                    os.close(current);current=nxt
                fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
            except FileNotFoundError:
                if optional:
                    return None
                raise
            first=os.fstat(fd)
            need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
                 0<=first.st_size<=maximum,'ROOT_SINGLE_REGULAR_SUMMARY_BOUND')
            chunks=[];size=0
            while True:
                need(time.monotonic()-self.started<8,'READ_DEADLINE')
                part=os.read(fd,min(16384,maximum+1-size))
                if not part:
                    break
                chunks.append(part);size+=len(part);self.bytes+=len(part)
                need(size<=maximum and self.bytes<=2097152,'TOTAL_READ_BOUND')
            last=os.fstat(fd)
            keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
            need(size==first.st_size and all(getattr(first,k)==getattr(last,k) for k in keys),'FILE_CHANGED')
            return b''.join(chunks)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(current)


def fixed_parent_binding(coordinator,stage):
    for value in (coordinator,stage):
        need(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==NONCE,
             'EXACT_FRESH_FLOW_SOURCE_BINDING_REQUIRED')
        need(value.get('ok') is PARENT_EXPECTED_OK and value.get('secondary_errors')==[] and
             value.get('business_success_verified') is False and
             value.get('whole_app_production_ready') is False,'PRESERVE_EXACT_ACTUAL_PARENT_STATUS_WITHOUT_QUALIFICATION')
    need(stage.get('coordinator_result')=={'path':str(FILES['coordinator.json']),'bytes':COORDINATOR_BYTES,
         'sha256':COORDINATOR_SHA},
         'ACTUAL_PARENT_COORDINATOR_CHAIN')
    need(coordinator.get('flow')==str(FLOW) and coordinator.get('package')=='com.amazon.mShop.android.shopping' and
         coordinator.get('uid')==10129 and coordinator.get('helper_package')=='org.droidloom.qa.amazon.r1' and
         coordinator.get('helper_uid')==HELPER_UID and coordinator.get('inspect_worker_requested') is True,
         'EXACT_CURRENT_FAILED_INSPECTION_SCOPE')
    need(coordinator.get('owned_task_absent_after_cleanup') is True,
         'ACTUAL_PARENT_CLEANUP_CLAIM_RETAINED_NOT_YET_INDEPENDENTLY_VERIFIED')
    need(coordinator['Main_before']==coordinator['Main_after']==stage['Main_before']==stage['Main_after'],
         'ACTUAL_PARENT_MAIN_CHAIN')
    return parent_phase_pins(coordinator)


def parent_phase_pins(coordinator):
    retained=coordinator.get('retained_phase_results')
    need(type(retained) is dict and set(retained)=={'launch','inspect','cleanup'},
         'EXACT_THREE_RETAINED_WORKER_PINS_REQUIRED')
    pins={'launch.json':retained['launch'],'inspection.json':retained['inspect'],
          'cleanup.json':retained['cleanup']}
    for name,pin in pins.items():
        maximum=32768 if name=='launch.json' else 262144
        need(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and
             pin.get('path')==str(FILES[name]) and type(pin.get('bytes')) is int and
             0<pin['bytes']<=maximum and type(pin.get('sha256')) is str and
             re.fullmatch('[0-9a-f]{64}',pin['sha256']),
             'EXACT_PARENT_BOUND_PATH_BOUNDED_BYTES_AND_SHA_REQUIRED:'+name)
    need(coordinator.get('cleanup_result')==pins['cleanup.json'],
         'DUPLICATE_PARENT_CLEANUP_PIN_DIFFERS')
    need(coordinator.get('launch_result')==pins['launch.json'],
         'DUPLICATE_PARENT_LAUNCH_PIN_DIFFERS')
    if 'inspection_result' in coordinator:
        need(coordinator['inspection_result']==pins['inspection.json'],
             'DUPLICATE_PARENT_INSPECTION_PIN_DIFFERS')
    return pins


def launch_binding(value):
    need(value.get('phase')=='launch' and value.get('nonce')==NONCE and
         value.get('source_manifest_sha256')==SOURCE_SHA and value.get('package')=='com.amazon.mShop.android.shopping' and
         value.get('uid')==10129 and value.get('helper_package')=='org.droidloom.qa.amazon.r1' and
         value.get('helper_uid')==HELPER_UID, 'EXACT_ORIGINAL_LAUNCH_BODY_SCOPE')


def inspection_binding(value):
    need(value.get('phase')=='inspect' and value.get('nonce')==NONCE and
         value.get('source_manifest_sha256')==SOURCE_SHA and value.get('package')=='com.amazon.mShop.android.shopping' and
         value.get('uid')==10129 and value.get('helper_package')=='org.droidloom.qa.amazon.r1' and
         value.get('helper_uid')==HELPER_UID, 'EXACT_FAILED_OR_COMPLETED_INSPECTION_BODY_SCOPE')


def collect(coordinator_sha,stage_sha):
    need(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    need(type(PARENT_EXPECTED_OK) is bool and
         all(type(n) is int and 0<n<=262144 for n in (COORDINATOR_BYTES,STAGE_BYTES)) and
         all(type(s) is str and re.fullmatch('[0-9a-f]{64}',s) for s in (COORDINATOR_SHA,STAGE_SHA)) and
         (coordinator_sha,stage_sha)==(COORDINATOR_SHA,STAGE_SHA),
         'EXACT_CURRENT_TERMINAL_PINS_REQUIRED')
    reader=Reader();files={};missing=[];observations={};error=None
    bindings={'parent_chain':False,'cleanup_parent_pin':False,'launch_parent_pin':False,
              'launch_scope':False,'inspection_parent_pin':False,'inspection_scope':False}
    def add(name,expected=None,size=None,optional=False):
        raw=reader.read(FILES[name],optional=optional)
        if raw is None:
            missing.append({'name':name,'path':str(FILES[name])});return None
        observations[name]={'path':str(FILES[name]),'bytes':len(raw),'sha256':sha(raw)}
        need(expected is None or sha(raw)==expected,'BOUND_ORIGINAL_SHA_CHANGED:'+name)
        need(size is None or len(raw)==size,'BOUND_ORIGINAL_SIZE_CHANGED:'+name)
        value=json.loads(raw)
        need(type(value) is dict,'FIXED_RECORD_OBJECT_REQUIRED:'+name);no_raw_ui(value)
        files[name]={**observations[name],'text':raw.decode('utf-8','strict')}
        return value
    try:
        c=add('coordinator.json',coordinator_sha,COORDINATOR_BYTES)
        s=add('stage.json',stage_sha,STAGE_BYTES)
        pins=fixed_parent_binding(c,s);bindings['parent_chain']=True
        # Hashes come only from the already externally pinned parent bytes.
        # Preserve retirement first even if a later worker scope/export guard fails.
        pin=pins['cleanup.json']
        add('cleanup.json',pin['sha256'],pin['bytes']);bindings['cleanup_parent_pin']=True
        pin=pins['launch.json']
        launched=add('launch.json',pin['sha256'],pin['bytes']);bindings['launch_parent_pin']=True
        launch_binding(launched);bindings['launch_scope']=True
        pin=pins['inspection.json']
        worker=add('inspection.json',pin['sha256'],pin['bytes']);bindings['inspection_parent_pin']=True
        inspection_binding(worker);bindings['inspection_scope']=True
    except Exception as failure:
        error={'type':type(failure).__name__,'message':str(failure),'errno':getattr(failure,'errno',None)}
    bundle={'schema':1,'scope':'fixed-amazon05-actual-inspection-and-retirement-only',
        'files':files,'missing':missing,'observations':observations,'bindings':bindings,'error':error,
        'collection_complete':error is None,'source_manifest_sha256':SOURCE_SHA,'flow_nonce':NONCE,
        'bytes_read':reader.bytes,'raw_UI_or_commercial_journal_exported':False,
        'Android_or_process_actions':0,'runtime_qualification_asserted':False,
        'permission_or_original_file_changes':0,'independent_external_inspection_hash_available':False,
        'child_hashes_derived_only_from_exact_external_parent_bytes':True,
        'cleanup_or_UI_window_release_claimed_by_reader':False,
        'inspection_worker_required':True,'redundant_inspection_stdout_read':False,'read_is_sequential_not_atomic':True}
    raw=(json.dumps(bundle,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw)<=3145728,'SUMMARY_BUNDLE_BOUND')
    print(raw.decode('utf-8','strict'),end='',flush=True)
    return 0 if error is None else 1


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collect-once',action='store_true')
    p.add_argument('--coordinator-sha256');p.add_argument('--stage-sha256')
    args=p.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','files':{k:str(v) for k,v in FILES.items()},'remote_actions':0}))
        return 0
    return collect(args.coordinator_sha256,args.stage_sha256)


if __name__=='__main__':
    raise SystemExit(main())
