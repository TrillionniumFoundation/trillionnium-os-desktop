# Actual publication rejection: foreground evidence only

The real publisher job `1a1b1f2e015-fc05-7ba9` ended durable failed / exit 1, with complete 582-byte stdout and empty stderr. Its only reported error is `FOREGROUND_MUST_STILL_BE_BILI`. It reports `publication_attempted=false`, `outcome_unknown=false`, zero UI/instrumentation/install/grant actions, and the original action outcome remains UNKNOWN. This failed proof attempt must not be repeated or treated as a published reconciliation.

Exact original metadata is retained under `publish-existing-r2/actual/`:

- stdout SHA-256 `6018ef68e5fc95822137d56b2bfe9f8ec7cfe805988e9a4df434f2903cade3ab`;
- terminal, 726 bytes, SHA-256 `b1211031571b1aab3d0d65a8afe9fb0ebf059cd41769f8d25856556454ce660f`.

## The predicate is valid

The actual frozen `helper/qa_adapter.py` (29,378 bytes / `ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c`), `Session.foreground`, lines 250–263, evaluates:

```python
require(value['package'] == self.qa.PACKAGE, 'FOREGROUND_MUST_STILL_BE_BILI')
```

Here `self.qa.PACKAGE` is `com.lianjia.beike`. The old BILI wording is a retained label, not the predicate's target. Changing that label would not resolve the actual rejection. The prior `android_backend.foreground` function must already have parsed exactly one unique `mCurrentFocus` window token/package/activity for this particular error to occur. Thus the rejected observation had a parsed package different from Beike; its exact name is not present in the publisher's error output.

The original backend intentionally discards full `dumpsys window displays` output. During this private foreground operation, `Flow.bind` uses its private transport branch, which records command SHA, output lengths/hashes, return code and post-lease/post-guard transport evidence but does not create a persisted raw window dump. The helper rejects before returning its compact target scope. We must not manufacture the missing historical foreground package from an earlier successful inspection or from a later current observation.

## Minimal fixed host read

`read_failed_publication_step_r1.py` reads only the settled failed proof directory:

`/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb/steps/owned-postcondition-close-01`

The expected 26 files follow directly from the frozen publisher's order: intent and held binding; three recorded readonly commands with intent/result/stdout/stderr; four transports with intent/command-result/verified-result. Those commands are helper UID lookup, helper APK path lookup, task-stack lookup, and then the private foreground query. The original package equality rejection occurs after the first three have returned and the fourth has been parsed.

The reader requires exactly that file set, verifies source/request/scope identity, reuses the already reviewed pure command verifiers, and parses only task 876 through the exact pinned original pure task parser. It verifies all recorded children and the fourth private transport are complete and stable. It retains the original 26 raw files in a new private host bundle, never exports full window text, and separately requires the original close reconciliation file to remain absent. The safe result includes only helper UID/code path, task 876 metadata, command/transport hashes and limits, plus an explicit UNKNOWN for the discarded historical foreground package.

No current Main process is inspected, no guard or lock is acquired, no namespace is entered, and no Android command is run. Input files are no-follow, root-private, bounded, read with before/after stat and path checks and fully reread. Only reader-owned descriptors are closed, followed by complete process FD-identity checks. A successful reader result would prove historical evidence retention and interpretation, not current foreground identity.

## A later current snapshot needs a separate coordinated window

After root reviews the actual host-read result, the smallest useful current observation is an independent readonly step under the original exact successor/held-R5/App identity and original action/flow leases:

1. Reacquire the fixed R5 authority and validate installed helper UID/APK through the unchanged Session method.
2. Capture current task stacks and report only whether the original owned task 876 remains the exact leaf and its component/display/user.
3. Call the frozen backend's readonly foreground parser through the same private held transport and report only its actual package/component/window token. The diagnostic must not require the package to equal Beike merely to report a mismatch, and it must not grant any mutation or reconciliation authority from that diagnostic. The existing helper mutation foreground predicate remains unchanged.
4. Recheck exact guards and retire all owned authority; retain original transport evidence and require complete stdout plus durable terminal. No raw full-window text, node text, screenshot, resume, activation, click, input, install, permission change or publisher retry is part of this observation.

This is a proposed read-only diagnostic, not a prepared or submitted Main request. Root must coordinate its lease window after the independent framework build activity. If a target-owned foreground can later be restored through an authorized existing path, that will need its own actual evidence and review; this plan does not perform or preauthorize that action.
