# Candidate 05 host fixture build 02 handoff

This directory contains a local request generator and a concrete request generated from the actual candidate 05 source and small-gate receipts. It does not contain a build 02 result. No Hepta request, factory service, namespace fixture, Android action, or Main action has been executed by this handoff.

The generated `actual-handoff-01/exact-process-start-request.json` is the proposed single build request. Its source packet and entry are checked by SHA-256 before execution. The entry accepts only the four pinned build files, verifies the actual candidate 05 receipts and full candidate inventory, and creates these exact fresh roots:

- `/home/alex/work/pocket4-owned-factory-v2-host-source-02`
- `/home/alex/work/pocket4-owned-factory-v2-host-build-02`

Either pre-existing root causes rejection. The old source 01 and build 01 are preserved. The entry requires an unprivileged operator and defaults to a plan without actions. The request budget is one CPU, 1 GiB, nice 10, and 600 seconds. It performs the same nine dependency scans, nine translation-unit compilations, two links, and one final worker-closure audit as build 01: 21 commands in total. The compiler and three unchanged fixture inputs are pinned to the actual successful build 01 receipt.

The builder additionally requires the dependency union to contain 291 actual files, matching the original successful build. It retains the original per-unit actual `-MD` versus preflight `-M` equality checks, complete input pins before and after compilation, full candidate inventory checks, fixture-source checks, and final named-worker ELF audit. The number 291 alone is not the dependency qualification. A different closure fails; it is not silently accepted or used to weaken the prior checks.

The only derivation from the old builder is shown in `actual-handoff-01/build01-to-build02.patch`: candidate/root/pin changes, binding the actual candidate 05 source and small-gate receipts, recording those references in the result, and the dependency-cardinality gate. Compiler options, source units, command runner, link flags, client controls, Bionic branch fixture, and worker auditor are unchanged. The generated `stage_and_build02.py` is new orchestration code and requires independent review before submission. No runtime service controller is included or modified here.

## Evidence consumed

- Candidate 05 manifest: `4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba`.
- Actual candidate 05 source receipt: `33697d93292428c660f69c629ab9851248f5e5e1c3653f9531e5382f49479d36`.
- Actual matched small-gate receipt: `e53c3e9e5846d36f971bae6140c394b837fa54525c0e2df4ac153c9ef5540803`.
- Successful original build 01 receipt: `adb1b0cb4bfa12d3d154c0538e931a7752046f8ab295e2bab77687615af6c81e`.

The actual matched gate observed eight adapter controls, 34 ancillary controls, and the real listener inheritance rejection control. The original candidate 04 PIDFD leak evidence and earlier failed attempts remain unchanged. These results do not qualify the complete V2 authorization exchange, a service lifetime, Android production integration, or applications.

## Local checks

`offline-controls.json` records ten local request/entry checks. The two default entries and the exact packet wrapper return plan-only. A changed packet is rejected before entry. A self-consistent but incomplete gate receipt is rejected before an output directory is created. That negative receipt is an explicitly temporary fixture and is deleted. The controls verify the unchanged old client/auditor bytes and command runner, exact resource/path constraints, and the frozen generated-file pins. They do not execute the actual build or measure its dependency closure.

An actual successful build 02 result, actual worker audit and independent Start/trampoline review are still required before the root coordinator can consider the separately reviewed owned runtime fixture. The metadata feature remains disabled in the production engine candidate. NOFILE-zero behavior, ART/engine pairing and generation hooks, trusted Android positive cases, and complete app acceptance remain separate open gates.
