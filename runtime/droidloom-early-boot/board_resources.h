// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_BOARD_RESOURCES_H
#define DROIDLOOM_BOARD_RESOURCES_H
int droidloom_board_deliver_root(int pidfd, int userns, int mountns, int child_root, int detached_root);
int droidloom_board_enter(int held_root);
#endif
