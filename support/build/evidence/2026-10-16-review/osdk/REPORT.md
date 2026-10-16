# Review-hardening native OSDK matrix

One new complete **22/22** integration run passed on source commit `f473a2ccc8dfeaed1223e8478a19c79c90b323e4`, with **0 failures, 0 blocked cases and 1 VMX-unavailable soft skip**. This is the explicit `osdk-native-local-tcp-gdb-capture-v2` profile. Its scope is OSDK tooling and small OSTD example kernels; complete Asterinas kernel acceptance is recorded separately by the parent phase. Previous Unix and TCP results remain unchanged.

`invocation.json` is the original record written **before launch**. It contains the actual command and selected environment:

```sh
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb \
  --output "$PWD/support/build/out/next5-osdk-full-01" \
  --target-dir "$PWD/support/build/out/osdk-capture-v2-02/target"
```

The parent observed actual runner exit **0** from tool session `20691`; `completion.json` records that observation separately from the original invocation. The console and all harness, OSDK, Cargo, QEMU and debugger command records are retained in `logs.tar.gz`. The reused target is the runner's isolated cache; no target files or generated example implementations are copied into this archive.

## Source, tools and actual guests

The recorded runtime HEAD is `8db0b13bc29a0177a9ddfd0a472a0a4817a078e3`. Its complete Git tree equals publication commit `f473a2c`: **`a522e35bf5c5b2def3f7aa0d5c6b9a728b4769f7`**. All **89** recorded support, OSDK production, upstream-test and fixed local `align_ext` source hashes match the published Git blobs, including all **15** integration support files. `provenance/source-bindings.json` provides every comparison; the original runtime HEAD/status is preserved unchanged.

Asterinas remains v0.19.0 commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`. The environment records actual paths, SHA256 and verbose versions for pinned Rust `nightly-2026-07-21`, rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48`, and Cargo. Generated dependency locks remain bound to the original fixed seeds and external package identities. The exact original/adapted test hashes, harness patch and normalized dependency locks are retained.

There were **11 actual QEMU guests**, all with raw exit **33**, no timeout and nonempty serial logs matching the QEMU records' expected SHA256 and size. Their actual QEMU PIDs are recorded individually in `qemu.json` and `report.json`. QEMU uses x86_64 q35, TCG, CPU `max`, one vCPU, 512 MiB, direct multiboot and explicit SeaBIOS. The hypervisor example's VMX-unavailable fallback is reported as a soft skip, not successful VMX virtualization.

The coverage guest's OSDK-managed monitor uses private, preconnected inherited **FD 64**, with connected loopback endpoints, `listening=false`, explicit named-descriptor inheritance and the actual QEMU PID **6865** in its metadata. Actual QEMU argv retains `socket,id=osdk-managed-monitor,fd=64,server=off` and `-monitor chardev:osdk-managed-monitor`. The GDB listener is separately held through QEMU spawn and passed as FD 3. These records establish the actual private transport handoff for this run; they do not relabel the original Unix profile.

## Real coverage

The original OSTD poweroff path and ISA debug-exit are preserved. Real `nm` resolves the original symbol ELF, then GDB installs a hardware breakpoint at `ostd::arch::power::try_poweroff`. The actual PC matches the exact resolved address. At that stop the same guest has emitted its coverage announcement; GDB saves fresh memory through HMP, verifies the announced size, removes its breakpoint and detaches. The original guest resumes and exits QEMU with raw **33**; actual OSDK and GDB exits are both **0**.

| Evidence | Actual value |
| --- | --- |
| Raw profile size | 2,094,448 bytes |
| Raw SHA256 | `24312473e6f0cdfc94d12dc826ae323843fbdcf5f7c1a806bf99aa335d7f7e04` |
| Pinned LLVM merge/show | Both exit 0 |
| Functions / maximum function count | 5696 / 383731 |
| Finalized capture | Passed; exact PC, symbol ELF, boot ELF, announcement, paused/final serial and raw bindings |

The actual size comes from this run's announcement and bytes, not an earlier phase's profile size. `case-15/coverage/result.json`, `case-15/guests/guest-001/coverage-capture.json` and `artifacts.json` provide the full bindings and compressed `.profraw`/`.profdata` hashes.

## Archive compatibility and integrity

The frozen hardened `archive.py` was actually executed against this completed output into a new scratch destination. It successfully selected **345 files**. All **346** entries in its original checksum file, including its index, were checked; every selected source size/SHA was checked after decompressing helper logs/metadata. `provenance/helper-archive.json` and `helper-evidence.sha256` retain those original output records unchanged.

`helper-compatibility.json` maps each historical helper output name to the retained original content: raw logs/metadata in `logs.tar.gz`, or the separately compressed coverage artifacts. This keeps the helper's original index/checksums and compatibility proof without duplicating its entire compressed output tree. The historical helper checksum file applies to that scratch output, while the phase's `SHA256SUMS` applies to the files committed here.

`members.json` lists every raw tar member's size/SHA and the tar archive's hash. Key JSON and locks are byte-identical readable copies. The tar is finalized by atomic replacement, reopened, and every member checked. Each of the **11 actual source serial files** is additionally checked against the helper snapshot, tar bytes and QEMU record, rather than accepting only matching index claims. `provenance/archive-validation.json` records these checks. No guest was rerun during archival. `SHA256SUMS` covers all final files except itself.
