"""One candidate ART run linked to the retained verified original; inert by default.

The runner records real compiler/target dumps and never labels an unseen
oatdump class-status grammar as Verified. It does not deploy its candidate.
"""
from pathlib import Path
import argparse,contextlib,datetime,fcntl,hashlib,json,os,re,resource,stat,sys,time,types

ROOT=Path('/home/alex/work/pocket4-storage-session-candidate-20261105-r12')
OUT=ROOT/'art-candidate22'
BASE=ROOT/'art-pair20'
BASE_RESULT_SHA='1138ea24880808e639112691c5e224497705a82b289aa646d1687c0117583292'
BASE_CLOSURE_SHA='0fc09f9cbeaba50f128aaefc47bd2725a5bf4381ffb9f52452c7ad947c07f710'
BASE_REVIEW_SHA='dbf9b5d74fa4c58fc3e1a3126fb3bc82ce7632a71febba9febb176333970ed69'
BASE_ARGV=[]
TX=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
LIB_SHA='605a30fe58ad9fb49bb62d85750a2d558686ea5730d000b3d703e88dde9e8aa5'
DISCOVERY_SHA='614f0c61ec4956a626edb06950bb6b7494ed856dc1dc2c45ac8bfd748421bab9'
ORIGINAL_SHA='f33987e633e476f47ea043af3f7fb94907fd2431fa2b5b49df84cb586bce5c50'
CANDIDATE_SHA='f1acb56e23cd9082a77ef686f2e840a736e7769dd8843830e53e56b1ac31566f'
DEX2OAT='/apex/com.android.art/bin/dex2oat64'
OATDUMP='/apex/com.android.art/bin/oatdump'
CONTEXT='/system/framework/com.android.location.provider.jar'
INPUTS={'original':(ROOT/'input/services-installed.jar',ORIGINAL_SHA),
        'candidate':(ROOT/'alignment15/services-storage-single-removal.jar',CANDIDATE_SHA)}
DEADLINE=0.0

def require(value,reason):
    if not value:raise RuntimeError(reason)

def budget(seconds=0):
    require(time.monotonic()+seconds<DEADLINE,'OWNED_TOTAL_TIME_BUDGET_EXHAUSTED')

def sha(data):return hashlib.sha256(data).hexdigest()

def meta(st):
    return dict(device=st.st_dev,inode=st.st_ino,bytes=st.st_size,mode=st.st_mode,
                uid=st.st_uid,gid=st.st_gid,nlink=st.st_nlink,
                mtime_ns=st.st_mtime_ns,ctime_ns=st.st_ctime_ns)

def pin_fd(fd,maximum=256*1024*1024):
    before=meta(os.fstat(fd))
    require(stat.S_ISREG(before['mode']) and 0<=before['bytes']<=maximum,'FILE_TYPE_OR_SIZE')
    h=hashlib.sha256();offset=0
    while offset<before['bytes']:
        budget();data=os.pread(fd,min(1048576,before['bytes']-offset),offset)
        require(data,'SHORT_READ');h.update(data);offset+=len(data)
    require(meta(os.fstat(fd))==before,'FILE_CHANGED_DURING_HASH')
    return {**before,'sha256':h.hexdigest()}

def pin_host(path,expected):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        p=pin_fd(fd,40*1024*1024)
        require(p['nlink']==1 and p['sha256']==expected,'HOST_INPUT_PIN_MISMATCH')
        return p
    finally:os.close(fd)

def pin_guest(s,peer,path):
    fd=s.target.open_root(path,os.O_RDONLY)
    other=-1
    try:
        other=peer.open_root(path,os.O_RDONLY)
        p=pin_fd(fd);q=meta(os.fstat(other))
        require((p['device'],p['inode'],p['bytes'])==(q['device'],q['inode'],q['bytes']),
                'INIT_AND_SYSTEMSERVER_BACKING_DIFFER')
        return p
    finally:
        if other>=0:os.close(other)
        os.close(fd)

def names_at(s,path):
    fd=s.target.open_root(path,os.O_RDONLY|os.O_DIRECTORY)
    try:names=sorted(os.listdir(fd))
    finally:os.close(fd)
    require(len(names)<=256 and all(re.fullmatch(r'[A-Za-z0-9_.+-]+',n) for n in names),
            'ART_DIRECTORY_NOT_BOUNDED')
    return names

def snapshot(s,peer,lib,discovery):
    budget();s.guard();peer.verify()
    values,cp=s.held.bind_classpaths(s.target,s.activation['framework_epoch'],
                                    s.epoch.process_identity,s.guard)
    require(values==discovery['boot_classpaths']['values'],'BOOT_CLASSPATH_CHANGED')
    require(all(values[k]==s.environment[k] for k in values),'HELPER_CLASSPATH_DIFFERS')
    expect={p['path']:p for p in discovery['boot_classpaths']['files']}
    for p in cp['files']:
        require(all(p[k]==expect[p['path']][k] for k in ('device','inode','bytes','sha256')),
                'OBSERVED_BCP_FILE_CHANGED')
    env=lib.selected_environment(s.held.read_at(peer.proc_fd,'environ',256*1024,DEADLINE))
    require(env==discovery['system_server_environment'],'SYSTEMSERVER_ENVIRONMENT_CHANGED')
    require(env['SYSTEMSERVERCLASSPATH'].split(':')[:2]==[CONTEXT,'/system/framework/services.jar'],
            'SYSTEMSERVER_PREFIX_NOT_OBSERVED_ORDER')
    directories={'boot':names_at(s,'/system/framework/x86_64'),
                 'art_lib64':names_at(s,'/apex/com.android.art/lib64')}
    paths={DEX2OAT,OATDUMP,CONTEXT,'/system/framework/services.jar',
           '/apex/apex-info-list.xml','/system/apex/com.android.art.apex',
           '/system/bin/linker64','/system/bin/env','/system/xbin/su',
           '/system/bin/timeout','/system/bin/sh','/system/bin/toybox','/system/bin/id'}
    paths.update('/system/framework/x86_64/'+n for n in directories['boot']
                 if n.startswith('boot') and n.endswith(('.art','.oat','.vdex')))
    paths.update('/apex/com.android.art/lib64/'+n for n in directories['art_lib64'] if n.endswith('.so'))
    require(len(paths)<=256,'TOO_MANY_ART_DEPENDENCIES')
    files={p:pin_guest(s,peer,p) for p in sorted(paths)}
    require(sum(p['bytes'] for p in files.values())<=1024*1024*1024,'ART_DEPENDENCY_BYTES')
    require(files['/system/framework/services.jar']['sha256']==ORIGINAL_SHA,'INSTALLED_JAR_CHANGED')
    for old in [discovery['tools']['dex2oat64'],discovery['tools']['oatdump']]:
        require(all(files[old['path']][k]==old[k] for k in ('device','inode','bytes','sha256')),
                'INSTALLED_ART_TOOL_CHANGED')
    for old in discovery['mapped_boot_artifacts']:
        if old['path'].startswith('/system/framework/x86_64/boot'):
            require(all(files[old['path']][k]==old[k] for k in ('device','inode','bytes','sha256')),
                    'MAPPED_BOOT_IMAGE_CHANGED')
    require(files['/apex/apex-info-list.xml']['sha256']==discovery['apex_list_sha256'],
            'APEX_DESCRIPTOR_CHANGED')
    require(files[CONTEXT]['sha256']=='9d69d65fb929d0d3d24842dcfc89968043b406b417adc596ccacc8dd466e267d',
            'SYSTEMSERVER_PREFIX_PIN_CHANGED')
    inputs={label:pin_host(path,pin) for label,(path,pin) in INPUTS.items()}
    peer.verify();s.guard()
    return dict(values=values,classpath_files=cp['files'],environment=env,
                guest_files=files,directories=directories,host_inputs=inputs)

def command(s,label,args,extras,timeout):
    budget(timeout+2)
    chain=['/system/bin/env','-i']+[k+'='+s.environment[k] for k in sorted(s.environment)]
    chain+=['/system/xbin/su','2000','/system/bin/timeout','-k','2',str(timeout-5),*args]
    with s.target.entry(chain) as (entry,authority):
        require(len(set((*authority,*extras)))==len(authority)+len(extras),'FD_ALIAS')
        r=s.run_host(label,entry,timeout,tuple((*authority,*extras)))
    require(r['joined'] and not r['timed_out'],'OWNED_CHILD_NOT_JOINED_OR_TIMED_OUT')
    return r

def own_file(path,data,stack,mode=0o440,uid=2000):
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
    stack.callback(os.close,fd)
    os.fchown(fd,uid,1000);os.fchmod(fd,mode)
    offset=0
    while offset<len(data):offset+=os.write(fd,data[offset:])
    os.fsync(fd);return fd

def prepare_phase(label,tx,stack):
    path,pin=INPUTS[label]
    raw=tx.read_regular(path,pin,maximum=40*1024*1024)
    directory=OUT/label;directory.mkdir(mode=0o750);os.chown(directory,0,1000)
    own_file(directory/(label+'.jar'),raw,stack,mode=0o444,uid=0);del raw
    # Input and marker are reopened read-only; only two output FDs are writable.
    source=os.open(directory/(label+'.jar'),os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    stack.callback(os.close,source)
    marker=('pocket4-art-candidate22:'+label+':'+pin+'\n').encode()
    own_file(directory/'marker',marker,stack,mode=0o444,uid=0)
    markfd=os.open(directory/'marker',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    stack.callback(os.close,markfd)
    oat=own_file(directory/(label+'.odex'),b'',stack)
    vdex=own_file(directory/(label+'.vdex'),b'',stack)
    os.chmod(directory,0o555)  # Root owns it; UID2000 cannot chmod or alter entries.
    dirfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);stack.callback(os.close,dirfd)
    require(pin_fd(source)['sha256']==pin,'OWNED_INPUT_COPY_DIFFERS')
    return dict(source=source,oat=oat,vdex=vdex,directory=dirfd,marker=markfd,marker_bytes=marker)

def prove_fds(s,label,fds,read_only,writable,marker,dirfd):
    require(len(set(fds))==len(fds),'DUPLICATE_EXTRA_FD')
    expected=b'2000\n';records=[]
    for fd in fds:
        st=os.fstat(fd);flags=fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE
        require(flags==(os.O_RDONLY if fd in read_only else os.O_RDWR),'FD_ACCESS_MODE_DIFFERS')
        require((fd in read_only)^(fd in writable),'FD_ROLE_AMBIGUOUS')
        expected+=f'/proc/self/fd/{fd}:{st.st_dev}:{st.st_ino}:{st.st_size}\n'.encode()
        records.append(dict(fd=fd,device=st.st_dev,inode=st.st_ino,bytes=st.st_size,
                            access='read-only' if fd in read_only else 'new-output-read-write'))
    script="set -eu\n/system/bin/id -u\n/system/bin/toybox stat -L -c '%n:%d:%i:%s' "
    script+=' '.join('/proc/self/fd/'+str(fd) for fd in fds)
    script+=f'\n/system/bin/cat /proc/self/fd/{marker} /proc/self/fd/{dirfd}/marker\n'
    expected+=os.pread(marker,512,0)*2
    r=command(s,label+'-fd-proof',['/system/bin/sh','-c',script],fds,10)
    require(r['rc']==0 and r['stdout']==expected,'SAME_CHAIN_FD_IDENTITY_OR_MARKER_PROOF_FAILED')
    return dict(all_descriptor_identities_exact=True,uid=2000,records=records,
                stdout_sha256=sha(r['stdout']),marker_direct_and_directory_equal=True)

def record_command(tx,label,r):
    for stream in ('stdout','stderr'):
        tx.write_new(OUT/(label+'.'+stream),r[stream],alex_readable=True)
    return {k:r[k] for k in ('rc','timed_out','joined','spawned')}|{
        stream:dict(bytes=len(r[stream]),sha256=sha(r[stream])) for stream in ('stdout','stderr')}

def target_proof(text):
    header=re.compile(r'^\d+: Lcom/android/server/storage/StorageSessionController; '
        r'\(offset=0x[0-9a-f]+\) \(type_idx=\d+\) \(([^)]+)\) \(([^)]+)\)$',re.M)
    hits=list(header.finditer(text));require(len(hits)==1,'EXACT_TARGET_CLASS_NOT_UNIQUE')
    h=hits[0];require(h[1]=='Verified','EXACT_TARGET_CLASS_NOT_VERIFIED')
    next_class=re.compile(r'^\d+: L[^;]+; \(offset=',re.M).search(text,h.end())
    end=next_class.start() if next_class else len(text)
    method=re.compile(r'^\s*\d+: void com\.android\.server\.storage\.StorageSessionController\.'
        r'onVolumeUnmount\(com\.android\.server\.storage\.ImmutableVolumeInfo\) '
        r'\(dex_method_idx=\d+\)$',re.M)
    methods=list(method.finditer(text,h.end(),end))
    require(len(methods)==1,'EXACT_METHOD_NOT_IN_EXACT_CLASS')
    window=text[h.start():end]
    require(len(window.encode())<=65536,'EXACT_CLASS_BLOCK_TOO_LARGE')
    return dict(class_header=h[0],status=h[1],compilation_kind=h[2],
        method_header=methods[0][0].strip(),unique_exact_class=True,method_in_exact_class=True),window

def normalized_argv(argv):
    result=[]
    for arg in argv:
        if re.fullmatch(r'--(?:zip|oat|output-vdex|class-loader-context)-fd[s]?=\d+',arg):
            arg=arg.split('=')[0]+'=<FD>'
        elif re.fullmatch(r'--oat-location=/proc/self/fd/\d+/(?:original|candidate)\.odex',arg):
            arg='--oat-location=<OWNED_DIRECTORY>/<PHASE>.odex'
        elif arg.startswith('-Xbootclasspathfds:'):
            entries=arg.split(':')[1:]
            require(len(entries)==52 and all(x.isdigit() for x in entries),'BCP_FD_ARGUMENT_SHAPE')
            arg='-Xbootclasspathfds:<52_FDS_IN_OBSERVED_ORDER>'
        result.append(arg)
    return result

def baseline_gate(tx):
    global BASE_ARGV
    r=json.loads(tx.read_regular(BASE/'result.json',BASE_RESULT_SHA,maximum=1024*1024))
    tx.read_regular(ROOT/'verify_art20.py',
        'e2dfabd5a0b01316c05181c5c06e35ab980c108c8c40d51746a0f79a38ddf80b')
    review=json.loads(tx.read_regular(ROOT/'art-baseline-review21/result.json',BASE_REVIEW_SHA))
    require(review['original_result_sha256']==BASE_RESULT_SHA and not review['candidate_attempted'],
            'BASELINE_REVIEW_LINK_DIFFERS')
    require(list(r['phases'])==['original'] and r['error']=='RuntimeError:TARGET_DUMP_NOT_BOUNDED',
            'BASELINE_TERMINAL_STATE_DIFFERS')
    v=r['phases']['original']
    for key in ('compiler','target_dump','android_log'):
        require(v[key]['rc']==0 and v[key]['joined'] and not v[key]['timed_out'],'BASELINE_TOOL_FAILED')
    require(v['fd_proof']['all_descriptor_identities_exact'] and r['input_boot_apex_classpaths_unchanged'],
            'BASELINE_FD_OR_INPUT_CLOSURE_FAILED')
    for flag in ('--compiler-filter=verify','--abort-on-hard-verifier-error','--abort-on-soft-verifier-error'):
        require(v['argv'].count(flag)==1,'BASELINE_COMPILER_FLAGS_MISSING')
    for name,file in (('oat','original.odex'),('vdex','original.vdex')):
        pin_host(BASE/'original'/file,v['outputs'][name]['sha256'])
    pin_host(BASE/'original/original.jar',ORIGINAL_SHA)
    raw=tx.read_regular(BASE/'original-target-dump.stdout',v['target_dump']['stdout']['sha256'],
                       maximum=8*1024*1024)
    proof,_=target_proof(raw.decode())
    before=tx.read_regular(BASE/'before.json',BASE_CLOSURE_SHA,maximum=1024*1024)
    after=tx.read_regular(BASE/'after.json',BASE_CLOSURE_SHA,maximum=1024*1024)
    require(before==after,'RETAINED_BASELINE_CLOSURE_DIFFERS')
    BASE_ARGV=list(v['argv'])
    return json.loads(before),dict(result_sha256=BASE_RESULT_SHA,closure_sha256=BASE_CLOSURE_SHA,
        reconciliation_sha256=BASE_REVIEW_SHA,target=proof,
        original_output_sha256=v['target_dump']['stdout']['sha256'],
        original_reexecuted=False,original_exit2_preserved=True,
        boot_image_inference_warning_retained=True,
        runtime_cache_write_observation_for_original='not collected; no retrospective zero-write claim')

def cache_inventory(s):
    # These are fixed cache candidates under the observed ANDROID_DATA=/data.
    # Presence is measured, never assumed. No user data/content is opened.
    require(s.environment['ANDROID_DATA']=='/data','ANDROID_DATA_DIFFERS')
    s.guard();result=dict(complete=True,roots={});count=0
    def walk(fd,depth):
        nonlocal count
        budget();require(depth<=3,'CACHE_DEPTH_LIMIT')
        first=meta(os.fstat(fd));entries={}
        for name in sorted(os.listdir(fd)):
            count+=1;require(count<=512,'CACHE_ENTRY_LIMIT')
            st=os.stat(name,dir_fd=fd,follow_symlinks=False)
            entry={'metadata':meta(st)}
            if stat.S_ISDIR(st.st_mode):
                child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                try:entry['directory']=walk(child,depth+1)
                finally:os.close(child)
            entries[name]=entry
        require(meta(os.fstat(fd))==first,'CACHE_DIRECTORY_CHANGED_DURING_READ')
        return dict(metadata=first,entries=entries)
    for path in ('/data/dalvik-cache','/data/misc/apexdata/com.android.art/dalvik-cache'):
        fd=-1
        try:
            try:fd=s.target.open_root(path,os.O_RDONLY|os.O_DIRECTORY)
            except FileNotFoundError:
                result['roots'][path]=dict(exists=False)
                continue
            result['roots'][path]=dict(exists=True,tree=walk(fd,0))
        except BaseException as e:
            result['complete']=False
            result['roots'][path]=dict(error=type(e).__name__+':'+str(e))
        finally:
            if fd>=0:os.close(fd)
    result['entries']=count;s.guard();return result

def phase(s,label,tx,stack,bcp,context,classpath,result):
    budget(120)
    own=prepare_phase(label,tx,stack)
    extras=tuple([*bcp,context,own['source'],own['oat'],own['vdex'],own['directory'],own['marker']])
    read_only=set(extras)-{own['oat'],own['vdex']}
    value=dict(attempted=False,target_status_verified=False)
    result['phases'][label]=value
    value['fd_proof']=prove_fds(s,label,extras,read_only,{own['oat'],own['vdex']},own['marker'],own['directory'])
    before_input=pin_fd(own['source'])
    timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%m-%d %H:%M:%S.000')
    args=[DEX2OAT,f"--zip-fd={own['source']}",'--zip-location=/system/framework/services.jar',
          f"--oat-fd={own['oat']}",f"--output-vdex-fd={own['vdex']}",
          f"--oat-location=/proc/self/fd/{own['directory']}/{label}.odex",
          '--instruction-set=x86_64','--boot-image=/system/framework/boot.art',
          '--runtime-arg','-Xbootclasspath:'+classpath,
          '--runtime-arg','-Xbootclasspathfds:'+':'.join(map(str,bcp)),
          '--class-loader-context=PCL['+CONTEXT+']',f'--class-loader-context-fds={context}',
          '--compiler-filter=verify','--abort-on-hard-verifier-error','--abort-on-soft-verifier-error',
          '--copy-dex-files=always','--runtime-arg','-Xms32m','--runtime-arg','-Xmx768m','-j2']
    require(normalized_argv(args)==normalized_argv(BASE_ARGV),'COMPILER_FLAGS_DIFFER_FROM_BASELINE')
    value['argv']=args;value['attempted']=True
    try:
        r=command(s,label+'-compiler',args,extras,85)
        value['compiler']=record_command(tx,label+'-compiler',r)
        require(r['rc']==0,'BASELINE_COMPILER_FAILED' if label=='original' else 'CANDIDATE_COMPILER_FAILED')
        require(os.pread(own['oat'],4,0)==b'\x7fELF' and os.pread(own['vdex'],4,0)==b'vdex',
                'COMPILER_OUTPUT_HEADER_MISSING')
        dump=[OATDUMP,f"--oat-file=/proc/self/fd/{own['directory']}/{label}.odex",
              f"--dex-file=/proc/self/fd/{own['directory']}/{label}.jar",
              '--class-filter=com.android.server.storage.StorageSessionController',
              '--method-filter=onVolumeUnmount','--no-disassemble','--no-dump:vmap']
        r=command(s,label+'-target-dump',dump,extras,12)
        value['target_dump']=record_command(tx,label+'-target-dump',r)
        require(r['rc']==0,'TARGET_OATDUMP_FAILED')
        text=r['stdout'].decode('utf-8','strict')
        require('StorageSessionController' in text and 'onVolumeUnmount' in text,'TARGET_CLASS_OR_METHOD_NOT_IN_DUMP')
        proof,window=target_proof(text)
        value['target']=proof
        value['target_status_verified']=True
        tx.write_new(OUT/(label+'-target.txt'),window.encode(),alex_readable=True)
        value['target_window_sha256']=sha(window.encode())
        value['compiler_and_target_dump_completed']=True
        value['qualification']='EXACT_TARGET_STORED_STATUS_VERIFIED'
    finally:
        final_errors=[]
        try:
            value['input_after']=pin_fd(own['source'])
            value['outputs']={name:pin_fd(own[name]) for name in ('oat','vdex')}
            require(value['input_after']==before_input,'COMPILER_CHANGED_OWNED_INPUT')
        except BaseException as e:final_errors.append('output-or-input-pins:'+type(e).__name__+':'+str(e))
        try:
            r=command(s,label+'-compiler-log',['/system/bin/logcat','-d','-b','all','--uid=2000',
                '-v','threadtime','-T',timestamp,'dex2oat:V','dex2oat64:V','oatdump:V','art:V','*:S'],(),10)
            value['android_log']=record_command(tx,label+'-compiler-log',r)
            require(r['rc']==0,'COMPILER_LOG_READ_FAILED')
        except BaseException as e:
            value['log_error']=type(e).__name__+':'+str(e)
            final_errors.append('log:'+value['log_error'])
        if final_errors:
            value['final_errors']=final_errors
            raise RuntimeError('PHASE_FINAL_COLLECTION_FAILED:'+repr(final_errors))

def resource_admission():
    cgroup='/system.slice/pocket4-art-candidate22-r12.service'
    require(Path('/proc/self/cgroup').read_text().strip()=='0::'+cgroup,'NOT_IN_OWNED_ART_UNIT')
    base=Path('/sys/fs/cgroup')/cgroup.lstrip('/')
    limits={n:(base/n).read_text().strip() for n in ('memory.max','memory.swap.max','cpu.max','pids.max')}
    require(limits['memory.max']=='2147483648' and limits['memory.swap.max']=='0','MEMORY_LIMITS_DIFFER')
    quota,period=map(int,limits['cpu.max'].split())
    require(quota==2*period and limits['pids.max']=='64','CPU_OR_TASK_LIMIT_DIFFERS')
    require(os.sched_getaffinity(0)=={20,21},'CPU_AFFINITY_DIFFERS')
    require(resource.getrlimit(resource.RLIMIT_CORE)==(0,0),'CORE_DUMP_NOT_DISABLED')
    require(resource.getrlimit(resource.RLIMIT_FSIZE)==(268435456,268435456),'FILE_OUTPUT_LIMIT_DIFFERS')
    return limits

def resource_usage():
    cgroup='/system.slice/pocket4-art-candidate22-r12.service'
    require(Path('/proc/self/cgroup').read_text().strip()=='0::'+cgroup,'RESOURCE_UNIT_DIFFERS')
    base=Path('/sys/fs/cgroup')/cgroup.lstrip('/')
    peak=(base/'memory.peak').read_text().strip()
    events=(base/'memory.events').read_text()
    require(len(peak)<32 and len(events)<4096,'RESOURCE_RECORD_TOO_LARGE')
    return dict(memory_peak_bytes=int(peak),memory_events={k:int(v) for k,v in
        (line.split() for line in events.splitlines())},scope='this owned ART unit only')

def execute(result,tx,lib,discovery,baseline):
    with tx.CameraSession(OUT/'journal') as s,contextlib.ExitStack() as stack:
        result['epoch_sha256']=s.epoch_sha256
        expected=s.activation['framework_epoch']['binding']['processes']['system_server']
        require(expected==discovery['system_server_identity'],'SYSTEMSERVER_GENERATION_DIFFERS')
        peer=s.held.HeldZygoteRoot(expected,DEADLINE);stack.callback(peer.close)
        before=snapshot(s,peer,lib,discovery)
        require(before==baseline,'FRESH_DEPENDENCIES_DIFFER_FROM_VERIFIED_BASELINE')
        tx.write_new(OUT/'before.json',before,alex_readable=False)
        cache_before=cache_inventory(s)
        tx.write_new(OUT/'cache-before.json',cache_before,alex_readable=False)
        bcp=[]
        for path in before['values']['BOOTCLASSPATH'].split(':'):
            fd=s.target.open_root(path,os.O_RDONLY);stack.callback(os.close,fd)
            old=next(x for x in before['classpath_files'] if x['path']==path)
            p=pin_fd(fd)
            require(all(p[k]==old[k] for k in ('device','inode','bytes','sha256')),'HELD_BCP_DIFFERS')
            bcp.append(fd)
        require(len(bcp)==52,'BCP_COUNT_NOT_OBSERVED_52')
        context=s.target.open_root(CONTEXT,os.O_RDONLY);stack.callback(os.close,context)
        require(pin_fd(context)==before['guest_files'][CONTEXT],'HELD_PREFIX_DIFFERS')
        try:
            phase(s,'candidate',tx,stack,bcp,context,before['values']['BOOTCLASSPATH'],result)
            result['commands_completed']=True
        finally:
            after=snapshot(s,peer,lib,discovery)
            tx.write_new(OUT/'after.json',after,alex_readable=False)
            result['input_boot_apex_classpaths_unchanged']=after==before
            require(after==before,'INPUT_BOOT_APEX_CLASSPATH_OR_GENERATION_CHANGED')
            require(s.epoch.process_identity(expected['host_pid'])==expected,'SYSTEMSERVER_CHANGED_AFTER_RUN')
            cache_after=cache_inventory(s)
            tx.write_new(OUT/'cache-after.json',cache_after,alex_readable=False)
            complete=cache_before['complete'] and cache_after['complete']
            result['cache_observation']=dict(complete=complete,
                persistent_delta_observed=(cache_before!=cache_after) if complete else None,
                before_sha256=sha(json.dumps(cache_before,sort_keys=True).encode()),
                after_sha256=sha(json.dumps(cache_after,sort_keys=True).encode()),
                interpretation='Metadata delta only in two scoped cache roots; not a trace of transient writes, not attributed to this compiler, and not retrospective evidence for ART20.')
            result['guard_after']=s.guard()
    result['state']='CANDIDATE_TARGET_ART_VERIFIED_AGAINST_RETAINED_ORIGINAL'
    result['verified']=True

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(state='INERT',output=str(OUT),candidate_sha256=CANDIDATE_SHA,
            verifier_executed=False,deployed=False,needs_source_review_before_execution=True)));return 0
    global DEADLINE
    DEADLINE=time.monotonic()+225
    require(os.geteuid()==0,'ROOT_REQUIRED')
    raw=TX.read_bytes();require(sha(raw)==TX_SHA,'TRANSACTION_SOURCE_PIN')
    tx=types.ModuleType('art_pair_tx');tx.__file__=str(TX);exec(compile(raw,str(TX),'exec'),tx.__dict__)
    lib=tx.load_module(ROOT/'collect_art16.py',LIB_SHA,'art_discovery_pin_library')
    discovery=json.loads(tx.read_regular(ROOT/'art-discovery16/result.json',DISCOVERY_SHA,maximum=1048576))
    require(discovery['state']=='DISCOVERY_COMPLETE_NO_VERIFIER_RUN','DISCOVERY_NOT_COMPLETE')
    OUT.mkdir(mode=0o750);os.chown(OUT,0,1000);os.chmod(OUT,0o750)
    result=dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),state='STARTED',
        phases={},commands_completed=False,verified=False,deployed=False,UI_actions=0,volume_actions=0,
        installed_runtime_mutations_requested=False,all_runtime_writes_observed=False,
        original_reexecuted=False,baseline=None,output_scope=str(OUT),automatic_retry=False,
        limits=dict(memory_bytes=2147483648,swap_bytes=0,cpus=[20,21],compile_threads=2,
                    outer_seconds=240,internal_seconds=225,compiler_seconds=85,compiler_inner_seconds=80))
    rc=0
    try:
        result['actual_unit_limits']=resource_admission()
        result['runner_sha256']=sha(Path(__file__).read_bytes())
        baseline,baseline_proof=baseline_gate(tx)
        result['baseline']=baseline_proof
        tx.write_new(OUT/'intent.json',dict(runner_sha256=result['runner_sha256'],
            original_sha256=ORIGINAL_SHA,candidate_sha256=CANDIDATE_SHA,
            limits=result['limits'],actual_unit_limits=result['actual_unit_limits'],
            order=['candidate'],baseline_result_sha256=BASE_RESULT_SHA,automatic_retry=False,deployed=False),alex_readable=True)
        execute(result,tx,lib,discovery,baseline)
    except BaseException as e:
        result.update(state='CANDIDATE_CHECK_INCOMPLETE',verified=False,error=type(e).__name__+':'+str(e));rc=2
    try:result['resource_usage']=resource_usage()
    except BaseException as e:
        result.update(state='CANDIDATE_CHECK_INCOMPLETE',verified=False,
            resource_error=type(e).__name__+':'+str(e));rc=2
    result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    tx.write_new(OUT/'result.json',result,alex_readable=True)
    data=(OUT/'result.json').read_bytes()
    print(json.dumps(dict(state=result['state'],error=result.get('error'),phases=list(result['phases']),
        verified=result['verified'],commands_completed=result['commands_completed'],result_sha256=sha(data),
        result_bytes=len(data),result_path=str(OUT/'result.json'),deployed=False),sort_keys=True));return rc

if __name__=='__main__':sys.exit(main())
