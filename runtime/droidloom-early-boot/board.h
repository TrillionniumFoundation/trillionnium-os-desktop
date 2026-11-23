// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_BOOT_BOARD_H
#define DROIDLOOM_BOOT_BOARD_H
#include <stdint.h>
#include <sys/types.h>

struct droidloom_early_plan {
    char selection_sha256[65];
    char base_cohort_sha256[65];
    uint32_t host_uid, uid_start, uid_count, gid_start, gid_count;
};

int droidloom_early_read_plan(struct droidloom_early_plan *plan);
int droidloom_post_switch_read_plan(struct droidloom_early_plan *plan);
int droidloom_verified_elf(int fd, off_t expected_size, const unsigned char expected[32]);
int droidloom_early_original_elf(int fd);

/* Executed by the new PID1. Consume the verified root within its own namespaces,
 * apply the board's normal process filesystems, device and cgroup isolation,
 * and pivot off the Ubuntu root. The caller retains ownership of held_root. */
int droidloom_board_enter(int held_root);
#endif
