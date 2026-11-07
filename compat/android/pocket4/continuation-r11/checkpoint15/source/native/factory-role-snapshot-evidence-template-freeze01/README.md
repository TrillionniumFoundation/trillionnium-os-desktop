# Snapshot original-evidence readers, source-only template 01

The single-result template derives from the actually used registry run02 protected result reader. Only its fixed path, literal binding placeholders, and result labels change. It retains the 131072-byte bound, root-owned regular-file check, canonical path, no-follow held descriptor, exact named/held identities before and after, actual terminal size/SHA, UTF8 and compressed full-byte transport. No files, child processes, test, service, or Main action are created by either reader.

After the unique snapshot runtime has an authoritative terminal and actual result size/SHA, `make_requests.py result` can bind those two observations to a fresh request output. It cannot fill them in advance. The reader collects failure evidence as well as success evidence; binding is not a PASS assertion.

After the complete original runtime result has been retrieved, `make_requests.py logs` accepts that raw receipt and derives exactly two paths: `snapshot.stdout` and `snapshot.stderr` in the fixed original run01 directory. It preserves the raw receipt locally, requires the observed byte/SHA/six-field identities and path, re-reads that exact authority before and after both held log reads, and rejects any mismatch. The two-log reader body changes only registry-to-snapshot result labels. Missing execution/log metadata is a refusal, not a partial PASS.

Both exact requests retain sudo only for reading existing protected evidence, CPU25%, MemoryMax128MiB, nice15 and 30 seconds. Requests are source only and are never dispatched by the generator. No actual snapshot build, ELF, runtime, result or log pin is invented in this freeze. Root remains the exclusive remote dispatcher.
