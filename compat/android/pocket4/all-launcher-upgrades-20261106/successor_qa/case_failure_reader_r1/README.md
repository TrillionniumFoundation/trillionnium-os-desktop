# Fixed host reader for the failed task 878 case

This is a new, unexecuted reader for the already completed failure of
`close-and-observe-search-01`, controller job `1a1b272ec9d-fc05-7e0d`.
It does not replay either click, run a helper, acquire a Main/Flow lock, enter
Android, call a guard, publish reconciliation, or change any original file.

The actual controller returned failed/1 with complete durable output. Its owned
child exited normally with status 1, its held pidfd was observed and closed,
and the parent's descriptor identities returned to the original set. The
unchanged case runner returned 2, `action_attempted=true`,
`outcome_unknown=true`. Those facts are embedded as exact original bytes and
remain failed. They are not a successful case or postcondition proof.

## Why the existing summary is insufficient

The frozen `qa_contract.py` strict finish check raises
`EXACT_SUCCESSFUL_FINISH_REQUIRED` unless the actual instrumentation output has
one result and exactly finish `-1`. The frozen `Session.instrument` first saves
the command and transport evidence, then parses it. On rejection it saves the
specific nonce's `.failed-assessment.json`, including a content-free diagnostic
when the original helper failure protocol can be verified. Its surrounding
sequence still attempts the original after-state, foreground, task and helper
checks. The case runner's top-level error stores only the type and code, not
the exception's attached detailed observation.

The actual first operation and its independent post-inspection passed the
declared homepage search-node assertion. The next sequence rejected. Until
the nonce evidence is read, the summary does **not** establish whether that
rejection happened during before-state, fresh inspection, click, or after-state.
It must not be described as a completed search click or a verified search page.

## Exact read boundary

The reader pins seven frozen source files and loads only their existing pure
parser/validation/file-read definitions. The no-follow file bootstrap and
whole-process descriptor census are copied byte for byte from the already
executed inspection reader. No frozen source is changed.

Only the original scope, task-878 launch scope, exact case/request, and files in
the single fixed `steps/close-and-observe-search-01` directory may be read. That
directory is enumerated once with a closed filename grammar: three metadata
files, four case operation/postcondition filenames, the fourteen declared
nonces, at most 38 recorded commands, and at most 50 transports. Missing future
phases are recorded as absent; they are not treated as passed or inapplicable.
Unexpected names are rejected before their contents are read. Private backend
foreground transports retain their original hashes and lengths; the reader
does not invent or seek raw window text that the original backend discarded.

Every selected file is read through no-follow path components, bounded to
2 MiB, and checked against its complete stat and pathname identity. The total
original byte bound is 32 MiB. All bytes and identities are checked again before
and after creating the new private copy. The internal deadline is 120 seconds;
the exact process envelope permits 150 seconds, CPU 100%, memory 512 MiB.

The new root-owned directory is
`/home/alex/work/pocket4-beike-case-failure-evidence-20261106-r1`.
It is created once with mode 0700. `bundle.private.json` is created with
O_EXCL/no-follow, mode 0600, fsynced and fully read back. A preexisting directory
is a rejection, not a retry. The bundle contains the complete original bytes
and full identities. **The bundle is private and must not enter Git.**

Stdout contains only file hashes/counts, named phases, actual command/transport
outcomes, and the frozen parser's content-free failure diagnostic. It does not
contain inspection nodes, business text, images, titles, or private raw streams.
Collection `ok=true` means those bytes were copied and descriptors closed;
`diagnosis_completed` independently reports whether every offline consistency
check completed. Neither result is UI authority or production readiness.

## Scope of offline checks

The reader compares the saved case result with the actual controller-captured
original result. It binds the case, scope, epoch, package, UID, helper source,
task-878 launch, recorded classpaths and exact parent process. It checks every
available command against the closed original UID/path/task/instrumentation
argv set and all seven recorded authority descriptors. All original raw
stdout/stderr hashes and transport associations are checked. Each saved
successful assessment is reparsed with the unchanged helper contract. Each
saved failed assessment must reproduce its original strict error, and any
helper rejection must match the original failure diagnostic. The first
postcondition is recomputed from its original complete inspection without
exporting the node content.

No live identity is claimed. No old-task-876 success verifier, case success
producer, replacement envelope, or changed Flow consumer is used. The original
UNKNOWN remains untouched; further mutation continues to require the original
admission rules.

## Local controls and invocation

`prepare_packet.py` checks exact source and actual receipt hashes and preserves
all integer values in Python. Its only use of the previous private inspection
reader is to extract the already verified task-878 launch file's size and hash;
no node content is copied into the source or packet. The actual failed first
local assembly, before any packet existed, reported that the launch summary
did not contain the file's size; the final assembler uses that real metadata
instead of inventing a size.

`check_local_boundaries.py` checks the actual failed receipt, rejects unrelated
paths/nonces and counts beyond the declared case, rejects changed original
bytes, and exercises real unprivileged-file/symlink rejection with complete FD
restoration. It runs under actual UID 1000 and makes no fake root-positive claim.

The exact one-time request is `process-request.review-only.json`. It has not
been submitted by this agent. Root must review its complete source and request
before submitting it. No additional optional tests or Main requests are needed
to understand the currently missing failure phase.
