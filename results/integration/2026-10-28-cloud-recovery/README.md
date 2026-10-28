# Cloud recovery: A04/A10 host boundaries

Observed 2026-10-28 in a restored Linux x86_64 cloud environment as UID 1000.
Remote main was `38227d33fd3ed668f0424bc153e0d3d811731597`.
The current product candidate was PR276 at
`745c0731aed270ee394145c6767371a6af47f49f`, tree
`fa70b1b95206d25775009c6965245d34051468a4`, already containing main.
An isolated worktree and new branch retained the original mounted worktree.
No original owner's branch, target cache, device or deployment was modified.
PR276 describes an original product build; its remote process liveness was not
observable here, so that build was not duplicated.

## Changes and executed identity

Code commit: `e8d6c432a4b16ba67ed85bd07d749d12ac01a397`.
Code tree: `f082a0c3613c990c8abf01c214fc82f139d71657`.
The logs were produced against these working source bytes before committing.
This later evidence-only commit does not claim additional product execution.

- Rootfs extraction compared absolute manifest names against relative keys.
  Duplicate entries were rejected only after writing the destination. The
  existing final verification did reject them; this was not a successful
  verification bypass. Duplicates now fail before opening the archive.
- A double-slash manifest path retained an absolute parent after stripping
  one slash, looping forever at `/`. The original synthetic child hit its
  two-second bound and was killed/reaped. Such paths now fail before archive
  access. The regression runs in a subprocess with a five-second bound.
- The differential comparator could match empty reports, omitted observations,
  missing ELF inventories and bool/int-equivalent facts. It now requires a
  passed reference, recorded ELF identity and observations, and compares
  nested JSON types strictly. This is not a complete report-schema validator.
- The A10 shared-parent test requested 0755 through mkdir under umask 0077,
  actually creating a private directory. It now explicitly chmods its own
  disposable fixture to 0755, preserving the original refusal assertion.

## Actual host checks

| Command / scope | Result |
| --- | --- |
| `python3 -B -m unittest discover -s support/ui -p test_product_dependencies.py -v` | 41 passed |
| `python3 -B -W error::ResourceWarning -m unittest discover -s support/ui/product -p 'test_*.py' -v` | Original: 88 passed, 1 failed, 4 skipped. Fixed: 89 passed, 4 skipped, 93 total |
| `umask 0022; python3 -B -m unittest discover -s support/ui/product -p test_desktop.py -v` | 46 passed; fixed full product run above used inherited 0077 |
| `python3 -B -m unittest discover -s tests/workloads/linux -p test_rootfs_tar.py -v` | Duplicate red control: two failing subtests. Final: 6 passed; `-O` also 6 passed |
| `python3 -B tests/workloads/linux/test_compare.py` | Final 15 passed; `-O` also 15 passed. Both original red stages retained |
| `python3 -B tests/workloads/linux/test_replay_qemu.py` | 9 passed: host oracle tests, no QEMU executed |
| `python3 -B tests/workloads/linux/test_trace_summary.py` | 11 passed |
| `python3 -B -m unittest discover -s support/ui -p test_build_target_lease.py -v` | 4 passed |
| `python3 -B tests/workloads/linux/test_full_ubuntu_profile.py` | 28 passed, 1 error: missing exact `/usr/bin/python3.12`; unchanged and unqualified |

All test data was synthetic. Four product cases require actual Root and were
skipped, not counted as passes. Python was 3.12.14 from the cloud tool runtime;
it does not supply the fixed system-interpreter path required by the Ubuntu
fixture. No privileged installation was attempted to manufacture that input.
Original failures, reproduction scripts and raw logs are under `host/` and
`a04/`; reproduction scripts retain their original execution paths and must
be pointed at the original candidate to reproduce the old defects.

## Current remote observations and remaining boundaries

`host/remote-snapshot.json` retains connector snapshots. PR215 was already
closed/merged through the later convergence; it is not a current conflict.
PR196 transport lookup failed twice, so its present PR state is not asserted.
The five returned PR276 runs and PR277 Root fixture run 40556935271 were
completed/success. The API is limited to the first page of PR-triggered runs;
this is not a complete required-check inventory. PR277 job 122375390295
reported successful execution of its original two privileged fixtures.
These are remote CI observations, not local executions of this new commit.

The ARM workflow on PR276 still pins historical Hepta `f8c9419`; its success
does not qualify the product's `a39a087` dependency on ARM. This environment
has no discovered Rust, Cargo, QEMU, Xvfb or /dev/kvm. It performed no native
kernel, graphical product, ARM, macOS, physical ExFAT disk, Windows runtime
or Memory release validation. No user Mac was accessed. Real login/model,
Notes effects/readback and privileged target installation remain with the
original owner and its existing authorization boundary. No merge, deployment,
security permission change or CI rerun was performed.

Personal context was unavailable; gh API calls returned Forbidden. Authorized
Git reads and the connected GitHub tools provided the recorded current state.
No credentials or access controls were changed to work around those failures.
