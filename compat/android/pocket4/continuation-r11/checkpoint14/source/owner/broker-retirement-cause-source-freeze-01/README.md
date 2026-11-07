# Producer11 joined-retirement cause diagnostic: source only

Owner10 actually completed HELLO, broker READY, detached socket PROJECT,
COMMIT and DONE, then retired faulted before any enrollment grant. Its
original 15-file collection confirms that stderr contains only the generic
relay-retired error. The inner RetirementReceipt.reason existed, but the
bootstrap caller converted it to the faulted flag and consumed the receipt.
No claim is made that blkio/cpuset messages or SIGHUP caused this failure.

This one-file overlay borrows the original relay reason and original lifecycle
outcome immediately before receipt consumption. It emits one diagnostic line
with schema, exact nonce/authority-generation/cgroup identity and status flags.
Both causes are independently encoded as UTF-8 hex; neither overwrites the
other and the decoder can recover embedded newlines/non-ASCII bytes exactly.
No new authority, retry, thread, descriptor, timeout, PSI threshold, IPC field
or production entry is added. Healthy retirement with no cause emits nothing.
An output error is ignored and cannot replace the original error/receipt.

Four Rust tests exercise exact dual-cause retention, no healthy output, exact
UTF-8/framing and a real owned UnixStream whose peer has closed. They have NOT
been compiled or run locally: this environment has no Rust compiler. Matching
compile and ordinary execution must establish their results. Expected totals
are 30 relay and unchanged 122 supervisor library tests, plus unchanged 7 IPC
controls. A subsequent fresh owned runtime is still needed for the real cause.
This candidate is not deployed; Owner10 and every old frozen file remain intact.
