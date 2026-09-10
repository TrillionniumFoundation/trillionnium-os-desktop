# Linux platform adapters — S09 technical development contract

This directory contains executable Linux mechanism adapters for the S09 host-integration gate. They convert ambiguous operating-system state into bounded facts or typed refusals. They do not authorize a browser principal, issue a capability, execute an external effect, qualify an installed image, or grant hardware, signing, publication, or release authority.

## Status and claim ceiling

Status: `S09_SOURCE_CANDIDATE_HOST_MECHANISM_ONLY`

Claim ceiling: descriptor-confined no-replace filesystem publication, operating-system entropy and monotonic time, bounded `/proc` and cgroup-v2 identity, retained Wayland endpoint custody, and pure HTTPS/address/redirect/connected-peer policy on a Linux host. No external effect, real browser dispatch, installed image, physical hardware, signing, publication, or production release is claimed.

The narrower machine truth, gate registry, non-claims, live GitHub state, and exact evidence always win over this document.

## Adapter boundaries

### Filesystem

`AtomicFileStore` is rooted in one retained, pre-provisioned, non-symlink directory identity. Every parent is opened descriptor-relatively with `O_DIRECTORY|O_NOFOLLOW`; no authority-bearing parent is created implicitly. Files are bounded to 16 MiB and mode `0600`.

Publication is deliberately no-replace. The store creates a private exclusive staging inode, completes the write, synchronizes that inode, installs the destination with an atomic same-directory hard link using `follow_symlinks=False`, reads back the destination bytes, digest, type, and mode, synchronizes the directory, removes the staging name, and synchronizes the directory again. An existing destination is never overwritten. There is no pathname `rename` fallback and no replay after the commit boundary.

`read_bounded_regular_file` uses descriptor-relative no-follow traversal, acquires leaves with `O_NONBLOCK` before type admission so FIFOs cannot stall the check, rejects non-regular leaves, enforces the byte ceiling before and during the read, and retains the opened inode throughout the operation.

### Clock and entropy

`MonotonicClock` reads `time.monotonic_ns`, remembers the previous observation, rejects regression, rejects non-positive timeouts, and refuses deadlines outside the gate's signed 63-bit domain.

`OsEntropy` uses Linux `getrandom`, accepts requests only from 1 through 4096 bytes, rejects short or all-zero output, and has no deterministic, timestamp, PID, file, or pseudorandom fallback.

### Process and service identity

`read_process_identity` reads bounded `status`, `stat`, and `cgroup` files beneath one exact `/proc/<pid>` directory. It requires uniform real, effective, saved, and filesystem UID/GID values, a positive process start time, and exactly one safe cgroup-v2 row. A service or scope component is reported when present. This mechanism snapshot does not itself authorize a semantic principal; product custody must additionally bind socket credentials, pidfd liveness, executable identity, and current policy.

### Wayland endpoint

`connect_wayland_endpoint` accepts one safe `WAYLAND_DISPLAY` basename and retains both `XDG_RUNTIME_DIR` and the socket with Linux `O_PATH|O_NOFOLLOW`. It connects only through `/proc/self/fd/<endpoint-fd>` to the retained socket inode, with no pathname fallback, so endpoint or directory replacement cannot redirect the client. Directory/socket ownership and mode are checked on retained descriptors, and the connected compositor peer is bound with Linux `SO_PEERCRED`.

This adapter proves only local endpoint custody and connectivity. It does not claim a window, surface, frame, focus, pointer, keyboard, IME, popup refusal, trusted-chrome pixels, or crash-placeholder behavior.

### Controlled network policy

`validate_external_https`, `globally_routable`, `bind_connected_peer`, and `validate_redirect_chain` are side-effect-free policy helpers. They require credential-free HTTPS; bound URL bytes and redirect count; reject ambiguous authority, backslashes, control characters, and unreviewed Unicode/IDNA behavior; reject private, loopback, link-local, multicast, unspecified, reserved, and non-global addresses; require the connected peer to be in the exact approved DNS set; and revalidate every redirect hop.

They perform no DNS, TLS, or network I/O. A later egress service must bind resolver answers, redirects, connected peer, TLS identity, permit, session/origin, and receipt lifecycle in one operation.

## Dependency and authority direction

```text
kernel / filesystem / procfs / AF_UNIX / Wayland endpoint
  -> platform/linux adapters
  -> bounded mechanism facts
  -> BrowserActor / capability / egress policy at a later gate
```

These adapters must never import browser planning, model output, credentials, signing keys, update state, or release promotion. Mechanism facts do not equal authorization. A successful check must not execute or replay an effect.

## Failure semantics

Every ambiguity fails closed. Unsafe components, symlinks, wrong file type, unsafe owner or mode, byte overflow, missing parent custody, entropy failure, clock regression, malformed procfs, identity drift, unsafe Wayland state, malformed URL, unsafe address, redirect overflow, or connected-peer mismatch raises a typed refusal.

Before the hard-link publication boundary, failure removes the staging name and emits no completion receipt. Once the destination link may exist, any readback, directory-sync, or cleanup failure becomes `PublicationIndeterminate`; the exception carries the intended receipt plus observed destination device/inode when available. The caller must use `AtomicFileStore.reconcile` to inspect the existing destination. Reconciliation never writes, replaces, retries, or replays the publication.

No caller may turn a refusal into success by broadening permissions, following a symlink, accepting a fixture, weakening a limit, changing a claim field, or substituting a cached identity. A potential external effect remains never-automatic.

## Testing and evidence

Run:

```bash
python3 tools/validate_linux_platform_adapters.py
python3 -m unittest tests.test_linux_platform_adapters -v
python3 tools/validate_module_documentation.py
python3 tools/validate_repository.py
python3 tools/validate_project_truth.py
```

The hostile corpus covers traversal, parent symlinks, non-regular leaves, a no-writer FIFO deadline, procfs regular-file controls, byte and mode limits, absent pre-provisioned parents, existing-destination refusal, post-publication uncertainty plus reconcile-only recovery, clock/deadline bounds, entropy limits, malformed `/proc`, non-uniform identities, duplicate or unsafe cgroups, HTTPS authority attacks, literal/connected multicast parity, Unicode hostname refusal, DNS/peer mismatch, redirect downgrade and overflow, Wayland permissions/type, deterministic endpoint and directory replacement, and `SO_PEERCRED` binding.

The permanent workflow separately binds the exact pull-request head and live two-parent prospective merge. Source or hosted-host success is not installed-image, hardware, signing, or release evidence.

## Operations

Provision trusted store directories through reviewed image/package manifests with exact owner, group, and mode before services start. Do not let an application create or repair trusted directory topology. Treat storage-full, staging-write, fsync, no-replace link, destination-readback, directory-barrier, ownership, entropy, clock, procfs, cgroup, and Wayland failures as operational security events with bounded redacted diagnostics.

On `PublicationIndeterminate`, stop automatic retries and reconcile the exact path, expected digest, expected byte length, and mode. A matching destination may be accepted as the completed fact; a missing or mismatching destination remains a hard refusal requiring operator investigation. Never replace the destination as recovery.

For Wayland troubleshooting, record only endpoint class, ownership result, peer-credential verification result, and failure code. For network troubleshooting, record policy stage and address class without persisting credentials, private page data, or full sensitive URLs.

Real PID 1, compositor, input/IME, resolver, TLS, proxy, and namespace behavior must be exercised by headed-host and S10 installed-image workflows. Manual invocation cannot promote those gates.

## Compatibility and change protocol

Any change to path semantics, byte limits, file mode, no-replace commit sequence, reconciliation semantics, entropy source, clock domain, `/proc` parsing, cgroup identity, Wayland ownership, `SO_PEERCRED`, URL grammar, address classification, redirect limit, or DNS/peer binding must atomically update:

1. `contracts/linux-platform-adapters.v1.json`;
2. implementation and typed errors;
3. hostile tests and structural validator;
4. this technical development contract;
5. applicable threat/control matrices and gate invalidation paths.

Then run exact-head and prospective-merge qualification, obtain independent platform-security review, and repeat the corresponding host or installed-image evidence on the final immutable object. No compatibility shim may silently widen authority.
