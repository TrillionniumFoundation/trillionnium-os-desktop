"""Comparison-only view of the normal Rust owner's private leaf channel.

This module does not admit a peer, select a Main, or mint business authority.
The normal source-owned Rust invocation creates the sealed descriptor and the
unnamed check endpoint after borrowing its actual Main and PM observations.
A saved document or a standalone Python invocation cannot recreate those Rust
types. Only fixed host Python children inherit the two comparison descriptors;
the mapped namespace helper never receives them.
"""
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import stat
import time

ROOT=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2')
FACTS_ENV='DROIDLOOM_NATIVE_LEAF_FACTS_FD'
GUARD_ENV='DROIDLOOM_NATIVE_LEAF_GUARD_FD'
MAX_FACTS=262144
SEALS=fcntl.F_SEAL_SEAL|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW|fcntl.F_SEAL_WRITE
# This is a fixed source set, not a prefix permission. It is updated only with
# the reviewed actual host callers; no descriptor is inherited by Android.
UI_CHILDREN=frozenset({
    str(ROOT/'source/support/business_ui_entry.py'),
    str(ROOT/'source/clock-support/business_ui_entry.py'),
})
CLOCK_CHILD=str(ROOT/'source/clock/clock_entry.py')
IHG_CHILD=str(ROOT/'source/ihg/app_entry.py')
CAMERA_CHILD=str(ROOT/'source/camera-photo/camera_entry.py')
HOST_CHILDREN=UI_CHILDREN|{CLOCK_CHILD,IHG_CHILD,CAMERA_CHILD}
NORMAL_PROGRAMS={
    'manager':'/usr/lib/droidloom/production/current/droidloomd',
    'presenter':'/usr/bin/droidloom-wayland',
}
META=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def need(value,code):
    if not value:raise RuntimeError(code)
def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def parse(raw):
    def pairs(items):
        out={}
        for key,value in items:
            need(key not in out,'DUPLICATE_NATIVE_LEAF_CHANNEL_FIELD');out[key]=value
        return out
    def bad(_):raise RuntimeError('NONFINITE_NATIVE_LEAF_CHANNEL_FIELD')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
def metadata(fd):return tuple(getattr(os.fstat(fd),key) for key in META)
def number(value,minimum=0,maximum=2**64-1):
    return type(value) is int and minimum<=value<=maximum

def validate_core(core):
    need(type(core) is dict and set(core)=={
        'schema','application','main','data','peer','comparison_only',
        'account_contents_read','business_acceptance_evaluated'} and
        core['schema']=='droidloom.native-leaf-baseline.v1' and
        core['comparison_only'] is True and core['account_contents_read'] is False and
        core['business_acceptance_evaluated'] is False,'EXACT_ACTUAL_NATIVE_LEAF_COMPARISON_REQUIRED')
    app,main,data,peer=(core[key] for key in ('application','main','data','peer'))
    need(type(app) is dict and type(main) is dict and type(data) is dict and type(peer) is dict and
        main.get('schema')=='droidloom.runtime-main-custody.v1' and
        data.get('schema')=='droidloom.native-leaf-data.v1','EXACT_NORMAL_MAIN_AND_DATA_SCHEMAS')
    need(app['epoch']==main['epoch'] and app['package']==data['package'] and
        app['user']==data['user']==0 and app['uid']==data['android_uid'] and
        number(app['uid'],1,99999) and number(app['version_code'],1) and
        isinstance(app['apks'],list) and 0<len(app['apks'])<=64,
        'SAME_ACTUAL_PACKAGE_MAIN_AND_WORKING_DATA_REQUIRED')
    need(peer['boot_id']==main['epoch']['boot_id'] and
        peer['pid']>1 and peer['systemd_invocation_checked'] is False and
        data['framework_root']==main['framework']['root'] and
        data['user_namespace']==main['persistent_data']['user_namespace'] and
        type(main['persistent_data'].get('original_copy_origin')) is dict,
        'NORMAL_OWNER_AND_ORIGINAL_WORKING_LINEAGE_REQUIRED')
    need(type(data['directories']) is list and len(data['directories'])==4 and
        [row['path'] for row in data['directories']]==[
            '/data/user/0','/data/user_de/0',
            '/data/user/0/'+app['package'],'/data/user_de/0/'+app['package']] and
        all(row['device']==data['data_root']['device'] for row in data['directories']) and
        all(row['host_uid']==data['mapped_host_uid'] for row in data['directories'][2:]) and
        data['directories'][2]['inode']!=data['directories'][3]['inode'],
        'EXACT_TARGET_ONLY_CE_DE_METADATA_REQUIRED')
    release=main.get('normal_host_release')
    need(type(release) is dict and set(release)=={'schema','manager','presenter'} and
         release['schema']=='droidloom.normal-host-release.v1',
         'ACTUAL_NORMAL_HOST_RELEASE_REQUIRED')
    for role,path in NORMAL_PROGRAMS.items():
        pin=release[role]
        need(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==path and
             number(pin['bytes'],64,128*1024*1024) and type(pin['sha256']) is str and
             re.fullmatch('[0-9a-f]{64}',pin['sha256']),
             'EXACT_SELECTED_NORMAL_HOST_PROGRAM_REQUIRED')
    need(release['manager']['sha256']!=release['presenter']['sha256'] and
         release['manager']['bytes']==peer['executable_bytes'] and
         release['manager']['sha256']==peer['executable_sha256'],
         'NORMAL_SELECTED_MANAGER_AND_ACTUAL_PEER_MUST_MATCH')
    return core


def inventory_table(value,core):
    """Validate comparison data only; the actual token stays in the Rust owner."""
    if value is None:
        need(core['application']['package']!='com.ihg.apps.android',
             'IHG_REQUIRES_COMPLETE_ACTUAL_USER0_INVENTORY')
        return None
    need(core['application']['package']=='com.ihg.apps.android' and
         type(value) is dict and set(value)=={'schema','epoch','records','records_sha256',
             'stdout_bytes','stdout_sha256','query_receipt','comparison_only'} and
         value['schema']=='droidloom.user-zero-package-inventory.v1' and
         value['epoch']==core['main']['epoch'] and value['comparison_only'] is True and
         type(value['records']) is list and 1<=len(value['records'])<=2048 and
         number(value['stdout_bytes'],1,65536) and
         all(type(value[k]) is str and re.fullmatch('[0-9a-f]{64}',value[k])
             for k in ('stdout_sha256','records_sha256')),
         'EXACT_COMPLETE_USER0_INVENTORY_COMPARISON_REQUIRED')
    rows=value['records'];names=[];records={};size=0
    for row in rows:
        need(type(row) is dict and set(row)=={'package','uid'} and
             type(row['package']) is str and 1<=len(row['package'])<=255 and
             (row['package']=='android' or ('.' in row['package'] and
                 all(re.fullmatch('[A-Za-z0-9_]+',p) for p in row['package'].split('.')))) and
             number(row['uid'],0,99999),
             'COMPLETE_USER0_INVENTORY_ROW_DIFFERS')
        name,uid=row['package'],row['uid'];need(name not in records,'DUPLICATE_USER0_PACKAGE')
        names.append(name);records[name]=uid
        size+=len(('package:'+name+' uid:'+str(uid)+'\n').encode())
    need(names==sorted(names) and size==value['stdout_bytes'] and
         sha(canonical(rows))==value['records_sha256'] and
         records.get(core['application']['package'])==core['application']['uid'],
         'COMPLETE_USER0_INVENTORY_BODY_OR_TARGET_DIFFERS')
    r=value['query_receipt'];life=r.get('lifecycle',{}) if type(r) is dict else {}
    io=life.get('stdio_creator',{}) if type(life) is dict else {}
    need(type(r) is dict and set(r)=={'schema','lifecycle','query_pid','query_waitid_code',
         'query_waitid_status','exec','output_bytes','output_sha256','elapsed_millis','cgroup_removed'} and
         r['schema']==2 and number(r['query_pid'],2,2**32-1) and
         r['query_waitid_code']==1 and r['query_waitid_status']==0 and
         r['cgroup_removed'] is True and type(r['exec']) is dict and
         r['output_bytes']==value['stdout_bytes'] and r['output_sha256']==value['stdout_sha256'] and
         type(life) is dict and set(life)=={'owner','factory_pid','factory_tid','factory_pidfd_device',
             'factory_pidfd_inode','query_pidfd_device','query_pidfd_inode','stdio_creator','release_acknowledged'} and
         life['owner']=='instance_factory' and number(life['factory_pid'],2,2**32-1) and
         life['factory_pid']==life['factory_tid'] and life['factory_pid']!=r['query_pid'] and
         all(number(life[k],1) for k in ('factory_pidfd_device','factory_pidfd_inode',
             'query_pidfd_device','query_pidfd_inode')) and life['release_acknowledged'] is True and
         type(io) is dict and set(io)=={'pid','waitid_code','waitid_status'} and
         number(io['pid'],2,2**32-1) and io['pid'] not in (life['factory_pid'],r['query_pid']) and
         io['waitid_code']==1 and io['waitid_status']==0,
         'ACTUAL_RETIRED_FIXED_QUERY_COMPARISON_REQUIRED')
    return records

class ComparisonChannel:
    def __init__(self):
        self.pid=os.getpid()
        values=[]
        for key in (FACTS_ENV,GUARD_ENV):
            raw=os.environ.get(key,'')
            need(raw.isdecimal() and len(raw)<=10 and 3<=int(raw)<2**31,
                 'NORMAL_RUST_LEAF_CHANNEL_REQUIRED')
            values.append(int(raw))
        self.facts_fd,self.guard_fd=values
        need(self.facts_fd!=self.guard_fd,'DISTINCT_NORMAL_COMPARISON_DESCRIPTORS')
        # They remain borrowed from the actual invocation. No duplicate survives
        # a single check, and neither original is closed by a comparison object.
        for fd in values:os.set_inheritable(fd,False)
        self.before=metadata(self.facts_fd)
        st=os.fstat(self.facts_fd)
        need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and st.st_nlink==0 and
             0<st.st_size<=MAX_FACTS and
             fcntl.fcntl(self.facts_fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY and
             fcntl.fcntl(self.facts_fd,fcntl.F_GET_SEALS)==SEALS,
             'SEALED_READONLY_NORMAL_COMPARISON_MEMFD_REQUIRED')
        self.raw=os.pread(self.facts_fd,MAX_FACTS+1,0)
        need(len(self.raw)==st.st_size and metadata(self.facts_fd)==self.before,
             'COMPLETE_NORMAL_COMPARISON_MEMFD_REQUIRED')
        envelope=parse(self.raw)
        keys={'schema','baseline','normal_source_recipe','host_source_entries','user_zero_package_inventory',
              'deadline_monotonic_ns','comparison_only'}
        working=type(envelope) is dict and envelope.get('schema')=='droidloom.native-leaf-channel.v2'
        allowed=(keys|{'working_native_source'},keys|{'working_preparation_owner'}) if working else (keys,)
        need(type(envelope) is dict and set(envelope) in allowed and
            envelope['schema'] in ('droidloom.native-leaf-channel.v1','droidloom.native-leaf-channel.v2') and
            envelope['comparison_only'] is True and
            number(envelope['deadline_monotonic_ns'],1) and
            0<envelope['deadline_monotonic_ns']-time.monotonic_ns()<=7200*10**9,
            'ORIGINAL_NORMAL_LEAF_ABSOLUTE_DEADLINE_REQUIRED')
        self.deadline_ns=envelope['deadline_monotonic_ns']
        self.working_native_source=(validate_working_native_source(envelope['working_native_source'])
                                    if 'working_native_source' in envelope else None)
        self.working_preparation_owner=(validate_working_preparation_owner(envelope['working_preparation_owner'])
                                       if 'working_preparation_owner' in envelope else None)
        self.core=validate_core(envelope['baseline'])
        self.user_zero_package_inventory=envelope['user_zero_package_inventory']
        self.user_zero_records=inventory_table(self.user_zero_package_inventory,self.core)
        self.normal_host_release=self.core['main']['normal_host_release']
        self.normal_source_recipe=envelope['normal_source_recipe']
        need(type(self.normal_source_recipe) is dict and set(self.normal_source_recipe)=={'bytes','sha256'} and
             number(self.normal_source_recipe['bytes'],1,16*1024*1024) and
             type(self.normal_source_recipe['sha256']) is str and
             re.fullmatch('[0-9a-f]{64}',self.normal_source_recipe['sha256']),
             'SAME_COMPILED_NORMAL_SOURCE_RECIPE_REQUIRED')
        self.host_source_entries=envelope['host_source_entries']
        need(type(self.host_source_entries) is dict and set(self.host_source_entries)==HOST_CHILDREN,
             'EXACT_FIXED_HOST_SOURCE_ENTRY_SET_REQUIRED')
        for path,pin in self.host_source_entries.items():
            need(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==path and
                 number(pin['bytes'],1,2*1024*1024) and type(pin['sha256']) is str and
                 re.fullmatch('[0-9a-f]{64}',pin['sha256']),
                 'EXACT_COMPILED_HOST_ENTRY_PIN_REQUIRED')
        self.guard_identity=metadata(self.guard_fd)
        need(stat.S_ISSOCK(os.fstat(self.guard_fd).st_mode),'PRIVATE_CHECK_ENDPOINT_REQUIRED')
        with socket.socket(fileno=os.dup(self.guard_fd)) as sock:
            need(sock.family==socket.AF_UNIX and sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)==socket.SOCK_DGRAM and
                 sock.getsockname() in ('',b'') and sock.getpeername() in ('',b''),
                 'UNNAMED_NORMAL_CHECK_SOCKETPAIR_REQUIRED')
        self.guard()

    def working_runtime_root(self):
        return working_runtime_root(self)

    def validate_inventory_comparison(self,value):
        # A stored pre-install table is compared explicitly by the fixed IHG
        # source/install chain. It is never a replacement for this live token.
        return inventory_table(value,self.core)

    @property
    def deadline(self):return self.deadline_ns/10**9
    def remaining(self,maximum=2):
        need(self.pid==os.getpid(),'COMPARISON_CHANNEL_CANNOT_BE_REUSED_AFTER_FORK')
        left=(self.deadline_ns-time.monotonic_ns())/10**9
        need(left>0,'ORIGINAL_NATIVE_LEAF_BUDGET_EXPIRED')
        return min(maximum,left)
    def guard(self):
        timeout=self.remaining()
        need(metadata(self.facts_fd)==self.before and
             metadata(self.guard_fd)==self.guard_identity and
             fcntl.fcntl(self.facts_fd,fcntl.F_GET_SEALS)==SEALS and
             os.pread(self.facts_fd,MAX_FACTS+1,0)==self.raw,
             'HELD_NORMAL_COMPARISON_DESCRIPTOR_CHANGED')
        with socket.socket(fileno=os.dup(self.guard_fd)) as sock:
            sock.settimeout(timeout)
            need(sock.send(b'G')==1,'NORMAL_CUSTODY_CHECK_NOT_SENT')
            raw,ancillary,flags,_=sock.recvmsg(2,0)
            need(raw==b'0' and not ancillary and flags==0,
                 'ACTUAL_NORMAL_CUSTODY_CHECK_FAILED')
        self.remaining()
        return {'schema':'droidloom.native-leaf-local-check.v1',
            'actual_main_epoch':self.core['main']['epoch'],
            'core_sha256':sha(canonical(self.core)),
            'local_held_peer_proc_namespace_data_checked':True,
            'fresh_full_main_rpc':False,'business_acceptance_evaluated':False}
    def observe_running_engine(self):
        """Synchronize one parent-owned live observation after cleanup ownership.
        Only the sealed original work deadline bounds this wait. The parent
        keeps its fixed <=70-second request inside that same deadline.
        """
        end_ns=self.deadline_ns
        def left():
            self.remaining(7200)
            value=(end_ns-time.monotonic_ns())/10**9
            need(value>0,'ORIGINAL_RUNNING_ENGINE_WINDOW_EXPIRED')
            return value
        def held():
            need(metadata(self.facts_fd)==self.before and
                 metadata(self.guard_fd)==self.guard_identity and
                 fcntl.fcntl(self.facts_fd,fcntl.F_GET_SEALS)==SEALS and
                 os.pread(self.facts_fd,MAX_FACTS+1,0)==self.raw,
                 'HELD_NORMAL_COMPARISON_DESCRIPTOR_CHANGED')
        held()
        interrupted=None;reply=None;pending=False
        try:
            with socket.socket(fileno=os.dup(self.guard_fd)) as sock:
                try:
                    sock.settimeout(left())
                    # Mark before send: an interrupted send has unknown delivery.
                    # It is never resent, and an unsynchronized endpoint is retired.
                    pending=True
                    need(sock.send(b'E')==1,'FIXED_RUNNING_ENGINE_CHECK_NOT_SENT')
                    while reply is None:
                        sock.settimeout(left())
                        try:
                            reply=sock.recvmsg(2,0)
                        except OSError:
                            raise
                        except BaseException as error:
                            # Preserve a signal exception, but consume the one
                            # outstanding reply before the original finally sends G.
                            if interrupted is None:interrupted=error
                finally:
                    if pending and reply is None:
                        try:sock.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                        os.environ.pop(GUARD_ENV,None)
                        try:os.close(self.guard_fd)
                        except OSError:pass
        except BaseException as error:
            if interrupted is not None and error is not interrupted:
                interrupted.add_note('RUNNING_ENGINE_REPLY_NOT_SYNCHRONIZED_ENDPOINT_RETIRED')
                raise interrupted from error
            raise
        if interrupted is not None:raise interrupted
        raw,ancillary,flags,_=reply
        need(raw==b'E' and not ancillary and flags==0,
             'ACTUAL_RUNNING_ENGINE_OBSERVATION_FAILED')
        left();held()
        # Consume the E reply before a subsequent local G. No new JSON/PID/UID/
        # ABI/path authority is returned; the real opaque fact stays in Rust.
        return None

    def inherit_for_host(self,argv,environment,pass_fds=()):
        self.guard()
        return inherit_for_host(argv,environment,pass_fds)
    def require_core(self,value):
        self.guard()
        need(value==self.core,'SAVED_NATIVE_LEAF_COMPARISON_DIFFERS_FROM_LIVE_OWNER')
        return self.guard()

def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None
def _absolute(value):
    return type(value) is str and len(value)<=4096 and value.startswith('/') and \
        '\0' not in value and all(p not in ('','.','..') for p in value.split('/')[1:])
def fixed_child(argv,pass_fds):
    """Pure exact call-shape selection. It grants no caller-selected command."""
    if type(argv) not in (list,tuple) or len(argv)<4:return None
    argv=list(argv)
    # The two real UI callers use -I without -B. Keep that exact source shape
    # separate from the three other fixed host children.
    if argv[:2]==['/usr/bin/python3','-I'] and argv[2] in UI_CHILDREN:
        entry=argv[2]
        need(len(argv)>=12 and argv[3] in ('client','backend') and
             argv[4]=='--scope' and _absolute(argv[5]) and
             argv[6]=='--expect-scope-sha256' and _hash(argv[7]) and
             argv[8]=='--step' and type(argv[9]) is str and
             re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',argv[9]) and
             argv[10]=='--command' and type(argv[11]) is str and
             re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',argv[11]) and
             ((argv[3]=='backend' and len(argv)==12) or
              (argv[3]=='client' and 13<=len(argv)<=128 and argv[12]=='--')) and
             not pass_fds,'EXACT_FIXED_UI_HOST_CHILD_REQUIRED')
        return entry,None
    if argv[:3]!=['/usr/bin/python3','-I','-B']:return None
    entry=argv[3]
    common=(len(argv)>=13 and argv[4]=='--preparation' and
        _absolute(argv[5]) and str(Path(argv[5]).parent)==str(ROOT/'preparations') and
        argv[6]=='--expect-preparation-sha256' and _hash(argv[7]))
    if entry==CLOCK_CHILD:
        need(common and len(argv)==19 and argv[8:10]==['execute-worker','--request'] and
             _absolute(argv[10]) and argv[11]=='--expect-request-sha256' and _hash(argv[12]) and
             argv[13]=='--monitor-fd' and type(argv[14]) is str and argv[14].isdecimal() and
             argv[15]=='--monitor-parent' and _absolute(argv[16]) and
             argv[17]=='--expect-monitor-parent-sha256' and _hash(argv[18]) and
             tuple(pass_fds)==(int(argv[14]),) and int(argv[14])>=3,
             'EXACT_CLOCK_WORKER_WITH_ITS_MONITOR_FD_REQUIRED')
        need(stat.S_ISSOCK(os.fstat(pass_fds[0]).st_mode),'ACTUAL_CLOCK_MONITOR_SOCKET_REQUIRED')
        return entry,None
    if entry==IHG_CHILD:
        coordinator=(common and len(argv)==13 and argv[8] in ('clock-worker','ihg-coordinator') and
            argv[9]=='--request' and _absolute(argv[10]) and
            argv[11]=='--expect-request-sha256' and _hash(argv[12]))
        phase=(common and len(argv)==15 and argv[8:10]==['ihg-worker','--scope'] and
            _absolute(argv[10]) and argv[11]=='--expect-scope-sha256' and _hash(argv[12]) and
            argv[13]=='--phase' and argv[14] in ('launch','inspect','cleanup'))
        need((coordinator or phase) and not pass_fds,'EXACT_IHG_HOST_WORKER_REQUIRED')
        return entry,None
    if type(entry) is str and re.fullmatch(r'/proc/self/fd/[0-9]+',entry):
        fd=int(entry.rsplit('/',1)[1])
        # This branch is only the already-held fixed Camera source, not a
        # delegation to another descriptor or arbitrary /proc executable.
        if not (common and len(argv)==13 and argv[8:10]==['execute','--request'] and
                _absolute(argv[10]) and argv[11]=='--expect-request-sha256' and _hash(argv[12]) and
                tuple(pass_fds)==(fd,) and fd>=3):
            return None
        need(os.readlink(entry)==CAMERA_CHILD,'ONLY_NAMED_FIXED_CAMERA_SOURCE_FD_MAY_INHERIT')
        return CAMERA_CHILD,fd
    return None

def verify_host_source(channel,path,held_fd=None):
    pin=channel.host_source_entries[path]
    source=Path(path);owned=[]
    try:
        parent=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);owned.append(parent)
        parents=[]
        for part in source.parts[1:-1]:
            child=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            owned.append(child);st=os.fstat(child)
            need(stat.S_ISDIR(st.st_mode) and st.st_uid==st.st_gid==0 and
                 stat.S_IMODE(st.st_mode)==0o755,'NORMAL_INSTALLED_HOST_SOURCE_PARENT_REQUIRED')
            parents.append((parent,part,child,(st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid)))
            parent=child
        fd=os.open(source.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);owned.append(fd)
        first=metadata(fd);st=os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and st.st_nlink==1 and
             stat.S_IMODE(st.st_mode)==0o444 and st.st_size==pin['bytes'],
             'EXACT_INSTALLED_HOST_SOURCE_REQUIRED')
        if held_fd is not None:need(metadata(held_fd)==first,'HELD_CAMERA_SOURCE_DIFFERS_FROM_NAMED_RECIPE_SOURCE')
        raw=bytearray()
        while len(raw)<=pin['bytes']:
            channel.remaining();part=os.read(fd,min(65536,pin['bytes']+1-len(raw)))
            if not part:break
            raw.extend(part)
        need(len(raw)==pin['bytes'] and sha(raw)==pin['sha256'] and
             first==metadata(fd)==tuple(getattr(os.stat(source.name,dir_fd=parent,follow_symlinks=False),k) for k in META),
             'COMPILED_HOST_SOURCE_FULL_READBACK_REQUIRED')
        if held_fd is not None:need(metadata(held_fd)==first,'HELD_CAMERA_SOURCE_CHANGED')
        for directory,name,child,identity in parents:
            named=os.stat(name,dir_fd=directory,follow_symlinks=False);held=os.fstat(child)
            need(identity==(named.st_dev,named.st_ino,named.st_mode,named.st_uid,named.st_gid)==
                 (held.st_dev,held.st_ino,held.st_mode,held.st_uid,held.st_gid),
                 'HOST_SOURCE_PARENT_CHANGED')
    finally:
        for fd in reversed(owned):os.close(fd)

def inherit_for_host(argv,environment,pass_fds):
    """Only exact fixed host callers receive the two comparison descriptors."""
    env=dict(environment)
    for key in (FACTS_ENV,GUARD_ENV):env.pop(key,None)
    selected=fixed_child(argv,pass_fds)
    if selected is None:
        # In particular the seven-FD mapped namespace helper keeps exactly its
        # original authority set and receives no host-only comparison endpoint.
        return env,tuple(pass_fds)
    channel=ComparisonChannel();channel.guard()
    path,held_fd=selected
    verify_host_source(channel,path,held_fd)
    pair=(channel.facts_fd,channel.guard_fd)
    need(not set(pass_fds)&set(pair),'COMPARISON_AND_EXISTING_FDS_MUST_BE_DISTINCT')
    for key,fd in zip((FACTS_ENV,GUARD_ENV),pair):env[key]=str(fd)
    channel.guard()
    return env,tuple(pass_fds)+pair


def validate_working_native_source(value):
    """Validate comparison shape; only the retained Rust owner grants custody."""
    need(type(value) is dict and set(value)=={
        'schema','custody','selection','catalog','comparison_only'} and
        value['schema']=='droidloom.working-native-source-comparison.v1' and
        value['comparison_only'] is True,'EXACT_WORKING_SOURCE_COMPARISON_REQUIRED')
    owner=value['custody']
    need(type(owner) is dict and set(owner)=={
        'schema','runtime_evidence_directory','fresh_source_lock','fresh_application_lock',
        'applications','actual_pid','historical_original_lock_identity_claimed',
        'runtime_qualified','production_ready','physical_plan'} and
        owner['schema']=='droidloom.working-native-source-custody.v1' and
        owner['historical_original_lock_identity_claimed'] is False and
        owner['runtime_qualified'] is False and owner['production_ready'] is False and
        number(owner['actual_pid'],2,2**32-1),
        'ACTUAL_WORKING_OWNER_COMPARISON_REQUIRED')
    root=owner['runtime_evidence_directory']
    need(type(root) is str and re.fullmatch(
        r'/var/lib/droidloom/qualification/working-qualification-[0-9a-f]{64}/runtime-evidence',root),
        'EXACT_ADMITTED_WORKING_RUNTIME_DIRECTORY_REQUIRED')
    def pin(row,path=None):
        need(type(row) is dict and set(row)=={'path','bytes','sha256'} and
             type(row['path']) is str and number(row['bytes'],1,128*1024*1024) and
             type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['sha256']) and
             (path is None or row['path']==str(path)),'EXACT_WORKING_SOURCE_FILE_PIN_REQUIRED')
    def identity(row,mode=None):
        need(type(row) is list and len(row)==9 and all(number(v) for v in row) and
             row[3:6]==[0,0,1] and (mode is None or row[2]==mode),
             'ACTUAL_ROOT_SOURCE_F9_REQUIRED')
    locks=[]
    for key,name in [('fresh_source_lock','source.lock'),('fresh_application_lock','application.lock')]:
        row=owner[key]
        need(type(row) is dict and set(row)=={'name','f9'} and row['name']==name,
             'DISTINCT_WORKING_SOURCE_LOCK_ROLES_REQUIRED')
        identity(row['f9'],stat.S_IFREG|0o600)
        need(row['f9'][6]==0,'EMPTY_FRESH_WORKING_LOCK_REQUIRED')
        locks.append(row['f9'][:2])
    need(locks[0]!=locks[1],'WORKING_LOCK_ROLES_CANNOT_SHARE_AN_INODE')
    app=owner['applications']
    need(type(app) is dict and set(app)=={'path','bytes','sha256','f9'},
         'EXACT_INSTALLED_APPLICATIONS_COMPARISON_REQUIRED')
    pin({k:app[k] for k in ('path','bytes','sha256')},'/usr/bin/droidloom-applications')
    identity(app['f9'])
    need(app['f9'][6]==app['bytes'] and stat.S_ISREG(app['f9'][2]) and
         app['f9'][2]&0o6022==0 and app['f9'][2]&0o111!=0,
         'ACTUAL_INSTALLED_APPLICATIONS_ELF_REQUIRED')
    pin(value['selection'],ROOT/'selection/selection-14.json')
    pin(value['catalog'])
    need(value['catalog']['path']=='/etc/droidloom/native-application-leaves/catalogs/'+
         value['catalog']['sha256']+'.json','COMPILED_WORKING_CATALOG_PATH_REQUIRED')
    plan=owner['physical_plan']
    need(type(plan) is dict and set(plan)=={'path','bytes','sha256','f9'},
         'ACTUAL_AUTHENTICATED_PHYSICAL_PLAN_REQUIRED')
    pin({k:plan[k] for k in ('path','bytes','sha256')})
    identity(plan['f9'],stat.S_IFREG|0o400)
    need(plan['f9'][6]==plan['bytes'] and Path(plan['path']).is_relative_to(root),
         'WORKING_PLAN_MUST_REMAIN_IN_THIS_ACTUAL_RUNTIME_DIRECTORY')
    return value


def working_release(legacy,preparation_ref,channel):
    """Borrow the actual live Rust source owner, retaining normal source FDs.

    This adapter cannot mint a Rust lease. Each guard asks the already inherited
    private channel to revalidate the opaque source owner and original deadline.
    The original resource class still observes the real native parent/cgroup.
    """
    source=channel.working_native_source
    need(channel.working_preparation_owner is None,'PREPARATION_OWNER_CANNOT_EXECUTE_AN_APPLICATION_LEAF')
    if source is None:return None
    base=legacy['ReleaseLease']
    class WorkingLease(base):
        def __init__(self):
            need(os.getuid()==os.geteuid()==0,'ACTUAL_ROOT_WORKING_LEAF_REQUIRED')
            self.pid=os.getpid();self.closed=False
            self.directories={};self.files=[];self.lock_fds=[]
            self.resource_scope=None;self.release_ref=None
            self.preparation_ref=dict(preparation_ref);self.working_channel=channel
            self.working_source=source
            try:
                channel.guard()
                owner=source['custody']
                need(os.getppid()==owner['actual_pid'],'ACTUAL_RUST_WORKING_PARENT_REQUIRED')
                select_pin=source['selection'];catalog_pin=source['catalog']
                selection=legacy['parse'](self._file(Path(select_pin['path']),select_pin,1024*1024,root_owned=True))
                catalog=legacy['parse'](self._file(Path(catalog_pin['path']),catalog_pin,65536,root_owned=True))
                selected=legacy['selected_preparation'](catalog,selection,preparation_ref)
                self._file(Path(preparation_ref['path']),preparation_ref,1024*1024,root_owned=True)
                self._file(Path(selected['entry']['path']),selected['entry'],262144,root_owned=True)
                app=owner['applications']
                self.cli_reference={k:app[k] for k in ('path','bytes','sha256')}
                self._file(legacy['CLI'],self.cli_reference,128*1024*1024,root_owned=True,executable=True)
                actual=next(identity for _,identity,_,_,ref in self.files
                            if ref['path']==str(legacy['CLI']))
                need(actual==app['f9'],'HELD_APPLICATIONS_ELF_DIFFERS_FROM_ACTUAL_RUST_OWNER')
                self.guard()
            except BaseException:
                self.close();raise
        def guard(self):
            need(not self.closed and os.getpid()==self.pid,'SAME_WORKING_LEAF_PROCESS_REQUIRED')
            self.working_channel.guard()
            for path,(fd,identity,parent,name,required) in self.directories.items():
                need(legacy['f9'](os.fstat(fd))[:6]==identity==legacy['f9'](os.lstat(path))[:6],
                     'WORKING_SOURCE_DIRECTORY_CHANGED')
                if parent is not None:
                    need(legacy['f9'](os.stat(name,dir_fd=parent,follow_symlinks=False))[:6]==identity,
                         'WORKING_SOURCE_DIRECTORY_LINK_CHANGED')
            for fd,identity,parent,name,reference in self.files:
                need(legacy['f9'](os.fstat(fd))==identity==
                     legacy['f9'](os.stat(name,dir_fd=parent,follow_symlinks=False)),
                     'WORKING_SOURCE_FILE_IDENTITY_CHANGED')
                need(hashlib.sha256(self._body(fd,identity[6])).hexdigest()==reference['sha256'],
                     'WORKING_SOURCE_FILE_BODY_CHANGED')
                need(legacy['f9'](os.fstat(fd))==identity==
                     legacy['f9'](os.stat(name,dir_fd=parent,follow_symlinks=False)),
                     'WORKING_SOURCE_CHANGED_DURING_BOOKEND')
            if self.resource_scope is not None:self.resource_scope.report()
            self.working_channel.guard()
            return dict(self.cli_reference)
    return WorkingLease()


def validate_working_preparation_owner(value):
    need(type(value) is dict and set(value)=={
        'schema','runtime_evidence_directory','actual_pid','comparison_only'} and
        value['schema']=='droidloom.working-native-preparation-comparison.v1' and
        value['comparison_only'] is True and number(value['actual_pid'],2,2**32-1) and
        type(value['runtime_evidence_directory']) is str and re.fullmatch(
            r'/var/lib/droidloom/qualification/working-qualification-[0-9a-f]{64}/runtime-evidence',
            value['runtime_evidence_directory']),
        'EXACT_ACTUAL_PREPARATION_OWNER_COMPARISON_REQUIRED')
    return value


def working_runtime_root(channel):
    """Read-only pathname derived from the actual retained source owner."""
    channel.guard()
    value=(channel.working_native_source['custody'] if channel.working_native_source is not None
           else channel.working_preparation_owner)
    return Path(value['runtime_evidence_directory']) if value is not None else None
