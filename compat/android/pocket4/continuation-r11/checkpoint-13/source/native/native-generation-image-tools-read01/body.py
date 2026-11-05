ROOT = Path('/home/alex/work/pocket4-native-generation-image-tools-readonly-01-20261105')
TOOLS = ('zip', 'unzip', 'debugfs', 'mke2fs', 'fsck.erofs', 'mkfs.erofs',
         'fakeroot', 'chown', 'setfattr')
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
                    (Path('/usr/bin'), Path('/usr/lib'))),
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
              'tools': {}, 'backend_observations': [],
              'fakeroot_backend_selection_qualified': False,
              'dynamic_library_closure_qualified': False,
              'purpose': 'Read exact existing image-test tools and complete fakeroot wrapper before any tool execution.'}
    resource_fd = -1
    resource_before = None
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        for name in TOOLS:
            found = shutil.which(name, path='/usr/bin:/bin')
            require(found is not None, 'required fixed test tool absent from controlled PATH: ' + name)
            row = observe(found)
            require(row.get('absent') is not True and row['held_before'][2] & 0o111,
                    'fixed test tool is absent or not executable: ' + name)
            report['tools'][name] = row
        for name in BACKENDS:
            report['backend_observations'].append(observe(name))
        for name, row in report['tools'].items():
            require(shutil.which(name, path='/usr/bin:/bin') == row['requested_path'] and
                    observe(row['requested_path']) == row, 'system tool changed after read: ' + name)
        for row in report['backend_observations']:
            require(observe(row['requested_path']) == row, 'fixed backend observation changed after read')
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
        print(json.dumps({'state': 'PLAN_ONLY', 'fixed_tool_names': TOOLS,
                          'fixed_backend_paths': BACKENDS, 'commands_executed': 0,
                          'remote_actions': 0, 'requires_explicit_execute_once': True}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: collect.py [--execute-once]')
