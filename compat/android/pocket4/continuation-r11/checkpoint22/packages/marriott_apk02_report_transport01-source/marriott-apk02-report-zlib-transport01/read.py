"""Fixed one-report lossless zlib transport. No report parsing or child execution."""
import hashlib
import json
import os
import signal
import stat
import sys
import time
import zlib

ROOT = '/home/alex/work/p4-marriott-apk02-report-transport01-20261106'
PARENT = '/home/alex/work'
INPUTS = (
    ('marriott_apk02', '/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-02-20261106/build-result.json',
     2778880, '4ac6808bb258b7595f1eafa1e1f76716288d47e7c0796d60d4ec748bc2f16cae',
     0o400, 'marriott-apk02-build-result.json.zlib'),
)
STARTED = time.monotonic()
WORK_END = STARTED + 40.0
CONTROL_END = STARTED + 45.0
ACTIVE_END = WORK_END
MEMORY_MAX = 268435456
OUTPUT_MAX = 131072
LEDGER = []
DIRECTORIES = []
ERRORS = []
REPORT = {
    'schema': 1, 'kind': 'p4-fixed-marriott-apk02-report-zlib-transport01',
    'collection_complete': False, 'report_contents_parsed': False,
    'runtime_or_compile_qualification_asserted': False,
    'source_files_modified': False, 'Main_actions': 0, 'Android_actions': 0,
    'children_started': 0, 'network_calls': 0, 'directory_enumerations': 0,
    'control_seconds': 45, 'work_seconds': 40, 'outer_terminal_required': True,
    'global_process_FD_equality_asserted': False, 'process_import_FDs_claimed_owned': False,
    'records': [], 'resource_health': {}, 'cleanup': [], 'parent_identity_checks': [],
    'zlib_compile_version': zlib.ZLIB_VERSION, 'zlib_runtime_version': zlib.ZLIB_RUNTIME_VERSION,
}

class DeadlineExpired(BaseException):
    pass

def alarm_handler(signum, frame):
    raise DeadlineExpired('fixed transport control deadline')

def need(condition, message):
    if not condition:
        raise RuntimeError(message)

def tick():
    need(time.monotonic() < ACTIVE_END, 'fixed transport phase deadline')

def failure(stage, error):
    ERRORS.append({'stage': stage, 'type': type(error).__name__,
                   'message': str(error)[:2048], 'errno': getattr(error, 'errno', None)})

def digest(data):
    return hashlib.sha256(data).hexdigest()

def meta(fd):
    value = os.fstat(fd)
    return {'device': value.st_dev, 'inode': value.st_ino, 'mode': value.st_mode,
            'uid': value.st_uid, 'gid': value.st_gid, 'nlink': value.st_nlink,
            'bytes': value.st_size, 'mtime_ns': value.st_mtime_ns,
            'ctime_ns': value.st_ctime_ns}

def identity(value):
    return tuple(value[k] for k in ('device', 'inode', 'mode', 'uid', 'gid'))

def take(fd, label):
    event = {'fd': fd, 'label': label, 'close_attempted': False, 'closed': False}
    LEDGER.append(event)
    return event

def close_event(event):
    if event['close_attempted']:
        return
    event['close_attempted'] = True
    try:
        os.close(event['fd'])
        event['closed'] = True
    except BaseException as error:
        failure('close:'+event['label'], error)

def open_directory(path, record=True):
    tick()
    need(path.startswith('/') and len(path[1:].split('/')) <= 64 and
         all(p not in ('', '.', '..') for p in path[1:].split('/')),
         'noncanonical or excessive fixed directory depth')
    current = take(os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC),
                   'directory:/')
    current_path = ''
    for part in path[1:].split('/'):
        tick()
        current_path += '/' + part
        current = take(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                               dir_fd=current['fd']), 'directory:'+current_path)
        row = meta(current['fd'])
        need(stat.S_ISDIR(row['mode']), 'fixed parent is not directory')
        if record:
            DIRECTORIES.append({'path': current_path, 'event': current, 'before': row})
    return current

def open_file(path, flags=os.O_RDONLY, record_parents=True):
    parent, name = path.rsplit('/', 1)
    need(name not in ('', '.', '..') and '/' not in name, 'invalid fixed file basename')
    directory = open_directory(parent, record_parents)
    event = take(os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory['fd']),
                 'file:'+path)
    return event

def regular(row, count, mode):
    need(stat.S_ISREG(row['mode']) and stat.S_IMODE(row['mode']) == mode and
         row['uid'] == row['gid'] == 1000 and row['nlink'] == 1 and row['bytes'] == count,
         'fixed regular file tuple differs')

def full_read(event, maximum):
    tick()
    os.lseek(event['fd'], 0, os.SEEK_SET)
    data = bytearray()
    while True:
        tick()
        part = os.read(event['fd'], min(65536, maximum + 1 - len(data)))
        if not part:
            break
        data.extend(part)
        need(len(data) <= maximum, 'bounded complete read overflow')
    return bytes(data)

def self_read(path, maximum):
    # /proc/self is the kernel self reference; never enumerated and never another PID.
    tick()
    event = take(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), 'self:'+path)
    try:
        need(stat.S_ISREG(os.fstat(event['fd']).st_mode), 'self metadata file shape')
        data = bytearray()
        while True:
            tick()
            part = os.read(event['fd'], min(4096, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
            need(len(data) <= maximum, 'self metadata read overflow')
        return bytes(data).decode('ascii')
    finally:
        close_event(event)

def at_text(directory, name):
    tick()
    need('/' not in name and name not in ('', '.', '..'), 'invalid resource leaf')
    event = take(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=directory['fd']), 'own-cgroup:'+name)
    try:
        need(stat.S_ISREG(os.fstat(event['fd']).st_mode), 'resource pseudo-file shape')
        data = bytearray()
        while True:
            tick()
            part = os.read(event['fd'], min(4096, 32769-len(data)))
            if not part:
                break
            data.extend(part)
            need(len(data) <= 32768, 'resource pseudo-file bound')
        return bytes(data).decode('ascii').strip()
    finally:
        close_event(event)

def uint(value):
    need(value.isascii() and value.isdecimal(), 'invalid unsigned resource value')
    number = int(value)
    need(number <= (1 << 64)-1, 'resource value overflow')
    return number

def limit(value):
    return 'max' if value == 'max' else uint(value)

def counters(value):
    result = {}
    for line in value.splitlines():
        fields = line.split()
        need(len(fields) == 2 and fields[0] not in result and
             all(c in 'abcdefghijklmnopqrstuvwxyz_' for c in fields[0]),
             'invalid resource counters')
        result[fields[0]] = uint(fields[1])
    need(bool(result), 'empty resource counters')
    return result

def membership():
    value = self_read('/proc/self/cgroup', 4096)
    need(value.startswith('0::/') and value.endswith('\n') and value.count('\n') == 1,
         'own unified membership shape')
    relative = value[4:-1]
    need(relative and all(p not in ('', '.', '..') for p in relative.split('/')),
         'root/noncanonical own resource domain')
    return value, '/sys/fs/cgroup/'+relative

def mount_identity():
    matches = []
    for line in self_read('/proc/self/mountinfo', 262144).splitlines():
        fields = line.split()
        if len(fields) < 10 or fields[4] != '/sys/fs/cgroup':
            continue
        separator = fields.index('-')
        need(separator >= 6 and len(fields) >= separator+4 and
             fields[3] == '/' and fields[separator+1] == 'cgroup2',
             'fixed cgroup mount differs')
        matches.append({'id': fields[0], 'parent': fields[1], 'device': fields[2],
                        'root': fields[3], 'mountpoint': fields[4],
                        'filesystem': fields[separator+1], 'source': fields[separator+2]})
    need(len(matches) == 1, 'unique own cgroup2 mount absent')
    return matches[0]

def namespaces():
    result = {}
    for name in ('mnt', 'cgroup'):
        value = os.stat('/proc/self/ns/'+name)
        result[name] = [value.st_dev, value.st_ino]
    return result

def resource_sample(domain, membership_value, cg_mount, ns, identity_before):
    tick()
    need(membership() == membership_value and mount_identity() == cg_mount and namespaces() == ns,
         'own cgroup or namespace changed')
    row = meta(domain['fd'])
    need(identity(row) == identity(identity_before), 'held own domain changed')
    need(cg_mount['device'] == str(os.major(row['device']))+':'+str(os.minor(row['device'])),
         'held cgroup device not the qualified cgroup2 mount')
    named = open_directory(membership_value[1], False)
    need(identity(meta(named['fd'])) == identity(row), 'named own cgroup changed')
    values = {name: limit(at_text(domain, name)) for name in
              ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max')}
    cpu = at_text(domain, 'cpu.max').split()
    need(len(cpu) == 2, 'CPU limit shape')
    values['cpu.max'] = [limit(cpu[0]), uint(cpu[1])]
    need(values['memory.max'] == MEMORY_MAX and isinstance(values['cpu.max'][0], int) and
         values['cpu.max'][0] == values['cpu.max'][1] and values['cpu.max'][1] > 0,
         'actual own resource limits differ from request')
    processes = [uint(v) for v in at_text(domain, 'cgroup.procs').splitlines()]
    need(os.getpid() in processes and len(processes) == len(set(processes)), 'own PID domain membership')
    children = self_read('/proc/self/task/'+str(os.getpid())+'/children', 4096).strip()
    need(children == '', 'childless controller acquired children')
    current = uint(at_text(domain, 'memory.current'))
    peak = uint(at_text(domain, 'memory.peak'))
    swap = uint(at_text(domain, 'memory.swap.current'))
    events = counters(at_text(domain, 'memory.events'))
    need(all(k in events for k in ('max', 'oom', 'oom_kill')) and
         all(events.get(k, 0) == 0 for k in ('max','oom','oom_kill','oom_group_kill')) and
         current <= MEMORY_MAX and peak <= MEMORY_MAX, 'own memory limit/OOM event')
    return {'domain': row, 'mount': cg_mount, 'membership': membership_value[0],
            'namespaces': ns, 'limits': values, 'memory_current': current,
            'memory_peak': peak, 'memory_swap_current': swap,
            'memory_events': events, 'direct_cgroup_procs': processes,
            'self_children_empty': True, 'sample_monotonic_ns': time.monotonic_ns()}

def verify_named(path, expected, maximum=None, expected_hash=None):
    event = open_file(path, record_parents=False)
    row = meta(event['fd'])
    need(row == expected, 'final named file identity differs: '+path)
    if maximum is not None:
        data = full_read(event, maximum)
        need(len(data) == expected['bytes'] and digest(data) == expected_hash,
             'final named output bytes differ')
        need(meta(event['fd']) == row, 'final named output changed during read')
    return row

def main():
    global ACTIVE_END
    root_event = None
    parent_event = None
    root_initial = None
    created = False
    own_outputs = []
    inputs = []
    domain = None
    resources_ready = False
    previous_umask = None
    old_handler = signal.signal(signal.SIGALRM, alarm_handler)
    old_timer = signal.setitimer(signal.ITIMER_REAL, 45.0)
    try:
        need(old_timer == (0.0, 0.0), 'unexpected inherited interval timer')
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000,
             'ordinary UID/GID1000 required')
        membership_value = membership()
        cg_mount = mount_identity()
        ns = namespaces()
        domain = open_directory(membership_value[1], False)
        domain_identity = meta(domain['fd'])
        REPORT['resource_health']['before'] = resource_sample(
            domain, membership_value, cg_mount, ns, domain_identity)
        resources_ready = True
        for role, path, count, sha, mode, output_name in INPUTS:
            tick()
            event = open_file(path)
            before = meta(event['fd'])
            item = {'role': role, 'input_path': path, 'input_before': before,
                    'input_bytes': count, 'input_sha256': sha, 'full_reads': 0,
                    'compression': 'zlib', 'compression_level': 6, 'output_name': output_name,
                    'output_complete': False}
            REPORT['records'].append(item)
            regular(before, count, mode)
            body = full_read(event, count)
            item['input_observed_sha256'] = digest(body)
            need(len(body) == count and item['input_observed_sha256'] == sha and meta(event['fd']) == before,
                 'fixed input whole bytes/SHA or held identity differ: '+role)
            item['full_reads'] = 1
            inputs.append((event, body, item, mode))
        need(not ERRORS, 'prior input/resource FD failure forbids output creation')
        parent_event = open_directory(PARENT)
        previous_umask = os.umask(0o077)
        os.mkdir(ROOT.rsplit('/', 1)[1], 0o700, dir_fd=parent_event['fd'])
        created = True
        root_event = take(os.open(ROOT.rsplit('/', 1)[1],
                          os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                          dir_fd=parent_event['fd']), 'created-directory:'+ROOT)
        root_initial = meta(root_event['fd'])
        need(stat.S_ISDIR(root_initial['mode']) and stat.S_IMODE(root_initial['mode']) == 0o700 and
             root_initial['uid'] == root_initial['gid'] == 1000, 'new owned directory differs')
        os.fsync(parent_event['fd'])
        for event, body, item, mode in inputs:
            tick()
            need(not ERRORS, 'prior failure forbids another compressed output')
            compressed = zlib.compress(body, level=6)
            tick()
            # zlib overhead is small, but use an explicit conservative 64KiB allowance.
            need(0 < len(compressed) <= min(1048576, len(body)+65536), 'compressed output bound')
            repeated = full_read(event, len(body))
            need(repeated == body and digest(repeated) == item['input_sha256'] and
                 meta(event['fd']) == item['input_before'], 'input changed across compression')
            item['full_reads'] = 2
            out = take(os.open(item['output_name'], os.O_RDWR | os.O_CREAT | os.O_EXCL |
                               os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=root_event['fd']),
                       'created-file:'+ROOT+'/'+item['output_name'])
            own = {'event': out, 'name': item['output_name'], 'origin': None,
                   'completed': False, 'removed': False}
            own_outputs.append(own)
            origin = meta(out['fd'])
            own['origin'] = origin
            regular(origin, 0, 0o400)
            offset = 0
            while offset < len(compressed):
                tick()
                written = os.write(out['fd'], compressed[offset:offset+65536])
                need(written > 0, 'zero-length owned output write')
                offset += written
            os.fsync(out['fd'])
            row = meta(out['fd'])
            regular(row, len(compressed), 0o400)
            need(identity(row) == identity(origin), 'created output inode changed')
            copy = full_read(out, len(compressed))
            need(copy == compressed and meta(out['fd']) == row, 'held compressed output changed')
            os.fsync(root_event['fd'])
            item.update(output_path=ROOT+'/'+item['output_name'], output_metadata=row,
                        output_bytes=len(compressed), output_sha256=digest(compressed),
                        output_complete=True, input_after=meta(event['fd']))
            own['completed'] = True
        for event, body, item, mode in inputs:
            need(meta(event['fd']) == item['input_before'], 'final held source changed')
            item['input_named_after'] = verify_named(item['input_path'], item['input_before'])
            item['output_named_after'] = verify_named(item['output_path'], item['output_metadata'],
                                                       item['output_bytes'], item['output_sha256'])
        need(identity(meta(root_event['fd'])) == identity(root_initial), 'held created directory changed')
        final_root = open_directory(ROOT, False)
        need(identity(meta(final_root['fd'])) == identity(root_initial), 'named created directory changed')
        for item in DIRECTORIES:
            held_after = meta(item['event']['fd'])
            named = open_directory(item['path'], False)
            named_after = meta(named['fd'])
            REPORT['parent_identity_checks'].append({'path': item['path'], 'before': item['before'],
                'held_after': held_after, 'named_after': named_after})
            need(identity(held_after) == identity(item['before']) == identity(named_after),
                 'parent directory identity changed: '+item['path'])
        REPORT['parent_identity_scope'] = 'full component NOFOLLOW opens; held/named device,inode,mode,uid,gid equality; directory nlink/timestamps are not immutable because the own new child changes its parent'
        REPORT['owned_directory'] = {'path': ROOT, 'before': root_initial, 'after': meta(root_event['fd']),
                                     'parent_after': meta(parent_event['fd'])}
        tick()
    except BaseException as error:
        failure('transport', error)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        ACTIVE_END = CONTROL_END
        if ERRORS and root_event is not None:
            for own in own_outputs:
                if own['completed']:
                    continue
                try:
                    tick()
                    current = os.stat(own['name'], dir_fd=root_event['fd'], follow_symlinks=False)
                    held = meta(own['event']['fd'])
                    need((current.st_dev, current.st_ino) == (held['device'], held['inode']) and
                         stat.S_ISREG(held['mode']) and held['uid'] == held['gid'] == 1000 and
                         held['nlink'] == 1 and (own['origin'] is None or
                         identity(held) == identity(own['origin'])), 'partial output is no longer own inode')
                    os.unlink(own['name'], dir_fd=root_event['fd'])
                    own['removed'] = True
                    os.fsync(root_event['fd'])
                    REPORT['cleanup'].append({'name': own['name'], 'partial_owned_file_removed': True})
                except BaseException as error:
                    failure('partial-output-cleanup', error)
        if resources_ready:
            try:
                after = resource_sample(domain, membership_value, cg_mount, ns, domain_identity)
                REPORT['resource_health']['after'] = after
                before = REPORT['resource_health']['before']
                need(before['limits'] == after['limits'] and after['memory_peak'] >= before['memory_peak'] and
                     before['memory_events'].keys() == after['memory_events'].keys() and
                     all(after['memory_events'][k] >= before['memory_events'][k] for k in before['memory_events']),
                     'own resource interval differs')
                REPORT['resource_health']['held_own_cgroup_gate_passed'] = True
            except BaseException as error:
                failure('resource-final', error)
        for event in reversed(LEDGER):
            close_event(event)
        if previous_umask is not None:
            os.umask(previous_umask)
        signal.signal(signal.SIGALRM, old_handler)
    REPORT['owned_directory_created'] = created
    REPORT['completed_output_paths_retained'] = [ROOT+'/'+x['name'] for x in own_outputs if x['completed']]
    REPORT['fd_events'] = LEDGER
    REPORT['all_tracked_owned_FDs_closed'] = all(x['closed'] for x in LEDGER)
    REPORT['control_deadline_met'] = time.monotonic() <= CONTROL_END
    REPORT['errors'] = ERRORS
    REPORT['first_error'] = ERRORS[0] if ERRORS else None
    REPORT['elapsed_seconds'] = time.monotonic()-STARTED
    REPORT['collection_complete'] = bool(not ERRORS and REPORT['all_tracked_owned_FDs_closed'] and
        REPORT['control_deadline_met'] and REPORT['resource_health'].get('held_own_cgroup_gate_passed') and
        len(REPORT['records']) == 1 and all(x['output_complete'] for x in REPORT['records']))
    encoded = (json.dumps(REPORT, sort_keys=True, separators=(',',':'))+'\n').encode()
    if len(encoded) > OUTPUT_MAX:
        print(json.dumps({'kind': REPORT['kind'], 'collection_complete': False,
                          'error': 'transport metadata stdout bound exceeded',
                          'full_metadata_bytes': len(encoded), 'full_metadata_sha256': digest(encoded)}))
        return 1
    sys.stdout.buffer.write(encoded)
    return 0 if REPORT['collection_complete'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
