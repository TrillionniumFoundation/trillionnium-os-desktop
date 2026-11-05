IMAGE_TOOL_OBSERVATION = 'b7129a849481537bd9a6e8124ab43c639d22712b0ce732488f132186ee1b7292'
IMAGE_TEST_PATH = '/usr/bin:/usr/sbin:/bin:/sbin'
FAKEROOT_DAEMON = '/usr/bin/faked-sysv'
FAKEROOT_PRELOAD = '/usr/lib/x86_64-linux-gnu/libfakeroot/libfakeroot-sysv.so'
FAKEROOT_TEST = 'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'
IMAGE_TOOL_PATHS = {
    'zip':'/usr/bin/zip', 'unzip':'/usr/bin/unzip', 'debugfs':'/usr/sbin/debugfs',
    'mke2fs':'/usr/sbin/mke2fs', 'fsck.erofs':'/usr/bin/fsck.erofs',
    'mkfs.erofs':'/usr/bin/mkfs.erofs', 'fakeroot':'/usr/bin/fakeroot',
    'chown':'/usr/bin/chown', 'setfattr':'/usr/bin/setfattr',
}
IMAGE_TOOL_NAMES = tuple(IMAGE_TOOL_PATHS)
FAKEROOT_AUXILIARIES = ('/usr/bin/sed', '/usr/bin/cut', '/usr/bin/cat')


def image_pin(path, allowed, native_elf):
    row = pin_resolved(path, allowed)
    resolved = Path(row['resolved_path'])
    for parent in resolved.parents:
        value = parent.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and not value.st_mode & 0o022,
                'image tool ancestor is not immutable to this operator: '+str(parent))
    fd = os.open(resolved, os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(identity(before) == row['identity'] and before.st_uid == 0 and
                not before.st_mode & 0o022, 'image input owner/mode changed or is not root-owned')
        is_elf = os.read(fd,4) == b'\x7fELF'
        require(is_elf is native_elf, 'image input ELF/script kind differs')
        require(identity(before) == identity(os.fstat(fd)) == identity(resolved.lstat()),
                'image input changed during owner/type verification')
        require(path.resolve(strict=True) == resolved, 'image input resolution changed')
    finally:
        os.close(fd)
    row['root_owner_and_nonwritable_parents_verified'] = True
    row['is_ELF'] = is_elf
    return row


def image_toolchain(report, environment):
    raw, authority_pin = pinned_packet('image-tools-result.json', IMAGE_TOOL_OBSERVATION)
    authority = json.loads(raw)
    require(authority['state'] == 'PASS_FIXED_READ_ONLY_OBSERVATIONS' and
            authority['commands_executed'] == 0 and authority['image_or_mount_actions'] == 0 and
            authority['install_update_actions'] == 0 and authority['observations_unchanged_after'] is True and
            authority['owned_resource_gate']['pass'] is True and set(authority['tools']) == set(IMAGE_TOOL_NAMES) and
            authority['controlled_selection_PATH'] == IMAGE_TEST_PATH and not authority['missing_required_tools'] and
            sum(len(rows) for rows in authority['tool_candidate_observations'].values()) == 13 and
            len(authority['backend_observations']) == 10,
            'fixed image tool observation is not complete')
    require(all(name not in environment for name in ('FAKEROOTKEY','LD_PRELOAD','LD_LIBRARY_PATH')),
            'image tool environment contains inherited fakeroot or loader state')
    wrapper = authority['tools']['fakeroot']['complete_script_source']
    require(sha(wrapper.encode()) == authority['tools']['fakeroot']['sha256'] and
            wrapper.startswith('#!/bin/sh\n') and
            'FAKEROOT_PREFIX=/usr\nFAKEROOT_BINDIR=/usr/bin\n' in wrapper and
            'USEABSLIBPATH=0\nFAKEROOT_LIB=libfakeroot-sysv.so\n' in wrapper and
            'PATHS=/usr/lib/x86_64-linux-gnu/libfakeroot:${FAKEROOT_PREFIX}/lib64/libfakeroot:${FAKEROOT_PREFIX}/lib32/libfakeroot\n' in wrapper and
            'FAKED=${FAKEROOT_BINDIR}/faked-sysv\n' in wrapper,
            'complete observed fakeroot wrapper does not select the fixed sysv backend')
    allowed = [Path('/usr/bin'), Path('/usr/sbin'), Path('/usr/lib')]
    rows = []
    executables = []
    for name in IMAGE_TOOL_NAMES:
        before = authority['tools'][name]
        requested = IMAGE_TOOL_PATHS[name]
        require(before['requested_path'] == requested and before['uid'] == 0 and
                shutil.which(name,path=IMAGE_TEST_PATH) == requested,
                'image tool does not match the explicit controlled PATH selection')
        row = image_pin(Path(requested), allowed, before['is_ELF'])
        require(row['sha256'] == before['sha256'] and row['bytes'] == before['bytes'] and
                row['resolved_path'] == before['resolved_path'], 'observed image tool changed: '+name)
        rows.append(row)
        if before['is_ELF']:
            executables.append(Path(requested))
        else:
            require(name == 'fakeroot', 'only the independently read fakeroot script may be a wrapper')
    backends = {row['requested_path']:row for row in authority['backend_observations']}
    for name in (FAKEROOT_DAEMON, FAKEROOT_PRELOAD, '/bin/sh', '/usr/bin/getopt'):
        require(name in backends and backends[name].get('absent') is not True,
                'exact fakeroot backend/interpreter is absent from the fixed read authority')
        before = backends[name]
        row = image_pin(Path(name), allowed, True)
        require(before['is_ELF'] is True and row['sha256'] == before['sha256'] and
                row['bytes'] == before['bytes'] and row['resolved_path'] == before['resolved_path'],
                'fakeroot backend/interpreter changed')
        rows.append(row)
        executables.append(Path(name))
    # These three fixed auxiliary paths were identified in the complete wrapper.
    # They are first observed here before execution, not claimed as reader02 pins.
    auxiliaries = []
    for name in FAKEROOT_AUXILIARIES:
        require(shutil.which(Path(name).name,path=IMAGE_TEST_PATH) == name,
                'fixed fakeroot auxiliary is shadowed in the controlled PATH')
        row = image_pin(Path(name), allowed, True)
        rows.append(row)
        auxiliaries.append(row)
        executables.append(Path(name))
    require(shutil.which('getopt',path=IMAGE_TEST_PATH) == '/usr/bin/getopt',
            'observed getopt is shadowed in the controlled PATH')
    # Fixed root-owned native ELF inputs only; no fixture/candidate program is
    # passed to ldd. Runtime dependencies are held/hash-pinned and rechecked.
    linked = set()
    for index,path in enumerate(executables):
        raw = command(['/usr/bin/ldd',str(path)],COPIED,environment,
                      'image-linked-libraries-'+str(index),report['commands'],10).decode()
        require('not found' not in raw, 'image tool runtime library is missing')
        for line in raw.splitlines():
            match = re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:
                linked.add(match.group(1))
    for name in sorted(linked):
        rows.append(image_pin(Path(name), allowed+[Path('/lib')], True))
    report['actual_image_tools_authority'] = authority_pin
    report['image_tools_scope'] = {
        'tool_names':list(IMAGE_TOOL_NAMES), 'controlled_test_PATH':IMAGE_TEST_PATH,
        'fixed_fakeroot_daemon':FAKEROOT_DAEMON, 'fixed_fakeroot_preload':FAKEROOT_PRELOAD,
        'auxiliaries_first_observed_before_execution':auxiliaries,
        'fakeroot_args':'-- <actual held test executable> --exact <fixed metadata test> --nocapture',
        'fakeroot_save_or_load_flags_permitted':False,
        'real_ext4_erofs_zip_fakeroot_tests_required':5,
        'mount_or_install_commands_permitted':False,
        'fixtures_are_test_marked_bytes_not_platform_signed_APEX':True,
        'uutils_chown_compatibility_not_assumed':True}
    return list({row['requested_path']:row for row in rows}.values())


def reap_normal_fakeroot_daemon(record):
    # The exact test wrapper owns one daemon and requests its normal TERM on
    # exit. The controller is a subreaper: an exited adopted daemon still needs
    # waitpid. This function never signals a child or treats a live one as done.
    record.update({'maximum_seconds':2,'signal_actions':0,'reaped':[],'remaining':[]})
    deadline = min(time.monotonic()+2, DEADLINE)
    while True:
        current = children()
        record['remaining'] = current
        require(len(current)+len(record['reaped']) <= 1,
                'exact fakeroot test left more than its one owned daemon')
        if not current:
            return
        for pid in current:
            got,status = os.waitpid(pid,os.WNOHANG)
            if got:
                record['reaped'].append({'pid':got,'status':status})
                require((os.WIFEXITED(status) and os.WEXITSTATUS(status)==0) or
                        (os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGTERM),
                        'owned fakeroot daemon did not exit normally or by wrapper TERM')
        if not children():
            record['remaining'] = []
            return
        require(time.monotonic()<deadline,'owned fakeroot daemon remained live after bounded normal retirement')
        time.sleep(0.01)
