# Narrow ctypes bootstrap ownership probe, revision 1

This candidate has **not run on Pocket4**. It is a single host-only observation
needed to explain the real source-generation FD failure. It creates no Main
binding, acquires no Main/global/flow lock, enters no namespace, invokes no
native Android command, and writes no application or system file. A separate
reviewed bootstrap stages this candidate once in its own new root-private host
directory. Its directly owned child is the only process it may signal, through
a pidfd held before that child receives its release byte.

## Actual failed evidence kept unchanged

The source-only generation attempt `1a1b13a09dc-fc05-7718` failed because its
whole-process descriptor count changed from 4 to 5. Although the inner render
finished, the overall result is failed; neither that generated helper nor the
nonce `77fe9d36efe51cf69813f3411099f049` is reused.

The diagnostic `1a1b155cac9-fc05-77d4` then failed before any Main work. Its first
new descriptor was fd3 for
`/usr/lib/x86_64-linux-gnu/libffi.so.8.2.0`, created during frozen-core import and
configuration. It remained after explicit cleanup; there were no tracked
resources or native commands. The exact observed full stat, including integer
nanoseconds from the original raw JSON, is fixed in this probe. The diagnostic
stdout is 9,093 bytes, SHA256
`046b39cd66008d65c6cddcf9ed2e89a2d117ffaa8702b4c9628d875ca627c4b8`.

## Primary-source explanation and remaining deployed-build check

The local actual successor baseline identifies the launcher interpreter as
`/usr/bin/python3.14`. That does not yet identify the full patch/build version.
The following primary-source chain explains a process-lifetime descriptor:

1. CPython v3.14.0 [`Modules/_ctypes/_ctypes.c`](https://github.com/python/cpython/blob/v3.14.0/Modules/_ctypes/_ctypes.c),
   Git blob `08e00adfd0c3e6d7ae0a2ce6d22cbd986631d5ed`, `_ctypes_mod_exec`,
   allocates and frees one closure during module import to initialize the
   dlmalloc allocator before concurrent use. This is an actual module-import
   operation; it does not require calling the Android namespace helper.
2. CPython v3.14.0 [`Modules/_ctypes/malloc_closure.c`](https://github.com/python/cpython/blob/v3.14.0/Modules/_ctypes/malloc_closure.c),
   blob `80ba96614bff79955ad593455e210d566ff9426f`, routes
   `Py_ffi_closure_alloc` to `ffi_closure_alloc` when available.
3. libffi v3.5.2 [`src/closures.c`](https://github.com/libffi/libffi/blob/v3.5.2/src/closures.c),
   blob `02cf78fa26c0aaadb4af5265d32489ca3e216014`, initializes the static
   trampoline facility when allocating a closure.
4. libffi v3.5.2 [`src/tramp.c`](https://github.com/libffi/libffi/blob/v3.5.2/src/tramp.c),
   blob `76a9dfe75c2c3b407a8b168d249f1b1be1ecf8ba`, opens the mapped libffi
   binary with `O_RDONLY|O_CLOEXEC` in `ffi_tramp_get_libffi`, keeps that
   descriptor in `tramp_globals.fd` on the successful path, and uses it for
   executable table mappings. `ffi_tramp_free` returns a trampoline to its
   table; it does not close that global file descriptor. Manually closing the
   library's descriptor would corrupt its ownership model and could cause
   later mmap calls to use a recycled descriptor number.

These retrieved sources establish the design; the probe binds the actual
deployed Python and `_ctypes` binary hashes/build IDs and the actual libffi file
hash/build ID/symbols to the observed behavior. It does **not** claim the deployed
libffi source is exactly v3.5.2 or that filename `8.2.0` is a package version.
That exact source-build lineage is not established solely by ELF symbol names.

## Exact observation

The parent starts one fresh `python3 -B -I` child, obtains its pidfd, then sends
one release byte. The child requires Python 3.14, no preloaded `_ctypes` or
`ctypes`, and only stdin/stdout/stderr as inherited descriptors.

It captures double-checked descriptor identities after importing `_ctypes`,
then `ctypes`, then the exact pinned `held_runtime_r5.py` source **without
constructing any HeldTarget or MainBinding**, and finally after reading public
runtime identities and running GC. Only the first import may create the one
specific libffi descriptor. Its full stat must match the actual failed
diagnostic, its flags must be read-only and close-on-exec, its current path and
loaded maps must name the same file, and it must remain unchanged at every
subsequent phase. The probe uses `pread` to hash the library-owned descriptor
without changing its file offset. It never closes that descriptor.

The probe records ELF build IDs, the `_ctypes` dependency on `libffi.so.8`,
`PyInit__ctypes`, and bounded public FFI symbols. No arbitrary process maps,
business data, environment variables, or Android files are exported.

The parent drains bounded stdout/stderr, waits for normal child exit and held
pidfd readability, closes its own pipes/pidfd, and requires its original FD
identity set restored. Only then may it report that this child's library FD
lifetime ended with that owned process. A 30-second deadline or any error is
failed, even if the parent's exact pidfd SIGKILL successfully retires its child.
No process-group or numeric-PID signal is permitted. There is no retry.

## Invocation and local controls

The exact on-host worker argv after the separately reviewed root-private stage
is:

```
/usr/bin/python3 -B -I /home/alex/work/pocket4-ffi-bootstrap-probe-20261106-r1/probe_ffi_bootstrap.py --host-only
```

Local controls run with:

```
python3 -B test_probe_controls.py
```

They use real directly owned host child processes/pidfds and temporary files:
normal exit and FD restoration; timeout retirement by one owned pidfd signal;
wrong library identity rejected without closing the file; reused FD identity
and malformed ELF rejected. Passing these controls is not a Pocket4 probe
result. The local interpreter is not substituted for Pocket4's Python 3.14.

## Intended subsequent fix, not applied here

After the actual host observation passes, a new explicit source-preparation
revision can initialize this pinned library resource before Main admission,
record its exact immutable identity as a library-owned bootstrap resource, and
freeze it throughout Main work. All worker-owned resources still close
explicitly; any other new/missing/replaced descriptor still fails. Final
success must also depend on the bounded worker's observed process exit, which
retires the library-private resource. This is neither an unconditional baseline
shift nor a descriptor-count allowance. Old failure receipts remain failed;
the runtime guard, integrity checks, Bili boundary, and Meituan permissions
remain unchanged. No QA, install, production or cleanup success follows from
this host probe alone.
