# hepta-browserd

This package is the D0 daemon scaffold for the desktop product. It currently
contains only deterministic contract/session self-checks. It intentionally
starts no Servo runtime, Unix socket listener, WebDriver server, or external
network operation.

```bash
cargo run -p hepta-browserd -- --self-check
```

The first production-shaped listener is a later D0C-2/D3 deliverable and must
bind peer credentials, a per-session nonce, bounded frames, deadlines, and the
machine-readable browser API contract before accepting mutations.
