# Independent review of the original-b05 corrective collector

Reviewer: `/root/app_history`. This review is local and read-only. It did not
execute the candidate, APK tools, Main queries, installs, lifecycle commands or
Git writes. It does not authorize the agent to submit a remote job.

## Scope and result

No new static blocker was found in the four supplied diffs, the changed
collector functions, full tool loop and final resource/receipt gates. The
reviewed worker is 62,604 bytes, SHA
`b4d27e1364feb28cab6634c77ed764e15359720025192117ecc8cb84d4391e1a`;
the exact request is 102,353 bytes, SHA
`d11a943e2ea28aba760247a10245807eab20db95a99c268507d427867b8e163b`.

All 14 listed source/review/input files were independently checked against
`SOURCE_REVIEW.json`. The exact process request contains the reviewed stager
and three staged files verbatim. An independent AST source comparison
confirmed that all 15 named original tool, file-reader, signature, XML,
dependency/layout binding and runner definitions remain byte-for-byte equal
to the previously reviewed official two-package comparison source. The
existing owned-lifetime functions are not replaced by the new worker gate.

## Important behavior

The request is a new complete corrective audit of the four original b05
packages: `com.MobileTicket`, `com.amazon.mShop.android.shopping`,
`com.android.calendar`, and `com.android.camera2`. It requires the six original
APKs, exactly 341,931,165 logical bytes. The old failed result is pinned, and
each original UID, version code, code path, data identity, PM signer record
and complete APK path/size/hash/full-stat set must equal the actual pinned
47-package scope before the new observation proceeds. The two-package
diagnostic cannot qualify as the full batch.

The official AAPT2 remains separately bound to its exact actual host proof and
seven-file system dependency graph. The original nineteen-file legacy graph
and original AAPT XML reader/signature verifier remain bound. No private
library search exception, LD override, stub, or tool-path rewrite is added.
The controlled RUNPATH layout is checked initially, before and after each of
the 18 primary commands, and finally: 38 complete observations. Every spawn
retains the explicit remaining-deadline check after its layout verification.

Each of the six APKs receives exactly three primary commands: original
signature verification, official badging, original XML manifest reading.
All 18 must finish normally with complete captured streams. Official badging
stderr must actually be empty. Held APK bytes/full stat/path are verified
before and after tools; current app data identities and runtime are checked
again. The new status cannot pass on a partial list, a skipped split, or only
the Calendar/Fcitx diagnostic.

## SDK format fix

The independently read actual official badging outputs contain
`minSdkVersion:'37'` for Calendar and `minSdkVersion:'23'` for Fcitx. Their
direct `uses-sdk` XML attributes are respectively `0x25` and `0x17`; target
values are 34 and 36. The old parser only looked for `sdkVersion:` and
therefore emitted null for the new tool's explicit minimum-SDK spelling.

The new parser combines both minimum-SDK aliases in one cardinality check,
then requires one whole quoted line. Duplicate same-name lines, both aliases
even with equal values, conflicting values, trailing garbage, an extra quoted
value and an empty present value all reject. A genuinely absent line remains
unknown (`None`), not a manufactured SDK. No minimum-less-than-target rule is
invented; Calendar's actual 37/34 is retained unchanged. The existing local
control artifact records the two actual badging/XML comparisons and seven
negative controls. This reviewer did not rerun those controls or an APK tool.

## Acceptance limits

The on-host intermediate result is not sufficient. Final original stdout,
authoritative durable terminal, all child joins, released locks, directory
closure, final observation-FD retirement, whole-process descriptor check and
the existing owned-parent lifetime gate must jointly pass. Late receipt or
FD failures continue to clear `corrective_audit_complete`; no retry follows.

The old b05 failed job, original request and stopped gate remain unchanged.
Only a separately accepted actual full corrective result could be used by a
new explicit audit continuation. It must not reclassify the old failure or
advance it merely because this source passed review. Neither badging nor
this batch proves complete resource-table health, effective permission grants,
business behavior, all 45-app coverage, production readiness or cleanup
eligibility.
