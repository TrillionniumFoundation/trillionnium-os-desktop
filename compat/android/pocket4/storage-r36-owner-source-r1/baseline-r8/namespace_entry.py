"""Enter only the original owned build mount, then execute one fixed ordinary role."""
import hashlib, json, pathlib, sys
C = pathlib.Path(__file__).parent
assert len(sys.argv) == 5
accepted, admission_sha, role, role_manifest_sha = sys.argv[1:]
raw = (C / 'SOURCE-MANIFEST.json').read_bytes(); assert hashlib.sha256(raw).hexdigest() == accepted
manifest = json.loads(raw)
for name in ('common.py', 'storage_support.py', 'rotation_support.py'):
    body = (C / name).read_bytes(); assert hashlib.sha256(body).hexdigest() == manifest['files'][name]['sha256']
    exec(compile(body, str(C / name), 'exec'))
import threading, types
contract = json.loads((C / 'contract.json').read_bytes())
admission_ref, admission = storage_admission(C, accepted, admission_sha, contract)
Q = P(contract['desktop_root']); MOUNT = P(contract['mount_target'])


def main():
    need(str(C) == contract['desktop_source'] and role in contract['role_units'] and
         os.getresuid() == os.getresgid() == (0, 0, 0), 'one exact initial root namespace-entry role')
    boot_is(contract['hosts']['desktop']['boot']); _, sources = sealed_sources(C, accepted)
    directory = Q / 'entry-commands'
    if not directory.exists(): directory.mkdir(mode=0o700)
    need(directory.resolve() == directory and directory.lstat().st_uid == 0, 'owned entry journal')
    own_commands = directory / role; own_commands.mkdir(mode=0o700)
    commands = Commands(own_commands)
    intent_ref, intent = root_record(Q / 'actor-intents' / (role + '.json'))
    validate_role_intent(contract, accepted, admission_sha, role, intent)
    need(intent['role_manifest_sha256'] == role_manifest_sha and
         P('/proc/self/cmdline').read_bytes().split(b'\0')[:-1] == [x.encode() for x in intent['argv']],
         'actual fixed entry command and separate reviewed role manifest')
    unit = show(commands, contract['role_units'][role])
    need(unit['Description'] == intent['description'] and unit['MainPID'] == str(os.getpid()) and
         unit['User'] == unit['Group'] == '0' and
         P('/proc/self/cgroup').read_text().strip() == '0::' + unit['ControlGroup'] and
         int(unit['ExecMainStartTimestampMonotonic']) * 1000 >= intent['created_monotonic_ns'],
         'actual system-manager root entry identity')
    ready_ref, ready = root_record(Q / 'OWNER-READY.json')
    need(ready['schema'] == 'p4-production651-owned-storage-ready-v1' and ready['nonce'] == contract['nonce'] and
         ready['source_manifest_sha256'] == accepted and ready['admission_sha256'] == admission_sha and
         ready['native']['boot'] == contract['hosts']['desktop']['boot'] and
         ready['mount_target'] == str(MOUNT) and ready['image_uuid'] == contract['image_uuid'] and
         ready['image_bytes'] == contract['image_bytes'] and not (Q / 'STOPPING.json').exists(),
         'exact live original private volume readiness')
    need(time.monotonic_ns() < ready['deadline_monotonic_ns'] - (3600 * 10**9),
         'storage lease retains a cleanup margin before another role begins')
    role_root = P(contract['import_source_dir'] if role == 'source_import' else contract['full_source_dir'])
    role_ref, selected = root_record(role_root / 'ROLE-SOURCE-MANIFEST.json')
    need(role_ref['sha256'] == role_manifest_sha and selected['schema'] == 'p4-production651-role-source-v1' and
         selected['storage_source_manifest_sha256'] == accepted and selected['storage_admission_sha256'] == admission_sha,
         'separately sealed exact role-source closure')
    script_names = {'source_import': 'import_source.py', 'vendor_outer': 'full_outer_vendor.py',
        'vendor_inner': 'full_controller_vendor.py', 'wm_outer': 'full_outer_wm.py', 'wm_inner': 'full_controller_wm.py'}
    script_ref = selected['roles'][role]['source_script']
    need(script_ref['path'] == str(role_root / script_names[role]), 'one finite role script')
    script_actual, script_raw = pin(script_ref['path'], script_ref)
    selected_sources = [pin(ref['path'], ref)[0] for ref in selected['sources'].values()]
    need(script_actual in selected_sources, 'selected script is in the complete reviewed role closure')
    held = []; namespace_fd = receipt_fd = volume_fd = original_cwd = None
    done = threading.Event(); watcher = None
    try:
        for key in ('native', 'client', 'ssh'):
            source = ready[key]
            process = HeldProcess(source['pid']); held.append(process)
            need(process.start == source['start_ticks'] and process.live(), 'original storage/transport process generation')
            state = show(commands, source['unit'])
            need(state['InvocationID'] == source['InvocationID'] and state['MainPID'] == str(process.pid) and
                 proc_ref(process.pid)['cgroup'].strip() == '0::' + state['ControlGroup'],
                 'original storage/transport manager identity')
        owner = held[0]
        need(ready['native']['unit'] == contract['controller_unit'] and
             ready['client']['unit'] == contract['client_unit'] and ready['ssh']['unit'] == contract['ssh_unit'],
             'fixed owner, client and SSH units')
        namespace_fd = os.open('ns/mnt', os.O_RDONLY | os.O_CLOEXEC, dir_fd=owner.procfd)
        before_ns = P('/proc/self/ns/mnt').stat().st_ino
        need(os.fstat(namespace_fd).st_ino == ready['mount_namespace_inode'] and
             ready['mount_namespace_inode'] != ready['host_mount_namespace_inode'] == P('/proc/1/ns/mnt').stat().st_ino,
             'held original private mount namespace differs from global host')
        library = ctypes.CDLL(None, use_errno=True)
        need(library.setns(namespace_fd, 0x00020000) == 0, 'entered only held original mount namespace')
        need(P('/proc/self/ns/mnt').stat().st_ino == ready['mount_namespace_inode'] and owner.live() and
             MOUNT.lstat().st_dev == os.makedev(43, 0) and
             f9(MOUNT.lstat())[:2] == ready['mount_root_identity'][:2], 'actual selected private filesystem root')
        lines = [line for line in P('/proc/self/mountinfo').read_text().splitlines() if line.split()[4] == str(MOUNT)]
        need(len(lines) == 1 and lines[0].split()[2] == '43:0' and ' - ext4 /dev/nbd0 ' in lines[0],
             'actual original ext4 mount in entered namespace')
        uuid = commands.run('selected-volume-uuid', ['/usr/sbin/blkid', '-p', '-s', 'UUID', '-o', 'value', '/dev/nbd0'], 20)
        need(output(uuid).strip() == contract['image_uuid'], 'actual fixed filesystem UUID')
        fresh_memory = 28 * GIB if role in ('source_import', 'vendor_outer', 'wm_outer') else 24 * GIB
        need(mem_available() >= fresh_memory and free_space(MOUNT) >= contract['volume_prebuild_free_minimum'],
             'unchanged real full resource thresholds on the mounted filesystem')
        if role != 'source_import':
            need(time.monotonic_ns() + (contract['storage_stop_seconds'] + 28800) * 10**9 < ready['deadline_monotonic_ns'],
                 'a full eight-hour generation fits before storage cleanup margin')
        original_cwd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        volume_fd = os.open(MOUNT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        need(f9(os.fstat(volume_fd)) == f9(MOUNT.lstat()), 'same held volume root for complete role lifetime')
        os.fchdir(volume_fd)
        receipt_path = Q / 'actor-entries' / (role + '.json')
        receipt_fd = os.open(receipt_path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o444)
        os.fchmod(receipt_fd, 0o444)
        os.setgroups([]); os.setresgid(1000, 1000, 1000); os.setresuid(1000, 1000, 1000)
        role_umask = 0o077 if role == 'source_import' else 0o022
        os.umask(role_umask)
        status = P('/proc/self/status').read_text()
        values = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
        need(os.getresuid() == os.getresgid() == (1000, 1000, 1000) and os.getgroups() == [] and
             all(int(values[name].strip(), 16) == 0 for name in ('CapInh', 'CapPrm', 'CapEff', 'CapAmb')),
             'all role code runs as ordinary UID/GID 1000 with zero active capability sets')
        proof = {'schema': 'p4-production651-owned-namespace-entry-v1', 'role': role,
            'nonce': contract['nonce'], 'source_manifest_sha256': accepted, 'admission_sha256': admission_sha,
            'role_manifest': role_ref, 'role_script': script_actual, 'intent': intent_ref, 'owner_ready': ready_ref,
            'unit': unit, 'pid': os.getpid(), 'start_ticks': birth(os.getpid()),
            'manager_entry_uid': 0, 'actual_role_uid': 1000, 'actual_role_gid': 1000,
            'actual_supplementary_groups': [], 'actual_capabilities_zero': True,
            'actual_role_umask': role_umask,
            'namespace_before': before_ns, 'namespace_entered': ready['mount_namespace_inode'],
            'volume_root': f9(MOUNT.lstat()), 'volume_uuid': contract['image_uuid'],
            'storage_actor_generations': [{'pid': x.pid, 'start_ticks': x.start} for x in held],
            'H_job_id': None, 'Android_starts': 0, 'production_ready': False}
        body = (json.dumps(proof, sort_keys=True, indent=2) + '\n').encode()
        view = memoryview(body)
        while view:
            count = os.write(receipt_fd, view); need(count > 0, 'finite entry receipt write'); view = view[count:]
        os.fsync(receipt_fd)
        receipt_state = os.fstat(receipt_fd)
        need(stat.S_ISREG(receipt_state.st_mode) and receipt_state.st_uid == receipt_state.st_gid == 0 and
             receipt_state.st_nlink == 1 and stat.S_IMODE(receipt_state.st_mode) == 0o444 and
             receipt_state.st_size == len(body), 'original held root entry receipt after ordinary write')
        os.lseek(receipt_fd, 0, os.SEEK_SET)
        receipt_readback = bytearray()
        while len(receipt_readback) < len(body):
            block = os.read(receipt_fd, len(body) - len(receipt_readback))
            need(block, 'complete held entry receipt readback'); receipt_readback.extend(block)
        need(bytes(receipt_readback) == body and f9(os.fstat(receipt_fd)) == f9(receipt_state),
             'same held receipt full bytes and F9 after irreversible UID drop')
        proof_ref = {'path': str(receipt_path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                     'identity': f9(receipt_state)}
        os.close(receipt_fd); receipt_fd = None
        def check():
            need(all(p.live() for p in held) and not (Q / 'STOPPING.json').exists() and
                 time.monotonic_ns() < ready['deadline_monotonic_ns'] and
                 P('/proc/self/ns/mnt').stat().st_ino == ready['mount_namespace_inode'],
                 'original owned storage lifetime and namespace remain valid')
        def watch():
            while not done.wait(0.5):
                try: check()
                except BaseException:
                    os.kill(os.getpid(), signal.SIGTERM); return
        bound = types.ModuleType('p4_storage_entry')
        bound.proof = proof; bound.proof_reference = proof_ref; bound.check = check
        bound.selected_role_manifest = selected; bound.intent = intent; bound.owner_ready = ready
        sys.modules['p4_storage_entry'] = bound
        sources_unchanged(sources)
        for reference in selected_sources: pin(reference['path'], reference)
        check()
        # Keep the entry's actual manager PID/cmdline; only the reviewed fixed
        # Python role executes in-process after the irreversible UID drop.
        os.environ.update({'HOME': '/home/qian-qi', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin',
                           'LANG': 'C.UTF-8', 'XDG_RUNTIME_DIR': '/run/user/1000',
                           'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'})
        watcher = threading.Thread(target=watch, name='owned-storage-lifetime', daemon=True); watcher.start()
        scope = {'__name__': '__main__', '__file__': script_actual['path'], '__package__': None}
        exec(compile(script_raw, script_actual['path'], 'exec'), scope)
    finally:
        done.set()
        if watcher is not None: watcher.join(timeout=1)
        if receipt_fd is not None: os.close(receipt_fd)
        if original_cwd is not None: os.fchdir(original_cwd); os.close(original_cwd)
        if volume_fd is not None: os.close(volume_fd)
        if namespace_fd is not None: os.close(namespace_fd)
        for process in held: process.close()


if __name__ == '__main__': main()
