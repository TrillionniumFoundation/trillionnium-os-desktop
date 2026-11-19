# CP3A provider sources and current United preflight

This packet records the actual ordinary-user source qualification of the four
system providers required by the existing CP3A source adapter. It also replaces
the United 4.2.103/3621 selection in the current business preflight with the
already qualified 4.2.104/3622 source. It grants no installation, provider
semantics, native execution, business acceptance, or production readiness.

## Actual provider execution

The retained official `CP3A.260905.010` / build `16176746` / API 37 system image
is 2,294,853,632 bytes, SHA256
`dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4`.
The worker opened this existing image read-only. It did not download, mount,
compile, install, launch Android, or read application data.

The successful second execution ran on `ai395` as uid 1000 (`qq`) from
2026-11-19 11:02:06.839096 UTC to 11:02:12.696550 UTC. Its isolated user unit was
limited to CPU 31, 768 MiB memory, zero swap, and 64 tasks. The systemd execution
reported 5.922 seconds elapsed, 3.330 seconds CPU, and 169.7 MiB peak memory.
The worker limited output to 256 MiB with 16 MiB reserved for the terminal
receipt. The original unit and cgroup were observed retired afterwards.

All four APKs have version name `17` and version code `37`:

| Package | APK bytes | APK SHA256 |
| --- | ---: | --- |
| `com.android.providers.calendar` | 336,615 | `1ae37944b4f5f24d8d7bc849c76bd80c678d19cc3f5647ccaebd1254d8508744` |
| `com.android.providers.contacts` | 942,497 | `196cf184ca743601469dc235a4c7a163ac8ca9442cfdbd033bdaf109f5a9fd14` |
| `com.android.externalstorage` | 57,567 | `00cf8db78a3f8846e34fd3e6b7f1c811a9393b7c2e6227c083e27e5cdb0fa515` |
| `com.android.providers.media.module` | 13,826,854 | `aff897cc1f56583cd71c4cf48330eb4514fdefbd54f069e55223bd31e7af305b` |

Each has its own verified signer, preserved in the raw receipt. No uniform
platform signer was inferred. The MediaProvider receipt binds the entire
original chain: the GSI member `com.android.mediaprovider.capex`, the exact
`original_apex` ZIP member, its exact `apex_payload.img` member, and the APK at
`/priv-app/MediaProvider@CP3A.260905.010/MediaProvider.apk`. Both archives and all
four APKs were read to complete EOF with CRC and SHA coverage. The CAPEX/APEX
container signatures and AVB remain unqualified; a container digest is never
used as the APK identity.

`actual/RESULT.json` retains all 24 command lifecycles, 26 unchanged input
F9/SHA bookends, six actual rejected identity mutations, and the four receipt
references. Twelve of the commands are the actual SDK37 signature, badging,
and manifest checks. The 48 complete stdout/stderr files are in `actual/logs`;
17 intentionally contain zero bytes. Every child was observed through its
original PIDFD and reaped. Four APKs total 15,163,533 bytes.

## Preserved failure and independent review

The first run stopped at MediaProvider's actual filesystem owner 1000:1000
because its original image-leaf check assumed 0:0. Its failed result and
retirement observations remain under `history`. The second worker changes
only the new output root and the exact MediaProvider inode/owner/size and
APEX/payload pins. Default 0:0 checks for the other three providers remain.
Filesystem ownership inside an image is not an installed Android application
UID; `actual_UID` remains null for all four providers.

Both exact worker revisions and their delta are retained. The independent
review records the bounded-pipe output and SIGCHLD/leader-thread fixes before
execution, and the narrow second-run source change. That review explicitly
does not claim a separate independent review of the successful second result.
The failed first run is never counted as another successful cohort.

## Current selection and its consumer

`assemble_provider_cohort.py` checks 56 pinned metadata inputs, the actual
source lifecycles, complete receipts, raw logs, and MediaProvider chain. It
reconstructs `current/CURRENT-CP3A-PROVIDER-COHORT.json`, filling only the four
previously absent current APK/signer/receipt identities and source status.
Existing target-app records, historical provider records, runtime prerequisites,
and the coherent-full-GSI installation requirement remain in force.

`refresh_preflight.py` binds the existing qualified United source state,
registry, freshness record, and split receipt. It reconstructs
`current/CURRENT-BUSINESS-PLAN.json` with United version 4.2.104/code 3622 and
preserves the old selection as history. The other 38 package rows and the
complete installation prerequisites are unchanged, including Meituan's
data-preserving signer-migration requirement and Play country/expiry checks.
The final release still needs a fresh latest-release check before activation.

`verify_current_inputs.py` consumes both generated current files and reproduces
their exact bytes from the original evidence. The existing
`../source-refresh-20261119/SOURCE-REFRESH.json` now selects this packet and
these two outputs with full size/SHA pins. Its `verify_refresh.py` verifies the
selected packet and calls this consumer in addition to reconstructing the
unchanged six Beike/United source outputs. Adding evidence alone does not
change a live `CURRENT`, device image, installed package, or runtime guard.

## Validation and remaining gates

`validation/RESULT.json` records 14 local controls and two successful metadata
generation commands. The controls cover archive integrity, duplicate/missing
members, output capacity, capped child logs with reaping, SIGCHLD refusal,
exact source reconstruction, distinct signers, container-versus-APK identity,
false runtime promotion, retained Meituan migration, United split/version
identity, and the unchanged other 38 app rows. An initial case-sensitive test
message mismatch is recorded as a test-only failure; the exact rejection was
then matched and the control passed.

Offline replay requires repository dependencies at their exact pinned paths:

```sh
python3 -B compat/android/pocket4/current-app-acceptance/system-cp3a-provider-source-20261119/verify_current_inputs.py
python3 -B compat/android/pocket4/current-app-acceptance/source-refresh-20261119/verify_refresh.py
```

These consumers perform zero SDK commands, zero APK/image body reads, and zero
Android actions. Source qualification for four providers does not complete
provider semantic cleanup, destination custody, coherent GSI installation,
framework/UID binding, current business executors, or the 39-app acceptance
matrix. All runtime/business/production flags remain false. The only excluded
applications remain TextNow, TextFree, and Uber Rider.
