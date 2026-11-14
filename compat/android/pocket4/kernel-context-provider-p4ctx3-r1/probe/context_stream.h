/* SPDX-License-Identifier: Apache-2.0
 * Real queued stream controls. PID1 may relabel only its disposable test socket;
 * the socket creator still enters the independent zero-capability A identity.
 */
#ifndef SO_PASSPIDFD
#define SO_PASSPIDFD 76
#endif
#ifndef SCM_PIDFD
#define SCM_PIDFD 4
#endif

static struct { int listener, transport[2]; char path[108]; } boundary_work;

static void boundary_creator(struct observation *o, int unused)
{
    (void)unused; close(boundary_work.listener); close(boundary_work.transport[1]);
    if (setns(selected_net, CLONE_NEWNET) || change_pair('a', 1, 1) || drop_identity()) { o->error = errno; return; }
    o->caps = caps_zero();
    read_text("/proc-selected/self/attr/current", o->text[0], sizeof(o->text[0]));
    read_text("/proc/self/attr/apparmor/current", o->text[1], sizeof(o->text[1]));
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) { o->error = errno; return; }
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    memcpy(address.sun_path, boundary_work.path, strlen(boundary_work.path) + 1);
    if (connect(fd, (struct sockaddr *)&address, sizeof(address)) || send_fd(boundary_work.transport[0], fd)) o->error = errno;
    close(fd); close(boundary_work.transport[0]);
}

static int boundary_send(int fd, const char payload[2], int right)
{
    struct iovec vector = {(void *)payload, 2};
    union { struct cmsghdr alignment; unsigned char bytes[CMSG_SPACE(sizeof(int))]; } control = {0};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1};
    if (right >= 0) {
        message.msg_control = control.bytes; message.msg_controllen = sizeof(control.bytes);
        struct cmsghdr *c = CMSG_FIRSTHDR(&message);
        c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS; c->cmsg_len = CMSG_LEN(sizeof(int));
        memcpy(CMSG_DATA(c), &right, sizeof(right));
    }
    ssize_t sent = sendmsg(fd, &message, MSG_NOSIGNAL);
    if (sent != 2) { if (sent >= 0) errno = EPROTO; return -1; } return 0;
}

struct boundary_read { int error, length, sec, cred, pidfd, rights, cloexec; char label[256]; };

static struct boundary_read boundary_receive(int fd, int peek, int extras, int right,
                                              ino_t right_inode, const char expected[2], const char *label)
{
    struct boundary_read out = {.cloexec = 1};
    char payload[4] = {0}; struct iovec vector = {payload, sizeof(payload)};
    union { struct cmsghdr alignment; unsigned char bytes[2048]; } control = {0};
    struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes)};
    out.length = (int)recvmsg(fd, &message, MSG_WAITALL | MSG_CMSG_CLOEXEC | (peek ? MSG_PEEK : 0));
    if (out.length != 2 || memcmp(payload, expected, 2) || (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) out.error = out.length < 0 ? errno : EPROTO;
    for (struct cmsghdr *c = CMSG_FIRSTHDR(&message); c; c = CMSG_NXTHDR(&message, c)) {
        size_t length = c->cmsg_len >= CMSG_LEN(0) ? c->cmsg_len - CMSG_LEN(0) : 0;
        if (c->cmsg_level != SOL_SOCKET) { out.error = EPROTO; continue; }
        if (c->cmsg_type == SCM_SECURITY) {
            out.sec++;
            if (!length || length >= sizeof(out.label) || strnlen((char *)CMSG_DATA(c), length) != length - 1) out.error = EPROTO;
            else memcpy(out.label, CMSG_DATA(c), length);
        } else if (c->cmsg_type == SCM_CREDENTIALS) {
            struct ucred credentials = {0}; out.cred++;
            if (length != sizeof(credentials)) out.error = EPROTO;
            else {
                memcpy(&credentials, CMSG_DATA(c), sizeof(credentials));
                if (credentials.pid != 1 || credentials.uid || credentials.gid) out.error = EPROTO;
            }
        } else if (c->cmsg_type == SCM_PIDFD || c->cmsg_type == SCM_RIGHTS) {
            if (!length || length % sizeof(int)) { out.error = EPROTO; continue; }
            for (size_t offset = 0; offset + sizeof(int) <= length; offset += sizeof(int)) {
                int received = -1; memcpy(&received, (unsigned char *)CMSG_DATA(c) + offset, sizeof(received));
                if (received < 0) { out.error = EPROTO; continue; }
                int descriptor_flags = fcntl(received, F_GETFD);
                if (descriptor_flags < 0 || !(descriptor_flags & FD_CLOEXEC)) out.cloexec = 0;
                if (c->cmsg_type == SCM_PIDFD) {
                    char path[96], info[512]; out.pidfd++;
                    snprintf(path, sizeof(path), "/proc/self/fdinfo/%d", received); read_text(path, info, sizeof(info));
                    if (!strstr(info, "Pid:\t1\n")) out.error = EPROTO;
                } else {
                    struct stat info; char value[7] = {0}; out.rights++;
                    if (fstat(received, &info) || info.st_ino != right_inode || pread(received, value, 6, 0) != 6 || memcmp(value, "8764FD", 6)) out.error = errno ? errno : EPROTO;
                }
                close(received);
            }
        } else out.error = EPROTO;
    }
    if (out.sec != 1 || strcmp(out.label, label) || out.cred != extras || out.pidfd != extras || out.rights != right || !out.cloexec) out.error = out.error ? out.error : EPROTO;
    return out;
}

static void stream_boundary_controls(void)
{
    for (int mode = 0; mode < 3; mode++) {
        memset(&boundary_work, 0, sizeof(boundary_work));
        boundary_work.listener = boundary_work.transport[0] = boundary_work.transport[1] = -1;
        snprintf(boundary_work.path, sizeof(boundary_work.path), "/p4-context-work/stream-boundary-%d", mode);
        struct sockaddr_un address = {.sun_family = AF_UNIX}; memcpy(address.sun_path, boundary_work.path, strlen(boundary_work.path) + 1);
        int error = 0, source = -1, receiver = -1, rights = -1, enabled = 1; ino_t rights_inode = 0;
        const char *step = "selected listener"; struct observation creator = {0};
        struct boundary_read peek = {0}, first = {0}, second = {0};
        char before[256] = {0}, after[256] = {0}, rights_path[128] = {0};
        struct timeval timeout = {.tv_sec = 2};
        if (setns(selected_net, CLONE_NEWNET) || (boundary_work.listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0)) < 0) { error = errno; goto done; }
        if (setsockopt(boundary_work.listener, SOL_SOCKET, SO_PASSSEC, &enabled, sizeof(enabled)) ||
            setsockopt(boundary_work.listener, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
            (mode && (setsockopt(boundary_work.listener, SOL_SOCKET, SO_PASSCRED, &enabled, sizeof(enabled)) ||
                      setsockopt(boundary_work.listener, SOL_SOCKET, SO_PASSPIDFD, &enabled, sizeof(enabled)))) ||
            bind(boundary_work.listener, (struct sockaddr *)&address, sizeof(address)) || chmod(boundary_work.path, 0777) ||
            listen(boundary_work.listener, 1) || setns(initial_net, CLONE_NEWNET) ||
            socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, boundary_work.transport)) { error = errno; goto done; }
        step = "zero-cap A source and fd transfer";
        if (worker(boundary_creator, 0, &creator) || creator.error) { error = creator.error ? creator.error : errno; goto done; }
        source = receive_fd(boundary_work.transport[1]); if (source < 0) { error = errno; goto done; }
        step = "source label A and first queued SKB";
        if (fgetxattr(source, "security.selinux", before, sizeof(before)) <= 0 || strcmp(before, SEL_A)) { error = errno ? errno : EPROTO; goto done; }
        if (mode == 2) {
            snprintf(rights_path, sizeof(rights_path), "/p4-context-work/stream-rights-%d", mode);
            rights = open(rights_path, O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
            struct stat status;
            if (rights < 0 || write_all(rights, "8764FD", 6) || fstat(rights, &status)) { error = errno; goto done; }
            rights_inode = status.st_ino;
        }
        if (boundary_send(source, "Aa", rights)) { error = errno; goto done; }
        step = "authorized diagnostic socket relabel A to B";
        if (fsetxattr(source, "security.selinux", SEL_B, sizeof(SEL_B), 0) ||
            fgetxattr(source, "security.selinux", after, sizeof(after)) <= 0 || strcmp(after, SEL_B)) { error = errno ? errno : EPROTO; goto done; }
        step = "second queued SKB and accept";
        if (boundary_send(source, "Bb", -1) || shutdown(source, SHUT_WR) ||
            (receiver = accept4(boundary_work.listener, NULL, NULL, SOCK_CLOEXEC)) < 0) { error = errno; goto done; }
        if (setsockopt(receiver, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout))) { error = errno; goto done; }
        step = "MSG_WAITALL PEEK then consume typed boundary";
        peek = boundary_receive(receiver, 1, mode != 0, mode == 2, rights_inode, "Aa", SEL_A);
        first = boundary_receive(receiver, 0, mode != 0, mode == 2, rights_inode, "Aa", SEL_A);
        second = boundary_receive(receiver, 0, mode != 0, 0, rights_inode, "Bb", SEL_B);
        if (peek.error || first.error || second.error) error = peek.error ? peek.error : first.error ? first.error : second.error;
done:
        if (setns(initial_net, CLONE_NEWNET) && !error) error = errno;
        int fds[] = {source, receiver, rights, boundary_work.listener, boundary_work.transport[0], boundary_work.transport[1]};
        for (unsigned i = 0; i < sizeof(fds) / sizeof(fds[0]); i++) if (fds[i] >= 0) close(fds[i]);
        unlink(boundary_work.path); if (rights_path[0]) unlink(rights_path);
        int passed = !error && creator.caps && !strcmp(creator.text[0], SEL_A) && !strcmp(creator.text[1], AA_A);
        report(mode == 0 ? "stream_typed_boundary_without_credentials" : mode == 1 ? "stream_typed_boundary_credentials_pidfd" : "stream_typed_boundary_credentials_pidfd_rights",
               passed, error, "step=%s source_inode_label=%s -> %s creator_caps_zero=%d; queued_before_accept=1; "
               "peek/consume/next lengths=[%d,%d,%d] labels=[%s,%s,%s] errors=[%d,%d,%d]; "
               "credentials=[%d,%d,%d] pidfds=[%d,%d,%d] rights=[%d,%d,%d] cloexec=[%d,%d,%d]; "
               "same PID1 credentials across SKBs, only typed security label changes",
               step, before, after, creator.caps, peek.length, first.length, second.length, peek.label, first.label, second.label,
               peek.error, first.error, second.error, peek.cred, first.cred, second.cred, peek.pidfd, first.pidfd, second.pidfd,
               peek.rights, first.rights, second.rights, peek.cloexec, first.cloexec, second.cloexec);
    }
}
