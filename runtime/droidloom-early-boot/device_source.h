// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_EARLY_DEVICE_SOURCE_H
#define DROIDLOOM_EARLY_DEVICE_SOURCE_H

#include <stdint.h>
#include <sys/types.h>

#define DROIDLOOM_DEVICE_SLOT "/run/droidloom-early/private-dev"
struct droidloom_device_identity {
    dev_t device;
    ino_t inode;
    uint64_t mount;
};

/* Called only by the single-threaded board executables before loading policy.
 * The original Linux mount namespace is restored before the descriptor returns. */
int droidloom_hold_device_source(int create, struct droidloom_device_identity *identity);

int droidloom_prepare_device_source(int bank, const char *cohort, struct droidloom_device_identity *identity);

#endif
