"""Three fixed preparation diagnostics through the actual normal broker.

The Python document is comparison data. The Rust parent retains each opaque
execution observation through this collector's retirement and compares the
complete records before publishing a baseline or qualification.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import time

def need(value,code):
    if not value:raise RuntimeError(code)
def write(root,name,raw):
    path=root/name
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        view=memoryview(raw)
        while view:view=view[os.write(fd,view):]
        os.fsync(fd)
    finally:os.close(fd)
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def document(root,name,value):
    return write(root,name,(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())

def capture(base,mapping,reader,commands,contract,guard,root,*,live):
    need(os.getuid()==os.geteuid()==0,'EXISTING_ROOT_MAIN_FACTORY_REQUIRED')
    host=contract.verify_host_helper();binding=contract.main_binding(base)
    need(live.core==base['native_owner'] and mapping.guard()==base['main_user_namespace'],
         'ACTUAL_HELD_MAIN_MAPPING_AND_NORMAL_CHANNEL_REQUIRED')
    root=Path(root)
    need(root.is_absolute() and root.resolve()==root and root.is_relative_to(contract.QUALIFICATION)
         and not root.exists(),'FRESH_CANONICAL_MAIN_ENTRY_DIRECTORY_REQUIRED')
    parent=root.parent.lstat()
    need(stat.S_ISDIR(parent.st_mode) and parent.st_uid==parent.st_gid==0
         and stat.S_IMODE(parent.st_mode)==0o700,'ORIGINAL_PRIVATE_MAIN_OUTPUT_DIRECTORY_REQUIRED')
    need(os.getppid()>1 and base['collector_parent_pid']==os.getppid(),
         'ACTUAL_NORMAL_RUST_COLLECTOR_PARENT_REQUIRED')
    root.mkdir(mode=0o700);channel=live.preparation_reads()
    started=time.time_ns();started_mono=time.monotonic_ns();rows=[]
    def check():
        need(not signal.sigpending()&{signal.SIGINT,signal.SIGTERM},'MAIN_READONLY_ENTRY_CANCELLED')
        guard();live.guard()
        need(mapping.guard()==base['main_user_namespace'],'MAIN_MAPPING_CHANGED_AROUND_READONLY_COMMAND')
        need(contract.verify_host_helper()==host,'HISTORICAL_HELPER_SOURCE_PROOF_CHANGED')
    for name,literal,expected in contract.COMMANDS:
        check();begin=time.monotonic_ns()
        document(root,name+'.intent.json',{
            'schema':'droidloom.preparation-read-intent.v1','name':name,'main_binding':binding,
            'literal_operation':list(literal),'started_monotonic_ns':begin,
            'mutation':False,'automatic_retry':False})
        observed=channel.read(name)
        stdout=write(root,name+'.stdout',bytes(observed['stdout']))
        stderr=write(root,name+'.stderr',bytes(observed['stderr']))
        record={'schema':'droidloom.preparation-read-command.v1','name':name,
            'main_binding':binding,'gateway':observed,'stdout':stdout,'stderr':stderr,
            'started_monotonic_ns':begin,'finished_monotonic_ns':time.monotonic_ns(),
            'Android_mutations':0,'automatic_retry':False,'comparison_only':True}
        ref=document(root,name+'.result.json',record);rows.append({'name':name,'result':ref})
        receipt=observed['receipt']
        need(receipt['query_waitid_code']==1 and receipt['query_waitid_status']==0
             and bytes(observed['stdout'])==expected and observed['stderr']==[],
             'CURRENT_MAIN_FIXED_READONLY_COMMAND_FAILED_OR_OUTPUT_CHANGED')
        check()
    transport=channel.finish();check()
    receipt={'schema':'droidloom.native-leaf-readonly-entry.v2','main_binding':binding,
        'historical_helper':host,'main_capture_output':base['capture_output_path'],'commands':rows,
        'started_unix_ns':started,'finished_unix_ns':time.time_ns(),
        'started_monotonic_ns':started_mono,'finished_monotonic_ns':time.monotonic_ns(),
        'transport_close':transport,'normal_factory_executions':3,
        'Main_readonly_entry_passed':True,'Android_readonly_commands':3,'Android_mutations':0,
        'automatic_retry':False,'native_execution_authority_transferred':False,
        'daemon_ReadyTreeWitness_issued':False,'whole_process_tree_cleanup_qualified':False,
        'whole_app_business_accepted':False,'production_ready':False}
    return document(root,'result.json',receipt)
