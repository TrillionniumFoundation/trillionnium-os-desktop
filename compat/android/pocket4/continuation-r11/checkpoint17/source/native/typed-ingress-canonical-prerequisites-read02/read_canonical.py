#!/usr/bin/env python3
"""Fixed canonical content plus three bounded metadata trees; no copy/build/network."""
import base64,datetime,gzip,hashlib,json,os,posixpath,signal,stat,sys,time
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


def stop_signal(number, _frame):
    raise RuntimeError('readonly controller interrupted by signal '+str(number))


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


def read_held_link(fd):
    # Linux readlinkat(held O_PATH symlink, "") reads this inode, not its target.
    raw=os.readlink(b'',dir_fd=fd)
    require(isinstance(raw,bytes) and 0<len(raw)<=MAX_LINK_BYTES,
            'held symlink text is empty or exceeds its fixed bound')
    return raw


def observe_alias(name,state,report):
    check_deadline(state)
    require(name in ALIASES and '/' not in name,'alias outside the exact five-name set')
    parent_fd=directory(WORK,state)
    path=WORK/name
    row={'path':str(path),'target_followed':False,'target_opened':False,
         'target_contents_read':False,'error':None}
    report['aliases'].append(row)
    fd=None
    try:
        before=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
        row['named_before']=full_identity(before)
        require(stat.S_ISLNK(before.st_mode),'fixed alias is not a symlink; retained without following')
        require(0<before.st_size<=MAX_LINK_BYTES,'fixed symlink exceeds its link-text bound')
        fd=os.open(name,os.O_PATH|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=parent_fd)
        held=os.fstat(fd)
        row['held_before']=full_identity(held)
        require(stat.S_ISLNK(held.st_mode) and full_identity(held)==full_identity(before),
                'held symlink differs from named alias')
        # Register before readlink/decoding, so every owned FD is finalized even on failure.
        state['aliases'].append((fd,name,row))
        fd=None
        held_fd=state['aliases'][-1][0]
        raw=read_held_link(held_fd)
        named_raw=os.readlink(os.fsencode(name),dir_fd=parent_fd)
        require(raw==named_raw and len(raw)==held.st_size,'held/named link text differs')
        text=raw.decode('utf-8','strict')
        row['link_text']=text
        row['link_bytes']=len(raw)
        row['link_sha256']=sha(raw)
        row['lexical_target_only']=posixpath.normpath(text if text.startswith('/') else str(WORK)+'/'+text)
        row['lexical_target_is_not_a_canonicalization']=True
        row['held_after_read']=full_identity(os.fstat(held_fd))
        row['named_after_read']=full_identity(os.stat(name,dir_fd=parent_fd,follow_symlinks=False))
        require(row['held_after_read']==row['held_before']==row['named_after_read'],
                'fixed alias changed during link-text read')
    except BaseException as error:
        row['error']=error_row(error)
        note_error(report,'fixed-alias',error,path)
    finally:
        if fd is not None:
            try: os.close(fd)
            except BaseException as error: note_error(report,'unregistered-alias-close',error,path)


def recheck_aliases(state,report):
    parent_fd=state['directories'].get(str(WORK),(None,None))[0]
    for fd,name,row in state['aliases']:
        try:
            check_deadline(state)
            held=os.fstat(fd)
            named=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
            held_text=read_held_link(fd)
            named_text=os.readlink(os.fsencode(name),dir_fd=parent_fd)
            row['held_final']=full_identity(held)
            row['named_final']=full_identity(named)
            row['final_link_sha256']=sha(held_text)
            require(row['held_final']==row['held_before']==row['named_final'],
                    'fixed alias identity changed before finalization')
            require(held_text==named_text and len(held_text)==row['link_bytes'] and
                    sha(held_text)==row['link_sha256'],'fixed alias text changed before finalization')
            row['revalidated_unchanged']=True
        except BaseException as error:
            row['revalidation_error']=error_row(error)
            row['revalidated_unchanged']=False
            note_error(report,'fixed-alias-final',error,WORK/name)
    for path,(fd,row) in reversed(tuple(state['directories'].items())):
        try:
            check_deadline(state)
            held=os.fstat(fd)
            named=os.stat(path,follow_symlinks=False)
            row['held_after']=full_identity(held)
            row['named_after']=full_identity(named)
            before=row['held_before']
            require(directory_identity(held)==before[:5] and
                    directory_identity(named)==before[:5],
                    'held or named parent-chain directory identity changed')
            row['object_unchanged']=True
            row['content_metadata_changed']=row['held_after']!=before or row['named_after']!=before
        except BaseException as error:
            row['object_unchanged']=False
            row['revalidation_error']=error_row(error)
            note_error(report,'parent-chain-final',error,path)


WORK=Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1')
WORK_IDENTITY=[66306, 40166050, 16893, 1000, 1000]
ALIASES=('base-system', 'mesa-source', 'python', 'mesa-tools', 'framework-res.apk')
ALIAS_BINDINGS={'base-system': {'identity': [66306, 40170895, 41471, 1000, 1000, 71, 1792770937198380970, 1792770937198380970], 'target': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system', 'sha256': 'e7fa667793889daa974799050313298f6af0b0b2875ab5327984f3252817e1cf'}, 'mesa-source': {'identity': [66306, 40170917, 41471, 1000, 1000, 69, 1792770937198380970, 1792770937198380970], 'target': '/home/alex/work/p4-nativebridge-repair-20261017-1428-work/mesa-source', 'sha256': '11a96f34a9bf46c626437d9c0ea4f87b9c3563bf0bd2e48a8f69983d7afc1583'}, 'python': {'identity': [66306, 40170915, 41471, 1000, 1000, 66, 1792770937198380970, 1792770937198380970], 'target': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/python', 'sha256': 'a6ab3230f0b40945fde82f087fa032c658be462109b5d637ea7e1c17e2e45b37'}, 'mesa-tools': {'identity': [66306, 40170916, 41471, 1000, 1000, 70, 1792770937198380970, 1792770937198380970], 'target': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/mesa-tools', 'sha256': '4112d7ac7c8aa807ff63a6cc9718382abad138c03bf33f3e4ff3ebad226a61e7'}, 'framework-res.apk': {'identity': [66306, 40170914, 41471, 1000, 1000, 77, 1792770937198380970, 1792770937198380970], 'target': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/framework-res.apk', 'sha256': 'adedcf5d9559afb56c2cdf0e0d3c6b7295cc8148025567e705e491daf59c861f'}}
ALIAS_REPORT={'bytes': 15264, 'sha256': 'cad64eff346b7ab393b243c219ef6461c3ec8a3afe13e4d738d4b16e620e0f20'}
PRIOR_FAILURE={'bytes': 47126, 'sha256': '22bb492e41a71eaa99287e913ccee842d473f7f7b2d21f9faf0aced38408d0c3'}
MAX_LINK_BYTES=4096
MAX_TOTAL_READ=1024*1024*1024
MAX_REPORT=1024*1024
CHUNK=262144
AUTHORITY={'native_bridge_source_sha256': 'dbdc2047120c3ce607a3127ac261c4ffd9218c09acd5f490f835fae3b79827e0', 'normal_android_source_sha256': '32d465c001be935f2d460995257da40fed15026b7c805367c18bbc6cd81dac6b', 'normal_source_library_sha256': '731d24f84669469e5775230ada9cfb5321422ab63d8de0497672ae32e64120e3', 'prior_engine_inputs_sha256': '97c3b9e686ee2c1d2ac2a5f996cc2cee0a7f54dcb939f09bb44c3f5278f9a5b5', 'prior_engine_preparation_sha256': '0db7bdac207cab7bd800f6c9948d41b530da1d6ccb077897a508e641c7abee2c', 'original_sparse_lock_sha256': '4d8f2d047254268305f4802d9dd67bebdfd162d836664c733ecc07e2f9ced178', 'expanded_sparse_lock_sha256': 'ca62c69ff22eba9ff84992aaa18114b74c951802c084bd8cb25cfc22d741ae54', 'image_tools_observation_sha256': 'b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292'}
DIRECTORIES=tuple(Path(value) for value in ['/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1', '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system', '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64', '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/apex', '/home/alex/work/p4-nativebridge-repair-20261017-1428-work/mesa-source', '/home/alex/work/m692-pinned-android17-build-inputs-20261015/python', '/home/alex/work/m692-pinned-android17-build-inputs-20261015/mesa-tools'])
TREE_ROOTS=tuple(Path(value) for value in ['/home/alex/work/p4-nativebridge-repair-20261017-1428-work/mesa-source', '/home/alex/work/m692-pinned-android17-build-inputs-20261015/python', '/home/alex/work/m692-pinned-android17-build-inputs-20261015/mesa-tools'])
FILES=[{'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libandroid.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': 'ce601e9536fb971a53bcdf17acd0bf25ee0ac54b1c4e03f83904514667bfb25e', 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libandroid_runtime.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libaaudio.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libamidi.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libbinder_ndk.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libcamera2ndk.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libEGL.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libGLESv1_CM.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libGLESv2.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libGLESv3.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libjnigraphics.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libmediandk.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libnativewindow.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libOpenMAXAL.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libOpenSLES.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libwebviewchromium_plat_support.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libvulkan.so', 'category': 'base_system_link_reference', 'max_bytes': 67108864, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ELF64_x86_64', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/apex/com.android.art.apex', 'category': 'apex_container', 'max_bytes': 268435456, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ZIP', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/apex/com.android.neuralnetworks.apex', 'category': 'apex_container', 'max_bytes': 268435456, 'expected_sha256': None, 'expected_bytes': None, 'format': 'ZIP', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/framework-res.apk', 'category': 'framework_resource', 'max_bytes': 134217728, 'expected_sha256': 'b5b5756e6d93680f1086417d764d18c9e67c8e884879cb894849bec12f20a9ec', 'expected_bytes': None, 'format': 'ZIP', 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/mesa-tools/src/compiler/clc/mesa_clc', 'category': 'mesa_tool', 'max_bytes': 134217728, 'expected_sha256': None, 'expected_bytes': None, 'format': None, 'summary': None}, {'path': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/mesa-tools/src/compiler/spirv/vtn_bindgen2', 'category': 'mesa_tool', 'max_bytes': 134217728, 'expected_sha256': None, 'expected_bytes': None, 'format': None, 'summary': None}, {'path': '/home/alex/work/p4-nativebridge-repair-20261017-1428-work/mesa-source/android/mesa3d_cross.mk', 'category': 'mesa_projection_input', 'max_bytes': 1048576, 'expected_sha256': None, 'expected_bytes': None, 'format': None, 'summary': 'mesa_python_assignment'}, {'path': '/home/alex/work/pocket4-native-typed-ingress-builder465-compile-01-20261105/builder-source/tools/droidloom-update/src/assemble.rs', 'category': 'exact_builder465_source', 'max_bytes': 21737, 'expected_sha256': '8863f18ded14bb26c320eff7a62e1aa8c99e6d668e2e86f18b7b76b029c43e18', 'expected_bytes': 21737, 'format': None, 'summary': None}, {'path': '/home/alex/work/pocket4-native-typed-ingress-builder465-compile-01-20261105/builder-source/tools/droidloom-update/src/python.rs', 'category': 'exact_builder465_source', 'max_bytes': 3141, 'expected_sha256': '9d7e0561ddea70bda91a6e2ba215ff7487ce1c59d4e9f925e1cef03b08dc3216', 'expected_bytes': 3141, 'format': None, 'summary': None}, {'path': '/home/alex/work/pocket4-native-typed-ingress-builder465-compile-01-20261105/builder-source/android/manifest/source-lock-x86_64.json', 'category': 'exact_builder465_source', 'max_bytes': 1968, 'expected_sha256': '35a001b392b7202e9b963e8f218406dd47ed506556de0e8b5bb375c6e6137236', 'expected_bytes': 1968, 'format': None, 'summary': None}, {'path': '/home/alex/work/pocket4-native-typed-ingress-builder465-compile-01-20261105/builder-source/android/manifest/build-python-lock.json', 'category': 'exact_builder465_source', 'max_bytes': 1937, 'expected_sha256': 'ca2eb995f48c19d7b09dbb9dad19e200857642b70de0ed704778f3b8895738a4', 'expected_bytes': 1937, 'format': None, 'summary': None}]


def check_alias_authority(state, report):
    work_fd=directory(WORK,state)
    require(directory_identity(os.fstat(work_fd))==WORK_IDENTITY,
            'original work identity differs from the actual alias observation')
    for name in ALIASES:
        observe_alias(name,state,report)
    require(len(report['aliases'])==len(ALIASES),'incomplete fixed alias observation')
    for row in report['aliases']:
        name=Path(row['path']).name
        expected=ALIAS_BINDINGS[name]
        require(row['error'] is None and row['held_before']==expected['identity'] and
                row['link_text']==expected['target'] and
                row['link_sha256']==expected['sha256'],
                'fixed alias changed from the reviewed actual binding: '+name)


def tree_metadata(root, state, budget):
    # This is a cost/type/identity census. Extra regular-file contents are not read.
    root=Path(root)
    root_fd=directory(root,state)
    digest=hashlib.sha256()
    totals={'entries':0,'directories':0,'regular_files':0,'symlinks':0,'other':0,
            'regular_logical_bytes':0,'regular_allocated_bytes_by_path':0,
            'symlink_text_bytes':0,'lexically_external_symlinks':0}
    links=[]
    def add_record(relative, before, link_text=None):
        encoded=json.dumps({'path':relative,'identity':full_identity(before),
            'nlink':before.st_nlink,'allocated_bytes':before.st_blocks*512,
            'link_text':link_text},ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()+b'\n'
        digest.update(encoded)
    def visit(fd, relative, depth):
        check_deadline(state)
        require(depth<=64,'fixed tree metadata depth bound exceeded')
        names=[]
        # scandir(fd) enumerates only the held directory; no entry is followed.
        with os.scandir(fd) as entries:
            for entry in entries:
                check_deadline(state)
                budget['entries']+=1
                require(budget['entries']<=100000,'combined fixed-tree entry bound exceeded')
                require(entry.name not in ('','.','..') and '/' not in entry.name,
                        'invalid directory entry name')
                names.append(entry.name)
        for name in sorted(names):
            check_deadline(state)
            child_relative=name if not relative else relative+'/'+name
            require(len(os.fsencode(child_relative))<=4096,'fixed-tree relative path exceeds bound')
            before=os.stat(name,dir_fd=fd,follow_symlinks=False)
            totals['entries']+=1
            child_fd=None
            if stat.S_ISDIR(before.st_mode):
                totals['directories']+=1
                child_fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=fd)
                primary=None
                try:
                    require(full_identity(os.fstat(child_fd))==full_identity(before),
                            'tree directory changed between name and held FD')
                    add_record(child_relative,before)
                    visit(child_fd,child_relative,depth+1)
                    require(full_identity(os.fstat(child_fd))==full_identity(before),
                            'held tree directory changed during traversal')
                except BaseException as error:
                    primary=error
                    raise
                finally:
                    try: os.close(child_fd)
                    except BaseException as error:
                        if primary is None: raise
                        state['tree_secondary_errors'].append({'path':str(root/child_relative),
                            'phase':'nested-directory-close','error':error_row(error)})
            elif stat.S_ISREG(before.st_mode):
                totals['regular_files']+=1
                totals['regular_logical_bytes']+=before.st_size
                totals['regular_allocated_bytes_by_path']+=before.st_blocks*512
                budget['logical_bytes']+=before.st_size
                require(budget['logical_bytes']<=64*1024**3,'combined fixed-tree logical byte bound exceeded')
                add_record(child_relative,before)
            elif stat.S_ISLNK(before.st_mode):
                totals['symlinks']+=1
                require(0<before.st_size<=MAX_LINK_BYTES,'tree symlink text exceeds bound')
                raw=os.readlink(os.fsencode(name),dir_fd=fd)
                require(isinstance(raw,bytes) and len(raw)==before.st_size,'tree symlink length changed')
                text=raw.decode('utf-8','strict')
                totals['symlink_text_bytes']+=len(raw)
                # Only lexical information: never open or canonicalize the target.
                absolute=posixpath.normpath(text if text.startswith('/') else str((root/child_relative).parent)+'/'+text)
                inside=os.path.commonpath((str(root),absolute))==str(root)
                totals['lexically_external_symlinks']+=int(not inside)
                record={'path':child_relative,'text':text,'sha256':sha(raw),
                        'lexical_target_within_root':inside,'target_followed':False}
                budget['link_report_bytes']+=len(json.dumps(record,ensure_ascii=True).encode())
                require(budget['link_report_bytes']<=131072,'combined symlink metadata report bound exceeded')
                links.append(record)
                add_record(child_relative,before,text)
                require(os.readlink(os.fsencode(name),dir_fd=fd)==raw,'tree symlink changed while observed')
            else:
                totals['other']+=1
                add_record(child_relative,before)
            after=os.stat(name,dir_fd=fd,follow_symlinks=False)
            require(full_identity(before)==full_identity(after),
                    'tree entry changed during metadata observation: '+child_relative)
    held_before=full_identity(os.fstat(root_fd))
    add_record('',os.fstat(root_fd))
    visit(root_fd,'',0)
    held_after=full_identity(os.fstat(root_fd))
    require(held_before==held_after,'fixed root changed during metadata walk')
    return {'root':str(root),'held_root_before':held_before,'held_root_after':held_after,
            'metadata_sha256':digest.hexdigest(),'counts':totals,'symlinks':links,
            'regular_contents_read':False,'regular_content_hashes_qualified':False,
            'metadata_is_not_a_source_content_manifest':True,
            'logical_and_allocated_bytes_count_paths_not_unique_inodes':True,
            'external_symlink_targets_followed':False}


def plan():
    return {'schema':1,'state':'PLAN_ONLY','directories':[str(p) for p in DIRECTORIES],
            'files':FILES,'aliases':ALIAS_BINDINGS,'actual_alias_report':ALIAS_REPORT,
            'prior_prerequisite_failure':PRIOR_FAILURE,
            'tree_metadata_roots':[str(p) for p in TREE_ROOTS],
            'tree_maximum_entries_combined_per_pass':100000,
            'tree_maximum_depth':64,'tree_maximum_logical_bytes_combined_per_pass':64*1024**3,
            'tree_passes':2,'tree_regular_contents_read':False,
            'aggregate_regular_read_bound_including_revalidation':MAX_TOTAL_READ,
            'maximum_report_bytes':MAX_REPORT,'observation_deadline_seconds':54,
            'CPUQuota_percent':25,'MemoryMax':134217728,'timeout_seconds':60,
            'source_or_workspace_writes':0,'subprocesses':0,'Main_actions':0,
            'normal_builder_admitted':False,'transitive_build_closure_qualified':False}


def collect():
    report=plan();report.update(state='RUNNING',started_utc=utc(),first_error=None,
        secondary_errors=[],files=[],directories=[],aliases=[],tree_metadata=[],
        source_authorities_reexecuted=False,Main_identity_observed=False,
        started_children=0,joined_children=0,forced_cleanup=0,
        APEX_embedded_ELFs_extracted_or_verified=False,
        Mesa_Python_tools_content_copy_qualified=False,Teto_full_source_revalidated=False)
    state={'directories':{},'files':[],'aliases':[],'bytes_read':0,
           'deadline':time.monotonic()+54,'early_close_errors':[],'tree_secondary_errors':[]}
    resource_fd=-1;before=None
    try:
        require(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,
                'ordinary operator UID/GID1000 required')
        signal.signal(signal.SIGTERM,stop_signal);signal.signal(signal.SIGINT,stop_signal)
        resource_fd,before=begin_resources();report['owned_resources_before']=before
        check_alias_authority(state,report)
        for path in DIRECTORIES:
            try: directory(path,state)
            except BaseException as error: note_error(report,'fixed-directory',error,path)
        for spec in FILES: observe_file(spec,state,report)
        budget={'entries':0,'logical_bytes':0,'link_report_bytes':0}
        for root in TREE_ROOTS:
            row={'root':str(root),'complete':False};report['tree_metadata'].append(row)
            try: row['before']=tree_metadata(root,state,budget)
            except BaseException as error: note_error(report,'tree-metadata-before',error,root)
    except BaseException as error:
        note_error(report,'admission-or-observation',error)
    finally:
        after_budget={'entries':0,'logical_bytes':0,'link_report_bytes':0}
        for row in report['tree_metadata']:
            if 'before' not in row: continue
            try:
                after=tree_metadata(Path(row['root']),state,after_budget)
                require(after==row['before'],'fixed tree metadata changed between the two bounded passes')
                row['after_metadata_sha256']=after['metadata_sha256']
                row['after_held_root']=after['held_root_after']
                row['complete']=True
            except BaseException as error: note_error(report,'tree-metadata-after',error,row['root'])
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
        try: recheck_aliases(state,report)
        except BaseException as error: note_error(report,'alias-and-parent-postcheck',error)
        for fd,name,row in reversed(state['aliases']):
            try: os.close(fd)
            except BaseException as error: note_error(report,'alias-close',error,WORK/name)
        for key,(fd,row) in reversed(tuple(state['directories'].items())):
            try: os.close(fd)
            except BaseException as error: note_error(report,'directory-close',error,key)
            report['directories'].append(row)
        for row in state['early_close_errors']+state['tree_secondary_errors']:
            if report['first_error'] is None: report['first_error']=row
            else: report['secondary_errors'].append(row)
        if resource_fd>=0 and before is not None:
            try: report['owned_resource_gate']=finish_resources(resource_fd,before,report)
            except BaseException as error: note_error(report,'resource-postcheck',error)
        if resource_fd>=0:
            try: os.close(resource_fd)
            except BaseException as error: note_error(report,'resource-close',error)
        report['bytes_read_including_revalidation']=state['bytes_read']
        report['all_27_fixed_files_observed_and_revalidated']=(len(report['files'])==len(FILES) and
            all(row.get('revalidated_unchanged') is True for row in report['files']))
        report['all_three_tree_metadata_censuses_complete']=(len(report['tree_metadata'])==len(TREE_ROOTS) and
            all(row['complete'] for row in report['tree_metadata']))
        report['all_five_aliases_revalidated']=(len(report['aliases'])==len(ALIASES) and
            all(row.get('error') is None and row.get('revalidated_unchanged') is True for row in report['aliases']))
        complete=all(report[name] for name in ['all_27_fixed_files_observed_and_revalidated',
                    'all_three_tree_metadata_censuses_complete','all_five_aliases_revalidated'])
        if not complete and report['first_error'] is None:
            note_error(report,'completeness',RuntimeError('fixed canonical observation is incomplete'))
        report['state']='COMPLETE_CANONICAL_CONTENT_AND_TREE_METADATA' if report['first_error'] is None else 'FAIL'
        report['finished_utc']=utc()
    raw=(json.dumps(report,ensure_ascii=True,separators=(',',':'))+'\n').encode()
    require(len(raw)<=MAX_REPORT,'canonical readonly report exceeds its finite output bound')
    packed=gzip.compress(raw,compresslevel=6,mtime=0)
    print(json.dumps({'encoding':'gzip+base64','uncompressed_bytes':len(raw),'sha256':sha(raw),
        'gzip_bytes':len(packed),'gzip_sha256':sha(packed),
        'payload':base64.b64encode(packed).decode('ascii')},separators=(',',':')),flush=True)
    return 0 if report['state']=='COMPLETE_CANONICAL_CONTENT_AND_TREE_METADATA' else 1


if __name__=='__main__':
    if sys.argv[1:]==[]:
        print(json.dumps(plan(),sort_keys=True,indent=2))
    elif sys.argv[1:]==['--execute']:
        raise SystemExit(collect())
    else:
        raise SystemExit('only default PLAN or --execute is supported')
