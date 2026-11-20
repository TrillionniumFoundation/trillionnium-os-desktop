

def _mapped_guest_id(raw, guest):
    """One actual Android user-zero range; no configured or caller supplied map."""
    need(type(guest) is int and 0 <= guest < 100000,
         'EXACT_ANDROID_USER_ZERO_ID_REQUIRED')
    need(type(raw) is bytes and 0 < len(raw) <= 8192,
         'BOUNDED_ACTUAL_ID_MAP_REQUIRED')
    match = re.fullmatch(rb'[ \t]*([0-9]{1,10})[ \t]+([0-9]{1,10})[ \t]+'
                         rb'([0-9]{1,10})[ \t]*\n', raw)
    need(match is not None, 'ONE_COMPLETE_KERNEL_ID_MAP_REQUIRED')
    inside, outside, count = (int(value) for value in match.groups())
    need(inside == 0 and 100000 <= count <= 0xffffffff
         and 0 <= outside <= 0xffffffff and outside + count <= 0x100000000
         and guest < count, 'COMPLETE_BOUNDED_ANDROID_ID_RANGE_REQUIRED')
    return outside + guest


def mapped_file_info(view, file_fd, guest_uid, guest_gid=None):
    """Read this FD's host ownership against the same held Main's live maps.

    The original MainView still establishes admission. Only metadata from its
    held proc directory is read. The user namespace and both maps bracket the
    fstat; nothing is added to the original seven execution authority FDs.
    A process-local first binding also prevents a later phase from accepting a
    different user namespace or maps on the same otherwise-held process.
    """
    need(type(view) is MainView and type(file_fd) is int and file_fd >= 3,
         'ACTUAL_MAIN_VIEW_AND_CALLER_HELD_FILE_REQUIRED')
    need(type(guest_uid) is int and 0 <= guest_uid < 100000
         and (guest_gid is None or type(guest_gid) is int and 0 <= guest_gid < 100000),
         'EXACT_ANDROID_USER_ZERO_IDS_REQUIRED')
    guest_gid = guest_uid if guest_gid is None else guest_gid
    before_guard = view.guard()
    target = view.target
    proc_fd = target.proc_fd
    before_proc = metadata(os.fstat(proc_fd))
    opened = []
    deadline = time.monotonic() + 3

    def own(fd):
        opened.append(fd)
        need(fd >= 3 and not os.get_inheritable(fd), 'PRIVATE_METADATA_FD_REQUIRED')
        return fd

    def bounded(fd, limit):
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        size = 0
        while True:
            need(time.monotonic() <= deadline, 'ACTUAL_ID_MAP_READ_DEADLINE')
            part = os.read(fd, min(65536, limit + 1 - size))
            if not part:
                return b''.join(chunks)
            size += len(part)
            need(size <= limit, 'ACTUAL_ID_MAP_READ_BOUND')
            chunks.append(part)

    def user_node(fd):
        info = os.fstat(fd)
        need(fcntl.ioctl(fd, 0xb703) == 0x10000000 and info.st_ino > 0,
             'ACTUAL_KERNEL_USER_NAMESPACE_FD_REQUIRED')
        return info.st_dev, info.st_ino

    try:
        with target.lease():
            namespace_fd = own(os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC,
                                       dir_fd=proc_fd))
            namespace = user_node(namespace_fd)
            uid_fd = own(os.open('uid_map', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=proc_fd))
            gid_fd = own(os.open('gid_map', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=proc_fd))
            status_fd = own(os.open('status', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                   dir_fd=proc_fd))
            uid_map, gid_map = bounded(uid_fd, 8192), bounded(gid_fd, 8192)
            host_uid = _mapped_guest_id(uid_map, guest_uid)
            host_gid = _mapped_guest_id(gid_map, guest_gid)
            root_uid, root_gid = _mapped_guest_id(uid_map, 0), _mapped_guest_id(gid_map, 0)
            expected = view.baseline.value['framework_epoch']['binding']['processes']['init']
            need(target.expected['pid'] == expected['host_pid']
                 and target.expected['uid'] == [str(root_uid)] * 4
                 and expected['uids'] == [root_uid] * 4,
                 'ACTUAL_ID_MAP_MUST_BIND_THE_ORIGINAL_MAIN_ROOT_UID')
            gids = re.findall(rb'^Gid:\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$',
                              bounded(status_fd, 65536), re.M)
            need(gids == [(str(root_gid).encode(),) * 4],
                 'ACTUAL_ID_MAP_MUST_BIND_THE_LIVE_MAIN_ROOT_GID')
            binding = (os.getpid(), target, proc_fd, before_proc, namespace, uid_map, gid_map)
            previous = getattr(view, '_mapped_file_owner_scope', None)
            need(previous is None or previous == binding,
                 'ORIGINAL_MAIN_USER_NAMESPACE_OR_ID_MAP_CHANGED')
            info = os.fstat(file_fd)
            need(view.guard() == before_guard and view.target is target,
                 'ORIGINAL_MAIN_CHANGED_DURING_OWNER_OBSERVATION')
            deadline = time.monotonic() + 3
            named_namespace_fd = own(os.open('ns/user', os.O_RDONLY | os.O_CLOEXEC,
                                             dir_fd=proc_fd))
            need(user_node(named_namespace_fd) == namespace
                 and bounded(uid_fd, 8192) == uid_map and bounded(gid_fd, 8192) == gid_map
                 and metadata(os.fstat(proc_fd)) == before_proc,
                 'ACTUAL_MAIN_ID_MAPPING_CHANGED_DURING_FILE_OBSERVATION')
            need(metadata(os.fstat(file_fd)) == metadata(info),
                 'HELD_FILE_CHANGED_DURING_OWNER_OBSERVATION')
            view._mapped_file_owner_scope = binding
            return info, (host_uid, host_gid)
    finally:
        errors = []
        for fd in reversed(opened):
            try:
                os.close(fd)
            except BaseException as error:
                errors.append(error)
        if errors:
            raise RuntimeError('ACTUAL_OWNER_METADATA_FD_CLOSE_FAILED') from errors[0]
