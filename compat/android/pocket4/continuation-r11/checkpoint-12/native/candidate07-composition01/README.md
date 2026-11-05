# Candidate07: host sysroot UAPI compatibility

This is a create-only source composition, based on the exact candidate06 inventory. It changes four include lists and adds one private UAPI compatibility header. The source manifest grows from 948 to 949 files; the engine inventory grows from 925 to 926. All other 944 overlay files, including 921 engine files, retain their original bytes.

The four function implementations are unchanged. The new header uses available system headers and supplies missing declarations with values checked against the observed Bionic UAPI. Syscall fallbacks are restricted to x86_64 LP64. Existing values are checked with static assertions. No kernel error is converted to success.

## Actual evidence bound by the composer

The exact candidate06 full source contract is retained as `references/base-source-contract.py`. It verifies the original complete source inventory, its six signal fixes, the earlier NOFILE host and Android comparison, the source and actual ELF of builder450, and the prior source projection assumptions. These earlier runtime results remain results for their original source and artifacts.

The composer additionally checks the actual `host-glibc-uapi-tu-control-01` receipt with SHA-256 `5a09aa094c960a2bcc2d357fa732aac0cdb95203d25d3b690ced62497bb1c1d1`. The original host compiler and sysroot reproduced the unpatched missing `linux/memfd.h` failure. The five candidate translation units compiled with all original target, warning, and sysroot flags. Their actual dependency inventories include all five files introduced by this composition. The 13 commands have one expected preimage failure and twelve successful commands. The actual control reported no changed inputs, timeout, unreaped child, or owned OOM event.

`ACTUAL_TU_BINDING.json` records a local read-only check of the complete actual receipt and the exact source bytes, using explicit local path mappings. It did not reexecute the compiler, run an object, compose the remote candidate, or access Main.

## Execution and limits

`compose.py` defaults to a plan. The exact request stages seven pinned files under a new source root and invokes `--execute-once`. It verifies the entire parent before copying, uses exclusive writes, checks the complete new inventory, and revalidates the parent and proof authority afterward. Any existing output root causes rejection. It does not start a build or service, install software, alter the parent, or retry automatically.

The new compatibility includes have not yet passed the complete engine build, the complete host suite, Android ABI qualification, or app acceptance. The feature remains disabled by default. The unresolved enabled-generation/ART lifecycle work is unchanged. Candidate06, its full-build failure, and the original host header failure remain separate immutable evidence.
