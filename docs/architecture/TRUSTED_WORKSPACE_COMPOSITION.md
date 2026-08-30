# Trusted workspace composition

**Checkpoint:** `TOS-D0A-02` headed-host qualification candidate
**Runtime status:** proof-soundness rerun required on the exact candidate head

The visible desktop workspace has two trust surfaces:

```text
native/compositor-owned trusted chrome
  + exactly one authoritative untrusted Servo content surface
```

They are composed into one visible workspace but never share a DOM trust
realm. External navigation targets only the existing content surface and can
never replace the trusted chrome. Popup, new-window and second-content-surface
requests are denied in v1.

`hepta-workspace-composition` is the engine-neutral state and invariant model.
It records geometry, content lifecycle, pointer/keyboard/IME ownership,
popup refusals, content frame publication and crash/recovery transitions. It
does not own a native window or Servo object.

## Headed-host proof contract

The exact-pin Servo adapter must demonstrate one native trusted window and one
logical content WebView at a time. WebView creation, invalidation, live count,
and peak count are measured rather than asserted. Every delegate callback and
asynchronous screenshot, JavaScript evaluation, and timer completion is bound
to both an immutable content generation and the originating Servo WebView. A
late generation-1 callback is ignored and counted; it cannot mutate generation
2 or satisfy a generation-2 gate.

The recovery corpus uses an explicitly external `SIGKILL` fault injection. It
is not represented as a Servo panic hook. Before dispatching the signal, the
adapter records the unique direct `--content-process` child's PID and Linux
`/proc/<pid>/stat` start time and immediately revalidates that identity. The
adapter then records three mandatory, independently checkable facts:

1. the exact PID/start-time target was selected;
2. `SIGKILL` was successfully sent to that identity;
3. the matching `/proc` identity disappeared and no active content child
   existed before recovery.

Servo documents `WebViewDelegate::notify_crashed` as a pipeline-panic callback.
An externally killed content process is not required to emit that callback, so
it is recorded as optional diagnostic evidence and cannot block or satisfy the
external-process recovery proof.

Recovery is forbidden until all three mandatory facts are present. The adapter captures
machine-readable process topology before the fault, after exact termination,
and after recovery. Generation 2 is authoritative only after one distinct
replacement PID/start-time identity exists, the old PID remains absent, and a
new generation-2 frame and page evidence have been produced.

A content crash returns keyboard ownership to trusted chrome, ends active
content IME, removes the old presentable frame and displays a trusted crash
placeholder. Recovery requires generation 2 and a new frame; stale pixels are
not promoted as live content.

## Claim ceiling

D0A-02 covers the visible local-fixture headed host path, native pointer,
button, wheel and keyboard input, the bounded basic IME submission/control
path, popup and external-navigation denial, exact content-process fault
attribution, trusted-chrome survival, and generation-2 replacement.

The gate does **not** claim a clipboard path. It also does not claim bounded
clean Servo shutdown or child reaping after the result is emitted; that remains
a later lifecycle gate and is recorded explicitly as a non-claim. It does not
prove a Debian/QEMU integration, BrowserActor, AgentPort activation, persistent
credentials, external browsing or effects, hardware support, or release
readiness.

Source tests alone prove deterministic policy and rollback behavior. D0A-02 is
closed only after the permanent headed workflow passes on the exact candidate
head, the resulting artifact is independently reviewed, and the same workflow
passes again on the exact integrated `main` tree.
