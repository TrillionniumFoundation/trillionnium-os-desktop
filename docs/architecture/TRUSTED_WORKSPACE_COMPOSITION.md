# Trusted workspace composition

**Checkpoint:** `TOS-D0A-02` source foundation  
**Runtime status:** pending exact Servo first-frame integration

The visible desktop workspace has two trust surfaces:

```text
native/compositor-owned trusted chrome
  + exactly one untrusted Servo content surface
```

They are composed into one visible workspace but never share a DOM trust
realm. External navigation targets only the existing content surface and can
never replace the trusted chrome. Popup, new-window and second-content-surface
requests are denied in v1.

`hepta-workspace-composition` is the engine-neutral state and invariant model.
It records geometry, content lifecycle, pointer/keyboard/IME ownership,
popup refusals, content frame publication and crash/recovery transitions. It
does not own a native window or Servo object.

A content crash returns keyboard ownership to trusted chrome, ends active
content IME, removes the old presentable frame and displays a trusted crash
placeholder. Recovery requires an explicit non-zero session generation and a
new frame; stale pixels are not promoted as live content.

Source tests prove deterministic policy and rollback behavior only. D0A-02 is
not complete until a runtime adapter demonstrates one visible native window,
trusted chrome, exactly one Servo surface, a local fixture first frame,
native pointer/keyboard/IME input, popup denial and content-process recovery.
