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
static __thread unsigned native_calls, native_get_calls, attr_opens, attr_reads, attr_writes, attr_closes;
static __thread int get_error;
static __thread int get_unset;
static __thread int expected_error, fallback_error, clearing;
static __thread char last_path[128];
enum { attr_fd = 1234567 };

long syscall(long number, ...)
{
    va_list args;
    va_start(args, number);
    if (number == __NR_lsm_get_self_attr) {
        unsigned attr = va_arg(args, unsigned);
        struct lsm_ctx *ctx = va_arg(args, struct lsm_ctx *);
        uint32_t *bytes = va_arg(args, uint32_t *);
        unsigned flags = va_arg(args, unsigned);
        va_end(args);
        native_get_calls++;
        assert(attr == LSM_ATTR_FSCREATE && expected_attr == attr);
        assert(flags == LSM_FLAG_SINGLE && ctx->id == LSM_ID_SELINUX);
        assert(ctx->flags == 0 && *bytes >= sizeof(*ctx) + strlen(expected) + 8);
        if (!strcmp(scenario, "get-eintr") && native_get_calls == 1) {
            errno = EINTR;
            return -1;
        }
        if (get_error) {
            errno = get_error;
            return -1;
        }
        uint64_t length = get_unset ? 0 : strlen(expected) + 1;
        uint32_t size = (sizeof(*ctx) + length + 7) & ~7U;
        ctx->id = LSM_ID_SELINUX;
        ctx->flags = 0;
        ctx->len = size;
        ctx->ctx_len = length;
        if (length) memcpy(ctx->ctx, expected, length);
        *bytes = size;
        if (!strcmp(scenario, "get-bad-count")) return 2;
        if (!strcmp(scenario, "get-bad-id")) ctx->id = LSM_ID_APPARMOR;
        if (!strcmp(scenario, "get-bad-flags")) ctx->flags = 1;
        if (!strcmp(scenario, "get-bad-short")) *bytes = sizeof(*ctx) - 1;
        if (!strcmp(scenario, "get-bad-size")) *bytes = UINT32_MAX;
        if (!strcmp(scenario, "get-bad-length")) ctx->len++;
        if (!strcmp(scenario, "get-bad-context-length")) ctx->ctx_len = UINT64_MAX;
        if (!strcmp(scenario, "get-bad-nul")) ctx->ctx[length - 1] = 'x';
        if (!strcmp(scenario, "get-bad-embedded-nul")) ctx->ctx[1] = '\0';
        if (!strcmp(scenario, "get-bad-unset-alignment")) {
            ctx->ctx_len = 0;
            ctx->len = sizeof(*ctx) + 1;
            *bytes = ctx->len;
        }
        if (!strcmp(scenario, "get-bad-padding")) {
            assert(sizeof(*ctx) + length < size);
            ((unsigned char *)ctx)[sizeof(*ctx) + length] = 1;
        }
        return 1;
    }
    assert(number == __NR_lsm_set_self_attr);
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
    if (!strcmp(scenario, "positive-result") || !strcmp(scenario, "positive-result-null")) {
        errno = ENOSYS; /* Stale errno must not turn a bad success into fallback. */
        return 1;
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
        assert((flags & O_ACCMODE) == (get_error ? O_RDONLY : O_RDWR));
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
ssize_t read(int fd, void *bytes, size_t count)
{
    if (fd == attr_fd) {
        attr_reads++;
        assert(get_error == ENOSYS || get_error == EOPNOTSUPP);
        size_t size = get_unset ? 0 : strlen(expected) + 1;
        assert(count >= size);
        if (size) memcpy(bytes, expected, size);
        return (ssize_t)size;
    }
    ssize_t (*original)(int, void *, size_t);
    *(void **)(&original) = dlsym(RTLD_NEXT, "read");
    assert(original);
    return original(fd, bytes, count);
}
/* Debian _FORTIFY_SOURCE=3 emits this checked public read entrypoint. */
ssize_t __read_chk(int fd, void *bytes, size_t count, size_t buffer_size)
{
    assert(count <= buffer_size);
    return read(fd, bytes, count);
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
                  !strcmp(name, "keycreate") ? LSM_ATTR_KEYCREATE :
                  !strcmp(name, "fscreate") ? LSM_ATTR_FSCREATE : 0;
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

    if (!strncmp(scenario, "get-", 4)) {
        assert(id == LSM_ATTR_FSCREATE);
        get_unset = !strcmp(scenario, "get-unset") ||
                    !strcmp(scenario, "get-cleared") ||
                    !strcmp(scenario, "get-enosys-unset") ||
                    !strcmp(scenario, "get-eopnotsupp-unset");
        if (!strcmp(scenario, "get-enosys") || !strcmp(scenario, "get-enosys-unset"))
            get_error = ENOSYS;
        else if (!strcmp(scenario, "get-eopnotsupp") || !strcmp(scenario, "get-eopnotsupp-unset"))
            get_error = EOPNOTSUPP;
        else if (!strcmp(scenario, "get-eacces")) get_error = EACCES;
        else if (!strcmp(scenario, "get-eperm")) get_error = EPERM;
        else if (!strcmp(scenario, "get-einval")) get_error = EINVAL;
        else if (!strcmp(scenario, "get-e2big")) get_error = E2BIG;
        else if (!strcmp(scenario, "get-efault")) get_error = EFAULT;
        else if (!strcmp(scenario, "get-enomem")) get_error = ENOMEM;
        if (!strcmp(scenario, "get-cleared")) {
            assert(api.set(expected) == 0);
            expected = "";
            assert(api.set(NULL) == 0 && native_calls == 2);
        }
        if (!strcmp(scenario, "get-public-wrapper"))
            *(void **)(&api.get) = dlsym(library, "getfscreatecon");
        char sentinel[] = "unchanged";
        char *context = sentinel;
        int malformed = !strncmp(scenario, "get-bad-", 8);
        int denied = get_error && get_error != ENOSYS && get_error != EOPNOTSUPP;
        if (malformed || denied) {
            assert(api.get(&context) == -1);
            assert(errno == (malformed ? EPROTO : get_error));
            assert(context == sentinel && attr_opens == 0 && attr_reads == 0);
        } else {
            assert(api.get(&context) == 0);
            if (get_unset) assert(context == NULL);
            else assert(context && !strcmp(context, expected));
            free(context);
            if (get_error) {
                assert(attr_opens == 1 && attr_reads == 1 && attr_closes == 1);
                assert(!strcmp(last_path, attr_path));
            } else assert(attr_opens == 0 && attr_reads == 0);
        }
        assert(native_get_calls == (!strcmp(scenario, "get-eintr") ? 2u : 1u));
        assert(attr_writes == 0);
    } else if (!strcmp(scenario, "other-attribute")) {
        assert(!id && (!strcmp(name, "sockcreate") || !strcmp(name, "current")));
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
        struct api fs = { .attr = LSM_ATTR_FSCREATE };
        *(void **)(&fs.set) = dlsym(library, "setfscreatecon_raw");
        *(void **)(&fs.get) = dlsym(library, "getfscreatecon_raw");
        assert(fs.set && fs.get);
        expected_attr = fs.attr;
        expected = original;
        assert(fs.set(expected) == 0 && native_calls == 4);
        assert(fs.set(expected) == 0 && native_calls == 4);
        cached_equals(fs.get, original);
        cached_equals(key.get, original);
        cached_equals(api.get, "u:r:droidloom_query_io:s0");
        assert(native_get_calls == 0 && attr_opens == 0);
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
        else if (!strcmp(scenario, "positive-result") || !strcmp(scenario, "positive-result-null"))
            expected_error = EPROTO;
        else assert(!strcmp(scenario, "cache-and-clear") ||
                    !strcmp(scenario, "eintr") || !strcmp(scenario, "null-first"));
        clearing = !strcmp(scenario, "positive-result-null") || !strcmp(scenario, "null-first") ||
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
            assert(api.set(clearing ? NULL : expected) == -1 && errno == expected_error);
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
    printf("PASS %s/%s: native_set=%u native_get=%u procattr_open=%u read=%u write=%u close=%u\n",
           name, scenario, native_calls, native_get_calls, attr_opens, attr_reads, attr_writes, attr_closes);
    dlclose(library);
    return 0;
}
