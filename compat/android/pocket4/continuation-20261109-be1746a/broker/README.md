# Pocket4 sealed input and namespace broker integration

This capsule integrates the sealed-spec descriptor chain, the frozen owner namespace broker r2, and all three public lifecycle fixes into a full b4dc workspace copy. It also fixes the creator-death test's kernel-exit barrier. The active owner source, CURRENT, Android services, host accounts, and grants were not modified.

## Actual verification

Pocket4 kernel 7.0.14-p4cred1; boot 97d9600f-e081-465c-9e6e-62651e09806b; Rust 1.93.0.

| Verification | Observed result | Scope |
| --- | --- | --- |
| Supervisor library | 178 passed, 0 failed, 24 ignored | Ordinary UID, complete integrated library suite |
| Supervisor CLI | 6 passed, 0 failed | Ordinary UID |
| Library and supervisor binaries | Cargo build succeeded | Actual non-test compilation |
| Creator-thread diagnostic filters | 2 passed | Included in the 178 above, not additional unique tests |
| Fixed private owned-child userns test | 1 passed, 0 failed, 201 filtered | Exact integrated binary, only the selected root test |
| Combined patch replay | 13 exact outputs verified | Fresh declared-source tree from b4dc Git object preimages |

The ordinary suite used cargo test --locked --offline -j 1 -p droidloom-supervisor --lib --bins -- --test-threads=1. The subsequent cargo build used the same package/target/lock/offline/job bounds. It had an independent target directory, one CPU, nice 19, and a 3 GiB memory bound.

The root control used a root-owned binary copy, its own systemd unit, CPUQuota=100%, MemoryMax=4G, RuntimeMaxSec=35, NoNewPrivileges, private temporary/devices/network namespaces, ProtectSystem=strict, a restricted capability bound, and AmbientCapabilities=CAP_SETUID. It validated exact UID/GID maps with setgroups=allow, supplementary group set/read/clear, wrong/repeated map rejection, changed-authority rejection, exact child retirement, and continued public HostAdmission rejection. Parent identity, seven namespaces, mountinfo hash, boot, public authority hashes, and original Android data metadata matched before/after. The unit ended inactive/dead with MainPID 0 and no control group. Original Android data bodies were not opened.

These are source and one fixed private syscall-control results. They do not issue HostAdmission, activate Android, qualify apps, or establish production readiness. The ordinary run's 24 ignored entries remain explicit; only one was separately executed. This capsule excludes the owner's moving host-admission-tree increment after 08:19 UTC.

## Exact composition and fixes

The full workspace was exported from b4dc3b49ce29e706efca0ba5a7c775864d9b54b8. Frozen broker copies came from production-namespace-broker-source-20261109-8b88-r2, manifest SHA-256 766c95f556a5d8eb28d9c551e852a12481b939e768553e7d056ed852560c4120.

The eight sealed source files matched the public source-chain pins at commit 208d2dca4dccb622869916b9a7381decdddc0dce, identity-review-fixes.patch SHA-256 87291657b2dc5104594ceac28ee50ee95488874b3bf8d5d6419ce6ad46531364. The lifecycle overlay came from commit 9d45eba81752d1e10906b5dc6d7e9a3c1a6b42c2, patch SHA-256 a40a62a907ec75177350310bdb96b78d6ea690b56b9123ba9c2516ed94c31267. Its four preimages and postimages matched exactly.

The lib conflict retains both namespace and sealed-spec modules. The CLI conflict retains the exact sealed public main with all six CLI controls. Compilation caught one duplicate byte-equivalent FIFO regression test introduced by textual merging. Keeping it once restored production_identity.rs to the exact frozen broker hash. No implementation assertion was removed.

The public lifecycle tests initially failed twice: joining the creating Rust thread did not yet establish kernel thread-pidfd readability, and both children reached sentinel exit127. The correction opens the creator's PIDFD_THREAD while it is alive and blocked, joins it, then waits at most two seconds for that exact kernel task before sending Enter/Go. Both actual diagnostic lines recorded readable_after_join=false and held_thread_exit=true after bounded polling. Production logic and the expected exit125 assertions remain unchanged. creator-exit-barrier.patch applies independently to the exact public lifecycle test postimage.

The first root attempt never ran its test because /run is mounted noexec, producing systemd 203/EXEC. A new root-only stage under /var/lib fixed placement without changing mount or capability policy. Failed and successful attempts retain separate receipts and identities.

## Replay

combined.patch transforms all 13 pinned b4dc preimages directly into the qualified result; it already includes sealed, broker, lifecycle, and test-barrier changes. Do not apply the component patches again on top.

The inherited public reconstruction route starts at upstream 500dd3af851aaadb95537b68129b8bd889504951, applies the first six prerequisite patches recorded in source-chain.json, and then this combined patch in place of identity-review-fixes.patch. This contribution verified local b4dc Git objects and all 13 outputs; it did not rerun that entire public prerequisite chain for the two additional existing broker files. Verify every preimage before applying.

Compile and invoke the standalone Rust verifier:

    rustc --edition=2024 --crate-name verify_source verify-source.rs -o verify-source
    ./verify-source /absolute/capsule/path check-before /absolute/base/source
    ./verify-source /absolute/capsule/path replay /absolute/base/source /absolute/new/output
    ./verify-source /absolute/capsule/path check-after /absolute/integrated/source

The replay output must not exist. The verifier checks the embedded patch digest, all existing/absent preimages, git apply --check, and all 13 final hashes. It creates a declared-source subset; this subset alone is not a buildable workspace. Full-workspace compilation happened separately in the recorded isolated source tree.

source-manifest.json records all pins and merge decisions. qualification.json records ordinary results and earlier failed/superseded attempts. private-userns.json records the separate fixed syscall control. execution-identities.json records durable process/PTTY identities and setup failures. Raw output remains in the remote qualification root. owned-stage-inventory.json identifies isolated paths for the parent's final reference-aware cleanup.

## Temporary private copy retirement

After fresh unit/cgroup quiescence and inode/hash verification, the two redundant root-owned test binary copies and their empty stage directories were removed. The exact failed transient unit was reset after its exit203 was retained. The original qualified build binary and complete raw receipts remain in the independent integration root. private-stage-retirement.json records both actions; no owner source or Android data was removed.
