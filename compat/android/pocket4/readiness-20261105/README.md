# Pocket4: all 45 tracked Apps, current evidence and unpassed gates

## Current result

The complete 2026-11-05 05:46:49.686297 UTC inventory contains **186 installed packages, 45 launcher packages/components, and 44 third-party packages**. All original **45 tracked Apps** remain in scope. No new launcher was found. **0/45 whole Apps are production ready.** System Apps, the Thread demo, GMS, WebView shell and QA fixtures remain explicit entries. PackageManager's third-party count is a different set from the 45 launcher set and from the review-purpose categories below.

`readiness-matrix.json` is the generated machine-readable result. `app-gates.json` defines exact per-profile checks and every package-to-profile assignment. Each App row carries its original version/status, historical evidence pointers, current UID/version, progress observations, gate states and the complete list of unpassed gates. The full historical inputs remain unchanged under `inputs/`.

## Concrete remaining blockers

| App / workstream | Latest evidence and next required result |
|---|---|
| Camera | Exact release08 SHA `0218041bc46f49c0c9622196e2a3610c641e0cc8f12386f23cdd88dc3a3ce18e` installed once; UID/CE/DE/permissions identity preserved. Acceptance then observed the cannot-connect dialog: 1 launch, **0 shutters**, 1 owned close. CameraService exposes **0 cameras** and the provider manager is waiting for its physical source. The 05:33:37 source-loss event predates the update/acceptance; the new APK is not established as its cause. Restore/diagnose availability, then qualify preview, real photo output, persistence, video and recovery. |
| Contacts | Latest owned launch reached an observation mismatch. **0 Create clicks, field entries, saves, deletes or account actions**; task 886 was normally removed and the empty database/account topology were preserved. This is an **UI observation gate block**, not proof of an App crash or failed contact business behavior. Diagnose the saved observation before another admitted step. |
| Bilibili | The newer retained video transition opened the intended course page and closed only its owned task, but retained buffering and no verified advancing frames/audio. Keep the earlier Nov4 scoped visual result as history; do not transfer it into a current whole-App pass. |
| Marriott / China Eastern | Retained Nov4 current-R16 evidence records native SIG11 with an observed virtual proc-fd mismatch / native SIGILL respectively. Corrected-runtime and actual business requalification remain absent. |
| Meituan / Beike | Retained evidence records startup self-exit / a blank login router. Stable merchant/item or listing detail completion remains unverified. |
| Remaining Apps | Launch/onboarding or older guest-core observations do not close the package-specific checks listed below. Login, external service, controlled call/message peer and hardware prerequisites remain explicit. |
| Native candidate07 | Job `1a1aa09c5d6-fc05-3bd3` built the engine and host suite successfully and restored the original source projection. The reviewed later host-bound request and Android template contain **no actual passing full-host/Android result**. Counts in those plans are requirements, not new test results. |
| ART | Normal-projection draft is source-only/uncompiled. Matching Rust/full ART/paired APEX/lifecycle gates remain open; no candidate07 build result is substituted for these. |
| LMKD / Owner | Actual Owner08 stopped before ACTIVE and did not qualify installed operation or pressure survival. The mount mechanism recorded expected syscalls but failed its parent protocol/cleanup qualification; revision03's 15 local collection controls are not a namespace/Owner/pressure pass. Producer09/init ABI3 requests still need their matching actual receipts in this evidence set. |

Platform state is a read-only snapshot of retained files from the parallel owner's workspace. Another owner may have advanced since that snapshot. This bundle starts or repeats none of its builds/tests. Platform candidate progress is never treated as an App pass or proof of causality.

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
| `com.android.contacts` | Contacts | contacts: Create and edit one uniquely owned contact fixture with exact field readback. |
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
| `local.pocket4.fixture` | Pocket4 fixture | fixture: Identify and review the exact fixture source/APK and its intended shipping/test purpose. |
| `org.chromium.webview_shell` | WebView shell | webview: Load controlled local/HTTPS fixtures and verify layout, text, images and JavaScript. |
| `org.droidloom.qa.editorcontract` | Editor contract QA | editor: Verify focus, Unicode composition, exact text readback, selection and deletion in the editor contract. |
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
  --output readiness-next.json
```

For later complete inventories, pass the new receipt to `--inventory`. The updater unions its launcher set with the immutable 45-App baseline; absent or disabled entries remain in the matrix, and new launchers get an unclassified checklist that cannot pass release scope until reviewed. A different epoch/version/UID invalidates old gate credit. A same-version APK replacement also resets all prior binary-specific gate credit.

Add hash-referenced scoped observations to `progress.json`; they can retain failed/blocked/pending gates but **cannot pass a gate**. Historical snapshot booleans and install/build/launch success cannot promote readiness.

Optional `--gate-reviews review.json` accepts only schema `pocket4-reviewed-app-gates-v1` with a `reviews` array. Each review needs a unique `id`, `reviewer`, `package`, `scope` (`scoped` or `whole_app_release`), `observed_at_utc`, exact `framework_epoch_sha256`, `version_code`, `uid`, `apk_sha256`, nonempty `evidence` containing bundle-relative `path` and `sha256`, and `checks` mapping known gate IDs to `passed/failed/blocked/pending`. The files must exist and match their hashes; the review must follow the current inventory and any newer retained failure cutoff. A passed `release_scope` additionally requires `scope=whole_app_release`, `all_features_reviewed=true`, `retained_failures_reconciled=true` and `unresolved_findings=[]`. These are explicit reviewer attestations backed by inspected evidence, not semantic proof extracted automatically from arbitrary documents. Every required gate must pass on the same exact binary before an App can qualify. This delivered matrix contains **no passing gate review**.

## Local validation and evidence limits

Four focused local integrity regressions passed in 0.014 seconds: actual inventory/45-entry preservation; rejection of incomplete/malformed/reordered/duplicate input and historical readiness booleans; union retention when a fixture disappears and a new launcher appears; and prevention of scoped/stale/mixed-APK review promotion. The tests' positive review objects are explicitly synthetic and never enter the delivered matrix. `validation.json` records this scope. No parallel owner's tests were rerun.

`SOURCE_MANIFEST.json` binds this bundle. Raw personal images, contact rows and account names are absent. `inputs/platform-observations.json` retains the original source hashes and selected facts; its source locators identify the retained receipts reviewed locally. Where this bundle contains an extract rather than the full original, that distinction remains explicit. Earlier evidence is not silently superseded or deleted.
