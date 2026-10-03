# Persistent service Owner v2 FOUNDATION

This Linux source candidate provides a retained root-selected policy document
and continuity of its original current Owner. It has seven public methods and
three opaque proof types. It does not connect those proofs to a request, an
Actor, a Coordinator, a Page, a journal or native Servo. Source tests and a
root kernel corpus have separate evidence domains. No caller bool, observed
snapshot, chosen attestor or principal string can construct an Owner proof.

`contracts/approved-service-owner-foundation.v2.json` is the finite source/API
contract. `tools/verify_approved_service_owner.py` is mandatory under `make
validate`; it binds complete reviewed source bytes as well as the finite Rust
public method/type inventory. The inventory is a source profile, not a Rust
compiler or an identity authority. Independent compilation and actual root
tests remain necessary. No Foundation result constitutes installed activation,
native health, hardware trust, human approval or production readiness.

## Policy input and public API

`ApprovedServicePolicyDocument::open_default()` selects exactly
`/etc/hepta/approved-mechanisms.v2.conf`. `open_root_owned(path: &Path)` is the
explicit root-owned mechanism/test-path entry. Neither entry accepts an
attestor, identity snapshot, expected runtime hash or time bypass. Both reject
relative paths, raw dot/dot-dot/doubled-slash aliases, NUL, more than 1024 path
bytes or more than 32 components. Component traversal uses retained nofollow
root-directory descriptors and a nonblocking readonly leaf. Ancestors must be
root owned and not group/world writable. The regular nonempty leaf must be
root owned, not group/world writable, one link and at most 8192 bytes.

The exact schema is `trillionnium.approved-mechanisms.v2`. Nineteen ASCII
newline-terminated `key=value` fields are required: `schema` plus `uid`, `gid`,
`unit`, `cgroup`, `elf_sha256` and `principal_id` for each of `control`, `agent`
and `owner`. Duplicate, missing, unknown, noncanonical or empty fields refuse.
IDs are canonical decimal u32 excluding MAX. Unit names are bounded to 128
bytes; cgroups to 512 bytes with normal bounded components and the selected
unit as the last component; ELF pins are 64 lowercase hex bytes; principals
are bounded ASCII identifiers of at most 64 bytes. All three principal IDs
must differ. Control and Agent entries are parsed here but not admitted or
consumed by this FOUNDATION package.

`document.ensure_current()` checks the original creator, retained and named
root path components, leaf identity and full digest before/after bounded
reads. `document.select_current_owner()` permits one atomic selection attempt
per opened source state. It attests a private actual self socket pair with
fixed `ProcfsPeerAttestor::default().attest`, compares the root-selected Owner
UID/GID/unit/cgroup/ELF pin and retains original `PeerRequestCustody`. There
is no static-executable feature fallback. A failed selection retires that
source. Second selection refuses; a separate new document is a distinct
source, not a global singleton or resurrection of any retired proof.

`ApprovedServiceOwnerBinding::ensure_current()` and `::verifier()` use the
same source and original custody. `ApprovedServiceOwnerVerifier::ensure_current()`
checks the source, the original current peer/pidfd and the source again. All
three types have private fields and no safe Clone construction. Dropping the
document leaves a retained binding current; dropping one verifier does not
revoke its binding; dropping the binding revokes issued verifiers through the
original custody. Sequential calls after that drop refuse permanently. The
package does not claim a stronger completion guarantee for concurrent calls
overlapping revocation.

## Creator identity and sticky failure

Before policy IO, private `CreatorContext` captures the real creating PID,
two private actual UnixStream endpoints, each endpoint's device/inode,
SO_COOKIE, SO_TYPE, FD_CLOEXEC and SO_PEERCRED, and a retained descriptor to
fixed `/proc/thread-self/ns/pid` verified by `NS_GET_NSTYPE == CLONE_NEWPID`.
The fixed proc namespace magic link is followed deliberately; it is not an
operator-supplied policy path and is not opened with the policy's nofollow
walker. Its retained and fresh namespace identities must agree.

An ordinary different numerical PID refuses before querying FDs or policy
resources. A nested PID namespace may reuse the same number, so that branch
also checks the exclusive original endpoints and PID namespace. Inherited
original peer credentials can report PID zero when the original creator is
outside the nested PID namespace. This is refused; a newly created pair does
not replace the original pair. Cached endpoint credentials describe creation
time only; actual default-proc Owner attestation still checks live identity.
The numeric-collision branch is deliberately not claimed to be FD-free.

Same-creator context/source/namespace failures retire the source atomically.
Restoring a pathname, content, permissions or namespace cannot revive it.
Ordinary foreign-process refusal does not retire the parent's separate fork
memory state. `InvalidConfiguration`, `SourceRefused`, `Changed`,
`ProcessChanged` and `PeerRefused` are typed refusals; the inherited v1
`DeadlineExceeded` variant does not create a new service lifetime deadline.
Namespace-local root ownership is not hostile privileged-host or firmware
trust. Unsafe same-process FD replacement is not a supported authority API.

## Actual root kernel corpus

`crates/hepta-peer-attestation/tests/approved_service_owner_kernel.rs` is one
new `harness=false` target with its default test activation retained. The
default entry uses noninteractive sudo for a root-owned private preparation
directory, copies and fully hashes the compiled ELF, writes a static
nineteen-field profile and executes that copy in a uniquely named oneshot
systemd test unit. Its Owner entry is fixed to root 0:0, that unit/cgroup and
the prepared ELF digest before Owner execution. Its Control and Agent entries
are fixed unconsumed fixtures. This preparation is a source-kernel test profile
and does not install or approve a product policy.

The new unit has `RuntimeMaxSec=90` and explicit `TimeoutStartSec=90` because
oneshot startup needs its own bounded timeout. Original native 5/20/60-second
budgets and original cases are unchanged. Unsupported namespace/capability
returns 77 with an explicit NOT PASSED diagnostic; no skip or success is
substituted. Root stages are serial and each specifically created fork child
is waited. The root selected policy and ELF receive full final byte readback,
and every group checks the exact FD inventory.

Twelve groups cover fixed root/default-proc Owner, at least 61 seconds of the
same source/binding/verifiers, binding revocation, document/verifier drop,
one selection per state, ordinary fork, nested PID1 actual Doc refusal,
five wrong static Owner fields, strict nineteen fields and root leaf custody,
leaf replacement/permission restoration, ancestor replacement/foreign root
ownership, and mount namespace change/return with sticky retirement. The
same-process namespace state being changed is confined to a specifically
waited child; no new proc mount, global namespace change or production service
configuration is created.

In nested PID1, the document is opened before the nested fork. Only the actual
`ensure_current() == ProcessChanged` result is asserted. Host-mounted proc
numeric lookup is not promoted into a fake successful nested default-proc
Owner proof. Greater-than-sixty-second **source continuity is not NativeHealth**:
it performs no browser request, page ownership, native effect or health commit.

## Compatibility and remaining work

The original v1 thirteen-field contract, APIs, source bodies, tests and
20-second request/5-second native budgets remain unchanged. Two old files
receive exact finite public module tails; two existing source checkers apply
that explicitly reviewed inverse only at their original whole-source digest
boundary. Their old EXPECTED objects and rule bodies stay unchanged apart
from that guarded read boundary. The mandatory v2 gate independently requires
both attached tails and the complete new modules; the old public export
scanner still scans every new Rust source file.

Next packages must implement per-request Control/Agent admission with fresh
bounded original deadlines, typed bridges into the original Actor and
Coordinator, persistent Page/journal state and installed root-selected
three-role execution. A source state has no service deadline to renew and
cannot mint any existing request/effect/health permit. Actual native sixty
second health, installed packaging, hardware, signing and independent human
approvals remain separate blockers. Frozen author and different-author facts
must state which source tuple and actual executions were observed; older
source/native results do not transfer to this candidate.

## Root fixture executable directory follow-up

The first actual Root source-kernel window on frozen `defcee99d5dece104bb5f364e8be686669bcc0fc`
returned 1 before any of the twelve groups or unit observations. Its preparer
created the fixed root-owned profile and ELF copy, but systemd-run refused the
`/run/hepta-service-owner-v2-kernel-<pid>/source-kernel` executable with
Permission denied. The original report is retained at
`work/persistent-owner-v2-foundation-root-kernel-facts/actual-kernel-result.json`,
SHA256 `78208dd25865d2551bb9d546830604a9234eba14d5e8111e995d818646a9602d`.
All 642 source files and the original compiled ELF were identical before and
after that attempt. Zero entered groups provide no v2 API or continuity pass.

The different-author read-only host observation at
`work/persistent-owner-v2-kernel-noexec-readonly-facts/actual-host-readonly-observations.json`,
SHA256 `4d564e5d7a7a8b81fac7f06af078f13f4e937b70f59f183cc502db1911974078`,
records `/run` as a noexec tmpfs in the same mount namespace observed by PID 1.
It records `/var/lib` on an executable ext4 mount and `/`, `/var` and `/var/lib`
as root 0:0 directories with mode 0755. These are observations of this host,
not caller-supplied authority or a requirement to change a host mount.

This narrow source successor changes only the fixed unique preparation base to
`/var/lib/hepta-service-owner-v2-kernel-<pid>`. It retains create-new allocation,
private directory mode 0700, copied ELF mode 0500, policy mode 0600, full byte
readback, cleanup, all twelve group bodies, the 61-second source-continuity
minimum and the 90-second unit budgets. The external Root runner still owns a
120-second parent bound. An unavailable or denied fixture execution remains
NOT PASSED; no permission relaxation or retry result substitutes for an actual
complete run. This source change has not itself executed the kernel groups.
Source continuity remains distinct from NativeHealth, installed activation and
production qualification.

The complete different-author read-only diagnosis is retained at
`work/persistent-owner-v2-kernel-noexec-readonly-facts/readonly-noexec-diagnosis.json`,
SHA256 `d51b5bfda88b627ac08226661efc34cebfce0f2c2ddbda33837a2552babc1fd6`.
It binds the eleven fresh host observations and the original failure. The
systemd 255 primary-source executable lookup performs its execute check before
starting the unit, so the observed noexec mount explains the pre-unit refusal.
No original-attempt syscall trace was collected; future LSM or other host
restrictions are not ruled out. The replacement fixture still needs its own
actual complete twelve-group and continuity execution.

## Test-target strict lint follow-up

The frozen `defcee99d5dece104bb5f364e8be686669bcc0fc` harness-target strict
Clippy command returned 101 after the shared package-cache wait. Its original
log at `work/persistent-owner-v2-foundation-author-facts/continued-extra-lint-0.log`
has SHA256 `9b94a7b07e0f73171691f29a50fe3e4412c966af6532ac75d5a64ea50c6128bd`.
It reported `sliced_string_as_bytes` for the missing-final-newline negative
fixture. The following two lib/tests lint commands were not executed, so that
attempt does not supply a complete test-target lint pass.

The narrow successor takes the byte view before removing the final byte. The
fixture source is the strict ASCII nineteen-field profile ending in newline,
so both expressions produce exactly the same profile bytes with that newline
removed. Its refusal assertion and every other kernel line remain unchanged.
No lint allowance, skipped case, permission change or shortened budget is
introduced. New compilation, strict test-target lint and actual kernel results
remain separate facts that must bind their own frozen successor.
