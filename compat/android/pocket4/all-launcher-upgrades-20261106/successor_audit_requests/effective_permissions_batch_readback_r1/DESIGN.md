# One private readback per successful fixed batch

This local preparer replaces the default of one remote log-reader job per App
with **one closed reader for each actually successful original capture batch**.
It does not create or submit any remote process, advance the capture ledger or
interpret permission content. No future batch is predeclared successful.

`prepare_batch_private_readback.py --batch N` imports the exact frozen original
capture gate, validates its source/input closure and applies its full individual
batch capture gate: actual claim/submission, authoritative terminal, original
outer/child lifetime, all service commands, full47 identity checks and raw stream
receipts. Failure or missing evidence prevents a reader from being written.

Each normal batch has one to four target packages, so the reader contains only
two to eight literal stdout pins. The pins are taken from the successful actual
service reports in exact package/order sequence: dump-package then AppOps for
each target. Paths must be the expected `android-NN.stdout` under that batch's
fixed output root. No caller may supply a remote path. Each file keeps the
original 256 KiB maximum and aggregate raw bytes are capped at 2 MiB. The
preparer computes and records the exact actual sum and the maximum private
stdout size before a packet can be reviewed.

The five original reader functions (`need`, `sha`, `canonical`, `read_file`,
`read_host_pin`) remain byte-for-byte unchanged. This retains component-by-
component no-follow opens, root-owned regular/single-link files, exact file
size and full SHA256, all nine held/reopened-path stat fields, and finally-close
of every owned descriptor. The main function is adapted only for the literal
batch pins, capture-job binding, file/aggregate limits and a bounded final
private hex payload. The whole-process check remains the original before/after
FD count; this design does not label it a whole-process FD identity census.

The original host request remains sudo -n, isolated Python, CPU25, 256 MiB,
nice10 and timeout60. There is no action lock, Main read, namespace entry,
Android command, App invocation or permission mutation. The maximum 2 MiB raw
payload produces at most `2 * actual_raw_bytes + 32768` bytes of private JSON.
That is a declared transport/storage budget, not permission to truncate. Root
must retrieve complete original stdout and the authoritative durable terminal;
partial/truncated reader output cannot qualify, and an unknown job is reconciled
by its one original key.

## Private/public split

The **entire reader stdout**, every process-read response containing it, and all
decoded PM/AppOps logs go under the declared `p4_private_ui` directory outside
the Git project. The public project receives only source/requests, fixed pins,
start/terminal metadata, a hash-only readback receipt and a separately reviewed
minimal permission interpretation. The collector's existing raw-only status is
not promoted to semantic grant proof by a successful readback.

The successful Fcitx readback `1a1b2c25ac5-fc05-7f9f` is reused. Invoking the
preparer for its exact original capture produces a no-new-request result. Its
old single-package candidate and actual receipt remain intact.

The original microG b02 failed capture cannot qualify here. Its independently
reviewed 2 MiB correction will need actual full joint linkage before any reader
is materialized for that result. A future explicit revision can bind its exact
two successful log pins and the separately approved microG-only larger stdout;
this revision does not raise the generic per-file or aggregate limits or accept
an unverified replacement receipt.

The remaining original successful batches can each yield one reader after their
actual outcomes are present. This is a readback plan, not a capture-coordinator
workaround: no failed/STOP capture ledger is rewritten and no later capture is
admitted by this preparer.
