# Bilibili r3 bounded stable observation and search entry 01

This new once-only flow uses the already installed r3 helper UID 10166 and
the unchanged source/build/APK/signer/installed-file chain. It does not install
or change an APK. All 20 nonces are new. The original failed flow stays retired.

## Observed problem and narrow change

The original actual r3 attempt observed a complete 76-node tree. Before its
single proposed click, Java captured a complete 156-node tree and rejected
`INSPECTED_TREE_OR_WINDOW_CHANGED` before `performAction`. The subsequent private
observation also had 156 nodes. First/post window metadata and the search-entry
node were equal, while other tree paths changed. The action capture's full tree
was not retained, so the post-tree is not asserted identical to it. This is an
observed whole-tree change; no network or Main failure is inferred.

Before attempting any click, the new controller permits at most four successful
read-only state/inspect/state sequences under a 12-second admission deadline.
Two consecutive complete tree hashes, window hashes, node counts, original
foreground scope and accessibility state must agree. Each sequence must complete
its own independent after-state, restoration and exact helper identity checks.
The deadline is checked before and after each already bounded joined sequence;
it is not an interruptible hard timeout inside an Android command. The original
per-command and 240-second worker limits remain the outer bounds.

A failed read exits immediately as the primary failure. Only successful reads
whose complete observations differ can lead to another finite observation.
There is no fixed sleep, retry of failed instrumentation, or action replay.
The original independent post-inspection and exact cleanup still run on failure.

After stability is observed, the unchanged Session still captures another fresh
inspection, selects the exact public search-entry node, and calls Java's unchanged
whole-tree, focused-window and target gates. Stability does not replace these
gates or guarantee the future action. The only mutation allowed is one
`ACTION_CLICK` matching `tv.danmaku.bili:id/expand_search`, class
`android.widget.LinearLayout`, description `Search bar, button`.

## Scope and cleanup

The original R4 recorder, R5 held namespace transport, Main fence and action lock
remain in use. The exact original finally cleanup block is unchanged: only the
positively owned new task is removed; existing tasks and commercial app data are
preserved. This is not a force-stop or proof of a cold process start. The package
is not instrumented; the owned helper self-instruments. R1/R2/v2 are untouched.

There are no text, audio, settings, permission, login, message, purchase or media
actions. Search-page meaning is evaluated from a separately retained private
post-tree; acknowledged click alone keeps the business outcome unknown. Input
of the fixed public query “微积分” awaits the observed exact EditText selector and
a separately reviewed next flow. Whole-App readiness remains open.

## Resources and evidence

Default PLAN performs no device or remote actions. Each original CLI phase is a
separate joined process. Worker 240 seconds, outer 600 seconds, CPU 100 percent,
RAM 512 MiB, swap 0 and TasksMax 128 are unchanged. Up to 12 additional no-mutation
instrumentation commands implement the bounded observations; there is no stress.

Public records contain only hashes, safe scope/counters, restoration and the fixed
public selector. Commercial UI text, raw node arrays and private journals remain
outside Git in the exact owned flow. Local controls label their observation and
clock seams and do not imply an Android PASS. Old FAIL sources and receipts are
not changed or reinterpreted as successful.
