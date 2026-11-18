"""Export only the independently qualified original dedicated regular image."""
import hashlib, json, pathlib, sys
C = pathlib.Path(__file__).parent
assert len(sys.argv) == 3
accepted, admission_sha = sys.argv[1:]
raw = (C / 'SOURCE-MANIFEST.json').read_bytes(); assert hashlib.sha256(raw).hexdigest() == accepted
manifest = json.loads(raw)
for name in ('common.py', 'storage_support.py', 'rotation_support.py'):
    body = (C / name).read_bytes(); assert hashlib.sha256(body).hexdigest() == manifest['files'][name]['sha256']
    exec(compile(body, str(C / name), 'exec'))
contract = json.loads((C / 'contract.json').read_bytes())
admission_ref, admission = storage_admission(C, accepted, admission_sha, contract)
Q = P(contract['p4_root']); IMAGE = P(contract['image_path']); SOCKET = Q / 'ipc/export.sock'
STOP = []


def stopped(signum, frame):
    STOP.append(signum)


def main():
    need(str(C) == contract['p4_source'] and os.getresuid() == os.getresgid() == (1000, 1000, 1000),
         'fixed ordinary server generation')
    _, sources = sealed_sources(C, accepted)
    tools = check_tools(contract, 'pocket4'); boot_is(contract['hosts']['pocket4']['boot'])
    pin(admission['canonical']['path'], admission['canonical'])
    need(mem_available() >= contract['p4_fresh_memory_minimum'] and
         free_space(Q.parent) >= contract['p4_fresh_disk_minimum'], 'fresh P4 storage reserve')
    need(not os.path.lexists(Q) and Q.parent.resolve() == Q.parent, 'new server evidence directory')
    Q.mkdir(mode=0o700); (Q / 'commands').mkdir(mode=0o700); (Q / 'ipc').mkdir(mode=0o700)
    commands = Commands(Q / 'commands')
    result = {'schema': 'p4-production651-nbd-server-result-v1', 'nonce': contract['nonce'],
        'source_manifest_sha256': accepted, 'admission_sha256': admission_sha, 'H_job_id': None,
        'server_lifecycle_clean': False, 'errors': [], 'Android_starts': 0, 'full_build_started': False,
        'production_ready': False, 'commands': commands.records}
    child = image_fd = lock = None
    deadline = time.monotonic() + contract['storage_work_seconds']
    signal.signal(signal.SIGTERM, stopped); signal.signal(signal.SIGINT, stopped)
    try:
        result['native'] = native_identity(commands, contract['server_unit'], contract['server_description'], 1000)
        result['actual_lifetime'] = verify_storage_unit(commands, contract, 'server', result['native']['InvocationID'])
        result['preserved_image_lineage'] = rotation_image_input(commands, contract, admission)
        lock_ref, _ = pin(contract['allocation_lock_path'], admission['allocation_lock'])
        lock = os.open(contract['allocation_lock_path'], os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        need(f9(os.fstat(lock)) == lock_ref['identity'], 'original allocator owner lock inode')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        image_fd, result['image_before'] = physical_image(IMAGE, contract['image_bytes'], admission['allocated_image']['identity'])
        # Pass the original held regular-file FD. QEMU cannot select a replacement
        # by reopening a different pathname in the image directory.
        argv = [tools['qemu-nbd']['path'], '--persistent', '--shared=1', '--socket=' + str(SOCKET),
                '--export-name=' + contract['export_name'], '--format=raw', '--cache=writeback',
                '--aio=threads', '--discard=ignore', '--detect-zeroes=off', '/proc/self/fd/' + str(image_fd)]
        child = commands.start('owned-unix-server', argv, pass_fds=(image_fd,))
        wait_until = time.monotonic() + 15
        while not SOCKET.exists():
            need(child['held'].live() and not STOP and time.monotonic() < wait_until, 'original server socket readiness')
            time.sleep(0.05)
        sock = SOCKET.lstat()
        need(stat.S_ISSOCK(sock.st_mode) and sock.st_uid == sock.st_gid == 1000 and
             stat.S_IMODE(sock.st_mode) & 0o077 == 0, 'private original server Unix socket')
        actual = proc_ref(child['held'].pid)
        need(actual['cmdline'] == [a.encode() for a in argv] and actual['cgroup'] == P('/proc/self/cgroup').read_text(),
             'actual foreground qemu server and original cgroup')
        actual['cmdline'] = argv; result['server'] = actual
        result['ready'] = save(Q / 'SERVER-READY.json', {
            'schema': 'p4-production651-nbd-server-ready-v1', 'nonce': contract['nonce'],
            'source_manifest_sha256': accepted, 'admission_sha256': admission_sha,
            'native': result['native'], 'server': actual, 'socket_f9': f9(sock),
            'allocated_image': admission['allocated_image'], 'image': result['image_before'],
            'image_uuid': contract['image_uuid'], 'image_bytes': contract['image_bytes'],
            'export_name': contract['export_name'], 'created_ns': time.time_ns(),
            'source_imports': 0, 'Android_starts': 0, 'production_ready': False}, 0o444)
        result['minimum_MemAvailable'] = mem_available(); result['minimum_disk_free'] = free_space(Q)
        while not STOP:
            need(time.monotonic() < deadline and child['held'].live(), 'finite original live storage export')
            memory, disk = mem_available(), free_space(Q)
            result['minimum_MemAvailable'] = min(result['minimum_MemAvailable'], memory)
            result['minimum_disk_free'] = min(result['minimum_disk_free'], disk)
            need(memory >= contract['p4_live_memory_reserve'] and disk >= contract['p4_live_disk_reserve'],
                 'Pocket4 live 5 GiB RAM and 256 GiB disk reserves')
            time.sleep(0.5)
        result['stop_requested'] = True
    except BaseException as error:
        result['errors'].append(repr(error))
    finally:
        if child is not None:
            try: result['server_retirement'] = commands.finish(child, 60, stop=True)
            except BaseException as error: result['errors'].append('server retirement: ' + repr(error))
        try:
            if image_fd is not None:
                os.fsync(image_fd); after = os.fstat(image_fd)
                need(stat.S_ISREG(after.st_mode) and after.st_nlink == 1 and after.st_size == contract['image_bytes'] and
                     after.st_blocks * 512 >= after.st_size and f9(after) == f9(IMAGE.lstat()) and
                     (after.st_dev, after.st_ino) == tuple(result['image_before']['identity'][:2]),
                     'same physically allocated original image after writer retirement')
                result['image_after'] = {'path': str(IMAGE), 'identity': f9(after), 'allocated_bytes': after.st_blocks * 512}
            sources_unchanged(sources); check_tools(contract, 'pocket4'); pin(admission_ref['path'], admission_ref)
            result['fixed_sources_tools_and_admission_unchanged'] = True
        except BaseException as error: result['errors'].append('final image/input observation: ' + repr(error))
        finally:
            if image_fd is not None: os.close(image_fd)
        result['signals'] = STOP
        result['server_lifecycle_clean'] = bool(result.get('stop_requested') and not result['errors'] and
            result.get('server_retirement', {}).get('PIDFD_HUP') is True)
        save(Q / 'SERVER-RESULT.json', result, 0o444)
        if lock is not None: os.close(lock)
    return 0 if result['server_lifecycle_clean'] else 1


if __name__ == '__main__': raise SystemExit(main())
