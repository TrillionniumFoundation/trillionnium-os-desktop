# V2 proc/maps factory component — review draft

This is a new implementation. No former factory server has been recovered or assumed.

The default executable prints a disabled contract and exits. The service entry requires two already-open, nonblocking descriptors: an abstract AF_UNIX/SOCK_SEQPACKET listener named `droidloom.proc_maps.v2`, and an owner control socket. The executable never binds or activates a socket, enters a namespace, changes credentials, mounts files, signals apps, or logs their maps. Root coordinates any actual service execution.

## Scope implemented

The V2 wire explicitly marks its statfs words as the Linux LP64 raw representation. A separate host-libc conversion clears ST_VALID only for Bionic. The client and metadata decoder consume these distinct representations; legacy V1 wire is not accepted as V2.

The factory validates its actual initial user namespace, root real/effective/saved/fs credentials and single-thread entry. It verifies the inherited listener and obtains a kernel PIDFD for the root control owner, which must be a different process in the same PID and initial user namespace. Owner death, control HUP or unsolicited control input retires the service.

A connection authenticates its real peer through SO_PEERCRED and SO_PEERPIDFD. The configured nonroot UID range is explicit. UID/GID slots, capabilities and namespace handles are read from kernel objects. Peer status and root/namespace observations are cross-checked before publication. These samples bind this request; they are **not a proof that arbitrary credential or mount transitions never occurred**.

The factory's /proc mount is verified against its actual PID namespace using a held PID 1 namespace object. An authenticated peer can have a different numeric PID view. The factory follows the peer's kernel proc-root handle, holds that root and its procfs view, verifies its PID namespace, derives the peer-visible TGID from kernel namespace IDs, and verifies the requesting TID is a member of the same process. The received maps descriptor must match the dev/inode/type of maps independently opened in that held peer view. Source statfs comes from the actual received descriptor, preserving its mount flags.

The input is an App-owned, nonempty, bounded, fully sealed tmpfs object. The service copies it into a **new** root-owned memfd, stores the V2 origin tag, sets mode 0444 and all four seals, reopens it read-only through the factory's own thread fd table, and verifies its inode, tag, flags, seals and offset before transfer. It never changes ownership of App input. The origin tag is an inode-origin convention, not an integrity or authenticity verdict about the App or payload.

The source `kOriginStartTicks` value is captured through the factory's verified procfs view for the pinned peer. It is an internal peer-generation identifier; no claim is made that it equals a time-namespace-adjusted textual value in another proc view.

## Inherited owner contract still requiring integration

The launcher must pin the exact factory executable and protocol, sanitize inherited descriptors, retain the external control creator alive, own and reap the service process, and close the control channel on retirement. It must create the abstract listener in the intended Android network namespace. A listener with the same name in another network namespace is not reachable by the App and does not qualify the service.

The READY frame on the control channel is not an independent proof of the child process identity. The launcher must bind it to the actual child/PIDFD it owns. The service will not act as a free-standing or ambient daemon without the inherited contract.

Deployment must keep the engine, ART private generation protocol, updater pair gate and factory protocol/artifact mutually bound. The current work does not yet implement the final launcher/updater lifecycle. The full overlay must update PROCMET1 markers to PROCMET2 and remain disabled until the new pair is qualified.

## Verification

The exact source and result pins are in the adjacent control reports. These reports compile the service but invoke only its no-argument disabled branch. They run pure shared-wire and proc-status/stat parsers. The Bionic branch fixture uses host compilation and is explicitly not an Android executable.

The controls compare independent fixed wire bytes, all 120 raw statfs bytes, host conversion, signed/range failures, V1 rejection, output atomicity, namespace-ID list parsing and zero-capability/four-credential-slot requirements. Deliberately broken raw and libc flag conversions must fail their corresponding controls.

The first 17-control draft did not independently assert the reply magic literal and missed a retained `DP4REP01` constant. It was corrected before service execution and supplemented with fixed wire-byte oracles. `preimage-01` and `controls-01` preserve the original text and results; later controls bind the corrected source.

## Remaining gates

- Actual peer/PID/proc/root view behavior, SCM_RIGHTS rejection and closure, owner death, timeout and service reaping need owned runtime controls.
- Trusted V2 snapshot positive cases need actual root factory plus owned nondebug Android App validation.
- Engine/default-disabled and enabled TUs, full engine link, paired ART APEX build, actual ELF audits and outer ARM64 guest adapter controls are separate gates.
- Ordinary tmpfs metadata with NOFILE=0 still returns the previously observed EMFILE. Path-owner resource and lifecycle qualifications remain open.
- Host-native credential/root/mount changes, final host thread exit and all-app acceptance are not qualified by this component.

No Main deployment or production-ready claim is authorized by these source or pure controls.
