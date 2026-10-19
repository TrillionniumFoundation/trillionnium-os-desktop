#define _GNU_SOURCE
/* SPDX-License-Identifier: MPL-2.0 */
/* A05 minimum repro: shebang final ELF vs script-valued /proc/self/exe.
 * Never treats merely printing /proc/self/exe as a kernel-compatibility pass.
 * Tests original Linux; guest comparison is a separate required experiment.
 */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static int check_interpreter(const char *self) {
    struct stat executable, proc_exe;
    if (stat(self, &executable) != 0 || stat("/proc/self/exe", &proc_exe) != 0) return 71;
    if (executable.st_dev != proc_exe.st_dev || executable.st_ino != proc_exe.st_ino) return 72;
    char path[PATH_MAX], resolved[PATH_MAX];
    ssize_t size = readlink("/proc/self/exe", path, sizeof(path)-1);
    if (size < 0) return 73;
    path[size] = '\0';
    if (realpath(self, resolved) == NULL) return 74;
    return strcmp(path, resolved) == 0 ? 0 : 75;
}

int main(int argc, char **argv) {
    if (argc >= 2 && strcmp(argv[1], "--interpreter") == 0) {
        return check_interpreter(argv[0]);
    }
    if (argc != 2) return 64;
    char exe[PATH_MAX], script[PATH_MAX], shebang[PATH_MAX+64];
    if (realpath(argv[0], exe) == NULL) return 65;
    if (snprintf(script, sizeof(script), "%s/a04-interpreter.sh", argv[1]) >= (int)sizeof(script)) return 66;
    if (snprintf(shebang, sizeof(shebang), "#!%s --interpreter\n", exe) >= (int)sizeof(shebang)) return 67;
    /* Linux shebang must fit the interpreter path. Avoid relying on truncation. */
    if (strlen(shebang) > 255) return 68;
    int fd = open(script, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0700);
    if (fd < 0) return 69;
    ssize_t length = (ssize_t)strlen(shebang);
    if (write(fd, shebang, (size_t)length) != length || close(fd) != 0) {
        unlink(script);
        return 70;
    }
    pid_t child = fork();
    if (child < 0) { unlink(script); return 76; }
    if (child == 0) {
        execl(script, script, (char *)NULL);
        _exit(127);
    }
    int status = 0;
    int result = waitpid(child, &status, 0);
    if (unlink(script) != 0) return 77;
    if (result != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        fprintf(stderr, "proc self exe shebang interpreter mismatch; child_status=%d\n",
                WIFEXITED(status) ? WEXITSTATUS(status) : -1);
        return 78;
    }
    puts("{\"ok\":true,\"shebang_interpreter_elf\":true,\"proc_self_exe_is_interpreter\":true,\"child_reaped\":true,\"script_unlinked\":true}");
    return 0;
}
