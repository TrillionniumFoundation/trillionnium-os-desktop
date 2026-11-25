# Actual application window lifecycle evidence

The existing `qmp_evidence.py lifecycle` action observes one reviewed application's
normal launch, native window, OS close, and separate reopen in the currently owned
qualification VM. It does not start a VM, an Android runtime, a service, or a
second presenter. It never accepts a task ID, object ID, component, resolution,
arbitrary remote command, or saved launch event as close authority.

## Required original inputs

The existing `bind` action must have admitted the original live QEMU process,
private QMP socket, root-protected run/prepared receipts, normal host manifest,
original fixture owner/unit InvocationID, and the fixture's fresh loopback SSH
key. The running guest must be a normal `android_runtime` boot with the complete
public import: the exact 39 selected package identities, every APK in their
current signed base/split sets, the three source JSON files, and the exact
canonical gate registry. The APK count is the actual complete pinned selection;
65 APKs belonged to the earlier batch and is not a release invariant. Each app
retains the installer's 32-file and 2 GiB bounds, with an 8 GiB whole-input bound.
The importer accepts this scope only with fresh Android data and no original
userdata import. This action rejects inputs without the canonical registry and
all calibration guests.

Install the public APKs through the existing restricted package helper before
using this action. The action does not install, downgrade, uninstall, force-stop,
clear data, or rewrite signatures. It first observes the actual complete PM APK
set and physical runtime epoch. If the selected package already has any task,
it rejects the operation and leaves those tasks alone.

The normal host must include the read-only `droidloomctl tasks` command and
`p4-presenter-window-event-v1` events from the original native presenter's
existing `DROIDLOOM_INPUT_TRACE=1` qualification environment. The public presenter
and client bytes must match the normal host-stage manifest used by `bind`.
Changing a host ELF may also change the MAC export's labeler ELF identity; check
the actual five-file MAC release bindings before selecting the normal run.

The action has a fixed 600-second whole exchange deadline and requires more than
616 seconds remaining in the original owner's admitted lifetime. A normal run
with a suitable duration up to the existing 3,600-second limit can provide that
window. It neither extends nor takes over the owner's shutdown/reap deadline.

## Invocation

Use the root-protected imported controller and the binding produced for that
exact live run:

```sh
sudo /usr/bin/python3 /var/lib/droidloom-qualification/CONTROLLER/qmp_evidence.py lifecycle \
  --binding /var/lib/droidloom-qualification/EVIDENCE/BINDING.json \
  --binding-sha256 ACTUAL_BINDING_SHA256 \
  --name firefox-lifecycle-1 \
  --package org.mozilla.firefox
```

The capitalized paths and digest are the actual outputs of the existing import
and bind steps, not defaults to manufacture. The package must be in the guest's
pinned complete selection. Its component is taken from that original selection
and independently matched to the live Android launcher catalog.

## Recorded exchange

Each guest exchange is saved as a new root-private JSON file before the next
mutating step. A failed post-launch check retains the actual public client
response and original returned binding. A launch is never automatically retried.

The sequence is: complete actual task/installed identity baseline; one normal
launch; task binding readback; actual native create and bind events; sampled
presentation callback and current native focus; the normal GNOME Alt-F4 binding;
one fixed paired Alt/F4 QMP gesture; the original window's successful
`request_close` send and actual native unmap events; actual selected-package
task absence; one separate launch; and a later actual native creation, task
binding, focus and sampled presentation. It also captures the actual QEMU
console at the launched, closed and reopened stages.

Only missing asynchronous observations may be polled. An identity, source,
epoch, duplicate-event, journal sender, or ordering failure ends the exchange.
No task cleanup or retry follows an uncertain command or QMP acknowledgement.
The existing `capture` and `key` actions retain their narrower contracts and
key whitelist; Alt-F4 is available only inside this closed lifecycle exchange.

## Limits of this evidence

A native `close_sent` event means the original normal close message was sent;
it does not mean Android acknowledged task removal. This action additionally
requires the actual native unmap and a fresh task list with the selected package
absent. That absence and a later window event still do not prove exclusive
Android launch causality against every possible concurrent actor.

The receipts therefore retain `fresh_task_proven=false`,
`common_gate_accepted=false`, `data_preservation_qualified=false`,
`application_business_accepted=false`, `guest_qualified=false`, and
`production_ready=false`. Screenshots are actual console pixels, without a
claim that each pixel belongs to a particular Android task. A close and reopen
does not establish account state, saved data, any app-specific business gate,
or the complete common lifecycle gate. Those checks must consume their own
real observations under the unchanged required gate registry.

The offline tests exercise the original credential-bearing QMP transport,
strict public-source/epoch checks, native creation identity, actual-close
requirements, and the fixed OS gesture. They do not claim a successful guest
run.
