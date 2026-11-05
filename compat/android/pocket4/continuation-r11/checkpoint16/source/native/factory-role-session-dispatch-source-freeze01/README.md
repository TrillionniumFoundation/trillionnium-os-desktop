# Authenticated role-session dispatch — source freeze 01

This revision connects an already approved `Registry` handle to the real snapshot maker and a fixed response on that authenticated session. It is disabled until a trusted caller supplies the registry, handle and service-owner control lease. It does not create a listener or add a factory CLI. The existing V2 factory remains byte-identical and continues to be disabled by default.

## Production changes

- `role_session.{h,cc}` define a 192-byte response: version/size/error/descriptor-count, reserved bytes and the complete 160-byte request. The client framing entry requires that exact outstanding request. It is not a replacement for authenticating the root server.
- `DispatchOne` handles only Create, Suspend and Release on an already approved/attached grant. Begin, root-parent approval and Attach admission stay outside this entry. An operation name never supplies authority.
- Create calls `CreateAuthorizedSnapshotBefore`. The real maker still uses the original canonical proc maps inode and sealed owned payload checks, raw 120-byte filesystem metadata, final flags/seals/tag/offset checks and FinishCreate tail. A successful FD can reach sendmsg only after FinishCreate and another active-grant/owner check.
- Receive, creation and response use the same absolute two-second monotonic deadline. Nonblocking socket syscalls do not reset it. File/identity operations are checked at their existing boundaries; this is not an asynchronous interruption guarantee for a blocked kernel syscall.
- A valid maker error completes the transaction and returns an error without a descriptor; authorization failure, unsupported input, timeout, owner loss and transport failure revoke the live grant. A revoked process retains its one-time tombstone until kernel PIDFD exit. Suspend sends a staged acknowledgement then detaches with the original caller lease; Release holds a duplicate only to acknowledge after revocation.
- The independent OwnerLease requires an actual live kernel root peer PIDFD in the initial user namespace and the service PID namespace, plus a quiet held control connection. It never changes credentials or adds capabilities. Registry::Approve still requires the separate exact actual parent. Observed unchanged states do not prove that no transient change occurred.
- Known FD-bearing SCM_RIGHTS and rejected SCM_PIDFD ancillary data are adopted and closed on failure. Credentials and unknown non-FD data are not treated as descriptor numbers. Receive outputs and DispatchResult are unchanged on failure.

## Verified here

`local/result.json` records one local g++ build of both controls with -Wall -Wextra -Werror, followed by 17 real response codec/socket transport cases (247 assertions) and the root fixture's default PLAN entry. The transport uses actual socketpair/sendmsg/recvmsg, including automatic SCM_PIDFD, fd counts, exact request echo and output atomicity. The socket controls do not initialize a role Registry or create a snapshot. The matching Pocket4 compiler, Android ABI and new root dispatch execution are not qualified by this local result.

The new nine-case root fixture is source only: authorized snapshot/Release; maker rejection/recovery; wrong token; unsupported active operation; peer HUP; service-owner HUP; idle deadline; Suspend/Attach; unexpected service-owner control data. It creates only owned role/root children and fixed payloads, uses the existing real PIDFD parent approval helpers, and requires 18 normal reaps and no forced cleanup. It has not been run. It does not deterministically exercise a FinishCreate failure during snapshot construction, or every send-buffer saturation race.

## Remaining production gates

The platform still needs trusted listener/admin dispatch and typed early Android fork/role/range caller wiring; early all-thread NNP plus immutable base/range policy; approved paired engine/ART/factory identity and lifecycle; a matching build and independent source/ELF review; actual isolated positive/negative session execution. No early role label, post-hoc snapshot, or this mechanism fixture substitutes for these gates. The ordinary zero-capability V2 client, original NOFILE controls and their source identities are unchanged. This scope contains ordinary O_RDONLY dispatch controls; O_NOFOLLOW requires its separate actual runtime result and existing kernel/capability support.

`INPUT_BINDINGS.json` pins all fourteen inherited files. `CHANGE_BOUNDARIES.json` identifies two modified files, five new files and twelve unchanged inputs. The fixed snapshot verification helper is extracted verbatim with byte-range/SHA binding in HELPER_BINDING.json. Old failures and all original frozen directories remain unchanged. No Main, Android, namespace, remote service or Hepta action occurred.
