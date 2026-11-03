/* Guest-only launcher for the unchanged original CognitiveStore API fixture.
 * No SQL, production authority, or replacement owner enters this launcher. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static const char *fixture = "/payload/bin/hepta-original-cognitive-store-probe";

/* Output files live on a fresh, bounded guest state disk. The host QEMU
 * deadline bounds child execution; emission refuses oversized diagnostics. */
static int emit(const char *name, const char *file, const char *nonce, size_t limit) {
    struct stat info;
    unsigned char data[4096];
    int fd = open(file, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return -1;
    if (limit > 512 * 1024 || fstat(fd, &info) != 0 || !S_ISREG(info.st_mode) ||
        info.st_size < 0 || (unsigned long long)info.st_size > limit) {
        close(fd);
        return -1;
    }
    /* Finish every file read before starting the serial record. Otherwise a
     * kernel syscall log can split the hex line at the next buffered read.
     * Bound allocation and handle legitimate partial TTY writes. An I/O error
     * remains a visible failure rather than accepting a damaged record. */
    char *record = malloc(128 + 2 * limit);
    if (record == NULL) { close(fd); return -1; }
    int prefix = snprintf(record, 128, "HEPTA_RUNTIME_%s nonce=%s hex=", name, nonce);
    if (prefix <= 0 || prefix >= 128) { free(record); close(fd); return -1; }
    size_t length = (size_t)prefix, used = 0;
    const char digits[] = "0123456789abcdef";
    for (;;) {
        ssize_t count = read(fd, data, sizeof(data));
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) { free(record); close(fd); return -1; }
        if (count == 0) break;
        used += (size_t)count;
        if (used > limit) { free(record); close(fd); return -1; }
        for (ssize_t index = 0; index < count; ++index) {
            record[length++] = digits[data[index] >> 4];
            record[length++] = digits[data[index] & 15];
        }
    }
    close(fd);
    if (used != (size_t)info.st_size) { free(record); return -1; }
    record[length++] = '\n';
    size_t sent = 0;
    while (sent < length) {
        ssize_t count = write(STDOUT_FILENO, record + sent, length - sent);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { free(record); return -1; }
        sent += (size_t)count;
    }
    free(record);
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2 || strlen(argv[1]) != 64 ||
        strspn(argv[1], "0123456789abcdef") != 64) return 20;
    const char *nonce = argv[1];
    umask(0077);
    /* mkdir must fail if the supposedly fresh image already contains state. */
    if (mkdir("/state/probe", 0700) != 0 || mkdir("/state/tmp", 0700) != 0) return 21;
    printf("HEPTA_RUNTIME_BEGIN nonce=%s\n", nonce);
    fflush(stdout);
    pid_t pid = fork();
    if (pid < 0) return 22;
    if (pid == 0) {
        int out = open("/state/runtime.stdout", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        int err = open("/state/runtime.stderr", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        int in = open("/dev/null", O_RDONLY | O_NOFOLLOW);
        if (out < 0 || err < 0 || in < 0) _exit(125);
        if (dup2(in, STDIN_FILENO) < 0 || dup2(out, STDOUT_FILENO) < 0 ||
            dup2(err, STDERR_FILENO) < 0) _exit(125);
        if (in > 2) close(in);
        if (out > 2) close(out);
        if (err > 2) close(err);
        if (chdir("/state/probe") != 0) _exit(125);
        char *child_argv[] = {
            (char *)fixture, "probe", "/state/probe/store", NULL
        };
        /* No host credentials, provider settings, or authority enter. */
        char *environment[] = {
            "PATH=/bin:/sbin", "HOME=/state/probe", "TMPDIR=/state/tmp",
            "LANG=C", "LC_ALL=C", "RUST_BACKTRACE=0", NULL
        };
        execve(fixture, child_argv, environment);
        int saved_errno = errno;
        dprintf(STDERR_FILENO, "HEPTA_RUNTIME_EXECVE_ERROR errno=%d\n", saved_errno);
        _exit(127);
    }
    int status;
    pid_t waited;
    do { waited = waitpid(pid, &status, 0); } while (waited < 0 && errno == EINTR);
    if (waited != pid) return 23;
    if (emit("STDOUT", "/state/runtime.stdout", nonce, 512 * 1024) != 0 ||
        emit("STDERR", "/state/runtime.stderr", nonce, 64 * 1024) != 0) return 24;
    if (WIFEXITED(status)) {
        printf("HEPTA_RUNTIME_CHILD nonce=%s kind=exit code=%d\n", nonce, WEXITSTATUS(status));
    } else if (WIFSIGNALED(status)) {
        printf("HEPTA_RUNTIME_CHILD nonce=%s kind=signal code=%d\n", nonce, WTERMSIG(status));
    } else return 25;
    /* A nonzero fixture exit is visible even if the serial oracle is absent. */
    return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : 26;
}
