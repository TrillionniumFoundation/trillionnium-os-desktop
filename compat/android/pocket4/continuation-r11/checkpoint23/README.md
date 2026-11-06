# Pocket4 Android — checkpoint23

Frozen evidence cut: **2026-11-06 21:56:09 UTC**. Parent: `5f3d73b486297a4cf1c999f62f953bbd3a42b55d`.

**Whole-app production-ready: 0/45. Main was not deployed or restarted.** This checkpoint records concrete repairs and scoped validation while retaining every earlier failure and unknown outcome. Later actual results belong in a later checkpoint and do not change this cut.

## Qualified progress

The remaining22 commercial-app metadata reads now have qualified latest results. The initial Douyin and WeChat reads exceeded the single-file bound; the correction uses an exact512MiB bound for those two fixed apps, with the aggregate512MiB bound and path, identity, source, Main and FD checks preserved. Both new attempts passed. Metadata establishes the installed package, UID, version and artifacts within its scope; it does not establish business behavior, an independently measured installed signer or whole-process cleanup.

The12306, Hilton and United owned helpers each passed a real12-command build with32 scope and16 deep controls. The first12306 installation attempt then failed before staging or Android commands because its metadata reference used the wrong schema. That failure and its retired credentials remain recorded. Hilton and United installation requests were unrun at this cut.

The real ARM64 NDK fixture APK05 build passed50 commands,16 object compilations and7 links. The packaged native binaries contain23 nonzero TestBody symbols, including12 ProcSelfMaps tests. The APK now targets24, matching the observed device minimum; no deprecated-target bypass is introduced. Its full9,811,685-byte original build report is retained without numeric reserialization. The38 read-only controls and50 new entry controls passed. Original install01 remains UNKNOWN; residual package/data absence does not stand in for all-user PackageManager authority. Install02 was only source preparation at this cut, and no ARM64 runtime pass is claimed.

Native host builders472/473/474 passed their scoped validations. Builder474 completed74 commands and35 focused tests against501 source files. The normal09 attempt stopped at its fresh memory gate. Latest available memory was14,140,059,648 bytes against the unchanged16,106,127,360-byte minimum. Reviewed normal10 and Composer requests remain unrun.

IHG owned task877 retirement02 passed46 controls and13 commands. Only877 was removed;875 and878 stayed unchanged, and the three Main windows matched. This does not resolve the original London launch outcome or explain earlier task876 disappearance/task878 origin. The shared UI hold remains. A separate Status call exhibited an extra direct daemon child while in flight; the final Main observation was stable. Status/Readiness source repair was in progress, without a compiled or deployed fix at this cut.

## Read the evidence

- `status.json`: current fixed-cut qualifications and remaining gates.
- `acceptance-matrix.json`: all45 original app rows, each still pending whole-app acceptance.
- `cut_scope.json`:239 original archive roots, normalized dependency references and695 inherited canonical roots.
- `payload-index.json`: every checkpoint payload except the index itself, with exact byte count, SHA-256 and Git blob identity.
- `assembly/root-verification.json`: independent Root verification of the fixed seed, directory Merkle closure, index, prior master and cut discipline.
- `packages/`: byte-identical source and original evidence leaves; dependency metadata is explicitly derived.

Hyatt's diagnostic admission is included as **ADMITTED_RESULT_UNCOLLECTED_BY_ROOT_AT_CUT**. The seed field name does not establish an observed running state. Its later result is excluded from this checkpoint.

## Remaining release gates

Complete and actually test the Status/Readiness production change; qualify helper installation/state and NDK runtime/cleanup; satisfy the fresh15GiB normal-build gate; then complete fresh scoped business flows and whole-process/FD/resource verification for every app. System and fixture apps keep their distinct ownership assumptions. Historical Hyatt minus500, Hertz SIG11, Air China SIGKILL and CEair observations retain their uncertainty. Source tests and successful helper builds do not set a whole-app row to ready.
