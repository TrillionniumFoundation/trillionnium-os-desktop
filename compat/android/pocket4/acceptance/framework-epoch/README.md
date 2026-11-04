# Android framework epoch guard

This guard closes an acceptance gap exposed on Pocket4: Android init and the
outer cell remained alive while a composer failure caused SurfaceFlinger,
zygote, and system_server to restart. UI snapshots and task IDs from before that
restart could no longer support later business-flow actions or conclusions.

## Use in a workflow

1. Verify the daemon's cell, resource policy, installed artifacts, and package
   through the existing trusted launcher and acceptance controls.
2. Call `capture_android(verified_init_host_pid)` immediately before reading UI.
3. Save the UI observation and require `require_unchanged(epoch)` afterward.
4. Retain that same epoch when deciding an action from that observation. Invoke
   the action through `execute_bound(epoch, operation)`. The operation should
   save its exact transport receipts before returning or raising.
5. Verify the action's declared UI/business postcondition in the same epoch.

If a framework process has changed before dispatch, the guard raises an
`EpochError` with `action_attempted=false`. If a change is detected after dispatch,
the receipt has `action_attempted=true`, `outcome_unknown=true`, and
`automatic_retry=false`. It does not silently adopt replacement processes. A new
epoch requires a fresh observation and decision; an unknown action is never
replayed automatically.

The guard pins boot identity and each selected process's host PID, start tick,
parent, namespace PIDs, UIDs, executable, command line, PID/mount namespaces, and
cgroup. Android discovery additionally checks the expected executable, UID,
parent relationship, cell PID namespace, and cgroup ancestry. It uses command
line rather than Linux `comm` to find zygote64: this device's zygote has `comm=main`.
It preserves legitimate private mount namespaces for zygote and system_server.

Pre/post checks cannot make an external UI action atomic with a future process
restart. The postcheck reports that race as unknown. Stable process identity is
also not proof of a stable window, successful playback, correct native-bridge
behavior, or a completed business operation. Existing window, selector,
resource, artifact, and business assertions remain necessary.

## Verification

Run on Linux with a `/proc` mount corresponding to the Python process's PID
namespace and permission to inspect its children:

```sh
python3 -m unittest -v test_framework_epoch.py
```

Ten tests use real Linux processes, with no mocked `/proc` trees. They cover
retained parent plus restarted child, missing processes, exec with unchanged PID
and start tick, process names containing parentheses, pre-dispatch rejection,
restart during an action, timeout preservation, no replay, document integrity,
and serialization. All ten passed on Pocket4. An initial attempt in the cloud
executor could not inspect its child PIDs through that environment's `/proc`;
the guard failed closed, and no checks were relaxed to accommodate it.

A separate read-only check captured the actual Pocket4 init, zygote64,
system_server, and SurfaceFlinger, read the activity stack, and verified the same
epoch afterward. It did not induce a restart or modify Android services. This
module is used by new acceptance workflows; it does not replace or change the
installed `android-app` helper or ActionRunner APK.
