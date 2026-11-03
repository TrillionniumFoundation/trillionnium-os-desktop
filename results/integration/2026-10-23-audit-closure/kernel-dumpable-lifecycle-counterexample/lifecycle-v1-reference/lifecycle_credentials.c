#include "lifecycle_probe.h"

void credential_case(unsigned number) {
    if (number == 12) {
        /* Only this isolated Root-created child ever has initial capabilities.
         * Dropping permitted capabilities must not make an image nondumpable. */
        bound_caps();
        check("cap_drop_set_one", prctl(PR_SET_DUMPABLE, 1L), 0);
        no_caps();
        check("permitted_capability_decrease_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        return;
    }
    int alternate_uid = number >= 5 && number <= 8;
    int alternate_gid = number >= 9;
    unprivileged(60001, alternate_uid ? 60002 : 60001,
                 alternate_uid ? 60002 : 60001,
                 60001, alternate_gid ? 60002 : 60001,
                 alternate_gid ? 60002 : 60001);
    check("credential_set_one", prctl(PR_SET_DUMPABLE, 1L), 0);
    switch (number) {
    case 0:
        check("uid_noop", setresuid(60001, 60001, 60001), 0);
        check("gid_noop", setresgid(60001, 60001, 60001), 0);
        check("uid_gid_noop_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        break;
    case 1:
        check("fsuid_query", setfsuid((uid_t)-1), 60001);
        check("fsgid_query", setfsgid((gid_t)-1), 60001);
        check("query_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        break;
    case 2:
        check("fsuid_noop", setfsuid(60001), 60001);
        check("fsgid_noop", setfsgid(60001), 60001);
        check("fsid_noop_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        break;
    case 3:
        errno = 0;
        check("failed_uid_change", setresuid(-1, 60003, -1), -1);
        check("failed_uid_errno", errno, EPERM);
        check("failed_uid_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        errno = 0;
        check("failed_gid_change", setresgid(-1, 60003, -1), -1);
        check("failed_gid_errno", errno, EPERM);
        check("failed_gid_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        break;
    case 4:
        check("failed_fsuid_returns_old", setfsuid(60003), 60001);
        check("failed_fsuid_unchanged", setfsuid((uid_t)-1), 60001);
        check("failed_fsgid_returns_old", setfsgid(60003), 60001);
        check("failed_fsgid_unchanged", setfsgid((gid_t)-1), 60001);
        check("failed_fsid_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        break;
    case 5:
        check("effective_uid_change", setresuid(-1, 60001, -1), 0);
        check("effective_uid_change_clears", prctl(PR_GET_DUMPABLE), 0);
        break;
    case 6:
        check("filesystem_uid_change", setfsuid(60001), 60002);
        check("filesystem_uid_current", setfsuid((uid_t)-1), 60001);
        check("filesystem_uid_change_clears", prctl(PR_GET_DUMPABLE), 0);
        break;
    case 7:
        check("real_uid_only_change", setresuid(60002, -1, -1), 0);
        check("real_uid_only_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        break;
    case 8:
        check("saved_uid_only_change", setresuid(-1, -1, 60001), 0);
        check("saved_uid_only_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        break;
    case 9:
        check("effective_gid_change", setresgid(-1, 60001, -1), 0);
        check("effective_gid_change_clears", prctl(PR_GET_DUMPABLE), 0);
        break;
    case 10:
        check("filesystem_gid_change", setfsgid(60001), 60002);
        check("filesystem_gid_current", setfsgid((gid_t)-1), 60001);
        check("filesystem_gid_change_clears", prctl(PR_GET_DUMPABLE), 0);
        break;
    case 11:
        check("real_gid_only_change", setresgid(60002, -1, -1), 0);
        check("real_gid_only_preserves_one", prctl(PR_GET_DUMPABLE), 1);
        break;
    }
}
