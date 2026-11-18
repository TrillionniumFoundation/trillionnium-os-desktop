# Pocket4's 39 required application assessments

The user excluded exactly three unavailable official APKs on 2026-11-18:
TextNow (`com.enflick.android.TextNow`), TextFree (`com.pinger.textfree`), and
Uber Rider (`com.ubercab`). The original 42-package selection remains recorded
in `release-scope-20261118.json`; the other 39 packages remain required.
Exclusions are always reported as `exempt_unverified` and contribute zero passes.

The fixed selection comes from the published historical `CANDIDATE42.json`
identified in that definition. It establishes package membership only. Its old
versions, APK identities and runtime results are not adopted. No existing
42-app contract, historical report, business executor, or installation is changed.

## Produce a report for the actual required scope

Prepare a separately reviewed native release manifest containing exactly the
39 required packages, their current complete identities, the accepted Main,
and all six common gates plus every business gate in their bound profiles.
Keep the original 42-app contract and history intact. Do not fabricate APK
identities for the three unavailable packages or reuse old versions as current.
The native checker already accepts an externally pinned application count:

```sh
droidloom-applications \
  --release-check /absolute/path/manifest39.json \
  --release-results /absolute/path/results39.json \
  --expect-release-sha256 "$MANIFEST39_SHA256" \
  --expect-main-sha256 "$MAIN_SHA256" \
  --expect-app-count 39 > /absolute/path/report39.json
```

This command checks declared evidence and bytes; it does not execute Android
tests. An incomplete report is still emitted with exit status 1. Retain that
status and report. A previous 42-app report cannot be relabeled as a 39-app
report; the checker must calculate a report for the new pinned manifest.

Then bind that native output to the explicit user scope:

```sh
python3 -I -B compat/android/pocket4/current-app-acceptance/release_scope.py \
  --manifest /absolute/path/manifest39.json \
  --manifest-sha256 "$MANIFEST39_SHA256" \
  --registry /absolute/path/app-release-gates.json \
  --registry-sha256 "$GATE_REGISTRY_SHA256" \
  --report /absolute/path/report39.json \
  --report-sha256 "$REPORT39_SHA256"
```

The SHA-256 values must come from independently selected, reviewed input
records. File contents and their self-reported hashes are not a substitute
for these explicit pins. Paths must be absolute canonical regular files.
The tool reads only these explicit files and its fixed scope definition; it
never opens referenced APKs, evidence paths, sockets, accounts or user data.

The native report's manifest hash must match the complete supplied manifest.
This binds the Main, boot, framework epoch, cohort and application identities
without adding invented freshness fields to the native report. Business gates
come from the pinned registry, including all checks in each selected profile;
there are no hardcoded obsolete business gate lists. The registry may contain
additional support packages, which do not alter the fixed selected package set.

## Interpretation and checks

The output retains the native report unchanged and adds a required-39 summary
and the three exclusions. Native global issues keep the result incomplete even
if 39 per-app rows contain complete declared evidence. Missing, failed, blocked
and unsupported required gates remain incomplete. Contradictory counts, unknown
schemas, duplicate keys/packages, empty business definitions and another
manifest's report are rejected.

Exit status 0 means complete **declared evidence coverage** for the 39 required
applications; 1 means incomplete coverage; 2 means invalid input. The output
always retains `production_ready`, `runtime_qualified`, `latest_versions_verified`
and `deletion_authorized` as false. It does not authenticate evidence authors,
prove evidence semantics or freshness, or turn a Clock/IHG partial case into
whole-app acceptance. Runtime qualification, current-version verification and
safe final cleanup still require their original evidence and implementation.

Run the host controls with:

```sh
python3 -I -B compat/android/pocket4/current-app-acceptance/test_release_scope.py
```

All fixtures are synthetic JSON. They do not open any APK, contact a device,
install an application, change permissions, or execute a business action.

## Current input observations, 2026-11-18

The first current source-input verification produced native expected-input
fragments for seven complete, unmodified publisher APKs, totaling
1,112,420,343 bytes. All seven passed the same final verifier's actual SDK 37
signature, binary manifest, whole-file hash and reviewed native-layout
checks on 2026-11-18 between 10:24:30 and 10:24:52.025 UTC. The independently
pinned candidate definitions retain each exact signer and payload hash:

| Application | Signed Android version / code | Candidate definition |
| --- | --- | --- |
| Firefox | `160.0.1` / `2016196678` | [firefox-candidate.json](firefox-candidate.json) |
| Fcitx | `0.1.3-0-g048f581c` / `114` | [fcitx-candidate.json](fcitx-candidate.json) |
| Shenzhou | `9.6.3` / `329` | [szzc-candidate.json](szzc-candidate.json) |
| Ctrip | `8.97.6` / `2136` | [ctrip-candidate.json](ctrip-candidate.json) |
| Beike | `3.06.71` / `3067100` | [beike-candidate.json](beike-candidate.json) |
| China Eastern | `9.5.16` / `239` | [ceair-candidate.json](ceair-candidate.json) |
| Railway 12306 | `5.9.4.5` / `275` | [12306-candidate.json](12306-candidate.json) |

The [APK verifier guide](../apk-content-identity/README.md) records the
actual checks, source pins, channel observations and limits. Firefox,
Shenzhou and Ctrip are newer than the historical candidates; the other four
fresh official downloads still match their historical package versions.
The Fcitx release tag is `0.1.3`; the exact signed Android build name above
is preserved, along with the selected GitHub signing channel.

The additional v3 layout model retains literal path/bytes/hash bindings
and separately checks shared-library layouts, two dynamic-table views,
zero-byte placeholders, a bounded 7z container and an interpreter-tagged
ARM32 ET_DYN object. Compressed content is not decoded or counted as an ELF
library; an interpreter declaration with a zero entry is not evidence of a
standalone executable role. The original v1 behavior and v2 exact-four
cross-architecture layout remain intact. Four real wrong-candidate controls
failed without receipts, alongside 63 separate source controls.

These are source-input results. They do not establish installation, current
device readback, native loading, inner-archive compatibility, business
acceptance or production qualification. Expected-input fragments retain
their observed local paths; a future owner must regenerate and bind them
to the actual deployment locations through the unchanged runtime gates.

### Current microG and its retained Companion dependency

A subsequent common-verifier run checked all nine complete APKs on
2026-11-18 between 11:04:11 and 11:04:38.163 UTC. All nine SDK 37 candidate
invocations passed with unchanged APK F9 and whole-file SHA-256 bookends.
The total original APK size is 1,225,152,890 bytes. This covers eight
required39 source inputs and one separately retained dependency, with zero
runtime, business, exemption or production credit. The nine-input record is
39,218 bytes, SHA-256
`eb85fdb5a4dcfd51e8d73d31a4f2ac8746c1a944eb1e5d8f8bc3761a2230d93d`.

| Application | Signed Android version / code | Scope | Candidate definition |
| --- | --- | --- | --- |
| microG Services | `0.3.18.252432` / `252432036` | Required39 member | [microg-candidate.json](microg-candidate.json) |
| microG Companion | `0.3.18.40226` / `84022636` | Retained dependency outside required39 | [microg-companion-candidate.json](microg-companion-candidate.json) |

Both inputs are the standard artifacts of the official stable
[microG v0.3.18.252432 release](https://github.com/microg/GmsCore/releases/tag/v0.3.18.252432).
Their actual whole-file hashes match the published GitHub asset digests,
and SDK 37 verified the same historical certificate pin
`9bd06727e62796c0130eb6dab39b73157451582cbd138e86c468acc395d14165`.
The Huawei `-hw` build and the `org.microg.gms` user preview are separate
variants. The release
prose's `250932036` is not used as a version-code pin; the selected asset
and signed manifest establish `252432036` for Services.

Services has 24 standard native libraries across four ABIs and no layout
exceptions. Companion has no standard `lib` payload. Its separate
`pocket4-official-apk-candidate-no-native-v1` model requires an empty ABI
list while retaining all signature, external candidate hash, whole APK,
binary manifest and standalone-base checks. It rejects every actual file
under `lib`, ambiguous paths, special members and nonempty directory
entries. Existing v1/v2/v3 candidates still reject empty ABI lists. This
proves only the standard-directory observation; it does not prove absence
of dynamically loaded native code. The source suites now contain 40
candidate controls, 9 dual-dynamic controls and 20 resource controls.

Companion is `com.android.vending`, not Google Play Store. It remains one
of the five previously retained dependencies alongside
`com.android.droidloom.home`, `com.android.droidloom.ime`,
`local.pocket4.actions.v2` and `com.android.webview`. The other four require
the actual coherent Android build and runtime; Firefox does not replace
the embedded WebView provider. Neither Companion nor these dependencies
changes the required39 denominator or the three explicit exemptions.

### Other current-channel observations

Fresh anonymous official Google Play US pages also exposed the following
exact application-detail version strings. The observations were made on
2026-11-18 between 09:11:57 and 09:16:44 UTC. Each version was joined to the
same detail object's exact package name, rather than taken from reviews or
an `Updated on` date. All eleven differ from the 2026-11-09 historical
candidate. Their current complete signed APK/split inputs have not yet been
acquired in this continuation.

| Application / official US source | Exact selected package | Historical candidate | Observed public version |
| --- | --- | --- | --- |
| [National](https://play.google.com/store/apps/details?id=com.ehi.national.mobile&hl=en_US&gl=US) | `com.ehi.national.mobile` | `6.15.0.9354` | `6.16.0.9403` |
| [IHG](https://play.google.com/store/apps/details?id=com.ihg.apps.android&hl=en_US&gl=US) | `com.ihg.apps.android` | `5.108.1` | `5.111.1` |
| [Hyatt](https://play.google.com/store/apps/details?id=com.Hyatt.hyt&hl=en_US&gl=US) | `com.Hyatt.hyt` | `26.9.0` | `26.11.1` |
| [Amazon Shopping](https://play.google.com/store/apps/details?id=com.amazon.mShop.android.shopping&hl=en_US&gl=US) | `com.amazon.mShop.android.shopping` | `32.18.0.100` | `32.19.0.100` |
| [Best Buy](https://play.google.com/store/apps/details?id=com.bestbuy.android&hl=en_US&gl=US) | `com.bestbuy.android` | `26.9.20` | `26.11.10` |
| [Hertz](https://play.google.com/store/apps/details?id=com.hertz.android.digital&hl=en_US&gl=US) | `com.hertz.android.digital` | `5.6.0` | `5.8.0` |
| [Hilton](https://play.google.com/store/apps/details?id=com.hilton.android.hhonors&hl=en_US&gl=US) | `com.hilton.android.hhonors` | `2026.9.29` | `2026.11.3` |
| [Marriott](https://play.google.com/store/apps/details?id=com.marriott.mrt&hl=en_US&gl=US) | `com.marriott.mrt` | `10.79.0` | `10.82.0` |
| [United](https://play.google.com/store/apps/details?id=com.united.mobile.android&hl=en_US&gl=US) | `com.united.mobile.android` | `4.2.98` | `4.2.103` |
| [StreetEasy](https://play.google.com/store/apps/details?id=com.zillow.android.streeteasy&hl=en_US&gl=US) | `com.zillow.android.streeteasy` | `3.127.1` | `2026.47.0` |
| [ANA](https://play.google.com/store/apps/details?id=jp.co.ana.android.tabidachi&hl=en_US&gl=US) | `jp.co.ana.android.tabidachi` | `7.6.0` | `7.7.1` |

These are dated public-channel observations, not a device-entitlement or
all-channel maximum claim. Amazon and Marriott also have differing public
channel version labels. A Chinese Hilton package with a different package
name cannot replace the required global package. The owner must establish
the selected delivery channel, complete APK/split set, actual signer and
version code from authenticated package bytes before updating a runtime plan.

The original HTTP observations retain exact source-body sizes and SHA-256s.
Their application-detail fields were `ds:5[1][2][77][0]` for package and
`ds:5[1][2][140][0][0][0]` for version. The current official page body pins
are recorded below to distinguish these readings from earlier cached text.
They are observation references only, never install or acceptance receipts.

| Selected package | Observed UTC | HTTP body bytes | HTTP body SHA-256 |
| --- | --- | ---: | --- |
| `com.ehi.national.mobile` | `2026-11-18T09:11:57.986042+00:00` | 1,285,681 | `12025fd092119c76bbf348b18fb709956c2a77c64d15d2f22d1e5f1eb801a0f3` |
| `com.ihg.apps.android` | `2026-11-18T09:11:57.986806+00:00` | 1,298,810 | `d4bd37e02a8bf101d0e627b09ab04e6fddcf0d5776a3f55eb7345a0c56e8924e` |
| `com.Hyatt.hyt` | `2026-11-18T09:16:36.775040+00:00` | 1,265,318 | `d56a6eda3579ee9d8491e089de706333861b28f46ffecf30583da831f64278e1` |
| `com.amazon.mShop.android.shopping` | `2026-11-18T09:16:36.776095+00:00` | 1,357,347 | `a99f1274624f1f10d5f4f467c1cbde544090dd8a84a54c1ca1fa406b463e29d9` |
| `com.bestbuy.android` | `2026-11-18T09:16:36.776709+00:00` | 1,303,995 | `e58e9b5f6acab64221b79506fa390a8449c5f32a847e74f547db89c4170e5d37` |
| `com.hertz.android.digital` | `2026-11-18T09:16:40.636176+00:00` | 1,289,382 | `4f1899ef082c96258f16bc93a3a9de27271ecb89c2b34db2cafa1476484c270f` |
| `com.hilton.android.hhonors` | `2026-11-18T09:16:40.664679+00:00` | 1,294,119 | `86d75e5148429146219edba5567bd0ede2f0862219cdf3ad9c6ceb2c8db1c0a3` |
| `com.marriott.mrt` | `2026-11-18T09:16:40.705458+00:00` | 1,283,479 | `294eac3b7548a4265b7581d340af83e578517d3daa45d28633b724049edb963a` |
| `com.united.mobile.android` | `2026-11-18T09:16:44.834252+00:00` | 1,284,403 | `d1fca22409b5944b088453be5261abc2229383f408bb189ff71d3c1418817817` |
| `com.zillow.android.streeteasy` | `2026-11-18T09:16:44.845417+00:00` | 1,280,013 | `20385d1796dd6caa16690a2b7701b5c1e118a1de00074e91a14e202205afb579` |
| `jp.co.ana.android.tabidachi` | `2026-11-18T09:16:44.862639+00:00` | 1,263,923 | `737ebb8a746e82547262dc54eee08d8cb41ea28deb02ce85f553bac10ca0a162` |

Required input gaps remain ordinary blockers. They do not create additional
exemptions beyond TextNow, TextFree and Uber Rider. Failed, inaccessible or
older download responses are not used as current inputs. This guide does
not change the fixed scope hash, native release-report schema or any common
and business gate, and grants no deployment or deletion authority.
