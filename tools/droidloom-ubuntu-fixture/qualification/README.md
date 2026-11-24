# Bounded normal-VM screen and input evidence

This qualification controller attaches only to an explicitly selected, already running normal fixture VM. It does not start, continue, stop, signal or reap QEMU. The original fixture process retains shutdown and reaping. No live VM or QMP connection was used to validate this tool.

## Prerequisites

The VM owner selects the real run directory, systemd unit and InvocationID. The original `RUNNING.json`, `QEMU-ADMITTED.json`, `RUN-INPUTS.json` and prepared receipt must still be protected and unchanged. Calibration VMs and ended runs are rejected.

Import `qmp_evidence.py` as an ordinary root-owned, single-link file, mode 0555, below `/var/lib/droidloom-qualification`; preserve root-owned non-writable ancestor directories. Verify the delivered size and SHA-256 before execution. Do not loosen the original run directory or QMP socket permissions.

For task evidence and keys, the normal run must have its original explicitly enabled loopback SSH forwarding and fresh fixture key/known-hosts files. The fixed probe uses only the fresh guest's alex account. It does not use original account data, SSH agent state or an arbitrary remote command.

The normal native presenter must include the focus trace source change. Before that unit starts, the VM owner must arrange the existing diagnostic environment values `DROIDLOOM_INPUT_TRACE=1` and `DROIDLOOM_FRAME_TRACE=1`. This controller does not edit a unit or enable tracing. Missing focus/presentation records cause input to fail closed.

## Bind the selected run

Set the values below from the actual original owner and the current protected normal release. These are operator-selected arguments, not PID or path discovery:

```sh
sudo -n /usr/bin/python3 /var/lib/droidloom-qualification/r133-qmp-evidence-516eec/qmp_evidence.py bind \
  --run-directory "$RUN" \
  --unit "$OWNER_UNIT" \
  --invocation "$OWNER_INVOCATION_ID" \
  --fixture "$PROTECTED_FIXTURE" \
  --fixture-sha256 "$FIXTURE_SHA256" \
  --host-stage "$PROTECTED_HOST_STAGE_JSON" \
  --host-stage-sha256 "$HOST_STAGE_SHA256" \
  --output /var/lib/droidloom-qualification/selected-normal-screen-evidence
```

The output directory must be a new direct child of the qualification root. The returned `binding.path` and `binding.sha256` are the exact arguments for the following commands. Bind performs no QMP connection.

Binding records the actual QEMU PID/start identity, a live PIDFD inode, its original fixture parent and ELF, the original private QEMU full F9 and bytes, the existing socket node, host boot ID and owning systemd InvocationID/cgroup. It rechecks all four UID/GID slots, empty supplementary groups, zero effective/permitted/inheritable/ambient capabilities, no-new-privileges, seccomp and non-dumpability. Every later operation revalidates these facts. The original capability bounding-set value is recorded without changing it.

## Screen capture

```sh
sudo -n /usr/bin/python3 /var/lib/droidloom-qualification/r133-qmp-evidence-516eec/qmp_evidence.py capture \
  --binding "$BINDING" --binding-sha256 "$BINDING_SHA256" --name initial-desktop
```

This obtains the guest display console through the original QMP connection. A new root0600 ordinary file is opened with O_WRONLY, O_EXCL and O_NOFOLLOW. Its held FD travels in SCM_RIGHTS to QMP `add-fd`; `screendump` uses only the returned `/dev/fdset/N`; the exact returned fdset entry is removed. FD sets 1 and 2 remain reserved for the original VM inputs.

The resulting receipt contains the image's complete F9, SHA-256, exact P6 header, dimensions, complete pixel length and collection interval. Accepted images are at most 4096 by 4096 and 64 MiB. This is a read/acceptance bound, not a filesystem quota. Failed evidence is retained and is not a successful screenshot receipt.

A desktop screenshot alone does not establish an Android task's first frame. Review the actual pixels and combine them with the task's original launch event and native presentation feedback.

## Selected launch event

The app runner supplies schema `p4-selected39-launch-event-v1`. Copy one complete event, without editing it, into a root-protected ordinary JSON file and pin that file. Do not give the controller a growing JSONL file.

Required data includes:

- `package`, `component`, `guest_clock="CLOCK_MONOTONIC"`, guest monotonic start/end and `guest_boot_id`.
- Original `epoch={boot_id,cell_host_pid,framework_host_pid,framework_start_ticks}`.
- Exact launch `binding={object,composer_display,android_display,task}`, where the Android display is 0.
- Original CLI response pin; optional presenter PID/InvocationID, when already actually observed.

The planned guest app-runner event stream is the flat file `/var/lib/droidloom-public-apks/u1000/selected39-r3-events.jsonl`. That stream is not itself an authorization to send input.

A task capture adds the event arguments:

```sh
sudo -n /usr/bin/python3 /var/lib/droidloom-qualification/r133-qmp-evidence-516eec/qmp_evidence.py capture \
  --binding "$BINDING" --binding-sha256 "$BINDING_SHA256" --name selected-app \
  --event "$ROOT_PROTECTED_EVENT" --event-sha256 "$EVENT_SHA256"
```

The fixed SSH probe verifies the actual presenter's PID/start, unit InvocationID, compiled ELF bytes and SELinux role. It reads only the existing trace journal and runs the existing fixed `droidloomctl --json inspect PACKAGE --user 0` operation using the normal release's pinned client ELF. The returned real Android epoch must exactly match the selected launch event. No new product request is introduced.

Only the real native `stage=presented` callback for the selected object counts as presentation feedback. A launch, commit, flush or QMP reply does not count. The original diagnostic trace samples frame numbers congruent to 1 modulo 8; the receipt preserves actual frame/buffer IDs, display/callback times, sequence and drop count. It explicitly leaves first-ever-frame and pixel-to-task proof false.

## One bounded navigation key

After viewing the screen and selecting the corresponding current launch event:

```sh
sudo -n /usr/bin/python3 /var/lib/droidloom-qualification/r133-qmp-evidence-516eec/qmp_evidence.py key \
  --binding "$BINDING" --binding-sha256 "$BINDING_SHA256" --name selected-app-tab \
  --event "$ROOT_PROTECTED_EVENT" --event-sha256 "$EVENT_SHA256" --key tab
```

The only keys are tab, left, right, up and down. There are no text strings, return key, chords, pointer coordinates or arbitrary QMP operations.

Before input, the controller captures a real screen, obtains an actual native focus enter for the same task object, observes real presentation feedback and rechecks the current Android epoch. An unmapped focus leave with object 0 revokes focus. An old event, a foreign presenter, a changed generation or missing focus fails before input.

Down and up are sent together in one fixed QMP request. The controller then captures another screen and requires the actual presenter's matching non-repeat Wayland down/up pair, same object and scan code, with consecutive native serials. It rechecks the presenter's identity and current epoch. QMP acknowledgement alone never passes.

The native Wayland trace occurs before the product input transport completes. Accordingly every receipt retains `android_input_consumed=false`, `application_business_accepted=false`, `guest_qualified=false` and `production_ready=false`. Actual Android and application behavior still need their own evidence.

## Bounds and ownership

The QMP connection uses actual per-message SCM_CREDENTIALS; SO_PEERCRED alone is insufficient because the original listener was created by the root fixture and inherited by QEMU. Unexpected sender credentials or ancillary FDs fail closed.

Each connection has a 28-second absolute deadline, two-second socket operations, a 64 KiB line limit, 32-event response limit and 2 MiB aggregate reply limit. Fresh guest probes have an eight-second deadline and 2 MiB combined output limit. The probe kills and reaps only its own SSH subprocess on failure. Operation admission leaves headroom before the original fixture deadline; it never extends the VM's lifetime.

A private lock serializes this controller's operations. It does not replace the original owner or authorize concurrent shutdown. Stop scheduling evidence operations before the owner's normal shutdown window. The original owner remains the only VM lifecycle controller.

## Offline verification

Run `python3 test_qmp_evidence.py` outside a VM. The seven tests use ordinary local Unix sockets and original owned subprocesses. They verify actual message credentials across an inherited listener, SCM_RIGHTS delivery to the held file, complete PPM validation, response/deadline bounds, foreign or revoked focus, changed Android epoch, real presentation versus commit, and bounded probe-child retirement.

The fixed embedded guest program is also compiled separately as Python source. These checks do not assert live QEMU, guest Wayland, Android or application qualification.
