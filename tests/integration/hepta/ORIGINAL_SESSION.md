# Original Agentd → persistent Session qualification

This is an optional extension of [the original process gate](ORIGINAL_AGENTD.md).
The fixed original remains `hepta-private-ci@f8c9419df6ddeb36ff8b522a50219981fb8d9345`.
Its existing FleetRegistry, Supervisor and UnixProcessDriver still own every
Agentd launch, promotion, drain, restart and stop. The additional
[`original_session_probe.rs`](original_session_probe.rs) module launches actual
`trill-session` and invokes actual `trill-ctl snapshot`; it implements no Agentd
server, RPC client, authority or operation ledger. Production UI/observer code
is unchanged by this extension.

The prior archived ARM gate passed eight process/CLI checks with fresh observer
instances. Those results do not qualify this new continuous-consumer path.
An executed report must contain both `live_agentd_acceptance: passed` and
`persistent_session_acceptance: passed`. Source review, parser/unit tests,
successful preflight, build completion and a capture acknowledgment do not
substitute for these runtime results.

## Build and run

Build `trill-session` and `trill-ctl` with the committed UI lock using Rust 1.96.
Bind the prebuilt files to the actual build command, desktop commit/tree and
their SHA256 values. The gate hashes these supplied ELF files before and after
execution; that alone does not establish which source produced a supplied ELF.

```sh
CARGO_TARGET_DIR=/absolute/new-ui-target rustup run 1.96.0 cargo build \
  --locked --manifest-path ui/Cargo.toml -p trill-session \
  --bin trill-session --bin trill-ctl

python3 tests/integration/hepta/run_original_agentd.py \
  --hepta-source /absolute/hepta-private-ci \
  --work-dir /absolute/new-original-agentd-work \
  --session-bin /absolute/new-ui-target/debug/trill-session \
  --ctl-bin /absolute/new-ui-target/debug/trill-ctl \
  --execute --report /absolute/new-original-session-report.json
```

The generated original-linked runner now copies both `original_agentd_probe.rs`
and `original_session_probe.rs`. It uses the same original seed lock and build
target as the original process gate; no additional Rust dependency is added.
The direct runner retains its four positional arguments and accepts the same
`--session-bin` and `--ctl-bin` options. Supplying neither retains the existing
eight-check process/CLI gate.

## Required continuous observations

| Phase | Required actual result |
| --- | --- |
| `starting` | First Session observes the original Starting PID/spawn before the original owner ticks promotion. |
| `running` | Same Session instance, PID and Linux observer TID observes current generation = spawn + 1, ready and original lifecycle events. |
| `draining` | Same Session/worker observes current generation = spawn + 2 and not ready. |
| `old_spawn_stale` | After original restart and a successful new-spawn CLI read, the unchanged old Session rejects the old spawn, preserves old-source evidence and continues answering IPC. |
| `recovered_running` | The probe kills/reaps only its owned first Session, then explicitly launches a second Session with the new endpoint settings from the original owner. A new Session instance observes the replacement Running PID/spawn. |
| `stopped_stale` | After the original owner stops Agentd, the second Session retains historical evidence as stale and still answers IPC; its own child is then killed/reaped and recorded. |

All endpoint settings are supplied together at Session startup:
`TRILL_HEPTA_AGENTD_SOCKET`, `TRILL_HEPTA_AGENT_ID`,
`TRILL_HEPTA_SPAWN_GENERATION` and `TRILL_HEPTA_PEER_UID`. There is no automatic
discovery or cross-spawn reconfiguration. One observer thread is checked via
its actual Linux `/proc/<pid>/task/<tid>/comm` name and retained TID in each
continuous interval. This qualification requires Linux and a readable process
view in the same PID namespace; it is not a portable mobile-runtime claim.

Fresh success and failure timestamps must be within seven seconds of the
sample check. Each phase has a 20-second observation deadline; successful
`trill-ctl` calls must finish in under three seconds. Time limits only bound
retries: PID, spawn, current generation, ready state, lifecycle and event
predicates determine success.

Original restart can append a second Draining event, and original stop may
publish Draining after the last captured Running cut. The stale oracle accepts
that legitimate final old-source progress without rebinding agent/spawn/PID or
erasing the earlier event prefix. It then requires a second, later failed poll
whose entire `last_observation` is unchanged. Both stale samples and the
preceding live observation are retained in the phase record.

## Optional real Shell capture barrier

Add `--session-phase-dir /absolute/new-phase-dir` and optionally
`--session-ack-seconds 120` (default 60, allowed 1–120). The probe creates that
new private directory and atomically writes `phase-1.json` through
`phase-6.json`. Every record contains sequence/name, actual Session instance,
PID and observer TID, runtime/socket paths, complete actual ctl snapshot,
original-owner process identity and the exact required acknowledgment object.

The capture consumer starts one actual Shell using the record's `runtime_dir`.
The runtime directory inode remains stable across the explicit Session restart,
so the same Shell can reconnect through its production Session IPC. The Shell
must share the Session PID namespace for kernel peer-credential validation.
It must not receive the privileged Agentd endpoint, manufacture a projection or
launch another Session.

After validating the real displayed phase and preserving the capture evidence,
the consumer atomically creates `ack-N.json`, mode `0600`, containing exactly
the corresponding record's `ack` object. For example:

```json
{"sequence":1,"phase":"starting","session_instance":"<actual 32-character instance>"}
```

The acknowledgment is bounded to 1 KiB, same owner UID, one link and a regular
file. A wrong, stale or missing acknowledgment fails this bounded run. It is
only a sequencing barrier. The Session acceptance receipt explicitly says
`shell_capture_qualified_by_this_record: false`; Shell pixels, input and renderer
source identity require the independent capture evidence.

The original process deadline remains 240 seconds without Session. Session
adds 120 seconds; a capture barrier adds six times the selected acknowledgment
deadline. The outer waitable-child group guard still owns timeout cleanup.
Session logs are preserved on success and runtime failure. Neither this gate
nor its capture mode submits objectives, runs a model or executes device effects.
