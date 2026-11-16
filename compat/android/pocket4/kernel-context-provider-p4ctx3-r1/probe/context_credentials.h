/* Disposable guest only. All policy changes occur after PID1/marker/DMI checks. */
static int p4_open_for_credential_case(const char *path, int mode,
                                     struct child_result *result)
{
    int fd = -1;
    result->credential_mode = mode;
    if (mode < 0 || mode > 3) { errno = EINVAL; goto fail; }
    if (mode && change_pair(mode == 3 ? 'b' : 'a', 1, 1)) goto fail;
    if (mode == 2 && (change_pair('b', 1, 1) || drop_identity())) goto fail;
    read_text("/proc/self/attr/apparmor/current", result->opened_credential,
              sizeof(result->opened_credential));
    read_text("/proc-selected/self/attr/current", result->opened_selinux,
              sizeof(result->opened_selinux));
    result->opened_uid = (unsigned)geteuid();
    fd = open(path, O_RDWR | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) goto fail;
    if (mode == 1 && (change_pair('b', 1, 1) || drop_identity())) goto fail;
    if (mode == 3 && (change_pair('a', 1, 1) || drop_identity())) goto fail;
    read_text("/proc/self/attr/apparmor/current", result->active_credential,
              sizeof(result->active_credential));
    read_text("/proc-selected/self/attr/current", result->active_selinux,
              sizeof(result->active_selinux));
    result->active_uid = (unsigned)geteuid();
    if (mode) {
        result->caps_zero = caps_zero();
        int forbidden = open("/p4-context-work/aa-denied", O_RDONLY | O_CLOEXEC);
        int saved = errno;
        if (forbidden >= 0) { close(forbidden); errno = EPROTO; goto fail; }
        result->forbidden_open_errno = saved;
        if (saved != EACCES || !result->caps_zero) { errno = EPROTO; goto fail; }
    }
    return fd;
fail:
    result->label_setup_error = errno ? errno : EPROTO;
    if (fd >= 0) close(fd);
    errno = result->label_setup_error;
    return -1;
}
