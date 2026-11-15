# Exact function slices for source review and data-only tests.
# This is not a standalone controller and has no entrypoint.
# Full original MAC/API validators are intentionally not stubbed here.

def need(value, message):
    if not value:
        raise RuntimeError(message)


def unique_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate JSON field')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def validate_fixed_nsfs_records(nsfs_rows):
    need(type(nsfs_rows) is list and len(nsfs_rows) == 4, 'four complete fixed namespace records')
    expected_ns = [('/proc/self/ns/user', 0x10000000, 3), ('/proc/self/ns/pid', 0x20000000, 4)] * 2
    negative = [{'command':c, 'return':-1, 'errno':errno.EACCES} for c in (0xb701, 0xb702, 0xb704, 0xb603)]
    for row, (path, kind, ident) in zip(nsfs_rows, expected_ns):
        need(type(row) is dict and set(row) == {'path','context','inode','actual_type','actual_id','denied','production_ready'}
             and row['path'] == path and row['actual_type'] == kind and row['actual_id'] == ident
             and row['context'] in ('u:object_r:droidloom_nsfs:s0', 'u:object_r:droidloom_nsfs:s0\0')
             and row['denied'] == negative and row['production_ready'] is False,
             'actual fixed namespace label, positive type/ID and four exact EACCES controls')
        inode = row['inode']
        need(type(inode) is list and len(inode) == 9 and all(type(n) is int and 0 <= n <= 0xffffffffffffffff for n in inode)
             and stat.S_ISREG(inode[2]), 'actual nine-field namespace inode identity')
    # Pre-exec descriptors are CLOEXEC. Across exec, retain the full observations
    # but compare the stable nsfs object identity, not freshly materialized inode
    # timestamps. The exact fixed type/ID, labels and denied ioctls remain bound.
    stable = [dict(row, inode=row['inode'][:7]) for row in nsfs_rows]
    need(stable[:2] == stable[2:], 'same fixed initial namespace object identity across original manager exec')


def validate_original_server_metadata(metadata):
    need(type(metadata) is dict and set(metadata) == {'node', 'expected_mode', 'peer_authenticated', 'label_mutations'}
         and type(metadata['expected_mode']) is int and metadata['expected_mode'] == 0o700
         and metadata['peer_authenticated'] is False and type(metadata['label_mutations']) is int
         and metadata['label_mutations'] == 0, 'bounded unauthenticated original server metadata only')
    node = metadata['node']
    need(type(node) is list and len(node) == 9 and all(type(n) is int and 0 <= n <= 0xffffffffffffffff for n in node)
         and node[2] == (stat.S_IFSOCK | 0o700) and node[3:6] == [0, 0, 1],
         'actual root0700 original server socket identity before peer authentication')


def parse_component_serial(console, contract, payloads):
    need(console.endswith('\n') and '\r' not in console, 'complete raw original-systemd component serial')
    tags = ('P4_SYSTEMD_BEFORE_EXEC', 'P4_SYSTEMD_SERVER_METADATA', 'P4_SYSTEMD_SERVER_INODE', 'P4_SYSTEMD_OBSERVER_STARTED',
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
         'P4_SYSTEMD_SERVER_METADATA', 'P4_SYSTEMD_SERVER_INODE', 'P4_SYSTEMD_GUEST_FINAL'],
         'four actual NSFS observations bracket original systemd exec')
    validate_fixed_nsfs_records(nsfs_rows)
    need(cold_order == ['P4_SYSTEMD_BEFORE_EXEC', 'P4_SYSTEMD_OBSERVER_STARTED', 'P4_SYSTEMD_SERVER_METADATA',
         'P4_SYSTEMD_SERVER_INODE', 'P4_SYSTEMD_GUEST_FINAL'],
         'one complete actual original-systemd cold lifecycle; partial boot is not success')
    before = rows['P4_SYSTEMD_BEFORE_EXEC'][0]; started = rows['P4_SYSTEMD_OBSERVER_STARTED'][0]
    inode = rows['P4_SYSTEMD_SERVER_INODE'][0]; final = rows['P4_SYSTEMD_GUEST_FINAL'][0]
    metadata = rows['P4_SYSTEMD_SERVER_METADATA'][0]
    validate_original_server_metadata(metadata)
    need(metadata['node'] == inode['node'], 'same recorded original socket node before validation and peer authentication')
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
