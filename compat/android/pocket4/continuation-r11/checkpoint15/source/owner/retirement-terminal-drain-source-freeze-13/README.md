# Producer13: retained I/O provenance and exact terminal draining

The three preimages are exact producer11 matching-build inputs. The two
diagnostic files are byte-identical to immutable diagnostics12. Their separate
patch preserves the original openat errno, failed relative name/flags, held base
identity and caller role. It does not repair or reinterpret Owner11's unknown
boot ENOENT cause.

The separately reviewable retirement-only patch fixes a concrete public-retire
ordering defect: a broker may already have sent AUDIT and RETIRED and closed.
Sending RETIRE before reading these packets rejects that valid cleanup proof.
The new code drains actual input first through the unchanged receiver. A close
racing a send can only be discharged by the same full AUDIT/nonce/generation/
endpoint/cgroup/budget/flags checks plus the exact owned child's matching exit.
Bare HUP, an exited child or a failed command supplies no retirement evidence.
An unresolved send error remains the primary error. No command is replayed.

All work uses the original bounded deadline. A protocol/I/O retirement failure
sets a permanent poison bit before returning, so a second call cannot consume a
remaining valid tail and turn the original failure into a certificate. COMMIT
also rejects that bit. Ok(false) is only a still-pending wait and can continue.
The old slot is marked retired only where the original exact-child exit gate
already did so. Process-owner, init, cgroup cleanup and new-generation admission
remain separate requirements, with no altered authority checks or fallback.

Seven new Rust tests are expected (three diagnostic, four retirement). The four
retirement tests call the real public LifecycleBroker::retire against private
seqpacket sockets and exact owned Python children. Rust encodes the packets;
the fixed Python script only sends them and optionally waits for an exact
request. Test-only post-READY scope/handle setup does not claim public bootstrap,
leader-origin, native enrollment or Android qualification. Cases include healthy
and faulted already-closed peers, a live peer receiving one command, ten invalid
or missing-proof cases rejected again on a second call, and valid terminal data
while the child is still alive. The old send-first failure is explicitly retained
as a real transport control before successful draining in the positive test.

Local Python mechanics ran five exact embedded-script cases with owned sockets,
sealed input memfds, exact child waits and EOF checks. They do not execute Rust
or certify the production method. Local attempt01 lacked fcntl seal constants
in the default interpreter; attempt02 exposed the test script's inherited
nonblocking socket wait. Both originals remain. The script now sets bounded
timeouts on its two inherited sockets; attempt03 passed under /usr/bin/python3.
The script itself is unchanged by later Rust-only edits, and its hash is checked.

Rust is unavailable locally. Matching compile and the actual 37 relay / 122
supervisor tests, two original public controls (1 pass / 36 filtered), seven IPC,
worker context and ABI3 checks remain required. No device/runtime request is in
this source freeze. Owner11 remains failed with incomplete original retirement
and separately completed outer cleanup. Main, pressure thresholds, RC reload
and all-App production qualification are unchanged.
