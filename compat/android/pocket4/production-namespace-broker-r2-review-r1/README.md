# Owner r2 namespace lifecycle review

This capsule proposes three focused fixes to the owner's pinned r2 private namespace constructor. It is a source review contribution. The owner working tree, host account/subordinate-ID files, CURRENT, Android services and runtime were not modified.

The public `prepare_user_namespace` body remains byte-for-byte unchanged: a current identity lease is revalidated, then the call returns `HostAdmissionRequired`. None of these tests issues host admission or qualifies production Android.

## Exact source boundary

The r2 source manifest is `production-namespace-broker-source-20261109-8b88-r2/manifest.json`, 25,798 bytes, SHA-256 `766c95f556a5d8eb28d9c551e852a12481b939e768553e7d056ed852560c4120`. Its recorded workspace baseline is `b4dc3b49ce29e706efca0ba5a7c775864d9b54b8`; the r2 qualified sources include owner changes beyond that commit.

`owner-broker-r2-lifecycle.patch` changes only `production_namespace.rs`, `production_namespace_child.rs` and `production_namespace_tests.rs`. `production_identity.rs` is an unchanged harness input. Exact preimage and postimage sizes/hashes are in `source-replay.json`. A clean local replay passed `git apply --check`, then the applied bytes matched all four candidate inputs exactly.

The final read checked both the immutable r2 copies and the actual owner working source, not just capsule self-consistency. All four current working files still matched the r2 preimages; the bounded qualification directory listing contained r1 and r2. CURRENT recorded at 2026-11-09T08:21:04.867373+00:00 still referenced that exact r2 manifest. Its full-file pin is 221,613 bytes / `04fe75a81b798613a98353504d004cb2be5bb66866af88238252e1a0ce00cbf4`. Only the relevant CURRENT projection is included. These are point-in-time observations; reconcile any later owner generation before applying the patch.

## What changes

1. **Bind parent-death handling to the creating thread.** The parent opens its own live TID with `PIDFD_THREAD`, pins both child FD sources above slots 3/4, then raw-clones. The child retains only its control socket and that exact thread pidfd. After each `PR_SET_PDEATHSIG` arm, including the credential-change rearm, it polls the thread pidfd and checks the expected parent TGID. A dead creator is rejected even while another thread keeps the same TGID alive. The existing atomic child pidfd and same-thread Owner boundary remain.
2. **Report signal-mask restoration errors in release builds while retaining child custody.** Restoration is explicit. If clone succeeded, the acquired pidfd/control and restoration result return together. Owner installs all resources and the lease before surfacing the error. Its existing exact-pidfd retirement path either proves reaping or quarantines the resources. No signal-restoration correctness predicate depends on `debug_assert`.
3. **Bind procfs to the caller's PID namespace before numeric child lookup.** A held procfs root deliberately resolves the kernel `thread-self` link. Its status must contain exactly one correct NSpid/NStgid and matching Pid/Tgid. Typed current and future-child PID namespace FDs must match. This rejects an ancestor procfs view, including a coincident numeric PID, or a pending different namespace for future children. The check is repeated during ownership validation.

The fixed child still performs only stack-based/raw syscall work after clone. It still clears inherited supplementary groups, preserves `setgroups=allow`, checks complete maps, changes to namespace IDs zero and parks. The patch does not add a production constructor, mapper authority, exec path or external PID adoption.

Linux documents the creating-thread meaning and cleared-on-credential-change behavior of [PR_SET_PDEATHSIG](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html), the thread-specific polling behavior of [PIDFD_THREAD](https://man7.org/linux/man-pages/man2/pidfd_open.2.html), and the mount-relative ordering of [NSpid/NStgid](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html).

## Actual verification

All results below are from Pocket4 on kernel `7.0.14-p4cred1`, boot `97d9600f-e081-465c-9e6e-62651e09806b`, Rust 1.93.0. They are not GitHub runner results.

| Execution | Result | Scope |
| --- | --- | --- |
| Debug harness, ordinary UID | 38 passed, 0 failed, 2 explicitly ignored | 33 existing ordinary controls from the two selected modules plus five new controls |
| Release harness, ordinary UID | 38 passed, 0 failed, 2 explicitly ignored | Cargo artifact records opt-level 3 and debug_assertions=false |
| Release private proc-view control, root | 1 test passed, containing three actual cases | Ancestor proc rejected; freshly mounted matching proc accepted; pending child PID namespace rejected |

The two creator-death controls use the actual cloning thread, then join it while the parent TGID remains alive. One tests initial arm; the other first clears PDEATHSIG to reproduce the rearm interval without changing IDs or writing maps. Both prove the exact child was reaped with the rejection exit status.

The signal-restore negative control produces a real EINVAL with the kernel's invalid sigset size 7, then successfully restores the original mask with size 8 before forwarding the observed error. It verifies error propagation, exact child retirement and preservation of the durable reservation. It does **not** claim that a genuine size-8 restoration failure would leave the mask restored.

The private proc controls use fresh-exec children in their own PID/mount namespaces with private mount propagation. They create no user namespace and write no UID/GID map. The root unit is bounded to CPU 100%, memory 3 GiB and 45 seconds, with NoNewPrivileges and only SYS_ADMIN/DAC_READ_SEARCH/KILL in its capability bound. The parent UID/GID/groups, seven namespace identities, mountinfo hash and boot identity were equal before/after. All relevant units were observed inactive/dead, MainPID 0, with no control group after completion.

The original privileged user-namespace mapping control remains unrun in this review. This capsule does not replace the owner's broader reported 41-control qualification or full host/NSS/namespace admission work.

Two initial setup/environment failures are disclosed in `execution-identities.json`: a locked build rejected an unmaterialized harness lock, then a default-umask fixture run rejected group-writable temporary directories. Full offline metadata resolution preserved every original registry package/checksum, and the final test units used UMask=0077. No production custody rule or original identity source was weakened. Only the final successful evidence is copied here.

## Reproduction and integration

Use an isolated layout matching the reviewed harness:

```text
OWN/source/                       existing verified workspace dependency source
OWN/qualification/REVIEW/harness/ Cargo.toml, Cargo.lock, review.rs
                                  four exact owner r2 source files, then this patch
```

The harness reuses the real workspace CellSpec/IdRange and contract crate, rather than fabricated stand-ins. `verification/dependency-source-pins.json` identifies the actual path-dependency inputs. The full workspace, Cargo cache and executables are intentionally not vendored.

Verify all preimage hashes before applying the patch to the corresponding runtime source paths. Copy the resulting selected sources into the harness, preserve the pinned registry dependency set, then use the existing Rust 1.93.0 toolchain, offline/locked -j1, a private TMPDIR, UMask=0077, an isolated CARGO_TARGET_DIR and the same resource bounds. Ordinary invocations are `cargo test --offline --locked -j1 --test owner_broker_review -- --test-threads=1` and the corresponding `--release` invocation. The separately approved privileged filter is `production_namespace::tests::privileged_proc_pid_namespace_view_controls` with `--exact --ignored --nocapture --test-threads=1`.

Do not replay the owner's old private driver constants or treat these receipts as a new generation's qualification. A changed owner preimage, kernel/boot, custody manifest, binary, namespace policy or test source requires fresh verification at that boundary.

## Limits and retirement

The public host admission gate stays closed. Complete effective NSS, active/inactive namespace history and future runtime construction are separate requirements. A successful active-only namespace census does not itself establish complete production admission.

Review of the current private child's inherited MM did not establish a foreign-owner exposure: its new user namespace is owned by initial-host UID 0 and runs no untrusted payload. This differs from entering an existing foreign-owned user namespace. A future dedicated-UID owner or untrusted pre-exec peer needs its own credential/dumpability review; no global sysctl requirement is added here.

`execution-identities.json` records known terminal outcomes and keeps the original cb startup `outcome_unknown` separate. A later fresh-boot scan found neither its stage nor its exact argv process; that is quiescence evidence, **not** a known exit code. The new stage setup and every subsequent build/control/read have positive terminal records. No compile/test is still using this review's CARGO_HOME.

The owned stage inventory is a point-in-time input to the root's final cleanup. It includes build hardlinks and is not deletion authorization. The final whole-root reference/hardlink scan remains mandatory; no independent cleanup or live-owner mutation was performed here.
