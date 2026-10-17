# Independent latest-main host ABI acceptance

Exact detached main `47288c4465720d125658b392efc655b333c90868` passed the unchanged A02 unified acceptance under the fixed `nightly-2026-07-21` in this project cloud, at 2026-10-17 04:12:59–04:13:10 UTC. Its 32-line runtime addition is `Transport::decode_response_snapshot_for`, which bounds a copied HOSR response by the transport capacity and typed request before delegating to the existing decoder. Five new Rust tests exercise fixed vectors and rejected bounds/correlation.

| Actual host validation | Result |
| --- | --- |
| Required acceptance checks | 13/13, all return0, no timeout or omitted check |
| Python ABI, ordinary / optimized | 52/52 and 52/52; no skips |
| Rust unit/integration plus doctest | 74 + 1; no failed, ignored or filtered tests |
| Independent fixed vectors | 12 HOS2 + 24 semantic edge + 1 transport |
| Compiled source mutants | 12/12 killed; 17 expected negative assertions |
| fmt / strict Clippy / bare no_std | All passed; target `x86_64-unknown-none` |
| Original source custody | Git clean before/after, exact HEAD unchanged and selected input hashes unchanged |

The compiler identifies as `rustc 1.99.0-nightly`, full commit `87e5904f5eb6398af6b22eac2802c78934260c48`; Cargo full commit is `3efb1f477e99b42974b982d939fd100303cdf7db`. This was host byte-codec acceptance only. It did not install OSDK, build a new kernel, run QEMU, or validate native ioctl/copyout, trusted CapSpace, CPU limits, G1/G2 or persistence. The deliberate mutant assertion failures are successful negative controls and are kept as raw failures.

`raw/` retains all 37 files from the completed independent bundle byte-for-byte, including its original checksum table, original A02 reports, controller commands/environment/UTC/exits, before/after Git records and the consumed source archive. Compiled target directories are omitted. The source archive contains 28 selected original inputs plus the generated dependency-free `Cargo.lock`; its members are checked without extracting or executing them. The new method, new tests and unchanged acceptance runner are also checked against their captured Git blob IDs.

From any working directory, the portable offline check needs only Python's standard library and these evidence files:

```bash
python3 -I /absolute/checkout/support/build/evidence/2026-10-17-main47288-abi/verify.py
python3 -I -O /absolute/checkout/support/build/evidence/2026-10-17-main47288-abi/verify.py
```

This verifies checksums, raw command/source bindings, full fixed tool identities, the source closure and the actual raw test names/counts. It does not rerun the completed Rust/Python acceptance. The controller's original command and complete reports remain in `raw/`; replaying the acceptance requires an existing fixed nightly and a new independent output directory. No original owner source or raw bundle byte was modified while packaging this phase.
