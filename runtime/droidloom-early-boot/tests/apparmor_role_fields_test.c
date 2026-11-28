// SPDX-License-Identifier: GPL-3.0-or-later
#include "apparmor_epoch.c"
#include <assert.h>

int main(void)
{
    unsigned checks = 0;
    for (size_t i = 0; i < DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES; ++i) {
        const struct droidloom_board_apparmor_profile *role = &droidloom_board_apparmor_profiles[i];
        assert(board_profile_fields(i, role->name, "enforce", role->kernel_sha256) == 0); ++checks;
        errno = 0;
        assert(board_profile_fields(i, role->name, "complain", role->kernel_sha256) == -1 && errno == EBADMSG); ++checks;
        errno = 0;
        assert(board_profile_fields(i, "foreign-profile", "enforce", role->kernel_sha256) == -1 && errno == EBADMSG); ++checks;
        char digest[65]; memcpy(digest, role->kernel_sha256, sizeof(digest));
        digest[0] = digest[0] == '0' ? '1' : '0';
        errno = 0;
        assert(board_profile_fields(i, role->name, "enforce", digest) == -1 && errno == EBADMSG); ++checks;
    }
    errno = 0;
    assert(board_profile_fields(DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES, "foreign-profile", "enforce", "") == -1 && errno == EBADMSG); ++checks;
    printf("early loaded board role field checks: %u; runtime custody stays three profiles\n", checks);
    return 0;
}
