# Isolated signal qualification runner, revision 3

This is a reviewable execution candidate. No host test binary, device service,
Android cell or APK was executed while creating this package. Root owns all
device execution. The source manifest is the external entry pin; each invocation
also requires explicit hashes for its input and previous terminal receipts.

The r1 wrapper's fresh R16 baseline and candidate complete host suites have now
actually passed. The first isolated Android attempt, a01, failed before any
probe installation at initial framework discovery and was exactly cleaned up.
Revision r2 preserves those original records and adds the diagnostics/readiness
described below. It reuses the externally pinned r1 host qualification; it does
not run or re-label the host suite as a new r2 execution.

Revision r2's source staging then exposed an independent admission error:
loading `host_suite.py` from a copied r2 directory changed its `HERE`, so its
internal verification rejected the r2 manifest against the required original
r1 hash. This happened before preparation, nonce allocation, images or services.
The failed dispatch and r2 source are retained. Revision r3 loads the verifier
from the externally pinned original r1 manifest directory. No native host suite
is repeated; a03 uses new source/evidence roots and fresh private images.

## Required order

1. Run the new host wrapper once on the frozen R16 host binary. This closes the
   missing historical cwd/environment evidence. Use the exact seven-file
   `r16-host-layout.json`, derived from the actual device inventory.
2. Obtain a successful **new** native-engine build with `--tests`, its input and
   final receipts, and the actual engine hash. A cancelled, OOM-terminated or
   merely started build is ineligible.
3. Run the same frozen host wrapper once on that build, binding the new baseline
   execution receipt. The candidate arm checks all six signal-fix raw/effective
   file hashes, the engine, host binary, three corpora and three host libraries.
4. Use the separately frozen preparation r1 to create new runtime copies and
   fresh 8 GiB userdata plus 128 MiB metadata images. Never copy Main userdata.
5. Supply the externally read `prepared.json` hash and the actual candidate
   host-suite result hash to runtime `check`, then one runtime `run`.

Each new host attempt has its own immutable input JSON, new evidence directory,
unique nonce and controller unit name. Each Android case has its own nonce from
the pinned preparation receipt. There is no automatic replay or overwrite mode.
On an ambiguous timeout, preserve the existing claim, processes and evidence for
exact reconciliation. A different path or nonce is not automatic permission to
rerun an unknown mutation.

## Exact source and input contracts

The source package contains:

- `host_suite.py`: full host baseline/candidate execution and receipt verifier.
- `host-test-contract.json`: all 3,793 real R16 registered names; 3,791 executed,
  including three specific skips; exactly two suppressed disabled cases.
- `r16-host-layout.json`: the real frozen binary, three corpora and three library
  hashes. Their combined observed size is 37,219,805 bytes. The old R16 engine
  SHA is a historical label for this arm, not a newly executed Android result.
- `run.py`: preparation admission, new owned cell, four instrumentation cases,
  exact package and reverse owned-service cleanup.
- `host-launch-inputs.json`: actual compat-unshare, host unshare, ip and Python
  pins. The compat wrapper and unshare match the successful original v5 pins.
- two host input templates and the pure local controls/results.

Edit **copies** of the templates, not frozen source files. Fill remote absolute
source paths. The candidate template also needs actual completed build receipt
and engine hashes, plus the new baseline result hash. `check` rejects placeholders.
Use the unchanged preparation r1 `inputs-template.json` for the Android input
contract. Its final receipt/engine fields must select the same build qualified
by the new host suite.

Preparation r1 source-manifest SHA:
`3f12e8bcde951712a20208aaeed04f1125bac58993ce1a3f5a93e4f950a9b103`.
Runtime does not trust standalone r1 `check-prepared` as execution authority:
it additionally checks the **external** prepared hash, exactly 86 runtime
records, both exact APKs, both fresh image identities, all four distinct case
nonces, and an independently reconstructed complete private-cell spec.

## Host suite commands

Replace bracketed arguments with reviewed literal values. Do not execute these
commands with unfilled placeholders or derive shell commands using `eval`.

Read-only admission, for either arm:

```sh
sudo /usr/bin/python3 -I /ABSOLUTE_REMOTE_RUNTIME_R1/host_suite.py check \
  --inputs /ABSOLUTE_REVIEWED_HOST_INPUT.json \
  --inputs-sha256 INPUT_SHA256 \
  --source-manifest /ABSOLUTE_REMOTE_RUNTIME_R1/source-manifest.json \
  --source-manifest-sha256 RUNTIME_MANIFEST_SHA256
```

Single actual execution in the exact unit named by that input JSON:

```sh
sudo /usr/bin/systemd-run --unit=EXACT_UNIT_FROM_INPUT_JSON \
  --description='Owned full signal host suite EXACT_NONCE_FROM_INPUT_JSON' \
  --property=Type=exec --property=Restart=no --property=RuntimeMaxSec=900 \
  --property=TimeoutStopSec=10 --property=KillMode=control-group \
  --property=OOMPolicy=stop --property=CPUQuota=100% \
  --property=MemoryMax=1G --property=MemoryHigh=infinity \
  --property=MemorySwapMax=0 --property=TasksMax=128 \
  --property=Nice=10 --property=UMask=0077 --wait --pipe -- \
  /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C \
  /usr/bin/python3 -I /ABSOLUTE_REMOTE_RUNTIME_R1/host_suite.py run \
  --inputs /ABSOLUTE_REVIEWED_HOST_INPUT.json \
  --inputs-sha256 INPUT_SHA256 \
  --source-manifest /ABSOLUTE_REMOTE_RUNTIME_R1/source-manifest.json \
  --source-manifest-sha256 RUNTIME_MANIFEST_SHA256
```

The wrapper refuses execution outside its exact independent unit. It checks
memory.max=1 GiB, memory.high=max, swap=0, one CPU quota and TasksMax=128. It
sets its affinity to the explicit single CPU in the input (template CPU 6),
disables core files and executes a fresh private fixture copy. It never changes
Main limits or the frozen original test tree.

The actual test environment contains only PATH, LANG, LC_ALL, private HOME,
private TMPDIR and the private three-library LD_LIBRARY_PATH. The working
directory is the private binary/corpus directory. Registration runs once;
the suite then runs once with `--gtest_filter=*`, `--gtest_repeat=1`, no sharding
and no enable-disabled flag. Before accepting a result it checks the complete
registration and XML sets, exact skip reasons, zero failures, exit zero, actual
process mappings of the pinned binary and three libraries, unchanged test
artifacts, unchanged Main epoch and no remaining owned test descendants or
memory-limit/OOM events. It retains stdout/stderr and terminal receipts.

If the baseline fails under these explicit limits/environment, stop and retain
the failure. The new environment is not qualified and candidate execution is
ineligible. Do not omit cases or silently raise limits to turn the same attempt
into a pass. Any necessary correction requires a separately reviewed revision
and a new explicitly authorized attempt.

## Isolated Android commands

Run the frozen preparation r1 first, with the actual completed candidate input
contract, and read back the prepared receipt SHA. No display or Android service
is started by preparation. Do not run the Main-bound `owned-probe-tools/run-r3.py`
for this isolated candidate.

Read-only runtime admission:

```sh
sudo /usr/bin/python3 -I /ABSOLUTE_REMOTE_RUNTIME_R3/run.py check \
  --inputs /ABSOLUTE_ANDROID_INPUT.json --inputs-sha256 ANDROID_INPUT_SHA256 \
  --prepared-sha256 ACTUAL_PREPARED_JSON_SHA256 \
  --preparation-source /ABSOLUTE_REMOTE_PREPARATION_R1 \
  --source-manifest /ABSOLUTE_REMOTE_RUNTIME_R3/source-manifest.json \
  --source-manifest-sha256 RUNTIME_R3_MANIFEST_SHA256 \
  --host-wrapper-source-manifest /ABSOLUTE_REMOTE_RUNTIME_R1/source-manifest.json \
  --host-suite-receipt /ABSOLUTE_CANDIDATE_HOST_EVIDENCE/result.json \
  --host-suite-sha256 ACTUAL_CANDIDATE_HOST_RESULT_SHA256 \
  --host-launch-inputs /ABSOLUTE_REMOTE_RUNTIME_R1/host-launch-inputs.json \
  --host-launch-inputs-sha256 c313ea1f0d03474b05ee2ee8ae3bb74d0131d57469fb9dbf454d03745e3002fb
```

Revision r2 changes only initial private-framework diagnostics/readiness and
separates the Android runner's source identity from the already executed r1
host qualification. The complete original r1 host manifest is externally
provided and must match `ad47718c72d7fd8ecb3ce4147fd3e6dbc2ec6f662d079103bd7ecb5a55863bc5`.
The copied `host_suite.py`, 3793-test contract and R16 fixture layout must remain
byte-identical to that manifest. Its actual completed candidate suite receipt
is revalidated by the unchanged parser. No host test is relabeled as r2.

Use a new attempt name, fresh images and new five nonces. Never restart the
failed a01 cell or reuse its prepared receipt. Its failure and exact cleanup
remain immutable; no signal case was observed in that attempt.

Before any probe install, r2 retains a bounded census of the exact owned daemon
cgroup subtree. It records the cgroup device/inode, init identity before/after,
each scoped PID's argv, executable, UIDs, parent, PID/mount namespaces and
per-file errors. Other PID namespaces are counted without retaining their
argv. A PID which leaves the owned cgroup or changes generation is not retained
as a matching identity. Reads, PIDs, directories, elapsed time and the report
size all have fixed bounds. An incomplete enumeration or changed init/cgroup
stops the run. Individual exiting-process/read-error rows remain diagnostic;
they do not establish a valid framework role.

The unmodified original `capture_android` is still the only epoch admission
authority. Only `FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING`, before any probe
action, permits another read-only observation within a 30-second admission
deadline. Every census and capture error gets a separate create-only receipt.
Other errors, Main/init/daemon changes and expired deadlines stop immediately.
An individual bounded census/guard read already underway may finish after
the deadline, but it cannot admit an epoch or start an action after it.
The first successful strict snapshot is fixed as `PRIVATE_EPOCH`; the loop
cannot be reentered once it is set or after any probe action. All four case
nonces remain at most once, with no replay path.

For the actual single `run`, use the same arguments in an independently named
root controller unit, with CPUQuota=10%, MemoryMax=256M, MemorySwapMax=0,
TasksMax=128, Type=exec, Restart=no, KillMode=control-group, OOMPolicy=stop,
TimeoutStopSec=30 and RuntimeMaxSec=1500. Do not restrict its CPU affinity:
the original v5 fixture explicitly verifies the retained 24-CPU inventory.
The exact controller unit must be new. Record its InvocationID/Description and
terminal job result. The controller creates its O_EXCL run claim before starting
the retained v5 service sequence.

The runner loads only 18 original v5 function definitions, with their original
source hash pinned. It does not execute the old module's top level, old Main PID
discovery or old Activity/default-alarm flows. Main discovery is bound to the
current pinned activation receipt. Private D-Bus, WLR headless Sway and the real
presenter get new directories and sockets; no Main Wayland/presenter socket,
physical output or input backend is used. The normal render node is used in the
same way as the successful original v5 fixture. No handshake is synthesized.

Private services retain the original limits: bus 2%/32 MiB, Sway 8%/256 MiB,
presenter 50%/512 MiB, daemon 130%/4608 MiB, swap zero, Restart=no and bounded
lifetimes. Main stays on its read-only checked activation and resource contract.
Cold boot, passive Home/IME bootstrap and stopped adbd are required.

The four cases are r2 `svc`, `smc-handler`, `smc-default`, then r3
`smc-mask-edit`. Each actual case is bound to its exact installed package UID,
version/APK hash, private epoch, guest PID, single durable nonce claim/result
and a stable actual candidate-engine mapping. A held host file descriptor binds
the mounted engine hash before and after the short case; the sampler checks
device/inode and executable mappings while the exact process is alive. Missing
mapping evidence is incomplete, never inferred from a previous case.

After each failure the wrapper preserves raw results and performs only exact
owned reconciliation/cleanup. It uninstalls its two packages in reverse order
when the same private epoch/UID/APK can still be authenticated, checks code/data
absence and the private baseline package identities, stops its own cell through
its explicit socket, then stops exact InvocationID/Description-bound services
in reverse order. It never stops a mismatching generation. Fresh files and
private runtime directories are retained as evidence rather than recursively
deleted. A service whose launch delivery is uncertain is reconciled only using
its fresh nonce-bearing Description and real InvocationID.

## Qualification boundary

A host-suite PASS qualifies only that full owned host test execution. An Android
`OWNED_SYNC_SIGNAL_CANARY_PASS` qualifies only these four owned synchronous
signal contracts on the exact candidate and private epoch. It does not establish
all asynchronous software-queued signal semantics, commercial-app root cause,
installed Main integration, all-app compatibility or production readiness.
The real r2/r3 R16 failures and original cancelled/OOM build receipts remain
separate immutable evidence; this runner does not replace them.
