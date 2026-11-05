int ObserveRevokedSession(int connection, uint64_t end) {
  if (connection < 0) { errno = EBADF; return -1; }
  const int before = errno;
  for (;;) {
    timespec time{};
    if (clock_gettime(CLOCK_MONOTONIC, &time) < 0) return -1;
    const uint64_t now = static_cast<uint64_t>(time.tv_sec) * 1000000000ULL + time.tv_nsec;
    if (now >= end) { errno = ETIMEDOUT; return -1; }
    const int timeout = static_cast<int>(std::min<uint64_t>((end - now + 999999) / 1000000, 2000));
    pollfd entry{connection, static_cast<short>(POLLIN | POLLHUP), 0};
    const int polled = poll(&entry, 1, timeout);
    if (polled < 0 && errno == EINTR) continue;
    if (polled < 0) return -1;
    if (!polled) { errno = ETIMEDOUT; return -1; }
    if (entry.revents & POLLNVAL) { errno = EBADF; return -1; }
    if (polled != 1 || !(entry.revents & POLLHUP)) { errno = EPROTO; return -1; }
    unsigned char byte{};
    iovec vector{&byte, sizeof(byte)};
    msghdr message{}; message.msg_iov = &vector; message.msg_iovlen = 1;
    // No ancillary buffer: unexpected rights cannot be installed in this
    // process. MSG_CTRUNC still makes such a queued message a failure.
    const ssize_t count = recvmsg(connection, &message,
                                 MSG_DONTWAIT | MSG_TRUNC | MSG_CMSG_CLOEXEC);
    const int observed = errno;
    if (count < 0 && observed == EINTR) continue;
    if ((message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) || count > 0) {
      errno = EPROTO; return -1;
    }
    if (!count || (count < 0 && observed == ECONNRESET)) { errno = before; return 0; }
    errno = observed; return -1;
  }
}
