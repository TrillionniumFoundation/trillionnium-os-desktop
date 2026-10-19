# Manifest lifecycle observations

The writer of the original same-content profile left after `next3-kernel`
remains unidentified. Later observations prove that this workspace can recreate
a deleted, owned file with its old mtime: the bounded nonce control observed an
incoming temporary file and `.rsync-tmp` rename sequence. This establishes an
environmental recreation mechanism for that control, but does not identify the
process/syscall that recreated the historical kernel profile. No cleanup
strategy or service was changed for this investigation.

## Isolated controls

The existing runner and cleanup guards were exercised with disposable host
tools and fake make in a temporary project on the same overlay filesystem:

- 20 ordinary runs exited 0; all 20 removed their owned profile. Inotify recorded
  20 `CREATE OSDK.toml` and 20 `DELETE OSDK.toml` events, with no residual file.
- A known replacement control used `copy2` plus `os.replace` inside fake make.
  The replacement preserved the profile's bytes and mtime but changed its inode.
  The runner exited 0 and correctly retained that foreign inode. This produces
  a similar final state, but establishes only this control's known cause.

The inspected source matches commit
`0e5f17911b8518d3f9e2a98595cc2990c4966522`: runner SHA256
`a4b7f05133273d8c73af4b8c31e0cefee46eb8a825a1bfe61ff992e6de33e191`.
The original per-run JSON did not independently emit a source hash; the
attribution is the source inspected before those runs and its matching Git
version. Later `gdb_server` wrapper changes are not attributed to the 20 fake
measurements. `fake-case-index.json` retains this limitation and the exact case
results remain readable in `normal-results.json` and
`same-content-replacement.json`. These controls performed no real Git
operation, Rust compilation or QEMU execution.

## First real debug attempt

The final observer records for `next4-kernel-debug` are retained as
`live-invocation.json` and `live-events.jsonl`. The actual driver exited 1:
release compilation with debug information finished, but `rust-strip` was
missing and the kernel driver failed before QEMU/GDB readiness. This is a
failed debug attempt, not a passed kernel boot or debugging session.

Inotify observed temporary inode `27:1572956` acquire the minimal profile bytes,
the same inode published at `OSDK.toml`, deletion of the temporary name, and
eventual deletion of `OSDK.toml`. The final invocation records
`manifest_present_after=false`. No replacement or cleanup residual was observed
in this attempt. The new wrapper's source hashes are recorded separately in
`live-case-index.json`; this real debug source is not the fake-run source.

The driver console is the full captured top-level output of this attempt. Its
kernel compilation and driver logs remain in the parent's separate debug-run
archive and are not duplicated here. `live-case-index.json` identifies those
scratch originals and their hashes.

One preliminary `strace ... true` probe failed with ptrace permission errors.
Its empty output file proves no syscall trace content; its invocation and
reported stderr were added to the final invocation metadata from the prior tool
receipt. No ptrace observation was performed on the real build. The actual
observer used inotify, which does not supply writer PIDs and cannot establish
the cause of the older residual.

## Recreation after the first observed cleanup

The first real observer proved deletion of inode `27:1572956` and absence of the
path. A later read-only stat found a different inode, `27:1572927`, with the
**exact original mtime and bytes**; its birth time was 3.213 seconds after that
recorded deletion. Thus the first attempt did remove its original inode. The
second debug attempt correctly refused the new existing file, rather than
overwriting it. `post-cleanup-reappearance.json` retains the read-only stat;
`preservation.json` records the parent's subsequent locked preservation.

The third debug attempt subsequently succeeded (GDB Rust entry and raw QEMU
33). A later read-only observation again found a matching profile, now inode
`27:1572967` with the third attempt's newer mtime. The parent reported no Git
write operation between that attempt's completion and the observation. There
was no corresponding continuous inotify trace for the third attempt, so these
records do not newly assert when it was deleted or recreated. Its result and
log hashes are references in `follow-up-index.json`; the large debug-run logs
remain in the parent's archive.

The active Git executable is an ordinary C ELF Git 2.51.1 at
`/usr/local/bin/git`, not a script wrapper. The specifically inspected
hooks/fsmonitor/worktree configuration keys were unset, and the default hooks
directory contained only inactive `.sample` hooks. No authentication
configuration was read. The recurrence cannot be attributed to Git merely from
the earlier temporal association.

## One bounded owned-file control

Two visible `sync_share.sh` processes and an rsync daemon provided a concrete
environmental lead. The installed script selects `RSYNC_DIR`, uses rsync
`--delay-updates --update --times`, excludes `.git/`, and debounces local events
for two seconds. This agent's directory-only environment value was
`RSYNC_DIR=/workspace/scratch`. Service-specific environment and peer transfer
history were not read. `sync-script-readonly.json` retains the script hash and
sanitized structural observations, not endpoint or authentication values.

Exactly one additional control ran, bounded to **14.043 seconds**. It created
unique nonce bytes in its own isolated scratch directory, waited four seconds,
and deleted its own file. After **2.261 seconds**, the file reappeared with the
same nonce and mtime but a different inode. Inotify recorded a temporary
`.owned-profile.txt.*` file, creation of `.rsync-tmp`, and `MOVED_TO` of the
owned filename. The control itself invoked no Git, kernel or service operation.
`nonce-control.json` retains the complete event sequence and observed states.

This is direct reproduction of file recreation in the current workspace,
consistent with the installed synchronization mechanism. It does not bind a
particular PID to the writer syscall or establish the cause of every historical
profile. No additional synchronization research or service change followed
this single control.

## Raw records

`raw-logs.tar.gz` retains the two fake raw logs, the first real observer's full
top-level console and inotify stderr, and the empty preliminary ptrace output.
`raw-log-index.json` lists every member's byte length and SHA256. Key JSON
records remain outside the archive. The original preserved profile was not
modified, and no production kernel/debug output tree was copied into this
subdirectory.
