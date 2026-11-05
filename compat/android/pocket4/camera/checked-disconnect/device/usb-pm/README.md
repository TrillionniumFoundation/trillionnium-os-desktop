# Pocket4 camera: prepared single-device runtime-PM contrast

**Preparation only. No Pocket4 preflight, experiment, sysfs write, provider change, USB reset, capture, or UI action was performed by this task.** The executable defaults to an inert JSON plan. The current device is absent, so the available evidence does not permit an actual power-management contrast yet.

## What the actual evidence establishes

`SOURCE_EVIDENCE.json` contains the exact hashes and paths of the retained local evidence, selected raw identity evidence, all seven historical intervals, and the latest power metadata. These are observations of the Pocket4 host, not values synthesized for the script.

| Fact | Retained observation |
| --- | --- |
| Actual kernel | `7.0.0-38-generic` |
| Target | USB `3-4`, VID/PID `1e08:5520`, SunplusIT Inc / Integrated Camera |
| Serial | `JX20250923V2`, present in each retained kernel enumeration and the installed provider's by-id source path |
| Device revision | Kernel `bcdDevice=9.23`; future sysfs binding requires its hexadecimal representation `0923` |
| Historical device numbers | 8 through 14, seven separate enumerations |
| Historical presence intervals | Seven intervals of approximately 14 seconds, measured from whole-second kernel timestamps |
| Provider activity in the retained service window | Seven registered idle generations, zero recorded `physical_camera_open` or `physical_camera_closed` events |
| Latest read-only observation | `2026-11-05T06:01:03.098003+00:00` |
| Target device at that observation | `/sys/bus/usb/devices/3-4` absent |
| Parent port | Hardwired, not attached, runtime active, suspended time 0, `power/control=auto` |
| Root hub | Runtime active, suspended time 0, `power/control=auto` |
| Target's own PM values | **Unknown: the target device was absent** |

The observed root-hub canonical path is `/sys/devices/pci0000:00/0000:00:08.3/0000:c7:00.0/usb3`. The script requires a future target to resolve to that exact parent followed by `/3-4`. This is an execution constraint derived from the observed parent topology; it is not a claim that a current target directory was inspected.

The Gain query warning is not proof of the disconnect cause. No autosuspend, human unplug, physical hardware fault, or firmware fault has been established. Upstream Linux 7.0 mechanisms and documentation are relevant background; the actual Ubuntu kernel has not been reconstructed from its exact build source in this work.

## Scope of the proposed contrast

The single intervention is `on\n` to **the exact target USB device's own** `power/control`. It is allowed only when that same attribute currently reads `auto` and its device-specific autosuspend delay is a recognized integer in `0 <= delay < 30000` milliseconds. A negative delay already disables autosuspend. A delay of 30 seconds or longer falls outside this fixed observation window and produces `NO_WRITE_OUTSIDE_OBSERVATION_WINDOW`. Both cases perform zero power writes rather than running an uninformative contrast.

The script observes the same device generation for 30 seconds after verified `on` and runtime-active readback. It samples presence, identity, control, runtime status and the suspended-time counter once per second. It then restores the original `auto` value through the original retained control descriptor, at most once, and verifies the readback while the same generation still exists.

Linux documents `on` as preventing device autosuspend and resuming a suspended device; `auto` permits runtime PM. System-wide sleep is a separate mechanism. The script therefore rejects a material difference between monotonic and boot-time elapsed time during the contrast. See the [Linux 7.0 USB PM interface](https://docs.kernel.org/7.0/driver-api/usb/power-management.html).

No interface, port, hub, controller, driver-binding, quirk, global module parameter, udev rule, provider service, or Android state is changed. No video node or usbfs device is opened. Nothing waits for a future attachment and no watcher or service is installed.

## Invocation modes

| Mode | Behavior |
| --- | --- |
| No arguments | Outputs `PLAN_ONLY`; does not inspect the host or sysfs |
| `--preflight` | Immediately reads host identity and the presently attached exact target; exits with a blocked result if absent or mismatched; no configuration or evidence-directory write |
| `--execute` | Requires explicit `--expected-boot-id` and a new absolute `--result-dir`; root on the exact host/kernel; takes the existing cooperative UI lock nonblocking; records durable intent before the one `on` attempt |

An example of the inert mode is:

```sh
python -I -B pm_control_trial.py
```

A future read-only preflight uses:

```sh
python -I -B pm_control_trial.py --preflight
```

An execute invocation is deliberately not supplied with a usable boot ID. The owner must first obtain and review the current preflight, then explicitly select execute mode with that observed boot ID and a new evidence directory. A zero-write blocked attempt does not arm a background retry. An existing result directory makes the invocation fail before opening a writable target descriptor.

The shared lock is `/run/lock/android-digitalis-actions.lock`, opened without creation and acquired nonblocking. It coordinates with the already reviewed Android action scripts. It does not lock the camera provider or claim control over independent host applications.

## Identity, generation and restoration rules

The runner checks the current host name, actual kernel release, boot ID and host mount namespace. The device alias must resolve to the required canonical topology on an actual sysfs mount. It then requires all of VID, PID, serial, manufacturer, product, revision, bus number and device path to match the retained target evidence, and records the current USB device address.

It opens and retains the exact device directory, power directory, identity attributes, and `power/control` descriptor. Before any store and on every observation, it compares current path identity with the retained directory/control device-and-inode identity, rechecks the cached identifying attributes, and checks that the original objects remain linked. All writes use the originally opened control descriptor; no write reopens a pathname after validation.

This distinction matters when a disconnect and re-enumeration reuse the name `3-4`: a write through the old descriptor cannot be redirected to the replacement pathname. The device's disappearance or generation mismatch prevents restoration to a replacement. The result then explicitly reports restoration as unverified. It does not silently equate “a new device has auto” with restoration of the original experiment.

Each store uses one direct libc `write` invocation with the complete payload. An error, EINTR or short result is not retried. A failed or interrupted `on` attempt remains potentially effective until same-generation readback establishes the current state. Cleanup attempts the one `auto` restoration if the held target still reads `on`; an already restored `auto` is recorded without another write.

Cleanup is independent of unrelated PM diagnostic counters. A missing counter or a failed evidence-log write after mutation does not bypass the same-generation restoration attempt. An initial failure to record durable `on` intent prevents the mutation entirely.

The [Linux 7.0 sysfs documentation](https://docs.kernel.org/7.0/filesystems/sysfs.html) describes complete-buffer stores and refreshing reads at offset zero. It also distinguishes a retained kernel object from the continued physical presence of its device. The script checks physical-generation presence explicitly and does not treat an open descriptor alone as proof of attachment.

## Result interpretation

| Terminal state | Meaning |
| --- | --- |
| `STOPPED_WITHOUT_POWER_WRITE` | A precondition or evidence requirement failed before the first power-write attempt |
| `ON_WINDOW_OBSERVED_ORIGINAL_VALUE_VERIFIED` | The 30-second sampled observation completed and the same generation's original control value was verified afterward |
| `CONTRAST_INCOMPLETE_RESTORED` | The contrast failed or was interrupted, but the original control value was verified on the same generation |
| `CONTRAST_INCOMPLETE_RESTORATION_UNVERIFIED` | A write was attempted and restoration could not be verified; no automatic rerun or cross-generation write follows |

Even the complete observation state keeps `causality_established`, `idle_window_independently_verified`, `camera_function_qualified` and `production_ready` false. A single survival window is evidence for further diagnosis. It cannot establish that runtime PM caused the earlier disconnects, prove an uninterrupted control value between samples, or qualify Android preview/photo persistence.

## Evidence still required before interpretation or execution

1. The actual camera must reappear now. Its own directory, identity and power attributes must be readable; parent-port attributes cannot substitute for them.
2. A fresh read-only host boot ID and actual target `power/control`, `autosuspend_delay_ms`, runtime status and counters must be observed. The execute path rechecks them immediately and retains the same generation for the entire attempt.
3. The owner must coordinate an idle interval. Review complete kernel and provider records covering the contrast, including capture-open/close events and disconnect/re-enumeration events. Any capture contaminates an idle comparison. The provider log alone does not exclude all unrelated host applications.
4. Preserve the before/after event receipts and same-generation restoration readback. No second intervention follows a result with uncertain effects.
5. Before any later Android Camera acceptance, independently require a present stable physical source and current-epoch CameraService registration, then perform the separately reviewed business acceptance. This PM script does none of those UI actions.

The script handles ordinary exceptions and catchable SIGINT/SIGTERM/SIGHUP by entering cleanup. A process killed with SIGKILL, machine power loss, interpreter failure or an uninterruptible kernel I/O cannot be guaranteed to run a userspace `finally` block. A fixed deadline around the outer process must not be presented as proof of restoration. Such a termination leaves an unknown result requiring a read-only check of the exact surviving generation; it never authorizes a blind write to a newly appeared device.

## Offline verification

Nine focused tests pass in `test_pm_control_trial.py`:

- A complete simulated 30-second interval performs one `on` and one restore.
- An already-`on` target performs zero writes.
- A delay of 30 seconds or longer produces `NO_WRITE_OUTSIDE_OBSERVATION_WINDOW` with zero writes.
- Device replacement receives no restoration write.
- An uncertain first write is not repeated and is restored when still attributable to the same generation.
- Cancellation and cleanup-log failure do not skip restoration.
- An external return to `auto` is preserved and does not qualify the interval.
- Failure of a diagnostic counter does not block control restoration.
- A disposable ordinary-file descriptor remains attached to its old object after its pathname is replaced; the replacement receives no write.

The final test is ordinary Linux FD behavior, not a real kernfs or hardware test. All fake devices and temporary files stay within this local preparation directory. `validation.json` records the actual local test result and the inert default-plan run. No real host preflight or execute mode was run.

`SOURCE_MANIFEST.json` pins the script, tests, evidence extraction, documentation, default plan and validation receipt. The previous all-App readiness matrix remains unchanged by this preparation.
