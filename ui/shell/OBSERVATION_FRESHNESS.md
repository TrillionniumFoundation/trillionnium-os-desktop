# Hepta observation freshness before drawing

Runtime health and the optional known run each have a separate successful
sample clock. The Session owns these read-only observations. Shell does not
infer a new successful sample from a recently delivered snapshot, a poll
attempt, a local task update or a different projection's success.

`Desktop::receive_and_refresh_hepta` consumes queued replies and evaluates
both clocks before any page draws. Bridge records request start and actual
transport return before its bounded response queue can wait. For each
projection, the renderer adds three durations:

| Duration | Source and purpose |
| --- | --- |
| Sample age at Session snapshot | Successful read-start Instant to snapshot creation; includes the complete poll and worker/Session queue delay |
| Full IPC round trip | Bridge request start to transport return; conservatively bounds unmeasured snapshot-to-receipt transfer |
| Time since actual receipt | Bridge return to pre-draw evaluation; includes the UI response queue delay |

The total bound must be at most 7,000 ms. Independently, the sample's Unix
timestamp must be neither future nor older than 7,000 ms. Comparing the
three monotonic durations separately is insufficient: a 6,000 ms source
age, 20 ms IPC round trip and 1,991 ms queue delay total 8,011 ms, even if
wall-clock rollback makes the source appear only 6,000 ms old.

The full round trip can conservatively count some time already included in
the Session age. This may turn a view unknown earlier than its exact age
would require. For a repeated successful sample, the clock retains the
larger of its previous bound advanced to the new receipt and its newly
computed source-age-plus-round-trip bound. It never adds overlapping round
trips repeatedly or trusts a younger repeated frame to undo elapsed time.

## Runtime clock and visible state

Before the complete health → capabilities → events → closing health poll,
Session records its monotonic start and conservative `sampled_unix_ms`.
Only a validated successful poll advances a nonzero, nonwrapping success
sequence and replaces that start Instant. `last_attempt_unix_ms` records
completion separately. Failed polls do not advance the sequence or
retimestamp the last successful read; a known-run read cannot renew either.

Each snapshot with runtime history adds an optional
`hepta.runtime_sample_clock`, separate from the immutable `last_observation`:

```json
{
  "observation_sequence": 1,
  "sample_age_at_snapshot_ms": 6000
}
```

The age is recalculated from the successful read start to snapshot creation,
rounded **up** to milliseconds. A 7,000 ms duration plus one nanosecond is
reported as 7,001 ms. An absent successful sample, missing clock metadata or
a reversed monotonic duration is never represented as a zero-age success.

`RuntimeReceiptClock` binds the sample to the enclosing Session instance,
original AgentId, spawn generation, process PID and successful-read sequence.
Normal lifecycle changes to current generation do not change that source.
A different source starts an independent bound and must supply its own
valid age. A missing-history frame from the same Session preserves the
previous clock internally; a later repeated sample cannot use that missing
frame to reset its age. A higher successful-read sequence can establish a
new bound.

| Condition | Runtime result |
| --- | --- |
| Total monotonic bound and source wall age are both at most 7 seconds | Keep `Observed` |
| Total monotonic bound exceeds 7 seconds | `Stale`, `session_snapshot_expired` |
| Original wall sample is older than 7 seconds | `Stale`, `hepta_observation_expired` |
| Source wall timestamp is in the future | `Stale`, `hepta_observation_time_invalid` |
| Observed history has no runtime clock | `Stale`, `hepta_observation_age_missing` |
| Successful sequence is zero or regresses within its source | `Stale`, a bounded sequence diagnostic |
| Request/receipt/evaluation time is reversed, absent or inconsistent with the clock's source | `Stale`, `session_snapshot_time_invalid` |
| `Observed` contains no last observation | `Unavailable`, `hepta_observation_missing` |
| View is already stale, unavailable, connecting or unconfigured | Preserve its existing state and diagnostic |

Expiry leaves the complete successful observation and the Session's attempt
timestamp unchanged. It never promotes a view to `Observed`; only a later
valid Session snapshot can restore the current display. Runtime expiry
does not expire a separately fresh run, invent host IPC loss, submit a task
or change the configured Agentd endpoint. The actual runtime-page layout
diagnostic uses the same bound and source predicate as the visible status.

## Independently sampled known run

The launcher's optional `TRILL_HEPTA_RUN_ID` enables a separate read-only
run card. Its existing clock follows the same total-age arithmetic, using
the start of its own bounded health → run status → closing health read.
Snapshot metadata `hepta.run.sample_age_at_snapshot_ms` accompanies its
immutable successful observation, whose sequence is independent of runtime
health. Its source key is `(session_instance, run_id)`.

A first null `RunStatus` result has no successful run sample and omits that
age. A later null result preserves historical owner fields and means only
that the current owner projection lacks the requested run. It cannot
resolve submission uncertainty, prove non-admission or authorize replay.
Missing age, identity/sequence mismatch and reversed clocks remain unknown.
This change does not add a submission ledger or change run-status semantics.

## Wire compatibility

An observed runtime now includes `runtime_sample_clock` even when no known
run is configured. `hepta.run` remains omitted in that case; the whole
configured-runtime snapshot is not byte-for-byte equal to older frames.
Deploy matching Session, Shell and `trill-ctl` builds together. Older strict
decoders reject the new runtime clock field. The new decoder accepts an old
frame lacking that optional field, but Shell treats its observed runtime
history as stale/unknown. A snapshot with neither successful runtime history
nor a configured run still omits both additions. Strict unknown-field
rejection remains enabled.

## Regression and evidence boundaries

With Rust 1.88 on PATH, the exact initial RED/GREEN pair is:

```sh
cargo test --manifest-path ui/Cargo.toml --locked -p trill-shell runtime_total_age_ -- --nocapture
```

The negative case drives the real Desktop response queue and egui status
renderer with the 8,011 ms timeline above. The old predicate actually draws
`Hepta: OBSERVED · READ ONLY`; the fix must draw the stale label. Its 7,000 ms
positive control prevents an implementation that merely rejects every frame.
The additional cases cover the 7,001 ms boundary, missing/invalid ages,
future wall/monotonic times, source changes, same-source missing history,
sequence regression, independent run freshness and visible/layout agreement.
Repeated-frame cases verify both no rejuvenation and no duplicated RTT sum.

Session tests cover upward rounding, immutable sample/attempt retention and
nonwrapping success sequences. `ui/session/tests/hepta_run.rs` uses the actual
Session executable and a scripted fixed-v2 UDS peer to verify slow complete
runtime and run reads, responsive host IPC, and two failed polls that retain
the runtime success sequence while its age advances. The known-run null and
old-spawn assertions remain in that same fixture.

These are Rust, response-queue, egui-layout and scripted UDS tests. They do not
qualify original Agentd compatibility, compositor pixels, model execution,
issuer integration or desktop/mobile device effects. Every RED/GREEN result
keeps its exact source, command and executable identity. Earlier native
captures remain bound to their own source and binaries.
