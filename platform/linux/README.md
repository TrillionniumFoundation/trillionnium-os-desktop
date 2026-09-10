# Linux platform adapters — S09 technical development contract

This directory contains executable Linux mechanism adapters used by the S09 host-integration gate. They turn ambiguous operating-system state into bounded facts or typed refusals. They do not authorize a browser principal, issue a capability, execute an external effect, qualify an installed image, or grant hardware/signing/release authority.

## Status and claim ceiling

Status: `S09_SOURCE_CANDIDATE_HOST_MECHANISM_ONLY`

Claim ceiling: descriptor-confined filesystem publication, operating-system entropy and monotonic time, bounded `/proc`/cgroup-v2 identity, existing Wayland endpoint custody, and pure HTTPS/address/redirect/connected-peer policy on a Linux host. No external effect, real browser dispatch, installed image, physical hardware, signing, publication, or production release is claimed.

The narrower machine truth, gate registry, non-claims, live GitHub state and exact evidence always win over this document.

## Adapter boundaries

### Filesystem

`AtomicFileStore` publishes only into a pre-provisioned non-symlink directory tree. It walks every parent through directory descriptors with `O_DIRECTORY|O_NOFOLLOW`, creates a private exclusive temporary file, completes the write, synchronizes the file, atomically renames it, then synchronizes the parent directory. It does not create authority-bearing parent directories implicitly. Files use mode `0600` and are bounded to 16 MiB in this gate.

`read_bounded_regular_file` uses the same descriptor-relative no-follow traversal, acquires leaves with `O_NONBLOCK` before type admission so FIFOs cannot stall the check, rejects non-regular leaves, checks the byte ceiling before and during the read, and keeps the opened inode pinned throughout the operation.

### Clock and entropy

`MonotonicClock` reads `time.monotonic_ns`, remembers the last observation, rejects regression, rejects zero/negative timeout, and refuses a deadline that cannot fit the gate's signed 63-bit domain.

`OsEntropy` uses Linux `getrandom`, enforces a 1–4096 byte request, rejects short or all-zero output, and has no deterministic, timestamp, PID, file or pseudorandom fallback.

### Process and service identity

`read_process_identity` reads bounded `status`, `stat`, and `cgroup` files beneath one exact `/proc/<pid>` directory. It requires uniform real/effective/saved/filesystem UID and GID values, a positive process start time and exactly one safe cgroup-v2 row. It reports the service/scope component when present. This snapshot does not itself authorize a semantic principal; the product custody layer must combine it with `SO_PEERCRED`, pidfd liveness, executable identity and current policy.

### Wayland endpoint

`connect_wayland_endpoint` accepts one safe `WAYLAND_DISPLAY` basename and acquires both `XDG_RUNTIME_DIR` and the socket with Linux `O_PATH|O_NOFOLLOW`. It connects only through `/proc/self/fd/<endpoint-fd>` to the retained socket inode, with no pathname fallback, so endpoint or directory replacement cannot redirect the client. Directory/socket ownership and mode are checked on retained descriptors, and the connected compositor peer is bound with Linux `SO_PEERCRED`.

This adapter proves only local endpoint custody and connectivity. It does not claim a window, surface, frame, focus, pointer, keyboard, IME, popup refusal, trusted-chrome pixels or crash-placeholder behavior. Those require the real headed Servo/Wayland runtime workflow and installed-image gate.

### Controlled network policy

`validate_external_https`, `globally_routable`, `bind_connected_peer` and `validate_redirect_chain` are side-effect-free policy helpers. They:

- require credential-free HTTPS;
- bound URL bytes and redirect count;
- reject ambiguous authority, backslash, control characters and unreviewed Unicode/IDNA behavior;
- reject private, loopback, link-local, multicast, unspecified, reserved and non-global addresses;
- require the connected peer address to be a member of the exact approved DNS answer set;
- revalidate every redirect hop.

They do not perform DNS, TLS or network I/O. A future egress service must bind resolver answers, redirect decisions, connected peer, TLS identity, permit, session/origin and receipt lifecycle in one operation.

## Dependency and authority direction

```text
kernel / filesystem / procfs / AF_UNIX / Wayland endpoint
  -> platform/linux adapters
  -> bounded mechanism facts
  -> BrowserActor / capability / egress policy at a later gate
```

The adapters must never import browser planning, model output, credentials, signing keys, update state or release promotion. Policy facts do not equal authorization. A successful mechanism check must not execute or replay an effect.

## Failure semantics

Every ambiguity fails closed. Unsafe path components, symlinks, wrong file type, byte overflow, missing parent custody, partial entropy, time regression, UID/GID drift, malformed procfs, multiple cgroup-v2 rows, wrong Wayland ownership, malformed URL, unsafe address, redirect overflow or connected-peer mismatch raises a typed refusal.

No caller may convert a refusal into a success by retrying with broader permissions, following a symlink, accepting a fixture, changing a claim field, suppressing a log, weakening a limit or substituting a cached identity. A failed atomic write must leave no promoted completion receipt. A potential external effect remains never-automatic.

## Testing and evidence

Run:

```bash
python3 tools/validate_linux_platform_adapters.py
python3 -m unittest tests.test_linux_platform_adapters -v
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
```

The hostile corpus covers traversal, parent symlinks, non-regular leaves, a no-writer FIFO subprocess deadline, procfs regular-file controls, oversize and wrong-mode writes, absent pre-provisioned parents, clock/deadline bounds, entropy limits, malformed `/proc`, non-uniform identities, duplicate/unsafe cgroups, HTTPS authority attacks, literal/connected multicast parity, Unicode hostname refusal, unsafe address classes, DNS/peer mismatch, redirect downgrade/overflow, Wayland directory permissions, endpoint type, deterministic endpoint/directory replacement and `SO_PEERCRED` binding.

The permanent workflow must separately bind the exact pull-request head and the live two-parent prospective merge. Source or hosted-host success is not installed-image, hardware, signing or release evidence.

## Operations

Provision store directories through the reviewed image/package manifest with exact owner, group and mode before starting services. Do not let the application create or repair trusted directory topology. Treat storage-full, fsync, rename, ownership, entropy, clock, procfs, cgroup and Wayland errors as operational security events with bounded redacted diagnostics.

For Wayland troubleshooting, record only endpoint class, ownership result, peer-credential verification result and failure code. Do not expose raw sensitive process/session identifiers in normal logs. For network troubleshooting, record policy stage and address class without persisting credentials, private page data or full sensitive URLs.

Real PID 1, compositor, input/IME, resolver, TLS, proxy and namespace behavior must be exercised in the S09 headed-host and S10 installed-image workflows. Manual invocation cannot promote those gates.

## Compatibility and change protocol

Any change to path semantics, byte limits, file mode, sync order, entropy source, clock domain, `/proc` parsing, cgroup identity, Wayland ownership, `SO_PEERCRED`, URL grammar, address classification, redirect limit or DNS/peer binding must update atomically:

1. `contracts/linux-platform-adapters.v1.json`;
2. implementation and typed errors;
3. hostile tests and structural validator;
4. this technical development contract;
5. applicable threat/control matrices and gate invalidation paths.

Then run exact-head and prospective-merge qualification, obtain independent platform-security review, and repeat the corresponding host or installed-image evidence on the final immutable object. No compatibility shim may silently widen authority.
