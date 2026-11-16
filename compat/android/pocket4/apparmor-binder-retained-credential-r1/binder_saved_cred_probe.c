/* SPDX-License-Identifier: Apache-2.0
 * Isolated kernel regression control, not an Android compatibility shim.
 * Run as PID 1 in a disposable VM initramfs. No host disks or network are used.
 * Both cases use real Binder IPC. The second retains TXN_SECURITY_CTX, as QPR1
 * does; the first is a negative control for the scope of the kernel failure.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/android/binder.h>
#include <linux/android/binderfs.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define MAP_BYTES (1024U * 1024U)
#define REPLY_VALUE UINT32_C(0x50344352)
#define TEST_CODE UINT32_C(1599098439)

struct child_result {
    int completed;
    int failed_reply;
    int extended_error;
    unsigned int extended_command;
    int system_errno;
    int valid_reply;
    char opened_credential[256];
    char active_credential[256];
    int credential_mode;
    int label_setup_error;
    int forbidden_open_errno;
    unsigned int opened_uid;
    unsigned int active_uid;
};

struct case_result {
    int context_requested;
    int credential_mode;
    int transaction_received;
    int context_received;
    int server_error;
    int timed_out;
    int child_exited;
    int child_status;
    unsigned int sender_euid;
    char context[256];
    struct child_result child;
};

static long long milliseconds(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
    return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static void read_text(const char *path, char *out, size_t length) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) { snprintf(out, length, "ERROR:%d", errno); return; }
    ssize_t n = read(fd, out, length - 1);
    close(fd);
    if (n < 0) { snprintf(out, length, "ERROR:%d", errno); return; }
    out[n] = 0;
    while (n && (out[n - 1] == '\n' || out[n - 1] == '\r')) out[--n] = 0;
}

static void json_string(const char *s) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        if (*p == '"' || *p == '\\') { putchar('\\'); putchar(*p); }
        else if (*p < 32 || *p >= 127) printf("\\u%04x", *p);
        else putchar(*p);
    }
    putchar('"');
}

static int exchange(int fd, const void *write_buffer, size_t write_bytes,
                    void *read_buffer, size_t read_bytes, size_t *received) {
    struct binder_write_read b = {0};
    b.write_size = write_bytes;
    b.write_buffer = (binder_uintptr_t)(uintptr_t)write_buffer;
    b.read_size = read_bytes;
    b.read_buffer = (binder_uintptr_t)(uintptr_t)read_buffer;
    int result;
    do { result = ioctl(fd, BINDER_WRITE_READ, &b); } while (result < 0 && errno == EINTR);
    if (received) *received = b.read_consumed;
    if (result < 0) return -1;
    if (b.write_consumed != write_bytes) { errno = EPROTO; return -1; }
    return 0;
}

static int write_transaction(int fd, uint32_t command, const struct binder_transaction_data *data) {
    unsigned char wire[sizeof(command) + sizeof(*data)];
    memcpy(wire, &command, sizeof(command));
    memcpy(wire + sizeof(command), data, sizeof(*data));
    return exchange(fd, wire, sizeof(wire), NULL, 0, NULL);
}

static int in_mapping(const void *mapping, binder_uintptr_t pointer, size_t size) {
    uintptr_t begin = (uintptr_t)mapping, end = begin + MAP_BYTES, p = (uintptr_t)pointer;
    return p >= begin && p <= end && size <= end - p;
}

static void free_buffer(int fd, binder_uintptr_t pointer) {
    uint32_t command = BC_FREE_BUFFER;
    unsigned char wire[sizeof(command) + sizeof(pointer)];
    memcpy(wire, &command, sizeof(command));
    memcpy(wire + sizeof(command), &pointer, sizeof(pointer));
    (void)exchange(fd, wire, sizeof(wire), NULL, 0, NULL);
}

#include "binder_saved_credentials.h"

static void child_call(const char *path, int output, int credential_mode) {
    struct child_result result = {0};
    int fd = p4_open_for_credential_case(path, credential_mode, &result);
    void *mapping = MAP_FAILED;
    if (fd < 0) { result.system_errno = errno; goto done; }
    mapping = mmap(NULL, MAP_BYTES, PROT_READ, MAP_PRIVATE, fd, 0);
    if (mapping == MAP_FAILED) { result.system_errno = errno; goto done; }
    struct binder_transaction_data transaction = {0};
    transaction.target.handle = 0;
    transaction.code = TEST_CODE;
    if (write_transaction(fd, BC_TRANSACTION, &transaction)) {
        result.system_errno = errno;
        goto done;
    }
    long long deadline = milliseconds() + 6000;
    while (milliseconds() < deadline) {
        unsigned char buffer[4096];
        size_t count = 0;
        if (exchange(fd, NULL, 0, buffer, sizeof(buffer), &count)) {
            if (errno == EAGAIN) { struct pollfd p = {fd, POLLIN, 0}; poll(&p, 1, 20); continue; }
            result.system_errno = errno; break;
        }
        for (size_t offset = 0; offset < count;) {
            uint32_t command;
            if (count - offset < sizeof(command)) { result.system_errno = EPROTO; goto done; }
            memcpy(&command, buffer + offset, sizeof(command)); offset += sizeof(command);
            size_t size = _IOC_SIZE(command);
            if (size > count - offset) { result.system_errno = EPROTO; goto done; }
            if (command == BR_FAILED_REPLY) {
                struct binder_extended_error error = {0};
                result.failed_reply = 1;
                if (ioctl(fd, BINDER_GET_EXTENDED_ERROR, &error)) result.system_errno = errno;
                else { result.extended_error = error.param; result.extended_command = error.command; }
                result.completed = 1;
                goto done;
            }
            if (command == BR_REPLY) {
                struct binder_transaction_data reply;
                memcpy(&reply, buffer + offset, sizeof(reply));
                uint32_t value = 0;
                if (reply.data_size == sizeof(value) && in_mapping(mapping, reply.data.ptr.buffer, sizeof(value))) {
                    memcpy(&value, (const void *)(uintptr_t)reply.data.ptr.buffer, sizeof(value));
                    result.valid_reply = value == REPLY_VALUE;
                }
                free_buffer(fd, reply.data.ptr.buffer);
                result.completed = 1;
                goto done;
            }
            if (command == BR_DEAD_REPLY || command == BR_ERROR) {
                result.system_errno = EPROTO; goto done;
            }
            offset += size;
        }
    }
done:
    if (mapping != MAP_FAILED) munmap(mapping, MAP_BYTES);
    if (fd >= 0) close(fd);
    ssize_t written = write(output, &result, sizeof(result));
    close(output);
    _exit(written == sizeof(result) ? 0 : 2);
}

static struct case_result run_case(const char *name, int security_context, int credential_mode) {
    struct case_result result = {.context_requested = security_context, .credential_mode = credential_mode};
    int control = -1, fd = -1, pipes[2] = {-1, -1};
    void *mapping = MAP_FAILED;
    pid_t child = -1;
    control = open("/dev/binderfs/binder-control", O_RDWR | O_CLOEXEC);
    if (control < 0) { result.server_error = errno; goto done; }
    struct binderfs_device device = {0};
    snprintf(device.name, sizeof(device.name), "%s", name);
    if (ioctl(control, BINDER_CTL_ADD, &device)) { result.server_error = errno; goto done; }
    close(control); control = -1;
    char path[512]; snprintf(path, sizeof(path), "/dev/binderfs/%s", name);
    if (chmod(path, 0666)) { result.server_error = errno; goto done; }
    fd = open(path, O_RDWR | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) { result.server_error = errno; goto done; }
    mapping = mmap(NULL, MAP_BYTES, PROT_READ, MAP_PRIVATE, fd, 0);
    if (mapping == MAP_FAILED) { result.server_error = errno; goto done; }
    struct flat_binder_object object = {0};
    object.hdr.type = BINDER_TYPE_BINDER;
    object.flags = FLAT_BINDER_FLAG_ACCEPTS_FDS | (security_context ? FLAT_BINDER_FLAG_TXN_SECURITY_CTX : 0);
    if (ioctl(fd, BINDER_SET_CONTEXT_MGR_EXT, &object)) { result.server_error = errno; goto done; }
    uint32_t enter = BC_ENTER_LOOPER;
    if (exchange(fd, &enter, sizeof(enter), NULL, 0, NULL) || pipe2(pipes, O_CLOEXEC)) {
        result.server_error = errno; goto done;
    }
    child = fork();
    if (child < 0) { result.server_error = errno; goto done; }
    if (child == 0) {
        close(pipes[0]); munmap(mapping, MAP_BYTES); close(fd);
        child_call(path, pipes[1], credential_mode);
    }
    close(pipes[1]); pipes[1] = -1;
    long long deadline = milliseconds() + 8000;
    while (milliseconds() < deadline) {
        int status = 0;
        pid_t exited = waitpid(child, &status, WNOHANG);
        if (exited == child) { result.child_exited = 1; result.child_status = status; child = -1; break; }
        if (exited < 0) { result.server_error = errno; break; }
        unsigned char buffer[4096]; size_t count = 0;
        if (exchange(fd, NULL, 0, buffer, sizeof(buffer), &count)) {
            if (errno == EAGAIN) { struct pollfd p = {fd, POLLIN, 0}; poll(&p, 1, 20); continue; }
            result.server_error = errno; break;
        }
        for (size_t offset = 0; offset < count;) {
            uint32_t command;
            if (count - offset < sizeof(command)) { result.server_error = EPROTO; goto done; }
            memcpy(&command, buffer + offset, sizeof(command)); offset += sizeof(command);
            size_t size = _IOC_SIZE(command);
            if (size > count - offset) { result.server_error = EPROTO; goto done; }
            if (command == BR_TRANSACTION_SEC_CTX || command == BR_TRANSACTION) {
                struct binder_transaction_data_secctx received = {0};
                memcpy(&received, buffer + offset, size);
                result.transaction_received++;
                result.sender_euid = received.transaction_data.sender_euid;
                if (command == BR_TRANSACTION_SEC_CTX && in_mapping(mapping, received.secctx, 1)) {
                    const char *text = (const char *)(uintptr_t)received.secctx;
                    size_t remaining = (uintptr_t)mapping + MAP_BYTES - (uintptr_t)text;
                    size_t length = strnlen(text, remaining < sizeof(result.context) ? remaining : sizeof(result.context));
                    if (length && length < sizeof(result.context) && length < remaining) {
                        memcpy(result.context, text, length); result.context_received = 1;
                    }
                }
                uint32_t value = REPLY_VALUE;
                struct binder_transaction_data reply = {0};
                reply.data_size = sizeof(value);
                reply.data.ptr.buffer = (binder_uintptr_t)(uintptr_t)&value;
                if (write_transaction(fd, BC_REPLY, &reply)) { result.server_error = errno; goto done; }
                free_buffer(fd, received.transaction_data.data.ptr.buffer);
            } else if (command != BR_NOOP && command != BR_TRANSACTION_COMPLETE) {
                result.server_error = EPROTO; goto done;
            }
            offset += size;
        }
    }
done:
    if (child > 0) {
        result.timed_out = 1;
        kill(child, SIGKILL); waitpid(child, &result.child_status, 0); child = -1;
    }
    if (pipes[1] >= 0) { close(pipes[1]); pipes[1] = -1; }
    if (pipes[0] >= 0) {
        ssize_t n = read(pipes[0], &result.child, sizeof(result.child));
        if (n != sizeof(result.child) && !result.server_error) result.server_error = EIO;
        close(pipes[0]);
    }
    if (mapping != MAP_FAILED) munmap(mapping, MAP_BYTES);
    if (fd >= 0) close(fd);
    if (control >= 0) close(control);
    return result;
}

static void emit_case(const struct case_result *r) {
    printf("{\"context_requested\":%s,\"transaction_received\":%d,\"context_received\":%s,"
           "\"server_error\":%d,\"timed_out\":%s,\"child_exited\":%s,\"child_wait_status\":%d,"
           "\"sender_euid\":%u,\"context\":", r->context_requested ? "true" : "false",
           r->transaction_received, r->context_received ? "true" : "false", r->server_error,
           r->timed_out ? "true" : "false", r->child_exited ? "true" : "false", r->child_status, r->sender_euid);
    json_string(r->context);
    printf(",\"client\":{\"completed\":%s,\"failed_reply\":%s,\"extended_error\":%d,"
           "\"extended_command\":%u,\"system_errno\":%d,\"valid_reply\":%s,\"opened_credential\":",
           r->child.completed ? "true" : "false", r->child.failed_reply ? "true" : "false",
           r->child.extended_error, r->child.extended_command, r->child.system_errno,
           r->child.valid_reply ? "true" : "false");
    json_string(r->child.opened_credential);
    printf(",\"active_credential\":"); json_string(r->child.active_credential);
    printf(",\"credential_mode\":%d,\"label_setup_error\":%d,\"forbidden_open_errno\":%d,"
           "\"opened_uid\":%u,\"active_uid\":%u}}", r->child.credential_mode,
           r->child.label_setup_error, r->child.forbidden_open_errno,
           r->child.opened_uid, r->child.active_uid);
}

static int mount_required(const char *source, const char *target, const char *type) {
    if (mkdir(target, 0755) && errno != EEXIST) return -1;
    return mount(source, target, type, 0, NULL);
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (getpid() != 1 || getuid() != 0) {
        fprintf(stderr, "Disposable VM PID 1 required; refusing host execution\n");
        return 64;
    }
    char marker[128];
    read_text("/p4-disposable-kernel-control", marker, sizeof(marker));
    if (strcmp(marker, "pocket4-private-kernel-control-20261108-8b88-v1")) {
        fprintf(stderr, "Disposable initramfs marker required; refusing mounts\n");
        return 64;
    }
    int setup_error = 0;
    if (mount_required("proc", "/proc", "proc") || mount_required("sysfs", "/sys", "sysfs") ||
        mount_required("devtmpfs", "/dev", "devtmpfs") ||
        mount_required("securityfs", "/sys/kernel/security", "securityfs")) setup_error = errno;
    if (!setup_error && p4_assert_disposable_vm()) setup_error = errno;
    if (!setup_error) {
        int module = open("/binder_linux.ko", O_RDONLY | O_CLOEXEC);
        if (module >= 0) {
            if (syscall(SYS_finit_module, module, "", 0) && errno != EEXIST) setup_error = errno;
            close(module);
        } else if (errno != ENOENT) setup_error = errno;
    }
    if (!setup_error && mount_required("binder", "/dev/binderfs", "binder")) setup_error = errno;
    size_t policy_bytes = 0;
    if (!setup_error && p4_load_credential_policy(&policy_bytes)) setup_error = errno;
    struct stat denied_status;
    if (!setup_error && (stat("/p4-denied-credential-control", &denied_status) ||
        !S_ISREG(denied_status.st_mode) || (denied_status.st_mode & 0777) != 0444 ||
        denied_status.st_uid != 0)) setup_error = EPROTO;
    char lsm[512], credential[256]; struct utsname uts = {0};
    read_text("/sys/kernel/security/lsm", lsm, sizeof(lsm));
    read_text("/proc/self/attr/current", credential, sizeof(credential)); uname(&uts);
    struct case_result without = {0}, with = {0}, saved = {0}, fresh = {0};
    if (!setup_error) {
        without = run_case("control-no-context", 0, 0);
        with = run_case("control-with-context", 1, 0);
        saved = run_case("control-saved-credential", 1, 1);
        fresh = run_case("control-fresh-credential", 1, 2);
    }
    printf("P4_BINDER_KERNEL_CONTROL_BEGIN\n{\"schema\":\"isolated-binder-saved-credential-kernel-control-v1\","
           "\"Android_boot_completed\":false,\"runtime_qualified\":false,\"setup_error\":%d,\"kernel\":", setup_error);
    json_string(uts.release); printf(",\"active_lsm\":"); json_string(lsm);
    printf(",\"init_credential\":"); json_string(credential); printf(",\"cases\":[");
    if (!setup_error) {
        emit_case(&without); printf(","); emit_case(&with);
        printf(","); emit_case(&saved); printf(","); emit_case(&fresh);
    }
    printf("],\"policy_loaded_bytes\":%zu}\nP4_BINDER_KERNEL_CONTROL_END\n", policy_bytes);
    sync(); reboot(RB_POWER_OFF);
    for (;;) pause();
}
