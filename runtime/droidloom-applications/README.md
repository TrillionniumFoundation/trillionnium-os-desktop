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
package/user's task ID, root task, Android display, and base component. The
`visible` and `top_activity` values belong to the containing root; the actual
framework prints them on each child row. They do not establish leaf-specific
visibility or host pixels. A null root top activity is omitted from stdout and
becomes `None`; zero is a valid observed root/task number. The full fixed-command
stdout is bound by length and SHA-256; unrelated task contents are not returned.
Missing required metadata, repeated identities, malformed output, and changed
installed identity or epoch fail the read.

The runtime result records `tasks_before` and `tasks_after`. After launch, the
actual authenticated Composer binding must appear under a visible root for that
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

The format regression is grounded in the selected official system image
`dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4`.
Its actual `framework.jar`
(`bc8a175a95dcb50b5ae62a03a0ec2ba0fdea34169f83b2aab3c8bf2790707587`)
contains the inspected `ActivityTaskManager.RootTaskInfo.toString` DEX method;
its `services.jar`
(`bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86`)
contains `ActivityManagerShellCommand.runStackList`, which prints those objects.
This checks the actual selected bytes without claiming the separate vendor
source revision is identical to the official system.

Actual `RetirementUnproven` errors remain typed through the inspection adapter,
workflow postcheck, and task-observation controller boundary. The legacy
controller enters `Quarantined` before another readiness poll and retains the
original owner; the early controller leaves its original service loop through
the existing quarantine path. An ordinary text rejection cannot manufacture a
retirement failure, and successful readiness cannot erase one.
