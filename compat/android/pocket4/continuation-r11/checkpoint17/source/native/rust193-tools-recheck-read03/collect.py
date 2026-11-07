#!/usr/bin/env python3
"""Fixed installed tools: held hashes only; no tool execution or install/update."""
import base64,datetime,gzip,hashlib,json,os,stat,sys,time
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

EXPECTED = [{'requested_path': '/home/alex/.cargo/bin/rustup', 'resolved_path': '/home/alex/.cargo/bin/rustup', 'bytes': 20838840, 'sha256': '4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10', 'held_before': [66306, 31732023, 33261, 20838840, 1773571247969072921, 1785828354765868529], 'held_after': [66306, 31732023, 33261, 20838840, 1773571247969072921, 1785828354765868529]}, {'requested_path': '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/cargo', 'resolved_path': '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/cargo', 'bytes': 40753664, 'sha256': '9548937d530bf439ff1ba47a3b2bd26eeb9c3aff1961c20c01798613de922578', 'held_before': [66306, 37113966, 33261, 40753664, 1793527515454921431, 1793527515557925710], 'held_after': [66306, 37113966, 33261, 40753664, 1793527515454921431, 1793527515557925710]}, {'requested_path': '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/rustc', 'resolved_path': '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/rustc', 'bytes': 656704, 'sha256': 'd32249a7c3bfcfc67b471460386e46323accae7125e344567a12d5664d99bb57', 'held_before': [66306, 37114023, 33261, 656704, 1793527620057550401, 1793527625615953418], 'held_after': [66306, 37114023, 33261, 656704, 1793527620057550401, 1793527625615953418]}, {'requested_path': '/usr/bin/cc', 'resolved_path': '/usr/bin/x86_64-linux-gnu-gcc-15', 'bytes': 1305304, 'sha256': 'b5f1b773a7c733738352000c92a077dc5852a1a2fc6d836b1e411be1e9ec5f88', 'held_before': [66306, 108008578, 33261, 1305304, 1774174097000000000, 1791083705251606151], 'held_after': [66306, 108008578, 33261, 1305304, 1774174097000000000, 1791083705251606151]}, {'requested_path': '/usr/bin/ld', 'resolved_path': '/usr/bin/x86_64-linux-gnu-ld.bfd', 'bytes': 1890472, 'sha256': '97f48d93b8b076a92d2809ec29dcb17f0f37c8827358f832255e2ed22fef6075', 'held_before': [66306, 108034599, 33261, 1890472, 1773538381000000000, 1791083704198584053], 'held_after': [66306, 108034599, 33261, 1890472, 1773538381000000000, 1791083704198584053]}, {'requested_path': '/usr/bin/ar', 'resolved_path': '/usr/bin/x86_64-linux-gnu-ar', 'bytes': 55944, 'sha256': '531473816bf553e863df5aab14c8177c72b732cf80c51dcf0fa990a50125041c', 'held_before': [66306, 108008448, 33261, 55944, 1773538381000000000, 1791083704197584032], 'held_after': [66306, 108008448, 33261, 55944, 1773538381000000000, 1791083704197584032]}, {'requested_path': '/usr/bin/as', 'resolved_path': '/usr/bin/x86_64-linux-gnu-as', 'bytes': 826608, 'sha256': '4e5fcaa3cdc160173cb5cfe7aa35dc39d7aa1f06ba8d75b8d923bbae5473991b', 'held_before': [66306, 108034591, 33261, 826608, 1773538381000000000, 1791083704197584032], 'held_after': [66306, 108034591, 33261, 826608, 1773538381000000000, 1791083704197584032]}, {'requested_path': '/usr/bin/git', 'resolved_path': '/usr/bin/git', 'bytes': 4547768, 'sha256': 'ed8b2df973b28c0fb773b9c0dc0816d3ee2b3835bb932d9153c21417bb51b362', 'held_before': [66306, 108004715, 33261, 4547768, 1792159905000000000, 1792504324680976384], 'held_after': [66306, 108004715, 33261, 4547768, 1792159905000000000, 1792504324680976384]}, {'requested_path': '/usr/bin/ninja', 'resolved_path': '/usr/bin/ninja', 'bytes': 350624, 'sha256': '91e9548850cda2799facfdaa7abe33f9e978832f85e98212255708a7bbe437f2', 'held_before': [66306, 108037344, 33261, 350624, 1763657883000000000, 1791083933685882212], 'held_after': [66306, 108037344, 33261, 350624, 1763657883000000000, 1791083933685882212]}, {'requested_path': '/usr/bin/cp', 'resolved_path': '/usr/bin/gnucp', 'bytes': 137840, 'sha256': '8fcdb2485ebc68f00392d647b3d3d9130f0d4bb9f72c69ee258086dd63e1c122', 'held_before': [66306, 108025621, 33261, 137840, 1787670447000000000, 1791083646529510452], 'held_after': [66306, 108025621, 33261, 137840, 1787670447000000000, 1791083646529510452]}, {'requested_path': '/usr/bin/ldd', 'resolved_path': '/usr/bin/ldd', 'bytes': 5390, 'sha256': '8b85fafd8313f5e55058f543a66d3826adcd11e073c697f9d0208755378e2054', 'held_before': [66306, 108017658, 33261, 5390, 1788444579000000000, 1791083352725946198], 'held_after': [66306, 108017658, 33261, 5390, 1788444579000000000, 1791083352725946198]}, {'requested_path': '/usr/libexec/gcc/x86_64-linux-gnu/15/collect2', 'resolved_path': '/usr/libexec/gcc/x86_64-linux-gnu/15/collect2', 'bytes': 479104, 'sha256': '8ab5d946ba2c948e5ea5c91e25a104439302e0599a521785770d10690c565437', 'held_before': [66306, 3032898, 33261, 479104, 1774174097000000000, 1791083705252606172], 'held_after': [66306, 3032898, 33261, 479104, 1774174097000000000, 1791083705252606172]}]
CONFIG = {'requested_path': '/home/alex/work/pocket4-signal-mask-r11-build-memory-01/builder-source/rust-toolchain.toml', 'resolved_path': '/home/alex/work/pocket4-signal-mask-r11-build-memory-01/builder-source/rust-toolchain.toml', 'bytes': 86, 'sha256': '8bc51ecab82415fddd8489604f2424e137d71856e7f65cbdcfaa48850d794b46', 'held_before': [66306, 33732367, 33204, 86, 1793551340473884787, 1793804758887232592], 'held_after': [66306, 33732367, 33204, 86, 1793551340473884787, 1793804758887232592]}
ALLOWED_CONTENT_PATHS = ['/home/alex/.cargo/bin/rustup', '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/cargo', '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/rustc', '/home/alex/work/pocket4-signal-mask-r11-build-memory-01/builder-source/rust-toolchain.toml', '/usr/bin/git', '/usr/bin/gnucp', '/usr/bin/ldd', '/usr/bin/ninja', '/usr/bin/x86_64-linux-gnu-ar', '/usr/bin/x86_64-linux-gnu-as', '/usr/bin/x86_64-linux-gnu-gcc-15', '/usr/bin/x86_64-linux-gnu-ld.bfd', '/usr/libexec/gcc/x86_64-linux-gnu/15/collect2']
PRIOR_PIN = {'bytes': 9419, 'sha256': '45d3a3307cf40c57c1835f1a275be7cb2e920f0d2b703880756ce0bd89386cfd'}
FAILURE_PIN = {'bytes': 7681, 'sha256': '44da2c2f9f2df67bc1c32fe25f003442378b19e341da4add8869b77488e7fee3'}

def read_tool(wanted, budget):
    path = Path(wanted['requested_path'])
    check_time(budget)
    named_before = path.lstat()
    link_before = os.readlink(path) if stat.S_ISLNK(named_before.st_mode) else None
    resolved = path.resolve(strict=True)
    row = {'requested_path': str(path), 'expected': wanted,
           'requested_named_before': identity(named_before), 'requested_link_text_before': link_before,
           'resolved_path': str(resolved), 'error': None, 'content_read': False}
    # A changed resolution is evidence, not permission to read an unseen target.
    if str(resolved) != wanted['resolved_path']:
        row['resolution_changed'] = True
        row['unknown_target_contents_read'] = False
        row['compilation_admission_fields_equal'] = False
        row['error'] = {'type': 'UnapprovedResolvedTarget', 'message': 'fixed tool resolves to a different target'}
        return row
    require(str(resolved) in ALLOWED_CONTENT_PATHS, 'tool target is outside the fixed original content list')
    fd = os.open(resolved, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    primary = None
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= 256 * 1024**2,
                'fixed tool/config is not a bounded regular file')
        digest = hashlib.sha256()
        total = 0
        while True:
            check_time(budget)
            block = os.read(fd, 65536)
            if not block:
                break
            total += len(block)
            budget['bytes_read'] += len(block)
            require(total <= before.st_size and budget['bytes_read'] <= 512 * 1024**2,
                    'fixed tool/config grew or aggregate observation bound exceeded')
            digest.update(block)
        after = os.fstat(fd)
        resolved_named = resolved.lstat()
        named_after = path.lstat()
        link_after = os.readlink(path) if stat.S_ISLNK(named_after.st_mode) else None
        require(total == before.st_size and identity(before) == identity(after) == identity(resolved_named),
                'held tool/config bytes or object changed during read')
        require(identity(named_before) == identity(named_after) and link_before == link_after and
                path.resolve(strict=True) == resolved, 'requested tool alias changed during observation')
        row.update({'bytes': total, 'sha256': digest.hexdigest(), 'content_read': True,
                    'held_before': identity(before), 'held_after': identity(after),
                    'resolved_named_after': identity(resolved_named),
                    'requested_named_after': identity(named_after), 'requested_link_text_after': link_after,
                    'resolution_changed': False})
        row['changed_compilation_admission_fields'] = [key for key in ('sha256', 'bytes', 'resolved_path')
                                                     if row[key] != wanted[key]]
        row['compilation_admission_fields_equal'] = not row['changed_compilation_admission_fields']
        row['original_object_metadata_equal'] = row['held_before'] == wanted['held_before']
        return row
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            os.close(fd)
        except BaseException as error:
            if primary is None:
                raise
            budget['secondary_close_errors'].append({'path': str(path), 'error': error_row(error)})


def check_time(budget):
    require(time.monotonic() < budget['deadline'], 'fixed tool observation deadline exceeded')


def collect():
    require(os.getuid() == os.geteuid() == 1000, 'operator UID1000 required')
    report = {'schema': 1, 'state': 'RUNNING', 'started_utc': utc(), 'first_error': None, 'secondary_errors': [],
              'prior_tool_observation': PRIOR_PIN, 'repository_channel': '1.93.0',
              'actual_build_failure': FAILURE_PIN, 'comparison_fields_used_by_compiler': ['sha256', 'bytes', 'resolved_path'],
              'queries': [], 'commands_executed': 0, 'tool_execution': False, 'install_update_actions': 0,
              'builds_started': 0, 'source_writes': 0, 'Main_actions': 0, 'Main_identity_observed': False,
              'fresh_observation_is_not_tool_execution_approval': True, 'complete': False, 'tools': []}
    budget = {'deadline': time.monotonic() + 25, 'bytes_read': 0, 'secondary_close_errors': []}
    resource_fd = -1
    resource_before = None
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        require(len(EXPECTED) == 12 and len({r['requested_path'] for r in EXPECTED}) == 12,
                'fixed original tool set differs')
        for wanted in EXPECTED:
            try:
                row = read_tool(wanted, budget)
                report['tools'].append(row)
                if row['error'] is not None:
                    note_error(report, 'tool-observation', RuntimeError(row['error']['message']), wanted['requested_path'])
            except BaseException as error:
                report['tools'].append({'requested_path': wanted['requested_path'], 'expected': wanted, 'error': error_row(error)})
                note_error(report, 'tool-observation', error, wanted['requested_path'])
        report['repository_toolchain'] = read_tool(CONFIG, budget)
        require(report['repository_toolchain']['error'] is None and
                report['repository_toolchain']['compilation_admission_fields_equal'], 'fixed repository channel source changed')
        for row in report['tools']:
            if not row.get('content_read'):
                continue
            again = read_tool(row['expected'], budget)
            require(again == row, 'tool did not remain identical across the full fixed observation: ' + row['requested_path'])
        require(read_tool(CONFIG, budget) == report['repository_toolchain'], 'repository channel changed after observation')
        report['all_observed_tool_contents_and_aliases_unchanged_after'] = True
        report['changed_tools'] = [{'path': r['requested_path'],
                                    'changed_admission_fields': r.get('changed_compilation_admission_fields', ['unobserved']),
                                    'original_object_metadata_equal': r.get('original_object_metadata_equal')}
                                   for r in report['tools'] if not r.get('compilation_admission_fields_equal')]
        report['complete'] = len(report['tools']) == 12 and all(r.get('content_read') and r['error'] is None for r in report['tools'])
        if report['complete'] and report['first_error'] is None:
            report['state'] = 'PASS_FIXED_TOOL_OBSERVATION_NOT_EXECUTION_APPROVAL'
    except BaseException as error:
        note_error(report, 'fixed-tool-recheck', error)
    finally:
        for row in budget['secondary_close_errors']:
            report['secondary_errors'].append({'phase': 'held-close', **row})
        try:
            require(resource_fd >= 0 and resource_before is not None, 'owned resource admission incomplete')
            report['owned_resource_gate'] = finish_resources(resource_fd, resource_before, report)
        except BaseException as error:
            report['owned_resource_gate'] = {'pass': False, 'error': error_row(error)}
            note_error(report, 'owned-resources-after', error)
        if resource_fd >= 0:
            try:
                os.close(resource_fd)
            except BaseException as error:
                note_error(report, 'owned-resource-close', error)
        if report['first_error'] is not None or report['secondary_errors']:
            report['state'] = 'FAIL'
        report['bytes_read'] = budget['bytes_read']
        report['finished_utc'] = utc()
        raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
        require(len(raw) <= 262144, 'fixed tool observation report exceeded bound')
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        print(json.dumps({'encoding': 'gzip+base64', 'uncompressed_bytes': len(raw), 'sha256': sha(raw),
                          'gzip_bytes': len(compressed), 'gzip_sha256': sha(compressed),
                          'payload': base64.b64encode(compressed).decode(), 'state': report['state']}), flush=True)
    return 0 if report['state'] == 'PASS_FIXED_TOOL_OBSERVATION_NOT_EXECUTION_APPROVAL' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode': 'PLAN', 'fixed_tools': 12, 'fixed_repository_config': CONFIG['requested_path'],
                          'commands_executed': 0, 'builds_started': 0, 'Main_actions': 0,
                          'CPUQuota_percent': 25, 'MemoryMax': 134217728, 'timeout_seconds': 30}))
    elif sys.argv[1:] == ['--execute']:
        raise SystemExit(collect())
    else:
        raise SystemExit('only default PLAN or --execute is supported')
