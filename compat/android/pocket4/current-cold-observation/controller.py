"""One finite component-only MAC VM qualification, with exact native owned retirement."""
import datetime, errno, fcntl, hashlib, json, os, re, select, signal, stat, sys, time, traceback
from pathlib import Path

D = Path('/home/alex/work/p4-systemd-cold-vm-20261114-e6ac-r8')
UNIT = 'p4-systemd-cold-vm-20261114-e6ac-r8.service'
DESCRIPTION = 'Pocket4 original systemd cold component 20261114 e6ac r8'
CG = Path('/sys/fs/cgroup/system.slice') / UNIT
UUID = '14112026-0058-4000-a001-e6ac9e05361c'
CONTROL = Path('/home/alex/work/p4ctx3-initramfs-control-01a1ca08-r4')
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
SUPPORT_EXPECTED = {
    'transform_support.py': (10301, '4f9d586c2db5589be95b8c154ac4ec86f838d31283664f9c184a7633850ee31e'),
    'owned_lifecycle.py': (14201, '94d18007becfbe14a7ca833d73389e45c39f76cb874de2f341a5d500edc4a4fd'),
    'owned_adoption.py': (2868, '5062e1f68d2815688286e3e691b81592bbda227477e224281462ee482107c080'),
}
INPUTS = {
    'kernel': ('/home/alex/work/p4-r13-natural-nnp-private-vm-20261113-r2/guest-inputs/vmlinuz', 17138176, 'a91670a793380d629aaf82edffcdff11799e52cf26ff43db70030afe04d64d12'),
    'initrd': ('/home/alex/work/p4-r13-natural-nnp-private-vm-20261113-r2/guest-inputs/initrd.img', 92339714, 'da16ffc3855d2c36a6ced126e89ae3ea0a26ce8cf37b0a9ca5735d313d7962de'),
    'kernel_config': ('/home/alex/work/p4ctx3-kernel-import-01a1ca08-r1/tree/lib/modules/7.0.14-p4ctx3/config-7.0.14-p4ctx3', 308714, '85658dc84bd493671a4c533b2bc33e6a66d7032616c13ed57ebd28eade863e58'),
}
CARRIER = Path('/home/alex/work/p4-systemd-cold-carrier-20261114-e6ac-r8')
OUTER_UNIT = 'p4-systemd-cold-outer-20261114-e6ac-r8.service'
OUTER_DESCRIPTION = 'Pocket4 original systemd cold native controller 20261114 e6ac r8'
AUTHENTICATED_CONTROLLER_BODY = None
AUTHENTICATED_BUNDLE = None
SERIAL_LIMIT = 40 * 1024**2
COMPONENT_LOG = D / 'qemu-tmp/guest-component.ndjson'
HELD = {}; SUPPORT = None; COMMANDS = None; REPORT = None
PIDFD = None; POLL = None; BOUND_PID = None; BOUND_START = None; INVOCATION = None
QEMU = None; QEMU_ENV = None; EXPECTED_GROUPS = None; UNIT_REQUESTED = False

def need(value, message):
    if not value:
        raise RuntimeError(message)

def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns]

def pin(path, expected=None, contents=False, copy_to=None, mode=0o444, system_links=False):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, 'canonical exact input required: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    dest = None
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= 5 * 1024**3, 'bounded regular input')
        need(before.st_nlink == 1 or (system_links and str(path).startswith('/usr/') and before.st_uid == 0), 'source must be single-link or existing installed public system object')
        if contents:
            need(before.st_size <= 64 * 1024**2, 'bounded memory contents')
        if copy_to is not None:
            dest = os.open(copy_to, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
            os.fchmod(dest, mode)
        h = hashlib.sha256(); parts = []; size = 0
        while block := os.read(fd, 1024**2):
            need(SUPPORT is None or not SUPPORT.CANCELLED, 'copy cancelled')
            size += len(block); h.update(block)
            if contents: parts.append(block)
            if dest is not None:
                view = memoryview(block)
                while view:
                    n = os.write(dest, view); need(n > 0, 'short private copy'); view = view[n:]
        need(size == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'held source changed: ' + str(path))
        ref = {'path': str(path), 'bytes': size, 'sha256': h.hexdigest(), 'identity': f9(before)}
        if expected is not None:
            need(ref['bytes'] == expected['bytes'] and ref['sha256'] == expected['sha256'], 'full size/SHA mismatch: ' + str(path))
            if 'identity' in expected: need(ref['identity'] == expected['identity'], 'source F9 mismatch: ' + str(path))
        if dest is not None: os.fsync(dest)
        return (ref, b''.join(parts)) if contents else ref
    finally:
        if dest is not None: os.close(dest)
        os.close(fd)

def sync_regular_log(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        need(stat.S_ISREG(os.fstat(fd).st_mode), 'regular log descriptor before fsync')
        os.fsync(fd)
    finally:
        os.close(fd)

def component_log(expected_initial=None, contents=False):
    value = pin(COMPONENT_LOG, contents=contents)
    ref = value[0] if contents else value
    node = ref['identity']
    need(node[3:6] == [1000, 1000, 1] and stat.S_IMODE(node[2]) == 0o600,
         'exact ordinary QEMU COM2 log owner, link count and mode')
    if expected_initial is not None:
        need(node[:6] == expected_initial['identity'][:6], 'same precreated COM2 log inode')
    need(ref['bytes'] <= SERIAL_LIMIT, 'bounded complete independent component channel')
    return value


def create(path, value, mode=0o400):
    raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    os.fchmod(fd, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return pin(path)

def held_support():
    for name, (ref, fd, body) in HELD.items():
        need(f9(os.fstat(fd)) == ref['identity'] == f9((CONTROL / name).lstat()), 'support F9 changed')
        need(os.pread(fd, len(body) + 1, 0) == body, 'support bytes changed')

def prepare_support():
    global SUPPORT, COMMANDS
    for name, (size, sha) in SUPPORT_EXPECTED.items():
        ref, raw = pin(CONTROL / name, {'bytes': size, 'sha256': sha}, contents=True)
        need(ref['identity'][3:6] == [0, 0, 1], 'root-sealed original lifecycle support')
        fd = os.open(CONTROL / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        HELD[name] = (ref, fd, raw)
    def load_held(path):
        path = Path(path); held_support()
        need(path.parent == CONTROL and path.name in ('owned_lifecycle.py', 'owned_adoption.py'), 'exact support module only')
        module = type(sys)('_mac_component_' + path.stem); module.__file__ = str(path)
        sys.modules[module.__name__] = module
        exec(compile(HELD[path.name][2], str(path), 'exec'), module.__dict__)
        return module
    SUPPORT = type(sys)('_mac_component_support'); SUPPORT.__file__ = str(CONTROL / 'transform_support.py')
    exec(compile(HELD['transform_support.py'][2], SUPPORT.__file__, 'exec'), SUPPORT.__dict__)
    SUPPORT.load_module = load_held
    COMMANDS = SUPPORT.OwnedCommands(D / 'commands', CONTROL)
    SUPPORT.install_signals(); held_support()
    REPORT['original_lifecycle_support'] = {name: item[0] for name, item in HELD.items()}

def run(name, argv, timeout=30, recovery=False):
    held_support()
    try:
        return COMMANDS.run(name, argv, timeout, env=ENV, cwd=D, recovery=recovery, discard_logs=False)
    finally:
        row = COMMANDS.last_record
        if row is not None and row.get('name') == name and not any(r['name'] == name for r in REPORT['commands']):
            REPORT['commands'].append(row)
        held_support()

def resources():
    available = int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))) * 1024
    st = os.statvfs(D); free = st.f_bavail * st.f_frsize
    need(available >= 13 * 1024**3 and free >= 12 * 1024**3, 'fresh 13GiB covers outer4GiB plus QEMU4GiB and 5GiB host reserve; 12GiB disk required')
    return {'MemAvailable_bytes': available, 'disk_available_bytes': free, 'minimum_memory_bytes': 13 * 1024**3, 'host_reserve_bytes': 5 * 1024**3, 'minimum_disk_bytes': 12 * 1024**3}

def host_snapshot():
    return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'kernel': os.uname().release,
            'active_lsm': Path('/sys/kernel/security/lsm').read_text().strip(),
            'apparmor_profiles_sha256': hashlib.sha256(Path('/sys/kernel/security/apparmor/profiles').read_bytes()).hexdigest(),
            'canonical': pin('/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json')}


def unique_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate JSON field')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def validate_bundle(bundle):
    need(set(bundle) == {'schema', 'sealed', 'controller', 'native_nonce', 'admission', 'payloads', 'qmp_source', 'qmp_stats_profile', 'qmp_stats_profile_sha256'}, 'exact component bundle schema with independently frozen KVM profile')
    need(bundle['schema'] == 'p4-systemd-cold-component-native-input-stats-v2' and bundle['sealed'] is True,
         'review-only template cannot dispatch; final input sealing required')
    need(re.fullmatch('[0-9a-f]{64}', bundle['native_nonce']), 'fixed native generation nonce')
    need(set(bundle['payloads']) == {'guest_init', 'policy', 'policy_export', 'apparmor', 'features', 'contract', 'systemd_public', 'systemd_manifest', 'observer_unit', 'observer_target', 'selinux_config', 'selinux_file_contexts'}, 'exact twelve public component input roles')
    for role, ref in bundle['payloads'].items():
        need(set(ref) == {'path', 'bytes', 'sha256'} and type(ref['bytes']) is int and 0 < ref['bytes'] <= 16 * 1024**2,
             'bounded exact payload pin: ' + role)
        need(re.fullmatch('[0-9a-f]{64}', ref['sha256']), 'whole payload SHA: ' + role)
        path = Path(ref['path'])
        need(path.is_absolute() and path.resolve() == path, 'canonical public input path')
        need(not str(path).startswith('/var/lib/droidloom/'), 'no original Android cohort/userdata input')
    need(bundle['payloads']['policy']['bytes'] == 736879 and bundle['payloads']['policy']['sha256'] ==
         '794f0839e5249818231d3759ba96f371842b3036099e146031adfec061abdca2', 'exact qualified R10 systemd DAC bootstrap policy input')
    need(bundle['payloads']['policy_export']['bytes'] == 736879 and bundle['payloads']['policy_export']['sha256'] ==
         '794f0839e5249818231d3759ba96f371842b3036099e146031adfec061abdca2', 'diagnostic expected export equals compiler A; actual R10 kernel export not yet observed')
    need(bundle['payloads']['guest_init']['bytes'] == 2118040 and bundle['payloads']['guest_init']['sha256'] ==
         '6faa4e278b9325612931070b8f1fe04f4ac186da6609ee3e14ef503b6225073a', 'exact qualified API preparation, first-load and NSFS guest ELF')
    for role, size, digest in [('selinux_config', 124, '12e92404a2ff890b1da58b8e52212bf6a76315a370e6301834f9fb3a3b2c7464'),
                               ('selinux_file_contexts', 8027, '297afb5c4033874d10ee9fa574ecdcd7ec9682573661e15586f18950f402c1dd')]:
        need(bundle['payloads'][role]['bytes'] == size and bundle['payloads'][role]['sha256'] == digest,
             'exact original default-backend qualified two-file configuration: ' + role)
    need(set(bundle['controller']) == {'bytes', 'sha256'}, 'exact reviewed controller pin')
    need(hashlib.sha256(bundle['qmp_source'].encode()).hexdigest() ==
         '821476d1d0af05097e3212e23d0ed04ab120f5be42bd2b2094497bdfdd31ecdd', 'reviewed original-custody QMP gate and bounded two-counter observation')
    stats_module = type(sys)('_p4_validate_stats_profile')
    exec(compile(bundle['qmp_source'], 'authenticated_owned_qmp_gate.py', 'exec'), stats_module.__dict__)
    stats_module.validate_profile(bundle['qmp_stats_profile'], bundle['qmp_stats_profile_sha256'])
    admission = bundle['admission']
    need(set(admission) == {'boot_id', 'kernel', 'canonical_bytes', 'canonical_sha256'}, 'explicit current host admission')
    need(type(admission['canonical_bytes']) is int and admission['canonical_bytes'] > 0 and
         re.fullmatch('[0-9a-f]{64}', admission['canonical_sha256']), 'final CURRENT pin required')

def outer_budget():
    need(AUTHENTICATED_CONTROLLER_BODY is not None and AUTHENTICATED_BUNDLE is not None, 'authenticated native source')
    row = Path('/proc/self/cgroup').read_text().strip()
    need(row == '0::/system.slice/' + OUTER_UNIT, 'exact native root controller cgroup')
    group = Path('/sys/fs/cgroup/system.slice') / OUTER_UNIT
    values = {n: (group / n).read_text().strip() for n in
              ('memory.max', 'memory.swap.max', 'memory.swap.current', 'memory.events', 'cpu.max', 'pids.max', 'cpuset.cpus.effective')}
    need(values['memory.max'] == str(4 * 1024**3) and values['memory.swap.max'] == values['memory.swap.current'] == '0', 'native outer memory4GiB/swap0')
    need(values['cpuset.cpus.effective'] == '4-5', 'actual outer cpuset enforces only CPUs4,5')
    quota, period = map(int, values['cpu.max'].split())
    need(quota == 2 * period and values['pids.max'] == '128' and os.sched_getaffinity(0) == {4, 5}, 'native outer CPUs4,5/CPU2/tasks128')
    expected = ['/usr/bin/python3', '-I', '-B', '-c', AUTHENTICATED_CONTROLLER_BODY.decode(), *sys.argv[1:]]
    actual = Path('/proc/self/cmdline').read_bytes().split(b'\0')
    need(actual[-1] == b'' and [x.decode() for x in actual[:-1]] == expected, 'actual native executable arguments bind full reviewed source and bundle')
    need(dict(item.split(b'=', 1) for item in Path('/proc/self/environ').read_bytes().rstrip(b'\0').split(b'\0')) ==
         {k.encode(): v.encode() for k, v in ENV.items()}, 'exact native sanitized environment')
    status = run('native-outer-actual-status', ['/usr/bin/systemctl', 'show', OUTER_UNIT,
        '--property=Id,LoadState,ActiveState,SubState,MainPID,InvocationID,Description,ControlGroup,User,Group,ExecMainCode,ExecMainStatus,Result', '--no-pager'])
    pairs = [line.split('=', 1) for line in Path(status['stdout']['path']).read_text().splitlines() if '=' in line]
    need(len(dict(pairs)) == len(pairs), 'unique native properties')
    observed = dict(pairs)
    need(observed['Id'] == OUTER_UNIT and observed['Description'] == OUTER_DESCRIPTION and
         observed['MainPID'] == str(os.getpid()) and observed['ControlGroup'] == '/system.slice/' + OUTER_UNIT and
         observed['User'] == observed['Group'] == '0' and re.fullmatch('[0-9a-f]{32}', observed['InvocationID']), 'actual native unit invocation and root PID')
    logs = {}
    for fd, name in ((1, 'outer.stdout'), (2, 'outer.stderr')):
        path = CARRIER / name; node = os.fstat(fd)
        need(os.readlink('/proc/self/fd/' + str(fd)) == str(path) and f9(node) == f9(path.lstat()), 'same actual native file log descriptor')
        need(stat.S_ISREG(node.st_mode) and node.st_uid == node.st_gid == 0 and node.st_nlink == 1 and stat.S_IMODE(node.st_mode) == 0o600,
             'root owned native log, single link, mode0600')
        need(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_APPEND, 'actual append-only native output descriptor')
        logs[name] = {'path': str(path), 'device': node.st_dev, 'inode': node.st_ino, 'append': True}
    result = {'execution_kind': 'native_systemd_system_unit', 'H_job_id': None, 'unit': OUTER_UNIT,
              'native_nonce': AUTHENTICATED_BUNDLE['native_nonce'], 'InvocationID': observed['InvocationID'],
              'pid': os.getpid(), 'start_ticks': Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19],
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'status': observed,
              'cgroup': str(group), 'limits': values, 'affinity': [4, 5], 'logs': logs}
    create(D / 'NATIVE-OUTER-STARTED.json', result)
    REPORT['native_outer'] = result
    REPORT['outer_budget_before'] = {'group': str(group), 'values': values, 'affinity': [4, 5]}
    return group

def parse_original_component_serial(console, contract, payloads):
    tags = ('P4_MAC_GUEST_AUTHENTICATED', 'P4_MAC_POLICY_LOADED', 'P4_MAC_POLICY_CHUNK',
            'P4_MAC_DECISION', 'P4_MAC_STACK_PENDING', 'P4_MAC_STACK_EXECUTED',
            'P4_MAC_CHILD_ERROR', 'P4_MAC_CHILD_RETIREMENT', 'P4_MAC_GUEST_FINAL')
    rows = {tag: [] for tag in tags}; ordered = []
    need(console.endswith('\n') and '\r' not in console, 'complete raw COM2 records without console transformations')
    for line in console.splitlines():
        need(line.startswith('P4_MAC_'), 'component channel contains only recognized guest records')
        tag, separator, payload = line.partition(' ')
        need(separator == ' ' and tag in rows and len(payload) <= 65536, 'finite recognized component serial record')
        value = unique_json(payload); need(type(value) is dict, 'component record object')
        rows[tag].append(value); ordered.append(tag)
    REPORT['guest_component_records'] = rows
    if len(rows['P4_MAC_GUEST_FINAL']) == 1:
        REPORT['guest_final'] = rows['P4_MAC_GUEST_FINAL'][0]
    REPORT['actual_top_level_tests'] = len(rows['P4_MAC_DECISION'])
    REPORT['actual_passed_top_level_tests'] = sum(row.get('passed') is True for row in rows['P4_MAC_DECISION'])
    # Failure records and the complete serial remain in the result; none are
    # transformed into Android/runtime admission or fabricated successful tests.
    need(not rows['P4_MAC_CHILD_ERROR'] and not rows['P4_MAC_CHILD_RETIREMENT'], 'no surrogate child or retirement error')
    need(rows['P4_MAC_GUEST_AUTHENTICATED'] == [{'kernel': '7.0.14-p4ctx3', 'PID1': True,
         'natural_NNP': 0, 'surrogate_only': True, 'Android_starts': 0}], 'one authenticated component-only guest')
    need(ordered and ordered[0] == 'P4_MAC_GUEST_AUTHENTICATED' and ordered[-1] == 'P4_MAC_GUEST_FINAL', 'complete ordered component serial')
    need(len(rows['P4_MAC_POLICY_LOADED']) == 1, 'one actual kernel policy receipt')
    policy = rows['P4_MAC_POLICY_LOADED'][0]
    need(policy['input_bytes'] == payloads['policy']['bytes'] and policy['input_sha256'] == payloads['policy']['sha256'] and
         policy['host_policy_loads'] == 0 and policy['guest_policy_loads'] == 1, 'exact guest-only policy bytes')
    lsm = policy['LSM'].split(',')
    need(lsm.count('selinux') == lsm.count('apparmor') == 1 and lsm.index('selinux') < lsm.index('apparmor'), 'actual SELinux-before-AppArmor')
    need(policy['netlink_xperm'] == 1 and policy['input_header'] in ([30, 0xc0000001], [30, 1])
         and policy['kernel_header'] == [30, 1], 'actual selected extended-netlink capability and exact known version30 MLS headers')
    epoch = policy['epoch']
    need(type(epoch) is list and len(epoch) == 5 and epoch[0] == epoch[2] == epoch[4] == 1 and epoch[1] % 2 == 0, 'actual enforcing policy epoch')
    if policy['complete_export_bytes_equal'] is not True:
        chunks = rows['P4_MAC_POLICY_CHUNK']; raw = bytearray()
        need(type(policy['kernel_bytes']) is int and 0 < policy['kernel_bytes'] <= 16 * 1024**2, 'bounded public kernel policy readback')
        for index, chunk in enumerate(chunks):
            need(set(chunk) == {'index', 'offset', 'hex'} and chunk['index'] == index and chunk['offset'] == len(raw), 'complete ordered policy chunks')
            need(re.fullmatch('[0-9a-f]+', chunk['hex']) and len(chunk['hex']) % 2 == 0 and len(chunk['hex']) <= 8192, 'public policy hex only')
            part = bytes.fromhex(chunk['hex']); raw.extend(part)
            need(len(raw) <= policy['kernel_bytes'], 'bounded readback total')
        need(len(raw) == policy['kernel_bytes'] and hashlib.sha256(raw).hexdigest() == policy['kernel_sha256'], 'full kernel policy readback size/SHA')
        REPORT['public_kernel_policy_readback'] = create(D / 'kernel-component-readback.policy', bytes(raw), 0o444)
    else:
        expected_export = payloads['policy_export']
        selected_ref, selected_bytes = pin(expected_export['path'], expected_export, contents=True)
        need(not rows['P4_MAC_POLICY_CHUNK'] and policy['kernel_bytes'] == len(selected_bytes) == policy['expected_export_bytes'] and
             policy['kernel_sha256'] == selected_ref['sha256'] == policy['expected_export_sha256'],
             'complete actual kernel export matches the separately sealed expected bytes')
        REPORT['kernel_policy_export_verification'] = {
            'selected_export': selected_ref, 'whole_guest_kernel_export_matched_sealed_expected': True,
            'actual_comparison': 'qualified static guest compares complete bytes before any decision or surrogate execution',
            'serial_hex_retransmission_omitted_only_after_complete_equality': True,
            'input_and_kernel_export_have_separate_complete_identities': True,
        }
    need(policy['complete_export_bytes_equal'] is True, 'actual complete kernel export identity required')
    expected_input_equal = payloads['policy']['bytes'] == payloads['policy_export']['bytes'] and payloads['policy']['sha256'] == payloads['policy_export']['sha256']
    need(policy['complete_bytes_equal'] is expected_input_equal, 'input equality diagnostic agrees with both full selected identities')
    for key in ('load_elapsed_us', 'readback_elapsed_us'):
        need(type(policy[key]) is int and 0 <= policy[key] <= 960_000_000, 'finite actual policy phase timing')
    access, transitions, creates = contract['access'], contract['transitions'], contract['creation_labels']
    decisions = rows['P4_MAC_DECISION']
    need(len(access) == contract['expected_access_cases'] == 132 and len(transitions) == contract['expected_transition_cases'] == 9
         and len(creates) == contract['expected_creation_cases'] == 2 and len(decisions) == 143, 'all143 exact reviewed kernel decisions; original140 included')
    sequence = None
    for expected, row in zip(access, decisions[:132]):
        need(row['kind'] == 'access' and all(row[key] == expected[key] for key in ('source', 'target', 'class', 'expected_allow')),
             'exact ordered access control inputs')
        need(row['passed'] is True and type(row['requested']) is int and 0 < row['requested'] <= 0xffffffff and
             type(row['actual_allowed']) is int and 0 <= row['actual_allowed'] <= 0xffffffff, 'actual nonempty successful access decision')
        need((row['actual_allowed'] & row['requested']) == (row['requested'] if row['expected_allow'] else 0), 'actual requested permission outcome')
        if sequence is None:
            sequence = row['sequence']
        need(type(sequence) is int and sequence > 0 and row['sequence'] == sequence, 'one actual policy decision sequence')
    for expected, row in zip(transitions, decisions[132:141]):
        need(row['kind'] == 'transition' and all(row[key] == expected[key] for key in ('source', 'executable', 'expected')) and
             row['actual'] in (row['expected'], row['expected'] + '\n', row['expected'] + '\0') and row['passed'] is True, 'actual exact transition context')
    for expected, row in zip(creates, decisions[141:]):
        need(row['kind'] == 'creation_label' and all(row[key] == expected[key] for key in ('source', 'parent', 'class', 'expected'))
             and row['actual'] in (row['expected'], row['expected'] + '\n', row['expected'] + '\0')
             and row['passed'] is True, 'actual two exact initial private-inode contexts')
    need(len(rows['P4_MAC_STACK_PENDING']) == len(rows['P4_MAC_STACK_EXECUTED']) == 1, 'both surrogate exec stages observed')
    pending, executed = rows['P4_MAC_STACK_PENDING'][0], rows['P4_MAC_STACK_EXECUTED'][0]
    need(pending == {'actual_NNP': 1, 'pending': 'p4-mac-fixture-android (enforce)\n',
         'current': 'p4-mac-fixture-broker (enforce)\n', 'PDEATHSIG': 9, 'surrogate': True}, 'actual pending fixture stack')
    need(executed['apparmor'] == 'p4-mac-fixture-android//&p4-mac-fixture-broker (enforce)\n' and
         executed['selinux'] in ('u:r:droidloom_host:s0', 'u:r:droidloom_host:s0\n', 'u:r:droidloom_host:s0\0') and
         executed['NNP'] == 1 and executed['PDEATHSIG'] == 0 and executed['surrogate'] is True and
         executed['actual_original_Android_ELF_execs'] == 0 and executed['passed'] is True, 'actual fixture label, NNP and process attributes')
    REPORT['actual_surrogate_execs'] = 2
    need(len(rows['P4_MAC_GUEST_FINAL']) == 1, 'one component guest terminal')
    final = rows['P4_MAC_GUEST_FINAL'][0]; REPORT['guest_final'] = final
    need(set(final) == {'passed', 'detail', 'error', 'Android_starts', 'actual_original_Android_ELF_execs',
         'host_policy_loads', 'runtime_qualified', 'production_ready', 'host_survival_qualified'}, 'exact component terminal scope')
    need(final['Android_starts'] == final['actual_original_Android_ELF_execs'] == final['host_policy_loads'] == 0 and
         final['runtime_qualified'] is final['production_ready'] is final['host_survival_qualified'] is False,
         'no runtime, original Android, host-survival or production qualification')
    need(final['passed'] is True and final['error'] is None and policy['complete_export_bytes_equal'] is True, 'actual component success, including whole kernel policy identity')
    detail = final['detail']; stack = detail['stack']
    need(detail['decisions'] == {'attempted': 143, 'passed': 143, 'sequence': sequence} and
         detail['kernel_policy_matches_selected_export'] is True and detail['kernel_policy_matches_compiler_bytes'] is expected_input_equal and detail['epoch_before'] == detail['epoch_after'] == epoch and
         detail['all_owned_children_retired'] is True and detail['passed'] is True, 'complete finite component decision and lifecycle result')
    need(stack['PIDFD_exit'] is True and stack['original_child_reaped'] is True and stack['forced_cleanup'] is False and
         stack['wait_status'] == stack['observed_status'] == 0 and stack['observed_code'] == 1 and stack['passed'] is True,
         'original surrogate PIDFD exit and normal reap')
    timing = detail['timing_us']
    need(set(timing) == {'load', 'readback', 'serialization_output', 'decisions', 'stack'} and
         all(type(v) is int and 0 <= v <= 960_000_000 for v in timing.values()), 'complete finite actual phase timings')
    need(timing['load'] == policy['load_elapsed_us'] and timing['readback'] == policy['readback_elapsed_us'], 'same actual policy phase measurements')
    REPORT['guest_phase_timings_us'] = timing
    REPORT['component_checks_passed'] = True

# Reviewed companion functions inserted verbatim into the new cold controller.
# No process, network, policy load, xattr mutation or host installation here.
def cold_mkdir(root, relative):
    need(relative and not relative.startswith('/') and all(x not in ('', '.', '..') for x in relative.split('/')),
         'fixed private guest directory path')
    current = root
    for name in relative.split('/'):
        current = current / name
        try:
            current.mkdir(mode=0o755)
            os.chmod(current, 0o755)
        except FileExistsError:
            pass
        node = current.lstat()
        need(stat.S_ISDIR(node.st_mode) and not stat.S_ISLNK(node.st_mode) and
             node.st_uid == node.st_gid == 0 and stat.S_IMODE(node.st_mode) == 0o755,
             'root-owned actual guest parent, without symlink traversal')

def cold_resolve_guest_link(name, target, links, regulars, directories):
    def normalize(parts):
        result = []
        for part in parts:
            if part in ('', '.'):
                continue
            if part == '..':
                need(result, 'guest alias cannot escape its own root')
                result.pop()
            else:
                result.append(part)
        return result
    todo = normalize(([] if target.startswith('/') else name.split('/')[:-1]) + target.split('/'))
    for _ in range(32):
        replaced = False
        for index in range(1, len(todo) + 1):
            prefix = '/'.join(todo[:index])
            if prefix in links:
                value = links[prefix]
                todo = normalize(([] if value.startswith('/') else todo[:index-1]) + value.split('/') + todo[index:])
                replaced = True
                break
        if not replaced:
            result = '/'.join(todo)
            need(result in regulars or result in directories, 'every guest alias resolves entirely inside captured guest inputs')
            return result
    raise RuntimeError('original guest alias cycle or chain exceeds32')

def materialize_cold_inputs(root, payloads, originals):
    import io, tarfile
    ref, manifest_raw = pin(payloads['systemd_manifest']['path'], payloads['systemd_manifest'], contents=True)
    originals.append(ref)
    need(len(manifest_raw) == 7214 and hashlib.sha256(manifest_raw).hexdigest() ==
         '2102e116ca510fc2c65be96f3ab20fbb5e1fb631f7601d90af6122bbe6cb9662',
         'exact manifest compiled into the qualified static cold guest')
    manifest = unique_json(manifest_raw)
    need(set(manifest) == {'schema', 'scope', 'archive_bytes', 'archive_sha256', 'members'} and
         manifest['schema'] == 'p4-original-systemd-disposable-inputs-v1' and
         manifest['scope'] == 'ISOLATED_COMPONENT_ONLY_NOT_PRODUCTION', 'exact cold component input scope')
    ref, archive = pin(payloads['systemd_public']['path'], payloads['systemd_public'], contents=True)
    originals.append(ref)
    archive_ref = ref
    need(ref['bytes'] == manifest['archive_bytes'] == 7287036 and ref['sha256'] == manifest['archive_sha256'] ==
         'eca15b2960049d684bb0dfe817832374242ac656dae51f085f0f13178352d7d8',
         'whole reviewed original systemd public closure archive')
    members = manifest['members']; need(type(members) is dict and len(members) == 45, 'exact45 public members')
    regulars, links, directories = {}, {}, set()
    for name, expected in members.items():
        need(name and not name.startswith('/') and all(x not in ('', '.', '..') for x in name.split('/')),
             'relative fixed public guest member')
        for n in range(1, len(name.split('/'))):
            directories.add('/'.join(name.split('/')[:n]))
        if 'symlink' in expected:
            need(set(expected) == {'symlink', 'mode'} and expected['mode'] == 0o777 and
                 type(expected['symlink']) is str and expected['symlink'], 'exact original symlink entry')
            links[name] = expected['symlink']
        else:
            need(set(expected) == {'bytes', 'sha256', 'mode'} and type(expected['bytes']) is int and
                 0 < expected['bytes'] <= 8 * 1024**2 and expected['mode'] in (0o444, 0o555) and
                 re.fullmatch('[0-9a-f]{64}', expected['sha256']), 'bounded single public ELF')
            regulars[name] = expected
    need(len(regulars) == 28 and len(links) == 17 and not set(links) & directories,
         'captured regular-file parents never pass through guest symlinks')
    resolved_links = {name: cold_resolve_guest_link(name, target, links, regulars, directories) for name, target in links.items()}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:xz') as source:
        objects = source.getmembers()
        need(len(objects) == 45 and len({x.name for x in objects}) == 45, 'archive has exactly45 unique members')
        for member in objects:
            need(member.name in members and member.name not in seen, 'no additional archive entries')
            seen.add(member.name); expected = members[member.name]
            need(member.uid == member.gid == 0 and member.mtime == 0 and not member.pax_headers and
                 member.mode == expected['mode'], 'fixed root archive headers')
            if member.name in links:
                need(member.issym() and member.linkname == links[member.name] and member.size == 0,
                     'exact original alias header')
                continue
            need(member.isfile() and member.size == expected['bytes'], 'exact public regular file only')
            body = source.extractfile(member).read(member.size + 1)
            need(len(body) == expected['bytes'] and hashlib.sha256(body).hexdigest() == expected['sha256'],
                 'whole original public ELF before private guest copy')
            cold_mkdir(root, str(Path(member.name).parent))
            create(root / member.name, body, member.mode)
    need(seen == set(members), 'complete reviewed public input archive')
    # Create aliases last. No host resolve(), extraction API, or later write may
    # traverse an absolute guest alias and reach outside this new private image.
    for name, target in sorted(links.items()):
        parent = str(Path(name).parent)
        if parent != '.': cold_mkdir(root, parent)
        os.symlink(target, root / name)
        node = (root / name).lstat()
        need(stat.S_ISLNK(node.st_mode) and node.st_uid == node.st_gid == 0 and node.st_nlink == 1
             and stat.S_IMODE(node.st_mode) == 0o777 and os.readlink(root / name) == target, 'actual private guest alias')
    for directory in ('etc/systemd/system', 'usr/lib/systemd/system', 'usr/lib/systemd/system-generators',
                      'etc/systemd/system-generators', 'var', 'var/lib', 'var/lib/systemd', 'var/log', 'var/tmp'):
        cold_mkdir(root, directory)
    fixed = {
        'etc/machine-id': b'61a925a202ee4849ace189cb56812b51\n',
        'etc/hostname': b'p4-systemd-cold\n',
        'etc/os-release': b'NAME="Pocket4 disposable systemd component"\nID=p4-systemd-component\n',
        'etc/passwd': b'root:x:0:0:Disposable guest root:/:/sbin/nologin\n',
        'etc/group': b'root:x:0:\ntty:x:5:\n',
        'etc/nsswitch.conf': b'passwd: files\ngroup: files\nshadow: files\nhosts: files\n',
        'etc/hosts': b'127.0.0.1 localhost\n::1 localhost\n',
    }
    for name, body in fixed.items(): create(root / name, body, 0o444)
    default_selinux = {'selinux_config': 'etc/selinux/config',
                      'selinux_file_contexts': 'etc/selinux/p4-systemd-component/contexts/files/file_contexts'}
    for role, name in default_selinux.items():
        cold_mkdir(root, str(Path(name).parent))
        ref = payloads[role]
        originals.append(pin(ref['path'], ref, copy_to=root / name, mode=0o444))
    REPORT['fixed_default_selinux_configuration'] = {'files': default_selinux,
        'prior_ordinary_parser_queries': 251, 'customization_files': 0, 'second_policy_binary': False,
        'host_configuration_files_copied': 0, 'production_ready': False}

    for role, name in (('observer_unit', 'p4-systemd-observe.service'), ('observer_target', 'p4-systemd-observe.target')):
        ref = payloads[role]
        originals.append(pin(ref['path'], ref, copy_to=root / 'etc/systemd/system' / name, mode=0o444))
    REPORT['original_systemd_guest_inputs'] = {'manifest': manifest, 'archive': archive_ref, 'resolved_guest_aliases': resolved_links,
        'actual_cold_boot_qualified': False, 'complete_dlopen_closure': False, 'production_ready': False,
        'original_systemd_bytes': 141776, 'original_systemd_sha256': 'a37f481da20c11ba2b5d06fcf549f3a0afdbfd903c7694411295e39f11f34234',
        'synthetic_guest_configuration_only': sorted(fixed), 'host_configuration_files_copied': 0}
    REPORT['guest_links'] = {name: {'identity': f9((root / name).lstat()), 'target': target} for name, target in links.items()}
    return set(regulars) | set(fixed) | {'etc/systemd/system/p4-systemd-observe.service', 'etc/systemd/system/p4-systemd-observe.target'} | set(default_selinux.values())

def fixed_api_snapshot(value, before_policy=False):
    need(type(value) is list and len(value) == 2, 'two actual fixed API snapshots')
    identities = []
    for row, path, kind, mode, flags in zip(value,
            ('/dev/shm', '/sys/fs/cgroup'), ('tmpfs', 'cgroup2'), (0o1777, 0o555),
            (['nodev', 'nosuid', 'rw'], ['nodev', 'noexec', 'nosuid', 'relatime', 'rw'])):
        need(type(row) is dict and set(row) == {'identity', 'raw_mountinfo', 'selinux_superblock_option'},
             'actual complete API mount observation')
        identity = row['identity']
        need(type(identity) is dict and set(identity) == {'mount_id', 'parent_mount_id', 'device',
             'root', 'path', 'filesystem', 'source', 'vfs_options', 'super_options', 'inode', 'unique_mount_id'},
             'complete held API mount identity')
        need(type(row['raw_mountinfo']) is str and len(row['raw_mountinfo']) <= 4096
             and '\n' not in row['raw_mountinfo'] and '\r' not in row['raw_mountinfo'], 'bounded single mountinfo line')
        p = row['raw_mountinfo'].split()
        need(len(p) == 10 and p[3:5] == ['/', path] and p[6:] and p[6:9] == ['-', kind, kind],
             'actual fixed private API mount, no subroot or propagation alias')
        need(all(re.fullmatch('[0-9]+', x) for x in p[:2]) and re.fullmatch('[0-9]+:[0-9]+', p[2]),
             'actual numeric mount IDs and device')
        raw_flags = p[5].split(',')
        need(len(raw_flags) == len(set(raw_flags)) and sorted(raw_flags) == flags,
             'exact API writable, no-suid, no-device, execution and atime flags')
        raw_options = p[9].split(',')
        need(all(raw_options) and len(raw_options) == len(set(raw_options)), 'unique actual superblock options')
        seclabel = 'seclabel' in raw_options
        need(type(row['selinux_superblock_option']) is bool and row['selinux_superblock_option'] == seclabel,
             'explicit actual SELinux superblock advertisement')
        if before_policy:
            need(not seclabel, 'no initialized SELinux superblock advertisement before first load')
        normalized = sorted(x for x in raw_options if x != 'seclabel')
        if path == '/dev/shm':
            need(set(normalized) <= {'rw', 'size=16384k', 'nr_inodes=1024', 'inode64', 'mode=1777', 'mode=01777'}
                 and {'rw', 'size=16384k', 'nr_inodes=1024'} <= set(normalized),
                 'fixed tmpfs memory and inode limits; no context override')
        else:
            need(normalized == ['nsdelegate', 'rw'], 'fixed real manager cgroup2 mount options')
        node = identity['inode']
        need(type(node) is list and len(node) == 5 and all(type(x) is int and 0 <= x <= 0xffffffffffffffff for x in node)
             and node[1] > 0 and stat.S_ISDIR(node[2]) and stat.S_IMODE(node[2]) == mode and node[3:] == [0, 0],
             'actual root-owned API directory identity and exact mode')
        mount_id, parent_id = int(p[0]), int(p[1])
        device = [int(x) for x in p[2].split(':')]
        need(device == [os.major(node[0]), os.minor(node[0])], 'mountinfo and held inode device agree')
        unique = identity['unique_mount_id']
        need(mount_id > 0 and parent_id > 0 and mount_id != parent_id and type(unique) is int and 0 < unique <= 0xffffffffffffffff,
             'returned actual mount and unique mount generation IDs')
        expected = {'mount_id': mount_id, 'parent_mount_id': parent_id, 'device': device,
                    'root': '/', 'path': path, 'filesystem': kind, 'source': kind,
                    'vfs_options': flags, 'super_options': normalized, 'inode': node, 'unique_mount_id': unique}
        need(identity == expected, 'all actual parsed mount fields bound without ignored options')
        identities.append(identity)
    need(len({x['mount_id'] for x in identities}) == len({x['unique_mount_id'] for x in identities}) == 2,
         'two distinct real API mount generations')
    return identities


def fixed_api_covered_targets(rows, mounted):
    need(type(rows) is list and len(rows) == 2, 'both actual covered target observations')
    for row, mount, path, source, kind, magic, mode, created in zip(rows, mounted,
            ('/dev/shm', '/sys/fs/cgroup'), ('/dev', '/sys'), ('devtmpfs', 'sysfs'),
            (0x01021994, 0x62656572), (0o755, 0o555), (True, False)):
        need(type(row) is dict and set(row) == {'path', 'identity', 'raw_mountinfo',
             'created_here', 'identity_after_mount', 'raw_mountinfo_after_mount'} and row['path'] == path
             and row['created_here'] is created and row['identity_after_mount'] == row['identity']
             and row['raw_mountinfo_after_mount'] == row['raw_mountinfo'],
             'fixed original kernel mountpoint versus newly created target')
        identity = row['identity']
        need(type(identity) is dict and set(identity) == {'inode', 'filesystem_magic',
             'filesystem_id_bytes', 'mount_id', 'unique_mount_id'}, 'complete covered filesystem identity')
        node, fsid = identity['inode'], identity['filesystem_id_bytes']
        need(type(node) is list and len(node) == 5 and all(type(x) is int and 0 <= x <= 0xffffffffffffffff for x in node)
             and node[1] > 0 and node[2] == (stat.S_IFDIR | mode) and node[3:] == [0, 0],
             'exact source-specific covered root mode and owner')
        need(type(identity['filesystem_magic']) is int and identity['filesystem_magic'] == magic
             and type(fsid) is list and len(fsid) == 8 and all(type(x) is int and 0 <= x <= 255 for x in fsid),
             'actual fixed source filesystem magic and complete fsid')
        need(type(row['raw_mountinfo']) is str and len(row['raw_mountinfo']) <= 4096
             and '\n' not in row['raw_mountinfo'] and '\r' not in row['raw_mountinfo'], 'bounded source mountinfo')
        parts = row['raw_mountinfo'].split()
        need(len(parts) == 10 and parts[3:5] == ['/', source] and parts[6:8] == ['-', kind]
             and all(re.fullmatch('[0-9]+', x) for x in parts[:2])
             and re.fullmatch('[0-9]+:[0-9]+', parts[2]), 'actual private fixed source mount')
        mount_id, unique = identity['mount_id'], identity['unique_mount_id']
        need(type(mount_id) is int and 0 < mount_id == int(parts[0]) == mount['parent_mount_id']
             and type(unique) is int and 0 < unique <= 0xffffffffffffffff and unique != mount['unique_mount_id']
             and [int(x) for x in parts[2].split(':')] == [os.major(node[0]), os.minor(node[0])],
             'covered inode filesystem and original parent mount generation bind new mount')


def validate_fixed_api_lifecycle(prepared, first_policy, before_exec, after_exec):
    need(type(prepared) is dict and set(prepared) == {'first_policy_precondition', 'mounts', 'initial_UID_map',
         'guest_policy_loads', 'label_mutations', 'namespace_creations', 'production_ready', 'covered_targets'},
         'one complete first-policy API preparation receipt')
    need(prepared['first_policy_precondition'] == first_policy and type(prepared['initial_UID_map']) is list
         and all(type(x) is int for x in prepared['initial_UID_map']) and prepared['initial_UID_map'] == [0, 0, 4294967295]
         and prepared['production_ready'] is False, 'same actual first-policy boot and initial-user-namespace map')
    for name in ('guest_policy_loads', 'label_mutations', 'namespace_creations'):
        need(type(prepared[name]) is int and prepared[name] == 0, 'API preparation performs no policy, label or namespace mutation')
    initial = fixed_api_snapshot(prepared['mounts'], before_policy=True)
    fixed_api_covered_targets(prepared['covered_targets'], initial)
    before = fixed_api_snapshot(before_exec)
    after = fixed_api_snapshot(after_exec)
    need(initial == before == after and before_exec == after_exec,
         'same actual held API mount generations before load, before original exec and through real manager observation')


def parse_component_serial(console, contract, payloads):
    need(console.endswith('\n') and '\r' not in console, 'complete raw original-systemd component serial')
    tags = ('P4_SYSTEMD_BEFORE_EXEC', 'P4_SYSTEMD_SERVER_INODE', 'P4_SYSTEMD_OBSERVER_STARTED',
            'P4_SYSTEMD_GUEST_FINAL', 'P4_SYSTEMD_HANDOFF_ERROR', 'P4_SYSTEMD_OBSERVER_ERROR')
    rows = {tag: [] for tag in tags}; original = []; cold_order = []; cold_started = False
    first_policy_rows = []; nsfs_rows = []; full_order = []; cold_observation_order = []; api_preparation_rows = []
    for line in console.splitlines():
        tag, separator, payload = line.partition(' ')
        need(separator == ' ' and len(payload) <= 65536, 'bounded complete guest observation record')
        full_order.append(tag)
        if tag == 'P4_SYSTEMD_API_PREPARED':
            need(not cold_started and not first_policy_rows and full_order ==
                 ['P4_MAC_GUEST_AUTHENTICATED', 'P4_SYSTEMD_API_PREPARED'],
                 'fixed API preparation occurs once before the first policy load')
            value = unique_json(payload); need(type(value) is dict, 'actual API preparation object')
            api_preparation_rows.append(value)
            continue
        if tag == 'P4_MAC_FIRST_POLICY':
            need(not cold_started, 'first-policy evidence precedes original systemd')
            value = unique_json(payload); need(type(value) is dict, 'actual first-policy object')
            first_policy_rows.append(value)
            continue
        if tag == 'P4_NSFS_FIXED_QUERY':
            value = unique_json(payload); need(type(value) is dict, 'actual NSFS query object')
            cold_started = True; nsfs_rows.append(value); cold_observation_order.append(tag)
            continue
        if line.startswith('P4_MAC_'):
            need(not cold_started, 'original MAC suite precedes every cold-systemd action')
            original.append(line)
            continue
        tag, separator, value = line.partition(' ')
        need(separator == ' ' and tag in rows and len(value) <= 65536, 'known bounded original-systemd record')
        parsed = unique_json(value); need(type(parsed) is dict, 'original-systemd record object')
        cold_started = True; rows[tag].append(parsed); cold_order.append(tag); cold_observation_order.append(tag)
    REPORT['original_systemd_component_records'] = rows
    REPORT['actual_first_policy_records'] = first_policy_rows
    REPORT['actual_fixed_api_preparation_records'] = api_preparation_rows
    REPORT['actual_nsfs_fixed_query_records'] = nsfs_rows
    need(len(first_policy_rows) == len(api_preparation_rows) == 1 and full_order[:4] ==
         ['P4_MAC_GUEST_AUTHENTICATED', 'P4_SYSTEMD_API_PREPARED', 'P4_MAC_FIRST_POLICY', 'P4_MAC_POLICY_LOADED'],
         'exactly one actual first-policy precondition in the controlled fresh boot')
    first = first_policy_rows[0]
    need(set(first) == {'guest_boot_id', 'policy_open_errno', 'no_policy_before_this_load', 'first_policy_required'}
         and type(first['policy_open_errno']) is int and first['policy_open_errno'] == errno.EINVAL == 22
         and first['no_policy_before_this_load'] is first['first_policy_required'] is True,
         'only exact EINVAL before the sealed guest sole policy load')
    need(type(first['guest_boot_id']) is str and
         re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', first['guest_boot_id'])
         and first['guest_boot_id'] != REPORT['host_before']['boot_id'], 'actual canonical disposable guest boot differs from host')
    loaded_rows = [unique_json(line.partition(' ')[2]) for line in original if line.startswith('P4_MAC_POLICY_LOADED ')]
    need(len(loaded_rows) == 1 and loaded_rows[0].get('first_policy_precondition') == first,
         'same actual precondition bound to the subsequent full policy load receipt')
    # Scope is the controlled sealed fresh boot and its sole loader. No global
    # inference about unrelated security_read_policy serialization errors.
    REPORT['first_policy_controlled_fresh_boot_observed'] = True
    # The entire old143/2exec assertion body stays unchanged in this function.
    parse_original_component_serial('\n'.join(original) + '\n', contract, payloads)
    need(not rows['P4_SYSTEMD_HANDOFF_ERROR'] and not rows['P4_SYSTEMD_OBSERVER_ERROR'],
         'actual original systemd handoff/observer error remains failure')
    need(len(nsfs_rows) == 4 and cold_observation_order == [
         'P4_NSFS_FIXED_QUERY', 'P4_NSFS_FIXED_QUERY', 'P4_SYSTEMD_BEFORE_EXEC',
         'P4_SYSTEMD_OBSERVER_STARTED', 'P4_NSFS_FIXED_QUERY', 'P4_NSFS_FIXED_QUERY',
         'P4_SYSTEMD_SERVER_INODE', 'P4_SYSTEMD_GUEST_FINAL'], 'four actual NSFS observations bracket original systemd exec')
    expected_ns = [('/proc/self/ns/user', 0x10000000, 3), ('/proc/self/ns/pid', 0x20000000, 4)] * 2
    negative = [{'command':c, 'return':-1, 'errno':errno.EACCES} for c in (0xb701, 0xb702, 0xb704, 0xb603)]
    for row, (path, kind, ident) in zip(nsfs_rows, expected_ns):
        need(set(row) == {'path','context','inode','actual_type','actual_id','denied','production_ready'}
             and row['path'] == path and row['actual_type'] == kind and row['actual_id'] == ident
             and row['context'] in ('u:object_r:droidloom_nsfs:s0', 'u:object_r:droidloom_nsfs:s0\0')
             and row['denied'] == negative and row['production_ready'] is False,
             'actual fixed namespace label, positive type/ID and four exact EACCES controls')
        inode = row['inode']
        need(type(inode) is list and len(inode) == 9 and all(type(n) is int and 0 <= n <= 0xffffffffffffffff for n in inode)
             and stat.S_ISREG(inode[2]), 'actual nine-field namespace inode identity')
    need(nsfs_rows[:2] == nsfs_rows[2:], 'same held initial namespaces across original manager exec')
    need(cold_order == ['P4_SYSTEMD_BEFORE_EXEC', 'P4_SYSTEMD_OBSERVER_STARTED', 'P4_SYSTEMD_SERVER_INODE', 'P4_SYSTEMD_GUEST_FINAL'],
         'one complete actual original-systemd cold lifecycle; partial boot is not success')
    before = rows['P4_SYSTEMD_BEFORE_EXEC'][0]; started = rows['P4_SYSTEMD_OBSERVER_STARTED'][0]
    inode = rows['P4_SYSTEMD_SERVER_INODE'][0]; final = rows['P4_SYSTEMD_GUEST_FINAL'][0]
    need(before['actual_initial_namespaces'] == [row['inode'] for row in nsfs_rows[:2]],
         'original handoff binds the actual pre-exec namespace records')
    need(before['original_PID1'] == 1 and before['natural_NNP'] == 0 and before['production_ready'] is False and
         before['Android_starts'] == 0 and before['original_ELF_bytes'] == 141776 and
         before['original_ELF_sha256'] == 'a37f481da20c11ba2b5d06fcf549f3a0afdbfd903c7694411295e39f11f34234' and
         type(before['start_ticks']) is int and before['start_ticks'] > 0, 'actual original PID1 handoff and exact public ELF')
    need(before['inputs'] == {'ELFs': 28, 'original_aliases': 17, 'archive_sha256': payloads['systemd_public']['sha256'],
         'input_manifest_sha256': payloads['systemd_manifest']['sha256'], 'complete_dlopen_closure': False},
         'all exact45 guest inputs actually checked before handoff')
    need(started['PPID'] == 1 and type(started['PID']) is int and started['PID'] > 1 and started['NNP'] == 1 and
         started['scope'] == 'ISOLATED_COMPONENT_ONLY_NOT_PRODUCTION', 'actual original manager child and applied NNP1')
    need(set(final) == {'passed', 'detail', 'error', 'production_ready', 'runtime_qualified', 'Android_starts',
         'host_policy_loads', 'actual_original_Android_ELF_execs', 'label_mutations', 'host_survival_qualified'} and
         final['production_ready'] is final['runtime_qualified'] is final['host_survival_qualified'] is False and
         final['Android_starts'] == final['actual_original_Android_ELF_execs'] == final['host_policy_loads'] == final['label_mutations'] == 0,
         'cold diagnostic never grants production, Android, label installation, or host-survival qualification')
    need(final['passed'] is True and final['error'] is None, 'actual original manager observation must succeed')
    detail = final['detail']
    need(detail['actual_original_systemd_PID1'] is True and detail['actual_original_ELF_bytes'] == before['original_ELF_bytes']
         and detail['actual_original_ELF_sha256'] == before['original_ELF_sha256']
         and detail['original_PID1_start_ticks'] == before['start_ticks'] and detail['held_exe_node'] == before['held_ELF_node'],
         'same actual PID1 generation and original held ELF across exec')
    host = ('u:r:droidloom_host:s0', 'u:r:droidloom_host:s0\n', 'u:r:droidloom_host:s0\0')
    need(detail['same_connection_SO_PEERCRED'] == [1, 0, 0] and detail['same_connection_SO_PEERPIDFD_live'] is True and
         detail['same_connection_SO_PEERSEC'] in host and detail['actual_manager_SELinux'] in host and
         detail['actual_manager_AppArmor'] == 'unconfined\n' and detail['UNIX_FD_negotiated'] is True and
         re.fullmatch('OK [0-9a-fA-F]{32}\\r\\n', detail['actual_authentication']),
         'actual same-FD manager peer, LSM identities, root authentication and UNIX_FD support')
    need(detail['actual_server_node'] == inode['node'] and detail['actual_server_security_selinux'] == inode['actual_security_selinux']
         and inode['filesystem_magic'] == 0x01021994 and inode['peer_authenticated'] is False and inode['label_mutations'] == 0,
         'same original actual service-side socket inode and observed old label')
    need(detail['label_mutations'] == 0 and detail['effective_production_unit_qualified'] is False and detail['daemon_death_qualified'] is False,
         'socket observation does not install a label or qualify production unit lifetime')
    old = REPORT['guest_component_records']['P4_MAC_POLICY_LOADED'][0]
    for value in (before['policy'], detail['policy']):
        need(value['epoch'] == old['epoch'] and value['LSM'] == old['LSM'] and value['netlink_xperm'] == 1 and
             value['input_bytes'] == payloads['policy']['bytes'] and value['input_sha256'] == payloads['policy']['sha256'] and
             value['export_bytes'] == payloads['policy_export']['bytes'] and value['export_sha256'] == payloads['policy_export']['sha256'] and
             value['selinux'] in host and value['apparmor'] == 'unconfined\n', 'same complete installed input/export/epoch through actual systemd')
    need(before['policy'] == detail['policy'] and detail['passed'] is True, 'complete unchanged cold manager observation')
    validate_fixed_api_lifecycle(api_preparation_rows[0], first, before['api_mounts'], detail['api_mounts'])
    REPORT['actual_fixed_API_mount_lifecycle_observed'] = True
    REPORT['actual_nsfs_fixed_query_observations_passed'] = 4
    REPORT['actual_nsfs_positive_ioctl_calls'] = 8
    REPORT['actual_nsfs_adjacent_EACCES_controls'] = 16
    REPORT['original_systemd_cold_observation_passed'] = True
    REPORT['actual_original_systemd_execs_observed'] = 1
    REPORT['effective_production_unit_qualified'] = False
    REPORT['daemon_death_qualified'] = False


# Source-only companion for the next reviewed cold carrier. This observes the
# original QEMU generation; it never changes scheduling, quota or watchdogs.
QEMU_PROC_FD = None
QEMU_CGROUP_FD = None
QEMU_PROC_IDENTITY = None
QEMU_CGROUP_IDENTITY = None
CPU_OBSERVATION_LAST_NS = None
CPU_OBSERVATION_LIMIT = 160
SERIAL_OBSERVATION_FILES = {}

def cpu_observation_accounting(raw):
    fields = raw.rsplit(')', 1)[1].split()
    positions = {'utime_ticks': 11, 'stime_ticks': 12, 'guest_time_ticks': 40}
    need(len(fields) > 40 and all(fields[index].isdigit() for index in positions.values()),
         'complete unsigned proc task CPU accounting fields14,15,43')
    # guest_time is included in utime; preserve the raw counters instead of
    # treating the guest counter as additional CPU time or clamping differences.
    return {name: int(fields[index]) for name, index in positions.items()}

def serial_observation_prepare():
    need(not SERIAL_OBSERVATION_FILES, 'one held serial observer per original generation')
    refs = [('qemu.stdout', D / 'qemu.stdout', REPORT['console_logs_initial']['qemu.stdout']),
            ('qemu.stderr', D / 'qemu.stderr', REPORT['console_logs_initial']['qemu.stderr']),
            ('component_stdout', COMPONENT_LOG, REPORT['component_log_initial'])]
    for name, path, ref in refs:
        need(ref['path'] == str(path), 'fixed original serial observation path')
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            node = f9(os.fstat(fd))
            need(node[:6] == ref['identity'][:6] == f9(path.lstat())[:6] and
                 stat.S_ISREG(node[2]) and node[5] == 1 and 0 <= node[6] <= SERIAL_LIMIT,
                 'held original single-link serial output inode')
            SERIAL_OBSERVATION_FILES[name] = {'fd': fd, 'path': path,
                'identity': node[:6], 'last_size': node[6]}
        except BaseException:
            os.close(fd)
            raise
    REPORT['serial_observation_contract'] = {
        'initial_files': {name: ref for name, _, ref in refs},
        'sampling': 'before and after each existing bounded CPU sample',
        'metadata_only': True, 'held_read_only_descriptors': True,
        'running_content_reads': 0, 'extra_QMP_commands': 0,
        'maximum_CPU_samples': CPU_OBSERVATION_LIMIT,
        'per_file_version_fields': 'device,inode,mode,uid,gid,nlink,size,mtime_ns,ctime_ns',
        'output_growth_does_not_prove_KVM_exit_cause': True,
    }

def serial_observation_snapshot():
    need(set(SERIAL_OBSERVATION_FILES) == {'qemu.stdout', 'qemu.stderr', 'component_stdout'},
         'all three held original serial files')
    started = time.monotonic_ns(); wall = time.time_ns()
    files = {}
    for name, held in SERIAL_OBSERVATION_FILES.items():
        node = f9(os.fstat(held['fd']))
        need(node[:6] == held['identity'] == f9(held['path'].lstat())[:6],
             'same held original serial output inode throughout observation')
        need(held['last_size'] <= node[6] <= SERIAL_LIMIT,
             'bounded nondecreasing original serial output extent')
        files[name] = {'identity': node, 'bytes': node[6]}
        held['last_size'] = node[6]
    return {'monotonic_start_ns': started, 'wall_time_ns': wall,
            'monotonic_end_ns': time.monotonic_ns(), 'files': files}

class CpuObservationOriginalExited(RuntimeError):
    pass

def cpu_observation_live_pidfd():
    need(PIDFD is not None and POLL is not None, 'held original CPU-observed PIDFD')
    events = POLL.poll(0)
    if events:
        need(len(events) == 1 and events[0][0] == PIDFD and
             events[0][1] & (select.POLLIN | select.POLLHUP) and
             not events[0][1] & (select.POLLERR | select.POLLNVAL),
             'only actual original PIDFD exit may end CPU sampling')
        REPORT['cpu_observation_original_exit'] = {
            'pid': BOUND_PID, 'start_ticks': BOUND_START, 'invocation': INVOCATION,
            'actual_PIDFD_revents': events[0][1], 'monotonic_ns': time.monotonic_ns(),
            'incomplete_sample_not_counted_as_success': True,
        }
        raise CpuObservationOriginalExited('actual original QEMU exited during CPU observation')

def cpu_observation_read(directory, name, maximum=65536):
    need(name and '/' not in name and name not in ('.', '..'), 'fixed proc observation basename')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    try:
        parts = []; size = 0
        while True:
            block = os.read(fd, min(4096, maximum + 1 - size))
            if not block:
                break
            parts.append(block); size += len(block)
            need(size <= maximum, 'bounded proc/cgroup observation')
        return b''.join(parts).decode('ascii', errors='strict')
    finally:
        os.close(fd)

def cpu_observation_generation():
    need(QEMU_PROC_FD is not None and QEMU_CGROUP_FD is not None,
         'same live original QEMU PIDFD for CPU observation')
    cpu_observation_live_pidfd()
    need(f9(os.fstat(QEMU_PROC_FD)) == QEMU_PROC_IDENTITY,
         'same original held QEMU proc directory inode')
    need(f9(os.fstat(QEMU_CGROUP_FD))[:6] == QEMU_CGROUP_IDENTITY[:6],
         'same original held QEMU cgroup directory inode')
    try:
        bound = cpu_observation_read(QEMU_PROC_FD, 'stat')
        membership = cpu_observation_read(QEMU_PROC_FD, 'cgroup')
    except OSError as error:
        if error.errno in (errno.ENOENT, errno.ESRCH):
            cpu_observation_live_pidfd()
        raise
    need(bound.rsplit(')', 1)[1].split()[19] == BOUND_START,
         'held QEMU proc start generation')
    need(membership == '0::/system.slice/' + UNIT + '\n',
         'held original QEMU remains in its original unit cgroup')
    lines = [line for line in Path('/proc/self/fdinfo/' + str(PIDFD)).read_text().splitlines()
             if line.startswith('Pid:')]
    if not (len(lines) == 1 and int(lines[0].split()[1]) == BOUND_PID):
        # fdinfo may change to Pid:-1 during the original exit. Only the held
        # PIDFD's actual exit event makes that an incomplete observation.
        cpu_observation_live_pidfd()
        raise RuntimeError('CPU observer original PIDFD binding changed while live')
    cpu_observation_live_pidfd()
    return bound

def cpu_observation_prepare():
    global QEMU_PROC_FD, QEMU_CGROUP_FD, QEMU_PROC_IDENTITY, QEMU_CGROUP_IDENTITY
    need(QEMU_PROC_FD is QEMU_CGROUP_FD is None, 'one CPU observer per original generation')
    cpu_observation_live_pidfd()
    QEMU_PROC_FD = os.open('/proc/' + str(BOUND_PID), os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    QEMU_CGROUP_FD = os.open(CG, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    QEMU_PROC_IDENTITY = f9(os.fstat(QEMU_PROC_FD))
    QEMU_CGROUP_IDENTITY = f9(os.fstat(QEMU_CGROUP_FD))
    need(stat.S_ISDIR(QEMU_PROC_IDENTITY[2]) and stat.S_ISDIR(QEMU_CGROUP_IDENTITY[2]),
         'actual proc and cgroup directories')
    cpu_observation_generation()
    clock_ticks = os.sysconf('SC_CLK_TCK')
    need(isinstance(clock_ticks, int) and clock_ticks > 0, 'actual positive host clock ticks per second')
    serial_observation_prepare()
    REPORT['cpu_observation_contract'] = {
        'original_pid': BOUND_PID, 'original_start_ticks': BOUND_START,
        'original_unit': UNIT, 'original_invocation': INVOCATION,
        'held_proc_identity': QEMU_PROC_IDENTITY,
        'held_cgroup_identity': QEMU_CGROUP_IDENTITY,
        'maximum_samples': CPU_OBSERVATION_LIMIT, 'running_minimum_interval_ns': 1000000000,
        'maximum_tasks_per_sample': 64, 'allowed_CPUs': [4, 5],
        'SC_CLK_TCK': clock_ticks, 'proc_stat_CPU_fields': {'utime': 14, 'stime': 15, 'guest_time': 43},
        'guest_time_included_in_utime': True,
        'watchdog_and_resource_limits_changed': False,
        'causal_attribution_from_sampling_alone': False,
    }
    REPORT['actual_QEMU_cpu_samples'] = []
    cpu_observation_sample('paused-before-cont', force=True)

def cpu_observation_sample(phase, force=False):
    try:
        return cpu_observation_sample_inner(phase, force)
    except OSError as error:
        if error.errno in (errno.ENOENT, errno.ESRCH):
            cpu_observation_live_pidfd()
        raise

def cpu_observation_sample_inner(phase, force=False):
    global CPU_OBSERVATION_LAST_NS
    now = time.monotonic_ns()
    if not force and CPU_OBSERVATION_LAST_NS is not None and now - CPU_OBSERVATION_LAST_NS < 1000000000:
        return
    need(phase in ('paused-before-cont', 'running'), 'fixed CPU observation phases')
    rows = REPORT['actual_QEMU_cpu_samples']
    need(len(rows) < CPU_OBSERVATION_LIMIT, 'finite CPU observation count')
    started = time.monotonic_ns(); wall = time.time_ns()
    original_stat = cpu_observation_generation()
    serial_before = serial_observation_snapshot()
    values = {name: cpu_observation_read(QEMU_CGROUP_FD, name)
              for name in ('cpu.stat', 'cgroup.events', 'cpuset.cpus.effective')}
    need(values['cpuset.cpus.effective'].strip() == '4-5',
         'actual original QEMU cgroup restricts every thread to CPUs4,5')
    cpu_values = dict(line.split() for line in values['cpu.stat'].splitlines())
    need(all(name in cpu_values and cpu_values[name].isdigit()
             for name in ('usage_usec', 'user_usec', 'system_usec', 'nr_periods', 'nr_throttled', 'throttled_usec')),
         'actual bounded numeric cgroup CPU counters')
    taskdir = os.open('task', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=QEMU_PROC_FD)
    tasks = []
    try:
        names = os.listdir(taskdir)
        need(1 <= len(names) <= 64 and all(x.isdecimal() for x in names), 'actual bounded QEMU task catalog')
        names.sort(key=int)
        for name in names:
            fd = None
            try:
                fd = os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=taskdir)
                inode = f9(os.fstat(fd))
                first = cpu_observation_read(fd, 'stat')
                status = cpu_observation_read(fd, 'status')
                stats = cpu_observation_read(fd, 'schedstat')
                affinity = sorted(os.sched_getaffinity(int(name)))
                last = cpu_observation_read(fd, 'stat')
                fields = first.rsplit(')', 1)[1].split()
                after = last.rsplit(')', 1)[1].split()
                tgids = [line.split()[1] for line in status.splitlines() if line.startswith('Tgid:')]
                need(tgids == [str(BOUND_PID)] and fields[19] == after[19] and f9(os.fstat(fd)) == inode,
                     'actual task belongs to same QEMU and held task generation')
                allowed = [line.split()[1] for line in status.splitlines() if line.startswith('Cpus_allowed_list:')]
                need(allowed == ['4-5'] and affinity == [4, 5],
                     'each actual held QEMU task has both proc and scheduler affinity4,5')
                raw_stats = stats.split()
                need(len(raw_stats) == 3 and all(x.isdigit() for x in raw_stats), 'actual three-field task schedstat')
                tasks.append({'tid': int(name), 'start_ticks': fields[19], 'held_proc_identity': inode,
                    'stat_before': first, 'stat_after': last, 'schedstat_raw': stats,
                    'accounting_before': cpu_observation_accounting(first),
                    'accounting_after': cpu_observation_accounting(last),
                    'runtime_ns': int(raw_stats[0]), 'runqueue_wait_ns': int(raw_stats[1]),
                    'timeslices': int(raw_stats[2]), 'Tgid': BOUND_PID,
                    'proc_Cpus_allowed_list': allowed[0], 'actual_scheduler_affinity': affinity})
            except OSError as error:
                # QEMU creates and retires helper threads. Preserve only exact
                # kernel disappearance codes as incomplete task observations;
                # no such row is a successful schedstat measurement.
                need(error.errno in (errno.ENOENT, errno.ESRCH), 'no unexplained task observation error')
                tasks.append({'tid': int(name), 'incomplete': True, 'actual_errno': error.errno})
            finally:
                if fd is not None:
                    os.close(fd)
    finally:
        os.close(taskdir)
    serial_after = serial_observation_snapshot()
    cpu_observation_generation()
    if phase == 'paused-before-cont':
        need(all('schedstat_raw' in row for row in tasks),
             'all enumerated paused QEMU tasks observed before CPU start')
    need(any(row.get('tid') == BOUND_PID and 'schedstat_raw' in row for row in tasks),
         'actual original QEMU leader schedstat observed in every completed sample')
    finished = time.monotonic_ns()
    rows.append({'phase': phase, 'wall_time_ns': wall, 'monotonic_start_ns': started,
        'monotonic_end_ns': finished, 'read_elapsed_ns': finished-started,
        'pid': BOUND_PID, 'start_ticks': BOUND_START, 'unit': UNIT, 'invocation': INVOCATION,
        'held_process_stat': original_stat, 'cgroup_raw': values, 'tasks': tasks,
        'serial_growth': {'before': serial_before, 'after': serial_after},
        'original_PIDFD_live_at_both_boundaries': True})
    CPU_OBSERVATION_LAST_NS = finished

def cpu_observation_bind_qmp(cpus):
    # Diagnostic join only. A QMP numeric thread ID creates no process authority.
    # Resolve it solely beneath the held original QEMU proc directory and retain
    # the observed task generation for later raw schedstat correlation.
    cpu_observation_generation()
    need(type(cpus) is list and len(cpus) == 2, 'exact two configured virtual CPUs')
    for row in cpus:
        need(type(row) is dict and {'cpu-index', 'thread-id', 'qom-path', 'target'} <= set(row)
             and set(row) <= {'cpu-index', 'thread-id', 'qom-path', 'target', 'props', 'qom-type'},
             'bounded documented CpuInfoFast shape')
        need(type(row['cpu-index']) is int and row['cpu-index'] in (0, 1)
             and type(row['thread-id']) is int and 1 < row['thread-id'] < 2**31
             and row['target'] == 'x86_64' and type(row['qom-path']) is str
             and 0 < len(row['qom-path']) <= 1024, 'fixed x86 two-CPU mapping')
    need({row['cpu-index'] for row in cpus} == {0, 1}
         and len({row['thread-id'] for row in cpus}) == 2
         and len({row['qom-path'] for row in cpus}) == 2, 'unique virtual CPU indices and host threads')
    # The earlier sample preceded the QMP handshake and may legitimately omit
    # vCPU threads created during QEMU initialization. Keep it as raw evidence,
    # then capture the actual paused task generations after the authenticated
    # query has returned. This is one strict sample, not a readiness retry.
    need('QMP_CPU_query_before_start' not in REPORT, 'one original pre-start CPU query binding')
    sample_index = len(REPORT['actual_QEMU_cpu_samples'])
    need(sample_index > 0, 'initial original CPU sample retained')
    query = {'pid': BOUND_PID, 'start_ticks': BOUND_START, 'invocation': INVOCATION,
             'query_cpus_fast': cpus, 'observed_monotonic_ns': time.monotonic_ns(),
             'initial_sample_count': sample_index, 'paused_sample_index': sample_index,
             'paused_sample_completed': False, 'binding_completed': False}
    REPORT['QMP_CPU_query_before_start'] = query
    cpu_observation_sample('paused-before-cont', force=True)
    need(len(REPORT['actual_QEMU_cpu_samples']) == sample_index + 1,
         'one completed post-query paused sample')
    paused = REPORT['actual_QEMU_cpu_samples'][sample_index]
    query['paused_sample_completed'] = True
    need(paused['phase'] == 'paused-before-cont' and paused['pid'] == BOUND_PID
         and paused['start_ticks'] == BOUND_START and paused['invocation'] == INVOCATION,
         'same paused original QEMU generation')
    previous = {row['tid']: row for row in paused['tasks'] if 'schedstat_raw' in row}
    taskdir = os.open('task', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=QEMU_PROC_FD)
    mapped = []
    try:
        for row in sorted(cpus, key=lambda item: item['cpu-index']):
            tid = row['thread-id']; need(tid in previous, 'QMP thread present in paused actual task catalog')
            task = os.open(str(tid), os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=taskdir)
            try:
                inode = f9(os.fstat(task)); first = cpu_observation_read(task, 'stat')
                status = cpu_observation_read(task, 'status'); last = cpu_observation_read(task, 'stat')
                start = first.rsplit(')', 1)[1].split()[19]
                tgids = [line.split()[1] for line in status.splitlines() if line.startswith('Tgid:')]
                allowed = [line.split()[1] for line in status.splitlines() if line.startswith('Cpus_allowed_list:')]
                need(start == last.rsplit(')', 1)[1].split()[19] == previous[tid]['start_ticks']
                     and inode == previous[tid]['held_proc_identity']
                     and f9(os.fstat(task)) == inode and tgids == [str(BOUND_PID)]
                     and allowed == ['4-5'] and sorted(os.sched_getaffinity(tid)) == [4, 5],
                     'mapped vCPU thread has original task generation, group and actual CPU bounds')
                mapped.append({'cpu_index': row['cpu-index'], 'tid': tid, 'start_ticks': start,
                    'held_proc_identity': inode, 'actual_Tgid': BOUND_PID, 'actual_affinity': [4, 5],
                    'QMP_cpu_info': row, 'paused_sample_index': sample_index,
                    'paused_sample_start_ticks': previous[tid]['start_ticks']})
            finally:
                os.close(task)
    finally:
        os.close(taskdir)
    cpu_observation_generation()
    REPORT['QMP_CPU_mapping_before_start'] = mapped
    query['binding_completed'] = True
    return mapped

def cpu_observation_close():
    global QEMU_PROC_FD, QEMU_CGROUP_FD
    errors = []
    for fd in [*(held['fd'] for held in SERIAL_OBSERVATION_FILES.values()), QEMU_PROC_FD, QEMU_CGROUP_FD]:
        if fd is not None:
            try: os.close(fd)
            except OSError as error: errors.append(repr(error))
    SERIAL_OBSERVATION_FILES.clear()
    QEMU_PROC_FD = QEMU_CGROUP_FD = None
    need(not errors, 'all original CPU and serial observation descriptors closed: ' + repr(errors))


def show_unit(recovery=False):
    row = run('unit-show-' + str(len(REPORT['commands'])), ['/usr/bin/systemctl', 'show', UNIT, '--property=Id,LoadState,ActiveState,SubState,MainPID,InvocationID,Description,ControlGroup,Result,ExecMainCode,ExecMainStatus,User,Group', '--no-pager'], recovery=recovery)
    raw = Path(row['stdout']['path']).read_text(); need(len(raw) < 16384, 'bounded unit status')
    pairs = [line.split('=', 1) for line in raw.splitlines() if '=' in line]
    need(len(dict(pairs)) == len(pairs), 'unique properties')
    return dict(pairs)

def vm_resources():
    values = {n: (CG / n).read_text().strip() for n in ('memory.max', 'memory.swap.max', 'memory.swap.current', 'memory.current', 'memory.peak', 'memory.events', 'cpu.max', 'cpuset.cpus.effective', 'pids.current')}
    need(values['memory.max'] == str(4 * 1024**3) and values['memory.swap.max'] == values['memory.swap.current'] == '0', 'VM memory4GiB/swap0')
    q, period = map(int, values['cpu.max'].split()); need(q == 2 * period, 'VM CPU2')
    need(values['cpuset.cpus.effective'] == '4-5', 'actual VM cpuset enforces only CPUs4,5')
    events = dict(line.split() for line in values['memory.events'].splitlines())
    need(all(int(events.get(k, 0)) == 0 for k in ('oom', 'oom_kill', 'oom_group_kill')), 'VM OOM prohibited')
    return values

class ComponentChannelPending(RuntimeError):
    """Only an observed zero COM2 descriptor count may await initialization."""


def component_descriptor_snapshot(proc, held_log):
    # This observation creates no process authority. live_original validates the
    # original PIDFD/generation/identity first, then rechecks PIDFD liveness.
    sample = {'started_ns': time.time_ns(), 'pid': BOUND_PID, 'start_ticks': BOUND_START,
              'InvocationID': INVOCATION, 'file': held_log, 'scanned_fd_numbers': [],
              'vanished_readlinks': [], 'candidates': [], 'scan_complete': False}
    REPORT.setdefault('QEMU_component_descriptor_observations', []).append(sample)
    for entry in sorted((proc / 'fd').iterdir(), key=lambda path: int(path.name)):
        sample['scanned_fd_numbers'].append(int(entry.name))
        try:
            target = os.readlink(entry)
        except FileNotFoundError:
            sample['vanished_readlinks'].append(int(entry.name))
            continue
        if target != str(COMPONENT_LOG):
            continue
        candidate = {'fd': int(entry.name), 'target': target}
        sample['candidates'].append(candidate)
        # Matching pathname errors are terminal, never an unobserved zero.
        node = entry.stat(); candidate['identity'] = f9(node)
        need(candidate['identity'][:6] == held_log['identity'][:6],
             'original QEMU holds original COM2 file inode')
        with (proc / 'fdinfo' / entry.name).open('rb') as stream:
            info = stream.read(65537)
        need(len(info) <= 65536, 'bounded actual QEMU COM2 fdinfo')
        candidate['fdinfo_raw'] = info.decode('ascii', errors='strict')
        candidate['identity_after'] = f9(entry.stat())
        candidate['target_after'] = os.readlink(entry)
        need(candidate['identity_after'][:6] == candidate['identity'][:6]
             and candidate['target_after'] == target, 'same COM2 descriptor inode through observation')
    sample['matching_count'] = len(sample['candidates'])
    sample['scan_complete'] = True; sample['finished_ns'] = time.time_ns()
    return sample


def live_original(allow_pending_component=False):
    need(PIDFD is not None and not POLL.poll(0), 'original live QEMU PIDFD required')
    lines = [line for line in Path('/proc/self/fdinfo/' + str(PIDFD)).read_text().splitlines() if line.startswith('Pid:')]
    need(len(lines) == 1 and int(lines[0].split()[1]) == BOUND_PID, 'kernel PIDFD binding')
    p = Path('/proc') / str(BOUND_PID)
    need(p.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] == BOUND_START, 'original QEMU generation')
    need(os.readlink(p / 'exe') == '/usr/bin/qemu-system-x86_64', 'actual QEMU executable')
    args = (p / 'cmdline').read_bytes().split(b'\0'); need(args[-1] == b'' and [x.decode() for x in args[:-1]] == QEMU, 'exact QEMU argv')
    env = (p / 'environ').read_bytes().split(b'\0'); need(env[-1] == b'', 'complete environment')
    pairs = [x.split(b'=', 1) for x in env[:-1]]
    need(len(dict(pairs)) == len(pairs) and {k.decode(): v.decode() for k, v in pairs} == QEMU_ENV, 'exact QEMU environment')
    status = dict(line.split(':', 1) for line in (p / 'status').read_text().splitlines() if ':' in line)
    ids = {k: list(map(int, status[k].split())) for k in ('Uid', 'Gid', 'Groups', 'NSpid')}
    caps = {k: int(status[k].strip(), 16) for k in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')}
    need(ids['Uid'] == ids['Gid'] == [1000] * 4 and set(ids['Groups']) == set(EXPECTED_GROUPS), 'ordinary QEMU IDs')
    need(all(v == 0 for v in caps.values()) and status['NoNewPrivs'].strip() == '1', 'QEMU caps0/NNP1')
    need((p / 'cgroup').read_text() == '0::/system.slice/' + UNIT + '\n' and os.sched_getaffinity(BOUND_PID) == {4, 5}, 'owned QEMU cgroup/affinity')
    unit = show_unit()
    need(unit['MainPID'] == str(BOUND_PID) and unit['InvocationID'] == INVOCATION and unit['Description'] == DESCRIPTION and unit['User'] == unit['Group'] == '1000', 'exact original unit invocation')
    # This is original custody, not a pre-CPU readiness or success witness.
    bound = {'pid': BOUND_PID, 'start_ticks': BOUND_START, 'InvocationID': INVOCATION}
    previous = REPORT.setdefault('actual_QEMU_bound_generation', bound)
    need(previous == bound, 'same original QEMU generation before COM2 readiness')
    held_log = component_log(REPORT['component_log_initial'])
    observed = component_descriptor_snapshot(p, held_log)
    REPORT['resource_samples'].append({'time_ns': time.time_ns(), 'values': vm_resources(), 'fresh_host_resources': resources()})
    need(not POLL.poll(0), 'QEMU remained paused/live through observation')
    if observed['matching_count'] == 0 and allow_pending_component:
        raise ComponentChannelPending('actual original QEMU has not opened fixed COM2 yet')
    need(observed['matching_count'] == 1, 'one actual QEMU output descriptor for fixed COM2 channel')
    REPORT['QEMU_component_log_descriptor'] = {'fd': observed['candidates'][0]['fd'], 'file': held_log}
    return {'pid': BOUND_PID, 'start_ticks': BOUND_START, 'argv': QEMU, 'environment': QEMU_ENV, 'IDs': ids, 'caps': caps, 'NNP': 1, 'InvocationID': INVOCATION, 'affinity': [4, 5]}

def stop_owned():
    if not UNIT_REQUESTED: return
    unit = show_unit(recovery=True)
    if unit.get('LoadState') == 'loaded' and unit.get('ActiveState') != 'inactive':
        need(unit.get('Description') == DESCRIPTION and unit.get('User') == '1000', 'only this owned QEMU unit')
        need(unit.get('ControlGroup') == '/system.slice/' + UNIT or unit.get('MainPID') == '0', 'owned cgroup scope')
        if INVOCATION is not None: need(unit.get('InvocationID') == INVOCATION, 'never stop a different invocation')
        run('owned-unit-stop', ['/usr/bin/systemctl', 'stop', UNIT], recovery=True)
    unit = show_unit(recovery=True)
    need(unit.get('MainPID', '0') == '0' and not unit.get('ControlGroup') and unit.get('ActiveState') in ('inactive', 'failed') and not CG.exists(), 'actual unit/cgroup retired')
    if PIDFD is not None: need(bool(POLL.poll(2000)), 'original QEMU PIDFD observed exit')
    REPORT['owned_VM_unit_retired'] = True; REPORT['actual_QEMU_PIDFD_exit'] = PIDFD is not None; REPORT['unit_after'] = unit


def main():
    global REPORT, PIDFD, POLL, BOUND_PID, BOUND_START, INVOCATION, UNIT_REQUESTED, QEMU, QEMU_ENV, EXPECTED_GROUPS
    global AUTHENTICATED_CONTROLLER_BODY, AUTHENTICATED_BUNDLE
    need(os.getresuid() == os.getresgid() == (0, 0, 0), 'existing root rights for isolated VM preparation')
    need(len(sys.argv) == 4, 'exact authenticated component bundle path/SHA and controller path')
    bundle_path, bundle_sha, controller_path = sys.argv[1:]
    need(Path(bundle_path) == CARRIER / 'INPUT-BUNDLE.json' and Path(controller_path) == CARRIER / 'controller.py', 'fixed native carrier source paths')
    bundle_ref, raw = pin(bundle_path, contents=True)
    need(bundle_ref['sha256'] == bundle_sha, 'reviewed complete component bundle SHA')
    bundle = unique_json(raw); validate_bundle(bundle)
    controller_ref, body = pin(controller_path, bundle['controller'], contents=True)
    need(bundle_ref['identity'][3:6] == controller_ref['identity'][3:6] == [0, 0, 1], 'root sealed native input and controller')
    AUTHENTICATED_CONTROLLER_BODY, AUTHENTICATED_BUNDLE = body, bundle
    lockpath = Path('/home/alex/work/pocket4-android-final/.qpr1-kernel-control-8b88.lock')
    lock = os.open(lockpath, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC); lockid = f9(os.fstat(lock))
    need(stat.S_ISREG(lockid[2]) and lockid[1] == 41719533 and lockid[3:6] == [0, 0, 1], 'original root owned VM lock')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    need(not os.path.lexists(D), 'create-only new component VM namespace')
    os.umask(0o077); D.mkdir(mode=0o700)
    REPORT = {'schema': 'p4-original-systemd-cold-native-owned-VM-v1', 'state': 'PREPARING', 'errors': [], 'commands': [],
              'resource_samples': [], 'VM_launches': 0, 'actual_top_level_tests': 0, 'actual_passed_top_level_tests': 0,
              'original_systemd_cold_observation_passed': False, 'actual_original_systemd_execs_observed': 0,
              'effective_production_unit_qualified': False, 'daemon_death_qualified': False,
              'actual_surrogate_execs': 0, 'Android_starts': 0, 'actual_original_Android_ELF_execs': 0,
              'host_kernel_installations': 0, 'host_reboots': 0, 'host_MAC_policy_loads': 0, 'host_policy_loads': 0,
              'host_Android_namespace_creations': 0, 'original_userdata_or_private_key_reads': 0,
              'component_only': True, 'surrogate_only': False, 'host_survival': False, 'runtime': False,
              'host_survival_qualified': False, 'runtime_qualified': False, 'production_ready': False,
              'ExecutionAdmission_constructible': False, 'execution_kind': 'native_systemd_system_unit', 'H_job_id': None,
              'native_nonce': bundle['native_nonce'], 'started_ns': time.time_ns(),
              'original_kernel_control_lock': {'path': str(lockpath), 'identity': lockid}}
    originals = []; REPORT['public_inputs_before'] = originals
    before = None; disk = None; disk_ref = None; outer = None; stats_session = None
    try:
        before = host_snapshot(); REPORT['host_before'] = before
        admission = bundle['admission']
        need(before['canonical']['bytes'] == admission['canonical_bytes'] and
             before['canonical']['sha256'] == admission['canonical_sha256'], 'exact reviewed fresh CURRENT snapshot')
        need(before['boot_id'] == admission['boot_id'] and before['kernel'] == admission['kernel'], 'same selected Pocket4 host boot and kernel')
        stats_profile = bundle['qmp_stats_profile']
        need(stats_profile['host'] == {'release': os.uname().release, 'version': os.uname().version, 'boot_id': before['boot_id']},
             'same explicitly reviewed KVM host kernel build and boot')
        need('selinux' not in before['active_lsm'].split(','), 'host SELinux remains inactive; only the new guest loads policy')
        REPORT['resources_before_preparation'] = resources()
        originals += [bundle_ref, controller_ref]
        create(D / 'controller.py', body); create(D / 'INPUT-BUNDLE.json', raw)
        create(D / 'owned_qmp_gate.py', bundle['qmp_source'].encode())
        prepare_support(); outer = outer_budget()
        root = D / 'rootfs'; root.mkdir(mode=0o755); os.chmod(root, 0o755)
        for name in ('sbin', 'etc', 'dev', 'proc', 'sys', 'run', 'tmp', 'control', 'fixture'):
            path = root / name; path.mkdir(mode=0o755); os.chmod(path, 0o755)
        create(root / 'p4-mac-disposable-root', b'p4-mac-policy-e6ac-r1\n', 0o444)
        create(root / 'etc/fstab', ('UUID=' + UUID + ' / ext4 defaults 0 1\n').encode(), 0o444)
        guest = D / 'guest-inputs'; guest.mkdir(mode=0o755); os.chmod(guest, 0o755)
        for label, name in (('kernel', 'vmlinuz'), ('initrd', 'initrd.img')):
            path, size, sha = INPUTS[label]
            originals.append(pin(path, {'bytes': size, 'sha256': sha}, copy_to=guest / name, mode=0o444))
        path, size, sha = INPUTS['kernel_config']
        config_ref, config_body = pin(path, {'bytes': size, 'sha256': sha}, contents=True); originals.append(config_ref)
        config = config_body.decode().splitlines()
        need(all(line in config for line in ('CONFIG_EXT4_FS=y', 'CONFIG_SECURITY_SELINUX=y', 'CONFIG_SECURITY_APPARMOR=y', 'CONFIG_SERIAL_8250=y', 'CONFIG_SERIAL_8250_CONSOLE=y', 'CONFIG_SERIAL_8250_RUNTIME_UARTS=32')),
             'exact selected kernel contains ext4 and both MAC implementations')
        payloads = bundle['payloads']
        # Four independent copies of the qualified static fixture. Original host
        # systemd and its captured loader/libraries are confined to this guest;
        # no Android ELF, cohort, userdata or original runtime harness enters.
        for relative in ('sbin/init', 'fixture/broker', 'fixture/android', 'fixture/systemd-observer'):
            ref = payloads['guest_init']
            originals.append(pin(ref['path'], ref, copy_to=root / relative, mode=0o555))
        extra_cold_files = materialize_cold_inputs(root, payloads, originals)
        destinations = {'policy': 'component.policy', 'policy_export': 'policy-export.bin', 'apparmor': 'apparmor-fixture.bin',
                        'features': 'apparmor-features.json', 'contract': 'fixture-contract.json'}
        for role, name in destinations.items():
            ref = payloads[role]
            originals.append(pin(ref['path'], ref, copy_to=root / 'control' / name, mode=0o444))
        contract = unique_json((root / 'control/fixture-contract.json').read_bytes())
        need(contract['scope'] == 'ISOLATED_COMPONENT_ONLY_NOT_PRODUCTION' and
             len(contract['access']) == contract['expected_access_cases'] == 132
             and len(contract['transitions']) == contract['expected_transition_cases'] == 9
             and len(contract['creation_labels']) == contract['expected_creation_cases'] == 2, 'whole143 reviewed finite policy contract')
        for role, path in (('policy', '/control/component.policy'), ('policy_export', '/control/policy-export.bin'), ('apparmor', '/control/apparmor-fixture.bin'),
                           ('features', '/control/apparmor-features.json')):
            need(contract[role]['path'] == path and contract[role]['bytes'] == payloads[role]['bytes'] and
                 contract[role]['sha256'] == payloads[role]['sha256'], 'guest contract binds full source bytes: ' + role)
        tools = {}
        for tool in ('/usr/bin/readelf', '/usr/bin/qemu-system-x86_64', '/usr/bin/systemctl', '/usr/bin/systemd-run', '/usr/sbin/mke2fs'):
            canonical = Path(tool).resolve(); ref = pin(canonical, system_links=True)
            need(ref['identity'][3] == 0, 'original installed public tool owner')
            originals.append(ref); tools[tool] = ref
        REPORT['host_tools'] = tools
        need({k: tools['/usr/bin/qemu-system-x86_64'][k] for k in ('bytes', 'sha256')} ==
             {k: stats_profile['qemu'][k] for k in ('bytes', 'sha256')}, 'same independently reviewed installed QEMU executable bytes')
        row = run('fixture-static-ELF-program-headers', ['/usr/bin/readelf', '-W', '-l', str(root / 'sbin/init')])
        programs = Path(row['stdout']['path']).read_text()
        row = run('fixture-static-ELF-dynamic', ['/usr/bin/readelf', '-W', '-d', str(root / 'sbin/init')])
        dynamic = Path(row['stdout']['path']).read_text()
        need('INTERP' not in programs and '(NEEDED)' not in dynamic and '(RPATH)' not in dynamic and '(RUNPATH)' not in dynamic,
             'actual static fixture has no host-dependent ELF lookup')
        loads = [line.split() for line in programs.splitlines() if line.strip().startswith('LOAD ')]
        stacks = [line.split() for line in programs.splitlines() if line.strip().startswith('GNU_STACK ')]
        need(loads and all(not ('W' in ''.join(row[6:-1]) and 'E' in ''.join(row[6:-1])) for row in loads), 'no fixture W+X load')
        need(len(stacks) == 1 and 'E' not in ''.join(stacks[0][6:-1]), 'actual NX fixture stack')
        REPORT['guest_files'] = {p.relative_to(root).as_posix(): pin(p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
        expected_files = {'p4-mac-disposable-root', 'etc/fstab', 'sbin/init', 'fixture/broker', 'fixture/android',
                          'control/component.policy', 'control/policy-export.bin', 'control/apparmor-fixture.bin', 'control/apparmor-features.json', 'control/fixture-contract.json'}
        expected_files.update(extra_cold_files); expected_files.add('fixture/systemd-observer')
        need(set(REPORT['guest_files']) == expected_files, 'only reviewed component fixture root files')
        fixture_nodes = [REPORT['guest_files'][name]['identity'][:2] for name in ('sbin/init', 'fixture/broker', 'fixture/android', 'fixture/systemd-observer')]
        need(len({tuple(node) for node in fixture_nodes}) == 4, 'four actual independent single-link fixture inodes')
        disk = D / 'new-private-root.ext4'
        fd = os.open(disk, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.ftruncate(fd, 512 * 1024**2); os.fsync(fd); os.close(fd)
        run('new-private-component-root-mke2fs', ['/usr/sbin/mke2fs', '-t', 'ext4', '-F', '-U', UUID, '-L', 'P4MACPOLICY',
            '-m', '0', '-E', 'lazy_itable_init=0,lazy_journal_init=0', '-d', str(root), str(disk)], 120)
        os.chmod(disk, 0o444); disk_ref = pin(disk); REPORT['new_private_base_disk'] = disk_ref
        need({p: pin(root / p) for p in REPORT['guest_files']} == REPORT['guest_files'], 'whole root files unchanged after formatter')
        create(D / 'PREPARATION-READY.json', {'root_files': REPORT['guest_files'], 'base_disk': disk_ref, 'inputs': originals,
            'commands': REPORT['commands'], 'VM_launches': 0, 'Android_starts': 0, 'actual_original_Android_ELF_execs': 0,
            'component_only': True, 'runtime_qualified': False, 'production_ready': False})
        os.chmod(D, 0o711)
        tmp, qmpdir = D / 'qemu-tmp', D / 'qmp'
        for path in (tmp, qmpdir):
            path.mkdir(mode=0o700); os.chown(path, 1000, 1000)
        REPORT['console_logs_initial'] = {}
        for name in ('qemu.stdout', 'qemu.stderr'):
            REPORT['console_logs_initial'][name] = create(D / name, b'', 0o600)
        create(COMPONENT_LOG, b'', 0o600); os.chown(COMPONENT_LOG, 1000, 1000)
        REPORT['component_log_initial'] = component_log()
        need(REPORT['component_log_initial']['bytes'] == 0, 'fresh empty COM2 channel')

        EXPECTED_GROUPS = os.getgrouplist('alex', 1000)
        QEMU_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'HOME': '/nonexistent', 'TMPDIR': str(tmp)}
        QEMU = ['/usr/bin/qemu-system-x86_64', '-no-user-config', '-nodefaults', '-machine', 'q35,accel=kvm', '-cpu', 'host', '-m', '3072', '-smp', '2', '-display', 'none', '-serial', 'stdio', '-serial', 'file:' + str(COMPONENT_LOG), '-monitor', 'none', '-nic', 'none', '-no-reboot', '-S', '-qmp', 'unix:' + str(qmpdir / 'qmp.sock') + ',server=on,wait=off', '-smbios', 'type=1,manufacturer=Pocket4KernelQualification,product=Pocket4MACPolicyControlsE6acR1,serial=p4-mac-policy-e6ac-r1', '-drive', 'file=' + str(disk) + ',if=none,format=raw,id=p4nvme,snapshot=on', '-device', 'nvme,drive=p4nvme,serial=P4MACPOLICY', '-kernel', str(guest / 'vmlinuz'), '-initrd', str(guest / 'initrd.img'), '-append', 'console=ttyS0,115200 root=UUID=' + UUID + ' rootfstype=ext4 ro init=/sbin/init fsck.mode=force fsck.repair=no noresume panic=1 oops=panic loglevel=6 p4mac=policy-e6ac-r1 lsm=landlock,lockdown,yama,integrity,selinux,apparmor,bpf selinux=1 enforcing=1 apparmor=1']
        properties = ['Type=exec', 'RemainAfterExit=yes', 'User=1000', 'Group=1000', 'MemoryMax=4294967296', 'MemorySwapMax=0', 'CPUQuota=200%', 'CPUAffinity=4 5', 'AllowedCPUs=4 5', 'TasksMax=64', 'KillMode=control-group', 'RuntimeMaxSec=180', 'TimeoutStopSec=15', 'OOMPolicy=stop', 'Nice=15', 'UMask=0077', 'PrivateMounts=yes', 'PrivateNetwork=yes', 'PrivateTmp=yes', 'ProtectSystem=strict', 'ProtectHome=read-only', 'ProtectKernelTunables=yes', 'ProtectKernelModules=yes', 'ProtectControlGroups=yes', 'NoNewPrivileges=yes', 'CapabilityBoundingSet=', 'AmbientCapabilities=', 'DevicePolicy=closed', 'DeviceAllow=/dev/kvm rw', 'LimitCORE=0', 'ReadOnlyPaths=' + str(D), 'ReadWritePaths=' + str(tmp) + ' ' + str(qmpdir), 'InaccessiblePaths=/var/lib/droidloom -/dev/nvme0n1 -/dev/nvme0n1p1 -/dev/nvme0n1p2 -/run/systemd/private -/run/dbus/system_bus_socket -/run/user', 'StandardInput=null', 'StandardOutput=append:' + str(D / 'qemu.stdout'), 'StandardError=append:' + str(D / 'qemu.stderr')]
        REPORT['unit_properties'] = properties; REPORT['qemu_argv'] = QEMU; REPORT['sanitized_QEMU_environment'] = QEMU_ENV
        REPORT['resources_before_VM_start'] = resources()
        need(show_unit().get('LoadState') == 'not-found' and not CG.exists(), 'never reuse existing unit')
        argv = ['/usr/bin/systemd-run', '--unit=' + UNIT, '--description=' + DESCRIPTION, '--collect']
        for prop in properties: argv += ['-p', prop]
        argv += ['/usr/bin/python3', '-I', '-B', '-c', 'import os;os.execve(' + repr(QEMU[0]) + ',' + repr(QEMU) + ',' + repr(QEMU_ENV) + ')']
        create(D / 'VM-LAUNCH-INTENT.json', {'unit': UNIT, 'argv': argv, 'one_launch_only': True, 'resources': REPORT['resources_before_VM_start']})
        UNIT_REQUESTED = True; run('new-owned-QEMU-unit-start', argv); REPORT['VM_launches'] = 1
        unit = show_unit(); need(unit['Description'] == DESCRIPTION and unit['MainPID'] not in ('', '0'), 'new actual MainPID')
        BOUND_PID = int(unit['MainPID']); INVOCATION = unit['InvocationID']; PIDFD = os.pidfd_open(BOUND_PID, 0)
        POLL = select.poll(); POLL.register(PIDFD, select.POLLIN)
        BOUND_START = Path('/proc/' + str(BOUND_PID) + '/stat').read_text().rsplit(')', 1)[1].split()[19]
        deadline = time.monotonic() + 15
        REPORT['prelaunch_absolute_deadline_monotonic'] = deadline
        while True:
            need(time.monotonic() < deadline and not POLL.poll(0), 'bounded original prelaunch')
            if os.readlink('/proc/' + str(BOUND_PID) + '/exe') == QEMU[0] and (qmpdir / 'qmp.sock').exists():
                try:
                    before_cpu = live_original(allow_pending_component=True)
                except ComponentChannelPending:
                    # Only an exact zero may wait. Duplicate-FD, inode, identity,
                    # unit, resource and every other error remain terminal.
                    pass
                else:
                    need(time.monotonic() < deadline and not POLL.poll(0), 'original prelaunch completed before its deadline')
                    REPORT['actual_QEMU_before_CPU_start'] = before_cpu
                    break
            remaining = deadline - time.monotonic()
            need(remaining > 0 and not POLL.poll(min(50, max(1, int(remaining * 1000)))),
                 'bounded original prelaunch')
        cpu_observation_prepare()
        module = type(sys)('_d7_owned_QMP'); exec(compile(bundle['qmp_source'], str(D / 'owned_qmp_gate.py'), 'exec'), module.__dict__)
        REPORT['QMP_controller_call_boundaries'] = {'before': {
            'monotonic_start_ns': time.monotonic_ns(), 'wall_time_ns': time.time_ns(),
            'monotonic_end_ns': time.monotonic_ns()}}
        REPORT['QMP_stats_observation'] = {'profile_sha256': bundle['qmp_stats_profile_sha256'], 'records': [], 'runtime_qualified': False}
        def stats_record(value):
            records = REPORT['QMP_stats_observation']['records']
            need(len(records) < 4096, 'bounded QMP observation metadata count')
            records.append(value)
            if value['state'] in ('QMP_PAUSED_CPU_QUERY_OBSERVED', 'QMP_CONT_REQUEST_COMMITTED_ONCE', 'QMP_CONT_ACKNOWLEDGED_ONCE'):
                create(D / ('QMP-' + value['state'] + '.json'), value)
        stats_session = module.start_exact_owned_cpu(qmpdir / 'qmp.sock', BOUND_PID, PIDFD, live_original,
            stats_record, cpu_observation_bind_qmp, stats_profile, bundle['qmp_stats_profile_sha256'])
        REPORT['QMP_CPU_start_gate'] = stats_session.start_result
        REPORT['QMP_controller_call_boundaries']['after'] = {
            'monotonic_start_ns': time.monotonic_ns(), 'wall_time_ns': time.time_ns(),
            'monotonic_end_ns': time.monotonic_ns()}
        deadline = time.monotonic() + 150
        while not POLL.poll(100):
            need(time.monotonic() < deadline and not SUPPORT.CANCELLED, 'finite actual VM completion')
            available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
            REPORT['running_host_memory_samples'] = REPORT.get('running_host_memory_samples', 0) + 1
            REPORT['minimum_running_MemAvailable_bytes'] = min(REPORT.get('minimum_running_MemAvailable_bytes', available), available)
            REPORT['last_running_host_reserve'] = {'time_ns': time.time_ns(), 'MemAvailable_bytes': available, 'minimum_bytes': 5 * 1024**3}
            need(available >= 5 * 1024**3, 'actual host memory reserve fell below 5GiB; retire only this owned VM')
            try: REPORT['last_running_VM_resources'] = vm_resources()
            except FileNotFoundError:
                if POLL.poll(0): break
                raise
            try:
                stats_session.drain_events(deadline)
                previous_samples = len(REPORT['actual_QEMU_cpu_samples'])
                cpu_observation_sample('running')
                if len(REPORT['actual_QEMU_cpu_samples']) != previous_samples:
                    row = REPORT['actual_QEMU_cpu_samples'][-1]
                    if stats_session.terminal_announced:
                        stats_record({'state': 'QMP_STATS_SLOT_AFTER_SHUTDOWN', 'sample_index': previous_samples,
                                      'original_PIDFD_exit_still_required': True})
                    elif stats_session.last_sample_end_ns is None or time.monotonic_ns() - stats_session.last_sample_end_ns >= 1000000000:
                        stats_session.sample({'sample_index': previous_samples, 'sample': row}, deadline)
                    else:
                        stats_record({'state': 'QMP_STATS_SLOT_SKIPPED_RATE_LIMIT', 'sample_index': previous_samples,
                                      'missing_is_not_zero': True})
            except CpuObservationOriginalExited:
                break
            need((D / 'qemu.stdout').stat().st_size + (D / 'qemu.stderr').stat().st_size + COMPONENT_LOG.stat().st_size <= SERIAL_LIMIT, 'bounded full component VM serial including public policy readback')
        REPORT['actual_QEMU_PIDFD_exit'] = True; unit = show_unit()
        REPORT['QMP_stats_observation']['coverage'] = stats_session.finish()
        deadline = time.monotonic() + 5
        while unit.get('MainPID') != '0' and time.monotonic() < deadline: unit = show_unit()
        need(unit['InvocationID'] == INVOCATION and unit['MainPID'] == '0' and unit['Result'] == 'success' and unit['ExecMainCode'] == '1' and unit['ExecMainStatus'] == '0', 'actual owned QEMU exited0')
        REPORT['actual_QEMU_terminal_unit'] = unit

        sync_regular_log(COMPONENT_LOG)
        REPORT['component_stdout'], machine_raw = component_log(REPORT['component_log_initial'], contents=True)
        console_ref, console_raw = pin(D / 'qemu.stdout', contents=True)
        critical = rb'BUG:|Oops:|Kernel panic|soft lockup|hard LOCKUP|rcu:.*stall|KASAN:|UBSAN:|general protection fault|kernel BUG at|WARNING: CPU:|clocksource: Long readout interval'
        incidents = [line.decode('utf-8', errors='replace') for line in console_raw.splitlines() if re.search(critical, line)]
        REPORT['kernel_console_observation'] = {'complete_console': console_ref, 'critical_lines': incidents,
            'no_observed_critical_events': not incidents, 'prior_VM3_events_preserved': True}
        parse_component_serial(machine_raw.decode('utf-8', errors='strict'), contract, payloads)
        need(not incidents, 'actual guest kernel has no recorded critical event or long clocksource interval')
        REPORT['state'] = 'ALL_COMPONENT_CONTROLS_PASSED_ANDROID_UNQUALIFIED'
    except BaseException as error:
        REPORT['state'] = 'FAILED_NOT_QUALIFIED'; REPORT['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        if stats_session is not None:
            try: stats_session.close()
            except BaseException as error: REPORT['errors'].append({'stage': 'QMP_stats_FD_close', 'message': repr(error)})
        try: stop_owned()
        except BaseException as error: REPORT['errors'].append({'stage': 'owned_VM_retirement', 'message': repr(error)})
        try: cpu_observation_close()
        except BaseException as error: REPORT['errors'].append({'stage':'CPU_observation_FD_close','message':repr(error)})
        if PIDFD is not None: os.close(PIDFD); PIDFD = None
        if COMMANDS is not None:
            REPORT['all_host_child_commands_retired'] = COMMANDS.all_retired
            REPORT['command_journal'] = COMMANDS.finish()
        try:
            for ref in originals: pin(ref['path'], ref, system_links=str(ref['path']).startswith('/usr/'))
            for alias in REPORT.get('installed_public_aliases', []):
                path = Path(alias['requested']); need(f9(path.lstat()) == alias['identity'] and str(path.resolve()) == alias['canonical'], 'original installed alias changed')
                if alias['link'] is not None: need(os.readlink(path) == alias['link'], 'original installed symlink changed')
            REPORT['all_source_inputs_unchanged'] = True
            if disk_ref is not None: pin(disk, disk_ref); REPORT['private_base_disk_unchanged'] = True
            if before is not None: REPORT['host_after'] = host_snapshot(); need(REPORT['host_after'] == before, 'same host kernel/MAC/canonical F9'); REPORT['host_unchanged'] = True
            if outer is not None:
                values = {n: (outer / n).read_text().strip() for n in ('memory.max', 'memory.swap.max', 'memory.swap.current', 'memory.peak', 'memory.events', 'cpu.max')}
                REPORT['outer_budget_after'] = values
                events = dict(line.split() for line in values['memory.events'].splitlines())
                need(all(int(events.get(k, 0)) == 0 for k in ('oom', 'oom_kill', 'oom_group_kill')), 'outer OOM0')
            held_support()
            need(f9(os.fstat(lock)) == f9(lockpath.lstat()) == lockid, 'same original VM lock inode/F9')
        except BaseException as error: REPORT['errors'].append({'stage': 'complete_after_inputs_host', 'message': repr(error)})
        for _, fd, _ in HELD.values(): os.close(fd)
        fcntl.flock(lock, fcntl.LOCK_UN); os.close(lock)
        for name in ('qemu.stdout', 'qemu.stderr'):
            if (D / name).exists():
                sync_regular_log(D / name)
                REPORT[name] = pin(D / name)
        try:
            if COMPONENT_LOG.exists():
                sync_regular_log(COMPONENT_LOG)
                REPORT['component_stdout'] = component_log(REPORT.get('component_log_initial'))
        except BaseException as error:
            REPORT['errors'].append({'stage': 'complete_COM2_log', 'message': repr(error)})
        if REPORT['errors'] or not REPORT.get('all_host_child_commands_retired'): REPORT['state'] = 'FAILED_NOT_QUALIFIED'
        REPORT['finished_ns'] = time.time_ns(); REPORT['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ref = create(D / 'RESULT.json', REPORT)
        print(json.dumps({'state': REPORT['state'], 'result': ref, 'VM_launches': REPORT['VM_launches'], 'actual_cases': REPORT['actual_top_level_tests'], 'actual_passed': REPORT['actual_passed_top_level_tests'], 'errors': REPORT['errors']}), flush=True)
    return 0 if REPORT['state'] == 'ALL_COMPONENT_CONTROLS_PASSED_ANDROID_UNQUALIFIED' else 1

if __name__ == '__main__':
    raise SystemExit(main())
