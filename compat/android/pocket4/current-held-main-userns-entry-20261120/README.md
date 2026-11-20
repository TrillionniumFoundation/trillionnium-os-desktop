# Held mapped Main guest entry

The earlier seven-FD helper entered six namespaces while keeping the host user
namespace and host credentials. Current mapped Main execution also requires entry
into the exact namespace that owns those six namespaces and an explicit switch to
guest UID/GID zero. This source preserves the original seven transferred authority
FDs, parent-death and owned-child wait/reap boundary.

The new userns FD comes from `NS_GET_USERNS` on the already-held mount namespace.
The helper checks its actual direct parent and root creator, all six namespace
owners, and the fixed held-root `proc/1` namespace links, root inode, start epoch
and UID/GID maps. The caller supplies three comparison values from its separately
held authenticated Main; these values do not issue a Main witness. After clearing
supplementary groups, the helper enters the user namespace, switches to guest
GID/UID zero, rearms parent death after each credential transition, then performs
the original six namespace entries, chroot, fork, exec and exact reap.

## Actual validation

Pocket4 built the exact source with pinned Rust 1.93.0, edition 2021, warnings
denied, optimization level 2 and no debug information. All four pure Rust cases
passed; the real binary rejected an incomplete comparison contract before entry.
An isolated root-owned kernel fixture created its own user namespace, one-ID map,
six namespaces and private PID1/proc. Four incorrect namespace/root/epoch cases
were rejected, and the actual positive entry returned guest UID zero. All helper,
keeper and init children were reaped; host mount and namespace bookends and the
input ELF stayed unchanged. No Android namespace or command was used.

`HANDOFF.json` contains the exact original source, binary, compiler and report
FilePins, compile argv and an external map to all twenty original stdout/stderr
byte copies. Report bodies are unchanged. The native executable remains outside
Git; this packet contains source, bounded reproduction controllers and finite
qualification evidence only. The controllers use create-only isolated roots and
are historical exact invocations, not commands to rerun over their existing paths.
A fresh rerun must choose a separately reviewed, executable root-owned fixture
location and regenerate its own references. Never change host mount flags.

The earlier private R1 outcome remains recorded: `/run` was noexec, so no helper
ran and the fixture was retired. R2 correctly rejected all four bad identities but
its assertion expected a later error string; the stronger earlier map rejection
stopped that harness before the positive. R3 changed only the new fixture path and
that expected error; it used the same reviewed source and compiled ELF.

## Remaining production prerequisites

Canonical source/binary deployment is pending. The original daemon peer, selected
Main, seven held namespaces, PIDFD, complete root/mount graph, actual mapping and
epoch must be held by the caller throughout each owned command and cleanup. A new
readonly entry receipt from that exact authenticated Main is required separately;
the private fixture does not satisfy `Main_readonly_entry_passed`. The independent
persistent-data provider and original data continuity are also required.

No release was adopted, no CURRENT pointer or original input was changed, and no
service or Android was started. Runtime and production qualification remain false.
