/* SPDX-License-Identifier: LGPL-2.0-or-later */
#include "config.h"
#include "gdm-environment-file.h"
#include <errno.h>
#include <fcntl.h>
#include <glib/gstdio.h>
#include <linux/capability.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <signal.h>
#include <sys/fsuid.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static gint stop_peer, peer_samples;
static gpointer peer (gpointer unused)
{
        (void) unused;
        while (!g_atomic_int_get (&stop_peer)) {
                g_assert_cmpuint (setfsuid ((uid_t) -1), ==, 0);
                g_assert_cmpuint (setfsgid ((gid_t) -1), ==, 0);
                g_atomic_int_inc (&peer_samples);
                g_thread_yield ();
        }
        return NULL;
}
static void remove_dac_privileges (void)
{
        struct __user_cap_header_struct h = { .version = _LINUX_CAPABILITY_VERSION_3 };
        struct __user_cap_data_struct d[2] = {{0}, {0}};
        guint32 allowed = (1U << CAP_CHOWN) | (1U << CAP_FOWNER) |
                          (1U << CAP_SETUID) | (1U << CAP_SETGID);
        d[0].effective = d[0].permitted = allowed;
        g_assert_cmpint (syscall (SYS_capset, &h, d), ==, 0);
        g_assert_cmpint (syscall (SYS_capget, &h, d), ==, 0);
        g_assert_cmpuint (d[0].effective, ==, allowed);
        g_assert_cmpuint (d[0].permitted, ==, allowed);
}
static void child_test (const char *home, int mode)
{
        g_autoptr(GError) error = NULL;
        g_autoptr(GHashTable) env = g_hash_table_new (g_str_hash, g_str_equal);
        g_autofree char *probe = g_build_filename (home, "root-must-not-write", NULL);
        g_hash_table_insert (env, "GDM_TEST", "first");
        g_assert_cmpint (prctl (PR_SET_DUMPABLE, 0, 0, 0, 0), ==, 0);
        remove_dac_privileges ();
        errno = 0;
        g_assert_cmpint (open (probe, O_WRONLY | O_CREAT | O_EXCL, 0600), ==, -1);
        g_assert_cmpint (errno, ==, EACCES);

        if (mode == 2) {
                struct sock_filter insns[] = {
                        BPF_STMT (BPF_LD | BPF_W | BPF_ABS, offsetof (struct seccomp_data, nr)),
                        BPF_JUMP (BPF_JMP | BPF_JEQ | BPF_K, SYS_setfsuid, 0, 3),
                        BPF_STMT (BPF_LD | BPF_W | BPF_ABS, offsetof (struct seccomp_data, args[0])),
                        BPF_JUMP (BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 1),
                        BPF_STMT (BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
                        BPF_STMT (BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
                };
                struct sock_fprog filter = { G_N_ELEMENTS (insns), insns };
                g_assert_cmpint (prctl (PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0), ==, 0);
                g_assert_cmpint (prctl (PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &filter), ==, 0);
                gdm_write_dynamic_environment (home, GREETER_UID_MIN, 65534, env, &error);
                _exit (99); /* An unproven restoration must never return. */
        }

        g_atomic_int_set (&stop_peer, 0);
        g_atomic_int_set (&peer_samples, 0);
        GThread *thread = g_thread_new ("original-fs-identity", peer, NULL);
        while (!g_atomic_int_get (&peer_samples))
                g_thread_yield ();
        gboolean ok = gdm_write_dynamic_environment (home, GREETER_UID_MIN, 65534, env, &error);
        if (mode == 1) {
                g_assert_false (ok);
                g_assert_nonnull (error);
                g_clear_error (&error);
        } else {
                g_assert_true (ok);
                g_assert_no_error (error);
                g_hash_table_replace (env, "GDM_TEST", "replacement");
                g_assert_true (gdm_write_dynamic_environment (home, GREETER_UID_MIN, 65534, env, &error));
                g_assert_no_error (error);
        }
        g_assert_cmpuint (setfsuid ((uid_t) -1), ==, 0);
        g_assert_cmpuint (setfsgid ((gid_t) -1), ==, 0);
        g_assert_false (gdm_write_dynamic_environment (home, 0, 65534, env, &error));
        g_assert_error (error, G_IO_ERROR, G_IO_ERROR_INVALID_ARGUMENT);
        g_atomic_int_set (&stop_peer, 1);
        g_thread_join (thread);
        g_assert_cmpint (g_atomic_int_get (&peer_samples), >, 0);
        _exit (0);
}
static void run_case (int mode)
{
        if (geteuid () != 0) {
                g_test_skip ("Requires an isolated root test child to drop all DAC bypass capabilities");
                return;
        }
        g_autoptr(GError) error = NULL;
        g_autofree char *base = g_dir_make_tmp ("gdm-environment-test-XXXXXX", &error);
        g_assert_no_error (error);
        g_assert_cmpint (chmod (base, 0755), ==, 0);
        g_autofree char *home = g_build_filename (base, "dynamic-home", NULL);
        g_autofree char *config = g_build_filename (home, ".config", NULL);
        g_autofree char *directory = g_build_filename (config, "environment.d", NULL);
        g_autofree char *file = g_build_filename (directory, "gdm.conf", NULL);
        g_assert_cmpint (mkdir (home, 0700), ==, 0);
        g_assert_cmpint (chown (home, GREETER_UID_MIN, 65534), ==, 0);
        if (mode == 1) {
                int fd = open (config, O_WRONLY | O_CREAT | O_EXCL, 0600);
                g_assert_cmpint (fd, >=, 0);
                g_assert_cmpint (close (fd), ==, 0);
        }
        int output[2] = {-1, -1};
        if (mode == 2)
                g_assert_cmpint (pipe2 (output, O_CLOEXEC), ==, 0);
        pid_t pid = fork ();
        g_assert_cmpint (pid, >=, 0);
        if (pid == 0) {
                if (mode == 2) {
                        close (output[0]);
                        g_assert_cmpint (dup2 (output[1], STDOUT_FILENO), ==, STDOUT_FILENO);
                        g_assert_cmpint (dup2 (output[1], STDERR_FILENO), ==, STDERR_FILENO);
                        close (output[1]);
                }
                child_test (home, mode);
        }
        if (mode == 2)
                close (output[1]);
        int status;
        g_assert_cmpint (waitpid (pid, &status, 0), ==, pid);
        if (mode == 2) {
                char diagnostic[4096] = {0};
                ssize_t bytes = read (output[0], diagnostic, sizeof diagnostic - 1);
                g_assert_cmpint (bytes, >, 0);
                close (output[0]);
                g_assert_nonnull (strstr (diagnostic, "Cannot restore GDM filesystem user after environment write"));
                g_assert_true (WIFSIGNALED (status));
                g_assert_true (WTERMSIG (status) == SIGTRAP || WTERMSIG (status) == SIGABRT);
        } else {
                g_assert_true (WIFEXITED (status));
                g_assert_cmpint (WEXITSTATUS (status), ==, 0);
        }
        if (mode != 1) {
                struct stat st;
                g_assert_cmpint (lstat (file, &st), ==, 0);
                g_assert_cmpuint (st.st_uid, ==, GREETER_UID_MIN);
                g_assert_cmpuint (st.st_gid, ==, 65534);
                g_assert_cmpuint (st.st_mode & 0777, ==, 0600);
                for (int i = 0; i < 2; i++) {
                        g_assert_cmpint (lstat (i ? directory : config, &st), ==, 0);
                        g_assert_cmpuint (st.st_uid, ==, GREETER_UID_MIN);
                        g_assert_cmpuint (st.st_mode & 0777, ==, 0700);
                }
                g_autofree char *contents = NULL;
                g_assert_true (g_file_get_contents (file, &contents, NULL, &error));
                g_assert_no_error (error);
                g_assert_cmpstr (contents, ==, mode == 2 ? "GDM_TEST=first\n" : "GDM_TEST=replacement\n");
                g_assert_cmpint (unlink (file), ==, 0);
                g_assert_cmpint (rmdir (directory), ==, 0);
                g_assert_cmpint (rmdir (config), ==, 0);
        } else {
                g_assert_cmpint (unlink (config), ==, 0);
        }
        g_assert_cmpint (rmdir (home), ==, 0);
        g_assert_cmpint (rmdir (base), ==, 0);
}
static void success (void) { run_case (0); }
static void io_failure (void) { run_case (1); }
static void restore_failure (void) { run_case (2); }
int main (int argc, char **argv)
{
        g_test_init (&argc, &argv, NULL);
        g_test_add_func ("/environment/private-write-replace-and-thread-scope", success);
        g_test_add_func ("/environment/io-failure-restores-identity", io_failure);
        g_test_add_func ("/environment/restoration-denial-is-fatal", restore_failure);
        return g_test_run ();
}
