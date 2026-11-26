// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_LINUX_RUN_LABEL_H
#define DROIDLOOM_LINUX_RUN_LABEL_H

#include <sys/types.h>
#include <sys/stat.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

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
struct droidloom_linux_credentials {
    struct droidloom_linux_run root;
    struct droidloom_linux_run systemd;
    struct droidloom_linux_run staging;
};
struct droidloom_linux_journal_store {
    struct droidloom_linux_run log;
    struct droidloom_linux_run journal;
};
int droidloom_hold_ubuntu_log(const struct droidloom_linux_run *run, struct droidloom_linux_journal_store *store);
int droidloom_label_ubuntu_log(const struct droidloom_linux_journal_store *store);
void droidloom_close_ubuntu_log(struct droidloom_linux_journal_store *store);
int droidloom_hold_ubuntu_credentials(const struct droidloom_linux_run *run,
                                     struct droidloom_linux_credentials *credentials);
int droidloom_label_ubuntu_credentials(const struct droidloom_linux_credentials *credentials);
void droidloom_close_ubuntu_credentials(struct droidloom_linux_credentials *credentials);
int droidloom_hold_linux_init_scope(struct droidloom_linux_init_scope *held);
int droidloom_label_linux_init_scope(const struct droidloom_linux_init_scope *held);
void droidloom_close_linux_init_scope(struct droidloom_linux_init_scope *held);

int droidloom_hold_linux_shm(struct droidloom_linux_run *out);
int droidloom_label_linux_shm(const struct droidloom_linux_run *held);
int droidloom_hold_linux_run(struct droidloom_linux_run *run);
int droidloom_label_private_device(const struct droidloom_linux_run *held);
int droidloom_label_linux_run(const struct droidloom_linux_run *run);
int droidloom_hold_linux_udev(const struct droidloom_linux_run *run, struct droidloom_linux_run *udev);
int droidloom_label_linux_udev(const struct droidloom_linux_run *udev);
int droidloom_hold_linux_udev_data(const struct droidloom_linux_run *udev,
                                  struct droidloom_linux_run *data);
int droidloom_label_linux_udev_data(const struct droidloom_linux_run *data);
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

/* All 65 original Linux VT nodes remain writable devtmpfs inodes. */
#define DROIDLOOM_LINUX_VT_COUNT 65U
struct droidloom_linux_vt {
    int fd;
    int label_kind;
    struct stat identity;
};
struct droidloom_linux_vts {
    int dev;
    int proc_fds;
    uint64_t dev_mount;
    uint64_t proc_mount;
    struct stat dev_identity;
    struct stat proc_identity;
    size_t held_count;
    bool prepared;
    struct droidloom_linux_vt nodes[DROIDLOOM_LINUX_VT_COUNT];
};
int droidloom_prepare_linux_vts(struct droidloom_linux_vts *held);
int droidloom_verify_linux_vts(const struct droidloom_linux_vts *held);
void droidloom_close_linux_vts(struct droidloom_linux_vts *held);
#endif
