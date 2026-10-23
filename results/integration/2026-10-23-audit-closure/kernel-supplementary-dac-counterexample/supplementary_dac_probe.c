#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static int failures;

static void observe(const char *name, int actual, int expected) {
    printf("SUPPLEMENTARY_DAC_CHECK name=%s actual=%d expected=%d errno=%d\n",
           name, actual, expected, errno);
    if (actual != expected) failures++;
}

static int read_public(const char *path) {
    char value = 0;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    int result = read(fd, &value, 1) == 1 && value == 'P';
    close(fd);
    return result;
}

static void child(const char *plain, const char *nested, int supplementary) {
    gid_t member = 60002;
    if (setgroups(supplementary ? 1 : 0, supplementary ? &member : NULL) ||
        setresgid(60001, 60001, 60001) || setresuid(60001, 60001, 60001) ||
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) _exit(71);
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct caps[2] = {{0}};
    if (syscall(SYS_capget, &header, caps) || caps[0].effective || caps[1].effective ||
        caps[0].permitted || caps[1].permitted || getuid() != 60001 || getgid() != 60001 ||
        prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1) _exit(72);
    gid_t groups[4] = {0};
    int count = getgroups(4, groups);
    if (count != supplementary || (supplementary && groups[0] != member)) _exit(73);
    printf("SUPPLEMENTARY_DAC_CHILD uid=60001 gid=60001 group_count=%d group=%u caps=0 nnp=1\n",
           count, count ? (unsigned)groups[0] : 0);
    observe(supplementary ? "supplementary_file_read" : "nonmember_file_refused", read_public(plain), supplementary);
    observe(supplementary ? "supplementary_directory_search" : "nonmember_directory_refused", read_public(nested), supplementary);
    int fd = open(plain, O_WRONLY | O_CLOEXEC);
    int saved = errno;
    if (fd >= 0) close(fd);
    errno = saved;
    observe(supplementary ? "member_write_refused" : "nonmember_write_refused", fd < 0 && saved == EACCES, 1);
    fflush(stdout);
    _exit(failures ? 42 : 0);
}

static int make_public(const char *path) {
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) return -1;
    int result = write(fd, "P", 1) == 1 && fchown(fd, 0, 60002) == 0 && fchmod(fd, 0640) == 0;
    if (close(fd)) result = 0;
    return result ? 0 : -1;
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (geteuid() != 0) return 70;
    char root[] = "/tmp/supplementary-dac-XXXXXX";
    if (!mkdtemp(root) || chmod(root, 0755)) return 74;
    char plain[256], directory[256], nested[256];
    if (snprintf(plain, sizeof(plain), "%s/public", root) >= (int)sizeof(plain) ||
        snprintf(directory, sizeof(directory), "%s/search", root) >= (int)sizeof(directory) ||
        snprintf(nested, sizeof(nested), "%s/search/public", root) >= (int)sizeof(nested)) return 75;
    if (mkdir(directory, 0700) || chown(directory, 0, 60002) || chmod(directory, 0710) ||
        make_public(plain) || make_public(nested)) return 76;
    int reaped = 0;
    for (int member = 1; member >= 0; member--) {
        pid_t pid = fork();
        if (pid < 0) { failures++; break; }
        if (pid == 0) child(plain, nested, member);
        int status = 0;
        if (waitpid(pid, &status, 0) != pid) failures++;
        else {
            reaped++;
            if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) failures++;
            printf("SUPPLEMENTARY_DAC_REAP member=%d exited=%d code=%d\n", member,
                   WIFEXITED(status), WIFEXITED(status) ? WEXITSTATUS(status) : -1);
        }
    }
    if (unlink(nested) || unlink(plain) || rmdir(directory) || rmdir(root)) failures++;
    printf("SUPPLEMENTARY_DAC_COMPLETE pass=%d reaped=%d production_ready=0\n", failures == 0, reaped);
    return failures ? 42 : 0;
}
