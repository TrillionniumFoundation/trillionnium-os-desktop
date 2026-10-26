# Original native CPU owner build and G2 boundary

`build_original_entry.py` measures a **tracked executable target in the original
`codex-hepta-agentd` package**. It does not synthesize a Rust or C qualification
owner. The selected source must compose the existing `ProductionDurableWriter`,
`LocalLeaseOutbox`, `CognitiveStore`, protected authority and original FinalUse
target; source review and actual execution must establish that composition.
Merely linking the Agentd library or successfully calling `ReadUsage` establishes
none of those properties.

The build keeps the original Cargo lock, default features and release profile.
It selects the exact installed toolchain in `codex-rs/rust-toolchain.toml`, uses
the previously established static GNU flags, and runs the original release
symbol archival/strip script. The original OS `inspect_probe_elf` then applies
the unchanged trusted image bounds and mapping checks. A too-large or dynamic
result remains a failed profile check with its real build, ELF and log retained.
No size limit, supplier, feature or profile is weakened to make the result pass.

Both repositories must be clean at explicitly supplied full commit and tree
identities. Before/after snapshots verify every tracked byte against its actual
Git blob, including files hidden from `git status` by `assume-unchanged`.
The existing Cargo target cache must be separate from source/evidence and is
leased with the same nonblocking exclusive lock used by the native runtime
preparation. Do not run a noncooperating build in that cache concurrently.
Original prebuilt V8 inputs, when needed, are supplied as one independently
pinned archive/bindings pair. The command stays offline and does not execute
the produced binary.

## Invocation

The entry must already exist in the frozen Hepta commit. Choose the reviewed
complete native owner target, not the old external `read_usage` feasibility
fixture. All paths are absolute; the output directory must not exist.

```sh
python3 -I -B tests/workloads/hepta_cpu_control/build_original_entry.py \
  --execute \
  --desktop-source "$OS_SOURCE" --desktop-head "$OS_HEAD" --desktop-tree "$OS_TREE" \
  --hepta-source "$HEPTA_SOURCE" --hepta-head "$HEPTA_HEAD" --hepta-tree "$HEPTA_TREE" \
  --entry "$ORIGINAL_NATIVE_ENTRY" --entry-kind bin \
  --toolchain-bin "$PINNED_TOOLCHAIN_BIN" --cargo-home "$DEPENDENCY_HOME" \
  --target-cache "$EXCLUSIVE_STATIC_TARGET" --output "$NEW_BUILD_EVIDENCE"
```

If the original graph requires V8, also supply `--v8-archive`, `--v8-bindings`,
`--expected-v8-archive-sha256` and `--expected-v8-bindings-sha256`. Omitting any
one of the four is an error. The result records actual command exits, elapsed
times, tool hashes, original entry, source snapshots, unstripped binary,
packaged binary and the original ELF inspection.

Even on success the result keeps `executed_binary`, `native_role_verified`,
`persistent_cpu_verified`, `recovery_verified` and `g2_complete` false. The
build is the input to the runtime gate and does not replace it.

### Explicit OpenSSL static private archive

Some system OpenSSL metadata names `-l:libjitterentropy.a` directly in
`libcrypto.pc`'s `Libs.private`. The locked Rust `pkg-config` dependency emits
that form as a build-script `rustc-link-arg`; when emitted for a library it may
be absent from the final executable link. This builder can supply that one
original dependency explicitly after verifying its source:

```sh
  --static-private-archive /usr/lib/x86_64-linux-gnu/libjitterentropy.a \
  --expected-static-private-archive-sha256 "$INDEPENDENT_ARCHIVE_SHA256"
```

Add both options to the invocation above only when the installed OpenSSL
metadata actually requires this archive. The builder requires the direct token
and actual static `pkg-config` output to agree, refuses other `-l:` inputs,
checks all three OpenSSL modules' original library and `.pc` directories, and
requires a canonical, ordinary archive with the independently supplied SHA256.
It records `libssl.a`, `libcrypto.a`, the archive, metadata, query output and
native tool bytes before and after the build. The linker record identifies the
selected Rust toolchain's `gcc-ld/ld.lld` and `rust-lld`, not the host's unrelated
default `ld.bfd`. This records installed tool identities; it does not trace the
final linker subprocess. `linker_execution_observed` remains false. A prior
run's actual linker log cannot be treated as an execution trace for this run.

The archive is copied byte-for-byte into the new evidence directory. The final
tracked target alone uses `cargo rustc` with one `-C link-arg` pointing to that
copy; the dependency RUSTFLAGS, Cargo lock, default features, release profile
and cache remain unchanged. A new output path forces a final-target relink
without assuming that Cargo fingerprints arbitrary archive contents. The
`static-private-before.json`, `static-private-after.json` and
`result.json.static_private_archive` records bind the original inputs and the
retained final-link copy; any changed input fails the postcheck.

This optional path still runs the original packaging and unchanged 8 MiB
file/16 MiB LOAD-map checks. Their outcome is measured, not assumed. The current
G2 consumer deliberately rejects the additional `cargo rustc` command shape;
this measurement path does not extend G2 admission or prove native authority.

## Native authority handoff that the runtime must prove

`/dev/hepta-control` binds its open file to the exact original `Process` and
live image epoch. A child, a later exec, a copied bootstrap page or an inherited
descriptor cannot acquire its parent's role. The actual final role process
must open its own device and use that same `AgentdHos2Device` inside the original
synchronous FinalUse dispatch.

The retained G1-d transaction creates only three frozen initial processes. Its
manager and recovery namespaces and canonical CPU delegations belong to those
actual initial images. A general Root fork/exec launcher supplies process
custody, but does not by itself activate these kernel roles. Any new trusted
activation must preserve final-image verification, exact process identity,
one-time activation, old-grant fencing and the original retained history.

G2 needs the real original Supervisor/Registry identity and generation, the
independent protected Current cut and live issuer, and the original durable
writer's immutable K-to-D binding. It must demonstrate at least one real CPU
effect, same-D replay and changed-payload refusal, lost reply followed by query,
durable terminal confirmation before contiguous retirement, manager fault,
successor recovery, old-boot refusal and an unresolved prefix that is not
retired or resent. The original kernel watchdog's bounded recovery and user
pause preservation remain separate observations. A C program must not stand in
for the writer, FinalUse owner or persistence in any of these checks.

## Local regression checks

```sh
python3 -B -m unittest discover -s tests/workloads/hepta_cpu_control -p 'test_*.py' -v
```

These checks exercise actual temporary Git repositories, metadata selection,
exclusive file locking and failed subprocess evidence. Static-private guard
tests use real C object/archive files and actual input mutations, with explicitly
synthetic `pkg-config` and LLD query replies. They do not build OpenSSL or the
Hepta entry, validate the host's actual pkg-config resolution, or execute a
native guest.
