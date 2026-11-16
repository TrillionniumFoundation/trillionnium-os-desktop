/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef _UAPI_LINUX_P4_LSM_CONTEXT_H
#define _UAPI_LINUX_P4_LSM_CONTEXT_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define P4_LSM_CONTEXT_ABI 1U
#define P4_LSM_NETNS_FIXED (1U << 0)
#define P4_LSM_NETNS_USED  (1U << 1)

/*
 * Both commands require size=sizeof(struct p4_lsm_netns), ABI version 1,
 * an nsfs network-namespace FD, its exact inode number, and zero flags and
 * reserved. SET requires lsm_id=LSM_ID_SELINUX; GET requires lsm_id=0.
 * GET returns lsm_id and flags. SET has no output and never resets state.
 */
struct p4_lsm_netns {
	__u32 size;
	__u32 version;
	__s32 netns_fd;
	__u32 lsm_id;
	__u64 expected_ns_inum;
	__u32 flags;
	__u32 reserved;
};

#define P4_LSM_NETNS_SET _IOW(0xb7, 1, struct p4_lsm_netns)
#define P4_LSM_NETNS_GET _IOWR(0xb7, 2, struct p4_lsm_netns)

#endif /* _UAPI_LINUX_P4_LSM_CONTEXT_H */
