# Self-hosted qualification lanes

## Status and claim ceiling

The repository has three named self-hosted Linux/X64 runner lanes: `desktop`,
`rog`, and `pocket4`. The committed availability workflows are deliberately
manual, tokenless, and checkout-free. A successful availability probe proves
only that GitHub Actions assigned the requested labels to an online runner and
that a small read-only shell probe completed on `refs/heads/main`.

Runner availability does **not** prove an integrated desktop image, a Servo
semantic adapter, installed D4-D7 authorities, fixed hardware identity,
long-duration stability, power-loss recovery, signing-key custody, promotion,
or release readiness. Those claims require the separate evidence packages and
independent roles defined below.

## Lane inventory

| Lane | Required labels | Permitted current use | Explicit non-claim |
| --- | --- | --- | --- |
| `desktop` | `self-hosted`, `linux`, `x64` with `RUNNER_NAME=desktop` | bounded manual connectivity and capability discovery | not a fixed-BOM or product-image result |
| `rog` | `self-hosted`, `linux`, `x64`, `rog` | bounded manual availability and browser/version discovery | not D3, D8, or release evidence |
| `pocket4` | `self-hosted`, `linux`, `x64`, `pocket4` | bounded manual availability discovery | not D3, D8, or release evidence |

The label set is scheduling metadata, not a hardware attestation. A qualifying
packet must independently record immutable hardware, firmware, storage,
peripheral, image, kernel, initrd, source, and runner identities.

## Probe trust boundary

`.github/workflows/self-hosted-desktop-availability.yml` and
`.github/workflows/self-hosted-fleet-availability.yml` enforce all of the
following:

- `workflow_dispatch` only;
- `permissions: {}`;
- no repository checkout;
- `refs/heads/main` only;
- an exact expected runner name;
- bounded ten-minute jobs;
- read-only host discovery commands;
- no secrets, credentials, source mutation, artifact promotion, or release
  operation.

Browser discovery uses an explicit static command graph. A variable or
operator-controlled value must never be executed as a command. The workflows
must stay inside the governance workflow inventory and immutable action policy.

## Admission before any qualification workload

A self-hosted machine may run a higher-tier qualification workload only after
all applicable conditions are true:

1. the tested source is an exact, reviewed commit reachable from protected
   `refs/heads/main`;
2. the workflow file and every script, contract, schema, lock, and test input
   are digest-bound to that commit;
3. the relevant GitHub environment and runner group restrict execution to
   approved branches and independent operators;
4. the workspace is freshly provisioned or cryptographically measured and is
   cleaned after use;
5. production private keys are absent from the runner and ordinary Actions;
6. network access is disabled unless a gate explicitly defines a controlled,
   logged adversarial network corpus;
7. source, operator, reviewer, hardware-lab, signer, attestor, and promoter
   identities remain separated where the gate requires separation;
8. cancellation, interruption, runner replacement, missing artifacts, stale
   source, and incomplete sampling fail closed rather than resuming as a pass.

## D3 exact-image lane

D3 requires an exact integrated image containing the reviewed PageOwner,
BrowserActor, AgentPort development profile, receipt journal, and a real
Servo-owned retained-node semantic resolver. The runner must prove, from raw
artifacts rather than copied booleans:

- exact source, tree, workflow, Servo commit, image, kernel, initrd, and
  dependency identities;
- systemd PID 1, Wayland readiness, one logical Servo content surface, and
  production AgentPort default-disabled state;
- PID/UID/GID/start-time/pidfd/cgroup/unit/executable identity continuity and
  dispatch-time revalidation;
- current-frame unique retained-node resolution;
- role, accessible-name digest, structural fingerprint, document revision,
  semantic revision, and mutation-epoch revalidation in one engine-owned
  critical section;
- exactly one role-authorized action with no coordinate, DOM-order,
  name-only, page-script, cross-frame, or generic-action fallback;
- stale, absent, ambiguous, drifted, cancelled, timed-out, mutation-race,
  content-crash, browser-crash, and indeterminate no-replay cases;
- fsync-committed requested, dispatched, completed or indeterminate receipt
  chains and recovery behavior;
- attestations from the distinct roles required by the D3 evidence contract.

The pinned Servo revision currently supplies accessibility tree updates but its
servoshell AccessKit action-request path still has an upstream forwarding TODO.
D3 therefore remains blocked until a reviewed Servo patch or public engine API
provides the retained-node action boundary. Host-side coordinate synthesis or
page JavaScript is forbidden as a substitute.

## D4-D7 installed-product lane

After D3 promotion, installed-product qualification must execute the real OS and
native adapters, not only reference models:

- **D4:** same-PageOwner native input, bounded human lease, preemption, IME,
  clipboard, drag/drop, modal, navigation, minimize/show, crash, and stale
  target corpus;
- **D5:** signed trusted-app installation, internal origin, content-root
  custody, CSP, storage and service-worker partitioning, trust indicator,
  publisher enrollment, rotation, downgrade rejection, and revocation;
- **D6:** portal implementations, resolver/proxy/TLS/connected-peer controls,
  redirect reauthorization, namespace policy, and the full SSRF/rebinding and
  worker/frame bypass corpus;
- **D7:** persistent effect provider and reconciliation, no automatic replay,
  inactive-slot update, rollback state, recovery media, disk-full, partial
  write, journal corruption, interrupted update, and power-loss recovery.

Each layer is a prerequisite for the next. A source verifier or injected
in-memory backend is not installed-product evidence.

## D8 fixed-hardware lane

A D8 run must freeze a declared BOM and record at least:

- machine, board, CPU, GPU, RAM, storage, display, input, audio, network,
  firmware, TPM/Secure-Boot state where applicable, and peripheral identities;
- exact source, image, kernel, initrd, SBOM, provenance, runner image, workflow,
  operator, and wall-clock/monotonic timing identities;
- cold boot, shutdown, suspend/resume, display, input, audio, accessibility,
  multi-monitor, update/rollback, and recovery results required by the
  hardware contract;
- uninterrupted 24-hour and 72-hour datasets where required;
- the required bounded unexpected-power-loss corpus, including raw logs for
  every trial and recovery;
- independent operator and reviewer attestations over a closed artifact set.

`rog` and `pocket4` labels alone do not establish this identity. QEMU, cloud
VMs, simulated time, manually edited metrics, repeated copies of one sample, or
an interrupted run cannot satisfy D8.

## D9 signing and publication lane

D9 must not run private-key operations on any ordinary self-hosted Actions
runner. Production signing occurs offline or in an independently administered
HSM/threshold service with dual control. The ceremony must bind the exact
protected release commit, tag, image, SBOM, provenance, update metadata,
recovery metadata, previous stable release, and anti-rollback state.

The source author, approver, build operator, artifact signer, update signer,
recovery signer, release attestor, promoter, and publication approver must meet
the separation rules in the release contract. Fixture keys, repository
secrets, renamed test keys, partial signatures, or manually authored PASS
records are rejected.

## Artifact custody

Every higher-tier packet must use a closed artifact set of regular files with
canonical relative paths, byte counts, and SHA-256 digests. Symlinks, path
traversal, extra files, missing files, mutable remote references, stale source,
incomplete logs, and mismatched identities invalidate the packet and every
downstream promotion that depends on it.

## Operator commands

Availability probes are dispatched manually from the exact `main` workflow in
GitHub Actions. They take no source or promotion input. Higher-tier commands are
defined by their respective contracts and verification documentation; the
operator must archive raw evidence before running the repository verifier.

## Change protocol

A change to labels, runner name, workflow, permissions, shell command graph,
timeout, environment, hardware profile, evidence schema, trust root, threshold,
claim ceiling, or source identity invalidates affected evidence. Update the
workflow inventories, repository validator, D0T-03 source validator,
governance validator, this document, and hostile tests in the same reviewed
change.
