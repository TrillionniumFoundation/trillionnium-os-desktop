#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/lsm.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Public-ABI regression tests against the built shared library. Only this
 * disposable process interposes kernel/procattr calls; these are unit tests,
 * not evidence that a real SELinux transition was admitted. */
static const char *scenario;
static const char *expected = "u:r:droidloom_policy_loader:s0";
static unsigned native_calls, attr_opens, attr_writes, attr_closes;
static int expected_error;
static char last_path[128];
enum { attr_fd = 1234567 };

long syscall(long number, ...)
{
    va_list args;
    assert(number == __NR_lsm_set_self_attr);
    va_start(args, number);
    unsigned attr = va_arg(args, unsigned);
    struct lsm_ctx *ctx = va_arg(args, struct lsm_ctx *);
    uint32_t bytes = va_arg(args, uint32_t);
    unsigned flags = va_arg(args, unsigned);
    va_end(args);
    native_calls++;
    assert(attr == LSM_ATTR_EXEC && flags == 0);
    assert(ctx->id == LSM_ID_SELINUX && ctx->flags == 0);
    assert(ctx->ctx_len == strlen(expected) + 1);
    assert(ctx->len == sizeof(*ctx) + ctx->ctx_len && bytes == ctx->len);
    assert(memcmp(ctx->ctx, expected, ctx->ctx_len) == 0);
    if (!strcmp(scenario, "eintr") && native_calls == 1) {
        errno = EINTR;
        return -1;
    }
    if (expected_error) {
        errno = expected_error;
        return -1;
    }
    return 0;
}

int open(const char *path, int flags, ...)
{
    if (!strncmp(path, "/proc/thread-self/attr/", 23)) {
        attr_opens++;
        assert((flags & O_ACCMODE) == O_RDWR);
        assert(flags & O_CLOEXEC);
        assert(strlen(path) < sizeof(last_path));
        strcpy(last_path, path);
        return attr_fd;
    }
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    int (*original)(const char *, int, ...);
    *(void **)(&original) = dlsym(RTLD_NEXT, "open");
    assert(original);
    return original(path, flags, mode);
}

/* The normal Debian build enables large-file and fortified open variants. */
int open64(const char *path, int flags, ...)
{
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    return open(path, flags, mode);
}

int __open64_2(const char *path, int flags)
{
    assert(!(flags & O_CREAT));
    return open(path, flags);
}

ssize_t write(int fd, const void *bytes, size_t count)
{
    if (fd == attr_fd) {
        attr_writes++;
        assert(count == strlen(expected) + 1);
        assert(memcmp(bytes, expected, count) == 0);
        return (ssize_t)count;
    }
    ssize_t (*original)(int, const void *, size_t);
    *(void **)(&original) = dlsym(RTLD_NEXT, "write");
    assert(original);
    return original(fd, bytes, count);
}

int close(int fd)
{
    if (fd == attr_fd) {
        attr_closes++;
        return 0;
    }
    int (*original)(int);
    *(void **)(&original) = dlsym(RTLD_NEXT, "close");
    assert(original);
    return original(fd);
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    scenario = argv[2];
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        fprintf(stderr, "%s\n", dlerror());
        return 1;
    }
    int (*set_exec)(const char *);
    int (*set_fscreate)(const char *);
    int (*get_exec)(char **);
    *(void **)(&set_exec) = dlsym(library, "setexeccon_raw");
    *(void **)(&set_fscreate) = dlsym(library, "setfscreatecon_raw");
    *(void **)(&get_exec) = dlsym(library, "getexeccon_raw");
    assert(set_exec && set_fscreate && get_exec);
    native_calls = attr_opens = attr_writes = attr_closes = 0;
    if (!strcmp(scenario, "enosys")) expected_error = ENOSYS;
    else if (!strcmp(scenario, "eopnotsupp")) expected_error = EOPNOTSUPP;
    else if (!strcmp(scenario, "eacces")) expected_error = EACCES;
    else if (!strcmp(scenario, "eperm")) expected_error = EPERM;
    else if (!strcmp(scenario, "einval")) expected_error = EINVAL;
    else if (!strcmp(scenario, "e2big")) expected_error = E2BIG;
    else assert(!strcmp(scenario, "cache-and-clear") ||
                !strcmp(scenario, "eintr") || !strcmp(scenario, "other-attribute"));
    if (!strcmp(scenario, "other-attribute")) {
        assert(set_fscreate(expected) == 0);
        assert(native_calls == 0 && attr_opens == 1 && attr_writes == 1 && attr_closes == 1);
        assert(!strcmp(last_path, "/proc/thread-self/attr/fscreate"));
    } else if (expected_error && expected_error != ENOSYS && expected_error != EOPNOTSUPP) {
        errno = 0;
        assert(set_exec(expected) == -1 && errno == expected_error);
        assert(native_calls == 1 && attr_opens == 0 && attr_writes == 0 && attr_closes == 0);
    } else {
        assert(set_exec(expected) == 0);
        assert(native_calls == (!strcmp(scenario, "eintr") ? 2u : 1u));
        unsigned fallback = expected_error ? 1u : 0u;
        assert(attr_opens == fallback && attr_writes == fallback && attr_closes == fallback);
        if (fallback) assert(!strcmp(last_path, "/proc/thread-self/attr/exec"));
        if (!strcmp(scenario, "cache-and-clear")) {
            assert(set_exec(expected) == 0 && native_calls == 1);
            char *context = NULL;
            assert(get_exec(&context) == 0 && context && !strcmp(context, expected));
            free(context);
            expected = "";
            assert(set_exec(NULL) == 0 && native_calls == 2);
            assert(set_exec(NULL) == 0 && native_calls == 2);
            assert(attr_opens == 0 && attr_writes == 0 && attr_closes == 0);
        }
    }
    printf("PASS %s: native=%u procattr_open=%u write=%u close=%u\n",
           scenario, native_calls, attr_opens, attr_writes, attr_closes);
    dlclose(library);
    return 0;
}
