# Contacts03: persistence, search opening and UI deletion

The retained third run succeeded on the installed Contacts APK. It created one device-local test contact, edited its name, closed the owned task, opened a new task, searched the edited name, opened the matching result, and deleted the same record through the Contacts interface. All recorded owned phases use contact, raw-contact and name-data ID **6**. The terminal result records **12 inputs**, two normally closed tasks (**992, 993**), no pending effects and **zero Provider fallback cleanup calls**. The original empty raw-contact baseline returned, with zero owned tombstones.

The original second run remains **FAILED** with `REVIEWED_SNAPSHOT_CHANGED`: it completed editing, persistence and search input but stopped before opening the search result. It used one exact Provider fallback cleanup. That cleanup is not UI deletion evidence. The retained two observations have different pixel hashes while their full result/query/row/list binding and window context remain equal, excluding only connection-scoped accessibility window IDs.

## What changed

Only the private `open-search-result` branch uses one native `method=mouse` operation. It binds the current query, unique full leaf/row/list, durable owned record IDs, owned task/focus and two window/context/geometry observations. The native implementation derives the fresh node center; the controller supplies no coordinates. Native target and actual-target receipts are checked, and a fresh detail observation plus same-ID Provider readback remains necessary. Unknown effects cannot be replayed. Other inputs retain the original pointer path and original budgets: 240 seconds of work, 60 seconds of cleanup, 24 inputs, two owned launches and one created contact.

A separate private Trial method binds the current run's edited marker and all three originally claimed IDs for the delete menu. The prior shared Trial and helper were not modified. This is a controller correction and observed Contacts business evidence; no Contacts APK was replaced for this change.

## Evidence and privacy

`actual03-result-selected.json` and `actual02-result-selected.json` are **selected projections**, not the original remote bytes. Each names the original byte count and SHA256. The full originals remain private and unchanged. Existing account count/type projections, screenshot metadata and unneeded node geometry are omitted. Only the equality result of the private account comparison is published. Device-local test rows contain null account fields; they do not reveal existing accounts.

The five files in `source/`, three diffs, historical host-test declarations and preparation peers are byte-identical to their frozen inputs. The two original dependencies `verify_contact.py` and `ui_preflight05.py` contain a private account-topology contract and are therefore identified by their original hashes and sizes only. No executable redacted substitute is supplied. The `.txt` verifier excerpt is explicitly non-executable and contains only selected exact identity/owned-record/readback methods. Controller dependency pins remain the original pins.

The 10 historical host boundary cases exercised real private methods with retained nodes and controlled transport outcomes. They are not device business tests. Their test source is archived, but the private full observation fixture and two dependencies are withheld; this publication is not a self-contained rerunnable test environment. Preparation reports keep their original pre-execution state, while the later actual result records execution.

## Qualification boundary

The independent review supports the scoped `contacts.persist` decision for Root to assess. It does not edit the readiness matrix. General stability, complete data/permission behavior and release qualification remain pending or blocked; whole-app production readiness is not granted. This run does not prove an independently complete crash/ANR observation window or account synchronization. The unchanged installed Contacts and Provider identity was checked by the frozen execution path; broader runtime identity evidence is maintained separately.

No PNG, complete UI tree, raw account topology, process map, APK, request envelope or signing material is included. No device operation occurred while deriving this bundle.
