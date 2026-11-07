#!/usr/bin/env python3
"""Four exact R8 install originals and a bounded unique state-command index; no actions."""
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

ROOT = Path('/home/alex/work/pocket4-owned-bili-qa-r8-install-state-01')
STEP = Path('/home/alex/work/pocket4-bilibili-owned-qa-r8-flow-fd9784f9e464119899726c3b583243a8/steps/install-state-r8-01')
NONCE = 'c296619272cb68fddb8923891ff0dff9'
PACKAGE = 'org.droidloom.qa.bili.r8'
PROTOCOL = 'pocket4-owned-bili-qa-v8'
PINS = {'coordinator.json': (3025, 'e734a7f5dea6de9f1b3e96727cc925fe422c74980d0e6692dc5f9412abf79676'),
        'stage.json': (2032, '91ffb967b00952273ac8168c3cd29def9c2488d55d8c642537dce54d7fb9cdf0')}
INSTALL_NONCE = 'fd9784f9e464119899726c3b583243a8'
SOURCE_SHA = '24262630242b244327a285e171c6936b00315705c541cb3d7506dfdeef49afbe'
PACKET_SHA = '693f7d62ac1c7518bd772be74c9ed1a608c9b5e847a49647c743d0807c2f4d9e'
SESSION_SHA = '2c09ebd36105fdc79386ce929946c28fc5a60cc21ed902e083c3ee13f9d7655e'
QA_SOURCE_SHA = '8e3454bcc9ebe1ff55dcaf62706ce1176cfa1d0f0ede7099cbbfa46f4ad53f1e'
BUILD_SHA = '8954a0b50093ed2110bac1e493cc2a847dfe326cb69f7fe03091aaa91d878b3c'
APK_SHA = 'b576afe56b97160dc341fe15973f5afe23db03dc2961aedaa500f1527ec13122'
SIGNER_SHA = 'b1ec4d840f5dd85513d3b3c08fbf97d829b580d4c718d6bf30cce5a8270a457d'
BASE = {
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'worker.json':STEP/'result.json',
    'worker-command-result.json':ROOT/'evidence/02-install-state.result.json',
}
STATE_FILES = tuple(STEP/('command-%03d.result.json'%index) for index in range(1,17))
READ_ALLOWLIST = set(BASE.values())|set(STATE_FILES)


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
        require(path in READ_ALLOWLIST, 'EXACT_FOUR_ORIGINALS_AND_SIXTEEN_OWNED_STATE_COMMAND_PATHS_REQUIRED')
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
                'EXACT_ACTUAL_R8_PARENT_RECEIPTS_REQUIRED')
    require(coordinator.get('package')==PACKAGE and stage.get('coordinator_result')==coordinator_pin and
            stage.get('packet_sha256')==PACKET_SHA and stage.get('coordinator_returncode')==0 and
            coordinator.get('flow')==str(STEP.parent.parent),'EXACT_ACTUAL_R8_PARENT_CHAIN_REQUIRED')
    pin=coordinator.get('worker_result')
    require(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==str(BASE['worker.json']) and
            type(pin['bytes']) is int and 0<pin['bytes']<=65536 and isinstance(pin['sha256'],str) and
            re.fullmatch('[0-9a-f]{64}',pin['sha256']), 'EXACT_PARENT_BOUND_WORKER_PIN_REQUIRED')
    return pin


def state_only(worker,coordinator):
    require(worker.get('package')==PACKAGE and worker.get('state_nonce')==NONCE and
            worker.get('nonce')==INSTALL_NONCE and worker.get('ok') is True and
            worker.get('error') is None and worker.get('secondary_errors')==[] and
            worker.get('UI_actions')==worker.get('audio_actions')==0 and
            worker.get('UiAutomation_connection_requested') is False and
            worker.get('runtime_session_binding_sha256')==SESSION_SHA,'OWNED_NO_UI_R8_WORKER_REQUIRED')
    build=worker.get('build')
    require(isinstance(build,dict) and build.get('build_receipt_sha256')==BUILD_SHA and
            build.get('source_manifest_sha256')==QA_SOURCE_SHA and
            build.get('APK',{}).get('sha256')==APK_SHA and build['APK'].get('bytes')==37008 and
            build.get('signer_certificate_sha256')==SIGNER_SHA,'EXACT_ACTUAL_R8_BUILD_REQUIRED')
    state=worker.get('state')
    require(isinstance(state,dict),'COMPLETED_OWNED_STATE_RECEIPT_REQUIRED')
    helper=state.get('helper')
    require(isinstance(helper,dict) and helper.get('protocol')==PROTOCOL and helper.get('op')=='state' and
            helper.get('nonce')==NONCE and helper.get('ui_automation_connected') is False and
            helper.get('requires_post_termination_state_check') is False and
            helper.get('window_observation')=={} and helper.get('tree_observations')==[] and
            helper.get('inspection_idle_observation')=={} and
            helper.get('wire_codec')=='gzip-canonical-json-v1' and 'inspection' not in helper,
            'ONLY_NO_AUTOMATION_NO_IDLE_STATE_CAN_BE_EXPORTED')
    uid=worker.get('owned_package_uid')
    require(type(uid) is int and 10000<=uid<100000 and
            uid not in (10117,10125,10164,10165,10166,10169,10170,10175,10184,10202) and
            helper.get('self_uid')==coordinator.get('owned_package_uid')==uid,'ACTUAL_NEW_R8_HELPER_UID_REQUIRED')
    installed=worker.get('installed_before_state')
    require(isinstance(installed,dict) and installed==worker.get('installed_after_state') and
            installed.get('package')==PACKAGE and installed.get('uid')==uid and
            installed.get('apk_sha256')==APK_SHA and installed.get('bytes')==37008 and
            installed.get('signer_bound_by_exact_signed_apk_bytes')==SIGNER_SHA,
            'ACTUAL_INSTALLED_R8_IDENTITY_REQUIRED')
    canonical=json.dumps(helper,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    require(sha(canonical)==state.get('wire_sha256')==coordinator.get('state_wire_sha256') and
            state.get('actual_command_returncode')==0 and state.get('actual_instrumentation_finish_code')==-1 and
            state.get('held_transport_returned_after_post_guard') is True and
            helper.get('ok') is True and helper.get('error') is None and helper.get('secondary_errors')==[] and
            helper.get('action_attempted') is False and helper.get('outcome_unknown') is False,
            'EXACT_CANONICAL_NO_ACTION_STATE_BINDING_REQUIRED')
    return uid


def worker_command_scope(command,coordinator):
    expected=['/usr/bin/python3','-I',str(ROOT/'source/install_state.py'),'--worker-once',
              '--source-manifest-sha256',SOURCE_SHA]
    require(command.get('name')=='02-install-state' and command.get('argv')==expected and
            command.get('spawned') is True and command.get('joined') is True and
            command.get('timed_out') is False and command.get('returncode')==0 and
            command.get('secondary_errors')==[] and command.get('Main_before') is True and
            command.get('Main_after')==coordinator.get('Main_after') and
            type(command.get('owned_child_pid')) is int and command['owned_child_pid']>0,
            'EXACT_ORIGINAL_OWNED_R8_WORKER_COMMAND_REQUIRED')
    out,err=command.get('stdout'),command.get('stderr')
    require(isinstance(out,dict) and type(out.get('bytes')) is int and 0<out['bytes']<=65536 and
            isinstance(out.get('sha256'),str) and re.fullmatch('[0-9a-f]{64}',out['sha256']) and
            err=={'bytes':0,'sha256':sha(b'')},'BOUNDED_JOINED_WORKER_STREAM_PINS_REQUIRED')


def state_command_binding(reader,worker):
    state=worker['state'];expected=state.get('recorder_command_result_sha256')
    require(isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected),
            'EXACT_WORKER_STATE_COMMAND_PIN_REQUIRED')
    matches=[]
    for index,path in enumerate(STATE_FILES,1):
        raw=reader.read(path,optional=True)
        if raw is None or sha(raw)!=expected:continue
        row=json.loads(raw);no_raw_ui(row)
        require(row.get('owned_command_joined') is True and row.get('spawned') is True and
                row.get('timed_out') is False and row.get('errors')==[] and row.get('returncode')==0 and
                row.get('stdout_sha256')==state.get('stdout_sha256') and
                row.get('stderr_sha256')==state.get('stderr_sha256'),
                'ACTUAL_JOINED_STATE_COMMAND_REQUIRED')
        matches.append({'index':index,'path':str(path),'bytes':len(raw),'sha256':sha(raw),
            'actual_command_joined':True,'actual_command_returncode':0,
            'matched_exact_worker_state_command_sha256':True,'private_command_stdout_or_stderr_exported':False})
    require(len(matches)==1,'UNIQUE_EXACT_STATE_COMMAND_INDEX_REQUIRED')
    return matches[0]


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
    raw=r.read(BASE['worker-command-result.json'])
    command=json.loads(raw);no_raw_ui(command);worker_command_scope(command,coordinator)
    r.add('worker-command-result.json',BASE['worker-command-result.json'],raw)
    state_binding=state_command_binding(r,worker)
    result={'schema':1,'scope':'exact-owned-r8-install-four-safe-originals-and-state-command-index',
        'files':r.records,'state_nonce':NONCE,'actual_helper_uid':uid,
        'state_wire_sha256':worker['state']['wire_sha256'],
        'state_command_index':state_binding['index'],'state_command_binding':state_binding,
        'total_read_bytes':r.total,'elapsed_seconds':time.monotonic()-r.started,
        'parent_bound_worker_original_exported':True,'worker_command_exact_owned_scope_verified':True,
        'Android_commands':0,'service_or_process_actions':0,'permission_or_original_file_changes':0,
        'private_stdout_or_UI_tree_exported':False,
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
