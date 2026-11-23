// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_EARLY_CUSTODY_H
#define DROIDLOOM_EARLY_CUSTODY_H
#include <sys/types.h>

/* The board first stage must have created the still-suspended original Android
 * task itself, using clone with CLONE_NEWPID | CLONE_PIDFD. The legitimate
 * board preparation owns that child's isolated mounts, network and ID lease.
 * Ubuntu's final root must already be mounted. This call measures its actual
 * root-selected private release and binds it to the digest of the release the caller actually prepared. */
int droidloom_publish_selected_child(pid_t child,int clone_pidfd,const char *prepared_sha256);
#endif
