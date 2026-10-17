# Original Agentd live-source and trusted-ingress review

This is a source review at **2026-10-17 13:20 UTC**, before any original-process
result was supplied to this review. It changes no executable source or
qualification receipt. It neither links nor launches Agentd.

**Later execution:** the separate [ARM64 original-process receipt](evidence/2026-10-17-original-agentd-arm/README.md)
records the successful build/link and eight runtime checks completed after this
review. The statements below retain the 13:20 source-review time boundary;
they do not replace that runtime evidence or qualify persistent Session/Shell.

The reviewed desktop cut is local
`50fa836e064f67268aafcc6d64835426f89cc90b`, published with the same tree as
[`5beb3fab54fe7dd60072864276ece1ced38150ab`][desktop]. Its A07 directories are
byte-identical to local `a732c2c0e80793c6362892a40b810a8b2def08f2`.
The unchanged original is
[`hepta-private-ci@f8c9419df6ddeb36ff8b522a50219981fb8d9345`][upstream].

| Reviewed desktop file | SHA256 |
| --- | --- |
| `run_original_agentd.py` | `fff0b1228d6f02da4f5a02c3a1af3eb1e5f9aa55f5b7021b8db997934d5e5ceb` |
| `original_agentd_probe.rs` | `6620f550cbfa4fa9561df375d8bf52208bd342c8530319818cd4b5cf351c2beb` |

The archived original-library and original Agentd `cargo check` results remain
separate from this review. See [BUILD_REVIEW.md](BUILD_REVIEW.md) and its raw
evidence links. No new Cargo command or closed regression was rerun here.

## Read-only process gate

**No definite startup-argument or read-protocol mismatch was found in the
reviewed gate.** This is a source-level conclusion; the real link, private-store
initialization, App Server readiness and process assertions still require
execution. The following bindings are present in the fixed original source:

| Boundary | Source finding |
| --- | --- |
| Agent registration and child identity | The probe uses the original FleetRegistry, Supervisor and UnixProcessDriver. The [driver][driver] sets the agent, immutable spawn, fleet/home/run roots, CODEX_HOME and working directory; [AgentdConfig][config] checks the registered Starting generation and acquires the original writer lock. |
| Optional trust configuration | [runtime.rs][runtime] accepts no AuthBus trust/checkpoint and no objective profile. The probe supplies neither. This is a valid original startup profile, without an issuer or effect provider. |
| Private control transport | The original [control listener][control] prepares its private socket directory, sets the socket owner-only, and accepts one bounded newline JSON request. Its filesystem boundary and the observer's additional kernel peer UID/PID checks are distinct checks. |
| Inert provider configuration | Every provider field in the probe is present in the original [ModelProviderInfo][provider]. `requires_openai_auth = false` is supported. The selected loopback endpoint has no service; the probe submits no model turn. |
| Lifecycle generation | Original [refresh_generation][lifecycle] accepts Starting at spawn, Running at spawn + 1 and Draining at spawn + 2. Promotion/drain within one process does not change its immutable spawn. |
| Drain then restart | Original [supervisor control][supervisor-control] accepts an already-Draining process when restart is requested; this probe sequence does not require a replacement lifecycle controller. |
| Absent run | Original [RunStatus][run-status] returns an optional runtime receipt. A fresh owner can return `null` for the probe's deliberately absent run. This does not establish durable-publication absence after an objective submission. |

The source review does not establish that the selected graph fits a particular
runner. The complete gate's 8 GiB admission estimate is unchanged. Actual build,
link, startup and cleanup failures remain failures.

The probe currently collapses original Supervisor faults and rejected observer
results into fixed error messages (`original_agentd_probe.rs:122–151`). Its
Starting wait also discards individual failed observations before reporting a
timeout. This can obscure a real startup diagnosis; it cannot make a failed
check pass. Bounded original faults and observer error codes would be useful if
the real run reaches such a failure. This review does not change that code.

## Session handoff

The reviewed [Session worker][session] reads all four trusted endpoint settings
once at Session startup. It polls off the IPC thread and retains the last
successful projection as stale after a failure. It does not discover or
automatically accept a different AgentId, spawn, UID or socket. Normal current
generation progression preserves the event window; a changed PID or spawn
invalidates that window and retains a history/source-change indication.

Use the gate's explicit `--hold-seconds 30` window and its `trusted_endpoint`
record if a separate trusted test launcher needs to start Session. Bind that
Session executable to its own actual build source and hash. The original gate
creates a fresh observer CLI for each read; it does not itself qualify a
persistent Session or renderer. After the original Supervisor restarts the
agent, the old configured Session must fail its spawn fence. A trusted launcher
must explicitly select the new owner configuration for a new Session.

## Smallest trusted objective adapter boundary

The compiled ingress is [state_control.rs:206–228][objective-route] calling
`ObjectiveRuntimeHost::submit`. The original [module declarations][modules]
include `objective_runtime`; the file named `objective_ingress.rs` is not
declared there. The presence of that older file does not establish a second
running objective route.

1. A trusted owner supplies an already registered issuer and selected objective
   profile. The original [CLI][cli] accepts `--authbus-trust-file`,
   `--authbus-checkpoint-file` and `--objective-profile-file`. The [trust file][trust]
   and frozen profile must be direct, private regular files in the canonical
   Agent home; the [replay checkpoint][checkpoint] must already exist in a
   separate canonical private directory outside that home. The profile must
   register at least one allowed signed adapter identity. These are deployment
   prerequisites; the desktop must not create an issuer or signer implicitly.
2. UI input remains an untrusted draft until the registered trusted adapter
   authenticates and constructs the bounded structured objective. The original
   [wire body][objective-wire] carries the spawn, run ID, revision, structured
   source JSON, runtime/preference/model/prompt/artifact digests and authority
   epoch. The envelope adds issuer/key epoch, message ID, sequence, expiry and
   signature. No private key or privileged Agentd socket belongs in the renderer.
3. A narrow trusted transport can forward that exact signed envelope through
   the existing `AgentdClient::objective_start`. Original [admission][objective]
   enforces source JSON <= 32 KiB, encoded body <= 48 KiB, expiry within five
   minutes, registered issuer authentication and the host-derived owner scope.
   The Agentd owner supplies the current generation, fence and selected profile.
   The adapter must not fall back to raw `RunStart`, arbitrary RPC, or a
   TrustedReadOnlyOrganV1 handler to perform I/O or effects.
4. The original owner retains publication, replay and runtime ownership. Keep
   the existing read-only observer separate from this future explicitly enabled
   ingress. A desktop receipt projection is not another durable operation or
   authority ledger.

### Submission and recovery semantics

Original [objective_runtime.rs:206–327][objective] persists the publication
before its later trust recheck and runtime projection. Once a request may have
reached that owner, a timeout, connection loss or error can therefore leave a
durable publication. Without authoritative evidence of non-admission or a
precise receipt, the desktop must represent this as **SubmitUnknown**; it must
not infer that no work was admitted. A local rejection before any send remains
distinguishable from this uncertain transport outcome.

`RunStatus` reads the current in-memory `runs` projection, not the durable
run-start journal. A `null` result does not resolve an unknown submission to
"not accepted". The fixed protocol does not expose a separate objective
publication-status method. A future recovery UI needs the original owner's
reconciliation result or a still-valid exact authenticated retry; it must not
implement a substitute durable status store.

The original [replay check][replay] permits an already-consumed sequence only
when the recorded authentication and run ID match exactly. Signature expiry,
revocation, owner generation and readiness checks still apply. The client must
not refresh the signature, change the run ID or rebind to a new spawn to turn
an unknown submission into an automatic new attempt.

An `Admitted` response includes publication/chain digests and a disposition;
`Conflict` includes its recorded conflict digest. These are publication results,
not evidence of HOS2 execution or completed device effects. In particular,
explicit abstention can be durably admitted without starting a run. Effect
authority and final effect receipts continue to come from the original owners.

[desktop]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/5beb3fab54fe7dd60072864276ece1ced38150ab
[upstream]: https://github.com/TrillionniumFoundation/hepta-private-ci/tree/f8c9419df6ddeb36ff8b522a50219981fb8d9345
[driver]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-supervisor/src/unix.rs#L175-L234
[config]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/config.rs#L127-L218
[runtime]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/runtime.rs#L132-L180
[control]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/control.rs#L43-L138
[provider]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/model-provider-info/src/lib.rs#L111-L165
[lifecycle]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state.rs#L311-L370
[supervisor-control]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-supervisor/src/control.rs#L118-L164
[run-status]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state_control.rs#L523-L531
[session]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/ui/session/src/hepta.rs#L17-L279
[objective-route]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state_control.rs#L206-L228
[modules]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/lib.rs#L7-L46
[cli]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/main.rs#L31-L150
[trust]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/authbus_trust.rs#L30-L142
[checkpoint]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/authbus_checkpoint.rs#L39-L139
[objective-wire]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agent-protocol/src/authbus.rs#L27-L81
[objective]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/objective_runtime.rs#L140-L396
[replay]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/objective_runtime.rs#L502-L568
