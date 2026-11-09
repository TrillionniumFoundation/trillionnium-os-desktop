# Production identity input validation

Three input defects are corrected on the actual identity source commit
`098a58c107977c0be24e4b8311c77af1d786c9ad`. These are prerequisite source
repairs. They do not implement an executing production backend or qualify an
Android boot, application, UID map, seccomp policy, or deployment.

## Changes

- Shared `CellSpec` validation rejects subordinate UID and GID intervals that
  include the reserved unmapped ID `u32::MAX`. The highest valid interval ends
  exclusively at that value. Invalid specifications fail before any backend
  operation. The dedicated identity module already enforced this boundary;
  the shared specification now agrees with it.
- Anchored identity authority opens retain their ownership, held-parent and
  `O_NOFOLLOW` checks and add `O_NONBLOCK`. A FIFO replacement is rejected by
  the existing inode-type check without waiting for a writer.
- The CLI opens its specification once with `O_NONBLOCK`, checks the held
  descriptor for a regular file, and reads at most 1 MiB plus one byte. The
  metadata size check is an early rejection; the actual read limit also rejects
  growth after that check. Ordinary symlink paths remain compatible. No unsafe
  code was added to the CLI. This does not promise a deadline for regular-file
  I/O, including a stalled network filesystem.

`production-identity-reservation.patch` supplies the previously unpublished
identity prerequisite. `identity-review-fixes.patch` is the additional reviewed
three-file delta. `source-chain.json` binds every patch and the exact before and
after bytes of all three reviewed files.

## Actual source validation

Tests ran on Pocket4 as the ordinary user, from an isolated archive of the
actual clean identity commit. The observed compiler was **rustc 1.95.0
(59807616e 2026-04-14)**, resolved from the installed stable toolchain. Cargo
used `--locked --offline -j 1`, an independent target and registry, CPU quota
100%, affinity to one logical CPU, nice 19, and a 3 GiB memory limit.

| Invocation | Observed result |
| --- | --- |
| Identity module tests | 18 passed, 0 failed, 0 ignored; 17 existing tests plus the FIFO regression |
| Shared specification test subset | 6 passed, 0 failed, 0 ignored; includes the new highest-valid and invalid UID/GID boundary tests |
| CLI specification input tests | 5 passed, 0 failed, 0 ignored |
| Complete ordinary supervisor library suite | 150 passed, 0 failed, 13 ignored |
| Normal supervisor binary build | Exit 0 |

The first two rows are subsets of the complete library suite and must not be
added to its count. The 13 ignored entries retain their existing explicit
private-fixture or privileged-environment requirements; their exact names and
reasons are in `source-qualification.json`. No `--ignored` suite was run.
That receipt also retains the host, durable H job identities, launch nonces,
and authoritative terminal states for setup and each validation invocation.

Four separate negative controls each produced exactly one failed assertion and
exit 101: the old shared ID boundary, authority opens without `O_NONBLOCK`, the
original CLI loader against a real FIFO, and a disabled read-size limit. FIFO
controls released and joined their blocked reader, completing in 1.00 seconds.
The unending reader has an independent byte-count assertion, so its negative
control fails without unbounded memory consumption.

Rustfmt with edition 2024 passed for `main.rs` and `production_identity.rs`.
The original and candidate `lib.rs` both have existing formatting differences.
None intersects the added or changed library lines; `format-scope.json` records
that comparison. Unrelated formatting was retained.

The resource sample taken **after cache preparation, before tests** reported
`memory.current=3220291584`, `memory.max=3221225472`, and `memory.events`
`max=26413`, `oom=0`, `oom_kill=0`. The memory ceiling was reached during that
sample window. This is not a zero-pressure or end-to-end build resource
qualification. The unnecessary copied Git cache was removed.

## Offline source replay

From this repository root:

```sh
python3 compat/android/pocket4/production-identity-input-validation-r1/verify_source_chain.py --repo-root .
```

The verifier uses only Python's standard library and Git. It verifies the
length and SHA-256 of all seven existing patch inputs, creates a temporary
repository, runs `git apply --index --check` before every apply, and verifies
the three actual source preimages and final files. It makes no network calls,
downloads no dependencies, builds no Rust or Android code, and removes its
temporary reconstruction on exit. The recorded local replay is in
`source-reconstruction.json`; CI must run the verifier itself.

The chain is the common 385-file text snapshot, the cumulative audio
prerequisite, GSI layout support, namespace ownership, guest directory/umask
repair, identity prerequisite, and this input validation delta. The cumulative
audio prerequisite already contains the older host status/readiness changes;
do not apply that older host patch again. The reconstructed source is a declared
subset with exact reviewed host bytes, not a recreation of a complete local Git
commit or a current Audio build candidate.

## Remaining production gates

The dedicated account and non-overlapping effective grants, active namespace
ownership audit, pidfd-bound map broker preserving Android group semantics,
idmapped data handling, peer identity compatibility, applied seccomp and
complete lifecycle validation remain separate requirements. The identity
prerequisite is not integrated into an executing production backend.
`production_ready` and `runtime_qualified` remain false. This package grants no
application acceptance credit.
