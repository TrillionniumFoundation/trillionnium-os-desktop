# Isolated signal canary — preparation r1

This revision implements **preparation and read-only verification**. It never
starts Android, systemd units, a compositor, a presenter, an Activity, or an APK.
The runtime adapter is a separate reviewable revision. Nothing here promotes a
candidate into Main or establishes commercial-app readiness.

## Frozen basis

`v5_original.py` is the exact previously successful private-cell runner, SHA-256
`895ecbfec6d04170adf0dbc16a0fd18d3de0b78317efec86de1846295dfcddb8`.
It is retained **as a reference only**, and is never imported or executed by
`prepare.py`; its old Main PIDs and Activity probes are not a current contract.
The new preparation follows the corresponding successful v5 preparation:
copy its 86 frozen runtime artifacts, rewrite sources only into a new private
stage, replace that stage's single native-engine override, and format fresh
8 GiB userdata plus 128 MiB metadata images. Existing userdata is never read.

The eventual runtime must use the original real fixture: a separate headless
Sway output, private D-Bus and Wayland sockets, an actual owned presenter, and a
private daemon/cell. Main's presenter socket, physical output and input are not
part of this fixture. No simulated bridge handshake or security-policy change
is permitted.

## Fill and pin the input contract

Copy `inputs-template.json` to a new attempt input file. Existing exact device
paths/hashes are populated from the two read-only device exports. Empty fields
must be filled explicitly from **completed actual** new engine receipts and
the location of this frozen source delivery. Empty fields deliberately fail
before any mutation. The suggested attempt name, host UID 2401 and subordinate
range 14000000..14099999 have not been reserved on the device: collision checks
must succeed; any conflict requires a newly reviewed input contract.

Required missing engine fields are the exact new `android-out` engine path and
hash, the same output's `droidloom-native-engine-inputs.json` and final
`droidloom-native-engine-source.json` paths/hashes, and the remote location of
the frozen `signal-mask-r1-pins.json`. A request receipt, cancelled job, partial
build, or `--tests` merely being requested cannot substitute for a completed
`selected_artifacts_built` receipt. That final receipt must bind the exact six
raw and effective signal candidate files, the x86_64 ELF engine and the built
full host-suite target.

The two probe APKs remain their independently frozen r2/r3 packages. Their
build receipts must bind every source file plus the original SOURCE_PINS.json;
no Activity and no permission declaration is allowed. Preparation does not
alter them or run them. R3's pre-fix R16 failures are retained independently.

Once every field is reviewed, compute the exact input-file SHA-256 and pass it
explicitly to all commands. No mode rediscovers or silently accepts another
Main generation. The activation pin is the retained 2026-11-04 Main baseline:
framework, daemon, presenter, launcher, data-directory identity, resource
bounds and mounted engine are checked read-only. A changed baseline stops work.

```sh
sudo python3 prepare.py check-inputs --inputs /absolute/reviewed-input.json --inputs-sha256 INPUT_SHA256
sudo python3 prepare.py prepare --inputs /absolute/reviewed-input.json --inputs-sha256 INPUT_SHA256
sudo python3 prepare.py check-prepared --inputs /absolute/reviewed-input.json --inputs-sha256 INPUT_SHA256
```

Commands are examples, not evidence that they were executed. The actual
`runner_manifest.path` must point to this revision's `source-manifest.json` and
its exact externally recorded SHA-256. Use non-optimized Python: `-O` would
disable assertions in the retained original runtime and is explicitly refused.

`check-inputs` is read-only. `prepare` claims a fresh attempt directory with
exclusive creation and writes only its new evidence/stage/data paths. Existing
paths, units, UID/GID or subordinate ranges are rejected. Files, candidate
engine, APKs and fresh data images are hashed; every image also records its
device/inode before any boot. Main is checked before and after preparation.
`check-prepared` verifies the successful preparation receipt, unchanged bytes,
unchanged Main, still-absent runtime paths/units and absence of a run claim.

Any partial failure remains in place. There is no delete-existing, resume,
automatic retry or automatic cleanup mode in this preparer. Preserve the
failure receipt; do not reuse the same attempt/nonce to hide an unknown result.

## Runtime qualification still required

The following remain explicit runtime gates, not claims made by preparation:

1. Run the complete newly built host suite with exact matching binary,
   libraries and corpora; retain full registration, XML, stdout/stderr and
   authoritative terminal status. Compare actual names and skip/disabled
   dispositions with the retained R16 suite. No filtered substitute or retry.
2. Bind a new one-shot runtime runner to this prepared receipt, its own exact
   source manifest and that full-suite completion receipt.
3. Cold-boot the private fixture with original bounded controller/bus/Sway/
   presenter/daemon resources; verify distinct namespaces, boot completion,
   private framework epoch, mounted candidate and actual translator mapping.
4. Run r2 `svc`, `smc-handler`, `smc-default` and r3 `smc-mask-edit` once each
   using the already allocated unique nonces. Save raw transport output before
   parsing; compare it with each durable nonce claim/final JSON. The pure
   `assess.py` rejects missing checks, stale nonce, wrong bytes, incomplete
   default-child cleanup or a mask edit made effective only by harness cleanup.
5. Remove only identity-matched owned probe packages, then stop only the owned
   private cell and exact unit invocations in reverse order. Keep evidence;
   prove Main's retained epoch/resources unchanged and own cgroups empty.

`verify_local.py` exercises parser admission/rejection against the measured
R16 outputs and declared synthetic receipt fixtures. It runs no native code,
device tool, service, installation or preparation. Local test success does not
qualify a cold boot, host suite or candidate engine. Its report states that
durable probe files were not independently read back in these local controls.
