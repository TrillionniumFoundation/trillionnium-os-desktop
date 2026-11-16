/* Original real Binder wire protocol, adapted only for finite provider controls. */
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
    char opened_selinux[256];
    char active_selinux[256];
    int caps_zero;
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
    int remount_plain_errno;
    int remount_same_errno;
    int remount_other_errno;
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

#include "context_credentials.h"

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

static struct case_result binder_run_case(const char *root, const char *name, int security_context, int credential_mode, int selected) {
    struct case_result result = {.context_requested = security_context, .credential_mode = credential_mode};
    int control = -1, fd = -1, pipes[2] = {-1, -1};
    void *mapping = MAP_FAILED;
    pid_t child = -1;
    char control_path[512]; snprintf(control_path, sizeof(control_path), "%s/binder-control", root);
    control = open(control_path, O_RDWR | O_CLOEXEC);
    if (control < 0) { result.server_error = errno; goto done; }
    struct binderfs_device device = {0};
    snprintf(device.name, sizeof(device.name), "%s", name);
    if (ioctl(control, BINDER_CTL_ADD, &device)) { result.server_error = errno; goto done; }
    close(control); control = -1;
    char path[512]; snprintf(path, sizeof(path), "%s/%s", root, name);
    if (chmod(path, 0666)) { result.server_error = errno; goto done; }
    fd = open(path, O_RDWR | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) { result.server_error = errno; goto done; }
    result.remount_plain_errno = mount(NULL, root, NULL, MS_REMOUNT, NULL) ? errno : 0;
    result.remount_same_errno = mount(NULL, root, NULL, MS_REMOUNT,
                                    selected ? "lsm_context=selinux" : "lsm_context=default") ? errno : 0;
    result.remount_other_errno = mount(NULL, root, NULL, MS_REMOUNT,
                                     selected ? "lsm_context=default" : "lsm_context=selinux") ? errno : 0;
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

