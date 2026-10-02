# Explicit native direct-INET qualification

This source procedure exercises the fixed Servo headed prototype inside a real
Linux systemd network namespace. It is disabled unless
`HEPTA_D0A02_NETNS_PROFILE=immutable-origin-v1` is explicitly supplied. It does
not enable the installed browser actor, an approved app, external egress, or
production activation. Results belong to the compiled object and actual CI
event that produced the complete packet. The contract contains the procedure,
not an embedded successful qualification result.

The normative closed profile is
[`native-direct-inet-qualification.v1.json`](../../contracts/native-direct-inet-qualification.v1.json).
The source entry is
[`network_confinement.rs`](../../experiments/servo-headed-runtime/src/network_confinement.rs);
the host launcher, independent observer and strict reader are
[`servo_namespace_qualification.py`](../../tools/servo_namespace_qualification.py).
The ordinary unit corpus contains source decoder fixtures and actual local
dual-stack canary payloads. It cannot qualify a native Servo process. The
separate `kernel-fixture` command runs actual systemd and the same compiled Rust
entry; its result explicitly states that Servo was not executed.

## Source and process boundary

The launcher requires the committed Git blobs, tested commit/tree and evidence
lane already recorded by the normal headed workflow. It binds the before-launch
compiled binary SHA-256 and device/inode, the five actual installed formatted
overlay files, and the fixed source-file inventory. Each case launches a fresh
unit and compares the live executable against that original binary identity.
The compiled Cargo executable has a separate admission path because Cargo may
retain both its example name and a hash-named hard link. The supplied source
must be a regular, current-UID executable with no group or world write access.
Both compile entry points use `umask 077`; staging never repairs an unsafe
input's permissions. Its absolute path must contain no `..` component. Every
ancestor and the source descriptor are retained through `O_NOFOLLOW` opens.
A copy and SHA-256 are produced from that same descriptor, bounded to 4 GiB and
60 seconds. Original metadata, every ancestor identity and a fresh opening of
the named source are checked before admission and after the corpus.

The launcher creates a fresh private `0700` directory below `RUNNER_TEMP`, or
the repository's parent directory when that variable is absent. This directory
is required to be outside both the conventional and explicit artifact output.
The default locations are outside `/tmp`; an explicitly configured temporary
parent must be visible to the unit, which does not enable `PrivateTmp`.
An exclusive `0500`, single-link copy is synced, verified
against the original bytes and retained through a read-only descriptor. The
write descriptor is closed before execution to avoid Linux `ETXTBSY`. Both
the workflow and shell entry use this same launcher. `source_binding`, every
unit's live executable identity and every case's binary hash refer to the
actual single-link copy. The original and copy identities and digests are
rechecked between cases and at the end. Source files, overlays, packet files
and portable evidence retain their strict single-link checks.

Only after all cases and owned-unit retirement return successfully does the
creator remove its matching copy and empty matching directory. Replaced paths
and foreign entries are refused. A failed or interrupted corpus retains the
private copy for diagnosis; no recursive cleanup or automatic repair is used.
GC in either process closes only its own descriptor copies, with ownership
detached before close. A traced Python line interruption after detachment or
at the native-close line retires the pending local descriptor and still
attempts all other owned descriptors. The attempt mark and native call share
one traceable line; an error after an attempted close never retries its integer,
which may already identify a foreign descriptor. An inherited owner is rejected
at verify/cleanup entry, before path checks or mutations. This
ephemeral source procedure does not prove every interruption between a native
descriptor-return syscall and Python field assignment, every opcode between the
close-attempt mark and the native call, repeated faults inside cleanup, or every
concurrent same-UID pathname mutation. It does not add a durable product
executable store.

`Unit` owns one random `hepta-netns-<UUID>.service` name and is restricted to its
creator PID. It uses the real systemd MainPID and ControlGroup; the `systemd-run`
forwarder is never treated as the native process. The renderer runs as the
ordinary host runner UID/GID, with `PrivateNetwork=yes`,
`RestrictAddressFamilies=AF_UNIX`, `RestrictNamespaces=yes`, native syscall ABI,
empty capability bounding/ambient sets and `NoNewPrivileges=yes`. Missing
systemd, seccomp, pidfd, pidfd_getfd, IPv6 or required permissions is a failure.
There is no skip-as-success path.

Host records reside in the case directory. The renderer writes only its
`renderer/` subdirectory: `ProtectSystem=strict`, `ProtectHome=read-only` and an
exact `ReadWritePaths` constrain that namespace's filesystem writes. Both the
actual process UID/GID and this actual property are observed. This keeps the
host observation files outside the renderer's directly writable mount path; it
does not establish an approved Unix peer/path policy or prevent a host AF_UNIX
service from acting as a proxy.

`qualify_if_requested(Role, root)` checks real CapEff/CapBnd/CapAmb, no_new_privs,
seccomp, current network namespace and process start time before engine startup.
It duplicates each entry descriptor and checks its type, device and inode. Every
socket in that inventory must actually report SO_DOMAIN=AF_UNIX. Merely entering
a network namespace does not revoke an inherited INET socket.

The entry performs actual IPv4/IPv6 TCP connection and UDP socket-bind attempts.
Only kernel-policy errors EPERM, EACCES or EAFNOSUPPORT qualify. Connection
refusal, routing failure, unsupported canary reachability or timeout cannot
stand in for denial. An actual AF_UNIX pair must exchange the fixed payload.
The source publishes a bounded private entry record and requests SIGSTOP before
Servo or content threads start.

The host retains a pidfd for that exact stopped incarnation, and the privileged
test inspector independently retains its own pidfd. It checks actual process
start, executable device/inode, UID/GID, unit membership, network namespace,
capabilities and seccomp. It duplicates **every** descriptor using the real
`pidfd_getfd` syscall and inspects every socket's actual SO_DOMAIN. Descriptor
names, identities, process incarnation and stopped state are checked again.
Only after the complete source/host binding succeeds does the launcher send
SIGCONT through the original retained handle. No content IPC token or unrelated
process command line is copied into a packet.

The embedder entry and both real direct content children must have the same
private network namespace and differ from the outside host namespace. Content
entries bind the exact parent, executable, group/session and real
`--content-process` role. The crash receipt must name one of those independently
observed content incarnations. Successful source declarations without those
host records cannot satisfy the corpus.

## Limits and lifecycle

The Rust entry has one ten-second absolute `Instant` budget. It is checked before
and after protocol probes and host observation, never renewed after resume. A
stopped process cannot execute its own timer: the host observer has its own
four-second inventory budget, the launcher has bounded startup/stop operations,
and the real unit has `RuntimeMaxSec=180` and `TimeoutStopSec=5`. An absent observer
cannot grant success; the unit is stopped or times out. These are qualification
limits, not a production broker execution-time guarantee.

Entry FD count is at most 256; entry proc text is at most 8 KiB. Raw JSON/text is
bounded, runtime logs/screenshots at most 16 MiB. A root observation reads only
the selected stopped unit member's bounded proc records. No process-wide `ps`
dump is used. Cleanup stops only the owned unit name, confirms it is inactive and
each retained process handle has exited, closes descriptors, then retires the
unit. It never uses the forwarder's PID as renderer identity or signals an
unowned numeric process group.
Every owned case cleanup is attempted even if an earlier cleanup fails. A join
interruption still closes retained descriptors once the observer has retired;
if the observer remains live, its descriptors remain owned and the case fails.
No cleanup error can produce a success verification.

`QualificationProfile::check_current` checks the same creator PID and namespace;
the object is an observation, not an egress permit. `inspect_stopped` is a
privileged qualification helper; its input selects the already owned unit
member, and its output carries actual kernel facts. `validate_binding`,
`validate_runtime`, `verify_packet` and `verify_corpus` are evidence readers.
They do not mint production/principal authority from JSON. Production authority
still requires the unavailable installed integration and external policy.

## Required corpus and raw packet

The permanent workflow first repeats the original normal checkpoint profile,
default rapid queue and three held-gesture refusals. Their stimulus/gate
functions are preserved. The new namespace corpus then runs:

- A fresh nonce-disabled default burst with exactly the original three rapid
  Down/Up pairs in one XTest batch and no per-pair ACK pacing or additional
  clicks. It retains all normal DOM/IME/chrome/resource/fault/recovery gates:
  three actual DOM Down events, three document click events, the nine bounded
  DOM down/up/click records, the original fixture-button click, exact matching
  Servo ACK IDs and both generation screenshots.
- The original chrome, window-leave and focus-loss held refusals inside fresh
  constrained units. Each admits exactly one real Down, sends no Up, produces
  the exact fresh-Servo-owner refusal and performs no fault/recovery promotion.
- Four inherited-INET negatives: host-created IPv4/IPv6 sockets passed as the
  original unit fd0 to embedder and standalone content entry. The stopped host
  observer must duplicate that actual offending fd0. Each exits 1 before Servo,
  produces a bounded refusal and no runtime PASS or input-ready marker. A
  standalone content-entry negative uses a qualification-invalid token that is
  never consumed; it is not a real Servo content generation or broker handshake.

For every case the outside host runs real IPv4 and IPv6 nonce payload/ACK
positive controls before and after the unit. The listeners must observe exactly
those four control connections and no other connection or payload. Network
unreachability alone cannot qualify. The immutable fixture at the exact
`https://fixture.netns-qualification.invalid` origin is served by the owned
resource callback from bounded immutable bytes; it holds no TCP listener and
does not perform DNS, HTTP transport, signed app admission or egress mediation.

The artifact subtree is `native-direct-inet-v1/`. Each case contains
`namespace-launch.json`, host observations, `outside-canary.json`, the host
stimulus when applicable, and a `renderer/` directory holding original runtime
facts plus `namespace-entry-<PID>-<start>.json` or a refusal. The complete
`namespace-corpus.json` binds exact source/compiled input hashes and all raw
case-byte hashes. `verify-corpus` reopens the original bytes through retained
directory descriptors from `/`, rejecting symlinks in every ancestor above
and below the packet root as well as at the leaf. It also rejects
hard links, mutable modes, duplicate/non-finite JSON, unknown/nested fields,
bool/float identity aliases, stale incarnations, omitted generations, extra
entries, changed source inventories and any claim/default drift. The reader
checks numeric identity types before comparing receipts.

Run the actual native profile only after the exact pinned target is compiled:

```sh
python3 tools/servo_namespace_qualification.py run \
  --binary "$PWD/servo-source/target/debug/examples/trillionnium_headed_runtime" \
  --output "$PWD/artifacts/servo-headed-runtime/native-direct-inet-v1"
python3 tools/servo_namespace_qualification.py verify-corpus \
  --output "$PWD/artifacts/servo-headed-runtime/native-direct-inet-v1"
```

## Remaining authority and installed gaps

AF_UNIX remains available for actual Servo/X11 IPC. Domain 1 is **not** proof of
an approved peer, path or IPC operation. Host AF_UNIX forwarding proxies,
arbitrary visible Unix endpoints and authority carried by non-socket FDs remain
unqualified. The entry inventory is not a lifetime FD admission policy: an
AF_UNIX peer could pass a new INET descriptor through SCM_RIGHTS after the stop.
Late descriptor-transfer authority and lifetime socket authority remain false
in the closed corpus and contract. No complete filesystem/IPC principal policy
is claimed. This
profile does not supply the installed systemd/browser startup, native product
PageOwner/EngineHost, identity broker, signed app catalog, external egress
admission, real Wayland/scaling, physical hardware input, clipboard or complete
browser resource-class integration. The existing HTTP resource report keeps
`network_namespace_confinement=false` and `all_protocol_confinement=false`;
this separate explicit test profile cannot promote those ceilings.

At source creation the local same-entry kernel corpus and decoder regressions
are reviewable evidence. Actual pinned Servo compilation and the complete new
namespace corpus require their own CI object and original packets. A successful
kernel helper or a source fixture never substitutes for that execution.
