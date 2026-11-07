# Pocket4 R11 — checkpoint 08

This checkpoint continues the existing repair branch. **Whole-App production readiness remains 0/45 launcher Apps.** The source and evidence below do not authorize production activation. Main keeps its existing engine, presenter, framework epoch and resource configuration.

The new results close two concrete host-side blockers: the factory fixture now completes its intended runtime matrix, and the corrected startup-prefix identity capture passes an actual normal run with exact retirement. Full engine regression, actual Android factory/lifecycle integration and complete business-flow acceptance remain open.

## Factory: inherited capabilities explained and cleared in the owned client

The original runtime01 reached factory READY and rejected the first client with stage 1 / EPERM. Runtime02 used the same factory and a diagnostic client. Its actual diagnostic reported real/effective/saved UID and GID 61171, zero effective/permitted capabilities, but inheritable capability words `[0, 8]`. The thread pidfd and user-namespace ioctl both succeeded and returned the expected initial user namespace. The production all-zero capability check correctly rejected the client.

Runtime03 changes the fixture's already dropped, owned client only. After clearing supplementary groups and completing `setresgid`/`setresuid`, it explicitly clears and reads back all effective, permitted and inheritable capability words. The existing parent-death-signal rearm, held-parent pidfd check, sealed-ELF execution, namespace checks and production authority checks remain unchanged. Factory/root actors retain their original behavior. The host03 factory ELF is byte-identical to host02; the host03 client adds failure-only diagnostics.

The actual runtime03 job `1a1a8c3a6dc-fc05-2fae` exited 0 with durable complete output. Its complete result is 179,971 bytes, SHA256 `cb4c2d7efff50fa57d1d0d79ab29b785f4c9c9e79c25c4cc0d2d58f1618f5885`.

- All 28 scenario records met their controller assertions, including normal and cross-PID-namespace snapshot operations, malformed requests/replies, wrong UID/source/seals, timeout, peer death, control HUP and owner death. The wrong-proc-view negative control deliberately returned EXDEV and client exit 1; it is retained as an expected rejection.
- All 37 controlled children were reaped. The private namespace init also exited 0 and was reaped. No forced cleanup kill or cleanup error was recorded; the deliberate owner-death stimulus remains a distinct test action.
- Main's pinned identity/configuration checks passed. Main and owned-unit memory-event deltas were all zero.
- This executes host ELFs. The Bionic-shaped branch fixture is not execution of the Bionic API, and there was no Android/ARM64 factory execution or production bootstrap.

The earlier runtime01 and runtime02 failures are retained. The first local capdrop driver also failed before saving its child detail; the second retained the real reason: the local container has empty capability sets and cannot seed the test permission. Neither local failure executed the new capdrop function. The actual Pocket4 runtime supplies the positive validation. A later truncated local copy of the runtime result was preserved separately and restored from the original version-pinned chunks; the authoritative complete SHA was rechecked.

## Startup prefix: actual NUL padding fix and normal runtime

The original normal-plan preflight failed its `system_server` identity comparison. A fixed-process diagnostic held the original process and observed the same 99-byte cmdline before and after. The only discrepancy was representation: the original prefix capture retained 85 empty arguments from trailing NUL padding, while the established framework guard filtered empty arguments. All other identity fields matched the original binding.

Prefix02 canonicalizes only that read-only Main comparison. Strict startup argv and the underlying process identity helper remain unchanged. The matching device preparation passed 16 actor controls and 27 coordinator controls. It verified reuse of the exact original compiled probe; it performed no new native build or native controls. The original six native controls remain attributed to their original receipt.

The live preflight then passed. The actual normal runtime `1a1a8c5cf70-fc05-2fb2` completed with coordinator result SHA256 `77891888cc854305d8e0a7af6391894079567010d311597a7a4f900e65fb11e8` and actor result SHA256 `22a4677c309a1e3481170a38db14a96793348121fde2ff19c36f20d8ab9877c0`.

- The actual native `ip netns exec` → `unshare` → private PID1 chain matched the admitted argv, held namespace, invocation, cgroup and original process identities.
- The next exec closed all four fixed descriptors. The actor's final audit saw only itself in the original unit.
- The unit lifetime was 223,800 microseconds, peak memory 27,275,264 bytes, swap peak zero, and pressure/OOM counters zero.
- The original pidfd became dead, the original cgroup was independently proven removed, the transient unit became not-found, and the exact network namespace was removed after proving it had no live members.
- Main's before/after epoch, daemon invocation, held cgroup, process identities, installed contract and limits matched. No Android operation or Main deployment occurred.

This is a real host-prefix run with a declared C stand-in. It does not execute the Rust Owner, Android init constructor, finite-domain broker handshake, LMKD enrollment or abandoned-generation recovery. The next integration step needs the exact producer/barrier source and ELF closure and a separate, bounded private CellSpec. A broader death matrix is not substituted for that integration. The 31 explicitly recorded producer05 build inputs have now all been retrieved or matched locally, totaling 726,924 bytes, with every SHA/size matching the original successful build receipt. This closes that recorded-input gap; it does not establish the complete transitive Cargo dependency or ELF closure. Sixteen older local variants are retained separately and identified by hash.

## Complete engine build: retained admission failures and an actual owned OOM

Candidate05 still binds 948 candidate files and the same 925 engine files, including all six signal fixes. The normal builder and its source-projection lock/recovery path remain in use.

| Attempt | Go soft heap | RAM / swap hard limits | Fresh memory admission | Actual outcome |
| --- | --- | --- | --- | --- |
| Original combined05 | 6 GiB | 11 / 1 GiB | 15 GiB MemAvailable | Rejected before the inner compiler started |
| Independent Go5 | 5 GiB | 10 / 1 GiB | 14 GiB MemAvailable | Preparation passed; fresh build admission failed before the inner compiler |
| Independent Go4 | 4 GiB | 9 / 1 GiB | 13 GiB MemAvailable | Entered compilation, then failed with one owned OOM kill and SIGTERM |
| Independent Go6r2 | 6 GiB | 11 / 1 GiB | 14 GiB MemAvailable and 2 GiB SwapFree | Preparation and fresh admission passed; running at first observation |

Go4 job `1a1a8b5b235-fc05-2f88` ran for 762.44 seconds. Its logs reached Soong bootstrap step 273/274, which is not whole-engine progress. The final owned-unit measurements were exactly 9 GiB memory peak and 1 GiB swap peak, with `memory.events` reporting `max=4344`, `oom=1`, `oom_kill=1`. Its builder returned -15, its artifact gate was not reached, and the runtime reported cancelled rather than timed out. The exact SIGTERM sender is not proven. The root and three agents' retained call records show no intentional cancellation request by them; that is not a host signal-sender audit.

Owned build cleanup completed. The Main identity/limit fence passed and Main memory-event deltas were zero. The pre/post observations also recorded Main memory-current decreasing, swap-current increasing by 249,143,296 bytes, and one additional task; no claim of zero transient interference or causal attribution is made.

The source-projection journal remains present. Follow-on work must use the normal builder's lock and journal recovery, not delete or repair the journal by hand. A fresh read at 23:00:32 UTC observed 14.492 GiB MemAvailable and 3.459 GiB SwapFree. The independent Go6r2 profile restores the previously successful 11 GiB RAM / 1 GiB swap package. Its unchanged 449-file builder manifest is `e7c225bd2842c260d9f4149aca3c4483ed31c569efb31068b6d787892bd17017`; its actual preparation is `da6fdf1b6c5b5fc05f509e220664746c91028e2f44e941803186ca677e833499`. Its fresh admission is 14 GiB MemAvailable and 2 GiB SwapFree: explicit 3 GiB RAM and 1 GiB swap differences, not reservations. It adds a final rejection for missing/malformed counters or any owned OOM kill and requires the recovered Go6 projection to match the prior successful input. All 29 local function/PLAN controls passed independently.

Actual Go6r2 job `1a1a8de3bbf-fc05-2fe9` started at 23:21:40 UTC and was observed running. At its own launch it read 15,588,405,248 bytes MemAvailable and 3,861,467,136 bytes SwapFree, used CPUs 22 and 23, and retained the normal builder recovery/lock path. This is a running observation, not a terminal result. No complete candidate05 engine or regression success is claimed here.

## Bilibili: R3 device admission passed; UI helper provenance remains separate

R3 fixes the original helper-size bound with the exact existing 4,366,312-byte artifact length and original SHA256. Its actual read-only device job `1a1a8a103bd-fc05-2f47` exited 0. The single Android package query returned exactly `package:tv.danmaku.bili uid:10117\n`, SHA256 `6ccabdca04cf7be1ceb3e0dbf7284e375fcb90c62a0030ecb3d51ef17f579582`. The held-namespace transport child was joined and the pinned Main checks matched. There was no UI, audio, launch or close action.

Two subsequent metadata-only source searches completed within their fixed bounds. Stage1 indexed direct child directories under the known task parent; stage2 inspected direct entries of three actually observed task roots and returned 46 unentered directories. Neither search read file bodies or found a direct ActionRunner source/build/manifest candidate in its scope. This limited search does not prove the source is absent elsewhere.

The installed `local.pocket4.actions.v2/.ActionRunner` still lacks an exact source/build/signature binding. Its gate is not relaxed. A separate owned self-instrumentation fixture is being designed for the minimum Bilibili tree/action contract; it must independently bind source, SDK inputs, APK, signer and held Main transport before any installation or UI use. Continued playback, controls, reopening, cold start and app-attributed audio remain open.

## NOFILE-zero source work

A separate candidate introduces a second preallocated raw-worker stack. Only an explicit EMFILE from `pidfd_open` or `pidfd_getfd` may trigger a synchronous clone from the actual caller with a private inherited file table. It reuses the full context, inode, tag and seal validation and holds the caller gate/signal mask until kernel clear-tid. Generation admission, initial-user-namespace authority and final ABI publication remain intact. Candidate05 and its failed build roots are not modified.

The new production source compiled locally and passed a two-worker final-ELF closure audit and actual negative admission controls. The earlier five positive kernel-mechanism controls are a separate fixture; they do not qualify this production integration. Positive execution of the new owner under an eligible nonroot context and Android regression are still required. Startup at NOFILE=0 and virtual O_PATH reopening under exhausted descriptors remain explicit limitations.

## Release boundaries

Full repaired-engine build and host/Android regressions, NOFILE-zero positive production execution, paired ART/APEX and updater qualification, actual Rust Owner/init/broker/LMKD lifecycle, helper APK/source binding, Bilibili app-attributed audio, and all remaining whole-App business flows remain open. No APK, ELF, archive, cache or private commercial runtime journal is included in the Git payloads. Publication preserves the previous 2,530 payloads and is not deployment.
