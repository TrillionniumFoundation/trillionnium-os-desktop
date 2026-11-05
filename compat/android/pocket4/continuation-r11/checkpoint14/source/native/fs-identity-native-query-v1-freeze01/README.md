# Native FS identity query policy V1, source and local controls

This independent candidate changes three production files in Bionic's seccomp component. The existing app, app-zygote and system entry points continue to construct exactly the original programs. A new private entry is available only to an LP64 x86_64 host; other builds reject that entry without installation. It has no runtime caller in this revision.

Only native syscall 122 (setfsuid) and 123 (setfsgid), and only arguments whose low 32 bits are UINT32_MAX, receive an ALLOW prefix. The entire i386 secondary branch is byte-identical to the original. Compat setfsuid32/setfsgid32 (215/216), old16 (138/139), x32 and all other numbers receive no new permission. Every other argument falls through to the original base table. An additional filter cannot override an earlier TRAP.

The actual Bionic SYSCALLS.TXT, x86 UAPI number headers and complete seccomp_policy.h are copied under references/actual-bionic-abi and checked before the local comparison. Their source reader was reported by Root to finish with exit 0 and durable complete output. This source binding does not bind installed Bionic or a target kernel.

## Actual local outcome

local05/result.json is an actual PASS for this limited local control: the full preimage/candidate translation units compile with g++ at O0 and explicit generated-policy/logging/Clang-offset fixtures; the three existing entry-point programs are identical; all 213,512 independent cBPF comparisons pass; only eight native query decisions differ; the full compat suffix is identical. Sixteen exact owned native/x32/stacking/NOFILE0 child cases pass and are reaped without timeout. Source and compiler bytes remain unchanged. This is not an AOSP Clang build or an Android policy qualification.

The policy tables in fixtures/seccomp_bpfs.h are deliberately small and explicit. Their x32 and old16 denials support the local negative control only; the complete actual AOSP-generated tables must still be compiled and checked. The mapping fixture is derived from the actual copied ABI inputs, and the seccomp_policy.h fixture is the complete actual header. The explicit offsetof fixture adapts an unchanged Clang extension for local GCC. O0 avoids a separate inherited GCC maybe-uninitialized diagnostic; it does not waive the target warning gate.

## Preserved failures and superseded scope

The first GCC baseline offsetof failure (local01) and baseline O2 maybe-uninitialized failure (local02) are preserved with their exact source revisions. local03 passed a wider explicit-fixture prototype but did not execute compat syscalls. local04's wider native/compat exception is superseded, and its overall FAIL is retained: 16 native cases passed; all 13 compat cases faulted during their int80(getpid) capability preflight, before any test filter was installed. They were all reaped.

The independent one-child compat diagnostic captured SIGSEGV, si_code 128, trap 13, error 1026, at the exact int80 instruction with eax=20. It installed no filter and exited through its own signal handler; the parent reaped it without forcing termination. This proves that this local execution environment did not execute the compat entry, not a bug in the candidate filter. These 13 cases are not converted to PASS or silently skipped. The new V1 needs no added compat permission because the current raw metadata owner uses the native x86_64 syscall instruction.

## Kernel argument reasoning

The native kernel handler takes uid_t/gid_t (32-bit) and derives the kernel identity before any credential allocation. An invalid identity returns the old filesystem ID; UINT32_MAX is invalid. Upper register bits are outside that parameter. The current source aliases distinguish the old16 compat ABI, which receives no exception here. Primary source mechanism reference: Android common kernel commit f54c77dd9953241be8b63f9239facdde82b3eb18, kernel/sys.c blob e6e0ece5f6a04401506d62fb602d7034d4273fe1, setfsuid/setfsgid definitions. This is a mechanism reference, not a Pocket4 installed-kernel source binding. Native zero/sign/arbitrary-upper variants are also exercised in actual local kernel children.

## Remaining integration gates

There is no ART/zygote runtime caller, no role authorization, no factory change, no enabled engine or image in this package. The ordinary V2 factory and its zero-capability gate, candidate07, and all 26 ordinary NOFILE controls are unchanged. The next target gate must use the actual generated Bionic policy tables, target compiler and final ELF. A separate trusted pre-guest role/factory authorization and lifecycle implementation remains necessary before any enabled test. No Main action or deployment was performed.
