"""Own one dedicated production build mount and retire its original actors."""
import hashlib, json, pathlib, sys

C = pathlib.Path(__file__).parent
accepted = globals().get('_accepted', sys.argv[1] if len(sys.argv) == 3 else '')
admission_sha = globals().get('_admission_sha', sys.argv[2] if len(sys.argv) == 3 else '')
raw_manifest = (C / 'SOURCE-MANIFEST.json').read_bytes()
assert hashlib.sha256(raw_manifest).hexdigest() == accepted
manifest = json.loads(raw_manifest); common = (C / 'common.py').read_bytes()
assert hashlib.sha256(common).hexdigest() == manifest['files']['common.py']['sha256']
exec(compile(common, str(C / 'common.py'), 'exec'))
support = (C / 'storage_support.py').read_bytes()
assert hashlib.sha256(support).hexdigest() == manifest['files']['storage_support.py']['sha256']
exec(compile(support, str(C / 'storage_support.py'), 'exec'))
rotation = (C / 'rotation_support.py').read_bytes()
assert hashlib.sha256(rotation).hexdigest() == manifest['files']['rotation_support.py']['sha256']
exec(compile(rotation, str(C / 'rotation_support.py'), 'exec'))

contract = json.loads((C / 'contract.json').read_bytes())
admission_ref, admission = storage_admission(C, accepted, admission_sha, contract)
Q = P(contract['desktop_root']); DEVICE = P('/dev/nbd0'); SYS = P('/sys/class/block/nbd0')
MOUNT = P(contract['mount_target']); TUNNEL = Q / 'ipc/tunnel.sock'; RELAY = Q / 'ipc/client.sock'
SSH = ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'ConnectTimeout=8', '-o', 'ConnectionAttempts=1', '-o', 'ControlMaster=no',
       '-o', 'ControlPath=none', '-o', 'ControlPersist=no']
STOP = False

def requested_stop(signum, frame):
    global STOP
    STOP = True

def assert_original_nbd_state():
    need(not P('/sys/module/nbd').exists() and not list(P('/sys/class/block').glob('nbd*')) and
         not list(P('/dev').glob('nbd[0-9]*')), 'original unloaded module and zero devices')

def mount_entries():
    rows = []; namespaces = set(); count = 0
    for process in P('/proc').iterdir():
        if not process.name.isdigit(): continue
        try:
            namespace = (process / 'ns/mnt').stat().st_ino
            if namespace in namespaces: continue
            content = (process / 'mountinfo').read_text(); namespaces.add(namespace); count += 1
            for line in content.splitlines():
                fields = line.split()
                if fields[2] == '43:0': rows.append({'pid': int(process.name), 'namespace': namespace, 'line': line})
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.ESRCH): raise
    return {'mounts': rows, 'namespaces_read': count}

def device_identity():
    s = DEVICE.lstat()
    need(stat.S_ISBLK(s.st_mode) and os.major(s.st_rdev) == 43 and os.minor(s.st_rdev) == 0,
         'only newly created nbd0 block device')
    need((SYS / 'dev').read_text().strip() == '43:0', 'kernel device identity')
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_rdev]

def device_owner(client, original_device, expected=None, require_full_size=True):
    client.verify_live()
    need(device_identity() == original_device and not list((SYS / 'holders').iterdir()), 'exact holder-free original device')
    if require_full_size: need((SYS / 'size').read_text().strip() == str(contract['image_sectors']), 'full sized original device')
    pid = int((SYS / 'pid').read_text().strip())
    process = P('/proc') / str(pid); status = process.joinpath('status').read_text()
    tgid = int(next(line.split()[1] for line in status.splitlines() if line.startswith('Tgid:')))
    need(tgid == client.held.pid and process.joinpath('cgroup').read_text().strip() == '0::' + client.state['ControlGroup'],
         'kernel NBD owner is a thread of the held original qemu process')
    owner = {'pid': pid, 'Tgid': tgid, 'start_ticks': birth(pid), 'device_identity': original_device,
             'native_InvocationID': client.ref['InvocationID'], 'main_start_ticks': client.held.start}
    if expected is not None: need(owner == expected, 'same exact NBD connection owner')
    return owner

def ordinary_props(memory, seconds):
    return ['MemoryMax=' + str(memory), 'MemorySwapMax=0', 'TasksMax=64', 'CPUQuota=200%',
            'CPUAffinity=6 7', 'AllowedCPUs=6 7', 'RuntimeMaxSec=' + str(seconds), 'TimeoutStopSec=1200',
            'OOMPolicy=stop', 'Nice=15', 'NoNewPrivileges=yes']

def own_mount():
    rows = []
    for line in P('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split()
        if fields[4] == str(MOUNT):
            need(fields[2] == '43:0' and ' - ext4 /dev/nbd0 ' in line, 'only original fixed new filesystem mounted at trial target')
            rows.append(line)
    need(len(rows) <= 1, 'one owned private mount')
    return rows

def retire_transport(commands, result, client, ssh, owned_device, owner):
    need(not mount_entries()['mounts'], 'no remaining mount before transport retirement')
    need(client is not None or not (SYS / 'pid').exists(), 'no unowned kernel connection before tunnel retirement')
    if client is not None:
        if client.ref is None:
            try: client.reconcile()
            except BaseException as error:
                state = show(commands, client.unit)
                if client.ref is None and state.get('LoadState') == 'not-found' and not (P('/sys/fs/cgroup/system.slice') / client.unit).exists() and not (SYS / 'pid').exists():
                    result['client_never_observed'] = {'state': state, 'error': repr(error), 'no_kernel_connection': True}; client = None
                elif client.ref is not None: result['errors'].append('recovered client control error: ' + repr(error))
                else: raise
    if client is not None:
        if (SYS / 'pid').exists():
            need(client.held is not None and client.held.live(), 'held original client required for partial connection')
            current = device_owner(client, owned_device, owner, require_full_size=False)
            result['retirement_connection_owner'] = current
            if (SYS / 'size').read_text().strip() == str(contract['image_sectors']):
                try: commands.run('flush-owned-detached-filesystem', ['/usr/sbin/blockdev', '--flushbufs', str(DEVICE)], 20)
                except BaseException as error: result['errors'].append('flush: ' + repr(error))
            device_owner(client, owned_device, current, require_full_size=False)
            try: commands.run('disconnect-only-original-nbd-owner', ['/usr/bin/qemu-nbd', '--disconnect', str(DEVICE)], 20)
            except BaseException as error: result['errors'].append('disconnect acknowledgement: ' + repr(error))
            deadline = time.monotonic() + 10
            while (SYS / 'pid').exists() and time.monotonic() < deadline: time.sleep(0.05)
            need(not (SYS / 'pid').exists(), 'original connection actually detached before retiring transport')
            result['client_retirement'] = client.retire(False, expected_exit=0)
        else:
            need(not SYS.exists() or (SYS / 'size').read_text().strip() == '0', 'partial client has no kernel connection')
            result['client_retirement'] = client.retire(True)
        if not result['client_retirement']['expected_exit_matches']: result['errors'].append('actual client normal exit mismatch')
        need((not SYS.exists() or (SYS / 'size').read_text().strip() == '0') and not (SYS / 'pid').exists(), 'kernel connection detached')
    if ssh is not None:
        if ssh.ref is None:
            try: ssh.reconcile()
            except BaseException as error:
                state = show(commands, ssh.unit)
                if ssh.ref is None and state.get('LoadState') == 'not-found' and not (P('/sys/fs/cgroup/system.slice') / ssh.unit).exists():
                    result['ssh_never_observed'] = {'state': state, 'error': repr(error)}; ssh = None
                elif ssh.ref is not None: result['errors'].append('recovered SSH control error: ' + repr(error))
                else: raise
        if ssh is not None: result['ssh_retirement'] = ssh.retire(True)

def recover_detached_resources(commands, old):
    """Recovery after the original controller is terminal; never remount/restart."""
    need(old['nonce'] == contract['nonce'] and old['source_manifest_sha256'] == accepted and old['admission_sha256'] == admission_sha and
         old['native']['boot'] == contract['hosts']['desktop']['boot'], 'same failed original cohort')
    need(not P(old['native']['cgroup']).exists() and not mount_entries()['mounts'],
         'old controller and all mounts gone before independent recovery')
    proof = {'errors': [], 'original_result_preserved': True, 'new_starts': 0,
             'external_recovery_consumers': external_consumers_retired(commands, contract)}
    loaded_by_us = any(row['name'] == 'load-exact-installed-nbd-module' and row.get('exit_code') == 0 for row in old['commands'])
    identity = old.get('new_device_identity')
    if P('/sys/module/nbd').exists():
        need(loaded_by_us and sorted(p.name for p in P('/sys/class/block').glob('nbd*')) == ['nbd0'] and
             ((identity is not None and device_identity() == identity) or
              (identity is None and not (SYS / 'pid').exists() and (SYS / 'size').read_text().strip() == '0' and not list((SYS / 'holders').iterdir()))),
             'exact original successful module load and original device identity')
    actors = {}
    for role in ('client', 'ssh'):
        state = show(commands, contract[role + '_unit'])
        if state.get('LoadState') == 'not-found':
            need(not (P('/sys/fs/cgroup/system.slice') / contract[role + '_unit']).exists(), 'absent old actor cgroup')
            actors[role] = None
        else:
            actors[role] = OwnedUnit.recover(commands, Q / 'commands', contract[role + '_unit'])
    retire_transport(commands, proof, actors['client'], actors['ssh'], identity, None)
    if P('/sys/module/nbd').exists():
        need(not (SYS / 'pid').exists() and (SYS / 'size').read_text().strip() == '0' and
             not list((SYS / 'holders').iterdir()) and not mount_entries()['mounts'], 'only detached original module remains')
        commands.run('recover-original-module-retirement', [contract['hosts']['desktop']['tools']['rmmod']['path'], 'nbd'], 20)
        deadline = time.monotonic() + 10
        while P('/sys/module/nbd').exists() or list(P('/sys/class/block').glob('nbd*')) or list(P('/dev').glob('nbd[0-9]*')):
            need(time.monotonic() < deadline, 'original module device removal completes'); time.sleep(0.05)
    assert_original_nbd_state()
    proof['retained_unverified_socket_paths'] = []
    for path, key in ((TUNNEL, 'tunnel_socket_f9'), (RELAY, 'relay_socket_f9')):
        if key in old: proof[key] = remove_retired_socket(path, old[key])
        elif os.path.lexists(path):
            need(not any(line.endswith(' ' + str(path)) for line in P('/proc/net/unix').read_text().splitlines()), 'no live socket at unverified artifact path')
            proof['retained_unverified_socket_paths'].append(str(path))
    need(hashlib.sha256(P('/proc/1/mountinfo').read_bytes()).hexdigest() == old['host_global_mounts_sha256'], 'independent unchanged global mount view')
    proof['original_module_device_mount_state_restored'] = True
    return proof

def main():
    need(str(C) == contract['desktop_source'] and os.getresuid() == os.getresgid() == (0, 0, 0), 'fixed root controller')
    _, sources = sealed_sources(C, accepted)
    boot_is(contract['hosts']['desktop']['boot']); tools = check_tools(contract, 'desktop')
    pin(contract['hosts']['desktop']['module']['path'], contract['hosts']['desktop']['module'])
    need(mem_available() >= contract['desktop_fresh_memory_minimum'] and
         free_space(Q.parent) >= contract['desktop_local_disk_minimum'], 'fresh composite 28 GiB RAM and local evidence space')
    assert_original_nbd_state()
    own_ns = P('/proc/self/ns/mnt').stat().st_ino; host_ns = P('/proc/1/ns/mnt').stat().st_ino
    need(own_ns != host_ns, 'native controller starts in its private mount namespace')
    host_mounts = P('/proc/1/mountinfo').read_bytes()
    Q.mkdir(mode=0o700)
    rootfd = os.open(Q, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(rootfd)
        need(stat.S_ISDIR(before.st_mode) and before.st_uid == before.st_gid == 0 and
             f9(before) == f9(Q.lstat()), 'one new root-owned trial directory')
        os.fchmod(rootfd, 0o711); os.fsync(rootfd)
        after = os.fstat(rootfd)
        need((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino) and
             after.st_uid == after.st_gid == 0 and stat.S_IMODE(after.st_mode) == 0o711 and
             f9(after) == f9(Q.lstat()), 'same root-owned directory permits private IPC traversal')
    finally:
        os.close(rootfd)
    (Q / 'commands').mkdir(mode=0o700)
    (Q / 'ipc').mkdir(mode=0o700); os.chown(Q / 'ipc', 1000, 1000)
    commands = Commands(Q / 'commands')
    lock = os.open(Q / 'owner.lock', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    result = {'schema': 'p4-production651-nbd-desktop-result-v1', 'nonce': contract['nonce'],
              'source_manifest_sha256': accepted, 'passed': False, 'errors': [],
              'admission_sha256': admission_sha,
              'H_job_id': None, 'Android_starts': 0, 'full_build_started': False, 'production_ready': False}
    ssh = None; client = None; loaded = False; mounted = False; writer = None; workfd = None
    owned_device = None; owner = None; client_disconnected = False; client_launch_attempted = False
    module_attempted = False; mount_attempted = False
    signal.signal(signal.SIGTERM, requested_stop); signal.signal(signal.SIGINT, requested_stop)
    started = time.monotonic()
    try:
        result['native'] = native_identity(commands, contract['controller_unit'], contract['controller_description'], 0)
        result['actual_lifetime'] = verify_storage_unit(commands, contract, 'controller', result['native']['InvocationID'])
        result['new_empty_mountpoint'] = original_empty_mountpoint(contract, admission)
        (Q / 'actor-intents').mkdir(mode=0o700)
        entry_directory = Q / 'actor-entries'
        entry_directory.mkdir(mode=0o711)
        entry_fd = os.open(entry_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            old_entry = os.fstat(entry_fd)
            need(old_entry.st_uid == old_entry.st_gid == 0 and
                 f9(old_entry) == f9(entry_directory.lstat()), 'only the newly created root entry directory')
            os.fchmod(entry_fd, 0o711); os.fsync(entry_fd)
            new_entry = os.fstat(entry_fd)
            need((new_entry.st_dev, new_entry.st_ino) == (old_entry.st_dev, old_entry.st_ino) and
                 new_entry.st_uid == new_entry.st_gid == 0 and stat.S_IMODE(new_entry.st_mode) == 0o711 and
                 f9(new_entry) == f9(entry_directory.lstat()), 'new public proof traversal after UID drop')
        finally:
            os.close(entry_fd)
        result['mount_namespaces'] = {'own': own_ns, 'host': host_ns}
        result['host_global_mounts_sha256'] = hashlib.sha256(host_mounts).hexdigest()
        save(Q / 'HOST-MOUNTS-BEFORE.json', {'nonce': contract['nonce'], 'native': result['native'],
             'source_manifest_sha256': accepted, 'admission_sha256': admission_sha,
             'sha256': result['host_global_mounts_sha256']}, 0o444)
        config = commands.run('inspect-existing-ssh-config', ['/usr/bin/ssh', '-G', 'pocket4'], 20, uid=1000)
        settings = output(config).splitlines()
        need(hashlib.sha256(output(config).encode()).hexdigest() == contract['hosts']['desktop']['resolved_ssh_whole_sha256'],
             'same previously inspected SSH alias configuration')
        need(not any(line.startswith(('localforward ', 'remoteforward ', 'dynamicforward ')) for line in settings),
             'existing alias has no extra forwarding')
        remote_boot = commands.run('existing-trusted-peer-boot', SSH + ['pocket4', '/usr/bin/cat', '/proc/sys/kernel/random/boot_id'], 25, uid=1000)
        need(output(remote_boot).strip() == contract['hosts']['pocket4']['boot'], 'actual trusted peer boot')
        ready_row = commands.run('read-original-server-ready', SSH + ['pocket4', '/usr/bin/cat', contract['p4_root'] + '/SERVER-READY.json'], 25, uid=1000)
        ready = json.loads(output(ready_row))
        need(ready['nonce'] == contract['nonce'] and ready['source_manifest_sha256'] == accepted and ready['admission_sha256'] == admission_sha and
             ready['image_bytes'] == contract['image_bytes'] and ready['image_uuid'] == contract['image_uuid'] and
             ready['native']['boot'] == contract['hosts']['pocket4']['boot'], 'same fixed owned server export')
        need(ready['allocated_image'] == admission['allocated_image'] and
             0 <= time.time_ns() - ready['created_ns'] <= contract['initial_ready_fresh_seconds'] * 10**9,
             'fresh preserved-volume server export bound to complete offline verification')
        result['remote_server_ready'] = ready
        tunnel_argv = SSH + ['-N', '-o', 'ExitOnForwardFailure=yes', '-o', 'StreamLocalBindUnlink=no',
            '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=3',
            '-L', str(TUNNEL) + ':' + contract['p4_root'] + '/ipc/export.sock', 'pocket4']
        ssh = OwnedUnit(commands, contract['ssh_unit'], contract['ssh_description'], 1000, tunnel_argv,
                        Q / 'commands', ordinary_props(256 * 1024 ** 2, contract['storage_runtime_max_seconds']))
        ssh.launch()
        need(ssh.held is not None and ssh.held.live(), 'actual foreground SSH process')
        deadline = time.monotonic() + 15
        while not TUNNEL.exists():
            need(ssh.held.live() and not STOP and time.monotonic() < deadline, 'owned SSH creates its Unix listener')
            time.sleep(0.05)
        s = TUNNEL.lstat()
        need(stat.S_ISSOCK(s.st_mode) and s.st_uid == s.st_gid == 1000 and stat.S_IMODE(s.st_mode) & 0o077 == 0,
             'private SSH Unix socket')
        result['tunnel_socket_f9'] = f9(s)
        assert_original_nbd_state()
        module_attempted = True
        save(Q / 'MODULE-INTENT.json', {'nonce': contract['nonce'], 'original_loaded': False,
             'module': contract['hosts']['desktop']['module'], 'native': result['native']}, 0o444)
        commands.run('load-exact-installed-nbd-module', [contract['hosts']['desktop']['tools']['insmod']['path'],
             contract['hosts']['desktop']['module']['path'], 'nbds_max=1', 'max_part=0'], 20)
        loaded = True
        commands.run('settle-only-new-device-event', [contract['hosts']['desktop']['tools']['udevadm']['path'], 'settle', '--timeout=10'], 15)
        deadline = time.monotonic() + 10
        while not DEVICE.exists():
            need(time.monotonic() < deadline and not STOP, 'new single NBD node appears'); time.sleep(0.05)
        need(sorted(p.name for p in P('/sys/class/block').glob('nbd*')) == ['nbd0'], 'only new nbd0')
        need((SYS / 'size').read_text().strip() == '0' and not (SYS / 'pid').exists() and
             not list((SYS / 'holders').iterdir()) and not mount_entries()['mounts'], 'new unused nbd0')
        owned_device = device_identity()
        result['new_device_identity'] = owned_device
        save(Q / 'DEVICE-BEFORE-ATTACH.json', {'nonce': contract['nonce'], 'identity': owned_device,
             'native': result['native'], 'size_sectors': 0, 'pid_absent': True}, 0o444)
        client_argv = ['/usr/bin/qemu-nbd', '--verbose', '--connect=/dev/nbd0', '--socket=' + str(RELAY),
             '--cache=writeback', '--discard=ignore', '--detect-zeroes=off', '--image-opts',
             'driver=nbd,server.type=unix,server.path=' + str(TUNNEL) + ',export=' + contract['export_name']]
        client_launch_attempted = True
        client = OwnedUnit(commands, contract['client_unit'], contract['client_description'], 0, client_argv,
             Q / 'commands', ordinary_props(256 * 1024 ** 2, contract['storage_runtime_max_seconds']) + ['RestrictAddressFamilies=AF_UNIX'])
        client.launch()
        need(client.held is not None and client.held.live(), 'actual foreground qemu process')
        deadline = time.monotonic() + 20
        while not (SYS / 'pid').exists() or (SYS / 'size').read_text().strip() != str(contract['image_sectors']):
            need(client.held.live() and ssh.held.live() and not STOP and time.monotonic() < deadline, 'finite original NBD attach')
            time.sleep(0.05)
        owner = device_owner(client, owned_device); result['connection_owner'] = owner
        relay = RELAY.lstat()
        need(stat.S_ISSOCK(relay.st_mode) and relay.st_uid == relay.st_gid == 0, 'owned client Unix relay socket')
        result['relay_socket_f9'] = f9(relay)
        uuid = commands.run('read-owned-filesystem-uuid', ['/usr/sbin/blkid', '-p', '-s', 'UUID', '-o', 'value', str(DEVICE)], 20)
        need(output(uuid).strip() == contract['image_uuid'], 'exact new ext4 filesystem UUID')
        commands.run('private-mount-propagation', ['/usr/bin/mount', '--make-rprivate', '/'], 20)
        result['new_empty_mountpoint_before_mount'] = original_empty_mountpoint(
            contract, admission, expected=result['new_empty_mountpoint'])
        mount_attempted = True
        before_mount = own_mount(); need(not before_mount, 'no original mount at new task target')
        save(Q / 'MOUNT-INTENT.json', {'nonce': contract['nonce'], 'namespace': own_ns, 'device_identity': owned_device,
             'connection_owner': owner, 'target': str(MOUNT), 'original_mounts': before_mount}, 0o444)
        commands.run('mount-only-owned-new-volume', ['/usr/bin/mount', '-t', 'ext4', '-o', 'rw,nodev,nosuid,noatime,nodiscard', str(DEVICE), str(MOUNT)], 30)
        mounted = True
        rows = mount_entries(); result['mounted_observation'] = rows
        need(rows['mounts'] and all(x['namespace'] == own_ns and (' ' + str(MOUNT) + ' ') in x['line'] for x in rows['mounts']),
             'only owned private namespace mounts this new device')
        result['preserved_volume_anchors'] = preserved_volume_anchors(contract, admission)
        result['new_volume_directories_created'] = 0
        result['rotation_inputs_sha256'] = admission['rotation_inputs']['sha256']
        need(free_space(MOUNT) >= contract['volume_prebuild_free_minimum'], 'new volume has original 248 GiB admission space')
        result['owner_ready'] = save(Q / 'OWNER-READY.json', {
            'schema': 'p4-production651-owned-storage-ready-v1', 'nonce': contract['nonce'],
            'source_manifest_sha256': accepted, 'admission_sha256': admission_sha,
            'native': result['native'], 'mount_namespace_inode': own_ns,
            'host_mount_namespace_inode': host_ns, 'mount_target': str(MOUNT),
            'mount_root_identity': f9(MOUNT.lstat()), 'mountinfo': own_mount(),
            'connection_owner': owner, 'ssh': ssh.ref, 'client': client.ref,
            'tunnel_socket_f9': result['tunnel_socket_f9'], 'relay_socket_f9': result['relay_socket_f9'],
            'image_uuid': contract['image_uuid'], 'image_bytes': contract['image_bytes'],
            'original_server_ready': ready, 'created_ns': time.time_ns(),
            'deadline_monotonic_ns': int((started + contract['storage_work_seconds']) * 10**9),
            'full_builds_started': 0, 'Android_starts': 0, 'production_ready': False}, 0o444)
        result['minimum_MemAvailable'] = mem_available()
        result['minimum_local_free'] = free_space(Q)
        result['minimum_volume_free'] = free_space(MOUNT)
        while not STOP:
            need(time.monotonic() - started < contract['storage_work_seconds'], 'finite original storage lease')
            need(client.held.live() and ssh.held.live(), 'original owned transport remains live')
            memory, local_free, volume_free = mem_available(), free_space(Q), free_space(MOUNT)
            result['minimum_MemAvailable'] = min(result['minimum_MemAvailable'], memory)
            result['minimum_local_free'] = min(result['minimum_local_free'], local_free)
            result['minimum_volume_free'] = min(result['minimum_volume_free'], volume_free)
            need(memory >= contract['desktop_live_memory_reserve'] and
                 local_free >= contract['desktop_local_disk_minimum'] and volume_free >= 32 * GIB,
                 'actual host 12 GiB RAM, local evidence and original 32 GiB shared volume reserves')
            time.sleep(0.5)
        result['stop_requested'] = True
    except BaseException as error:
        result['errors'].append(repr(error))
    finally:
        try:
            if (Q / 'OWNER-READY.json').exists():
                save(Q / 'STOPPING.json', {'nonce': contract['nonce'], 'native': result['native'],
                    'source_manifest_sha256': accepted, 'admission_sha256': admission_sha, 'observed_ns': time.time_ns()}, 0o444)
                result['mounted_role_retirements'] = retire_registered_roles(commands, Q, contract, accepted, admission_sha)
                result['external_recovery_consumers'] = external_consumers_retired(commands, contract)
                result['normal_source_recovery'] = recover_normal_projection(commands, Q, MOUNT, contract, accepted, admission_sha)
                result['selected_delivery'] = capture_selected_delivery(Q, MOUNT, contract, accepted, admission_sha)
            if workfd is not None: os.close(workfd); workfd = None
            observed_mount = own_mount()
            if observed_mount:
                need(mount_attempted and P('/proc/self/ns/mnt').stat().st_ino == own_ns, 'actual mount belongs to original private operation')
                device_owner(client, owned_device, owner)
                try: commands.run('normal-owned-unmount', ['/usr/bin/umount', str(MOUNT)], 45)
                except BaseException as error: result['errors'].append('unmount acknowledgement: ' + repr(error))
                need(not own_mount(), 'actual owned mount removed')
                mounted = False
            retire_transport(commands, result, client, ssh, owned_device, owner)
            if 'tunnel_socket_f9' in result:
                result['tunnel_socket_retirement'] = remove_retired_socket(TUNNEL, result['tunnel_socket_f9'])
            if 'relay_socket_f9' in result:
                result['relay_socket_retirement'] = remove_retired_socket(RELAY, result['relay_socket_f9'])
            loaded = loaded or any(row['name'] == 'load-exact-installed-nbd-module' and row.get('exit_code') == 0 for row in commands.records)
            if loaded:
                need(sorted(p.name for p in P('/sys/class/block').glob('nbd*')) == ['nbd0'] and
                     not (SYS / 'pid').exists() and (SYS / 'size').read_text().strip() == '0' and
                     not list((SYS / 'holders').iterdir()) and not mount_entries()['mounts'], 'no consumer before owned module removal')
                try: commands.run('unload-only-new-unused-nbd-module', [contract['hosts']['desktop']['tools']['rmmod']['path'], 'nbd'], 20)
                except BaseException as error: result['errors'].append('module unload acknowledgement: ' + repr(error))
                deadline = time.monotonic() + 10
                while P('/sys/module/nbd').exists() or list(P('/sys/class/block').glob('nbd*')) or list(P('/dev').glob('nbd[0-9]*')):
                    need(time.monotonic() < deadline, 'normal removal of newly created device nodes'); time.sleep(0.05)
            assert_original_nbd_state()
            need(P('/proc/1/mountinfo').read_bytes() == host_mounts, 'host global mount view unchanged')
            sources_unchanged(sources); check_tools(contract, 'desktop')
            pin(admission_ref['path'], admission_ref)
            pin(contract['hosts']['desktop']['module']['path'], contract['hosts']['desktop']['module'])
            boot_is(contract['hosts']['desktop']['boot'])
            result['original_module_device_mount_state_restored'] = True
        except BaseException as error:
            result['errors'].append('retirement: ' + repr(error))
        result['passed'] = bool(not result['errors'] and result.get('stop_requested') and
                                result.get('original_module_device_mount_state_restored'))
        result['passed_scope'] = 'storage_lifecycle_only'
        result['full_builds_started_by_owner'] = 0
        result['pipeline_build_success_not_inferred'] = True
        result['commands'] = commands.records
        result['elapsed_seconds'] = time.monotonic() - started
        save(Q / 'DESKTOP-RESULT.json', result, 0o444)
        fcntl.flock(lock, fcntl.LOCK_UN); os.close(lock)
    return 0 if result['passed'] else 1

if __name__ == '__main__': raise SystemExit(main())
