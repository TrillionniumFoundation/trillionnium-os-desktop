#!/usr/bin/env python3
"""Fixed read-only export of this owned r4 install and no-automation state."""
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

ROOT = Path('/home/alex/work/pocket4-owned-bili-qa-r4-install-state-01')
STEP = Path('/home/alex/work/pocket4-bilibili-owned-qa-r4-flow-dbe9123975207fa1dce3ed2a35ddcfa7/steps/install-state-r4-01')
NONCE = '395066c472be8e687d2a1579315ddb9b'
PACKAGE = 'org.droidloom.qa.bili.r4'
PROTOCOL = 'pocket4-owned-bili-qa-v4'
PINS = {'coordinator.json':(3025,'2e19bc64b71461430c0581deec9c47db1f2c2144851e908371963b25e214d50f'), 'stage.json':(2032,'f466e61fba902d171d1c8fd42544d7e0a84067c73215740732d2a482a355c39e')}
BASE = {
    'coordinator.json':ROOT/'result.json',
    'stage.json':ROOT/'stage-result.json',
    'worker.json':STEP/'result.json',
    'worker-command-result.json':ROOT/'evidence/02-install-state.result.json',
    'worker.stdout':ROOT/'evidence/02-install-state.stdout',
    'worker.stderr':ROOT/'evidence/02-install-state.stderr',
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
        require(path.is_absolute() and '..' not in path.parts and
                (ROOT in path.parents or STEP in path.parents), 'FIXED_OWNED_PATH_REQUIRED')
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


def collect():
    require(os.getuid()==os.geteuid()==0,'ROOT_READ_ONLY_REQUIRED')
    r=Reader()
    for name,path in BASE.items():
        r.add(name,path)
    worker=json.loads(r.records['worker.json']['text'])
    require(worker.get('package')==PACKAGE and worker.get('state_nonce')==NONCE and
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
    require(type(uid) is int and 10000<=uid<100000 and uid not in (10117,10125,10164,10165,10166) and
            helper.get('self_uid')==uid,'ACTUAL_R4_UID_REQUIRED')
    request=json.loads(r.add('state.request.json',STEP/(NONCE+'.request.json')))
    require(request=={'protocol':PROTOCOL,'nonce':NONCE,'op':'state'},'FIXED_STATE_REQUEST_REQUIRED')
    assessment=json.loads(r.add('state.assessment.json',STEP/(NONCE+'.assessment.json')))
    require(assessment==state,'ACTUAL_WORKER_AND_ASSESSMENT_DIFFER')
    wanted=state.get('recorder_command_result_sha256')
    require(isinstance(wanted,str) and re.fullmatch('[0-9a-f]{64}',wanted),'ACTUAL_STATE_COMMAND_PIN_REQUIRED')
    matches=[]
    # This exact owned install step has a bounded command sequence. Only the
    # record whose complete hash equals its state receipt is exported.
    for index in range(1,17):
        path=STEP/('command-%03d.result.json'%index)
        raw=r.read(path,optional=True)
        if raw is not None and sha(raw)==wanted:
            matches.append((index,path,raw))
    require(len(matches)==1,'UNIQUE_ACTUAL_STATE_COMMAND_REQUIRED')
    index,path,raw=matches[0]
    command=json.loads(r.add('state-command.result.json',path,raw))
    stem=STEP/('command-%03d'%index)
    out=r.add('state-command.stdout',Path(str(stem)+'.stdout'))
    err=r.add('state-command.stderr',Path(str(stem)+'.stderr'))
    require(sha(out)==state['stdout_sha256']==command['stdout_sha256'] and
            sha(err)==state['stderr_sha256']==command['stderr_sha256'],'ACTUAL_STATE_OUTPUT_PINS_DIFFER')
    encoded=re.findall(rb'^INSTRUMENTATION_RESULT: owned_qa_result_gzip_base64=([^\r\n]+)\r?$',out,re.M)
    require(len(encoded)==1,'ONE_STATE_WIRE_REQUIRED')
    wire=decode_state_wire(encoded[0])
    require(sha(wire)==state['wire_sha256'] and json.loads(wire)==helper,'RAW_STATE_NOT_MATCHING_PARSED_NO_UI_RECEIPT')
    result={'schema':1,'scope':'exact-owned-r4-install-and-no-automation-state-readback',
        'files':r.records,'state_command_index':index,'state_nonce':NONCE,'actual_helper_uid':uid,
        'total_read_bytes':r.total,'elapsed_seconds':time.monotonic()-r.started,
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
