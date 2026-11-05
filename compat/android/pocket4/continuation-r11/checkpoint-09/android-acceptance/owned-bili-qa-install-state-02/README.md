# Actual QA build02: one install and one state

This separate candidate binds the actually completed owned QA build02. It does
not modify recovery02, the R3 recorder, the held helper, commercial APKs or the
old local.pocket4.actions.v2. No runtime is authorized merely by this tree.

## Exact operation

The request creates only /home/alex/work/pocket4-owned-bili-qa-install-state-02
and a new original-recorder flow whose suffix is the fixed 32-hex NONCE.
The original recorder init and this worker run as separate joined processes,
so flow.lock is never reacquired recursively in one process. All Android
commands use the R4 private copy of frozen R3 Flow.android, its held namespace/root helper and Main
epoch/source/config/three-host-process/resource/data-directory fences.
The original ACTION_LOCK covers absence, staging, install and state.

Before any installation, the fixed actual build and stage receipts, complete
source/tool/11-command/manifest contract and exact signed APK bytes must match
INPUTS.json. The installation presence query is exactly the fixed new package,
including known uninstalled records across all users. Any output rejects.

The staged APK lives in a fresh root-owned directory under the held Android
/data/local/tmp. Creation is exclusive; file/directory FDs remain held through
retirement. Only the exact owned inodes are unlinked/rmdir; no recursion or
permission workaround is permitted. Installed package manager access failures
remain original failures. The actual install uses -R -t --user 0 --pkg with the
fixed new package. There is no -r, -g, install-existing or unsupported-option
fallback. Official AOSP's newer default allows replacement even without -r;
-R explicitly clears that behavior. INPUTS.json pins the exact primary source
blob/body read, and does not assert it is the exact deployed device framework.

After actual Success/rc0/joined/quiet command and mandatory post guard, the new
package's UID must be an ordinary user0 app UID, distinct from Bili and old v2.
The exact single installed base APK is read through the held root and hashed
against the actual signed artifact. This establishes the signer binding by
byte equality to the actual apksigner-verified APK, without trusting an
unverified package label.

Exactly one state nonce is sent to the new self-instrumentation. The frozen
Java state branch does not call getUiAutomation. The existing qa_contract
requires the exact nonce/request/UID, successful finish, actual joined command,
no stderr, no helper error, and ui_automation_connected=false. Installed UID,
path and APK are rechecked after state. A final across-users query must contain
only that one UID. No action selector, tree, coordinate, text input, shell
permission adoption or accessibility settings modification exists in this entry.

## Package retention and failure handling

The new owned helper is retained after a successful state check for a separate,
reviewed inspect/action admission. The temporary APK/directory is retired.
The old v2 helper is never invoked or changed; its original UID guard remains.
Bili data directory identities and UID guards remain unchanged.

There is no automatic install retry or uninstall after an unknown outcome.
If installation was attempted and any later step fails, the original failure
and possible retained owned package are reported, and root can reconcile it
from exact command, UID and APK evidence. No state operation is attempted
after an unverified install. Frozen command evidence retains timeouts,
lease-exit failures and Main-post-guard failures. Cleanup/FD-close/final-guard
errors are secondary to the original failure and still fail qualification.

The recorder's Main gate does not compare an old package-count baseline.
Its packages.list reader keeps only Bili10117/v2 10125, discards other rows,
and checks the original Bili data inodes. No 182-count or arbitrary package
inventory exception is added.

## Request and resources

make_request.py only generates JSON and never dispatches it. stage_execute.py
requires the exact hash-bound source packet and a fresh root. The actual managed
job has CPU100%, RAM512MiB, nice10, outer300s; only its exact current managed
cgroup is set to swap0/Tasks128. Counters are read while the coordinator is
alive, not after systemd removes the group. max/oom/oom_kill/oom_group_kill must
all remain zero. The worker has a bounded original run_cli wait; an unknown
outer timeout never produces a success or full-process-tree cleanup claim.

Private raw command outputs stay in the fresh root/flow. The main result and
worker result contain only the new owned package metadata/state digests and
fence summaries. No full activation, package inventory, private commercial
journal, APK or key is included in this source publication.

## Later inspect/action consumption

Install+state does not establish UI or audio qualification. A later request must
bind the actual durable install-state receipt and new UID/APK before using the
frozen QA adapter. Inspect/action still require the original owned task scope.
The frozen adapter consumes joined state -> operation -> state receipts; global
restoration is proven only by the later completed no-UiAutomation state plus
the actual own-ServiceInfo readback. Click is dispatch acknowledgement, keeps
outcome_unknown=true, and cannot stand in for playback/audio or business success.
No later operation is part of this request.

## R4 prefix fix and separate host binding

Install01's actual failure remains unchanged: original R3 checked -t across the
entire helper argv and rejected the legal Android test-APK argument before
spawning its install command. No state ran. The owned staging inodes were
retired and Main stayed unchanged. This is a new root, flow, nonce and request.

The new private recorder is copied only after every original R3 payload and
manifest is verified. Its 44-file manifest changes only the production
bound_android_transport.py hash. The original R3 files and installed helpers
are never modified. R4 checks the first exact --, the exact helper/current
parent/7-FD prefix, and the unchanged complete Android suffix. It still rejects
numeric namespace-target prefixes. The separate 17-control source/report pins
are retained, with synthetic target/runner scope explicit.

The actual compiled QA source and APK remain recovery02. session_binding.py is
a new explicit host-only constructor tied to the new R4 manifest; it inherits
the original installed/instrument/foreground/task/sequence methods unchanged.
It does not mutate the original adapter's R3 global pin or fake a R3 contract.
Full original build/manifest/APK/signer verification remains mandatory.
