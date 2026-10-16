# A09 2026-10-16: Rust contract safety follow-up

## Defects corrected (source-level; hardware not touched)

1. Public mutable identifiers on DeviceHandle, MemoryObject, Buffer, Queue
   and Completion allowed a kernel consumer to modify BDF/group, DMA offset,
   direction or queue identity after admission. Fields are now private; only
   immutable getters expose their observed values.
2. A generation counter at u64::MAX previously caused DeviceHandle::fence()
   to return ArithmeticOverflow **while remaining Assigned**, potentially
   leaving a live device on an exceptional path. The overflow path now
   transitions to Quarantined, without releasing buffers or reassigning.
3. Quarantine and cancel_unknown_effect previously failed before entering a
   terminal safe state on generation overflow. Both now fence/quarantine
   even at the maximum generation. Queue outstanding charges remain held,
   Buffer remains UnknownEffect; the model cannot release/reuse the buffer.
4. Compile-fail API docs guard against external mutation or fabricated
   Completion struct literals; new Rust tests exercise overflow and getters.

The model is NOT a device driver. In particular, a malicious trusted driver
could still invoke the `*_after_platform_checks` methods without physically
pinning or synchronizing pages. Only a real kernel adapter under A01/A05/A06
can establish DMA, IRQ and ResourceDomain isolation. The registry remains a
separate trusted kernel owner; this crate does not enforce exclusive BDF across
independently constructed DeviceHandles or overlapping MemoryObjects.

## Reproducible offline test command

```sh
bash support/vmm/verify.sh
# Equivalent Rust-only command:
cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline
```

The committed Cargo.lock is a dependency-free lockfile. No Ollama or GPU is
invoked by the test script, including when /dev/nvidia* exists.

**Evidence labels:** Python 50/50 host/fixture suite was previously
reproduced in the tool container; the corrected Rust code has NOT been
compiled there because rustc/cargo are absent. Run the script in A01's
authorized Rust build environment to check the new 17 Rust unit tests and
3 compile-fail doctests. Do NOT mark Rust/OS/GPU pass until those commands
actually succeed and link their unmodified logs.

**A00 ownership:** .github/workflows/** is owned by A00. A09 supplies this
entrypoint only; A00 must add the relevant PR path filter/job. No workflow
permissions were altered by A09.
