# Hepta observation freshness before drawing

The Shell's IPC worker and egui event loop run independently. A valid
`Observed` response can wait in the bounded response queue while the UI
thread is paused. The Bridge records its actual transport receipt before
queue delivery; UI dequeue never replaces that timestamp. Its runtime
sample also retains the original `sampled_unix_ms`.

The previous renderer checked only the age of `hepta_last_snapshot`, which
`receive()` reset to `Instant::now()`. An old response delivered after a UI
pause could therefore briefly show `OBSERVED · READ ONLY`. The existing
one-shot `LayoutProbe` already rejected that expired sample, so marker tests
alone did not cover the visible status.

`Desktop::receive_and_refresh_hepta` is the actual entry used before every
page draws. It consumes pending responses, then samples the monotonic and
Unix clocks. `hepta_panel::expire_unfresh_observation` checks both:

| Condition | Visible result |
| --- | --- |
| Local receipt and runtime sample are each at most 7 seconds old | Keep `Observed` |
| Original sample is older than 7 seconds, even if just received | Mark `Stale`, `hepta_observation_expired` |
| Local receipt is older than 7 seconds | Mark `Stale`, `session_snapshot_expired` |
| Sample is in the future after clock rollback or invalid input | Mark `Stale`, `hepta_observation_time_invalid` |
| Local receipt is absent or later than the monotonic evaluation | Mark `Stale`, `session_snapshot_time_invalid` |
| `Observed` contains no last observation | Mark `Unavailable`, `hepta_observation_missing` |
| View is already stale, unavailable, connecting or unconfigured | Preserve its existing state and diagnostic |

The entire last successful observation and the Session's attempt timestamp
remain intact. The helper never rewrites a sample time or promotes a view
back to `Observed`. Only a subsequent Session snapshot can restore the
current state. Runtime staleness does not turn an otherwise connected host
Session offline, submit a task or rebind an Agentd endpoint.

The runtime-page layout diagnostic shares the same freshness predicate.
Checking only the marker cannot fix or qualify the visible state.

## Known-run total monotonic age

A trusted launcher's optional `TRILL_HEPTA_RUN_ID` enables a separate
read-only run card. Health polling cannot renew its sample. The Session
worker retains the start `Instant` of the successful, independently bounded
`run_status` read, including its closing health check and delivery delay.
Each Session snapshot with run history adds `sample_age_at_snapshot_ms`
inside `hepta.run`, alongside the immutable `last_observation`. It is the
monotonic duration from that start to snapshot creation, rounded **up** to
milliseconds. For example, 7,000 ms plus one nanosecond is reported as
7,001 ms. A first null result with no prior sample omits the age field and
continues to mean only that the current owner projection lacks the run ID.

Bridge records both request start and transport return before its bounded
response queue can wait. For runs, the renderer adds three durations:

| Duration | Source and purpose |
| --- | --- |
| Sample age at Session snapshot | Independent Session monotonic clock; includes worker and Session delay |
| Full IPC round trip | Bridge start to actual transport return; a conservative upper bound on the unmeasured snapshot-to-receipt transfer |
| Time since actual receipt | Bridge return to pre-draw evaluation; includes any UI queue delay |

The **sum** must be at most 7,000 ms. A larger bound expires the run even
when each duration individually is below seven seconds and the wall clock
has rolled back to near the original sample time. The full round trip may
count some time already included in the Session age, adding up to one round
trip of conservative age in addition to the sub-millisecond upward rounding.
This conservative result remains unknown, never an inferred effect or
outcome. The source wall-clock check
also remains: expired or future wall timestamps fail closed independently.

For the same `(session_instance, run_id, observation_sequence)`, a new frame
sets an anchor at its actual receipt using the larger of the previous bound
advanced to that instant and its newly computed source-age-plus-round-trip
bound. This preserves elapsed time without repeatedly adding overlapping
round trips. Only a higher successful-read sequence or an explicit new
Session/run source starts a new bound. Missing source age, reversed clocks,
sequence regression, identity mismatch or arithmetic failure cannot produce
a current run. Historical owner fields and attempt timestamps are retained.

This enhanced total-age rule applies to the configured run projection.
Runtime health retains the separate source-wall/actual-receipt checks above;
other existing projections do not acquire the new Session age field. With
no configured run, `hepta.run` is absent and the previous snapshot JSON is
unchanged. Deploy Session, Shell and `trill-ctl` from matching source when
enabling this option. An older observed-run frame lacking source age is
accepted as historical data by the new decoder but cannot appear fresh.

## Focused regression

```sh
cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-shell \
  --locked --offline observation_freshness_tests
```

The deterministic delayed-response case enqueues a sample at Unix ms
`10,000`, consumes it through the real Desktop response path, and evaluates
the frame at `18,001`. It then draws the real `hepta_panel::status` function
with egui and checks its text shapes for the stale label. An unused helper
or a change to the layout marker alone cannot satisfy this case.

The other cases cover the exact `7,000`/`7,001` ms boundaries for both clocks,
future/missing samples and local receipts, complete historical retention,
existing diagnostics and restoration by a subsequent fresh snapshot. These
are synthetic response-queue and egui layout tests. They are not original
Agentd, physical compositor or device-effect evidence.

The known-run cases additionally cover the first queued frame across wall
rollback, a 6,000 ms source age plus a 100 ms round trip plus 900/901 ms of
queue delay, missing/invalid age, and repeated snapshots that neither renew
the sample nor accumulate duplicate round trips. A bounded two-request
handshake verifies that Bridge stamps receipt before the next request and
before UI dequeue. Session unit tests check upward rounding without changing
history; its real UDS integration fixture checks that a held run read's
reported source age includes the full hold. These tests qualify the local
clock and response path, not original-owner compatibility or device effects.

The RED source commit retains the old receipt-only behavior and introduces
the same pre-draw entry and regression cases. The GREEN source adds the
shared dual-clock predicate. Their actual command results must be retained
with the corresponding source identities. Native Shell binaries and six
original-owner phase captures likewise keep their own build-source binding;
old ELF evidence must never be reassigned to this change.
