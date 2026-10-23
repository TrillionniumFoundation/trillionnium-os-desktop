# G2 post-exec observation prerequisites: actual kernel-object evidence

## Scope and implementation

This archive qualifies the internal external-mutation fences and typed post-exec
observation handoff prerequisites. Existing boot profiles have no caller that
activates the new sealed-launcher authority. This is not a native G2 grant/read,
FinalUse, durable HOS2 effect, history-retirement or production-authority pass.

The reviewed A+B source is commit
`62e8327e94fe2c7f6e3c64b40ebd3541298e4ae8`, tree
`1a4e92d51275211cee1b50bf1d91c6f14064e4e4`, based on #249
`cfe28e3efb5e025d58a9d663d1dd6a681c224892`. The fixed feature runner is
`aa9a6003c545c398ecad2ea089e2d45fe9d2d706`. Final source
`c2203318888e2f9de90cb6683a9b4bfa6092c2a1`, tree
`6ebd9d4d579a17ab49b8622e6e47bd9623f2c814`, adds only the test-fixture lifetime
correction described below. No production behavior or permission assertion was
weakened to obtain the second pass.

The Asterinas Process and VMAR owners now track active external operations before
an irreversible admission fence can commit. Real proc-mem handles, ptrace targets
and foreign CLONE_VM/vfork paths participate. The typed child handoff binds the
original launcher Process allocation, real child pidfd, live post-exec image and
actual per-open control session. It reuses the original CPU observer and lease;
it does not create a manager, history owner, delivery namespace or writer.

## Actual runs

| Run | Source | Actual result |
| --- | --- | --- |
| Default full aster-core | 62e8327e | 280 passed; 0 failed, filtered or soft-skipped |
| First g1c feature full aster-core | aa9a6003 | 290 passed; 1 failed; complete failure retained |
| Corrected g1c feature full aster-core | c2203318 | 291 passed; 0 failed, filtered or soft-skipped |
| Feature-runner host checker | aa9a6003 | 16 tests passed with normal Python and with -O |

The successful feature run executes the original full-core checker unchanged,
plus all 16 specifically required A+B tests exactly once. It is not a filtered
suite. Raw QEMU exit is 33; the wrapper exits are recorded separately.
The original checker SHA256 remains
`e80fc3fe31b689938b742b46efec461dadd07421b2039a9d247d6911f96bb314`.

The first feature failure was a fixture lifetime error: construction of a
Weak-backed pidfd consumed the last strong reference to the intended live foreign
Process. Production correctly returned ESTALE before it could test permission.
The correction retains that Process, requires the original EPERM result while
it is live, explicitly drops it, then requires ESTALE. The rejected run, exact
test-only patch and successful rerun are all included.

An earlier wrapper assertion expected physical mode 0755 although the repository
records executable Git mode 100755 and the host umask produces 0700. The retained
mode observation documents this discrepancy. The continuation verifies the Git
executable mode and actual executability; it does not relax source-byte checks.

## Reproduction and evidence identity

Use the committed `support/build/ktest/run.py` wrapper with the repository's
pinned nightly, locked dependencies and the OSDK installed from that same
worktree. Shared OSDK installation/build operations must be serialized.

For the feature run, select `--g1c-postexec-observe` and provide the static
`--trusted-initial-elf` whose exact identity is recorded in the archive.
The wrapper freezes that ELF through the original trusted-initial-image
preparation code. No alternate issuer or fake CPU observer is introduced.

`archive-manifest.json` records every copied file's original absolute location,
byte length and SHA256. Copies include original CRLF/ANSI serial bytes, empty
streams, actual exit records, commands, source pins, patch inputs, Cargo locks,
and rejected evidence. ELF binaries remain at their original build locations;
their exact identities are listed in the manifest rather than replaced with
reconstructed binaries. Archive commits do not change the tested source identity.

Default result SHA256:
`b31de360831c7874ec820955887089f3c540247befa65e30bc53641df80e5cb5`.

Corrected feature result SHA256:
`b693c9765c590b593b6a1be042979e8fa6024d0256627024d95cdcc46603a87b`.

`source-review-handoff.md` is the original pre-build review handoff, preserved
verbatim as historical design input. This README and actual receipts describe
the later verification state.

## Remaining blockers

- Connect a real sealed original Supervisor/Registry launch to the actual child
  descriptor handoff and Agentd's synchronous observation bootstrap. Registry
  configuration and image hashes alone cannot mint a role.
- Establish immutable executable backing for the enabled profile. These fences
  block external process/VMAR mutation but do not freeze a writable file's page
  cache. A bounded native profile must use the actual readonly payload drive,
  readonly mount and exact static Agentd ELF. General writable-backed exec needs
  a separate typed immutable-backing proof before activation.
- Run the same integrated source's ordinary G1-d feature and sealed native
  grant/read regressions. These internal full-core results cannot replace them.
- Connect original FinalUse authority, HOS2 effects and saved receipts to the
  existing durable writer, terminal transition, acknowledgement and retirement.
  There is no new issuer, authority clock, frontier, SQLite owner or ledger here.
- F1/F2, total memory/watchdog recovery, SMP, hardware and ARM/BSP remain separate
  qualifications. No field in these results certifies those boundaries.
