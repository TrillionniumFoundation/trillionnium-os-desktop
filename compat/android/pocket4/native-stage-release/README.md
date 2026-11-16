# Native full-build release consumer

The existing `stage_model.native_release` rejected every candidate because no
reviewed policy consumed actual full-build completion and retirement. This
change adds that policy to the existing evidence reader and maintenance gate.
It does not build, install, restart, recover source, hold locks or mark runtime
acceptance.

The consumer is bound to the separately published
`native597-8gib-hostreserve5-20261108-r1` execution binding, exact 597-project
source, complete 515-file builder and engine/whole-ART pair. Four caller refs
must identify actual outputs: `runtime_request`, `runtime_exit`,
`outer_runtime_admission` and `parent_work_lease_terminal`. Each ref contains
`path`, positive `bytes` and the actual lowercase SHA-256. No future receipt hash
is supplied in this package.

## What a release requires

- The actual H request and raw durable terminal agree on the job and launch
  nonce, exact launcher/packet, 8 GiB cap, CPU quota and complete successful exit.
- The original inner and outer terminals both succeed. Every adopted child has
  a known raw zero wait status; old nonzero-child exceptions are not inherited.
  No owned OOM or swap use is accepted.
- The original fresh resource receipt retains its raw meminfo hash, same job
  cgroup, 8 GiB hard cap, 5 GiB host reserve and at least 13 GiB MemAvailable.
  A historical sample or global swap cannot satisfy current admission.
- The normal build's three records, product pair, actual engine and whole ART
  APEX are exactly the already independently crypto/TU-qualified contract.
  Source success cannot become artifact success.
- The stopped-cohort before/after fences and capture retirement are complete.
  All four parent leases are released after source restoration, all six lock
  identities are distinct, no owned children remain, and all three projection
  journals are still absent.

The controller's historical file identity has six fields; stage qualification
uses nine. The consumer maps device, inode, mode, size, mtime and ctime to their
actual nine-field positions and compares every original field. It preserves
full nine-field comparisons and requires single-link evidence. This fixes a
real record-format mismatch without dropping identity validation.

Seven SHA-pinned actual documents enter the existing maintenance gate. Its
fixed predicates retain every validated document field; callers cannot provide
arbitrary predicates. The rest of the existing stage and qualifier remain
responsible for candidate composition, signed APEX verification, seven actual
translation units, fresh runtime generation and all application acceptance.

## Integration and controls

`native-release.patch` changes only `stage_model.native_release` from the reviewed
Audio r4 stage parent. `source/native_release.py` contains the same function as a
standalone, importable source fragment. The complete old stage file is not
shipped: its deployment baseline is stale and the canonical deployment already
includes SensorService. Integrate the function into the freshly reviewed common
stage source, preserve the independent Audio changes, and reseal that complete
source manifest. This package does not update `BASE_PINS` or claim that the
whole stage bundle is ready.

Run from any working directory:

```sh
python3 -I -B /path/to/native-stage-release/tests/test_native_release.py
```

The 29 portable controls exercise the actual consumer with explicitly synthetic
record fixtures. They cover complete-contract acceptance and rejection of failed
or source-only builds, unknown/nonzero/boolean raw exits, nonzero/signalled
children, partial or mixed pairs, identity drift, wrong generations, broken
resource admission, nondurable logs, lease/restore ordering and reappearing
journals. Fixtures model the existing held-reader interface; they do not qualify
real host bytes or replace its filesystem tests. No raw host, device, account or
application logs are included.

This source is prepared before the new full build has produced an actual pair.
It grants no production, installation, fresh-runtime or application acceptance.
