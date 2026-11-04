# Active call inventory and preservation boundary

This inventories the actual pinned source. Definitions retained in reference
files are not automatically reachable execution entries.

| Caller | Actual existing operation | Integrated route | Evidence and lock |
|---|---|---|---|
| `Flow.stacks` | `cmd activity stack list` | `Flow.android` → held transport → seven FD entry | Original direct raw command receipt; fixed Main fence before/after |
| `Flow.cleanup` | One `cmd activity stack remove <new task>` | Same held transport | Original `cleanup-attempted.json`; original global action flock; native launch receipt and exact leaf required |
| Original `wait_for_removal` callback | At most 32 read-only stack lists, eight-second observation window, per read ≤3 s | Same held transport with original short timeout behavior | Every original raw readback saved; no repeated remove; other task set must remain |
| `exit-info` operation | `dumpsys activity exit-info tv.danmaku.bili` | Same held transport | Original package-specific raw evidence, no log clearing |
| New `admission` | One package/UID query for Bilibili user 0 | Same held transport | Metadata binding and exact UID output; no UI/launch/audio |
| `Flow.launch_locked` | One host `sudo -u #1000 env … droidloomctl launch … --json` | Original native daemon launch, unchanged argv | Newly added same action flock; original launch intent/receipt/task ownership; an existing Bili task now stops the flow before launch |
| `Flow.ui` | Original APP CLI: dump/find/click/set-text/observe | Physical private `existing_ui_entry.py client`; logical original argv retained | Original command label/argv/raw CLI output used by reconciliation; once-only parent step |
| Exact APP `client()` | Original argument validation and `--interactive-production` guard; one exact sudo/BACKEND spawn | Only that spawn redirects to private `existing_ui_entry.py backend` | Original client behavior, child claim, exact serialized request and parent intent hash |
| Exact BACKEND `helper()` | Original input parser/action flock/dispatch | Private BACKEND module; only `arun` replaced | Existing global action lock is still acquired by the actual original function |
| BACKEND `ui()` | Original action runner instrumentation | Held transport, unchanged original request/protocol | Intermediate output only in memory; transport sizes/hashes/status and final original scoped CLI output retained |
| BACKEND `foreground()` | `dumpsys window displays` | Held transport | Original function discards raw output, keeps only foreground package/activity/window identifiers |
| BACKEND `capture()` | `screencap -p`, with before/after verified window context | Held transport | Full screenshot remains in memory; original crop and scoped observation output retained |
| APP/BACKEND `discover()` | Host `droidloomctl status --json` and read-only `/proc` discovery | Original source, with fixed init/status checks in `MainBinding` | No Android namespace command in this function; no new epoch is adopted |
| `Flow.engine_maps` | Read-only exact Bili process/UID/namespace/maps/engine binding | Original method AST unchanged | Private original scoped mapping evidence; this is not instruction, audio or whole-app qualification |

The allowed recorder UI operation set does **not** reach helper `home`,
`back`, `tap`, `swipe`, `launch`, `screenshot`, `visual-click`, `snapshot-tap`,
`visual-find`, `apps`, arbitrary shell, or OCR command entry. The original
`find` operation uses native selectors. In-app Back, if later needed, must be
an explicitly observed supported control; this source does not add global
Back/key injection.

The copied APP's original `arun` and BACKEND's original numeric `arun`
definitions remain verbatim for provenance. The APP module is used only for
its client/discovery; the BACKEND module has `arun` replaced before its
`helper()` can dispatch. The old external installed CLI/BACKEND files are
checked for their original pins but are not executed as namespace command
entry points by this adapter. The full active Python source contains no
`nsenter` execution.

## Target and cleanup ownership

Main is fixed to the r10 activation and 48cb epoch. The original Main
daemon/launcher/presenter process identities, cell configuration, limits and
framework epoch checks are retained; they are not replaced by a PID-number
check. The shared entry helper receives held descriptors and removes them
before the Android command exec, under its separately retained qualification.

The app task must be identified by the successful original native launch
receipt, absent from the prelaunch snapshot, display 0/user 0, the exact
freeform leaf and Bilibili package. Only that saved new task may be explicitly
removed. Existing tasks and account/data directories are preserved. A failed
or uncertain remove is not repeated. Native launch and UI unknown outcomes
stay unknown; reconciliation permits a new decision from a later observation,
not replay of the old command.

`flow.lock` keeps its original process lifetime, including final evidence.
Child wrappers do not reacquire that lock. They verify it is currently held,
refuse completed parent steps/commands, and claim a new private child journal
once. That check is an active-phase gate, not a claim that a flock alone
identifies a particular process. Fixed source, command and request bindings
are separate checks.

No full descendant-tree guarantee is added. Host command sessions, the shared
helper's direct-child boundary, Android's original inner timeout and explicit
owned-task cleanup have distinct scopes. A helper/command failure does not
prove a Binder-launched app action did not occur. An unjoined direct command
poisons held-resource release; the final result fails.
