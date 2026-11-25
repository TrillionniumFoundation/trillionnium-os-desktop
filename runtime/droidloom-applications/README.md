# Native application observation

The runtime plan keeps the complete installed APK set, source selection, physical
Main epoch, required release gates, and per-application outcome. A successful
installation or launcher response does not satisfy those gates.

## Task metadata around a launch

The normal `launch_only` route uses the authorized supervisor request
`ObserveApplicationTasks { expected: ApplicationInspection }` before and after
its one launch. Both the legacy Ready owner and the kernel-first early owner
borrow their existing live execution capability. Development mode rejects this
request.

The producer runs only the source-owned `cmd activity stack list` command under
the existing `LaunchRead` role. Complete Package Manager identity, all installed
APK hashes, and the physical framework generation are checked before and after
the read. The existing absolute workflow deadline caps the command's shorter
operation deadline. Actual successful child exit, output hashes, and cgroup
retirement are required; every outcome performs the final original-owner check.
No executable, shell, process descriptor, task ID, or Android path is a public
input to this request.

The `droidloom.application-task-snapshot.v1` response contains the selected
package/user's task ID, root task, Android display, base component, visibility
flag, and current top activity. The full fixed-command stdout is bound by length
and SHA-256; unrelated task contents are not returned. Missing target metadata,
repeated identities, malformed output, and changed installed identity or epoch
fail the read. A target task with a foreign permission or login activity is
recorded as such. Android task visibility is framework metadata, not an image
of the host window.

The runtime result records `tasks_before` and `tasks_after`. After launch, the
actual authenticated Composer binding must appear as a visible task of that
same package/user on the built-in Android display. If a post-launch check fails,
the error retains the actual launch binding and the operation does not retry or
attempt numeric-ID cleanup. Existing source/specification pins are rechecked
before the task observation, before launch, and after completion.

A task observed in the baseline remains a pre-existing task. A task absent from
that baseline is not automatically an exclusively owned task: snapshot timing
alone does not establish launch causality. Consequently `fresh_task_proven`,
`close_observed`, and `reopen_observed` remain false and `business_pending`
remains true. No common or application-specific release gate is granted here.
Normal owned close must retain a live same-session capability to the actual
presenter window and use its established close path. Saved snapshot JSON or a
remembered task number cannot supply that capability.

The parser and route tests use explicit transport models. They cover changed
APK/epoch/UID identities, unrelated packages/users, duplicate or malformed task
records, wrong or hidden post-launch tasks, failure after a real launch shape,
and the pre-existing-task case. They are source-level verification and do not
stand in for a real enforcing device run, usable controls, rendered UI, audio,
state persistence, or whole-application release acceptance.
