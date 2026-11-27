"""Future same-Main qualification of exactly three fixed readonly commands.

This module is called only by the pinned Main factory after authenticated native
image inspection. It neither discovers an alternative Main nor creates a native
Ready permit. No private fixture or saved JSON can stand in for its live inputs.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import time

HOST_ENV={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'}

def need(value,code):
    if not value:raise RuntimeError(code)

def capture(base,mapping,reader,commands,contract,guard,root):
    need(os.getuid()==os.geteuid()==0,'EXISTING_ROOT_MAIN_FACTORY_REQUIRED')
    host=contract.verify_host_helper();binding=contract.main_binding(base)
    need(mapping.guard()==base['main_user_namespace'],'ACTUAL_HELD_MAIN_MAPPING_REQUIRED')
    root=Path(root)
    need(root.is_absolute() and root.resolve()==root and root.is_relative_to(contract.qualification_root())
         and not root.exists(),'FRESH_CANONICAL_MAIN_ENTRY_DIRECTORY_REQUIRED')
    parent=root.parent.lstat()
    need(stat.S_ISDIR(parent.st_mode) and parent.st_uid==parent.st_gid==0
         and stat.S_IMODE(parent.st_mode)==0o700,'ORIGINAL_PRIVATE_MAIN_OUTPUT_DIRECTORY_REQUIRED')
    root.mkdir(mode=0o700)
    started=time.time_ns();started_mono=time.monotonic_ns()
    target=None;rows=[];primary=None;acquired=closed=0
    init=base['main_epoch']['binding']['processes']['init']
    protected={row['host_pid'] for row in base['main_epoch']['binding']['processes'].values()}
    protected.update(row['host_pid'] for row in base['host_processes'].values())
    parent=os.getppid()
    need(parent>1 and parent not in protected and base['collector_parent_pid']==parent,
         'ACTUAL_NORMAL_RUST_COLLECTOR_PARENT_REQUIRED')
    protected.add(parent)
    need(len(protected)==7,'ALL_ACTUAL_RUNTIME_AND_COLLECTOR_PIDS_PROTECTED')

    def live_guard(*,action_attempted=False):
        need(action_attempted is False,'READONLY_MAIN_ENTRY_CANNOT_ADMIT_MUTATION')
        guard()
        need(mapping.guard()==base['main_user_namespace'],'MAIN_MAPPING_CHANGED_AROUND_READONLY_COMMAND')
        if target is not None:target.verify()
        need(contract.verify_host_helper()==host,'CURRENT_HELPER_OR_HOST_PROOF_CHANGED')
        return binding

    try:
        live_guard()
        proc=os.open('/proc/'+str(init['host_pid']),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:actual=reader.proc_identity_at(proc,init['host_pid'],time.monotonic()+3)
        finally:os.close(proc)
        need(actual['pid']==init['host_pid'] and int(actual['start'])==init['start_ticks']
             and actual['ppid']==init['parent_host_pid'] and actual['uid']==[str(x) for x in init['uids']]
             and [int(x) for x in actual['nspid']]==init['namespace_pids']
             and actual['exe']==init['executable'] and actual['cgroup'].splitlines()==init['cgroup']
             and set(actual['ns'])=={'mnt','pid','uts','ipc','net','cgroup'}
             and all(actual['ns'][name]==base['main_user_namespace']['owned_entry_namespaces'][name]['namespace']['link']
                     for name in actual['ns']),
             'READONLY_ENTRY_TARGET_MUST_BE_THIS_AUTHENTICATED_MAIN')
        target=reader.HeldTarget(actual,contract.HELPER['path'],contract.HELPER['sha256'],
                                 main_user_namespace=base['main_user_namespace'])
        acquired=len(target._fds)
        need(acquired>7 and target.user_namespace_fd>=3,'PRIVATE_USERNS_HANDLE_MUST_REMAIN_HELD')
        for name,literal,expected in contract.COMMANDS:
            need(not signal.sigpending()&{signal.SIGINT,signal.SIGTERM},'MAIN_READONLY_ENTRY_CANCELLED')
            live_guard()
            logical=contract.command_argv(base['android_env'],literal)
            try:
                with target.entry(logical) as (argv,descriptors):
                    contract.validate_physical_argv(argv,binding,base['android_env'],literal)
                    result=commands.run_recorded(name,argv,15,root,live_guard,
                        protected_pids=sorted(protected),mutation=False,pass_fds=descriptors,
                        host_env=HOST_ENV,check=True,output_bound=4096)
            except BaseException as error:
                record=getattr(error,'command_observation',{})
                if record and record.get('host_retirement_proved') is not True:target.poison_unjoined_command()
                else:target.seal_admission()
                raise
            live_guard()
            need(result.stdout==expected and result.stderr==b'' and result.returncode==0,
                 'CURRENT_MAIN_FIXED_READONLY_COMMAND_OUTPUT_CHANGED')
            path=root/(name+'.result.json');raw=commands.read(path,maximum=131072)
            ref={'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            need(commands.parse(raw)==result.command_observation,'ACTUAL_READONLY_COMMAND_RESULT_NOT_DURABLE')
            rows.append({'name':name,'result':ref})
        live_guard()
    except BaseException as error:primary=error;raise
    finally:
        if target is not None:
            try:
                target.close()
                need(target._closed and not target._fds,'READONLY_MAIN_ENTRY_FDS_UNCLOSED')
                closed=acquired
            except BaseException as error:
                if primary is None:raise
                primary.add_note('Main readonly held authority close failed: '+type(error).__name__)
    need(len(rows)==3 and acquired==closed and acquired>0,'COMPLETE_CURRENT_MAIN_ENTRY_REQUIRED')
    need(not signal.sigpending()&{signal.SIGINT,signal.SIGTERM},'MAIN_READONLY_ENTRY_CANCELLED_BEFORE_COMMIT')
    guard();need(mapping.guard()==base['main_user_namespace'],'FINAL_MAIN_ENTRY_MAPPING_CHANGED')
    receipt={'schema':'droidloom.native-leaf-readonly-entry.v1','main_binding':binding,'helper':host,
        'main_capture_output':base['capture_output_path'],'commands':rows,
        'started_unix_ns':started,'finished_unix_ns':time.time_ns(),
        'started_monotonic_ns':started_mono,'finished_monotonic_ns':time.monotonic_ns(),
        'authority_close':{'acquired':acquired,'closed':closed,'remaining':0,'errors':[]},
        'Main_readonly_entry_passed':True,'Android_readonly_commands':3,'Android_mutations':0,
        'automatic_retry':False,'native_execution_authority_transferred':False,
        'daemon_ReadyTreeWitness_issued':False,'whole_process_tree_cleanup_qualified':False,
        'whole_app_business_accepted':False,'production_ready':False}
    return commands.write_new(root/'result.json',receipt)
