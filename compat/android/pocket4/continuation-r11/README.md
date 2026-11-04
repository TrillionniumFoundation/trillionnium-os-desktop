# Pocket4 Android continuation: source and measured evidence

This continuation targets Android 17 in DroidLoom on the Pocket4 Linux host.
The existing R16 native engine and presenter repair remain the deployed baseline.
**Overall status is NO-GO. No application is declared fully production ready.**

## Completed evidence

- PackageManager returned all 182 installed packages and 45 launcher packages on the verified R16 framework generation. The matrix lists every launcher and distinguishes actual current business evidence from pending acceptance. Inventory completeness does not imply application acceptance.
- A single China Eastern launch produced a fresh native SIGILL. The preserved private tombstone contains matching JIT and undefined-helper logs for `0xd4000003`, while the verified corresponding installed libc ELF offset contains `0xd4000001`. Exact engine disassembly and ELF segment checks support this observation. The code writer, code-cache behavior and application signal recovery remain unproven. Raw commercial logs and the tombstone are not published.
- The owned descriptor-owner primitive compiled and ran on the Pocket4 host and as a nondebuggable x86_64 Android instrumentation APK. Independent descriptor tables, a full caller descriptor table, caller-thread pidfd acquisition, metadata identity and child cleanup passed. The actual Android process reported Seccomp 0 and NoNewPrivs 0; no policy was changed. This qualifies the present Pocket4 configuration only.
- The owned descriptor test APK was removed by exact package identity and APK hash. All 182 preexisting package/UID/version identities remained unchanged.
- The LMKD enrollment host crate built on Pocket4: six Rust checks and seven actual IPC controls passed. The new r6 Android source compiled and linked: six fresh translation units, recorded complete `-MD` dependencies for those units, unchanged inputs and unchanged shared-library contract. The three reused support objects retain the explicitly recorded historical system-header provenance limitation.

- The owned ARM64 baseline ran through the actual R16 native bridge: SVC passed; default SMC terminated only the owned child with SIGILL and reaped it; recoverable SMC delivered precise signal metadata and restored registers/SP/NZCV/PC, but failed the saved signal-mask check. The original failure is retained. All owned baseline packages were removed afterward.

## Work still in progress

The native metadata owner candidate fixes demonstrated descriptor-table exhaustion and close/reuse corruption, but independent review found a further resource regression when thread creation fails. The open/readlink candidate also has unresolved temporary-descriptor and classification behavior. Neither candidate is approved for deployment.

The LMKD r6 candidate connects enrollment, packet handling, session revocation and guarded synchronous signal delivery. Its host supervisor listener, unique cell ownership, namespace binding and real pressure qualification are not yet complete. The previous foreground-loss failure remains a failure; a successful build does not supersede it.

The owned ARM64 signal probe contains separate SVC, recoverable SMC and default-SMC cases. Its source is included here; individual execution receipts determine which cases have actually run. The probe modifies only its own explicitly identified signal context. It does not reinterpret SMC as a system call or change commercial APKs.

## Reproduction boundaries

`probes/tooling/build-owner-executed.py` is the exact builder revision used for the successful owner APK. `build.py` additionally supports the ARM64 signal source layout. These builders depend on separately installed, hash-pinned Pocket4 build inputs, the retained NDK archive and the preexisting owned-test signing configuration. The public repository includes no signing key, APK, shared library or commercial application data. Missing private baseline inputs must not be replaced silently.

`probes/tooling/run.py` is bound to one exact activation and framework generation. Each mutation claims a new phase and checks the owned package identity; unknown outcomes require reconciliation. It may not authorize execution on a different generation. It does not restart Android, change security policy or operate on a commercial application's data.

Original runtime receipt hashes identify private evidence. Reformatted public JSON is a derivative and does not claim byte identity with those original files. The source pins and delivery manifest below identify the public bytes separately.
