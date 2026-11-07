# Amazon QA R1: exact installation and state only

This is a new, once-only install of `org.droidloom.qa.amazon.r1`, built from the
frozen dedicated Amazon source. It does not launch Amazon, inspect or click UI,
connect UiAutomation, change permissions/settings, replace an installed helper,
or execute the legacy v2/Bili recorder CLI. The previous Bili source is unchanged.

The actual build receipt, stage receipt, APK bytes and signer are external fixed
inputs. All eleven completed build commands, source/tool equality, self target,
SDK31 compile/minimum and target33, no permissions/components, and signed APK are
checked by the actual built adapter before installation and at exit. The new
helper must be absent for all users including uninstalled records. Installation
uses `-R -t --user 0 --pkg <exact self>` once, without fallback. Its resulting UID,
base APK bytes/signature binding and one no-UiAutomation state result are checked
and retained. No automatic uninstall/reinstall follows an ambiguous result.

## Shared implementation and independent scope

`amazon_transport.py` is the frozen R4 BoundArun with only EXPECTED_PACKAGE and
EXPECTED_UID changed to Amazon/10129. All function bodies, exact seven held-FD
entry checks, original timeout semantics, first-error/lease-exit/post-guard
recording and failure poison are unchanged. The shared R4 manifest is an actual
immutable library dependency; it is not presented as the new transport manifest.
The new runtime source manifest binds the separate Amazon transport and context.
The original Flow.command body is called directly by the new context; no Bili
Flow or MainBinding business constructor is instantiated. Original Main identity,
classpaths with both roots, helper qualification and held namespaces/root remain
mandatory. No numeric target entry is used.

`amazon_context.Context` allows exactly thirteen ordered commands, including one
install and one state call. It closes admission after any rejected/failed call.
The state adapter Session itself is the actual built Amazon source, without any
method override; inspection/action/launch cannot pass this context's command
plan. Its standalone execute() remains closed. A future Amazon business flow
requires separate reviewed entry, actual installed UID and current UI selectors.

The existing installation lock function (same inode, EX|NB, five-second admission)
and owned APK staging/retirement are derived from frozen install03. The temporary
APK is cleaned only through its held file/directory identities. Worker receipt
writing, lock release, held binding release, target FD closure and final Main
checks preserve the first error. The exact managed job keeps one CPU, 512 MiB,
zero swap and 128 tasks; its post counters must have zero limit/OOM events.

## Commercial target binding

Before installing the new helper, the exact current Amazon UID, version and three
APK paths are read under the held Main entry. Each commercial APK is held read-only
and streamed against the prior actual identity/hash reference. Metadata is checked
at every command guard; final paths/UID/version and all three held hashes must
match again. No target package inventory count is assumed. This does not independently
establish Amazon's signer and it does not authorize App launch or whole-App readiness.

## Use and boundaries

Default install_state.py and make_request.py are PLAN_ONLY. The exact request is
for Root to review and dispatch once after the current owned runtime cleanup.
Partial staging/unknown outcomes are retained, never automatically replayed. Actual
installation/Android state are NOT RUN by local controls. Twelve local controls cover new source binding, ordered admission, exact artifact
predicates and first-error cleanup seams. The local filesystem rejects chown to
UID1000 (EINVAL); that original failed fixture is retained. Subsequent hash/FD
controls project only UID/GID in their explicit test identity seam: actual inode,
mode, links, size, timestamps, file reads/hashes and closure remain real. A separate
negative verifies that the unchanged production gate rejects the actual local
UID0 file. None of these controls qualifies Android ownership/namespace behavior.
Original real flock controls are retained references, not rerun.
