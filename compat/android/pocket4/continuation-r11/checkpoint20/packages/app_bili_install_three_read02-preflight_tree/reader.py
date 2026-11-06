#!/usr/bin/env python3
"""Fixed read-only export of this owned BILI R9 install and no-automation state."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import zlib

ROOT = Path('/home/alex/work/pocket4-owned-bili-qa-r9-install-state-01')
STEP = Path('/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-d327cfd21d7b59df0c45a68efdd74c98/steps/install-state-r9-01')
NONCE = 'dc55b7c139daf6db8fe94faa170916a9'
PACKAGE = 'org.droidloom.qa.bili.r9'
PROTOCOL = 'pocket4-owned-bili-qa-v9'
PINS = {'coordinator.json': (3917, '4e6d090d00eada5dc1604977491ed88054595f856dd620d12ace55222825fd71'), 'stage.json': (4141, 'b52f8f856e377c38b7a8a64f172e0970f0cd37f4ef7b87fb63a6005a67c8b6cd')}
INSTALL_NONCE = 'd327cfd21d7b59df0c45a68efdd74c98'
SOURCE_SHA = '399cebc279ac8653b943b5c433b248c94dec32062b85b45e9cb6c22fce379a66'
BASE = {
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'worker.json':STEP/'result.json',
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode_state_wire(encoded):
    # This reader only exports the small no-UiAutomation state envelope. Its
    # 64 KiB receipt limit remains stricter than the helper's general UI limit.
    require(isinstance(encoded,bytes) and 0<len(encoded)<=65536,'STATE_BASE64_BOUND')
    compressed=base64.b64decode(encoded,validate=True)
    require(0<len(compressed)<=65536 and base64.b64encode(compressed)==encoded,
            'CANONICAL_STATE_BASE64_REQUIRED')
    decoder=zlib.decompressobj(31)
    wire=decoder.decompress(compressed,65537)
    require(0<len(wire)<=65536 and decoder.eof and not decoder.unconsumed_tail and
            not decoder.unused_data,'ONE_COMPLETE_BOUNDED_STATE_GZIP_REQUIRED')
    return wire


class Reader:
    def __init__(self):
        self.started = time.monotonic()
        self.total = 0
        self.records = {}

    def read(self, path, optional=False):
        require(time.monotonic()-self.started < 8, 'READ_DEADLINE')
        require(path in BASE.values(), 'EXACT_THREE_FILE_ALLOWLIST_REQUIRED')
        directory = os.open('/', os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        fd = None
        try:
            for name in path.parts[1:-1]:
                next_fd = os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=directory)
                os.close(directory); directory=next_fd
            try:
                fd=os.open(path.name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=directory)
            except FileNotFoundError:
                if optional:
                    return None
                raise
            first=os.fstat(fd)
            require(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
                    0<=first.st_size<=65536,'ROOT_SINGLE_REGULAR_BOUNDED_RECEIPT_REQUIRED')
            chunks=[];count=0
            while True:
                require(time.monotonic()-self.started<8,'READ_DEADLINE')
                part=os.read(fd,min(16384,65537-count))
                if not part:
                    break
                chunks.append(part);count+=len(part);self.total+=len(part)
                require(count<=65536 and self.total<=524288,'TOTAL_OR_FILE_BOUND')
            last=os.fstat(fd)
            fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
            require(count==first.st_size and all(getattr(first,k)==getattr(last,k) for k in fields),'RECEIPT_CHANGED')
            return b''.join(chunks)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(directory)

    def add(self, name, path, raw=None):
        require(name not in self.records,'DUPLICATE_EXPORT_NAME')
        if raw is None:
            raw=self.read(path)
        text=raw.decode('utf-8','strict')
        if name in PINS:
            require((len(raw),sha(raw))==PINS[name],'EXTERNAL_TERMINAL_RECEIPT_PIN_CHANGED:'+name)
        self.records[name]={'path':str(path),'bytes':len(raw),'sha256':sha(raw),'text':text}
        return raw


def no_raw_ui(value):
    if isinstance(value,dict):
        require(not ({'nodes','text','content_desc','inspection','raw_tree','raw_ui_tree','screenshot','pixels'} & set(value)),
                'RAW_UI_FIELD_FORBIDDEN_IN_STATE_EXPORT')
        for item in value.values():no_raw_ui(item)
    elif isinstance(value,list):
        for item in value:no_raw_ui(item)


def parent_worker_pin(coordinator,stage,coordinator_pin):
    for value in (coordinator,stage):
        require(value.get('ok') is True and value.get('error') is None and value.get('secondary_errors')==[] and
                value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==INSTALL_NONCE,
                'EXACT_ACTUAL_BILI_R9_PARENT_RECEIPTS_REQUIRED')
    require(coordinator.get('package')==PACKAGE and stage.get('coordinator_result')==coordinator_pin,
            'EXACT_ACTUAL_BILI_R9_PARENT_CHAIN_REQUIRED')
    pin=coordinator.get('worker_result')
    require(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==str(BASE['worker.json']) and
            type(pin['bytes']) is int and 0<pin['bytes']<=65536 and isinstance(pin['sha256'],str) and
            re.fullmatch('[0-9a-f]{64}',pin['sha256']), 'EXACT_PARENT_BOUND_WORKER_PIN_REQUIRED')
    return pin


def state_only(worker,coordinator):
    require(worker.get('package')==PACKAGE and worker.get('state_nonce')==NONCE and
            worker.get('nonce')==INSTALL_NONCE and
            worker.get('runtime_recorder_manifest_sha256')=='6d99374e1580083fd0f30b7f9b3c520306680760c97ad0d5400798fda427fb6e' and
            worker.get('runtime_session_binding_sha256')=='aa6f468fa8e058882e681362aeb7fb4ba5b726d3d34c8dcfdc2b947aa6fb8b7e' and
            worker.get('build',{}).get('source_manifest_sha256')=='4eb11cf497615272c1bef280bbd849de4f983ba4147ea9356356dff076ce9c56' and
            worker.get('UI_actions')==worker.get('audio_actions')==0 and
            worker.get('UiAutomation_connection_requested') is False,'OWNED_NO_UI_WORKER_REQUIRED')
    state=worker.get('state')
    require(isinstance(state,dict),'COMPLETED_OWNED_STATE_RECEIPT_REQUIRED')
    helper=state.get('helper')
    require(isinstance(helper,dict) and helper.get('protocol')==PROTOCOL and helper.get('op')=='state' and
            helper.get('nonce')==NONCE and helper.get('ui_automation_connected') is False and
            helper.get('requires_post_termination_state_check') is False and
            helper.get('window_observation')=={} and helper.get('tree_observations')==[] and
            helper.get('wire_codec')=='gzip-canonical-json-v1' and 'inspection' not in helper,
            'ONLY_NO_AUTOMATION_STATE_CAN_BE_EXPORTED')
    uid=worker.get('owned_package_uid')
    require(type(uid) is int and 10000<=uid<100000 and
            uid not in (10130,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190,10137,10196,10198,10203,10204) and
            helper.get('self_uid')==coordinator.get('owned_package_uid')==uid,'ACTUAL_BILI_R9_HELPER_UID_REQUIRED')
    require(worker.get('ok') is True and worker.get('error') is None and
            worker.get('secondary_errors')==[] and worker.get('install_success_observed') is True and
            worker.get('outcome_unknown') is False and worker.get('package_retained') is True and
            worker.get('installed_before_state')==worker.get('installed_after_state') and
            worker.get('installed_before_state',{}).get('uid')==uid and
            worker.get('installed_before_state',{}).get('apk_sha256')=='e1cad62bba0266e646e7be4ce5250917fbf5df910ac604dddfe0a8aa25ac320b',
            'ACTUAL_BILI_R9_INSTALL_AND_APK_CHAIN_REQUIRED')
    canonical=json.dumps(helper,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    require(sha(canonical)==state.get('wire_sha256')==coordinator.get('state_wire_sha256') and
            state.get('actual_command_returncode')==0 and state.get('actual_instrumentation_finish_code')==-1 and
            state.get('held_transport_returned_after_post_guard') is True and
            helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors')==[] and
            helper.get('action_attempted') is False and helper.get('outcome_unknown') is False,
            'EXACT_CANONICAL_NO_ACTION_STATE_BINDING_REQUIRED')
    return uid


def collect():
    require(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    r=Reader()
    for name in ('coordinator.json','stage.json'):
        value=json.loads(r.add(name,BASE[name]));no_raw_ui(value)
    coordinator=json.loads(r.records['coordinator.json']['text'])
    stage=json.loads(r.records['stage.json']['text'])
    observed={k:r.records['coordinator.json'][k] for k in ('path','bytes','sha256')}
    pin=parent_worker_pin(coordinator,stage,observed)
    raw=r.read(BASE['worker.json'])
    require((len(raw),sha(raw))==(pin['bytes'],pin['sha256']),'PARENT_BOUND_WORKER_BYTES_CHANGED')
    worker=json.loads(raw);no_raw_ui(worker)
    uid=state_only(worker,coordinator)
    r.add('worker.json',BASE['worker.json'],raw)
    result={'schema':1,'scope':'exact-owned-bili-r9-install-parent-bound-worker-and-no-automation-state',
        'files':r.records,'state_nonce':NONCE,'actual_helper_uid':uid,
        'total_read_bytes':r.total,'elapsed_seconds':time.monotonic()-r.started,
        'parent_bound_worker_original_exported':True,'state_assessment_embedded_in_worker':True,
        'raw_state_command_stream_read':False,'optional_command_scan_performed':False,
        'Android_commands':0,'service_or_process_actions':0,'permission_or_original_file_changes':0,
        'raw_commercial_UI_or_journal_exported':False,'independent_runtime_qualification':False}
    text=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    require(len(text.encode())<=524288,'EXPORT_BOUND')
    print(text,flush=True)
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once',action='store_true')
    args=parser.parse_args(argv)
    if not args.collect_once:
        print(json.dumps({'state':'PLAN_ONLY','fixed_roots':[str(ROOT),str(STEP)],'remote_actions':0}))
        return 0
    return collect()


if __name__=='__main__':
    raise SystemExit(main())
