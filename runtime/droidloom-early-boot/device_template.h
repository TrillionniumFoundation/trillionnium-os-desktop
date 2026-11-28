// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_SELECTED_DEVICE_TEMPLATE_H
#define DROIDLOOM_SELECTED_DEVICE_TEMPLATE_H

/* Return a writable, private copy of the four stock nodes of the selected
 * CP3A release. The published image is only opened read-only. */
int droidloom_private_device_template(const char *selected_base);

/* Return a detached ext4 tree backed exclusively by that per-generation copy. */
int droidloom_open_device_bank(const char *selected_base);

int droidloom_populate_private_devices(int verified_tmpfs, int stock_node_image, const char *cohort);

#endif
