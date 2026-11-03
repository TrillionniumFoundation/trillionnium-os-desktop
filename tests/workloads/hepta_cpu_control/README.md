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
exclusive file locking and failed subprocess evidence. They do not build the
Hepta entry or execute a native guest.
