// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_BOARD_POLICY_H
#define DROIDLOOM_BOARD_POLICY_H
#include <sys/types.h>
int droidloom_board_activate_policy(gid_t observer_gid, const char *cohort);
int droidloom_board_verify_policy_epoch(void);
#endif
