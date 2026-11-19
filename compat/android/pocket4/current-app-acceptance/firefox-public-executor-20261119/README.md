# Firefox public-page executor source candidate

This package prepares the public Firefox flow from the required39 r2 checklist.
The production entry is **HELD**. It cannot issue an Android command or a finite
application acceptance in this revision. A successor must independently bind
the actual controller, browser-session owner, current selectors and runtime
receipts before replacing the explicit hold. There is no configuration flag or
caller-supplied attestation that unlocks it.

## Prepared implementation

`firefox_protocol.py` specifies one ordered, bounded execution: admit an owned
session; open the Mozilla Manifesto; navigate the same tab to Mozilla History;
go back and forward; open and close a second owned tab; normally close the
owned task; reopen it independently; then clean up only the owned tabs and task.
Every observation binds the same admitted Main, UID, Android user, framework
epoch, selected APK, helper and session. Unknown outcomes stop dispatch without
retry or blind Android cleanup.

`firefox_adapter.py` contains the concrete calls to the existing source-bound
Flow launch, typed accessibility find/click/set-text, recorder and owned-task
cleanup paths. It verifies the recorded command, exact logical request and
scope, stdout binding, successful host retirement and existing Flow guards.
It retains the original Main/source/lease/action-lock boundaries. It does not
replace the old helper, selectors, source registries or required39 plan.

The production `execute`, adapter `admit`, and shared operation guard all first
raise `HELD_FIREFOX_CONTROLLER_AND_BROWSER_OWNER_NOT_SOURCE_BOUND`. Constructor
creation does not inspect a caller-provided browser owner. The remaining
transport functions are available for source review and offline controls;
their existence is not a current runtime capability claim.

`firefox_custody.py` adds a narrowly scoped streaming path for the exact selected
Firefox APK: version **160.0.1**, versionCode **2016196678**, **140689915 bytes**,
SHA-256 **283b19f8313e8ce6e8a913bb178ce4a79c5cecd82c49f821de7fafb068c73fcd**.
The existing generic helper reads whole bodies with a 128 MiB ceiling; the
selected Firefox body exceeds that ceiling. This implementation streams at
most 64 KiB per read, checks the complete hash and EOF under a deadline, holds
the original descriptor, and compares full file identity before and after,
including the independently reopened name. It does not raise the generic
ceiling or admit other package bodies. Existing helper APK custody remains on
the unchanged helper path. This package has not reread or rerun SDK tools on
the selected Firefox APK; its source qualification is inherited explicitly
from the fixed registry record in `SOURCE-BINDING.json`.

Host resource release has an explicit contract: only the literal `True` from
`release_host_resources()` is a release acknowledgment. False, None, other
truthy values and exceptions retain failure. Closing host resources does not
create Android cleanup credit.

## Fixed public pages

| Page | Exact URL | Exact visible heading required on Android |
| --- | --- | --- |
| Manifesto | https://www.mozilla.org/en-US/about/manifesto/ | The Mozilla Manifesto |
| History | https://www.mozilla.org/en-US/about/history/ | History of the Mozilla Project |

The coordinating reviewer separately opened both official web pages on
2026-11-19 and confirmed those headings. That read-only web observation is
recorded in `PUBLIC-PAGES.json`; it does not prove Android rendering, TLS
state, selector identity, page visibility or navigation.

## Remaining execution prerequisites

1. Bind the actual final Main, Firefox UID and Android user, framework epoch,
   current installed APK and helper custody, and actual engine mapping. The
   previous plan contains null runtime bindings; this package does not fill
   them with fixtures or guesses.
2. Supply and independently pin a real controller implementation with current
   phase scopes, lease, source guards and UI context. Reconcile the current
   host CLI cohort with the old typed consumer before any launch.
3. Supply and independently pin a browser-session/tab owner implementation.
   An Android task claim cannot establish browser tab ownership. The generic
   historical ActionRunner does not supply this capability. Reading existing
   user tabs or history is prohibited, including for initial discovery.
4. Bind reviewed selectors observed on this exact Firefox payload. This package
   contains no guessed resource IDs, coordinates or app UID and no history or
   tab-list route. Caller-authored JSON or a method returning true is not an
   admitted implementation or observation receipt.
5. In a later admitted revision, observe the complete public sequence, actual
   owned cleanup, common stability and data-preservation gates, and release
   review. A finite public case alone cannot make the whole app or all39
   production ready.

The original typed consumer expects `/usr/local/bin/android-app` SHA-256
`4823c1a6d2434a9d102b2b6dbc369dd0cf192e7fc0a31384a68dddb370d0a340` and
`/usr/local/libexec/android-digitalis-observe-helper` SHA-256
`76e9875d141f69976cbbafe469aa13439cf99c3214bc479a0c80cda740c8dcfa`.
Fresh bounded source reads observed, respectively,
`e775301b11960df8109f39ef1adfc662bebd8fc536414580c71c7aa0da263efe` and
`d1fc02bdbbd72c8e9ee440dbf81274662d60228a4e7ecc661484241d889d7bd4`.
`ORIGINS.json` preserves both mismatches. No live file or old expected pin was
changed, and current source-cohort compatibility remains unqualified.

The exact historical helper APK and its already-existing disassembly establish
the find response fields `ok`, `count`, `matches`, and `window_context`.
`ORIGINS.json` binds that source chain. Historical helper identity and wire
schema are not observations of the currently installed helper.

## Actual host controls and reproduction

The final source revision passed **35** host-only controls: the original32 plus
three targeted controls for the hard production hold, exact resource release
acknowledgment and loss of protocol credit on unacknowledged release. The
suite includes real temporary-file streaming/hash/identity checks and exact
existing parent-recorder fixtures. It performs zero Android, download or SDK
operations. Its test doubles cannot issue finite application credit.

Run from this directory with the normal Python module path:

```sh
python3 -B -m unittest -v test_firefox.py
```

The actual interpreter, timestamps, exit status, before/after source hashes and
unaltered raw stdout/stderr are in `validation-r2/EXECUTION.json`. `VALIDATION.json`
binds that execution and the preserved original32 evidence. The original32
source snapshots and original metadata are in `history-32-controls-r1`; its raw
logs remain at `validation-r1`. The snapshots are historical source records,
not a newly executed second package. `admission-and-release-r2.patch` shows the
narrow revision from those snapshots.

For CI, include `originals/business_ui_entry.py`: three controls import that
exact source without invoking its main entry. No Android service, SDK,
production controller or browser-session provider is needed for these offline
controls. The documented normal module invocation was tested; isolated `-I`
direct-script invocation is not claimed.

## Scope and publication

`CURRENT-SOURCE-SUCCESSOR.json` is an additive source status. It does not rewrite
the r2 PLAN, the CP3A source adapter, the source state or current registry. The
scope remains42 selected,39 required and only the existing TextNow, TextFree
and Uber exemptions. It does not recalculate the old32 missing executors as
passed, and grants no installed, runtime, native compatibility, whole-app
business, all39 latest or production credit. Publication alone does not
authorize execution or lift the hard hold.

`MANIFEST.json` and `FILES.sha256` fix the package contents. Empty stdout logs
remain genuinely zero bytes and are listed explicitly; no placeholder
newline was inserted. The compressed historical export is a binary source
evidence file, not executable app input. Other original files are public
source and provenance observations, retained without modification.
