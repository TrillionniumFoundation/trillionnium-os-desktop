// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_APPARMOR_EPOCH_H
#define DROIDLOOM_APPARMOR_EPOCH_H
#include <stddef.h>

/* The first loader retains the validated kernel measurements in memory across
 * its own initial SELinux load. Only the typed, read-only final view is published. */
struct droidloom_apparmor_measurement { char bytes[2048]; size_t size; char camera[1024]; size_t camera_size; };
int droidloom_prepare_epoch_directory(int handoff);
struct droidloom_raw_profile { const unsigned char *data; size_t size; };
int droidloom_capture_apparmor_epoch(struct droidloom_apparmor_measurement *saved,
                                    const struct droidloom_raw_profile inputs[4]);
int droidloom_open_initial_selinux_status(void);
int droidloom_publish_apparmor_epoch(int handoff, int status, const char *input_sha256,
                                    const struct droidloom_apparmor_measurement *saved);
#endif
