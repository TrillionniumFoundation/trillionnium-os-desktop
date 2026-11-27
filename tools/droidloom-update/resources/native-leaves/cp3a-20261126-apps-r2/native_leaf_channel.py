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
        need(type(envelope) is dict and set(envelope)=={
            'schema','baseline','normal_source_recipe','host_source_entries','user_zero_package_inventory',
            'deadline_monotonic_ns','comparison_only'} and
            envelope['schema']=='droidloom.native-leaf-channel.v1' and
            envelope['comparison_only'] is True and
            number(envelope['deadline_monotonic_ns'],1) and
            0<envelope['deadline_monotonic_ns']-time.monotonic_ns()<=7200*10**9,
            'ORIGINAL_NORMAL_LEAF_ABSOLUTE_DEADLINE_REQUIRED')
        self.deadline_ns=envelope['deadline_monotonic_ns']
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
