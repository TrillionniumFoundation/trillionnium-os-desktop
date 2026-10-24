# Original native owner product kernel build

`build_native_owner_kernel.py` builds a reviewed original Agentd executable into
the existing `g2-trusted-daemon` product profile. It uses the original local OSDK
installation and `support/build/kernel.sh kernel`. It does not run the executable
or start QEMU. A successful result is a build input for `run_native_owner.py`,
not evidence that native Hepta, recovery or sustained CPU control has passed.

## Required inputs

The source review, its explicit SHA-256, the two clean source roots, the successful
original entry build receipt and its explicit SHA-256 must describe the same
complete source pair. The wrapper calls the existing `owner_build` gate before
either compilation command. An oversized owner, changed source, changed release
profile or unsuccessful original packaging fails at this point. The owner file
limit remains 8 MiB and its original static LOAD span limit remains 16 MiB.

Use a private kernel Cargo home with the original `cargo`, `rustc` and `rustup`
proxies and cached dependencies. Supply the actual Rustup directory explicitly.
The wrapper verifies the installed `nightly-2026-07-21` Cargo and rustc commit
identities and records their actual binary hashes. It always rebuilds OSDK from
the exact reviewed OS worktree: `OSDK_LOCAL_DEV=1` embeds source paths, so an OSDK
binary built from a different worktree is not reused.

The Cargo home, OSDK target, kernel target, source roots, VDSO directory and new
evidence directory must be canonical and disjoint. Stable advisory locks cover
the three mutable Cargo resources until artifact retention and verification
finish. The original kernel wrapper also holds its own workspace lock. Builders
which do not use these advisory locks must be coordinated separately.

Every path argument is explicit. For example, after assigning these variables
to actual canonical paths and verified input hashes:

```sh
python3 -B "$TASK_HARNESS/tests/workloads/hepta_cpu_control/build_native_owner_kernel.py" \
  --source-review "$TASK_REVIEW" \
  --source-review-sha256 "$TASK_REVIEW_SHA256" \
  --desktop-source "$TASK_OS_SOURCE" \
  --hepta-source "$TASK_HEPTA_SOURCE" \
  --owner-build-receipt "$TASK_OWNER_BUILD/result.json" \
  --owner-build-sha256 "$TASK_OWNER_BUILD_SHA256" \
  --owner-elf "$TASK_OWNER_ELF" \
  --cargo-home "$TASK_KERNEL_CARGO" \
  --rustup-home "$TASK_RUSTUP_DIR" \
  --osdk-target "$TASK_OSDK_TARGET" \
  --kernel-target "$TASK_KERNEL_TARGET" \
  --vdso-directory "$TASK_VDSO_DIR" \
  --vdso-sha256 "$TASK_VDSO_SHA256" \
  --busybox "$TASK_BUSYBOX" \
  --busybox-sha256 "$TASK_BUSYBOX_SHA256" \
  --output "$TASK_NEW_KERNEL_EVIDENCE" \
  --jobs 2
```

The output parent and both target directories must already exist. The output
directory itself must not exist. Timeouts bound the two host build commands;
they do not change any guest authorization, watchdog or grant lifetime.

## Original commands and retained evidence

`pipeline.json` contains exactly two compilation steps, with their actual argv,
working directories, raw log hashes, exit codes and elapsed times:

1. `cargo +nightly-2026-07-21 install --offline --locked --force cargo-osdk
   --path <reviewed-os>/kernel/asterinas/osdk --target-dir <osdk-target>`.
2. `/bin/bash <reviewed-os>/support/build/kernel.sh kernel`, with only the
   existing G2 selector enabled and its reviewed original owner input.

The Make overlay must forward `--features=g2-trusted-daemon` after overriding
the upstream common arguments. `test_g2_product_profile.py` checks that actual
GNU Make expansion. Its dry-run tests do not compile a kernel.

The wrapper retains full original OS source snapshots before and after the
build, both repositories' original owner snapshots, the unchanged source review
bytes, actual OSDK binary, real stage logs and all files produced by the original
kernel wrapper. It copies the actual generated product lock from
`<kernel-target>/osdk/asterinas-run-base/Cargo.lock` and requires exact equality
to the original fixed 204-package lock.

The product ELF is selected by the actual OSDK Run bundle at
`<kernel-target>/osdk/asterinas/bundle.toml`. The manifest's `aster_bin.path`
identifies the single converted multiboot ELF member. The wrapper retains the
unmodified manifest as `kernel-build/osdk-bundle.toml`, checks its actual release
profile, G2 feature and default compiler settings, and verifies its initramfs
against the original kernel wrapper's retained image. It never selects a file
by globbing a target cache or taking a kernel-test ELF.

`product-kernel.elf` must have the original OSDK ELF64/EM_386 multiboot header and
contain the entire reviewed original owner image from the original
`include_bytes!` input. The recorded offset and SHA-256 come from these actual
bytes. The source Cargo artifacts and original owner are not rewritten.

Before completion, the wrapper runs the existing
`native_owner_inputs.kernel_build` consumer gate against the retained directory.
The consumer will run this gate again when `run_native_owner.py` consumes the
explicit final pipeline hash. All command failures, timeouts and validation
failures retain a false result and their original logs in the new evidence
directory. A failed directory is not reused.

## Scope of tests

```sh
python3 -B -m unittest discover \
  -s tests/workloads/hepta_cpu_control \
  -p test_build_native_owner_kernel.py -v
```

These tests exercise real local advisory-lock contention, canonical-path
rejection, immutable artifact copies, a failing subprocess with unchanged CRLF
output, and actual timeout termination. They do not fabricate a successful
kernel pipeline or claim a native owner execution. The actual product build and
each native guest scenario remain separate acceptance steps.
