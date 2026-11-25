// SPDX-License-Identifier: GPL-3.0-or-later
// Compile this with selected.c, -ffunction-sections -fdata-sections,
// -Wl,--gc-sections and -lcrypto. Dead code elimination removes PID 1 startup.
// Arguments are read-only copies from the exact admitted candidate and original
// normal systemd Debian archives. This test never executes either executable.
#define main droidloom_board_init_unused_main
#include "../board_init.c"
#undef main
#include <assert.h>
#include <sys/mman.h>

static void identity_unchanged(int fd, const struct stat *before)
{
    struct stat after;
    assert(fstat(fd, &after) == 0);
    assert(after.st_dev == before->st_dev && after.st_ino == before->st_ino &&
           after.st_size == before->st_size && after.st_mode == before->st_mode &&
           after.st_uid == before->st_uid && after.st_gid == before->st_gid &&
           after.st_nlink == before->st_nlink &&
           after.st_mtim.tv_sec == before->st_mtim.tv_sec &&
           after.st_mtim.tv_nsec == before->st_mtim.tv_nsec &&
           after.st_ctim.tv_sec == before->st_ctim.tv_sec &&
           after.st_ctim.tv_nsec == before->st_ctim.tv_nsec);
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    int selected = trusted_elf(argv[1]);
    int original = trusted_elf(argv[2]);
    assert(selected >= 0 && original >= 0);
    struct stat selected_before, original_before;
    assert(fstat(selected, &selected_before) == 0);
    assert(fstat(original, &original_before) == 0);
    assert(lseek(selected, 17, SEEK_SET) == 17);
    assert(verified_systemd(selected) == 0);
    assert(lseek(selected, 0, SEEK_CUR) == 17); // verification uses the held fd/pread
    assert(verified_systemd(original) == -1 && errno == ESTALE);

    int changed = memfd_create("systemd-identity-negative", MFD_CLOEXEC);
    assert(changed >= 0);
    unsigned char buffer[32768];
    off_t offset = 0;
    while (offset < selected_before.st_size) {
        ssize_t count = pread(selected, buffer, sizeof(buffer), offset);
        assert(count > 0);
        assert(pwrite(changed, buffer, (size_t)count, offset) == count);
        offset += count;
    }
    assert(verified_systemd(changed) == 0);
    unsigned char byte;
    assert(pread(changed, &byte, 1, 4096) == 1);
    byte ^= 0x40;
    assert(pwrite(changed, &byte, 1, 4096) == 1);
    assert(verified_systemd(changed) == -1 && errno == ESTALE);
    assert(ftruncate(changed, selected_before.st_size - 1) == 0);
    assert(verified_systemd(changed) == -1 && errno == EINVAL);

    int directory = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    assert(directory >= 0);
    assert(verified_systemd(directory) == -1 && errno == EINVAL);
    close(directory);
    close(changed);
    identity_unchanged(selected, &selected_before);
    identity_unchanged(original, &original_before);
    close(selected);
    close(original);
    puts("actual board systemd verifier: selected normal ELF accepted; original, equal-size mutation, truncation and nonregular FD rejected; source identities unchanged; production_qualified=false");
    return 0;
}
