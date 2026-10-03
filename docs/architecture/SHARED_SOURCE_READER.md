# Shared source reader descriptor custody

`tools/browser_codec_reference_security.py::open_regular_beneath` keeps its
existing parameters and raw `int` return value. It supplies repository source
and portable evidence readers with a regular file opened relative to a retained
directory chain. It grants no peer, principal, signature, durable journal,
installed or native authority. The closed profile is
[`shared-source-reader.v1.json`](../../contracts/shared-source-reader.v1.json);
the actual filesystem regressions are
[`test_shared_source_reader.py`](../../tests/test_shared_source_reader.py).

The earlier walker opened `next_fd`, checked it, and then closed the preceding
directory. A `KeyboardInterrupt` at the ordinary Python line before that close
left the new descriptor outside cleanup. The actual before probe at original
line 194 retained the new directory FD after garbage collection. The correction
registers an empty private owner before each root, parent and leaf open. Local
variables and the ancestor list share those same owners. A line interruption
before retiring the old directory therefore keeps both FDs reachable for
cleanup. The private walker returns an owned leaf; interruption of that private
result delivery also retains descriptor cleanup through the owner.

Cleanup detaches an FD before attempting native `close`. If an ordinary line
interrupts before the attempt, the owner restores it for later cleanup. Once
native close is attempted, cleanup never retries that integer: close may have
taken effect and the process may already have reused the number for another
file. Each remaining ancestor cleanup is attempted even if an earlier close
raises. The destructor performs descriptor cleanup only and suppresses its
cleanup exception; it has no shutdown, unlock, unlink or repair operation.

The existing path policy remains in force. The supplied root and each parent
below it use `O_DIRECTORY|O_NOFOLLOW`; the leaf uses
`O_NOFOLLOW|O_NONBLOCK` and must be a regular file. The `after_component` hook
still runs after the actual new parent is opened and checked, before the old
parent is retired. Renaming that pinned parent and replacing its pathname with
a symlink does not redirect the later leaf lookup: the original directory FD
continues to select the original file. This helper does not itself validate all
absolute ancestors of an arbitrary supplied root, enforce one hard link, bound
file bytes, or attest unchanged names and bytes. Callers such as
`artifact_evidence.open_file` use `/` as the root to walk every absolute component
and add their own link, size and readback checks. Those separate requirements
are preserved rather than supplied by this cleanup correction.

The public API transfers an ordinary raw integer and close responsibility to
the caller. The final raw-result return event and later caller `os.fdopen`
delivery remain separate resource ownership gaps. The regression explicitly
observes a final raw-return trace interruption leaving the actual undelivered
FD and closes that FD as probe cleanup. This package closes the reproduced
parent-walk and private owned-stage line failures; it does not claim every
native call, opcode, final delivery or repeated cleanup interruption is closed.
Existing consumers that receive raw FDs require separate review at their own
acquisition, transfer and cleanup boundaries. Source test success supplies no
installed, Servo, boot, effect or whole-route qualification.
