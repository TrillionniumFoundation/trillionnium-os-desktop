# Production lifecycle and selected application leaf integration

This is a source and custody audit, not an Android execution result. All 42 whole-application acceptances remain pending; `runtime_qualified` and `production_ready` remain false. No shared source, selected preparation, registry, or `CONTINUATION_CURRENT.json` was modified.

## Actual lifecycle supported by the new entry

The current `droidloom-supervisor` daemon owns `ActiveCell { spec_path, spec, cell: DevelopmentCell }`. Its start path calls `recover_development_cell` and `start_development_cell`; its poll and stop paths operate that same owned development cell. The new `ObserveRuntime`, `InspectApplication`, and `OpenBrowser` handlers first authorize the socket peer against that active cell, then create `LiveApplicationProbe`. Consequently the new runtime observation explicitly reports `lifecycle: development`. It neither constructs nor serializes production admission.

The application command transport now binds the existing cell owner and framework through held process/PIDFD and namespace descriptors and owns only its new command cgroup. It must never adopt an arbitrary process into `OwnedNamespaceChild`: that helper's retirement semantics can terminate the Android PID namespace. Application command cleanup cannot invoke production-tree `retire` or `reap_init` either.

The production sources inspected expose two earlier lifecycle stages. `prepare_admitted_user_namespace(HostAdmission)` produces an owned mapped, parked child while retaining and revalidating the opaque host/identity authority. `IsolatedNamespaces::witness()` revalidates keeper/PID1 custody before lending an `OwnedNamespaceWitness`; `verify_live_admission` revalidates the admission against that witness. Those stages explicitly exclude Android execution and do not constitute a daemon-owned, running Android `ProductionCell`. The local inspection found no valid production active-Main adapter that could simply be substituted for `DevelopmentCell` in this entry.

### Minimum genuine production integration

The production lifecycle owner must first retain the actual opaque admission, subordinate-ID lease, keeper/PID1 custody, admitted mounts/devices/process filesystem, owned cgroup, and protected data ownership while starting the real Android cohort. That owner must then lend a scoped runtime witness to application observations; accepting a caller-provided PID, JSON admission boolean, or detached namespace witness is insufficient. The existing daemon authorization, poll, stop, error retention, and retirement paths must operate the real owner before a production branch can be added to `ActiveCell` and the application probe.

The adapter should preserve the already implemented command cgroup ownership and FD-bound namespace entry. It must bind the framework observation to the same production owner and current source/Main generation, without retiring the cell as a command cleanup action. Both the applications client and daemon need deployment together; an older daemon that does not return `runtime_observation` is rejected by the new client.

Tests for that future integration require a genuinely admitted production owner: rejected or expired admission before any Android operation; failed-start ownership retention and retirement; owner or framework exit/PID reuse; same-generation observation; cross-user denial; preservation of the actual data backing; and command descendants retiring without affecting PID1. None of those production tests is claimed by this capsule. If a production lifecycle enum value is added later, every per-application observation must bind that lifecycle as well as its physical epoch; the current enum has only the actual Development variant.

## Exact selected preparation scope

The read at 15:56:41Z bound CURRENT SHA `2090bc8e1bc1785fb78f29e50dadfc13d53dff76e03afd85c8737a307853a3a3`. A later read at 16:23:40Z bound CURRENT SHA `29b05aa1fb2a2eff5c4bf0dcab945028d57a2ccf1eb412c255b7f2e56d1290e2`, 287867 bytes. Both selected the same preparation manifest, 12088 bytes, SHA `cc06d0fbccb1f3ab5ddaa70946ac62eca2c0254752c0653194a2506318cda692`, at `/home/alex/work/pocket4-android-final/qualification/application-preparation-selection-20261108-8b88-r3.json`. Each read was unchanged after reading; neither snapshot freezes future owner progress.

The 13 selected preparations were read and checked against their exact reference bytes and SHA. Entry, profile, and transport source readback also checked each referenced source against its own pin. Historical source dependencies found inside those frozen references are provenance, not additional selected preparations or runtime passes.

| Selected preparation family | Actual entry and scope | Selected application |
| --- | --- | --- |
| `business-system-cases-runtime-inputs-20261108-8b88-r2` | `system_entry.py`: `contacts_search` and `calendar_core` | Contacts, Calendar |
| `calendar-reminder-runtime-inputs-20261108-8b88-r2` | `system_entry.py`: `calendar_reminder`, owned local reminder | Calendar |
| `camera-app-photo-preparation-resume-20261107-r4` | `camera_entry.py`: original one-photo case, two normal launches and persistence | Camera |
| `camera-photo-display-preparation-resume-20261107-r4` | `photo_display_wrapper.py`: original display lease/capture wrapper | Camera |
| `clock-remaining-runtime-inputs-20261108-8b88-r2` | `clock_entry.py`: `timer15`, `expiry06`, `alarm04` | DeskClock |
| `business-app-runtime-inputs-20261108-8b88-r2` | `app_entry.py`: `clock_timer` and public `ihg_london` | DeskClock, IHG |
| `documents-saf11-runtime-inputs-20261108-8b88-r2` | `documents_entry.py`: original nine scoped SAF gates | DocumentsUI |
| `documents-search-sort-runtime-inputs-20261108-8b88-r2` | `documents_entry.py`: original twelve features plus owned search and visible sort | DocumentsUI |
| `gallery-new-runtime-preparation-20261107-r7` | `gallery_current_entry.py`: current installation/source closure | Gallery |
| `gallery-rotation-current-preparation-20261107-r7` | `gallery_rotation_entry.py`: one owned JPEG rotation | Gallery |
| `gallery-video-current-preparation-20261107-r7` | `video_entry.py`: owned silent-video case | Gallery |
| `gallery-seek-current-preparation-20261107-r6` | `video_entry.py`: video and seek | Gallery |
| `gallery-album-current-preparation-20261107-r6` | `video_entry.py`: video, seek and owned album | Gallery |

These preparations cover partial routes for seven distinct selected applications. The other 34 non-Firefox selected applications have no route in this selection. This does not assert that no other historical work exists elsewhere. Firefox is the separate new partial implicit-HTTPS entry. No preparation, installation path, or partial case satisfies the six common gates or a complete application contract by itself.

The source-bound entries take an exact `--preparation` plus `--expect-preparation-sha256`. Identity and plan modes require new independently pinned requests and fresh Main/support/baseline evidence. Execute accepts only the entry's exact prepared plan shape: system cases use `{"base_plan": <file pin>}`; Camera consumes the prepared plan itself and checks its `source_preparation`; Clock, Documents and the business-app coordinator use `{"plan": <file pin>}`; Gallery uses its exact schema plus baseline, qualification, installation, and output references. The Camera display wrapper uses its separately pinned input schema. The precise existing shape must be preserved rather than translating every leaf to one invented generic request.

## Reuse boundary and remaining concrete blockers

The existing leaf transport already has a different, source-bound ownership contract. `app_common.py` pins `business_scope.py` and `BusinessBaseline`, creates `HeldTarget` from the admitted baseline, preserves per-step evidence, and checks held source/APK references. System/Camera wrappers narrowly adapt the frozen seven-FD `BoundArun`. Clock/Documents preserve one open-file-description action lock, absolute business/cleanup leases, protected state, exact UI-window ownership and bounded private image channels. Gallery also binds its current installation and owned media. The new 64 KiB command output bound and 20-second command deadline cannot replace screenshot, media, or long case transports without losing those original contracts.

The new Rust transport can be reused for current PM UID/version/full APK observations and specifically implemented fixed command operations. A safe leaf adapter must continue to call the original leaf's authoritative baseline/lease/evidence and cleanup owner, then adopt an explicitly reviewed current source/identity contract. Merely feeding the new observation JSON to an old leaf does not satisfy those contracts. There is no generic arbitrary-command endpoint in the new daemon.

The selected non-Gallery profile sources still contain exact earlier APK/UID expectations. For example Calendar pins the older `c8a9d40d...` APK and UID 10061, and DeskClock pins `433ff501...` and UID 10063. The latest CURRENT separately names signed QPR1 port candidates Calendar SHA `8d3ca352655a27c25e9c0da12edd2fcd18bf26816fc53d04a209cf7ff7717b9f`, 2672653 bytes, and DeskClock SHA `e8b7e2d5e90b2ec4100bd8b06403c659d4a86c9f29e45bb6b06363aed2f1f30a`, 7821343 bytes. The old leaf identity checker requires equality with its expectation. Therefore current APK adoption requires an explicit source/profile successor and new observed identities; silently changing or guessing the UID is not valid. The Gallery migration has its own current host-artifact contract and cannot be treated as an unchanged legacy profile.

The common registry pinned by the selected `app_common.py` is still the original SHA `441289f9c04b46f38e1dd6e19f23ec6e4c6729b6a6f814cab81c0ae6fbbb1e78`. Firefox's independent registry successor SHA `0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8` is not silently installed over that shared pin. Coordinated adoption must preserve the old contracts and explicitly update all source-bound references.

Other remaining conditions are actual coherent Android/Main readiness; deployed same-version daemon/client; supported delegation of the invocation cgroup; installed current official artifacts with independent signer verification; authorized account/environment coverage where the application contract requires it; and all common/UI/business gates. Meituan's signer migration remains blocked and its user data must be retained. No calls, messages, bookings, purchases, or account actions were performed by this audit.

## Common blocker closed by the accompanying R3 source

Before R3 the complete dispatch could perform repeated requests after runtime loss and had no single initial live generation observation. R3 adds one read-only `ObserveRuntime`, rejects an unavailable or mismatching precondition before the first package, and makes loss of transport or generation sticky. A package-specific failure performs only a fresh read-only runtime check; the failed application operation is never retried. Once invalidated, later application operations stop and every selected row is blocked. Earlier observations remain diagnostic evidence, while all partial/unsupported credit is withheld. Accepted count remains zero and all gate execution stays pending.

Actual normal tests passed for these exact source bytes: 14 supervisor-focused tests, 36 application library tests, and three CLI tests. The independent same-file harness passed 29 tests, with the two explicitly root-only host controls ignored. A real Unix-socket CLI negative control received exactly one `observe_runtime` request, made zero package calls, returned 42 blocked rows and exit 1, and removed its owned temporary fixture. It used a clearly synthetic Main file and no Android process. Those tests close the scheduling/source defect; they do not close any application runtime gate.
