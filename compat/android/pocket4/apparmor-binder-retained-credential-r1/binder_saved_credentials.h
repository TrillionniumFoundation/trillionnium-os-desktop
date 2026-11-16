/* SPDX-License-Identifier: Apache-2.0
 * Disposable-VM controls only. This is not an Android or host policy.
 * Included after the base control's read_text() and child_result definitions.
 */
#ifndef P4_BINDER_SAVED_CREDENTIALS_H
#define P4_BINDER_SAVED_CREDENTIALS_H

#include <grp.h>

#define P4_PROFILE_A "p4-binder-cred-a"
#define P4_PROFILE_B "p4-binder-cred-b"
#define P4_TEST_UID 10001U

static int p4_assert_disposable_vm(void) {
    char text[256];
    if (getpid() != 1 || getuid() != 0) { errno = EPERM; return -1; }
    read_text("/p4-disposable-kernel-control", text, sizeof(text));
    if (strcmp(text, "pocket4-private-kernel-control-20261108-8b88-v1")) {
        errno = EPERM; return -1;
    }
    read_text("/sys/class/dmi/id/sys_vendor", text, sizeof(text));
    if (strcmp(text, "Pocket4KernelQualification")) { errno = EPERM; return -1; }
    read_text("/sys/class/dmi/id/product_name", text, sizeof(text));
    if (strcmp(text, "DisposableKernelControl")) { errno = EPERM; return -1; }
    read_text("/sys/class/dmi/id/product_serial", text, sizeof(text));
    if (strcmp(text, "p4-kernel-cred-20261108-8b88-r1")) { errno = EPERM; return -1; }
    return 0;
}

static int p4_load_credential_policy(size_t *loaded_bytes) {
    const size_t maximum = 1024U * 1024U;
    int input = -1, output = -1, result = -1, saved_errno;
    unsigned char *bytes = NULL;
    struct stat status;
    if (p4_assert_disposable_vm()) return -1;
    input = open("/p4-binder-credential-policy.bin", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (input < 0) goto done;
    if (fstat(input, &status)) goto done;
    if (!S_ISREG(status.st_mode) || status.st_size <= 0 ||
        (uint64_t)status.st_size > maximum) { errno = EINVAL; goto done; }
    bytes = malloc((size_t)status.st_size);
    if (!bytes) goto done;
    size_t count = 0;
    while (count < (size_t)status.st_size) {
        ssize_t got = read(input, bytes + count, (size_t)status.st_size - count);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) { if (!got) errno = EIO; goto done; }
        count += (size_t)got;
    }
    unsigned char extra;
    if (read(input, &extra, 1) != 0) { errno = EIO; goto done; }
    output = open("/sys/kernel/security/apparmor/.load", O_WRONLY | O_CLOEXEC);
    if (output < 0) goto done;
    ssize_t wrote;
    do { wrote = write(output, bytes, count); } while (wrote < 0 && errno == EINTR);
    if (wrote != (ssize_t)count) { if (wrote >= 0) errno = EIO; goto done; }
    *loaded_bytes = count;
    result = 0;
done:
    saved_errno = errno;
    if (input >= 0) close(input);
    if (output >= 0) close(output);
    free(bytes);
    errno = saved_errno;
    return result;
}

static int p4_change_profile(const char *profile) {
    char command[128], observed[256], expected[256];
    int length = snprintf(command, sizeof(command), "changeprofile %s", profile);
    if (length <= 0 || (size_t)length >= sizeof(command)) { errno = EINVAL; return -1; }
    int fd = open("/proc/self/attr/current", O_WRONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    ssize_t wrote;
    do { wrote = write(fd, command, (size_t)length + 1); } while (wrote < 0 && errno == EINTR);
    int saved_errno = errno;
    close(fd);
    if (wrote != (ssize_t)length + 1) { errno = wrote < 0 ? saved_errno : EIO; return -1; }
    read_text("/proc/self/attr/current", observed, sizeof(observed));
    snprintf(expected, sizeof(expected), "%s (enforce)", profile);
    if (strcmp(observed, expected)) { errno = EPROTO; return -1; }
    return 0;
}

static int p4_drop_test_identity(void) {
    if (setgroups(0, NULL) || setresgid(P4_TEST_UID, P4_TEST_UID, P4_TEST_UID) ||
        setresuid(P4_TEST_UID, P4_TEST_UID, P4_TEST_UID)) return -1;
    if (getuid() != P4_TEST_UID || geteuid() != P4_TEST_UID ||
        getgid() != P4_TEST_UID || getegid() != P4_TEST_UID) {
        errno = EPROTO; return -1;
    }
    return 0;
}

/* mode 1: open under A, transition to B, drop UID, use that same open FD.
 * mode 2: transition to B and drop UID first, then open a fresh FD under B.
 */
static int p4_open_for_credential_case(const char *path, int mode,
                                       struct child_result *result) {
    int fd = -1;
    result->credential_mode = mode;
    if (mode != 0) {
        if (mode != 1 && mode != 2) { errno = EINVAL; goto failure; }
        if (p4_change_profile(P4_PROFILE_A)) goto failure;
        if (mode == 2 && (p4_change_profile(P4_PROFILE_B) || p4_drop_test_identity()))
            goto failure;
    }
    read_text("/proc/self/attr/current", result->opened_credential,
              sizeof(result->opened_credential));
    result->opened_uid = (unsigned int)geteuid();
    fd = open(path, O_RDWR | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) goto failure;
    if (mode == 1 && (p4_change_profile(P4_PROFILE_B) || p4_drop_test_identity()))
        goto failure;
    read_text("/proc/self/attr/current", result->active_credential,
              sizeof(result->active_credential));
    result->active_uid = (unsigned int)geteuid();
    if (mode != 0) {
        int forbidden = open("/p4-denied-credential-control", O_RDONLY | O_CLOEXEC);
        int observed_errno = errno;
        if (forbidden >= 0) {
            close(forbidden); errno = EPROTO; goto failure;
        }
        result->forbidden_open_errno = observed_errno;
        if (observed_errno != EACCES) { errno = EPROTO; goto failure; }
    }
    return fd;
failure:
    result->label_setup_error = errno ? errno : EPROTO;
    if (fd >= 0) close(fd);
    errno = result->label_setup_error;
    return -1;
}

#endif
