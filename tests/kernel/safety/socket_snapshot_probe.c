// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <grp.h>
#include <stdio.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
#ifndef SO_PEERGROUPS
#define SO_PEERGROUPS 59
#endif
static int failures;
static void check(const char *name, int ok) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, ok ? "true" : "false");
    failures += !ok;
}
static int peer(int fd, uid_t uid, gid_t gid) {
    struct ucred c = {0}; socklen_t n = sizeof(c);
    return !getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &c, &n) &&
        n == sizeof(c) && c.pid == getpid() && c.uid == uid && c.gid == gid;
}
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0); alarm(15);
    if (geteuid()) return 77;
    gid_t initial[] = {60003, 60004}, replacement[] = {60005};
    if (setgroups(2, initial)) return 77;
    int old[2], fresh[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, old)) return 90;
    check("initial_peer_root", peer(old[0], 0, 0));
    if (setgroups(1, replacement) || setresgid(60001, 60001, 60001) ||
        setresuid(60001, 60001, 60001)) return 77;
    check("old_peer_identity_frozen_after_setresid", peer(old[0], 0, 0));
    gid_t groups[8] = {0}; socklen_t size = sizeof(groups);
    int rc = getsockopt(old[0], SOL_SOCKET, SO_PEERGROUPS, groups, &size);
    check("old_peer_groups_frozen_after_setgroups", !rc && size == sizeof(initial) &&
        groups[0] == initial[0] && groups[1] == initial[1]);
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, fresh)) return 90;
    check("new_peer_uses_new_identity", peer(fresh[0], 60001, 60001));
    size = sizeof(groups);
    rc = getsockopt(fresh[0], SOL_SOCKET, SO_PEERGROUPS, groups, &size);
    check("new_peer_uses_new_groups", !rc && size == sizeof(replacement) && groups[0] == replacement[0]);
    close(old[0]); close(old[1]); close(fresh[0]); close(fresh[1]);
    return failures ? 42 : 0;
}
