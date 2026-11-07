#!/usr/bin/env python3
"""Read fixed image-test tools. No tool, build, image, mount or service is executed."""
import datetime,hashlib,json,os,shutil,stat,sys
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

ROOT = Path('/home/alex/work/pocket4-native-generation-image-tools-readonly-02-20261105')
TOOLS = {
    'zip': ('/usr/bin/zip',),
    'unzip': ('/usr/bin/unzip',),
    'debugfs': ('/usr/bin/debugfs', '/usr/sbin/debugfs'),
    'mke2fs': ('/usr/bin/mke2fs', '/usr/sbin/mke2fs'),
    'fsck.erofs': ('/usr/bin/fsck.erofs', '/usr/sbin/fsck.erofs'),
    'mkfs.erofs': ('/usr/bin/mkfs.erofs', '/usr/sbin/mkfs.erofs'),
    'fakeroot': ('/usr/bin/fakeroot',),
    'chown': ('/usr/bin/chown',),
    'setfattr': ('/usr/bin/setfattr',),
}
CONTROLLED_PATH = '/usr/bin:/usr/sbin:/bin:/sbin'
PRIOR_PATH = Path('/home/alex/work/pocket4-native-generation-image-tools-readonly-01-20261105/result.json')
PRIOR_SHA = '85ba1d47a80f57de6ba5af983cf90d89171f7139de66a5a7136daabfbbca5a7d'
BACKENDS = (
    '/usr/bin/faked', '/usr/bin/faked-sysv', '/usr/bin/faked-tcp',
    '/usr/lib/libfakeroot.so', '/usr/lib/libfakeroot/libfakeroot.so',
    '/usr/lib/x86_64-linux-gnu/libfakeroot/libfakeroot.so',
    '/usr/lib/x86_64-linux-gnu/libfakeroot/libfakeroot-sysv.so',
    '/usr/lib/x86_64-linux-gnu/libfakeroot/libfakeroot-tcp.so',
    '/bin/sh', '/usr/bin/getopt',
)


def observe(requested):
    path = Path(requested)
    try:
        resolved = path.resolve(strict=True)
        require(any(resolved.is_relative_to(root) for root in
                    (Path('/usr/bin'), Path('/usr/sbin'), Path('/usr/lib'))),
                'resolved system input outside fixed roots: ' + str(path))
        fd = os.open(resolved, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        return {'requested_path': str(path), 'absent': True,
                'error': {'type': type(error).__name__, 'errno': error.errno,
                          'filename': error.filename}}
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
                not (before.st_mode & 0o022) and before.st_size <= 64 * 1024 * 1024,
                'expected root-owned, non-writable bounded regular system input: ' + str(path))
        digest = hashlib.sha256()
        prefix = b''
        total = 0
        while True:
            raw = os.read(fd, 65536)
            if not raw:
                break
            if len(prefix) < 65536:
                prefix += raw[:65536-len(prefix)]
            digest.update(raw)
            total += len(raw)
            require(total <= 64 * 1024 * 1024, 'system input grew beyond bound')
        after = os.fstat(fd)
        named = resolved.lstat()
        require(total == before.st_size and identity(before) == identity(after) == identity(named) and
                path.resolve(strict=True) == resolved, 'held/resolved system input changed')
        result = {'requested_path': str(path), 'resolved_path': str(resolved),
                  'bytes': total, 'sha256': digest.hexdigest(), 'uid': before.st_uid,
                  'held_before': identity(before), 'held_after': identity(after),
                  'named_after': identity(named), 'is_ELF': prefix.startswith(b'\x7fELF')}
        if prefix.startswith(b'#!'):
            require(total <= 65536, 'system wrapper exceeds complete source bound')
            result['complete_script_source'] = prefix.decode('utf-8')
        return result
    finally:
        os.close(fd)


def prior_failure():
    fd = os.open(PRIOR_PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 1000 and
                not (before.st_mode & 0o022) and before.st_size <= 16384,
                'prior owned observation type/owner/bound differs')
        raw = os.read(fd, 16385)
        require(len(raw) == before.st_size and len(raw) <= 16384 and sha(raw) == PRIOR_SHA and
                identity(before) == identity(os.fstat(fd)) == identity(PRIOR_PATH.lstat()),
                'prior failure receipt changed')
        observed = json.loads(raw)
        require(observed['state'] == 'FAIL' and list(observed['tools']) == ['zip', 'unzip'] and
                observed['backend_observations'] == [] and observed['commands_executed'] == 0 and
                observed['error'] == "RuntimeError('required fixed test tool absent from controlled PATH: debugfs')",
                'prior observation is not the recorded PATH failure')
        return {'path': str(PRIOR_PATH), 'bytes': len(raw), 'sha256': sha(raw),
                'held_before': identity(before), 'held_after': identity(os.fstat(fd)),
                'named_after': identity(PRIOR_PATH.lstat()), 'state': observed['state']}
    finally:
        os.close(fd)


def execute():
    require(os.getuid() == os.geteuid() == 1000, 'ordinary operator required')
    for path in (ROOT.parent, *ROOT.parent.parents):
        require(stat.S_ISDIR(path.lstat().st_mode), 'evidence parent alias rejected')
    require(not ROOT.exists() and not ROOT.is_symlink(), 'fresh evidence root required')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    report = {'schema': 1, 'state': 'RUNNING', 'started_utc': utc(),
              'Main_actions': 0, 'commands_executed': 0, 'builds_started': 0,
              'image_or_mount_actions': 0, 'install_update_actions': 0,
              'tools': {}, 'tool_candidate_observations': {}, 'missing_required_tools': [],
              'backend_observations': [], 'controlled_selection_PATH': CONTROLLED_PATH,
              'fakeroot_backend_selection_qualified': False,
              'dynamic_library_closure_qualified': False,
              'purpose': 'Read exact existing image-test tools and complete fakeroot wrapper before any tool execution.'}
    resource_fd = -1
    resource_before = None
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        report['prior_failed_observation'] = prior_failure()
        for name, paths in TOOLS.items():
            rows = [observe(path) for path in paths]
            report['tool_candidate_observations'][name] = rows
            available = [row for row in rows if row.get('absent') is not True]
            if not available:
                report['missing_required_tools'].append(name)
                continue
            selected = available[0]
            require(selected['held_before'][2] & 0o111,
                    'selected fixed system input is not executable: ' + name)
            require(shutil.which(name, path=CONTROLLED_PATH) == selected['requested_path'],
                    'controlled selection differs from the fixed observed path: ' + name)
            report['tools'][name] = selected
        for name in BACKENDS:
            report['backend_observations'].append(observe(name))
        # Missing fixed tools do not suppress the remaining readonly evidence.
        # They still make the completed observation ineligible for execution.
        for name, rows in report['tool_candidate_observations'].items():
            for row in rows:
                require(observe(row['requested_path']) == row,
                        'fixed tool candidate changed after read: ' + name)
        for name, row in report['tools'].items():
            require(shutil.which(name, path=CONTROLLED_PATH) == row['requested_path'],
                    'controlled tool selection changed after read: ' + name)
        for row in report['backend_observations']:
            require(observe(row['requested_path']) == row, 'fixed backend observation changed after read')
        require(prior_failure() == report['prior_failed_observation'], 'prior receipt changed during observation')
        require(not report['missing_required_tools'], 'one or more required fixed tools remain absent')
        report['observations_unchanged_after'] = True
        report['state'] = 'PASS_FIXED_READ_ONLY_OBSERVATIONS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
                                  'filename': getattr(error, 'filename', None)}
    finally:
        try:
            require(resource_fd >= 0 and resource_before is not None, 'resource admission incomplete')
            report['owned_resource_gate'] = finish_resources(resource_fd, resource_before, report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass': False, 'error': repr(error)}
            report['state'] = 'FAIL'
        finally:
            if resource_fd >= 0:
                os.close(resource_fd)
        report['finished_utc'] = utc()
        raw = (json.dumps(report, indent=2) + '\n').encode()
        require(len(raw) <= 262144, 'evidence exceeds fixed output bound')
        fd = os.open(ROOT/'result.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(fd, 'wb') as stream:
            require(stream.write(raw) == len(raw), 'short result write')
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({'state': report['state'], 'result': {'path': str(ROOT/'result.json'),
                          'bytes': len(raw), 'sha256': sha(raw)}, 'commands_executed': 0}), flush=True)
    return 0 if report['state'] == 'PASS_FIXED_READ_ONLY_OBSERVATIONS' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'state': 'PLAN_ONLY', 'fixed_tool_candidates': TOOLS,
                          'fixed_backend_paths': BACKENDS, 'commands_executed': 0,
                          'remote_actions': 0, 'requires_explicit_execute_once': True}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: collect.py [--execute-once]')
