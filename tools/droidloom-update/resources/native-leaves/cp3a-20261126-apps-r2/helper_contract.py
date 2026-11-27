"""Pinned mapped-userns helper and a fresh, same-Main readonly qualification.

Private kernel controls prove the helper mechanism only. They cannot supply the
current Main receipt, native Ready witness, or any App task-cleanup permission.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

COHORT=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2')
QUALIFICATION=Path('/var/lib/droidloom/qualification/pocket4')
HELPER={'path':str(COHORT/'bin/held-namespace-entry'),'bytes':3972024,
        'sha256':'67cfd1c212e9f40ce3f0ff7be856a05f8189c674cbfa270757a672ea596a6c3f'}
SOURCE={'path':str(COHORT/'source/held_namespace_entry.rs'),'bytes':21907,
        'sha256':'5367f5c9786b9d3795b14c51af6c6bd488782a624b9066ce84e64af7feacf792'}
EVIDENCE={'path':str(COHORT/'evidence/helper/evidence-manifest.json'),'bytes':19353,
          'sha256':'fc20a33d502707bf0a3f9194a966b44282eca214f62bfe830f7eae498c8c8c1a'}
COMMANDS=(('guest-uid',('/system/bin/toybox','id','-u'),b'0\n'),
          ('guest-gid',('/system/bin/toybox','id','-g'),b'0\n'),
          ('boot-completed',('/system/bin/getprop','sys.boot_completed'),b'1\n'))
META=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def need(value,code):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def parse(raw):
    def pairs(items):
        value={}
        for key,item in items:
            need(key not in value,'DUPLICATE_HELPER_EVIDENCE_FIELD');value[key]=item
        return value
    def nonfinite(_):raise RuntimeError('NONFINITE_HELPER_EVIDENCE')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)
def metadata(info):return tuple(getattr(info,key) for key in META)

def read_ref(ref,*,qualification=False,mode=None):
    need(type(ref) is dict and set(ref)=={'path','bytes','sha256'} and
         type(ref['bytes']) is int and 0<=ref['bytes']<=8*1024*1024 and
         type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}',ref['sha256']),
         'EXACT_HELPER_FILEPIN_REQUIRED')
    path=Path(ref['path']);root=QUALIFICATION if qualification else COHORT
    need(path.is_absolute() and path.resolve()==path and path.is_relative_to(root),
         'CANONICAL_HELPER_EVIDENCE_PATH_REQUIRED')
    for parent in path.parents:
        info=parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0 and not info.st_mode&0o022,
             'ROOT_SEALED_HELPER_EVIDENCE_PARENT_REQUIRED')
    if qualification:
        need(stat.S_IMODE(root.lstat().st_mode)==0o700 and
             stat.S_IMODE(path.parent.lstat().st_mode)==0o700,'PRIVATE_MAIN_RECEIPT_ROOT_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        first=os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid==first.st_gid==0 and first.st_nlink==1
             and first.st_size==ref['bytes'] and not first.st_mode&0o022,
             'ROOT_SEALED_HELPER_EVIDENCE_FILE_REQUIRED')
        need(mode is None or stat.S_IMODE(first.st_mode)==mode,'HELPER_INSTALLED_MODE_CHANGED')
        raw=bytearray();deadline=time.monotonic()+8
        while True:
            need(time.monotonic()<deadline,'HELPER_EVIDENCE_READ_DEADLINE')
            block=os.read(fd,min(65536,ref['bytes']+1-len(raw)))
            if not block:break
            raw.extend(block);need(len(raw)<=ref['bytes'],'HELPER_EVIDENCE_GREW')
        need(metadata(first)==metadata(os.fstat(fd))==metadata(path.lstat()) and
             len(raw)==ref['bytes'] and sha(raw)==ref['sha256'],'HELPER_EVIDENCE_BOOKEND_CHANGED')
        return bytes(raw)
    finally:os.close(fd)

def verify_host_helper():
    packet=parse(read_ref(EVIDENCE,mode=0o444))
    need(packet.get('schema')=='pocket4-byte-preserved-helper-evidence-v1' and
         packet.get('Main_readonly_entry_passed') is False and packet.get('runtime_qualified') is False
         and packet.get('production_ready') is False and packet.get('historical_paths_grant_current_authority') is False,
         'HOST_HELPER_PROOF_CANNOT_ISSUE_MAIN_AUTHORITY')
    need(packet['binary']['copy']==HELPER and packet['copies']['source']['copy']==SOURCE,
         'FROZEN_HELPER_SOURCE_AND_BINARY_REQUIRED')
    read_ref(HELPER,mode=0o755);read_ref(SOURCE,mode=0o444)
    bodies={}
    for name,row in packet['copies'].items():
        need(row['copy']['bytes']==row['original']['bytes'] and
             row['copy']['sha256']==row['original']['sha256'],'HISTORICAL_HELPER_BODY_REWRITTEN')
        raw=read_ref(row['copy'],mode=0o444)
        if name!='source':bodies[name]=parse(raw)
    outputs={}
    need(len(packet['raw_outputs'])==20,'ALL_ACTUAL_HELPER_RAW_OUTPUTS_REQUIRED')
    for row in packet['raw_outputs']:
        old=row['original'];new=row['copy']
        need(old['bytes']==new['bytes'] and old['sha256']==new['sha256'] and
             old['path'] not in outputs,'EXACT_UNREWRITTEN_HELPER_RAW_OUTPUT_MAPPING')
        outputs[old['path']]=(old,read_ref(new,mode=0o444))
    build=bodies['build'];private=bodies['private'];review=bodies['review'];handoff=bodies['handoff']
    need(build.get('schema')=='p4-held-main-userns-entry-build-controls-v1' and build.get('passed') is True
         and build.get('pure_tests_passed')==4 and build.get('real_pre_namespace_rejection_controls')==1
         and build.get('all_owned_children_retired') is True and build.get('final_descendant_retirement')==[],
         'ACTUAL_PINNED_HELPER_BUILD_CONTROLS_REQUIRED')
    need(private.get('schema')=='p4-held-main-userns-entry-private-kernel-controls-v1' and private.get('passed') is True
         and private.get('error') is None and private.get('normal_fixture_retirement') is True
         and private.get('all_owned_children_reaped') is True
         and private.get('host_mount_and_namespace_bookends_equal') is True
         and private.get('input_bookends_equal') is True and private.get('inherited_authority_fd_count')==7,
         'ACTUAL_PRIVATE_KERNEL_ENTRY_AND_RETIREMENT_REQUIRED')
    need(review.get('passed_source_review') is True and review.get('findings')==[]
         and handoff.get('Main_readonly_entry_passed') is False
         and handoff.get('daemon_ReadyTreeWitness_issued') is False,
         'REVIEW_AND_HOST_ONLY_QUALIFICATION_BOUNDARY_REQUIRED')
    for report in (build,private):
        need(report.get('Android_namespace_entries')==report.get('Android_commands_executed')==0
             and report.get('runtime_qualified') is False and report.get('production_ready') is False,
             'PRIVATE_HELPER_PROOF_IS_NOT_ANDROID_QUALIFICATION')
    expected={'compiler-version':0,'normal-build':0,'test-build':0,'pure-tests':0,'real-missing-contract':125,
              'wrong-userns':125,'wrong-start':125,'mixed-namespace':125,'wrong-root':125,'actual-private-userns-entry':0}
    commands=build['commands']+private['commands']
    need(len(commands)==10 and {row['name'] for row in commands}==set(expected),'EXACT_HELPER_CONTROL_SET_REQUIRED')
    seen=set()
    for row in commands:
        need(row['exit_code']==expected[row['name']] and row.get('actual_child_reaped') is True
             and row.get('original_pidfd_held_until_reaped') is True,'HELPER_CONTROL_CHILD_NOT_RETIRED')
        for stream in ('stdout','stderr'):
            original,raw=outputs[row[stream]['path']]
            need(all(row[stream][key]==original[key] for key in ('path','bytes','sha256')),
                 'ACTUAL_HELPER_COMMAND_OUTPUT_PIN_CHANGED')
            seen.add(original['path'])
            if row['name']=='actual-private-userns-entry' and stream=='stdout':
                need(raw==b'0\n','PRIVATE_GUEST_UID_ZERO_NOT_OBSERVED')
    need(seen==set(outputs),'ORPHAN_OR_MISSING_HELPER_OUTPUT')
    return {'source':SOURCE,'binary':HELPER,'host_evidence':EVIDENCE,
            'current_Main_qualified':False,'whole_process_tree_cleanup_qualified':False}

def main_binding(base):
    need(base.get('schema')=='droidloom.native-leaf-runtime-comparison.v1' and
         base.get('saved_document_can_create_authority') is False,
         'CURRENT_KERNEL_FIRST_COMPARISON_REQUIRED')
    epoch=base['main_epoch'];core=base['native_owner']
    need(epoch['sha256']==sha(canonical(epoch['binding'])) and
         epoch['binding']['boot_id']==core['main']['epoch']['boot_id'] and
         epoch['binding']['processes']['init']['host_pid']==core['main']['init']['host_pid'],
         'FULL_ACTUAL_KERNEL_FIRST_MAIN_EPOCH_REQUIRED')
    return {'framework_epoch_sha256':epoch['sha256'],'boot_id':epoch['binding']['boot_id'],
        'init':epoch['binding']['processes']['init'],'main_user_namespace':base['main_user_namespace'],
        'actual_rust_main':core['main'],'actual_rust_peer':core['peer'],
        'actual_application':core['application'],'target_working_data':core['data'],
        'daemon':base['host_processes']['daemon'],
        'daemon_invocation':base['systemd_units']['daemon']['InvocationID'],
        'normal_host_release':base['normal_host_release'],
        'installed_daemon':base['installed_programs']['/usr/lib/droidloom/production/current/droidloomd']}

def command_argv(environment,literal):
    return ['/system/bin/env','-i']+[key+'='+environment[key] for key in sorted(environment)]+[
        '/system/bin/timeout','-k','2','10',*literal]

def validate_physical_argv(argv,binding,environment,literal):
    need(type(argv) is list and argv and argv[0]==HELPER['path'] and argv.count('--')==1,
         'ACTUAL_CURRENT_HELPER_EXECUTION_REQUIRED')
    separator=argv.index('--');flags={}
    for arg in argv[1:separator]:
        need(type(arg) is str and arg.startswith('--') and arg.count('=')==1,'EXACT_HELD_HELPER_FLAG')
        name,value=arg[2:].split('=');need(name not in flags and value.isdecimal(),'UNIQUE_NUMERIC_HELPER_FLAG')
        flags[name]=int(value)
    descriptors={'root-fd','mnt-fd','pid-fd','uts-fd','ipc-fd','net-fd','cgroup-fd'}
    need(set(flags)==descriptors|{'parent-pid','expected-userns-device','expected-userns-inode','expected-init-start-ticks'}
         and flags['parent-pid']>1 and len({flags[key] for key in descriptors})==7
         and all(flags[key]>=3 for key in descriptors),'EXACT_SEVEN_HELD_AUTHORITIES_REQUIRED')
    user=binding['main_user_namespace']['user_namespace']
    need(flags['expected-userns-device']==user['device'] and flags['expected-userns-inode']==user['inode']
         and flags['expected-init-start-ticks']==binding['init']['start_ticks']
         and argv[separator+1:]==command_argv(environment,literal),'SAME_MAIN_FIXED_READONLY_COMMAND_REQUIRED')

def verify_main_receipt(base):
    host=verify_host_helper();ref=base['main_readonly_entry'];receipt=parse(read_ref(ref,qualification=True,mode=0o600))
    binding=main_binding(base)
    need(receipt.get('schema')=='droidloom.native-leaf-readonly-entry.v1'
         and receipt.get('main_binding')==binding and receipt.get('helper')==host
         and receipt.get('main_capture_output')==base['capture_output_path']
         and receipt.get('Main_readonly_entry_passed') is True
         and receipt.get('native_execution_authority_transferred') is False
         and receipt.get('daemon_ReadyTreeWitness_issued') is False
         and receipt.get('whole_process_tree_cleanup_qualified') is False
         and receipt.get('whole_app_business_accepted') is False and receipt.get('production_ready') is False
         and receipt.get('Android_mutations')==0 and receipt.get('automatic_retry') is False,
         'FRESH_SAME_MAIN_READONLY_ENTRY_RECEIPT_REQUIRED')
    need(type(receipt['started_unix_ns']) is int and type(receipt['finished_unix_ns']) is int
         and 0<receipt['started_unix_ns']<=receipt['finished_unix_ns']<=base['captured_unix_ns']
         and type(receipt['started_monotonic_ns']) is int and type(receipt['finished_monotonic_ns']) is int
         and base['normal_live_comparison_before']['finished_monotonic_ns']<=receipt['started_monotonic_ns']
         <=receipt['finished_monotonic_ns']<=base['normal_live_comparison_after']['started_monotonic_ns'],
         'READONLY_ENTRY_MUST_FOLLOW_THIS_NATIVE_MAIN_INSPECTION')
    rows=receipt['commands'];need(type(rows) is list and len(rows)==receipt.get('Android_readonly_commands')==3,
         'EXACT_THREE_MAIN_READONLY_COMMANDS_REQUIRED')
    for row,(name,literal,wanted) in zip(rows,COMMANDS):
        need(row['name']==name,'FIXED_MAIN_READONLY_COMMAND_ORDER_REQUIRED')
        record=parse(read_ref(row['result'],qualification=True,mode=0o600))
        need(record.get('schema')=='pocket4-business-host-result-v1' and record.get('name')==name
             and record.get('Main_before')==record.get('Main_after')==binding
             and record.get('host_retirement_proved') is True and record.get('evidence_complete') is True
             and record.get('returncode')==0 and record.get('timed_out') is False and record.get('spawned') is True
             and record.get('errors')==[] and record.get('action_attempted') is False
             and record.get('Android_outcome_unknown') is False and record.get('automatic_retry') is False
             and record.get('post_guard_deferred_to_held_transport') is False
             and record['cancellation']=={'count':0,'signals':[]},'CURRENT_MAIN_COMMAND_FAILED_OR_UNKNOWN')
        validate_physical_argv(record['argv'],binding,base['android_env'],literal)
        lifecycle=record['lifecycle'];reaper=record['subreaper']
        need(all(lifecycle.get(key) is True for key in ('child_started','child_reaped','owned_tree_cleanup_complete',
             'all_acquired_fds_closed','retirement_within_deadline')) and lifecycle.get('remaining_owned_children')==[]
             and all(reaper.get(key) is True for key in ('begin_passed','restored','final_children_empty')),
             'CURRENT_MAIN_READONLY_CHILD_RETIREMENT_INCOMPLETE')
        need(read_ref(record['stdout'],qualification=True,mode=0o600)==wanted
             and read_ref(record['stderr'],qualification=True,mode=0o600)==b'',
             'CURRENT_MAIN_READONLY_EXPECTED_OUTPUT_REQUIRED')
    closed=receipt['authority_close']
    need(type(closed['acquired']) is int and closed['acquired']>0
         and closed['acquired']==closed['closed'] and closed['remaining']==0 and closed['errors']==[],
         'CURRENT_MAIN_ENTRY_HELD_AUTHORITIES_UNCLOSED')
    return {'source_sha256':SOURCE['sha256'],'binary_sha256':HELPER['sha256'],
        'qualification':ref,'current_Main_qualified':True,'whole_process_tree_cleanup_qualified':False}

def verify_shared_helper(baseline):
    baseline.guard()
    result=verify_main_receipt(baseline.docs['runtime_observation'])
    baseline.guard()
    return result
