// Own-process control for the actual new diagnostic function only.
// No complete client Run(), connection, namespace entry, service, or credential change.
#define main factory_client_entry_not_invoked
#include "/workspace/scratch/94990735b266/native-new-env-01/factory-host-diagnostic03-build01/client_control.cc"
#undef main

int main() {
  uid_t before_uid[3]{}, after_uid[3]{};
  gid_t before_gid[3]{}, after_gid[3]{};
  if (getresuid(&before_uid[0], &before_uid[1], &before_uid[2]) < 0 ||
      getresgid(&before_gid[0], &before_gid[1], &before_gid[2]) < 0) return 70;
  const long before_fsuid = syscall(SYS_setfsuid, static_cast<uid_t>(-1));
  const long before_fsgid = syscall(SYS_setfsgid, static_cast<gid_t>(-1));
  const int before_fds = CountFds();
  if (before_fds < 0) return 71;
  Result result;
  result.name = "diagnostic_function_only";
  result.Fail(1, EIO);
  errno = EIO;
  DiagnoseInitialNamespace(&result);
  const int after_errno = errno;
  const int after_fds = CountFds();
  if (getresuid(&after_uid[0], &after_uid[1], &after_uid[2]) < 0 ||
      getresgid(&after_gid[0], &after_gid[1], &after_gid[2]) < 0) return 72;
  const long after_fsuid = syscall(SYS_setfsuid, static_cast<uid_t>(-1));
  const long after_fsgid = syscall(SYS_setfsgid, static_cast<gid_t>(-1));
  const bool ok = after_errno == EIO && before_fds == after_fds &&
      result.stage == 1 && result.error == EIO && !result.pass &&
      !result.request_sent &&
      memcmp(before_uid, after_uid, sizeof(before_uid)) == 0 &&
      memcmp(before_gid, after_gid, sizeof(before_gid)) == 0 &&
      before_fsuid == after_fsuid && before_fsgid == after_fsgid;
  result.fd_before = before_fds;
  result.fd_after = after_fds;
  Print(result);
  printf("{\"control\":\"actual_diagnostic_function_only\",\"pass\":%s,"
         "\"errno_before\":%d,\"errno_after\":%d,\"fds_before\":%d,\"fds_after\":%d,"
         "\"uid_gid_fsids_unchanged\":%s,\"client_Run_invoked\":false}\n",
         ok ? "true" : "false", EIO, after_errno, before_fds, after_fds,
         (memcmp(before_uid, after_uid, sizeof(before_uid)) == 0 &&
          memcmp(before_gid, after_gid, sizeof(before_gid)) == 0 &&
          before_fsuid == after_fsuid && before_fsgid == after_fsgid) ? "true" : "false");
  return ok ? 0 : 1;
}
