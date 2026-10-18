# Debug runner records its own private SDK

Support code `a5af45537dea32039ea172ad0d7e381400c07d95` fixes a downstream regression after the ordinary build
entry moved OSDK installation to each run's private prefix. The previous debug
runner still observed CARGO_HOME/bin/cargo-osdk after readiness. A missing global
SDK incorrectly failed the debug run; an unrelated global SDK was recorded as
the current build. With a foreign global SDK present it also ignored a missing
private SDK or a bad private installation receipt.

The actual public debug CLI, with explicitly substituted host-only build/GDB/boot
work, reproduced all four pre-fix failures. The new helper observes only
boot/osdk/bin/cargo-osdk, reads the regular executable through one descriptor
with NOFOLLOW/NONBLOCK, checks unchanged descriptor and pathname identities,
and verifies the exact SHA256/path against boot/osdk/cargo-osdk.sha256.
The record includes installation root, source directory, Cargo.toml and
Cargo.lock hashes. Shared Cargo home contents are never a fallback.

The complete debug host suite passed 16/16 under -I and 16/16 under -I -O,
including existing cancellation/session ownership and encoded-flag entry tests.
The independent reviewer separately ran the same four focused public-CLI
fixtures in both modes: four expected failures with the old source and
four passes with the corrected source in each mode. These focused checks repeat
a subset of the complete suite and are reported separately.

This phase executes no real SDK installation, Rust compilation, GDB session,
or QEMU guest. Fixture result.json files deliberately contain host substitutes;
their passed fields do not establish a guest or entry breakpoint result.
The SDK observation describes bytes at observation time, not immutable custody
of bytes already executed. Earlier genuine kernel/debug evidence retains its
own original source and binary identities. Neither kernel.sh, minimal.mk,
kernel runtime code, nor the prior private-sdk evidence phase was changed.

Complete fixture projects, source snapshots, command records, raw observations
and intermediate failures are in host-fixtures.tar.gz. The index binds each
regular member; the offline verifier reads the archive in memory without
extracting or executing its contents. Baseline and final source bytes and raw
test/review logs are also retained in readable form.

```sh
python3 -I support/build/evidence/2026-10-17-debug-private-sdk/verify.py --repo .
python3 -I -O support/build/evidence/2026-10-17-debug-private-sdk/verify.py --repo .
```
