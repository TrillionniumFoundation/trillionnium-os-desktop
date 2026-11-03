// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

static void require(int okay, const char *why)
{
    if (okay) return;
    fprintf(stderr, "MEMFD_METADATA_FAIL %s errno=%d\n", why, errno);
    exit(1);
}
static void marker(const char *text)
{
    size_t size = strlen(text);
    require(write(STDOUT_FILENO, text, size) == (ssize_t)size, "marker write");
}
int main(int argc, char **argv)
{
    require(argc == 2 && getuid() == 0 &&
            (!strcmp(argv[1], "--linux-reference") ||
             (!strcmp(argv[1], "--disposable-guest") && access("/.hepta-disposable-guest", F_OK) == 0)),
            "explicit root test environment");
    alarm(30); marker("MEMFD_METADATA_BEGIN\n");
    int fd = memfd_create("root-sealed-bootstrap", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    require(fd >= 0, "memfd create");
    struct stat st;
    require(fstat(fd, &st) == 0 && S_ISREG(st.st_mode) && st.st_uid == 0 && st.st_nlink == 0,
            "detached regular root-owned metadata");
    marker("MEMFD_METADATA_PASS detached_metadata\n");
    const char payload[] = "bounded original memfd owner";
    require(write(fd, payload, sizeof(payload)) == sizeof(payload), "initial payload");
    require(fchmod(fd, 0400) == 0, "readonly mode");
    const int seals = F_SEAL_SEAL | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_WRITE;
    require(fcntl(fd, F_ADD_SEALS, seals) == 0 && fcntl(fd, F_GET_SEALS) == seals, "four seals");
    require(fstat(fd, &st) == 0 && (st.st_mode & 07777) == 0400 && st.st_nlink == 0,
            "readonly detached sealed metadata");
    marker("MEMFD_METADATA_PASS readonly_four_seals\n");
    int alias = dup(fd); require(alias >= 0 && close(fd) == 0, "duplicate then close original");
    char buffer[sizeof(payload)];
    require(fstat(alias, &st) == 0 && st.st_nlink == 0 && st.st_uid == 0 &&
            lseek(alias, 0, SEEK_SET) == 0 && read(alias, buffer, sizeof(buffer)) == sizeof(buffer) &&
            memcmp(buffer, payload, sizeof(payload)) == 0, "alias keeps original inode and bytes");
    marker("MEMFD_METADATA_PASS duplicate_lifetime\n");
    errno = 0; require(write(alias, "x", 1) == -1 && errno == EPERM, "sealed write denied");
    errno = 0; require(ftruncate(alias, 0) == -1 && errno == EPERM, "sealed shrink denied");
    errno = 0; require(ftruncate(alias, sizeof(payload) + 1) == -1 && errno == EPERM, "sealed grow denied");
    require(fstat(alias, &st) == 0 && st.st_nlink == 0 && st.st_size == sizeof(payload) &&
            fcntl(alias, F_GET_SEALS) == seals && close(alias) == 0, "final metadata and owner close");
    marker("MEMFD_METADATA_PASS sealed_mutations_rejected\n");
    alarm(0); marker("MEMFD_METADATA_COMPLETE cases=4\n"); return 0;
}
