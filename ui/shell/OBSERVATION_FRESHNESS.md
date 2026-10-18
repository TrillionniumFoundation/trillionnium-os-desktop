# Hepta observation freshness before drawing

The Shell's IPC worker and egui event loop run independently. A valid
`Observed` response can wait in the bounded response queue while the UI
thread is paused. Its later arrival is a new local receipt, but its runtime
sample retains the original `sampled_unix_ms`.

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

The RED source commit retains the old receipt-only behavior and introduces
the same pre-draw entry and regression cases. The GREEN source adds the
shared dual-clock predicate. Their actual command results must be retained
with the corresponding source identities. Native Shell binaries and six
original-owner phase captures likewise keep their own build-source binding;
old ELF evidence must never be reassigned to this change.
