# v14 runtime, native UI and packaging attempts

This directory preserves **completed attempts**, including failed attempts and
the evidence that explained them. It is not a production approval or a statement
that the complete workspace gate, native UI qualification or all project
blockers have closed. The archive does not contain product ELF/tar payloads or
actual fonts. Exact binary/resource hashes remain in their original receipts.

The archive was created from completed remote attempts, downloaded in 40
version-pinned chunks, and verified locally with the original archiver against
all 1,998 members. `ARCHIVE_INTEGRITY.json` records the outer SHA256, Git blob,
manifest SHA256 and actual member counts. Preserve the compressed archive bytes;
extract a copy to inspect original logs and PNGs.

The retained selection manifest initially described the v14 **original-owner
host test group** as “12 passed, 2 failed” without naming that group. The complete
host invocation had 21 passes (8 library + 1 native text + 12 original-owner)
and 2 failures, then stopped before the typed-host group. The table below uses
the corrected complete counts from the retained raw test log. This explanation
does not alter the frozen selection manifest or original results.

## Source identities and scope

| Role | Full source identity | Evidence and boundary |
| --- | --- | --- |
| Actual v14 Desktop release | Commit `6ee49848a4da82ee71e9707285dcc2c7e2b3c66b`; tree `e011aa3608213340ce0ef586266f8efeb9a7f549` | `v14-release/frozen/build-receipt.json` binds the published source to the actual before/after release tree and five measured ELFs. |
| Actual v14 Hepta dependency | Commit `52456c309f64ee80e7e377f774445c5dfe0523c9`; tree `9d0949a72d064cc2222859780c6ccd9a22c8e575` | Original release receipt and `pack-attempt1/organ-source-profile.json`; a later test-harness change does not relabel these binaries. |
| Original history owner | `995b6fb9ef73ada7c3348b01deb28940a2c4a2d1` | Actual ancestry is checked by the original source-profile tool; preserve its build/verify receipts. Similar tree content or the different `995b68e2…` UI commit is not a substitute. |
| Successful route-v2 source | Commit `84b51f68549447b314f9ea910988ad27ef5b9f6e`; complete tree `715ef84bd616969d2b60b69d5c0862d89d695bc2` | `route-v2/` records the original targeted route tests, formatter and fix command. This is a separate source from the compiled v14 release. |
| Native acceptance harnesses | See each attempt's retained `provenance.json`, source receipt and helper hashes | Corrected XRes/GTK/AT-SPI scripts may be newer than the frozen v14 ELF. Their identity is recorded separately. |
| SDK candidate | See `sdk-v2-rejected/` original/candidate metadata, source profile and explicit Cargo override | The baseline SDK remains `337566c8b25d47f7e4fff6a202157b65bf183330`. A refused candidate graph is not an accepted replacement. |

## Retained attempt ledger

The statuses below summarize root's completed actual runs. The raw commands,
exit statuses, source receipts and full logs remain the authoritative evidence.
Failed cases are not added to pass totals or silently represented as skipped.

| Evidence prefix | Recorded outcome | What it establishes |
| --- | --- | --- |
| `v14-tests/` | Native UI/host metadata and formatting completed; UI tests: 300 passed, 2 ignored; host invocation: 21 passed, 2 failed | Preserve both failures. Later v14 steps that the runner never reached are not claimed. |
| `v14-release/` | Actual release build passed; five ELF hashes and lengths frozen; Shell approximately 89 MB before packaging strip | Exact byte counts are in the receipt. This establishes a built release, not all acceptance gates. |
| `resources/` | Original bundle inventories and binding retained | Original 54-file resource set. Actual fonts/assets are excluded from this evidence archive. `pack-attempt1/original-resource-files.json` retains per-file hashes. |
| `history/`, `pack-attempt1/source-profile-*.json` | Original source binding and ancestry proof retained | The original history-owner proof was obtained from actual history, not waived on a shallow/incomplete clone. |
| `window-initial/` | Original window discovery failed within its unchanged 30-second gate | SDK337 does not publish `_NET_WM_PID`; the old `xdotool --pid` condition could not identify an already rendered window. |
| `window-diagnostic/` | At about 24 seconds, actual X tree and PNG showed the complete Hepta window and composer; PID property absent | Rendering diagnosis only. The initial 2/10-second observations showed cold paging. The diagnostic does not turn the earlier gate into a pass. |
| `xres-boundaries/` | Eight actual XRes ownership boundaries passed | Server-side client PID works without or despite a forged PID property, rejects a wrong PID and ambiguous two-window selection. This fixture is not a Rust product/UI qualification. |
| `window-xres-initial/`, `window-gtk3-failure/` | Old GTK/AT-SPI attempts failed; the GTK3 attempt reached an AT-SPI `get_text` TypeError | Keep the original failures and per-attempt harness identity. |
| `window-atspi-text-failure/` | Corrected AT-SPI text attempt subsequently failed at real IBus XIM readiness | This batch does not claim complete IME qualification. |
| `diagnostic-bytecode` in `HASH_ONLY_EVIDENCE.json` | Preserved diagnostic bytecode metadata/hash only | The archive does not contain or execute `.pyc` bytes. |
| `route-v1/` | Compilation failed on a missing original trait import | Retained as the actual first failure. |
| `route-v2/` | Original `just fmt`, four route tests and `just fix` passed at the exact tree above | Targeted original route behavior only; not the entire workspace gate. |
| `v15-host/` | Host suite: 28 passed (8 library + 1 native text + 14 original-owner + 5 typed-host); strict Clippy failed on two `collapsible_if` findings | The strict gate remains failed for this attempt. Subsequent corrections belong to later source/attempt evidence. |
| `sdk-v2-rejected/` | Original/candidate graph verification rejected the `num-traits` source closure | Both metadata graphs, exact override configuration and refusal logs remain available. No candidate build/qualification is inferred. |
| `pack-attempt1/` | Original source-profile build/verify, host archive, independent strip and pack A passed; external extraction then rejected `manifest.json` mode `0600` | The product's original packer created a private manifest under umask 077. The failure was the external extraction gate's extra permission assumption. No install/upgrade/rollback result is inferred. |

The external runner's subsequent v2 fix permits `0600` or `0644` only for the
exact `trillionnium-desktop/manifest.json` member. Other regular files still
require `0644` or `0755`; per-file/total sizes, normalized paths, duplicate
refusal and link restrictions remain. That code change is not evidence that
attempt 2 passed.

## Archive integrity and exclusions

Inside the compressed archive, `ARCHIVE_PLAN.json` lists exact original paths, byte counts, SHA256 values and
file-version metadata. The archiver refuses changes between selection, read,
copy and complete-batch verification. `ARCHIVE_MANIFEST.json` lists every
archived member. `HASH_ONLY_EVIDENCE.json` preserves the diagnostic bytecode
metadata without its binary payload. The complete gzip tar and manifest have
independent hashes in `ARCHIVE_INTEGRITY.json`.

The following were explicitly in flight when this batch was scoped and are
excluded: `native-v14-product-attempt2/`, `hepta-fullgate-52456c-v2/`, and
`desktop-v16-*`. SDK worktrees, Cargo targets, original ELF copies, extracted
packages, product tarballs and actual font/resource payloads are also excluded.
Full selected logs, metadata and PNG bytes are retained without truncation.

This batch establishes no production Root/human/model authentication, physical
keyboard/IME or human Orca verdict, mobile-device qualification, or fullgate
closure. Any later result must cite its own completed source and execution
receipt; it must not overwrite the earlier failures in this directory.

## Verify the retained archive

```sh
python3 -B archive_evidence.py verify \
  --archive v14-runtime-attempts.tar.gz \
  --sha256 0eedee0938ef616db79d711417e59f23d828aae5af571664b6dda85ba8f61713
```

The verifier checks member count, normalized paths, link refusal, sizes and every
recorded member SHA256. It reports success only after reading the complete
archive. The archive SHA256 is
`0eedee0938ef616db79d711417e59f23d828aae5af571664b6dda85ba8f61713`.
The source identities in these historical receipts remain unchanged when the
current integration pins advance.
