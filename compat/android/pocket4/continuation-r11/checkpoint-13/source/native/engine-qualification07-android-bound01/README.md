# Candidate07 four-case Android preparation binding

This freeze binds the unchanged qualification template04 to the complete, actually observed candidate07 host result (27,332 bytes, SHA256 `67d0f1a2bb123303b5ca38f046e3f8539b4585336c0360ca7fd0637d9964e556`). The original generator verified its input/fixture/engine/baseline/Main/resource/terminal conditions before generating these inputs. Its source remains SHA256 `c29fb03633ede92c845018ab93a20530320a5741e33afab1986b5bfa457c0efd`.

The host result records 3,793 registrations, 3,791 executions and 3,788 completions, with the original two disabled tests and three baseline-policy skips, zero failures and no postcheck error. This is a host-suite result. No Android case has run from this freeze.

## Ordered root-owned steps

1. Review and dispatch `stage-request.json` once. It only creates `android-inputs.json` with `O_EXCL` in the existing exact private input directory. It does not create a directory, replace the host input, start a child, or invoke Android. It checks the existing host input's exact bytes, SHA, owner, mode, link count and held/named identity before and after the new write. It also binds the already observed private parent's device/inode/owner/mode.
2. Run `generated/android-input-check-request.json` against the original R5 source and source manifest. This step revalidates current allocation and other original input conditions.
3. Only after that succeeds, run `generated/android-prepare-request.json`. The unchanged R5 path prepares the private fixture; it does not authorize the four runtime cases by itself.
4. Bind the actual prepared result through unchanged template04 `android-check`, obtain the independent root review, and only then generate `android-runtime`.

The proposed host UID 2407 and sub-ID start 14600000 are not reserved. The original live allocation check must reject any conflict; no fallback allocation, account changes or relaxed ownership checks were added.

The four planned cases remain r2 SVC, r2 SMC with handler, r2 SMC with default disposition, and r3 SMC with saved-mask edits. Original runner identities, private-image checks, whole-unit cleanup and Main before/after observations remain required.

## Validation and limits

Local work parsed the stager, verified its embedded payloads against the generated source files, verified request stdin against the complete stager, and ran its default PLAN only. No remote request was dispatched here. An unfrozen draft incorrectly expected a top-level Android `nonce`; the default PLAN rejected it before any filesystem action. The final source checks the actual unchanged `attempt.name` schema, and the draft failure is retained in `LOCAL_SOURCE_CHECK.json`.

The candidate07 engine still uses the default metadata feature flag 0. Passing these planned signal controls will not establish enabled ART/factory lifecycle correctness or all-app production readiness. The old host staging permissions failure and the successful corrected host run remain separate immutable records.
