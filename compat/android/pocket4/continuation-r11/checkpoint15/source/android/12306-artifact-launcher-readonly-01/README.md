# 12306 current artifact and launcher read, revision 1

This source performs one narrowly scoped metadata observation of
`com.MobileTicket`, the exact 12306 package in the existing published 45-App
launcher matrix. It does not launch an App, call an instrumentation helper,
connect UiAutomation, take a screenshot, read App data, change permissions or
settings, install an APK, or deploy an engine. It never instantiates or changes
the Bili business Flow or an Amazon App context.

## Historical reference versus current evidence

The historical matrix has SHA-256
`05e74a719281abab717464978d85393dec8d0d528c1e7ccbd93691f156ce56e4`.
Its exact 12306 row says package `com.MobileTicket`, historical version 275,
`production_ready=false` and `CURRENT_EPOCH_BUSINESS_ACCEPTANCE_PENDING`.
The included reference contains just that row and its original observation
metadata. No current UID, APK directory, split count, signer or launcher is
inferred from it. Version 275 is recorded as a historical comparison, not an
admission requirement for this metadata read.

The five actual commands, if separately admitted by Root, are fixed:

1. `cmd package list packages -U --show-versioncode --user 0 com.MobileTicket`
2. `cmd package path --user 0 com.MobileTicket`
3. `cmd package resolve-activity --brief --user 0 -a android.intent.action.MAIN -c android.intent.category.LAUNCHER com.MobileTicket`
4. The exact same package-path read.
5. The exact same UID/version read.

The UID must additionally match that package's entry in the already hash-bound
Main activation. Before and after metadata and paths must be identical. A unique
current launcher is required to belong to `com.MobileTicket`. No component is
guessed and no fallback is tried. This retained resolution alone will not
authorize a later launch; that launch would need its own current binding.

## Reused execution and file boundaries

The base is the previously frozen, actually executed Amazon artifact reader.
The changes are a new package, root, nonce, descriptive labels, the fifth
read-only command, and the already reviewed bounded component parser. Its
original `Flow.command` observation function and seven held namespace/root FD
entry protocol are reused directly. The original Main epoch/config/three host
identities/resource guard, fixed source/tool pins, independent release and
post-command guard, and first-error preservation remain intact. There is no
numeric `nsenter --target` entry and no legacy helper fallback.

The same bounded action-lock admission is used even though these commands are
read-only. It waits on one held inode with `EX|NB` for the existing five-second
admission interval, rechecks Main after acquiring it, and closes only its own
descriptor. The source does not identify or disturb another lock holder.

APK paths come only from this package's successful Package Manager response.
One to sixteen distinct paths are allowed, with exactly one `base.apk` and
optional syntactically valid split filenames under one exact package install
directory. There is no assumption that 12306 has Amazon's three APKs. Unknown
path layouts fail closed rather than broadening a search. Each installed file
is opened beneath the held Main root and retained through the final package
recheck. The original owner, single-link, regular-file, write-mode and metadata
checks remain; each file is streamed in 64 KiB chunks, at most 256 MiB per file
and 512 MiB total. The hash pass has a 45-second budget within the 140-second
worker budget. Each path is reopened after the two final commands and must
still identify the same held file. All held APK descriptors close in reverse
order on success or failure.

The result contains exact paths, UID/version, stable held-file metadata and
SHA-256 values, the current launcher component, command completion evidence and
Main/source/release evidence. It exports no APK bytes, package inventory,
commercial journal, raw UI, account data or signer key. Independently verified
signer status and whole-App readiness remain false.

## Source-only validation

Thirteen local controls passed: the inherited package/path and command-lifetime
checks plus exact historical package binding, accepting a newly observed version
without rewriting history, variable split count, unique same-package launcher
validation with no fallback, and exactly five ordered read-only commands. The
command runner, authority FD numbers and lease are explicit protocol seams;
these controls did not enter a namespace, hash a real App APK or run Android.
Default PLAN performs no file or device reads. The actual frozen source/stage
and request stdin are hash-bound by the generator.

The only authorized prospective root is
`/home/alex/work/pocket4-12306-artifact-launcher-readonly-01`, with a new
once-only nonce. The request uses the prior 240-second outer budget, one CPU,
512 MiB memory and nice 10. Root must review and dispatch the exact request
once. An unknown response is reconciled using that same key; a partial or failed
run is retained and is not automatically repeated.
