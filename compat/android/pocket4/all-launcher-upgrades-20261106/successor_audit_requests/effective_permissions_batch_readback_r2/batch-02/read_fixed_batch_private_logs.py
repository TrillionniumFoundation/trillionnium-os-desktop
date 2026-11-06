#!/usr/bin/env python3
"""Read one exact settled batch of private service logs; compress whole original result, no Main command."""
import base64
import zlib
import hashlib
import json
import os
import stat
import sys
STAT_KEYS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
PINS = ({'bytes': 1478016, 'path': '/home/alex/work/pocket4-microg-permission-correction-observation-20261106-r1/android-02.stdout', 'sha256': '738586aac7aef5aafee12cc238bb0f70be69ba218d8b512b25fe168559dfab8d'}, {'bytes': 1478, 'path': '/home/alex/work/pocket4-microg-permission-correction-observation-20261106-r1/android-03.stdout', 'sha256': '2c636551a798d17ebcb17ca12440f7772d486b86af9f017683fba7ed0735118c'})
CAPTURE_BINDING = {'source_capture_batch': 2, 'source_capture_job': '1a1b2d790f2-fc05-7ffb', 'source_capture_artifact_sha256': '60006128ea7afdfd2fe81b3f408147d948cbedf2a0a4c5a4011b03f34989a5e3', 'source_capture_outer_stdout_sha256': 'e9cebfcf091c930cb063f7a7ae50af51e795e34c42b42dfbbaa8f2d3cfad96b1', 'source_capture_terminal_sha256': '6a870f1cb79b8944ab0950edc2a907fa8a2579790b464e9c9a36944437416109', 'target_log_mapping': [{'target_package': 'com.google.android.gms', 'target_user': 0, 'service': 'package-dump-package', 'maximum_body_bytes': 2097152, 'pin': {'bytes': 1478016, 'path': '/home/alex/work/pocket4-microg-permission-correction-observation-20261106-r1/android-02.stdout', 'sha256': '738586aac7aef5aafee12cc238bb0f70be69ba218d8b512b25fe168559dfab8d'}}, {'target_package': 'com.google.android.gms', 'target_user': 0, 'service': 'appops-get-user0', 'maximum_body_bytes': 262144, 'pin': {'bytes': 1478, 'path': '/home/alex/work/pocket4-microg-permission-correction-observation-20261106-r1/android-03.stdout', 'sha256': '2c636551a798d17ebcb17ca12440f7772d486b86af9f017683fba7ed0735118c'}}], 'microG_correction_linkage': {'schema': 'pocket4-explicit-microg-correction-linkage-v1', 'original_capture_plan_sha256': '802c9616b99c0c753c7a31188ab7b594e5baba39d6940d963c2c1b9bd2cdb749', 'original_gate_sha256': 'dc4fffb3f11e8428db732b96cd1925f0bdce239cdce81ff64ab369dc14c751f4', 'input_closure_sha256': '8bb09230184ffd2fa86791a280fce34c72ba217dbd493139ee2992c756add0f3', 'original_failed_job': '1a1b2be17ec-fc05-7f8b', 'original_failed_artifact_sha256': 'f86711fe87e7c4976dd61cdd5c53bbfeb5f4692af773990d89db088781758cf3', 'original_failed_terminal_sha256': 'bd1a4b5cc261490f0a18aeb55ce99eede71fd5a4882d174e5801a3ee00cb7ac4', 'original_gate_STOP_sha256': 'd2ab87f1aa7674003db63a588e650431d7b3c147b59852fd23c8f5a8790dabc8', 'corrective_job': '1a1b2d790f2-fc05-7ffb', 'corrective_artifact_sha256': '60006128ea7afdfd2fe81b3f408147d948cbedf2a0a4c5a4011b03f34989a5e3', 'corrective_outer_stdout_sha256': 'e9cebfcf091c930cb063f7a7ae50af51e795e34c42b42dfbbaa8f2d3cfad96b1', 'corrective_terminal_sha256': '6a870f1cb79b8944ab0950edc2a907fa8a2579790b464e9c9a36944437416109', 'original_failed_capture_reclassified': False, 'original_b01_b02_modified': False, 'original_scope_and_b03_b13_requests_unchanged': True, 'all_runtime_and_owned_lifetime_checks_required': True, 'raw_capture_is_semantic_grant_proof': False, 'automatic_retry': False, 'production_ready': False}, 'raw_capture_is_semantic_grant_proof': False, 'original_failed_capture_reclassified': False, 'role_status': 'UNKNOWN_NOT_QUERIED'}
BODY_LIMITS = [2097152, 262144]
ACTUAL_LOG_BYTES = 1479494
MAX_INNER_BYTES = 2991756
MAX_COMPRESSED_STDOUT_BYTES = 1048576

def need(value,code):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def read_file(parent,name,size,digest,owned_mode=None):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1 and
             before.st_size==size and (owned_mode is None or stat.S_IMODE(before.st_mode)==owned_mode),'PINNED_ROOT_FILE')
        body=bytearray()
        while len(body)<=size:
            part=os.read(fd,min(65536,size+1-len(body)))
            if not part:break
            body.extend(part)
        again=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        try:
            need(len(body)==size and sha(body)==digest and
                 all(getattr(before,k)==getattr(os.fstat(fd),k)==getattr(os.fstat(again),k) for k in STAT_KEYS),'FILE_OR_PATH_CHANGED')
        finally:os.close(again)
        return bytes(body)
    finally:os.close(fd)

def read_host_pin(pin):
    path=pin['path'];parts=path[1:].split('/')
    need(path.startswith('/') and all(x not in ('','.','..') for x in parts),'CANONICAL_PIN_PATH')
    fds=[]
    try:
        parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(parent)
        for name in parts[:-1]:
            parent=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(parent)
        return read_file(parent,parts[-1],pin['bytes'],pin['sha256'])
    finally:
        errors=[]
        for fd in reversed(fds):
            try:os.close(fd)
            except OSError:errors.append(fd)
        need(not errors,'PIN_READER_FDS_NOT_CLOSED')


def main():
    need(os.getuid()==os.geteuid()==0,'EXISTING_AUTHORIZED_ROOT_READER_REQUIRED')
    before=len(os.listdir('/proc/self/fd'))
    need(2<=len(PINS)<=8 and len(PINS)==len(BODY_LIMITS),'EXACT_FIXED_BATCH_LOG_COUNT')
    need(all(type(p['bytes']) is int and 0<=p['bytes']<=cap for p,cap in zip(PINS,BODY_LIMITS)) and sum(p['bytes'] for p in PINS)==ACTUAL_LOG_BYTES<=2097152,'FIXED_BATCH_CAPTURE_BYTE_LIMITS')
    rows=[]
    for pin in PINS:
        raw=read_host_pin(pin)
        rows.append({**pin,'encoding':'hex','bytes_hex':raw.hex(),'held_file_and_path_rechecked':True})
    after=len(os.listdir('/proc/self/fd'))
    need(after==before,'HOST_READER_DESCRIPTOR_DIFFERENCE')
    result={'schema':'pocket4-fixed-batch-private-service-log-readback-v2','ok':True,
            'capture_binding':CAPTURE_BINDING,'files':rows,
            'process_FDs_before':before,'process_FDs_after':after,
            'existing_files_modified':False,'Main_reads':0,'native_commands':0,
            'Android_commands':0,'aapt_commands':0,'UI_actions':0,'installs':0,
            'namespace_entries':0,'permission_changes':0,'action_lock_acquired':False,
            'automatic_retry':False,'original_failed_audit_reclassified':False,
            'raw_output_may_contain_private_state':True,'raw_output_repository_publication_admitted':False}
    raw=canonical(result)
    need(len(raw)<=MAX_INNER_BYTES,'COMPLETE_PRIVATE_RESULT_BYTE_BOUND')
    compressed=zlib.compress(raw,9)
    envelope=canonical({'encoding':'zlib-base64','artifact_bytes':len(raw),'artifact_sha256':sha(raw),'data':base64.b64encode(compressed).decode('ascii')})
    need(len(envelope)+1<=MAX_COMPRESSED_STDOUT_BYTES,'COMPRESSED_PRIVATE_STDOUT_BOUND_NO_PARTIAL_PUBLICATION')
    print(envelope.decode('ascii'),flush=True)

if __name__=='__main__':main()

