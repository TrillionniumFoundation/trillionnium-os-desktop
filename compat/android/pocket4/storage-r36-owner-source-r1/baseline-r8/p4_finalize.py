"""Read-only offline ext4 check and exact persisted selected-output readback."""
import hashlib, json, pathlib, sys
C = pathlib.Path(__file__).parent
assert len(sys.argv) == 5
accepted, admission_sha, desktop_retirement_sha, server_retirement_sha = sys.argv[1:]
raw = (C / 'SOURCE-MANIFEST.json').read_bytes(); assert hashlib.sha256(raw).hexdigest() == accepted
manifest = json.loads(raw)
for name in ('common.py', 'storage_support.py', 'rotation_support.py'):
    body = (C / name).read_bytes(); assert hashlib.sha256(body).hexdigest() == manifest['files'][name]['sha256']
    exec(compile(body, str(C / name), 'exec'))
contract = json.loads((C / 'contract.json').read_bytes())
admission_ref, admission = storage_admission(C, accepted, admission_sha, contract)
Q = P(contract['p4_root']); IMAGE = P(contract['image_path']); STOP = []


def stopped(signum, frame): STOP.append(signum)


def main():
    need(str(C) == contract['p4_source'] and os.getresuid() == os.getresgid() == (1000, 1000, 1000),
         'fixed ordinary offline finalizer')
    boot_is(contract['hosts']['pocket4']['boot']); _, sources = sealed_sources(C, accepted)
    tools = check_tools(contract, 'pocket4')
    need(mem_available() >= contract['p4_fresh_memory_minimum'] and
         free_space(Q) >= contract['p4_fresh_disk_minimum'], 'fresh readback and selected-output reserve')
    desktop_ref, body = pin(Q / 'DESKTOP-INDEPENDENT-RETIREMENT.json'); desktop = json.loads(body)
    server_ref, body = pin(C / 'server-INDEPENDENT-RETIREMENT.json'); server = json.loads(body)
    need(desktop_ref['sha256'] == desktop_retirement_sha and server_ref['sha256'] == server_retirement_sha,
         'exact independent desktop and server retirements')
    for value, role in ((desktop, 'controller'), (server, 'server')):
        need(value['role'] == role and value['nonce'] == contract['nonce'] and value['retirement_passed'] is True and
             value['source_manifest_sha256'] == accepted and value['admission_sha256'] == admission_sha,
             'actual independently retired original storage cohort')
    need(desktop['original_module_device_mount_state_restored'] is True and server['cgroup_absent'] is True,
         'zero original transport writers before offline check')
    offline = server['offline_original_image']
    need(offline['image']['path'] == str(IMAGE) and not offline['image_writers'] and not offline['unavailable'],
         'actual independently observed offline original image')
    local_server_ref = None
    if server['result'] is not None:
        local_server_ref, body = pin(Q / 'SERVER-RESULT.json'); local_server = json.loads(body)
        need(local_server_ref == server['result'] and local_server['nonce'] == contract['nonce'], 'original server terminal receipt')
    directory = Q / 'finalize'; directory.mkdir(mode=0o700)
    (directory / 'exports').mkdir(mode=0o700); (directory / 'commands').mkdir(mode=0o700)
    commands = Commands(directory / 'commands')
    result = {'schema': 'p4-production651-nbd-offline-filesystem-result-v1', 'nonce': contract['nonce'],
        'source_manifest_sha256': accepted, 'admission_sha256': admission_sha, 'passed': False, 'errors': [],
        'desktop_retirement': desktop_ref, 'server_retirement': server_ref,
        'Android_starts': 0, 'production_ready': False, 'commands': commands.records, 'exported_files': []}
    fd = None; deadline = time.monotonic() + contract['finalize_work_seconds']; last_progress = 0.0
    signal.signal(signal.SIGTERM, stopped); signal.signal(signal.SIGINT, stopped)

    def checkpoint():
        nonlocal last_progress
        need(not STOP and time.monotonic() < deadline, 'finite ordinary read-only finalization')
        need(mem_available() >= contract['p4_live_memory_reserve'] and
             free_space(Q) >= contract['p4_live_disk_reserve'], 'P4 memory/disk reserves during readback')
        if time.monotonic() - last_progress >= 30:
            last_progress = time.monotonic()
            print(json.dumps({'stage': result.get('stage', 'admission'), 'observed_ns': time.time_ns(),
                'whole_image_bytes_read': result.get('whole_image_bytes_read', 0),
                'selected_outputs_completed': len(result['exported_files'])}), flush=True)
            os.fsync(1)

    def command(name, argv, limit):
        child = commands.start(name, argv)
        try:
            end = min(deadline, time.monotonic() + limit)
            while child['popen'].poll() is None:
                checkpoint(); need(time.monotonic() < end, 'finite standard filesystem reader')
                time.sleep(0.2)
            return commands.finish(child, 10)
        except BaseException:
            if not child.get('finished'):
                try: commands.finish(child, 10, stop=True)
                except BaseException as error: result['errors'].append('reader retirement: ' + repr(error))
            raise

    try:
        result['native'] = native_identity(commands, contract['finalize_unit'], contract['finalize_description'], 1000)
        result['actual_lifetime'] = verify_storage_unit(commands, contract, 'finalize', result['native']['InvocationID'])
        state = show(commands, contract['server_unit'])
        need(state['MainPID'] == '0' and state['ActiveState'] == 'inactive' and
             not (P('/sys/fs/cgroup/system.slice') / contract['server_unit']).exists(), 'server remains retired')
        fd = os.open(IMAGE, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(fd)
        need(f9(before) == offline['image']['identity'] == f9(IMAGE.lstat()) and
             stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_size == contract['image_bytes'] and before.st_blocks * 512 >= before.st_size,
             'original fully allocated offline image after actual writer retirement')
        result['e2fsck'] = command('whole-offline-e2fsck-readonly', [tools['e2fsck']['path'], '-f', '-n', str(IMAGE)], 1800)
        need(f9(before) == f9(os.fstat(fd)) == f9(IMAGE.lstat()), 'read-only e2fsck preserves image F9')
        digest = hashlib.sha256(); count = 0; result['stage'] = 'whole-formatted-image-readback'
        while block := os.read(fd, 4 * 1024**2):
            checkpoint(); digest.update(block); count += len(block); result['whole_image_bytes_read'] = count
        need(count == contract['image_bytes'] and f9(before) == f9(os.fstat(fd)) == f9(IMAGE.lstat()),
             'complete stable offline 400 GiB image readback')
        result['whole_image'] = {'path': str(IMAGE), 'bytes': count, 'sha256': digest.hexdigest(),
            'identity': f9(before), 'allocated_bytes': before.st_blocks * 512}
        delivery_path = Q / 'SELECTED-OUTPUTS.json'
        if delivery_path.exists():
            delivery_ref, body = pin(delivery_path, limit=8 * 1024**2); delivery = json.loads(body)
            desktop_result_ref, body = pin(Q / 'DESKTOP-RESULT.json'); desktop_result = json.loads(body)
            original_desktop_ref = desktop['result']
            need(original_desktop_ref['path'] == contract['desktop_root'] + '/DESKTOP-RESULT.json' and
                 original_desktop_ref['bytes'] == desktop_result_ref['bytes'] and
                 original_desktop_ref['sha256'] == desktop_result_ref['sha256'] and
                 original_desktop_ref['identity'][3:6] == [0, 0, 1] and
                 stat.S_IMODE(original_desktop_ref['identity'][2]) == 0o444,
                 'exact original desktop receipt bytes in a separately identified P4 copy')
            need(desktop_result['nonce'] == contract['nonce'] and desktop_result['source_manifest_sha256'] == accepted and
                 desktop_result['admission_sha256'] == admission_sha and
                 desktop_result['selected_delivery']['present'] is True and
                 desktop_result['selected_delivery']['copied_manifest']['path'] == contract['desktop_root'] + '/SELECTED-OUTPUTS.json' and
                 desktop_result['selected_delivery']['copied_manifest']['bytes'] == delivery_ref['bytes'] and
                 desktop_result['selected_delivery']['copied_manifest']['sha256'] == delivery_ref['sha256'] and
                 delivery['schema'] == 'p4-production651-selected-output-delivery-v1' and
                 delivery['nonce'] == contract['nonce'] and delivery['storage_source_manifest_sha256'] == accepted and
                 delivery['storage_admission_sha256'] == admission_sha, 'original selected output manifest and actual desktop capture')
            need(0 < len(delivery['files']) <= 20000 and sum(row['bytes'] for row in delivery['files']) <= 16 * GIB,
                 'original bounded selected output export')
            result['delivery_manifest'] = delivery_ref
            result['desktop_result_original_reference'] = original_desktop_ref
            result['desktop_result_p4_copy_reference'] = desktop_result_ref
            result['desktop_result_whole_bytes_equal'] = True
            result['cross_host_F9_equality_not_claimed'] = True
            result['stage'] = 'selected-persisted-output-readback'
            names = set()
            for index, row in enumerate(delivery['files']):
                checkpoint(); relative = row['image_path']; p = pathlib.PurePosixPath(relative)
                need(not p.is_absolute() and '..' not in p.parts and relative not in names and
                     re.fullmatch('[A-Za-z0-9._/+@-]+', relative) is not None and
                     (relative.startswith('build-production651/') or relative.startswith('delivery/host-deps/')),
                     'only selected original output path in image')
                names.add(relative)
                target = directory / 'exports' / ('%05d-' % index + p.name)
                inode = command('read-original-persisted-inode', [tools['debugfs']['path'], '-R', 'stat /' + relative, str(IMAGE)], 30)
                text = output(inode)
                need(int(re.search(r'Inode:\s+(\d+)', text).group(1)) == row['identity'][1] and
                     re.search(r'User:\s+1000\s+Group:\s+1000', text) is not None,
                     'actual persisted original selected inode and ordinary owner')
                command('dump-original-selected-output', [tools['debugfs']['path'], '-R',
                        'dump /' + relative + ' ' + str(target), str(IMAGE)], 1800)
                out = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                try: os.fsync(out)
                finally: os.close(out)
                read_fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                try:
                    old = os.fstat(read_fd); hashed = hashlib.sha256(); size = 0
                    need(stat.S_ISREG(old.st_mode) and old.st_nlink == 1 and old.st_size == row['bytes'],
                         'exact ordinary persisted output size')
                    while block := os.read(read_fd, 4 * 1024**2):
                        checkpoint(); hashed.update(block); size += len(block)
                    need(f9(old) == f9(os.fstat(read_fd)) == f9(target.lstat()) and size == old.st_size,
                         'stable complete persisted output readback')
                    actual = {'path': str(target), 'bytes': size, 'sha256': hashed.hexdigest(), 'identity': f9(old)}
                finally: os.close(read_fd)
                need(actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256'],
                     'complete persisted selected output matches original ordinary producer hash')
                result['exported_files'].append({'image_path': relative, 'persisted_inode': row['identity'][1], 'readback': actual})
        need(f9(before) == f9(os.fstat(fd)) == f9(IMAGE.lstat()), 'all offline readers preserve exact image identity')
        sources_unchanged(sources); check_tools(contract, 'pocket4'); pin(admission_ref['path'], admission_ref)
        checkpoint(); result['passed'] = True
    except BaseException as error: result['errors'].append(repr(error))
    finally:
        if fd is not None: os.close(fd)
        result['signals'] = STOP
        result['passed'] = bool(result['passed'] and not result['errors'] and not STOP)
        result['passed_scope'] = 'offline_filesystem_and_selected_persisted_bytes_only'
        result['full_build_success_not_inferred'] = True
        save(Q / 'FILESYSTEM-RESULT.json', result, 0o444)
    return 0 if result['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
