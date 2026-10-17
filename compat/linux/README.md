# A04 Linux compatibility / pinned Hepta W1 profile

Scope: `compat/linux/**`, `support/rootfs/**`, `tests/workloads/linux/**`.
No kernel/Hepta upstream writes, production service changes, HOS2 wire changes,
permission weakening, new authorizer or root `README.md` content.

## Hepta source-derived execution path and current build receipt

Fixed source SHA: `f8c9419df6ddeb36ff8b522a50219981fb8d9345`.
`codex-hepta-agentd` includes the existing Codex App Server in-process;
`codex-rs/hepta-agentd/src/app_runtime.rs` calls the original
`codex_app_server::run_main_with_transport_options` using a UNIX socket,
`src/runtime.rs` owns the readiness/lifecycle, `src/client.rs` offers the
existing authenticated ObjectiveStart client, and `src/config.rs` requires a
real matching fleet manifest/identity/working directory/Codex home. Actual
canonical intelligence invocation additionally requires the existing host
provider, authority, runner and run record. This is source inspection only.

The fixed source was compiled through the real `runtime_codex_product_e2e`
dependency path on a disposable Linux host. The temporary
`codex-hepta-agentd` ELF has SHA-256
`0a8266635f8dd1b49d5213af4f01aab6c66d7450d9b9e940f71490893ce404ae`, is an
x86_64 PIE using `/lib64/ld-linux-x86-64.so.2`, and has direct NEEDED entries
for `libssl.so.3`, `libcrypto.so.3`, `libgcc_s.so.1`, `libm.so.6`, `libc.so.6`
and the loader. The build also fixed Tokio 1.52.3, SQLx 0.9.0,
libsqlite3-sys 0.37.0, Mio 1.2.0, Socket2 0.6.3, Hyper 1.8.1, Rustls 0.23.45,
OpenSSL 0.10.75 and related versions in `hepta-profile.json`.

The test binary ran but the Wiremock Responses provider received zero requests
and no terminal receipt was produced. `strace` was blocked by the host
(`PTRACE_TRACEME` returned `EPERM`). The binary hash and dependency inventory
are therefore build evidence, not a complete runtime closure. Do not consider
`--help`, daemon readiness, mock-provider startup, or this failed test an E2E
tool-effect pass.

## Real Hepta ELF build and tracing on a disposable, provisioned Linux host

Obtain fixed upstream source in a scratch clone/worktree, without modifying a
running Hepta service. Verify `git rev-parse HEAD` returns the exact fixed SHA.

```sh
cargo build --locked --release --manifest-path hepta-private-ci/codex-rs/Cargo.toml \
  -p codex-hepta-agentd --bin codex-hepta-agentd
sha256sum hepta-private-ci/codex-rs/target/release/codex-hepta-agentd
# Provision genuine HEPTA_FLEET_ROOT/HEPTA_AGENT_ID/HEPTA_AGENT_GENERATION,
# HEPTA_AGENT_HOME/HEPTA_AGENT_RUN_ROOT/CODEX_HOME, fleet manifest, real owners,
# trusted invocation provider, runner, isolated workspace and auth client.
A04_EXPECTED_HEPTA_SHA256=<exact-built-binary-sha256> \
  ./compat/linux/trace-hepta.sh /absolute/path/to/codex-hepta-agentd \
  /new/private/hepta-trace [actual startup flags]
python3 compat/linux/trace_summary.py /new/private/hepta-trace \
  --output /new/private/hepta-aggregate.json \
  --private-path-output /new/private/hepta-runtime-paths.DO_NOT_COMMIT.json
```

`trace-hepta.sh` **requires** the independently pinned expected SHA before
any ELF execution; writes raw `strace -ff -ttt -yy` logs into a **new 0700
private directory** (including stdout/stderr, paths and arguments), and
refuses overwrites. Under a separately authenticated client, submit the real
ObjectiveStart and observe a genuine Codex tool effect. Retain owner/host
assembly and third-party provider status as distinct evidence. A timeout is
incomplete capture, NOT a Linux ABI error; no automatic E2E assertion occurs.

`trace_summary.py` reports **completed** syscalls only. It joins strace
`<unfinished ...>`/`<... resumed>` pairs, attributes returned errno to that
completed call, records unmatched/timed-out calls as `incomplete_syscalls`,
records orphan resumes separately, and excludes kernel-internal `ERESTART*`
from userspace errno counts. Nonzero incomplete/orphan counts set
`trace_completeness=incomplete` and **do not** qualify the observed dependency
closure. The schema-3 public aggregate is **not** proof of end-to-end tool
execution. It emits public-safe syscall/errno counts with *no literal
paths*, and optionally a separate 0600 **private**, unverified candidate file
inventory. Trace-derived candidate files still need resolved loader,
transitive `DT_NEEDED`, runtime dlopen, dynamic configurations, NSS/DNS,
certificates, SQLite WAL, host mounts and services before creating a Hepta
qualified rootfs. Never check in private trace/data/paths or credentials.

## Executable Linux baseline and A01 replay handoff

`tests/workloads/linux/run.py` produces 31 host-passed cases from identical
static/dynamic ELF, actual SQLite WAL/fork/reopen, Linux error semantics and
resource-release observations; Rust/Tokio remains `not_run` in the pinned Linux reference: its reviewed
standalone lock/build is now recorded, but runtime execution is blocked by
managed-host pathname AF_UNIX `EPERM`. `guest.py` layers the pinned
ELF and 28 C cases over A01's **real** tested
initramfs without modifying A01 files. It records QEMU serial/exit and exact
artifact hashes if actually run. The complete shell instructions are in
`tests/workloads/linux/README.md`.

A01 [PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)
reports real fixed Asterinas kernel QEMU startup. That is not equivalent to
A04's workload passing. A temporary, non-system QEMU/SeaBIOS extraction now
boots the pinned A01 kernel/initramfs under TCG and exits 33 with complete boot
markers. The exact Debian13 rootfs and manifest-pinned ELF bytes are still
required for the full A04 replay; Ubuntu-built replacements are rejected.
Ptrace remains restricted, and no such environment limitation is classified as
a kernel ABI bug.

`compare.py` rejects same-ELF hash changes, errno/result differences, missing
cases and guest claims without actual boot evidence; it deliberately allows
concurrency state invariants rather than fixing a scheduler order. The full
guest gate remains incomplete until remaining Python + Tokio runtime cases
are genuinely reprovisioned. Distinguish Linux reference, synthetic parser
unit tests, new-kernel guest and bare metal in every report.


### Measured Linux syscall reference and guarded guest replay

The second-stage Linux host trace uses an actual self-contained x86_64
ptrace syscall collector in tests/workloads/linux/ptrace_trace.c and
ptrace_probe.py, verified against the hash-pinned static/dynamic C and SQLite
ELF bytes plus staged dynamic loader. 28/28 case facts matched; 62 distinct
syscall numbers were observed. The committed compact
sanitized reference separates kernel-internal -ERESTARTSYS=512 from
application-visible errno. Raw traces and operator paths are private.
These are Linux HOST observations, not a new-kernel or Hepta W1 proof.

The executable tests/workloads/linux/replay_qemu.py consumes the already
verified A01 QEMU boot artifacts, checks their hashes against the accepted
kernel/initramfs/SeaBIOS, packs exact A04 ELF, boots disposable single-CPU
TCG (no network, data disks or KVM), and records guest serial/raw exit
and differential. The cloud QEMU prerequisite is now closed by the pinned
QEMU/SeaBIOS boot receipt; the full replay remains blocked until the exact
Debian13 rootfs/ELF archive is supplied. See
tests/workloads/linux/README.md for commands,
negative tests and environment classification. S1 durable block storage
and a genuine authenticated Hepta Agentd tool invocation remain untested.

## Latest exact Linux ELF profile (2026-10-16)

Original Linux: 31 passing cases, 0 failures, Rust/Tokio not run. Fixed-rootfs
chroot and staged loader: 28/28 C ELF cases passed. Numeric ptrace: 28/28
with 62 syscall kinds. New application-level checks cover pathname AF_UNIX
peer credentials and cross-process robust pthread owner-death recovery.

A focused temporary guest archive has already exercised 13 ABI probes on the
pinned A01 guest; the full fixed C subset still requires the exact Debian13
rootfs/ELF archive. The guest parser and replay gate now reject
exit=0/`ok=true` if any pinned
errno, SQLite or IPC observation differs; all 28 packaged C cases must agree.
This has host and synthetic evidence only, not a real Asterinas guest run.

### Host-only rehearsal of the exact guest shell

\`tests/workloads/linux/host_guest_rehearsal.py\` materializes the pinned
17-file rootfs in a disposable chroot, stages a separately hashed host
BusyBox for instrumentation, then runs the **same 28-case shell** to be placed
in A01's initramfs. The actual Debian 13 reference run passed 28/28 and is
recorded in \`tests/workloads/linux/baselines/host-guest-shell-rehearsal-debian13-x86_64.json\`.
It is deliberately recorded as \`qemu_used=false\`, not a kernel result.
The strict serial parser also refuses duplicated/out-of-order markers,
ambiguous JSON and kernel panic output; those are negative host unit tests.
