#!/usr/bin/env python3
"""Three fixed commit root trees only; no source expansion, fetch, blob read or build."""
import base64,datetime,gzip,hashlib,json,os,re,selectors,signal,stat,subprocess,sys,time
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


SOURCE_ROOT = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
PROJECTS = (
    ('frameworks/base', '94b4c163b7dfe5ce3607f7bb8456f9573f7de57d'),
    ('frameworks/native', 'ae266dcb706d083868578cfedce381ef44488a07'),
    ('external/skia', '508606366e71a3daa933a4e08bc49b84e387ec18'),
)
GIT = Path('/usr/bin/git')
GIT_BYTES = 4547768
GIT_SHA = 'ed8b2df973b28c0fb773b9c0dc0816d3ee2b3835bb932d9153c21417bb51b362'
GIT_AUTHORITY_SHA = '45d3a3307cf40c57c1835f1a275be7cb2e920f0d2b703880756ce0bd89386cfd'
ORIGINAL_LOCK_SHA = '4d8f2d047254268305f4802d9dd67bebdfd162d836664c733ecc07e2f9ced178'
OUTPUT_BOUND = 32768
ENTRY_BOUND = 128
ENV = {
    'PATH':'/usr/bin:/bin', 'LANG':'C', 'LC_ALL':'C', 'TZ':'UTC',
    'GIT_NO_LAZY_FETCH':'1', 'GIT_NO_REPLACE_OBJECTS':'1',
    'GIT_OPTIONAL_LOCKS':'0', 'GIT_TERMINAL_PROMPT':'0',
    'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null',
}


def error_row(error):
    return {'type':type(error).__name__, 'message':str(error),
            'errno':getattr(error,'errno',None), 'filename':getattr(error,'filename',None)}


def fail(report, phase, error):
    row={'phase':phase, 'error':error_row(error)}
    if report['first_error'] is None:
        report['first_error']=row
    else:
        report['secondary_errors'].append(row)
    report['state']='FAIL'


def tool_snapshot(fd):
    before=os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_uid==0 and
            before.st_gid==0 and not (before.st_mode & 0o022) and
            before.st_size==GIT_BYTES and before.st_mode & 0o111,
            'fixed root-owned Git type, ownership, size or executable mode differs')
    require(GIT.resolve(strict=True)==GIT, 'fixed Git path acquired an alias')
    os.lseek(fd,0,os.SEEK_SET)
    digest=hashlib.sha256(); total=0
    while True:
        block=os.read(fd,65536)
        if not block: break
        total+=len(block)
        require(total<=GIT_BYTES, 'held Git grew beyond its exact bound')
        digest.update(block)
    after=os.fstat(fd); named=GIT.lstat()
    require(total==GIT_BYTES and digest.hexdigest()==GIT_SHA and
            identity(before)==identity(after)==identity(named),
            'held Git contents or named identity differs from the qualified tool')
    return {'path':str(GIT), 'bytes':total, 'sha256':digest.hexdigest(),
            'uid':before.st_uid, 'gid':before.st_gid,
            'held_before':identity(before), 'held_after':identity(after),
            'named_after':identity(named), 'authority_sha256':GIT_AUTHORITY_SHA}


def directory_snapshot(path, fd):
    held=os.fstat(fd); named=path.lstat()
    require(stat.S_ISDIR(held.st_mode) and stat.S_ISDIR(named.st_mode) and
            identity(held)==identity(named) and path.resolve(strict=True)==path,
            'fixed repository directory identity or canonical path differs')
    return {'path':str(path), 'held_identity':identity(held),
            'named_identity':identity(named), 'uid':held.st_uid, 'gid':held.st_gid}


def output_row(raw, complete):
    return {'bytes':len(raw), 'sha256':sha(raw),
            'base64':base64.b64encode(raw).decode('ascii'),
            'complete':complete}


def read_tree(relative, commit, git_fd, overall_deadline, report):
    path=SOURCE_ROOT/relative
    require(path.resolve(strict=True)==path, 'fixed repository path is aliased')
    for parent in (path,*path.parents):
        require(stat.S_ISDIR(parent.lstat().st_mode), 'fixed repository ancestor is aliased')
    directory_fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW)
    row={'repository':str(path), 'commit':commit, 'recursive':False,
         'entry_bound':ENTRY_BOUND, 'stdout_bound':OUTPUT_BOUND,
         'stderr_bound':OUTPUT_BOUND, 'started_utc':utc(),
         'child_pid':None, 'returncode':None, 'joined':False,
         'forced_kill':False, 'timed_out':False, 'error':None}
    report['commands'].append(row)
    process=None; selector=None; streams={}; buffers={'stdout':bytearray(),'stderr':bytearray()}
    eof=set(); primary=None; after_error=None
    def note_after_error(phase, error):
        nonlocal after_error
        if after_error is None: after_error=error
        row.setdefault('secondary_errors',[]).append({'phase':phase,'error':error_row(error)})
    try:
        row['directory_before']=directory_snapshot(path,directory_fd)
        args=[str(GIT),'--no-pager','--no-replace-objects',
              '-c','core.fsmonitor=false','-c','core.untrackedCache=false',
              '-C',str(path),'ls-tree','-z',commit]
        row['argv']=args
        require(time.monotonic()<overall_deadline, 'overall read deadline elapsed before child start')
        process=subprocess.Popen(args, executable='/proc/self/fd/'+str(git_fd),
                  cwd='/',env=ENV,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE,close_fds=True,pass_fds=(git_fd,),start_new_session=True)
        row['child_pid']=process.pid
        selector=selectors.DefaultSelector()
        for name,stream in [('stdout',process.stdout),('stderr',process.stderr)]:
            streams[name]=stream
            os.set_blocking(stream.fileno(),False)
            selector.register(stream,selectors.EVENT_READ,name)
        deadline=min(overall_deadline,time.monotonic()+6.0)
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:
                row['timed_out']=True
                raise TimeoutError('fixed Git child exceeded its six-second/overall deadline')
            for key,_ in selector.select(min(remaining,0.1)):
                name=key.data
                raw=os.read(key.fd,min(8192,OUTPUT_BOUND+1-len(buffers[name])))
                if not raw:
                    selector.unregister(key.fileobj); eof.add(name); continue
                buffers[name].extend(raw)
                require(len(buffers[name])<=OUTPUT_BOUND, name+' exceeded fixed 32768-byte bound')
        remaining=deadline-time.monotonic()
        if remaining<=0:
            row['timed_out']=True
            raise TimeoutError('fixed Git child join deadline elapsed')
        try:
            row['returncode']=process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            row['timed_out']=True
            raise TimeoutError('fixed Git child did not join before deadline') from error
        row['joined']=True
        require(row['returncode']==0, 'fixed Git ls-tree returned nonzero')
        require(not buffers['stderr'], 'fixed Git ls-tree emitted stderr')
        raw=bytes(buffers['stdout'])
        require(raw and raw.endswith(b'\0'), 'root tree output empty or incomplete')
        records=raw[:-1].split(b'\0')
        require(0<len(records)<=ENTRY_BOUND, 'root tree exceeds fixed 128-entry bound')
        entries=[]; seen=set()
        for record in records:
            match=re.fullmatch(rb'([0-7]{6}) (tree|blob|commit) ([0-9a-f]{40})\t([^\x00]+)',record)
            require(match is not None, 'unrecognized complete root tree row')
            mode,kind,object_id,name=match.groups()
            require(name not in (b'.',b'..') and b'/' not in name and name not in seen,
                    'root tree name is not a unique top-level component')
            seen.add(name)
            entries.append({'mode':mode.decode('ascii'),'type':kind.decode('ascii'),
                            'object':object_id.decode('ascii'),'name':name.decode('utf-8')})
        row['entries']=entries
        row['entry_count']=len(entries)
        row['top_level_directories']=[entry['name'] for entry in entries if entry['type']=='tree']
    except BaseException as error:
        primary=error
        row['error']=error_row(error)
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill(); row['forced_kill']=True
                row['returncode']=process.wait(timeout=2.0)
                row['joined']=True
            except BaseException as error:
                row['join_error']=error_row(error)
                note_after_error('child-join',error)
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                note_after_error('selector-close',error)
        # Popen owns both pipes even if selector setup failed before registration.
        if process is not None:
            for name,stream in [('stdout',process.stdout),('stderr',process.stderr)]:
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException as error:
                        note_after_error(name+'-close',error)
        for name in buffers:
            row[name]=output_row(bytes(buffers[name]),name in eof)
        try:
            row['directory_after']=directory_snapshot(path,directory_fd)
            require(row['directory_after']==row.get('directory_before'), 'repository directory changed during root tree observation')
        except BaseException as error:
            row['postcheck_error']=error_row(error)
            note_after_error('directory-postcheck',error)
        finally:
            try:
                os.close(directory_fd)
            except BaseException as error:
                note_after_error('directory-close',error)
        row['finished_utc']=utc()
    if primary is not None:
        if after_error is not None: row['secondary_error']=error_row(after_error)
        raise primary
    if after_error is not None: raise after_error
    require(row['joined'] and not row['forced_kill'] and not row['timed_out'], 'child did not finish normally and join')
    return row


def stop_signal(number, _frame):
    raise RuntimeError('controller interrupted by signal '+str(number))


def main():
    report={'schema':1,'state':'RUNNING','started_utc':utc(), 'commands':[],
            'first_error':None,'secondary_errors':[],
            'tool_authority_sha256':GIT_AUTHORITY_SHA,
            'source_lock_reference_sha256':ORIGINAL_LOCK_SHA,
            'source_lock_reobserved':False, 'source_lock_modified':False,
            'git_environment':ENV, 'Main_actions':0, 'Main_identity_observed':False,
            'fetches_requested':0,'blob_reads_requested':0,'recursive_git_reads':0,
            'source_expansions':0,'builds_started':0,'transitive_build_closure_qualified':False}
    git_fd=-1; resource_fd=-1; before=None
    try:
        require(os.getuid()==os.geteuid()==1000, 'ordinary operator UID1000 required')
        signal.signal(signal.SIGTERM,stop_signal); signal.signal(signal.SIGINT,stop_signal)
        resource_fd,before=begin_resources(); report['owned_resources_before']=before
        git_fd=os.open(GIT,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
        report['git_before']=tool_snapshot(git_fd)
        deadline=time.monotonic()+22.0
        for relative,commit in PROJECTS:
            read_tree(relative,commit,git_fd,deadline,report)
        require(len(report['commands'])==3, 'three exact root trees were not all completed')
        report['state']='PASS_THREE_FIXED_COMMIT_ROOT_TREES'
    except BaseException as error:
        fail(report,'observation',error)
    finally:
        if git_fd>=0:
            try:
                report['git_after']=tool_snapshot(git_fd)
                require(report['git_before']==report['git_after'], 'qualified Git changed during observation')
            except BaseException as error:
                fail(report,'tool-postcheck',error)
            finally:
                try:
                    os.close(git_fd)
                except BaseException as error:
                    fail(report,'git-close',error)
        try:
            require(resource_fd>=0 and before is not None, 'owned resource admission incomplete')
            report['owned_resource_gate']=finish_resources(resource_fd,before,report)
        except BaseException as error:
            fail(report,'resource-postcheck',error)
        finally:
            if resource_fd>=0:
                try:
                    os.close(resource_fd)
                except BaseException as error:
                    fail(report,'resource-close',error)
        report['all_started_children_joined']=all(c['joined'] for c in report['commands'] if c['child_pid'] is not None)
        if not report['all_started_children_joined']:
            fail(report,'child-join',RuntimeError('a started exact child was not joined'))
        report['finished_utc']=utc()
    raw=(json.dumps(report,ensure_ascii=True,separators=(',',':'))+'\n').encode('utf-8')
    encoded=gzip.compress(raw,compresslevel=6,mtime=0)
    envelope={'encoding':'gzip+base64','uncompressed_bytes':len(raw),'sha256':sha(raw),
              'gzip_bytes':len(encoded),'gzip_sha256':sha(encoded),
              'payload':base64.b64encode(encoded).decode('ascii')}
    print(json.dumps(envelope,separators=(',',':')),flush=True)
    return 0 if report['state']=='PASS_THREE_FIXED_COMMIT_ROOT_TREES' else 1


if __name__=='__main__':
    sys.exit(main())
