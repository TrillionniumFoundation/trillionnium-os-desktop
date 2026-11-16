# Held Android Java environment prerequisite

This capsule fixes a concrete prerequisite for the next actual Settings/UI flow. The existing safe Android command transport cleared its environment and set only PATH, LANG, ANDROID_ROOT and ANDROID_DATA. `am instrument` starts Android Java and needs the current framework boot classpath and ART runtime roots. The existing source-pinned business adapter already requires these values; inheriting the host environment or a caller-provided classpath would not establish the right runtime.

Only `/system/bin/am instrument` and the explicit `/system/bin/app_process`, `app_process32` and `app_process64` entry paths request the added Java environment. PM queries and the existing Firefox `am start` path keep their original four environment variables.

## Source binding and behavior

Private source commit: `7113c8fe36fc34b6350cb61478bf2082bb211d2e`.
Parent: `deacfc207c99a74a8aac056b086dc1b8f7e8f0c2`.
Tree: `e8e2df870d2c2018d1f89d5eb50eae4c60786147`.
The worktree was clean after this independent commit. No Settings page implementation is included in this commit.

`java-environment.patch` applies to the exact `apps-runtime-fence` source. The three changed/new files are the same files compiled by the workspace and isolated harness:

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| `application_command.rs` | 22810 | `576dd46107100edff7993f325fa148a024fa40fa5cf9a6baea8cbd8df07e2a0d` |
| `application_command_tests.rs` | 11791 | `23b107886d555b2e653c8bb0ab18528a9891180cf848c46ef84340add28a83d8` |
| `application_environment.rs` | 11119 | `97e46072652c545e3480e691508d567bc33089964f132181dfbdb1857a3f21f1` |

The environment is read relative to the already held framework proc directory, with the existing PIDFD/process-identity verification before and after the read. The whole proc environment is bounded at 64 KiB; each selected value is bounded at 32 KiB. The six required values are PATH, BOOTCLASSPATH, DEX2OATBOOTCLASSPATH, ANDROID_ROOT, ANDROID_DATA and ANDROID_ART_ROOT. Five optional keys are ANDROID_ASSETS, ANDROID_I18N_ROOT, ANDROID_TZDATA_ROOT, SYSTEMSERVERCLASSPATH and STANDALONE_SYSTEMSERVER_JARS.

Required keys must exist exactly once. Selected values must be UTF-8 and satisfy explicit Android absolute-path, classpath, root and segment rules. Empty, duplicate or traversing classpath entries are rejected. Unknown process values are discarded; host environment, LD_PRELOAD, caller CLASSPATH, Java options and private session values are not forwarded. The selected map is re-read and compared after invocation, and output is withheld on a change. Preparation and the final checks remain inside the invocation deadline.

Namespace FD entry, per-invocation cgroup ownership, nonblocking output bounds, whole-group retirement and direct-child reaping remain the existing implementation. No cell namespace is retired by an application command. This change does not add a production cell owner, create an admission token, install an Android package, start Android or run instrumentation.

The requirements are derived from the exact existing business support source: `business_scope.py`, SHA-256 `e2a9b509102806483c64c181034e59aded211f42e5f05fcfd85057cc25c9fb7a`, in `business-support-host-20261108-r1/source-manifest.json`, SHA-256 `8cfa9cb05bb7e7768350dbe04acd4cd6421b9f4e8493746aad49b64c37969e70`. The framework's live environment is still the execution input; historical environment values are not reused.

## Actual validation and CI entry

On Pocket4 as UID 1000, pinned to CPU 2 with one Cargo job and a 2 GiB memory limit:

- Workspace job `1a1c1547b02-e62c-6e`: **14 passed, 0 failed, 2 ignored**, authoritative exit 0, complete/durable logs.
- Independent same-file harness job `1a1c1591065-e62c-76`: **14 passed, 0 failed, 2 ignored**, authoritative exit 0, complete/durable logs. Its source files and Cargo.lock remained unchanged during the run.

These are overlapping executions of the same 14 tests, not 28 distinct controls. Nine tests are new: seven environment/parser boundaries, one actual owned host child's held-proc/PIDFD environment read and exit rejection, and one expired Java operation rejected before entry. The original two privileged cgroup/namespace controls remain explicitly ignored in these runs; older results are not transferred to these new bytes.

CI can execute the exact delivered source directly:

```sh
cargo test --locked --manifest-path compat/android/pocket4/continuation-20261109-2840/apps-java-environment/harness/Cargo.toml --lib -- --test-threads=1
```

Expected: **14 passed, 0 failed, 2 ignored**. The minimal harness uses `#[path]` for the actual transport, which in turn loads its actual environment module and tests. It reuses the same PIDFD visibility adapters and actual CPU-placement source from the prior published capsule. It does not stub a control handler, process runner or Android runtime. The isolated harness has the expected unused `NamespaceTarget::capture` warning because it does not include the daemon; the real workspace compiled without warnings.

The new lock SHA-256 is `c6f81b62dd213a6eaf2304ad92dfe762c15a962a763e8557e2242f5d772f831c`. Only the root package name changed from the published runtime-fence harness; all 33 external package records and checksums are identical. `harness/LOCK-PROVENANCE.json` records that comparison.

The evidence text retains the actual reported stdout and terminal observations; the workspace transcript omits only the encoded formatted-source transport envelope after validating and reconstructing its exact source bytes. Full durable job logs remain separately identified above.

## Consumer pin correction and remaining scope

The `audit/` files close the earlier unexplained-consumer-drift hypothesis. The exact deployment manifest already records both installed consumer hashes and their different staged hashes. The two relevant source files differ only in their expected `--kill-child=TERM` versus `--kill-child=KILL` owner command. The selected application leaves intentionally require the staged final consumer bytes. Their precondition must remain enforced until that cohort is actually deployed.

This capsule closes a source prerequisite for actual UI instrumentation. Settings page/task/window flow integration, pixel/crop evidence, permission/account error handling, the explicitly selected reversible setting round trip, actual production lifecycle integration and fresh Main-bound execution remain pending. **Application runtime acceptance remains 0 of 42; runtime_qualified and production_ready remain false.**
