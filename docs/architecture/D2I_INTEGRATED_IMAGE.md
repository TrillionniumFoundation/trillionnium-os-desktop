# D2I integrated D1 plus headed Servo image

D2I is not satisfied by placing a green D1 run beside a green host Servo run.
The gate starts from the exact D1 ext4 image qualified by D1's same-run
two-build byte-identity check, injects one exact headed Servo runtime and a
bounded qualification-only systemd overlay twice, and requires the resulting
images to be byte-for-byte identical. D2I does not inherit a cross-run or
hermetic-host reproducibility claim that D1 has not established.

The image preparation step binds every e2fsprogs mutation to the committed
`source_date_epoch` in the inclusive Unix-second range `1..4294967295`
(the ext4 superblock timestamp representation is unsigned 32-bit; values
outside that range would truncate or wrap). Debugfs receives the value with its
`@<unix-seconds>` form, not its calendar-date form; zero is rejected because
e2fsprogs treats a zero fake-time value as unset. It normalizes injected inode
times and generations, pre-existing parent-directory times, and the ext4
superblock write/check accounting fields after the repair pass. The final
read-only `e2fsck` check must still pass; these normalizations remove host-clock
metadata without weakening filesystem integrity validation.

The evidence envelope binds the complete checked-out repository through its
`tree_sha`. Its file-level `input_digests` map is generated from the D2I-01
invalidation pathspecs in `manifests/gates.v1.json`, covering every tracked
file in those domains rather than a hand-maintained subset. The exact external
Servo and e2fsprogs revisions are recorded separately in the envelope and
preparation receipt; host package/tool state remains a recorded, non-hermetic
qualification input.

The tested image boots under QEMU q35/TCG with `-nic none`. systemd starts the
existing headless Weston service, then runs the headed workspace as the
unprivileged `hepta-desktop` user. The runtime has a private network namespace,
may use AF_UNIX for Wayland and Servo IPC, and has no product AgentPort
activation marker or socket.

Content-process fault injection is a single, qualification-only systemd
helper. The runtime publishes an exact PID/start-time arm record and waits for
the helper's atomic `content-sigkill-sent.json` receipt; it never calls
`kill(2)`. The helper parses the canonical identity shape, derives start time
from the post-`comm` procfs fields, and uses exclusive `mktemp` files before
publishing receipts/proofs, so a runtime-owned state directory cannot turn a
diagnostic write into a symlink or pathname race. This keeps causality
auditable and prevents an internal runtime kill from racing the external
injector. The runtime remains supervised after it writes evidence so the
helper and acceptance unit can export diagnostics.

The external proof also binds process topology, not just a PID: before the
fault there must be exactly one active `--content-process` whose parent is the
embedder; after SIGKILL the persisted topology must contain zero active content
processes; and after recovery exactly one replacement direct child must appear
with a distinct PID/start-time identity. Any broker/launcher intermediate or
additional active content process fails closed. These facts are emitted in the
`zero_process_intermediate_topology` proof fields and asserted by guest,
QEMU-host, and workflow gates.

Guest acceptance binds the result to:

- systemd, udev, D-Bus, logind and headless Wayland being active;
- one visible native workspace window with native trusted chrome;
- exactly one logical untrusted content surface;
- page-observed pointer, button, wheel and keyboard input;
- Servo IME composition start, update and end submission;
- a second recovered content generation and recovery screenshot;
- no QEMU network device and no active product AgentPort.

On any failure, the QEMU harness exports guest acceptance/runtime state,
systemd journals, injector receipt/topology, and a bounded console diagnostic
record before returning the failure status.

The external fault proof is intentionally callback-independent: a Servo
`notify_crashed` callback is optional diagnostic telemetry, not a promotion
precondition. The current candidate still records
`actual_content_process_crash_currently_proven: false` because the exact-head
machine evidence has not yet been reviewed and replayed on integrated `main`.
D2I cannot be promoted to closed until the runtime exercises and records the
four causal facts (exact signal target, old identity disappearance, zero-process
intermediate, and distinct replacement), the exact-head workflow passes,
digest-bound evidence is committed, independent review completes, and the
exact integrated `main` revision is rerun.
