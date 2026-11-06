# Owner17 owned guest bootstrap search modes

This is one Rust production-file successor to the actual Host16 entry source.
The original Owner16 FAILED report, binaries and source are unchanged. Its
generation-private logger delivered both real KernelLogger markers and161943
bytes, including four LMKD exec EACCES messages and a distinct critical
hwservicemanager repeated-SIGABRT fatal reboot. The actual unit uses UMask0077.
All27 pinned Rust inputs have been inspected for umask calls; none contains
one. The prior mkdir0755/create_dir_all paths admit0700 guest directories.

Only /droidloom and the new create-only lmkd-bootstrap directory are adjusted
through held descriptors. Before chmod the exact synthetic root must be
tmpfs, inode1, UID/GID0 and0755; parents and target must be directories on the
same device, owned byUID/GID0, without group/other writes or special bits.
This prevents chmod of a host or partition bind. The existing parent is
accepted only within that already-created private guest tmpfs. Names are
one fixed component; O_NOFOLLOW/O_CLOEXEC remain. The held target and named
target must agree before and after fchmod0755. Host package/data parents,
unit umask, all payload hashes and read-only binds remain unchanged.

The actual mode operation is factored after root/private-tmpfs authorization.
Three added Rust tests exercise it with ordinary owned files: exact scope,
replacement/symlink rejection before chmod, and the original EBADF from an
O_PATH descriptor. They are not yet compiled or run. Eight local kernel
mechanism assertions reproduced the umask counterexample and verified the
held chmod/mode/inode behavior; they do not execute the Rust function or
prove private mount authorization, LMKD effective capabilities, or Android.
The existing39 relay and136 supervisor tests remain; the candidate adds3
supervisor tests, for an exact139 expectation on the next ordinary run.

The RC requests DAC_OVERRIDE. Therefore the directory defect alone does not
prove the complete cause of all four EACCES results. The HWS abort message
is still absent and is a separate investigation. No critical service flag,
Main setting, identity gate, broker grant or generation recovery is relaxed.
FD/named checks are not an atomic filesystem CAS; the production call occurs
in the existing single-threaded pre-init entry and owned private mount view.
