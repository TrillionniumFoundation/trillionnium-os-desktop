#!/usr/bin/env python3
"""Fixed normal-build prerequisites only; no recursive traversal, copy, subprocess or build."""
import base64,datetime,gzip,hashlib,json,os,signal,stat,sys,time
from pathlib import Path

def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]


def resource_text(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        raw = os.read(fd, 32769)
        require(len(raw) <= 32768, 'owned resource observation exceeds bound')
        return raw.decode('ascii').strip()
    finally:
        os.close(fd)


def resource_events(text):
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows), 'malformed owned memory.events')
    events = {row[0]:int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(k in events for k in ['oom','oom_kill','oom_group_kill']), 'incomplete or duplicate owned memory.events')
    return events


def resource_snapshot(directory_fd, membership):
    observed = Path('/proc/self/cgroup').read_text().strip()
    require(observed == membership, 'controller cgroup membership changed')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    held_st = os.fstat(directory_fd)
    named_st = path.lstat()
    require(stat.S_ISDIR(held_st.st_mode) and stat.S_ISDIR(named_st.st_mode) and
            (held_st.st_dev,held_st.st_ino) == (named_st.st_dev,named_st.st_ino), 'owned invocation cgroup identity changed')
    fields = {name:resource_text(directory_fd,name) for name in [
        'cgroup.procs','memory.events','memory.current','memory.peak','memory.high','memory.max',
        'memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max']}
    require(str(os.getpid()) in fields['cgroup.procs'].split(), 'controller is not in the held invocation')
    require(fields['memory.max'] == '134217728' and fields['cpu.max'] == '25000 100000', 'owned resource limits do not match the request')
    for key in ['memory.current','memory.peak','memory.swap.current','memory.swap.peak']:
        require(fields[key].isdigit(), 'invalid owned resource counter: '+key)
    return {'observed_utc':utc(), 'membership':membership, 'path':str(path),
            'directory_identity':[held_st.st_dev,held_st.st_ino],
            'controller_pid':os.getpid(), 'fields':fields, 'events':resource_events(fields['memory.events'])}


def begin_resources():
    membership = Path('/proc/self/cgroup').read_text().strip()
    require('\n' not in membership and membership.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'), 'not the exact owned user invocation')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    require(path.name.startswith('hepta-runtime-job-') and path.name.endswith('.service') and '..' not in path.parts, 'unexpected owned unit path')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = resource_snapshot(fd,membership)
        require(all(before['events'][k] == 0 for k in ['oom','oom_kill','oom_group_kill']), 'owned invocation already recorded OOM before the control')
        return fd,before
    except BaseException:
        os.close(fd)
        raise


def finish_resources(directory_fd, before, report):
    after = resource_snapshot(directory_fd,before['membership'])
    report['owned_resources_after'] = after
    report['owned_memory_peak'] = int(after['fields']['memory.peak'])
    report['owned_memory_swap_peak'] = int(after['fields']['memory.swap.peak'])
    require(after['directory_identity'] == before['directory_identity'], 'owned cgroup object replaced')
    require(set(before['events']) == set(after['events']), 'owned memory event fields changed')
    delta = {key:after['events'][key]-value for key,value in before['events'].items()}
    report['owned_memory_events_delta'] = delta
    require(all(value >= 0 for value in delta.values()), 'owned memory event counters went backwards')
    require(all(delta[key] == 0 for key in ['oom','oom_kill','oom_group_kill']), 'owned OOM event occurred; control is not qualified')
    require(all(before['fields'][key] == after['fields'][key] for key in ['memory.max','memory.high','memory.swap.max','cpu.max']), 'owned cgroup limits changed during control')
    return {'pass':True, 'before':before, 'after':after, 'memory_events_delta':delta,
            'memory_peak':int(after['fields']['memory.peak']), 'memory_swap_peak':int(after['fields']['memory.swap.peak']),
            'resource_settings_changed':False, 'swap_max_observed_only':after['fields']['memory.swap.max']}


WORK = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1')
OWNER = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01')
TETO_ROOT = OWNER/'full-build-combined07-go5-streaming-01'
TETO = TETO_ROOT/'engine-working'
PROPOSED_WORK = OWNER/'typed-ingress-framework-work-01-20261105'
MAX_TOTAL_READ = 1024*1024*1024
MAX_REPORT = 262144
CHUNK = 262144
AUTHORITY = {
    'native_bridge_source_sha256':'dbdc2047120c3ce607a3127ac261c4ffd9218c09acd5f490f835fae3b79827e0',
    'normal_android_source_sha256':'32d465c001be935f2d460995257da40fed15026b7c805367c18bbc6cd81dac6b',
    'normal_source_library_sha256':'731d24f84669469e5775230ada9cfb5321422ab63d8de0497672ae32e64120e3',
    'prior_engine_inputs_sha256':'97c3b9e686ee2c1d2ac2a5f996cc2cee0a7f54dcb939f09bb44c3f5278f9a5b5',
    'prior_engine_preparation_sha256':'0db7bdac207cab7bd800f6c9948d41b530da1d6ccb077897a508e641c7abee2c',
    'original_sparse_lock_sha256':'4d8f2d047254268305f4802d9dd67bebdfd162d836664c733ecc07e2f9ced178',
    'expanded_sparse_lock_sha256':'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54',
    'image_tools_observation_sha256':'b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292',
}
API_LIBRARIES = (
    'libandroid','libandroid_runtime','libaaudio','libamidi','libbinder_ndk',
    'libcamera2ndk','libEGL','libGLESv1_CM','libGLESv2','libGLESv3',
    'libjnigraphics','libmediandk','libnativewindow','libOpenMAXAL',
    'libOpenSLES','libwebviewchromium_plat_support','libvulkan',
)
DIRECTORIES = (
    WORK, WORK/'base-system', WORK/'base-system/system',
    WORK/'base-system/system/lib64', WORK/'base-system/system/apex',
    WORK/'mesa-source', WORK/'python', WORK/'mesa-tools',
    WORK/'aosp-source', OWNER, TETO,
)


def file_spec(path, category, bound, expected_sha=None, expected_bytes=None,
              format_kind=None, summary=None):
    return {'path':str(path), 'category':category, 'max_bytes':bound,
            'expected_sha256':expected_sha, 'expected_bytes':expected_bytes,
            'format':format_kind, 'summary':summary}


FILES = [file_spec(WORK/('base-system/system/lib64/'+name+'.so'),
                  'base_system_link_reference', 64*1024*1024,
                  expected_sha=('ce601e9536fb971a53bcdf17acd0bf25ee0ac54b1c4e03f83904514667bfb25e'
                                if name=='libandroid' else None), format_kind='ELF64_x86_64')
         for name in API_LIBRARIES] + [
    file_spec(WORK/'base-system/system/apex/com.android.art.apex',
              'apex_container',256*1024*1024,format_kind='ZIP'),
    file_spec(WORK/'base-system/system/apex/com.android.neuralnetworks.apex',
              'apex_container',256*1024*1024,format_kind='ZIP'),
    file_spec(WORK/'framework-res.apk','framework_resource',128*1024*1024,
              expected_sha='b5b5756e6d93680f1086417d764d18c9e67c8e884879cb894849bec12f20a9ec',format_kind='ZIP'),
    file_spec(WORK/'mesa-tools/src/compiler/clc/mesa_clc','mesa_tool',128*1024*1024),
    file_spec(WORK/'mesa-tools/src/compiler/spirv/vtn_bindgen2','mesa_tool',128*1024*1024),
    file_spec(WORK/'mesa-source/android/mesa3d_cross.mk','mesa_projection_input',1024*1024,
              summary='mesa_python_assignment'),
    file_spec(WORK/'aosp-source/.droidloom-source-manifest.json','source_materialization_manifest',1024*1024,
              summary='source_manifest'),
    file_spec(TETO_ROOT/'preparation.json','teto_historical_authority',118896,
              expected_sha=AUTHORITY['prior_engine_preparation_sha256'],expected_bytes=118896,summary='teto_preparation'),
    file_spec(TETO_ROOT/'engine-working-mode-manifest.json','teto_mode_manifest',262144,
              expected_sha='76ea2a30a17ac67a9988f238a9a7dbbb5d8cface789a627125a90bbd0937d390',summary='teto_modes'),
    file_spec(TETO/'Android.bp','teto_fixed_source_sample',1024*1024,
              expected_sha='bfd8ee63943b331ff09c67879065f9794bae7c7b897ba049961cbe47cd2d97e7'),
    file_spec(TETO/'.git/HEAD','teto_head',4096,summary='teto_head'),
    file_spec('/usr/bin/unzip','previously_observed_image_tool',195184,
              expected_sha='908a7d41dfe105c724737cb7f355f474186f51d645829af522265f01492a0cc7',expected_bytes=195184,format_kind='ELF64_x86_64'),
    file_spec('/usr/sbin/debugfs','previously_observed_image_tool',231368,
              expected_sha='864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f',expected_bytes=231368,format_kind='ELF64_x86_64'),
]


def error_row(error):
    return {'type':type(error).__name__,'message':str(error),
            'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}


def note_error(report, phase, error, path=None):
    row={'phase':phase,'path':str(path) if path is not None else None,'error':error_row(error)}
    if report['first_error'] is None: report['first_error']=row
    else: report['secondary_errors'].append(row)
    report['state']='FAIL'


def full_identity(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,
            st.st_size,st.st_mtime_ns,st.st_ctime_ns]


def directory_identity(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid]


def check_deadline(state):
    require(time.monotonic()<state['deadline'],'fixed readonly observation deadline elapsed')


def directory(path, state):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts and '.' not in path.parts,
            'fixed observation path is not absolute and normalized')
    key=str(path)
    if key in state['directories']: return state['directories'][key][0]
    check_deadline(state)
    parent_fd=None if path==Path('/') else directory(path.parent,state)
    fd=os.open('/' if parent_fd is None else path.name,
               os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,
               dir_fd=parent_fd)
    try:
        held=os.fstat(fd)
        named=os.stat('/' if parent_fd is None else path.name,
                      dir_fd=parent_fd,follow_symlinks=False)
        require(stat.S_ISDIR(held.st_mode) and full_identity(held)==full_identity(named),
                'fixed directory held/named identity differs')
        row={'path':key,'held_before':full_identity(held),'named_before':full_identity(named),
             'contents_enumerated':False,'recursive_bytes_measured':False}
        state['directories'][key]=(fd,row)
        return fd
    except BaseException:
        try: os.close(fd)
        except BaseException as error:
            state['early_close_errors'].append({'phase':'directory-setup-close','path':key,'error':error_row(error)})
        raise


def named_file(path, state):
    parent_fd=directory(path.parent,state)
    return os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False)


def digest_file(fd, maximum, state, capture=False):
    check_deadline(state)
    os.lseek(fd,0,os.SEEK_SET)
    h=hashlib.sha256(); total=0; prefix=b''; parts=[]
    while True:
        check_deadline(state)
        block=os.read(fd,min(CHUNK,maximum+1-total))
        if not block: break
        total+=len(block);state['bytes_read']+=len(block)
        require(total<=maximum,'held regular file exceeds fixed byte bound')
        require(state['bytes_read']<=MAX_TOTAL_READ,'aggregate readonly byte bound exceeded')
        h.update(block)
        if len(prefix)<20: prefix=(prefix+block)[:20]
        if capture: parts.append(block)
    return total,h.hexdigest(),prefix,b''.join(parts) if capture else None


def summarize_file(kind, raw):
    if kind=='mesa_python_assignment':
        found=b'MESA3D_PYTHONPATH := $(AOSP_ABSOLUTE_PATH)/external/python/mako' in raw
        require(found,'normal Mesa Python assignment prerequisite differs')
        return {'normal_assignment_present':True,'python_tree_contents_qualified':False}
    if kind=='teto_head':
        require(raw==b'a9496d886a85752ba407b76509952c06cd79ddb8\n','historical Teto detached HEAD changed')
        return {'detached_head':raw.decode('ascii').strip(),'origin_or_ancestry_revalidated':False}
    value=json.loads(raw)
    if kind=='source_manifest':
        require(value['schema_version']==1 and
                value['source_lock_sha256']==AUTHORITY['original_sparse_lock_sha256'],
                'old materialization no longer records its exact original lock')
        require(len(value['plan']['projects'])==214 and len(value['plan']['links'])==8,
                'old materialization project or link count differs')
        return {'schema_version':1,'source_lock_sha256':value['source_lock_sha256'],
                'projects':214,'root_links':8,'live_project_contents_revalidated':False,
                'reusable_as_expanded_lock_workspace':False}
    if kind=='teto_preparation':
        require(value['state']=='PREPARED_NOT_BUILT' and value['engine_file_count']==926 and
                value['git_head']=='a9496d886a85752ba407b76509952c06cd79ddb8' and
                value['git_base']=='917021cf3ecd077eb1581146a79d2265011755b8' and
                value['origin']=='https://github.com/denialwm/teto.git',
                'historical Teto preparation authority differs')
        return {'engine_file_count':926,'git_head':value['git_head'],'git_base':value['git_base'],
                'origin':value['origin'],'full_current_working_tree_revalidated':False}
    if kind=='teto_modes':
        require(isinstance(value,dict) and len(value)==926,'Teto historical mode map differs')
        return {'entries':926,'current_file_modes_revalidated':False}
    raise RuntimeError('unknown fixed summary kind')


def observe_file(spec, state, report):
    path=Path(spec['path']);row={'spec':spec,'error':None};report['files'].append(row)
    fd=-1
    try:
        parent=directory(path.parent,state)
        st=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        row['named_before']=full_identity(st)
        require(stat.S_ISREG(st.st_mode),'fixed input is not a regular non-symlink file')
        row['allocated_bytes']=st.st_blocks*512
        require(st.st_size<=spec['max_bytes'],'fixed input exceeds declared byte bound')
        if spec['expected_bytes'] is not None:
            require(st.st_size==spec['expected_bytes'],'fixed input exact length changed')
        fd=os.open(path.name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent)
        held=os.fstat(fd);row['held_before']=full_identity(held)
        require(full_identity(held)==full_identity(st),'input changed between named and held observation')
        n,digest,prefix,raw=digest_file(fd,spec['max_bytes'],state,capture=spec['summary'] is not None)
        row.update(bytes=n,sha256=digest,prefix20_hex=prefix.hex(),held_after_read=full_identity(os.fstat(fd)),
                   named_after_read=full_identity(named_file(path,state)))
        require(n==held.st_size and row['held_before']==row['held_after_read']==row['named_after_read'],
                'held or named input changed while reading')
        if spec['expected_sha256'] is not None:
            require(digest==spec['expected_sha256'],'fixed input differs from prior actual authority')
        if spec['format']=='ELF64_x86_64':
            require(len(prefix)>=20 and prefix[:6]==b'\x7fELF\x02\x01' and prefix[18:20]==b'\x3e\x00',
                    'normal input is not a little-endian ELF64 x86_64 file')
        elif spec['format']=='ZIP':
            require(prefix[:4]==b'PK\x03\x04','normal APEX/APK input is not a ZIP local-file container')
        if spec['category']=='previously_observed_image_tool':
            require(held.st_uid==held.st_gid==0 and not (held.st_mode&0o022) and held.st_mode&0o111,
                    'previously observed image tool owner or executable permissions differ')
        if spec['category']=='mesa_tool':
            require(held.st_mode&0o111,'Mesa tool is not executable')
        if spec['summary'] is not None: row['summary']=summarize_file(spec['summary'],raw)
        state['files'].append((fd,path,spec,row));fd=-1
    except BaseException as error:
        row['error']=error_row(error);note_error(report,'fixed-file',error,path)
    finally:
        if fd>=0:
            try: os.close(fd)
            except BaseException as error: note_error(report,'failed-input-close',error,path)


def system_text(path, state):
    parent=directory(path.parent,state);fd=os.open(path.name,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent)
    primary=None;result=None
    try:
        before=os.fstat(fd);parts=[];total=0
        while True:
            check_deadline(state)
            block=os.read(fd,min(8192,32769-total))
            if not block: break
            total+=len(block);parts.append(block)
            require(total<=32768,'fixed system observation exceeds bound')
        raw=b''.join(parts);after=os.fstat(fd);named=named_file(path,state)
        require(len(raw)<=32768 and stat.S_ISREG(before.st_mode) and
                directory_identity(before)==directory_identity(after)==directory_identity(named),
                'fixed system observation bound or identity changed')
        result={'path':str(path),'observed_utc':utc(),'bytes':len(raw),'sha256':sha(raw),
                'held_before':full_identity(before),'held_after':full_identity(after),
                'named_after':full_identity(named),'text':raw.decode('ascii')}
    except BaseException as error:
        primary=error
    finally:
        try: os.close(fd)
        except BaseException as error:
            if primary is None: primary=error
            else: state['early_close_errors'].append({'phase':'system-file-close','path':str(path),'error':error_row(error)})
    if primary is not None: raise primary
    return result


def stop_signal(number, _frame):
    raise RuntimeError('readonly controller interrupted by signal '+str(number))


def plan():
    return {'schema':1,'state':'PLAN_ONLY','directories':[str(p) for p in DIRECTORIES],
            'files':FILES,'proposed_workspace_absence':str(PROPOSED_WORK),
            'system_reads':['/proc/meminfo','/proc/pressure/memory'],
            'filesystem_capacity_paths':[str(WORK),str(OWNER)],
            'aggregate_read_bound_including_revalidation':MAX_TOTAL_READ,
            'observation_deadline_seconds':24,'CPUQuota_percent':25,'MemoryMax':134217728,
            'timeout_seconds':30,'normal_materialization_projects':214,'normal_root_links':8,
            'source_authority':AUTHORITY,'directory_recursion':False,
            'source_or_workspace_writes':0,'subprocesses':0,'Main_actions':0,
            'Soong_started':False,'transitive_build_closure_qualified':False}


def collect():
    report=plan();report.update(state='RUNNING',started_utc=utc(),first_error=None,
            secondary_errors=[],files=[],directories=[],filesystem_capacity=[],system_observations=[],
            source_authorities_reexecuted=False,Main_identity_observed=False,
            started_children=0,joined_children=0,forced_cleanup=0,
            directory_copy_cost_known=False,fresh_source_materialization_cost_known=False,
            APEX_embedded_ELFs_extracted_or_verified=False,
            Mesa_Python_or_Teto_full_tree_revalidated=False,normal_builder_admitted=False)
    state={'directories':{},'files':[],'bytes_read':0,'deadline':time.monotonic()+24.0,'early_close_errors':[]}
    resource_fd=-1;before=None
    try:
        require(os.getuid()==os.geteuid()==1000,'ordinary operator UID1000 required')
        signal.signal(signal.SIGTERM,stop_signal);signal.signal(signal.SIGINT,stop_signal)
        resource_fd,before=begin_resources();report['owned_resources_before']=before
        for path in DIRECTORIES:
            try: directory(path,state)
            except BaseException as error: note_error(report,'fixed-directory',error,path)
        for path in (WORK,OWNER):
            try:
                fd=directory(path,state);s=os.fstatvfs(fd)
                report['filesystem_capacity'].append({'path':str(path),'observed_utc':utc(),
                    'available_bytes':s.f_bavail*s.f_frsize,'free_bytes':s.f_bfree*s.f_frsize,
                    'total_bytes':s.f_blocks*s.f_frsize,'available_inodes':s.f_favail,
                    'directory_recursive_cost_inferred':False})
            except BaseException as error: note_error(report,'filesystem-capacity',error,path)
        try:
            parent=directory(PROPOSED_WORK.parent,state)
            try: observed=os.stat(PROPOSED_WORK.name,dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError: report['proposed_workspace_observation']={'path':str(PROPOSED_WORK),'absent':True}
            else:
                report['proposed_workspace_observation']={'path':str(PROPOSED_WORK),'absent':False,'identity':full_identity(observed)}
                raise RuntimeError('proposed independent workspace already exists; no action taken')
        except BaseException as error: note_error(report,'workspace-absence',error,PROPOSED_WORK)
        for path in (Path('/proc/meminfo'),Path('/proc/pressure/memory')):
            try: report['system_observations'].append(system_text(path,state))
            except BaseException as error: note_error(report,'system-observation',error,path)
        for spec in FILES: observe_file(spec,state,report)
    except BaseException as error:
        note_error(report,'admission-or-observation',error)
    finally:
        report['secondary_errors'].extend(state['early_close_errors'])
        for fd,path,spec,row in state['files']:
            try:
                n,digest,_,_=digest_file(fd,spec['max_bytes'],state)
                row['held_final']=full_identity(os.fstat(fd));row['named_final']=full_identity(named_file(path,state))
                row['final_bytes']=n;row['final_sha256']=digest
                require(n==row['bytes'] and digest==row['sha256'] and
                        row['held_final']==row['named_final']==row['held_before'],
                        'fixed input bytes or held/named identity changed by final observation')
                row['revalidated_unchanged']=True
            except BaseException as error: note_error(report,'input-postcheck',error,path)
            finally:
                try: os.close(fd)
                except BaseException as error: note_error(report,'input-close',error,path)
        for key,(fd,row) in reversed(list(state['directories'].items())):
            try:
                path=Path(key);held=os.fstat(fd)
                named=path.lstat()
                row['held_after']=full_identity(held);row['named_after']=full_identity(named)
                require(directory_identity(held)==directory_identity(named)==row['held_before'][:5],
                        'fixed directory object or permissions changed')
                row['object_unchanged']=True
                row['content_metadata_changed']=row['held_before'][5:]!=row['held_after'][5:]
            except BaseException as error: note_error(report,'directory-postcheck',error,key)
            finally:
                try: os.close(fd)
                except BaseException as error: note_error(report,'directory-close',error,key)
                report['directories'].append(row)
        try:
            require(resource_fd>=0 and before is not None,'owned resource admission incomplete')
            report['owned_resource_gate']=finish_resources(resource_fd,before,report)
        except BaseException as error: note_error(report,'resource-postcheck',error)
        finally:
            if resource_fd>=0:
                try: os.close(resource_fd)
                except BaseException as error: note_error(report,'resource-close',error)
        report['bytes_read_including_revalidation']=state['bytes_read']
        report['fixed_asset_logical_bytes_observed']=sum(r.get('bytes',0) for r in report['files']
            if r['spec']['category'] in ('base_system_link_reference','apex_container','framework_resource','mesa_tool'))
        report['fixed_asset_sum_is_not_full_workspace_cost']=True
        report['all_fixed_files_observed_and_revalidated']=len(report['files'])==len(FILES) and all(r.get('revalidated_unchanged') is True for r in report['files'])
        if report['first_error'] is None and report['all_fixed_files_observed_and_revalidated']:
            report['state']='COMPLETE_FIXED_PREREQUISITE_OBSERVATION'
        else: report['state']='FAIL'
        report['finished_utc']=utc()
    raw=(json.dumps(report,ensure_ascii=True,separators=(',',':'))+'\n').encode('utf-8')
    require(len(raw)<=MAX_REPORT,'readonly report exceeds its fixed output bound')
    encoded=gzip.compress(raw,compresslevel=6,mtime=0)
    print(json.dumps({'encoding':'gzip+base64','uncompressed_bytes':len(raw),'sha256':sha(raw),
            'gzip_bytes':len(encoded),'gzip_sha256':sha(encoded),
            'payload':base64.b64encode(encoded).decode('ascii')},separators=(',',':')),flush=True)
    return 0 if report['state']=='COMPLETE_FIXED_PREREQUISITE_OBSERVATION' else 1


if __name__=='__main__':
    if sys.argv[1:]==[]:
        print(json.dumps(plan(),sort_keys=True,indent=2))
    elif sys.argv[1:]==['--execute']:
        sys.exit(collect())
    else:
        raise SystemExit('only default PLAN or --execute is supported')
