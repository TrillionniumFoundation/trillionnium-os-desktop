# Reviewed mozjs secondary input — source candidate

`manifests/mozjs-secondary-input.v1.json` records the exact secondary archive
used by `mozjs_sys` 140.14.0-1 on `x86_64-unknown-linux-gnu` for Servo PIN
`670ae8a70801b162e186f81cbb5bdd2d59c39108`.
`contracts/mozjs-secondary-input.v1.json` describes the additive custody API and
the explicit candidate compile profile. No original source API, Cargo lock,
PIN patch, workflow, native case or deadline is changed.

The locked crate checksum is
`4cb5edb8729da5f2b09939fcad2559ba1c54e55d222f14d485b88c7d645890d5`.
It covers the crate archive, not the secondary release archive downloaded by
that crate's `build.rs`. The reviewed secondary input is official release asset
527403045, `libmozjs-x86_64-unknown-linux-gnu.tar.gz`, exactly 19381534 bytes,
SHA-256 `c5f93d7f9f1b450e2a608b5e7378c95ec8fa9f3689bdfe1f6ad548e434c3107b`.
The observed GitHub asset API size/digest correspond to the complete locally
observed bytes. That correspondence is not artifact attestation, an independent
signature, signer approval or production trust. The observed `gh` 2.45 tool
did not support the attestation command; this profile does not invoke it.

The reviewed upstream `build.rs` SHA-256 is
`94b782be9a6ca00644c8ae85817bd6b946b993a96c59a9b7cda7cf9b095f5cf0`.
Its attestation helper inspects spawn failure without inspecting nonzero exit
status. This is a static source observation; no actual nonzero-status fault
injection or successful artifact attestation is claimed here.

## Archive admission and lifetime

`tools/mozjs_secondary_input.py::lease_archive(path)` loads the entire finite
typed manifest and admits only that reviewed size and digest. It uses the
existing `ManagedSourceReader` and owned `_SourceDescriptor` mechanism. Every
input path component is opened without following symlinks; the input is a
regular file with one hard link. Copying is streaming and bounded to 32 MiB,
with an additional EOF check and original file/name identity checks including
size, mtime and ctime. The JSON manifest is bounded to 16384 bytes and duplicate
members are refused. There is no download or caller-supplied digest authority.

The same copied bytes are placed in a Linux memfd with `F_SEAL_WRITE`,
`F_SEAL_GROW`, `F_SEAL_SHRINK` and `F_SEAL_SEAL`. Admission then reads the actual
`/proc/<creator PID>/fd/<n>` path completely and checks SHA, size, all seals and
retained object/mode/uid/gid/link identity. Linux can update timestamps during a
failed write on a sealed memfd. Its byte proof therefore uses retained object,
size, seals and complete digest; mutable-source copy checks still include
timestamps. Original input path replacement after admission cannot redirect
the sealed snapshot.

`SealedArchiveLease.readback()` returns only byte count, SHA and sealed status.
`stable_path()` returns a borrowed parent-process procfs path. It is valid while
the creator retains this lease and is not a transferable approval or promise
about a later reused FD number. No public API transfers a raw descriptor.
Public use is restricted to the creator process and thread; fork, foreign
thread, reentry, closed lease and descriptor replacement are refused. Explicit
close detaches the owned descriptor before its single native close attempt.
Descriptor-number replacement is not closed as though it belonged to this
lease. Ordinary helper-result loss and interrupted reads keep object ownership
and descriptor-only finalization; all native/opcode windows or repeated cleanup
faults are not covered.

Source/API checks and optional full archive admission:

```sh
python3 tools/verify_mozjs_secondary_input.py
python3 tools/verify_mozjs_secondary_input.py --archive /absolute/independent/libmozjs-x86_64-unknown-linux-gnu.tar.gz
python3 -m unittest tests.test_mozjs_secondary_input -v
```

## Explicit candidate compile

`tools/build_mozjs_locked_native.py` is an additional opt-in entry point. It
reads an already separately prepared exact-PIN native graph; it never assembles
or edits the upstream checkout. Preflight checks the original lock using the
existing reviewed lock verifier, original common native API, original format
configuration, reviewed assembled target sources, whole assembled Servo Cargo
manifest and selected toolchain. This is finite preflight, not complete upstream
working-tree or hermetic dependency qualification.

Each invocation creates an exclusive, initially empty `CARGO_TARGET_DIR`
outside the upstream checkout. No existing build cache or original active
target is accepted. This is essential: the upstream `MOZJS_ARCHIVE` branch first
treats the value as a URL base and only falls back to a filesystem path if the
download fails. Its `OUT_DIR` archive cache can otherwise override the provided
value. The candidate supplies the stable sealed parent procfs path to that
variable; proving the actual upstream fallback and consumption still requires
later actual build traces. Environment assignment is not that proof. The fresh
target's initial emptiness is checked at creation; this entry point is not a
sandbox against same-UID changes to build outputs or Cargo configuration.

Before setting its environment, the entry point rejects every inherited
`MOZJS_*` selector, feature/profile/target/build overrides, rustflags and compiler
wrappers, and conflicting toolchain, incremental, jobs or backtrace values. It
sets toolchain 1.97.1, incremental 0 and two build jobs. The two fixed profiles
retain the original compile argument bodies:

```sh
python3 tools/build_mozjs_locked_native.py --profile native-owner \
  --upstream /absolute/separately-prepared-servo \
  --original-lock /absolute/pristine-PIN-Cargo.lock \
  --archive /absolute/independent/libmozjs-x86_64-unknown-linux-gnu.tar.gz \
  --target-parent /absolute/independent-build-parent
# --profile approved-startup selects only the original approved connected target.
```

The fixed Cargo command is `cargo test --locked --profile checked-release -p
servo --no-default-features --features bundled,js_jit --test
trillionnium_product_owner --no-run --message-format=json`, or the original
`trillionnium_approved_connected` target for `approved-startup`. It executes no
original four native or two approved cases. Their original five-second native
and twenty-second connection budgets and assertions remain unchanged.

The supervisor owns the subprocess object before initialization can acquire its
child. It retains the same sealed archive throughout the child process-group
lifetime. The total candidate lifecycle is bounded to 10800 seconds, reserving
five-second TERM and KILL/reap phases within that bound. Ordinary timeout,
exception or cancellation (including CLI SIGTERM and Ctrl-C) causes bounded
group termination and a leader wait;
the lease is released only after the group is observed absent. An unresolved
bounded shutdown retains process and lease custody in a long-lived caller and
is never success. Supervisor death/SIGKILL, native spawn/opcode windows, children
that deliberately escape the group, repeated cleanup interruption and hostile
same-UID processes are outside this mechanism. The standalone CLI's lifetime
cannot preserve input custody after its own process dies. No installed or
production process-custody claim follows from these host tests.

## Status and remaining evidence

Status is source candidate, not qualified. Independent safety review and actual
Cargo consumption evidence remain incomplete. A real complete archive lease
check proves that the supplied fixed bytes passed admission and readback. The
small host cases exercise Linux seals, procfs, actual children, fork/thread
refusal, object-return loss, read interruption and bounded cancellation; they
do not recompile Servo or establish the downstream build-script's behavior.

Later acceptance must independently review this source and trace actual Cargo
consumption using a new empty target, retain complete exact-PIN/lock/profile
facts, and separately run the unchanged native and approved cases. All original
CI lanes keep their existing behavior. This source candidate does not mint
production signer facts, change trust roots, prove an installed desktop or close
G1, G0 or production readiness.
