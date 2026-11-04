# Pocket4 Android repair — checkpoint 06

Status: scoped implementation and runtime evidence. Whole-app production readiness remains **0/45**. No Main engine deployment is included.

This checkpoint adds the R21 metadata ABI probe, the revised R5 isolated signal runner and exact cleanup fixture, the completed a04 Android signal canary, and the init-barrier source with host controls and a matching Android compile. Every one of the 1,390 inherited payloads is unchanged. Earlier failed attempts remain part of the history and evidence.

## Observed results

| Area | Actual result | Scope |
| --- | --- | --- |
| R21 metadata probe | 16 expected cases passed; 16 direct and 2 nested children reaped; owned package/UID 10163 removed | x86-64 Android probe. Raw Linux statfs and Bionic statfs are separately represented. The outer ARM64 adapter and a real privileged factory were not exercised. |
| R5 fixture02 | One exact unit whose MainPID was zero but whose held cgroup still contained the owned child was stopped once; child PIDFD exited, child was reaped, hierarchy disappeared | One owned unit and child. The injected ENOSPC remains a recorded failure, and the fixture explicitly does not qualify a full canary. |
| a04 synchronous signals | All four actual Android cases passed against candidate engine 643db1c51e98a32df10dce57fe7199408ed3c78b0cbe50e0358312700203cdd0 | SVC, handled SMC, default-fatal SMC, and edited return signal mask. No commercial App business acceptance is inferred. |
| a04 lifetime and classpath | 52 JAR backing identities matched through held init/zygote descriptors; both probe packages removed; four cell units plus the controller retired | The init and zygote mount namespaces actually differed. A same-path assumption was not used as proof. |
| Init constructor barrier | 20 host transport controls and strict host build passed; matching Android shared library compiled with 147 pinned inputs and 140 dependency entries | The new constructor has not run inside Android; the supervisor producer and native LMKD lifecycle remain separate pending gates. |

## Signal behavior established by a04

The SVC instruction remained `0xd4000001` and returned the correct guest PID without a signal. The SMC instruction remained `0xd4000003`; the handled case received precise SIGILL information and respected guest register, NZCV and resume-PC edits. The default case terminated and reaped its owned child with SIGILL. The mask-edit case applied the handler's requested mask while removing the unblockable SIGKILL/SIGSTOP bits, then restored the original harness mask.

The raw per-case results, engine bindings, classpath correspondence, installation/removal records, controller terminal receipt and independent post-exit checks are retained in [signal-runtime-a04](signal-runtime-a04/). The root readback is [root-actual-review.json](signal-runtime-a04/tooling/root-actual-review.json); the original aggregate is [runtime-result.json](signal-runtime-a04/runtime-result.json).

The R5 source and qualification controls are in [signal-r5-frozen03](signal-r5-frozen03/). [signal-r5-fixture02/result.json](signal-r5-fixture02/result.json) records the exact live-subtree cleanup. The original fixture01 failure caused by a 33-character nonce, its exact recovery and the corrected 32-character preflight are preserved. No production identity guard was relaxed.

## Metadata behavior and remaining red cases

[R21 source and build review](native-r21/README.md) and [actual runtime summary](native-runtime-r21/summary.json) distinguish the 120-byte Linux kernel statfs structure from Bionic's normalized representation. The observed raw flags were 32 versus libc 0 for the memfd filesystem, and 4143 versus libc 4111 for procfs. The probe checks output preservation for EBADF and bounded handling of EFAULT.

The `RLIMIT_NOFILE=0` raw and ordinary TMPFS paths still return the known EMFILE result. These expected red observations are included in the 16-case probe; passing the probe does **not** mean that descriptor-exhaustion behavior has been repaired. The default-disabled raw feature, actual adapter, privileged factory, paired ART/engine build, APEX signing/update lifecycle and Android integration remain open.

## Main preservation and resource evidence

Main remained bound to engine `c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d`, presenter `47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24`, and framework epoch `48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f`. Original App data and unrelated projects were not reset.

The a04 cleanup checked the exact held cgroup hierarchies and process generations. Its OOM-related counters were zero. The controller recorded memory.max pressure events; this checkpoint does not claim that every memory.events counter was zero. Escaped-descendant cleanup is not qualified.

Raw private boot journals are retained at their original runtime location and excluded from this Git payload. Their file/hash index remains with the exported evidence. No APK, ELF binary, build cache, private journal or image is committed.

## Continuing work

The combined metadata/factory candidate must preserve the six signal source changes verified by a04. The first combined-source attempt failed in its diff generator before compilation and remains a failed attempt. A corrected explicit-file composer and an owned host factory fixture are being prepared separately.

The supervisor producer must complete the real init HELLO, broker READY, socket projection, COMMIT, native LMKD enrollment and exact retirement on a fresh owned Android cell. Its source/build controls do not substitute for that execution.

Bilibili's exact original recorder has been recovered, and its held-namespace transport repair is being connected to the recorder's original task preservation and evidence flow. Reopen, pause/seek, Back, cold start and attributed audible playback remain open. Every remaining commercial App requires its own complete business acceptance before the 0/45 count can change.
