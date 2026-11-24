/* SPDX-License-Identifier: LGPL-2.0-or-later */
#include "config.h"
#include "gdm-dynamic-files.h"
#include "gdm-environment-file.h"
#include "gdm-file-utils.h"
#include <fcntl.h>
#include <glib/gstdio.h>
#include <linux/capability.h>
#include <pwd.h>
#include <sys/fsuid.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

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
        ok = gdm_dynamic_tree_at (parent, which == 4 ? "alias" : "home",
                                  which == 1 || which == 2 || which == 6 ? original : GREETER_UID_MIN + 1,
                                  65534, which == 1 || which == 2 || which == 6, &error);
        if (which == 0 || which == 1 || which == 5) {
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
                g_assert_false (ok); g_assert_nonnull (error); g_clear_error (&error);
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
        g_autofree char *home = g_build_filename (base, "home", NULL);
        g_autofree char *deep = g_build_filename (home, "deep", NULL);
        g_autofree char *file = g_build_filename (deep, "data", NULL);
        g_autofree char *outside = g_build_filename (base, "outside", NULL);
        g_autofree char *link = g_build_filename (home, "link", NULL);
        g_autofree char *fifo = g_build_filename (home, "fifo", NULL);
        g_autofree char *alias = g_build_filename (base, "alias", NULL);
        uid_t original = GREETER_UID_MIN;
        gid_t original_gid = 65534;
        struct stat before, after;
        int status, parent;
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
        g_assert_cmpint (chmod (deep, 0000), ==, 0);
        if (which != 1) g_assert_cmpint (chmod (home, 0000), ==, 0);
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
        g_assert_cmpint (lstat (outside, &before), ==, 0);
        pid_t pid = fork (); g_assert_cmpint (pid, >=, 0);
        if (pid == 0) child_case (parent, home, which, original);
        g_assert_cmpint (waitpid (pid, &status, 0), ==, pid);
        g_assert_true (WIFEXITED (status)); g_assert_cmpint (WEXITSTATUS (status), ==, 0);
        g_assert_cmpint (lstat (outside, &after), ==, 0);
        g_assert_cmpuint (before.st_ino, ==, after.st_ino);
        g_assert_cmpuint (before.st_uid, ==, after.st_uid);
        g_assert_cmpuint (before.st_gid, ==, after.st_gid);
        g_assert_cmpuint (before.st_mode, ==, after.st_mode);
        if (which == 1) {
                g_assert_cmpint (faccessat (parent, "home", F_OK, AT_SYMLINK_NOFOLLOW), ==, -1);
                g_assert_cmpint (errno, ==, ENOENT);
        } else {
                g_assert_cmpint (lstat (home, &after), ==, 0);
                g_assert_cmpuint (after.st_mode & 0777, ==, which == 0 || which == 5 ? 0700 : 0000);
                g_assert_cmpint (lstat (deep, &after), ==, 0);
                g_assert_cmpuint (after.st_mode & 0777, ==, 0000);
                if (which == 0 || which == 5) {
                        g_assert_cmpuint (after.st_uid, ==, GREETER_UID_MIN + 1);
                        g_assert_cmpint (lstat (file, &after), ==, 0);
                        g_assert_cmpuint (after.st_uid, ==, GREETER_UID_MIN + 1);
                        g_assert_cmpuint (after.st_gid, ==, 65534);
                        g_autofree char *body = NULL;
                        g_assert_true (g_file_get_contents (file, &body, NULL, &error));
                        g_assert_cmpstr (body, ==, "original-private-bytes");
                }
        }
        close (parent);
        g_autoptr(GFile) cleanup = g_file_new_for_path (base);
        g_assert_true (gdm_rm_recursively (cleanup, &error)); g_assert_no_error (error);
}
static void transfer (void) { run_case (0); }
static void lifecycle (void) { run_case (1); }
static void foreign (void) { run_case (2); }
static void hard_link (void) { run_case (3); }
static void root_alias (void) { run_case (4); }
static void original_gdm (void) { run_case (5); }
static void denied_switch (void) { run_case (6); }
int main (int argc, char **argv)
{
        g_test_init (&argc, &argv, NULL);
        g_test_add_func ("/dynamic-files/private-000-transfer-no-follow", transfer);
        g_test_add_func ("/dynamic-files/write-retire-exclusive-recreate", lifecycle);
        g_test_add_func ("/dynamic-files/foreign-owner-fails-and-restores", foreign);
        g_test_add_func ("/dynamic-files/hard-link-transfer-rejected", hard_link);
        g_test_add_func ("/dynamic-files/root-alias-rejected", root_alias);
        g_test_add_func ("/dynamic-files/original-gdm-data-owner", original_gdm);
        g_test_add_func ("/dynamic-files/denied-fsuid-restores-without-dac", denied_switch);
        return g_test_run ();
}
