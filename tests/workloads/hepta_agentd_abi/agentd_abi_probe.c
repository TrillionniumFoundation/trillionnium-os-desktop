/* Isolated-guest launcher only. It never constructs fleet state or grants. */
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

static const char *binary = "/payload/bin/codex-hepta-agentd";

static int emit(const char *name, const char *file, const char *nonce) {
    unsigned char data[4097];
    size_t used = 0;
    int fd = open(file, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return -1;
    while (used < sizeof(data)) {
        ssize_t n = read(fd, data + used, sizeof(data) - used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { close(fd); return -1; }
        if (n == 0) break;
        used += (size_t)n;
    }
    close(fd);
    if (used > 4096) return -1;
    printf("HEPTA_ABI_%s nonce=%s hex=", name, nonce);
    for (size_t i = 0; i < used; ++i) printf("%02x", data[i]);
    putchar('\n');
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2 || strlen(argv[1]) != 64 ||
        strspn(argv[1], "0123456789abcdef") != 64) return 20;
    const char *nonce = argv[1];
    printf("HEPTA_ABI_BEGIN nonce=%s\n", nonce);
    fflush(stdout);
    pid_t pid = fork();
    if (pid < 0) return 21;
    if (pid == 0) {
        int out = open("/tmp/agentd-abi.stdout", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        int err = open("/tmp/agentd-abi.stderr", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        int in = open("/dev/null", O_RDONLY | O_NOFOLLOW);
        if (out < 0 || err < 0 || in < 0) _exit(125);
        if (dup2(in, STDIN_FILENO) < 0 || dup2(out, STDOUT_FILENO) < 0 ||
            dup2(err, STDERR_FILENO) < 0) _exit(125);
        if (in > 2) close(in);
        if (out > 2) close(out);
        if (err > 2) close(err);
        char *child_argv[] = {(char *)binary, NULL};
        char *empty_environment[] = {NULL};
        execve(binary, child_argv, empty_environment);
        int saved_errno = errno;
        dprintf(STDERR_FILENO, "HEPTA_ABI_EXECVE_ERROR errno=%d\n", saved_errno);
        _exit(127);
    }
    int status;
    pid_t waited;
    do { waited = waitpid(pid, &status, 0); } while (waited < 0 && errno == EINTR);
    if (waited != pid) return 22;
    if (emit("STDOUT", "/tmp/agentd-abi.stdout", nonce) != 0 ||
        emit("STDERR", "/tmp/agentd-abi.stderr", nonce) != 0) return 23;
    if (WIFEXITED(status)) {
        printf("HEPTA_ABI_CHILD nonce=%s kind=exit code=%d\n", nonce, WEXITSTATUS(status));
    } else if (WIFSIGNALED(status)) {
        printf("HEPTA_ABI_CHILD nonce=%s kind=signal code=%d\n", nonce, WTERMSIG(status));
    } else return 24;
    return 0;
}
