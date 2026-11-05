# Paired detached socket projection, ABI 2

NORMAL03 reached authenticated init HELLO and broker READY, then failed at
`project-bind-mount` with errno 22. Its original failure and exact retirement
remain unchanged. A separate actual Pocket4 owned namespace probe confirmed:
raw foreign O_PATH bind fails EINVAL; reopening the same inode in the child
namespace binds successfully; a source-owner detached clone transfers through
SCM_RIGHTS and attaches with move_mount. The two processes shared the same
initial user namespace and had distinct mount namespaces. Its exact result is
included, but it does not qualify this new producer or Android constructor.

## Paired production change

The supervisor still validates the exact READY endpoint inode, socket type,
UID/GID, mode and O_PATH descriptor. It revalidates the original HostContext
through the existing broker gate before cloning that locally opened endpoint
with `open_tree(CLONE|CLOEXEC|AT_EMPTY_PATH)`. The clone must retain the exact
inode, type, owner, mode and descriptor sealing. Only that new detached mount FD
is sent. The original endpoint proof remains retained for audit and cleanup;
the temporary clone is closed after send or on every error. The broker is a
direct exec with no namespace transition, and the worker's captured namespaces
must remain the leader's. An init-received foreign raw FD is never cloned here.

The real init constructor keeps its own newly O_EXCL-created target FD open and
uses `move_mount(F_EMPTY_PATH|T_EMPTY_PATH)` exactly once. It retains root/dev/
socket-directory owner/mode checks, socket post-stat identity checks, all
credentials, nonces, phase/rights counts, finite deadlines and first-errno
preservation. No raw bind fallback or path-based target reopening is added.

The descriptor semantics are explicitly versioned: init wire magic P4IBV2!!,
numeric ABI 2, constructor environment ABI 2 and CLI entry ABI
`droidloom-relay-entry-v2`. Old init headers are rejected before projection;
old entry binaries are refused by the existing exact ABI query. The deployment
pair must additionally bind both resulting executable/DSO SHA-256 values in the
original explicit CellSpec. No current artifact or installed service changed.

## Actual validation and limits

Local strict C compilation succeeded. Seven owned directory/projection syscall
seam controls passed, including exact empty-path move flags, a still-open target
FD with CLOEXEC, O_EXCL refusal, directory policy checks, target closure and
first errno preservation. Their move syscall is explicitly replaced and they
do not claim actual mount execution. The first local transport case failed;
the original result is preserved, and a direct local capability check records
EPERM when creating an AF_UNIX SOCK_SEQPACKET listener. The Pocket4 matching
build must still run both original 20-case transport suites and all seven
diagnostic controls. The added Rust ordinary control refuses non-O_PATH input
before mount creation; no Rust execution is claimed in this checkpoint.

Next required evidence: fresh matching Rust build and ordinary controls,
matching Android DSO build and owned C controls, then a new exact private
CellSpec/nonce/unit run showing the actual constructor PROJECTED/COMMIT/DONE,
broker ACTIVE and complete original Stop/retirement. RC critical/property
reload semantics, actual pressure and installed lifecycle qualification remain
separate open gates. No old failed cell is replayed.
