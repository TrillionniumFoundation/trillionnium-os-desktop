/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_FS_STRUCT_H
#define _LINUX_FS_STRUCT_H

#include <linux/path.h>
#include <linux/refcount.h>
#include <linux/spinlock.h>
#include <linux/seqlock.h>

struct fs_struct {
	int users;
	/* One aggregate owner reference while the original users discipline
	 * owns this fs (also the initial unpublished-copy reference), plus
	 * independent observers. Never use refs for shared-fs access checks.
	 */
	refcount_t refs;
	seqlock_t seq;
	int umask;
	int in_exec;
	struct path root, pwd;
} __randomize_layout;

extern struct kmem_cache *fs_cachep;

extern void exit_fs(struct task_struct *);
extern void set_fs_root(struct fs_struct *, const struct path *);
extern void set_fs_pwd(struct fs_struct *, const struct path *);
extern struct fs_struct *copy_fs_struct(struct fs_struct *);
/* Drop the original aggregate ownership, after its last users slot
 * or when discarding an unpublished copy. This may leave observers alive.
 */
extern void free_fs_struct(struct fs_struct *);

/* Lifetime only: neither function reads or changes users or in_exec.
 * get requires a reference the caller already owns, or task_lock followed
 * by fs->seq with an attached, positively counted task fs. No resurrection.
 * Final put releases paths and may sleep; never call it under a spinlock.
 */
extern void get_fs_struct_ref(struct fs_struct *);
extern void put_fs_struct_ref(struct fs_struct *);
extern int unshare_fs_struct(void);

static inline void get_fs_root(struct fs_struct *fs, struct path *root)
{
	read_seqlock_excl(&fs->seq);
	*root = fs->root;
	path_get(root);
	read_sequnlock_excl(&fs->seq);
}

static inline void get_fs_pwd(struct fs_struct *fs, struct path *pwd)
{
	read_seqlock_excl(&fs->seq);
	*pwd = fs->pwd;
	path_get(pwd);
	read_sequnlock_excl(&fs->seq);
}

extern bool current_chrooted(void);

#endif /* _LINUX_FS_STRUCT_H */
