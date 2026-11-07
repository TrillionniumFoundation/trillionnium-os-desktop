#!/usr/bin/env python3
"""Fixed read-only collection of Bili R10 install02 originals; no action or retry."""
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

ROOT = Path("/home/alex/work/pocket4-owned-bili-qa-r10-install-state-02")
STEP = Path("/home/alex/work/pocket4-bilibili-owned-qa-r10-flow-d5a77071f725e6bfb854effcd467cc99/steps/install-state-r10-02")
NONCE = "d6a0aab3fd95f4e006a35683d0bd2c7b"
PACKAGE = "org.droidloom.qa.bili.r10"
PROTOCOL = "pocket4-owned-bili-qa-v10"
PINS = {"coordinator.json": (4415, "89f20a28d01c4b4798051f03ff72071714116e63a53c5ecacb11269a041959bf"), "stage.json": (7299, "e9ada57f1bce000382c4b6fc989a9150a2ae78662cbe2916fa48b9f8609e9a1e")}
INSTALL_NONCE = "d5a77071f725e6bfb854effcd467cc99"
SOURCE_SHA = "e3cb2adbcfe46a47ca81ec3b5883f1e1a0cd806b21e964d75944e8fe5cd49387"
BASE = {
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'worker.json':STEP/'result.json',
    'worker-command.json':ROOT/'evidence/02-install-state.result.json',
    'worker-stdout.json':ROOT/'evidence/02-install-state.stdout',
    'state-command.json':STEP/'command-006.result.json',
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
        require(path in BASE.values(), 'EXACT_SIX_FILE_ALLOWLIST_REQUIRED')
        directory = os.open('/', os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        fd = None
        try:
            for name in path.parts[1:-1]:
                try:
                    next_fd = os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=directory)
                except FileNotFoundError:
                    if optional:return None
                    raise
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
    # Both externally pinned parents retain their original status and errors.
    # Collection never qualifies installation or changes a failure/unknown.
    for value in (coordinator,stage):
        require(value.get('source_manifest_sha256')==SOURCE_SHA and value.get('nonce')==INSTALL_NONCE and
                type(value.get('ok')) is bool and isinstance(value.get('secondary_errors'),list),
                'EXACT_ACTUAL_BILI_R10_PARENT_RECEIPTS_REQUIRED')
    require(coordinator.get('package')==PACKAGE and stage.get('coordinator_result')==coordinator_pin,
            'EXACT_ACTUAL_BILI_R10_PARENT_CHAIN_REQUIRED')
    for value in (coordinator,stage):
        require((value['ok'] is True and value.get('error') is None) or
                (value['ok'] is False and isinstance(value.get('error'),dict)),
                'EXACT_ORIGINAL_PARENT_STATUS_SHAPE_REQUIRED')
    rows=[coordinator[key] for key in ('worker_result','failed_worker_result') if key in coordinator]
    if not rows:
        return None
    require(all(pin==rows[0] for pin in rows),'CONFLICTING_PARENT_WORKER_PINS')
    pin=rows[0]
    require(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==str(BASE['worker.json']) and
            type(pin['bytes']) is int and 0<pin['bytes']<=65536 and isinstance(pin['sha256'],str) and
            re.fullmatch('[0-9a-f]{64}',pin['sha256']), 'EXACT_PARENT_BOUND_WORKER_PIN_REQUIRED')
    return pin


def owned_failure(worker):
    # Bili's original worker is recorder/session based. Its exact pinned parent
    # binds the staged source; it does not emit the three custom-App Context
    # fields (target_package/source_manifest/App_launches/settings_writes).
    require(worker.get('package')==PACKAGE and
            worker.get('nonce')==INSTALL_NONCE and worker.get('state_nonce')==NONCE and
            worker.get('UI_actions')==0 and worker.get('audio_actions')==0 and
            worker.get('UiAutomation_connection_requested') is False and
            worker.get('permission_grants')==0 and worker.get('old_v2_helper_called') is False and
            worker.get('automatic_retry') is False and
            type(worker.get('ok')) is bool and isinstance(worker.get('secondary_errors'),list),
            'EXACT_NO_UI_OWNED_WORKER_REQUIRED')
    for key,wanted in {
        'runtime_recorder_manifest_sha256':'002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff',
        'runtime_session_binding_sha256':'d896b750b6e35fc859c773a5f9797c22c33631a9bfc4c3c4d327706438cf0013',
    }.items():
        if key in worker:require(worker[key]==wanted,'OBSERVED_RUNTIME_SOURCE_CHANGED:'+key)
    if 'build' in worker:
        require(worker['build']['source_manifest_sha256']=='52ababa77e144bdb43f0f6fde4483e2f8cb43dcf8c431590b02b068d2715f9f2' and
                worker['build']['APK']['sha256']=='db20a0f098ce6d1e7cc69cfbb32971a138b9c722a46b13bcfda5333620da48be',
                'OBSERVED_BUILD_CHANGED')
    state=worker.get('state')
    if state is not None:
        require(isinstance(state,dict),'STATE_TYPE')
        helper=state.get('helper')
        require(isinstance(helper,dict) and helper.get('protocol')==PROTOCOL and helper.get('op')=='state' and
                helper.get('nonce')==NONCE and helper.get('ui_automation_connected') is False and
                helper.get('window_observation')=={} and helper.get('tree_observations')==[] and
                'inspection' not in helper,'ONLY_NO_AUTOMATION_STATE_CAN_BE_EXPORTED')
    no_raw_ui(worker)


def collect():
    require(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    r=Reader()
    for name in ('coordinator.json','stage.json'):
        value=json.loads(r.add(name,BASE[name]));no_raw_ui(value)
    coordinator=json.loads(r.records['coordinator.json']['text'])
    stage=json.loads(r.records['stage.json']['text'])
    observed={k:r.records['coordinator.json'][k] for k in ('path','bytes','sha256')}
    pin=parent_worker_pin(coordinator,stage,observed)
    observations={}
    worker=None
    if pin is not None:
        raw=r.read(BASE['worker.json'])
        require((len(raw),sha(raw))==(pin['bytes'],pin['sha256']),'PARENT_BOUND_WORKER_BYTES_CHANGED')
        worker=json.loads(raw);owned_failure(worker)
        r.add('worker.json',BASE['worker.json'],raw)
        observations['worker']={'present':True,'parent_bound':True}
    else:
        raw=r.read(BASE['worker.json'],optional=True)
        observations['worker']={'present':raw is not None,'parent_bound':False,
            'unbound_original_exported':False}
        if raw is not None:
            observations['worker'].update(bytes=len(raw),sha256=sha(raw))
    command_raw=r.read(BASE['worker-command.json'],optional=True)
    command=None
    observations['worker_command']={'present':command_raw is not None}
    if command_raw is not None:
        command=json.loads(command_raw);no_raw_ui(command)
        expected_argv=['/usr/bin/python3','-I','-B',str(ROOT/'source/install_state.py'),
            '--worker-once','--source-manifest-sha256',SOURCE_SHA]
        require(coordinator.get('install_state_worker_requested') is True and
                command.get('name')=='02-install-state' and command.get('argv')==expected_argv,
                'EXACT_SOURCE_BOUND_WORKER_COMMAND_REQUIRED')
        for key in ('stdout','stderr'):
            stream=command.get(key)
            require(type(stream) is dict and set(stream)=={'bytes','sha256'} and
                    type(stream['bytes']) is int and stream['bytes']>=0 and
                    isinstance(stream['sha256'],str) and re.fullmatch('[0-9a-f]{64}',stream['sha256']),
                    'EXACT_WORKER_STREAM_PIN:'+key)
        r.add('worker-command.json',BASE['worker-command.json'],command_raw)
    # The only stdout path admitted here is this fixed Python worker's public
    # JSON result, never an Android instrumentation stream or stderr text.
    if command is not None and worker is not None:
        printed=r.read(BASE['worker-stdout.json'],optional=True)
        observations['worker_json_stdout']={'present':printed is not None,'exported':False}
        if printed is not None:
            require(command['stdout']=={'bytes':len(printed),'sha256':sha(printed)},
                    'ACTUAL_WORKER_STDOUT_PARENT_PIN')
            try:
                printed_value=json.loads(printed)
            except (ValueError,UnicodeError):
                observations['worker_json_stdout']['public_worker_JSON']=False
            else:
                no_raw_ui(printed_value)
                require(printed_value==worker,'ACTUAL_WORKER_STDOUT_AND_DURABLE_JSON_SEMANTICS')
                r.add('worker-stdout.json',BASE['worker-stdout.json'],printed)
                observations['worker_json_stdout'].update(public_worker_JSON=True,exported=True)
    if worker is not None and isinstance(worker.get('state'),dict):
        state=worker['state'];digest=state.get('recorder_command_result_sha256')
        require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),'EXACT_STATE_METADATA_PIN')
        state_raw=r.read(BASE['state-command.json'])
        require(sha(state_raw)==digest,'EXACT_STATE_COMMAND_PARENT_SHA')
        state_command=json.loads(state_raw);no_raw_ui(state_command)
        require(state_command.get('stdout_sha256')==state.get('stdout_sha256') and
                state_command.get('stderr_sha256')==state.get('stderr_sha256'),
                'EXACT_NO_UI_STATE_COMMAND_STREAM_BINDING')
        r.add('state-command.json',BASE['state-command.json'],state_raw)
        observations['state_command']={'present':True,'parent_bound':True,'index':6}
    else:
        observations['state_command']={'not_read':True,'parent_pin_available':False}
    result={'schema':1,'scope':'exact-owned-bili-r10-install02-originals',
        'files':r.records,'observations':observations,
        'total_read_bytes':r.total,'elapsed_seconds':time.monotonic()-r.started,
        'actual_install_success_qualified':False,'original_failure_and_unknown_preserved':True,
        'state_command_index':6,'raw_state_command_stream_read':False,
        'optional_command_scan_performed':False,'Android_commands':0,'service_or_process_actions':0,
        'permission_or_original_file_changes':0,'raw_commercial_UI_or_journal_exported':False,
        'independent_runtime_qualification':False,'cleanup_authority':False,'automatic_retry':False}
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
