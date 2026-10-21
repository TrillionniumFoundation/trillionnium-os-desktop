# Runner lifecycle host evidence

This directory records host process cleanup and lock ordering. No Rust kernel build or QEMU acceptance is claimed here.

Code: [2eee2c3df5a837e89ae7557510008ce1de37a1ca](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/2eee2c3df5a837e89ae7557510008ce1de37a1ca). The original code is exactly the `run.py` bytes in [b5030737451cd7b57813fc4e3c39665a6bb66cfc](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/b5030737451cd7b57813fc4e3c39665a6bb66cfc); `source-provenance.json` verifies both source hashes without copying production source.

The original runner fails all four real negative controls: a normally exited leader leaves a TERM-ignoring descendant; Ctrl-C leaves its descendant; SIGTERM kills the runner directly; and a busy lock consumes a new output directory. `baseline-frozen-controls.log` inside `logs.tar.gz` uses the final test fixture against the exact original bytes. The fixture cleans its own surviving processes by pidfd.

Final checks: lifecycle **10/10** under `python3 -I` and `python3 -I -O`; existing timeout **1/1** in both modes. The previously completed profile **7/7** checks used identical final logic before a docstring-only edit. Exact commands and source hashes remain in the unmodified `commands.json` and `frozen-report.json`.

`logs.tar.gz` contains all 23 available raw scratch logs, including failures and intermediate attempts. `logs.members.json` gives each original name, size and SHA256. Intermediate `/proc` observation attempts are historical only and were removed because `/proc` PID numbering does not match the caller namespace. The final implementation does not walk `/proc` or enable subreaping.

`existing-runner-final.log` retains a genuine immediate-flock assertion failure. SIGKILL delivery to a descendant is asynchronous; the corrected original test still requires acquisition of the actual lock within two seconds. The new tests additionally require pidfd exit notification and TCP listener release. Production code signals only the group anchored by its unreaped direct child, then reaps that leader. It does not claim to adopt or reap grandchildren, and sends no numeric group signal after reap. Descendants escaping the original group are outside this contract.

To reproduce the negative controls, use a checkout containing commit `2eee2c3df5a837e89ae7557510008ce1de37a1ca`, apply `fixture.patch` in a separate empty directory with `git apply`, and run `python3 -I fixtures/reproduce-runner-baseline.py /absolute/repository`. Expected status is 1 with four failures. This is a newly packaged reproduction recipe; the retained executed caller was the equivalent importlib/unittest invocation described in `commands.json`. Existing evidence directories and failure logs are preserved by the tests.

`SHA256SUMS` covers every delivered regular file except itself. No target, registry, dependency cache, generated binary, or production code copy is included.
