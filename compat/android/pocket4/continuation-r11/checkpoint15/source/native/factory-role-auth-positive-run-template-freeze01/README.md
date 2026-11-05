# Owned role authorization run template

This package contains a runtime **template**, not an executed result and not a
request bound to an invented ELF. `make_run_request.py` requires the complete
successful matching build receipt. It substitutes exactly one receipt SHA into
the template and creates a new three-file request. The final stage is root-owned
and create-only under `/run`; it never changes or creates a system account.

The fixed matching build source is
`factory-role-auth-positive-source-freeze01`, manifest
`d400255a4318ec5856692254cff062280021aeea5bf80662eb939a00d7586aa2`.
Its ten cases and complete scope are preserved. There is no listener, public
socket name, namespace change, Android action, snapshot creation, or factory
service. The three capabilities exist only in owned client children. Their
fixture filter is deliberately not the Android production policy.

## Admission and execution

- Require successful actual build-only state, all required compile/dep/link/PLAN
  commands, immutable source, tools and dependencies, qualified owned cgroup,
  and no forced or incomplete cleanup. Hold the exact built ELF and verify its
  complete SHA, inode, executable type and named identity before fd-based exec.
- Re-read the exact seven-file staged build source and compare with the actual
  build inventory. Bind the runtime `ldd` closure exactly to the build library
  inventory. Recheck all sources, ELF, authority and libraries afterward.
- Execute via `sudo -n` inside the existing finite user job. The root Python
  process must remain in that job's exact held cgroup: 50% CPU and 256 MiB RAM;
  one CPU affinity leaves two logical CPUs free. Record memory/swap peaks,
  all memory event deltas and unchanged limits. New OOM/kill/group events fail.
  `memory.swap.max` is observed, not claimed to be finite.
- Only configured UID/GID 61179 absence is checked; there is no account mutation,
  process scan or search for an alternative identity. All client endpoints are
  anonymous, private socketpairs and the role child is nondumpable.
- Root controller is a subreaper. The actual harness deadline is 30 seconds, the
  outer held-ELF child bound is 45 seconds, controller bound is 90 seconds and
  request timeout is 120 seconds. Timeout uses the exact owned PIDFD. Any adopted
  child remaining when the harness finishes fails; emergency cleanup uses only
  owned children and any forced cleanup is a failure.
- Require exactly ten ordered case JSON records plus one aggregate. The aggregate
  must report ten normal direct reaps, one normal nested reap, no forced cleanup,
  and no uncollected child. The source checks per-case descriptor balance. Parent
  cleanup and source/library/resource gates must independently pass.

## Reuse and limits

`run_common.py` is byte-for-byte the earlier owned NOFILE runner's common
functions. `verify_rows` and `held_executable` are also copied verbatim. The new
root scope, ten-case parser and one-ELF runtime body are explicit changes; the
old NOFILE fixture and its 26-case results are not modified or relabeled.

`Main_actions=0` describes code scope only. This runtime does not observe the
Main identity or infer that no resource contention occurred. It does not prove
production filter installation, cross-thread credential transition exclusion,
forced PID reuse, shared-VM PID namespace collision rejection, Android/ART
integration, snapshot provenance, or whole-app readiness. Those remain separate
gates. A successful mechanism result must never be described as enabling the
role service.
