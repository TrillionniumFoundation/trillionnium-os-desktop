// SPDX-License-Identifier: GPL-3.0-or-later
#include "board.h"
#include "board_policy.h"

#include <errno.h>
#include <stdio.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    (void)argv;
    if (argc != 1 || geteuid() != 0)
        return 1;
    struct droidloom_early_plan plan;
    int selected = droidloom_early_read_plan(&plan);
    if (selected < 0) {
        perror("Droidloom early board selection");
        return 1;
    }
    if (selected == 0)
        return 0;
    if (droidloom_board_activate_policy((gid_t)(plan.gid_start + 9999), plan.base_cohort_sha256) < 0) {
        perror("Droidloom early shared-kernel policy");
        return 1;
    }
    return 0;
}
