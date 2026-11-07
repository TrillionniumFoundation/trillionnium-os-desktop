"""Create-only preparation. No namespaces, services, network or Android execution."""
import errno, grp, hashlib, json, os, pwd, re, stat, subprocess, sys, time, traceback
from pathlib import Path
import owned
import pinned_support as support


def available_ids(spec):
    uid = spec['host_uid']; lo = spec['subordinate_uids']['start']; count = spec['subordinate_uids']['count']
    owned.need(spec['subordinate_gids'] == spec['subordinate_uids'], 'this fixed profile requires equal subordinate ranges')
    try: pwd.getpwuid(uid)
    except KeyError: pass
    else: raise RuntimeError('proposed host UID already belongs to an account')
    try: grp.getgrgid(uid)
    except KeyError: pass
    else: raise RuntimeError('proposed host GID already belongs to a group')
    files = {}
    for path in ('/etc/subuid', '/etc/subgid'):
        raw = Path(path).read_bytes(); owned.need(len(raw) <= 1024 * 1024, 'subordinate table exceeds bound')
        for line in raw.decode().splitlines():
            if not line.strip() or line.lstrip().startswith('#'): continue
            fields = line.split(':'); owned.need(len(fields) == 3, 'malformed subordinate record')
            start, length = map(int, fields[1:]); owned.need(not (start < lo + count and lo < start + length), 'subordinate range is allocated')
        files[path] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    initial = os.stat('/proc/self/ns/user')
    seen = 0
    for name in os.listdir('/proc'):
        if not name.isdecimal(): continue
        seen += 1; owned.need(seen <= 20000, 'process availability census exceeded bound')
        try:
            directory = os.open('/proc/' + name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        except FileNotFoundError: continue
        try:
            try:
                status = dict(line.split(':', 1) for line in owned.bounded(directory, 'status').decode().splitlines() if ':' in line)
                ids = [int(x) for field in ('Uid', 'Gid') for x in status[field].split()]
                owned.need(not any(x == uid or lo <= x < lo + count for x in ids), 'proposed UID/range has a live process')
                ns = os.stat('ns/user', dir_fd=directory)
                if (ns.st_dev, ns.st_ino) != (initial.st_dev, initial.st_ino):
                    for table in ('uid_map', 'gid_map'):
                        for line in owned.bounded(directory, table).decode().splitlines():
                            fields = line.split(); owned.need(len(fields) == 3, 'malformed user namespace map')
                            _, start, length = map(int, fields)
                            owned.need(not (start <= uid < start + length) and not (start < lo + count and lo < start + length), 'proposed UID/range has a live namespace mapping')
            except (FileNotFoundError, ProcessLookupError): pass
        finally: os.close(directory)
    return {'host_uid': uid, 'subordinate_range': {'start': lo, 'count': count},
            'tables': files, 'processes_observed': seen, 'available_at_observation': True,
            'reservation_created_in_passwd_or_subid_tables': False}


def input_file(row, root_owned=True):
    path = Path(row.get('path', row.get('frozen')))
    parent = owned.root_directory(path.parent) if root_owned else owned.directory(path.parent)
    try: fd = os.open(path.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
    finally: os.close(parent)
    try:
        digest, st = owned.digest_fd(fd, row['bytes'])
        owned.need(digest == row['sha256'] and stat.S_ISREG(st.st_mode) and st.st_nlink >= 1 and not st.st_mode & 0o6022,
                   'input digest/type/privilege differs: ' + str(path))
        if root_owned: owned.need(st.st_uid == st.st_gid == 0 and st.st_nlink == 1, 'sealed base input owner/link count differs')
        if 'device' in row: owned.need((st.st_dev, st.st_ino) == (row['device'], row['inode']), 'actual build artifact was replaced')
        if 'mode' in row: owned.need(stat.S_IMODE(st.st_mode) == row['mode'], 'input mode differs')
        return fd, st
    except BaseException:
        os.close(fd); raise


def inspect_tool(path, expected_digest=None):
    # Only package symlinks are accepted here; the resolved immutable native ELF
    # and symlink spelling become part of the preparation receipt/runtime pin.
    parent = owned.root_directory(Path(path).parent)
    try:
        link = os.stat(Path(path).name, dir_fd=parent, follow_symlinks=False)
        owned.need(link.st_uid == link.st_gid == 0, 'tool pathname is not root-owned')
        link_text = os.readlink(Path(path).name, dir_fd=parent) if stat.S_ISLNK(link.st_mode) else None
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=parent)
    finally: os.close(parent)
    try:
        digest, st = owned.digest_fd(fd)
        support.verify_fd(fd, digest, True)
        owned.need(os.pread(fd, 4, 0) == b'\x7fELF', 'standard tool is not native ELF')
        owned.need(expected_digest is None or digest == expected_digest, 'pinned tool digest differs')
        resolved = os.readlink('/proc/self/fd/' + str(fd))
        owned.need(resolved.startswith('/') and not resolved.endswith(' (deleted)'), 'tool kernel path differs')
        return fd, {'path': path, 'resolved_path': resolved, 'link': link_text, 'sha256': digest,
                    'bytes': st.st_size, 'identity': owned.file_id(fd), 'mode': stat.S_IMODE(st.st_mode)}
    except BaseException: os.close(fd); raise


def base_contract(plan):
    base = Path(plan['base']['path'])
    for name, key in [('media-canary-manifest.json', 'manifest_sha256'), ('cell.json', 'spec_sha256')]:
        fd = os.open(base / name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            digest, _ = owned.digest_fd(fd)
            owned.need(digest == plan['base'][key], 'original base metadata differs')
        finally: os.close(fd)
    records = []
    for row in plan['base']['records']:
        owned.need(Path(row['frozen']) == base / row['relative'] and '..' not in Path(row['relative']).parts, 'base record escaped')
        fd, st = input_file(row)
        try: records.append({'relative': row['relative'], 'sha256': row['sha256'], 'bytes': st.st_size, 'identity': owned.file_id(fd)})
        finally: os.close(fd)
    return records


def resources(plan):
    text = Path('/proc/meminfo').read_text()
    available = int(re.search(r'^MemAvailable:\s+(\d+)', text, re.M)[1]) * 1024
    pressure = Path('/proc/pressure/memory').read_text()
    full = re.search(r'^full avg10=([0-9.]+)', pressure, re.M)
    owned.need(available >= plan['mem_available_min_bytes'] and full and float(full[1]) <= plan['host_memory_full_avg10_max'], 'host memory preflight failed')
    disk = os.statvfs('/opt'); free = disk.f_bavail * disk.f_frsize
    owned.need(free >= plan['disk_available_min_bytes'], 'fresh data disk reserve unavailable')
    return {'MemAvailable_bytes': available, 'memory_pressure': pressure, 'disk_available_bytes': free}


def main(plan, sources):
    result = {'schema': 1, 'kind': 'owner18-normal-preparation01', 'success': False,
              'attempt_nonce': plan['attempt_nonce'], 'runtime_executed': False,
              'namespace_or_network_changed': False, 'production_ready': False, 'errors': []}
    package_fd = state_fd = data_fd = -1; tools = {}; fence = None
    try:
        owned.need(os.geteuid() == os.getuid() == os.getegid() == 0, 'preparation requires original host root')
        owned.need(len(plan['attempt_nonce']) == 64 and
                   plan['scope'] == 'REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT' and
                   plan['kind'] == 'owned-real-producer18-normal01-private-crash-buffer01', 'wrong fixed profile')
        owned.need(not Path(plan['package']).exists() and not Path(plan['state']).exists(), 'preparation root already exists')
        owned.need(support.props(plan['unit']).get('LoadState') == 'not-found', 'owned unit already exists')
        fence = support.MainFence(plan, vars(support)); result['main_before'] = fence.check()
        result['id_availability'] = available_ids(plan['spec'])
        result['resources_before'] = resources(plan)
        result['base_before'] = base_contract(plan)
        result['tools'] = {}
        for path in plan['tools_fixed_paths']:
            tools[path], result['tools'][path] = inspect_tool(path, plan['tools_sha256'][path])
        tools[plan['presenter']['path']], result['presenter'] = inspect_tool(plan['presenter']['path'], plan['presenter']['sha256'])
        owned.need(pwd.getpwnam('alex').pw_uid == plan['helper_uid'] and grp.getgrnam('alex').gr_gid == plan['helper_gid'], 'paired private helper account differs')
        result['helper_groups'] = sorted(os.getgrouplist('alex', plan['helper_gid']))
        # Persist the attempt before the first candidate/resource creation.
        opt = owned.root_directory('/opt')
        try:
            package_fd = owned.make_child(opt, Path(plan['package']).name)
            state_fd = owned.make_child(opt, Path(plan['state']).name)
        finally: os.close(opt)
        owned.save(state_fd, 'preparation-claim.json', {'attempt_nonce': plan['attempt_nonce'], 'package': plan['package'], 'state': plan['state'], 'retry_allowed': False})
        for name in ('bin', 'lib', 'source'):
            fd = owned.make_child(package_fd, name); os.close(fd)
        for name in ('claims', 'data', 'evidence'):
            fd = owned.make_child(state_fd, name)
            if name == 'data': data_fd = fd
            else: os.close(fd)
        result['copied_artifacts'] = {}
        for role, row in plan['artifacts'].items():
            source_fd, before = input_file(row, False)
            target = Path(plan['package']) / row['destination']; parent = owned.root_directory(target.parent)
            try:
                raw = os.pread(source_fd, before.st_size + 1, 0)
                owned.need(len(raw) == before.st_size and hashlib.sha256(raw).hexdigest() == row['sha256'], 'copy input changed')
                owned.write_bytes(parent, target.name, raw, 0o444 if role == 'init-barrier' else 0o555)
                owned.need(support.stamp(os.fstat(source_fd)) == support.stamp(before), 'source changed during copy')
                verify = support.pinned(target, row['sha256'], role != 'init-barrier')
                try: result['copied_artifacts'][role] = {'path': str(target), 'bytes': len(raw), 'sha256': row['sha256'], 'identity': owned.file_id(verify)}
                finally: os.close(verify)
            finally: os.close(source_fd); os.close(parent)
        canonical = json.dumps(plan['spec'], ensure_ascii=False, separators=(',', ':')).encode()
        owned.need(hashlib.sha256(canonical).hexdigest() == plan['canonical_spec_sha256'], 'canonical CellSpec differs')
        owned.need(all(x['target'] not in ('/system/etc/init/lmkd.rc', '/system/bin/lmkd') for x in plan['spec']['android_file_overrides']), 'legacy LMKD override remains')
        owned.write_bytes(package_fd, 'cell.json', canonical)
        source_fd = owned.root_directory(Path(plan['package']) / 'source')
        try:
            for name, row in sources.items():
                raw = row['content'].encode(); owned.need(hashlib.sha256(raw).hexdigest() == row['sha256'], 'source payload SHA differs')
                owned.write_bytes(source_fd, name, raw)
        finally: os.close(source_fd)
        plan_raw = (json.dumps(plan, sort_keys=True, indent=2) + '\n').encode()
        owned.write_bytes(package_fd, 'plan.json', plan_raw)
        result['plan_sha256'] = hashlib.sha256(plan_raw).hexdigest()
        result['source_files'] = {name: {'bytes': len(row['content'].encode()), 'sha256': row['sha256']} for name, row in sources.items()}
        result['data_images'] = []
        for row in plan['data_images']:
            fd = os.open(row['name'], os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=data_fd)
            try:
                os.ftruncate(fd, row['bytes']); os.fsync(fd)
                path = str(Path(plan['spec']['data_dir']) / row['name'])
                tool = tools['/usr/sbin/mkfs.ext4']
                command = ['/proc/self/fd/' + str(tool), '-t', 'ext4', '-F', '-m', '0', '-L', row['label'], '-O', 'verity,^orphan_file', '-E', 'lazy_itable_init=1,lazy_journal_init=1', '/proc/self/fd/' + str(fd)]
                done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    close_fds=True, pass_fds=(tool, fd), env={'PATH':'/usr/sbin:/usr/bin','LC_ALL':'C'}, timeout=35)
                owned.need(len(done.stdout) + len(done.stderr) <= 65536, 'mkfs output bound exceeded')
                entry = {'name': row['name'], 'bytes': row['bytes'], 'identity': owned.file_id(fd), 'returncode': done.returncode,
                         'stdout': done.stdout.decode(), 'stderr': done.stderr.decode(), 'fresh_sparse_created': True, 'existing_userdata_copied': False}
                result['data_images'].append(entry)
                owned.need(done.returncode == 0 and os.fstat(fd).st_size == row['bytes'], 'fresh ext4 creation failed')
                os.fsync(fd)
            finally: os.close(fd)
        # Seal only this new immutable package; mutable state/data/claims are retained.
        for name in ('bin', 'lib', 'source'): os.chmod(name, 0o555, dir_fd=package_fd)
        os.fchmod(package_fd, 0o555)
        os.fchmod(state_fd, 0o755)
        result['package_identity'] = owned.file_id(package_fd); result['state_identity'] = owned.file_id(state_fd)
        result['canonical_spec_sha256'] = plan['canonical_spec_sha256']
        result['base_after'] = base_contract(plan)
        owned.need(result['base_before'] == result['base_after'], 'complete base input contract changed')
        for path, fd in tools.items():
            row = result['presenter'] if path == plan['presenter']['path'] else result['tools'][path]
            support.verify_fd(fd, row['sha256'], True)
        result['main_after'] = fence.check()
        result['success'] = True
    except BaseException as error:
        owned.record_error(result, 'prepare', error); result['traceback'] = traceback.format_exc()
    finally:
        if fence is not None:
            try: result['main_final'] = fence.check()
            except BaseException as error: owned.record_error(result, 'main_final', error); result['success'] = False
            fence.close()
        for fd in tools.values(): os.close(fd)
        if state_fd >= 0:
            owned.save(state_fd, 'prepared.json', result)
        if data_fd >= 0: os.close(data_fd)
        if package_fd >= 0: os.close(package_fd)
        if state_fd >= 0: os.close(state_fd)
    raw = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    summary = {'success': result['success'], 'result_path': plan['state'] + '/prepared.json',
               'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
               'first_error': result.get('first_error'), 'runtime_executed': False}
    if state_fd < 0: summary['result_before_owned_root'] = result
    print(json.dumps(summary))
    return 0 if result['success'] else 1
