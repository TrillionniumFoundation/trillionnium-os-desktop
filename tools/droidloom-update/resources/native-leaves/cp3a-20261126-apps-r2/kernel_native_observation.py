"""Current kernel-first leaf comparisons, subordinate to the live Rust owner.

The Rust producer/leaf runner supplies the actual Main, actual PM token, target
working-directory metadata and a private bounded check channel. This module
does not authenticate a socket peer, admit a saved owner, select an alternative
Main, or mint a business gate. It preserves actual proc/PIDFD/root/namespace,
normal service, classpath and fixed readonly helper observations.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import time
import types

ROOT=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2')
MAIN=ROOT/'source/main'
QUALIFICATION=Path('/var/lib/droidloom/qualification/pocket4')
CHANNEL_SHA='3ec881482aef5bffb2c9d05e79d6ca3f44cd3c0d94a36c3c1dd7fd995e5e7ac1'
DATA_SHA='700c81b80bf8378cb1d3e2e916d82ba3a9004bfb9d2d75c9aab7773a8c3c98ed'
ANCESTRY_SHA='824492a2e9068aa30c3d5dc148402802843a3aaa574c41c290819a9f3d65d201'
EPOCH_SHA='ba4854fcc42def3fb37ac8add1e2b4382d24cb716e2d8181e84b286d5975c377'
READER_SHA='3d2860cde4ec7c7cbe67ed4756d9f599646ee39dc36f2f80b3ef008fba6b80cb'
CAPTURE_SHA='eac7d44f24f299718dd4f090a2aecfe1e40bace3578c0ddb15831357615dabff'
HELPER_SHA='3a3dd3037c03c09fd7ebc1068123a202a29d286c1bf77fb81a4476fb25576a3c'
READONLY_SHA='98f6af7733896835da8d375a950a5cc0de01bd4429622c8ada230a869efc25d1'
COMMANDS_SHA='25aac17bf57736ab0a6680b2da2304cc2b68fec31c1f9c421d62b2bcbf1a759a'
SCHEMA='droidloom.native-leaf-business-baseline.v1'
QUAL_SCHEMA='droidloom.native-leaf-business-qualification.v1'
RUNTIME_SCHEMA='droidloom.native-leaf-runtime-comparison.v1'
ROLES=('daemon','presenter','init','zygote64','system_server','surfaceflinger')
ANDROID=('init','zygote64','system_server','surfaceflinger')
NS=('user','mnt','pid','uts','ipc','net','cgroup')
PROGRAM='/usr/lib/droidloom/production/current/droidloomd'
PRESENTER='/usr/bin/droidloom-wayland'
ENGINE='/system/system_ext/lib64/libberberis_arm64.so'
SYSTEM_UNIT='droidloom-production.service'
USER_UNIT='droidloom-production-desktop.service'
CGROUP='/system.slice/droidloom-production.service'
PAYLOAD_CGROUP=CGROUP+'/cell-u1000/payload/'
LIMITS={'cpu.max':'600000 100000','memory.high':'6442450944',
        'memory.max':'8589934592','memory.swap.max':'0','pids.max':'32768'}
META=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def need(value,code):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def parse(raw):
    def pairs(rows):
        out={}
        for key,value in rows:
            need(key not in out,'DUPLICATE_NATIVE_LEAF_BASELINE_FIELD');out[key]=value
        return out
    def bad(_):raise RuntimeError('NONFINITE_NATIVE_LEAF_BASELINE_FIELD')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
def metadata(fd):return {key:getattr(os.fstat(fd),key) for key in META}
def node(fd):
    st=os.fstat(fd);return {'device':st.st_dev,'inode':st.st_ino}
def root_parents(path,private=False):
    need(path.is_absolute() and path.resolve()==path,'CANONICAL_NATIVE_LEAF_FILE_REQUIRED')
    for parent in path.parents:
        st=parent.lstat()
        need(stat.S_ISDIR(st.st_mode) and st.st_uid==st.st_gid==0 and not st.st_mode&0o022,
             'ROOT_PROTECTED_NATIVE_LEAF_PARENT_REQUIRED')
    if private:
        need(path.is_relative_to(QUALIFICATION) and
             stat.S_IMODE(path.parent.lstat().st_mode)==0o700,
             'PRIVATE_NORMAL_BASELINE_DIRECTORY_REQUIRED')
def read_ref(ref,maximum=16*1024*1024,source=False):
    need(type(ref) is dict and set(ref) in ({'path','sha256'},{'path','bytes','sha256'}) and
         type(ref['path']) is str and type(ref['sha256']) is str and
         re.fullmatch('[0-9a-f]{64}',ref['sha256']),'EXACT_NATIVE_LEAF_FILEPIN_REQUIRED')
    path=Path(ref['path']);root_parents(path,private=not source)
    if source:need(path.is_relative_to(ROOT),'FIXED_COHORT_SOURCE_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=metadata(fd)
        need(stat.S_ISREG(before['st_mode']) and before['st_uid']==before['st_gid']==0 and
             before['st_nlink']==1 and 0<before['st_size']<=maximum and
             stat.S_IMODE(before['st_mode'])==(0o444 if source else 0o600),
             'SEALED_SOURCE_OR_PRIVATE_NORMAL_BASELINE_REQUIRED')
        raw=bytearray();end=time.monotonic()+10
        while True:
            need(time.monotonic()<end,'NATIVE_LEAF_FILE_READ_DEADLINE')
            block=os.read(fd,min(65536,maximum+1-len(raw)))
            if not block:break
            raw.extend(block);need(len(raw)<=maximum,'NATIVE_LEAF_FILE_GREW')
        named=path.lstat()
        need(before==metadata(fd)=={k:getattr(named,k) for k in META} and
             len(raw)==before['st_size'] and sha(raw)==ref['sha256'] and
             ('bytes' not in ref or ref['bytes']==len(raw)),'NATIVE_LEAF_FILE_BOOKEND_CHANGED')
        return bytes(raw)
    finally:os.close(fd)
def load(path,pin,name):
    raw=read_ref({'path':str(path),'sha256':pin},1024*1024,source=True)
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module
def data_module():
    # Only its original duplicate-safe parser and mapped namespace reader are
    # reused. The historical 45-package/predeployment measure is never called.
    return load(ROOT/'source/support/business_data.py',DATA_SHA,'native_leaf_data_read_helpers')
def channel():
    return load(MAIN/'native_leaf_channel.py',CHANNEL_SHA,'native_leaf_private_comparison').ComparisonChannel()
def exact_epoch(boot,processes):
    binding={'boot_id':boot,'processes':processes}
    return {'schema':'pocket4-framework-epoch-v1','binding':binding,'sha256':sha(canonical(binding))}
def target_data(core):
    app=core['application'];data=core['data'];origin=core['main']['persistent_data']['original_copy_origin']
    rows={}
    for row in data['directories'][2:]:
        prefix=row['path'].removeprefix('/data/')
        rows[prefix]={'device':row['device'],'inode':row['inode'],'mount_id':row['mount_id'],
            'mode':row['mode'],'uid':row['host_uid'],'gid':row['host_gid']}
    return {'schema':'droidloom.native-leaf-target-working-data.v1',
        'scope':'actual_inspected_user_0_package_only',
        'package_uids':{app['package']:app['uid']},'directories':rows,
        'working_data_root':data['data_root'],'original_copy_origin':origin,
        'original_directory_identity_compared':False,'account_contents_read':False}

def validate_process_against_main(role,identity,held,core):
    key={'init':'init','zygote64':'zygote','system_server':'framework'}.get(role)
    if key:
        actual=core['main'][key]
        need(all(identity[name]==actual[name] for name in
             ('host_pid','parent_host_pid','start_ticks')) and
             node(held['pidfd'])==actual['pidfd'] and node(held['root'])==actual['root'] and
             node(held['exe'])==actual['executable'],'ACTUAL_PROCESS_DIFFERS_FROM_RUST_MAIN')
        values=core['main']['owner']['namespaces'] if role=='init' else (
            core['main']['framework_namespaces'] if role=='system_server' else None)
        if values is not None:
            for item in values:
                name='mnt' if item['name']=='mount' else item['name']
                need(node(held['namespaces'][name])=={'device':item['device'],'inode':item['inode']},
                     'ACTUAL_NAMESPACES_DIFFER_FROM_RUST_MAIN')
    elif role=='daemon':
        need(identity['host_pid']==core['peer']['pid'] and
             identity['start_ticks']==core['peer']['start_ticks'] and
             identity['uids']==[0]*4 and identity['executable']==PROGRAM and
             identity['cmdline']==[PROGRAM,'--socket','/run/droidloom/control.sock'],
             'ACTUAL_NORMAL_BROKER_DIFFERS_FROM_RUST_PEER')
    elif role=='presenter':
        need(identity['uids']==[1000]*4 and identity['executable']==PRESENTER and
             identity['cmdline']==[PRESENTER,'--production'],
             'ACTUAL_NORMAL_PRODUCTION_PRESENTER_REQUIRED')
    else:
        need(role=='surfaceflinger' and identity['executable']=='/system/bin/surfaceflinger' and
             identity['cmdline']==['/system/bin/surfaceflinger'] and
             identity['parent_host_pid']==core['main']['init']['host_pid'],
             'ACTUAL_CURRENT_SURFACEFLINGER_REQUIRED')

class Observation:
    def __init__(self,live,expected=None,seconds=120):
        self.live=live;self.core=live.core;self.expected=expected
        self.deadline=min(time.monotonic()+seconds,live.deadline)
        self.data=data_module()
        self.epoch=load(MAIN/'framework_epoch.py',EPOCH_SHA,'native_leaf_actual_epoch')
        self.reader=load(MAIN/'held_runtime.py',READER_SHA,'native_leaf_actual_root_reader')
        self.ancestry=load(MAIN/'cell_ancestry.py',ANCESTRY_SHA,'native_leaf_actual_fd_helpers')
        self.host=load(MAIN/'capture_main.py',CAPTURE_SHA,'native_leaf_existing_bounded_unit_reader')
        self.pool=self.ancestry.ManagedFDs();self.handles={};self.main_user_namespace=None
        self.rows={};self.android_environment=None;self.units=None;self.child_selection=None
        self.programs=None
    def check(self):
        need(time.monotonic()<self.deadline,'ORIGINAL_NATIVE_LEAF_OBSERVATION_DEADLINE')
    def _unit_rows(self):
        self.check();self.live.guard()
        account=pwd.getpwuid(1000)
        need(account.pw_uid==1000 and re.fullmatch('[a-z_][a-z0-9_-]{0,63}',account.pw_name),
             'ACTUAL_NORMAL_DESKTOP_ACCOUNT_REQUIRED')
        user=['/usr/sbin/runuser','-u',account.pw_name,'--','/usr/bin/env',
              'XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
              '/usr/bin/systemctl','--user']
        rows={'daemon':self.host.show(['/usr/bin/systemctl'],SYSTEM_UNIT,seconds=min(3,self.live.remaining(3))),
              'presenter':self.host.show(user,USER_UNIT,seconds=min(3,self.live.remaining(3)))}
        self.check();self.live.guard()
        need(int(rows['daemon']['MainPID'])==self.core['peer']['pid'] and
             rows['daemon']['ControlGroup']==CGROUP and
             re.fullmatch('[0-9a-f]{32}',rows['daemon']['InvocationID']) and
             re.fullmatch('[0-9a-f]{32}',rows['presenter']['InvocationID']) and
             rows['presenter']['ControlGroup'].startswith('/user.slice/user-1000.slice/') and
             rows['presenter']['ControlGroup'].endswith('/'+USER_UNIT),
             'ACTUAL_FIXED_NORMAL_SERVICE_INVOCATIONS_REQUIRED')
        return rows
    def _children(self,proc,pid):
        task=self.pool.own(os.open('task',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                  dir_fd=proc),'init_tasks')
        try:
            names=os.listdir(task)
            need(0<len(names)<=256 and all(re.fullmatch('[1-9][0-9]{0,9}',v) for v in names),
                 'FIXED_MAIN_INIT_THREAD_BOUND')
            tids=sorted(map(int,names));need(pid in tids,'ACTUAL_MAIN_INIT_THREAD_REQUIRED')
            rows={};flat=[]
            for tid in tids:
                self.check()
                thread=self.pool.own(os.open(str(tid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                            dir_fd=task),'init_thread')
                try:
                    raw=self.ancestry.read_proc_leaf(self.pool,thread,'children',65536,self.check)
                    need(all(c in b'0123456789 \t\n' for c in raw),'ACTUAL_INIT_CHILD_LIST_REQUIRED')
                    values=[int(v) for v in raw.split()]
                    need(len(values)<=1024 and len(values)==len(set(values)) and
                         all(1<v<2**31 for v in values),'ACTUAL_INIT_CHILD_BOUND')
                    rows[str(tid)]=sorted(values);flat.extend(values)
                finally:self.pool.close(thread)
            need(len(flat)<=4096 and len(flat)==len(set(flat)) and
                 sorted(os.listdir(task))==sorted(names),'ACTUAL_INIT_CHILDREN_CHANGED')
            return {'thread_ids':tids,'per_thread':rows,'child_host_pids':sorted(flat)}
        finally:self.pool.close(task)
    def _surfaceflinger(self):
        init=self.core['main']['init']['host_pid']
        pidfd=self.pool.own(os.pidfd_open(init,0),'discovery_init_pidfd')
        proc=self.pool.own(os.open('/proc/'+str(init),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),
                           'discovery_init_proc')
        try:
            need(node(pidfd)==self.core['main']['init']['pidfd'],'EXACT_RUST_INIT_PIDFD_REQUIRED')
            self.ancestry.require_pidfd_live(pidfd)
            first=self._children(proc,init);matches=[]
            for pid in first['child_host_pids']:
                self.check()
                child=self.pool.own(os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),
                                    'init_child_proc')
                try:
                    raw=self.ancestry.read_proc_leaf(self.pool,child,'cmdline',65536,self.check)
                    if raw==b'/system/bin/surfaceflinger\0':matches.append(pid)
                finally:self.pool.close(child)
            second=self._children(proc,init)
            self.ancestry.require_pidfd_live(pidfd);self.live.guard()
            need(first==second and len(matches)==1,'ONE_STABLE_SAME_MAIN_SURFACEFLINGER_REQUIRED')
            self.child_selection={'method':'actual_held_init_all_thread_direct_children',
                                  'selected_host_pid':matches[0],'initial_table':second}
            return matches[0]
        finally:self.pool.close(proc);self.pool.close(pidfd)
    def identities(self):
        self.check();self.live.guard()
        actual=self.epoch.capture_processes({name:row['host_pid'] for name,row in self.rows.items()})
        need(actual['binding']=={'boot_id':self.core['main']['epoch']['boot_id'],'processes':self.rows},
             'ACTUAL_NORMAL_PROCESS_GENERATION_CHANGED')
        if self.handles:
            for name,row in self.rows.items():
                if name in self.handles:
                    validate_process_against_main(name,row,self.handles[name],self.core)
        self.check();return actual['binding']['processes']
    def acquire(self):
        self.live.guard();self.units=self._unit_rows()
        if self.expected is None:
            sf=self._surfaceflinger()
        else:
            self.live.require_core(self.expected['native_owner'])
            need(self.units==self.expected['systemd_units'],'NORMAL_SERVICE_INVOCATION_CHANGED')
            sf=self.expected['main_epoch']['binding']['processes']['surfaceflinger']['host_pid']
            self.child_selection=self.expected['surfaceflinger_selection']
        chosen={'daemon':self.core['peer']['pid'],'presenter':int(self.units['presenter']['MainPID']),
                'init':self.core['main']['init']['host_pid'],'zygote64':self.core['main']['zygote']['host_pid'],
                'system_server':self.core['main']['framework']['host_pid'],'surfaceflinger':sf}
        need(len(set(chosen.values()))==6,'SIX_DISTINCT_ACTUAL_RUNTIME_PROCESSES_REQUIRED')
        value=self.epoch.capture_processes(chosen)
        need(value['binding']['boot_id']==self.core['main']['epoch']['boot_id'],'SAME_ACTUAL_BOOT_REQUIRED')
        self.rows=value['binding']['processes']
        if self.expected is not None:
            need(self.rows==self.expected['processes'],'ACTUAL_NORMAL_PROCESS_SET_CHANGED')
        for name,row in self.rows.items():
            pid=row['host_pid'];self.check()
            pidfd=self.pool.own(os.pidfd_open(pid,0),name+'_pidfd')
            proc=self.pool.own(os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),
                               name+'_proc')
            self.ancestry.require_pidfd_live(pidfd)
            root=self.pool.own(os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc),name+'_root')
            exe=self.pool.own(os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),name+'_exe')
            ns={k:self.pool.own(os.open('ns/'+k,os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc),name+'_ns_'+k) for k in NS}
            self.handles[name]={'pidfd':pidfd,'proc':proc,'root':root,'exe':exe,'namespaces':ns}
            validate_process_against_main(name,row,self.handles[name],self.core)
        self.identities()
        owner=self.core['main']['persistent_data']['user_namespace']
        owner={**owner,'link':'user:['+str(owner['inode'])+']'}
        host=self.pool.own(os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC),'host_user_namespace')
        self.main_user_namespace=self.data.userns_module().HeldMainUserNamespace(
            self.rows['init'],self.handles['init'],owner,host,self.core['main']['epoch']['boot_id'],self.identities)
        mapping=self.main_user_namespace.guard()
        for name in ('uid_map','gid_map'):
            need([{'inside':mapping[name]['inside'],'outside':mapping[name]['outside'],
                   'count':mapping[name]['count']}]==self.core['data'][name],
                 'PYTHON_AND_RUST_ACTUAL_ID_MAPS_DIFFER')
        if self.expected is not None:
            need(mapping==self.expected['main_user_namespace'],'ACTUAL_MAPPED_USER_NAMESPACE_CHANGED')
        self.programs=self.program_artifacts(None if self.expected is None else self.expected['installed_programs'])
        self.identities()
    def artifact(self,fd,limit=268435456):
        before=metadata(fd)
        need(stat.S_ISREG(before['st_mode']) and before['st_nlink']==1 and
             0<before['st_size']<=limit,'CURRENT_ARTIFACT_BOUND')
        os.lseek(fd,0,os.SEEK_SET);h=hashlib.sha256();count=0
        while True:
            self.check();part=os.read(fd,min(131072,before['st_size']+1-count))
            if not part:break
            count+=len(part);need(count<=before['st_size'],'CURRENT_ARTIFACT_GREW');h.update(part)
        need(count==before['st_size'] and metadata(fd)==before,'CURRENT_ARTIFACT_CHANGED')
        return {'bytes':count,'sha256':h.hexdigest(),'file':before}
    def guest(self,role,path,flags=os.O_RDONLY):
        self.check()
        return self.pool.own(self.reader.open_in_root(self.handles[role]['root'],path,flags),'guest_artifact')
    def program_artifacts(self,expected):
        # The source-owned Rust release reader must supply the selected normal
        # host program commitments. Root ownership alone is not that proof.
        contract=getattr(self.live,'normal_host_release',None)
        need(type(contract) is dict and contract.get('schema')=='droidloom.normal-host-release.v1' and
             set(contract)=={'schema','manager','presenter'} and
             contract['manager']['path']==PROGRAM and contract['presenter']['path']==PRESENTER,
             'ACTUAL_SELECTED_NORMAL_HOST_PROGRAMS_REQUIRED')
        output={}
        for role,path in (('daemon',PROGRAM),('presenter',PRESENTER)):
            root_parents(Path(path))
            named=self.pool.own(os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW),'named_normal_program')
            try:
                held=self.handles[role]['exe'];info=metadata(named)
                need(metadata(held)==info and info['st_uid']==info['st_gid']==0 and
                     stat.S_IMODE(info['st_mode'])==0o755 and info['st_nlink']==1,
                     'ACTUAL_RUNNING_NORMAL_PROGRAM_BACKING_REQUIRED')
                if expected is None:actual=self.artifact(held)
                else:
                    actual=expected[path]
                    need(info==actual['file'],'ACTUAL_NORMAL_PROGRAM_CHANGED')
                wanted=contract['manager' if role=='daemon' else 'presenter']
                need(actual['bytes']==wanted['bytes'] and actual['sha256']==wanted['sha256'],
                     'ACTUAL_NORMAL_PROGRAM_DIFFERS_FROM_SELECTED_RELEASE')
                if role=='daemon':
                    need(actual['bytes']==self.core['peer']['executable_bytes'] and
                         actual['sha256']==self.core['peer']['executable_sha256'],
                         'OBSERVED_NORMAL_PROGRAM_DIFFERS_FROM_AUTHENTICATED_PEER')
                need(metadata(named)==info==metadata(held),'NORMAL_PROGRAM_BOOKEND_CHANGED')
                output[path]=actual
            finally:self.pool.close(named)
        self.live.guard();return output
    def observe(self):
        value={'roles':self.identities(),'roots':{},'namespaces':{},'executables':{},
            'host_user_namespace':os.readlink('/proc/self/ns/user'),'limits':{},
            'main_user_namespace':self.main_user_namespace.guard(),'role_user_namespaces':{}}
        for role,h in self.handles.items():
            self.check();self.ancestry.require_pidfd_live(h['pidfd'])
            for leaf,flags,label in (('root',os.O_PATH|os.O_DIRECTORY,'roots'),('exe',os.O_RDONLY,'executables')):
                fd=self.pool.own(os.open(leaf,flags|os.O_CLOEXEC,dir_fd=h['proc']),'reopened_'+leaf)
                try:
                    need(node(fd)==node(h['root' if leaf=='root' else 'exe']),'HELD_ROLE_BACKING_CHANGED')
                    value[label][role]=node(fd) if leaf=='root' else metadata(fd)
                    if leaf=='exe':need(metadata(fd)==metadata(h['exe']),'HELD_EXECUTABLE_METADATA_CHANGED')
                finally:self.pool.close(fd)
            value['namespaces'][role]={}
            for name,held in h['namespaces'].items():
                link=os.readlink('ns/'+name,dir_fd=h['proc'])
                fd=self.pool.own(os.open('ns/'+name,os.O_RDONLY|os.O_CLOEXEC,dir_fd=h['proc']),'reopened_namespace')
                try:
                    actual=node(fd)
                    need(actual==node(held) and link==name+':['+str(actual['inode'])+']','HELD_NAMESPACE_CHANGED')
                    value['namespaces'][role][name]={'link':link,**actual}
                finally:self.pool.close(fd)
            fact=self.main_user_namespace.observe_role(h,self.rows[role],role)
            need(fact['user_namespace']==value['namespaces'][role]['user'],'ACTUAL_ROLE_USER_NAMESPACE_CHANGED')
            value['role_user_namespaces'][role]=fact
        for name in LIMITS:
            fd=self.pool.own(os.open('/sys/fs/cgroup'+CGROUP+'/'+name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC),
                               'normal_runtime_limit')
            try:value['limits'][name]=self.reader.read_fd(fd,8192,self.deadline).decode('ascii').strip()
            finally:self.pool.close(fd)
        need(value['limits']==LIMITS,'NORMAL_RUNTIME_LIMITS_CHANGED')
        need(self.rows['daemon']['cgroup'] in (['0::'+CGROUP],['0::'+CGROUP+'/broker']),
             'NORMAL_BROKER_CGROUP_CHANGED')
        for role in ANDROID:
            rows=[x[3:] for x in self.rows[role]['cgroup'] if x.startswith('0::')]
            need(len(rows)==1 and (rows[0]+'/'==PAYLOAD_CGROUP or rows[0].startswith(PAYLOAD_CGROUP)),
                 'ACTUAL_ANDROID_PROCESS_LEFT_NORMAL_PAYLOAD')
            need(value['roots'][role]==value['roots']['init'],'ACTUAL_ANDROID_ROOT_BACKING_DIFFERS')
        self.identities();self.live.guard()
        return value
    def classpaths(self,expected=None):
        raw=self.ancestry.read_proc_leaf(self.pool,self.handles['zygote64']['proc'],'environ',
                                        self.reader.ENV_LIMIT,self.check)
        values=self.reader.selected_classpaths(raw)
        self.android_environment=self.data.userns_module().android_environment(raw);del raw
        if self.expected is not None:
            need(self.android_environment==self.expected['android_env'],'CURRENT_ANDROID_ENVIRONMENT_CHANGED')
        paths=list(dict.fromkeys(p for k in self.reader.REQUIRED_CLASSPATHS for p in values[k].split(':')))
        need(0<len(paths)<=self.reader.PATH_COUNT_LIMIT,'CLASSPATH_PATH_BOUND')
        files=[];total=0
        if expected is not None:need(values==expected['values'] and len(paths)==len(expected['files']),
                                    'COMPLETE_CLASSPATH_SET_CHANGED')
        for index,path in enumerate(paths):
            left=self.guest('init',path);right=None
            try:
                right=self.guest('zygote64',path);a,b=metadata(left),metadata(right)
                need(a==b,'TWO_ACTUAL_CLASSPATH_ROOT_VIEWS_DIFFER')
                if expected is None:proof=self.artifact(left,self.reader.FILE_LIMIT)
                else:
                    old=expected['files'][index]
                    need(path==old['path'] and a==old['init_view'] and b==old['zygote_view'],
                         'CLASSPATH_BACKING_CHANGED')
                    proof={'sha256':old['sha256'],'bytes':old['bytes']}
                need(metadata(left)==a and metadata(right)==b,'CLASSPATH_READ_BOOKEND_CHANGED')
                files.append({'path':path,'sha256':proof['sha256'],'bytes':proof['bytes'],
                              'init_view':a,'zygote_view':b})
                total+=proof['bytes'];need(total<=self.reader.TOTAL_FILE_LIMIT,'CLASSPATH_TOTAL_BOUND')
            finally:
                if right is not None:self.pool.close(right)
                self.pool.close(left)
        self.live.guard();return {'values':values,'files':files,'total_bytes':total}
    def engine_file(self,expected=None):
        fd=self.guest('init',ENGINE)
        try:
            if expected is None:return self.artifact(fd)
            need(metadata(fd)==expected['file'],'ACTUAL_ENGINE_FILE_BACKING_CHANGED')
            return expected
        finally:self.pool.close(fd)
    def data_proof(self):
        self.live.guard();return target_data(self.core)
    def runtime(self,observation,classpath,artifacts):
        processes={name:self.rows[name] for name in ANDROID}
        epoch=exact_epoch(self.core['main']['epoch']['boot_id'],processes)
        return {'schema':RUNTIME_SCHEMA,'native_owner':self.core,
            'main_epoch':epoch,'processes':self.rows,'host_processes':{k:self.rows[k] for k in ('daemon','presenter')},
            'init_host_pid':self.rows['init']['host_pid'],'android_env':self.android_environment,
            'main_user_namespace':self.main_user_namespace.guard(),'systemd_units':self.units,
            'surfaceflinger_selection':self.child_selection,'installed_programs':self.programs,
            'normal_host_release':self.live.normal_host_release,
            'observation':observation,'classpath':classpath,'artifacts':artifacts,
            'daemon_status':self.native_status(),'data_continuity':self.data_proof(),
            'saved_document_can_create_authority':False,'business_acceptance_evaluated':False}
    def native_status(self):
        self.live.guard()
        return {'ok':True,'state':'running','host_pid':self.core['peer']['pid'],
            'runtime_epoch':self.core['main']['epoch'],'image_custody':{'owner':self.core['main']['owner']},
            'custody_comparison_only':True,'fresh_full_main_rpc':False,
            'native_ready_permit_issued':False,'outcome_unknown':False}
    def guard(self,runtime):
        self.check();self.live.require_core(runtime['native_owner']);self.identities()
        need(self._unit_rows()==runtime['systemd_units'],'ACTUAL_NORMAL_UNIT_INVOCATION_CHANGED')
        need(self.observe()==runtime['observation'] and
             self.classpaths(runtime['classpath'])==runtime['classpath'] and
             self.engine_file(runtime['artifacts']['engine'])==runtime['artifacts']['engine'] and
             self.data_proof()==runtime['data_continuity'] and
             self.program_artifacts(runtime['installed_programs'])==runtime['installed_programs'],
             'ACTUAL_RUNTIME_COMPARISON_CHANGED')
        self.identities();self.live.guard()
    def close(self):
        mapping=None;primary=None
        try:
            if self.main_user_namespace is not None:mapping=self.main_user_namespace.close()
        except BaseException as error:primary=error
        finally:self.pool.close_all()
        self.pool.require_clean()
        if primary is not None:raise primary
        result=self.pool.summary()
        if mapping is not None:
            need(mapping['remaining']==0 and not mapping['errors'] and
                 mapping['acquired']==mapping['closed']==mapping['close_attempts'],
                 'ACTUAL_MAPPED_NAMESPACE_FDS_UNCLOSED')
            for key in ('acquired','closed','close_attempts'):result[key]+=mapping[key]
        return result

def validate_document(value,live):
    need(type(value) is dict and set(value)=={'schema','native_owner','runtime_observation','framework_epoch',
        'observation','classpath','artifacts','data_continuity','user_zero_package_inventory','sampling','observation_fds',
        'captured_unix_ns','comparison_only','account_contents_read','whole_app_business_accepted',
        'production_ready'} and value['schema']==SCHEMA and value['comparison_only'] is True and
        value['account_contents_read'] is False and value['whole_app_business_accepted'] is False and
        value['production_ready'] is False,'EXACT_CURRENT_KERNEL_FIRST_BASELINE_REQUIRED')
    live.require_core(value['native_owner'])
    live.validate_inventory_comparison(value['user_zero_package_inventory'])
    runtime=value['runtime_observation']
    need(runtime['schema']==RUNTIME_SCHEMA and runtime['native_owner']==value['native_owner'] and
        runtime['main_epoch']==value['framework_epoch'] and
        value['framework_epoch']==exact_epoch(value['native_owner']['main']['epoch']['boot_id'],
            {k:runtime['processes'][k] for k in ANDROID}) and
        all(value[k]==runtime[k] for k in ('observation','classpath','artifacts','data_continuity')) and
        runtime['normal_host_release']==live.normal_host_release and
        runtime['saved_document_can_create_authority'] is False and
        runtime['business_acceptance_evaluated'] is False,
        'CURRENT_NORMAL_OBSERVATION_COMPONENTS_DIFFER')
    need(value['data_continuity']==target_data(value['native_owner']),'EXACT_TARGET_ONLY_DATA_COMPARISON_REQUIRED')
    sampling=value['sampling']
    need(sampling['double_observation_pairs']==3 and sampling['pairs_equal'] is True and
        10*10**9<=sampling['finished_monotonic_ns']-sampling['started_monotonic_ns']<=120*10**9,
        'ACTUAL_BOUNDED_REPEATED_RUNTIME_OBSERVATION_REQUIRED')
    closed=value['observation_fds']
    need(closed['acquired']>0 and closed['acquired']==closed['closed']==closed['close_attempts'] and
         closed['remaining']==0 and closed['errors']==[],'ACTUAL_OBSERVATION_FD_RETIREMENT_REQUIRED')
    return runtime

class BusinessBaseline:
    def __init__(self,baseline_ref,qualification_ref):
        self.data=data_module();self.live=channel()
        self.baseline_ref=baseline_ref;self.qualification_ref=qualification_ref
        self.value=parse(read_ref(baseline_ref));self.qualification=parse(read_ref(qualification_ref,262144))
        runtime=validate_document(self.value,self.live);q=self.qualification
        need(set(q)=={'schema','baseline','normal_source_recipe','core_sha256','main_epoch_sha256','user_zero_package_inventory_sha256',
            'actual_main_and_target_metadata_observed','working_copy_lineage_bound',
            'working_target_directory_identity_preserved','fixed_main_readonly_entry_observed',
            'comparison_only','account_contents_read','business_actions_admitted',
            'whole_app_business_accepted','production_ready','observation_fds'} and
            q['schema']==QUAL_SCHEMA and q['baseline']==baseline_ref and
            q['normal_source_recipe']==self.live.normal_source_recipe and
            q['core_sha256']==sha(canonical(self.live.core)) and
            q['user_zero_package_inventory_sha256']==sha(canonical(self.value['user_zero_package_inventory'])) and
            q['main_epoch_sha256']==self.value['framework_epoch']['sha256'] and
            q['actual_main_and_target_metadata_observed'] is True and
            q['working_copy_lineage_bound'] is True and
            q['working_target_directory_identity_preserved'] is True and
            q['fixed_main_readonly_entry_observed'] is True and q['comparison_only'] is True and
            q['account_contents_read'] is False and q['business_actions_admitted'] is False and
            q['whole_app_business_accepted'] is False and q['production_ready'] is False and
            q['observation_fds']==self.value['observation_fds'],
            'NORMAL_CURRENT_COMPARISON_QUALIFICATION_REQUIRED')
        self.docs={'runtime_observation':runtime}
        self._current_native_discovery=None
        helper=load(MAIN/'helper_contract.py',HELPER_SHA,'native_leaf_current_helper_contract')
        helper.verify_main_receipt(runtime)

    def package_uid_preimage(self):
        need(self.live.core['application']['package']=='com.ihg.apps.android',
             'FIXED_IHG_PACKAGE_INVENTORY_REQUIRED')
        return self.live.validate_inventory_comparison(self.value['user_zero_package_inventory'])
    def require_preinstall_inventory(self):
        before=self.package_uid_preimage();self.live.guard()
        need('org.droidloom.qa.ihg.finalmain.r1' not in before and
             self.live.user_zero_records==before,
             'COMPLETE_ACTUAL_PREINSTALL_TABLE_AND_HELPER_ABSENCE_REQUIRED')
        return dict(before)
    def require_installed_helper_inventory(self,helper_uid):
        before=self.package_uid_preimage();self.live.guard()
        name='org.droidloom.qa.ihg.finalmain.r1'
        need(name not in before and type(helper_uid) is int and 10000<=helper_uid<100000 and
             helper_uid not in before.values(),'NEW_HELPER_CANNOT_SHARE_ANY_PRESERVED_UID')
        expected=dict(before);expected[name]=helper_uid
        need(self.live.user_zero_records==expected,
             'ONLY_THE_ACTUAL_FIXED_HELPER_MAY_BE_ADDED_TO_USER0')
        return {'before_records_sha256':self.value['user_zero_package_inventory']['records_sha256'],
                'current_records_sha256':self.live.user_zero_package_inventory['records_sha256'],
                'only_added_package':name,'helper_uid':helper_uid}

    @property
    def protected_pids(self):
        return tuple(row['host_pid'] for row in self.value['observation']['roles'].values())
    def discover(self):
        self.guard()
        need(self._current_native_discovery is not None,'FRESH_NORMAL_RUNTIME_COMPARISON_REQUIRED')
        pid,env,status=self._current_native_discovery
        return pid,dict(env),dict(status)
    def guard(self,*,action_attempted=False):
        observer=None;primary=None;self._current_native_discovery=None
        try:
            read_ref(self.baseline_ref);read_ref(self.qualification_ref)
            runtime=validate_document(self.value,self.live)
            observer=Observation(self.live,runtime,seconds=15)
            observer.acquire();observer.guard(runtime)
            self._current_native_discovery=(runtime['init_host_pid'],
                dict(observer.android_environment),observer.native_status())
        except BaseException as error:
            primary=error;error.action_attempted=action_attempted
            error.outcome_unknown=action_attempted;error.automatic_retry=False
            raise
        finally:
            try:closed=observer.close() if observer is not None else None
            except BaseException as error:
                if primary is None:
                    error.action_attempted=action_attempted
                    error.outcome_unknown=action_attempted;error.automatic_retry=False;raise
                primary.add_note('NORMAL_BASELINE_HELD_FD_CLOSE_FAILED:'+type(error).__name__)
        return {'schema':'droidloom.native-leaf-business-main-guard.v1',
            'main_epoch_sha256':self.value['framework_epoch']['sha256'],
            'business_baseline_sha256':self.baseline_ref['sha256'],
            'business_qualification_sha256':self.qualification_ref['sha256'],
            'actual_identity_roots_executables_namespaces_checked':True,
            'original_working_lineage_bound':True,'current_target_directories_preserved':True,
            'local_rust_owner_check':True,'fresh_full_main_rpc':False,'observation_fds':closed,
            'Binder_task_cleanup_verified':False,'Binder_UID_cleanup_verified':False,
            'whole_app_business_accepted':False}

def collect(output_directory):
    """Internal comparison collector, invoked only by the source-owned Rust CLI."""
    need(os.getuid()==os.geteuid()==0,'NORMAL_ROOT_OBSERVER_REQUIRED')
    output=Path(output_directory);root_parents(output/'OBSERVED.json',private=True)
    need(output.is_relative_to(QUALIFICATION) and output.is_dir() and
         stat.S_IMODE(output.lstat().st_mode)==0o700 and not (output/'OBSERVED.json').exists(),
         'FRESH_PRIVATE_NORMAL_CAPTURE_DIRECTORY_REQUIRED')
    live=channel();observer=None;primary=None;closed=None
    commands=load(ROOT/'source/support/business_commands.py',COMMANDS_SHA,'normal_current_readonly_commands')
    helper=load(MAIN/'helper_contract.py',HELPER_SHA,'normal_current_readonly_contract')
    entry=load(MAIN/'main_readonly_entry.py',READONLY_SHA,'normal_current_readonly_entry')
    try:
        observer=Observation(live,seconds=240);observer.acquire()
        started=time.monotonic_ns();pairs=[];first=observer.observe()
        classpath=observer.classpaths()
        artifacts={role:observer.artifact(observer.handles[role]['exe']) for role in ROLES}
        artifacts['engine']=observer.engine_file()
        for index in range(3):
            left=observer.observe();right=observer.observe()
            need(left==right==first,'ACTUAL_RUNTIME_CHANGED_DURING_SAMPLING')
            need(observer.classpaths(classpath)==classpath,'ACTUAL_CLASSPATH_CHANGED_DURING_SAMPLING')
            pairs.append({'before':left,'after':right})
            if index<2:
                end=time.monotonic()+5
                while time.monotonic()<end:
                    observer.check();live.guard();time.sleep(max(0,min(0.1,end-time.monotonic())))
        finished=time.monotonic_ns()
        runtime=observer.runtime(first,classpath,artifacts)
        runtime['capture_output_path']=str(output/'BASELINE.json')
        runtime['collector_parent_pid']=os.getppid()
        runtime['normal_live_comparison_before']={'finished_monotonic_ns':finished,
            'source':'actual_rust_opaque_main_and_pm_with_local_comparison_channel',
            'fresh_full_main_rpc_from_python':False}
        def guard():
            observer.guard(runtime)
            return helper.main_binding(runtime)
        ref=entry.capture(runtime,observer.main_user_namespace,observer.reader,commands,helper,guard,
                          output/'main-readonly-entry')
        runtime['main_readonly_entry']=ref
        runtime['normal_live_comparison_after']={'started_monotonic_ns':time.monotonic_ns(),
            'source':'same_live_rust_owner_local_check','fresh_full_main_rpc_from_python':False}
        guard();runtime['captured_unix_ns']=time.time_ns()
        helper.verify_main_receipt(runtime)
        value={'schema':SCHEMA,'native_owner':live.core,'runtime_observation':runtime,
            'framework_epoch':runtime['main_epoch'],'observation':first,'classpath':classpath,
            'artifacts':artifacts,'data_continuity':runtime['data_continuity'],
            'user_zero_package_inventory':live.user_zero_package_inventory,
            'sampling':{'double_observation_pairs':3,'pairs_equal':True,
                'started_monotonic_ns':started,'finished_monotonic_ns':finished},
            'captured_unix_ns':time.time_ns(),'comparison_only':True,'account_contents_read':False,
            'whole_app_business_accepted':False,'production_ready':False}
    except BaseException as error:primary=error;raise
    finally:
        try:closed=observer.close() if observer is not None else None
        except BaseException as error:
            if primary is None:raise
            primary.add_note('NORMAL_CAPTURE_HELD_FD_CLOSE_FAILED:'+type(error).__name__)
    value['observation_fds']=closed
    validate_document(value,live);live.guard()
    result=commands.write_new(output/'OBSERVED.json',value)
    print(json.dumps({'schema':'droidloom.native-leaf-observer-output.v1','observation':result,
                      'comparison_only':True,'whole_app_business_accepted':False},sort_keys=True))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--collect',action='store_true',required=True)
    parser.add_argument('--output-directory',required=True)
    args=parser.parse_args();collect(args.output_directory)
if __name__=='__main__':main()
