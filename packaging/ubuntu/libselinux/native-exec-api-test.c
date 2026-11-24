#define _GNU_SOURCE
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/lsm.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Exercise the actual packaged public ABI. Only this disposable process
 * interposes syscall/procattr; passing is not real-kernel policy qualification. */
static __thread const char *scenario;
static __thread const char *expected = "u:r:droidloom_policy_loader:s0";
static __thread unsigned expected_attr;
static __thread unsigned native_calls, attr_opens, attr_writes, attr_closes;
static __thread int expected_error, fallback_error, clearing;
static __thread char last_path[128];
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
    assert(attr == expected_attr && flags == 0);
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

/* Match the normal Debian large-file/fortified build, not a custom C build. */
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
        if (clearing)
            assert(bytes == NULL && count == 0);
        else {
            assert(count == strlen(expected) + 1);
            assert(memcmp(bytes, expected, count) == 0);
        }
        if (fallback_error) {
            errno = fallback_error;
            return -1;
        }
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
        errno = EBADF; /* The setter must preserve a failed write's errno. */
        return 0;
    }
    int (*original)(int);
    *(void **)(&original) = dlsym(RTLD_NEXT, "close");
    assert(original);
    return original(fd);
}
typedef int (*set_context)(const char *);
typedef int (*get_context)(char **);
struct api { set_context set; get_context get; unsigned attr; };
static void cached_equals(get_context get, const char *text)
{
    char *context = NULL;
    assert(get(&context) == 0 && context && !strcmp(context, text));
    free(context);
}
static void *fresh_thread(void *argument)
{
    struct api *api = argument;
    scenario = "thread-local";
    expected_attr = api->attr;
    assert(api->set(expected) == 0 && native_calls == 1);
    expected = "u:r:droidloom_query_io:s0";
    assert(api->set(expected) == 0 && native_calls == 2);
    cached_equals(api->get, expected);
    assert(attr_opens == 0);
    return NULL;
}
int main(int argc, char **argv)
{
    assert(argc == 4);
    scenario = argv[3];
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        fprintf(stderr, "%s\n", dlerror());
        return 1;
    }
    const char *name = argv[2];
    unsigned id = !strcmp(name, "exec") ? LSM_ATTR_EXEC :
                  !strcmp(name, "keycreate") ? LSM_ATTR_KEYCREATE : 0;
    expected_attr = id;
    char symbol[64], attr_path[128];
    assert(snprintf(symbol, sizeof(symbol), "set%scon_raw",
                    !strcmp(name, "current") ? "" : name) > 0);
    struct api api = { .attr = id };
    *(void **)(&api.set) = dlsym(library, symbol);
    assert(snprintf(symbol, sizeof(symbol), "get%scon_raw",
                    !strcmp(name, "current") ? "" : name) > 0);
    *(void **)(&api.get) = dlsym(library, symbol);
    assert(api.set && api.get);
    assert(snprintf(attr_path, sizeof(attr_path), "/proc/thread-self/attr/%s", name) > 0);
    native_calls = attr_opens = attr_writes = attr_closes = 0;

    if (!strcmp(scenario, "other-attribute")) {
        assert(!id && (!strcmp(name, "fscreate") ||
                       !strcmp(name, "sockcreate") || !strcmp(name, "current")));
        assert(api.set(expected) == 0);
        assert(native_calls == 0 && attr_opens == 1 && attr_writes == 1 && attr_closes == 1);
        assert(!strcmp(last_path, attr_path));
        cached_equals(api.get, expected);
    } else if (!strcmp(scenario, "thread-local")) {
        assert(id && api.set(expected) == 0 && native_calls == 1);
        pthread_t thread;
        assert(pthread_create(&thread, NULL, fresh_thread, &api) == 0);
        assert(pthread_join(thread, NULL) == 0);
        cached_equals(api.get, expected);
        assert(api.set(expected) == 0 && native_calls == 1 && attr_opens == 0);
    } else if (!strcmp(scenario, "failure-retains-cache")) {
        assert(id && api.set(expected) == 0 && native_calls == 1);
        const char *original = expected;
        expected = "u:r:droidloom_query_io:s0";
        expected_error = EACCES;
        assert(api.set(expected) == -1 && errno == EACCES && native_calls == 2);
        cached_equals(api.get, original);
        expected = original;
        expected_error = 0;
        assert(api.set(expected) == 0 && native_calls == 2);
        expected = "";
        expected_error = EPERM;
        assert(api.set(NULL) == -1 && errno == EPERM && native_calls == 3);
        cached_equals(api.get, original);
        expected = original;
        expected_error = 0;
        assert(api.set(expected) == 0 && native_calls == 3 && attr_opens == 0);
    } else if (!strcmp(scenario, "independent-cache")) {
        assert(id == LSM_ATTR_EXEC);
        struct api key = { .attr = LSM_ATTR_KEYCREATE };
        *(void **)(&key.set) = dlsym(library, "setkeycreatecon_raw");
        *(void **)(&key.get) = dlsym(library, "getkeycreatecon_raw");
        assert(key.set && key.get);
        assert(api.set(expected) == 0 && native_calls == 1);
        expected_attr = key.attr;
        assert(key.set(expected) == 0 && native_calls == 2);
        assert(key.set(expected) == 0 && native_calls == 2);
        expected_attr = api.attr;
        assert(api.set(expected) == 0 && native_calls == 2);
        const char *original = expected;
        expected = "u:r:droidloom_query_io:s0";
        assert(api.set(expected) == 0 && native_calls == 3);
        cached_equals(api.get, expected);
        cached_equals(key.get, original);
        assert(attr_opens == 0);
    } else if (!strcmp(scenario, "public-wrapper")) {
        assert(id);
        assert(snprintf(symbol, sizeof(symbol), "set%scon", name) > 0);
        set_context public_set;
        *(void **)(&public_set) = dlsym(library, symbol);
        assert(public_set && public_set(expected) == 0 && native_calls == 1);
        cached_equals(api.get, expected);
        expected = "";
        assert(public_set(NULL) == 0 && native_calls == 2 && attr_opens == 0);
    } else {
        assert(id);
        if (!strcmp(scenario, "enosys") || !strcmp(scenario, "enosys-null") ||
            !strcmp(scenario, "fallback-failure")) expected_error = ENOSYS;
        else if (!strcmp(scenario, "eopnotsupp") || !strcmp(scenario, "eopnotsupp-null"))
            expected_error = EOPNOTSUPP;
        else if (!strcmp(scenario, "eacces")) expected_error = EACCES;
        else if (!strcmp(scenario, "eperm")) expected_error = EPERM;
        else if (!strcmp(scenario, "einval")) expected_error = EINVAL;
        else if (!strcmp(scenario, "e2big")) expected_error = E2BIG;
        else if (!strcmp(scenario, "efault")) expected_error = EFAULT;
        else if (!strcmp(scenario, "enomem")) expected_error = ENOMEM;
        else assert(!strcmp(scenario, "cache-and-clear") ||
                    !strcmp(scenario, "eintr") || !strcmp(scenario, "null-first"));
        clearing = !strcmp(scenario, "null-first") ||
                   !strcmp(scenario, "enosys-null") || !strcmp(scenario, "eopnotsupp-null");
        if (clearing) expected = "";
        if (!strcmp(scenario, "fallback-failure")) {
            fallback_error = EIO;
            assert(api.set(expected) == -1 && errno == EIO);
            assert(native_calls == 1 && attr_opens == 1 && attr_writes == 1 && attr_closes == 1);
            fallback_error = 0;
            assert(api.set(expected) == 0 && native_calls == 2 && attr_writes == 2);
            cached_equals(api.get, expected);
        } else if (expected_error && expected_error != ENOSYS && expected_error != EOPNOTSUPP) {
            errno = 0;
            assert(api.set(expected) == -1 && errno == expected_error);
            assert(native_calls == 1 && attr_opens == 0 && attr_writes == 0 && attr_closes == 0);
        } else {
            assert(api.set(clearing ? NULL : expected) == 0);
            assert(native_calls == (!strcmp(scenario, "eintr") ? 2u : 1u));
            unsigned fallback = expected_error ? 1u : 0u;
            assert(attr_opens == fallback && attr_writes == fallback && attr_closes == fallback);
            if (fallback) assert(!strcmp(last_path, attr_path));
            if (clearing) {
                assert(api.set(NULL) == 0 && native_calls == 1);
            } else if (!strcmp(scenario, "cache-and-clear")) {
                assert(api.set(expected) == 0 && native_calls == 1);
                cached_equals(api.get, expected);
                expected = "";
                assert(api.set(NULL) == 0 && native_calls == 2);
                assert(api.set(NULL) == 0 && native_calls == 2);
                assert(attr_opens == 0 && attr_writes == 0 && attr_closes == 0);
            }
        }
    }
    printf("PASS %s/%s: native=%u procattr_open=%u write=%u close=%u\n",
           name, scenario, native_calls, attr_opens, attr_writes, attr_closes);
    dlclose(library);
    return 0;
}
