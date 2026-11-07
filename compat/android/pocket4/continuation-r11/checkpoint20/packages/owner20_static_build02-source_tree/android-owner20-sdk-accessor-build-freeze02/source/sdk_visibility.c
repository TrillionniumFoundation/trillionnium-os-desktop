/* Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
 *
 * One fresh owned-generation SDK visibility observation. No property writes,
 * sockets to Android services, threads, forks, mounts, or process signals.
 * A root-warmed bionic property cache is deliberately retained after the
 * irreversible credential drop; this is not a fresh LMKD capability simulation.
 */
#define _GNU_SOURCE
#include "sdk_visibility_core.h"
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/system_properties.h>
#include <time.h>
#include <unistd.h>

_Static_assert(PROP_VALUE_MAX == SDK_VALUE_BYTES, "actual bionic value ABI differs");
_Static_assert(_LINUX_CAPABILITY_VERSION_3 == 0x20080522, "capability UAPI differs");
_Static_assert(_LINUX_CAPABILITY_U32S_3 == 2, "capability UAPI word count differs");

static const char *const bionic_paths[3] = {
    "/apex/com.android.runtime/lib64/bionic/libc.so",
    "/apex/com.android.runtime/bin/linker64",
    "/apex/com.android.runtime/lib64/bionic/libdl.so"
};
struct state {
    int channel, parent_pidfd;
    uint64_t started_ns, deadline_ns;
    unsigned int cap_count;
    const char *nonce;
};
static uint64_t now_ns(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) != 0 || t.tv_sec < 0 ||
        t.tv_nsec < 0 || t.tv_nsec >= 1000000000L) return 0;
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static bool parent_live(struct state *s) {
    struct pollfd p = {.fd = s->parent_pidfd, .events = POLLIN};
    int r = poll(&p, 1, 0);
    return r == 0 && p.revents == 0;
}
static bool budget(void *context) {
    struct state *s = context;
    uint64_t n = now_ns();
    return n >= s->started_ns && n < s->deadline_ns && parent_live(s);
}
static int close_once(int *fd) {
    int value = *fd;
    *fd = -1;
    return value < 0 ? 0 : close(value);
}
static int parse_fd(const char *value) {
    if (!value || !value[0] || value[0] == '0') return -1;
    unsigned int n = 0;
    for (const char *p = value; *p; ++p) {
        if (*p < '0' || *p > '9' || n > 6553U) return -1;
        n = n * 10U + (unsigned int)(*p - '0');
    }
    return n >= 3U && n <= 65535U ? (int)n : -1;
}
static bool valid_nonce(const char *value) {
    if (!value || strlen(value) != 64) return false;
    bool nonzero = false;
    for (size_t i = 0; i != 64; ++i) {
        unsigned char c = (unsigned char)value[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
        nonzero |= c != '0';
    }
    return nonzero;
}
static int capabilities(struct state *s, struct sdk_credentials *out) {
    struct __user_cap_header_struct h = {
        .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0};
    struct __user_cap_data_struct d[2] = {{0}, {0}};
    if (syscall(SYS_capget, &h, d) != 0) return -1;
    out->effective = ((uint64_t)d[1].effective << 32) | d[0].effective;
    out->permitted = ((uint64_t)d[1].permitted << 32) | d[0].permitted;
    out->inheritable = ((uint64_t)d[1].inheritable << 32) | d[0].inheritable;
    out->bounding = out->ambient = 0;
    unsigned int count = 0;
    for (unsigned int i = 0; i != 64; ++i) {
        if (!budget(s)) { errno = ETIMEDOUT; return -1; }
        errno = 0;
        int value = prctl(PR_CAPBSET_READ, (unsigned long)i, 0UL, 0UL, 0UL);
        if (value < 0) {
            if (errno != EINVAL || i == 0) return -1;
            break;
        }
        if (value > 1) { errno = EPROTO; return -1; }
        if (value) out->bounding |= UINT64_C(1) << i;
        value = prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, (unsigned long)i, 0UL, 0UL);
        if (value < 0 || value > 1) return -1;
        if (value) out->ambient |= UINT64_C(1) << i;
        ++count;
    }
    if (count == 0 || count == 64) { errno = EOVERFLOW; return -1; }
    if (s->cap_count && s->cap_count != count) { errno = EPROTO; return -1; }
    s->cap_count = count;
    out->no_new_privileges = prctl(PR_GET_NO_NEW_PRIVS, 0UL, 0UL, 0UL, 0UL);
    return out->no_new_privileges < 0 ? -1 : 0;
}
static int credentials(void *context, struct sdk_credentials *out) {
    struct state *s = context;
    memset(out, 0, sizeof(*out));
    uid_t ruid, euid, suid;
    gid_t rgid, egid, sgid, groups[SDK_GROUP_MAX];
    if (getresuid(&ruid, &euid, &suid) != 0 || getresgid(&rgid, &egid, &sgid) != 0) return -1;
    out->uids[0] = ruid; out->uids[1] = euid; out->uids[2] = suid;
    out->gids[0] = rgid; out->gids[1] = egid; out->gids[2] = sgid;
    int count = getgroups(SDK_GROUP_MAX, groups);
    if (count < 0 || count > SDK_GROUP_MAX) return -1;
    out->group_count = (unsigned int)count;
    for (int i = 0; i < count; ++i) out->groups[i] = groups[i];
    return capabilities(s, out);
}
static int get_value(void *context, const char *key, unsigned char *value, int *saved_errno) {
    (void)context;
    errno = 0;
    int result = __system_property_get(key, (char *)value);
    *saved_errno = errno;  /* This API does not promise errno diagnoses a missing property. */
    return result;
}
static int drop(void *context, enum sdk_drop_step step) {
    struct state *s = context;
    switch (step) {
        case SDK_NO_NEW_PRIVILEGES:
            return prctl(PR_SET_NO_NEW_PRIVS, 1UL, 0UL, 0UL, 0UL);
        case SDK_CLEAR_KEEP_CAPS:
            return prctl(PR_SET_KEEPCAPS, 0UL, 0UL, 0UL, 0UL);
        case SDK_CLEAR_AMBIENT:
            return prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0UL, 0UL, 0UL);
        case SDK_CLEAR_BOUNDING:
            for (unsigned int i = 0; i != s->cap_count; ++i) {
                if (!budget(s)) { errno = ETIMEDOUT; return -1; }
                if (prctl(PR_CAPBSET_DROP, (unsigned long)i, 0UL, 0UL, 0UL) != 0) return -1;
            }
            return 0;
        case SDK_CLEAR_GROUPS:
            return setgroups(0, NULL);
        case SDK_SET_GIDS:
            return setresgid(SDK_TARGET_ID, SDK_TARGET_ID, SDK_TARGET_ID);
        case SDK_SET_UIDS:
            return setresuid(SDK_TARGET_ID, SDK_TARGET_ID, SDK_TARGET_ID);
        case SDK_CLEAR_CAPS: {
            struct __user_cap_header_struct h = {
                .version = _LINUX_CAPABILITY_VERSION_3, .pid = 0};
            struct __user_cap_data_struct d[2] = {{0}, {0}};
            return (int)syscall(SYS_capset, &h, d);
        }
        case SDK_RESTORE_PARENT_DEATH:
            /* Changing credentials clears PDEATHSIG. Re-arm, then check the
             * already held parent pidfd, even though parent is outside this PID namespace. */
            if (prctl(PR_SET_PDEATHSIG, SIGKILL, 0UL, 0UL, 0UL) != 0) return -1;
            if (!parent_live(s)) { errno = ECHILD; return -1; }
            return 0;
        default:
            errno = EINVAL;
            return -1;
    }
}
static int packet(struct state *s, const char *body, size_t length, const int *fds, size_t count) {
    if (!budget(s) || length == 0 || length > 8192 || count > 3) { errno = EINVAL; return -1; }
    struct iovec io = {.iov_base = (void *)body, .iov_len = length};
    union {
        struct cmsghdr align;
        unsigned char bytes[CMSG_SPACE(3 * sizeof(int))];
    } control;
    memset(&control, 0, sizeof(control));
    struct msghdr message = {.msg_iov = &io, .msg_iovlen = 1};
    if (count) {
        message.msg_control = control.bytes;
        message.msg_controllen = CMSG_SPACE(count * sizeof(int));
        struct cmsghdr *c = CMSG_FIRSTHDR(&message);
        c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS;
        c->cmsg_len = CMSG_LEN(count * sizeof(int));
        memcpy(CMSG_DATA(c), fds, count * sizeof(int));
    }
    ssize_t sent = sendmsg(s->channel, &message, MSG_DONTWAIT | MSG_NOSIGNAL);
    if (sent != (ssize_t)length) { if (sent >= 0) errno = EIO; return -1; }
    return 0;  /* No retry or reconnect, including EINTR/EAGAIN. */
}
static int failure(struct state *s, const char *stage, int code, int saved_errno, unsigned int count) {
    char body[384];
    int length = snprintf(body, sizeof(body),
        "{\"schema\":1,\"phase\":\"failure\",\"nonce\":\"%s\","
        "\"stage\":\"%s\",\"error_code\":%d,\"errno_observation\":%d,\"completed\":%u}",
        s->nonce, stage, code, saved_errno, count);
    if (length > 0 && (size_t)length < sizeof(body))
        (void)packet(s, body, (size_t)length, NULL, 0);
    return 1;
}
static int token(struct state *s, const char *prefix) {
    size_t prefix_length = strlen(prefix);
    char expected[SDK_TOKEN_BYTES], body[SDK_TOKEN_BYTES + 1];
    if (prefix_length + 64 >= sizeof(expected)) { errno = EINVAL; return -1; }
    memcpy(expected, prefix, prefix_length);
    memcpy(expected + prefix_length, s->nonce, 64);
    size_t length = prefix_length + 64;
    uint64_t current = now_ns();
    if (!budget(s) || current >= s->deadline_ns) { errno = ETIMEDOUT; return -1; }
    int remaining = (int)((s->deadline_ns - current) / UINT64_C(1000000));
    if (remaining < 1) { errno = ETIMEDOUT; return -1; }
    struct pollfd p[2] = {{.fd = s->channel, .events = POLLIN},
                         {.fd = s->parent_pidfd, .events = POLLIN}};
    int ready = poll(p, 2, remaining);
    if (ready <= 0 || p[1].revents || p[0].revents != POLLIN || !budget(s)) {
        errno = ready < 0 ? errno : ETIMEDOUT; return -1;
    }
    union {
        struct cmsghdr align;
        unsigned char bytes[CMSG_SPACE(8 * sizeof(int))];
    } control;
    memset(&control, 0, sizeof(control));
    struct iovec io = {.iov_base = body, .iov_len = sizeof(body)};
    struct msghdr message = {.msg_iov = &io, .msg_iovlen = 1,
        .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes)};
    ssize_t received = recvmsg(s->channel, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC);
    bool unexpected = false, close_failed = false;
    for (struct cmsghdr *c = CMSG_FIRSTHDR(&message); c; c = CMSG_NXTHDR(&message, c)) {
        unexpected = true;
        if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS &&
            c->cmsg_len >= CMSG_LEN(0)) {
            size_t bytes = c->cmsg_len - CMSG_LEN(0);
            for (size_t i = 0; i + sizeof(int) <= bytes; i += sizeof(int)) {
                int fd;
                memcpy(&fd, (unsigned char *)CMSG_DATA(c) + i, sizeof(fd));
                if (close(fd) != 0) close_failed = true;
            }
        }
    }
    if (unexpected || close_failed || (message.msg_flags & ~(MSG_EOR | MSG_CMSG_CLOEXEC)) ||
        received != (ssize_t)length || memcmp(body, expected, length) != 0) {
        errno = EPROTO; return -1;
    }
    return 0;
}
static int credential_json(char *output, size_t available, const struct sdk_credentials *c) {
    int n = snprintf(output, available,
        "{\"uids\":[%u,%u,%u],\"gids\":[%u,%u,%u],\"group_count\":%u,"
        "\"effective\":\"%016llx\",\"permitted\":\"%016llx\","
        "\"inheritable\":\"%016llx\",\"bounding\":\"%016llx\","
        "\"ambient\":\"%016llx\",\"no_new_privileges\":%d}",
        c->uids[0], c->uids[1], c->uids[2], c->gids[0], c->gids[1], c->gids[2],
        c->group_count, (unsigned long long)c->effective, (unsigned long long)c->permitted,
        (unsigned long long)c->inheritable, (unsigned long long)c->bounding,
        (unsigned long long)c->ambient, c->no_new_privileges);
    return n > 0 && (size_t)n < available ? n : -1;
}
static int values_packet(struct state *s, const char *phase, const struct sdk_credentials *c,
                         const struct sdk_value values[SDK_KEY_COUNT], uint64_t before, uint64_t after) {
    char body[4096], creds[512];
    int cn = credential_json(creds, sizeof(creds), c);
    if (cn < 0) { errno = EOVERFLOW; return -1; }
    int n = snprintf(body, sizeof(body),
        "{\"schema\":1,\"phase\":\"%s\",\"nonce\":\"%s\","
        "\"credentials\":%s,\"before_ns\":%llu,\"after_ns\":%llu,\"values\":[",
        phase, s->nonce, creds, (unsigned long long)before, (unsigned long long)after);
    if (n < 0 || (size_t)n >= sizeof(body)) { errno = EOVERFLOW; return -1; }
    size_t position = (size_t)n;
    static const char hex[] = "0123456789abcdef";
    for (unsigned int i = 0; i != SDK_KEY_COUNT; ++i) {
        char value[2 * SDK_VALUE_BYTES + 1];
        unsigned int size = (unsigned int)values[i].result;
        for (unsigned int j = 0; j < size; ++j) {
            value[2*j] = hex[values[i].bytes[j] >> 4];
            value[2*j + 1] = hex[values[i].bytes[j] & 15];
        }
        value[2*size] = 0;
        n = snprintf(body + position, sizeof(body) - position,
            "%s{\"key\":\"%s\",\"return\":%d,\"errno_observation\":%d,\"value_hex\":\"%s\"}",
            i ? "," : "", sdk_keys[i], values[i].result, values[i].saved_errno, value);
        if (n < 0 || (size_t)n >= sizeof(body) - position) { errno = EOVERFLOW; return -1; }
        position += (size_t)n;
    }
    if (sizeof(body) - position < 3) { errno = EOVERFLOW; return -1; }
    body[position++] = ']'; body[position++] = '}'; body[position] = 0;
    return packet(s, body, position, NULL, 0);
}
static int ready_packet(struct state *s, const struct sdk_credentials *credentials_value) {
    int fds[3] = {-1, -1, -1};
    int result = -1, first_errno = 0;
    for (size_t i = 0; i != 3; ++i) {
        if (!budget(s)) { first_errno = ETIMEDOUT; goto done; }
        /* Ordinary APEX parent symlinks resolve inside the already verified
         * chroot; no host path lookup is performed. The final ELF must not be a symlink. */
        fds[i] = open(bionic_paths[i], O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
        if (fds[i] < 0) { first_errno = errno; goto done; }
        struct stat value;
        if (fstat(fds[i], &value) != 0) { first_errno = errno; goto done; }
        if (!S_ISREG(value.st_mode) || value.st_uid != 0 || value.st_gid != 0 ||
            (value.st_mode & 07022) || value.st_size <= 0 || value.st_size > 16*1024*1024) {
            first_errno = EPROTO; goto done;
        }
    }
    Dl_info info;
    memset(&info, 0, sizeof(info));
    if (dladdr((void *)(uintptr_t)&__system_property_get, &info) == 0 || !info.dli_fbase) {
        first_errno = EPROTO; goto done;
    }
    char creds[512], body[1536];
    if (credential_json(creds, sizeof(creds), credentials_value) < 0) {
        first_errno = EOVERFLOW; goto done;
    }
    int n = snprintf(body, sizeof(body),
        "{\"schema\":1,\"phase\":\"ready\",\"nonce\":\"%s\",\"pid\":%d,"
        "\"credentials\":%s,\"getter_address\":\"%llx\",\"getter_library_base\":\"%llx\","
        "\"libraries\":[\"%s\",\"%s\",\"%s\"],\"lifetime_ms\":%u,"
        "\"same_process_root_warmed_cache\":true,\"actual_LMKD_capability_simulation\":false}",
        s->nonce, (int)getpid(), creds, (unsigned long long)(uintptr_t)&__system_property_get,
        (unsigned long long)(uintptr_t)info.dli_fbase,
        bionic_paths[0], bionic_paths[1], bionic_paths[2], SDK_LIFETIME_MS);
    if (n <= 0 || (size_t)n >= sizeof(body)) { first_errno = EOVERFLOW; goto done; }
    result = packet(s, body, (size_t)n, fds, 3);
    if (result != 0) first_errno = errno;
done:
    for (size_t i = 0; i != 3; ++i) {
        if (close_once(&fds[i]) != 0 && first_errno == 0) {
            first_errno = errno; result = -1;
        }
    }
    errno = first_errno;
    return result;
}
int main(int argc, char **argv) {
    if (argc != 5 || strcmp(argv[1], "--sdk-visibility-v1") != 0 ||
        !valid_nonce(argv[2])) return 2;
    struct state s = {.channel = parse_fd(argv[3]), .parent_pidfd = parse_fd(argv[4]),
                      .nonce = argv[2]};
    if (s.channel < 0 || s.parent_pidfd < 0 || s.channel == s.parent_pidfd) return 2;
    s.started_ns = now_ns();
    if (!s.started_ns) return 2;
    s.deadline_ns = s.started_ns + (uint64_t)SDK_LIFETIME_MS * UINT64_C(1000000);
    int kind = 0;
    socklen_t kind_size = sizeof(kind);
    if (getsockopt(s.channel, SOL_SOCKET, SO_TYPE, &kind, &kind_size) != 0 ||
        kind_size != sizeof(kind) || kind != SOCK_SEQPACKET || !parent_live(&s) ||
        prctl(PR_SET_PDEATHSIG, SIGKILL, 0UL, 0UL, 0UL) != 0) return 2;
    struct sdk_backend backend = {.context = &s, .within_budget = budget,
        .get = get_value, .drop = drop, .credentials = credentials};
    struct sdk_credentials root, lower, after;
    struct sdk_value values[SDK_KEY_COUNT];
    unsigned int completed = 0;
    enum sdk_drop_step failed_step = SDK_NO_NEW_PRIVILEGES;
    int result = 1, saved_errno = 0;
    if (credentials(&s, &root) != 0 || !sdk_root(&root)) {
        saved_errno = errno; result = failure(&s, "root_credentials", -1, saved_errno, 0); goto done;
    }
    if (ready_packet(&s, &root) != 0) {
        saved_errno = errno; result = failure(&s, "bionic_ready", -1, saved_errno, 0); goto done;
    }
    if (token(&s, SDK_START_TOKEN) != 0) {
        saved_errno = errno; result = failure(&s, "source_authorization", -1, saved_errno, 0); goto done;
    }
    uint64_t before = now_ns();
    errno = 0;
    int rc = sdk_read_four(&backend, values, &completed);
    saved_errno = errno;
    uint64_t after_ns = now_ns();
    if (rc != 0) { result = failure(&s, "root_read", rc, saved_errno, completed); goto done; }
    if (credentials(&s, &after) != 0 || !sdk_root(&after) ||
        memcmp(&root, &after, sizeof(root)) != 0) {
        saved_errno = errno; result = failure(&s, "root_credentials_changed", -1, saved_errno, 4); goto done;
    }
    if (values_packet(&s, "root", &root, values, before, after_ns) != 0) {
        saved_errno = errno; result = failure(&s, "root_packet", -1, saved_errno, 4); goto done;
    }
    errno = 0;
    rc = sdk_drop_permanently(&backend, &lower, &failed_step);
    saved_errno = errno;
    if (rc != 0) { result = failure(&s, "irreversible_drop", rc, saved_errno, (unsigned int)failed_step); goto done; }
    before = now_ns();
    errno = 0;
    rc = sdk_read_four(&backend, values, &completed);
    saved_errno = errno;
    after_ns = now_ns();
    if (rc != 0) { result = failure(&s, "uid1069_read", rc, saved_errno, completed); goto done; }
    if (credentials(&s, &after) != 0 || !sdk_lowered(&after) ||
        memcmp(&lower, &after, sizeof(lower)) != 0) {
        saved_errno = errno; result = failure(&s, "uid1069_credentials_changed", -1, saved_errno, 4); goto done;
    }
    if (values_packet(&s, "uid1069", &lower, values, before, after_ns) != 0) {
        saved_errno = errno; result = failure(&s, "uid1069_packet", -1, saved_errno, 4); goto done;
    }
    /* Stay alive only inside the same 2s deadline for independent host-side
     * post-view/credentials/loaded-file checks. The original Stop never waits. */
    if (token(&s, SDK_FINISH_TOKEN) != 0) {
        saved_errno = errno; result = failure(&s, "post_observation_ack", -1, saved_errno, 4); goto done;
    }
    result = 0;
done:
    if (close_once(&s.channel) != 0 && result == 0) result = 3;
    if (close_once(&s.parent_pidfd) != 0 && result == 0) result = 3;
    return result;
}
