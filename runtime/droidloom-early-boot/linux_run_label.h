// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_LINUX_RUN_LABEL_H
#define DROIDLOOM_LINUX_RUN_LABEL_H

#include <sys/types.h>

/* Owned by the board's policy installer. Keep the same open directory across
 * the initial policy load and close it before the handoff to Linux PID 1. */
struct droidloom_linux_run {
    int fd;
    dev_t device;
    ino_t inode;
};

int droidloom_hold_linux_run(struct droidloom_linux_run *run);
int droidloom_label_linux_run(const struct droidloom_linux_run *run);
int droidloom_verify_linux_run(const struct droidloom_linux_run *run);

#endif
