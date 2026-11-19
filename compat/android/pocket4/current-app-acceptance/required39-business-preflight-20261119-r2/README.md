# Required39 business preflight and plans

This independent, host-only program turns already verified **source metadata** into a reviewable 39-package plan. It does not run Android or any existing application runner, open APK/image bodies, inspect user data, resolve credentials, or follow embedded origin paths. A successful command produces `PLAN_PREPARED_RUNTIME_BLOCKED`, never a business or production pass.

## Fixed scope and actual findings

The accepted source is the Beike successor `CURRENT-SOURCE-STATE.json`, 157891 bytes, SHA-256 `4d25fc0aafd5668cc3f0c31be157bc617732902976aad821333a02de84ff9bf7`. Its registry and freshness bytes are checked against the actual successor receipt and the state's own references. This includes Beike 3.06.80. The fixed United payload is still 4.2.103; independent metadata observed 4.2.104 and remains an explicit payload-qualification gate. This program cannot silently adopt another successor: its ten input pins are fixed in `preflight.py`.

- 39 required packages: 10 system and 29 non-system; only TextNow, TextFree and Uber are exempt. The microG vending companion stays outside the 39 count.
- The historical canonical45 has 38 of the required packages. Firefox is absent there, so this directory adds a public-only checklist without changing canonical45.
- Thirteen preparation references cover limited source workflows for **seven packages**, six system apps and IHG. **32 packages still lack a selected business executor.** This is a bounded conclusion about the inspected current selector, not a whole-host search claim.
- Calendar, Camera, Contacts, Clock and DocumentsUI have five confirmed target APK hash mismatches against the current coherent GSI. Equal version codes do not make these source profiles current.
- Gallery's official target hash matches, but its historical entry permits standalone APK installation. The selected source-state prohibits that path; an image-installed custody/verification adapter still needs review. Camera also retains an old CP2A MediaProvider binding. Calendar/Contacts/ExternalStorage/MediaProvider bindings must be checked against the current coherent GSI.
- All 39 actual Main/UID/user/framework epoch, installed APK identity, engine mapping, helper custody, owned task/fixture and UI selector bindings remain explicit null/unresolved gates. No guessed historical UID is admitted.
- The complete original `required_before_installation` map is preserved in the plan. Meituan's official-signer and existing-userdata migration remains `PENDING`, with `signer_migration_qualified=false`. The three retained Play inputs keep their original `UNAVAILABLE_COUNTRY` restrictions, historical metadata expiry and unqualified activation state. No migration, uninstall, data clearing or userdata generation change is admitted.

The source audit is bounded to 17 complete metadata documents and 29 pinned source files inspected without importing them. The evidence snapshot retains original source-document pins and parsed content; it does not claim their raw source-host bytes were reopened by this generator.

## Use and verification

Run only on the host, with a new output filename in an existing directory:

```sh
python3 -B preflight.py --out /absolute/path/to/new-plan.json
python3 -B -m unittest -v test_preflight.py
```

The loader opens only the ten fixed JSON basenames, refuses symlinks, requires exact bounded sizes and full SHA-256 before parsing, rejects duplicate JSON keys/non-finite numbers, and compares metadata F9 bookends before creating output. It does not traverse any paths recorded inside source evidence. Output uses exclusive creation, so existing source/evidence/plan files are never overwritten. No external process, network library or runtime module is used by the generator.

Semantic checks independently verify the exact 39/10/29 scope, original three exemptions, 29 plus companion registry, all accepted source/signature records, state-to-registry/freshness/actual-result links, 13 preparation references, seven-package mapping, five mismatches, all common gates and the pending United update. Runtime/business/production values remain false throughout. The historical audit's `counts.execution_ready` is an integer zero; this exact source field is accepted as a count, while per-package and output readiness fields must be boolean false.

`PLAN.json` is the actual local output. `VALIDATION.json` records the eleven accepted host-only contract tests and actual CLI outcome. The original ten controls remain unchanged; one additional control rejects omitted installation prerequisites, removed Meituan migration gates, changed retained-Play country restrictions or expiry, and promoted migration state. Tests include exact rejection reasons, so an unrelated earlier failure cannot make a negative control pass. They also cover changed pins, symlinks, duplicate keys, missing/duplicate packages, added exemptions, unverified signatures, broken source links, nested acceptance claims, selector-count promotion, erased target mismatches, unapproved Firefox actions/URLs, fabricated runtime bindings, omitted common gates and output overwrite refusal. No SDK, Android, VM, install or application execution occurred. The earlier r1 plan, validation and all ten source snapshots are retained unchanged.

## Firefox additive checklist

The planned public pages are Mozilla's [Manifesto](https://www.mozilla.org/en-US/about/manifesto/) and [History](https://www.mozilla.org/en-US/about/history/), with exact URL and visible heading checks. A future source-bound executor must first admit a controlled owned test session without opening existing user tabs or history. It then navigates the two pages in one owned tab, checks Back and Forward, opens and closes a second owned tab, normally closes only the owned task, independently reopens it and observes the expected controlled state. Unknown UI or ownership is a stop condition.

There is no download: the original canonical45 grants no Firefox download test scope. Login, form submission, outbound messages, payments/purchases, user-history inspection, user-tab enumeration, clear-data and force-stop are also excluded. The checklist is reviewable preparation only: `driver_implemented=false`, `execution_authorized=false`, and the 32 missing-executor count is unchanged. Rendering, failure cases, account-related scope where applicable, long-run stability and whole-app release review remain unexecuted.

## Per-package compact matrix

Every row below still requires all six original common gates: identity, lifecycle, stability, data/permissions preservation, complete release scope and UI observation. Existing finite source cases are not current runtime passes.

| Package | Fixed source version | Current selected workflow source | Concrete next gap |
|---|---|---|---|
| `com.Hyatt.hyt` | 26.11.1 | No selected business executor; hotel | Implement/run profile plus all common gates |
| `com.MobileTicket` | 5.9.6.8 | No selected business executor; train | Implement/run profile plus all common gates |
| `com.amazon.mShop.android.shopping` | 32.20.2.100 | No selected business executor; retail | Implement/run profile plus all common gates |
| `com.android.calendar` | 17 | calendar_core (Core21); calendar_reminder (Reminder22) | GSI target identity rebind |
| `com.android.camera2` | 2.0.002 | one-photo persistence; photo display lease wrapper | GSI target identity rebind |
| `com.android.contacts` | 1.7.34 | contacts_search (Search03) | GSI target identity rebind |
| `com.android.deskclock` | 17 | clock_timer (reviewed Timer15 readback successor); expiry06; alarm04 | GSI target identity rebind |
| `com.android.dialer` | 23.0 | No selected business executor; dialer | Implement/run profile plus all common gates |
| `com.android.documentsui` | 17 | SAF11 nine gates; Features10 plus owned search/sort fourteen gates | GSI target identity rebind |
| `com.android.gallery3d` | 1.1.40030 | current ART/source verification (dependency only); eight image-rotation gates; silent video + midpoint seek + two owned-album observations | Image-installed custody adapter; old standalone install forbidden |
| `com.android.messaging` | 1.0.001 | No selected business executor; messaging | Implement/run profile plus all common gates |
| `com.android.quicksearchbox` | 17 | No selected business executor; search | Implement/run profile plus all common gates |
| `com.android.settings` | 17 | No selected business executor; settings | Implement/run profile plus all common gates |
| `com.bestbuy.android` | 26.11.10 | No selected business executor; retail | Implement/run profile plus all common gates |
| `com.ehi.national.mobile` | 6.16.0.9403 | No selected business executor; rental | Implement/run profile plus all common gates |
| `com.google.android.gms` | 0.3.18.252432 | No selected business executor; gms | Implement/run profile plus all common gates |
| `com.hertz.android.digital` | 5.8.0 | No selected business executor; rental | Implement/run profile plus all common gates |
| `com.hilton.android.hhonors` | 2026.11.3 | No selected business executor; hotel | Implement/run profile plus all common gates |
| `com.ihg.apps.android` | 5.111.1 | ihg_london | Only destination text readback, no hotel result/details |
| `com.jingdong.app.mall` | 16.1.50 | No selected business executor; retail | Implement/run profile plus all common gates |
| `com.lianjia.beike` | 3.06.80 | No selected business executor; housing | Implement/run profile plus all common gates |
| `com.marriott.mrt` | 10.82.0 | No selected business executor; hotel | Implement/run profile plus all common gates |
| `com.rytong.airchina` | 7.53.4 | No selected business executor; flight | Implement/run profile plus all common gates |
| `com.rytong.ceair` | 9.5.16 | No selected business executor; flight | Implement/run profile plus all common gates |
| `com.sankuai.meituan.takeoutnew` | 8.86.4 | No selected business executor; delivery | Implement/run profile plus all common gates |
| `com.sdu.didi.psnger` | 8.0.20 | No selected business executor; ride | Implement/run profile plus all common gates |
| `com.ss.android.ugc.aweme` | 41.2.0 | No selected business executor; video | Implement/run profile plus all common gates |
| `com.szzc` | 9.6.3 | No selected business executor; rental | Implement/run profile plus all common gates |
| `com.taobao.taobao` | 10.69.0 | No selected business executor; retail | Implement/run profile plus all common gates |
| `com.tencent.mm` | 8.0.80 | No selected business executor; messaging | Implement/run profile plus all common gates |
| `com.united.mobile.android` | 4.2.103 | No selected business executor; flight | Implement/run profile plus all common gates |
| `com.xunmeng.pinduoduo` | 8.32.0 | No selected business executor; retail | Implement/run profile plus all common gates |
| `com.zhubajie.client` | 9.5.20 | No selected business executor; services | Implement/run profile plus all common gates |
| `com.zillow.android.streeteasy` | 2026.47.0 | No selected business executor; housing | Implement/run profile plus all common gates |
| `ctrip.android.view` | 8.97.6 | No selected business executor; travel | Implement/run profile plus all common gates |
| `jp.co.ana.android.tabidachi` | 7.7.1 | No selected business executor; flight | Implement/run profile plus all common gates |
| `org.fcitx.fcitx5.android` | 0.1.3-0-g048f581c | No selected business executor; ime | Implement/run profile plus all common gates |
| `org.mozilla.firefox` | 160.0.1 | No selected business executor; Firefox checklist missing in original canonical45 | New checklist only; UI executor absent |
| `tv.danmaku.bili` | 9.20.0 | No selected business executor; video | Implement/run profile plus all common gates |

## Review boundary

No historical canonical45, selection13 or frozen runner was edited. Existing case semantics and metadata references are reused; a second runtime framework is not introduced. The actual IHG source case only reaches London destination text/readback and owned cleanup; it does not establish populated availability, hotel details, rates or account behavior. Clock's reviewed timer core and independent alarm/expiry preparations remain finite scopes. Silent Gallery video is not audio qualification. Source-ready, launch-ready and business-accepted are distinct gates, and this output admits none of the latter two.
