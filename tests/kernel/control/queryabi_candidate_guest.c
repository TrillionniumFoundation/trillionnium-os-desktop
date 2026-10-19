/* Real disposable-guest regression; retain the original A05 probe verbatim. */
#define _GNU_SOURCE
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

/* The original probe uses unbuffered stdout. libc puts may write its text and
 * newline separately, allowing the kernel's syscall trace between them. Keep
 * exact-line evidence by submitting each marker and newline in one syscall. */
static int candidate_puts(const char *text) {
    char line[256];
    size_t length = strnlen(text, sizeof line - 1);
    if (length == sizeof line - 1) { _exit(90); }
    memcpy(line, text, length);
    line[length] = '\n';
    ssize_t written;
    do {
        written = write(STDOUT_FILENO, line, length + 1);
    } while (written < 0 && errno == EINTR);
    if (written != (ssize_t)(length + 1)) { _exit(91); }
    return 0;
}

#define puts candidate_puts
#define main original_queryabi_main
#include "queryabi_guest.c"
#undef main
#undef puts

/* These checks use actual Process sessions. They do not create native grants. */
static int same_session(int fd, const unsigned char *expected, int sequence) {
    unsigned char query[64], abi[112];
    prep(query, sequence);
    if (run_query(fd, query, abi, sizeof abi) != 0 || !valid_reply(abi, query) ||
        memcmp(abi + 40, expected + 40, 16) != 0 ||
        memcmp(abi + 64, expected + 64, 16) != 0) {
        fail("lifecycle_existing_session"); return 1;
    }
    int fresh = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
    if (fresh < 0) { fail("lifecycle_fresh_open"); return 1; }
    prep(query, sequence + 1);
    int result = run_query(fresh, query, abi, sizeof abi);
    close(fresh);
    if (result != 0 || !valid_reply(abi, query) ||
        memcmp(abi + 40, expected + 40, 16) != 0 ||
        memcmp(abi + 64, expected + 64, 16) != 0) {
        fail("lifecycle_fresh_session"); return 1;
    }
    return 0;
}

struct lifecycle_thread {
    int fd;
    unsigned char abi[112];
    pid_t process_id;
    long main_tid;
    int result;
};

static void *query_from_thread(void *opaque) {
    struct lifecycle_thread *state = opaque;
    if (getpid() != state->process_id || syscall(SYS_gettid) == state->main_tid) {
        fail("lifecycle_not_another_thread"); state->result = 1; return NULL;
    }
    state->result = same_session(state->fd, state->abi, 70);
    return NULL;
}

static int check_image_lifecycle(void) {
    int fd = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
    unsigned char query[64], abi[112];
    if (fd < 0) { fail("lifecycle_open"); return 51; }
    prep(query, 60);
    if (run_query(fd, query, abi, sizeof abi) != 0 || !valid_reply(abi, query)) {
        fail("lifecycle_queryabi"); close(fd); return 52;
    }

    /* Both failures occur before TaskSet accepts irreversible replacement.
     * The existing probe already checks successful exec revokes its old fd. */
    char *const environment[] = {NULL};
    errno = 0;
    if (syscall(SYS_execve, "/bin/hos2-queryabi",
                (char *const *)(uintptr_t)1, environment) != -1 || errno != EFAULT) {
        fail("lifecycle_exec_bad_argv"); close(fd); return 53;
    }
    if (same_session(fd, abi, 62) != 0) { close(fd); return 54; }
    candidate_puts("HEPTA_EXEC_EFAULT_SESSION_STABLE");

    char *const missing_argv[] = {(char *)"hepta-g1c-missing", NULL};
    errno = 0;
    if (syscall(SYS_execve, "/bin/hepta-g1c-missing", missing_argv, environment) != -1 ||
        errno != ENOENT) {
        fail("lifecycle_exec_missing_path"); close(fd); return 55;
    }
    if (same_session(fd, abi, 64) != 0) { close(fd); return 56; }
    candidate_puts("HEPTA_EXEC_ENOENT_SESSION_STABLE");

    struct lifecycle_thread state = {
        .fd = fd, .process_id = getpid(), .main_tid = syscall(SYS_gettid), .result = 1,
    };
    memcpy(state.abi, abi, sizeof abi);
    pthread_t thread;
    int thread_error = pthread_create(&thread, NULL, query_from_thread, &state);
    if (thread_error != 0) {
        errno = thread_error; fail("lifecycle_pthread_create"); close(fd); return 57;
    }
    thread_error = pthread_join(thread, NULL);
    if (thread_error != 0) {
        errno = thread_error; fail("lifecycle_pthread_join"); _exit(58);
    }
    if (state.result != 0) { close(fd); return 59; }
    candidate_puts("HEPTA_THREAD_SESSION_SHARED");
    if (same_session(fd, abi, 72) != 0) { close(fd); return 60; }
    close(fd);
    candidate_puts("HEPTA_NONLAST_THREAD_EXIT_SESSION_STABLE");
    return 0;
}

static int check_disabled_operations(void) {
    static const char *const markers[] = {
        "HEPTA_DISABLED_READ_USAGE_OK",
        "HEPTA_DISABLED_INSTALL_BUDGET_OK",
        "HEPTA_DISABLED_QUERY_DELIVERY_OK",
        "HEPTA_DISABLED_RETIRE_THROUGH_OK",
    };
    int fd = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
    unsigned char query[64], abi[112];
    if (fd < 0) { fail("candidate_open"); return 41; }
    prep(query, 40);
    if (run_query(fd, query, abi, sizeof abi) != 0 || !valid_reply(abi, query)) {
        fail("candidate_queryabi_only"); close(fd); return 42;
    }
    for (unsigned int opcode = 2; opcode <= 5; ++opcode) {
        unsigned char request[104] = {0}, response[128];
        unsigned int length = 64;
        prep(request, (int)(40 + opcode));
        u16le(request + 8, (uint16_t)opcode);
        u64le(request + 40, 1); /* nonzero target slot */
        u64le(request + 48, 1); /* nonzero target generation */
        if (opcode == 3) {
            length = 96;
            u32le(request + 16, 32);
            memset(request + 24, 0, 16);
            u64le(request + 24, 1); /* canonical InstallBudget sequence ID */
            u64le(request + 64, 1); /* expected revision */
            u64le(request + 72, 100000000); /* period ns */
            u64le(request + 80, 1000000); /* cap ns; reserved tail stays zero */
        } else if (opcode >= 4) {
            length = 104;
            u32le(request + 16, 40);
            memcpy(request + 64, abi + 40, 16); /* real returned boot identity */
            memcpy(request + 80, abi + 64, 16); /* real returned space identity */
            u64le(request + 96, 1); /* nonzero historical sequence */
        }
        errno = 0;
        if (run_request(fd, request, length, response, sizeof response) != -1 ||
            errno != EOPNOTSUPP) {
            fail(markers[opcode - 2]); close(fd); return (int)(43 + opcode);
        }
        candidate_puts(markers[opcode - 2]);
    }
    close(fd);
    candidate_puts("HEPTA_QUERYABI_CANDIDATE_OK disabled_operations=4");
    return 0;
}

int main(int argc, char **argv) {
    int result = original_queryabi_main(argc, argv);
    /* The exec child must finish only its original epoch check. */
    if (result != 0 ||
        (argc == 2 && strcmp(argv[1], "--exec-epoch-check") == 0)) {
        return result;
    }
    result = check_image_lifecycle();
    if (result != 0) { return result; }
    return check_disabled_operations();
}
