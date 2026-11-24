/* SPDX-License-Identifier: LGPL-2.0-or-later */
#include "config.h"
#include "gdm-dynamic-files.h"
#include "gdm-environment-file.h"
#include "gdm-file-utils.h"
#include <fcntl.h>
#include <grp.h>
#include <poll.h>
#include <stdio.h>
#include <glib/gstdio.h>
#include <linux/capability.h>
#include <pwd.h>
#include <sys/fsuid.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

/* Link wrappers affect only this test ELF. The normal daemon uses the same
 * uninstrumented static-library object and normal libc calls. */
static int race_kind, race_send = -1, race_ack = -1;
static dev_t race_device;
static ino_t race_inode;
static void byte_wait (int fd)
{
        struct pollfd p = { .fd = fd, .events = POLLIN };
        char value;
        g_assert_cmpint (poll (&p, 1, 5000), ==, 1);
        g_assert_cmpint (read (fd, &value, 1), ==, 1);
}
static void trigger_race (void)
{
        race_kind = 0;
        g_assert_cmpint (write (race_send, "x", 1), ==, 1);
        byte_wait (race_ack);
}
int __real_renameat2 (int, const char *, int, const char *, unsigned int);
int __wrap_renameat2 (int a, const char *an, int b, const char *bn, unsigned int flags)
{
        if ((race_kind == 1 || race_kind == 2) && flags == RENAME_EXCHANGE)
                trigger_race ();
        return __real_renameat2 (a, an, b, bn, flags);
}
static void source_read_race (int fd)
{
        struct stat st;
        if (race_kind == 3 && fstat (fd, &st) == 0 &&
            st.st_dev == race_device && st.st_ino == race_inode)
                trigger_race ();
}
ssize_t __real_pread (int, void *, size_t, off_t);
ssize_t __wrap_pread (int fd, void *buffer, size_t bytes, off_t offset)
{
        source_read_race (fd);
        return __real_pread (fd, buffer, bytes, offset);
}
/* Ubuntu's unchanged large-file/FORTIFY build uses these two libc entry
 * points. Keep the original check and full arguments in the test wrapper. */
ssize_t __real_pread64 (int, void *, size_t, off64_t);
ssize_t __wrap_pread64 (int fd, void *buffer, size_t bytes, off64_t offset)
{
        source_read_race (fd);
        return __real_pread64 (fd, buffer, bytes, offset);
}
ssize_t __real___pread64_chk (int, void *, size_t, off64_t, size_t);
ssize_t __wrap___pread64_chk (int fd, void *buffer, size_t bytes, off64_t offset, size_t size)
{
        source_read_race (fd);
        return __real___pread64_chk (fd, buffer, bytes, offset, size);
}
int __real_fchownat (int, const char *, uid_t, gid_t, int);
int __wrap_fchownat (int fd, const char *name, uid_t uid, gid_t gid, int flags)
{
        if (race_kind == 4 && uid == GREETER_UID_MIN + 1)
                trigger_race ();
        return __real_fchownat (fd, name, uid, gid, flags);
}
static gint stop_peer, samples;
static gpointer peer (gpointer unused)
{
        (void) unused;
        while (!g_atomic_int_get (&stop_peer)) {
                g_assert_cmpuint (setfsuid ((uid_t) -1), ==, 0);
                g_assert_cmpuint (setfsgid ((gid_t) -1), ==, 0);
                g_atomic_int_inc (&samples);
                g_thread_yield ();
        }
        return NULL;
}
static guint32 caps (gboolean missing_setuid)
{
        return (1U << CAP_CHOWN) | (1U << CAP_FOWNER) | (1U << CAP_SETGID) |
               (missing_setuid ? 0 : (1U << CAP_SETUID));
}
static void limited_caps (gboolean missing_setuid)
{
        struct __user_cap_header_struct header = { .version = _LINUX_CAPABILITY_VERSION_3 };
        struct __user_cap_data_struct value[2] = {{0}, {0}};
        value[0].effective = value[0].permitted = caps (missing_setuid);
        g_assert_cmpint (syscall (SYS_capset, &header, value), ==, 0);
}
static void check_identity (gboolean missing_setuid)
{
        struct __user_cap_header_struct header = { .version = _LINUX_CAPABILITY_VERSION_3 };
        struct __user_cap_data_struct value[2];
        g_assert_cmpint (syscall (SYS_capget, &header, value), ==, 0);
        g_assert_cmpuint (value[0].effective, ==, caps (missing_setuid));
        g_assert_cmpuint (value[0].permitted, ==, caps (missing_setuid));
        g_assert_cmpuint (value[1].effective | value[1].permitted, ==, 0);
        g_assert_cmpuint (getuid () | geteuid () | setfsuid ((uid_t) -1) | setfsgid ((gid_t) -1), ==, 0);
}
static void child_case (int parent, const char *home, int which, uid_t original)
{
        g_autoptr(GError) error = NULL;
        GThread *thread;
        gboolean ok;
        alarm (15);
        limited_caps (which == 6);
        check_identity (which == 6);
        thread = g_thread_new ("original-root-fsids", peer, NULL);
        while (!g_atomic_int_get (&samples)) g_thread_yield ();
        if (which == 1) {
                g_autoptr(GHashTable) environment = g_hash_table_new (g_str_hash, g_str_equal);
                g_hash_table_insert (environment, "GDM_TEST", "complete-lifecycle");
                g_assert_true (gdm_write_dynamic_environment (home, original, 65534, environment, &error));
                g_assert_no_error (error);
        }
        ok = gdm_dynamic_tree_at (parent, which == 4 ? "config" : (which == 1 || which == 2 || which == 6 || which == 7 ? "home" : "config"),
                                  which == 1 || which == 2 || which == 6 || which == 7 ? original : GREETER_UID_MIN + 1,
                                  65534, which == 1 || which == 2 || which == 6 || which == 7, &error);
        if (error) g_test_message ("case %d: %s", which, error->message);
        if (which == 1 || which == 5 || which == 9 || which == 13) {
                g_assert_true (ok); g_assert_no_error (error);
                if (which == 1) {
                        /* A second allocated UID must get a new, empty home. */
                        g_assert_true (gdm_create_dynamic_home_at (parent, "home", GREETER_UID_MIN + 1, 65534, &error));
                        g_assert_no_error (error);
                        g_assert_false (gdm_create_dynamic_home_at (parent, "home", GREETER_UID_MIN + 2, 65534, &error));
                        g_assert_error (error, G_IO_ERROR, G_IO_ERROR_EXISTS); g_clear_error (&error);
                        g_assert_true (gdm_dynamic_tree_at (parent, "home", GREETER_UID_MIN + 1, 65534, TRUE, &error));
                        g_assert_no_error (error);
                }
        } else {
                g_assert_false (ok); g_assert_nonnull (error);
                if (which >= 10 && which <= 12)
                        g_assert_nonnull (strstr (error->message, "source changed"));
                g_clear_error (&error);
        }
        check_identity (which == 6);
        g_atomic_int_set (&stop_peer, 1); g_thread_join (thread);
        g_assert_cmpint (g_atomic_int_get (&samples), >, 0);
        _exit (0);
}
static void run_case (int which)
{
        if (geteuid () != 0) { g_test_skip ("Requires private root child with exactly four non-DAC capabilities"); return; }
        g_autoptr(GError) error = NULL;
        g_autofree char *base = g_dir_make_tmp ("gdm-lifecycle-test-XXXXXX", &error);
        g_autofree char *home = g_build_filename (base, which == 4 ? "source-backup" : (which == 1 || which == 2 || which == 6 || which == 7 ? "home" : "config"), NULL);
        g_autofree char *deep = g_build_filename (home, "deep", NULL);
        g_autofree char *file = g_build_filename (deep, "data", NULL);
        g_autofree char *outside = g_build_filename (base, "outside", NULL);
        g_autofree char *link = g_build_filename (home, "link", NULL);
        g_autofree char *fifo = g_build_filename (home, "fifo", NULL);
        g_autofree char *alias = g_build_filename (base, "config", NULL);
        uid_t original = GREETER_UID_MIN;
        gid_t original_gid = 65534;
        struct stat before, after, original_file;
        int original_fd;
        int status, parent;
        int signal_pipe[2] = {-1, -1}, ack_pipe[2] = {-1, -1};
        pid_t attacker = -1;
        g_assert_no_error (error);
        g_assert_cmpint (chmod (base, 0755), ==, 0);
        if (which == 5) {
                struct passwd *account = getpwnam (GDM_PRE_DYNAMIC_USERNAME);
                g_assert_nonnull (account); original = account->pw_uid; original_gid = account->pw_gid;
        }
        parent = open (base, O_PATH | O_DIRECTORY | O_CLOEXEC);
        g_assert_cmpint (parent, >=, 0);
        g_assert_cmpint (mkdir (home, 0700), ==, 0);
        g_assert_cmpint (mkdir (deep, 0700), ==, 0);
        g_assert_true (g_file_set_contents (file, "original-private-bytes", -1, &error));
        g_assert_no_error (error);
        g_assert_cmpint (chmod (file, 0600), ==, 0);
        g_assert_cmpint (chown (file, which == 2 ? 1000 : original, original_gid), ==, 0);
        g_assert_cmpint (chown (deep, original, original_gid), ==, 0);
        g_assert_cmpint (chown (home, original, original_gid), ==, 0);
        if (which == 0 || which == 7) g_assert_cmpint (chmod (deep, 0000), ==, 0);
        if (which == 0) g_assert_cmpint (chmod (home, 0000), ==, 0);
        g_assert_true (g_file_set_contents (outside, "outside-must-not-change", -1, &error));
        g_assert_no_error (error); g_assert_cmpint (chmod (outside, 0600), ==, 0);
        if (which == 3) {
                g_assert_cmpint (unlink (outside), ==, 0);
                g_assert_cmpint (linkat (AT_FDCWD, file, AT_FDCWD, outside, 0), ==, 0);
        } else {
                g_assert_cmpint (symlink (outside, link), ==, 0);
                g_assert_cmpint (lchown (link, original, original_gid), ==, 0);
        }
        if (which == 1) {
                g_assert_cmpint (mkfifo (fifo, 0600), ==, 0);
                g_assert_cmpint (chown (fifo, original, original_gid), ==, 0);
        }
        if (which == 4) g_assert_cmpint (symlink (home, alias), ==, 0);
        original_fd = open (file, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
        g_assert_cmpint (original_fd, >=, 0);
        g_assert_cmpint (fstat (original_fd, &original_file), ==, 0);
        if (which == 8) {
                g_autofree char *stage = g_build_filename (base, ".config-handoff", NULL);
                g_assert_cmpint (mkdir (stage, 0700), ==, 0);
        }
        if (which >= 9) {
                struct stat source;
                g_autofree char *outside_dir = g_build_filename (base, "outside-dir", NULL);
                g_autofree char *moved = g_build_filename (outside_dir, "moved", NULL);
                g_autofree char *stage = g_build_filename (base, ".config-handoff", "deep", NULL);
                g_assert_cmpint (mkdir (outside_dir, 0700), ==, 0);
                g_assert_cmpint (chown (outside_dir, original, 65534), ==, 0);
                g_assert_cmpint (stat (file, &source), ==, 0);
                race_device = source.st_dev; race_inode = source.st_ino;
                g_assert_cmpint (pipe2 (signal_pipe, O_CLOEXEC), ==, 0);
                g_assert_cmpint (pipe2 (ack_pipe, O_CLOEXEC), ==, 0);
                race_send = signal_pipe[1]; race_ack = ack_pipe[0];
                race_kind = which == 10 ? 1 : which == 11 ? 2 : which == 12 ? 3 : which == 13 ? 4 : 0;
                attacker = fork (); g_assert_cmpint (attacker, >=, 0);
                if (attacker == 0) {
                        alarm (15); race_kind = 0;
                        close (signal_pipe[1]); close (ack_pipe[0]);
                        g_assert_cmpint (setgroups (0, NULL), ==, 0);
                        g_assert_cmpint (setgid (65534), ==, 0);
                        g_assert_cmpint (setuid (original), ==, 0);
                        int held = open (file, O_RDWR | O_CLOEXEC | O_NOFOLLOW);
                        g_assert_cmpint (held, >=, 0);
                        g_assert_cmpint (write (ack_pipe[1], "r", 1), ==, 1);
                        byte_wait (signal_pipe[0]);
                        if (which == 10) g_assert_cmpint (linkat (AT_FDCWD, file, AT_FDCWD, moved, 0), ==, 0);
                        if (which == 11) g_assert_cmpint (rename (file, moved), ==, 0);
                        if (which == 9 || which == 12) {
                                g_assert_cmpint (pwrite (held, "OLD-WRITER", 10, 0), ==, 10);
                                g_assert_cmpint (fsync (held), ==, 0);
                        }
                        if (which == 13) {
                                g_assert_cmpint (open (stage, O_PATH | O_DIRECTORY | O_CLOEXEC), ==, -1);
                                g_assert_cmpint (errno, ==, EACCES);
                        }
                        struct stat current;
                        g_assert_cmpint (fstat (held, &current), ==, 0);
                        g_assert_cmpuint (current.st_uid, ==, original);
                        g_assert_cmpuint (current.st_gid, ==, original_gid);
                        g_assert_cmpuint (current.st_mode, ==, source.st_mode);
                        close (held);
                        g_assert_cmpint (write (ack_pipe[1], "d", 1), ==, 1);
                        _exit (0);
                }
                close (signal_pipe[0]); close (ack_pipe[1]);
                byte_wait (ack_pipe[0]);
        }
        g_assert_cmpint (lstat (outside, &before), ==, 0);
        pid_t pid = fork (); g_assert_cmpint (pid, >=, 0);
        if (pid == 0) child_case (parent, home, which, original);
        g_assert_cmpint (waitpid (pid, &status, 0), ==, pid);
        g_assert_true (WIFEXITED (status)); g_assert_cmpint (WEXITSTATUS (status), ==, 0);
        race_kind = 0;
        if (attacker > 0) {
                if (which == 9) { g_assert_cmpint (write (signal_pipe[1], "x", 1), ==, 1); byte_wait (ack_pipe[0]); }
                g_assert_cmpint (waitpid (attacker, &status, 0), ==, attacker);
                g_assert_true (WIFEXITED (status)); g_assert_cmpint (WEXITSTATUS (status), ==, 0);
                close (signal_pipe[1]); close (ack_pipe[0]);
        }
        g_assert_cmpint (lstat (outside, &after), ==, 0);
        g_assert_cmpuint (before.st_ino, ==, after.st_ino);
        g_assert_cmpuint (before.st_uid, ==, after.st_uid);
        g_assert_cmpuint (before.st_gid, ==, after.st_gid);
        g_assert_cmpuint (before.st_mode, ==, after.st_mode);
        g_assert_cmpint (fstat (original_fd, &after), ==, 0);
        g_assert_cmpuint (after.st_uid, ==, original_file.st_uid);
        g_assert_cmpuint (after.st_gid, ==, original_file.st_gid);
        g_assert_cmpuint (after.st_mode, ==, original_file.st_mode);
        close (original_fd);
        if (which == 1) {
                g_assert_cmpint (faccessat (parent, "home", F_OK, AT_SYMLINK_NOFOLLOW), ==, -1);
                g_assert_cmpint (errno, ==, ENOENT);
        } else {
                g_assert_cmpint (lstat (home, &after), ==, 0);
                g_assert_cmpuint (after.st_mode & 0777, ==, which == 0 ? 0000 : 0700);
                g_assert_cmpint (lstat (deep, &after), ==, 0);
                g_assert_cmpuint (after.st_mode & 0777, ==, which == 0 || which == 7 ? 0000 : 0700);
                if (which == 5 || which == 9 || which == 13) {
                        g_assert_cmpuint (after.st_uid, ==, GREETER_UID_MIN + 1);
                        g_assert_cmpint (lstat (file, &after), ==, 0);
                        g_assert_cmpuint (after.st_uid, ==, GREETER_UID_MIN + 1);
                        g_assert_cmpuint (after.st_gid, ==, 65534);
                        g_assert_cmpuint (after.st_ino, !=, original_file.st_ino);
                        g_autofree char *body = NULL;
                        g_assert_true (g_file_get_contents (file, &body, NULL, &error));
                        g_assert_cmpstr (body, ==, "original-private-bytes");
                }
        }
        close (parent);
        g_autoptr(GFile) cleanup = g_file_new_for_path (base);
        g_assert_true (gdm_rm_recursively (cleanup, &error)); g_assert_no_error (error);
}
static void unreadable (void) { run_case (0); }
static void lifecycle (void) { run_case (1); }
static void foreign (void) { run_case (2); }
static void hard_link (void) { run_case (3); }
static void root_alias (void) { run_case (4); }
static void original_gdm (void) { run_case (5); }
static void denied_switch (void) { run_case (6); }
static void retire_unreadable (void) { run_case (7); }
static void pending_handoff (void) { run_case (8); }
static void old_writer (void) { run_case (9); }
static void concurrent_link (void) { run_case (10); }
static void concurrent_move (void) { run_case (11); }
static void concurrent_write (void) { run_case (12); }
static void private_stage (void) { run_case (13); }
int main (int argc, char **argv)
{
        g_test_init (&argc, &argv, NULL);
        g_test_add_func ("/dynamic-files/private-000-copy-refused-unchanged", unreadable);
        g_test_add_func ("/dynamic-files/write-retire-exclusive-recreate", lifecycle);
        g_test_add_func ("/dynamic-files/foreign-owner-fails-and-restores", foreign);
        g_test_add_func ("/dynamic-files/hard-link-transfer-rejected", hard_link);
        g_test_add_func ("/dynamic-files/root-alias-rejected", root_alias);
        g_test_add_func ("/dynamic-files/original-gdm-data-owner", original_gdm);
        g_test_add_func ("/dynamic-files/denied-fsuid-restores-without-dac", denied_switch);
        g_test_add_func ("/dynamic-files/private-000-retirement-refused", retire_unreadable);
        g_test_add_func ("/dynamic-files/retained-handoff-refused", pending_handoff);
        g_test_add_func ("/dynamic-files/old-writer-fd-cannot-change-new-inode", old_writer);
        g_test_add_func ("/dynamic-files/concurrent-hardlink-preserves-original-owner", concurrent_link);
        g_test_add_func ("/dynamic-files/concurrent-rename-preserves-original-owner", concurrent_move);
        g_test_add_func ("/dynamic-files/concurrent-write-refuses-publication", concurrent_write);
        g_test_add_func ("/dynamic-files/new-inodes-private-until-publication", private_stage);
        return g_test_run ();
}
