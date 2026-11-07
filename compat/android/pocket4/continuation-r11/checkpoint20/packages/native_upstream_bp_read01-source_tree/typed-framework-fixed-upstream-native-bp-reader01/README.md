# One fixed public Blueprint transfer

SOURCE_ONLY_UNRUN. Root is the sole dispatcher.

The actual owned Git reader failed because this BP blob is absent locally. It nevertheless fully verified the locked tree and observed Android.bp as mode 100644, blob 68246c4206ea702c8a66b73c37bfcacb51524086. The exact original failed report is included unchanged; no earlier reader is replayed.

This small source performs one HTTPS GET of the fixed public Gitiles commit/path with format=TEXT. It uses ordinary certificate and hostname verification, no environment proxy handler, no credentials or cookies, and no redirect or retry. The decoded source must be valid UTF-8, within 65,536 bytes, and recompute to the exact observed Git blob before any text is emitted. Canonical base64, complete HTTP body termination, and all size limits are checked. Failure output contains fixed codes and numeric status, never an unexpected response body.

The only filesystem reads are those naturally needed by Python and standard TLS trust initialization. There are no filesystem writes, subprocesses, Git commands, materialization, checkout, cache mutations, Main service actions or Android commands. Both response and connection are closed in finally; close errors keep collection failed. Qualification is limited to 10 seconds with a self alarm, connection timeout 5 seconds, and process timeout 20 seconds. The 10-second qualification deadline is not a hard wall-clock execution guarantee.

No local Python process, device request or control was run during source preparation. Success would establish only the exact public BP body and its hashes. It would not qualify current source reuse, a strict normal Soong graph, framework implementation bytecode, JNI linkage, a Main epoch or any application.
