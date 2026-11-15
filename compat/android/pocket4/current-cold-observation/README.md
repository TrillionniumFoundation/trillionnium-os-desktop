# Pocket4 cold-boot observation source

The R8 guest reported a real 26-second soft lockup and a 37.8-second clocksource
readout interval. These remain open runtime failures. Its existing evidence has
no per-vCPU KVM I/O-exit counters. The candidate in this directory connects a
finite two-counter observation to the existing cold controller so a newly
admitted owner generation can measure that gap.

This is source with host regressions, not an admitted VM bundle. The paths and
input identities still present in `controller.py` identify the original R8
baseline and must not be reused as a new deployment namespace. No actual host
KVM profile, distribution-source qualification, fresh storage/VM admission,
Android boot or app acceptance is supplied here.

## Behavior

The original owned QMP connection authenticates the fixed private socket,
kernel peer PID/UID/GID, original QEMU PIDFD and the controller's existing
custody checks. It reads the original two-CPU inventory and binds each mapped
TID to a held proc-directory identity and birth time. These bindings are checked
again at request boundaries.

Before the one original `cont`, the helper compares the complete returned KVM
schema with an independently frozen profile, then records one counter baseline.
Only `exits` and `io_exits` are requested, only for those two authenticated QOM
paths. The profile must identify both as dimensionless, unscaled cumulative
counters. Missing counters are errors. Values must be scalar unsigned 64-bit
integers; booleans, replacement identities, duplicate entries and counter
rollback are rejected.

The connection stays open through the original lifetime. Runtime queries join
existing CPU/serial observation slots. A slot that would violate the rate limit
is recorded as skipped, never filled with zero. Raw requests, replies and
lifecycle events retain host wall/monotonic receipt boundaries. These boundaries
do not synchronize the guest clock with the host clock.

The only added QMP commands are `query-stats-schemas` with `provider=kvm` and
`query-stats` with the fixed vCPU paths and two names. There is no command to
stop, restart, retry `cont`, mutate QOM, pass FDs or run arbitrary monitor text.

## Bounds and failure handling

- The original 16,384-byte frame and 16-frame response limits remain.
- All raw outgoing/incoming transcript bytes share a 524,288-byte ceiling.
- Runtime requests use one absolute 250 ms monotonic deadline, clipped by the
  existing owner deadline. Each socket operation uses its remaining time; frames
  do not refresh the deadline. Host scheduling and callback work can add elapsed
  time before an overrun is detected. The measured timeout regressions took
  about 252.4 and 252.2 ms; this is not a hard real-time 250 ms guarantee.
- At most one request is outstanding. The existing 160 observation-slot bound
  and one-per-second rate limit remain; the VM and outer deadlines do not grow.
- Every error ends the probe. The original owner retains teardown authority.
  Cleanup attempts every owned descriptor even when one close reports an error.

A legitimate `SHUTDOWN` notification can arrive while the QEMU process is
still alive. It stops new counter requests but does not grant success. The
helper keeps the original connection and waits for the controller's original
PIDFD exit before collecting the remaining stream and requiring complete EOF.
The controller still requires the original unit's successful exit and all
complete guest results. A later `RESUME`, `STOP`, malformed event or incomplete
stream is rejected. The source review found this ordering defect in the first
candidate, and a real Unix-socket regression reproduced the failure before the
fix.

## Profile and owner integration

The new sealed input schema is
`p4-systemd-cold-component-native-input-stats-v2`. It adds
`qmp_stats_profile` and `qmp_stats_profile_sha256`; the latter is the SHA-256 of
the profile's canonical JSON (`sort_keys=True`, compact separators,
`ensure_ascii=True`, no NaN). The complete helper source has its own exact hash
in `validate_bundle`.

The profile schema is `p4-kvm-two-counter-profile-v1` with these exact fields:

| Field | Required binding |
| --- | --- |
| `qemu` | Complete installed binary `bytes` and `sha256`, plus exact greeting `package` |
| `host` | Actual host `release`, `version` and `boot_id` |
| `source_evidence` | SHA-256 pins for the reviewed QEMU distribution source, distribution patch set and host KVM counter definitions |
| `expected_schema` | Complete exact `query-stats-schemas(provider=kvm)` return, independently reviewed before this run |

The controller checks the actual installed QEMU bytes and host kernel/boot
against the profile. The helper checks the greeting and returned schema. Hash
syntax checks do not establish that a source audit happened: the owner must
retain the identified source and review evidence. The fixture profile in the
tests is explicitly synthetic and is not a profile for Pocket4.

The profile must fit the original frame limit. If the actual same-generation
schema cannot fit, this proposal must fail and be redesigned; it must not widen
the original frame/resource gates automatically. Upstream QEMU v10.2.1 QAPI is
a development reference, not proof of Ubuntu distribution patch identity.

Before use, the current owner must bind a fresh namespace, controller, helper,
full input bundle, exact QEMU/host source profile, current source generation,
original locks and unchanged resource admission. The original compiler policy
A remains the load input. The separately verified export B may only be selected
under its exact A-plus-kernel binding; this observer does not change that gate.

## Source preservation and tests

The PR303 public controller contains 272 `need` calls. This revision preserves
269 of those ASTs exactly. The other three explicitly change the input key set,
input schema version and exact helper-source hash. It adds three new controller
checks for the host profile, installed QEMU bytes and metadata count. All 37
other original functions remain identical. QEMU arguments, resource properties,
owned retirement, guest policy parsing and critical-console rejection remain
identical. This does not claim automatic inheritance of the older 262-call
baseline's full qualification.

Run with Python 3.12 on Linux:

```sh
python3 -I -B test_observation.py
python3 -I -B test_integration.py
python3 -I -B test_qmp_stats.py
```

The socket tests must run as UID/GID 1000 because the production helper keeps
that fixed identity requirement. CI explicitly runs just that suite under those
numeric IDs. Tests use real Unix sockets, PIDFDs and proc descriptors with a
fake QMP server. They never launch QEMU or execute a policy load. The final local
evidence is 17 observation tests, 4 integration tests and 16 QMP test methods
(including distinct hostile-frame cases). The first candidate's successful
12-method run did not cover early shutdown; the subsequent failing reproduction
is retained with the corrected regression.

Primary QAPI reference:
<https://github.com/qemu/qemu/blob/v10.2.1/qapi/stats.json>.

The next useful result is a real admitted generation's per-vCPU counter deltas
correlated with COM2 growth and CPU accounting. Correlation alone will not prove
UART IRQ starvation. Any actual soft lockup remains a hard failure.
