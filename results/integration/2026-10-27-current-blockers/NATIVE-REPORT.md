# Immutable Windows native SSHSIG producer diagnostic 773

The only native dispatch, [run 40444364580](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/40444364580), attempt 1, completed **FAILURE**. Job 121991980305 ran from 2026-10-27 03:28:38 to 03:31:08 UTC. Head and actual checkout are `773d34e16fc1ffb7820ce01cde97a60f076d645c`, tree `08f47fb7cd767520b977d904881dbef6ec743620`. Checkout logs fetched and checked out that commit directly; this was not a PR merge checkout.

## Actual independent scopes

| Scope | Exact identity | Actual result |
|---|---|---|
| Newly ignored public-fixture producer collector | `codex-hepta-operator-acceptance` / `trust::tests::windows_contract_probe::records_unmodified_openssh_stream_and_private_file_output` | 1 PASS, command 95.031 s |
| Existing backend junction case | `codex-utils-path` / `private_artifacts_windows::tests::native_reparse_directory_is_refused_before_child_effect` | 1 FAIL, command 4.016 s |

The independent exact-ID parser checked one actual execution phase per scope, exactly one selected identity, no skipped selected case, and a matching summary/failure recap. The junction failure recap repeats its FAIL after the summary; it is not a second execution. Its original `mklink` success assertion still reports **“The syntax of the command is incorrect.”** The later reparse/identity/no-child-effect assertions were not reached. The fixture is not qualified by this run.

The original receipt remains `FAIL_DIAGNOSTIC_COLLECTION`, with `functionalQualification=false` and `productionAuthorityGranted=false`. The producer collector PASS establishes that observations were captured. None of its three original production verification calls succeeded. These scopes do not replace or increase the immutable original91 result from run378: **83 PASS / 7 FAIL / 1 LEAK**. No original91 rerun occurred here.

## Actual unmodified producer evidence

All modes used a newly generated, task-owned fixture key and the same original 39-byte public body `canonical operator acceptance statement`, namespace `hepta-vnext-operator-acceptance-v1`, and SHA512 signing option. No signature normalization, ACL repair, production credentials or business data were used.

| Mode | Original OpenSSH output | Strict Rust verification | Original production verification |
|---|---|---|---|
| `stdin_stdout` | Success; exact stdout 340 B; 6 CRLF, 6 CR, 6 LF | FAIL: armor differs from admitted envelope | FAIL: detached signature is not an OpenSSH SSHSIG envelope |
| `filename_new` | Success; original file 334 B; 0 CR, 6 LF | PASS | FAIL: private Windows filesystem identity indeterminate |
| `filename_precreated_private` | Success; original file 334 B; 0 CR, 6 LF; same full 128-bit file ID and full owner/DACL before signing and verification | PASS | FAIL: OpenSSH SSHSIG verification requires Unix inherited descriptors |

The stdout SHA256 is `408481af80d87b427d8489bc98bd1fd0cf77ef39929478ea53a23002bce1905c`. Both filename modes contain identical original signature bytes, SHA256 `efcc8ad4e343df57c48aaac7092cce7333e6c01165abbef6d18985e64054821e`. The stdout mode proves the CRLF envelope failure without rewriting the signature. The new-file mode has the original broad Everyone ACE mask `0x1301bf`; the canonical backend correctly refuses it. The precreated-private mode remains `O:LAD:P(A;OICI;FA;;;LA)` and preserves its full 16-byte ID `[136,53,0,0,0,0,2,0,0,0,0,0,0,0,0,0]` on volume `b8d6c010d6bfcd3e`. This supports a private fixture producer; it does not implement the missing independent Windows production verification contract.

The installed signer is `C:\Windows\System32\OpenSSH\ssh-keygen.exe`, SHA256 `c9dc170cd161db87e75eb6cf282f1325005b9e35628b9a36cb19883a8be1a34f`. Its observed full identity and owner/DACL are stable. Path, file metadata and before/after hashes do not prove the actual launched child image or an inherited verification handle chain.

## Provenance and retained evidence

The original artifact is ID `12707786552`, exactly **11,506 bytes**, API SHA256 `4a7f3d27842557e0005c320fc77a8e0caa27ebbb2e3b494c5484a8e19191464e`. The downloaded ZIP has the same digest and exactly four members. `native-artifact/` retains their original bytes. `NATIVE-QUALIFICATION-773.json` records independent exact-ID parsing and derived public-byte/identity facts; `qualify_actual_773.py` produces it from the original ZIP and frozen tracked source.

The actual Windows host was Server 2025 10.0.26100, Rust/Cargo 1.96.0 native MSVC, just 1.51.0 and Nextest 0.9.103. Source was fully clean before and after. All five tool files and the protected original91 driver, scope, Nextest policy and Cargo lock are identical before/after. The Windows Cargo lock SHA256 `593823dd...` is the exact CRLF projection of tracked LF bytes, not a dependency mutation. Both commands used zero retries and the original test profile.

The exact source archive is `source-773d34e16.tar.gz`, 55,369,656 bytes, SHA256 `2cdd8710c6316dc24e0473160895a82db744e08523ad3c5e63a5796e447bbaf7`. Local GNU cross Clippy, fixture controls and actionlint are separate from native execution. `ACTIONLINT-CORRECTION.json` retains the initial bare-command PATH failure and the subsequent actual absolute-path successful invocation. `STATIC-COMMAND-NOTE.json` retains the first extra empty `-p` command and the final exact clean corrected Clippy invocation. No earlier failure receipt was replaced.

The one normal branch push registered a separate push event whose only job was SKIPPED; it is not a diagnostic execution. Exactly one workflow_dispatch with empty inputs followed. No force push, PR, protected/default branch modification, original91 dispatch or diagnostic retry occurred.

## Remaining work supported by these facts

Use the canonical precreated-private filename method for the owned fixture producer, preserving the actual original OpenSSH bytes and full identity/security. Implement and prove a Windows production verification channel that retains the original statement, signer identity and protected owner binding and performs both strict Rust and independent real OpenSSH verification; the current non-Unix refusal must remain until that exists. Diagnose the actual native `cmd.exe` command line for the junction fixture rather than treating its unexecuted backend assertions as passed. Retain the real helper LEAK result until runner process lifetime is actually owned and reaped without changing timeouts or sleeping through the leak.
