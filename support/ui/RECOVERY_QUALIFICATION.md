# Linux recovery qualification tools

`notes_fault_controller.py` is an external qualification tool, not a product
authority or an alternative Notes transport. The selected Desktop/Hepta
commits remain in [the source contract](HEPTA_SHARED_PRESENTER.json). Build,
installation, human admission, the original Core thread and actual model must
be qualified separately. Controller success does not establish that the
original owner retained an Applied receipt or that product recovery passed.

## Development

`notes_fault_contract.py` observes the bounded original wire;
`notes_fault_linux.py` holds process/socket identities and traces one thread;
the CLI coordinates them. No additional Python or Rust dependency is needed.

```sh
python3 -I -B -m unittest discover -s support/ui -p test_notes_fault_contract.py
python3 -I -B -O -m unittest discover -s support/ui -p test_notes_fault_contract.py
```

These controls cover fragmented length accounting, the first complete body,
already-sent body bytes, wrong target/revision/text, duplicate fields,
non-Applied or mismatched results and hashes of the original request bytes.
They do not exercise ptrace, a real Root or an installed application. Actual
process/socket fixtures and installed-product scenarios need separate records
with tool/source hashes and real process identities.

The explicit privileged fixtures use only their own fork/exec Python children,
new private temporary directories and inherited sockets/pipes:

```sh
sudo -n python3 -I -B support/ui/qualification/notes_fault_socket_fixture.py \
  --output /absolute/new-socket-evidence
sudo -n python3 -I -B support/ui/qualification/notes_fault_cleanup_fixture.py \
  --output /absolute/new-cleanup-evidence
```

Their non-Root child UID/GID default to `SUDO_UID`/`SUDO_GID`; a direct Root
invocation must supply `--fixture-uid` and `--fixture-gid`. Output directories
must be new and outside the source checkout. Both require actual UID/EUID zero,
retain before/after source hashes, verify owned children are reaped and always
mark `product_qualified=false`. The socket fixture checks normal delivery,
real body loss/EPIPE and three exact refusal controls. The cleanup fixture
checks nonleader exec, actual signal races during attach/cleanup and idle
cancellation. Its signal wrapper schedules a real signal around the original
ptrace calls; it does not replace their kernel results.

## Exact partial-reply boundary

`ui/app-window/src/notes_organ.rs::serve` receives a request, waits for the
application worker, writes a four-byte big-endian length, then writes the
response body. The durable worker calls `NotesStore::apply_exact`, which
commits before returning its response. The first length-write syscall has
only four bytes in its arguments; it cannot reveal the Applied JSON buffer.
This implementation therefore verifies **four header bytes actually written
and zero body bytes written**, then observes the entire bounded Applied body
at its first syscall entry. It does not claim the earlier proposed boundary
before any response bytes were sent.

The observer hashes the original complete request bytes and matches its
target, operation, predecessor revision and expected UTF-8 text hash. It checks
the actual Applied response and duplicates the same kernel effect socket
through the held App pidfd. It calls only `shutdown(SHUT_WR)`, resumes the
original syscall and records its real EPIPE result. It edits no registers or
syscall results, fabricates no write success, patches no ELF, sends no request
and never opens the Notes store for writing. Recovery datagrams are untouched.

The original broker should receive the real length, fail reading the body,
poison its effect stream and retain uncertainty. The original thread/owner
must reconcile that same operation over the existing recovery lane. Verify
one revision change and the original receipt separately. A buffer observation
is not an owner receipt; later current-document edits can legitimately differ
from the old operation's saved result.

## Process and tracing contract

The tool supports Linux x86_64 scalar read/recvfrom and write/sendto. It requires
actual UID/EUID zero. The binding must be a canonical absolute regular file
owned by Root with mode 0600 and at most 16 KiB. Its schema is
`trill.notes.partial-reply-fault.v1`:

| Field | Required source |
| --- | --- |
| `boot_id` | Current kernel boot ID |
| `desktop_commit`, `hepta_commit` | Verified concrete installed package; these input strings alone prove no provenance |
| `root`, `session`, `app` | Each actual `pid`, `start_ticks`, `uid`, `gid`, canonical `executable`, SHA-256 |
| `target` | Original `session_instance`, `task_id`, `incarnation` |
| `expected_revision`, `text_sha256` | Selected operation's predecessor and intended text hash |
| `notes_state_dir` | Original durable directory matching the actual App environment |

The original Root must own the Session, which must own the App. Processes stay
held by pidfds, with UID/GID, birth and executable inode/hash checks. Executables
must be regular Root-custodied files without group/other write permissions.
The tool only inspects the state directory; it cannot make a temporary App
durable by setting an environment value.

The effect thread is selected from actual `/proc/.../syscall` metadata for a
blocking four-byte read and the private unnamed Unix stream whose kernel
pair-creator credentials match the held Session. Thread names are not used.
TID birth and held socket/FD inode identity are rechecked. Ambiguous threads,
unsupported syscalls or permissions, partial starts and changed identities
refuse the fault.

Only that thread is traced. Other UI/worker threads and clocks continue; actual
stop durations are recorded. A nonleader exec invalidates the scenario.
Cleanup follows only the held TGID and kernel `PTRACE_EVENT_EXEC` /
`PTRACE_GETEVENTMSG` transition; old-TID ESRCH is not proof of detach. Actual
signal-delivery stops preserve their signals across resume/detach. Cancellation
is checked while waiting. Cleanup sends neither SIGKILL nor SIGCONT; incomplete
cleanup fails the tool result. See the [Linux ptrace manual](https://man7.org/linux/man-pages/man2/ptrace.2.html).

## Installed-product scenario

Prepare the binding from the verified installation and original live bootstrap
before the selected replace reaches the effect channel. State/readback uses
its separate datagram; unsupported effect frames are refused. Do not substitute
a new grant, thread, App incarnation or caller-created receipt.

```sh
sudo -n python3 -I -B /absolute/reviewed/notes_fault_controller.py \
  --binding /absolute/root-private/binding.json --mode observe
sudo -n python3 -I -B /absolute/reviewed/notes_fault_controller.py \
  --binding /absolute/root-private/next-original-episode.json --mode drop-reply-body
```

Use separate genuinely approved episodes for the comparison; never replay an
uncertain operation. `observe` checks the boundary without a fault; confirm
the peer's real reply independently. `drop-reply-body` records physical
shutdown and syscall failure. `unexecuted` means only that the controller did
not inject a fault; the original operation may already have executed. The
acceptance record must bind source/binary checks, controller observations,
original broker uncertainty, owner/helper receipt readback, document identity,
revision/hash and later process recovery.
