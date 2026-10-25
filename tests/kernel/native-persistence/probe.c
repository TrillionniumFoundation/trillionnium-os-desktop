// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define STORE "/mnt/hepta-store"
#define SOURCE STORE "/native-root"
#define TARGET "/var/lib/hepta-native"
#define AGENT STORE "/agent-owner"
#define CONSUMER STORE "/consumer-local"
static const char *nonce;
static unsigned failures;
static void check(int ok, const char *name) {
    printf("{\"check\":\"%s\",\"passed\":%s,\"errno\":%d}\n", name, ok ? "true" : "false", errno);
    if (!ok) ++failures;
}
static int make_dir(const char *path, mode_t mode) {
    return mkdir(path, mode) == 0 || errno == EEXIST;
}
static int sync_dir(const char *path) {
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 0;
    int ok = fsync(fd) == 0; close(fd); return ok;
}
static int read_file(const char *path, char *out, size_t size) {
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return -1;
    ssize_t n = read(fd, out, size - 1);
    char extra; ssize_t tail = read(fd, &extra, 1); close(fd);
    if (n < 0 || tail != 0) return -1;
    out[n] = 0; return (int)n;
}
static int boot_id(char out[38]) {
    if (read_file("/proc/sys/kernel/random/boot_id", out, 38) != 37 || out[36] != '\n') return 0;
    for (unsigned i = 0; i < 36; ++i) {
        if (i == 8 || i == 13 || i == 18 || i == 23) { if (out[i] != '-') return 0; }
        else if (!((out[i] >= '0' && out[i] <= '9') || (out[i] >= 'a' && out[i] <= 'f'))) return 0;
    }
    if (out[14] != '4' || !strchr("89ab", out[19])) return 0;
    out[36] = 0; return 1;
}
static int atomic_file(const char *directory, const char *contents) {
    int dir = open(directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (dir < 0) return 0;
    int fd = openat(dir, ".pending", O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) { close(dir); return 0; }
    size_t len = strlen(contents), done = 0;
    while (done < len) {
        ssize_t n = write(fd, contents + done, len - done);
        if (n <= 0) { close(fd); close(dir); return 0; }
        done += (size_t)n;
    }
    int ok = fsync(fd) == 0;
    if (close(fd) != 0) ok = 0;
    if (ok) ok = renameat(dir, ".pending", dir, "fixture-data") == 0;
    if (ok) ok = fsync(dir) == 0;
    close(dir); return ok;
}
static int exact_file(const char *directory, const char *contents) {
    char path[256], actual[512]; struct stat st;
    snprintf(path, sizeof path, "%s/fixture-data", directory);
    if (read_file(path, actual, sizeof actual) < 0 || strcmp(actual, contents)) return 0;
    if (stat(path, &st) != 0 || !S_ISREG(st.st_mode) || (st.st_mode & 0777) != 0600) return 0;
    snprintf(path, sizeof path, "%s/.pending", directory);
    errno = 0; return lstat(path, &st) == -1 && errno == ENOENT;
}
static int denied_directory(const char *path) {
    errno = 0; int fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (fd >= 0) { close(fd); return 0; }
    return errno == EACCES;
}
static int drop_to(uid_t uid) {
    return setgroups(0, NULL) == 0 && setgid(uid) == 0 && setuid(uid) == 0
        && getuid() == uid && geteuid() == uid && getgid() == uid;
}
static void check_children(int phase, const char *expected) {
    pid_t child = fork(); int status;
    if (child == 0) {
        failures = 0;
        check(drop_to(60002), "original_agent_uid_has_no_root_credentials");
        if (failures) _exit(1);
        check(denied_directory(SOURCE) && denied_directory(TARGET), "agent_uid_cannot_read_root_source_or_bind");
        if (phase == 1) {
            check(atomic_file(AGENT, expected), "agent_directory_file_fsync_rename_dirfsync");
            check(atomic_file(CONSUMER, expected), "consumer_directory_file_fsync_rename_dirfsync");
        }
        check(exact_file(AGENT, expected), "agent_uid_reads_own_exact_durable_bytes");
        check(exact_file(CONSUMER, expected), "consumer_uid_reads_own_exact_durable_bytes");
        _exit(failures ? 1 : 0);
    }
    check(child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "agent_uid_child_completed");
    child = fork();
    if (child == 0) {
        failures = 0;
        check(drop_to(60001), "workload_uid_has_no_root_credentials");
        if (failures) _exit(1);
        check(denied_directory(SOURCE) && denied_directory(TARGET), "workload_uid_cannot_read_root_source_or_bind");
        check(denied_directory(AGENT) && denied_directory(CONSUMER), "workload_uid_cannot_read_agent_or_consumer_state");
        _exit(failures ? 1 : 0);
    }
    check(child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "workload_uid_child_completed");
}
static int owned_mode(const char *path, uid_t uid) {
    struct stat st;
    return lstat(path, &st) == 0 && S_ISDIR(st.st_mode) && st.st_uid == uid && st.st_gid == uid
        && (st.st_mode & 0777) == 0700;
}
static void mount_identity(void) {
    struct stat source = {0}, target = {0};
    check(stat(SOURCE, &source) == 0 && stat(TARGET, &target) == 0
          && source.st_dev == target.st_dev && source.st_ino == target.st_ino,
          "source_and_bind_share_original_device_and_inode");
    FILE *file = fopen("/proc/self/mountinfo", "r");
    check(file != NULL, "read_actual_proc_mountinfo");
    if (!file) return;
    char line[4096]; unsigned matches = 0; int valid = 0;
    while (fgets(line, sizeof line, file)) {
        char original[4096]; memcpy(original, line, strlen(line) + 1);
        char *fields[64], *state = NULL; unsigned count = 0;
        for (char *p = strtok_r(line, " \n", &state); p && count < 64; p = strtok_r(NULL, " \n", &state)) fields[count++] = p;
        if (count < 10 || strcmp(fields[4], TARGET)) continue;
        ++matches; unsigned maj, min; unsigned sep = 6;
        while (sep < count && strcmp(fields[sep], "-")) ++sep;
        valid = sscanf(fields[2], "%u:%u", &maj, &min) == 2
            && maj == major(source.st_dev) && min == minor(source.st_dev)
            && !strcmp(fields[3], "/native-root") && sep + 3 < count
            && !strcmp(fields[sep + 1], "ext2") && !strcmp(fields[sep + 2], "/dev/vda");
        printf("HEPTA_NATIVE_MOUNTINFO %s", original);
    }
    fclose(file);
    check(matches == 1 && valid, "mountinfo_fifth_column_and_source_device_match_bind");
    if (matches == 1 && valid)
        printf("{\"mount_identity\":true,\"device\":%llu,\"inode\":%llu,\"mountpoint\":\"%s\"}\n",
               (unsigned long long)source.st_dev, (unsigned long long)source.st_ino, TARGET);
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc != 3 || strlen(argv[1]) != 32 || (strcmp(argv[2], "first") && strcmp(argv[2], "second"))) return 2;
    nonce = argv[1];
    for (unsigned i = 0; i < 32; ++i) if (!strchr("0123456789abcdef", nonce[i])) return 2;
    int phase = !strcmp(argv[2], "first") ? 1 : 2;
    char current[38], previous[38] = {0}, contents[512], actual[512];
    check(getuid() == 0 && geteuid() == 0, "fixture_setup_runs_as_guest_root");
    check(boot_id(current), "read_current_original_kernel_boot_id");
    check(make_dir("/mnt", 0755) && make_dir(STORE, 0755) && make_dir("/var", 0755)
          && make_dir("/var/lib", 0755) && make_dir(TARGET, 0700), "create_guest_mountpoints");
    check(mount("/dev/vda", STORE, "ext2", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) == 0,
          "mount_generated_persistent_ext2");
    if (failures) return 1;
    if (phase == 1) {
        check(mkdir(SOURCE, 0700) == 0 && mkdir(AGENT, 0700) == 0 && mkdir(CONSUMER, 0700) == 0,
              "create_distinct_fresh_durable_directories");
        check(chown(AGENT, 60002, 60002) == 0 && chown(CONSUMER, 60002, 60002) == 0,
              "assign_original_agent_uid_directories");
        check(sync_dir(SOURCE) && sync_dir(AGENT) && sync_dir(CONSUMER) && sync_dir(STORE),
              "fsync_directory_ownership_and_parent_entries");
    }
    check(owned_mode(SOURCE, 0), "original_root_source_is_root_0700");
    check(owned_mode(AGENT, 60002) && owned_mode(CONSUMER, 60002), "separate_agent_and_consumer_roots_are_60002_0700");
    check(mount(SOURCE, TARGET, NULL, MS_BIND, NULL) == 0, "bind_original_root_directory");
    if (failures) return 1;
    mount_identity();
    if (phase == 1) {
        snprintf(contents, sizeof contents, "nonce=%s\nfirst_boot=%s\npayload=original-ext2-durable-fixture\n", nonce, current);
        check(atomic_file(TARGET, contents), "root_file_fsync_then_rename_then_directory_fsync");
    } else {
        int n = read_file(TARGET "/fixture-data", actual, sizeof actual);
        check(n > 0 && sscanf(actual, "nonce=%*32[0-9a-f]\nfirst_boot=%36[0-9a-f-]", previous) == 1,
              "read_previous_boot_from_actual_disk_file");
        snprintf(contents, sizeof contents, "nonce=%s\nfirst_boot=%s\npayload=original-ext2-durable-fixture\n", nonce, previous);
        check(n > 0 && !strcmp(contents, actual), "cross_boot_root_bytes_match_original_nonce_and_payload");
        check(previous[0] && strcmp(previous, current), "fresh_boot_identity_differs_from_durable_original");
    }
    check(exact_file(SOURCE, contents) && exact_file(TARGET, contents), "source_and_bind_read_same_exact_durable_file");
    check_children(phase, contents);
    if (failures) return 1;
    if (phase == 1) {
        printf("HEPTA_NATIVE_DURABLE nonce=%s boot_id=%s\n", nonce, current);
        for (;;) pause();
    }
    printf("HEPTA_NATIVE_REOPEN nonce=%s old_boot_id=%s new_boot_id=%s\n", nonce, previous, current);
    check(umount(TARGET) == 0 && umount(STORE) == 0, "reopened_fixture_unmounts_cleanly");
    return failures ? 1 : 0;
}
