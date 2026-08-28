# ADR 0002: Trusted shell plus one untrusted content WebView

- Status: Accepted; implementation variant pending D0A-02
- Date: 2026-08-28

## Decision

The visible desktop has a trusted shell/chrome surface and exactly one untrusted
Servo content WebView governed by one PageOwner. External navigation changes the
content WebView and cannot replace the shell. A hidden second Agent page or
independent browser control endpoint is forbidden.

Servo subprocesses are allowed for isolation. The product invariant counts
logical sessions and PageOwners, not operating-system PIDs.
