# Pocket4 original-init pre-Ready framework observation (R40)

This is a **source-only candidate**, staged against the original normal supervisor snapshot at commit `ce8eb1fe4d79a94c59b4afb9bbc14308f77de613`, not a replacement for the original release, APK signatures, or production admission.

`PRE-READY-FRAMEWORK.patch` modifies exactly two files in the original normal supervisor source under `runtime/droidloom-supervisor/src/`:

- `production_namespace_application_parent.rs`: retain original init/zygote/system_server identity with real read-only `/proc` observations before `ReadyTreeWitness`; verify source-owned proc inodes, generation/parent/start ticks, mapped credentials, original namespaces, payload budget, boot ID and current named proc entries on revalidation. Existing Ready-only application paths retain their current admission checks. No PID-only or serialized issuer.
- `production_namespace_execution_identity.rs`: make the existing original `ExecutedInitWitness` child borrow accessible to the enclosing execution module without granting a new constructor.

The candidate was built from an isolated byte-identical normal source copy at `ai395:/home/qq/work/current2392-cli-preparation-20261121-ce8eb1-r1/producer`. The complete reviewed source and result remain at `ai395:/home/qq/work/p4-r40-pre-ready-framework-20261123-r1/`.

## Verification performed

`patch -d <original-source> --dry-run -p1 < PRE-READY-FRAMEWORK.patch` succeeded with two matching source files. Patch SHA-256: `7ce9ed7dfb28722f84ce3249539883c4c69115413d4c9fb540c178e692735277`.

Rust 2024 formatting and actual offline compilation passed. The single targeted parentage/PID-reuse regression passed. A complete serial `cargo test --offline -p droidloom-supervisor --lib -- --test-threads=1` on ai395 finished **624 passed, 0 failed, 26 ignored**. An earlier parallel run produced **12 failing FD/lease/lock-sensitive tests**; it is retained as a failure, not converted into a clean production acceptance. See `RESULT.json` and the retained local serial test log.

## Deliberate non-qualification and follow-up

This source-only gate breaks the observation ordering dependency for a real original init/zygote/system_server lineage. It **does not** observe or certify either actual InputReader or InputDispatcher thread, their `InputPolicy` scheduler/cpu/cpuset/timer-slack effects, capability or seccomp contracts, final exec, production systemd service startup or Android Ready. `ExecutionAdmission` remains uninhabited. Do **not** turn the code or a static test into production acceptance.

Next normal-source work is to retain and revalidate the two exact input critical-thread identities in the same process generation, prove their actual task-profile effects and wire those facts into a staged pre-Ready activation hold followed by actual capability/seccomp/final-exec checks. Only then run the actual cold start and 39 app business/data acceptance with preservation of existing user state, and only after successful acceptance consider deleting superseded artifacts. No Razr or original Pocket4 data was modified here.
