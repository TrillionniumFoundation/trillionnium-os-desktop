# OOM adjustment authorization prerequisite

This stage is a prerequisite for scoped OOM admission. It does not enable
`memory.max`, implement an OOM killer, or claim full memory isolation.

The initial extraction preserves the old unconditional store. The eight native
regressions use owned, unscheduled real `Process`, `TaskSet`, `PosixThread`,
`Credentials`, VMAR and fork objects. They call the same writer-aware operation
as procfs. No test supplies a privileged boolean or edits host process files.
The tests are expected to detect the missing authorization and shared-VM state;
no before execution is claimed until its actual build/run evidence is retained.

The native fixtures exercise the real process-VM publication primitive for
exec/exit boundaries. They do not execute a userspace exec or exit syscall.
Complete qualification still needs actual owned guest syscalls for proc file
DAC, per-write authority, fork/CLONE_THREAD/CLONE_VM/vfork, exec and exit.

Sources for the required contract are Linux v6.2 `fs/proc/base.c` (the
`__set_oom_adj` path), `kernel/fork.c` (`copy_signal`, `copy_oom_score_adj`) and
`kernel/capability.c`. In particular, `oom_score_adj_min` is the authorized
floor, not a historical minimum and not the current value. Privileged writes
replace it in either direction. The initial user namespace is the authority.
