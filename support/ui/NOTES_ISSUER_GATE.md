# Original Notes issuer reply gate

This external Linux x86_64 qualification tool holds one original Root issuer
reply while the **same live Root** revokes the original signed Notes grant.
It creates no Root, issuer, clock, grant, broker, writer, consumer or product
fault flag. It changes no registers, syscall result, deadline or product ELF.
Every result has `product_qualified=false` and
`consumer_first_use_revoked_proven=false`.

Use this with the [original live administration lane](../../services/hepta-session-host/src/product_root/ADMIN.md)
and the [other recovery qualification tools](RECOVERY_QUALIFICATION.md).
It has not qualified an installed Root, original model operation or consumer.

## Source and process identity

`notes_issuer_gate_linux.py` uses the existing held-pidfd/executable/birth and
single-thread ptrace cleanup implementation. A Root0600 binding fixes the
actual boot, concrete Desktop/Hepta source IDs, exact Root/Agentd process
identity and executable hashes. Those input source strings do not establish
binary provenance: the installation receipt must do that separately.

The accepted issuer socket must have the exact original named path, Root0660
node, original Agentd group and Root02710 runtime parent. Its real
`SO_PEERCRED` must identify the held Agentd. The duplicate is obtained only
through the held Root pidfd. The socket inode/path and owner pidfd identity
are rechecked. The selected idle thread must be unique and actually blocked
in read/recvfrom of **one byte**, or poll/ppoll of exactly the issuer socket
plus the original Agentd pidfd. Thread names and the App's four-byte read
heuristic are not used. Partial starts, ambiguous threads, unsupported calls,
foreign credentials, replaced paths/FDs or denied inspection fail closed.

Only this issuer thread is traced; other Root/admin/authenticated-feed
threads and clocks keep running. Nonleader exec invalidates the boundary.
Cleanup follows the kernel's original-TID-to-held-TGID exec event, preserves
real pending signals and detaches only the held thread. SIGINT/SIGTERM request
cooperative cleanup. **SIGKILL of the controller cannot guarantee shutdown**:
the kernel may resume its tracee; reconcile the original operation and report
Unknown. The tool does not use EXITKILL to kill a genuine Root.

## Exact wire boundary and selection

The original `HostAuthorityPeerChannel` reads one idle byte, then gives the
remaining request/response one finite budget. The Root writes a real u32-BE
length before the JSON body. The gate requires all four length bytes already
written and zero body bytes written, then observes the complete original
`FinalUseResponse` at its first scalar write/sendto entry. Partial body
buffers are refused. It does not pretend the four-byte length buffer contains
the grant or claim a boundary before all reply bytes.

The selector fixes nonempty, exact original Notes `subject_id`,
`destination_id` and `scope_sha256`; `exact_binding` optionally fixes all five
binding fields too. Derive these from this actual Root's fixed Notes policy
and current target. There are no wildcards or automatic target changes. The
remaining request/payload digests are captured from the actual request, then
fixed and checked against the original grant. Unrelated known issuer requests
can pass without recording human text; at most 32 responses may precede the
selected request. No match, multiple idle matches, or timeout is not success.

The gate preserves original request/response bytes and extracts the exact
nested `SignedFinalUseGrant` substring. It does not reserialize a new signed
artifact. Pure parsing checks shape, identity, epoch, nonce and time shape,
**not cryptographic validity or unspent state**.

## Revocation and release

`notes_issuer_gate_admin.py` executes the held, Root-owned, SHA-pinned actual
`hepta-desktop-root` ELF. It does not search PATH, create a replacement Root
or accept a caller's `revoked=true` response. The held Root0600 descriptor
must identify the same actual Root PID, birth, boot and episode nonce.

At the held original body, it performs these original CLI commands in order:

1. `observe-grant --grant-id ID`: require the original volatile mirror's
   signed bytes and SHA to equal the held response exactly.
2. `observe-grant-state --signed-grant-file ARTIFACT`: require the original
   same-instance signature/policy validation, active existing effect lease,
   exact original head, no revocation, `grant_expired=false`, and both original
   authenticated consumer frontiers at that head.
3. One `revoke-grant`, using those exact effect/head revisions and a nonzero
   reason SHA. Require both actual CAS receipts, original grant identity,
   expected successor revisions/head, reason and in-validity revocation time.
4. One read-only `observe-grant-state`: independently require the exact
   original effect revocation/head and both authenticated consumer frontiers.

The device and Notes state hashes are recorded separately: their used-nonce
histories can legitimately differ. Only their exact epoch/revision must match
the actual head. The tool never updates either frontier.

Only after all four steps and identity/deadline checks does detach resume the
**untouched original body syscall**. The result records detach and cleanup
completion times. It means a body syscall was resumed, not that the client
received it or a consumer rejected it. A spent grant, expiry, another grant,
Pending, a partial CAS or a caller-made receipt cannot count as the scenario.
The independent acceptance must show this original, previously undelivered
grant's **first actual consumer entry rejected as Revoked**, before expiry.

## Time and Unknown

The binding's request timeout must come from the actual package/bootstrap and
is constrained to `1..500ms`; it can shorten, never increase, the observed
budget. The gate starts its request end at the actual first-byte read exit
and tightens it with the original bounded output poll. The arm window is at
most 180s and does not reset an exchange budget. File writes, fsync, process
startup, all four CLI calls and detach consume that same end. No retry or
new allowance is given to a slow stage. Clocks are never stopped.

The original Agentd client's deadline starts **before** the Root's first byte.
A Root-only trace cannot determine its earlier exact start. The client keeps
its own original limit; if it timed out, the product scenario fails even if
the Root-side gate had time. Actual timing qualification remains necessary.

The existing admin protocol also has its own bounded lifetime and cannot
carry the gate end. Killing this tool's own CLI child after the gate expires
**does not cancel a Root CAS** already admitted. A CAS may have succeeded or
may finish after that point. The tool records `mutation_attempted`, keeps all
actual partial replies, shuts down the original issuer's write half while
still held, detaches and reports Unknown. It never retries that mutation or
resends the operation. A failure during detach can already have resumed the
body; the result preserves `body_released` rather than claiming zero bytes.
Blocking kernel I/O/cleanup can itself exceed the budget; any such late
completion fails the result, without widening the original deadline.

## Running and review artifacts

Use a new Root0700 output directory under a safe private Root parent. The
binding has schema `trill.notes.original-issuer-gate.v1` and exactly:

| Field | Original source |
| --- | --- |
| `boot_id`, `desktop_commit`, `hepta_commit` | Current boot and verified installed source combination |
| `root`, `agentd` | Actual `pid`, `start_ticks`, `uid`, `gid`, canonical `executable`, SHA-256 |
| `issuer_path` | Actual named original issuer socket |
| `request_timeout_ms` | Actual bootstrap timeout, at most 500 |
| `selector` | Exact `subject_id`, `destination_id`, 32-byte `scope_sha256`, `exact_binding` (null or full binding) |
| `instance_file` | Same live Root's original Root0600 admin descriptor |
| `cli_executable`, `cli_sha256` | Verified installed original Root CLI ELF |
| `reason_sha256` | Canonical nonzero 64-character lowercase hex reason |

```sh
python3 -I -B support/ui/notes_issuer_gate_controller.py \
  --binding /root/private/original-issuer-binding.json \
  --output /root/private/new-issuer-gate-evidence --seconds 120
```

This requires actual UID/EUID zero and kernel ptrace/pidfd_getfd permission.
There is no lower-trust fallback. Original raw artifacts and admin JSON are
Root0600; the result records hashes, instance and binding identities, actual
steps/times, mutation uncertainty, and tracing cleanup. No prompt, arbitrary
process environment or credential file is read.

## Development and qualification scope

No new Python/Rust dependencies or Cargo target are needed:

```sh
python3 -I -B -m unittest discover -s support/ui -p test_notes_issuer_gate.py
python3 -I -B -O -m unittest discover -s support/ui -p test_notes_issuer_gate.py
python3 -I -B support/ui/qualification/notes_issuer_gate_kernel_fixture.py \
  --output /absolute/new-own-kernel-evidence
python3 -I -B support/ui/qualification/notes_issuer_gate_cleanup_fixture.py \
  --output /absolute/new-own-cleanup-evidence
```

The pure fixtures are shape/comparison controls with **invalid fixture
signatures**. Kernel fixtures use only their own current-UID child/socket,
real ppoll2/read1, real body writes and real shutdown/EPIPE. They deliberately
supply a fixture-only SCM_RIGHTS duplicate to the low-level scanner; the
production CLI never accepts that alternate path. They do not qualify the
production Root path/node/peer/pidfd_getfd or actual Root admin responses.
Cleanup fixtures exercise actual signal delivery, nonleader exec and
cancellation from read-one. All children are reaped; source snapshots before
and after must agree. No fixture starts product Root, GUI or model.
