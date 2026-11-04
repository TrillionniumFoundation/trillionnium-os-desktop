# Original Supervisor final diagnostics

## Purpose and integration

The original Unix process driver pipes Agentd stdout and stderr into the
original Supervisor's bounded in-memory log ring. The Root owner previously
printed tick faults but did not retain that ring when the Root process exited.
An Agentd fatal startup error could therefore leave only the Root's generic
owner-exited message.

The existing Root Supervisor lease now captures a bounded observation before
cleanup, runs the original cleanup unchanged, and captures a second observation
after cleanup. It writes one new file in the deployment's existing private
administrative directory: `supervisor-final.json`.
The fresh and successor entry points receive their own actual administrative
directory from the existing Product object. The phase is `startup` until
the original monitor takes ownership, then `monitor`.

This file is diagnostic evidence only. It does not grant authority, replace an
original receipt, establish a durable application outcome, or permit a retry.
A missing, partial, malformed, or unreadable file is an unavailable diagnostic.

## Data and bounds

The schema is `trill.original-root.supervisor-diagnostic.v1`.

| Field | Meaning and limit |
| --- | --- |
| `before_cleanup`, `after_cleanup` | Existing Supervisor snapshot scalars, or null when no snapshot was available. |
| `events` | Last 16 already-observed events per snapshot, with fixed event labels and original generation numbers. Dynamic event strings and release paths are omitted. |
| `last_agent_exit` | Latest original Agentd Exited event still in the original event ring, even when outside the retained 16-event tail. Success and optional code come directly from the original driver. |
| `log_tail` | At most 32 existing ring entries and 16 KiB of raw bytes in total, encoded as lowercase hex to preserve invalid UTF-8 and embedded zero bytes. |
| `log_snapshot` | Identifies the post-cleanup snapshot, or the explicit pre-cleanup fallback when no post-cleanup bytes were available. |
| `omitted_*` | Data omitted from the observed ring by this diagnostic's additional bounds. These counters cannot measure older ring evictions or dropped pipe-channel data. |
| `cleanup_observation` | Which original cleanup loop returned, or unconfirmed. It is not an independent process retirement proof. |

The original driver and Supervisor limits remain unchanged: 128 events,
256 log entries, at most 4,096 bytes per original entry, and a poll batch of 64.
No additional tick or pipe drain is performed to create this file. Late
asynchronous pipe bytes and historical ring losses are explicitly unknown.
An exit code of null remains null; no signal number is inferred.

The complete serialized document is at most 64 KiB. It contains no command line,
environment dump, dynamic event payload, or new authority material. Raw child
log bytes can nevertheless contain private data and must stay in Root custody.

## Custody and cleanup

Preparation and final persistence both require actual UID0 and EUID0. The
destination must be an existing physical Root0700 directory with the original
protected Root-owned ancestry. Its device and inode must remain the same.
Existing output is refused. The original file writer uses create-new,
O_NOFOLLOW, mode 0600, file fsync and parent-directory fsync; it never replaces
an earlier file or follows a final symlink.

Only in-memory bounded captures precede cleanup. The original stop call, its
six-second loop, the existing kill escalation, its two-second loop, and both
20 ms cadences are unchanged. The file write occurs after those original loops.
A diagnostic failure emits only a fixed message and does not restart a child,
extend a deadline, reissue an effect, or change an authority result. Abrupt Root
termination before the destructor finishes can still leave no complete file.

## Verification and limits

The added ordinary Rust fixtures use the original Fleet, Supervisor and Unix
process driver to observe a test-owned child producing stdout, non-UTF-8 stderr,
an embedded zero byte and a real exit code. Additional cases cover the full
original ring bounds, an exit outside the shortened event tail, null exit
codes, missing snapshots and refusal of a shared directory.

The explicit ignored Root fixture requires a protected Root0700
`TRILL_ROOT_DIAGNOSTIC_TEST_PARENT`. It checks the actual output's Root0600
mode, single link and create-new behavior, refuses a replaced directory inode
and aliases, and uses the existing credential-drop helper to prove UID/GID
60001 cannot read the private file. Its exact Rust test name is
`product_root::supervisor_diagnostics::tests::actual_root_private_sink_refuses_replacement_and_owner_read`.
Run it only through the already configured Root test runner, with the original
test profile and an explicit protected test directory.

Source formatting or fixture preparation does not count as a Rust test pass.
Ordinary fixture results do not qualify real Root custody; the ignored test
must run with actual Root. Neither fixture establishes power-loss durability,
completeness of every pipe byte, or production Chat/application success.
A same-pair installed reproduction is still required to diagnose a specific
Agentd failure.
