# hepta-browserd

This package is the D0 daemon scaffold for the desktop product. It currently
contains only deterministic contract/session self-checks. It intentionally
starts no Servo runtime, Unix socket listener, WebDriver server, or external
network operation.

```bash
cargo run -p hepta-browserd -- --self-check
```

The connected carrier and contract checks are host-validated in D0C-02 through
D0C-04. A production-shaped listener is still a later D3 deliverable and must
bind peer credentials, a per-session nonce, bounded frames, deadlines, and the
machine-readable browser API contract before accepting mutations.
