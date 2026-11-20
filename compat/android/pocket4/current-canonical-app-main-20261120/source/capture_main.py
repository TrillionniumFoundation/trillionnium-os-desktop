#!/usr/bin/python3 -I
"""Measure the newly deployed local Android cell; no historical PID fallback."""
import argparse, hashlib, json, os, re, select, signal, stat, subprocess, time, types
from pathlib import Path

QUALIFICATION=Path('/var/lib/droidloom/qualification/pocket4')
SOURCE=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main')
EPOCH=SOURCE/'framework_epoch.py'
EPOCH_SHA='ba4854fcc42def3fb37ac8add1e2b4382d24cb716e2d8181e84b286d5975c377'
READER=SOURCE/'held_runtime.py'
READER_SHA='6f0951391d95baa2e548826d3d7700b634ef89f1a6770d8a6d45b9e6eaaddd4e'
USERNS=SOURCE/'main_user_namespace.py'
USERNS_SHA='88c66969a2fd312eca02064aa1d6c4213ec031df7c7592daedb34ae57b48fda0'
NATIVE=SOURCE/'native_main_observation.py'
NATIVE_SHA='7f9224c7c5c089b396ff8fb99f1f6f62aea9cb60c1ea499ca7990d075356ed2e'
IMAGE=SOURCE/'native_image_observation.py'
IMAGE_SHA='1ba16da37f2261cb79df1883c16ee8a808f6fa0810b12ee0fb0b9938527d3c84'
HELPER_CONTRACT=SOURCE/'helper_contract.py'
HELPER_CONTRACT_SHA='bf8bfa382bae75b738717d03384a812a4e18c287678551081039a3144763390c'
READONLY_ENTRY=SOURCE/'main_readonly_entry.py'
READONLY_ENTRY_SHA='28bfcf094b02ad818fabe7cbb07ccc4342f16f74b56584247bc4d2ad8c1e25df'
COMMANDS=SOURCE.parent/'support'/'business_commands.py'
COMMANDS_SHA='5e9e4e5d81579321329a4d664906a5eab302d2522efae5e8c481039a58b10cf1'
USER = ['/usr/sbin/runuser','-u','alex','--','/usr/bin/env','XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus','/usr/bin/systemctl','--user']
SYSTEM = ['/usr/bin/systemctl']
PROPERTIES = 'ActiveState,SubState,MainPID,ControlPID,ControlGroup,InvocationID,FragmentPath,DropInPaths'
HOST_ENV = {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root','LANG':'C.UTF-8'}

def need(value, message):
    if not value:
        raise RuntimeError(message)

def meta(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def hash_fd(fd, limit=1024*1024*1024):
    before=os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, 'bounded regular file required')
    os.lseek(fd,0,os.SEEK_SET)
    h=hashlib.sha256();count=0
    while True:
        b=os.read(fd,1024*1024)
        if not b:break
        count+=len(b);need(count<=limit,'file exceeded bound');h.update(b)
    need(count==before.st_size and meta(before)==meta(os.fstat(fd)), 'file changed while hashing')
    return {'sha256':h.hexdigest(),'bytes':count,'device':before.st_dev,'inode':before.st_ino,
            'uid':before.st_uid,'gid':before.st_gid,'mode':stat.S_IMODE(before.st_mode),'nlink':before.st_nlink}

def file_ref(path, limit=1024*1024*1024, follow=False):
    p=Path(path)
    fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|(0 if follow else os.O_NOFOLLOW))
    try:row=hash_fd(fd,limit)
    finally:os.close(fd)
    return {'path':str(p),**row}

def read_pinned(ref, limit=16*1024*1024):
    p=Path(ref['path']);need(p.is_absolute(),'absolute reference required')
    fd=os.open(p,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        row=hash_fd(fd,limit);need(row['sha256']==ref['sha256'],'pinned file changed: '+str(p))
        os.lseek(fd,0,os.SEEK_SET)
        data=bytearray()
        while True:
            b=os.read(fd,65536)
            if not b:break
            data.extend(b)
        need(hashlib.sha256(data).hexdigest()==ref['sha256'],'pinned file changed after hash')
        return bytes(data)
    finally:os.close(fd)

def load_module(path, digest, name):
    raw=read_pinned({'path':str(path),'sha256':digest},1024*1024)
    mod=types.ModuleType(name);mod.__file__=str(path)
    exec(compile(raw,str(path),'exec'),mod.__dict__)
    return mod

def save_json(path, value):
    p=Path(path)
    data=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    return file_ref(p)

def host_command(argv, seconds=15):
    p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       env=HOST_ENV,start_new_session=True)
    try:out,err=p.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.communicate(timeout=3)
        raise RuntimeError('bounded read command timed out')
    need(p.returncode==0,'read command failed: '+str(argv[:4])+': '+err.decode(errors='replace')[:300])
    need(len(out)<=4*1024*1024 and len(err)<=1024*1024,'read response exceeded bound')
    return out

def show(base, unit, seconds=15):
    raw=host_command(base+['show',unit,'--property='+PROPERTIES],seconds=seconds)
    value=dict(line.split('=',1) for line in raw.decode().splitlines() if '=' in line)
    need(value.get('ActiveState')=='active' and value.get('SubState')=='running'
         and int(value.get('MainPID','0'))>1 and value.get('ControlPID')=='0','service not running: '+unit)
    return value

def resource_snapshot(unit):
    cg=unit['ControlGroup']
    need(cg.startswith('/') and '..' not in Path(cg).parts and cg!='/','daemon cgroup invalid')
    root=Path('/sys/fs/cgroup')/cg.lstrip('/')
    value={name:(root/name).read_text().strip() for name in ['cpu.max','memory.high','memory.max','pids.max']}
    fields=value['cpu.max'].split()
    need(len(fields)==2 and fields[0]!='max' and int(fields[0])==2*int(fields[1]),'CPU limit differs from 200%')
    need(value['memory.high']==str(5*1024**3) and value['memory.max']==str(6*1024**3)
         and value['pids.max']=='12288','runtime memory/task limits changed')
    return {'cgroup':cg,'values':value}

def capture(manifest_ref, output):
    need(os.getuid()==os.geteuid()==0,'existing root operator required')
    out=Path(output)
    need(out.is_absolute() and out.parent.resolve()==out.parent
         and out.parent.is_relative_to(QUALIFICATION),'canonical qualification output required')
    for parent in (QUALIFICATION,out.parent):
        info=parent.lstat()
        need(parent.resolve()==parent and stat.S_ISDIR(info.st_mode) and
             info.st_uid==info.st_gid==0 and stat.S_IMODE(info.st_mode)==0o700,
             'root private canonical qualification directory required')
    need(not out.exists(),'fresh baseline output required')
    manifest=json.loads(read_pinned(manifest_ref))
    need(manifest.get('ready_for_apply') is True,'complete accepted deployment stage required')
    cell_ref=file_ref('/etc/droidloom/cell.json')
    need(cell_ref['sha256']==manifest['candidate_cell']['sha256'],'candidate cell is not installed')
    installed={}
    for payload in manifest['payload']:
        row=file_ref(payload['install_target'])
        need(row['sha256']==payload['sha256'] and row['bytes']==payload['bytes'],'installed payload differs: '+row['path'])
        need(row['uid']==payload['install_owner']['uid'] and row['gid']==payload['install_owner']['gid']
             and row['mode']==payload['install_mode'] and row['nlink']==1,'installed payload metadata differs')
        installed[row['path']]=row
    epoch=load_module(EPOCH,EPOCH_SHA,'canonical_main_epoch')
    reader=load_module(READER,READER_SHA,'canonical_main_reader')
    mapping_module=load_module(USERNS,USERNS_SHA,'canonical_main_user_namespace')
    native=load_module(NATIVE,NATIVE_SHA,'canonical_native_observation')
    image=load_module(IMAGE,IMAGE_SHA,'canonical_native_image_validation')
    helper_contract=load_module(HELPER_CONTRACT,HELPER_CONTRACT_SHA,'canonical_current_helper_contract')
    readonly_entry=load_module(READONLY_ENTRY,READONLY_ENTRY_SHA,'canonical_current_Main_readonly_entry')
    commands=load_module(COMMANDS,COMMANDS_SHA,'canonical_owned_readonly_commands')
    helper_contract.verify_host_helper()
    units={'daemon':show(SYSTEM,'droidloomd.service'),
           'presenter':show(USER,'droidloom.service'),
           'applications':show(USER,'droidloom-applications.service')}
    resources=resource_snapshot(units['daemon'])
    hosts_epoch=epoch.capture_processes({'daemon':int(units['daemon']['MainPID']),
                                       'presenter':int(units['presenter']['MainPID'])})
    hosts=hosts_epoch['binding']['processes']
    need(hosts['daemon']['uids']==[0]*4 and hosts['daemon']['executable']=='/usr/bin/droidloomd','unverified daemon')
    need(hosts['presenter']['uids']==[1000]*4 and hosts['presenter']['executable']=='/usr/bin/droidloom-wayland','unverified presenter')
    need(hosts['daemon']['cgroup']==['0::'+resources['cgroup']],'native broker escaped bounded daemon cgroup')
    for role,target in (('daemon','/usr/bin/droidloomd'),('presenter','/usr/bin/droidloom-wayland')):
        running=file_ref('/proc/%d/exe'%hosts[role]['host_pid'],follow=True)
        need(running['sha256']==installed[target]['sha256'] and running['bytes']==installed[target]['bytes']
             and (running['device'],running['inode'])==(installed[target]['device'],installed[target]['inode']),
             'running host executable differs from installed release: '+role)
    app=epoch.process_identity(int(units['applications']['MainPID']))
    need(app['executable']=='/usr/bin/droidloom-applications' and app['uids']==[1000]*4,'catalog process identity differs')
    need(file_ref('/proc/%d/exe'%app['host_pid'],follow=True)['sha256']==installed['/usr/bin/droidloom-applications']['sha256'],
         'catalog executable differs')
    def host_guard():
        epoch.require_unchanged(hosts_epoch)
        need(epoch.process_identity(app['host_pid'])==app,'catalog generation changed')
        need(show(SYSTEM,'droidloomd.service',seconds=3)==units['daemon'],'native broker service invocation changed')
        need(resource_snapshot(units['daemon'])==resources,'native broker resource limits changed')
        need(file_ref('/etc/droidloom/cell.json')==cell_ref,'installed cell configuration changed')
        return {'hosts':hosts_epoch['binding'],'catalog':app,'unit':units['daemon'],'resources':resources,'cell':cell_ref}
    # Only this authenticated socket response selects the numeric process to
    # observe. It does not create or transfer a ReadyTreeWitness or command permit.
    observed=native.inspect(hosts['daemon'],installed['/usr/bin/droidloomd'],epoch,host_guard,image.validate_response)
    owner=observed['response']['image_custody']['owner']
    init=owner['cell_host_pid'];initial=epoch.process_identity(init)
    need(initial['host_pid']==observed['response']['host_pid']
         and initial['start_ticks']==owner['cell_start_ticks']
         and initial['parent_host_pid']==hosts['daemon']['host_pid'],
         'authenticated native init is not the original broker child')
    native_names={('mnt' if r['name']=='mount' else r['name']):r for r in owner['namespaces']}
    need(set(native_names)=={'user','mnt','pid','uts','ipc','net','cgroup'},'all native owner namespaces required')
    fds=[];acquired=closed=0;primary=None;mapping=None;handles={}
    def own(fd):
        nonlocal acquired
        fds.append(fd);acquired+=1
        need(fd>=3 and not os.get_inheritable(fd),'private Main observation descriptor required')
        return fd
    def hold(role,identity):
        pid=identity['host_pid']
        need(epoch.process_identity(pid)==identity,'process changed before hold: '+role)
        pidfd=own(os.pidfd_open(pid,0))
        proc=own(os.open('/proc/'+str(pid),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC))
        root=own(os.open('root',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC,dir_fd=proc))
        ns={name:own(os.open('ns/'+name,os.O_RDONLY|os.O_CLOEXEC,dir_fd=proc)) for name in native_names}
        need(epoch.process_identity(pid)==identity,'process changed after hold: '+role)
        value={'pidfd':pidfd,'proc':proc,'root':root,'namespaces':ns}
        handles[role]=value;return value
    def init_guard():
        need(epoch.process_identity(init)==initial,'original native init generation changed')
        host_guard()
    try:
        target=hold('init',initial)
        for name,fd in target['namespaces'].items():
            info=os.fstat(fd);want=native_names[name]
            need((info.st_dev,info.st_ino)==(want['device'],want['inode']),
                 'actual init namespace differs from authenticated native owner: '+name)
        host_user=own(os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC))
        expected=native_names['user']
        owner_user={'link':'user:['+str(expected['inode'])+']','device':expected['device'],'inode':expected['inode']}
        mapping=mapping_module.HeldMainUserNamespace(initial,target,owner_user,host_user,
                 hosts_epoch['binding']['boot_id'],init_guard)
        current=epoch.capture_android(init,mapping)
        processes=current['binding']['processes']
        need(processes['init']==initial,'initial observation changed during framework capture')
        inspection_epoch=observed['response']['inspection']['epoch']
        need(inspection_epoch=={'boot_id':current['binding']['boot_id'],'cell_host_pid':init,
             'framework_host_pid':processes['system_server']['host_pid'],
             'framework_start_ticks':processes['system_server']['start_ticks']},
             'native image inspection and actual framework epochs differ')
        init_group=processes['init']['cgroup']
        need(len(init_group)==1 and (init_group[0]=='0::'+resources['cgroup'] or
             init_group[0].startswith('0::'+resources['cgroup']+'/')),'init escaped original bounded daemon cgroup')
        all_processes={**hosts,**processes,'applications':app}
        for role,identity in all_processes.items():
            if role!='init':hold(role,identity)
            mapping.observe_role(handles[role],identity,role)
        z=processes['zygote64'];zroot=reader.HeldZygoteRoot(z,time.monotonic()+45)
        try:
            envfd=own(os.open('environ',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=handles['zygote64']['proc']))
            raw=reader.read_fd(envfd,reader.ENV_LIMIT,time.monotonic()+3)
            env=mapping_module.android_environment(raw);values=reader.selected_classpaths(raw);del raw
            class RootReader:
                def open_root(self,path,flags=os.O_RDONLY):return reader.open_in_root(target['root'],path,flags)
            initial_files,initial_bytes=reader.hash_classpaths(RootReader(),values,time.monotonic()+45)
            private,private_bytes=reader.hash_classpaths(zroot,values,time.monotonic()+45)
            need(initial_files==private and initial_bytes==private_bytes,'init and private zygote classpath views differ')
            zroot.verify()
        finally:zroot.close()
        samples=[]
        for i in range(3):
            first=epoch.capture_processes({k:v['host_pid'] for k,v in processes.items()})
            second=epoch.capture_processes({k:v['host_pid'] for k,v in processes.items()})
            need(first['binding']==second['binding']==current['binding'],'same framework double sample required')
            host_sample=epoch.capture_processes({k:v['host_pid'] for k,v in hosts.items()})
            need(host_sample['binding']==hosts_epoch['binding'],'same host epoch required')
            samples.append({'first':first,'second':second,'host_epoch':host_sample})
            if i<2:time.sleep(0.05)
        for h in handles.values():
            poller=select.poll();poller.register(h['pidfd'],select.POLLIN|select.POLLHUP|select.POLLERR)
            need(not poller.poll(0),'held process exited')
        mapping_report=mapping.guard()
        baseline={'schema':'pocket4-final-main-baseline-v2','main_epoch':current,
            'main_user_namespace':mapping_report,'native_main_observation':observed,
            'daemon_status':observed['response'],'init_host_pid':init,'android_env':env,
            'host_processes':hosts,'systemd_units':units,'resources':resources,
            'deployment_manifest':manifest_ref,'cell_spec':cell_ref,'catalog_process':app,
            'installed_payloads':installed,'classpath_values':values,'classpath_files':private,
            'classpath_bytes':private_bytes,'three_double_samples':samples,
            'readiness_observations_before_binding':[],'capture_output_path':str(out),
            'historical_PIDs_reused':False,'native_execution_authority_transferred':False}
        def readonly_guard():
            epoch.require_unchanged(current);host_guard()
            need(mapping.guard()==mapping_report,'same Main mapping required around readonly entry')
            for role,identity in all_processes.items():mapping.observe_role(handles[role],identity,role)
            # Original command recorder invokes this only before spawn and
            # after complete child/tree retirement; no RPC is re-entered while
            # a native application inspect is still in flight.
            native.status(hosts['daemon'],installed['/usr/bin/droidloomd'],epoch,host_guard,initial)
            epoch.require_unchanged(current)
        baseline['main_readonly_entry']=readonly_entry.capture(baseline,mapping,reader,commands,
            helper_contract,readonly_guard,out.parent/(out.name+'.readonly-entry'))
        # This cheap same-peer status is a revocation observation after the
        # completed native inspect, never a replacement for its true Ready gate.
        final_status=native.status(hosts['daemon'],installed['/usr/bin/droidloomd'],epoch,host_guard,initial)
        for role,identity in all_processes.items():mapping.observe_role(handles[role],identity,role)
        need(mapping.guard()==mapping_report,'Main maps changed during final observation')
        epoch.require_unchanged(current)
        for unit,base,name in (('presenter',USER,'droidloom.service'),('applications',USER,'droidloom-applications.service')):
            need(show(base,name)==units[unit],'host service generation changed: '+unit)
        baseline['native_final_status_observation']=final_status
        baseline['captured_unix_ns']=time.time_ns()
        helper_contract.verify_main_receipt(baseline)
    except BaseException as error:primary=error;raise
    finally:
        errors=[]
        if mapping is not None:
            try:
                accounting=mapping.close();acquired+=accounting['acquired'];closed+=accounting['closed']
                need(accounting['remaining']==0 and not accounting['errors'] and
                     accounting['acquired']==accounting['closed']==accounting['close_attempts'],
                     'held Main user namespace descriptors unclosed')
            except BaseException as error:errors.append(error)
        for fd in reversed(fds):
            try:os.close(fd);closed+=1
            except OSError as error:errors.append(error)
        if errors:
            if primary is None:raise RuntimeError('Main owned descriptor closure failed') from errors[0]
            primary.add_note('Main descriptor closure failed: '+repr([type(x).__name__ for x in errors]))
    baseline['observation_authorities']={'acquired':acquired,'closed':closed,'remaining':acquired-closed}
    need(acquired==closed,'Main observation authorities leaked')
    result=save_json(out,baseline)
    return baseline,result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--deployment-manifest',required=True)
    p.add_argument('--expect-sha256',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    b,ref=capture({'path':a.deployment_manifest,'sha256':a.expect_sha256},a.output)
    print(json.dumps({'status':'pass','baseline':ref,'epoch_sha256':b['main_epoch']['sha256'],
                      'classpath_files':len(b['classpath_files']),'observation_authorities':b['observation_authorities']}))

if __name__=='__main__':main()
