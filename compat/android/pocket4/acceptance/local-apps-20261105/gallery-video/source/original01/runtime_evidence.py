"""Read-only, held-generation process evidence during the necessary Gallery video session.

No Android command runs on the sampler thread. No environ, memory or document
content is read. The collector never qualifies an engine by APK ABI alone.
"""
from pathlib import Path
from datetime import datetime, timezone
import collections, hashlib, json, os, re, select, stat, struct, threading, time

TARGETS={'com.android.gallery3d':10064}
PROCESS_NAMES={'com.android.gallery3d':{'com.android.gallery3d'}}
CODE_ROOTS=('/system/','/system_ext/','/apex/','/vendor/','/product/','/usr/lib/droidloom/')
MAP_LINE=re.compile(r'^([0-9a-f]+)-([0-9a-f]+) ([rwxps-]{4}) ([0-9a-f]+) ([0-9a-f]+):([0-9a-f]+) (\d+)(?:\s+(.*))?$')
ENGINE_NAME=re.compile(r'(?:nativebridge|ndk[_-]?translation|droidloom|qemu|lib[^/]*engine)',re.I)


def need(ok,why):
    if not ok:raise RuntimeError(why)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def elf_header(raw):
    need(len(raw)>=64 and raw[:4]==b'\x7fELF','ELF_HEADER_REQUIRED')
    need(raw[4] in (1,2) and raw[5] in (1,2) and raw[6]==1,'ELF_IDENT_UNRECOGNIZED')
    endian='<' if raw[5]==1 else '>'
    machine=struct.unpack_from(endian+'H',raw,18)[0]
    return {'bits':32 if raw[4]==1 else 64,'byte_order':'little' if raw[5]==1 else 'big','machine':machine,
        'architecture':{3:'x86',62:'x86_64',40:'ARM',183:'AArch64'}.get(machine,'unclassified')}


def parse_maps(raw):
    text=raw.decode('utf-8','strict');rows=[]
    for line in text.splitlines():
        m=MAP_LINE.fullmatch(line);need(m is not None,'UNPARSED_MAPPING_LINE')
        start,end=int(m[1],16),int(m[2],16);need(start<end,'INVALID_MAPPING_RANGE')
        rows.append({'start':m[1],'end':m[2],'permissions':m[3],'offset':m[4],
            'device_major':int(m[5],16),'device_minor':int(m[6],16),'inode':int(m[7]),'path':m[8] or ''})
    need(rows and len(rows)<=32768,'EMPTY_OR_UNBOUNDED_MAPS');return rows


def stable_stat(st):return {k:getattr(st,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')}


def identity_key(record):
    return {k:record[k] for k in ('pid','start','uid','nspid','ns','exe')}


class RuntimeEvidence:
    def __init__(self,session,tx,root,fixture_name):
        need(re.fullmatch(r'Pocket4_Gallery_r12_[0-9a-f]{16}',fixture_name),'EXACT_FIXTURE_SEGMENT_REQUIRED')
        self.s,self.tx,self.root,self.fixture=session,tx,Path(root),fixture_name
        self.root.mkdir(mode=0o700);self.cache={};self.samples=[];self.errors=[];self.seen={};self.phase='before-ui'
        self.stop_event=threading.Event();self.thread=None;self.started=time.monotonic();self.max_seconds=900
        self.pid_ns=os.fstat(session.target.namespaces['pid']).st_ino
        self.uid_map=self.s.held.read_at(session.target.proc_fd,'uid_map',8192,time.monotonic()+2).decode()
        self.host_uids={p:self.host_uid(u) for p,u in TARGETS.items()}
        self.boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.log_before=None;self.log_after=None

    def host_uid(self,uid):
        rows=[tuple(map(int,line.split())) for line in self.uid_map.splitlines() if line.strip()]
        need(rows and all(len(r)==3 and r[2]>0 for r in rows),'UID_MAP_GRAMMAR')
        found=[outside+uid-inside for inside,outside,length in rows if inside<=uid<inside+length]
        need(len(found)==1,'ANDROID_UID_NOT_UNIQUELY_MAPPED');return found[0]

    def bounded(self,proc,name,maximum,deadline):return self.s.held.read_at(proc,name,maximum,deadline)

    def code_object(self,fd,expected=None,deadline=None):
        deadline=deadline or time.monotonic()+3;before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode),'CODE_OBJECT_NOT_REGULAR')
        if expected:
            need(before.st_ino==expected['inode'] and os.major(before.st_dev)==expected['device_major']
                and os.minor(before.st_dev)==expected['device_minor'],'MAPPED_PATH_INODE_DIFFERENT')
        key=tuple(stable_stat(before).values())
        if key in self.cache:return self.cache[key]
        head=os.pread(fd,64,0)
        if head[:4]!=b'\x7fELF':return {'elf':False,'identity':stable_stat(before),'content_read':'first_64_code_bytes_only'}
        meta=elf_header(head);result={'elf':True,'identity':stable_stat(before),**meta,'sha256':None}
        if before.st_size>128*1024*1024:
            result['hash_limit']='CODE_FILE_EXCEEDS_128_MIB';return result
        hasher=hashlib.sha256();offset=0
        while offset<before.st_size:
            need(time.monotonic()<deadline,'CODE_HASH_DEADLINE')
            b=os.pread(fd,min(65536,before.st_size-offset),offset);need(b,'CODE_FILE_TRUNCATED')
            offset+=len(b);hasher.update(b)
        need(stable_stat(os.fstat(fd))==stable_stat(before),'CODE_FILE_CHANGED_DURING_HASH')
        result['sha256']=hasher.hexdigest();self.cache[key]=result;return result

    def process(self,pid,package,phase,full):
        proc=os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
        pidfd=rootfd=-1;deadline=time.monotonic()+8
        try:
            pidfd=os.pidfd_open(pid,0);before=self.s.held.proc_identity_at(proc,pid,deadline)
            need(self.s.held.pidfd_alive(pidfd) and before['ns']['pid']=='pid:['+str(self.pid_ns)+']'
                and before['uid']==[str(self.host_uids[package])]*4,'TARGET_PROCESS_IDENTITY_CHANGED')
            cmd=self.bounded(proc,'cmdline',4096,deadline).split(b'\0')[0].decode('utf-8','strict')
            need(cmd in PROCESS_NAMES[package],'TARGET_UID_PROCESS_NAME_UNRECOGNIZED')
            status=self.bounded(proc,'status',65536,deadline).decode();fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status.splitlines() if ':' in line}
            fd_dir=os.open('fd',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=proc)
            try:
                fds=os.listdir(fd_dir);need(len(fds)<=8192,'FD_COUNT_BOUND');owned_refs=[];fd_races=0
                for name in fds:
                    try:
                        target=os.readlink(name,dir_fd=fd_dir)
                        if re.search(r'/(?:'+re.escape(self.fixture)+r')(?:/|$)',target):owned_refs.append(int(name))
                    except FileNotFoundError:fd_races+=1
            finally:os.close(fd_dir)
            row={'package':package,'android_uid':TARGETS[package],'host_identity':before,'process_name':cmd,
                'phase':phase,'utc':datetime.now(timezone.utc).isoformat(),'fd_count':len(fds),
                'owned_fixture_fd_numbers':sorted(owned_refs),'fd_enum_races':fd_races,
                'status':{k:fields[k] for k in ('VmRSS','VmHWM','VmSize','Threads') if k in fields},
                'stat_raw':self.bounded(proc,'stat',8192,deadline).decode(),'full_mapping_snapshot':bool(full)}
            if full:
                maps=self.bounded(proc,'maps',2*1024*1024,deadline);parsed=parse_maps(maps)
                rootfd=os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc);root_birth=os.fstat(rootfd)
                exefd=os.open('exe',os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc)
                try:row['executable']=self.code_object(exefd,deadline=deadline)
                finally:os.close(exefd)
                objects=[];unresolved=[];seen=set()
                for m in parsed:
                    path=m['path'];key=(m['device_major'],m['device_minor'],m['inode'],path)
                    if key in seen or not m['inode'] or not path.startswith('/'):continue
                    seen.add(key)
                    if not ('x' in m['permissions'] or ENGINE_NAME.search(path)):continue
                    if path.endswith(' (deleted)') or not path.startswith(CODE_ROOTS):
                        unresolved.append({'path':path,'reason':'UNTRUSTED_CODE_ROOT_OR_DELETED_MAPPING'});continue
                    try:
                        codefd=self.s.held.open_in_root(rootfd,path,os.O_RDONLY|os.O_NOFOLLOW)
                        try:obj=self.code_object(codefd,m,deadline)
                        finally:os.close(codefd)
                        objects.append({'path':path,'engine_name_candidate':bool(ENGINE_NAME.search(path)),**obj})
                    except Exception as exc:unresolved.append({'path':path,'reason':type(exc).__name__+': '+str(exc)})
                after_maps=self.bounded(proc,'maps',2*1024*1024,time.monotonic()+2)
                checkroot=os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc)
                try:need((os.fstat(checkroot).st_dev,os.fstat(checkroot).st_ino)==(root_birth.st_dev,root_birth.st_ino),'PROCESS_ROOT_CHANGED')
                finally:os.close(checkroot)
                row.update(maps_sha256=digest(maps),maps_bytes=len(maps),maps_rows=parsed,
                    maps_before_after_equal=maps==after_maps,mapped_code_objects=objects,unresolved_executable_objects=unresolved,
                    anonymous_executable_mappings=[m for m in parsed if 'x' in m['permissions'] and not m['inode']],
                    engine_mappings=[m for m in parsed if ENGINE_NAME.search(m['path'])],
                    actual_engine_exclusion_automatically_qualified=False)
            after=self.s.held.proc_identity_at(proc,pid,time.monotonic()+3)
            need(identity_key(before)==identity_key(after) and self.s.held.pidfd_alive(pidfd),'PROCESS_CHANGED_OR_EXITED_DURING_OBSERVATION')
            row['stable_process_identity']=True;row['cgroup_after']=after['cgroup'];return row
        finally:
            if rootfd>=0:os.close(rootfd)
            if pidfd>=0:os.close(pidfd)
            os.close(proc)

    def sample(self):
        phase=self.phase;rows=[];errors=[];started=time.monotonic()
        for item in Path('/proc').iterdir():
            if not item.name.isdecimal():continue
            need(time.monotonic()-started<12,'PROCESS_SCAN_DEADLINE')
            try:
                if (item/'ns/pid').stat().st_ino!=self.pid_ns:continue
                status=(item/'status').read_text();m=re.search(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$',status,re.M)
                if not m:continue
                packages=[p for p,u in self.host_uids.items() if int(m[1])==u]
                if not packages:continue
                package=packages[0];raw=(item/'stat').read_text();birth=raw.rsplit(')',1)[1].split()[19]
                key=(int(item.name),birth,phase);full=key not in self.seen
                row=self.process(int(item.name),package,phase,full);rows.append(row)
                if full and row.get('maps_before_after_equal'):self.seen[key]=True
            except (FileNotFoundError,ProcessLookupError):continue
            except Exception as exc:errors.append({'pid':int(item.name),'error':type(exc).__name__+': '+str(exc)})
        result={'phase':phase,'elapsed_seconds':time.monotonic()-self.started,'boot_id':self.boot_id,'rows':rows,'errors':errors}
        name='sample-%03d.json'%len(self.samples)
        self.tx.write_new(self.root/name,result)
        # Full maps stay in the owned journal. Retain only bounded summaries in
        # RAM even if a busy process needs several consistent-map observations.
        kept=('package','process_name','phase','utc','fd_count','fd_enum_races',
              'owned_fixture_fd_numbers','status','full_mapping_snapshot',
              'stable_process_identity','maps_before_after_equal')
        compact=[]
        for row in rows:
            small={k:row[k] for k in kept if k in row}
            small['host_pid']=row['host_identity']['pid'];small['start_ticks']=row['host_identity']['start']
            small['unresolved_executable_objects']=len(row.get('unresolved_executable_objects',[]))
            compact.append(small)
        self.samples.append({'path':name,'phase':phase,'rows':compact,'errors':errors})

    def start(self):
        need(self.thread is None,'SAMPLER_ALREADY_STARTED');self.s.guard()
        def worker():
            try:
                with self.s.target.lease():
                    while not self.stop_event.is_set():
                        need(time.monotonic()-self.started<self.max_seconds,'SAMPLER_LEASE_EXPIRED');self.sample()
                        self.stop_event.wait(.5)
            except BaseException as exc:self.errors.append(type(exc).__name__+': '+str(exc))
        self.thread=threading.Thread(target=worker,name='owned-gallery-runtime-evidence',daemon=False);self.thread.start()

    def phase_changed(self,label):
        need(re.fullmatch('[a-z][a-z0-9-]{0,63}',label),'PHASE_LABEL');self.phase=label

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:self.thread.join(timeout=20);need(not self.thread.is_alive(),'READ_ONLY_SAMPLER_NOT_JOINED')
        self.s.guard();need(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==self.boot_id,'BOOT_CHANGED')
        full=[r for s in self.samples for r in s['rows'] if r.get('full_mapping_snapshot')]
        resources={}
        for sample in self.samples:
            for row in sample['rows']:
                key=str(row['host_pid'])+':'+str(row['start_ticks'])
                item=resources.setdefault(key,{'host_pid':row['host_pid'],'start_ticks':row['start_ticks'],
                    'process_name':row['process_name'],'samples':0,'maximum_fd_count':0,'memory_kib_max':{},
                    'maximum_threads':None,'first_observed_utc':row['utc'],'last_observed_utc':row['utc']})
                item['samples']+=1;item['last_observed_utc']=row['utc']
                item['maximum_fd_count']=max(item['maximum_fd_count'],row['fd_count'])
                for name,value in row['status'].items():
                    if name=='Threads' and re.fullmatch(r'\d+',value):
                        item['maximum_threads']=max(item['maximum_threads'] or 0,int(value))
                    elif name in ('VmRSS','VmHWM','VmSize') and re.fullmatch(r'\d+ kB',value):
                        item['memory_kib_max'][name]=max(item['memory_kib_max'].get(name,0),int(value.split()[0]))
        out={'schema':'pocket4-gallery-active-runtime-evidence-v1','sample_count':len(self.samples),
            'elapsed_seconds':time.monotonic()-self.started,'boot_id':self.boot_id,'uid_map':self.uid_map,
            'target_android_uids':TARGETS,'target_host_uids':self.host_uids,'thread_joined':True,'errors':self.errors,
            'processes_observed':sorted({r['process_name'] for s in self.samples for r in s['rows']}),
            'stable_complete_mapping_samples':sum(r['stable_process_identity'] and r['maps_before_after_equal'] and r['unresolved_executable_objects']==0 for r in full),
            'scan_error_count':sum(len(s['errors']) for s in self.samples),
            'bounded_process_resource_observations':list(resources.values()),
            'long_duration_leak_or_stress_qualification':False,
            'exact_engine_review_required':True,'whole_app_production_ready':False,'process_memory_or_environment_read':False,
            'user_document_contents_read':False,'Android_commands_from_sampler_thread':0}
        self.tx.write_new(self.root/'summary.json',out);return out
