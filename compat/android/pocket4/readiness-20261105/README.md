# Pocket4: all 45 tracked Apps, current evidence and unpassed gates

## Current result

The complete 2026-11-05 05:46:49.686297 UTC inventory contains **186 installed packages, 45 launcher packages/components, and 44 third-party packages**. All original **45 tracked Apps** remain in scope. No new launcher was found. **0/45 whole Apps are production ready.** System Apps, the Thread demo, GMS, WebView shell and QA fixtures remain explicit entries. PackageManager's third-party count is a different set from the 45 launcher set and from the review-purpose categories below.

`readiness-matrix.json` is the generated machine-readable result. `app-gates.json` defines exact per-profile checks and every package-to-profile assignment. Each App row carries its original version/status, historical evidence pointers, current UID/version, progress observations, gate states and the complete list of unpassed gates. The full historical inputs remain unchanged under `inputs/`.

## Concrete remaining blockers

| App / workstream | Latest evidence and next required result |
|---|---|
| Camera | Release08 remains installed. Earlier real preview delivered 64 physical / 63 producer frames. Shared storage is now actually readable, but the newer 07:48 trial displayed a connection error with the physical USB source absent. Zero photos. Restore stable hardware, then photo/persistence/video/recovery. |
| Contacts | Contacts11 completed actual Device-only UI create/edit, normal close/reopen of the same ID3, menu Delete+confirmation and exact empty-database cleanup. Ten inputs, two normal closes, no fallback delete, matching APK/UID/version before and after. Search UI, remaining permission/sync/error and repeat/stability scope remain. |
| WebView shell | WebView04 completed local Unicode/form-event/JavaScript/storage/history/close-reopen and exact-key cleanup. Two launches/two normal closes, no pending effect, fixture reaped/socket closed. HTTPS, image/media, error paths and stability/release scope remain. |
| Bilibili | The newer retained video transition opened the intended course page and closed only its owned task, but retained buffering and no verified advancing frames/audio. Keep the earlier Nov4 scoped visual result as history; do not transfer it into a current whole-App pass. |
| Marriott / China Eastern | Retained Nov4 current-R16 evidence records native SIG11 with an observed virtual proc-fd mismatch / native SIGILL respectively. Corrected-runtime and actual business requalification remain absent. |
| Meituan / Beike | Retained evidence records startup self-exit / a blank login router. Stable merchant/item or listing detail completion remains unverified. |
| DeskClock | Stopwatch and timer core flows passed; notifications were actually enabled. The later 60-second background timer stayed RUNNING 28.245 seconds past due, so clock.timer is failed. Exact timer/task cleanup passed; original alarms stayed unchanged. Expiry cause, alarm/timezone/audio and full release remain open. |
| Pocket4 fixture | Exact installed source reviewed; two real Unicode/field-isolation/confirmation/clear/reopen rounds completed, 14 inputs and two normal closes. Ambiguous-selector negative coverage and full release gates remain open. |
| Editor Contract QA | Two real rounds verified Unicode, Enter callbacks, single-emoji deletion, clear, separate launches and exact cleanup. Twelve inputs, two normal closes, no fresh crash/ANR. Composition, selection, resize/focus and full release remain open. |
| DocumentsUI | Actual create/write/read, provider rename and Files UI rename preserved the owned 87-byte hash. The next open has an acknowledged tap but unknown post-observation. Own fixture state is retained for reconciliation; complete I/O/grants/reopen/delete/cleanup are not passed. |
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

Every row also requires exact installation/runtime identity, usable scoped UI, normal owned close/reopen, fresh stability/resource evidence, preserved data/permissions, and whole-release coverage review. The descriptions below are **planned required checks**, not reported passes. Supported authenticated/transactional scope needs an authorized test account/environment; outbound messages/calls need an explicitly authorized test recipient. No test plan here executes a purchase, booking, message, account change or device action.

| Package | App | Concrete business profile and first unpassed check |
|---|---|---|
| `com.Hyatt.hyt` | Hyatt | hotel: Enter location/dates/occupancy and verify populated matching availability. |
| `com.MobileTicket` | 12306 | train: Enter origin/destination/date; verify matching trains and seat availability. |
| `com.amazon.mShop.android.shopping` | Amazon | retail: Enter a product query; verify matching populated search results. |
| `com.android.calendar` | Calendar | calendar: Create/edit one uniquely owned local event; verify dates, timezone and recurrence. |
| `com.android.camera2` | Camera | camera: Observe a real live preview without the cannot-connect dialog; correlate the exact provider session. |
| `com.android.contacts` | Contacts | contacts: Extend the verified local CRUD flow to Search UI, remaining permission/sync/error behavior and repeat/stability coverage. |
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
| `local.pocket4.fixture` | Pocket4 fixture | fixture: Source and two-round controls reviewed; exercise exact ambiguous-selector rejection and finish remaining identity/resource/release scope. |
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
  --output readiness-next.json
```

For later complete inventories, pass the new receipt to `--inventory`. The updater unions its launcher set with the immutable 45-App baseline; absent or disabled entries remain in the matrix, and new launchers get an unclassified checklist that cannot pass release scope until reviewed. A different epoch/version/UID invalidates old gate credit. A same-version APK replacement also resets all prior binary-specific gate credit.

Add hash-referenced scoped observations to `progress.json`; they can retain failed/blocked/pending gates but **cannot pass a gate**. Historical snapshot booleans and install/build/launch success cannot promote readiness.

Optional `--gate-reviews review.json` accepts only schema `pocket4-reviewed-app-gates-v1` with a `reviews` array. Each review needs a unique `id`, `reviewer`, `package`, `scope` (`scoped` or `whole_app_release`), `observed_at_utc`, exact `framework_epoch_sha256`, `version_code`, `uid`, `apk_sha256`, nonempty `evidence` containing bundle-relative `path` and `sha256`, and `checks` mapping known gate IDs to `passed/failed/blocked/pending`. The files must exist and match their hashes; the review must follow the current inventory and any newer retained failure cutoff. A passed `release_scope` additionally requires `scope=whole_app_release`, `all_features_reviewed=true`, `retained_failures_reconciled=true` and `unresolved_findings=[]`. These are explicit reviewer attestations backed by inspected evidence, not semantic proof extracted automatically from arbitrary documents. Every required gate must pass on the same exact binary before an App can qualify. This matrix retains the historical Camera preview review but rejects its current credit after the newer hardware-absence failure. Current scoped reviews pass Contacts edit/cleanup/UI/lifecycle, WebView UI/lifecycle, Clock observed UI/lifecycle, local Probe source-contract/UI/lifecycle and Editor core UI/lifecycle checks. The newer actual timer-expiry failure remains failed; cleanup does not erase it. The composite business checks remain open wherever Search, HTTPS, media or error coverage is still missing. No whole-App release gate passes; all 45 Apps remain in scope.

## Local validation and evidence limits

Four focused local integrity regressions passed; the current run is recorded in validation.json: actual inventory/45-entry preservation; rejection of incomplete/malformed/reordered/duplicate input and historical readiness booleans; union retention when a fixture disappears and a new launcher appears; and prevention of scoped/stale/mixed-APK review promotion. The tests' positive review objects are explicitly synthetic and never enter the delivered matrix. `validation.json` records this scope. No parallel owner's tests were rerun.

`SOURCE_MANIFEST.json` binds this bundle. Raw personal images, contact rows and account names are absent. `inputs/platform-observations.json` retains the original source hashes and selected facts; its source locators identify the retained receipts reviewed locally. Where this bundle contains an extract rather than the full original, that distinction remains explicit. Earlier evidence is not silently superseded or deleted.
