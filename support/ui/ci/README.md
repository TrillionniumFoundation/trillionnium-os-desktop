# A00-owned GitHub CI handoff

The strict source format check is never silently bypassed. On failure,
the workflow additionally saves an ephemeral `rustfmt.patch` file so A10
can review/apply actual formatter output in a subsequent owned commit,
even if Cargo compilation failed before reaching the formatter gate.

This folder contains a VALID GitHub Actions workflow file but does not
automatically execute; it is intentionally outside .github/workflows/**
because A00 exclusively owns that directory. A00 should review
`a10-host.yml`, copy it into `.github/workflows/a10-host.yml`,
and merge/push through its own integration branch.

The workflow records compiler, unit-test, and rustfmt output (including
failures), the generated ui/Cargo.lock, and software-Wayland logs in a
downloadable a10-host-evidence Actions artifact. The artifact deliberately
excludes runtime sockets and ephemeral app process directories.

Running the workflow must produce actual Cargo build, unit-test and rustfmt
results and print the compiler/OS version. A10 host crates are separate from
the pinned Asterinas kernel nightly. Cargo.lock does not yet exist because
A10's current authoring environment has no Rust compiler or DNS access;
review the generated lockfile and commit it before claiming reproducibility.

On a Linux runner with Weston, Mesa/llvmpipe, and Rust, run
`bash tests/ui/headless-weston.sh`. It starts/stops its own Weston compositor
inside a private runtime, then calls `bash tests/ui/smoke-wayland.sh`.
The handoff CI workflow includes both Cargo host tests and this smoke step.
When Weston is absent the script explicitly fails, not skips/claims success.

On an already running Wayland workstation, execute
`bash tests/ui/smoke-wayland.sh` directly. This smoke checks two native app child
PIDs, both first-egui-update markers, Shell restart and cancellation. It
does NOT attest compositor-mapped surfaces, real CJK candidate UI, GPU
reset, permissions or new kernel boot. Never collapse host GUI checks into
the HOS2/N0 OS gate.

Even when A00 installs a workflow variant without a separate formatter-patch
step, the A10-owned `tests/ui/check-host.sh` produces
`$RUNNER_TEMP/a10/rustfmt.patch` on a formatting failure and exits nonzero.
The existing `a10-host-evidence` artifact path includes this patch.

If CI fails, preserve real logs, patch the Rust code, regenerate a reviewed
lockfile, rerun; do not silently remove tests or call no-run code VERIFIED.

The A10-owned `check-host.sh` now performs an EXIT-stage format check even
if Cargo compilation or Rust tests fail earlier. It writes both
`rustfmt-check.log` and, when needed, `rustfmt.patch` to the already
configured `$RUNNER_TEMP/a10/` artifact directory. The hook never converts
an earlier build/test failure into a success or invokes a GUI.
