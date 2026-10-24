/* Guest-only launcher. Fleet state and identities belong to the unchanged
 * original Rust FleetRegistry/Supervisor fixture, never to this launcher. */
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

static const char *fixture = "/payload/bin/hepta-original-observer-probe";

/* Output files live on a fresh, bounded guest state disk. The host QEMU
 * deadline bounds child execution; emission refuses oversized diagnostics. */
static int emit(const char *name, const char *file, const char *nonce, size_t limit) {
    struct stat info;
    unsigned char data[4096];
    int fd = open(file, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return -1;
    if (fstat(fd, &info) != 0 || !S_ISREG(info.st_mode) || info.st_size < 0 ||
        (unsigned long long)info.st_size > limit) {
        close(fd);
        return -1;
    }
    printf("HEPTA_RUNTIME_%s nonce=%s hex=", name, nonce);
    size_t used = 0;
    for (;;) {
        ssize_t count = read(fd, data, sizeof(data));
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) { close(fd); return -1; }
        if (count == 0) break;
        used += (size_t)count;
        if (used > limit) { close(fd); return -1; }
        for (ssize_t index = 0; index < count; ++index) printf("%02x", data[index]);
    }
    close(fd);
    putchar('\n');
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
            (char *)fixture, "/payload/bin/codex-hepta-agentd",
            "/payload/bin/hepta-observe", "/state/probe", "0", NULL
        };
        /* The original driver supplies registered HEPTA_* and CODEX_* values.
         * No host credentials, provider settings, identity, or authority enter. */
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
