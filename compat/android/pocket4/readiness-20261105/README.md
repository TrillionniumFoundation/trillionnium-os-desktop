# Pocket4: all 45 tracked Apps, current evidence and unpassed gates

> **Current status:** [Checkpoint 14](../continuation-r11/checkpoint-14/README.md) records a framework replacement after a native abort. This matrix is the preserved CP13 historical result. Its 1/45 acceptance has not been carried into the unadopted replacement framework; all 45 Apps retain their release gates.

## Historical CP13 result

Checkpoint13 covers reviewed device observations through **2026-11-06
00:15:28 UTC** and their subsequent independent local reviews. Later continuation
runs are outside this frozen result.

The complete 2026-11-05 05:46:49.686297 UTC inventory contains **186 installed packages, 45 launcher packages/components, and 44 third-party packages**. All original **45 tracked Apps** remain in scope. No new launcher was found. **1/45 whole Apps is production ready: the complete declared Pocket4 QA fixture.** The other44 Apps remain unqualified. System Apps, the Thread demo, GMS, WebView shell and QA fixtures remain explicit entries. PackageManager's third-party count is a different set from the 45 launcher set and from the review-purpose categories below.

`readiness-matrix.json` is the generated machine-readable result. `app-gates.json` defines exact per-profile checks and every package-to-profile assignment. Each App row carries its original version/status, historical evidence pointers, current UID/version, progress observations, gate states and the complete list of unpassed gates. The full historical inputs remain unchanged under `inputs/`.

## Concrete remaining blockers

| App / workstream | Latest evidence and next required result |
|---|---|
| Camera | Release08 remains installed. Earlier real preview delivered64 physical/63 producer frames. The fresh21:43:28 UTC USB06 read again found the exact Sunplus source absent and no matching video node; the same provider process remained running. The original12288-task guard passed before/after. Zero photos. Stable physical hardware, then photo/persistence/video/recovery remain required; provider liveness alone does not establish camera availability. |
| Contacts | Search03 completed actual edit, normal close/reopen, query of the edited name, matching-result opening and UI deletion of the same ID6. Twelve inputs, tasks992/993 closed, no pending effects, zero Provider fallback deletes and zero owned tombstones. This now passes contacts.persist alongside the existing edit/cleanup/UI/lifecycle and separately reviewed runtime identity. Earlier Search01/02 failures remain unchanged. Permission/sync/error paths, stability and whole release remain open. |
| WebView shell | WebView04 retains actual local Unicode/form-event/JavaScript/storage/history/close-reopen and exact-key cleanup. A source-identified late tracing-dialog callback now has a same-certificate75170-byte candidate45e7be63, with only one method and classes.dex changed. Actual build and payload/IR checks passed; candidate remains uninstalled and not ART-qualified. The installed test-library declarations and three JARs are bound, but no stored OAT context was present at the three exact checked locations. HTTPS, image/media, error paths and stability/release remain. |
| Bilibili | The newer R6 saved-record observation found player controls visible in a later complete observation, following an initially empty player subtree. The original business-success false and outcome-unknown true remain; advancing playback, pause/seek and audio remain unverified. The earlier buffering and Nov4 scoped visual results remain historical. |
| Marriott / China Eastern | Retained Nov4 current-R16 evidence records native SIG11 with an observed virtual proc-fd mismatch / native SIGILL respectively. Corrected-runtime and actual business requalification remain absent. |
| Meituan / Beike | Retained evidence records startup self-exit / a blank login router. Stable merchant/item or listing detail completion remains unverified. |
| DeskClock | Candidate04 433ff501 is now installed and independently bound to signing, UID/version/epoch and actual runtime mappings: four saved stable snapshots, two process generations and381 whole ELF hashes. Alarm04 actually reached firing state and posted its exact notification, but the original run failed because no alert task appeared; real Open/Dismiss remains unverified. Timer04 completed start/pause/close/reopen/resume/reset/delete with11 inputs and two normal closes. An independent saved review proves scheduler0→1→0→1→0→0. Expiry06 then completed a separate real60-second timer, exact expiry notification, native Stop/reset and UI deletion. Its saved current scheduler records show0→1→0→0. Together the two current-APK fixtures pass clock.timer alongside identity/UI/lifecycle; alarm/timezone, audio, stability and release remain open. They are not one paused/resumed timer subsequently allowed to expire. Older e4ff timer credit is not inherited. |
| Calendar | Candidate11 00cb0b0a remains installed. Core13 retains persistence/UI/lifecycle credit and its original overall FAILED diagnostic gap. Discovery17 actually captured date/timezone/repeat picker structures, then closed task1007 and deleted only its empty LOCAL calendar. Calendar18 used that grammar but failed the frozen first-open complete-readiness bound before any control input, event or calendar creation; task1013 closed and all eight tables remained zero. These controller outcomes add neither business credit nor a global business-failure cutoff. Actual date/timezone/recurrence editing, reminder/sync/runtime/stability/release remain open. |
| Pocket4 fixture | **Complete declared QA-App release accepted.** Probe04 exercised nine positive controls and one actual ambiguous-selector refusal, with tasks1008/1009/1010 normally closed and two default-state reopens.118.238 live seconds,255 samples and six stable mappings bind the actual ART/x86_64 runtime and381 whole-hashed ELF objects. Twenty contiguous diagnostic intervals contain no new exact-UID crash/ANR or unexplained exit. CE/DE/model state and permissions are preserved. All nine fixed gates pass after independent feature/runtime reviews; original controller ready=false and automatic complete-mapping0 remain unchanged beside the separate decision. |
| Editor Contract QA | Two real rounds verified Unicode, Enter callbacks, single-emoji deletion, clear, separate launches and exact cleanup. Twelve inputs, two normal closes, no fresh crash/ANR. A separate lifecycle candidate passed43 actual host checks and DEX roundtrip, but has no signed APK or installation because the original signing key is unavailable. Composition, selection, resize/focus and full release remain open. |
| DocumentsUI | Flow10 completed all12 scoped checks: exact grants/cancellation, Files New folder, two-file Copy/Move, two actual UI Delete confirmations, close/reopen hash readback, revoked-existing-URI SecurityException, GET_CONTENT exact read and empty final grants. Zero fallback file unlinks; all five tasks, helper and fixture state cleaned. Original09 failure remains. The provider clause still needs controlled ArchivesProvider and dedicated Downloads navigation; search/sort/name conflicts and runtime/stability/release remain open. Earlier I/O/persistence/lifecycle scope stays accepted. |
| Gallery | Earlier video and separately reviewed runtime identity retain narrow credit. Rotation03 failed after Open because the Hist parser expected one space. The read-only reconciliation then retained FAILED because only activity-duration strings differed; separate exact cleanup closed task1005, removed owned images100/98 and directories99/97, and uninstalled the helper without Open replay or lease extension. Rotation04 passed the corrected route check but stopped at the album-title predicate, with zero rotation. Task1011, two owned images/directories/index rows, helper/CEDE and staged APK were cleaned; original media and identities remain. No Gallery business gate or UI-delete credit is added. |
| Remaining Apps | Launch/onboarding or older guest-core observations do not close the package-specific checks listed below. Login, external service, controlled call/message peer and hardware prerequisites remain explicit. |
| Native candidate07 | New retained actual receipts report 3,793 registered / 3,791 executed / 3,788 completed host cases, three skips, two disabled and zero failures, plus four passing Android signal cases with the exact mapped candidate engine. Raw native assertions were separately recomputed by the owner's frozen assessor. Main deployment and commercial-App qualification remain open; the controller had nonzero memory-limit events. |
| ART | Normal-projection draft is source-only/uncompiled. Matching Rust/full ART/paired APEX/lifecycle gates remain open; no candidate07 build result is substituted for these. |
| LMKD / Owner | Actual Owner08 stopped before ACTIVE and did not qualify installed operation or pressure survival. The mount mechanism recorded expected syscalls but failed its parent protocol/cleanup qualification; revision03's 15 local collection controls are not a namespace/Owner/pressure pass. Producer09/init ABI3 requests still need their matching actual receipts in this evidence set. |

Platform state is a read-only snapshot of retained files from the parallel owner's workspace. Another owner may have advanced since that snapshot. This bundle starts or repeats none of its builds/tests. Platform candidate progress is never treated as an App pass or proof of causality.

## Shared storage prerequisite

One standard unmount and one mount restored the existing `emulated;0` session.
Fresh read-only open/stat/statfs checks succeeded for both shared-storage paths
at 07:47:31 UTC. Main/provider/vold identity and lower data metadata were
preserved. The original numerical-FUSE-ID qualification failure remains retained;
it was resolved by separate I/O and retired/new-session evidence, not another
mount attempt. App file-save qualification is separate.

The [session lifecycle patch and reference evidence](../shared-storage/storage-fuse08/README.md)
fix the reproduced double-removal/missing-wait logic. The main reference passed
nine host method cases; the matching `ImmutableVolumeInfo` reference variant is
clean-apply verified only at this checkpoint. The actual installed services JAR
is pinned. Its minimal DEX candidate was actually assembled and aligned, with
all 7,582 classes / 53,839 methods and 65 ZIP payloads compared. Only the reviewed
target method differs. Actual ART22 now reports the exact target class Verified
against the retained original baseline. The inferred boot-extension Wi-Fi checksum
warning is retained; entire boot-image qualification, live lifecycle and persistent
deployment remain open.

## Exact inventory reconciliation

The original `inputs/current-installed-inventory-20261105.json` remains byte-identical (SHA `27775988042249ca00a3ac02d303a146e74f1fe1bb26880e3cd2d75df4af887e`) and still has both completeness flags **false**. Its collector conservatively retained 91 unparsed header/metadata rows.

One separately authorized read-only job read the already-saved `launchers.stdout`; it made no new device query or UI action. Its 6,764 bytes have SHA `d58e953bd95b3ad545fd88239c0838450e478e7a6233a938d66cdab0a277bdca`. `parse_launcher_inventory.py` consumed the complete exact grammar: header 45, contiguous Activity #0 through #44, one correctly structured metadata row and unique component per block, and exact equality to the original component order/package set/unparsed header rows. Unknown, extra, reordered, malformed or duplicate rows reject the derivation.

The separate `inputs/current-installed-inventory-derived-20261105.json` is the completed read-only derivation (SHA `00318b2cb727e042b23901315ed93ca1a4410712a3f3a47e086f9f9cc6b95e35`). It does not rewrite the original outcome or infer readiness. `inputs/launcher-reader-job-status.json` retains the actual successful/durable reader terminal.

## Every retained App and its next business coverage

Every row also requires exact installation/runtime identity, usable scoped UI, normal owned close/reopen, fresh stability/resource evidence, preserved data/permissions, and whole-release coverage review. The descriptions below are required checks for the still-open Apps; the accepted QA fixture is explicitly marked. Supported authenticated/transactional scope needs an authorized test account/environment; outbound messages/calls need an explicitly authorized test recipient. No test plan here executes a purchase, booking, message, account change or device action.

| Package | App | Concrete business profile and first unpassed check |
|---|---|---|
| `com.Hyatt.hyt` | Hyatt | hotel: Enter location/dates/occupancy and verify populated matching availability. |
| `com.MobileTicket` | 12306 | train: Enter origin/destination/date; verify matching trains and seat availability. |
| `com.amazon.mShop.android.shopping` | Amazon | retail: Enter a product query; verify matching populated search results. |
| `com.android.calendar` | Calendar | calendar: Create/edit one uniquely owned local event; verify dates, timezone and recurrence. |
| `com.android.camera2` | Camera | camera: Observe a real live preview without the cannot-connect dialog; correlate the exact provider session. |
| `com.android.contacts` | Contacts | contacts: Edited-contact Search and exact reopen now verified; remaining permission/sync/error behavior and repeat/stability coverage stay open. |
| `com.android.deskclock` | DeskClock | clock: Create one owned alarm, observe delivery and dismiss it; preserve pre-existing alarms. |
| `com.android.dialer` | Dialer | dialer: Verify number entry/editing, contact lookup and supported dialer routes. |
| `com.android.documentsui` | DocumentsUI | documents: Create, rename, open and read a uniquely owned file with content hash verification. |
| `com.android.gallery3d` | Gallery | gallery: Observe known owned image/video fixtures with matching metadata and thumbnails. |
| `com.android.messaging` | Messaging | messaging: Verify recipient resolution and exact draft composition with owned test data. |
| `com.android.quicksearchbox` | QuickSearchBox | search: Enter Unicode queries with exact readback and verify matching local/web results. |
| `com.android.settings` | Settings | settings: Verify supported system, network, display, storage and application settings pages. |
| `com.android.threadnetwork.demoapp` | Thread network demo | thread: Identify the exact demo contract, supported radio/service and controlled peer prerequisites. |
| `com.bestbuy.android` | Best Buy | retail: Enter a product query; verify matching populated search results. |
| `com.ehi.national.mobile` | National | rental: Enter pickup/dropoff location and dates; verify populated matching vehicle availability. |
| `com.enflick.android.TextNow` | TextNow | voip: Resolve legitimate login/Play/service prerequisites with same-epoch exact-UID evidence. |
| `com.google.android.gms` | Google Play services / installed compatibility provider | gms: Verify the actual installed microG/GMS implementation, enabled services and declared compatibility scope. |
| `com.hertz.android.digital` | Hertz | rental: Enter pickup/dropoff location and dates; verify populated matching vehicle availability. |
| `com.hilton.android.hhonors` | Hilton | hotel: Enter location/dates/occupancy and verify populated matching availability. |
| `com.ihg.apps.android` | IHG | hotel: Enter location/dates/occupancy and verify populated matching availability. |
| `com.jingdong.app.mall` | JD | retail: Enter a product query; verify matching populated search results. |
| `com.lianjia.beike` | Beike | housing: Enter location/filters and verify matching populated listings. |
| `com.marriott.mrt` | Marriott | hotel: Enter location/dates/occupancy and verify populated matching availability. |
| `com.pinger.textfree` | TextFree | voip: Resolve legitimate login/Play/service prerequisites with same-epoch exact-UID evidence. |
| `com.rytong.airchina` | Air China | flight: Enter route/date/passenger query and verify matching populated availability. |
| `com.rytong.ceair` | China Eastern | flight: Enter route/date/passenger query and verify matching populated availability. |
| `com.sankuai.meituan.takeoutnew` | Meituan Takeout | delivery: Reach a stable usable home without a self-exit loop. |
| `com.sdu.didi.psnger` | DiDi | ride: Verify legitimate account and selected pickup/destination handling. |
| `com.ss.android.ugc.aweme` | Douyin | video: Enter a legitimate public query and verify matching title/author results. |
| `com.szzc` | SZZC | rental: Enter pickup/dropoff location and dates; verify populated matching vehicle availability. |
| `com.taobao.taobao` | Taobao | retail: Enter a product query; verify matching populated search results. |
| `com.tencent.mm` | WeChat | messaging: Verify recipient resolution and exact draft composition with owned test data. |
| `com.ubercab` | Uber | ride: Verify legitimate account and selected pickup/destination handling. |
| `com.united.mobile.android` | United | flight: Enter route/date/passenger query and verify matching populated availability. |
| `com.xunmeng.pinduoduo` | Pinduoduo | retail: Enter a product query; verify matching populated search results. |
| `com.zhubajie.client` | Zhubajie | services: Enter a service query and verify matching populated results. |
| `com.zillow.android.streeteasy` | StreetEasy | housing: Enter location/filters and verify matching populated listings. |
| `ctrip.android.view` | Ctrip | travel: Verify the supported flight/hotel/train search routes with location/date input. |
| `jp.co.ana.android.tabidachi` | ANA | flight: Enter route/date/passenger query and verify matching populated availability. |
| `local.pocket4.fixture` | Pocket4 fixture | fixture: All nine unchanged gates pass for the complete five-class QA contract, current APK and bounded three-round acceptance. |
| `org.chromium.webview_shell` | WebView shell | webview: Load controlled local/HTTPS fixtures and verify layout, text, images and JavaScript. |
| `org.droidloom.qa.editorcontract` | Editor contract QA | editor: Core Unicode/Enter/deletion/clear/reopen passed; finish composition, selection, resize/focus transitions and complete release qualification. |
| `org.fcitx.fcitx5.android` | Fcitx5 | ime: Verify configured Chinese/Unicode composition, candidate selection and exact commit into an owned field. |
| `tv.danmaku.bili` | Bilibili | video: Enter a legitimate public query and verify matching title/author results. |

## Reproduce or update without touching Pocket4

Run from this bundle directory with Python 3. No third-party Python dependencies are required. Outputs are create-only; choose a new name and review its diff before replacing a published matrix.

```sh
python -B parse_launcher_inventory.py \
  --original inputs/current-installed-inventory-20261105.json \
  --original-sha256 27775988042249ca00a3ac02d303a146e74f1fe1bb26880e3cd2d75df4af887e \
  --launchers inputs/launchers.stdout \
  --launchers-sha256 d58e953bd95b3ad545fd88239c0838450e478e7a6233a938d66cdab0a277bdca \
  --output inventory-reproduced.json
python -B update_matrix.py \
  --inventory inputs/current-installed-inventory-derived-20261105.json \
  --gate-reviews gate-reviews.json \
  --package-identities ../package-identity-observations-20261105.json \
  --output readiness-next.json
```

For later complete inventories, pass the new receipt to `--inventory`. The updater unions its launcher set with the immutable 45-App baseline; absent or disabled entries remain in the matrix, and new launchers get an unclassified checklist that cannot pass release scope until reviewed. A different epoch/version/UID invalidates old gate credit.

Independent installed-package observations now bind each review to the latest observed base APK and complete split set. This closes a concrete gap: previously a same-version replacement invalidated old credit only when a new gate review happened to name the new hash. Now an observed installation or content-identity change invalidates earlier credit immediately, even with no new review. Reinstalling the same bytes and an A→B→A rollback also require later reviews. A later read-only observation of identical bytes preserves earlier scoped results. An observation never passes a business or runtime-engine gate by itself.

`--package-identities` accepts schema `pocket4-package-identity-observations-v1`. Each observation carries a unique ID, package, Android user0, UID, version, epoch, timestamp, kind (`read_only` or `package_install`), complete base/split SHA-256/size/signer identities, and hash-and-size-verified evidence. The most recent observation must agree with the inventory. Reviews for a split package additionally bind the canonical `apk_set_sha256`. With no independent installed-APK observation, a review receives no current gate credit. The 45-package audit is a bounded observation window, not a simultaneous snapshot; the later actual Clock installation is a separate observation and supersedes its audited old APK.

Add hash-referenced scoped observations to `progress.json`; they can retain failed/blocked/pending gates but **cannot pass a gate**. Historical snapshot booleans and install/build/launch success cannot promote readiness.

Optional `--gate-reviews review.json` accepts only schema `pocket4-reviewed-app-gates-v1` with a `reviews` array. Each review needs a unique `id`, `reviewer`, `package`, `scope` (`scoped` or `whole_app_release`), `observed_at_utc`, exact `framework_epoch_sha256`, `version_code`, `uid`, `apk_sha256`, nonempty `evidence` containing bundle-relative `path` and `sha256`, and `checks` mapping known gate IDs to `passed/failed/blocked/pending`. The files must exist and match their hashes; the review must follow the current inventory and any newer retained failure cutoff. A passed `release_scope` additionally requires `scope=whole_app_release`, `all_features_reviewed=true`, `retained_failures_reconciled=true` and `unresolved_findings=[]`. These are explicit reviewer attestations backed by inspected evidence, not semantic proof extracted automatically from arbitrary documents. Every required gate must pass on the same exact binary before an App can qualify. This matrix retains the historical Camera preview review but rejects its current credit after the newer hardware-absence failure. Current scoped reviews pass Contacts identity/edit/cleanup/persistence/UI/lifecycle, Calendar persistence/UI/lifecycle, WebView UI/lifecycle, Clock433ff identity/UI/lifecycle, local Probe source-contract/UI/lifecycle and Editor core UI/lifecycle checks. The original timer-expiry failure and the later e4ff timer-completion evidence remain retained against their exact historical APKs. The installed433ff replacement does not inherit them; its timer completion and complete alarm/timezone gates remain pending. Documents11 passes local I/O and persistence; Gallery retains its independently reviewed runtime identity/UI/lifecycle scope. Composite checks remain open wherever HTTPS, media, provider, error, recurrence, reminder or other required coverage is missing. No whole-App release gate passes; all 45 Apps remain in scope.

## Local validation and evidence limits

Nine focused local integrity regressions passed; the current run is recorded in validation.json. They cover the actual inventory and full45-entry retention, malformed inputs and historical readiness booleans, absent/new launcher union, scoped/stale reviews, replacement without a new review, same-byte read-only observation versus reinstall, rollback to old bytes, complete split binding, and tampered evidence. The tests' positive review objects are explicitly synthetic and never enter the delivered matrix. No parallel owner's tests were rerun.

`SOURCE_MANIFEST.json` binds this bundle. Raw personal images, contact rows and account names are absent. `inputs/platform-observations.json` retains the original source hashes and selected facts; its source locators identify the retained receipts reviewed locally. Where this bundle contains an extract rather than the full original, that distinction remains explicit. Earlier evidence is not silently superseded or deleted.

## Checkpoint8 identity and review counts

The installed-package history now has49 observations across45 Apps. Clock e4ff and Calendar95633138 replacements each invalidate older binary-specific reviews. The matrix retains14 reviews, accepts8 scoped reviews and leaves6 older reviews without current credit. No whole-App release gate passes. The task budget profile changed only its pinned observation from12288 to6144 after actual read-only diagnosis; all original guard logic and earlier failed receipts remain intact.

## Historical checkpoint10 identity and review counts

The history contains52 installed-package observations across all45 Apps. The latest Calendar installation is candidate11 00cb0b0a; it invalidates earlier-binary reviews and has no accepted composite business gate. Clock remains installed as e4ff: timer is passed and the independently reviewed alarm03 due-delivery result is failed. Its signed and ART-verified candidate04 has no installed-App credit. Eighteen reviews are retained; twelve provide current scoped statuses, including negative results, and six older reviews have no current credit. Contacts receives only its separately reviewed observed runtime identity. Whole-App readiness is0/45. The original TasksMax/pids.max12288 profile was independently verified after its owner restored it; the historical6144 snapshot above is retained as history.

## Retained checkpoint12 identity and review counts

The history contains53 installed-package observations across all45 Apps. Clock's actual433ff installation invalidates all earlier-binary business reviews. Its saved runtime review passes identity. The separate Timer04 controls/persistence flow and Expiry06 real completion flow together pass clock.timer, while alarm/timezone and the whole release remain pending. Calendar Core13 passes persistence/UI/lifecycle without changing its original overall FAILED result or granting its unobserved date/timezone/recurrence clause. Discovery15/16 retain their clean pre-input failures without additional gate credit. Contacts Search03 passes the exact edited-contact persistence check. Gallery fixture cleanup adds progress only. Twenty-three reviews are retained, fifteen provide current scoped statuses, and eight older reviews have no current credit. Whole-App readiness remains0/45. All actual jobs in this cutoff used the original12288-task profile and the same held Main generation.

## Current checkpoint13 identity and release counts

All45 Apps and53 installed-package observations remain tracked. There are24 retained reviews:16 accepted records and8 older records without current credit. Fifteen accepted records provide scoped statuses; the other is Root's complete declared Probe QA release on exact APK91e352c2. Thus whole-App readiness is1/45, with all other44 Apps still open. Probe's original automatic ready=false and mapping counter0 are preserved; its independent final review supplies the missing gate decisions. Clock timer, Calendar persistence/UI/lifecycle, Contacts edit/search/persistence/cleanup and the older Files/Gallery/WebView scoped evidence retain their exact binary and feature limits. No tracked App binary was replaced in this checkpoint; temporary test helpers retain their exact install/cleanup receipts, and the WebView candidate earns no installed-App credit.

Calendar17 picker discovery, Calendar18 pre-input failure and the Gallery03/04 failed attempts and exact cleanup are retained without promoting unobserved business steps or revoking unrelated prior accepted scope. All actual device flows in this cutoff used the original12288-task Main profile and ownership guards. Later live continuations are outside this frozen matrix.
