#!/usr/bin/env python3
"""Private LMKD qualification; no Main UI, lifecycle, signal or config mutation."""
from __future__ import annotations
import argparse
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

CROOT = Path(os.environ.get('P4_LMKD_INPUT_ROOT', '/srv/pocket4-lmkd-inputs'))
NS = ('pid', 'mnt', 'cgroup', 'ipc', 'uts', 'net')
LIMITS = ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max', 'cpu.max')
GIB = 1024**3
UNIT_PREFIX = 'p4-lmkd-fixture-r10-'
DSOS = {'ld-android.so', 'libbase.so', 'libbpf_bcc.so', 'libbpf_minimal.so', 'libc++.so',
        'libc.so', 'libcutils.so', 'libdl.so', 'liblog.so', 'libm.so', 'libmemevents.so',
        'libprocessgroup.so', 'libpsi.so', 'libz.so'}

class Stop(RuntimeError):
    def __init__(self, reason, observation=None):
        super().__init__(reason)
        self.observation = observation
        self.evidence = None

def require(ok, tag):
    if not ok:
        raise Stop(tag)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def directory_policy(path, executable):
    p = Path(path)
    st = p.lstat()
    flags = os.statvfs(p).f_flag
    require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and st.st_gid == 0
            and stat.S_IMODE(st.st_mode) & 0o022 == 0, 'ROOT_OWNED_PARENT_REQUIRED')
    require(not (flags & os.ST_RDONLY), 'READONLY_PARENT')
    require(bool(flags & os.ST_NOEXEC) != executable, 'EXECUTION_LOCATION_POLICY')
    if not executable:
        require(flags & (os.ST_NOSUID | os.ST_NODEV | os.ST_NOEXEC)
                == os.ST_NOSUID | os.ST_NODEV | os.ST_NOEXEC, 'STATE_MOUNT_PROTECTIONS')
    return {'path':str(p), 'dev':st.st_dev, 'inode':st.st_ino,
            'mode':stat.S_IMODE(st.st_mode), 'uid':st.st_uid, 'gid':st.st_gid,
            'mount_flags':flags, 'noexec':bool(flags & os.ST_NOEXEC)}

def read_regular(path, bound=16*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size <= bound,
                'REGULAR_SINGLE_LINK_INPUT_REQUIRED')
        data = b''
        while len(data) <= bound:
            block = os.read(fd, min(65536, bound + 1 - len(data)))
            if not block:
                break
            data += block
        require(len(data) <= bound, 'INPUT_BOUND')
        return data
    finally:
        os.close(fd)

def load_pinned(path, expected):
    require(re.fullmatch(r'[a-f0-9]{64}', expected) is not None, 'SHA256_REQUIRED')
    data = read_regular(path)
    require(sha(data) == expected, 'INPUT_HASH_CHANGED')
    return json.loads(data)

def save(path, obj, mode=0o600):
    data = json.dumps(obj, indent=2, ensure_ascii=True).encode() + b'\n'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def command(argv, timeout=8):
    r = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=timeout, check=False)
    require(len(r.stdout) <= 65536 and len(r.stderr) <= 65536, 'COMMAND_OUTPUT_BOUND')
    require(r.returncode == 0, 'COMMAND_FAILED: ' + repr(argv) + ': ' + r.stderr.decode(errors='replace')[:1024])
    return r.stdout.decode()

def unit_properties(unit):
    names = ('LoadState', 'ActiveState', 'SubState', 'InvocationID', 'MainPID', 'ControlGroup',
             'ExecMainStatus', 'Result')
    text = command(['/usr/bin/systemctl', 'show', unit, '--property=' + ','.join(names)])
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)

def process_info(pid):
    require(type(pid) is int and pid > 1, 'PID_REQUIRED')
    p = Path('/proc') / str(pid)
    fields = (p/'stat').read_text().rsplit(') ', 1)[1].split()
    status = dict(line.split(':', 1) for line in (p/'status').read_text().splitlines() if ':' in line)
    cgroup = (p/'cgroup').read_text()
    require(cgroup.startswith('0::/') and cgroup.count('\n') == 1, 'CGROUP_V2_REQUIRED')
    return {'pid': pid, 'ppid': int(fields[1]), 'start_ticks': int(fields[19]),
            'nspid': [int(x) for x in status['NSpid'].split()],
            'cgroup': cgroup[3:].strip(),
            'ns': {name: (p/'ns'/name).stat().st_ino for name in NS}}

def is_descendant(child, parent):
    p = child
    for _ in range(5):
        info = process_info(p)
        if info['ppid'] == parent:
            return True
        if info['ppid'] <= 1:
            return False
        p = info['ppid']
    return False

def verify_framework_records(records, init, main_cgroup):
    """Critical guest generations are independent from the host/init generation."""
    expected = {'zygote64':('zygote64', '/system/bin/app_process64'),
                'system_server':('system_server', '/system/bin/app_process64'),
                'surfaceflinger':('/system/bin/surfaceflinger', '/system/bin/surfaceflinger')}
    require(len(records) == 3 and {x['role'] for x in records} == set(expected),
            'MAIN_FRAMEWORK_GENERATIONS_MISSING_OR_DUPLICATE')
    by_role = {x['role']:x for x in records}
    require(len({x['pid'] for x in records}) == 3, 'MAIN_FRAMEWORK_PID_ALIAS')
    for role, record in by_role.items():
        require((record['argv0'], record['exe']) == expected[role]
                and record['ns']['pid'] == init['ns']['pid']
                and (record['cgroup'] == main_cgroup or record['cgroup'].startswith(main_cgroup+'/')),
                'MAIN_FRAMEWORK_IDENTITY')
        parent = by_role['zygote64']['pid'] if role == 'system_server' else init['pid']
        require(record['ppid'] == parent and record['start_ticks'] > 0,
                'MAIN_FRAMEWORK_PARENT_OR_START')
    return by_role

def framework_pin(init, main_cgroup):
    def children(parent):
        result = set()
        for task in (Path('/proc')/str(parent)/'task').iterdir():
            result.update(int(x) for x in (task/'children').read_text().split())
        return sorted(result)

    def find(parent, roles):
        matches = []
        argv_roles = {'zygote64':'zygote64', 'system_server':'system_server',
                      '/system/bin/surfaceflinger':'surfaceflinger'}
        for pid in children(parent):
            p = Path('/proc')/str(pid)
            try:
                with (p/'cmdline').open('rb') as stream:
                    argv0 = stream.read(128).split(b'\0', 1)[0].decode('utf-8', 'strict')
            except FileNotFoundError:
                continue
            role = argv_roles.get(argv0)
            if role not in roles:
                continue
            before = process_info(pid)
            record = {**before, 'role':role, 'argv0':argv0, 'exe':os.readlink(p/'exe')}
            require(process_info(pid) == before, 'MAIN_FRAMEWORK_CHANGED_DURING_PIN')
            matches.append(record)
        return matches

    records = find(init['pid'], {'zygote64', 'surfaceflinger'})
    zygotes = [x for x in records if x['role'] == 'zygote64']
    require(len(zygotes) == 1, 'MAIN_ZYGOTE_NOT_UNIQUE')
    records += find(zygotes[0]['pid'], {'system_server'})
    return verify_framework_records(records, init, main_cgroup)

def main_pin(host_pid, init_pid, query_status=True):
    u = unit_properties('droidloomd.service')
    require(u['ActiveState'] == 'active' and re.fullmatch(r'[a-f0-9]{32}', u['InvocationID']),
            'MAIN_DAEMON_NOT_ACTIVE')
    host, init, daemon = process_info(host_pid), process_info(init_pid), process_info(int(u['MainPID']))
    require(init['nspid'][-1] == 1 and len(init['nspid']) >= 2 and is_descendant(init_pid, host_pid),
            'MAIN_INIT_NOT_OWNED_DESCENDANT')
    cg = Path('/sys/fs/cgroup') / u['ControlGroup'].lstrip('/')
    require(str(cg) == '/sys/fs/cgroup/system.slice/droidloomd.service', 'MAIN_CGROUP_UNEXPECTED')
    require(all(x['cgroup'] == u['ControlGroup'] or x['cgroup'].startswith(u['ControlGroup'] + '/')
                for x in (host, init, daemon)), 'MAIN_PROCESS_CGROUP_MISMATCH')
    framework = framework_pin(init, u['ControlGroup'])
    if query_status:
        status = json.loads(command(['/usr/sbin/runuser', '-u', 'alex', '--',
                                     '/usr/bin/droidloomctl', 'status', '--json']))
        require(status.get('ok') is True and status.get('host_pid') == host_pid
                and status.get('state') == 'running' and 'Android is ready' in status.get('message', ''),
                'MAIN_NOT_READY')
    s = cg.stat()
    data = Path('/var/lib/droidloom/users/1000/data').stat()
    return {'host': host, 'init': init, 'daemon': daemon, 'framework': framework,
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'invocation_id': u['InvocationID'], 'cgroup': str(cg),
            'cgroup_identity': [s.st_dev, s.st_ino],
            'config_sha256': sha(read_regular('/etc/droidloom/cell.json', 1024*1024)),
            'userdata_identity': [data.st_dev, data.st_ino],
            'limits': {name: (cg/name).read_text().strip() for name in LIMITS}}

def values(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        key, value = line.split()
        require(key not in result and value.isdecimal(), 'COUNTER_PARSE')
        result[key] = int(value)
    return result

def psi(path):
    data = {}
    for line in Path(path).read_text().splitlines():
        fields = line.split()
        require(fields[0] not in data, 'PSI_DUPLICATE')
        data[fields[0]] = {k: float(v) if k != 'total' else int(v)
                           for k, v in (x.split('=') for x in fields[1:])}
        require(len(fields) == 5 and set(data[fields[0]]) == {'avg10', 'avg60', 'avg300', 'total'}
                and all(math.isfinite(v) and v >= 0 for v in data[fields[0]].values()), 'PSI_FIELDS')
    require(set(data) == {'some', 'full'}, 'PSI_UNKNOWN')
    return data

def health(pin):
    mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    cg = Path(pin['cgroup'])
    out = {'host_available': int(mem['MemAvailable'].split()[0])*1024,
           'host_swap_free': int(mem['SwapFree'].split()[0])*1024,
           'main_current': int((cg/'memory.current').read_text()),
           'main_events': values(cg/'memory.events'), 'main_pids': int((cg/'pids.current').read_text()),
           'main_pids_events': values(cg/'pids.events'),
           'main_psi': psi(cg/'memory.pressure'), 'host_psi': psi('/proc/pressure/memory')}
    return out

def guard_admission(pin, current):
    def check(ok, reason, scope, metric, value, comparison, limit):
        if not ok:
            raise Stop(reason, {'scope':scope, 'metric':metric, 'value':value,
                                'required_comparison':comparison, 'limit':limit})
    check(current['host_available'] >= 8*GIB, 'HOST_RESERVE', 'host',
          'MemAvailable_bytes', current['host_available'], '>=', 8*GIB)
    check(current['host_swap_free'] >= 2*GIB, 'HOST_RESERVE', 'host',
          'SwapFree_bytes', current['host_swap_free'], '>=', 2*GIB)
    check(current['main_current']*100 < int(pin['limits']['memory.max'])*80,
          'MAIN_RAM_ADMISSION', 'main', 'memory.current_bytes', current['main_current'],
          'value * 100 < limit * 80', int(pin['limits']['memory.max']))
    check(current['main_pids']*100 < int(pin['limits']['pids.max'])*80,
          'MAIN_PID_ADMISSION', 'main', 'pids.current', current['main_pids'],
          'value * 100 < limit * 80', int(pin['limits']['pids.max']))
    for scope, name in (('main', 'main_psi'), ('host', 'host_psi')):
        check(current[name]['full']['avg10'] < 10, 'EXTERNAL_MEMORY_PRESSURE', scope,
              'memory.full.avg10_percent', current[name]['full']['avg10'], '<', 10)

def guard_health(current, baseline):
    for name in ('high', 'max', 'oom', 'oom_kill', 'oom_group_kill'):
        if current['main_events'][name] != baseline['main_events'][name]:
            raise Stop('MAIN_MEMORY_EVENT_CHANGED', {'scope':'main',
                       'metric':'memory.events.'+name, 'value':current['main_events'][name],
                       'required_comparison':'==', 'limit':baseline['main_events'][name]})
    if current['main_pids_events'] != baseline['main_pids_events']:
        raise Stop('MAIN_PID_EVENT_CHANGED', {'scope':'main', 'metric':'pids.events',
                   'value':current['main_pids_events'], 'required_comparison':'==',
                   'limit':baseline['main_pids_events']})

def syscall_metadata(raw):
    """Only syscall identity and an FD number; never dereference arguments."""
    parts = raw.strip().split()
    if parts == ['running']:
        return {'state':'running'}
    if not parts:
        return {'state':'empty'}
    number = int(parts[0], 0)
    if number == -1:
        return {'state':'user_mode'}
    result = {'state':'syscall', 'number':number}
    # x86-64 ABI of this fixed Pocket4 target. Other arguments may point to
    # private buffers and are deliberately not retained or dereferenced.
    names = {0:'read', 1:'write', 16:'ioctl', 17:'pread64', 18:'pwrite64',
             19:'readv', 20:'writev', 44:'sendto', 45:'recvfrom', 46:'sendmsg', 47:'recvmsg'}
    if number in names:
        require(len(parts) >= 2, 'OWNED_SYSCALL_METADATA_TRUNCATED')
        result['name'] = names[number]
        result['fd'] = int(parts[1], 0)
    return result

def fixture_observation(unit_cgroup):
    """Read only the independently verified owned domain; never signal a PID."""
    domain = unit_cgroup/'domain'
    result = {'current':int((domain/'memory.current').read_text()),
              'limits':{k:(domain/k).read_text().strip() for k in LIMITS},
              'events':values(domain/'memory.events'), 'stat':values(domain/'memory.stat'),
              'pressure':psi(domain/'memory.pressure'), 'processes':[]}
    identities = Path('/run')/unit_cgroup.name.removesuffix('.service')/'evidence/identities.json'
    labels = {1:('init', None, None)}
    if identities.exists():
        ids = json.loads(read_regular(identities, 16384))
        labels[ids['lmkd_pid']] = ('lmkd', ids['lmkd_start'], 1069)
        for child in ids['children']:
            labels[child['pid']] = (child['label'], child['start'], child['uid'])
    for pid in sorted(set(int(x) for x in (domain/'cgroup.procs').read_text().split())):
        try:
            info = process_info(pid)
            if info['cgroup'] != '/system.slice/'+unit_cgroup.name+'/domain':
                result['processes'].append({'pid':pid, 'membership_changed':True})
                continue
            p = Path('/proc')/str(pid)
            status = dict(line.split(':',1) for line in (p/'status').read_text().splitlines() if ':' in line)
            label, expected_start, expected_uid = labels.get(info['nspid'][-1], ('unmapped', None, None))
            uid = int(status['Uid'].split()[0])
            entry = {**info, 'label':label, 'state':status['State'].strip(),
                'uid':uid, 'oom_score_adj':int((p/'oom_score_adj').read_text()),
                'rss_kib':int(status.get('VmRSS','0 kB').split()[0]),
                'swap_kib':int(status.get('VmSwap','0 kB').split()[0]),
                'registered_start_matches':expected_start is None or expected_start == info['start_ticks'],
                'registered_uid_matches':expected_uid is None or expected_uid == uid}
            if label == 'lmkd' and entry['registered_start_matches'] and entry['registered_uid_matches']:
                entry['thread_waits'] = []
                for task in sorted((p/'task').iterdir()):
                    if not task.name.isdecimal():
                        continue
                    detail = {'tid':int(task.name)}
                    for name in ('comm', 'wchan', 'stack', 'syscall'):
                        try:
                            with (task/name).open() as stream:
                                raw = stream.read(4097)
                            if name == 'syscall':
                                detail[name] = syscall_metadata(raw)
                                fd = detail[name].get('fd')
                                if fd is not None and 0 <= fd < 2048:
                                    try:
                                        detail['syscall_fd_target'] = os.readlink(p/'fd'/str(fd))
                                    except OSError as exc:
                                        detail['syscall_fd_errno'] = exc.errno
                            else:
                                detail[name] = raw[:4096]
                            if len(raw) > 4096:
                                detail[name+'_truncated'] = True
                        except OSError as exc:
                            detail[name+'_errno'] = exc.errno
                    entry['thread_waits'].append(detail)
                entry['pidfds_and_epoll'] = []
                for fdpath in sorted((p/'fd').iterdir()):
                    try:
                        target = os.readlink(fdpath)
                        if target not in ('anon_inode:[pidfd]', 'anon_inode:[eventpoll]'):
                            continue
                        with (p/'fdinfo'/fdpath.name).open() as stream:
                            lines = stream.read(16385).splitlines()
                        detail = {'fd':int(fdpath.name), 'target':target, 'entries':[]}
                        for line in lines:
                            if line.startswith(('Pid:', 'NSpid:')):
                                detail['entries'].append(line)
                            elif line.startswith('tfd:'):
                                match = re.match(r'tfd:\s*(\d+)\s+events:\s*([0-9a-fA-F]+)', line)
                                if match:
                                    detail['entries'].append({'target_fd':int(match[1]), 'events_hex':match[2]})
                        entry['pidfds_and_epoll'].append(detail)
                    except OSError as exc:
                        entry['pidfds_and_epoll'].append({'fd':int(fdpath.name), 'errno':exc.errno})
            result['processes'].append(entry)
        except FileNotFoundError:
            result['processes'].append({'pid':pid, 'gone_during_observation':True})
    return result

def sample_health(pin, path, baseline=None, unit_cgroup=None):
    current = health(pin)
    frame = {'at_unix_ns':time.time_ns(), **current}
    fixture_error = None
    if unit_cgroup is not None:
        try:
            frame['fixture'] = fixture_observation(unit_cgroup)
        except (OSError, Stop, ValueError, KeyError) as exc:
            frame['fixture_observation_error'] = str(exc)
            fixture_error = Stop('OWNED_DOMAIN_OBSERVATION_FAILED',
                                 {'scope':'fixture', 'error':str(exc)})
    # Preserve the exact decision input before applying any policy. In particular,
    # the rejected PSI frame must not disappear behind an exception.
    save(path, frame)
    try:
        if fixture_error is not None:
            raise fixture_error
        guard_admission(pin, current)
        if baseline is not None:
            guard_health(current, baseline)
    except Stop as exc:
        exc.evidence = str(path)
        raise
    return current

def verify_domain_attestation(unit_cgroup, outer, inner, child, bootstrap):
    """Bind workload membership, accounting and monitors to one owned child.

    The unit remains the namespace delegation root and retains the outer hard
    limits. A namespace-root alias is never accepted as the monitored domain.
    """
    domain = unit_cgroup/'domain'
    supervisor = unit_cgroup/'supervisor'
    root_stat, ds, ss = unit_cgroup.lstat(), domain.lstat(), supervisor.lstat()
    require(all(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 for s in (root_stat, ds, ss)),
            'OWNED_CGROUP_DIRECTORIES_REQUIRED')
    require(ds.st_dev == ss.st_dev == root_stat.st_dev
            and len({root_stat.st_ino, ds.st_ino, ss.st_ino}) == 3,
            'MEMORY_DOMAIN_MUST_BE_OWNED_CHILD')
    require(outer['domain_relative'] == inner['domain_relative'] == '/domain'
            and [ds.st_dev, ds.st_ino] == [outer['domain_dev'], outer['domain_ino']]
            == [inner['domain_dev'], inner['domain_ino']], 'DOMAIN_INODE_DISAGREEMENT')
    require(inner['memory_mount_path'] == '/sys/fs/cgroup'
            and [inner['cgroup_dev'], inner['cgroup_ino']] == [ds.st_dev, ds.st_ino],
            'FIXED_MEMORY_MOUNT_MUST_BE_EXACT_CHILD')
    require(inner['root_pressure_write_errno'] == errno.EPERM,
            'NAMESPACE_ROOT_PROTECTION_NOT_RETAINED')
    unit_name = '/system.slice/'+unit_cgroup.name
    require(child['cgroup'] == unit_name+'/domain'
            and bootstrap['cgroup'] == unit_name+'/supervisor'
            and outer['bootstrap_cgroup'] == '/supervisor', 'PRIVATE_DOMAIN_MEMBERSHIP')
    expected = {'memory.max': '536870912', 'memory.high': 'max', 'memory.swap.max': '0',
                'pids.max': '64', 'cpu.max': '100000 100000'}
    actual = {k:(domain/k).read_text().strip() for k in LIMITS}
    require(actual == expected, 'PRIVATE_DOMAIN_LIMIT_MISMATCH')
    require((unit_cgroup/'cgroup.procs').read_text().strip() == '', 'DELEGATION_ROOT_NOT_EMPTY')
    return {'path': str(domain), 'identity': [ds.st_dev, ds.st_ino], 'limits': actual,
            'supervisor_identity': [ss.st_dev, ss.st_ino], 'root_pressure_write_errno': errno.EPERM}

def verify_manifest(m):
    require(m.get('schema') == 1 and m.get('target_sha256') ==
            'c6d49d95c16d1ce6d94293313ae9f6f683a079ebd4cc821338a701dfe5b2cf6f', 'MANIFEST_TARGET')
    require(m.get('execution_authorized') is False, 'MANIFEST_NOT_REVIEW_FORM')
    require(m.get('phases') == ['probe', 'protocol', 'pressure'], 'MANIFEST_PHASES')
    require(m.get('memory_domain_layout') == 'delegated-child-fixed-mount-v2', 'MANIFEST_MEMORY_DOMAIN')
    require(m.get('pid_reuse_qualified') is False and m.get('production_cgroup_kill_qualified') is False,
            'QUALIFICATION_SCOPE')
    require(m.get('runner_sha256') == sha(read_regular(__file__)), 'RUNNER_CHANGED_SINCE_REVIEW')
    destinations = set()
    for f in m['files']:
        require(set(f) == {'source', 'dest', 'sha256', 'mode'}, 'MANIFEST_FILE_SCHEMA')
        source = Path(f['source'])
        require(source.is_absolute() and source.is_relative_to(CROOT), 'INPUT_OUTSIDE_CANDIDATE')
        require(source.resolve() == source, 'INPUT_SYMLINK_PATH')
        dest = Path(f['dest'])
        require(not dest.is_absolute() and '..' not in dest.parts and str(dest) not in destinations,
                'DESTINATION_PATH')
        destinations.add(str(dest))
        require(f['mode'] in (0o444, 0o555), 'INPUT_MODE')
        require(sha(read_regular(source)) == f['sha256'], 'INPUT_CHANGED: ' + str(source))
    require({'system/bin/lmkd', 'system/bin/linker64', 'fixture-init'} |
            {'system/lib64/'+name for name in DSOS} == destinations,
            'REQUIRED_ARTIFACT_MISSING')
    entries = {f['dest']: f for f in m['files']}
    require(entries['system/bin/lmkd']['sha256'] == m['target_sha256'], 'TARGET_FILE_BINDING')
    require(entries['system/bin/linker64']['sha256'] ==
            'b49ddfc69f7ad2558fef7145524c353391d42bce8004ff5f09e022066c9a1173', 'LINKER_FILE_BINDING')
    return m

def freeze(args):
    require(os.geteuid() == 0, 'ROOT_READ_REQUIRED')
    pin = main_pin(args.host_pid, args.init_pid)
    health_path = Path(str(args.output)+'.health.json')
    current = sample_health(pin, health_path)
    os.chown(health_path, 1000, 1000)
    result = {'schema': 1, 'kind': 'post-release-main-fence', 'pin': pin, 'health': current,
              'health_evidence':str(health_path),
              'observed_unix_ns': time.time_ns(), 'approved_for_execution': False}
    save(Path(args.output), result)
    os.chown(args.output, 1000, 1000)
    print(json.dumps({'path': args.output, 'sha256': sha(Path(args.output).read_bytes()), 'pin': pin}))

def run(args):
    require(os.geteuid() == 0, 'ROOT_PRIVATE_UNIT_REQUIRED')
    require(args.execute_approved, 'EXPLICIT_REVIEWED_EXECUTION_REQUIRED')
    require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,22}', args.run_id), 'RUN_ID')
    os.umask(0o022)  # Only this preparation process; fixed metadata in the private tree.
    m = verify_manifest(load_pinned(args.manifest, args.manifest_sha256))
    fence = load_pinned(args.main_fence, args.main_fence_sha256)
    require(fence.get('kind') == 'post-release-main-fence' and fence.get('schema') == 1, 'FRESH_FENCE_REQUIRED')
    pin = fence['pin']
    require(main_pin(pin['host']['pid'], pin['init']['pid']) == pin, 'MAIN_FENCE_CHANGED')
    base = CROOT/'fixture-runs'
    base.mkdir(mode=0o755, exist_ok=True)
    out = base/args.run_id
    out.mkdir(mode=0o700)  # Atomic durable claim. Existing run is never replayed.
    unit = UNIT_PREFIX+args.run_id+'.service'
    stage = Path('/run')/(UNIT_PREFIX+args.run_id)
    payload = Path('/opt')/(UNIT_PREFIX+args.run_id)
    root = payload/'root'
    evidence = stage/'evidence'
    nonce = os.urandom(32).hex()
    result = {'ok': False, 'phase': args.phase, 'unit': unit, 'manifest_sha256': args.manifest_sha256,
              'main_fence_sha256': args.main_fence_sha256, 'begun_unix_ns': time.time_ns(),
              'main_before': pin, 'health_before': None, 'cleanup': {}}
    invocation = None
    unit_cgroup = None
    started = False
    try:
        before_health = sample_health(pin, out/'health-admission.json')
        result['health_before'] = before_health
        result['parent_directory_policy'] = {'payload':directory_policy('/opt', True),
                                            'state':directory_policy('/run', False)}
        require(unit_properties(unit)['LoadState'] == 'not-found', 'PRIVATE_UNIT_ALREADY_EXISTS')
        stage.mkdir(mode=0o700)
        evidence.mkdir(mode=0o700)
        (stage/'socket').mkdir(mode=0o755)
        payload.mkdir(mode=0o700)
        root.mkdir(mode=0o755)
        for path in ('system/bin', 'system/lib64', 'proc', 'sys/fs/cgroup', 'dev/socket', 'evidence'):
            (root/path).mkdir(mode=0o700 if path == 'evidence' else 0o755, parents=True, exist_ok=True)
        for f in m['files']:
            dest = root/f['dest']
            dest.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            data = read_regular(f['source'])
            require(sha(data) == f['sha256'], 'COPY_INPUT_CHANGED')
            fd = os.open(dest, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, f['mode'])
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            os.chmod(dest, f['mode'])
            require(sha(read_regular(dest)) == f['sha256'], 'STAGED_COPY_CHANGED')
        os.mknod(root/'dev/null', stat.S_IFCHR|0o666, os.makedev(1, 3))
        os.chmod(root/'dev/null', 0o666)
        save(out/'intent.json', {'unit': unit, 'stage': str(stage), 'payload':str(payload), 'phase': args.phase,
                               'manifest_sha256': args.manifest_sha256,
                               'main_fence_sha256': args.main_fence_sha256, 'automatic_retry': False})
        properties = ['Delegate=memory pids cpu',
                      'MemoryMax=512M', 'MemoryHigh=infinity', 'MemorySwapMax=0', 'CPUQuota=100%',
                      'CPUQuotaPeriodSec=100ms', 'TasksMax=64', 'RuntimeMaxSec=90', 'TimeoutStopSec=3',
                      'KillMode=control-group', 'UMask=0022', 'Nice=10', 'LimitCORE=0',
                      'LimitNOFILE=4096', 'LimitFSIZE=1048576', 'RestrictRealtime=yes',
                      'RemainAfterExit=yes', 'Type=exec', 'StandardInput=null',
                      'StandardOutput=append:'+str(stage/'unit.stdout'),
                      'StandardError=append:'+str(stage/'unit.stderr')]
        argv = ['/usr/bin/systemd-run', '--unit='+unit, '--no-block', '--quiet']
        argv += ['--property='+p for p in properties]
        argv += [str(root/'fixture-init'), str(root), str(stage), args.phase, unit, nonce]
        argv += [str(pin['init']['ns'][name]) for name in NS]
        save(out/'dispatch.json', {'executable': argv[0], 'args_without_private_token':
                                [x if x != nonce else '<private-token>' for x in argv[1:]],
                                'at_unix_ns': time.time_ns()})
        started = True
        command(argv)
        deadline = time.monotonic()+18
        permitted = False
        while time.monotonic() < deadline:
            props = unit_properties(unit)
            if props.get('InvocationID'):
                require(invocation in (None, props['InvocationID']), 'PRIVATE_INVOCATION_CHANGED')
                invocation = props['InvocationID']
            require(props.get('ActiveState') in ('activating', 'active'), 'PRIVATE_UNIT_STOPPED_BEFORE_PREFLIGHT')
            preflight = evidence/'outer-preflight.json'
            if preflight.exists():
                outer = json.loads(read_regular(preflight, 8192))
                inner = json.loads(read_regular(evidence/'inner-preflight.json', 8192))
                es = evidence.stat()
                require([es.st_dev, es.st_ino] == [inner['evidence_dev'], inner['evidence_ino']]
                        and es.st_uid == 0 and stat.S_IMODE(es.st_mode) == 0o700
                        and inner['state_noexec'] is True, 'PRIVATE_STATE_INODE_OR_POLICY_MISMATCH')
                ss = (stage/'socket').stat()
                require([ss.st_dev, ss.st_ino] == [inner['socket_dev'], inner['socket_ino']]
                        and ss.st_uid == 0 and stat.S_IMODE(ss.st_mode) == 0o755,
                        'PRIVATE_SOCKET_STATE_INODE_MISMATCH')
                require(props['ControlGroup'] == '/system.slice/'+unit, 'PRIVATE_CGROUP_NAME')
                unit_cgroup = Path('/sys/fs/cgroup')/props['ControlGroup'].lstrip('/')
                st = unit_cgroup.stat()
                require([st.st_dev, st.st_ino] == [outer['cgroup_dev'], outer['cgroup_ino']]
                        == [inner['namespace_root_dev'], inner['namespace_root_ino']],
                        'NAMESPACE_ROOT_INODE_DISAGREEMENT')
                child = process_info(outer['child_host_pid'])
                require(child['start_ticks'] == outer['child_start'] and child['nspid'][-1] == 1
                        and child['cgroup'] == props['ControlGroup']+'/domain' and child['ns'] == inner['ns'],
                        'PRIVATE_PID1_OUTER_MISMATCH')
                require(outer['bootstrap_host_pid'] == int(props['MainPID']) and child['ppid'] == int(props['MainPID']),
                        'PRIVATE_PARENT_MISMATCH')
                domain = verify_domain_attestation(unit_cgroup, outer, inner, child,
                                                   process_info(outer['bootstrap_host_pid']))
                require(all(child['ns'][n] != pin['init']['ns'][n]
                            and child['ns'][n] != Path('/proc/1/ns', n).stat().st_ino for n in NS),
                        'NAMESPACE_NOT_PRIVATE')
                require(inner['closed_inherited_fds'] is True and inner['only_owned_gate_fds'] == [3, 4]
                        and inner['lmkd_started'] is False and outer['lmkd_started'] is False,
                        'PRESTART_CONFINEMENT_MISSING')
                fdroot = Path('/proc')/str(child['pid'])/'fd'
                fds = {int(p.name): os.readlink(p) for p in fdroot.iterdir()}
                require(set(fds) == {0, 1, 2, 3} and fds[0] == '/dev/null'
                        and fds[1] == str(stage/'unit.stdout') and fds[2] == str(stage/'unit.stderr')
                        and re.fullmatch(r'pipe:\[\d+\]', fds[3]), 'PRIVATE_FD_INVENTORY')
                expected = {'memory.max': '536870912', 'memory.high': 'max', 'memory.swap.max': '0',
                            'pids.max': '64', 'cpu.max': '100000 100000'}
                require({k:(unit_cgroup/k).read_text().strip() for k in LIMITS} == expected,
                        'PRIVATE_LIMIT_MISMATCH')
                require(main_pin(pin['host']['pid'], pin['init']['pid'], False) == pin,
                        'MAIN_CHANGED_BEFORE_PRIVATE_RELEASE')
                sample_health(pin, out/'health-before-release.json', before_health, unit_cgroup)
                save(out/'preflight-verified.json', {'outer': outer, 'inner': inner, 'unit': props,
                                                   'memory_domain': domain,
                                                   'actual_private_fds':fds, 'at_unix_ns': time.time_ns()})
                fd = os.open(evidence/'permit', os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    stream.write(nonce)
                    stream.flush()
                    os.fsync(stream.fileno())
                permitted = True
                break
            time.sleep(.1)
        require(permitted, 'PREFLIGHT_TIMEOUT_NO_LMKD_RELEASE')
        deadline = time.monotonic()+68
        index = 0
        while time.monotonic() < deadline:
            props = unit_properties(unit)
            require(props.get('InvocationID') == invocation, 'PRIVATE_INVOCATION_CHANGED')
            if props.get('SubState') == 'exited' or props.get('ActiveState') in ('inactive', 'failed'):
                break
            require(main_pin(pin['host']['pid'], pin['init']['pid'], False) == pin, 'MAIN_CHANGED_DURING_FIXTURE')
            sample_health(pin, out/f'health-{index:03d}.json', before_health, unit_cgroup)
            index += 1
            require(unit_cgroup is not None, 'PRIVATE_CGROUP_UNKNOWN')
            ev = values(unit_cgroup/'memory.events')
            require(all(ev.get(k) == 0 for k in ('max', 'oom', 'oom_kill', 'oom_group_kill')), 'PRIVATE_KERNEL_OOM_OR_MAX')
            require(values(unit_cgroup/'pids.events')['max'] == 0, 'PRIVATE_PID_CAP')
            time.sleep(.5)
        else:
            raise Stop('PRIVATE_PHASE_DEADLINE')
        result['unit_end'] = props
        require(props.get('ExecMainStatus') == '0' and props.get('Result') == 'success', 'PRIVATE_PHASE_FAILED')
        phase_result = json.loads(read_regular(evidence/'phase-result.json', 16384))
        require(phase_result.get('ok') is True and phase_result.get('phase') == args.phase, 'PRIVATE_RESULT_NOT_VERIFIED')
        result['phase_result'] = phase_result
        result['main_after'] = main_pin(pin['host']['pid'], pin['init']['pid'])
        require(result['main_after'] == pin, 'MAIN_FINAL_FENCE_CHANGED')
        result['health_after'] = sample_health(pin, out/'health-final.json', before_health)
        result['ok'] = True
    except BaseException as exc:
        result['error'] = str(exc)
        if isinstance(exc, Stop):
            result['guard_observation'] = exc.observation
            result['guard_evidence'] = exc.evidence
    finally:
        if started:
            try:
                props = unit_properties(unit)
                if props.get('LoadState') != 'not-found':
                    require(props.get('ControlGroup') in ('', '/system.slice/'+unit), 'CLEANUP_CGROUP_MISMATCH')
                    require(invocation is None or props.get('InvocationID') == invocation, 'CLEANUP_INVOCATION_MISMATCH')
                    if invocation is None:
                        bootstrap = process_info(int(props['MainPID']))
                        proc = Path('/proc')/str(bootstrap['pid'])
                        actual = (proc/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
                        expected = [str(root/'fixture-init'), str(root), str(stage), args.phase, unit, nonce]
                        expected += [str(pin['init']['ns'][n]) for n in NS]
                        require(actual == [x.encode() for x in expected]
                                and os.readlink(proc/'exe') == str(root/'fixture-init')
                                and bootstrap['cgroup'] in ('/system.slice/'+unit,
                                                            '/system.slice/'+unit+'/supervisor'),
                                'CLEANUP_UNCLAIMED_INVOCATION_REQUIRES_RECONCILIATION')
                        require(re.fullmatch(r'[a-f0-9]{32}', props['InvocationID']) is not None,
                                'CLEANUP_INVOCATION_UNKNOWN')
                        invocation = props['InvocationID']
                        require(unit_properties(unit)['InvocationID'] == invocation
                                and process_info(bootstrap['pid'])['start_ticks'] == bootstrap['start_ticks'],
                                'CLEANUP_IDENTITY_CHANGED')
                    if unit_cgroup is not None and unit_cgroup.exists():
                        cs = unit_cgroup.stat()
                        require([cs.st_dev, cs.st_ino] == [outer['cgroup_dev'], outer['cgroup_ino']],
                                'CLEANUP_CGROUP_INODE_CHANGED')
                    result['cleanup']['unit_before_stop'] = props
                    command(['/usr/bin/systemctl', 'stop', unit], timeout=12)
                cg = Path('/sys/fs/cgroup/system.slice')/unit
                require(not cg.exists() or int((cg/'pids.current').read_text()) == 0, 'PRIVATE_TASKS_REMAIN')
                result['cleanup']['owned_unit_empty'] = True
            except BaseException as exc:
                result['cleanup']['error'] = str(exc)
                result['ok'] = False
        try:
            result['main_final'] = main_pin(pin['host']['pid'], pin['init']['pid'])
            require(result['main_final'] == pin, 'MAIN_FINAL_FENCE_CHANGED')
            result['main_preserved'] = True
        except BaseException as exc:
            result['main_preserved'] = False
            result['main_final_error'] = str(exc)
            result['ok'] = False
        try:
            if evidence.exists():
                shutil.copytree(evidence, out/'evidence', symlinks=False)
            for name in ('unit.stdout', 'unit.stderr'):
                if (stage/name).exists():
                    shutil.copyfile(stage/name, out/name)
        except BaseException as exc:
            result['evidence_copy_error'] = str(exc)
            result['ok'] = False
        result['ended_unix_ns'] = time.time_ns()
        result['stage_retained_for_review'] = str(stage)
        result['payload_retained_for_review'] = str(payload)
        save(out/'result.json', result)
        for p in out.rglob('*'):
            if not p.is_symlink():
                os.chown(p, 1000, 1000)
        os.chown(out, 1000, 1000)
    print(json.dumps({'ok':result['ok'], 'result_path':str(out/'result.json'),
                      'result_sha256':sha((out/'result.json').read_bytes()), 'error':result.get('error'),
                      'guard_observation':result.get('guard_observation'),
                      'guard_evidence':result.get('guard_evidence'),
                      'cleanup':result['cleanup']}))
    return 0 if result['ok'] else 1

def cli():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    f = sub.add_parser('snapshot-main')
    f.add_argument('--host-pid', type=int, required=True)
    f.add_argument('--init-pid', type=int, required=True)
    f.add_argument('--output', required=True)
    r = sub.add_parser('run')
    r.add_argument('--phase', choices=('probe', 'protocol', 'pressure'), required=True)
    r.add_argument('--run-id', required=True)
    r.add_argument('--manifest', required=True)
    r.add_argument('--manifest-sha256', required=True)
    r.add_argument('--main-fence', required=True)
    r.add_argument('--main-fence-sha256', required=True)
    r.add_argument('--execute-approved', action='store_true')
    a = p.parse_args()
    return freeze(a) if a.action == 'snapshot-main' else run(a)

if __name__ == '__main__':
    try:
        raise SystemExit(cli())
    except (Stop, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok':False, 'error':str(exc),
                          'guard_observation':getattr(exc, 'observation', None),
                          'guard_evidence':getattr(exc, 'evidence', None)}))
        raise SystemExit(1)
