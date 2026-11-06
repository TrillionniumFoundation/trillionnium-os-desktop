#!/usr/bin/env python3
"""Five fixed work aliases: held metadata and link text only; no target follow."""
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


WORK=Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1')
WORK_IDENTITY=[66306,40166050,16893,1000,1000]
ALIASES=('base-system','mesa-source','python','mesa-tools','framework-res.apk')
PRIOR_RESULT={'bytes':47126,'sha256':'22bb492e41a71eaa99287e913ccee842d473f7f7b2d21f9faf0aced38408d0c3'}
MAX_LINK_BYTES=4096
MAX_REPORT=65536


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


def stop_signal(signum,frame):
    raise RuntimeError('fixed metadata reader interrupted by signal '+str(signum))


def plan():
    return {'schema':1,'state':'PLAN_ONLY','work':str(WORK),'work_identity':WORK_IDENTITY,
            'aliases':[str(WORK/name) for name in ALIASES],
            'retained_prior_failure':PRIOR_RESULT,'per_link_max_bytes':MAX_LINK_BYTES,
            'maximum_report_bytes':MAX_REPORT,'observation_deadline_seconds':24,
            'CPUQuota_percent':25,'MemoryMax':134217728,'timeout_seconds':30,
            'target_follow_actions':0,'target_content_reads':0,'directory_enumerations':0,
            'source_or_workspace_writes':0,'subprocesses':0,'Main_actions':0,
            'normal_builder_admitted':False,'transitive_build_closure_qualified':False}


def collect():
    report=plan();report.update(state='COLLECTING',started_utc=utc(),aliases=[],parent_chain=[],
        first_error=None,secondary_errors=[],started_children=0,joined_children=0,forced_cleanup=0,
        Main_identity_observed=False,source_authorities_reexecuted=False)
    state={'deadline':time.monotonic()+24,'directories':{},'aliases':[],'early_close_errors':[]}
    resource_fd=None;before=None
    try:
        require(os.getuid()==1000 and os.geteuid()==1000 and os.getgid()==1000 and os.getegid()==1000,
                'fixed metadata reader requires the original operator UID/GID')
        resource_fd,before=begin_resources()
        report['owned_resources_before']=before
        work_fd=directory(WORK,state)
        require(directory_identity(os.fstat(work_fd))==WORK_IDENTITY,
                'work directory differs from actual read01 identity')
        for name in ALIASES: observe_alias(name,state,report)
    except BaseException as error:
        note_error(report,'collect',error)
    finally:
        try: recheck_aliases(state,report)
        except BaseException as error: note_error(report,'recheck',error)
        report['parent_chain']=[row for fd,row in state['directories'].values()]
        for row in state['early_close_errors']:
            if report['first_error'] is None: report['first_error']=row
            else: report['secondary_errors'].append(row)
            report['state']='FAIL'
        for fd,name,row in reversed(state['aliases']):
            try: os.close(fd)
            except BaseException as error: note_error(report,'alias-close',error,WORK/name)
        for path,(fd,row) in reversed(tuple(state['directories'].items())):
            try: os.close(fd)
            except BaseException as error: note_error(report,'parent-close',error,path)
        if resource_fd is not None and before is not None:
            try: report['owned_resource_gate']=finish_resources(resource_fd,before,report)
            except BaseException as error: note_error(report,'owned-resource-final',error)
        if resource_fd is not None:
            try: os.close(resource_fd)
            except BaseException as error: note_error(report,'owned-resource-close',error)
    complete=(len(report['aliases'])==len(ALIASES) and
              all(row.get('error') is None and row.get('revalidated_unchanged') is True
                  for row in report['aliases']))
    report['all_five_aliases_observed_and_revalidated']=complete
    if not complete and report['first_error'] is None:
        note_error(report,'complete',RuntimeError('the fixed five aliases were not all observed'))
    report['state']='PASS_FIXED_ALIAS_METADATA_ONLY' if report['first_error'] is None else 'FAIL'
    report['finished_utc']=utc()
    raw=json.dumps(report,ensure_ascii=True,separators=(',',':')).encode()
    require(len(raw)<=MAX_REPORT,'fixed alias report exceeds its finite output bound')
    packed=gzip.compress(raw,mtime=0)
    print(json.dumps({'encoding':'gzip+base64','uncompressed_bytes':len(raw),'sha256':sha(raw),
        'gzip_bytes':len(packed),'gzip_sha256':sha(packed),'payload':base64.b64encode(packed).decode(),
        'all_five_aliases_complete':complete and report['first_error'] is None},sort_keys=True),flush=True)
    return 0 if report['first_error'] is None else 1


if __name__=='__main__':
    if len(sys.argv)==1:
        print(json.dumps(plan(),sort_keys=True,indent=2))
    elif sys.argv[1:]==['--execute']:
        signal.signal(signal.SIGTERM,stop_signal)
        signal.signal(signal.SIGINT,stop_signal)
        raise SystemExit(collect())
    else:
        raise SystemExit('only default PLAN or the exact --execute mode is supported')
