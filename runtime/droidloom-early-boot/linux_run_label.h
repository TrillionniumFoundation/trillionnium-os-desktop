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


struct droidloom_linux_init_scope {
    struct droidloom_linux_run root;
    struct droidloom_linux_run scope;
    struct droidloom_linux_run procs;
    struct droidloom_linux_run controllers;
    struct droidloom_linux_run system_slice;
    struct droidloom_linux_run root_membership;
    struct droidloom_linux_run root_subtree_control;
};
int droidloom_hold_linux_init_scope(struct droidloom_linux_init_scope *held);
int droidloom_label_linux_init_scope(const struct droidloom_linux_init_scope *held);
void droidloom_close_linux_init_scope(struct droidloom_linux_init_scope *held);

int droidloom_hold_linux_shm(struct droidloom_linux_run *out);
int droidloom_label_linux_shm(const struct droidloom_linux_run *held);
int droidloom_hold_linux_run(struct droidloom_linux_run *run);
int droidloom_label_private_device(const struct droidloom_linux_run *held);
int droidloom_label_linux_run(const struct droidloom_linux_run *run);
int droidloom_verify_linux_run(const struct droidloom_linux_run *run);

struct droidloom_readiness_paths {
    struct droidloom_linux_run handoff;
    struct droidloom_linux_run readiness;
};

int droidloom_hold_readiness_paths(const struct droidloom_linux_run *run,
                                  gid_t observer_gid, struct droidloom_readiness_paths *paths);
int droidloom_label_readiness_paths(const struct droidloom_readiness_paths *paths);

int droidloom_project_linux_standard_devices(void);
int droidloom_linux_console_descriptors(void);
#endif
